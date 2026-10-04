"""Document models: what the LLM returns (Draft*) and what the API serves after validation."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Audience(StrEnum):
    manager = "manager"
    developer = "developer"
    agent = "agent"


ClaimKind = Literal["fact", "inference"]


# --- LLM output. Kept flat and simple so every provider's JSON-schema mode accepts it. ---


class DraftCitation(BaseModel):
    cell: int = Field(description="Cell number (the N in 'CELL N') that contains the quote.")
    quote: str = Field(description="Code copied verbatim from that cell, 1-6 consecutive lines. No line numbers.")


class DraftClaim(BaseModel):
    text: str = Field(description="One factual statement written for the target reader.")
    kind: ClaimKind = Field(description="'fact' if the code states it directly, 'inference' for risks or consequences.")
    citations: list[DraftCitation] = Field(description="At least one citation supporting the statement.")


class DraftSection(BaseModel):
    heading: str
    claims: list[DraftClaim]


class DraftDocument(BaseModel):
    title: str
    sections: list[DraftSection]


class CitationFix(BaseModel):
    claim_id: str
    citations: list[DraftCitation]


class RepairResponse(BaseModel):
    fixes: list[CitationFix]


# --- Validated output served by the API. ---

CitationStatus = Literal["verified", "relocated", "not_found"]
ClaimStatus = Literal["verified", "partial", "unverified"]


class Citation(BaseModel):
    cell: int
    quote: str
    status: CitationStatus
    # Inclusive 1-based ranges; None when the quote was not found.
    cell_lines: tuple[int, int] | None = None
    file_lines: tuple[int, int] | None = None
    # Number of places the quote matched in the cell; >1 means the first match was used.
    match_count: int = 0
    # Cell the model named, when the quote was actually found in a different cell.
    claimed_cell: int | None = None


class Claim(BaseModel):
    id: str
    text: str
    kind: ClaimKind
    status: ClaimStatus
    citations: list[Citation]
    repaired: bool = False


class Section(BaseModel):
    heading: str
    claims: list[Claim]


class ValidationReport(BaseModel):
    claims_total: int = 0
    claims_verified: int = 0
    claims_partial: int = 0
    claims_unverified: int = 0
    citations_total: int = 0
    citations_not_found: int = 0
    citations_relocated: int = 0
    repair_attempts: int = 0
    # Required sections the model did not write, even after being asked again.
    missing_sections: list[str] = Field(default_factory=list)


class Document(BaseModel):
    audience: Audience
    title: str
    sections: list[Section]
    validation: ValidationReport
    model: str
    prompt_version: str
    notebook_sha256: str
