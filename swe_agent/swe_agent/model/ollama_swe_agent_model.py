from collections import defaultdict

from tenacity import retry, wait_random_exponential, stop_after_attempt, retry_if_not_exception_type

from swe_agent import ModelArguments
from swe_agent.swe_agent.command.commands import Command
from swe_agent.swe_agent.model.models import SEWAgentModel, CostLimitExceededError, logger


class OllamaModel(SEWAgentModel):
    MODELS = defaultdict(lambda: {
        "max_context": 128_000,
        "cost_per_input_token": 0,
        "cost_per_output_token": 0,
    })

    def __init__(self, model_arguments: ModelArguments, commands: list[Command]):
        super().__init__(model_arguments, commands)
        from ollama import Client
        self.client = Client(host=model_arguments.host_url)

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

    @retry(
        wait=wait_random_exponential(min=1, max=15),
        reraise=True,
        stop=stop_after_attempt(3),
        retry=retry_if_not_exception_type((CostLimitExceededError, RuntimeError)),
    )
    def query(self, history: list[dict[str, str]]) -> str:
        """
        Query the Ollama API with the given `history` and return the response.
        """
        response = self.client.chat(
            model=self.api_model,
            messages=self.history_to_messages(history),
            options={
                "temperature": self.model_arguments.temperature,
                "top_p": self.model_arguments.top_p,
            }
        )
        # Calculate + update costs, return response
        if "prompt_eval_count" in response:
            input_tokens = response["prompt_eval_count"]
        else:
            logger.warning(
                "Prompt eval count not found in response. Using 0. "
                "This might be because the prompt has been cached. "
                "See https://github.com/princeton-nlp/SWE-agent/issues/44 "
                "and https://github.com/ollama/ollama/issues/3427."
            )
            input_tokens = 0
        output_tokens = response["eval_count"]
        self.update_stats(input_tokens, output_tokens)
        return response["message"]["content"]
