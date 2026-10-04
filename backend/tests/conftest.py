from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.config import LimitsConfig
from backend.parsing.loader import load_notebook
from backend.parsing.models import Notebook

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_path() -> Path:
    return FIXTURES / "sample_notebook.py"


@pytest.fixture
def notebook(sample_path: Path) -> Notebook:
    return load_notebook(str(sample_path), LimitsConfig())


class FakeCompletion:
    """Stands in for litellm.acompletion: returns queued replies and records every call."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def draft(*claims, title="Doc", heading="Section"):
    return {
        "title": title,
        "sections": [
            {
                "heading": heading,
                "claims": [
                    {"text": text, "kind": "fact", "citations": [{"cell": cell, "quote": quote}]}
                    for text, cell, quote in claims
                ],
            }
        ],
    }
