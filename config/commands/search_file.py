#!/usr/bin/env python3
# @yaml
# signature: search_file <search_term> [<file>]
# docstring: searches for search_term in file. If file is not provided, searches in the current open file
# arguments:
#   search_term:
#     type: str
#     description: the term to search for
#     required: true
#   file:
#     type: str
#     description: the file to search in (if not provided, searches in the current open file)
#     required: false

import os
import sys
from pathlib import Path


def search_file(search_term: str, filepath: str = None):
    # Check if file is provided, otherwise get current
    if filepath:
        file_path = Path(filepath)
    else:
        file_path = Path(os.getenv('CURRENT_FILE', '.'))

    # Check if file exists
    if not file_path.is_file():
        print(f"File {filepath} not found.")
        return

    with file_path.open() as file:
        matches = [(i + 1, line.strip()) for i, line in enumerate(file) if search_term in line]

    # If no matches found
    if not matches:
        print(f"No matches found for \"{search_term}\" in {str(file_path.resolve())}")
        return

    num_matches = len(matches)
    # If more than 100 lines matched
    if num_matches > 100:
        print(f"More than {num_matches} lines matched for \"{search_term}\" in {str(file_path.resolve())}. Please narrow your search.")
        return

    print(f"Found {num_matches} matches for \"{search_term}\" in {str(file_path.resolve())}:")
    for match in matches:
        print(f"Line {match[0]}: {match[1]}")
    print(f"End of matches for \"{search_term}\" in {str(file_path.resolve())}")


if __name__ == "__main__":
    args = sys.argv[1:]
    search_term = args[0]
    file_path = args[1] if len(args) > 1 else None
    search_file(search_term, file_path)
