from backend.config import load_settings


def test_yaml_env_expansion_and_overrides(tmp_path, monkeypatch):
    cfg = tmp_path / "harness.yaml"
    cfg.write_text(
        "provider: a\n"
        "providers:\n"
        "  a: {model: openai/x, api_base: '${TEST_BASE:-http://default}'}\n"
        "  b: {model: ollama_chat/y}\n"
    )
    settings = load_settings(cfg)
    assert settings.providers["a"].api_base == "http://default"

    monkeypatch.setenv("TEST_BASE", "http://custom")
    monkeypatch.setenv("HARNESS_PROVIDER", "b")
    monkeypatch.setenv("HARNESS_MODEL", "ollama_chat/z")
    monkeypatch.setenv("HARNESS_PORT", "9000")
    settings = load_settings(cfg)
    assert settings.providers["a"].api_base == "http://custom"
    assert settings.get_provider() == ("b", settings.providers["b"])
    assert settings.providers["b"].model == "ollama_chat/z"
    assert settings.server.port == 9000


def test_missing_file_uses_defaults(tmp_path):
    settings = load_settings(tmp_path / "absent.yaml")
    assert settings.get_provider()[0] == "gemini"
