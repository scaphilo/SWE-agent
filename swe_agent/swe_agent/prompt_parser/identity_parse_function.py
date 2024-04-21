from swe_agent.swe_agent.command.commands import Command
from typing import List
from swe_agent.swe_agent.prompt_parser.prompt_parser import PromptParser


class Identity(PromptParser):
    """
    This parser does not do any parsing. It just returns the model response as both the thought and action.
    """
    _error_message = """\
    It seems like something went wrong with your output. Please try again.
    """

    def __call__(self, model_response, commands: List[Command], strict=False):
        """
        This doesn't do any parsing. It just returns the model response as the thought and action.
        """
        return model_response, model_response
