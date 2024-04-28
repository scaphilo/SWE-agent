import os
import copy
import re
import fnmatch
from pathlib import Path
from swe_agent.swe_agent.action.action import Action


class FindFileAction(Action):
    def __init__(self):
        super().__init__()
        self.identification_string = r'find_file\s*([^ ]+)(?:\s*(.*))?'
        self.description = Path(__file__).with_suffix('.yaml').read_text()
        self.file_name = None
        self.dir_path = '.'

    def parse(self, action_string: str):
        match = re.fullmatch(self.identification_string, action_string)
        if match is not None:
            self.file_name = match.group(1)
            dir_path_candidate = match.group(2)
            if dir_path_candidate is not None:
                self.dir_path = match.group(2)

    def match(self, action_string: str):
        return bool(re.fullmatch(self.identification_string, action_string))

    def execute(self,
                logger,
                agent_status: 'AgentStatus' = None,
                git_comm_interface: 'GitCommunicationInterface' = None) -> 'AgentStatus':
        logger.info(f'Find file called with: filename={self.file_name}, directory={self.dir_path}')

        new_agent_status = copy.deepcopy(agent_status)

        if not os.path.isdir(self.dir_path):
            log_string = f"Directory {self.dir_path} not found"
            logger.error(log_string)
            new_agent_status.last_action_return = log_string
            return new_agent_status

        matches = []
        for dirpath, dirs, files in os.walk(self.dir_path):
            for filename in fnmatch.filter(files, self.file_name):
                matches.append(os.path.join(dirpath, filename))

        if not matches:
            log_string = f"No matches found for \"{self.file_name}\" in {self.dir_path}"
            logger.error(log_string)
            new_agent_status.last_action_return = log_string
            return new_agent_status

        log_string = f"Found {len(matches)} matches for \"{self.file_name}\" in {self.dir_path}"
        logger.info(log_string)
        for filename in matches:
            logger.info(filename)

        new_agent_status.last_action_return = log_string + '\n' + '\n'.join(matches)

        return new_agent_status