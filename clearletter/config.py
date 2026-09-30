"""Model choices, prices and settings, in one place.

Model IDs and prices checked against Anthropic's model table on 30 September 2026.
Prices are US dollars per million tokens (input, output).
"""

from dataclasses import dataclass, field

from dotenv import load_dotenv

# Reads ANTHROPIC_API_KEY from a local .env file (which git ignores).
load_dotenv()


@dataclass
class ModelConfig:
    model_id: str
    input_price: float  # $ per million input tokens
    output_price: float  # $ per million output tokens (thinking tokens count as output)
    extra: dict = field(default_factory=dict)  # model-specific request settings

    def cost(self, input_tokens, output_tokens):
        return (input_tokens * self.input_price + output_tokens * self.output_price) / 1_000_000


MODELS = {
    # Haiku 4.5: fastest and cheapest. Runs without extended thinking here.
    "haiku": ModelConfig("claude-haiku-4-5", 1.00, 5.00),
    # Sonnet 5.5 and Opus 5.5 always think before answering; "effort" sets how much.
    # "medium" is set explicitly on both so the comparison is fair.
    "sonnet": ModelConfig("claude-sonnet-5-5", 2.00, 10.00, {"output_config": {"effort": "medium"}}),
    "opus": ModelConfig("claude-opus-5-5", 4.00, 20.00, {"output_config": {"effort": "medium"}}),
}

DEFAULT_MODEL = "sonnet"
MAX_TOKENS = 16000
