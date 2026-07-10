"""Safe execution diagnostics shared by user errors and the admin inspector."""

from __future__ import annotations

import re
from dataclasses import dataclass

_MAX_DIAGNOSTIC_CHARACTERS = 8_000

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(
            r"(?i)((?:api[_-]?key|access[_-]?token|secret|password|credential)\s*[:=]\s*)"
            r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
        ),
        r"\1[REDACTED]",
    ),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"), "[REDACTED_API_KEY]"),
)

_TRACEBACK_LINE = re.compile(
    r"^\s*(?:File \".*\", line \d+|Traceback \(most recent call last\):)"
)


@dataclass(frozen=True, slots=True)
class SafeExecutionError:
    """Stable, non-sensitive failure information safe for API responses."""

    category: str
    message: str
    retryable: bool


def sanitise_diagnostic_text(
    value: str | None, *, limit: int = _MAX_DIAGNOSTIC_CHARACTERS
) -> str | None:
    """Redact credential-shaped values, stack traces, and excessive diagnostic content."""
    if value is None:
        return None
    cleaned_lines = [
        line
        for line in value.replace("\x00", "").splitlines()
        if not _TRACEBACK_LINE.match(line)
    ]
    cleaned = "\n".join(cleaned_lines).strip()
    for pattern, replacement in _SECRET_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    if len(cleaned) > limit:
        cleaned = f"{cleaned[: max(limit - 14, 0)]}… [truncated]"
    return cleaned or None


def _classify_error(
    *,
    error_name: str,
    raw_message: str | None,
    stage_name: str | None,
    is_timeout: bool = False,
) -> SafeExecutionError:
    normalized = (sanitise_diagnostic_text(raw_message, limit=1_000) or "").lower()
    stage_label = f"The {stage_name} stage" if stage_name else "The pipeline"

    if (
        error_name == "ProviderCredentialMissingError"
        or "credential" in normalized
        and "configured" in normalized
    ):
        return SafeExecutionError(
            category="provider_credential_missing",
            message=f"{stage_label} cannot run because its provider credential is not configured. An administrator must add or test the provider key.",
            retryable=False,
        )
    if "thinking budget" in normalized or "thinking_budget" in normalized:
        return SafeExecutionError(
            category="invalid_model_parameter",
            message=f"{stage_label} failed because its thinking budget is outside the selected model's supported range. Update the pipeline or response-model settings and retry.",
            retryable=False,
        )
    if (
        "max_output_tokens" in normalized
        or "output token" in normalized
        or "token limit" in normalized
    ):
        return SafeExecutionError(
            category="invalid_model_parameter",
            message=f"{stage_label} failed because its output-token limit is unsupported by the selected model. Update the configuration and retry.",
            retryable=False,
        )
    if is_timeout or "timeout" in normalized or "timed out" in normalized:
        return SafeExecutionError(
            category="provider_timeout",
            message=f"{stage_label} timed out while waiting for the configured provider. Retry the run; if it repeats, test the provider or increase the stage timeout.",
            retryable=True,
        )
    if (
        "rate limit" in normalized
        or "too many requests" in normalized
        or "429" in normalized
    ):
        return SafeExecutionError(
            category="provider_rate_limited",
            message=f"{stage_label} was temporarily rate-limited by the provider. Retry after a short delay or select another available model.",
            retryable=True,
        )
    if "cancel" in normalized or error_name in {
        "CancelledError",
        "PipelineRunCancelledError",
    }:
        return SafeExecutionError(
            category="cancelled",
            message=f"{stage_label} was cancelled before completion.",
            retryable=True,
        )
    if "model" in normalized and (
        "not found" in normalized
        or "unsupported" in normalized
        or "unavailable" in normalized
    ):
        return SafeExecutionError(
            category="model_unavailable",
            message=f"{stage_label} cannot use the configured model because it is unavailable or unsupported. Select an available model and retry.",
            retryable=False,
        )
    if "provider" in normalized and (
        "unavailable" in normalized
        or "connection" in normalized
        or "network" in normalized
    ):
        return SafeExecutionError(
            category="provider_unavailable",
            message=f"{stage_label} could not reach the configured provider. Test the provider connection or retry the run.",
            retryable=True,
        )

    return SafeExecutionError(
        category="stage_execution_failed",
        message=f"{stage_label} failed. An administrator can inspect the sanitised run diagnostics for the recorded cause and decide whether retry is safe.",
        retryable=False,
    )


def classify_execution_error(
    error: BaseException | None, *, stage_name: str | None = None
) -> SafeExecutionError:
    """Map an active implementation exception to a safe public explanation."""
    return _classify_error(
        error_name=type(error).__name__
        if error is not None
        else "PipelineRunFailureError",
        raw_message=str(error) if error is not None else None,
        stage_name=stage_name,
        is_timeout=isinstance(error, TimeoutError),
    )


def classify_stored_execution_error(
    error_code: str | None,
    error_message: str | None,
    *,
    stage_name: str | None = None,
) -> SafeExecutionError | None:
    """Classify previously persisted failure fields without recreating unsafe exceptions."""
    if not error_code and not error_message:
        return None
    return _classify_error(
        error_name=error_code or "PipelineRunFailureError",
        raw_message=error_message,
        stage_name=stage_name,
        is_timeout=error_code in {"TimeoutError", "ProviderTimeoutError"},
    )
