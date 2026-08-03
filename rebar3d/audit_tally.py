#!/usr/bin/env python3
"""Independent tally auditor for rebar3d out/ directory.

Recomputes per-diameter weight directly from each panel JSON's `bars` list
(kg = d^2/162 * length_m, length = sum of consecutive 3D point distances)
and cross-checks it against:
  1. The matching printed *_schedule.txt / *_combined_schedule.txt file's
     "reconstructed" column (should be an EXACT match -- same formula, same
     source bars -- any drift means the printed report is stale).
  2. For R1/R2 (or R1..Rn) sibling groups, the union of siblings' bars vs
     the *_combined_schedule.txt.
  3. A z_src confidence breakdown per panel/diameter: LOW-confidence
     (plane-snap, default, section-weak, synthesized) vs HIGH-confidence
     (section, and everything else not in the low set) share of weight.
"""
import json
import math
import re
from collections import defaultdict
from pathlib import Path

OUT = Path("/Users/jonathan/elco/vme/rebar3d/out")

LOW_CONF = {"plane-snap", "default", "section-weak", "synthesized"}


def poly_len(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def bar_weight_kg(d, pts):
    return (poly_len(pts) / 1000.0) * d * d / 162.0


def load_bars(json_path):
    d = json.loads(json_path.read_text())
    return d.get("bars", [])


def per_diameter_weights(bars):
    w = defaultdict(float)
    for b in bars:
        w[b["d"]] += bar_weight_kg(b["d"], b["pts"])
    return w


def per_diameter_conf(bars):
    """Return {dia: (low_kg, high_kg)}"""
    conf = defaultdict(lambda: [0.0, 0.0])
    for b in bars:
        wt = bar_weight_kg(b["d"], b["pts"])
        z = b.get("z_src", "")
        if z in LOW_CONF:
            conf[b["d"]][0] += wt
        else:
            conf[b["d"]][1] += wt
    return conf


SCHED_LINE_RE = re.compile(
    r"^T(\d+)\s+([\d.]+)k\s+([\d.]+)k\s+([+\-][\d.]+)k\s+(\d+)%|extra|-\s*$"
)
SCHED_LINE_RE2 = re.compile(
    r"^T(?P<dia>\d+)\s+(?P<recon>[\d.]+)k\s+(?P<official>[\d.]+)k\s+(?P<gap>[+\-][\d.]+)k\s+(?P<pct>\d+%|extra|-)\s*$"
)


def parse_schedule_txt(path):
    """Parse a _schedule.txt / _combined_schedule.txt file.
    Returns {dia: (recon_kg, official_kg, pct_str)}"""
    result = {}
    total = None
    for line in path.read_text().splitlines():
        line = line.rstrip()
        m = SCHED_LINE_RE2.match(line)
        if m:
            result[int(m.group("dia"))] = (
                float(m.group("recon")), float(m.group("official")), m.group("pct")
            )
            continue
        if line.startswith("TOTAL"):
            parts = line.split()
            # TOTAL   436.49k    508.51k  -72.02k    86%
            try:
                recon = float(parts[1].rstrip("k"))
                official = float(parts[2].rstrip("k"))
                pct = parts[4]
                total = (recon, official, pct)
            except Exception:
                pass
    return result, total


def find_panel_jsons():
    """Return list of (panel_name, json_path), excluding sub-part files like
    -A/-B/-C and mould (M...) files which don't get their own schedule."""
    jsons = sorted(OUT.glob("*.json"))
    return jsons


def main():
    report_lines = []
    flags = []

    # ---- Part 1: single-sheet panels with their own _schedule.txt ----
    schedule_txts = sorted(OUT.glob("*_schedule.txt"))
    combined_txts = sorted(OUT.glob("*_combined_schedule.txt"))

    combined_bases = {p.stem.replace("_combined_schedule", "") for p in combined_txts}

    checked_json_stems = set()

    for sched_path in schedule_txts:
        panel_stem = sched_path.stem[: -len("_schedule")]
        json_path = OUT / f"{panel_stem}.json"
        if not json_path.exists():
            report_lines.append(f"[MISSING JSON] {panel_stem}: schedule.txt exists, no matching json")
            continue
        checked_json_stems.add(panel_stem)
        bars = load_bars(json_path)
        my_w = per_diameter_weights(bars)
        printed, total_row = parse_schedule_txt(sched_path)

        all_dias = sorted(set(my_w) | set(printed))
        for dia in all_dias:
            recomputed = my_w.get(dia, 0.0)
            if dia in printed:
                p_recon, p_official, p_pct = printed[dia]
            else:
                p_recon, p_official, p_pct = 0.0, None, None
            diff = recomputed - p_recon
            rel = abs(diff) / p_recon if p_recon > 1e-9 else (abs(diff) if diff else 0.0)
            status = "OK"
            if p_official is None:
                status = "MISSING_IN_SCHEDULE_TXT"
            elif abs(diff) > max(0.02, 0.005 * max(p_recon, recomputed)):
                status = "MISMATCH"
            row = (panel_stem, dia, recomputed, p_recon, p_official, p_pct, diff, status)
            if status != "OK":
                flags.append(("RECON_MISMATCH", row))
            report_lines.append(
                f"{panel_stem:30s} T{dia:<3d} mine={recomputed:9.3f}k printed={p_recon:9.3f}k "
                f"official={p_official if p_official is not None else '?':>9} pct={p_pct} "
                f"diff={diff:+8.3f}k [{status}]"
            )

    # ---- Part 2: combined R1/R2 groups ----
    for comb_path in combined_txts:
        base = comb_path.stem.replace("_combined_schedule", "")
        header = comb_path.read_text().splitlines()[0]
        # "Combined: PW-GF-30(R1), PW-GF-30(R2)"
        members = []
        m = re.search(r"Combined:\s*(.+)", header)
        if m:
            members = [x.strip() for x in m.group(1).split(",")]
        all_bars = []
        missing_members = []
        for mem in members:
            jp = OUT / f"{mem}.json"
            if jp.exists():
                all_bars.extend(load_bars(jp))
                checked_json_stems.add(mem)
            else:
                missing_members.append(mem)
        if missing_members:
            report_lines.append(f"[MISSING MEMBER JSON] {base}: {missing_members}")

        my_w = per_diameter_weights(all_bars)
        printed, total_row = parse_schedule_txt(comb_path)
        all_dias = sorted(set(my_w) | set(printed))
        for dia in all_dias:
            recomputed = my_w.get(dia, 0.0)
            if dia in printed:
                p_recon, p_official, p_pct = printed[dia]
            else:
                p_recon, p_official, p_pct = 0.0, None, None
            diff = recomputed - p_recon
            status = "OK"
            if p_official is None:
                status = "MISSING_IN_SCHEDULE_TXT"
            elif abs(diff) > max(0.02, 0.005 * max(p_recon, recomputed)):
                status = "MISMATCH"
            row = (base + " (combined)", dia, recomputed, p_recon, p_official, p_pct, diff, status)
            if status != "OK":
                flags.append(("RECON_MISMATCH", row))
            report_lines.append(
                f"{base+' (combined)':30s} T{dia:<3d} mine={recomputed:9.3f}k printed={p_recon:9.3f}k "
                f"official={p_official if p_official is not None else '?':>9} pct={p_pct} "
                f"diff={diff:+8.3f}k [{status}]"
            )
        # verify TOTAL row too
        if total_row:
            t_recon, t_official, t_pct = total_row
            mine_total = sum(my_w.values())
            if abs(mine_total - t_recon) > max(0.05, 0.005 * max(mine_total, t_recon)):
                flags.append(("TOTAL_MISMATCH", (base, mine_total, t_recon)))

    # ---- Part 3: confidence composition pass ----
    conf_flags = []
    for sched_path in schedule_txts:
        panel_stem = sched_path.stem[: -len("_schedule")]
        json_path = OUT / f"{panel_stem}.json"
        if not json_path.exists():
            continue
        bars = load_bars(json_path)
        conf = per_diameter_conf(bars)
        printed, _ = parse_schedule_txt(sched_path)
        for dia, (low, high) in conf.items():
            tot = low + high
            if tot <= 0:
                continue
            low_frac = low / tot
            pct = None
            if dia in printed:
                pct = printed[dia][2]
            if pct and pct not in ("extra", "-"):
                try:
                    pctval = int(pct.rstrip("%"))
                except Exception:
                    pctval = None
                if pctval is not None and 96 <= pctval <= 104 and low_frac >= 0.5:
                    conf_flags.append((panel_stem, dia, pctval, low_frac, tot))

    for comb_path in combined_txts:
        base = comb_path.stem.replace("_combined_schedule", "")
        header = comb_path.read_text().splitlines()[0]
        members = []
        m = re.search(r"Combined:\s*(.+)", header)
        if m:
            members = [x.strip() for x in m.group(1).split(",")]
        all_bars = []
        for mem in members:
            jp = OUT / f"{mem}.json"
            if jp.exists():
                all_bars.extend(load_bars(jp))
        conf = per_diameter_conf(all_bars)
        printed, _ = parse_schedule_txt(comb_path)
        for dia, (low, high) in conf.items():
            tot = low + high
            if tot <= 0:
                continue
            low_frac = low / tot
            pct = None
            if dia in printed:
                pct = printed[dia][2]
            if pct and pct not in ("extra", "-"):
                try:
                    pctval = int(pct.rstrip("%"))
                except Exception:
                    pctval = None
                if pctval is not None and 96 <= pctval <= 104 and low_frac >= 0.5:
                    conf_flags.append((base + " (combined)", dia, pctval, low_frac, tot))

    # ---- Output ----
    print("=" * 100)
    print("PART 1+2: per-diameter recompute vs printed schedule files")
    print("=" * 100)
    for l in report_lines:
        print(l)

    print()
    print("=" * 100)
    print(f"DISCREPANCY FLAGS ({len(flags)} found)")
    print("=" * 100)
    for kind, row in flags:
        print(kind, row)

    print()
    print("=" * 100)
    print(f"CONFIDENCE-COMPOSITION FLAGS: suspiciously-exact match built mostly from low-confidence bars ({len(conf_flags)})")
    print("=" * 100)
    for panel, dia, pctval, low_frac, tot in conf_flags:
        print(f"{panel:30s} T{dia:<3d} match={pctval}% low_conf_frac={low_frac:.0%} of {tot:.2f}k total")

    print()
    print("=" * 100)
    print("PW-GF-30 SPECIFIC CHECK (per instructions)")
    print("=" * 100)
    r1 = load_bars(OUT / "PW-GF-30(R1).json")
    r2 = load_bars(OUT / "PW-GF-30(R2).json")
    combined = per_diameter_weights(r1 + r2)
    for dia in sorted(combined):
        print(f"T{dia}: {combined[dia]:.2f}k  (R1 alone: {per_diameter_weights(r1).get(dia,0):.2f}k, "
              f"R2 alone: {per_diameter_weights(r2).get(dia,0):.2f}k)")


if __name__ == "__main__":
    main()
