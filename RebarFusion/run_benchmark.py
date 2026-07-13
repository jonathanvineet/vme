"""
run_benchmark.py — Phase 13.1: Validation Corpus & Benchmark CLI.

Evaluates the frozen Phase 1-12 pipeline against every project in a
corpus directory (each subdirectory containing drawings/ + ground_truth/,
see benchmark/schemas/ground_truth_format.md). Evaluation layer only:
pipeline behavior is untouched; this loads, compares, and reports.

Usage:
    python run_benchmark.py <corpus_dir> [--out <report_dir>]
    python run_benchmark.py --project <single_project_dir> [--out <report_dir>]
"""
from __future__ import annotations

import argparse
import os
import sys

from benchmark.loaders.project_loader import load_project
from benchmark.reports.report_builder import write_reports


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 13.1: benchmark the Phase 1-12 pipeline")
    parser.add_argument("corpus", nargs="?", help="Corpus directory (one subdir per project)")
    parser.add_argument("--project", help="Evaluate a single project directory instead of a corpus")
    parser.add_argument("--out", default=os.path.join("benchmark", "reports", "latest"),
                        help="Report output directory")
    args = parser.parse_args()

    project_dirs = []
    if args.project:
        project_dirs = [args.project]
    elif args.corpus:
        project_dirs = sorted(
            os.path.join(args.corpus, d) for d in os.listdir(args.corpus)
            if os.path.isdir(os.path.join(args.corpus, d, "drawings"))
        )
    if not project_dirs:
        print("No projects found (need <dir>/drawings/ per project).")
        return 1

    projects = []
    for pd in project_dirs:
        print(f"Loading project: {pd}")
        projects.append(load_project(pd))

    report = write_reports(projects, args.out)

    stats = report["corpus_statistics"]
    print(f"\nProjects: {stats['projects']}  drawings: {stats['drawings_processed']}  "
          f"observations: {stats['observations']}  accepted identities: {stats['accepted_identities']}")
    for p in report["projects"]:
        im = p["identity_metrics"]
        print(f"  {p['project']}: precision={im['precision']} recall={im['recall']} "
              f"false_merge={im['false_merge_rate']} false_split={im['false_split_rate']}")
    print(f"\nReports written to {args.out}/ (report.json, summary.md, report.html)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
