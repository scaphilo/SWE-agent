from abc import abstractmethod, ABC
from swe_agent.development_environment.git_communication_interface import GitCommunicationInterface


class Action(ABC):
    actions = []

    @staticmethod
    def parse_action(action_string: str):
        for action_object in Action.actions:
            if action_object.match(action_string):
                return action_object
        return None

    def __init__(self):
        Action.actions.append(self)

    @staticmethod
    def get_action_descriptions():
        all_actions_descriptions = [action.description for action in Action.actions]
        all_actions_descriptions = '\n'.join(all_actions_descriptions)
        return all_actions_descriptions

    @abstractmethod
    def match(self, action_string: str):
        pass

    @abstractmethod
    def parse(self, action_string: str):
        pass

    @abstractmethod
    def execute(self,
                logger,
                agent_status: 'AgentStatus' = None,
                git_comm_interface: GitCommunicationInterface = None) -> 'AgentStatus':
        pass


