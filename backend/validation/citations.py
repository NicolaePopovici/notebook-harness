"""Turns a draft document into a validated one: each citation is located in the code, each claim gets a status."""

from __future__ import annotations

from ..parsing.models import Notebook
from ..pipeline.models import (
    Citation,
    Claim,
    ClaimStatus,
    DraftCitation,
    DraftClaim,
    DraftDocument,
    Section,
    ValidationReport,
)
from .quotes import QuoteLocator

# Very short quotes such as "df" or ")" match almost anywhere and prove nothing.
MIN_QUOTE_CHARS = 4


class CitationValidator:
    def __init__(self, notebook: Notebook):
        self.notebook = notebook
        self.locator = QuoteLocator(notebook.cells)

    def resolve_citation(self, draft: DraftCitation) -> Citation:
        quote = draft.quote.strip()
        if len("".join(quote.split())) < MIN_QUOTE_CHARS:
            return Citation(cell=draft.cell, quote=draft.quote, status="not_found")

        if match := self.locator.locate(draft.cell, quote):
            status = "verified"
            claimed_cell = None
        elif match := self.locator.locate_elsewhere(quote, exclude=draft.cell):
            # Real code, wrong cell number: keep it, but say so.
            status = "relocated"
            claimed_cell = draft.cell
        else:
            return Citation(cell=draft.cell, quote=draft.quote, status="not_found")

        return Citation(
            cell=match.cell_index,
            quote=draft.quote,
            status=status,
            cell_lines=match.cell_lines,
            file_lines=match.file_lines,
            match_count=match.match_count,
            claimed_cell=claimed_cell,
        )

    def resolve_claim(self, claim_id: str, draft: DraftClaim) -> Claim:
        citations = [self.resolve_citation(c) for c in draft.citations]
        return Claim(
            id=claim_id,
            text=draft.text,
            kind=draft.kind,
            status=claim_status(citations),
            citations=citations,
        )

    def resolve_document(self, draft: DraftDocument) -> list[Section]:
        sections = []
        for s_idx, draft_section in enumerate(draft.sections, start=1):
            claims = [
                self.resolve_claim(f"s{s_idx}c{c_idx}", draft_claim)
                for c_idx, draft_claim in enumerate(draft_section.claims, start=1)
            ]
            sections.append(Section(heading=draft_section.heading, claims=claims))
        return sections


def claim_status(citations: list[Citation]) -> ClaimStatus:
    found = sum(c.status != "not_found" for c in citations)
    if found == 0:
        return "unverified"
    return "verified" if found == len(citations) else "partial"


def build_report(sections: list[Section], repair_attempts: int) -> ValidationReport:
    report = ValidationReport(repair_attempts=repair_attempts)
    for section in sections:
        for claim in section.claims:
            report.claims_total += 1
            match claim.status:
                case "verified":
                    report.claims_verified += 1
                case "partial":
                    report.claims_partial += 1
                case "unverified":
                    report.claims_unverified += 1
            for citation in claim.citations:
                report.citations_total += 1
                report.citations_not_found += citation.status == "not_found"
                report.citations_relocated += citation.status == "relocated"
    return report
