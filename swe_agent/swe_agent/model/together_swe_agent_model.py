import os

import config
import together
from tenacity import retry, wait_random_exponential, stop_after_attempt, retry_if_not_exception_type

from swe_agent import ModelArguments
from swe_agent.swe_agent.command.commands import Command
from swe_agent.swe_agent.model.models import SEWAgentModel, CostLimitExceededError


class TogetherModel(SEWAgentModel):
    # Check https://docs.together.ai/docs/inference-models for model names, context
    # Check https://www.together.ai/pricing for pricing
    MODELS = {
        "meta-llama/Llama-2-13b-chat-hf": {
            "max_context": 4096,
            "cost_per_input_token": 2.25e-07,
            "cost_per_output_token": 2.25e-07,
        },
        "meta-llama/Llama-2-70b-chat-hf": {
            "max_context": 4096,
            "cost_per_input_token": 9e-07,
            "cost_per_output_token": 9e-07,
        },
        "mistralai/Mistral-7B-Instruct-v0.2": {
            "max_context": 32768,
            "cost_per_input_token": 2e-07,
            "cost_per_output_token": 2e-07,
        },
        "togethercomputer/RedPajama-INCITE-7B-Chat": {
            "max_context": 2048,
            "cost_per_input_token": 2e-07,
            "cost_per_output_token": 2e-07,
        },
        "mistralai/Mixtral-8x7B-Instruct-v0.1": {
            "max_context": 32768,
            "cost_per_input_token": 6e-07,
            "cost_per_output_token": 6e-07,
        },
    }

    SHORTCUTS = {
        "llama13b": "meta-llama/Llama-2-13b-chat-hf",
        "llama70b": "meta-llama/Llama-2-70b-chat-hf",
        "mistral7b": "mistralai/Mistral-7B-Instruct-v0.2",
        "mixtral8x7b": "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "redpajama7b": "togethercomputer/RedPajama-INCITE-7B-Chat",
    }

    def __init__(self, model_arguments: ModelArguments, commands: list[Command]):
        super().__init__(model_arguments, commands)

        # Set Together key
        cfg = config.Config(os.path.join(os.getcwd(), "keys.cfg"))
        together.api_key = cfg.TOGETHER_API_KEY

    def history_to_messages(
        self, history: list[dict[str, str]], is_demonstration: bool = False
    ) -> str:
        """
        Create `prompt` by filtering out all keys except for role/content per `history` turn
        """
        # Remove system messages if it is a demonstration
        if is_demonstration:
            history = [entry for entry in history if entry["role"] != "system"]
        # Map history to TogetherAI format
        mapping = {"user": "human", "assistant": "bot", "system": "bot"}
        prompt = [f'<{mapping[d["role"]]}>: {d["content"]}' for d in history]
        prompt = "\n".join(prompt)
        prompt = f"{prompt}\n<bot>:"
        return prompt

    @retry(
        wait=wait_random_exponential(min=1, max=15),
        reraise=True,
        stop=stop_after_attempt(3),
        retry=retry_if_not_exception_type((CostLimitExceededError, RuntimeError)),
    )
    def query(self, history: list[dict[str, str]]) -> str:
        """
        Query the Together API with the given `history` and return the response.
        """
        # Perform Together API call
        prompt = self.history_to_messages(history)
        completion = together.Complete.create(
            model=self.api_model,
            prompt=prompt,
            max_tokens=self.model_metadata["max_context"],
            stop="<human>",
            temperature=self.model_arguments.temperature,
            top_p=self.model_arguments.top_p,
        )
        # Calculate + update costs, return response
        response = completion["output"]["choices"][0]["text"].split("<human>")[0]
        input_tokens = completion["output"]["usage"]["prompt_tokens"]
        output_tokens = completion["output"]["usage"]["completion_tokens"]
        self.update_stats(input_tokens, output_tokens)
        return response
