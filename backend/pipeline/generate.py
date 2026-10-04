"""Generates one document: one prompt with the whole notebook, then quote validation and a targeted repair pass."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from ..llm.client import LLMClient
from ..parsing.models import Notebook
from ..validation.citations import CitationValidator, build_report, claim_status
from . import prompts
from .models import Audience, Claim, Document, DraftDocument, RepairResponse, Section
from .render import render_notebook

Progress = Callable[[str], Awaitable[None]]


async def _no_progress(_: str) -> None:
    pass


async def generate_document(
    notebook: Notebook,
    audience: Audience,
    client: LLMClient,
    progress: Progress = _no_progress,
) -> Document:
    system = prompts.load("system")
    user = f"{prompts.load(audience.value)}\n\n{render_notebook(notebook)}"

    await progress("Writing document")
    draft = await client.complete_json(system, user, output=DraftDocument)

    validator = CitationValidator(notebook)
    sections = validator.resolve_document(draft)

    attempts = 0
    while attempts < client.generation.max_repair_attempts and (failing := _failing_claims(sections)):
        attempts += 1
        await progress(f"Repairing {len(failing)} claim(s) with citations not found in the notebook (attempt {attempts})")
        repair = await client.complete_json(system, _repair_prompt(notebook, failing), output=RepairResponse)
        _apply_repairs(sections, repair, validator)

    await progress("Validated citations")
    return Document(
        audience=audience,
        title=draft.title,
        sections=sections,
        validation=build_report(sections, attempts),
        model=client.model,
        prompt_version=prompts.PROMPT_VERSION,
        notebook_sha256=notebook.sha256,
    )


def _failing_claims(sections: list[Section]) -> list[Claim]:
    return [claim for section in sections for claim in section.claims if claim.status != "verified"]


def _repair_prompt(notebook: Notebook, failing: list[Claim]) -> str:
    items = [
        {
            "claim_id": claim.id,
            "text": claim.text,
            "citations_not_found": [
                {"cell": c.cell, "quote": c.quote} for c in claim.citations if c.status == "not_found"
            ],
        }
        for claim in failing
    ]
    return f"{prompts.load('repair')}\n{json.dumps(items, indent=2)}\n\n{render_notebook(notebook)}"


def _apply_repairs(sections: list[Section], repair: RepairResponse, validator: CitationValidator) -> None:
    claims = {claim.id: claim for section in sections for claim in section.claims}
    for fix in repair.fixes:
        claim = claims.get(fix.claim_id)
        if claim is None or claim.status == "verified":
            continue
        # Keep citations that were already found; replace the ones that were not.
        kept = [c for c in claim.citations if c.status != "not_found"]
        new = [c for c in (validator.resolve_citation(d) for d in fix.citations) if c.status != "not_found"]
        if not new:
            continue
        claim.citations = kept + new
        claim.status = claim_status(claim.citations)
        claim.repaired = True
