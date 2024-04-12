import gymnasium as gym
import logging
import re

from rich.logging import RichHandler

from swe_agent.development_environment.development_environment_arguments import DevelopmentEnvironmentArguments
from swe_agent.development_environment.docker_communication_management import DockerCommunicationManagement
from swe_agent.development_environment.git_communication_management import GitCommunicationManagement
from swe_agent.development_environment.utils import (
    is_from_github_url,
    LOGGER_NAME,
)
from typing import Tuple

LONG_TIMEOUT = 500


class DevelopmentEnvironment(gym.Env):
    """Gym environment for SWE-bench. This class should handle all communication with the docker container."""

    name = "swe_main"

    def __init__(self, args: DevelopmentEnvironmentArguments):
        super().__init__()
        self.split = args.split
        self.data_path = args.data_path
        self.no_mirror = args.no_mirror
        self.is_github_url = is_from_github_url(args.data_path)
        self.container_name = args.container_name
        self.install_python_environment = args.install_environment
        handler = RichHandler(show_time=False, show_path=False)
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger(LOGGER_NAME)
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        logger.propagate = False
        self.logger = logger
        if not args.verbose:
            self.logger.disabled = True

        # Establish connection with execution container
        self.image_name = args.image_name
        # Set timeout
        self.timeout = args.timeout
        self.idx = 0
        self.clean_multi_line_functions = lambda x: x
        self.docker_communication = DockerCommunicationManagement(image_name=self.image_name,
                                                                  container_name=self.container_name,
                                                                  logger=self.logger)
        self.git_communication_management = GitCommunicationManagement(data_path=self.data_path,
                                                                       is_github_url=self.is_github_url,
                                                                       idx=self.idx,
                                                                       split=self.split,
                                                                       logger=self.logger,
                                                                       install_python_environment=self.install_python_environment,
                                                                       no_mirror=self.no_mirror,
                                                                       docker_communication=self.docker_communication,
                                                                       timeout=LONG_TIMEOUT)

    def get_git_communication_management(self):
        return self.git_communication_management

    def get_docker_communication(self):
        return self.docker_communication

    def reset(self, index: int = None, apply_test_patch: bool = False):
        return self.git_communication_management.reset(index, apply_test_patch)

    def step(self, action: str) -> Tuple[str, int, bool, dict]:
        """
        Runs given action in environment and returns corresponding output

        Args:
            action (`str`) - command to run in bash shell

        Returns:
            observation (`str`) - output from container
            reward (`float`) - value between 0 and 1 quantifying correctness of output + environment state
            done (`bool`) - whether task is over
            info (`dict`) - additional information (e.g. debugging information)
        """
        info = {}

        observation = ""
        # Handle special actions
        if action.strip() == "skip":
            observation = "Skipped"
            info["exit_status"] = "skipped"
            return observation, 0, True, info
        if action in {"exit_context", "exit_cost", "exit_error", "exit_format", "exit_api"}:
            try:
                observation = self.docker_communication.communicate(input="submit")
                submission = self.get_submission('submit', observation)
                assert submission is not None and submission.strip() != "", AssertionError('No submission found.')
                self.logger.info(f"Found submission: {submission}")
                info["exit_status"] = f"submitted ({action})"
                info["submission"] = submission
                observation = "Exited (autosubmitted)"
                self.logger.info("Exiting with autosubmission")
                return observation, 0, True, info
            except KeyboardInterrupt:
                raise
            except:
                observation = "Exited"
                info["exit_status"] = action
                return observation, 0, True, info

        # Attempt to run action in container
        observation = ""
        try:
            observation = self.docker_communication.communicate(input=action, timeout_duration=25)
        except TimeoutError:
            try:
                self.docker_communication.interrupt()
                observation += "\nEXECUTION TIMED OUT"
            except RuntimeError as e:
                observation += "\nEXECUTION TIMED OUT AND INTERRUPT FAILED. RESTARTING PROCESS."
                info["exit_status"] = "early_exit"
                self.logger.warning(f"Failed to interrupt container: {e}\nRESTARTING PROCESS.")
                self.docker_communication.reset_container()
                return observation, 0, True, info
        except RuntimeError as e:
            observation += "\nCOMMAND FAILED TO EXECUTE. RESTARTING PROCESS."
            info["exit_status"] = "early_exit"
            self.logger.warning(f"Failed to execute command: {e}\nRESTARTING PROCESS.")
            self.docker_communication.reset_container()
            return observation, 0, True, info
        except BrokenPipeError as e:
            observation += "\nBROKEN PIPE ERROR. RESTARTING PROCESS."
            info["exit_status"] = "early_exit"
            self.logger.error(f"Broken pipe error: {e}\nRESTARTING PROCESS.")
            self.docker_communication.reset_container()
            return observation, 0, True, info
        except Exception as e:
            observation += "\nEXECUTION FAILED OR COMMAND MALFORMED"

        # Record submission and end episode if `submit` keyword found
        submission = self.get_submission(action, observation)
        if submission is not None:
            self.logger.info(f"Found submission: {submission}")
            info["exit_status"] = "submitted"
            info["submission"] = submission if submission.strip() != "" else None
            observation = submission if submission.strip() != "" else None
            return observation, 0, True, info
        return observation, 0, False, info

    def get_submission(self, action, output: str) -> str:
        """
        Function for extracting diff patch submission at the end of an episode.

        Args:
            output (`str`) - `submit` observation
        Returns:
            submission (`str`) - diff patch submission
        """
        pattern = r"\<\<SUBMISSION\|\|(.*)\|\|SUBMISSION\>\>"
        match = re.search(pattern, output, re.DOTALL)
        if match is None:
            return None
        return match.group(1)
