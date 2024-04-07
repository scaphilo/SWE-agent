from typing import List

from swe_agent.swe_agent.command.bash_command_parser import BashCommandParser
from swe_agent.swe_agent.command.commands import Command


class DetailedBashCommandParser(BashCommandParser):
    """
    # command_name:
    #   "docstring"
    #   signature: "signature"
    #   arguments:
    #     arg1 (type) [required]: "description"
    #     arg2 (type) [optional]: "description"
    """
    def get_signature(cmd):
        signature = cmd.name
        if "arguments" in cmd.__dict__ and cmd.arguments is not None:
                if cmd.end_name is None:
                    for param, settings in cmd.arguments.items():
                        if settings["required"]:
                            signature += f" <{param}>"
                        else:
                            signature += f" [<{param}>]"
                else:
                    for param, settings in list(cmd.arguments.items())[:-1]:
                        if settings["required"]:
                            signature += f" <{param}>"
                        else:
                            signature += f" [<{param}>]"
                    signature += f"\n{list(cmd.arguments[-1].keys())[0]}\n{cmd.end_name}"
        return signature

    def generate_command_docs(
            self,
            commands: List[Command],
            subroutine_types,
            **kwargs,
            ) -> str:
        docs = ""
        for cmd in commands + subroutine_types:
            docs += f"{cmd.name}:\n"
            if cmd.docstring is not None:
                docs += f"  docstring: {cmd.docstring}\n"
            if cmd.signature is not None:
                docs += f"  signature: {cmd.signature}\n"
            else:
                docs += f"  signature: {self.get_signature(cmd)}\n"
            if "arguments" in cmd.__dict__ and cmd.arguments is not None:
                docs += "  arguments:\n"
                for param, settings in cmd.arguments.items():
                    req_string = "required" if settings["required"] else "optional"
                    docs += f"    - {param} ({settings['type']}) [{req_string}]: {settings['description']}\n"
            docs += "\n"
        return docs
