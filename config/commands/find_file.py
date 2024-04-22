#!/usr/bin/env python3
# @yaml
# signature: find_file <file_name> [<dir>]
# docstring: finds all files with the given name in dir. If dir is not provided, searches in the current directory
# arguments:
#   file_name:
#     type: string
#     description: the name of the file to search for
#     required: true
#   dir:
#     type: string
#     description: the directory to search in (if not provided, searches in the current directory)
#     required: false

import os
import sys
import fnmatch


def find_file(file_name, dir_path='.'):
    # Check if directory exists
    if not os.path.isdir(dir_path):
        print(f"Directory {dir_path} not found")
        return

    matches = []
    # Walth through directory
    for dirpath, dirs, files in os.walk(dir_path):
        for filename in fnmatch.filter(files, file_name):
            matches.append(os.path.join(dirpath, filename))

    # If no match found
    if not matches:
        print(f"No matches found for \"{file_name}\" in {dir_path}")
        return

    print(f"Found {len(matches)} matches for \"{file_name}\" in {dir_path}:")
    for filename in matches:
        print(filename)


if __name__ == "__main__":
    args = sys.argv[1:]
    file_name = args[0]
    dir_path = args[1] if len(args) > 1 else "."
    find_file(file_name, dir_path)
