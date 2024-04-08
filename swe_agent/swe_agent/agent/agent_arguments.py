from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from simple_parsing import field
from simple_parsing.helpers import FlattenedAccess, FrozenSerializable

from swe_agent.swe_agent.agent.agent_config import AgentConfig


@dataclass(frozen=True)
class AgentArguments(FlattenedAccess, FrozenSerializable):
    model: 'ModelArguments' = None
    config_file: Optional[Path] = None
    config: Optional[AgentConfig] = field(default=None, cmd=False)

    def __post_init__(self):
        if self.config is None and self.config_file is not None:
            # If unassigned, we load the config from the file to store its contents with the overall arguments
            config = AgentConfig.load_yaml(self.config_file)
            object.__setattr__(self, "config", config)
        assert self.config is not None
        for subroutine in getattr(self.config, "subroutines", {}).values():
            model_args = getattr(subroutine, "model")
            object.__setattr__(model_args, "per_instance_cost_limit", self.model.per_instance_cost_limit)
            object.__setattr__(model_args, "total_cost_limit", self.model.total_cost_limit)
