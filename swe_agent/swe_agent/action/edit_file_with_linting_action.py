import os
import re
import copy
from pathlib import Path
from shutil import copyfile
from flake8.api.legacy import get_style_guide
from swe_agent.swe_agent.action.action import Action
from swe_agent.swe_agent.action.open_file_action import OpenFileAction


class EditFileWithLintingAction(Action):
    def __init__(self):
        super().__init__()
        self.identification_string = r'edit_linting (\d+):(\d+)\s(.*)end_of_edit'
        self.description = Path(__file__).with_suffix('.yaml').read_text()
        self.start_line = None
        self.end_line = None
        self.replacement_text = None

    def parse(self, action_string: str):
        matches = re.search(self.identification_string, action_string, re.DOTALL)
        if matches is not None:
            self.start_line, self.end_line, self.replacement_text = matches.groups()

    def match(self, action_string: str):
        return bool(re.search(self.identification_string, action_string, re.DOTALL))

    def execute(self,
                logger,
                agent_status: 'AgentStatus' = None,
                git_comm_interface: 'GitCommunicationInterface' = None) -> 'AgentStatus':
        logger.info(f'Execute called with: window_size={agent_status.window_size}, overlap={agent_status.overlap},'
                    f' current_line={agent_status.current_line}, current_file={agent_status.current_file}')
        new_agent_status = copy.deepcopy(agent_status)

        absolute_file_path = agent_status.current_directory / agent_status.current_file
        if not self.start_line.isdigit() or not self.end_line.isdigit():
            new_agent_status.last_action_return = "start_line and end_line must be natural numbers."
            return new_agent_status

        start_line = int(self.start_line) - 1  # to make it 0-indexed, like python indices
        end_line = int(self.end_line)

        backup_file = "_backup".format(os.path.basename(agent_status.current_file))
        copyfile(agent_status.current_file, backup_file)  # creating a backup

        with open(absolute_file_path, "r") as file:
            lines = file.readlines()

        lines[start_line:end_line] = self.replacement_text

        with open(absolute_file_path, "w") as file:
            file.writelines(lines)

        log_string = ""

        # Runs linter only if current file is a python file
        if agent_status.current_file.__str__().endswith('.py'):
            style_guide = get_style_guide(select=['F821', 'F822', 'F831', 'E111', 'E112', 'E113', 'E999', 'E902'])
            report = style_guide.check_files([agent_status.current_file.__str__()])
            if report.total_errors == 0:
                log_string = "File updated. Please review the changes:\n"
            else:
                log_string = "Your proposed edit has introduced new syntax error(s). Fix the errors and try again.\n"
        else:
            log_string = '''File updated. Because the file was not of type .py, the linter did not check the content.\nPlease review the changes yourself:\n'''

        os.remove(backup_file)

        # Constrain the line within the files content and change the line
        new_agent_status.current_line = OpenFileAction.constrain_line(absolute_file_path, start_line, agent_status.window_size)

        # Print the new location in the file to last_action_return
        new_agent_status.last_action_return = log_string+ OpenFileAction.print(absolute_file_path, new_agent_status.current_line, agent_status.window_size)

        return new_agent_status
