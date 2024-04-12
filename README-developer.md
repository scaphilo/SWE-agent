# Project Title

## Table of Contents
1. [Overview](#overview)
2. [Installation](#installation)
3. [Command Line Arguments](#command-line-arguments)
4. [Contributing](#contributing)
5. [Contact](#contact)

## Overview
<Provide a brief description of what the project does, its architecture, and the technologies used>

## Installation
<Provide detailed instructions for setting up a development environment, including steps to install dependencies>

## Command Line Arguments
The `run.py` script takes a number of command line arguments to customize its behavior.

The priority for setting these parameters is as follows:

1. Command line arguments have the highest priority. If an argument is provided at runtime, it will override all other defaults.
2. The `ScriptArguments` class in `script_arguments.py`. If a default value is defined in this class for an argument, it will be used when that argument is not provided at the command line.
3. Global defaults set in the `default_params` variable in the `run.py` script have the lowest priority. They serve as a 'fall-back' option when no value is provided either at the command line or in the `ScriptArguments` class.

To use a command line argument, provide it in the format `--argument value` when running the script. For example, to set the `mode` argument to `test`, you can use:

<code>python run.py --mode test</code>

Refer to the code comments in the `ScriptArguments` class for a detailed list of available arguments and their expected values.

## Contributing
<Provide guidelines on how to contribute, any tests that need to be passed, and any code styling guidelines>

## Contact
<Contact details for the project maintainers>