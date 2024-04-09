import os
import random
import subprocess
from typing import Tuple

import config
from ghapi.core import GhApi
from git import Repo

from swe_agent.environment.utils import get_instances, get_gh_issue_data, parse_gh_issue_url, parse_gh_repo_url, \
    format_trajectory_markdown, copy_file_to_container

from swebench import (
    get_environment_yml,
    get_requirements,
    MAP_VERSION_TO_INSTALL
)
PATH_TO_REQS = "/root/requirements.txt"
PATH_TO_ENV_YML = "/root/environment.yml"


class GitCommunicationManagement:
    def __init__(self, data_path, is_github_url, split, idx, logger, install_python_environment,
                 no_mirror, docker_communication, timeout):
        self.docker_communication = docker_communication
        self.idx = idx
        self.split = split
        self.no_mirror = no_mirror
        self.install_python_environment = install_python_environment
        self.logger = logger
        self.data_path = data_path
        self.base_commit = None
        self.is_github_url = is_github_url
        self.timeout = timeout
        self.token = os.environ.get("GITHUB_TOKEN", None)
        # Get commit hash
        try:
            repo = Repo(search_parent_directories=True)
            self.commit_sha = repo.head.object.hexsha
        except KeyboardInterrupt:
            raise
        except:
            logger.warning("Failed to get commit hash for this repo")
            self.commit_sha = None

        if (self.token is None or self.token == "") and os.path.isfile(
                os.path.join(os.getcwd(), "keys.cfg")
        ):
            self.cfg = config.Config(os.path.join(os.getcwd(), "keys.cfg"))
            self.token = self.cfg.get("GITHUB_TOKEN", "git")
        self.data = get_instances(self.data_path, self.base_commit, self.split, token=self.token)
        self.record = self.data[idx]
        self.logger.info(f"💽 Loaded dataset from {self.data_path}")

    def get_data(self):
        return self.data

    def get_record(self):
        return self.record

    def get_token(self):
        return self.token

    def open_pull_request(self, action_config, info, trajectory):
        """Create PR to repository"""
        self.logger.info("Opening PR")
        # todo: have better way of handling this
        # Adding random string suffix to avoid name conflicts if we had a previously failed run
        issue_url = self.data_path
        issue = get_gh_issue_data(issue_url, token=self.token)
        branch_name = f"swe-agent-fix-#{issue.number}-" + str(random.random())[2:10]

        self.docker_communication.communicate_with_handling(
            input=f"rm model.patch",
            error_msg="Failed to remove model patch",
            timeout_duration=10,
        )
        self.docker_communication.communicate_with_handling(
            input=f"git checkout -b {branch_name}",
            error_msg="Failed to switch to new branch",
            timeout_duration=10,
        )
        self.docker_communication.communicate_with_handling(
            input=f"git add .",
            error_msg="Failed to add commits",
            timeout_duration=10,
        )
        self.docker_communication.communicate_with_handling(
            input=f"git commit -m 'Fix: {issue.title}' -m 'Closes #{issue.number}' ",
            error_msg="Failed to commit changes",
            timeout_duration=10,
        )
        # If users want to push to a fork, we add a new remote and push to that
        # otherwise, we push to 'origin' which has already been set up
        remote = "origin"
        if not action_config.push_gh_repo_url:
            owner, repo, _ = parse_gh_issue_url(issue_url)
        else:
            owner, repo = parse_gh_repo_url(action_config.push_gh_repo_url)
        if action_config.push_gh_repo_url:
            fork_url = f"https://{self.token}@github.com/{owner}/{repo}.git"
            self.docker_communication.communicate_with_handling(
                input=f"git remote add fork {fork_url}",
                error_msg="Failed to create new git remote",
                timeout_duration=10,
            )
            remote = "fork"
        self.docker_communication.communicate_with_handling(
            input=f"git push {remote} {branch_name}",
            error_msg=(
                "Failed to push branch to remote. Please check your token and permissions. "
                "You might want to push to a fork with the push_gh_repo_url option."
            ),
            timeout_duration=10,
        )

        # todo: add representation of trajectory to PR body
        body = (
            f"This is a PR opened by AI tool [SWE Agent](https://github.com/princeton-nlp/SWE-agent/) "
            f"to close [#{issue.number}]({issue_url}) ({issue.title}).\n\nCloses #{issue.number}."
        )
        body += "\n\n" + format_trajectory_markdown(trajectory)
        api = GhApi(token=self.token)
        pr_info = api.pulls.create(
            owner=owner,
            repo=repo,
            title=f"SWE-agent[bot] PR to fix: {issue.title}",
            head=branch_name,
            base="main",
            body=body,
            draft=True,
        )
        self.logger.info(
            f"🎉 PR created as a draft at {pr_info.html_url}. Please review it carefully, push "
            "any required changes onto the branch and then click "
            "'Ready for Review' to bring it to the attention of the maintainers."
        )

    def reset(self, index: int = None, apply_test_patch: bool = False) -> Tuple[str, dict]:
        """
        Function to reset container between each task instance.
        * Clones instance's repository
        * Cleans repository of prior modifications
        * Resets environment variables
        * Check out base commit

        Arguments:
            index (`int`) - index of task instance to reset to
        Returns:
            observation (`str`) - output from container
            info (`dict`) - additional information (e.g. debugging information)
        """
        info = {}
        info["commit_sha"] = self.commit_sha

        # Get task instance
        self.idx = index if index is not None else self.idx
        self.idx += 1

        # Set query, gold command
        self.base_commit = self.record["base_commit"]
        self.query = self.record["problem_statement"]
        self.reward = None

        ### Reset Container ###

        # Clone repository if not already cloned
        self.docker_communication.communicate(input="cd /")
        folders = self.docker_communication.communicate(input="ls").split("\n")
        repo_name = self.record["repo"].replace("/", "__")
        if repo_name not in folders:
            if not self.no_mirror and not self.is_github_url:
                self.logger.info(f"{repo_name} not found in container, cloning...")
                self.docker_communication.communicate_with_handling(
                    input=f"git clone https://{self.token}@github.com/swe-bench/{repo_name}.git",
                    error_msg="Failed to clone repository from mirror",
                    timeout_duration=self.timeout,
                )
            else:
                self.logger.info(f"Trying to clone from non-mirror...")
                self.docker_communication.communicate_with_handling(
                    input=f"git clone https://{self.token}@github.com/{self.record['repo']}.git {repo_name}",
                    error_msg="Failed to clone repository from non-mirror",
                    timeout_duration=self.timeout,
                )

        # Clean repository of any modifications + Checkout base commit
        for cmd in [
            "echo -n > /root/files_to_edit.txt",
            f"cd {repo_name}",
            "export ROOT=$(pwd -P)",
            "git status",
            "git restore .",
            f"git reset --hard {self.base_commit}",
            "git clean -fdxq",
        ]:
            self.docker_communication.communicate_with_handling(
                input=cmd,
                error_msg="Failed to clean repository",
            )

        # Reset environment variables
        for cmd in [
            'export CURRENT_FILE=""',
            "export CURRENT_LINE=0",
            "export SEARCH_RESULTS=()",
            "export SEARCH_FILES=()",
            "export SEARCH_INDEX=0",
        ]:
            self.docker_communication.communicate_with_handling(
                input=cmd,
                error_msg="Failed to reset environment variables",
            )

        # Set up environment
        self.docker_communication.communicate_with_handling(
            "source /root/miniconda3/etc/profile.d/conda.sh",
            error_msg="Failed to source conda",
        )

        system = self.docker_communication.communicate("uname -s").strip().lower()
        arch = self.docker_communication.communicate("uname -m").strip().lower()
        if system == 'linux' and arch == 'x86_64':
            self.docker_communication.communicate_with_handling(
                f"apt update; apt install build-essential -y",
                error_msg="Failed to install build-essential",
                timeout_duration=self.timeout,
            )

        # Call install environment helper function if specified
        if self.install_python_environment:
            if self.is_github_url:
                self.logger.warning((
                    "install_environment is set to True, but the data path is a GitHub URL. "
                    "Skipping conda environment installation."
                ))
            else:
                self.install_env()
        # Install mypy for linting purposes
        self.docker_communication.communicate_with_handling(
            f"pip install flake8",
            error_msg="Failed to install flake8 (lint library)"
        )

        # Apply test patch for oracle setting
        if apply_test_patch:
            path_to_patch = "test.patch"
            with open(path_to_patch, "w") as f:
                f.write(self.record["test_patch"])
            subprocess.run(
                f"docker cp {path_to_patch} {self.docker_communication.get_container_name()}:/root/test.patch",
                shell=True,
            )
            self.docker_communication.communicate_with_handling(
                input="git apply /root/test.patch",
                error_msg="Failed to apply test patch correctly"
            )
            os.remove(path_to_patch)
        # Write any metadata to info if necessary
        return None, info

    def install_env(self) -> None:
        """
        Creates conda environment and installs third party dependencies to allow code execution
        """
        repo_name = self.record["repo"].replace("/", "__")
        # Create environment if does not exist yet
        env_name = f"{repo_name}__{self.record['version']}"
        env_check = self.docker_communication.communicate(
            f"conda env list | grep {env_name}", timeout_duration=self.timeout
        )
        install_configs = MAP_VERSION_TO_INSTALL[self.record["repo"]][
            str(self.record["version"])
        ]
        if env_check.strip() == "":
            self.logger.info(f"{env_name} conda env not found, creating...")
            packages = (
                install_configs.get("packages", "")
            )
            if packages == "requirements.txt":
                # Create conda environment
                self.docker_communication.communicate_with_handling(
                    f"conda create -n {env_name} python={install_configs['python']} -y",
                    error_msg="Failed to create conda environment",
                    timeout_duration=self.timeout,
                )
                # Write reqs to requirements.txt in docker container
                content_reqs = get_requirements(self.record)
                copy_file_to_container(self.docker_communication.get_container_obj(), content_reqs, PATH_TO_REQS)
                # Create conda environment + install reqs
                self.docker_communication.communicate_with_handling(
                    f"conda activate {env_name}",
                    error_msg="Failed to activate conda environment",
                )
                self.docker_communication.communicate_with_handling(
                    f"pip install -r {PATH_TO_REQS}",
                    error_msg="Failed to install requirements.txt",
                    timeout_duration=self.timeout,
                )
                self.docker_communication.communicate(f"rm {PATH_TO_REQS}")
            elif packages == "environment.yml":
                # Write environment.yml to file
                content_env_yml = get_environment_yml(self.record, env_name)
                copy_file_to_container(self.docker_communication.get_container_obj(), content_env_yml, PATH_TO_ENV_YML)
                if "no_use_env" in install_configs and install_configs["no_use_env"]:
                    # Create conda environment
                    self.docker_communication.communicate_with_handling(
                        f"conda create -c conda-forge -n {env_name} python={install_configs['python']} -y",
                        error_msg="Failed to create conda environment",
                        timeout_duration=self.timeout,
                    )
                    # Install packages
                    self.docker_communication.communicate_with_handling(
                        f"conda env update -f {PATH_TO_ENV_YML}",
                        error_msg="Failed to install environment.yml",
                        timeout_duration=self.timeout
                    )
                else:
                    # Create environment + install packages
                    self.docker_communication.communicate_with_handling(
                        f"conda env create --file {PATH_TO_ENV_YML}",
                        error_msg="Failed to create conda environment with environment.yml",
                        timeout_duration=self.timeout,
                    )
                self.docker_communication.communicate(f"rm {PATH_TO_ENV_YML}")
            else:
                # Create environment + install packages
                self.docker_communication.communicate_with_handling(
                    f"conda create -n {env_name} python={install_configs['python']} {packages} -y",
                    error_msg="Failed to create conda environment",
                    timeout_duration=self.timeout,
                )
            # Install extra pip packages if specified
            if "pip_packages" in install_configs:
                self.docker_communication.communicate_with_handling(
                    f"source activate {env_name} && pip install {install_configs['pip_packages']}",
                    error_msg="Failed to install pip packages",
                    timeout_duration=self.timeout
                )

        # Activate environment
        self.docker_communication.communicate_with_handling(
            f"conda activate {env_name}",
            error_msg="Failed to activate conda environment"
        )

        # Install repo at base commit
        if "pre_install" in install_configs:
            self.logger.info("Running pre-install commands...")
            for pre_install_cmd in install_configs["pre_install"]:
                self.docker_communication.communicate_with_handling(
                    pre_install_cmd,
                    error_msg="Pre-install commands failed to execute successfully",
                )
        self.logger.info(f"Installing {repo_name} at base commit...")
        if "install" in install_configs:
            install_cmd = install_configs["install"]
            self.docker_communication.communicate_with_handling(
                install_cmd,
                error_msg="Install command failed to execute successfully",
                timeout_duration=self.timeout
            )
        if "post_install" in install_configs:
            self.logger.info("Running post-install commands...")
            for post_install_cmd in install_configs["post_install"]:
                self.docker_communication.communicate_with_handling(
                    post_install_cmd,
                    error_msg="Post-install commands failed to execute successfully",
                )
