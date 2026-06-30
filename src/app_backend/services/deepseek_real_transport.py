"""Stage 9.3-B-2b real DeepSeek transport implementation.

This module adds real transport code only. It does not add any HTTP endpoint,
does not connect to frontend UI, does not persist prompts or responses, and
does not run on app start, page load, or in a background job.

Only `load_deepseek_api_key_from_env()` reads the process environment. The
transport request and response schemas remain sanitized and do not expose API
keys, provider URLs, model names, raw prompts, raw responses, holdings,
account values, position weights, transactions, search results, or local paths.
"""
from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from typing import Any, Callable

from app_backend.schemas.ai_external import (
    DeepSeekProviderMessage,
    DeepSeekTransportMessage,
    DeepSeekTransportRequest,
    DeepSeekTransportResponse,
    DeepSeekTransportToolCall,
    DeepSeekTransportUsage,
)
from app_backend.services.deepseek_transport_contract import DeepSeekTransportError


_DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
_DEEPSEEK_CHAT_COMPLETIONS_URL = "https://api.deepseek.com/chat/completions"
_DEEPSEEK_MODEL_NAME = "deepseek-v4-pro"
_DEFAULT_TIMEOUT_SECONDS = 120.0
_DEFAULT_MAX_TOKENS = 2_400
_MAX_PROVIDER_RESPONSE_BYTES = 2_000_000


UrlOpen = Callable[[urllib.request.Request, float], Any]


def load_deepseek_api_key_from_env() -> str:
    """Load the DeepSeek API key from the process environment only.

    Missing or blank keys fail closed with a categorical transport error.
    The key is never printed, logged, embedded in schemas, or copied into
    exception details.
    """
    value = os.environ.get(_DEEPSEEK_API_KEY_ENV, "").strip()
    if not value:
        raise DeepSeekTransportError(
            kind="missing_key",
            detail="deepseek_api_key_missing",
        )
    return value


