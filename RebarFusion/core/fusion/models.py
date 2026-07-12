"""
core/fusion/models.py — Phase 12.1: Physical Identity Discovery, data model.

This module defines ONLY what Phase 12.1 (Observation Builder) needs:
DrawingRole, ObservationFact, and PhysicalObservation. It deliberately
does NOT define ObservationEdge, Claim, or PhysicalIdentity -- those
belong to Phase 12.2 (Candidate/Hypothesis Generator), 12.3 (Evidence
Engine), and 12.4 (Identity Resolver) respectively, per
docs/research/phase12_cross_view_fusion_research.md.

Implementation Rule #1: this subphase produces observations only. No
identity graph, no candidate scoring, no geometry, no reconstruction.

Observation invariant (added on 12.1's revision, before 12.2 started):
an observation must never carry a fact for an aspect it did not directly
read off its source drawing's Phase 9 output. Absence of a fact means
"this observation doesn't know," not "the value is empty/zero." A plan
observation has no HOOK fact -- not a HOOK fact with value=None -- because
Phase 9's EngineeringFamily has no hook data to read for a mould-position
family. See docs/audits/phase12/12.1_observation_builder.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

# Matches AnnotationParser.DIA_PATTERN (core/recognition/annotations.py) --
# a mark is "self-decoding" if the SAME text that identifies it also
# encodes its diameter (T12 -> 12mm, no lookup needed). This is the exact
# pattern already used by Phase 8 to extract TOKEN_DIAMETER; reused here
# rather than reinvented, per the research report's Step 6 requirement
# that self-decoding vs. reference-code marks be a first-class distinction.
_SELF_DECODING_MARK = re.compile(r'^[ØTYHd]\s*\d{1,2}$', re.IGNORECASE)
# Matches AnnotationParser.MARK_PATTERN -- any mark of this shape that
# ISN'T self-decoding is a reference code (N7, etc.) whose meaning
# requires a lookup elsewhere in the drawing set (see research report
# Step 1: SS-GF-01(M)'s N4/N6/N7).
_GENERIC_MARK = re.compile(r'^[A-Z][0-9]{1,3}$')

# The aspect vocabulary an observation's facts can be about. Deliberately
# only the aspects Phase 9's EngineeringFamily can actually supply today
# (MARK/DIAMETER/SPACING/SHAPE/ORIENTATION/POSITION/LENGTH/QUANTITY).
# HOOK and LEVEL are named in the research report's cross-view model but
# are NOT listed here: Phase 9 output carries no hook or absolute-level
# data to read, and per the observation invariant above, an aspect with
# no real source must not be fabricated just because the design doc
# anticipated it. Add them here only when a real source for them exists
# (Phase 12.2+ ingesting detail-sheet/schedule data directly).
ASPECT_MARK = "mark"
ASPECT_DIAMETER = "diameter"
ASPECT_SPACING = "spacing"
ASPECT_SHAPE = "shape"
ASPECT_ORIENTATION = "orientation"
ASPECT_POSITION = "position"
ASPECT_LENGTH = "length"
ASPECT_QUANTITY = "quantity"


@dataclass
class DrawingRole:
    """What a drawing IS, classified from its identity.view string against
    the two conventions confirmed by direct evidence in the research
    report (PW-GF-09(R)/(M1)/(M2)): 'R' = reinforcement_typical (self-
    decoding T-marks), 'M'/'M1'/'M2'/... = mould_instance (position,
    levels, N-mark references). Anything else is honestly unclassified --
    this is new, narrow, evidence-based logic, not a guess dressed up as
    fact."""
    role: str            # 'reinforcement_typical' | 'mould_instance' | 'unclassified'
    confidence: float
    evidence: str


def classify_drawing_role(view: str) -> DrawingRole:
    v = (view or "").strip().upper()
    if v == "R":
        return DrawingRole(
            role="reinforcement_typical",
            confidence=0.9,
            evidence="view suffix 'R' matches the confirmed Reinforcement-drawing "
                     "convention (PW-GF-09(R): self-decoding T-marks, typical-for note)",
        )
    if re.match(r'^M\d*$', v):
        return DrawingRole(
            role="mould_instance",
            confidence=0.9,
            evidence=f"view suffix '{v}' matches the confirmed Mould-drawing "
                     f"convention (PW-GF-09(M1)/(M2): dimension chains, N-mark "
                     f"references, absolute levels)",
        )
    return DrawingRole(
        role="unclassified",
        confidence=0.0,
        evidence=f"view suffix '{v}' does not match any confirmed drawing-role convention",
    )


def classify_mark_namespace(mark: Optional[str]) -> str:
    """'self_decoding' (T12 -- diameter IS the mark) vs 'reference_code'
    (N7 -- diameter requires a lookup elsewhere) vs 'unknown'."""
    if not mark:
        return "unknown"
    m = mark.strip()
    if _SELF_DECODING_MARK.match(m):
        return "self_decoding"
    if _GENERIC_MARK.match(m):
        return "reference_code"
    return "unknown"


@dataclass
class ObservationFact:
    """One claim an observation makes about SOME physical object -- not a
    field on the object itself. 'This observation is capable of claiming
    diameter' and 'this observation claims diameter=16' are the same
    statement here: the fact's presence in an observation's `facts` list
    IS the claim. There is deliberately no separate capability/claims-set
    field alongside `facts` -- two representations of the same
    information (what this observation asserts) would only be able to
    drift out of sync with each other, the exact duplicated-logic failure
    mode core/full_pipeline.py's docstring already warns about for
    drawing-level pipeline duplication."""
    uuid: UUID
    aspect: str           # one of the ASPECT_* constants above
    value: Any
    confidence: float
    source: str           # e.g. "family_annotation" -- what KIND of thing this observation read from
    # The actual CAD entity this fact traces back to, when that's known --
    # e.g. the MTEXT/TEXT/DIMENSION entity a mark or diameter was read
    # from. Added now, ahead of when Phase 12.2+ will render it in a
    # viewer provenance chain, rather than bolted on later once callers
    # already assume it doesn't exist. Honestly None where the real
    # source entity isn't threaded through the pipeline yet -- see
    # docs/audits/phase12/12.2_hypothesis_generator.md for exactly which
    # aspects have it today and which don't, and why.
    source_entity_uuid: Optional[UUID] = None


@dataclass
class PhysicalObservation:
    """One drawing's already-frozen Phase 9 EngineeringFamily, recast as
    evidence about SOME physical object -- not yet claimed to belong to
    any resolved identity. `facts` carries only what this observation
    directly read off its family; nothing is inferred, and nothing is
    fabricated for an aspect the family didn't actually supply (the
    observation invariant, see module docstring)."""
    uuid: UUID
    drawing_filename: str
    drawing_number: str              # DrawingIdentity.drawing_number, e.g. "SS-GF-01"
    drawing_view: str                # raw DrawingIdentity.view, e.g. "M"
    drawing_role: DrawingRole
    family_uuid: UUID
    # Metadata about the OBSERVATION itself (what kind of source this is) --
    # distinct from `facts`, which are claims about the physical OBJECT the
    # observation describes. mark_namespace/family_type/bbox answer "what is
    # this observation," not "what does it assert about the bar."
    mark_namespace: str              # 'self_decoding' | 'reference_code' | 'unknown'
    family_type: str                 # family.family_type, e.g. "main_bar"
    bbox: Tuple[float, float, float, float]
    member_component_uuids: List[UUID] = field(default_factory=list)
    facts: List[ObservationFact] = field(default_factory=list)

    def fact(self, aspect: str) -> Optional[ObservationFact]:
        """Convenience lookup: does this observation claim `aspect`? This
        is exactly the 'which observations claim diameter?' query later
        subphases need -- a linear scan over a handful of facts, not a
        growing set of optional attributes to check one by one."""
        for f in self.facts:
            if f.aspect == aspect:
                return f
        return None


# --- Phase 12.2: Hypothesis Generator -----------------------------------
# Architectural Law #1 (research report Addendum 3): an observation records
# facts, it never infers them. Phase 12.2's job is the next, separate
# responsibility: propose which observations MIGHT describe the same
# physical object -- an investigation, not a decision. Nothing in 12.2
# scores, accepts, rejects, or merges anything; that's Phase 12.3
# (Evidence Engine, scoring only) and Phase 12.4 (Identity Resolver,
# the only place a decision gets made).

HYPOTHESIS_PENDING = "PENDING"
HYPOTHESIS_ACCEPTED = "ACCEPTED"
HYPOTHESIS_REJECTED = "REJECTED"
# Reserved for Phase 12.4, given the shape now for the same reason
# ObservationFact.source_entity_uuid was added ahead of a populated source:
# "enough evidence this might be the same bar, not enough to auto-merge."
# Phase 12.2/12.3 never set this -- every hypothesis/score they produce
# stays PENDING.
HYPOTHESIS_REVIEW = "REVIEW"

# Evidence category vocabulary. Only ENGINEERING_CONTEXT, ROLE, FACT, and
# SPATIAL have a real generator today (core/fusion/hypothesis_generator.py).
# DRAWING_CONTEXT/ANNOTATION/TOPOLOGY/SCHEDULE are named here because a
# future evidence source will plausibly produce them (e.g. an explicit
# per-pair "same drawing_number" entry, or real schedule-table parsing),
# but nothing emits them yet -- listed for the vocabulary to be complete
# and stable, not because they're populated. Same discipline as ASPECT_*
# omitting HOOK/LEVEL: name only what has a real source.
EVIDENCE_CATEGORY_DRAWING_CONTEXT = "drawing_context"
EVIDENCE_CATEGORY_ENGINEERING_CONTEXT = "engineering_context"
EVIDENCE_CATEGORY_ANNOTATION = "annotation"
EVIDENCE_CATEGORY_ROLE = "role"
EVIDENCE_CATEGORY_FACT = "fact"
EVIDENCE_CATEGORY_SPATIAL = "spatial"
EVIDENCE_CATEGORY_TOPOLOGY = "topology"
EVIDENCE_CATEGORY_SCHEDULE = "schedule"

POLARITY_SUPPORTS = "supports"
POLARITY_CONTRADICTS = "contradicts"
POLARITY_UNKNOWN = "unknown"


@dataclass
class Evidence:
    """One qualitative reason two observations might (or might not)
    describe the same physical object. `confidence` starts as None --
    Phase 12.2 (which assigns `category`/`polarity`, both categorical
    labels, not scores) never sets it; Phase 12.3 is the only place a
    number gets attached, and only when it can be derived from a real
    upstream confidence already computed by an earlier phase (a fact's
    own confidence, a DrawingRole's own confidence) rather than invented.
    A 'fact_conflict' entry (polarity=CONTRADICTS) is exactly as valid an
    entry here as a 'same_mark' entry (polarity=SUPPORTS): recording *why
    a pair might be wrong* matters as much as recording why it might be
    right, so 12.4 has something to explain a rejection with instead of a
    bare score. Renamed from HypothesisEvidence (Phase 12.2's original
    name) once it became clear Phase 12.3 needed to extend the same
    object rather than wrap it -- a shared type, not two representations
    of one thing."""
    uuid: UUID
    category: str           # one of the EVIDENCE_CATEGORY_* constants
    polarity: str            # 'supports' | 'contradicts' | 'unknown'
    rule: str                # e.g. 'same_mark' | 'complementary_role' | 'fact_agreement' |
                              # 'fact_conflict' | 'spatial_distance'
    description: str
    observation_a: UUID
    observation_b: UUID
    confidence: Optional[float] = None


@dataclass
class IdentityHypothesis:
    """One observation's candidate group -- an investigation, not an
    identity. `status` starts and stays PENDING throughout Phase 12.2;
    ACCEPTED/REJECTED only happen in Phase 12.3+. Kept explicit (not
    inferred from candidate_observations being empty) so a viewer can
    later show 'considered and rejected' distinctly from 'never
    considered' -- the explainability requirement from the research
    report's candidate-generation acceptance criterion."""
    uuid: UUID
    anchor_observation: UUID
    candidate_observations: List[UUID] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    status: str = HYPOTHESIS_PENDING


# --- Phase 12.3: Evidence Engine ----------------------------------------
# Scoring only. Nothing below this line accepts, rejects, reviews, or
# merges anything -- that remains Phase 12.4's sole responsibility. A
# ScoredHypothesis is still an investigation, just a quantified one.

@dataclass
class EvidenceScore:
    """Explainable per-category breakdown, not one opaque number --
    reusing Phase 9.4's ConfidenceBreakdown philosophy (core/engineering/
    confidence.py): `overall` is the geometric mean of the category
    scores that actually have evidence, so one very weak category drags
    the whole score down rather than being averaged away, and a low
    `overall` can always be traced to `weakest_category`.
    `unscored_categories` is explicit, not just an absence -- a category
    with zero evidence is a different, honestly-reported state from a
    category that scored low."""
    category_scores: Dict[str, float] = field(default_factory=dict)
    overall: float = 0.0
    weakest_category: Optional[str] = None
    unscored_categories: List[str] = field(default_factory=list)


@dataclass
class ScoredCandidate:
    """One anchor/candidate pair, scored. `is_candidate` is carried over
    unchanged from Phase 12.2's qualification decision -- Phase 12.3 does
    not re-decide it, only quantifies the evidence behind it."""
    anchor_observation: UUID
    candidate_observation: UUID
    is_candidate: bool
    evidence: List[Evidence] = field(default_factory=list)
    score: EvidenceScore = field(default_factory=EvidenceScore)


@dataclass
class ScoredHypothesis:
    """Phase 12.3's output: the same hypothesis, with each of its
    candidate pairs quantified. `status` is inherited from the source
    IdentityHypothesis and is always PENDING here -- Phase 12.3 never
    promotes it."""
    uuid: UUID
    anchor_observation: UUID
    scored_candidates: List[ScoredCandidate] = field(default_factory=list)
    status: str = HYPOTHESIS_PENDING
