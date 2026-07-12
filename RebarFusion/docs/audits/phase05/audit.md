# Audit — Phase 5: Canonical Node Builder

## Scope
`core/topology/node_builder.py` (`build_nodes()`, `node_uuid()` — deterministic UUID5 from coordinates rounded to 5 decimals, matching the Phase 3 `EPSILON=1e-5` grid), `core/topology/nodes.py` (`CanonicalNode`, `CanonicalNodeRepository`). Exercised by `run_phase5.py`.

## Results

| Check | Result | Evidence |
|---|---|---|
| No duplicate nodes | PASS | `duplicates.json` = `[]` (empty) — a position-rounding sweep found zero collisions among 2360 nodes |
| No orphan nodes | Reported PASS by script's own logic at build time | but see Phase 6 finding below — **87 nodes end up with degree 0 by the time the connectivity graph is built** (`debug/phase06/.../validation.json`). This means Phase 5's orphan check (nodes with no `connected_entities` at node-build time) is not equivalent to "will have edges once the graph is built" — it's checking a different, weaker condition. Worth reconciling: are these 87 nodes genuinely isolated points in the drawing (e.g. stray endpoints), or is this a topology-builder bug that fails to connect nodes it should? |
| Stable UUIDs | Asserted by design (UUID5 is deterministic given identical input), **not empirically tested** | no test reads the same drawing twice and diffs node UUID sets |
| Complete connectivity | PASS (zero critical errors from `build_nodes()`) | `metrics.json`: `points_extracted: 3620, nodes_built: 2360, reduction_pct: 34.81` |

## Gap found
**No golden file, no regression coverage.** `tests/golden/SS-GF-01(M)/` has no `phase05/` directory, and `tests/regression.py` only uses Phase 5 output as a stepping stone toward the Phase 6 checks — it never independently verifies the node count, reduction percentage, or UUID set for Phase 5 itself. Of the six phases audited here, this is the **least protected**: no dedicated golden, no dedicated assertion, and its stated "no orphan nodes" claim is contradicted by what Phase 6 finds downstream.

## Verdict: **WEAK — passes its own checks, but those checks don't catch what Phase 6 later finds**
The 34.81% reduction (3620 points → 2360 nodes) is plausible for endpoint/intersection collapsing, and 0 duplicate nodes is a genuinely strong result. But the disconnect between "Phase 5 says no orphan nodes" and "Phase 6 finds 87 orphan nodes" means one of the two phases has an inaccurate orphan definition, or genuine isolated geometry exists in the drawing that both phases are technically reporting correctly under different definitions. This needs to be resolved, not just noted.

## Recommendation
1. Add a `tests/golden/SS-GF-01(M)/phase05/` fixture (node count, reduction_pct, node UUID set) with a regression check.
2. Reconcile Phase 5's "no orphan nodes" definition against Phase 6's degree-0 orphan count — they should either agree, or Phase 5's check should be renamed/removed since it doesn't predict Phase 6's actual connectivity outcome.
