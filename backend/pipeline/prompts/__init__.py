"""Prompt templates. PROMPT_VERSION changes whenever a template changes, which invalidates cached documents."""

from __future__ import annotations

import hashlib
import re
from functools import cache
from pathlib import Path

from ..models import Audience

_DIR = Path(__file__).parent
_NAMES = ["system", "repair", "missing_sections", *(a.value for a in Audience)]
# Section lines in the audience prompts look like: 1. "What this notebook does": ...
_SECTION = re.compile(r'^\d+\.\s+"([^"]+)"', re.MULTILINE)


@cache
def load(name: str) -> str:
    return (_DIR / f"{name}.md").read_text().strip()


def required_sections(audience: Audience) -> list[str]:
    """Section headings the audience's prompt asks for, in order."""
    return _SECTION.findall(load(audience.value))


PROMPT_VERSION = hashlib.sha256("\n".join(load(n) for n in _NAMES).encode()).hexdigest()[:10]
