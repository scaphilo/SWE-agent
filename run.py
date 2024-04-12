import json
import logging
import os
import re
import traceback
from typing import Any, Dict
import yaml

from getpass import getuser
from pathlib import Path
from rich.logging import RichHandler
from simple_parsing import parse

from swe_agent.application.action_arguments import ActionsArguments
from swe_agent.application.application_arguments import ApplicationArguments
from swe_agent.swe_agent.agent.agent_arguments import AgentArguments
from swe_agent.swe_agent.agent.agents import Agent
from swe_agent.swe_agent.model.model_arguments import ModelArguments
from swe_agent import DevelopmentEnvironmentArguments
from swe_agent.development_environment.development_environment import DevelopmentEnvironment

from swebench import KEY_INSTANCE_ID, KEY_MODEL, KEY_PREDICTION
from unidiff import PatchSet

from swe_agent.development_environment.utils import InvalidGithubURL, get_associated_commit_urls, get_gh_issue_data, parse_gh_issue_url

handler = RichHandler(show_time=False, show_path=False)
handler.setLevel(logging.DEBUG)
logger = logging.getLogger("run_dev")
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)
logger.propagate = False
logging.getLogger("simple_parsing").setLevel(logging.WARNING)


def main(application_arguments: ApplicationArguments):
    logger.info(f"📙 Arguments: {application_arguments.dumps_yaml()}")
    agent = Agent(name="primary", agent_arguments=application_arguments.agent)
    development_environment = DevelopmentEnvironment(application_arguments.environment)

    trajectories_path = Path("trajectories") / Path(getuser()) / application_arguments.run_name
    os.makedirs(trajectories_path, exist_ok=True)

    save_arguments(trajectories_path, application_arguments)

    for index in range(len(development_environment.get_git_communication_management().get_data())):
        try:
            # Reset environment
            instance_id = development_environment.get_git_communication_management().get_data()[index]["instance_id"]
            if should_skip(application_arguments, trajectories_path, instance_id):
                continue
            logger.info("▶️  Beginning task " + str(index))

            observation, info = development_environment.reset(index)
            if info is None:
                continue

            # Get info, patch information
            issue = development_environment.get_git_communication_management().get_query()
            files = []
            if "patch" in development_environment.get_git_communication_management().get_record():
                files = "\n".join(
                    [f"- {x.path}" for x in PatchSet(development_environment.get_git_communication_management().get_record()["patch"]).modified_files]
                )
            # Get test files, F2P tests information
            test_files = []
            if "test_patch" in development_environment.get_git_communication_management().get_record():
                test_patch_obj = PatchSet(development_environment.get_git_communication_management().get_record()["test_patch"])
                test_files = "\n".join(
                    [f"- {x.path}" for x in test_patch_obj.modified_files + test_patch_obj.added_files]
                )
            tests = ""
            if "FAIL_TO_PASS" in development_environment.get_git_communication_management().get_record():
                tests = "\n".join([f"- {x}" for x in development_environment.get_git_communication_management().get_record()["FAIL_TO_PASS"]])

            setup_args = {
                "issue": issue,
                "files": files,
                "test_files": test_files,
                "tests": tests
            }
            info, trajectory = agent.run(
                setup_args=setup_args,
                env=development_environment,
                observation=observation,
                traj_dir=trajectories_path,
                return_type="info_trajectory",
            )
            save_predictions(trajectories_path, instance_id, info)
            if application_arguments.actions.open_pr and should_open_pr(application_arguments, info, token=development_environment.get_git_communication_management().get_token()):
                development_environment.get_git_communication_management().open_pull_request(application_arguments.actions, info, trajectory)

        except KeyboardInterrupt:
            logger.info("Exiting InterCode environment...")
            development_environment.close()
            break
        except Exception as e:
            traceback.print_exc()
            logger.warning(f"❌ Failed on {development_environment.get_git_communication_management().get_record()['instance_id']}: {e}")
            development_environment.get_docker_communication().reset_container()
            continue


