
import re
from pathlib import Path
from swe_agent.swe_agent.action.action import Action
from swe_agent.swe_agent.action.open_file_action import OpenFileAction


class ScrollAction(Action):
    def __init__(self):
        super().__init__()
        self.identification_string = r'scroll\s*(up|down)'
        self.description = Path(__file__).with_suffix('.yaml').read_text()
        self.upwards = None

    def parse(self, action_string: str):
        match = re.fullmatch(self.identification_string, action_string)
        if match is not None:
            self.upwards = match.group(1) == 'up'

    def match(self, action_string: str):
        return bool(re.fullmatch(self.identification_string, action_string))

    def execute(self, logger,
                window_size: int = None,
                overlap: int = None,
                current_line: int = None,
                current_file: Path = None,
                git_comm_interface: 'GitCommunicationInterface' = None
                ):
        logger.info(f'Scroll called with: upwards={self.upwards}')

        if current_file is None or self.upwards is None:
            logger.error("No file open or scroll direction provided.")
            return

        new_current_line = current_line - window_size + overlap \
            if self.upwards is True else current_line + window_size - overlap

        new_current_line = OpenFileAction.constrain_line(current_file, new_current_line, window_size)
        new_current_line = OpenFileAction.print(current_file, new_current_line, window_size)

        logger.info(f"New current line: {new_current_line}")