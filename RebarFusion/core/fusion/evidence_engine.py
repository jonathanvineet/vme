"""
core/fusion/evidence_engine.py — Phase 12.3: Evidence Engine.

Turns Phase 12.2's qualitative evidence into structured, explainable
scores. Nothing here accepts, rejects, reviews, or merges anything --
every ScoredHypothesis this module produces stays status=PENDING. Its
only job is: (1) assign each Evidence item a confidence, wherever that
confidence can be derived from a real number an earlier phase already
computed, and (2) roll those per-item confidences up into a per-category
EvidenceScore (reusing Phase 9.4's ConfidenceBreakdown philosophy:
geometric mean across categories, weakest category always traceable).

Only candidate pairs Phase 12.2 already qualified are scored here --
Phase 12.3 quantifies 12.2's candidates, it does not re-decide who counts
as one (a non-candidate pair like N4-vs-N6 stays visible in the source
IdentityHypothesis.evidence for audit purposes, just never gets a
ScoredCandidate, since there is nothing for 12.4 to decide about it).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from core.fusion.models import (
    ASPECT_MARK,
    EVIDENCE_CATEGORY_ENGINEERING_CONTEXT, EVIDENCE_CATEGORY_FACT,
    EVIDENCE_CATEGORY_ROLE, EVIDENCE_CATEGORY_SPATIAL,
    POLARITY_CONTRADICTS, POLARITY_SUPPORTS,
    Evidence, EvidenceScore, IdentityHypothesis, PhysicalObservation,
    ScoredCandidate, ScoredHypothesis,
)

# Categories a real EvidenceScore can be computed for today -- must match
# the categories core/fusion/hypothesis_generator.py actually emits with a
# supports/contradicts polarity. SPATIAL is deliberately excluded: its
# evidence is polarity=UNKNOWN (no calibrated distance threshold exists
# yet), so it never contributes to category_scores/overall -- it stays
# visible per-pair in `evidence`, just not folded into the score.
_SCORABLE_CATEGORIES = (
    EVIDENCE_CATEGORY_ENGINEERING_CONTEXT, EVIDENCE_CATEGORY_ROLE, EVIDENCE_CATEGORY_FACT,
)


def _with_confidence(evidence: Evidence, observations: Dict, ) -> Evidence:
    """Assign confidence only where it's a real number already computed by
    an earlier phase -- never invented. same_mark/fact_agreement/
    fact_conflict: geometric mean of the two contributing facts' own
    confidences (Phase 12.1). complementary_role: geometric mean of the
    two DrawingRole confidences (also Phase 12.1). spatial_distance: left
    None -- no calibrated model exists (see hypothesis_generator.py)."""
    if evidence.confidence is not None:
        return evidence

    a = observations[evidence.observation_a]
    b = observations[evidence.observation_b]
    confidence: Optional[float] = None

    if evidence.rule == "same_mark":
        fa, fb = a.fact(ASPECT_MARK), b.fact(ASPECT_MARK)
        confidence = (fa.confidence * fb.confidence) ** 0.5
    elif evidence.rule == "complementary_role":
        confidence = (a.drawing_role.confidence * b.drawing_role.confidence) ** 0.5
    elif evidence.rule in ("fact_agreement", "fact_conflict"):
        # Which aspect this evidence is about isn't stored on Evidence
        # itself (it's in the description text) -- recover it by finding
        # the shared aspect both observations agree/disagree on. Safe
        # because _pair_evidence emits exactly one fact_agreement/
        # fact_conflict entry per shared aspect.
        for aspect in {f.aspect for f in a.facts} & {f.aspect for f in b.facts}:
            fa, fb = a.fact(aspect), b.fact(aspect)
            matches = (fa.value == fb.value) == (evidence.rule == "fact_agreement")
            if matches and aspect in evidence.description:
                confidence = (fa.confidence * fb.confidence) ** 0.5
                break

    return Evidence(
        uuid=evidence.uuid, category=evidence.category, polarity=evidence.polarity,
        rule=evidence.rule, description=evidence.description,
        observation_a=evidence.observation_a, observation_b=evidence.observation_b,
        confidence=confidence,
    )


def _score_pair(evidence: List[Evidence]) -> EvidenceScore:
    by_category: Dict[str, List[Evidence]] = {}
    for e in evidence:
        by_category.setdefault(e.category, []).append(e)

    category_scores: Dict[str, float] = {}
    unscored: List[str] = []
    for category in _SCORABLE_CATEGORIES:
        items = by_category.get(category, [])
        supports = sum(e.confidence or 1.0 for e in items if e.polarity == POLARITY_SUPPORTS)
        contradicts = sum(e.confidence or 1.0 for e in items if e.polarity == POLARITY_CONTRADICTS)
        if supports + contradicts == 0:
            unscored.append(category)
            continue
        category_scores[category] = round(supports / (supports + contradicts), 3)

    if not category_scores:
        return EvidenceScore(category_scores={}, overall=0.0, weakest_category=None, unscored_categories=unscored)

    product = 1.0
    for v in category_scores.values():
        product *= max(v, 1e-6)
    overall = round(product ** (1.0 / len(category_scores)), 3)
    weakest = min(category_scores, key=category_scores.get)

    return EvidenceScore(
        category_scores=category_scores, overall=overall,
        weakest_category=weakest, unscored_categories=unscored,
    )


def score_hypotheses(
    hypotheses: List[IdentityHypothesis], observations: List[PhysicalObservation]
) -> List[ScoredHypothesis]:
    """One ScoredHypothesis per input IdentityHypothesis, in the same
    order. Deterministic: no randomness, no dict-iteration-order
    dependence in the output (category_scores keys are a fixed tuple,
    scored_candidates follow candidate_observations' existing order)."""
    by_uuid = {o.uuid: o for o in observations}

    scored_hypotheses: List[ScoredHypothesis] = []
    for hyp in hypotheses:
        scored_candidates: List[ScoredCandidate] = []
        for candidate_uuid in hyp.candidate_observations:
            pair_evidence = [
                _with_confidence(e, by_uuid)
                for e in hyp.evidence
                if {e.observation_a, e.observation_b} == {hyp.anchor_observation, candidate_uuid}
            ]
            scored_candidates.append(ScoredCandidate(
                anchor_observation=hyp.anchor_observation,
                candidate_observation=candidate_uuid,
                is_candidate=True,
                evidence=pair_evidence,
                score=_score_pair(pair_evidence),
            ))

        scored_hypotheses.append(ScoredHypothesis(
            uuid=hyp.uuid, anchor_observation=hyp.anchor_observation,
            scored_candidates=scored_candidates, status=hyp.status,
        ))

    return scored_hypotheses
