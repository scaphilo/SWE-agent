import re
import math
from pathlib import Path
from swe_agent.swe_agent.action.action import Action


class GoToLineAction(Action):
    def __init__(self):
        super().__init__()
        self.identification_string = r'goto_line\s*([0-9]+)'
        self.description = Path(__file__).with_suffix('.yaml').read_text()
        self.line_number = None

    def match(self, action_string: str):
        return bool(re.fullmatch(self.identification_string, action_string))

    def parse(self, action_string: str):
        match = re.fullmatch(self.identification_string, action_string)
        if match is not None:
            self.line_number = int(match.group(1))

    def execute(self, logger,
                window_size: int = None,
                overlap: int = None,
                current_line: int = None,
                current_file: Path = None,
                git_comm_interface: 'GitCommunicationInterface' = None) -> str:
        logger.info(f'Go to line called with: line_number={self.line_number}')

        if current_file is None or self.line_number is None:
            logger.error("No file open or line number provided.")
            return

        with open(current_file, 'r') as file:
            max_line = sum(1 for _ in file)

        if self.line_number > max_line:
            logger.error(f"Requested line number is greater than the total number of lines {max_line}.")
            return

        # I'm not sure what were the semantics of your constraints, thus you might need to adjust following lines
        offset = math.floor(window_size / 6)
        new_current_line = max(self.line_number + math.floor(window_size / 2) - offset, 1)

        logger.info(f"Moved cursor to line {new_current_line}.")