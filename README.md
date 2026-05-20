# tokenledger

**AI cost ledger.** Sits as a transparent HTTP proxy between your tools (Claude Code, scripts, IDEs) and the Anthropic API — silently recording every LLM call, attributing spend to the git branch or work context you're on, and making it visible through a web dashboard.

**Goal:** Know what each PR, branch, or task actually cost in LLM API spend.

---

## How it works

```
Claude Code → tokenledger proxy (8080) → Anthropic API
                     ↓
               SQLite database
                     ↓
           tokenledger web UI (8787)
```

The proxy intercepts every API call, detects your current git branch (or uses a manual label), computes the cost, and writes a record to a local SQLite database. The web UI reads that database and shows you what everything cost.

Nothing is sent anywhere other than Anthropic. Your data stays on your machine.

---

## Install

```bash
git clone https://github.com/dbmikeldb/tokenledger
cd tokenledger
pip install -e ".[dev]"
```

Requires Python 3.11+.

---

## Quick start

**Terminal 1 — start the proxy:**
```bash
tokenledger serve
# tokenledger proxy listening on http://127.0.0.1:8080
```

**Terminal 2 — point Claude Code at it:**
```bash
# One-time setup in ~/.claude/settings.json:
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8080"
  }
}
```

**Terminal 3 — open the dashboard:**
```bash
tokenledger ui
# Opens http://127.0.0.1:8787 in your browser
```

Now use Claude Code normally. Every API call is recorded and attributed to your current git branch.

---

## Context attribution

tokenledger automatically detects your active git branch by scanning `~/*/` for the most recently switched repo. Switch branches and the next call is attributed to the new branch — no restart needed.

```bash
# See what context is currently recording
tokenledger context

# Override with a manual label (e.g. for non-git work)
tokenledger context "sprint-42-bugfix"

# Clear manual override, return to git auto-detection
tokenledger context --clear
```

You can also set the context when starting the proxy:
```bash
tokenledger serve --context "client-project"
```

### Switching context while the proxy is running

`tokenledger context` talks to the live proxy via HTTP — no restart needed:

```bash
tokenledger context "feat/payments"
# Context set: 'feat/payments' (proxy notified live)
```

---

## Web dashboard

```bash
tokenledger ui                    # default port 8787
tokenledger ui --port 9000
```

**Dashboard shows:**
- Stat cards: all-time spend, this week, this month, total tokens
- Active context banner (which branch is currently recording)
- Daily spend line chart (last 30 days)
- Cost per context bar chart
- Model breakdown donut (haiku / sonnet / opus)
- Context table with links to per-context drill-down

**Context detail shows:**
- Cumulative cost chart across all calls
- Call-by-call log with model, tokens, and cost

Both pages auto-refresh every 30 seconds.

---

## CLI report

```bash
# Summary table — cost per context
tokenledger report

# Per-call detail for context id=3
tokenledger report 3
```

---

## Data storage

All data lives in `~/.tokenledger/tokenledger.db` (SQLite). Override with:
```bash
export TOKENLEDGER_DB=/path/to/custom.db
```

---

## Running tests

```bash
pytest tests/ -v
pytest tests/ --cov=tokenledger
```

---

## Companion tool

**[tokenGate](https://github.com/dbmikeldb/tokenGate)** — interactive terminal gate that intercepts individual API calls before they're sent, shows token counts and cost estimates, and waits for you to pass, edit, or abort. Use tokenGate when you want to review calls; use tokenledger when you want to track spend passively.

---

## License

MIT
