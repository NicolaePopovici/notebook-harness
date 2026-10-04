import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.config import CacheConfig, ProviderConfig, ServerConfig, Settings

from .conftest import FakeCompletion, audience_of, draft


@pytest.fixture
def settings(tmp_path):
    return Settings(
        provider="fake",
        providers={
            "fake": ProviderConfig(model="openai/gpt-4o-mini"),
            "needs_key": ProviderConfig(model="gemini/gemini-2.5-flash", api_key_env="HARNESS_TEST_MISSING_KEY"),
        },
        cache=CacheConfig(dir=tmp_path / "cache"),
        server=ServerConfig(static_dir=tmp_path / "no-frontend"),
    )


@pytest.fixture
def fake():
    claim = ("Allocations are overwritten.", 5, 'x.write.mode("overwrite")')
    return FakeCompletion(lambda kwargs: draft(claim, audience=audience_of(kwargs)))


@pytest.fixture
def api(settings, fake):
    with TestClient(create_app(settings, completion_fn=fake)) as client:
        yield client


def open_sample(api, sample_path):
    response = api.post("/api/notebooks", json={"path": str(sample_path)})
    assert response.status_code == 200, response.text
    return response.json()


def run_to_end(api, notebook_id, **body):
    response = api.post(f"/api/notebooks/{notebook_id}/runs", json=body)
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    with api.stream("GET", f"/api/runs/{run_id}/events") as stream:
        events = [line for line in stream.iter_lines() if line.startswith("event:")]
    return api.get(f"/api/runs/{run_id}").json(), events


def test_open_notebook(api, sample_path):
    nb = open_sample(api, sample_path)
    assert len(nb["cells"]) == 5
    assert nb["cells"][1] == {"index": 2, "lang": "python", "title": "Config", "line_count": 2, "file_lines": [8, 9]}


def test_open_notebook_error(api):
    response = api.post("/api/notebooks", json={"path": "/nope/missing.py"})
    assert response.status_code == 400
    assert "not found" in response.json()["detail"]


def test_cell_with_highlight(api, sample_path):
    nb = open_sample(api, sample_path)
    cell = api.get(f"/api/notebooks/{nb['id']}/cells/4", params={"start": 5, "end": 5}).json()
    assert cell["highlight"] == [5, 5]
    assert [line["highlighted"] for line in cell["lines"]] == [False, False, False, False, True]
    assert cell["lines"][4]["file_line"] == 24


def test_cell_errors(api, sample_path):
    nb = open_sample(api, sample_path)
    assert api.get(f"/api/notebooks/{nb['id']}/cells/99").status_code == 404
    assert api.get(f"/api/notebooks/{nb['id']}/cells/2", params={"start": 1, "end": 9}).status_code == 400
    assert api.get("/api/notebooks/unknown/cells/1").status_code == 404


def test_run_generates_all_documents(api, sample_path, fake):
    nb = open_sample(api, sample_path)
    run, events = run_to_end(api, nb["id"])
    assert run["status"] == "completed"
    assert set(run["documents"]) == {"manager", "developer", "agent"}
    citation = run["documents"]["manager"]["sections"][0]["claims"][0]["citations"][0]
    assert citation["cell_lines"] == [2, 2]
    assert citation["file_lines"] == [29, 29]
    assert events[0] == "event: run_started" and events[-1] == "event: run_finished"
    assert len(fake.calls) == 3


def test_second_run_uses_cache(api, sample_path, fake):
    nb = open_sample(api, sample_path)
    run_to_end(api, nb["id"], audiences=["agent"])
    run, _ = run_to_end(api, nb["id"], audiences=["agent"])
    assert run["status"] == "completed"
    assert len(fake.calls) == 1
    run_to_end(api, nb["id"], audiences=["agent"], force=True)
    assert len(fake.calls) == 2


def test_failed_document_is_reported(api, sample_path, fake):
    fake.replies = ["garbage"]
    nb = open_sample(api, sample_path)
    run, events = run_to_end(api, nb["id"], audiences=["manager"])
    assert run["status"] == "failed"
    assert "valid JSON" in run["errors"]["manager"]
    assert "event: document_failed" in events


def test_provider_checks(api, sample_path):
    nb = open_sample(api, sample_path)
    unknown = api.post(f"/api/notebooks/{nb['id']}/runs", json={"provider": "nope"})
    assert unknown.status_code == 400
    missing_key = api.post(f"/api/notebooks/{nb['id']}/runs", json={"provider": "needs_key"})
    assert missing_key.status_code == 400
    assert "HARNESS_TEST_MISSING_KEY" in missing_key.json()["detail"]
    providers = {p["name"]: p for p in api.get("/api/providers").json()}
    assert providers["fake"]["default"] and not providers["needs_key"]["configured"]


def test_run_rejected_when_notebook_too_large(settings, fake, sample_path):
    settings.providers["tiny"] = ProviderConfig(model="openai/x", max_input_tokens=1000)
    with TestClient(create_app(settings, completion_fn=fake)) as api:
        nb = open_sample(api, sample_path)
        response = api.post(f"/api/notebooks/{nb['id']}/runs", json={"provider": "tiny"})
    assert response.status_code == 400
    assert "sample_notebook.py is too large for tiny" in response.json()["detail"]
    assert fake.calls == []
