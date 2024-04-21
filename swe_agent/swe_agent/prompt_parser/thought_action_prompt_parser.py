import re
from swe_agent.swe_agent.prompt_parser.prompt_parser import PromptParser, PromptParserFormatError
from swe_agent.swe_agent.command.commands import Command
from typing import List


class ThoughtActionPromptParser(PromptParser):
    """
    Expects the model response to be a discussion followed by a command wrapped in backticks.
    Example:
    Let's look at the files in the current directory.
    ```
    ls -l
    ```
    """
    _error_message = """\
    Your output was not formatted correctly. You must always include one discussion and one command as part of your 
    response. Make sure you do not have multiple discussion/command tags.
    Please make sure your output precisely matches the following format:
    DISCUSSION
    Discuss here with yourself about what your planning and what you're going to do in this step.
    
    ```
    command(s) that you're going to run
    ```
    """

    def __call__(self, model_response, commands: List[Command], strict=False) -> tuple[str, str]:
        """
        Parses the action from the output of the API call.
        We assume that the action is the last code block in the model_response.
        We also assume that the action is not nested within another code block.
        This is problematic if the model_response includes many unnamed ``` blocks.
        For instance:
        ```
        This is a code block.
        ```
        ```
        This is another code block.
        ```

        In this case, only the second code block will be parsed as the action.
        """
        code_block_pattern = re.compile(r'^```(\S*)\s*\n|^```\s*$', re.MULTILINE)
        stack = []
        model_action = ""
        model_thought = ""
        last_valid_block = None
        for match in code_block_pattern.finditer(model_response):
            if stack and not match.group(1):  # Closing of a code block
                start = stack.pop()
                # Check if it's not nested within another block
                if not stack:
                    last_valid_block = (start, match)
            elif match.group(1) is not None:  # Opening of a code block
                stack.append(match)
        if last_valid_block:
            start, end = last_valid_block
            thought = model_response[:start.start()] + model_response[end.end():]
            model_thought = thought
            model_action = model_response[start.end():end.start()]
            return model_thought, model_action
        raise PromptParserFormatError("No action found in model response.")