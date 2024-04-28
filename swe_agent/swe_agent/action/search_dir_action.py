import os
import re
import copy
import fnmatch
from pathlib import Path
from swe_agent.swe_agent.action.action import Action


class SearchDirAction(Action):
    def __init__(self):
        super().__init__()
        self.identification_string = r'search_dir\s*([^ ]+)(?:\s*([^ ]+))?'
        self.description = Path(__file__).with_suffix('.yaml').read_text()
        self.search_term = None
        self.dir = None

    def match(self, action_string: str):
        return bool(re.fullmatch(self.identification_string, action_string))

    def parse(self, action_string: str):
        match = re.fullmatch(self.identification_string, action_string)
        if match is not None:
            self.search_term = match.group(1)
            self.dir = match.group(2)

    def execute(self,
                logger,
                agent_status: 'AgentStatus' = None,
                git_comm_interface: 'GitCommunicationInterface' = None) -> 'AgentStatus':

        new_agent_status = copy.deepcopy(agent_status)
        logger.info(f'Search directory called with: search_term={self.search_term}, directory={self.dir}')

        # Set the default directory to the current directory if none was provided
        dir_path = self.dir if self.dir is not None else '.'

        # Check if directory exists
        if not os.path.isdir(dir_path):
            error_msg = "Directory path is not valid."
            logger.error(error_msg)
            new_agent_status.last_action_return = error_msg
            return new_agent_status

        matches = []
        # Walk through directory
        for dirpath, dirs, files in os.walk(dir_path):
            for filename in fnmatch.filter(files, '*.*'):
                # Open each file
                with open(os.path.join(dirpath, filename)) as file:
                    # Search each line
                    for line_num, line in enumerate(file, 1):
                        # If search string is found, add it to matches
                        if self.search_term in line:
                            matches.append((filename, line_num, line.strip()))

        match_report = f'Found {len(matches)} matches for "{self.search_term}" in {dir_path}.'
        logger.info(match_report)
        new_agent_status.last_action_return = match_report

        return new_agent_status
