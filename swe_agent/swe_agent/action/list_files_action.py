import re
import os
import copy
import datetime
from pathlib import Path

from swe_agent.development_environment.git_communication_interface import GitCommunicationInterface
from swe_agent.swe_agent.action.action import Action


class ListFilesAction(Action):
    def __init__(self):
        super().__init__()
        self.identification_string = r'^ls\s*(.*?)[\s\n]*$'
        self.description = Path(__file__).with_suffix('.yaml').read_text()

    def match(self, action_string: str):
        return bool(re.fullmatch(self.identification_string, action_string))

    def parse(self, action_string: str):
        pass

    def execute(self,
                logger,
                agent_status: 'AgentStatus' = None,
                git_comm_interface: GitCommunicationInterface = None) -> 'AgentStatus':

        new_agent_status = copy.deepcopy(agent_status)

       # Verify the directory exists
        if not os.path.exists(agent_status.current_directory):
            return f"Directory not found: {agent_status.current_directory}"

        # Get the list of files and directories
        names = os.listdir(agent_status.current_directory)

        # Initialize an empty result string
        result = ""

        for name in names:
            # Get the full path
            full_path = os.path.join(agent_status.current_directory, name)

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
