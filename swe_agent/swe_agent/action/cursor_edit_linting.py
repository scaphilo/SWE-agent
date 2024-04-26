#!/usr/bin/env python3
# @yaml
# signature: |-
#   cursor_edit_linting
#   <replacement_text>
#   end_of_edit
# docstring: replaces *all* of the text between the START CURSOR and the END CURSOR with the replacement_text.
# The replacement text is terminated by a line with only end_of_edit on it. All of the <replacement_text>
# will be entered, so make sure your indentation is formatted properly. To enter text at the beginning of the file,
# set START CURSOR and END CURSOR to 0.
# Use set_cursors to move the cursors around. Python files will be checked for syntax errors after the edit.

# end_name: end_of_edit
# arguments:
#   replacement_text:
#     type: str
#     description: the text to replace the current selection with
#     required: true

import os
import sys
from pathlib import Path
from flake8.api.legacy import get_style_guide


def cursor_edit_linting(replacement_text, current_file=None, start_cursor=-1, end_cursor=-1):
    # Use the current file from the argument or the environment variable
    current_file_path = Path(current_file) if current_file else Path(os.getenv('CURRENT_FILE'))

    if start_cursor == -1:
        start_cursor = int(os.getenv('START_CURSOR', '0'))
    if end_cursor == -1:
        end_cursor = int(os.getenv('END_CURSOR', '1'))

    if not current_file_path.is_file():
        print('No file open. Use the `open` command first.')
        return

    # Create a backup of the current file
    backup_file_path = current_file_path.parent / (current_file_path.name + '_backup')
    with current_file_path.open() as src, backup_file_path.open('w') as dst:
        dst.write(src.read())

    # Read the file line by line into a list
    with current_file_path.open() as file:
        lines = file.readlines()

    # Replace the content between start_cursor and end_cursor with replacement_text
    new_content = "".join(lines[:start_cursor-1]) + replacement_text + "".join(lines[end_cursor:])

    # Write the new content back into the original file
    with current_file_path.open('w') as file:
        file.write(new_content)

    current_file_str = str(current_file_path.resolve())

    # Run linter
    style_guide = get_style_guide(select=['F821', 'F822', 'F831', 'E111', 'E112', 'E113', 'E999', 'E902'])
    report = style_guide.check_files([current_file_str])

    if report.total_errors == 0:
        print("File updated. Please review the changes.")
    else:
        print("Your proposed edit has introduced new syntax error(s).")
        print("Fix the errors and try again.")

    # Remove backup file
    backup_file_path.unlink()


if __name__ == "__main__":
    args = sys.argv[1:]
    replacement_text = args[0]
    current_file = args[1] if len(args) > 1 else None
    start_cursor = int(args[2]) if len(args) > 2 else -1
    end_cursor = int(args[3]) if len(args) > 3 else -1
    cursor_edit_linting(replacement_text, current_file, start_cursor, end_cursor)