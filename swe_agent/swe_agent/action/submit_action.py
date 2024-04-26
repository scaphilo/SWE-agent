#!/usr/bin/env python3
# @yaml
# signature: submit
# docstring: submits your current code and terminates the session
import os
import subprocess


def submit():
    root_dir = os.getenv('ROOT')
    if root_dir is None:
        print('ROOT path not defined')
        return

    # Change directory to ROOT
    os.chdir(root_dir)

    # Check if the patch file exists and is non-empty
    patch_file = '/root/test.patch'
    if os.path.exists(patch_file) and os.path.getsize(patch_file) > 0:
        # Apply the patch in reverse
        subprocess.run(['git', 'apply', '-R'], input=open(patch_file).read())

    # Stage all changes
    subprocess.run(['git', 'add', '-A'])

    # Write staged changes to model.patch file
    with open('model.patch', 'w') as f:
        subprocess.run(['git', 'diff', '--cached'], stdout=f)

    # Read and print the contents of model.patch file
    with open('model.patch', 'r') as f:
        print('<<SUBMISSION||')
        print(f.read())
        print('||SUBMISSION>>')


if __name__ == '__main__':
    submit()
