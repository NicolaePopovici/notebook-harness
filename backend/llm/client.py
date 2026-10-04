"""Calls any LiteLLM-supported model and returns a validated Pydantic object."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import litellm
from pydantic import BaseModel, ValidationError

from ..config import GenerationConfig, ProviderConfig
from .schema import inline_schema

T = TypeVar("T", bound=BaseModel)
CompletionFn = Callable[..., Awaitable[Any]]

litellm.drop_params = True
litellm.suppress_debug_info = True

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


class LLMError(RuntimeError):
    pass


class ContextTooLargeError(LLMError):
    pass


class LLMClient:
    def __init__(
        self,
        provider_name: str,
        provider: ProviderConfig,
        generation: GenerationConfig,
        completion_fn: CompletionFn | None = None,
    ):
        self.provider_name = provider_name
        self.provider = provider
        self.generation = generation
        self._completion = completion_fn or litellm.acompletion

    @property
    def model(self) -> str:
        return self.provider.model

    def check_fits(self, system: str, user: str, output: type[BaseModel]) -> None:
        """Raise ContextTooLargeError if the prompt plus room for the reply exceeds the model's context window."""
        self._check_fits(_messages(system, user, inline_schema(output)))

    def _check_fits(self, messages: list[dict[str, str]]) -> None:
        limit = self.provider.context_limit()
        if limit is None:
            return
        max_tokens, source = limit
        needed = litellm.token_counter(model=self.provider.model, messages=messages)
        reserve = self.generation.reserved_output_tokens
        if needed + reserve > max_tokens:
            raise ContextTooLargeError(
                f"The prompt is about {needed:,} tokens, plus {reserve:,} kept free for the reply, but "
                f"{self.provider.model} accepts {max_tokens:,} ({source}). Use a model with a larger context "
                f"window, or raise the limit in harness.yaml if this model supports more."
            )

    async def complete_json(self, system: str, user: str, output: type[T]) -> T:
        """Ask for JSON matching `output`. Malformed replies are sent back to the model with the error."""
        schema = inline_schema(output)
        messages = _messages(system, user, schema)
        last_error = ""
        for _ in range(self.generation.max_parse_retries + 1):
            # Checked on every attempt: each retry adds the previous reply to the conversation.
            self._check_fits(messages)
            content = await self._call(messages, output.__name__, schema)
            try:
                return output.model_validate(parse_json(content))
            except (ValueError, ValidationError) as exc:
                last_error = str(exc)[:2000]
                messages += [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": f"That reply was not valid JSON for the schema:\n{last_error}\nReply again with only the corrected JSON object."},
                ]
        raise LLMError(f"Model {self.model} did not return valid JSON: {last_error}")

    async def _call(self, messages: list[dict[str, str]], name: str, schema: dict[str, Any]) -> str:
        kwargs: dict[str, Any] = {
            "model": self.provider.model,
            "messages": messages,
            "temperature": self.generation.temperature,
            "timeout": self.generation.timeout_s,
            **self.provider.extra,
        }
        if self.provider.api_base:
            kwargs["api_base"] = self.provider.api_base
        if key := self.provider.api_key():
            kwargs["api_key"] = key
        if _supports_schema(self.provider.model):
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": name, "schema": schema, "strict": True},
            }
        else:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await self._completion(**kwargs)
        except litellm.ContextWindowExceededError as exc:
            # Our token count is an estimate; the provider has the final say.
            raise ContextTooLargeError(
                f"The prompt is too long for {self.provider.model}'s context window. Use a model with a larger "
                f"context window. ({exc})"
            ) from exc
        except litellm.AuthenticationError as exc:
            hint = f" Set {self.provider.api_key_env}." if self.provider.api_key_env else ""
            raise LLMError(f"Authentication failed for {self.provider_name}.{hint}") from exc
        except litellm.RateLimitError as exc:
            raise LLMError(f"Rate limited by {self.provider_name}; try again shortly or lower generation.max_concurrency.") from exc
        except litellm.APIConnectionError as exc:
            raise LLMError(f"Could not reach {self.provider_name} ({self.provider.api_base or self.provider.model}): {exc}") from exc
        except litellm.Timeout as exc:
            raise LLMError(f"{self.provider_name} timed out after {self.generation.timeout_s}s.") from exc
        except Exception as exc:  # LiteLLM wraps provider errors in many types.
            raise LLMError(f"{self.provider_name} call failed: {exc}") from exc

        content = response.choices[0].message.content
        if not content:
            raise LLMError(f"{self.provider_name} returned an empty reply.")
        return content


def _messages(system: str, user: str, schema: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"{user}\n\nReply with a single JSON object matching this JSON schema:\n{json.dumps(schema)}"},
    ]


def _supports_schema(model: str) -> bool:
    try:
        return litellm.supports_response_schema(model=model)
    except Exception:
        return False


def parse_json(content: str) -> Any:
    text = _FENCE.sub("", content.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("No JSON object found in the reply.") from None
        return json.loads(text[start : end + 1])
