"""Helpers for framework tool results that encode failure in the payload."""

from __future__ import annotations

import json
from typing import Any


def tool_result_error(output: Any) -> str | None:
    """Return an error message for MCP/Mastra-style tool failure payloads.

    Detects protocol flags (``{isError: true}``, ``{is_error: true}``, Mastra
    ``{error: true, message}``, ``{success: false}``, ``{status: "error"}``)
    and application-level ``{error: "..."}`` / ``structuredContent.error``
    strings. Failures must be recorded as ``error`` (with no ``output``) per
    the trace contract. Returns ``None`` when ``output`` is a normal success
    payload.
    """
    record = _as_result_record(output)
    if record is None:
        return None

    if _is_flagged_failure(record):
        text = _content_text(record.get("content"))
        if text:
            return text
        flagged_error = _non_empty_string(record.get("error"))
        if flagged_error:
            return flagged_error
        message = _non_empty_string(record.get("message"))
        if message:
            return message
        encoded = _encoded_payload_error(record)
        if encoded:
            return encoded
        try:
            return json.dumps(record, default=str)
        except TypeError:
            return "Tool returned an error result"

    return _encoded_payload_error(record)


def _is_flagged_failure(record: dict[str, Any]) -> bool:
    return (
        record.get("isError") is True
        or record.get("is_error") is True
        or record.get("error") is True
        or record.get("success") is False
        or record.get("status") in ("error", "failed")
    )


def _encoded_payload_error(record: dict[str, Any]) -> str | None:
    direct = _non_empty_string(record.get("error"))
    if direct:
        return direct

    structured = _as_result_record(record.get("structuredContent"))
    if structured is not None:
        nested = _non_empty_string(structured.get("error"))
        if nested:
            return nested

    text = _content_text(record.get("content"))
    if not text:
        return None
    parsed = _as_result_record(text)
    if parsed is None:
        return None
    return _non_empty_string(parsed.get("error"))


def _content_text(content: Any) -> str | None:
    if not isinstance(content, list):
        return None
    texts = [
        text
        for part in content
        if isinstance(
            text := (
                part.get("text")
                if isinstance(part, dict)
                else getattr(part, "text", None)
            ),
            str,
        )
        and text
    ]
    text = "\n".join(texts).strip()
    return text or None


def _non_empty_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _as_result_record(output: Any) -> dict[str, Any] | None:
    if isinstance(output, dict):
        return output
    if isinstance(output, str):
        trimmed = output.strip()
        if not trimmed.startswith("{") and not trimmed.startswith("["):
            return None
        try:
            parsed = json.loads(trimmed)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    if output is not None and not isinstance(
        output, (int, float, bool, list, tuple, bytes)
    ):
        model_dump = getattr(output, "model_dump", None) or getattr(output, "dict", None)
        if callable(model_dump):
            try:
                dumped = model_dump()
                if isinstance(dumped, dict):
                    return dumped
            except Exception:
                pass
        if hasattr(output, "__dict__"):
            try:
                return {
                    k: v for k, v in vars(output).items() if not k.startswith("_")
                }
            except Exception:
                pass
    return None
