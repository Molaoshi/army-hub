import json

from army_bridge.tool_metrics import canonical_schema_bytes, compare_schema_surfaces, schema_surface


def definition(name: str, description: str = "") -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description or f"Definition for {name}",
        "parameters": {"type": "object", "properties": {}},
    }}


def test_schema_surface_is_deterministic_and_does_not_need_schema_content():
    first = [definition("alpha", "Read alpha"), definition("beta", "Read beta")]
    shuffled_keys = [{"function": dict(reversed(list(item["function"].items()))), "type": "function"} for item in first]
    surface = schema_surface(first)
    assert surface == schema_surface(shuffled_keys)
    assert surface["tool_count"] == 2
    assert surface["serialized_bytes"] == len(canonical_schema_bytes(first))
    assert surface["tool_names"] == ["alpha", "beta"]
    assert "Read alpha" not in json.dumps(surface)


def test_comparison_separates_deferred_and_replacement_schemas():
    raw = [definition("core"), definition("mcp_alpha"), definition("plugin_beta")]
    advertised = [definition("core"), definition("tool_search"), definition("tool_describe"), definition("tool_call")]
    report = compare_schema_surfaces(raw, advertised)
    assert report["raw"]["tool_count"] == 3
    assert report["advertised"]["tool_count"] == 4
    assert report["deferred"]["tool_names"] == ["mcp_alpha", "plugin_beta"]
    assert report["introduced"]["tool_names"] == ["tool_call", "tool_describe", "tool_search"]
    assert report["net_serialized_byte_reduction"] == (
        report["raw"]["serialized_bytes"] - report["advertised"]["serialized_bytes"]
    )
    assert report["measurement"] == "deterministic_compact_json_bytes_not_provider_tokens"


def test_empty_surfaces_report_zero_not_a_token_estimate():
    report = compare_schema_surfaces([], [])
    assert report["raw"]["serialized_bytes"] == 2
    assert report["advertised"]["serialized_bytes"] == 2
    assert report["net_serialized_byte_reduction"] == 0
