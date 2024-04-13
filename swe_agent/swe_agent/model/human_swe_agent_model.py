from swe_agent import ModelArguments
from swe_agent.swe_agent.command.commands import Command
from swe_agent.swe_agent.model.models import SEWAgentModel


class HumanModel(SEWAgentModel):
    MODELS = {"human": {}}

    def __init__(self, model_arguments: ModelArguments, commands: list[Command]):
        super().__init__(model_arguments, commands)

        # Determine which commands require multi-line input
        self.multi_line_command_endings = {
            command.name: command.end_name
            for command in commands
            if command.end_name is not None
        }

    def history_to_messages(
        self, history: list[dict[str, str]], is_demonstration: bool = False
    ) -> list[dict[str, str]]:
        """
        Create `messages` by filtering out all keys except for role/content per `history` turn
        """
        # Remove system messages if it is a demonstration
        if is_demonstration:
            history = [entry for entry in history if entry["role"] != "system"]
            return '\n'.join([entry["content"] for entry in history])
        # Return history components with just role, content fields
        return [
            {k: v for k, v in entry.items() if k in ["role", "content"]}
            for entry in history
        ]

    def query(self, history: list[dict[str, str]], action_prompt: str = "> ") -> str:
        """
        Logic for handling user input to pass to SWEEnv
        """
        action = input(action_prompt)
        command_name = action.split()[0] if action else ""

        # Special handling for multi-line input actions (i.e. edit)
        if command_name in self.multi_line_command_endings:
            buffer = [action]
            end_keyword = self.multi_line_command_endings[command_name]
            while True:
                action = input("... ")
                buffer.append(action)
                if action.rstrip() == end_keyword:
                    # Continue reading input until terminating keyword inputted
                    break
            action = "\n".join(buffer)
        elif action.strip() == "start_multiline_command":  # do arbitrary multi-line input
            buffer = []
            while True:
                action = input("... ")
                if action.rstrip() == "end_multiline_command":
                    break
                buffer.append(action)
            action = "\n".join(buffer)
        return action
