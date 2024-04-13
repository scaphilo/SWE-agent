import os

import config
from tenacity import retry, wait_random_exponential, stop_after_attempt, retry_if_not_exception_type

from swe_agent import ModelArguments
from swe_agent.swe_agent.command.commands import Command
from swe_agent.swe_agent.model.models import SEWAgentModel, CostLimitExceededError


class AnthropicModel(SEWAgentModel):
    MODELS = {
        "claude-instant": {
            "max_context": 100_000,
            "cost_per_input_token": 1.63e-06,
            "cost_per_output_token": 5.51e-06,
        },
        "claude-2": {
            "max_context": 100_000,
            "cost_per_input_token": 1.102e-05,
            "cost_per_output_token": 3.268e-05,
        },
        "claude-2.1": {
            "max_context": 100_000,
            "cost_per_input_token": 1.102e-05,
            "cost_per_output_token": 3.268e-05,
        },
        "claude-3-opus-20240229": {
            "max_context": 200_000,
            "max_tokens": 4096,  # Max tokens to generate for Claude 3 models
            "cost_per_input_token": 1.5e-05,
            "cost_per_output_token": 7.5e-05,
        },
        "claude-3-sonnet-20240229": {
            "max_context": 200_000,
            "max_tokens": 4096,
            "cost_per_input_token": 3e-06,
            "cost_per_output_token": 1.5e-05,
        },
        "claude-3-haiku-20240307": {
            "max_context": 200_000,
            "max_tokens": 4096,
            "cost_per_input_token": 2.5e-07,
            "cost_per_output_token": 1.25e-06,
        },
    }

    SHORTCUTS = {
        "claude": "claude-2",
        "claude-opus": "claude-3-opus-20240229",
        "claude-sonnet": "claude-3-sonnet-20240229",
        "claude-haiku": "claude-3-haiku-20240307",
    }

    def __init__(self, model_arguments: ModelArguments, commands: list[Command]):
        super().__init__(model_arguments, commands)

        # Set Anthropic key
        cfg = config.Config(os.path.join(os.getcwd(), "keys.cfg"))
        self.api = Anthropic(api_key=cfg["ANTHROPIC_API_KEY"])

    def history_to_messages(
        self, history: list[dict[str, str]], is_demonstration: bool = False
    ) -> list[dict[str, str]]:
        """
        Create `prompt` by filtering out all keys except for role/content per `history` turn
        Reference: https://docs.anthropic.com/claude/reference/complete_post
        """
        # Preserve behavior for older models
        if self.api_model in ["claude-instant", "claude-2"]:
            # Remove system messages if it is a demonstration
            if is_demonstration:
                history = [entry for entry in history if entry["role"] != "system"]
            # Map history to Claude format
            prompt = "\n\n"
            for entry in history:
                if entry["role"] in {"user", "system"}:
                    prompt += f'{HUMAN_PROMPT} {entry["content"]}\n\n'
                elif entry["role"] == "assistant":
                    prompt += f'{AI_PROMPT} {entry["content"]}\n\n'
            prompt += AI_PROMPT
            return prompt

        # Remove system messages if it is a demonstration
        if is_demonstration:
            history = [entry for entry in history if entry["role"] != "system"]
            return '\n'.join([entry["content"] for entry in history])

        # Return history components with just role, content fields (no system message)
        messages = [
            {
                k: v for k, v in entry.items()
                if k in ["role", "content"]
            }
            for entry in history if entry["role"] != "system"
        ]
        compiled_messages = []  # Combine messages from the same role
        last_role = None
        for message in reversed(messages):
            if last_role == message["role"]:
                compiled_messages[-1]["content"] = message["content"] + "\n" + compiled_messages[-1]["content"]
            else:
                compiled_messages.append(message)
            last_role = message["role"]
        compiled_messages = list(reversed(compiled_messages))
        # Replace any empty content values with a "(No output)"
        for message in compiled_messages:
            if message["content"].strip() == "":
                message["content"] = "(No output)"
        return compiled_messages

    @retry(
        wait=wait_random_exponential(min=1, max=15),
        reraise=True,
        stop=stop_after_attempt(3),
        retry=retry_if_not_exception_type((CostLimitExceededError, RuntimeError)),
    )
    def query(self, history: list[dict[str, str]]) -> str:
        """
        Query the Anthropic API with the given `history` and return the response.
        """
        # Preserve behavior for older models
        if self.api_model in ["claude-instant", "claude-2"]:
            # Perform Anthropic API call
            prompt = self.history_to_messages(history)
            input_tokens = self.api.count_tokens(prompt)
            completion = self.api.completions.create(
                model=self.api_model,
                prompt=prompt,
                max_tokens_to_sample=self.model_metadata["max_context"] - input_tokens,
                temperature=self.model_arguments.temperature,
                top_p=self.model_arguments.top_p,
            )
            # Calculate + update costs, return response
            response = completion.completion
            output_tokens = self.api.count_tokens(response)
            self.update_stats(input_tokens, output_tokens)
            return response

        # Get system message(s)
        system_message = "\n".join([
            entry["content"] for entry in history if entry["role"] == "system"
        ])
        messages = self.history_to_messages(history)
        # Perform Anthropic API call
        response = self.api.messages.create(
            messages=messages,
            max_tokens=self.model_metadata["max_tokens"],
            model=self.api_model,
            temperature=self.model_arguments.temperature,
            top_p=self.model_arguments.top_p,
            system=system_message,
        )

        # Calculate + update costs, return response
        self.update_stats(
            response.usage.input_tokens,
            response.usage.output_tokens
        )
        response = "\n".join([x.text for x in response.content])
        return response
