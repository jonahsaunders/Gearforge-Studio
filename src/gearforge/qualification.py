"""Explicit boundary between design screening and a verified production rating.

No production rating method is implemented in this release. Free-form profile
notes, supplier catalog numbers, CAD checks and passing screens cannot grant one.
"""
from __future__ import annotations

from . import __version__
from .models import Candidate, PrintProfile, Requirements


def production_assessment(candidate: Candidate, requirements: Requirements, profile: PrintProfile) -> dict:
    blockers = [
        {"id": "rating_method", "detail": "No independently verified fatigue/contact load-rating method is implemented for this design."},
        {"id": "duty_and_environment", "detail": "A reviewed load spectrum, starts/reversals, reliability target, lubrication and operating temperatures are required."},
        {"id": "material_allowables", "detail": "Traceable material/process fatigue and contact allowables with applicable life and temperature limits are required."},
        {"id": "bearing_and_shaft_rating", "detail": "Bearings use generic assumed ratings; shaft fatigue, keyways and external loads are not fully rated."},
        {"id": "assembly_strength", "detail": "Housing, fastener, gear attachment, retention and mounting strength are not verified."},
        {"id": "thermal_and_wear", "detail": "Temperature, lubrication, wear and applicable creep/scuffing limits are not verified."},
        {"id": "manufacturing_definition", "detail": "Production tooth/root geometry, tolerances, fits, finishes and inspection drawings are not released."},
        {"id": "validation_and_release", "detail": "Independent reference cases, applicable physical qualification and accountable engineering release are required."},
    ]
    if candidate.export_level == "concept":
        blockers.append({"id": "contact_geometry", "detail": "This family has no implemented manufacturing contact geometry."})
    else:
        blockers.append({"id": "full_cycle_contact", "detail": "Static checks and sampled poses do not verify continuous contact or the complete assembly cycle."})
    if candidate.family == "planetary":
        blockers.append({"id": "planetary_load_sharing", "detail": "Ring, planet pins, carrier stiffness and unequal planet load sharing are unverified."})
    if requirements.mode != "commercial":
        blockers.append({"id": "printed_material", "detail": "Printer/process/orientation/batch-specific fatigue, creep and wear evidence is required; a dimensional coupon is insufficient."})
    return {
        "schema_version": 1,
        "app_version": __version__,
        "candidate_id": candidate.id,
        "family": candidate.family,
        "status": "not_qualified",
        "production_approved": False,
        "rated_output_torque_nm": None,
        "rated_life_hours": None,
        "motor_capability_output_nm": candidate.available_output_nm,
        "requested_output_torque_nm": requirements.output_torque_nm,
        "requested_life_hours": requirements.life_hours,
        "profile_notes_present": bool(profile.test_evidence.strip()),
        "profile_notes_are_verified_material_data": False,
        "blockers": blockers,
        "meaning": "Motor capability and passing preliminary checks are not a gearbox service-load rating.",
    }


def require_production_rating(candidate: Candidate, requirements: Requirements, profile: PrintProfile):
    assessment = production_assessment(candidate, requirements, profile)
    if not assessment["production_approved"]:
        raise ValueError("Production export blocked: no verified gearbox load rating is available. "
                         "Run qualify to record the missing engineering evidence.")
