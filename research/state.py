"""Versioned portable research state and company-specific scenario defaults."""

import json
from dataclasses import asdict, dataclass, replace
from datetime import date
from math import isfinite

from research.model import SCENARIO_NAMES, ReferencePrice, Scenario

NOTES = {
    "thesis": "Investment thesis",
    "evidence": "Supporting evidence",
    "catalysts": "Catalysts",
    "risks": "Risks",
    "invalidation": "Evidence that would invalidate the thesis",
}
VERSION = 1
MAX_JSON_BYTES = 100_000


@dataclass(frozen=True)
class Workspace:
    company: str
    base_end: str
    scenarios: dict[str, Scenario]
    notes: dict[str, str]
    sensitivity_case: str = "Base"
    reference: ReferencePrice | None = None
    notes_origin: str = "Illustrative research prompts"


def default_scenario(company: dict, base, case: str) -> Scenario:
    growth, margin, pe, rationale = company["scenario_defaults"][case]
    return Scenario(growth, margin, float(base["weighted_shares"]), pe, rationale)


def default_workspace(code: str, company: dict, history) -> Workspace:
    eligible = usable_bases(history)
    base = eligible.iloc[-1]
    return Workspace(
        code,
        base["end"],
        {case: default_scenario(company, base, case) for case in SCENARIO_NAMES},
        dict(company["research_prompts"]),
    )


def usable_bases(history):
    """Eligible model bases require a revenue input and shares to seed the editable assumption."""
    return history.loc[history["revenue"].notna() & history["weighted_shares"].gt(0)]


def reset_scenario(workspace: Workspace, company: dict, base, case: str) -> Workspace:
    scenarios = {**workspace.scenarios, case: default_scenario(company, base, case)}
    return replace(workspace, scenarios=scenarios)


def save_workspace(workspace: Workspace, share_basis: str) -> bytes:
    payload = {"version": VERSION, "share_basis": share_basis, **asdict(workspace)}
    if workspace.reference:
        payload["reference"]["as_of"] = workspace.reference.as_of.isoformat()
    return (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def _is_dict(value, keys) -> bool:
    return isinstance(value, dict) and set(value) == set(keys)


def load_workspace(raw: bytes, code: str, allowed_ends: list[str], share_basis: str) -> Workspace:
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("Research JSON exceeds 100 KB.")
    try:
        payload = json.loads(raw)
        keys = (
            "version",
            "share_basis",
            "company",
            "base_end",
            "scenarios",
            "notes",
            "sensitivity_case",
            "reference",
            "notes_origin",
        )
        if (
            not _is_dict(payload, keys)
            or type(payload["version"]) is not int
            or payload["version"] != VERSION
        ):
            raise ValueError("Unsupported research file format or version.")
        if payload["company"] != code:
            raise ValueError("This research file belongs to a different company.")
        if payload["share_basis"] != share_basis:
            raise ValueError("The file uses a different split basis. Review the shares and price.")
        if payload["base_end"] not in allowed_ends:
            raise ValueError("The saved base fiscal year is unavailable.")
        if (
            not _is_dict(payload["scenarios"], SCENARIO_NAMES)
            or payload["sensitivity_case"] not in SCENARIO_NAMES
        ):
            raise ValueError("The file must contain Bear, Base, and Bull scenarios.")
        notes = payload["notes"]
        if not _is_dict(notes, NOTES) or any(
            not isinstance(value, str) or len(value) > 3500 for value in notes.values()
        ):
            raise ValueError(
                "Research notes must contain the five text sections (up to 3,500 characters each)."
            )
        if payload["notes_origin"] not in (
            "Illustrative research prompts",
            "Edited research notes",
        ):
            raise ValueError("Unknown research note type.")
        scenarios = {name: Scenario(**payload["scenarios"][name]) for name in SCENARIO_NAMES}
        reference = payload["reference"]
        if reference is not None:
            reference = ReferencePrice(
                **{**reference, "as_of": date.fromisoformat(reference["as_of"])}
            )
            if reference.share_basis != share_basis or not isfinite(reference.price):
                raise ValueError("The reference price has an incompatible share basis.")
    except (TypeError, KeyError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("Invalid research JSON structure.") from exc
    return Workspace(
        code,
        payload["base_end"],
        scenarios,
        notes,
        payload["sensitivity_case"],
        reference,
        payload["notes_origin"],
    )
