#!/usr/bin/env python3
# @yaml
# signature: |-
#   python edit_linting.py <start_line>:<end_line>
#   <replacement_text>
#   end_of_edit
# docstring: replaces lines <start_line> through <end_line> (inclusive) with the given text in the open file.
#   The replacement_text text is terminated by a line with only end_of_edit on it. All of the <replacement_text text>
#   will be entered, so make sure your indentation is formatted properly. Python files will be checked for
#   syntax errors after the edit. If the system detects a syntax error, the edit will not be executed.
#   Simply try to edit the file again, but make sure to read the error message and modify the edit command
#   you issue accordingly. Issuing the same command a second time will just lead to the same error message again.
# end_name: end_of_edit
# arguments:
#   start_line:
#     type: integer
#     description: the line number to start the edit at
#     required: true
#   end_line:
#     type: integer
#     description: the line number to end the edit at (inclusive)
#     required: true
#   replacement_text:
#     type: string
#     description: the text to replace the current selection with
#     required: true

import os
import argparse
from shutil import copyfile


def edit(current_file, start_line_end_line, replacement_text):

    start_line, end_line = start_line_end_line.split(":")

    if not start_line.isdigit() or not end_line.isdigit():
        print("start_line and end_line must be natural numbers.")
        return

    start_line = int(start_line) - 1  # to make it 0-indexed, like python indices
    end_line = int(end_line)
    replacement_text = replacement_text.split('\n')

    backup_file = "_backup".format(os.path.basename(current_file))
    copyfile(current_file, backup_file)  # creating a backup

    with open(current_file, "r") as file:
        lines = file.readlines()

    lines[start_line:end_line] = replacement_text

    with open(current_file, "w") as file:
        file.writelines(lines)

    # Runs linter only if current file is a python file
    if current_file.endswith('.py'):
        import subprocess
        lint_output = subprocess.getoutput("flake8 --select=F821,F822,F831,E111,E112,E113,E999,E902 " + current_file)
        print(lint_output)

    os.remove(backup_file)  # remove backup file


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="This script replaces lines <start_line> "                                                 "through <end_line> (inclusive) "
                                                 "with the given text in the open file.")
    parser.add_argument('--current_file', type=str, help='The file to work on',
                        default=os.getenv('CURRENT_FILE'))
    parser.add_argument('start_end', type=str,
                        help='lines to replace in the format <start_line>:<end_line>')
    parser.add_argument('replacement_text', type=str,
                        help='Text to replace the current selection with',
                        nargs='?', default='')

    args = parser.parse_args()

    if args.current_file is None:
        print("No file specified, and environment variable 'CURRENT_FILE' not set.")
    else:
        edit(args.current_file, args.start_end, args.replacement_text)
