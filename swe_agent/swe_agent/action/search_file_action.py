import os
import re
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
            self.search_term = match.group(1)
            self.file = match.group(2)

    def execute(self,
                logger,
                window_size: int = None,
                overlap: int = None,
                current_line: int = None,
                current_file: Path = None,
                git_comm_interface: 'GitCommunicationInterface' = None):
        logger.info(f'Search file called with: search_term={self.search_term}, file={self.file}')

        # Check if file is provided, otherwise use currently opened file
        filepath = self.file if self.file is not None else current_file

        # Check if file exists
        if not os.path.isfile(filepath):
            logger.error("File path is not valid.")
            return

        with open(filepath, 'r') as file:
            matches = [(i + 1, line.strip()) for i, line in enumerate(file) if self.search_term in line]

        logger.info(f'Found {len(matches)} matches for "{self.search_term}" in {filepath}.')