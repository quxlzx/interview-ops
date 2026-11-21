# interview-ops

Mock-interview ops for ML/AI internship hunting. Two stdlib+PyYAML CLIs
sharing one skill vocabulary:

- **mine.py** — mines skill demand from a job-postings JSON store
  (role + notes + tags, description when present), diffs against your
  self-assessment, writes `reports/gap_report.md` + `reports/gaps.json`.
- **drill.py** — SM-2-lite spaced repetition over `bank/*.yaml` question
  cards (101 seeded: ML fundamentals, deep learning, LLM/agents, ML infra,
  systems/SWE, DSA, behavioral). Due-card priority is weighted by gap
  status from `reports/gaps.json`: gap x3, sharpen x2, covered x1.

## Setup
```
python3 -m pip install -r requirements.txt   # PyYAML
cp data/my_skills.example.yaml data/my_skills.yaml   # then rate yourself honestly
./mine.py                                            # point --jobs at your own store
./drill.py init && ./drill.py drill
```

`--jobs` defaults to `~/internship-tracker/data/jobs.json` (see
github.com/quxlzx/internship-tracker for a compatible store schema); pass
`--jobs PATH` for anything else.

## Commands
```
./mine.py [--jobs PATH] [--min-demand 25] [--active-only]
./drill.py init | due [--list N] | drill [-n 8] | focus | stats
```

## Editing
- `data/my_skills.yaml` — personal, gitignored. Update as projects land.
- `data/skills_taxonomy.yaml` — canonical skills -> match aliases.
- `bank/*.yaml` — add questions freely; `init` upserts by id, existing
  schedules survive.
- Canonical vocabulary is shared by taxonomy, my_skills, and bank tags —
  add new skills to all three or drills won't route to gaps.

## Data flow
jobs store -> mine.py -> gaps.json -> drill.py weighting.

Personal data (self-assessment, drill history, reports) is gitignored by
design; this repo publishes only code + question bank + taxonomy.

MIT licensed.
