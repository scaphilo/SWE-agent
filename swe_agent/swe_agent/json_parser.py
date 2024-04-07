import json
import shlex
from typing import List

from swe_agent.swe_agent.command.commands import Command
from swe_agent.swe_agent.parsing import ParseFunction, FormatError, extract_keys, should_quote


class JsonParser(ParseFunction):
    """
    Expects the model response to be a JSON object.
    """
    _error_message = """\
    Your output could not be parsed as JSON. Please make sure your output 1) is valid JSON and
    2) Includes the "thought" and "command" fields.

    """

    def __call__(self, model_response, commands: List[Command], strict=False):
        """
        Parses the action from the output of the API call.
        We assume that model output is a JSON object with the following fields:
        {
            "thought": "discussion text here.",
            "command": {
                "arguments": {
                    "arg1": "value1",
                    "arg2": "value2",
                    ...
                },
                "name": "command_name"
            }
        }
        """
        try:
            data = json.loads(model_response)
            if not isinstance(data, dict):
                raise FormatError("Model output is not a JSON object.")

            # Check if required keys are present
            required_keys = ["thought", "command"]
            for key in required_keys:
                if key not in data:
                    raise FormatError(f"Key '{key}' is missing from model output.")

            # Check structure of 'command' key
            data_command = data["command"]
            if not isinstance(data_command, dict):
                raise FormatError("Value of 'command' key is not a JSON object.")

            # Check if required keys are present in 'command' object
            command_keys = ["name"]
            for key in command_keys:
                if key not in data_command:
                    raise FormatError(f"Key '{key}' is missing from 'command' object.")

            thought = data["thought"]

            # Generate action
            commands_dict = {c.name: c for c in commands}
            command = commands_dict.get(data_command["name"])
            if command is None:
                action = data_command['name']
                if "arguments" in data_command:
                    action += " " + ' '.join(data_command["arguments"].values())
            else:
                signature = command.signature
                signature = signature.replace("[", "").replace("]", "")\
                    .replace("<", "{").replace(">", "}")
                signature_args = extract_keys(signature)
                command_args = {k: "" for k in signature_args}

                if "arguments" in data_command:
                    for arg in signature_args:
                        if arg in data_command["arguments"]:
                            value = data_command["arguments"][arg]
                            if should_quote(value, command):
                                value = shlex.quote(value)
                            command_args[arg] = value
                action = signature.format(**command_args)
            action = action.strip()
            return thought, action
        except json.JSONDecodeError:
            raise FormatError("Model output is not valid JSON.")
