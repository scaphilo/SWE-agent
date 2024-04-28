import re
import math
import copy
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
                agent_status: 'AgentStatus' = None,
                git_comm_interface: 'GitCommunicationInterface' = None) -> 'AgentStatus':

        new_agent_status = copy.deepcopy(agent_status)
        logger.info(f'Go to line called with: line_number={self.line_number}')

        if agent_status.current_file is None or self.line_number is None:
            log_string = "No file open or line number provided."
            logger.error(log_string)
            new_agent_status.last_action_return = log_string
            return new_agent_status

        with open(agent_status.current_file, 'r') as file:
            max_line = sum(1 for _ in file)

        if self.line_number > max_line:
            log_string = f"Requested line number is greater than the total number of lines {max_line}."
            logger.error(log_string)
            new_agent_status.last_action_return = log_string
            return new_agent_status

        offset = math.floor(agent_status.window_size / 6)
        new_current_line = max(self.line_number + math.floor(agent_status.window_size / 2) - offset, 1)
        new_agent_status.current_line = new_current_line

        log_string = f"Moved cursor to line {new_current_line}."
        logger.info(log_string)

        new_agent_status.last_action_return = log_string

        return new_agent_status
