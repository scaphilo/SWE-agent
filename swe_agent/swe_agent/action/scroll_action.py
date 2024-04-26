#!/usr/bin/env python3
# @yaml
# signature: scroll <direction>
# docstring: moves the window up or down {WINDOW} lines
# arguments:
#   direction:
#     type: str
#     description: can have value "up" or "down"
#     required: true
import os
from open_file_action import _print, _constrain_line


def _scroll(upwards:bool):
    current_file = os.getenv('CURRENT_FILE')
    if current_file is None:
        print("No file open. Use the open command first.")
        return

    window = int(os.getenv('WINDOW'))
    overlap = int(os.getenv('OVERLAP', 0))
    current_line = int(os.getenv('CURRENT_LINE'))
    if upwards is True:
        os.environ['CURRENT_LINE'] = str(current_line - window + overlap)
    else:
        os.environ['CURRENT_LINE'] = str(current_line + window + overlap)

    _constrain_line()
    _print()

def scroll_down():
    _scroll(upwards=False)

def scroll_up():
    _scroll(upwards=True)


if __name__ == "__main__":
    scroll_up()
