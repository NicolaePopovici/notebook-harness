"""Turns Pydantic models into plain JSON schemas that every provider accepts (no $refs, no titles).

Objects get "additionalProperties": false so OpenAI's strict mode can enforce the schema;
LiteLLM removes it for providers that don't support it.
"""

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
            result = {}
            for key, value in node.items():
                if key == "properties":
                    # Keys here are field names (a field may be called "title"), not schema keywords.
                    result[key] = {name: resolve(field) for name, field in value.items()}
                elif key not in _DROP_KEYS:
                    result[key] = resolve(value)
            if result.get("type") == "object":
                result["additionalProperties"] = False
            return result
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)
