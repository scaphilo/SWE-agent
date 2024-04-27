import os
import re
from pathlib import Path
from swe_agent.swe_agent.action.action import Action


class CreateFileAction(Action):
    def __init__(self):
        super().__init__()
        self.identification_string = r'create_file (.*)'
        self.description = Path(__file__).with_suffix('.yaml').read_text()
        self.filename = None

    def parse(self, action_string: str):
        match = re.fullmatch(self.identification_string, action_string)
        if match is not None:
            self.filename = match.group(1)

    def match(self, action_string: str):
        return bool(re.fullmatch(self.identification_string, action_string))

    def execute(self,
                logger,
                agent_status: 'AgentStatus' = None,
                git_comm_interface: 'GitCommunicationInterface' = None) -> 'AgentStatus':
        logger.info(f'Create file called with: filename={self.filename}')

        if os.path.exists(self.filename):
            logger.error("Error: File '{}' already exists.".format(self.filename))
            # Use the existing open_file command to open the existing file
            # open_file(self.filename, None)
        else:
            # Create the file with an empty new line
            with open(self.filename, 'w') as fp:
                fp.write("\n")
            logger.info("File '{}' created successfully.".format(self.filename))
            # Use the existing open_file command to open the created file
            # open_file(self.filename, None)
