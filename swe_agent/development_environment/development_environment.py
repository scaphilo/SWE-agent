import re
from swe_agent.development_environment.development_environment_arguments import DevelopmentEnvironmentArguments
from swe_agent.development_environment.docker_communication_interface import DockerCommunicationInterface
from swe_agent.development_environment.git_communication_interface import GitCommunicationInterface
from typing import Tuple

LONG_TIMEOUT = 500


class DevelopmentEnvironment:
    """This is the development environment which runs the application sourcecode and the git
    commands. The development environment also checks out the application sourcecode for the modification.
    All file modifications are performed within this docker container.
    This class should handle all communication with the docker container.
    The scope of the development environment should in future be reduced to only run the code"""

    name = "swe_main"

    def __init__(self, development_environment_arguments: DevelopmentEnvironmentArguments, logger):
        super().__init__()
        self.split = development_environment_arguments.split
        self.sourcecode_repository_remote = development_environment_arguments.sourcecode_repository_remote
        self.sourcecode_repository_local = development_environment_arguments.sourcecode_repository_local
        self.sourcecode_repository_path = development_environment_arguments.sourcecode_repository_path
        self.no_mirror = development_environment_arguments.no_mirror
        self.sourcecode_repository_type = development_environment_arguments.sourcecode_repository_type
        self.container_name = development_environment_arguments.container_name
        self.install_python_environment = development_environment_arguments.install_environment
        self.logger = logger
        self.image_name = development_environment_arguments.image_name
        self.docker_communication_timeout = development_environment_arguments.docker_communication_timeout
        self.clean_multi_line_functions = lambda x: x
        self.docker_communication_interface = DockerCommunicationInterface(image_name=self.image_name,
                                                                           container_name=self.container_name,
                                                                           logger=self.logger)
        self.git_communication_interface = GitCommunicationInterface(sourcecode_repository_remote=self.sourcecode_repository_remote,
                                                                     sourcecode_repository_local=self.sourcecode_repository_local,
                                                                     github_issue_url=self.sourcecode_repository_path,
                                                                     sourcecode_repository_type=self.sourcecode_repository_type,
                                                                     split=self.split,
                                                                     logger=self.logger,
                                                                     no_mirror=self.no_mirror,
                                                                     timeout=LONG_TIMEOUT)

    def get_git_communication_interface(self):
        return self.git_communication_interface

    def get_docker_communication_interface(self):
        return self.docker_communication_interface

    @staticmethod
    def is_bash_command(development_environment_command) -> bool:
        if development_environment_command in {"exit_context",
                                               "exit_cost",
                                               "exit_error",
                                               "exit_format",
                                               "exit_api",
                                               "exit",
                                               "strip"}:
            return False
        else:
            return True

    @staticmethod
    def get_submission(output: str) -> str:
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

    def handle_special_actions(self, special_action) -> Tuple[str, dict]:
        info = {}
        if special_action.strip() == "skip":
            special_action_response = "Skipped"
            info["exit_status"] = "skipped"
            return special_action_response, info
        elif special_action in {"exit_context", "exit_cost", "exit_error", "exit_format", "exit_api"}:
            try:
                special_action_response = self.docker_communication_interface.communicate(bash_command="submit")
                submission = self.get_submission(special_action_response)
                assert submission is not None and submission.strip() != "", AssertionError('No submission found.')
                self.logger.info(f"Found submission: {submission}")
                info["exit_status"] = f"submitted ({special_action})"
                info["submission"] = submission
                special_action_response = "Exited (autosubmitted)"
                self.logger.info("Exiting with autosubmission")
                return special_action_response, info
                # Todo: Is there no need to run the docker exit_development_environment command?
            except KeyboardInterrupt:
                raise
            except:
                special_action_response = "Exited"
                info["exit_status"] = special_action
                return special_action_response, info
        else:  # only remaining alternative is to exit the development environment
            special_action_response = self.docker_communication_interface.exit_development_environment()
            info["exit_status"] = special_action
            return special_action_response, info

    def handle_bash_command_action(self, bash_command) -> Tuple[str, int, bool, dict]:
        info = {}
        commandline_response = ""
        try:
            commandline_response, exit_code = self.docker_communication_interface.communicate(bash_command=bash_command,
                                                                                              timeout_duration=self.docker_communication_timeout)
        except TimeoutError:
            try:
                self.docker_communication_interface.interrupt()
                commandline_response += "\nEXECUTION TIMED OUT"
            except RuntimeError as e:
                commandline_response += "\nEXECUTION TIMED OUT AND INTERRUPT FAILED. RESTARTING PROCESS."
                info["exit_status"] = "early_exit"
                self.logger.warning(f"Failed to interrupt container: {e}\nRESTARTING PROCESS.")
                self.docker_communication_interface.reset_container()
                return commandline_response, 0, False, info
        except RuntimeError as e:
            commandline_response += "\nCOMMAND FAILED TO EXECUTE. RESTARTING PROCESS."
            info["exit_status"] = "early_exit"
            self.logger.warning(f"Failed to execute command: {e}\nRESTARTING PROCESS.")
            self.docker_communication_interface.reset_container()
            return commandline_response, 0, False, info
        except BrokenPipeError as e:
            commandline_response += "\nBROKEN PIPE ERROR. RESTARTING PROCESS."
            info["exit_status"] = "early_exit"
            self.logger.error(f"Broken pipe error: {e}\nRESTARTING PROCESS.")
            self.docker_communication_interface.reset_container()
            return commandline_response, 0, False, info
        except Exception as e:
            commandline_response += "\nEXECUTION FAILED OR COMMAND MALFORMED"

        # Record submission and end episode if `submit` keyword found
        submission = self.get_submission(commandline_response)
        if submission is not None:
            self.logger.info(f"Found submission: {submission}")
            info["exit_status"] = "submitted"
            info["submission"] = submission if submission.strip() != "" else None
            commandline_response = submission if submission.strip() != "" else None
            return commandline_response, 0, True, info
        return commandline_response, 0, False, info

    def step(self, development_environment_command: str) -> Tuple[str, int, bool, dict]:
        """
        Runs given action in environment and returns corresponding output

        Args:
            development_environment_command (`str`) - command to run in bash shell

        Returns:
            observation (`str`) - output from container
            reward (`float`) - value between 0 and 1 quantifying correctness of output + environment state
            done (`bool`) - whether task is over
            info (`dict`) - additional information (e.g. debugging information)
        """
        if self.is_bash_command(development_environment_command):
            commandline_response, reward, done, info = self.handle_bash_command_action(bash_command=development_environment_command)
            return commandline_response, reward, done, info
        else:
            special_action_response, info = self.handle_special_actions(special_action=development_environment_command)
            return special_action_response, 0, True, info


