import json
import logging
import os
import re
import select
import subprocess
import tarfile
import tempfile
import time
import traceback

from datasets import load_dataset, load_from_disk
from ghapi.all import GhApi
from io import BytesIO
from typing import List, Tuple, Dict

LOGGER_NAME = "intercode"
GITHUB_ISSUE_URL_PATTERN = re.compile(r'github\.com\/(.*?)\/(.*?)\/issues\/(\d+)')

logger = logging.getLogger(LOGGER_NAME)


def is_from_github_url(data_path: str):
    return GITHUB_ISSUE_URL_PATTERN.search(data_path) is not None


def copy_file_to_container(container, contents, container_path):
    """
    Copies a given string into a Docker container at a specified path.

    Args:
    - container: Docker SDK container object.
    - contents: The string to copy into the container.
    - container_path: The path inside the container where the string should be copied to.

    Returns:
    - None
    """
    temp_file_name = None

    try:
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file_name = temp_file.name
            # Write the string to the temporary file and ensure it's written to disk
            temp_file.write(contents.encode('utf-8'))
            temp_file.flush()
            os.fsync(temp_file.fileno())

        # Create a TAR archive in memory containing the temporary file
        with tempfile.NamedTemporaryFile() as temp_tar:
            with open(temp_file_name, 'rb') as temp_file:
                # Prepare the TAR archive
                with BytesIO() as tar_stream:
                    with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                        tar_info = tarfile.TarInfo(name=os.path.basename(container_path))
                        tar_info.size = os.path.getsize(temp_file_name)
                        tar.addfile(tarinfo=tar_info, fileobj=temp_file)
                    tar_stream.seek(0)
                    # Copy the TAR stream to the container
                    container.put_archive(path=os.path.dirname(container_path), data=tar_stream.read())

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        logger.error(traceback.format_exc())
    finally:
        # Cleanup: Remove the temporary file if it was created
        if temp_file_name and os.path.exists(temp_file_name):
            os.remove(temp_file_name)


def read_with_timeout(container, pid_func, timeout_duration):
    """
    Read data from a subprocess with a timeout.
    This function uses a file descriptor to read data from the subprocess in a non-blocking way.

    Args:
        container (subprocess.Popen): The subprocess container.
        pid_func (function): A function that returns a list of process IDs (except the PID of the main process).
        timeout_duration (int): The timeout duration in seconds.

    Returns:
        str: The data read from the subprocess, stripped of trailing newline characters.

    Raises:
        TimeoutError: If the timeout duration is reached while reading from the subprocess.
    """
    buffer = b""
    fd = container.stdout.fileno()
    end_time = time.time() + timeout_duration

    while time.time() < end_time:
        pids = pid_func()
        if len(pids) > 0:
            # There are still PIDs running
            time.sleep(0.05)
            continue
        ready_to_read, _, _ = select.select([fd], [], [], 0.1)
        if ready_to_read:
            data = os.read(fd, 4096)
            if data:
                buffer += data
        else:
            # No more data to read
            break
        time.sleep(0.05)  # Prevents CPU hogging

    if container.poll() is not None:
        raise RuntimeError("Subprocess exited unexpectedly.\nCurrent buffer: {}".format(buffer.decode()))
    if time.time() >= end_time:
        raise TimeoutError("Timeout reached while reading from subprocess.\nCurrent buffer: {}\nRunning PIDs: {}".format(buffer.decode(), pids))
    return buffer.decode()


def get_commit(api: GhApi, owner: str, repo: str, base_commit: str = None):
    if base_commit:
        commit = api.repos.get_commit(owner, repo, base_commit)
    else:
        commit = api.repos.list_commits(owner, repo)[0]
    return commit


class InvalidGithubURL(ValueError):
    ...


def parse_gh_issue_url(issue_url: str) -> Tuple[str, str, str]:
    """Return owner, repo, issue number from issue url"""
    match = GITHUB_ISSUE_URL_PATTERN.search(issue_url)
    if not match:
        raise InvalidGithubURL(f"Invalid GitHub issue URL: {issue_url}")
    res = match.groups()
    assert len(res) == 3
    return tuple(res)  # type: ignore


def parse_gh_repo_url(repo_url: str) -> Tuple[str, str]:
    """Return owner, repo from repo url"""
    if not repo_url.startswith('http://') and not repo_url.startswith('https://'):
        repo_url = 'https://' + repo_url
    parts = repo_url.split('/')
    owner = parts[3]
    repo = parts[4]
    return owner, repo


def get_gh_issue_data(issue_url: str, *, token: str = ""):
    """Returns github issue data in the form of a dictionary.
    See https://docs.github.com/en/rest/issues/issues?apiVersion=2022-11-28#get-an-issue
    for return format
    """
    owner, repo, issue_number = parse_gh_issue_url(issue_url)
    api = GhApi(token=token)
    return api.issues.get(owner, repo, issue_number)


