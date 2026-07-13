# Benchmark Summary

## Corpus

- **projects**: 1
- **drawings_processed**: 8
- **observations**: 88
- **pair_decisions**: 1198
- **accepted_identities**: 1
- **ground_truth_identities**: 18
- **ground_truth_bars**: 7
- **engineer_hours**: 0.0
- **decision outcomes**: {"ACCEPTED": 1, "REJECTED": 1, "REVIEW": 1196}

## Per-project metrics

| Project | Precision | Recall | False merge | False split | Obs coverage | Eng coverage | Recon coverage |
|---|---|---|---|---|---|---|---|
| Apollo | 0.000 | 0.000 | 0.000 | 0.000 | 0.889 | 0.838 | 1.000 |

## Identity failures (explained)

### Apollo / PW-GF-09: all T8 reinforcement (5 functional groups, see notes) (gt-pw09-t8) — **missed**
- Expected: PW-GF-09(R).dwg::T8
- Resolved: 11 observation(s)
- Reason: observations resolved but no accepted identity contains any of them (pairs likely held at REVIEW/REJECTED -- see decisions)

### Apollo / PW-GF-09: T10 bars (gt-pw09-t10) — **missed**
- Expected: PW-GF-09(R).dwg::T10
- Resolved: 1 observation(s)
- Reason: observations resolved but no accepted identity contains any of them (pairs likely held at REVIEW/REJECTED -- see decisions)

### Apollo / PW-GF-09: T12 bars including 2-T12 Crack Bars (gt-pw09-t12) — **missed**
- Expected: PW-GF-09(R).dwg::T12
- Resolved: 11 observation(s)
- Reason: observations resolved but no accepted identity contains any of them (pairs likely held at REVIEW/REJECTED -- see decisions)

### Apollo / PW-GF-09: T16 edge bars (A17 — grouping UNRESOLVED) (gt-pw09-t16) — **partial**
- Expected: PW-GF-09(R).dwg::T16
- Resolved: 3 observation(s)
- Reason: partially recovered by identity 12dcc1cf-d9fb-51ef-84c8-a8060143ede3 (sets differ)

### Apollo / PW-GF-09: N7 dowel bars (16mm × 6) (gt-pw09-n7-dowel) — **unresolvable**
- Expected: PW-GF-09(M1).dwg::N7
- Resolved: 0 observation(s)
- Selector failure [mark_missing]: drawing 'PW-GF-09(M1).dwg' has observations but none marked 'N7' (marks present: ['N10'])
- Reason: no selector resolved to any pipeline observation -- see selector_failures; recall loss originates upstream of identity resolution

### Apollo / PW-GF-09: N8 dowel bars (16mm × 9) (gt-pw09-n8-dowel) — **unresolvable**
- Expected: PW-GF-09(M1).dwg::N8
- Resolved: 0 observation(s)
- Selector failure [mark_missing]: drawing 'PW-GF-09(M1).dwg' has observations but none marked 'N8' (marks present: ['N10'])
- Reason: no selector resolved to any pipeline observation -- see selector_failures; recall loss originates upstream of identity resolution

### Apollo / PW-GF-02: all T8 reinforcement (U-bars at 3 spacings + spaced bars, see notes) (gt-pw02-t8) — **missed**
- Expected: PW-GF-02(R).dwg::T8
- Resolved: 19 observation(s)
- Reason: observations resolved but no accepted identity contains any of them (pairs likely held at REVIEW/REJECTED -- see decisions)

### Apollo / PW-GF-02: 2-T10 bars (gt-pw02-t10) — **missed**
- Expected: PW-GF-02(R).dwg::T10
- Resolved: 3 observation(s)
- Reason: observations resolved but no accepted identity contains any of them (pairs likely held at REVIEW/REJECTED -- see decisions)

### Apollo / PW-GF-02: T12 bars (1-/2-/5-T12 groups) (gt-pw02-t12) — **missed**
- Expected: PW-GF-02(R).dwg::T12
- Resolved: 6 observation(s)
- Reason: observations resolved but no accepted identity contains any of them (pairs likely held at REVIEW/REJECTED -- see decisions)

### Apollo / PW-GF-02: T16 bars including 2-T16 CRACK BAR (gt-pw02-t16) — **missed**
- Expected: PW-GF-02(R).dwg::T16
- Resolved: 4 observation(s)
- Reason: observations resolved but no accepted identity contains any of them (pairs likely held at REVIEW/REJECTED -- see decisions)

### Apollo / PW-GF-02: 2-T20 bars (gt-pw02-t20) — **missed**
- Expected: PW-GF-02(R).dwg::T20
- Resolved: 3 observation(s)
- Reason: observations resolved but no accepted identity contains any of them (pairs likely held at REVIEW/REJECTED -- see decisions)

### Apollo / SS-GF-01: T8 bars (@150 and @200 groups) (gt-ss01-t8) — **missed**
- Expected: SS-GF-01(R).dwg::T8
- Resolved: 4 observation(s)
- Reason: observations resolved but no accepted identity contains any of them (pairs likely held at REVIEW/REJECTED -- see decisions)

### Apollo / SS-GF-01: T10 @125 bars (gt-ss01-t10) — **missed**
- Expected: SS-GF-01(R).dwg::T10
- Resolved: 1 observation(s)
- Reason: observations resolved but no accepted identity contains any of them (pairs likely held at REVIEW/REJECTED -- see decisions)

### Apollo / SS-GF-01: 2-T12 bars (gt-ss01-t12) — **missed**
- Expected: SS-GF-01(R).dwg::T12
- Resolved: 6 observation(s)
- Reason: observations resolved but no accepted identity contains any of them (pairs likely held at REVIEW/REJECTED -- see decisions)

### Apollo / SS-GF-01: 2-T20 bars (gt-ss01-t20) — **missed**
- Expected: SS-GF-01(R).dwg::T20
- Resolved: 7 observation(s)
- Reason: observations resolved but no accepted identity contains any of them (pairs likely held at REVIEW/REJECTED -- see decisions)

### Apollo / SS-GF-01: N6 upstand reference (diameter UNKNOWN) (gt-ss01-n6) — **missed**
- Expected: SS-GF-01(M).dxf::N6
- Resolved: 1 observation(s)
- Reason: observations resolved but no accepted identity contains any of them (pairs likely held at REVIEW/REJECTED -- see decisions)

### Apollo / SS-GF-01: N7 upstand reference (diameter UNKNOWN) (gt-ss01-n7) — **missed**
- Expected: SS-GF-01(M).dxf::N7
- Resolved: 1 observation(s)
- Reason: observations resolved but no accepted identity contains any of them (pairs likely held at REVIEW/REJECTED -- see decisions)

### Apollo / SS-GF-01: N4 reference (diameter UNKNOWN; geometry entangled with fragment cluster) (gt-ss01-n4) — **missed**
- Expected: SS-GF-01(M).dxf::N4
- Resolved: 1 observation(s)
- Reason: observations resolved but no accepted identity contains any of them (pairs likely held at REVIEW/REJECTED -- see decisions)

### Apollo / pipeline identity 12dcc1cf — **partial**
- Observations: 2
- Ground truth touched: ['gt-pw09-t16']
- Reason: overlaps ground truth gt-pw09-t16 but observation sets differ (pipeline 2 obs vs expected 3)
