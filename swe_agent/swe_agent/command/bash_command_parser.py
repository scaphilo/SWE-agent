import re
from pathlib import Path
from typing import List

import yaml

from swe_agent.swe_agent.command.command_parser import CommandParser
from swe_agent.swe_agent.command.commands import Command


class BashCommandParser(CommandParser):
    def parse_command_file(self, path: str) -> List[Command]:
        print('Parsing command file:', path)
        contents = open(path, "r").read()
        if contents.strip().startswith("#!"):
            commands = self.parse_script(path, contents)
        else:
            if not path.endswith(".sh") and not Path(path).name.startswith("_"):
                raise ValueError((
                    f"Source file {path} does not have a .sh extension.\n"
                    "Only .sh files are supported for bash function parsing.\n"
                    "If you want to use a non-shell file as a command (script), "
                    "it should use a shebang (e.g. #!/usr/bin/env python)."
                    ))
            return self.parse_bash_functions(contents)
        if len(commands) == 0 and not Path(path).name.startswith("_"):
            raise ValueError((
                f"Non-shell file {path} does not contain any commands.\n"
                "If you want to use a non-shell file as a command (script), "
                "it should contain exactly one @yaml docstring. "
                "If you want to use a file as a utility script, "
                "it should start with an underscore (e.g. _utils.py)."
                ))
        else:
            return commands

    @staticmethod
    def parse_bash_functions(contents) -> List[Command]:
        """
        Simple logic for parsing a bash file and segmenting it into functions.

        Assumes that all functions have their name and opening curly bracket in one line,
        and closing curly bracket in a line by itself.
        """
        lines = contents.split("\n")
        commands = []
        idx = 0
        docs = []
        while idx < len(lines):
            line = lines[idx]
            idx += 1
            if line.startswith("# "):
                docs.append(line[2:])
            elif line.strip().endswith("() {"):
                name = line.split()[0][:-2]
                code = line
                while lines[idx].strip() != "}":
                    code += lines[idx]
                    idx += 1
                code += lines[idx]
                docstring, end_name, arguments, signature = None, None, None, name
                docs_dict = yaml.safe_load("\n".join(docs).replace('@yaml', ''))
                if docs_dict is not None:
                    docstring = docs_dict["docstring"]
                    end_name = docs_dict.get("end_name", None)
                    arguments = docs_dict.get("arguments", None)
                    if "signature" in docs_dict:
                        signature = docs_dict["signature"]
                    else:
                        if arguments is not None:
                            for param, settings in arguments.items():
                                if settings["required"]:
                                    signature += f" <{param}>"
                                else:
                                    signature += f" [<{param}>]"
                command = Command.from_dict({
                    "code": code,
                    "docstring": docstring,
                    "end_name": end_name,
                    "name": name,
                    "arguments": arguments,
                    "signature": signature
                })
                commands.append(command)
                docs = []
        return commands

    @staticmethod
    def parse_script(path, contents) -> List[Command]:
        pattern = re.compile(r'^#\s*@yaml\s*\n^#.*(?:\n#.*)*', re.MULTILINE)
        matches = pattern.findall(contents)
        if len(matches) == 0:
            return []
        elif len(matches) > 1:
            raise ValueError((
                "Non-shell file contains multiple @yaml tags.\n"
                "Only one @yaml tag is allowed per script."
                ))
        else:
            yaml_content = matches[0]
            yaml_content = re.sub(r'^#', '', yaml_content, flags=re.MULTILINE)
            docs_dict = yaml.safe_load(yaml_content.replace('@yaml', ''))
            assert docs_dict is not None
            docstring = docs_dict["docstring"]
            end_name = docs_dict.get("end_name", None)
            arguments = docs_dict.get("arguments", None)
            signature = docs_dict.get("signature", None)
            name = Path(path).name.rsplit(".", 1)[0]
            if signature is None and arguments is not None:
                signature = name
                for param, settings in arguments.items():
                    if settings["required"]:
                        signature += f" <{param}>"
                    else:
                        signature += f" [<{param}>]"
            code = contents
            return [Command.from_dict({
                "code": code,
                "docstring": docstring,
                "end_name": end_name,
                "name": name,
                "arguments": arguments,
                "signature": signature
            })]

    def generate_command_docs(self, commands: List[Command], subroutine_types, **kwargs) -> str:
        docs = ""
        for cmd in commands:
            if cmd.docstring is not None:
                docs += f"{cmd.signature or cmd.name} - {cmd.docstring.format(**kwargs)}\n"
        for subroutine in subroutine_types:
            if subroutine.docstring is not None:
                docs += f"{subroutine.signature or subroutine.name} - {subroutine.docstring.format(**kwargs)}\n"
        return docs
