import json
import os
import re
from getpass import getuser
from pathlib import Path
from typing import Dict, Any

from swebench import KEY_MODEL, KEY_INSTANCE_ID, KEY_PREDICTION

from swe_agent.development_environment.utils import get_gh_issue_data, InvalidGithubURL, parse_gh_issue_url, \
    get_associated_commit_urls


class Application:

    def __init__(self, application_arguments, logger):
        self.application_arguments = application_arguments
        self.trajectory_path = None
        self.logger = logger

    def save_arguments(self):
        """Save the arguments to a yaml file to the run's trajectory directory."""
        log_path = self.trajectory_path / "args.yaml"

        if log_path.exists():
            try:
                other_args = self.application_arguments.load_yaml(log_path)
                if self.application_arguments.dumps_yaml() != other_args.dumps_yaml():  # check yaml equality instead of object equality
                    self.logger.warning("**************************************************")
                    self.logger.warning("Found existing args.yaml with different arguments!")
                    self.logger.warning("**************************************************")
            except Exception as e:
                self.logger.warning(f"Failed to load existing args.yaml: {e}")

        with log_path.open("w") as f:
            self.application_arguments.dump_yaml(f)

    def should_skip(self, instance_id):
        """Check if we should skip this instance based on the instance filter and skip_existing flag."""
        # Skip instances that don't match the instance filter
        if re.match(self.application_arguments.instance_filter, instance_id) is None:
            self.logger.info(f"Instance filter not matched. Skipping instance {instance_id}")
            return True

        # If flag is set to False, don't skip
        if not self.application_arguments.skip_existing:
            return False

        # Check if there's an existing trajectory for this instance
        log_path = self.trajectory_path / (instance_id + ".traj")
        if log_path.exists():
            with log_path.open("r") as f:
                data = json.load(f)
            # If the trajectory has no exit status, it's incomplete and we will redo it
            exit_status = data["info"].get("exit_status", None)
            if exit_status == "early_exit" or exit_status is None:
                self.logger.info(f"Found existing trajectory with no exit status: {log_path}")
                self.logger.info("Removing incomplete trajectory...")
                os.remove(log_path)
            else:
                self.logger.info(f"⏭️ Skipping existing trajectory: {log_path}")
                return True
        return False

    def create_trajectory_directory(self):
        self.trajectory_path = Path("trajectories") / Path(getuser()) / self.application_arguments.run_name
        os.makedirs(self.trajectory_path, exist_ok=True)

    def get_trajectory_path(self):
        return self.trajectory_path

    def save_predictions_json(self, instance_id, info):
        output_file = Path(self.trajectory_path) / "all_predictions.json"
        model_patch = info["submission"] if "submission" in info else None
        datum = {
            KEY_MODEL: Path(self.trajectory_path).name,
            KEY_INSTANCE_ID: instance_id,
            KEY_PREDICTION: model_patch,
        }
        with open(output_file, "a+") as fp:
            print(json.dumps(datum), file=fp, flush=True)
        self.logger.info(f"Saved predictions to {output_file}")

    def should_open_pr(self, info: Dict[str, Any], *, token: str = "") -> bool:
        """Does opening a PR make sense?"""
        if not info.get("submission"):
            self.logger.info("Not openening PR because submission was made.")
            return False
        if info["exit_status"] != "submitted":
            self.logger.info("Not openening PR because exit status was %s and not submitted.", info["exit_status"])
            return False
        try:
            issue = get_gh_issue_data(self.application_arguments.sourcecode_repository_path, token=token)
        except InvalidGithubURL:
            self.logger.info("Currently only github is supported to open PRs to. Skipping PR creation.")
            return False
        if issue.state != "open":
            self.logger.info(f"Issue is not open (state={issue.state}. Skipping PR creation.")
            return False
        if issue.assignee:
            self.logger.info("Issue is already assigned. Skipping PR creation. Be nice :)")
            return False
        if issue.locked:
            self.logger.info("Issue is locked. Skipping PR creation.")
            return False
        org, repo, issue_number = parse_gh_issue_url(self.application_arguments.sourcecode_repository_path)
        associated_commits = get_associated_commit_urls(org, repo, issue_number, token=token)
        if associated_commits:
            commit_url_strs = ", ".join(associated_commits)
            if self.application_arguments.actions.skip_if_commits_reference_issue:
                self.logger.info(f"Issue already has associated commits (see {commit_url_strs}). Skipping PR creation.")
                return False
            else:
                self.logger.warning(
                    f"Proceeding with PR creation even though there are already commits "
                    "({commit_url_strs}) associated with the issue. Please only do this for your own repositories "
                    "or after verifying that the existing commits do not fix the issue."
                )
        return True
