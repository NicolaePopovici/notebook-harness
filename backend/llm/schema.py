"""Turns Pydantic models into plain JSON schemas that every provider accepts (no $refs, no titles)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

_DROP_KEYS = {"title", "default"}


def inline_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(defs[node["$ref"].split("/")[-1]])
            return {k: resolve(v) for k, v in node.items() if k not in _DROP_KEYS}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)
