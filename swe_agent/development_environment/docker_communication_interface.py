import datetime
import hashlib
import shlex
import os
import time
import signal
import traceback
from typing import Tuple
import subprocess
import docker
from subprocess import PIPE, STDOUT

from swe_agent.development_environment.utils import read_with_timeout, copy_file_to_container
START_UP_DELAY = 5
TIMEOUT_DURATION = 25


class DockerCommunicationInterface:
    def __init__(self, image_name, container_name, logger):
        self.logger = logger
        self.container_name = container_name
        self.image_name = image_name
        self.return_code = None
        self.container = None
        self.container_obj = None
        self.persistent = container_name is not None
        self.reset_container()

    def get_container_obj(self):
        return self.container_obj

    def get_container_name(self):
        return self.container_name

    # def _communicate(self, bash_command, timeout_duration=TIMEOUT_DURATION):
    #     """Execute a command in a Docker container."""
    #     if bash_command.endswith("\n"):
    #         cmd = bash_command
    #     else:
    #         cmd = bash_command + "\n"
    #     self.logger.debug(f"Effective command sent to the development environment: {bash_command}.")
    #     try:
    #         exit_code = None
    #         output = ''
    #
    #         _, stdout = self.container_obj.exec_run(
    #             cmd=cmd,
    #             stdout=True,
    #             stderr=True,
    #             stdin=True,
    #             tty=True,
    #             demux=True
    #         )
    #
    #         try:
    #             with self.Timeout(timeout_duration) as t:
    #                 for line in stdout:
    #                     output += line.decode("utf-8")
    #                     # If no exit code yet, send CTRL+D
    #                     if not exit_code:
    #                         self.container_obj.exec_run(
    #                             cmd="printf '\x04'",  # Sending EOF (CTRL+D)
    #                             stdout=True,
    #                             stderr=True,
    #                             stdin=True,
    #                             tty=True,
    #                         )
    #                     else:
    #                         break
    #
    #             if not t.timed_out:
    #                 exit_code = t.exit_code
    #
    #         except self.Timeout as e:
    #             self.logger.error(f"Timeout after {timeout_duration}s: {e.error_message}")
    #             exit_code = t.exit_code
    #
    #         return output, exit_code
    #     except docker.errors.APIError as e:
    #         # Add specific handling for exceptions if needed
    #         self.logger.error(e)
    #         return None, 1

    def _communicate(self, bash_command: str, timeout_duration=25, ) -> Tuple[str, int]:
        try:
            self.return_code = None
            if bash_command.endswith("\n"):
                cmd = bash_command
            else:
                cmd = bash_command + "\n"
            self.logger.debug(f"Effective command sent to the development environment: {bash_command}.")
            encoded_command = cmd.encode()
            os.write(self.container.stdin.fileno(), encoded_command)
            time.sleep(0.1)
            self.container.stdin.flush()
        except BrokenPipeError:
            traceback.print_exc()
            self.logger.error(
                "Failed to communicate with container. Check docker logs for more information."
            )
            raise RuntimeError("Failed to communicate with development environment")
        try:
            buffer = read_with_timeout(self.container, self.get_pids, timeout_duration)
            self.container.stdin.write("echo $?\n")
            time.sleep(0.1)
            self.container.stdin.flush()
            exit_code = read_with_timeout(self.container, self.get_pids, 5).strip()
        except Exception as e:
            self.logger.error(f"Read with timeout failed on input:\n---\n{bash_command}\n---")
            raise e
        if not exit_code.isdigit():
            raise RuntimeError(f"Container crashed. Failed to get exit code. Output:\n---\n{buffer}\n---")
        return buffer, int(exit_code)

    def _check_syntax(self, input: str) -> Tuple[str, bool]:
        """
        Saves environment variables to file
        """
        output, exit_code = self._communicate(f"/bin/bash -n <<'EOF'\n{input}\nEOF\n")
        return output, exit_code

    def exit_development_environment(self) -> str:
        self.container.terminate()
        self.return_code = 0
        return ""

    def communicate(self, bash_command: str, timeout_duration=25) -> Tuple[str, int]:
        """
        Sends input to container and returns output

        Args:
            bash_command (`str`) - input to send to container

        Returns:
            output (`str`) - output from container
        """
        synthax_errors, exit_code = self._check_syntax(bash_command)
        if exit_code == 1:
            exit_code = 1
            return synthax_errors, exit_code
        commandline_response, exit_code = self._communicate(bash_command, timeout_duration=timeout_duration,)
        return commandline_response, exit_code

    def communicate_with_handling(self, bash_command: str, error_msg: str, timeout_duration=25) -> str:
        """
        Wrapper for communicate function that raises error if return code is non-zero
        """
        commandline_response, exit_code = self.communicate(bash_command, timeout_duration=timeout_duration)
        if exit_code != 0:
            self.logger.error(f"{error_msg}: {commandline_response}")
            self.close()
            raise RuntimeError(f"{error_msg}: {commandline_response}")
        return commandline_response

    def reset_container(self) -> None:
        if self.container is not None:
            self.close()
        self.container = None
        self.container_obj = None
        self._init_container()
        self._init_scripts()

    def _init_container(self) -> None:
        """
        Handles container initialization. Defines container name and creates it
        """
        if self.container_name is None:
            process_id = str(os.getpid())
            current_time = str(datetime.datetime.now())
            unique_string = current_time + process_id
            hash_object = hashlib.sha256(unique_string.encode())
            # Cannot have colons/slashes in container name, but those are important in image names
            # i.e., when we want swe-agent to pull the image from dockerhub
            image_name_sanitized = self.image_name.replace("/", "-")
            image_name_sanitized = image_name_sanitized.replace(":", "-")
            self.container_name = f"{image_name_sanitized}-{hash_object.hexdigest()[:10]}"
        self.container, self.parent_pids = self.get_container()
        try:
            client = docker.from_env()
        except docker.errors.DockerException as e:
            if "Error while fetching server API version" in str(e):
                raise RuntimeError(
                    "Docker is not running. Please start Docker and try again."
                ) from e
        self.container_obj = client.containers.get(self.container_name)
        self.logger.info("🌱 Environment Initialized")

    def _init_scripts(self):
        """
        Initialize custom commands within container
        """
        self.communicate_with_handling(
            bash_command="source /root/.bashrc",
            error_msg="Failed to source .bashrc",
        )
        self.communicate_with_handling(
            bash_command="mkdir -p /root/commands",
            error_msg="Failed to create commands directory",
        )
        self.communicate_with_handling(
            bash_command="touch /root/commands/__init__.py",
            error_msg="Failed to create __init__.py",
        )
        self.communicate_with_handling(
            bash_command="export PATH=$PATH:/root/commands",
            error_msg="Failed to add commands directory to PATH",
        )

    def close(self):
        """
        Handle environment shutdown
        """
        self.logger.info("Beginning environment shutdown...")
        try:
            self.exit_development_environment()
        except KeyboardInterrupt:
            self.logger.info("Shutdown interrupted by keyboard.")
            raise
        except Exception as e:
            self.logger.error(f"An error occurred during shutdown: {str(e)}")

        self.container.terminate()

        if self.persistent:
            if self.container_obj.status not in {"paused", "exited"}:
                self.container_obj.pause()
                self.logger.info("Agent container paused")
            else:
                self.logger.info(f"Agent container status: {self.container_obj.status}")
        else:
            try:
                self.container_obj.remove(force=True)
            except KeyboardInterrupt:
                self.logger.info("Shutdown interrupted by keyboard.")
                raise
            except Exception as e:
                self.logger.error(f"An error occurred while removing the container: {str(e)}")

        self.logger.info("Agent container stopped")

    def get_pids(self, all_pids=False) -> list[str]:
        """
        Gets list of processes running inside docker container
        """
        pids = (
            self.container_obj.exec_run("ps -eo pid,comm --no-headers")
            .output.decode()
            .split("\n")
        )
        pids = [x.split() for x in pids if x]
        if not all_pids:
            pids = [x for x in pids if x[1] != "ps" and x[0] not in self.parent_pids]
        return pids

    def interrupt(self):
        """
        Send interrupt signal to container and exhaust stdout buffer with a communicate call
        """
        pids = self.get_pids()
        for pid, cmd in pids:
            if pid not in self.parent_pids and cmd != "ps":
                self.container_obj.exec_run(f"kill -9 {pid}")
        try:
            _ = read_with_timeout(self.container, self.get_pids, 20)
        except TimeoutError:
            pass
        try:
            output, exit_code = self.communicate(bash_command="echo 'interrupted'", timeout_duration=5)
            assert output.strip().endswith("interrupted"), "container health check failed"
        except TimeoutError:
            raise RuntimeError("Failed to interrupt container")

    def add_commands(self, commands: list[dict]) -> None:
        """
        Adds custom commands to container
        """
        for command in commands:
            name = command["name"]
            contents = command["contents"]
            copy_file_to_container(self.get_container_obj(), contents, f"/root/commands/{name}")
            if command['type'] == "source_file":
                self.communicate_with_handling(
                    bash_command=f"source /root/commands/{name}",
                    error_msg=(
                        f"Failed to source {name}. If you meant to make a script,"
                        " start the file with a shebang (e.g. #!/usr/bin/env python)."
                    )
                )
            elif command['type'] == "script":
                self.communicate_with_handling(
                    bash_command=f"chmod +x /root/commands/{name}",
                    error_msg=f"Failed to chmod {name}",
                )
            elif command['type'] == "utility":
                # nothing to do for utility scripts
                pass
            else:
                raise ValueError(f"Invalid command type: {command['type']}")

    def get_available_actions(self) -> list[str]:
        """
        Returns list of available actions in current environment state
        """
        return []

    def get_container(self) -> subprocess.Popen:
        """
        Get a container object for a given container name and image name

        Arguments:
            container_name (str): Name of container
            image_name (str): Name of image
            persistent (bool): Whether to use a persistent container or not
        Returns:
            Container object
        """
        if self.persistent:
            return self._get_persistent_container()
        else:
            return self._get_non_persistent_container()

    def _get_persistent_container(self) -> Tuple[subprocess.Popen, set]:
        client = docker.from_env()
        containers = client.containers.list(all=True, filters={"name": self.container_name})
        if self.container_name in [c.name for c in containers]:
            container_obj = client.containers.get(self.container_name)
            if container_obj.status in {"created"}:
                container_obj.start()
            elif container_obj.status in {"running"}:
                pass
            elif container_obj.status in {"exited"}:
                container_obj.restart()
            elif container_obj.status in {"paused"}:
                container_obj.unpause()
            else:
                raise RuntimeError(f"Unexpected container status: {container_obj.status}")
        else:
            container_obj = client.containers.run(
                self.image_name,
                command='/bin/bash -l -m',
                name=self.container_name,
                stdin_open=True,
                tty=True,
                detach=True,
                auto_remove=not self.persistent,
            )
            container_obj.start()
        startup_cmd = [
            "docker",
            "exec",
            "-i",
            self.container_name,
            "/bin/bash",
            "-l",
            "-m",
        ]
        container = self.start_container(startup_cmd)
        # Get the process IDs of the container
        # There should be at least a head process and possibly one child bash process
        bash_pids, other_pids = self.get_background_pids(container_obj)
        bash_pid = 1
        if len(bash_pids) == 1:
            bash_pid = bash_pids[0][0]
        elif len(bash_pids) > 1 or len(other_pids) > 0:
            raise RuntimeError(f"Detected alien processes attached or running. Please ensure that no other agents are running on this container. PIDs: {bash_pids}, {other_pids}")
        return container, set(map(str, [bash_pid, 1, ]))

    def _get_non_persistent_container(self) -> Tuple[subprocess.Popen, set]:
        startup_cmd = [
            "docker",
            "run",
            "-i",
            "--rm",
            "--name",
            self.container_name,
            self.image_name,
            "/bin/bash",
            "-l",
            "-m",
        ]
        container = self.start_container(startup_cmd)
        return container, {"1", }  # bash PID is always 1 for non-persistent containers

    def start_container(self, startup_cmd):
        self.logger.debug(f"Starting container with command: %s", shlex.join(startup_cmd))
        container = subprocess.Popen(
            startup_cmd,
            stdin=PIPE,
            stdout=PIPE,
            stderr=STDOUT,
            text=True,
            bufsize=1,  # line buffered
        )
        time.sleep(START_UP_DELAY)
        # try to read output from container setup (usually an error), timeout if no output
        try:
            with self.Timeout(seconds=2):
                output = container.stdout.read()
                if output:
                    self.logger.error(f"Unexpected container setup output: {output}")
        except TimeoutError:
            pass
        return container

    def get_background_pids(container_obj):
        pids = (
            container_obj.exec_run("ps -eo pid,comm --no-headers")
            .output.decode()
            .split("\n")
        )
        pids = [x.split() for x in pids if x]
        pids = [x for x in pids if x[1] not in {"ps"} and x[0] != "1"]
        bash_pids = [x for x in pids if x[1] == "bash"]
        other_pids = [x for x in pids if x[1] not in {"bash"}]
        return bash_pids, other_pids

    class Timeout:
        def __init__(self, seconds=TIMEOUT_DURATION, error_message="Timeout"):
            self.seconds = seconds
            self.error_message = error_message

        def handle_timeout(self, signum, frame):
            raise TimeoutError(self.error_message)

        def __enter__(self):
            signal.signal(signal.SIGALRM, self.handle_timeout)
            signal.alarm(self.seconds)

        def __exit__(self, type, value, traceback):
            signal.alarm(0)
