"""Harness configuration: harness.yaml, overridden by HARNESS_* environment variables."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

DEFAULT_CONFIG_PATH = Path("harness.yaml")
# ${VAR} or ${VAR:-default} inside harness.yaml values.
_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


class ProviderConfig(BaseModel):
    # Any LiteLLM model string, e.g. "gemini/gemini-3.8-flash" or "ollama_chat/qwen2.5-coder:14b".
    model: str
    api_key_env: str | None = None
    api_base: str | None = None
    # Extra keyword arguments passed straight to litellm.acompletion.
    extra: dict[str, Any] = Field(default_factory=dict)

    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) if self.api_key_env else None

    def is_configured(self) -> bool:
        return self.api_key_env is None or bool(self.api_key())


class GenerationConfig(BaseModel):
    temperature: float = 0.1
    timeout_s: float = 300
    # Re-prompts for claims whose quotes could not be found in the notebook.
    max_repair_attempts: int = 1
    # Re-prompts when the model returns malformed JSON.
    max_parse_retries: int = 2
    # Documents generated at the same time (keep low for free-tier rate limits).
    max_concurrency: int = 3


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    open_browser: bool = True
    # Built frontend served at "/" when the directory exists.
    static_dir: Path = Path("frontend/dist")


class CacheConfig(BaseModel):
    enabled: bool = True
    dir: Path = Path(".harness/cache")


class LimitsConfig(BaseModel):
    max_notebook_bytes: int = 2_000_000
    allowed_suffixes: list[str] = Field(default_factory=lambda: [".py", ".ipynb"])


class Settings(BaseModel):
    provider: str = "gemini"
    providers: dict[str, ProviderConfig] = Field(
        default_factory=lambda: {
            "gemini": ProviderConfig(model="gemini/gemini-3.8-flash", api_key_env="GEMINI_API_KEY"),
        }
    )
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)

    def get_provider(self, name: str | None = None) -> tuple[str, ProviderConfig]:
        name = name or self.provider
        if name not in self.providers:
            raise KeyError(f"Unknown provider '{name}'. Configured: {', '.join(sorted(self.providers))}")
        return name, self.providers[name]


def load_settings(path: Path | None = None) -> Settings:
    path = path or Path(os.environ.get("HARNESS_CONFIG", DEFAULT_CONFIG_PATH))
    data: dict[str, Any] = {}
    if path.exists():
        data = _expand_env(yaml.safe_load(path.read_text()) or {})
    settings = Settings.model_validate(data)
    _apply_env_overrides(settings)
    return settings


def _expand_env(node: Any) -> Any:
    if isinstance(node, str):
        return _ENV_REF.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), node)
    if isinstance(node, dict):
        return {k: _expand_env(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_expand_env(v) for v in node]
    return node


def _apply_env_overrides(settings: Settings) -> None:
    env = os.environ
    if v := env.get("HARNESS_PROVIDER"):
        settings.provider = v
    if v := env.get("HARNESS_MODEL"):
        # Overrides the model of the active provider, e.g. to try another Gemini version.
        settings.providers[settings.provider].model = v
    if v := env.get("HARNESS_HOST"):
        settings.server.host = v
    if v := env.get("HARNESS_PORT"):
        settings.server.port = int(v)
    if v := env.get("HARNESS_OPEN_BROWSER"):
        settings.server.open_browser = v.lower() in {"1", "true", "yes"}
    if v := env.get("HARNESS_CACHE_DIR"):
        settings.cache.dir = Path(v)
    if v := env.get("HARNESS_STATIC_DIR"):
        settings.server.static_dir = Path(v)
