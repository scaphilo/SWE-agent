from abc import abstractmethod
from dataclasses import dataclass
from typing import List

from swe_agent.swe_agent.command.commands import ParseCommandMeta, Command


@dataclass
class CommandParser(metaclass=ParseCommandMeta):
    @classmethod
    def get(cls, name):
        try:
            return cls._registry[name]()
        except KeyError:
            raise ValueError(f"Command parser ({name}) not found.")

    @abstractmethod
    def parse_command_file(self, path: str) -> List[Command]:
        """
        Define how to parse a file into a list of commands.
        """
        raise NotImplementedError

    @abstractmethod
    def generate_command_docs(self, commands: List[Command], subroutine_types, **kwargs) -> str:
        """
        Generate a string of documentation for the given commands and subroutine types.
        """
        raise NotImplementedError
