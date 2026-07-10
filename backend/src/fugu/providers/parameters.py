"""Model execution-parameter validation against the backend catalogue."""

from __future__ import annotations

from dataclasses import dataclass

from fugu.providers.catalogue import ModelDefinition, get_provider_catalogue


@dataclass(frozen=True, slots=True)
class ModelExecutionParameters:
    """Validated optional parameters safe to pass to one provider request."""

    temperature: float | None = None
    max_output_tokens: int | None = None
    thinking_budget: int | None = None


def _validate_temperature(model: ModelDefinition, value: float | None) -> None:
    if value is None:
        return
    if "temperature" not in model.supported_parameters or model.temperature is None:
        raise ValueError(f"Model {model.identifier!r} does not support the temperature parameter.")
    if value < model.temperature.minimum or value > model.temperature.maximum:
        raise ValueError(
            f"Temperature {value} is invalid for model {model.identifier!r}; choose a value between "
            f"{model.temperature.minimum} and {model.temperature.maximum}."
        )


def _validate_output_limit(model: ModelDefinition, value: int | None) -> None:
    if value is None:
        return
    if "max_output_tokens" not in model.supported_parameters:
        raise ValueError(f"Model {model.identifier!r} does not support max_output_tokens.")
    if value < 1 or value > model.output_limit:
        raise ValueError(
            f"Output limit {value} is invalid for model {model.identifier!r}; choose a value between 1 and "
            f"{model.output_limit}."
        )


def _validate_thinking_budget(model: ModelDefinition, value: int | None) -> None:
    if value is None:
        return
    minimum = model.thinking_budget_minimum
    maximum = model.thinking_budget_maximum
    if "thinking_budget" not in model.supported_parameters or minimum is None or maximum is None:
        raise ValueError(f"Model {model.identifier!r} does not support thinking_budget.")
    if value < minimum or value > maximum:
        raise ValueError(
            f"Thinking budget {value} is invalid for model {model.identifier!r}; choose a value between "
            f"{minimum} and {maximum}."
        )


def validate_model_parameters(
    provider_identifier: str,
    model_identifier: str,
    *,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    thinking_budget: int | None = None,
) -> ModelExecutionParameters:
    """Validate provider/model parameters before any credential lookup or network request."""
    model = get_provider_catalogue().validate_selection(provider_identifier, model_identifier)
    _validate_temperature(model, temperature)
    _validate_output_limit(model, max_output_tokens)
    _validate_thinking_budget(model, thinking_budget)
    return ModelExecutionParameters(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        thinking_budget=thinking_budget,
    )
