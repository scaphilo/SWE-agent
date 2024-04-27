import os
import shutil
import random
import config
from ghapi.core import GhApi
from git import Repo
from typing import List, Tuple, Dict
import re

from swe_agent.development_environment.utils import (format_trajectory_markdown,
                                                     UndefinedSourcecodeRepositoryType, )

PATH_TO_REQUIREMENTS = "/root/requirements.txt"
PATH_TO_ENV_YML = "/root/environment.yml"
GITHUB_ISSUE_URL_PATTERN = re.compile(r'github\.com\/(.*?)\/(.*?)\/issues\/(\d+)')


class GitCommunicationInterface:
    def __init__(self,
                 sourcecode_repository_remote: str,
                 sourcecode_repository_local: str,
                 sourcecode_repository_type: str,
                 github_issue_url: str,
                 split: str,
                 logger,
                 no_mirror,
                 timeout: int):
        self.task_count = 0
        self.split = split
        self.no_mirror = no_mirror
        self.github_issue_url = github_issue_url
        self.sourcecode_repository_remote = sourcecode_repository_remote
        self.sourcecode_repository_local = sourcecode_repository_local
        self.sourcecode_repository_type = sourcecode_repository_type
        self.base_commit = None
        self.github_token = os.environ.get("GITHUB_TOKEN", None)
        self.timeout = timeout
        self.logger = logger
        if os.path.exists(sourcecode_repository_local):
            shutil.rmtree(sourcecode_repository_local)
        self.repo = Repo.clone_from(sourcecode_repository_remote, sourcecode_repository_local)
        # Get commit hash
        try:
            repo = Repo(search_parent_directories=True)
            self.commit_sha = repo.head.object.hexsha
        except KeyboardInterrupt:
            raise
        except:
            logger.warning("Failed to get commit hash for this repo")
            self.commit_sha = None

        if (self.github_token is None or self.github_token == "") and os.path.isfile(
                os.path.join(os.getcwd(), "keys.cfg")
        ):
            self.cfg = config.Config(os.path.join(os.getcwd(), "keys.cfg"))
            self.github_token = self.cfg.get("GITHUB_TOKEN", "git")
        if self.sourcecode_repository_type == "Github":
            self.repository_details_dict = self.fetch_github_issue_details()
        else:
            raise UndefinedSourcecodeRepositoryType("The Sourcecode Repository Type: %s does not exist"
                                                    .format(self.sourcecode_repository_type))
        self.logger.info(f"💽 Loaded dataset from {self.github_issue_url}")

    def get_issue_description(self):
        return self.issue_description

    def get_repository_details_dict(self):
        return self.repository_details_dict

    def get_token(self):
        return self.github_token

    @staticmethod
    def get_gh_issue_data(issue_url: str, *, token: str = ""):
        """Returns github issue data in the form of a dictionary.
        See https://docs.github.com/en/rest/issues/issues?apiVersion=2022-11-28#get-an-issue
        for return format
        """
        owner, repo, issue_number = GitCommunicationInterface.parse_gh_issue_url(issue_url)
        api = GhApi(token=token)
        return api.issues.get(owner, repo, issue_number)

    def fetch_github_issue_details(self) -> dict:
        """
        Fetches the GitHub issue details and constructs an instance.
    
        Returns:
            list: A list containing the constructed instance.
        """
    
        gitlab_details_dict = dict()
        try:
            owner, repo, issue_number = GitCommunicationInterface.parse_gh_issue_url(self.github_issue_url)
        except InvalidGithubURL:
            pass
        else:
            api = GhApi(token=self.github_token)
            issue = api.issues.get(owner, repo, issue_number)
            title = issue.title if issue.title else ""
            body = issue.body if issue.body else ""
            text = f"{title}\n{body}\n"
            gitlab_details_dict["repo"] = f"{owner}/{repo}"
            gitlab_details_dict["base_commit"] = self.base_commit if self.base_commit else GitCommunicationInterface.get_commit(api, owner, repo, self.base_commit).sha
            gitlab_details_dict["version"] = gitlab_details_dict["base_commit"][:7]
            self.issue_description = text
            self.issue_number = issue_number
            self.issue_title = issue.title
            gitlab_details_dict["instance_id"] = f"{owner}__{repo}-i{issue_number}"
        return gitlab_details_dict

    @staticmethod
    def get_commit(api: GhApi, owner: str, repo: str, base_commit: str = None):
        if base_commit:
            commit = api.repos.get_commit(owner, repo, base_commit)
        else:
            commit = api.repos.list_commits(owner, repo)[0]
        return commit

    @staticmethod
    def parse_gh_issue_url(issue_url: str) -> Tuple[str, str, str]:
        """Return owner, repo, issue number from issue url"""
        match = GITHUB_ISSUE_URL_PATTERN.search(issue_url)
        if not match:
            raise InvalidGithubURL(f"Invalid GitHub issue URL: {issue_url}")
        res = match.groups()
        assert len(res) == 3
        return tuple(res)  # type: ignore

    @staticmethod
    def parse_gh_repo_url(repo_url: str) -> Tuple[str, str]:
        """Return owner, repo from repo url"""
        if not repo_url.startswith('http://') and not repo_url.startswith('https://'):
            repo_url = 'https://' + repo_url
        parts = repo_url.split('/')
        owner = parts[3]
        repo = parts[4]
        return owner, repo

    @staticmethod
    def is_from_github_url(data_path: str):
        return GITHUB_ISSUE_URL_PATTERN.search(data_path) is not None

    def open_pull_request(self, action_config, info, trajectory):
        """Create PR to repository"""
        self.logger.info("Opening PR")
        # todo: have better way of handling this
        # Adding random string suffix to avoid name conflicts if we had a previously failed run
        issue_url = self.github_issue_url
        branch_name = f"swe-agent-fix-#{self.issue_number}-" + str(random.random())[2:10]

        self.repo.git.checkout('-b', branch_name)
        self.repo.git.add(all=True)
        self.repo.git.commit('-m', f"'Fix: {self.issue_title}' -m 'Closes #{self.issue_number}'")

        # If users want to push to a fork, we add a new remote and push to that
        # otherwise, we push to 'origin' which has already been set up
        remote = "origin"
        if not action_config.push_gh_repo_url:
            owner, repo, _ = GitCommunicationInterface.parse_gh_issue_url(issue_url)
        else:
            owner, repo = GitCommunicationInterface.parse_gh_repo_url(action_config.push_gh_repo_url)
        if action_config.push_gh_repo_url:
            fork_url = f"https://{self.github_token}@github.com/{owner}/{repo}.git"
            self.repo.git.remote("add", "fork", fork_url)
            remote = "fork"
        self.repo.git.push(remote, branch_name)

        # todo: add representation of trajectory to PR body
        body = (
            f"This is a PR opened by AI tool [SWE Agent](https://github.com/princeton-nlp/SWE-agent/) "
            f"to close [#{self.issue_number}]({issue_url}) ({self.issue_title}).\n\nCloses #{self.issue_number}."
        )
        body += "\n\n" + format_trajectory_markdown(trajectory)
        api = GhApi(token=self.github_token)
        pr_info = api.pulls.create(
            owner=owner,
            repo=repo,
            title=f"SWE-agent[bot] PR to fix: {self.issue_number}",
            head=branch_name,
            base="main",
            body=body,
            draft=True,
        )
        self.logger.info(
            f"🎉 PR created as a draft at {pr_info.html_url}. Please review it carefully, push "
            "any required changes onto the branch and then click "
            "'Ready for Review' to bring it to the attention of the maintainers.")


class InvalidGithubURL(ValueError):
    ...