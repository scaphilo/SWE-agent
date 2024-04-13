import json
import os

from swe_agent import ModelArguments
from swe_agent.swe_agent.command.commands import Command
from swe_agent.swe_agent.model.models import SEWAgentModel


class ReplayModel(SEWAgentModel):
    MODELS = {"replay": {}}

    def __init__(self, model_arguments: ModelArguments, commands: list[Command]):
        super().__init__(model_arguments, commands)

        if self.model_arguments.replay_path is None or not os.path.exists(self.model_arguments.replay_path):
            raise ValueError(
                "--replay_path must point to a file that exists to run a replay policy"
            )

        self.replays = [
            list(json.loads(x).values())[0]
            for x in open(self.model_arguments.replay_path, "r").readlines()
        ]
        self.replay_idx = 0
        self.action_idx = 0

    def query(self, history: list[dict[str, str]]) -> str:
        """
        Logic for tracking which replay action to pass to SWEEnv
        """
        action = self.replays[self.replay_idx][self.action_idx]
        self.action_idx += 1

        # Assuming `submit` is always last action of replay trajectory
        if action == "submit":
            self.replay_idx += 1
            self.action_idx = 0

        return action