class DeepSeekRealTransport:
    """Real DeepSeek HTTP transport behind the existing transport Protocol.

    This class accepts only `DeepSeekTransportRequest`. It builds provider
    HTTP details internally and converts provider output back to the sanitized
    `DeepSeekTransportResponse` shape.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        opener: UrlOpen | None = None,
    ) -> None:
        self._api_key = api_key.strip() if api_key is not None else None
        self._timeout_seconds = timeout_seconds
        self._max_tokens = max(256, min(max_tokens, 8_192))
        self._opener = opener

    def send(self, request: DeepSeekTransportRequest) -> DeepSeekTransportResponse:
        api_key = self._api_key or load_deepseek_api_key_from_env()
        if not api_key:
            raise DeepSeekTransportError(
                kind="missing_key",
                detail="deepseek_api_key_missing",
            )

        http_request = self._build_http_request(request=request, api_key=api_key)
        try:
            response_obj = (self._opener or _urlopen_with_timeout)(
                http_request,
                self._timeout_seconds,
            )
            status = int(getattr(response_obj, "status", 200))
            raw_body = response_obj.read(_MAX_PROVIDER_RESPONSE_BYTES)
        except TimeoutError as exc:
            raise DeepSeekTransportError(
                kind="timeout",
                detail="deepseek_transport_timeout",
            ) from exc
        except socket.timeout as exc:
            raise DeepSeekTransportError(
                kind="timeout",
                detail="deepseek_transport_timeout",
            ) from exc
        except urllib.error.HTTPError as exc:
            raise DeepSeekTransportError(
                kind="http_error",
                detail=f"provider_http_status_{exc.code}",
            ) from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, (TimeoutError, socket.timeout)):
                raise DeepSeekTransportError(
                    kind="timeout",
                    detail="deepseek_transport_timeout",
                ) from exc
            raise DeepSeekTransportError(
                kind="http_error",
                detail="provider_connection_failed",
            ) from exc
        except OSError as exc:
            raise DeepSeekTransportError(
                kind="http_error",
                detail="provider_connection_failed",
            ) from exc

        if status < 200 or status >= 300:
            raise DeepSeekTransportError(
                kind="http_error",
                detail=f"provider_http_status_{status}",
            )

        return _parse_provider_response(
            request=request,
            raw_body=raw_body,
        )

    def _build_http_request(
        self,
        *,
        request: DeepSeekTransportRequest,
        api_key: str,
    ) -> urllib.request.Request:
        body = {
            "model": _DEEPSEEK_MODEL_NAME,
            "messages": [_to_provider_message(message) for message in request.messages],
            "temperature": 0.2,
            "max_tokens": request.max_tokens or self._max_tokens,
            "stream": False,
        }
        if request.tools is not None:
            body["tools"] = request.tools
            body["tool_choice"] = request.tool_choice or "auto"
        if request.response_format is not None:
            body["response_format"] = request.response_format
        data = json.dumps(body, ensure_ascii=True).encode("utf-8")
        return urllib.request.Request(
            _DEEPSEEK_CHAT_COMPLETIONS_URL,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )


def _urlopen_with_timeout(
    request: urllib.request.Request,
    timeout_seconds: float,
) -> Any:
    return urllib.request.urlopen(request, timeout=timeout_seconds)


def _to_provider_message(
    message: DeepSeekProviderMessage | DeepSeekTransportMessage,
) -> dict[str, str]:
    if message.role in {"context", "summary"}:
        role = "user"
    else:
        role = message.role
    payload = {"role": role, "content": message.content}
    if role == "tool" and message.tool_call_id:
        payload["tool_call_id"] = message.tool_call_id
    if role == "assistant" and getattr(message, "tool_calls", None):
        payload["tool_calls"] = list(message.tool_calls)
    return payload


def _parse_provider_response(
    *,
    request: DeepSeekTransportRequest,
    raw_body: bytes,
) -> DeepSeekTransportResponse:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeepSeekTransportError(
            kind="malformed",
            detail="provider_response_not_json",
        ) from exc

    if not isinstance(payload, dict):
        raise DeepSeekTransportError(
            kind="malformed",
            detail="provider_response_not_object",
        )

    if _provider_refused(payload):
        raise DeepSeekTransportError(
            kind="provider_refusal",
            detail="provider_refusal",
        )

    content, finish_reason, tool_calls = _extract_message_payload(payload)
    usage = _extract_usage(payload)
    return DeepSeekTransportResponse(
        request_id=request.request_id,
        provider=request.provider,
        mode=request.mode,
        content_text=content,
        finish_reason=finish_reason,
        tool_calls=tool_calls,
        usage=usage,
    )


def _provider_refused(payload: dict[str, Any]) -> bool:
    if payload.get("refusal"):
        return True
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return False
    first = choices[0]
    if not isinstance(first, dict):
        return False
    message = first.get("message")
    return isinstance(message, dict) and bool(message.get("refusal"))


def _extract_message_payload(
    payload: dict[str, Any],
) -> tuple[str, str, list[DeepSeekTransportToolCall]]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise DeepSeekTransportError(
            kind="malformed",
            detail="provider_response_missing_choices",
        )

    first = choices[0]
    if not isinstance(first, dict):
        raise DeepSeekTransportError(
            kind="malformed",
            detail="provider_response_bad_choice",
        )

    message = first.get("message")
    if not isinstance(message, dict):
        raise DeepSeekTransportError(
            kind="malformed",
            detail="provider_response_missing_message",
        )

    content = message.get("content")
    tool_calls = _extract_tool_calls(message)
    if not tool_calls and (not isinstance(content, str) or not content.strip()):
        raise DeepSeekTransportError(
            kind="malformed",
            detail="provider_response_missing_content",
        )

    finish_reason = first.get("finish_reason")
    if finish_reason not in {"stop", "tool_calls", "length", "content_filter"}:
        finish_reason = "tool_calls" if tool_calls else "stop"
    return content if isinstance(content, str) else "", finish_reason, tool_calls


def _extract_tool_calls(message: dict[str, Any]) -> list[DeepSeekTransportToolCall]:
    raw_calls = message.get("tool_calls")
    if raw_calls is None:
        return []
    if not isinstance(raw_calls, list):
        raise DeepSeekTransportError(
            kind="malformed",
            detail="provider_tool_calls_not_list",
        )

    parsed: list[DeepSeekTransportToolCall] = []
    for raw_call in raw_calls:
        if not isinstance(raw_call, dict):
            raise DeepSeekTransportError(
                kind="malformed",
                detail="provider_tool_call_not_object",
            )
        function = raw_call.get("function")
        if not isinstance(function, dict):
            raise DeepSeekTransportError(
                kind="malformed",
                detail="provider_tool_call_missing_function",
            )
        call_id = raw_call.get("id")
        name = function.get("name")
        arguments = function.get("arguments", "{}")
        if not isinstance(call_id, str) or not call_id.strip():
            raise DeepSeekTransportError(
                kind="malformed",
                detail="provider_tool_call_missing_id",
            )
        if not isinstance(name, str) or not name.strip():
            raise DeepSeekTransportError(
                kind="malformed",
                detail="provider_tool_call_missing_name",
            )
        if isinstance(arguments, str):
            try:
                decoded_arguments = json.loads(arguments)
            except json.JSONDecodeError:
                decoded_arguments = {}
        else:
            decoded_arguments = arguments
        if not isinstance(decoded_arguments, dict):
            decoded_arguments = {}
        parsed.append(
            DeepSeekTransportToolCall(
                id=call_id,
                name=name,
                arguments=decoded_arguments,
            )
        )
    return parsed


def _extract_usage(payload: dict[str, Any]) -> DeepSeekTransportUsage:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return DeepSeekTransportUsage()
    input_tokens = _coerce_nonnegative_int(usage.get("prompt_tokens"))
    output_tokens = _coerce_nonnegative_int(usage.get("completion_tokens"))
    total_tokens = _coerce_nonnegative_int(usage.get("total_tokens"))
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens
    return DeepSeekTransportUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _coerce_nonnegative_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(value, 0)


__all__ = [
    "DeepSeekRealTransport",
    "load_deepseek_api_key_from_env",
]
