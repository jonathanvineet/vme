"""
benchmark/reports/report_builder.py — report.json, summary.md, report.html.

Deterministic by construction: no timestamps, no random ordering — every
collection is sorted before serialization, and json is dumped with
sort_keys=True, so identical pipeline output produces byte-identical
reports (regression-tested by tests/test_benchmark.py).
"""
from __future__ import annotations

import base64
import html
import json
import os
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List

from benchmark.loaders.project_loader import BenchmarkProject
from benchmark.metrics.identity_metrics import IdentityMetrics, compute_identity_metrics
from benchmark.metrics.coverage_metrics import CoverageMetrics, compute_coverage, corpus_statistics
from benchmark.visualization.error_gallery import render_error_image


def _plain(obj):
    if is_dataclass(obj):
        return {k: _plain(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    return obj


def evaluate_projects(projects: List[BenchmarkProject]) -> Dict[str, Any]:
    per_project = []
    for p in sorted(projects, key=lambda x: x.name):
        identity = compute_identity_metrics(p)
        coverage = compute_coverage(p)
        per_project.append({
            "project": p.name,
            "metadata": p.metadata,
            "identity_metrics": _plain(identity),
            "coverage_metrics": _plain(coverage),
        })
    return {
        "corpus_statistics": corpus_statistics(projects),
        "projects": per_project,
    }


def _fmt(value, note=""):
    if value is None:
        return f"n/a ({note})" if note else "n/a"
    return f"{value:.3f}"


def build_summary_md(report: Dict[str, Any]) -> str:
    lines = ["# Benchmark Summary", ""]
    stats = report["corpus_statistics"]
    lines += ["## Corpus", ""]
    for key in ("projects", "drawings_processed", "observations", "pair_decisions",
                "accepted_identities", "ground_truth_identities", "ground_truth_bars"):
        lines.append(f"- **{key}**: {stats[key]}")
    lines.append(f"- **decision outcomes**: {json.dumps(stats['decision_outcomes'], sort_keys=True)}")
    lines.append("")

    lines += ["## Per-project metrics", "",
              "| Project | Precision | Recall | False merge | False split | Obs coverage | Eng coverage | Recon coverage |",
              "|---|---|---|---|---|---|---|---|"]
    for p in report["projects"]:
        im, cm = p["identity_metrics"], p["coverage_metrics"]
        lines.append(
            f"| {p['project']} "
            f"| {_fmt(im['precision'], im['precision_note'])} "
            f"| {_fmt(im['recall'], im['recall_note'])} "
            f"| {_fmt(im['false_merge_rate'])} "
            f"| {_fmt(im['false_split_rate'])} "
            f"| {_fmt(cm['observation_coverage'])} "
            f"| {_fmt(cm['engineering_coverage'])} "
            f"| {_fmt(cm['reconstruction_coverage'], cm['reconstruction_note'])} |"
        )
    lines.append("")

    lines += ["## Identity failures (explained)", ""]
    any_failure = False
    for p in report["projects"]:
        for outcome in p["identity_metrics"]["gt_outcomes"]:
            if outcome["status"] in ("recovered",):
                continue
            any_failure = True
            lines.append(f"### {p['project']} / {outcome['gt_name']} ({outcome['gt_uuid']}) — **{outcome['status']}**")
            lines.append(f"- Expected: {', '.join(outcome['expected_observations']) or '(none)'}")
            lines.append(f"- Resolved: {len(outcome['resolved_observations'])} observation(s)")
            for f in outcome["selector_failures"]:
                lines.append(f"- Selector failure [{f['status']}]: {f['reason']}")
            lines.append(f"- Reason: {outcome['reason']}")
            lines.append("")
        for outcome in p["identity_metrics"]["pipeline_outcomes"]:
            if outcome["status"] == "correct":
                continue
            any_failure = True
            lines.append(f"### {p['project']} / pipeline identity {outcome['identity_uuid'][:8]} — **{outcome['status']}**")
            lines.append(f"- Observations: {len(outcome['observations'])}")
            lines.append(f"- Ground truth touched: {outcome['gt_identities_touched'] or '(none)'}")
            lines.append(f"- Reason: {outcome['reason']}")
            lines.append("")
    if not any_failure:
        lines.append("None — every ground-truth identity exactly recovered, every accepted identity correct.")
        lines.append("")
    return "\n".join(lines)


def _gallery_entries(projects: List[BenchmarkProject], report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One entry per identity error: title, explanation chain, optional PNG."""
    by_name = {p.name: p for p in projects}
    entries: List[Dict[str, Any]] = []
    for proj_report in report["projects"]:
        project = by_name[proj_report["project"]]
        obs_by_uuid = {str(o.uuid): o for o in project.observations}

        for outcome in proj_report["identity_metrics"]["gt_outcomes"]:
            if outcome["status"] == "recovered":
                continue
            groups = {"ground truth: " + outcome["gt_name"]:
                      [obs_by_uuid[u] for u in outcome["resolved_observations"] if u in obs_by_uuid]}
            for pid in outcome["matched_pipeline_identities"]:
                pset = next((i for i in project.identities if str(i.uuid) == pid), None)
                if pset:
                    groups[f"pipeline: {pid[:8]}"] = [
                        obs_by_uuid[str(u)] for u in pset.observations if str(u) in obs_by_uuid
                    ]
            image = render_error_image(
                f"{proj_report['project']}: {outcome['gt_name']} — {outcome['status']}",
                groups, note=outcome["reason"][:120],
            )
            entries.append({
                "kind": f"gt_{outcome['status']}",
                "title": f"{proj_report['project']} / {outcome['gt_name']}",
                "chain": {
                    "ground_truth": outcome["expected_observations"],
                    "pipeline": outcome["matched_pipeline_identities"],
                    "evidence": [f["reason"] for f in outcome["selector_failures"]],
                    "decision": outcome["status"],
                    "reason": outcome["reason"],
                },
                "png": image,
            })

        for outcome in proj_report["identity_metrics"]["pipeline_outcomes"]:
            if outcome["status"] in ("correct",):
                continue
            groups = {f"pipeline: {outcome['identity_uuid'][:8]}":
                      [obs_by_uuid[u] for u in outcome["observations"] if u in obs_by_uuid]}
            image = render_error_image(
                f"{proj_report['project']}: identity {outcome['identity_uuid'][:8]} — {outcome['status']}",
                groups, note=outcome["reason"][:120],
            )
            entries.append({
                "kind": f"pipeline_{outcome['status']}",
                "title": f"{proj_report['project']} / identity {outcome['identity_uuid'][:8]}",
                "chain": {
                    "ground_truth": outcome["gt_identities_touched"],
                    "pipeline": [outcome["identity_uuid"]],
                    "evidence": [],
                    "decision": outcome["status"],
                    "reason": outcome["reason"],
                },
                "png": image,
            })
    return entries


def build_html(report: Dict[str, Any], gallery: List[Dict[str, Any]]) -> str:
    e = html.escape
    parts = [
        "<meta charset='utf-8'><title>RebarFusion Benchmark Report</title>",
        "<style>body{font-family:system-ui;margin:2em;max-width:1100px}"
        "table{border-collapse:collapse}td,th{border:1px solid #999;padding:4px 8px;font-size:13px}"
        "h3{margin-top:2em}img{max-width:100%;border:1px solid #ccc}"
        ".chain{background:#f5f5f7;padding:8px 12px;font-size:13px;border-radius:6px}</style>",
        "<h1>RebarFusion Benchmark Report</h1>",
        "<h2>Corpus</h2><table>",
    ]
    for key, value in sorted(report["corpus_statistics"].items()):
        parts.append(f"<tr><th>{e(str(key))}</th><td>{e(json.dumps(value, sort_keys=True))}</td></tr>")
    parts.append("</table>")

    parts.append("<h2>Metrics</h2><table><tr><th>Project</th><th>Precision</th><th>Recall</th>"
                 "<th>False merge</th><th>False split</th><th>Obs cov</th><th>Eng cov</th><th>Recon cov</th></tr>")
    for p in report["projects"]:
        im, cm = p["identity_metrics"], p["coverage_metrics"]
        parts.append(
            f"<tr><td>{e(p['project'])}</td><td>{e(_fmt(im['precision'], im['precision_note']))}</td>"
            f"<td>{e(_fmt(im['recall'], im['recall_note']))}</td><td>{e(_fmt(im['false_merge_rate']))}</td>"
            f"<td>{e(_fmt(im['false_split_rate']))}</td><td>{e(_fmt(cm['observation_coverage']))}</td>"
            f"<td>{e(_fmt(cm['engineering_coverage']))}</td>"
            f"<td>{e(_fmt(cm['reconstruction_coverage'], cm['reconstruction_note']))}</td></tr>"
        )
    parts.append("</table>")

    parts.append("<h2>Identity error gallery</h2>")
    if not gallery:
        parts.append("<p>No identity errors.</p>")
    for entry in gallery:
        parts.append(f"<h3>{e(entry['title'])} — {e(entry['kind'])}</h3>")
        chain = entry["chain"]
        parts.append("<div class='chain'>")
        parts.append(f"<b>Ground truth</b>: {e(json.dumps(chain['ground_truth']))}<br>")
        parts.append(f"<b>Pipeline</b>: {e(json.dumps(chain['pipeline']))}<br>")
        if chain["evidence"]:
            parts.append(f"<b>Evidence</b>: {e('; '.join(chain['evidence']))}<br>")
        parts.append(f"<b>Decision</b>: {e(chain['decision'])}<br>")
        parts.append(f"<b>Reason</b>: {e(chain['reason'])}</div>")
        if entry["png"]:
            b64 = base64.b64encode(entry["png"]).decode("ascii")
            parts.append(f"<img src='data:image/png;base64,{b64}'>")
    return "\n".join(parts)


def write_reports(projects: List[BenchmarkProject], out_dir: str) -> Dict[str, Any]:
    os.makedirs(out_dir, exist_ok=True)
    report = evaluate_projects(projects)

    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)

    with open(os.path.join(out_dir, "summary.md"), "w", encoding="utf-8") as f:
        f.write(build_summary_md(report))

    gallery = _gallery_entries(projects, report)
    for idx, entry in enumerate(gallery):
        if entry["png"]:
            with open(os.path.join(out_dir, f"error_{idx:03d}.png"), "wb") as f:
                f.write(entry["png"])
    with open(os.path.join(out_dir, "report.html"), "w", encoding="utf-8") as f:
        f.write(build_html(report, gallery))

    return report
