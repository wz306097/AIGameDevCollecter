# AIGameDevCollecter

A **passive collector** that records real AI game-development sessions in a Godot
repo and periodically flags **bad cases** for review. It watches your normal git
history — no change to how you work — assembles sessions, runs lightweight L0/L1
validation, computes outcome metrics, and auto-tags sessions worth a second look.

The CLI is `survey`.

## Install

```bash
git clone https://github.com/wz306097/AIGameDevCollecter.git
cd AIGameDevCollecter
python -m pip install -e ".[dev]"
```

Python ≥ 3.10. Only needs `click` (+ `tomli` on 3.10). The optional Godot
headless scene-load check in L0 runs only if a `godot` binary is on PATH.

## Zero-setup quick start

From inside the game repo you want to observe:

```bash
cd /path/to/your-godot-game
survey watch
```

That's the whole setup. `watch` auto-creates the `survey` storage branch, installs
the post-commit hook, then every interval collects new sessions from git history,
computes metrics, and prints any newly flagged bad cases. `Ctrl-C` to stop.

```bash
survey watch --interval 30m     # default; accepts 45s / 30m / 2h
survey watch --once             # single pass and exit (good for cron, if you prefer)
```

## How it works

```
git history ──▶ infer sessions (commits grouped by time gap)
            ──▶ metrics: AI vs human lines (Co-Authored-By trailer),
                rounds, duration, token cost
            ──▶ L0/L1 validation (syntax, broken refs)
            ──▶ detect_bad_case ──▶ auto-tag (A1–C3 suggested) ──▶ survey branch
```

- **Storage**: a dedicated orphan `survey` branch holds `sessions/*.json` — it
  never touches your working tree.
- **AI vs human attribution**: a commit counts as AI-authored when its message
  has a `Co-Authored-By:` trailer matching the configurable `[git].ai_authors`
  list. This drives the `human_intervention_ratio` bad-case rule.

## Commands

| command | what it does |
|---|---|
| `survey init [--name N]` | create the survey branch + hook (name defaults to repo folder) |
| `survey collect [--since 7d]` | one collection pass |
| `survey watch [--interval 30m] [--once]` | built-in scheduler: collect + flag on a loop |
| `survey verify [--last]` | run L0/L1 on a session |
| `survey tag --pending` | list auto-detected sessions awaiting human classification |
| `survey tag <id> --type B1` | confirm a bad-case type |
| `survey report [--period 30d] [--format md\|json]` | summary report |
| `survey config show` | print merged config |

`collect`, `watch`, and `report` auto-initialize the survey branch if it's missing.

## Tests

```bash
pytest
```
