from __future__ import annotations

import json
from importlib.resources import files

from .models import RuleCatalog, SourceReference


def load_source_registry() -> dict[str, SourceReference]:
    resource = files("app.vedicdust").joinpath("resources/sources.json")
    payload = json.loads(resource.read_text(encoding="utf-8"))
    sources = [SourceReference.model_validate(item) for item in payload["sources"]]
    registry = {source.source_id: source for source in sources}
    if len(registry) != len(sources):
        raise ValueError("source registry contains duplicate source ids")
    return registry


def validate_profile_source_ids(source_ids: list[str]) -> None:
    registry = load_source_registry()
    missing = sorted(set(source_ids) - set(registry))
    if missing:
        raise ValueError(f"unknown source id(s): {', '.join(missing)}")


def load_rule_catalog() -> RuleCatalog:
    resource = files("app.vedicdust").joinpath("resources/rules.json")
    return RuleCatalog.model_validate_json(resource.read_text(encoding="utf-8"))


def validate_rule_catalog_sources(catalog: RuleCatalog) -> None:
    registry = load_source_registry()
    missing = sorted(
        {
            source_id
            for rule in catalog.rules
            for source_id in rule.source_ids
            if source_id not in registry
        }
    )
    if missing:
        raise ValueError(f"rule catalog has unknown source id(s): {', '.join(missing)}")
