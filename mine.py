#!/usr/bin/env python3
"""mine.py — skill-demand mining from internship-tracker jobs + gap diff.

Reads the internship-tracker jobs.json (role + notes + tags + description
when present), matches against data/skills_taxonomy.yaml, diffs against
data/my_skills.yaml, and writes reports/gap_report.md + reports/gaps.json.

Stdlib + PyYAML only. Usage:
  ./mine.py [--jobs PATH] [--min-demand N] [--active-only]
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
DEFAULT_JOBS = Path.home() / "internship-tracker" / "data" / "jobs.json"
INACTIVE = {"dropped", "closed"}


def boundary_match(text: str, alias: str) -> bool:
    esc = re.escape(alias)
    return re.search(rf"(?<![a-z0-9]){esc}(?![a-z0-9])", text) is not None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", default=str(DEFAULT_JOBS))
    ap.add_argument("--min-demand", type=int, default=25,
                    help="job matches at/above which a skill counts high-demand")
    ap.add_argument("--active-only", action="store_true",
                    help="ignore dropped/closed legacy postings")
    args = ap.parse_args()

    taxonomy = yaml.safe_load((ROOT / "data" / "skills_taxonomy.yaml").read_text())
    mine = yaml.safe_load((ROOT / "data" / "my_skills.yaml").read_text())

    store = json.loads(Path(args.jobs).read_text())
    jobs = store["jobs"] if isinstance(store, dict) else store
    if args.active_only:
        jobs = [j for j in jobs if j.get("status") not in INACTIVE]

    demand: Counter = Counter()
    examples: dict = {}
    for job in jobs:
        text = " ".join([
            job.get("role", ""), job.get("notes", ""),
            " ".join(job.get("tags", [])), job.get("description", ""),
        ]).lower()
        for skill, spec in taxonomy.items():
            if any(boundary_match(text, a.lower()) for a in spec["aliases"]):
                demand[skill] += 1
                examples.setdefault(skill, []).append(
                    f"{job.get('company','?')} — {job.get('role','?')}")

    high = {s for s, n in demand.items() if n >= args.min_demand}
    rows = []
    for skill in taxonomy:
        if skill not in high:
            continue
        level = (mine.get(skill) or {}).get("level", "none")
        status = {"strong": "covered", "working": "sharpen"}.get(level, "gap")
        rows.append({
            "skill": skill,
            "demand": demand[skill],
            "level": level,
            "status": status,
            "evidence": (mine.get(skill) or {}).get("evidence", ""),
        })
    # gaps first, then sharpen, then covered; within band by demand desc
    order = {"gap": 0, "sharpen": 1, "covered": 2}
    rows.sort(key=lambda r: (order[r["status"]], -r["demand"]))

    gaps_json = {
        "generated_from": str(args.jobs),
        "jobs_scanned": len(jobs),
        "min_demand": args.min_demand,
        "skills": {r["skill"]: r for r in rows},
    }
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "gaps.json").write_text(json.dumps(gaps_json, indent=2))

    lines = [
        "# Skill gap report",
        f"Scanned **{len(jobs)}** postings · high-demand threshold **{args.min_demand}**",
        "",
        "| status | skill | demand | your level |",
        "|---|---|---|---|",
    ]
    icon = {"gap": "🔴 gap", "sharpen": "🟡 sharpen", "covered": "🟢 covered"}
    for r in rows:
        lines.append(f"| {icon[r['status']]} | {r['skill']} | {r['demand']} | {r['level']} |")
    lines += ["", "## What to do", ""]
    for r in rows:
        if r["status"] == "gap":
            lines.append(f"- **{r['skill']}** ({r['demand']} postings): no evidence yet — "
                         f"bank drills + one small artifact to make it real.")
        elif r["status"] == "sharpen":
            lines.append(f"- **{r['skill']}** ({r['demand']} postings): you can do it, "
                         f"you can't *sell* it yet — drill delivery, not study.")
    lines.append("")
    lines.append("Low-demand skills omitted; run with --min-demand 10 for the long tail.")
    (ROOT / "reports" / "gap_report.md").write_text("\n".join(lines))

    print(f"scanned {len(jobs)} postings -> {len(rows)} high-demand skills")
    for r in rows:
        print(f"  {r['status']:8s} {r['skill']:22s} demand={r['demand']:3d} level={r['level']}")
    print("wrote reports/gap_report.md + reports/gaps.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
