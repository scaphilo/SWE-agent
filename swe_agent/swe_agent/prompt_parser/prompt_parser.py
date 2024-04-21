import textwrap
from abc import abstractmethod
from dataclasses import dataclass
from swe_agent.swe_agent.command.commands import Command
from typing import List


class PromptParserMeta(type):
    """
    Registry maps all inherited classes to their names.
    """
    _registry = {}

    def __new__(cls, name, bases, attrs):
        new_cls = super().__new__(cls, name, bases, attrs)
        if name != "ParseFunction":
            cls._registry[name] = new_cls
        return new_cls


@dataclass
class PromptParser(metaclass=PromptParserMeta):
    """
    Abstract class for the all types of prompt Parsers.
    We use get to generate the right parser based on the name of the parser.
    """
    _error_message = None

    @abstractmethod
    def __call__(self, model_response, commands: List[Command], strict=False):
        raise NotImplementedError

    @property
    def format_error_template(self):
        if self._error_message is None:
            raise NotImplementedError("You must define an error message for your parser.")
        return textwrap.dedent(self._error_message)

    @classmethod
    def get(cls, name):
        try:
            return cls._registry[name]()
        except KeyError:
            raise ValueError(f"Model output parser ({name}) not found.")


class PromptParserFormatError(Exception):
    pass



