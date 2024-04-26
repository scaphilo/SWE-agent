import re
import math
import os
from pathlib import Path
from swe_agent.swe_agent.action.action import Action


class OpenFileAction(Action):
    def __init__(self):
        super().__init__()
        self.identification_string = r'open_file\s*([^ ]+)(?:\s*([0-9]+))?'
        self.description = Path(__file__).with_suffix('.yaml').read_text()
        self.path = None
        self.line_number = None

    def match(self, action_string: str):
        return bool(re.fullmatch(self.identification_string, action_string))

    def parse(self, action_string: str):
        match = re.fullmatch(self.identification_string, action_string)
        if match is not None:
            self.path = match.group(1)
            self.line_number = int(match.group(2)) if match.group(2) is not None else None

    @staticmethod
    def constrain_line(current_file, current_line, window):
        if current_file is None:
            print("No file open. Use the open command first.")
            return

        with open(current_file, 'r') as f:
            max_line = sum(1 for line in f)

        half_window = math.floor(window / 2)

        current_line = max(min(int(current_line), max_line - half_window), half_window)
        new_current_line = str(current_line)
        return new_current_line

    @staticmethod
    def print(current_file, current_line, window):

        with open(current_file, 'r') as f:
            total_lines = sum(1 for line in f)

        print("[File: {} ({} lines total)]".format(os.path.realpath(current_file), total_lines))


        lines_above = max(current_line - window/2, 0)
        lines_below = max(total_lines - current_line - window/2, 0)

        if lines_above > 0:
            print("({} more lines above)".format(math.floor(lines_above)))

        with open(current_file, 'r') as f:
            lines = f.readlines()
        print(''.join(lines[math.floor(max(current_line + window/2, window/2) - window):math.floor(max(current_line + window/2, window/2))]))

        if lines_below > 0:
            print("({} more lines below)".format(math.ceil(lines_below)))


    def execute(self, logger,
                window_size: int = None,
                overlap: int = None,
                current_line: int = None,
                current_file: Path = None,
                git_comm_interface: 'GitCommunicationInterface' = None):
        logger.info(f'Open file called with: path={self.path}, line_number={self.line_number}')

        # Check if file exists and is not directory
        if not os.path.exists(self.path) or os.path.isdir(self.path):
            logger.error("File path is not valid.")
            return

        if self.line_number is not None:

            # Open file and compute the number of lines
            with open(self.path, 'r') as file:
                max_line = sum(1 for _ in file)

            # Check if the required line number is within the valid range
            if not 1 <= self.line_number <= max_line:
                logger.error("Line number is not within the valid range.")
                return

        # Set the environment variables for the current file and the current line
        new_current_line = os.path.realpath(self.path)
        if self.line_number is not None:
            new_current_line = str(self.line_number)


        # Call the _constrain_line function
        new_current_line = self._constrain_line(current_file, new_current_line, window_size)

        # Call the _print function
        new_current_line = self._print(current_file, new_current_line, window_size)

        return new_current_line
