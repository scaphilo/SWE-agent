import logging
from swe_agent import ModelArguments
from swe_agent.swe_agent.command.commands import Command
from typing import Optional
from swe_agent.swe_agent.model.model_apistats import APIStats

logger = logging.getLogger("api_models")


class ContextWindowExceededError(Exception):
    pass


class CostLimitExceededError(Exception):
    pass


class SEWAgentModel:
    MODELS = {}
    SHORTCUTS = {}

    def __init__(self, args: ModelArguments, commands: list[Command]):
        self.args = args
        self.commands = commands
        self.model_metadata = {}
        self.stats = APIStats()

        # Map `model_name` to API-compatible name `api_model`
        self.api_model = (
            self.SHORTCUTS[self.args.model_name]
            if self.args.model_name in self.SHORTCUTS
            else self.args.model_name
        )

        # Map model name to metadata (cost, context info)
        MODELS = {
            **{dest: self.MODELS[src] for dest, src in self.SHORTCUTS.items()},
            **self.MODELS,
        }
        if args.model_name in MODELS:
            self.model_metadata = MODELS[args.model_name]
        elif args.model_name.startswith("ft:"):
            ft_model = args.model_name.split(":")[1]
            self.model_metadata = MODELS[ft_model]
        elif args.model_name.startswith("ollama:"):
            self.api_model = args.model_name.split('ollama:', 1)[1]
            self.model_metadata = self.MODELS[self.api_model]
        elif args.model_name.startswith("azure:"):
            azure_model = args.model_name.split("azure:", 1)[1]
            self.model_metadata = MODELS[azure_model]
        else:
            raise ValueError(f"Unregistered model ({args.model_name}). Add model name to MODELS metadata to {self.__class__}")

    def reset_stats(self, other: APIStats = None):
        if other is None:
            self.stats = APIStats(total_cost=self.stats.total_cost)
            logger.info("Resetting model stats")
        else:
            self.stats = other

    def update_stats(self, input_tokens, output_tokens):
        """
        Calculates the cost of a response from the openai API.

        Args:
        input_tokens (int): The number of tokens in the prompt.
        output_tokens (int): The number of tokens in the response.

        Returns:
        float: The cost of the response.
        """
        # Calculate cost and update cost related fields
        cost = (
            self.model_metadata["cost_per_input_token"] * input_tokens
            + self.model_metadata["cost_per_output_token"] * output_tokens
        )
        self.stats.total_cost += cost
        self.stats.instance_cost += cost
        self.stats.tokens_sent += input_tokens
        self.stats.tokens_received += output_tokens
        self.stats.api_calls += 1

        # Log updated cost values to std. out.
        logger.info(
            f"input_tokens={input_tokens:_}, "
            f"output_tokens={output_tokens:_}, "
            f"instance_cost={self.stats.instance_cost:.2f}, "
            f"cost={cost:.2f}"
        )
        logger.info(
            f"total_tokens_sent={self.stats.tokens_sent:_}, "
            f"total_tokens_received={self.stats.tokens_received:_}, "
            f"total_cost={self.stats.total_cost:.2f}, "
            f"total_api_calls={self.stats.api_calls:_}"
        )

        # Check whether total cost or instance cost limits have been exceeded
        if (
            self.args.total_cost_limit > 0
            and self.stats.total_cost >= self.args.total_cost_limit
        ):
            logger.warning(
                f"Cost {self.stats.total_cost:.2f} exceeds limit {self.args.total_cost_limit:.2f}"
            )
            raise CostLimitExceededError("Total cost limit exceeded")

        if (
            self.args.per_instance_cost_limit > 0
            and self.stats.instance_cost >= self.args.per_instance_cost_limit
        ):
            logger.warning(
                f"Cost {self.stats.instance_cost:.2f} exceeds limit {self.args.per_instance_cost_limit:.2f}"
            )
            raise CostLimitExceededError("Instance cost limit exceeded")
        return cost

    def query(self, history: list[dict[str, str]]) -> str:
        raise NotImplementedError("Use a subclass of BaseModel")


def get_model(model_arguments: ModelArguments, commands: Optional[list[Command]] = None):
    """
    Returns correct model object given arguments and commands
    """
    from swe_agent.swe_agent.model.anthropic_swe_agent_model import AnthropicModel
    from swe_agent.swe_agent.model.human_swe_agent_model import HumanModel
    from swe_agent.swe_agent.model.human_thought_swe_agent_model import HumanThoughtModel
    from swe_agent.swe_agent.model.ollama_swe_agent_model import OllamaModel
    from swe_agent.swe_agent.model.open_ai_swe_agent_model import OpenAIModel
    from swe_agent.swe_agent.model.replay_swe_agent_model import ReplayModel

    if commands is None:
        commands = []

    if model_arguments.model_name == "human":
        return HumanModel(model_arguments, commands)
    if model_arguments.model_name == "human_thought":
        return HumanThoughtModel(model_arguments, commands)
    if model_arguments.model_name == "replay":
        return ReplayModel(model_arguments, commands)
    elif model_arguments.model_name.startswith("gpt") or model_arguments.model_name.startswith("ft:gpt") or model_arguments.model_name.startswith("azure:gpt"):
        return OpenAIModel(model_arguments, commands)
    elif model_arguments.model_name.startswith("claude"):
        return AnthropicModel(model_arguments, commands)
    elif model_arguments.model_name.startswith("ollama"):
        return OllamaModel(model_arguments, commands)
    else:
        raise ValueError(f"Invalid model name: {model_arguments.model_name}")
