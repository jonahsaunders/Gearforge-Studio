"""Deterministic rigid-body kinematics and quasi-static operating points.

No inertia, transient impacts, temperature prediction or elastic contact solver
is implied. Gear efficiencies are the synthesis model's explicit assumptions.
"""
from __future__ import annotations

import math
from dataclasses import replace

from .models import Candidate, Requirements, PrintProfile, candidate_from_dict, finite

TAU = 2 * math.pi


def shaft_rates(c: Candidate, input_rpm: float) -> list[float]:
    """Signed rpm viewed from +Z; planetary uses fixed ring, sun input."""
    rpm = finite(input_rpm, "Simulation input rpm", -100000, 100000)
    if c.family == "planetary":
        return [rpm, rpm / c.ratio]
    rates = [rpm]
    for stage in c.stages:
        rates.append(-rates[-1] / stage.ratio)
    return rates


def part_motion(c: Candidate, name: str, shaft: int, center, input_angle: float):
    """Return absolute spin increment and XY displacement from the CAD pose."""
    if not math.isfinite(input_angle):
        raise ValueError("Input angle must be finite")
    if c.export_level == "concept":
        return 0., (0., 0.)
    if c.family == "planetary":
        carrier = input_angle / c.ratio
        if name == "ring":
            return 0., (0., 0.)
        if name.startswith("planet_"):
            x, y = center[0] - c.size_mm[0]/2, center[1] - c.size_mm[1]/2
            displacement = (x*math.cos(carrier)-y*math.sin(carrier)-x,
                            x*math.sin(carrier)+y*math.cos(carrier)-y)
            spin = carrier if name.endswith("_pin") else carrier - (input_angle-carrier)*c.stages[0].driver.teeth/c.stages[0].planet.teeth
            return spin, displacement
        if shaft >= 0:
            return input_angle if shaft == 0 else carrier, (0., 0.)
        return 0., (0., 0.)
    if shaft >= 0:
        return input_angle * (-1)**shaft / math.prod(s.ratio for s in c.stages[:shaft]), (0., 0.)
    return 0., (0., 0.)


class SimulationClock:
    """Integrate measured elapsed seconds, independently of rendering frequency."""
    def __init__(self, input_rpm=1200.):
        self.input_rpm = input_rpm
        self.speed_factor = 1.
        self.time_scale = .01
        self.time_s = 0.
        self.input_angle = 0.

    def advance(self, elapsed_s):
        dt = finite(elapsed_s, "Elapsed seconds", 0, 3600) * self.time_scale
        self.time_s += dt
        self.input_angle += TAU*self.input_rpm*self.speed_factor/60*dt

    def seek(self, time_s):
        self.time_s = finite(time_s, "Simulation time", 0, 3600)
        self.input_angle = TAU*self.input_rpm*self.speed_factor/60*self.time_s

    def step_angle(self, radians):
        rpm = self.input_rpm*self.speed_factor
        if rpm == 0:
            raise ValueError("Choose a nonzero speed before stepping")
        self.input_angle += radians
        self.time_s += abs(radians/(TAU*rpm/60))


def operating_point(c: Candidate, req: Requirements, input_rpm: float, load_nm: float | None = None):
    rpm = finite(input_rpm, "Operating speed", .1, 100000)
    load = req.output_torque_nm if load_nm is None else finite(load_nm, "Output load", 0, 100000)
    curve = sorted(req.motor_curve)
    if curve and not curve[0][0] <= rpm <= curve[-1][0]:
        return {"input_rpm": rpm, "status": "Outside motor curve", "output_rpm": rpm/c.ratio}
    torque = replace(req, input_rpm=rpm).available_torque
    omega = TAU*rpm/60
    available = torque*c.ratio*c.efficiency
    input_power = torque*omega
    stages = []
    stage_rpm, stage_torque = rpm, torque
    for i, stage in enumerate(c.stages):
        out_torque = stage_torque*stage.ratio*stage.efficiency
        stages.append({"stage": i+1, "input_rpm": stage_rpm, "input_torque_nm": stage_torque,
                       "output_torque_nm": out_torque,
                       "tangential_n": 2000*stage_torque/stage.driver.pitch_mm,
                       "mesh_hz": stage_rpm*stage.driver.teeth/60 if c.family != "planetary" else (rpm-rpm/c.ratio)*stage.driver.teeth/60})
        stage_torque, stage_rpm = out_torque, stage_rpm/stage.ratio
    return {"input_rpm": rpm, "output_rpm": rpm/c.ratio, "motor_torque_nm": torque,
            "available_output_nm": available, "requested_load_nm": load,
            "input_power_w": input_power, "output_power_w": input_power*c.efficiency,
            "loss_power_w": input_power*(1-c.efficiency), "load_margin_nm": available-load,
            "status": "Load met" if available >= load else "Overload", "stages": stages}


