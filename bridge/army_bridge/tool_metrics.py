from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable


def canonical_schema_bytes(tool_definitions: Iterable[dict[str, Any]]) -> bytes:
    """Serialize a tool-definition array deterministically without exposing its contents."""
    return json.dumps(
        list(tool_definitions), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _tool_name(definition: dict[str, Any]) -> str:
    function = definition.get("function")
    return str(function.get("name") or "") if isinstance(function, dict) else ""


def schema_surface(tool_definitions: Iterable[dict[str, Any]]) -> dict[str, Any]:
    definitions = list(tool_definitions)
    payload = canonical_schema_bytes(definitions)
    return {
        "tool_count": len(definitions),
        "serialized_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "tool_names": sorted(name for name in map(_tool_name, definitions) if name),
    }


def compare_schema_surfaces(
    raw_definitions: Iterable[dict[str, Any]], advertised_definitions: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    raw = list(raw_definitions)
    advertised = list(advertised_definitions)
    raw_names = {_tool_name(item) for item in raw if _tool_name(item)}
    advertised_names = {_tool_name(item) for item in advertised if _tool_name(item)}
    deferred = [item for item in raw if _tool_name(item) not in advertised_names]
    introduced = [item for item in advertised if _tool_name(item) not in raw_names]
    raw_surface = schema_surface(raw)
    advertised_surface = schema_surface(advertised)
    return {
        "raw": raw_surface,
        "advertised": advertised_surface,
        "deferred": schema_surface(deferred),
        "introduced": schema_surface(introduced),
        "net_serialized_byte_reduction": raw_surface["serialized_bytes"] - advertised_surface["serialized_bytes"],
        "measurement": "deterministic_compact_json_bytes_not_provider_tokens",
    }
