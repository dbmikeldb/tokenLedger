# tokenledger

An AI cost ledger. Sits as a transparent HTTP proxy between your tools (Claude Code, scripts, IDEs) and the Anthropic API — recording every LLM call, attributing spend to the git branch or work context you're on, and reporting what each piece of work actually cost.

---

## Install

```bash
pip install -e ".[dev]"
```

Requires Python 3.11+.

---

## Quick start

```bash
# Start the proxy
tokenledger serve

# In another terminal (or ~/.claude/settings.json)
export ANTHROPIC_BASE_URL=http://127.0.0.1:8080

# Do your work — every API call is recorded automatically

# See what it cost
tokenledger report
```

---

## Context attribution

tokenledger automatically detects your current git branch and uses it as the cost context. Every call made while on `feat/auth` is attributed to `feat/auth`.

```bash
# Show current context
tokenledger context

# Override with a manual label (e.g. for non-git work)
tokenledger context "sprint-42-bugfix"

# Clear back to auto-detection
tokenledger context --clear
```

Priority: manual label > git branch > `untagged`

---

## Reporting

```bash
# Summary table — cost per context
tokenledger report

# Per-call detail for a specific context
tokenledger report 3
```

Example output:

```
               tokenledger — cost by context
┌────┬──────────────────┬────────┬───────┬──────────────┬───────────────┬────────────┐
│ ID │ Context          │ Source │ Calls │ Input tokens │ Output tokens │ Total cost │
├────┼──────────────────┼────────┼───────┼──────────────┼───────────────┼────────────┤
│  3 │ feat/auth        │ git    │    24 │      183,442 │        12,831 │    $0.6234 │
│  2 │ fix/login-bug    │ git    │     6 │       41,200 │         3,102 │    $0.1371 │
│  1 │ sprint-42-bugfix │ manual │    11 │       92,000 │         7,450 │    $0.3014 │
└────┴──────────────────┴────────┴───────┴──────────────┴───────────────┴────────────┘
```

---

## Persistent config (Claude Code)

Add to `~/.claude/settings.json`:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8080"
  }
}
```

---

## Data

All data is stored locally in `~/.tokenledger/tokenledger.db` (SQLite). Override with the `TOKENLEDGER_DB` environment variable. Nothing leaves your machine.

---

## Running tests

```bash
pytest tests/ -v
```

---

## License

MIT
