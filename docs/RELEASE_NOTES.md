# GearForge Studio 1.0.0rc10

This release candidate adds explicit rack-generated spur tooth roots as the
geometry foundation for subsequent tooth-bending and manufacturing work.

- Declare cutter depth/corner radius, individual tooth-thickness reduction,
  source and redistribution basis. The gear pair retains profile shift and tip shortening.
- Generate the rounded-cutter envelope and tangent involute joins. Reject
  undercut/cusps/folds analytically and check the nominal active contact start.
- Inspect tooth/whole-gear views; save strict study files; export sampled
  DXF, SVG and CSV with complete JSON/HTML evidence and an integrity manifest.
- Compare 266 radii against independent numerical cutting across seven original
  cases. No restricted reference, cutter dataset or new runtime dependency is added.

See [tooth-profile methods and limits](TOOTH_PROFILES.md). `VALIDATION.json`
identifies current evidence; historical records do not qualify a new build.
Native archives are unsigned and need acceptance on company workstation images.

Final production gearbox design and service-load ratings remain unqualified.
Actual material/cutter evidence, tooth-root/transient fatigue, loss/cooling maps,
lubrication, tolerances and physical qualification remain. The earlier prototype
CAD is separate from this generated geometry; its tooth outline is unchanged.
