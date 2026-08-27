"""Arbitrary input headers -> canonical schema.

Cheap to build, and the day a judge hands over a file with different column names
it saves the entire demo (roadmap R5). The failure mode we are buying our way out
of is a stack trace on stage; what we produce instead is a list of exactly which
required fields could not be located and which headers we did see.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_NORM = re.compile(r"[^a-z0-9]+")


def norm(name: str) -> str:
    """`Src IP` / `source-ip` / `SRC_IP` all collapse to the same key."""
    return _NORM.sub("", str(name).strip().lower())


class SchemaError(Exception):
    """Raised with an analyst-readable explanation, never a traceback."""


@dataclass
class Mapping:
    columns: dict[str, str] = field(default_factory=dict)   # canonical -> input header
    unmapped_inputs: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    chain_only: bool = False

    def get(self, canonical: str) -> str | None:
        return self.columns.get(canonical)


def build_mapping(headers: list[str], cfg: dict) -> Mapping:
    aliases: dict[str, list[str]] = cfg["aliases"]
    required: list[str] = cfg["required"]

    lookup: dict[str, str] = {}
    for canonical, names in aliases.items():
        for n in names:
            lookup[norm(n)] = canonical

    m = Mapping()
    seen_inputs: set[str] = set()
    for h in headers:
        canonical = lookup.get(norm(h))
        if canonical and canonical not in m.columns:
            m.columns[canonical] = h
            seen_inputs.add(h)
    m.unmapped_inputs = [h for h in headers if h not in seen_inputs]
    m.missing_required = [r for r in required if r not in m.columns]

    from .schema import NETWORK_FIELDS
    m.chain_only = not any(f in m.columns for f in ("src_ip", "dst_ip"))
    return m


def require_mappable(m: Mapping, headers: list[str]) -> None:
    if not m.missing_required:
        return
    raise SchemaError(
        "Could not map these required fields: "
        + ", ".join(m.missing_required)
        + ".\nColumns found in your file: "
        + ", ".join(headers[:40])
        + ("..." if len(headers) > 40 else "")
        + "\nAdd the header name under the matching entry in config/schema_map.yaml "
          "and re-run. No code change is needed."
    )
