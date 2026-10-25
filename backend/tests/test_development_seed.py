"""Seed field comparison stays idempotent and reports conflicts."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "seed_development_projects.py"
spec = importlib.util.spec_from_file_location("seed_development_projects", SCRIPT)
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


def _field(key: str, label: str, position: int) -> dict:
    return {
        "field_key": key,
        "label": label,
        "field_type": "text",
        "required": True,
        "section_name": "Record",
        "position": position,
    }


def test_second_plan_creates_nothing():
    desired = ["preschool-01", "paneerwala-01"]
    first = seed.plan_actions(set(), desired)
    second = seed.plan_actions(set(first["create"]), desired)
    assert second["create"] == []
    assert second["reuse"] == desired


def test_matching_fields_are_reused_and_conflicts_stop():
    desired = [
        {
            "field_key": "contact_record_name",
            "label": "Contact / Record Name",
            "field_type": "text",
            "required": True,
            "section_name": "Record",
        }
    ]
    existing = [_field("contact_record_name", "Contact / Record Name", 1)]
    assert seed.compare_fields(existing, desired) == "match"
    assert seed.compare_fields([], desired) == "prefix"
    conflict = [_field("contact_record_name", "Different", 1)]
    assert seed.compare_fields(conflict, desired) == "conflict"


def test_values_match_numbers_without_accepting_a_different_record():
    desired = {"expected_value": 250000, "notes": "seed:preschool-01"}
    assert seed.values_match({"expected_value": 250000.0, "notes": "seed:preschool-01"}, desired)
    assert not seed.values_match({"expected_value": 1, "notes": "seed:preschool-01"}, desired)
