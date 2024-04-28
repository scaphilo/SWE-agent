import re
import os
import copy
import datetime
from pathlib import Path

from swe_agent.development_environment.git_communication_interface import GitCommunicationInterface
from swe_agent.swe_agent.action.action import Action


class ChangeDirectoryAction(Action):
    def __init__(self):
        super().__init__()
        self.identification_string = r'cd\s*([^ ]+)?'
        self.description = Path(__file__).with_suffix('.yaml').read_text()
        self.folder_name = None

    def match(self, action_string: str):
        return bool(re.fullmatch(self.identification_string, action_string))

    def parse(self, action_string: str):
        match = re.fullmatch(self.identification_string, action_string)
        if match is not None:
            self.folder_name = match.group(1)

    def execute(self,
                logger,
                agent_status: 'AgentStatus' = None,
                git_comm_interface: GitCommunicationInterface = None) -> 'AgentStatus':

        new_agent_status = copy.deepcopy(agent_status)

        # Verify the directory exists
        absolute_path_new_folder = agent_status.current_directory / self.folder_name
        if not os.path.exists(absolute_path_new_folder):
            result = f"Directory not found: {absolute_path_new_folder}\n"
        else:
            new_agent_status.current_directory = absolute_path_new_folder
            result = f"Directory change successful: {absolute_path_new_folder}\n"

            # Get the list of files and directories
            names = os.listdir(absolute_path_new_folder)

            for name in names:
                # Get the full path
                full_path = os.path.join(absolute_path_new_folder, name)

                # Get details
                stats = os.stat(full_path)

                # File size in bytes
                size = stats.st_size

                # Last modified time
                mtime = datetime.datetime.fromtimestamp(stats.st_mtime).strftime('%b %d %H:%M')

                # Directory or file
                dir_or_file = "<DIR>" if os.path.isdir(full_path) else ""

                # Append details to the result
                result += f"{dir_or_file}\t{size}\t{mtime}\t{name}\n"

        new_agent_status.last_action_return = result
        return new_agent_status
