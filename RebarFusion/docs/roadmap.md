# Roadmap

The project's north star. One line per phase; details live in `docs/audits/` and `docs/README.md`. Update this document whenever a phase changes state.

```
✓ Phase 1     Project Manager (drawing discovery, identity, duplicates)
✓ Phase 2     Geometry Translation (DXF import)
✓ Phase 3     Canonicalization
✓ Phase 4     Spatial Index
✓ Phase 5     Canonical Nodes
✓ Phase 6     Connectivity Graph / Topology
✓ Phase 7     Shape Recognition (+7.5 accuracy, 7.6 plausibility, 7.7 fragments)
✓ Phase 8     Engineering Association (annotations -> geometry)
✓ Phase 9     Engineering Families (+9.1-9.4 provenance/spacing/confidence)
✓ Phase 10    Physical Reconstruction (geometry recovery, tube sweep, meshes)
✓ Phase 11    Engineering Viewer (11.0 audit, 11.1 pipeline modernization)
✓ Phase 12    Physical Identity Resolution
                12.1 Observation Builder
                12.2 Hypothesis Generator
                12.3 Evidence Engine
                12.4 Identity Resolver
✓ Phase 13.0  DWG Ingestion (ODA converter, one parser)
✓ Phase 13.1  Validation Corpus & Benchmark Framework

────────────────────────────────────────────────────────

CURRENT

→ Phase 13.2  Engineering Validation Dataset
              Collect and engineer-label 10-20 real precast packages
              into benchmark/corpus/. No new inference code until the
              corpus produces statistically meaningful metrics.
              Progress gate: corpus statistics in the benchmark report
              (projects / bars / engineer hours).

────────────────────────────────────────────────────────

FUTURE (do not start early; each gates on the one before)

Phase 14      Engineering Semantics
              Top/bottom reinforcement, curtailment, development length,
              lap splice, starter/anchor/distribution bars, panel/beam/
              column ownership, termination, continuity, joints, casting
              sequence. Engineering concepts, not CAD concepts. Gated on
              Phase 13.2's corpus — every semantic rule must be validated
              against labeled data, not assumed.

Phase 15      Automatic Digital Twin
              Drawings -> ... -> Identity -> Semantics -> Digital Twin.
              Reconstruction consumes resolved, semantically-understood
              identities end to end.

Phase 16      Construction Intelligence
Phase 17      Design Verification
Phase 18      Bidirectional BIM
```

## Standing rules (apply to every future phase)

- Audit before build; freeze with determinism + regression tests before moving on.
- Never fabricate engineering data; absence of information is a reportable fact.
- One responsibility per phase/subphase; identity before geometry; evidence before decisions.
- Every assumption goes through `docs/engineering_assumptions.md` with evidence and an enforcement point.
- Every improvement after Phase 13.1 must move a benchmark number, measured on the corpus — anecdotal success on one project no longer counts.
