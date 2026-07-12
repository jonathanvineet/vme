"""
Phase 7.6 — Physical Plausibility Engine.

A second, independent evidence layer on top of Phase 7 shape recognition.
Recognition answers "what shape is this" from topology alone (edge count,
node degree); this stage asks a different question — "could this reasonably
be a real piece of reinforcement, given the other bars recognized in this
drawing" — and never overwrites the recognizer's label or confidence. It
only attaches a plausibility decision (accept/review/reject) and evidence
that downstream phases can choose to act on.

Why not a fixed length cutoff (e.g. "reject anything under 50mm"): that
would encode one drawing's scale into the code and could reject genuinely
small reinforcement details (hooks, ties) on a different project. Instead,
thresholds are derived per recognition label from the drawing's own
observed length distribution using robust statistics (median + MAD, not
mean/stdev or quartiles) — MAD has a 50% breakdown point, which matters
here because on the audited drawing ~28% of bar-shape components were
sub-50mm fragments, a contamination level that would already distort a
quartile-based (IQR) estimate.

Two independent rules feed the decision, because neither alone is
sufficient:
  - MinimumLengthRule (modified z-score): catches an outlier relative to
    the label's own spread. Found to under-detect on the audited drawing —
    when the "normal" population itself spans a wide range (short ties up
    to multi-metre bars), MAD is large, so a near-zero fragment doesn't
    reach the z-score threshold even though it's obviously not a real bar
    (e.g. z=-1.29 for a 0.47mm 'straight_bar' against a 197mm median).
  - RelativeScaleRule (ratio to label median): a length under a small
    fraction of its label's median is implausible regardless of the
    population's absolute spread — a 0.47mm fragment is <1% of a 197mm
    median no matter how wide the rest of the distribution is. Still
    derived from the drawing's own median, not a fixed absolute number, so
    it generalizes across unit scales/vendors the same way the z-score
    rule does; the 5%/15% ratio thresholds are a reasonable convention,
    not a rigorously derived constant — flagged here for what it is.
"""

from dataclasses import dataclass, field
from typing import Dict, List
from uuid import UUID
import statistics

# Iglewicz & Hoaglin's modified z-score thresholds for outlier detection —
# a standard robust-statistics convention (see NIST/SEMATECH e-Handbook of
# Statistical Methods, outlier detection via modified z-score), not tuned to
# any one drawing.
MODIFIED_Z_REJECT_THRESHOLD = -3.5
MODIFIED_Z_REVIEW_THRESHOLD = -2.5

# Below this many same-label components in a drawing, there isn't enough
# data to build a reliable distribution — accept without judgement rather
# than guess from a handful of samples.
MIN_SAMPLE_SIZE_FOR_STATS = 5

# RelativeScaleRule thresholds: length as a fraction of the label's median.
RELATIVE_SCALE_REJECT_RATIO = 0.05
RELATIVE_SCALE_REVIEW_RATIO = 0.15


@dataclass
class PlausibilityEvidence:
    rule: str
    passed: bool
    detail: str


@dataclass
class PlausibilityResult:
    component_uuid: UUID
    label: str
    length: float
    median_for_label: float
    modified_z_score: float
    decision: str  # 'accept', 'review', 'reject'
    evidence: List[PlausibilityEvidence] = field(default_factory=list)


def _modified_z_scores(values: List[float]) -> List[float]:
    med = statistics.median(values)
    deviations = [abs(v - med) for v in values]
    mad = statistics.median(deviations)
    if mad == 0:
        # MAD degenerates when more than half the sample shares one value
        # (common for e.g. many identical straight-bar lengths); fall back
        # to mean absolute deviation so a genuine handful of tiny fragments
        # can still be distinguished from the bulk.
        mad = (statistics.mean(deviations) or 1e-9)
    return [0.6745 * (v - med) / mad for v in values]


def evaluate_plausibility(records: Dict[UUID, Dict]) -> Dict[UUID, PlausibilityResult]:
    """
    records: {component_uuid: {"label": str, "length": float}}
    Only components sharing a recognition label are compared against each
    other — a stirrup's typical length is not a straight bar's typical
    length, so pooling all labels together would wash out real outliers.
    """
    by_label: Dict[str, List[UUID]] = {}
    for cid, rec in records.items():
        by_label.setdefault(rec["label"], []).append(cid)

    results: Dict[UUID, PlausibilityResult] = {}
    for label, cids in by_label.items():
        lengths = [records[c]["length"] for c in cids]

        if len(cids) < MIN_SAMPLE_SIZE_FOR_STATS:
            for c in cids:
                results[c] = PlausibilityResult(
                    component_uuid=c, label=label, length=records[c]["length"],
                    median_for_label=statistics.median(lengths) if lengths else 0.0,
                    modified_z_score=0.0,
                    decision="accept",
                    evidence=[PlausibilityEvidence(
                        "sample_size", True,
                        f"Only {len(cids)} '{label}' component(s) in this drawing — "
                        f"too few to judge a distribution, accepted by default",
                    )],
                )
            continue

        med = statistics.median(lengths)
        z_scores = _modified_z_scores(lengths)
        for c, z in zip(cids, z_scores):
            length = records[c]["length"]
            ratio = (length / med) if med > 0 else 0.0

            z_decision = "reject" if z < MODIFIED_Z_REJECT_THRESHOLD else \
                ("review" if z < MODIFIED_Z_REVIEW_THRESHOLD else "accept")
            ratio_decision = "reject" if ratio < RELATIVE_SCALE_REJECT_RATIO else \
                ("review" if ratio < RELATIVE_SCALE_REVIEW_RATIO else "accept")

            # Combine: the stronger (more skeptical) of the two rules wins.
            severity = {"accept": 0, "review": 1, "reject": 2}
            decision = max([z_decision, ratio_decision], key=lambda d: severity[d])

            ev = [
                PlausibilityEvidence(
                    "length_outlier", z_decision == "accept",
                    f"length={length:.1f}mm vs '{label}' median={med:.1f}mm, modified z-score={z:.2f} -> {z_decision}",
                ),
                PlausibilityEvidence(
                    "relative_scale", ratio_decision == "accept",
                    f"length={length:.1f}mm is {ratio:.1%} of '{label}' median={med:.1f}mm -> {ratio_decision}",
                ),
            ]
            results[c] = PlausibilityResult(
                component_uuid=c, label=label, length=length,
                median_for_label=med, modified_z_score=z,
                decision=decision, evidence=ev,
            )

    return results
