"""Merge source payloads without losing provenance."""
from typing import Any


def merge_fields(*records: dict[str, Any]) -> dict[str, Any]:
    """First non-empty value wins; provenance is retained per field."""
    result: dict[str, Any] = {}
    provenance: dict[str, list[str]] = {}
    for record in records:
        source = str(record.get("_source", "unknown"))
        for key, value in record.items():
            if key.startswith("_") or value in (None, "", [], {}):
                continue
            provenance.setdefault(key, []).append(source)
            if key not in result:
                result[key] = value
    result["_provenance"] = provenance
    return result
