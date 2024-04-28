import re
import math
import os
import copy
from pathlib import Path
from swe_agent.swe_agent.action.action import Action


class OpenFileAction(Action):
    def __init__(self):
        super().__init__()
        self.identification_string = r'open_file\s*([^ ]+)(?:\s*([0-9]+))?'
        self.description = Path(__file__).with_suffix('.yaml').read_text()
        self.filename = None
        self.line_number = None

    def match(self, action_string: str):
        return bool(re.fullmatch(self.identification_string, action_string))

    def parse(self, action_string: str):
        match = re.fullmatch(self.identification_string, action_string)
        if match is not None:
            self.filename = match.group(1).strip()
            self.line_number = int(match.group(2)) if match.group(2) is not None else 0

    @staticmethod
    def constrain_line(current_file:str, current_line:int, window:int) -> int:
        with open(current_file, 'r') as f:
            max_line = sum(1 for line in f)

        half_window = math.floor(window / 2)

        current_line = max(min(int(current_line), max_line - half_window), half_window)
        new_current_line = current_line
        return new_current_line

    @staticmethod
    def print(current_file: str, current_line: int, window: int) -> str:
        with open(current_file, 'r') as f:
            total_lines = sum(1 for line in f)

        with open(current_file, 'r') as f:
            lines = f.readlines()

        start_line = math.floor(max(min(current_line + window/2, total_lines) - window, 0))
        end_line = math.floor(min(current_line + window/2, total_lines))
        read_lines = ''
        for i in range(start_line, end_line):
            read_lines += f'[{i+1}] {lines[i]}'
        return read_lines

    def execute(self,
                logger,
                agent_status: 'AgentStatus' = None,
                git_comm_interface: 'GitCommunicationInterface' = None) -> 'AgentStatus':

        new_agent_status = copy.deepcopy(agent_status)
        absolute_path = agent_status.current_directory / self.filename
        logger.info(f'Open file called with: filename={absolute_path}, line_number={self.line_number}')

        # Check if file exists and is not directory
        if not os.path.exists(absolute_path) or os.path.isdir(absolute_path):
            error_msg = "File path is not valid."
            logger.error(error_msg)
            new_agent_status.last_action_return = error_msg
            return new_agent_status

        if self.line_number != 0:
            # Open file and compute the number of lines
            with open(absolute_path, 'r') as file:
                max_line = sum(1 for _ in file)

            # Check if the required line number is within the valid range
            if not 1 <= self.line_number <= max_line:
                error_msg = "Line number is not within the valid range."
                logger.error(error_msg)
                new_agent_status.last_action_return = error_msg
                return new_agent_status

        # Set the environment variables for the current file and the current line
        new_agent_status.current_line = self.line_number
        new_agent_status.current_file = self.filename

        # Call the _constrain_line function
        new_agent_status.current_line = self.constrain_line(absolute_path,
                                                            new_agent_status.current_line,
                                                            agent_status.window_size)
        # Call the _print function
        new_agent_status.last_action_return = self.print(absolute_path,
                                                         new_agent_status.current_line,
                                                         agent_status.window_size)

        return new_agent_status
