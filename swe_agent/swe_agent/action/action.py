from pathlib import Path
from abc import abstractmethod, ABC
from swe_agent.development_environment.git_communication_interface import GitCommunicationInterface


class Action(ABC):
    actions = []

    @staticmethod
    def parse_action(action_string: str):
        for action_class in Action.actions:
            instance = action_class()
            if instance.match(action_string):
                return instance
        return None

    def __init__(self):
        Action.actions.append(self)

    @abstractmethod
    def match(self, action_string: str):
        pass

    @abstractmethod
    def parse(self, action_string: str):
        pass

    @abstractmethod
    def execute(self,
                logger,
                window_size: int = None,
                overlap: int = None,
                current_line: int = None,
                current_file: Path = None,
                git_comm_interface: GitCommunicationInterface = None) -> str:
        pass


