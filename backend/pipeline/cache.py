"""On-disk cache of generated documents, keyed by notebook content, model and prompt version."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from pydantic import ValidationError

from .models import Audience, Document

log = logging.getLogger(__name__)


class DocumentCache:
    def __init__(self, directory: Path, enabled: bool = True):
        self.directory = directory
        self.enabled = enabled

    def _path(self, sha256: str, audience: Audience, model: str, prompt_version: str) -> Path:
        model_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", model)
        return self.directory / sha256 / f"{audience.value}--{model_slug}--{prompt_version}.json"

    def get(self, sha256: str, audience: Audience, model: str, prompt_version: str) -> Document | None:
        if not self.enabled:
            return None
        path = self._path(sha256, audience, model, prompt_version)
        if not path.exists():
            return None
        try:
            return Document.model_validate_json(path.read_text())
        except (OSError, ValidationError) as exc:
            log.warning("Ignoring unreadable cache entry %s: %s", path, exc)
            return None

    def put(self, document: Document) -> None:
        if not self.enabled:
            return
        path = self._path(document.notebook_sha256, document.audience, document.model, document.prompt_version)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(document.model_dump_json(indent=2))
        tmp.replace(path)
