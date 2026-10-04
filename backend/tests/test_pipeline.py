import asyncio

import pytest

from backend.config import GenerationConfig, ProviderConfig
from backend.llm.client import LLMClient, LLMError
from backend.pipeline import prompts
from backend.pipeline.generate import generate_document
from backend.pipeline.models import Audience

from .conftest import FakeCompletion, draft


def client(fake, **gen):
    return LLMClient("fake", ProviderConfig(model="openai/gpt-4o-mini"), GenerationConfig(**gen), fake)


def test_verified_document(notebook):
    fake = FakeCompletion(draft(("Tolerance is one cent.", 2, "TOL = 0.01")))
    doc = asyncio.run(generate_document(notebook, Audience.manager, client(fake)))
    claim = doc.sections[0].claims[0]
    assert claim.status == "verified"
    assert claim.citations[0].file_lines == (8, 8)
    assert doc.validation.claims_unverified == 0
    assert doc.validation.missing_sections == []
    assert doc.validation.repair_attempts == 0
    assert len(fake.calls) == 1
    # The whole notebook is in the single prompt, without line numbers.
    prompt = fake.calls[0]["messages"][1]["content"]
    assert "=== CELL 5 · python ===" in prompt
    assert 'saveAsTable("fin.allocations")' in prompt


def test_repair_fixes_bad_quote(notebook):
    fake = FakeCompletion(
        draft(("Output overwrites the allocations table.", 5, 'mode("append")'), audience=Audience.developer),
        {"fixes": [{"claim_id": "s1c1", "citations": [{"cell": 5, "quote": 'x.write.mode("overwrite")'}]}]},
    )
    doc = asyncio.run(generate_document(notebook, Audience.developer, client(fake)))
    claim = doc.sections[0].claims[0]
    assert claim.status == "verified"
    assert claim.repaired
    assert [c.status for c in claim.citations] == ["verified"]
    assert doc.validation.repair_attempts == 1
    assert "s1c1" in fake.calls[1]["messages"][1]["content"]


def test_unrepairable_claim_stays_unverified(notebook):
    fake = FakeCompletion(
        draft(("Receipts are converted to EUR.", 3, "convert_to_eur(r)"), audience=Audience.agent),
        {"fixes": [{"claim_id": "s1c1", "citations": []}]},
    )
    doc = asyncio.run(generate_document(notebook, Audience.agent, client(fake)))
    assert doc.sections[0].claims[0].status == "unverified"
    assert doc.validation.claims_unverified == 1


def test_no_repair_when_disabled(notebook):
    fake = FakeCompletion(draft(("Made up.", 3, "nothing like this"), audience=Audience.agent))
    doc = asyncio.run(generate_document(notebook, Audience.agent, client(fake, max_repair_attempts=0)))
    assert doc.validation.claims_unverified == 1
    assert len(fake.calls) == 1


def test_malformed_json_is_retried(notebook):
    good = draft(("Tolerance is one cent.", 2, "TOL = 0.01"))
    fake = FakeCompletion("not json at all", good)
    doc = asyncio.run(generate_document(notebook, Audience.manager, client(fake)))
    assert doc.validation.claims_unverified == 0
    assert len(fake.calls) == 2


def test_code_fenced_json_is_accepted(notebook):
    import json

    fake = FakeCompletion("```json\n" + json.dumps(draft(("Tol.", 2, "TOL = 0.01"))) + "\n```")
    doc = asyncio.run(generate_document(notebook, Audience.manager, client(fake)))
    assert doc.validation.claims_unverified == 0


def test_gives_up_after_parse_retries(notebook):
    fake = FakeCompletion("still not json")
    with pytest.raises(LLMError, match="valid JSON"):
        asyncio.run(generate_document(notebook, Audience.manager, client(fake, max_parse_retries=1)))
    assert len(fake.calls) == 2


def test_schema_sent_when_model_supports_it(notebook):
    fake = FakeCompletion(draft(("Tol.", 2, "TOL = 0.01")))
    asyncio.run(generate_document(notebook, Audience.manager, client(fake)))
    rf = fake.calls[0]["response_format"]
    assert rf["type"] == "json_schema"
    assert "$defs" not in str(rf) and "$ref" not in str(rf)


def test_schema_keeps_fields_named_like_keywords():
    from backend.llm.schema import inline_schema
    from backend.pipeline.models import DraftDocument

    schema = inline_schema(DraftDocument)
    assert set(schema["required"]) <= set(schema["properties"])
    assert "title" in schema["properties"]
    assert "title" not in schema["properties"]["title"]
    # OpenAI strict mode: every object closed and every field required.
    claim = schema["properties"]["sections"]["items"]["properties"]["claims"]["items"]
    assert claim["additionalProperties"] is False
    assert set(claim["required"]) == set(claim["properties"])


def test_missing_sections_are_requested_and_ordered(notebook):
    full = draft(("Tolerance is one cent.", 2, "TOL = 0.01"))
    required = prompts.required_sections(Audience.manager)
    # The model only writes the last section, then the rest when asked (headings in a different case).
    first = {"title": "Doc", "sections": full["sections"][-1:]}
    rest = {"title": "x", "sections": [dict(s, heading=s["heading"].upper()) for s in full["sections"][:-1]]}
    fake = FakeCompletion(first, rest)
    doc = asyncio.run(generate_document(notebook, Audience.manager, client(fake)))
    assert [s.heading.lower() for s in doc.sections] == [h.lower() for h in required]
    assert doc.validation.missing_sections == []
    assert len(fake.calls) == 2
    second_prompt = fake.calls[1]["messages"][1]["content"]
    assert '"What this notebook does"' in second_prompt and '"Questions to ask the team"' not in second_prompt.split("Sections to write:")[1].split("Notebook:")[0]


def test_sections_still_missing_are_reported(notebook):
    only_last = draft(("Tolerance is one cent.", 2, "TOL = 0.01"))
    only_last["sections"] = only_last["sections"][-1:]
    fake = FakeCompletion(only_last)
    doc = asyncio.run(generate_document(notebook, Audience.manager, client(fake)))
    assert "What could go wrong" in doc.validation.missing_sections
    assert "What this notebook does" in doc.validation.missing_sections
    assert len(doc.sections) == 1


def test_empty_section_counts_as_missing(notebook):
    d = draft(("Tolerance is one cent.", 2, "TOL = 0.01"))
    d["sections"][3]["claims"] = []
    fake = FakeCompletion(d, {"title": "x", "sections": [draft(("Risk.", 5, 'mode("overwrite")'))["sections"][0] | {"heading": "What could go wrong"}]})
    doc = asyncio.run(generate_document(notebook, Audience.manager, client(fake)))
    assert doc.validation.missing_sections == []
    assert doc.sections[3].heading == "What could go wrong"
    assert doc.sections[3].claims[0].text == "Risk."
