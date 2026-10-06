from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

FAMILIES = ("spur", "helical", "planetary", "bevel", "worm", "cycloidal")
MODES = ("printed", "commercial", "hybrid")
MODULES = (0.8, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0)


def finite(value: Any, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return result


@dataclass
class PrintProfile:
    name: str = "PETG • uncharacterized"
    material: str = "PETG"
    allowable_mpa: float = 8.0
    modulus_mpa: float = 1600.0
    density_g_cm3: float = 1.27
    cost_per_kg: float = 25.0
    nozzle_mm: float = 0.4
    layer_mm: float = 0.2
    backlash_mm: float = 0.2
    bore_compensation_mm: float = 0.15
    shrink_percent: float = 0.0
    bearing_clearance_mm: float = 0.08
    max_temperature_c: float = 40.0
    test_evidence: str = ""
    orientation: str = "Gear flat; axis normal to build plate"

    def validate(self):
        ranges = {
            "allowable_mpa": (0.1, 1000), "modulus_mpa": (1, 300000),
            "density_g_cm3": (0.1, 25), "cost_per_kg": (0, 10000),
            "nozzle_mm": (0.1, 2), "layer_mm": (0.03, 1),
            "backlash_mm": (0.01, 2), "bore_compensation_mm": (-1, 2),
            "shrink_percent": (-3, 10), "bearing_clearance_mm": (-0.5, 1),
            "max_temperature_c": (-20, 200),
        }
        for k, bounds in ranges.items():
            setattr(self, k, finite(getattr(self, k), k, *bounds))
        if self.layer_mm > self.nozzle_mm:
            raise ValueError("Layer height must not exceed nozzle diameter")
        for key in ("name", "material", "test_evidence", "orientation"):
            if not isinstance(getattr(self, key), str) or len(getattr(self, key)) > 4000:
                raise ValueError(f"Invalid {key}")


@dataclass
class Requirements:
    input_rpm: float = 1200.0
    input_torque_nm: float = 0.08
    output_rpm: float = 100.0
    output_torque_nm: float = 0.65
    peak_factor: float = 1.5
    life_hours: float = 100.0
    safety_factor: float = 2.0
    max_x_mm: float = 250.0
    max_y_mm: float = 180.0
    max_z_mm: float = 110.0
    ratio_tolerance_percent: float = 2.0
    max_backlash_deg: float = 5.0
    ambient_c: float = 25.0
    mode: str = "hybrid"
    families: list[str] = field(default_factory=lambda: ["spur", "helical", "planetary"])
    max_stages: int = 2
    priority: str = "balanced"
    min_module_mm: float = 1.0
    max_module_mm: float = 3.0
    input_shaft_mm: float = 8.0
    output_shaft_mm: float = 10.0
    mounting: str = "foot"
    supplier: str = ""
    budget: float = 0.0
    currency: str = "USD"
    motor_curve: list[list[float]] = field(default_factory=list)

    @property
    def ratio(self):
        return self.input_rpm / self.output_rpm

    @property
    def available_torque(self):
        if not self.motor_curve:
            return self.input_torque_nm
        points = sorted(self.motor_curve)
        if not points[0][0] <= self.input_rpm <= points[-1][0]:
            raise ValueError("Operating speed is outside the supplied motor torque curve")
        for (n1, t1), (n2, t2) in zip(points, points[1:]):
            if n1 <= self.input_rpm <= n2:
                return t1 + (t2 - t1) * (self.input_rpm - n1) / (n2 - n1)
        return points[0][1]

    def validate(self):
        ranges = {
            "input_rpm": (0.1, 100000), "input_torque_nm": (0.0001, 100000),
            "output_rpm": (0.01, 100000), "output_torque_nm": (0.0001, 100000),
            "peak_factor": (1, 10), "life_hours": (0.1, 100000), "safety_factor": (1, 10),
            "max_x_mm": (20, 2000), "max_y_mm": (20, 2000), "max_z_mm": (20, 2000),
            "ratio_tolerance_percent": (0.01, 20), "max_backlash_deg": (0.01, 180),
            "ambient_c": (-20, 150), "min_module_mm": (0.8, 3), "max_module_mm": (0.8, 3),
            "input_shaft_mm": (3, 50), "output_shaft_mm": (3, 50), "budget": (0, 1e8),
        }
        for k, bounds in ranges.items():
            setattr(self, k, finite(getattr(self, k), k, *bounds))
        if not 1 < self.ratio <= 100:
            raise ValueError("This release supports reduction ratios greater than 1 and up to 100")
        if self.min_module_mm > self.max_module_mm:
            raise ValueError("Minimum module exceeds maximum module")
        if self.mode not in MODES or self.priority not in ("balanced", "size", "cost", "efficiency", "backlash"):
            raise ValueError("Unknown manufacturing mode or design priority")
        if not self.families or not isinstance(self.families, list) or any(f not in FAMILIES for f in self.families):
            raise ValueError("Select at least one supported gearbox family")
        if isinstance(self.max_stages, bool) or self.max_stages not in (1, 2):
            raise ValueError("Stage count must be 1 or 2")
        if self.mounting not in ("foot", "flange"):
            raise ValueError("Mounting must be foot or flange")
        if not isinstance(self.motor_curve, list) or len(self.motor_curve) > 200:
            raise ValueError("Invalid motor curve")
        normalized = []
        for p in self.motor_curve:
            if not isinstance(p, list) or len(p) != 2:
                raise ValueError("Motor curve rows must be [rpm, torque_Nm]")
            normalized.append([finite(p[0], "curve rpm", 0, 100000), finite(p[1], "curve torque", 0, 100000)])
        if normalized and (len(normalized) < 2 or len({p[0] for p in normalized}) != len(normalized)):
            raise ValueError("Motor curve needs at least two distinct speed samples")
        self.motor_curve = normalized
        for key in ("supplier", "currency"):
            if not isinstance(getattr(self, key), str) or len(getattr(self, key)) > 200:
                raise ValueError(f"Invalid {key}")
        _ = self.available_torque


@dataclass
class GearSpec:
    teeth: int
    module_mm: float
    width_mm: float
    bore_mm: float
    source: str = "print"
    sku: str = ""
    pressure_deg: float = 20.0
    helix_deg: float = 0.0
    hub_diameter_mm: float = 0.0
    hub_width_mm: float = 0.0
    bending_nm: float = 0.0
    contact_nm: float = 0.0
    price: float | None = None
    source_url: str = ""
    rating_conditions: str = ""
    material: str = ""
    internal: bool = False

    @property
    def pitch_mm(self):
        return self.teeth * self.module_mm / math.cos(math.radians(self.helix_deg))

    @property
    def outer_mm(self):
        return self.pitch_mm + (8 if self.internal else 2) * self.module_mm

    @property
    def length_mm(self):
        return self.width_mm + self.hub_width_mm


@dataclass
class Stage:
    driver: GearSpec
    driven: GearSpec
    ratio: float
    efficiency: float
    center_mm: float
    input_rpm: float = 0
    input_torque_nm: float = 0
    output_torque_nm: float = 0
    planet: GearSpec | None = None
    planet_count: int = 0


@dataclass
class Check:
    name: str
    status: str
    value: float | None
    limit: float | None
    unit: str
    detail: str


@dataclass
class Candidate:
    id: str
    family: str
    stages: list[Stage]
    ratio: float
    efficiency: float
    output_rpm: float
    available_output_nm: float
    size_mm: list[float]
    backlash_deg: float
    estimated_cost: float | None
    score: float = 0
    checks: list[Check] = field(default_factory=list)
    shafts: list[dict] = field(default_factory=list)
    layout: list[dict] = field(default_factory=list)
    bom: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    export_level: str = "prototype"
    pareto: bool = False

    @property
    def feasible(self):
        return not any(c.status == "fail" for c in self.checks)

    @property
    def label(self):
        return f"{self.family.title()} · {len(self.stages)} stage · {self.ratio:.3g}:1"


@dataclass
class SearchResult:
    candidates: list[Candidate]
    rejected: dict[str, int]
    evaluated: int
    elapsed_s: float
    explanations: list[str]


@dataclass
class Project:
    name: str = "Untitled gearbox"
    requirements: Requirements = field(default_factory=Requirements)
    profile: PrintProfile = field(default_factory=PrintProfile)
    notes: str = ""
    selected_id: str = ""
    # Design snapshots are compared against fresh calculations on load.
    design_snapshot: dict | None = None
    schema_version: int = 1

    def save(self, path: Path):
        self.requirements.validate()
        self.profile.validate()
        atomic_text(path, json.dumps(asdict(self), indent=2, allow_nan=False))

    @classmethod
    def load(cls, path: Path):
        if path.stat().st_size > 2_000_000:
            raise ValueError("Project exceeds the 2 MB size limit")
        data = json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda s: (_ for _ in ()).throw(ValueError("Non-finite JSON")))
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("Unsupported project schema")
        allowed = {f.name for f in fields(cls)}
        if set(data) - allowed:
            raise ValueError("Project contains unknown fields")
        req = Requirements(**data.pop("requirements"))
        profile = PrintProfile(**data.pop("profile"))
        req.validate()
        profile.validate()
        result = cls(requirements=req, profile=profile, **data)
        if not isinstance(result.name, str) or len(result.name) > 200:
            raise ValueError("Invalid project name")
        if not isinstance(result.notes, str) or len(result.notes) > 20000:
            raise ValueError("Invalid project notes")
        return result


def atomic_text(path: Path, content: str):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".gearforge-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def candidate_from_dict(data: dict) -> Candidate:
    data = dict(data)
    stages = []
    for raw in data.pop("stages"):
        raw = dict(raw)
        raw["driver"] = GearSpec(**raw["driver"])
        raw["driven"] = GearSpec(**raw["driven"])
        if raw.get("planet"):
            raw["planet"] = GearSpec(**raw["planet"])
        stages.append(Stage(**raw))
    data["checks"] = [Check(**c) for c in data["checks"]]
    return Candidate(stages=stages, **data)