def fetch_github_issue_details(github_issue_url: str, base_commit: str = None, token: str = None) -> list:
    """
    Fetches the GitHub issue details and constructs an instance.

    Arguments:
        github_issue_url (str): A GitHub issue URL.
        token (str, optional): GitHub API token. Defaults to None.
        base_commit:

    Returns:
        list: A list containing the constructed instance.
    """

    try:
        owner, repo, issue_number = parse_gh_issue_url(github_issue_url)
    except InvalidGithubURL:
        pass
    else:
        record = dict()
        api = GhApi(token=token)
        issue = api.issues.get(owner, repo, issue_number)
        title = issue.title if issue.title else ""
        body = issue.body if issue.body else ""
        text = f"{title}\n{body}\n"
        record["repo"] = f"{owner}/{repo}"
        record["base_commit"] = base_commit if base_commit else get_commit(api, owner, repo, base_commit).sha
        record["version"] = record["base_commit"][:7]
        record["problem_statement"] = text
        record["instance_id"] = f"{owner}__{repo}-i{issue_number}"
    return [record,]

def load_dataset_from_directory(file_path: str, split: str = None) -> dict:
    """
    Loads data from a local directory.

    Arguments:
        file_path (str): Directory path from where data should be retrieved.
        split (str, optional): A specific segment of the dataset to be returned. Defaults to None.

    Returns:
        dict: The data fetched from the directory.
    """

    # If file_path is a directory, attempt load from disk
    if os.path.isdir(file_path):
        dataset_or_dict = load_from_disk(file_path)
        if isinstance(dataset_or_dict, dict):
            return dataset_or_dict[split]
        return dataset_or_dict

def load_huggingface_dataset(file_path: str, base_commit: str = None, split: str = None) -> dict:
    """
    Loads a HuggingFace dataset.

    Arguments:
        file_path (str): Path to the HuggingFace dataset.
        split (str, optional): A specific segment of the dataset to be returned. Defaults to None.
        base_commit:

    Returns:
        dict: The requested HuggingFace dataset split.
    """
    if base_commit is not None:
        raise ValueError("base_commit must be None if data_path is not a github issue url")

    # If file_path is a file, load the file
    if file_path.endswith(".json"):
        return json.load(open(file_path))
    if file_path.endswith(".jsonl"):
        return [json.loads(x) for x in open(file_path, 'r').readlines()]
    try:
        dataset = load_dataset(file_path, split=split)
    except:
        raise ValueError(
            f"Could not load instances from {file_path}. "
            "Please ensure --data_path is a GitHub URL, a SWE-bench HuggingFace dataset, or a JSON/JSONL file."
        )
    return dataset


def get_associated_commit_urls(org: str, repo: str, issue_number: str, *, token: str = "") -> list[str]:
    """Return the URLs of commits that would close an issue."""
    api = GhApi(token=token)
    # Strangely the "pull_request" field of api.issues.get is often not set
    # so we have to go through the events to check if there's a commit
    events = api.issues.list_events(org, repo, issue_number)
    commit_urls = []
    for event in events:
        if not event.event == "referenced":
            continue
        if not event.commit_id:
            continue
        commit = api.repos.get_commit(org, repo, event.commit_id)
        message = commit.commit.message
        if f"fixes #{issue_number}" in message.lower() or f"closes #{issue_number}" in message.lower():
            commit_urls.append(commit.html_url)
    return commit_urls


def remove_triple_backticks(text: str) -> str:
    return "\n".join(line.removeprefix("```") for line in text.splitlines())


def format_trajectory_markdown(trajectory: List[Dict[str, str]]):
    """Format a trajectory as a markdown string for use in gh PR description."""
    emojis = {
        "action": "🔥",
        "observation": "👀",
        "response": "️🧑‍🚒",
        "state": "🧠",
        "thought": "💡",

    }
    prefix = [
        "<details>",
        "<summary>Thought process ('trajectory') of SWE-agent (click to expand)</summary>",
        "",
        "",
    ]
    steps = []
    for i, step in enumerate(trajectory):
        step_strs = []
        for key, value in step.items():
            emoji = emojis.get(key, "")
            if emoji:
                emoji += " "
            step_strs.append(f"**{emoji}{key.capitalize()} ({i})**:")
            if key in ["observation", "state", "action"]:
                step_strs.append("```")
                step_strs.append(remove_triple_backticks(value).strip())
                step_strs.append("```")
            else:
                step_strs.append(value.strip())
        steps.append("\n".join(step_strs))
    suffix = [
        "",
        "</details>",
    ]
    return "\n".join(prefix) + "\n\n---\n\n".join(steps) + "\n".join(suffix)

class UndefinedSourcecodeRepositoryType(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)
