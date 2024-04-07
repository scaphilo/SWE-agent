from dataclasses import dataclass

from simple_parsing.helpers import FrozenSerializable


@dataclass(frozen=True)
class ModelArguments(FrozenSerializable):
    model_name: str
    per_instance_cost_limit: float = 0.0
    total_cost_limit: float = 0.0
    temperature: float = 1.0
    top_p: float = 1.0
    replay_path: str = None
    host_url: str = "localhost:11434"
