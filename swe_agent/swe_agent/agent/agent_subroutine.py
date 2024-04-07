from dataclasses import dataclass
from typing import Optional, Any

from simple_parsing.helpers import FrozenSerializable

from swe_agent import ModelArguments


@dataclass(frozen=True)
class AgentSubroutine(FrozenSerializable):
    name: str
    agent_file: str
    return_type: str = None  # one of "action", "observation", "response", "state", "thought"
    init_observation: Optional[str] = None
    end_name: Optional[str] = None
    signature: Optional[str] = None
    docstring: Optional[str] = None
    model: Optional[ModelArguments] = None
    agent_args: Optional[Any] = None
