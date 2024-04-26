#!/usr/bin/env python3
# @yaml
# signature: open_file <path> [<line_number>]
# docstring: opens the file at the given path in the editor. If line_number is provided, the window will be moved
#     to include that line
# arguments:
#   path:
#     type: str
#     description: the path to the file to open
#     required: true
#   line_number:
#     type: int
#     description: the line number to move the window to (if not provided, the window will start at the top of the file)
#     required: false

import argparse
import re
import math
import os


def _constrain_line():
    current_file = os.getenv('CURRENT_FILE')
    if current_file is None:
        print("No file open. Use the open command first.")
        return

    window = int(os.getenv('WINDOW'))

    with open(current_file, 'r') as f:
        max_line = sum(1 for line in f)

    half_window = math.floor(window / 2)

    current_line = max(min(int(os.getenv('CURRENT_LINE')), max_line - half_window), half_window)
    os.environ['CURRENT_LINE'] = str(current_line)


def _print():
    current_file = os.getenv('CURRENT_FILE')

    with open(current_file, 'r') as f:
        total_lines = sum(1 for line in f)

    print("[File: {} ({} lines total)]".format(os.path.realpath(current_file), total_lines))

    window = int(os.getenv('WINDOW'))
    current_line = int(os.getenv('CURRENT_LINE'))

    lines_above = max(current_line - window/2, 0)
    lines_below = max(total_lines - current_line - window/2, 0)

    if lines_above > 0:
        print("({} more lines above)".format(math.floor(lines_above)))

    with open(current_file, 'r') as f:
        lines = f.readlines()
    print(''.join(lines[math.floor(max(current_line + window/2, window/2) - window):math.floor(max(current_line + window/2, window/2))]))

    if lines_below > 0:
        print("({} more lines below)".format(math.ceil(lines_below)))


def open_file(path, line_number):
    if not os.path.exists(path):
        print(f"File {path} not found")
        return

    if os.path.isdir(path):
        print(f"Error: {path} is a directory. You can only open files.")
        return

    if line_number == "":
        line_number = None

    if line_number is not None and not re.match("^[0-9]+$", line_number):
        print("Usage: open <file> [<line_number>]")
        print("Error: <line_number> must be a number")
        return

    if line_number is not None:
        line_number = int(line_number)

    with open(path, 'r') as file:
        max_line = sum(1 for line in file)

    if line_number is not None:
        if line_number > max_line:
            print(f"Warning: <line_number> ({line_number}) is greater than the number of lines in the file ({max_line})")
            print(f"Warning: Setting <line_number> to {max_line}")
            line_number = max_line
        elif line_number < 1:
            print("Warning: <line_number> is less than 1")
            print("Warning: Setting <line_number> to 1")
            line_number = 1

    # Set the environment variables for the current file and the current line
    os.environ['CURRENT_FILE'] = os.path.realpath(path)
    if line_number is not None:
        os.environ['CURRENT_LINE'] = str(line_number)

    # Call the _constrain_line function
    _constrain_line()

    # Call the _print function
    _print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Opens the file at the given path. If line number is provided, "
                                                 "the window will move to include that line.")

    parser.add_argument('path', type=str, help="The path to the file to open")
    parser.add_argument('--line_number', type=str, default="", help="The line number to move the window to")

    args = parser.parse_args()

    if args.path is None:
        print("No file specified.")
    else:
        open_file(args.path, args.line_number)
