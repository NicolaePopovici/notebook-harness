"""Generates one document: one prompt with the whole notebook, then quote validation and a targeted repair pass."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable

from ..llm.client import LLMClient
from ..parsing.models import Notebook
from ..validation.citations import CitationValidator, build_report, claim_status
from . import prompts
from .models import Audience, Claim, Document, DraftDocument, DraftSection, RepairResponse, Section
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

    required = prompts.required_sections(audience)
    missing = _missing_sections(draft.sections, required)
    if missing and client.generation.max_repair_attempts > 0:
        await progress(f"Writing {len(missing)} missing section(s): {', '.join(missing)}")
        extra = await client.complete_json(system, _missing_sections_prompt(audience, notebook, missing), output=DraftDocument)
        wanted = {_heading_key(h) for h in missing}
        draft.sections += [s for s in extra.sections if _heading_key(s.heading) in wanted and s.claims]
        missing = _missing_sections(draft.sections, required)
    draft.sections = _in_required_order(draft.sections, required)

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
        validation=build_report(sections, attempts).model_copy(update={"missing_sections": missing}),
        model=client.model,
        prompt_version=prompts.PROMPT_VERSION,
        notebook_sha256=notebook.sha256,
    )


def _heading_key(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", heading.lower()).strip()


def _missing_sections(sections: list[DraftSection], required: list[str]) -> list[str]:
    present = {_heading_key(s.heading) for s in sections if s.claims}
    return [h for h in required if _heading_key(h) not in present]


def _in_required_order(sections: list[DraftSection], required: list[str]) -> list[DraftSection]:
    """Required sections first, in prompt order (first one wins if repeated); any extra sections after."""
    required_keys = [_heading_key(h) for h in required]
    by_key: dict[str, DraftSection] = {}
    extra = []
    for section in sections:
        key = _heading_key(section.heading)
        if key not in required_keys:
            extra.append(section)
        elif section.claims and key not in by_key:
            by_key[key] = section
    return [by_key[k] for k in required_keys if k in by_key] + extra


def _missing_sections_prompt(audience: Audience, notebook: Notebook, missing: list[str]) -> str:
    headings = "\n".join(f'- "{h}"' for h in missing)
    return (
        f"{prompts.load(audience.value)}\n\n{prompts.load('missing_sections')}\n{headings}\n\n"
        f"{render_notebook(notebook)}"
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
