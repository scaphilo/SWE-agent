from swe_agent.swe_agent.prompt_parser.prompt_parser import PromptParser, PromptParserFormatError
from swe_agent.swe_agent.command.commands import Command
from typing import List


class XMLThoughtActionPromptParser(PromptParser):
    """
    Expects the model response to be a discussion followed by a command wrapped in XML tags.
    Example:
    Let's look at the files in the current directory.
    <command>
    ls -l
    </command>
    """
    _error_message = """\
    Your output was not formatted correctly. You must always include one discussion and one command as part of your response. Make sure you do not have multiple discussion/command tags.
    Please make sure your output precisely matches the following format:
    """

    def __call__(self, model_response, commands: List[Command], strict=False):
        """
        Parses the action from the output of the API call.
        We assume that the action is the last code block in the model_response.
        We also assume that the action is not nested within another code block.
        This is problematic if the model_response includes many unnamed ``` blocks.
        For instance:
        <command>
        This is a code block.
        </command>
        <command>
        This is another code block.
        </command>

        In this case, only the second code block will be parsed as the action.
        """
        if "<command>" not in model_response or "</command>" not in model_response:
            raise PromptParserFormatError("No action found in model response.")
        # `action` is everything between the last <command> and </command> tags
        start_action = model_response.rfind('<command>') + len('<command>')  # start after the last <command> tag
        end_thought = model_response.rfind('<command>')  # end before the last <command> tag
        end_action = model_response.rfind('</command>')  # end before the last </command> tag
        restart_thought = model_response.rfind('</command>') + len('</command>')  # start after the last </command> tag
        # `thought` is everything not in between <command> and </command> tags (includes after the last </command> tag)
        action = model_response[start_action:end_action]
        thought = model_response[:end_thought] + model_response[restart_thought:]

        return thought.strip(), action.strip()