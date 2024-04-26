import os
import re
from pathlib import Path
from swe_agent.swe_agent.action.action import Action
from swe_agent.development_environment.git_communication_interface import GitCommunicationInterface


class SubmitAction(Action):
    def __init__(self):
        super().__init__()
        self.identification_string = r'submit'
        self.description = Path(__file__).with_suffix('.yaml').read_text()

    def match(self, action_string: str):
        return bool(re.fullmatch(self.identification_string, action_string))

    def parse(self, action_string: str):
        return  # There are no additional arguments to parse in this action

    def execute(self, logger,
                window_size: int = None,
                overlap: int = None,
                current_line: int = None,
                current_file: Path = None,
                git_comm_interface: GitCommunicationInterface = None):
        logger.info(f'Submit action called.')

        root_dir = os.getenv('ROOT')
        if root_dir is None:
            logger.error('ROOT path not defined.')
            return

        # Change directory to ROOT
        os.chdir(root_dir)

        # Check if the patch file exists and is non-empty
        patch_file = '/root/test.patch'
        if os.path.exists(patch_file) and os.path.getsize(patch_file) > 0:
            git_comm_interface.repo.git.apply("-R")

        # Stage all changes
        git_comm_interface.repo.git.add("-A")

        # Write staged changes to model.patch file
        with open('model.patch', 'w') as f:
            git_comm_interface.repo.git.diff("--cached")

        # Read and print the contents of model.patch file
        with open('model.patch', 'r') as f:
            print('<<SUBMISSION||')
            print(f.read())
            print('||SUBMISSION>>')
