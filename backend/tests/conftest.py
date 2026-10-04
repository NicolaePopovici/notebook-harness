from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.config import LimitsConfig
from backend.parsing.loader import load_notebook
from backend.parsing.models import Notebook
from backend.pipeline import prompts
from backend.pipeline.models import Audience

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
        if callable(reply):
            reply = reply(kwargs)
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


FILLER = ("The tolerance is one cent.", 2, "TOL = 0.01")


def draft(*claims, audience=Audience.manager, title="Doc"):
    """A complete draft: `claims` go in the audience's first section, every other required section gets a filler claim."""
    sections = []
    for i, heading in enumerate(prompts.required_sections(audience)):
        section_claims = claims if i == 0 else (FILLER,)
        sections.append(
            {
                "heading": heading,
                "claims": [
                    {"text": text, "kind": "fact", "citations": [{"cell": cell, "quote": quote}]}
                    for text, cell, quote in section_claims
                ],
            }
        )
    return {"title": title, "sections": sections}


def audience_of(kwargs) -> Audience:
    """Which audience a captured completion call was for, from its prompt."""
    user = kwargs["messages"][1]["content"]
    return next(a for a in Audience if prompts.load(a.value) in user)
