import logging
import traceback
import yaml

from pathlib import Path
from rich.logging import RichHandler
from simple_parsing import parse
from unidiff import PatchSet

from swe_agent.application.action_arguments import ActionsArguments
from swe_agent.application.application import Application
from swe_agent.application.application_arguments import ApplicationArguments
from swe_agent.swe_agent.agent.agent_arguments import AgentArguments
from swe_agent.swe_agent.agent.agents import Agent
from swe_agent.swe_agent.model.model_arguments import ModelArguments
from swe_agent import DevelopmentEnvironmentArguments
from swe_agent.development_environment.development_environment import DevelopmentEnvironment

handler = RichHandler(show_time=False, show_path=False)
handler.setLevel(logging.DEBUG)
logger = logging.getLogger("run_dev")
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)
logger.propagate = False
logging.getLogger("simple_parsing").setLevel(logging.WARNING)


def main(application_arguments: ApplicationArguments):
    application = Application(application_arguments, logger)
    logger.info(f"📙 Arguments: {application_arguments.dumps_yaml()}")
    agent = Agent(name="primary", agent_arguments=application_arguments.agent)
    development_environment = DevelopmentEnvironment(application_arguments.development_environment_arguments)
    application.create_trajectory_directory()
    application.save_arguments()

    for task_count in range(len(development_environment.get_git_communication_management().get_path_to_sourcecode_repository())):
        try:
            # Reset environment
            instance_id = development_environment.get_git_communication_management().get_path_to_sourcecode_repository()[task_count]["instance_id"]
            if application.should_skip(instance_id):
                continue
            logger.info("▶️ Beginning task " + str(task_count))

            reset_commandline_response, info = development_environment.reset(task_count)
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

            agent_setup_arguments = {
                "issue": issue,
                "files": files,
                "test_files": test_files,
                "tests": tests
            }
            info, trajectory = agent.run(
                agent_setup_arguments=agent_setup_arguments,
                development_environment=development_environment,
                previous_commandline_response=reset_commandline_response,
                trajectory_directory=application.get_trajectory_directory(),
                return_type="info_trajectory",
            )
            application.save_predictions(instance_id, info)
            if application_arguments.actions.open_pr and application.should_open_pr(info, token=development_environment.get_git_communication_management().get_token()):
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
        sourcecode_repository_path="princeton-nlp/SWE-bench_Lite",
        sourcecode_repository_type="HuggingFace",
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
        development_environment_arguments=development_environment_arguments,
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
    application_arguments = parse(ApplicationArguments, default=defaults, add_config_path_arg=False)
    main(application_arguments)
