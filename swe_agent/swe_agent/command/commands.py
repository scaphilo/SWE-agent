from dataclasses import dataclass
from typing import Dict, Optional
from simple_parsing.helpers import FrozenSerializable


@dataclass(frozen=True)
class AssistantMetadata(FrozenSerializable):
    """Pass observations to the assistant, and get back a response."""
    system_template: Optional[str] = None
    instance_template: Optional[str] = None


# TODO: first can be used for two-stage actions
# TODO: eventually might control high-level control flow
@dataclass(frozen=True)
class ControlMetadata(FrozenSerializable):
    """TODO: should be able to control high-level control flow after calling this command"""
    next_step_template: Optional[str] = None
    next_step_action_template: Optional[str] = None
    

@dataclass(frozen=True)
class Command(FrozenSerializable):
    code: str
    name: str
    docstring: Optional[str] = None
    end_name: Optional[str] = None  # if there is an end_name, then it is a multi-line command
    arguments: Optional[Dict] = None
    signature: Optional[str] = None


class ParseCommandMeta(type):
    _registry = {}

    def __new__(cls, name, bases, attrs):
        new_cls = super().__new__(cls, name, bases, attrs)
        if name != "ParseCommand":
            cls._registry[name] = new_cls
        return new_cls


# DEFINE NEW COMMAND PARSER FUNCTIONS BELOW THIS LINE


