from __future__ import annotations

import json
import hashlib
from importlib.resources import files
from pathlib import Path

from .models import (
    EvidenceClass,
    RuleCatalog,
    SourceReference,
    ValidationFixtureReference,
    ValidationFixtureRegistry,
)
from .professional_review import validate_professional_review_fixture


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
    catalog = RuleCatalog.model_validate_json(resource.read_text(encoding="utf-8"))
    validate_rule_catalog_sources(catalog)
    return catalog


def load_validation_fixture_registry(
    registry_path: Path | None = None,
) -> dict[str, ValidationFixtureReference]:
    if registry_path is None:
        resource = files("app.vedicdust").joinpath("resources/validation_fixtures.json")
        payload_text = resource.read_text(encoding="utf-8")
        resource_dir = Path(str(resource)).resolve().parent
    else:
        resolved = registry_path.expanduser().resolve()
        payload_text = resolved.read_text(encoding="utf-8")
        resource_dir = resolved.parent
    payload = ValidationFixtureRegistry.model_validate_json(payload_text)
    for fixture in payload.fixtures:
        if fixture.fixture_kind not in {"independent_external", "professional_review"}:
            continue
        artifact_path = Path(str(fixture.evidence_artifact_path)).expanduser()
        if not artifact_path.is_absolute():
            artifact_path = resource_dir / artifact_path
        artifact_path = artifact_path.resolve()
        if not artifact_path.is_file():
            raise FileNotFoundError(
                f"validation evidence artifact not found for {fixture.fixture_id}: {artifact_path}"
            )
        digest = "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if digest != fixture.evidence_artifact_sha256:
            raise ValueError(f"validation evidence artifact hash mismatch for {fixture.fixture_id}")
        if fixture.fixture_kind == "professional_review":
            validate_professional_review_fixture(fixture, artifact_path)
    return {fixture.fixture_id: fixture for fixture in payload.fixtures}


def active_rule_pack_version() -> str:
    """Return the runtime rule-pack identifier from its single source of truth."""

    return f"vedicdust-rules-{load_rule_catalog().catalog_version}"


def validate_rule_catalog_sources(catalog: RuleCatalog) -> None:
    registry = load_source_registry()
    fixture_registry = load_validation_fixture_registry()
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

    missing_fixtures = sorted(
        {
            fixture_id
            for rule in catalog.rules
            for fixture_id in rule.validation_fixture_ids
            if fixture_id not in fixture_registry
        }
    )
    if missing_fixtures:
        raise ValueError(
            "rule catalog has unknown validation fixture id(s): " + ", ".join(missing_fixtures)
        )

    errors: list[str] = []
    for rule in catalog.rules:
        sources = [registry[source_id] for source_id in rule.source_ids]
        if rule.status != "draft":
            pending_sources = [
                source.source_id
                for source in sources
                if source.citation_status == "pending-edition-pin"
            ]
            if pending_sources:
                errors.append(
                    f"active rule {rule.rule_id} uses pending-edition source(s): "
                    + ", ".join(sorted(pending_sources))
                )
        if not any(source.evidence_class == rule.evidence_class for source in sources):
            errors.append(
                f"rule {rule.rule_id} has no source matching evidence class "
                f"{rule.evidence_class.value}"
            )
        if rule.status == "validated" and not rule.validation_fixture_ids:
            errors.append(f"validated rule {rule.rule_id} requires validation fixtures")
        if rule.rule_kind == "judgement" and rule.status != "draft":
            if not rule.validation_fixture_ids or not any(
                fixture_registry[fixture_id].fixture_kind == "contract"
                for fixture_id in rule.validation_fixture_ids
            ):
                errors.append(
                    f"active judgement rule {rule.rule_id} requires an executable contract fixture"
                )
        if rule.judgement_use != "directional":
            continue
        if rule.rule_kind != "judgement":
            errors.append(f"directional rule {rule.rule_id} must be a judgement rule")
        if rule.status != "validated":
            errors.append(f"directional rule {rule.rule_id} must be validated")
        if not rule.validation_fixture_ids:
            errors.append(f"directional rule {rule.rule_id} requires validation fixtures")
        elif not any(
            fixture_registry[fixture_id].fixture_kind == "professional_review"
            for fixture_id in rule.validation_fixture_ids
        ):
            errors.append(f"directional rule {rule.rule_id} requires a professional review fixture")
        has_pinned_authority = any(
            source.citation_status == "pinned"
            and source.evidence_class
            in {EvidenceClass.CLASSICAL_TEXT, EvidenceClass.LINEAGE_COMMENTARY}
            for source in sources
        )
        if not has_pinned_authority:
            errors.append(
                f"directional rule {rule.rule_id} requires a pinned classical or lineage source"
            )
    if errors:
        raise ValueError("; ".join(errors))
