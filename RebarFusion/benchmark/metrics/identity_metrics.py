"""
benchmark/metrics/identity_metrics.py — identity precision/recall and
false merge/split rates, with per-identity explanations.

Pure functions over already-loaded data; no pipeline access, no state.
Matching rule (v1, deliberately strict): a pipeline identity is "correct"
iff its observation set EXACTLY equals a ground-truth identity's resolved
observation set. Partial overlaps are counted as merge/split errors, not
partial credit — partial credit hides exactly the failures the corpus
exists to expose.

Undefined metrics stay None with an explanation string, never a
fabricated 0 or 1 (e.g. precision when zero identities were accepted).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from benchmark.loaders.project_loader import BenchmarkProject, resolve_selector


@dataclass
class GTIdentityOutcome:
    gt_uuid: str
    gt_name: str
    status: str                 # 'recovered' | 'split' | 'merged' | 'partial' | 'unresolvable' | 'missed'
    expected_observations: List[str] = field(default_factory=list)
    resolved_observations: List[str] = field(default_factory=list)
    matched_pipeline_identities: List[str] = field(default_factory=list)
    selector_failures: List[Dict[str, Any]] = field(default_factory=list)
    reason: str = ""


@dataclass
class PipelineIdentityOutcome:
    identity_uuid: str
    status: str                 # 'correct' | 'false_merge' | 'partial' | 'unmatched'
    observations: List[str] = field(default_factory=list)
    gt_identities_touched: List[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class IdentityMetrics:
    precision: Optional[float]
    precision_note: str
    recall: Optional[float]
    recall_note: str
    false_merge_rate: Optional[float]
    false_split_rate: Optional[float]
    gt_total: int
    accepted_total: int
    gt_outcomes: List[GTIdentityOutcome] = field(default_factory=list)
    pipeline_outcomes: List[PipelineIdentityOutcome] = field(default_factory=list)


def compute_identity_metrics(project: BenchmarkProject) -> IdentityMetrics:
    # Resolve every GT identity's selectors to concrete observation sets
    gt_sets: Dict[str, set] = {}
    gt_outcomes: List[GTIdentityOutcome] = []
    for gt in project.gt_identities:
        resolutions = [resolve_selector(s, project.observations) for s in gt.observations]
        resolved = {str(u) for r in resolutions for u in r.observation_uuids}
        failures = [
            {"selector": r.selector, "status": r.status, "reason": r.reason}
            for r in resolutions if r.status != "resolved"
        ]
        gt_sets[gt.uuid] = resolved
        gt_outcomes.append(GTIdentityOutcome(
            gt_uuid=gt.uuid, gt_name=gt.name,
            expected_observations=[f"{s.get('drawing')}::{s.get('mark')}" for s in gt.observations],
            resolved_observations=sorted(resolved),
            selector_failures=failures,
            status="pending", reason="",
        ))

    # Map observation -> owning GT identity (for merge detection)
    obs_to_gt: Dict[str, str] = {}
    for gt_uuid, obs_set in gt_sets.items():
        for obs in obs_set:
            obs_to_gt[obs] = gt_uuid

    pipeline_sets = {str(i.uuid): {str(o) for o in i.observations} for i in project.identities}

    # Classify each accepted pipeline identity
    pipeline_outcomes: List[PipelineIdentityOutcome] = []
    correct_pipeline: set = set()
    false_merges: set = set()
    for pid, pset in sorted(pipeline_sets.items()):
        touched = sorted({obs_to_gt[o] for o in pset if o in obs_to_gt})
        if len(touched) >= 2:
            status, reason = "false_merge", (
                f"observations span {len(touched)} distinct ground-truth bars: {touched}"
            )
            false_merges.add(pid)
        elif len(touched) == 1 and pset == gt_sets[touched[0]]:
            status, reason = "correct", f"exactly matches ground truth {touched[0]}"
            correct_pipeline.add(pid)
        elif len(touched) == 1:
            status, reason = "partial", (
                f"overlaps ground truth {touched[0]} but observation sets differ "
                f"(pipeline {len(pset)} obs vs expected {len(gt_sets[touched[0]])})"
            )
        else:
            status, reason = "unmatched", "no observation belongs to any labeled ground-truth bar"
        pipeline_outcomes.append(PipelineIdentityOutcome(
            identity_uuid=pid, status=status, observations=sorted(pset),
            gt_identities_touched=touched, reason=reason,
        ))

    # Classify each GT identity
    recovered = 0
    splits = 0
    for outcome in gt_outcomes:
        expected = gt_sets[outcome.gt_uuid]
        if not expected:
            outcome.status = "unresolvable"
            outcome.reason = (
                "no selector resolved to any pipeline observation -- see selector_failures; "
                "recall loss originates upstream of identity resolution"
            )
            continue
        containing = sorted(pid for pid, pset in pipeline_sets.items() if pset & expected)
        outcome.matched_pipeline_identities = containing
        if len(containing) == 0:
            outcome.status = "missed"
            outcome.reason = (
                "observations resolved but no accepted identity contains any of them "
                "(pairs likely held at REVIEW/REJECTED -- see decisions)"
            )
        elif len(containing) >= 2:
            outcome.status = "split"
            outcome.reason = f"observations scattered across {len(containing)} accepted identities"
            splits += 1
        elif pipeline_sets[containing[0]] == expected:
            outcome.status = "recovered"
            outcome.reason = f"exactly recovered as pipeline identity {containing[0]}"
            recovered += 1
        elif containing[0] in false_merges:
            outcome.status = "merged"
            outcome.reason = f"absorbed into false-merge identity {containing[0]}"
        else:
            outcome.status = "partial"
            outcome.reason = f"partially recovered by identity {containing[0]} (sets differ)"

    accepted_total = len(pipeline_sets)
    gt_total = len(gt_sets)

    precision = precision_note = None
    if accepted_total:
        precision = round(len(correct_pipeline) / accepted_total, 3)
        precision_note = f"{len(correct_pipeline)}/{accepted_total} accepted identities exactly match ground truth"
    else:
        precision_note = "undefined: zero identities were accepted (nothing to be precise about)"

    recall = recall_note = None
    if gt_total:
        recall = round(recovered / gt_total, 3)
        recall_note = f"{recovered}/{gt_total} ground-truth bars exactly recovered"
    else:
        recall_note = "undefined: project has no ground-truth identities"

    return IdentityMetrics(
        precision=precision, precision_note=precision_note,
        recall=recall, recall_note=recall_note,
        false_merge_rate=round(len(false_merges) / accepted_total, 3) if accepted_total else None,
        false_split_rate=round(splits / gt_total, 3) if gt_total else None,
        gt_total=gt_total, accepted_total=accepted_total,
        gt_outcomes=gt_outcomes, pipeline_outcomes=pipeline_outcomes,
    )
