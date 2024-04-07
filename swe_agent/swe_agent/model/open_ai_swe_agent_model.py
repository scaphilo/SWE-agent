import os

import config
from openai import OpenAI, BadRequestError
from openai.lib.azure import AzureOpenAI
from tenacity import retry, wait_random_exponential, stop_after_attempt, retry_if_not_exception_type

from swe_agent import ModelArguments
from swe_agent.swe_agent.command.commands import Command
from swe_agent.swe_agent.model.models import SEWAgentModel, CostLimitExceededError


class OpenAIModel(SEWAgentModel):
    MODELS = {
        "gpt-3.5-turbo-0125": {
            "max_context": 16_385,
            "cost_per_input_token": 5e-07,
            "cost_per_output_token": 1.5e-06,
        },
        "gpt-3.5-turbo-1106": {
            "max_context": 16_385,
            "cost_per_input_token": 1.5e-06,
            "cost_per_output_token": 2e-06,
        },
        "gpt-3.5-turbo-16k-0613": {
            "max_context": 16_385,
            "cost_per_input_token": 1.5e-06,
            "cost_per_output_token": 2e-06,
        },
        "gpt-4-32k-0613": {
            "max_context": 32_768,
            "cost_per_input_token": 6e-05,
            "cost_per_output_token": 0.00012,
        },
        "gpt-4-0613": {
            "max_context": 8_192,
            "cost_per_input_token": 3e-05,
            "cost_per_output_token": 6e-05,
        },
        "gpt-4-1106-preview": {
            "max_context": 128_000,
            "cost_per_input_token": 1e-05,
            "cost_per_output_token": 3e-05,
        },
        "gpt-4-0125-preview": {
            "max_context": 128_000,
            "cost_per_input_token": 1e-05,
            "cost_per_output_token": 3e-05,
        },
    }

    SHORTCUTS = {
        "gpt3": "gpt-3.5-turbo-1106",
        "gpt3-legacy": "gpt-3.5-turbo-16k-0613",
        "gpt4": "gpt-4-1106-preview",
        "gpt4-legacy": "gpt-4-0613",
        "gpt4-0125": "gpt-4-0125-preview",
        "gpt3-0125": "gpt-3.5-turbo-0125",
    }

    def __init__(self, args: ModelArguments, commands: list[Command]):
        super().__init__(args, commands)

        # Set OpenAI key
        cfg = config.Config(os.path.join(os.getcwd(), "keys.cfg"))
        if self.args.model_name.startswith("azure"):
            self.api_model = cfg["AZURE_OPENAI_DEPLOYMENT"]
            self.client = AzureOpenAI(api_key=cfg["AZURE_OPENAI_API_KEY"], azure_endpoint=cfg["AZURE_OPENAI_ENDPOINT"], api_version=cfg.get("AZURE_OPENAI_API_VERSION", "2024-02-01"))
        else:
            self.client = OpenAI(api_key=cfg["OPENAI_API_KEY"])

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
        Query the OpenAI API with the given `history` and return the response.
        """
        try:
            # Perform OpenAI API call
            response = self.client.chat.completions.create(
                messages=self.history_to_messages(history),
                model=self.api_model,
                temperature=self.args.temperature,
                top_p=self.args.top_p,
            )
        except BadRequestError as e:
            raise CostLimitExceededError(f"Context window ({self.model_metadata['max_context']} tokens) exceeded")
        # Calculate + update costs, return response
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        self.update_stats(input_tokens, output_tokens)
        return response.choices[0].message.content
