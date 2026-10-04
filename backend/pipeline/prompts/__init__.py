"""Prompt templates. PROMPT_VERSION changes whenever a template changes, which invalidates cached documents."""

from __future__ import annotations

import hashlib
from functools import cache
from pathlib import Path

from ..models import Audience

_DIR = Path(__file__).parent
_NAMES = ["system", "repair", *(a.value for a in Audience)]


@cache
def load(name: str) -> str:
    return (_DIR / f"{name}.md").read_text().strip()


PROMPT_VERSION = hashlib.sha256("\n".join(load(n) for n in _NAMES).encode()).hexdigest()[:10]
