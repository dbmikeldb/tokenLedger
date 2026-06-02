# tokenLedger

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
git clone https://github.com/dbmikeldb/tokenLedger
cd tokenLedger
pip install -e ".[proxy]"
```

Requires Python 3.11+.

---

## Quick start

**One-time setup:**
```bash
tokenledger install
source ~/.bashrc
```

This adds `tokenledger` to your PATH and creates a `claude` alias. From now on, just run:

```bash
claude
```

tokenledger automatically starts the proxy, opens the web dashboard, detects your active git branch, and launches Claude Code — all in one command.

---

## What `claude` does

1. Starts the proxy on `http://127.0.0.1:8080` (if not already running)
2. Starts the web UI at `http://127.0.0.1:8787` (if not already running)
3. Detects your current git repo and branch
4. Sets `ANTHROPIC_BASE_URL` so Claude Code routes through the proxy
5. Execs into the real `claude` binary — no wrapper process left behind

```bash
claude                    # normal usage
claude --no-ui            # skip starting the web UI
claude --summary          # print session cost on exit
```

> **Remote machines / SSH:** The UI binds to `127.0.0.1`. Forward the port with  
> `ssh -L 8787:127.0.0.1:8787 your-server` then browse to `http://localhost:8787`.

---

## Context attribution

tokenledger detects the active git branch by scanning repos under `~/` for the one whose `.git/index` was modified most recently — a reliable signal for which repo is actively being worked on.

```bash
# See what context is currently recording
tokenledger context

# Override with a manual label (e.g. for non-git work)
tokenledger context "sprint-42-bugfix"

# Clear manual override, return to git auto-detection
tokenledger context --clear
```

Context switches take effect on the next API call — no restart needed.

---

## Status and control

```bash
# Show proxy, UI, active context, and today's spend
tokenledger status

# Stop the proxy and web UI
tokenledger stop
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
- Repos tab — spend broken down by repository
- Context table with links to per-context drill-down

Both pages auto-refresh every 30 seconds.

---

## CLI reference

```bash
claude                            # start everything and launch Claude Code
tokenledger status                # health check: proxy, UI, context, spend
tokenledger stop                  # stop proxy and web UI
tokenledger context               # show active context
tokenledger context "label"       # set manual context
tokenledger context --clear       # return to git auto-detection
tokenledger report                # cost table by context
tokenledger report 3              # per-call detail for context id=3
tokenledger export                # export all calls to CSV (stdout)
tokenledger export --format json  # export as JSON
tokenledger install               # add PATH and alias to shell rc file
tokenledger serve                 # start proxy only
tokenledger ui                    # start web UI only
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
