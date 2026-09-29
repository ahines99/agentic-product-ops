"""Explicit bounded Anthropic Messages transport; no tools, retries or ambient credentials."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from pydantic import SecretStr

from agentic_product_ops.adapters.model.contracts import ModelRequest, ModelResponse, ProviderUsage
from agentic_product_ops.adapters.model.runner import RunStopped


def structured_schema(value: Any) -> Any:
    """Remove provider-unsupported constraints; the full original schema remains authoritative."""
    if isinstance(value, list):
        return [structured_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    unsupported = {
        "default",
        "title",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minLength",
        "maxLength",
        "pattern",
        "format",
        "minItems",
        "maxItems",
    }
    result = {}
    for key, item in value.items():
        if key in unsupported:
            continue
        result[key] = (
            {name: structured_schema(child) for name, child in item.items()}
            if key in {"properties", "$defs"}
            else structured_schema(item)
        )
    constraints = {
        key: item for key, item in value.items() if key in unsupported - {"title", "default"}
    }
    if constraints:
        result["description"] = (
            str(result.get("description", ""))
            + " Local validation constraints: "
            + json.dumps(constraints, separators=(",", ":"))
        ).strip()
    return result


class AnthropicProvider:
    def __init__(
        self,
        *,
        model: str,
        api_key: SecretStr,
        transport: httpx.MockTransport | None = None,
        allow_paid_execution: bool = False,
        timeout_seconds: float = 90,
        max_response_bytes: int = 500_000,
    ) -> None:
        if not model or not api_key.get_secret_value():
            raise ValueError("explicit Anthropic model and credential required")
        if transport is None and not allow_paid_execution:
            raise ValueError("paid execution disabled")
        if transport is not None and not isinstance(transport, httpx.MockTransport):
            raise ValueError("only in-memory mocks bypass execution authorization")
        if not 0 < timeout_seconds <= 120 or not 1024 <= max_response_bytes <= 1_000_000:
            raise ValueError("invalid transport bounds")
        self.model, self._key, self._transport = model, api_key, transport
        self._timeout, self._limit = timeout_seconds, max_response_bytes

    def _post(
        self, client: httpx.Client, path: str, body: dict[str, Any], deadline: float
    ) -> tuple[dict[str, Any], str | None]:
        encoded = json.dumps(body, separators=(",", ":")).encode()
        if len(encoded) > 500_000 or time.monotonic() >= deadline:
            raise RunStopped("provider request bound")
        with client.stream(
            "POST", path, content=encoded, timeout=max(0.001, deadline - time.monotonic())
        ) as response:
            if response.status_code != 200 or response.headers.get("content-encoding"):
                raise RunStopped("provider unavailable")
            raw = bytearray()
            for chunk in response.iter_bytes():
                if len(raw) + len(chunk) > self._limit or time.monotonic() >= deadline:
                    raise RunStopped("provider response bound")
                raw.extend(chunk)
            result = json.loads(raw)
            request_id = response.headers.get("request-id")
            if not isinstance(result, dict) or (
                request_id is not None and (len(request_id) > 128 or not request_id.isascii())
            ):
                raise RunStopped("invalid provider response")
            return result, request_id

    def complete(self, request: ModelRequest) -> ModelResponse:
        if request.model != self.model:
            raise RunStopped("model outside configured scope")
        body = {
            "model": self.model,
            "system": [
                {"type": "text", "text": request.system_policy},
                {
                    "type": "text",
                    "text": "Trusted configuration:\n" + request.authorized_configuration,
                },
            ],
            "messages": [{"role": "user", "content": request.untrusted_payload}],
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": structured_schema(json.loads(request.output_schema)),
                }
            },
        }
        deadline = time.monotonic() + self._timeout
        try:
            with httpx.Client(
                base_url="https://api.anthropic.com/v1/",
                headers={
                    "x-api-key": self._key.get_secret_value(),
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                },
                transport=self._transport,
                trust_env=False,
                follow_redirects=False,
                timeout=httpx.Timeout(self._timeout, connect=min(10, self._timeout)),
            ) as client:
                counted, _ = self._post(client, "messages/count_tokens", body, deadline)
                tokens = counted.get("input_tokens")
                if type(tokens) is not int or not 0 <= tokens <= request.max_input_tokens:
                    raise RunStopped("provider input budget exceeded")
                result, request_id = self._post(
                    client, "messages", {**body, "max_tokens": request.max_output_tokens}, deadline
                )
            if (
                result.get("type") != "message"
                or result.get("role") != "assistant"
                or result.get("model") != self.model
                or result.get("stop_reason") != "end_turn"
            ):
                raise RunStopped("incomplete or unexpected model output")
            texts = []
            for item in result["content"]:
                if item["type"] in {"thinking", "redacted_thinking"}:
                    continue  # Do not persist reasoning, signatures or reasoning summaries.
                if item["type"] != "text" or not isinstance(item["text"], str):
                    raise RunStopped("unexpected provider capability")
                texts.append(item["text"])
            if len(texts) != 1:
                raise RunStopped("ambiguous provider output")
            raw_usage = result["usage"]
            # No cache controls are sent. Still reserve/report all input categories if returned.
            counts = [
                raw_usage.get(key, 0)
                for key in (
                    "input_tokens",
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                )
            ]
            if "input_tokens" not in raw_usage or any(type(n) is not int or n < 0 for n in counts):
                raise RunStopped("invalid provider usage")
            usage = ProviderUsage(
                input_tokens=sum(counts),
                output_tokens=raw_usage["output_tokens"],
                provider_request_id=request_id or result["id"],
            )
            if (
                usage.input_tokens > request.max_input_tokens
                or usage.output_tokens > request.max_output_tokens
            ):
                raise RunStopped("provider usage exceeds reservation")
            return ModelResponse(output_json=texts[0], usage=usage)
        except Exception:
            raise RunStopped("Anthropic structured provider held; no automatic retry") from None
