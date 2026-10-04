import asyncio

import litellm
import pytest

from backend.config import GenerationConfig, ProviderConfig
from backend.llm.client import ContextTooLargeError, LLMClient
from backend.pipeline.generate import build_prompt, generate_document
from backend.pipeline.models import Audience, DraftDocument

from .conftest import FakeCompletion, draft


def test_context_limit_sources():
    assert ProviderConfig(model="openai/x", max_input_tokens=5000).context_limit() == (5000, "max_input_tokens in harness.yaml")
    assert ProviderConfig(model="ollama_chat/q", extra={"num_ctx": 32768}).context_limit() == (32768, "num_ctx in harness.yaml")
    limit, source = ProviderConfig(model="openai/gpt-4o-mini").context_limit()
    assert limit >= 100_000 and source == "LiteLLM's model info"
    assert ProviderConfig(model="openai/unknown-local-model").context_limit() is None


def test_check_fits(notebook):
    small = LLMClient("p", ProviderConfig(model="openai/x", max_input_tokens=9000), GenerationConfig(reserved_output_tokens=8000))
    with pytest.raises(ContextTooLargeError, match=r"accepts 9,000 \(max_input_tokens in harness.yaml\)"):
        small.check_fits(*build_prompt(notebook, Audience.manager), output=DraftDocument)

    big = LLMClient("p", ProviderConfig(model="openai/x", max_input_tokens=100_000), GenerationConfig())
    big.check_fits(*build_prompt(notebook, Audience.manager), output=DraftDocument)

    unknown = LLMClient("p", ProviderConfig(model="openai/unknown-local-model"), GenerationConfig())
    unknown.check_fits(*build_prompt(notebook, Audience.manager), output=DraftDocument)


def test_oversized_prompt_is_never_sent(notebook):
    fake = FakeCompletion(draft(("Tol.", 2, "TOL = 0.01")))
    client = LLMClient("p", ProviderConfig(model="openai/x", max_input_tokens=1000), GenerationConfig(), fake)
    with pytest.raises(ContextTooLargeError):
        asyncio.run(generate_document(notebook, Audience.manager, client))
    assert fake.calls == []


def test_provider_context_error_is_explained(notebook):
    async def overflow(**kwargs):
        raise litellm.ContextWindowExceededError("maximum context length is 1000 tokens", model="x", llm_provider="openai")

    client = LLMClient("p", ProviderConfig(model="openai/unknown-local-model"), GenerationConfig(), overflow)
    with pytest.raises(ContextTooLargeError, match="too long for openai/unknown-local-model's context window"):
        asyncio.run(generate_document(notebook, Audience.manager, client))