def should_open_pr(args, info: Dict[str, Any], *, token: str="") -> bool:
    """Does opening a PR make sense?"""
    if not info.get("submission"):
        logger.info("Not openening PR because submission was made.")
        return False
    if info["exit_status"] != "submitted":
        logger.info("Not openening PR because exit status was %s and not submitted.", info["exit_status"])
        return False
    try:
        issue = get_gh_issue_data(args.environment.data_path, token=token)
    except InvalidGithubURL:
        logger.info("Currently only github is supported to open PRs to. Skipping PR creation.")
        return False
    if issue.state != "open":
        logger.info(f"Issue is not open (state={issue.state}. Skipping PR creation.")
        return False
    if issue.assignee:
        logger.info("Issue is already assigned. Skipping PR creation. Be nice :)")
        return False
    if issue.locked:
        logger.info("Issue is locked. Skipping PR creation.")
        return False
    org, repo, issue_number = parse_gh_issue_url(args.environment.data_path)
    associated_commits = get_associated_commit_urls(org, repo, issue_number, token=token) 
    if associated_commits:
        commit_url_strs = ", ".join(associated_commits)
        if args.actions.skip_if_commits_reference_issue:
            logger.info(f"Issue already has associated commits (see {commit_url_strs}). Skipping PR creation.")
            return False
        else:
            logger.warning(
                f"Proceeding with PR creation even though there are already commits "
                "({commit_url_strs}) associated with the issue. Please only do this for your own repositories "
                "or after verifying that the existing commits do not fix the issue."
            )
    return True


def save_arguments(traj_dir, args):
    """Save the arguments to a yaml file to the run's trajectory directory."""
    log_path = traj_dir / "args.yaml"

    if log_path.exists():
        try:
            other_args = args.load_yaml(log_path)
            if (args.dumps_yaml() != other_args.dumps_yaml()):  # check yaml equality instead of object equality
                logger.warning("**************************************************")
                logger.warning("Found existing args.yaml with different arguments!")
                logger.warning("**************************************************")
        except Exception as e:
            logger.warning(f"Failed to load existing args.yaml: {e}")

    with log_path.open("w") as f:
        args.dump_yaml(f)


def should_skip(args, traj_dir, instance_id):
    """Check if we should skip this instance based on the instance filter and skip_existing flag."""
    # Skip instances that don't match the instance filter
    if re.match(args.instance_filter, instance_id) is None:
        logger.info(f"Instance filter not matched. Skipping instance {instance_id}")
        return True

    # If flag is set to False, don't skip
    if not args.skip_existing:
        return False

    # Check if there's an existing trajectory for this instance
    log_path = traj_dir / (instance_id + ".traj")
    if log_path.exists():
        with log_path.open("r") as f:
            data = json.load(f)
        # If the trajectory has no exit status, it's incomplete and we will redo it
        exit_status = data["info"].get("exit_status", None)
        if exit_status == "early_exit" or exit_status is None:
            logger.info(f"Found existing trajectory with no exit status: {log_path}")
            logger.info("Removing incomplete trajectory...")
            os.remove(log_path)
        else:
            logger.info(f"⏭️ Skipping existing trajectory: {log_path}")
            return True
    return False


def save_predictions(traj_dir, instance_id, info):
    output_file = Path(traj_dir) / "all_preds.jsonl"
    model_patch = info["submission"] if "submission" in info else None
    datum = {
        KEY_MODEL: Path(traj_dir).name,
        KEY_INSTANCE_ID: instance_id,
        KEY_PREDICTION: model_patch,
    }
    with open(output_file, "a+") as fp:
        print(json.dumps(datum), file=fp, flush=True)
    logger.info(f"Saved predictions to {output_file}")


if __name__ == "__main__":
    model = ModelArguments(
        model_name="gpt-3.5-turbo-1106",
        total_cost_limit=0.0,
        per_instance_cost_limit=3.0,
        temperature=0.0,
        top_p=0.95,
    )
    config_file = Path("config/default.yaml")
    development_environment_arguments = DevelopmentEnvironmentArguments(
        image_name="ghcr.io/scaphilo/swe-agent-environment:main",
        data_path="princeton-nlp/SWE-bench_Lite",
        split="dev",
        verbose=True,
        install_environment=False,
    )
    agent_arguments = AgentArguments(
        model=model,
        config_file=config_file,
    )
    defaults = ApplicationArguments(
        suffix="",
        environment=development_environment_arguments,
        skip_existing=True,
        agent=agent_arguments,
        actions=ActionsArguments(open_pr=False, skip_if_commits_reference_issue=True),
    )

    # Nicer yaml dumping of multiline strings
    def multiline_representer(dumper, data):
        """configures yaml for dumping multiline strings
        Ref: https://stackoverflow.com/questions/8640959/how-can-i-control-what-scalar-form-pyyaml-uses-for-my-data
        """
        if data.count("\n") > 0:  # check for multiline string
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    yaml.add_representer(str, multiline_representer)

    args = parse(ApplicationArguments, default=defaults, add_config_path_arg=False)
    main(args)
