import os
import fnmatch
import re
from pathlib import Path
from swe_agent.swe_agent.action.action import Action


class FindFileAction(Action):
    identification_string = r'find_file\s*([^ ]+)(?:\s*(.*))?'

    def __init__(self):
        super().__init__()
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

    def execute(self, logger, window_size: int = None, overlap: int = None,
                current_line: int = None, current_file: Path = None):
        logger.info(f'Find file called with: filename={self.file_name}, directory={self.dir_path}')

        if not os.path.isdir(self.dir_path):
            logger.error(f"Directory {self.dir_path} not found")
            return

        matches = []
        for dirpath, dirs, files in os.walk(self.dir_path):
            for filename in fnmatch.filter(files, self.file_name):
                matches.append(os.path.join(dirpath, filename))

        if not matches:
            logger.error(f"No matches found for \"{self.file_name}\" in {self.dir_path}")
            return

        logger.info(f"Found {len(matches)} matches for \"{self.file_name}\" in {self.dir_path}")
        for filename in matches:
            logger.info(filename)