def operating_sweep(c: Candidate, req: Requirements, points=25):
    if not isinstance(points, int) or not 2 <= points <= 200:
        raise ValueError("Sweep requires 2–200 points")
    curve = sorted(req.motor_curve)
    lo, hi = (curve[0][0], curve[-1][0]) if curve else (max(.1,req.input_rpm*.25), min(100000., req.input_rpm*2))
    lo = max(.1, lo)
    return {"candidate_id": c.id, "method": "Quasi-static, constant stage efficiencies; no inertia or thermal solver. Motor torque is interpolated only within supplied curve; otherwise constant torque is assumed.",
            "points": [operating_point(c, req, lo+(hi-lo)*i/(points-1)) for i in range(points)]}


def sampled_mesh_check(candidate: dict, requirements: dict, profile: dict, samples=12):
    """Exact B-rep gear-pair intersections at discrete input phases.

    The sampled interval is one input revolution, not a complete assembly repeat
    cycle. Does not validate continuous contact, fits, clearances or load sharing.
    """
    from .geometry import build_parts
    if not isinstance(samples, int) or not 3 <= samples <= 48:
        raise ValueError("Choose 3–48 mesh samples")
    c = candidate_from_dict(candidate)
    if c.export_level == "concept":
        raise ValueError("Detailed teeth are required for a sampled mesh check")
    req, p = Requirements(**requirements), PrintProfile(**profile)
    req.validate(); p.validate()
    parts = {part.name: part for part in build_parts(c, req, p) if part.name in {item["name"] for item in c.layout}}
    pairs = []
    for stage in range(len(c.stages)):
        layout = [item for item in c.layout if item["stage"] == stage]
        drivers = [item["name"] for item in layout if item["role"] == "driver"]
        driven = [item["name"] for item in layout if item["role"] == "driven"]
        planets = [item["name"] for item in layout if item["role"] == "planet"]
        pairs.extend([(drivers[0], n) for n in planets] + [(n, driven[0]) for n in planets] if planets else [(drivers[0], driven[0])])
    frames = []
    for i in range(samples):
        angle = TAU*i/samples
        shapes = {}
        for name, part in parts.items():
            spin, (dx,dy) = part_motion(c, name, part.shaft, part.center, angle)
            x,y,z = part.center
            shapes[name] = part.shape.val().rotate((x,y,z),(x,y,z+1),math.degrees(spin)).translate((dx,dy,0))
        overlaps = [{"a": a, "b": b, "overlap_mm3": round(shapes[a].intersect(shapes[b]).Volume(),6)} for a,b in pairs]
        frames.append({"input_degrees": 360*i/samples, "pairs": overlaps})
    maximum = max(row["overlap_mm3"] for f in frames for row in f["pairs"])
    return {"candidate_id": c.id, "samples": samples, "interval": "0 ≤ input angle < 360 degrees",
            "method": "Exact B-rep intersection at discrete poses. One input revolution only; not continuous contact or a complete assembly repeat cycle.",
            "tolerance_mm3": .05, "maximum_overlap_mm3": maximum,
            "status": "Interference detected" if maximum > .05 else "No interference at sampled poses", "frames": frames}
