import os
import re
import copy
from pathlib import Path
from swe_agent.swe_agent.action.action import Action


class SearchFileAction(Action):
    def __init__(self):
        super().__init__()
        self.identification_string = r'search_file\s*([^ ]+)(?:\s*([^ ]+))?'
        self.description = Path(__file__).with_suffix('.yaml').read_text()
        self.search_term = None
        self.file = None

    def match(self, action_string: str):
        return bool(re.fullmatch(self.identification_string, action_string))

    def parse(self, action_string: str):
        match = re.fullmatch(self.identification_string, action_string)
        if match is not None:
            self.search_term = match.group(1).strip()
            self.file = match.group(2)

    def execute(self,
                logger,
                agent_status: 'AgentStatus' = None,
                git_comm_interface: 'GitCommunicationInterface' = None) -> 'AgentStatus':

        new_agent_status = copy.deepcopy(agent_status)
        logger.info(f'Search file called with: search_term={self.search_term}, file={self.file}')

        # Check if file is provided, otherwise use currently opened file
        if self.file is not None:
            file_path = agent_status.current_directory / self.file
        else:
            file_path = agent_status.current_directory / agent_status.current_file

        # Check if file exists
        if not os.path.isfile(file_path):
            error_msg = "File path is not valid."
            logger.error(error_msg)
            new_agent_status.last_action_return = error_msg
            return new_agent_status

        with open(file_path, 'r') as file:
            matches = [(i + 1, line.strip()) for i, line in enumerate(file) if self.search_term in line]

        match_report = f'Found {len(matches)} matches for "{self.search_term}" in {file_path}.'
        logger.info(match_report)
        new_agent_status.last_action_return = match_report

        return new_agent_status
