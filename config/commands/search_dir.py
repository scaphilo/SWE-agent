#!/usr/bin/env python3
# @yaml
# signature: search_dir <search_term> [<dir>]
# docstring: searches for search_term in all files in dir. If dir is not provided, searches in the current directory
# arguments:
#   search_term:
#     type: str
#     description: the term to search for
#     required: true
#   dir:
#     type: str
#     description: the directory to search in (if not provided, searches in the current directory)
#     required: false

import os
import sys
import fnmatch


def search_dir(search_term: str, dir_path: str ='.'):
    # Check if directory exists
    if not os.path.isdir(dir_path):
        print(f"Directory {dir_path} not found")
        return

    matches = []
    # Walk through directory
    for dirpath, dirs, files in os.walk(dir_path):
        for filename in fnmatch.filter(files, '*.*'):
            # Open each file
            with open(os.path.join(dirpath, filename)) as file:
                # Search each line
                for line_num, line in enumerate(file, 1):
                    # If search string is found, print
                    if search_term in line:
                        matches.append((filename, line_num, line.strip()))
    # If no match found
    if not matches:
        print(f"No matches found for \"{search_term}\" in {dir_path}")
        return

    file_matches = len(matches)
    # If more than 100 files matched
    if file_matches > 100:
        print(f"More than {file_matches} files matched for \"{search_term}\" in {dir_path}. Please narrow your search.")
        return

    print(f"Found {file_matches} matches for \"{search_term}\" in {dir_path}:")
    for match in matches:
        print(f"{match[0]} (line {match[1]}: {match[2]})")
    print(f"End of matches for \"{search_term}\" in {dir_path}")


if __name__ == "__main__":
    args = sys.argv[1:]
    search_term = args[0]
    dir_path = args[1] if len(args) > 1 else "."
    search_dir(search_term, dir_path)