#!/usr/bin/env python3
"""drill.py — spaced-repetition mock-interview drills (SM-2 lite).

Bank: bank/*.yaml (or *.json) entries:
  id, category, skills[], difficulty 1-3, prompt, followups[], good_answer[]

Schedule lives in data/drills.sqlite. Gap priority comes from
reports/gaps.json (run mine.py first).

Commands:
  ./drill.py init            # load bank into sqlite (safe to re-run)
  ./drill.py due             # count/list due cards
  ./drill.py drill [-n N]    # interactive session (grade yourself 0-5, q=quit)
  ./drill.py focus           # due-card counts per gap skill
  ./drill.py stats           # schedule health
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "drills.sqlite"


def load_bank():
    cards = []
    for f in sorted(list((ROOT / "bank").glob("*.yaml")) + list((ROOT / "bank").glob("*.json"))):
        data = yaml.safe_load(f.read_text()) if f.suffix == ".yaml" else json.loads(f.read_text())
        for c in data:
            cards.append(c)
    return cards


def db():
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS cards(
        id TEXT PRIMARY KEY, category TEXT, skills TEXT, difficulty INT,
        prompt TEXT, followups TEXT, good_answer TEXT,
        ease REAL DEFAULT 2.5, interval REAL DEFAULT 0, due TEXT,
        reps INT DEFAULT 0, lapses INT DEFAULT 0, last_grade INT,
        last_seen TEXT)""")
    return conn


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def cmd_init(_args):
    conn = db()
    n = 0
    for c in load_bank():
        conn.execute(
            """INSERT INTO cards(id,category,skills,difficulty,prompt,followups,good_answer,due)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET prompt=excluded.prompt,
                 followups=excluded.followups, good_answer=excluded.good_answer""",
            (c["id"], c.get("category", "?"), json.dumps(c.get("skills", [])),
             int(c.get("difficulty", 2)), c["prompt"],
             json.dumps(c.get("followups", [])), json.dumps(c.get("good_answer", [])), now()))
        n += 1
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    print(f"loaded/refreshed {n} bank cards; {total} cards in schedule")


def gap_weights():
    p = ROOT / "reports" / "gaps.json"
    if not p.exists():
        return {}
    gaps = json.loads(p.read_text())["skills"]
    return {s: {"gap": 3.0, "sharpen": 2.0, "covered": 1.0}[v["status"]]
            for s, v in gaps.items()}


def due_cards(conn, weights):
    rows = conn.execute(
        "SELECT id,category,skills,difficulty,prompt,followups,good_answer,"
        "interval,reps,lapses FROM cards WHERE due<=? ", (now(),)).fetchall()
    def weight(r):
        skills = json.loads(r[2])
        w = max((weights.get(s, 1.0) for s in skills), default=1.0)
        # never-seen cards get a small boost; harder cards slight boost
        return -(w * 10 + r[3] + (2 if r[8] == 0 else 0))
    rows.sort(key=weight)
    return rows


def cmd_due(args):
    conn = db()
    rows = due_cards(conn, gap_weights())
    print(f"{len(rows)} cards due")
    if args.list:
        for r in rows[: args.list]:
            print(f"  [{r[1]} d{r[3]}] {r[0]}: {r[4][:80]}")


def cmd_drill(args):
    conn = db()
    weights = gap_weights()
    rows = due_cards(conn, weights)
    if not rows:
        print("Nothing due. Come back later — that's the whole point of spaced repetition.")
        return
    done = 0
    for r in rows:
        if done >= args.n:
            break
        cid, cat, skills, diff, prompt, followups, good, interval, reps, lapses = r
        print(f"\n=== {cid} [{cat} d{diff} reps={reps} lapses={lapses}] ===")
        print(f"Q: {prompt}")
        try:
            input("-- answer out loud, then Enter to reveal (q=quit): ")
        except (EOFError, KeyboardInterrupt):
            break
        if prompt and input("q to skip? [y/N]: ").lower().startswith("q"):
            continue
        for f in json.loads(followups):
            print(f"  ↳ follow-up: {f}")
        print("A strong answer covers:")
        for g in json.loads(good):
            print(f"  - {g}")
        while True:
            try:
                raw = input("self-grade 0-5 (5=nailed it, q=quit): ")
            except (EOFError, KeyboardInterrupt):
                return
            if raw.lower().startswith("q"):
                return
            if raw.strip().isdigit() and 0 <= int(raw) <= 5:
                grade = int(raw)
                break
            print("  enter 0-5")
        # SM-2 lite
        ease = conn.execute("SELECT ease FROM cards WHERE id=?", (cid,)).fetchone()[0]
        ease = max(1.3, ease + 0.1 - (5 - grade) * (0.08 + (4 - grade) * 0.02))
        if grade < 3:
            interval, lapses = 0.5, lapses + 1
        elif reps == 0:
            interval, reps = 1.0, reps + 1
        elif reps == 1:
            interval, reps = 6.0, reps + 1
        else:
            interval, reps = round(interval * ease, 1), reps + 1
        due = (datetime.now() + timedelta(days=interval)).strftime("%Y-%m-%d %H:%M")
        conn.execute("UPDATE cards SET ease=?, interval=?, due=?, reps=?, lapses=?,"
                     " last_grade=?, last_seen=? WHERE id=?",
                     (ease, interval, due, reps, lapses, grade, now(), cid))
        conn.commit()
        done += 1
        print(f"  -> next in {interval}d (ease {ease:.2f})")
    print(f"\nsession done: {done} cards drilled")


def cmd_focus(_args):
    conn = db()
    gaps = json.loads((ROOT / "reports" / "gaps.json").read_text())["skills"] \
        if (ROOT / "reports" / "gaps.json").exists() else {}
    rows = conn.execute("SELECT id,skills,category FROM cards WHERE due<=?", (now(),)).fetchall()
    per = {}
    for _id, skills, cat in rows:
        for s in json.loads(skills):
            per.setdefault(s, [0, ""])
            per[s][0] += 1
            per[s][1] = gaps.get(s, {}).get("status", "-")
    out = sorted(per.items(), key=lambda kv: (-kv[1][0], kv[0]))
    print(f"{'skill':22s} {'due':>4s}  gap-status")
    for s, (n, st) in out:
        print(f"{s:22s} {n:4d}  {st}")


def cmd_stats(_args):
    conn = db()
    tot = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    due = conn.execute("SELECT COUNT(*) FROM cards WHERE due<=?", (now(),)).fetchone()[0]
    seen = conn.execute("SELECT COUNT(*) FROM cards WHERE reps>0").fetchone()[0]
    mastered = conn.execute("SELECT COUNT(*) FROM cards WHERE interval>=21").fetchone()[0]
    lapses = conn.execute("SELECT SUM(lapses) FROM cards").fetchone()[0] or 0
    print(f"cards={tot} seen={seen} due_now={due} mastered(>=21d)={mastered} lapses={lapses}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    p = sub.add_parser("due"); p.add_argument("--list", type=int, const=20, nargs="?")
    p = sub.add_parser("drill"); p.add_argument("-n", type=int, default=8)
    sub.add_parser("focus")
    sub.add_parser("stats")
    args = ap.parse_args()
    {"init": cmd_init, "due": cmd_due, "drill": cmd_drill,
     "focus": cmd_focus, "stats": cmd_stats}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
