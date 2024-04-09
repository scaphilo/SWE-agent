import datetime
import hashlib
import os
import time
import traceback
from typing import Tuple

import docker

from swe_agent.environment.utils import read_with_timeout, get_container


class DockerCommunicationManagement:
    def __init__(self, image_name, container_name, logger):
        self.logger = logger
        self.container_name = container_name
        self.image_name = image_name
        self.container = None
        self.container_obj = None
        self.persistent = container_name is not None
        self.reset_container()
        self.return_code = None

    def get_container_obj(self):
        return self.container_obj

    def get_container_name(self):
        return self.container_name

    def _communicate(self, communication_input: str, timeout_duration=25, ) -> str:
        try:
            self.return_code = None
            cmd = communication_input if communication_input.endswith("\n") else communication_input + "\n"
            os.write(self.container.stdin.fileno(), cmd.encode())
            time.sleep(0.1)
            self.container.stdin.flush()
        except BrokenPipeError:
            traceback.print_exc()
            self.logger.error(
                "Failed to communicate with container. Check docker logs for more information."
            )
            raise RuntimeError("Failed to communicate with container")
        try:
            buffer = read_with_timeout(self.container, self.get_pids, timeout_duration)
            self.container.stdin.write("echo $?\n")
            time.sleep(0.1)
            self.container.stdin.flush()
            exit_code = read_with_timeout(self.container, self.get_pids, 5).strip()
        except Exception as e:
            self.logger.error(f"Read with timeout failed on input:\n---\n{communication_input}\n---")
            raise e
        if not exit_code.isdigit():
            raise RuntimeError(f"Container crashed. Failed to get exit code. Output:\n---\n{buffer}\n---")
        self.return_code = int(exit_code)
        return buffer

    def _check_syntax(self, input: str) -> Tuple [str, bool]:
        """
        Saves environment variables to file
        """
        output = self._communicate(f"/bin/bash -n <<'EOF'\n{input}\nEOF\n")
        return output, self.return_code == 0

    def communicate(self, input: str, timeout_duration=25) -> str:
        """
        Sends input to container and returns output

        Args:
            input (`str`) - input to send to container

        Returns:
            output (`str`) - output from container
        """
        if input.strip() != "exit":
            output, valid = self._check_syntax(input)
            if not valid:
                return output  # shows syntax errors
            output = self._communicate(
                input, timeout_duration=timeout_duration,
            )
            self.communicate_output = output
            return output
        else:
            self.container.terminate()
            self.return_code = 0
            self.communicate_output = ""
            return ""

    def communicate_with_handling(self, input: str, error_msg: str, timeout_duration=25) -> str:
        """
        Wrapper for communicate function that raises error if return code is non-zero
        """
        logs = self.communicate(input, timeout_duration=timeout_duration)
        if self.return_code != 0:
            self.logger.error(f"{error_msg}: {logs}")
            self.close()
            raise RuntimeError(f"{error_msg}: {logs}")
        return logs

    def reset_container(self) -> None:
        if self.container is not None:
            self.close()
        self.container = None
        self.container_obj = None
        if hasattr(self, "container"):
            try:
                self.container.terminate()
            except KeyboardInterrupt:
                raise
            except:
                pass
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
        self.container, self.parent_pids = get_container(container_name=self.container_name,
                                                         image_name=self.image_name,
                                                         persistent=self.persistent)
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
            "source /root/.bashrc",
            error_msg="Failed to source .bashrc",
        )
        self.communicate_with_handling(
            "mkdir -p /root/commands",
            error_msg="Failed to create commands directory",
        )
        self.communicate_with_handling(
            "touch /root/commands/__init__.py",
            error_msg="Failed to create __init__.py",
        )
        self.communicate_with_handling(
            "export PATH=$PATH:/root/commands",
            error_msg="Failed to add commands directory to PATH",
        )

    def close(self):
        """
        Handle environment shutdown
        """
        self.logger.info("Beginning environment shutdown...")
        try:
            self.communicate(input="exit")
        except KeyboardInterrupt:
            raise
        except:
            pass
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
                raise
            except:
                pass
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
            output = self.communicate(input="echo 'interrupted'", timeout_duration=5)
            assert output.strip().endswith("interrupted"), "container health check failed"
        except TimeoutError:
            raise RuntimeError("Failed to interrupt container")


