from swe_agent.swe_agent.prompt_parser.prompt_parser import PromptParser, PromptParserFormatError
from swe_agent.swe_agent.command.commands import Command
from typing import List


class ActionPromptParser(PromptParser):
    """
    Expects the model response to be a single command.
    Example: "ls -l"
    """
    _error_message = """\
    The command you provided was not recognized. Please specify one of the commands (+ any necessary arguments) from the following list in your response. Do not include any other text.
    
    COMMANDS:
    {command_docs}
    """

    def __call__(self, model_response, commands: List[Command], strict=False):
        if model_response.split():
            action = model_response.strip().split()[0]
            if action in {command.name for command in commands}:
                return model_response, model_response
        raise PromptParserFormatError("First word in model response is not a valid command.")