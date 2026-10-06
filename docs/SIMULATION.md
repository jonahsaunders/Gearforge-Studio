# Simulation methods and limits

The viewer integrates measured monotonic elapsed time and input RPM, independent
of frame rate. The initial assembly pose is preserved; rigid mesh transforms do
not rebuild or discard CAD. Playback scales (.001/.01/.1/1) control simulated
seconds per wall-clock second. Reverse changes input direction, pause retains
pose, seek applies the current speed from time zero, and Step tooth advances one
input-tooth pitch. There is no automatic playback. Reduce Motion disables play
and keeps seek and single stepping available.

External gears rotate oppositely; every downstream shaft uses the product of
its preceding reduction ratios. Coaxial gears on an intermediate shaft share
the same rotation. A fixed-ring planetary uses sun input and carrier output:
`(omega_sun - omega_carrier) * Nsun + (omega_ring - omega_carrier) * Nring = 0`.
Planet centers follow the carrier; absolute planet spin includes carrier motion
and counterrotation relative to it. The ring and housing stay fixed. Bearings
are stationary reference rings, not modeled rolling elements.

The operating sweep computes motor torque by linear interpolation within a
provided torque curve. No extrapolation is permitted. Without a curve it assumes
constant input torque over .25–2 times design speed (limited to 100,000 rpm).
For assumed efficiency eta and ratio R:

- `omega = rpm * 2*pi/60`
- `T_available_out = T_motor * R * eta`
- `P_in = T_motor * omega`; `P_out = eta * P_in`; `P_loss = P_in - P_out`
- `Load margin = T_available_out - requested_output_load`

These powers represent full modeled motor capability at each prescribed speed,
not power consumed by an arbitrary partial load. Overload means the prescribed
speed/load cannot be sustained under this model; it does not simulate stall or
deceleration. Stage mesh frequency and total tangential force are included in
JSON evidence. Planetary load sharing is not characterized. Off-design points do
not rerun every bearing, stress or temperature screen. Concepts use estimated
ratios/efficiencies, with no 3D tooth animation or intersection check.

The optional background mesh check builds real B-rep tooth solids and intersects
mating gear pairs at 12 evenly spaced poses over one input revolution. The
report includes pair volumes and phases with a 0.05 mm³ reporting threshold.
It does not cover a full assembly repeat cycle or continuously sweep contact;
unsampled interference is possible. It examines tooth pairs, not housing motion,
dynamic collisions, tooth compliance, contact pressure, lubrication, wear or
fatigue. Cancellation terminates the isolated worker. Results can be exported
along with the sweep. Every design export also includes sweep JSON and CSV.

Regression tests check elapsed-time/frame independence, direction, tooth-ratio
constraints, the Willis relation, orbit radius, motor interpolation, power
balance, overload, reduced motion, and preserved CAD meshes. Real sampled solid
evidence for three example families is in `mesh-sampling-evidence.json`.
