import os
import re
import copy
from pathlib import Path
from swe_agent.swe_agent.action.action import Action


class CreateFileAction(Action):
    def __init__(self):
        super().__init__()
        self.identification_string = r'create_file\s*([^ ]+)'
        self.description = Path(__file__).with_suffix('.yaml').read_text()
        self.filename = None

    def parse(self, action_string: str):
        match = re.fullmatch(self.identification_string, action_string)
        if match is not None:
            self.filename = match.group(1).strip()

    def match(self, action_string: str):
        return bool(re.fullmatch(self.identification_string, action_string))

    def execute(self,
                logger,
                agent_status: 'AgentStatus' = None,
                git_comm_interface: 'GitCommunicationInterface' = None) -> 'AgentStatus':
        logger.info(f'Create file called with: filename={self.filename}')

        # Create new agent_status and inherit values from the previously obtained status (to avoid None values)
        new_agent_status = copy.deepcopy(agent_status)

        if os.path.exists(self.filename):
            log_string = f"Error: File '{self.filename}' already exists."
            logger.error(log_string)
            new_agent_status.last_action_return = log_string
        else:
            # Create the file with an empty new line
            with open(self.filename, 'w') as fp:
                fp.write("\n")
            log_string = f"File '{self.filename}' created successfully."
            logger.info(log_string)
            new_agent_status.last_action_return = log_string

        return new_agent_status
