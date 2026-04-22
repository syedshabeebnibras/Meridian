"""Export a JSON Schema for every contract in `meridian_contracts`.

Used by the CI `contracts` job and available locally for humans that want to
inspect the wire format (e.g. the RAG team reviewing RetrievalResult).

Usage:
    uv run python scripts/export_schemas.py --out build/schemas
"""

from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path

import meridian_contracts as contracts
from pydantic import BaseModel


def iter_contract_classes() -> list[tuple[str, type[BaseModel]]]:
    """Every BaseModel subclass re-exported from meridian_contracts."""
    items: list[tuple[str, type[BaseModel]]] = []
    for name in contracts.__all__:
        obj = getattr(contracts, name)
        if inspect.isclass(obj) and issubclass(obj, BaseModel):
            items.append((name, obj))
    return sorted(items, key=lambda item: item[0])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("build/schemas"),
        help="Directory to write schemas into.",
    )
    args = parser.parse_args()

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for name, cls in iter_contract_classes():
        schema = cls.model_json_schema(mode="serialization")
        path = out / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2, sort_keys=True))
        written.append(name)

    print(f"Wrote {len(written)} schemas to {out}:")
    for name in written:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
