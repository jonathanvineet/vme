# Audit — Phase 6: Connectivity Graph Builder

## Scope
`core/topology/builder.py` (`TopologyBuilder`), `core/topology/graph.py` (`GraphEdge`, `ConnectivityGraph`, `ConnectedComponent`). Exercised by `run_phase6.py` against Phase 5's node repository.

## Results

| Check | Result | Evidence |
|---|---|---|
| Graph built, metrics computed | PASS | `metrics.json`: `total_nodes: 2360, total_edges: 1755, average_degree: 1.487, connected_components: 651, largest_component: 98, smallest_component: 2, average_component_size: 3.49` |
| Gate condition ("READY FOR PHASE 7") | Reports PASS | gate is defined as `critical_errors == []`, which is true |
| Duplicate edges | **FAIL (silently ignored by gate)** | `validation.json` lists **19 distinct duplicate topological edges** (same node pair connected twice) as warnings, not errors |
| Orphan nodes | **FAIL (silently ignored by gate)** | `validation.json`: `"87 orphan nodes (degree 0) in graph"` — 3.7% of all 2360 nodes have no edges at all |
| Regression (metrics + component UUID stability) | PASS | `tests/regression.py` currently matches golden exactly: `total_nodes:2360, total_edges:1755, average_degree:1.4872881355932204, connected_components:651, largest_component:98, smallest_component:2, average_component_size:3.4915514592933947`; component UUID set has no missing entries vs golden |

## Connected components sanity check
651 connected components from 2360 nodes / 1755 edges, average component size 3.49, largest 98, smallest 2. For a rebar drawing, a large number of small components (avg ~3.5 nodes) is plausible — individual bar segments and short connector runs would each form their own small component — but 651 components is also consistent with **fragmentation that should have been consolidated** if the true engineering intent is fewer, larger connected assemblies. This can't be resolved by graph metrics alone; it needs to be checked against Phase 7 recognition output (does recognition correctly group these components into bars/stirrups despite the fragmentation, or does fragmentation cause mis-recognition?).

## Key finding
Phase 6 is the first phase in this audit where **the automated gate and the actual data quality diverge**. The regression suite is green and the script prints "READY FOR PHASE 7," but 87 nodes have zero connectivity and 19 edge pairs are duplicated. Neither is currently a hard failure. This matters because:
- An orphan node (degree 0) cannot belong to any bar/stirrup path — if any of those 87 nodes should have been connected to real geometry, Phase 7 will simply never see that connection, with no error raised anywhere.
- A duplicate edge between the same two nodes inflates `average_degree`/`total_edges` slightly and could, depending on how Phase 7 walks the graph, cause bar paths to be traversed or counted twice.

This aligns with the disconnect flagged in `audit_phase05.md`: Phase 5 reports "no orphan nodes" using a different definition than Phase 6's degree-0 check — the two phases disagree about the same 87 nodes.

## UPDATE — gate tightened and defects classified (see `audit_phase06_defect_classification.md`)

The validation gate (`core/topology/builder.py::_stage_6_7_validation`) has been rewritten from a flat critical/warning split into four tiers (`critical_errors`, `errors`, `warnings`, `info`), and `run_phase6.py` / `tests/regression.py` now fail the "READY FOR PHASE 7" gate on `errors` as well as `critical_errors`, not just critical.

Both defect classes were individually classified rather than blindly reclassified:

- **87 orphan nodes**: 87/87 are ARC-center or CIRCLE-center reference points that `TopologyBuilder` never uses as edge endpoints by design (arcs connect via start/end angle points; circles produce no edges at all). This is a validation-definition gap, not a topology bug — Phase 5's orphan check and Phase 6's degree-0 check were checking two different things. **Fixed**: the gate now excludes these from the error count and reports them as `info`; any orphan node that is *not* an arc/circle center (a genuine unconnected LINE/POLYLINE endpoint) is still a hard `error`. Current count of genuine unexpected orphans: **0**.
- **19 duplicate edges**: all traced to source-DXF provenance (handle + block name). 15 of 19 are explainable — 6 are coincident structural/annotation line pairs (e.g. a rebar line traced by a bend-mark detail line on a different layer), 9 are duplicate boundary geometry baked into one specific "Filled" symbol block definition, reproduced at every insertion. The remaining 4 (`A-FLOR` arc pairs, no block, sequential handles) are ambiguous and need a domain/drafting call rather than a pipeline fix. **Not yet downgraded** — still reported as `errors`, correctly holding the gate at NOT READY, pending that call. See classification doc for full detail.

## Verdict: **Orphan-node issue RESOLVED. Duplicate-edge issue CLASSIFIED, gate correctly still failing pending a domain decision.**
The original finding stands as the audit's key discovery: the gate was too permissive and let two real (if differently-severe) issues through silently. That gate is now fixed. Of the two issues, orphan nodes turned out to be a false alarm from a validation-definition mismatch (now corrected in code with zero remaining unexplained orphans). Duplicate edges turned out to be real, mostly-explainable overlapping source geometry — not a `TopologyBuilder` bug, but a genuine open question about 4 of 19 edge pairs that the gate now correctly continues to block on rather than silently pass.

## Recommendation
1. Done: gate now fails on `errors`, not just `critical_errors`; orphan-node false positives eliminated.
2. Open: get a domain/CAD-literate read on the 4 `A-FLOR` arc pairs (Group C in the classification doc). If confirmed intentional, encode that specific exception explicitly (e.g. by layer/pattern) rather than a blanket duplicate-edge allowance — do not silently reclassify without that confirmation.
3. Do not proceed to trust Phase 7+ output for the 4 still-unresolved duplicate-edge regions until Recommendation 2 is resolved. Everything else in Phase 6 is now clean.
