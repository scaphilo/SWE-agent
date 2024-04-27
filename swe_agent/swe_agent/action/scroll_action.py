
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
                agent_status: 'AgentStatus' = None,
                git_comm_interface: 'GitCommunicationInterface' = None) -> 'AgentStatus':

        from swe_agent.swe_agent.agent.agents import AgentStatus
        logger.info(f'Scroll called with: upwards={self.upwards}')

        if agent_status.current_file is None or self.upwards is None:
            logger.error("No file open or scroll direction provided.")
            return

        new_current_line = agent_status.current_line - agent_status.window_size + agent_status.overlap \
            if self.upwards is True else agent_status.current_line + agent_status.window_size - agent_status.overlap

        new_current_line = OpenFileAction.constrain_line(agent_status.current_file, new_current_line, agent_status.window_size)
        new_current_line = OpenFileAction.print(agent_status.current_file, new_current_line, agent_status.window_size)

        logger.info(f"New current line: {new_current_line}")
        new_agent_status = AgentStatus(window_size=agent_status.window_size,
                                       overlap=agent_status.overlap,
                                       current_line=new_current_line,
                                       current_file=agent_status.current_file,
                                       last_action_return=agent_status.window_size)
        return new_agent_status