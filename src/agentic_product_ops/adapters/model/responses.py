"""Explicit, tool-free Responses transport. Construction never discovers credentials."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from pydantic import SecretStr

from agentic_product_ops.adapters.model.contracts import ModelRequest, ModelResponse, ProviderUsage
from agentic_product_ops.adapters.model.runner import RunStopped


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Provider subset only; domain constraints are revalidated after every response."""

    def visit(value: Any) -> Any:
        if isinstance(value, list):
            return [visit(item) for item in value]
        if not isinstance(value, dict):
            return value
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"default", "title"}:
                continue
            if key in {"properties", "$defs"}:
                result[key] = {name: visit(child) for name, child in item.items()}
            else:
                result[key] = visit(item)
        if result.get("type") == "object":
            result["additionalProperties"] = False
            result["required"] = list(result.get("properties", {}))
        return result

    result: dict[str, Any] = visit(schema)
    return result


class ResponsesProvider:
    """Network disabled unless explicitly authorized; mock transports cannot reach a host."""

    def __init__(
        self,
        *,
        model: str,
        api_key: SecretStr,
        transport: httpx.MockTransport | None = None,
        allow_paid_execution: bool = False,
        timeout_seconds: float = 30,
        max_response_bytes: int = 500_000,
    ) -> None:
        if not model or not api_key.get_secret_value():
            raise ValueError("explicit model and credential required")
        if transport is None and not allow_paid_execution:
            raise ValueError("paid execution disabled")
        if transport is not None and not isinstance(transport, httpx.MockTransport):
            raise ValueError("only an in-memory mock may bypass execution authorization")
        if not 0 < timeout_seconds <= 120 or not 1024 <= max_response_bytes <= 1_000_000:
            raise ValueError("invalid transport limits")
        self.model = model
        self._key = api_key
        self._transport = transport
        self._timeout = timeout_seconds
        self._limit = max_response_bytes

    def _post(
        self, client: httpx.Client, path: str, body: dict[str, Any], deadline: float
    ) -> tuple[dict[str, Any], str | None]:
        encoded = json.dumps(body, separators=(",", ":")).encode()
        if len(encoded) > 500_000 or time.monotonic() >= deadline:
            raise RunStopped("provider request limit")
        with client.stream(
            "POST", path, content=encoded, timeout=max(0.001, deadline - time.monotonic())
        ) as response:
            if response.status_code != 200 or response.headers.get("content-encoding"):
                raise RunStopped("provider unavailable or unsupported response")
            content = bytearray()
            for chunk in response.iter_bytes():
                if time.monotonic() >= deadline or len(content) + len(chunk) > self._limit:
                    raise RunStopped("provider response limit")
                content.extend(chunk)
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise RunStopped("invalid provider envelope")
            return parsed, response.headers.get("x-request-id")

    def complete(self, request: ModelRequest) -> ModelResponse:
        if request.model != self.model:
            raise RunStopped("model outside configured scope")
        body = {
            "model": self.model,
            "input": [
                {"role": "system", "content": request.system_policy},
                {"role": "developer", "content": request.authorized_configuration},
                {"role": "user", "content": request.untrusted_payload},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": request.role,
                    "strict": True,
                    "schema": strict_schema(json.loads(request.output_schema)),
                }
            },
            "tools": [],
        }
        deadline = time.monotonic() + self._timeout
        try:
            with httpx.Client(
                base_url="https://api.openai.com/v1/",
                headers={
                    "Authorization": "Bearer " + self._key.get_secret_value(),
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                },
                transport=self._transport,
                trust_env=False,
                follow_redirects=False,
                timeout=httpx.Timeout(self._timeout, connect=min(10, self._timeout)),
            ) as client:
                counted, _ = self._post(client, "responses/input_tokens", body, deadline)
                tokens = counted.get("input_tokens")
                if (
                    counted.get("object") != "response.input_tokens"
                    or type(tokens) is not int
                    or not 0 <= tokens <= request.max_input_tokens
                ):
                    raise RunStopped("provider input budget exceeded")
                result, request_id = self._post(
                    client,
                    "responses",
                    {**body, "store": False, "max_output_tokens": request.max_output_tokens},
                    deadline,
                )
            if result.get("status") != "completed" or result.get("error") is not None:
                raise RunStopped("provider incomplete or refused")
            texts: list[str] = []
            for item in result["output"]:
                if item["type"] == "reasoning":
                    continue  # Never retain hidden reasoning or summaries.
                if item["type"] != "message" or item.get("role") != "assistant":
                    raise RunStopped("unexpected provider capability")
                for content in item["content"]:
                    if content["type"] != "output_text" or not isinstance(content["text"], str):
                        raise RunStopped("provider incomplete or refused")
                    texts.append(content["text"])
            if len(texts) != 1:
                raise RunStopped("ambiguous provider output")
            usage = ProviderUsage(
                input_tokens=result["usage"]["input_tokens"],
                output_tokens=result["usage"]["output_tokens"],
                provider_request_id=request_id or result["id"],
            )
            if (
                usage.input_tokens > request.max_input_tokens
                or usage.output_tokens > request.max_output_tokens
            ):
                raise RunStopped("provider usage exceeds reservation")
            return ModelResponse(output_json=texts[0], usage=usage)
        except Exception:
            # Do not expose provider bodies, request headers or exception URLs.
            # A durable intent remains held after any uncertain generation outcome.
            raise RunStopped("structured provider held; no automatic retry") from None
