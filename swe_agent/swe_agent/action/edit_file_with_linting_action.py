import os
import re
from pathlib import Path
from shutil import copyfile
from flake8.api.legacy import get_style_guide
from swe_agent.swe_agent.action.action import Action


class EditFileWithLintingAction(Action):
    def __init__(self):
        super().__init__()
        self.identification_string = r'edit_linting (\d+):(\d+)\s(.*)end_of_edit'
        self.description = Path(__file__).with_suffix('.yaml').read_text()
        self.start_line = None
        self.end_line = None
        self.replacement_text = None

    def parse(self, action_string: str):
        matches = re.fullmatch(self.identification_string, action_string, re.DOTALL)
        if matches is not None:
            self.start_line, self.end_line, self.replacement_text = matches.groups()

    def match(self, action_string: str):
        return bool(re.fullmatch(self.identification_string, action_string, re.DOTALL))

    def execute(self, logger, window_size: int = None, overlap: int = None,
                current_line: int = None, current_file: Path = None) -> str:
        logger.info(f'Execute called with: window_size={window_size}, overlap={overlap},'
                    f' current_line={current_line}, current_file={current_file}')
        if not self.start_line.isdigit() or not self.end_line.isdigit():
            return "start_line and end_line must be natural numbers."

        start_line = int(self.start_line) - 1  # to make it 0-indexed, like python indices
        end_line = int(self.end_line)

        backup_file = "_backup".format(os.path.basename(current_file))
        copyfile(current_file, backup_file)  # creating a backup

        with open(current_file, "r") as file:
            lines = file.readlines()

        lines[start_line:end_line] = self.replacement_text

        with open(current_file, "w") as file:
            file.writelines(lines)

        # Runs linter only if current file is a python file
        if current_file.__str__().endswith('.py'):
            style_guide = get_style_guide(select=['F821', 'F822', 'F831', 'E111', 'E112', 'E113', 'E999', 'E902'])
            report = style_guide.check_files([current_file.__str__()])

            if report.total_errors == 0:
                print("File updated. Please review the changes.")
            else:
                print("Your proposed edit has introduced new syntax error(s).")
                print("Fix the errors and try again.")

        os.remove(backup_file)

