import re
import os
import copy
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
                agent_status: 'AgentStatus' = None,
                git_comm_interface: 'GitCommunicationInterface' = None) -> 'AgentStatus':

        new_agent_status = copy.deepcopy(agent_status)
        logger.info(f'Scroll called with: upwards={self.upwards}')

        # Check if a file is currently open and the scroll direction is specified
        if agent_status.current_file is None or self.upwards is None:
            error_msg = "No file open or scroll direction provided."
            logger.error(error_msg)
            new_agent_status.last_action_return = error_msg
            return new_agent_status

        # Check if file exists
        absolute_path = agent_status.current_directory / agent_status.current_file
        if not os.path.exists(absolute_path):
            error_msg = "Current file does not exist."
            logger.error(error_msg)
            new_agent_status.last_action_return = error_msg
            return new_agent_status

        # Calculate new current line depending on the scroll direction
        new_current_line = agent_status.current_line - agent_status.window_size + agent_status.overlap \
            if self.upwards is True else agent_status.current_line + agent_status.window_size - agent_status.overlap

        # Constrain the line within the files content and change the line
        new_agent_status.current_line = OpenFileAction.constrain_line(absolute_path, new_current_line, agent_status.window_size)

        # Print the new location in the file to last_action_return
        new_agent_status.last_action_return = OpenFileAction.print(absolute_path, new_agent_status.current_line, agent_status.window_size)

        logger.info(f"New current line: {new_agent_status.current_line}")

        return new_agent_status