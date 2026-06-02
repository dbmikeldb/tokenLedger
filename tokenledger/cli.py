"""tokenledger CLI."""

from __future__ import annotations

import argparse
import sys


def cmd_serve(args: argparse.Namespace) -> None:
    try:
        from tokenledger.proxy.server import run_server
    except ImportError:
        print(
            "Error: proxy dependencies not installed.\n"
            "Install with: pip install tokenledger[proxy]",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.context:
        from tokenledger.context.tracker import set_manual_context
        from tokenledger.storage.db import init_db
        db_path = init_db()
        set_manual_context(args.context, db_path)
        print(f"Context set: '{args.context}'", file=sys.stderr)

    try:
        run_server(host=args.host, port=args.port)
    except OSError as exc:
        print(f"Could not bind to {args.host}:{args.port}: {exc}", file=sys.stderr)
        sys.exit(1)


def _proxy_url() -> str | None:
    """Return the base URL of the running proxy, or None if not running."""
    import json
    from pathlib import Path
    from tokenledger.storage.db import default_db_path
    info_path = Path(default_db_path()).parent / "proxy.json"
    if not info_path.exists():
        return None
    try:
        info = json.loads(info_path.read_text())
        return f"http://{info['host']}:{info['port']}"
    except Exception:
        return None


def cmd_context(args: argparse.Namespace) -> None:
    from tokenledger.context.tracker import clear_context, set_manual_context
    from tokenledger.storage.db import get_open_context, init_db

    db_path = init_db()

    if args.clear:
        proxy = _proxy_url()
        if proxy:
            try:
                import urllib.request
                req = urllib.request.Request(f"{proxy}/control/context", method="DELETE")
                urllib.request.urlopen(req, timeout=2)
                print("Context cleared (proxy notified — will auto-detect git branch).")
                return
            except Exception:
                pass
        clear_context(db_path)
        print("Context cleared.")
        return

    if args.label:
        proxy = _proxy_url()
        if proxy:
            try:
                import urllib.request
                data = f'{{"label": "{args.label}"}}'.encode()
                req = urllib.request.Request(
                    f"{proxy}/control/context",
                    data=data,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=2)
                print(f"Context set: '{args.label}' (proxy notified live)")
                return
            except Exception:
                pass
        ctx_id = set_manual_context(args.label, db_path)
        print(f"Context set: '{args.label}' (id={ctx_id})")
        return

    # No args — show current context
    proxy = _proxy_url()
    if proxy:
        try:
            import urllib.request, json as _json
            with urllib.request.urlopen(f"{proxy}/control/context", timeout=2) as r:
                info = _json.loads(r.read())
            ctx = info.get("active")
            override = info.get("override")
            cwd = info.get("workspace_cwd", "")
            if ctx:
                note = f"  [override: '{override}']" if override else f"  [git cwd: {cwd}]"
                print(f"Active context: '{ctx['name']}' (source={ctx['source']}, id={ctx['id']}){note}")
            else:
                print("No active context.")
            return
        except Exception:
            pass
    ctx = get_open_context(db_path)
    if ctx:
        print(f"Active context: '{ctx['name']}' (source={ctx['source']}, id={ctx['id']})")
    else:
        print("No active context. Use 'tokenledger context <label>' to set one.")


def _proxy_is_alive(proxy_url: str) -> bool:
    """Return True if the proxy is responding to control requests."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"{proxy_url}/control/context", timeout=1):
            return True
    except Exception:
        return False


def _ensure_proxy(port: int) -> str:
    """Return a proxy URL, starting the proxy if necessary."""
    import json
    import os
    import subprocess
    import time
    from pathlib import Path
    from tokenledger.storage.db import default_db_path

    info_path = Path(default_db_path()).parent / "proxy.json"

    if info_path.exists():
        try:
            info = json.loads(info_path.read_text())
            pid = info.get("pid")
            if pid:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    info_path.unlink(missing_ok=True)
                except PermissionError:
                    pass
        except Exception:
            pass

    url = _proxy_url()
    if url and _proxy_is_alive(url):
        return url

    print(f"[tokenledger] starting proxy on port {port}...", file=sys.stderr)
    subprocess.Popen(
        ["tokenledger", "serve", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    proxy_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        time.sleep(0.2)
        if _proxy_is_alive(proxy_url):
            print("[tokenledger] proxy ready.", file=sys.stderr)
            return proxy_url

    print("[tokenledger] error: proxy did not become ready within 10 seconds.", file=sys.stderr)
    sys.exit(1)


def cmd_claude(args: argparse.Namespace) -> None:
    import json
    import os
    import shutil
    import socket
    import subprocess
    import urllib.request

    claude_bin = shutil.which("claude")
    if not claude_bin:
        print(
            "Error: 'claude' binary not found in PATH.\n"
            "Install Claude Code: https://docs.anthropic.com/claude-code",
            file=sys.stderr,
        )
        sys.exit(1)

    proxy_url = _ensure_proxy(args.port)

    # Start the web UI unless suppressed
    if not args.no_ui:
        ui_ready = False
        try:
            s = socket.socket()
            s.settimeout(0.5)
            s.connect(("127.0.0.1", 8787))
            s.close()
            ui_ready = True
        except OSError:
            pass
        if not ui_ready:
            subprocess.Popen(
                ["tokenledger", "ui", "--host", "127.0.0.1", "--port", "8787"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print("[tokenledger] web UI started at http://127.0.0.1:8787", file=sys.stderr)

    # Update proxy workspace CWD so git detection uses the right directory
    try:
        data = json.dumps({"cwd": os.getcwd()}).encode()
        req = urllib.request.Request(
            f"{proxy_url}/control/workspace",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception as exc:
        print(f"[tokenledger] warning: could not update workspace CWD: {exc}", file=sys.stderr)

    # Build child environment
    env = os.environ.copy()
    existing = env.get("ANTHROPIC_BASE_URL")
    if existing and existing != proxy_url:
        print(
            f"[tokenledger] warning: ANTHROPIC_BASE_URL already set to '{existing}'; not overriding.",
            file=sys.stderr,
        )
    else:
        env["ANTHROPIC_BASE_URL"] = proxy_url

    # Startup line
    try:
        with urllib.request.urlopen(f"{proxy_url}/control/context", timeout=1) as r:
            import json as _j
            _info = _j.loads(r.read())
        _ctx = _info.get("active")
        _ctx_label = _ctx["name"] if _ctx else "none"
    except Exception:
        _ctx_label = "unknown"
    _ui_hint = "" if args.no_ui else " · ui at http://127.0.0.1:8787"
    print(f"[tokenledger] proxy on :{args.port}{_ui_hint} · context: {_ctx_label}", file=sys.stderr)

    claude_argv = [claude_bin] + list(args.claude_args)

    if args.summary:
        pre_cost = 0.0
        try:
            from tokenledger.storage.db import get_context_summary, init_db
            db_path = init_db()
            rows = get_context_summary(db_path)
            pre_cost = sum(r["total_cost"] or 0 for r in rows)
        except Exception:
            pass

        result = subprocess.run(claude_argv, env=env)

        try:
            from tokenledger.storage.db import get_context_summary, init_db
            db_path = init_db()
            rows = get_context_summary(db_path)
            post_cost = sum(r["total_cost"] or 0 for r in rows)
            print(f"\n[tokenledger] session cost: ${post_cost - pre_cost:.4f}", file=sys.stderr)
        except Exception:
            pass

        sys.exit(result.returncode)
    else:
        os.execve(claude_bin, claude_argv, env)


def cmd_install(args: argparse.Namespace) -> None:
    import os
    import sys
    from pathlib import Path

    shell = args.shell
    if not shell:
        raw = os.environ.get("SHELL", "")
        if "zsh" in raw:
            shell = "zsh"
        elif "fish" in raw:
            shell = "fish"
        else:
            shell = "bash"

    if shell == "zsh":
        rc_path = Path.home() / ".zshrc"
    elif shell == "fish":
        rc_path = Path.home() / ".config" / "fish" / "config.fish"
    else:
        rc_path = Path.home() / ".bashrc"

    # Derive the venv bin dir from the currently running Python executable
    venv_bin = Path(sys.executable).parent
    if shell == "fish":
        path_line = f"\nfish_add_path {venv_bin}\n"
        path_check = str(venv_bin)
    else:
        path_line = f'\nexport PATH="{venv_bin}:$PATH"\n'
        path_check = str(venv_bin)

    alias_check = "alias claude=" if shell != "fish" else "alias claude "
    alias_line = (
        "\nalias claude='tokenledger claude'\n"
        if shell != "fish"
        else "\nalias claude 'tokenledger claude'\n"
    )

    rc_text = rc_path.read_text() if rc_path.exists() else ""
    already_path = path_check in rc_text
    already_alias = alias_check in rc_text

    if already_path and already_alias:
        print(f"Already installed in {rc_path}.")
        return

    if args.dry_run:
        if not already_path:
            print(f"Would append to {rc_path}:{path_line}", end="")
        if not already_alias:
            print(f"Would append to {rc_path}:{alias_line}", end="")
        return

    rc_path.parent.mkdir(parents=True, exist_ok=True)
    with rc_path.open("a") as f:
        if not already_path:
            f.write(path_line)
        if not already_alias:
            f.write(alias_line)

    print(f"Added to {rc_path}")
    print(f"Run: source {rc_path}")


def cmd_status(args: argparse.Namespace) -> None:
    import json
    import socket
    import urllib.request
    from datetime import date
    from pathlib import Path
    from tokenledger.storage.db import default_db_path, get_context_summary, get_open_context, init_db

    db_path = init_db()

    # Proxy
    proxy_url = _proxy_url()
    proxy_info_path = Path(default_db_path()).parent / "proxy.json"
    proxy_pid = None
    if proxy_info_path.exists():
        try:
            info = json.loads(proxy_info_path.read_text())
            proxy_pid = info.get("pid")
        except Exception:
            pass

    proxy_alive = bool(proxy_url and _proxy_is_alive(proxy_url))
    if proxy_alive:
        pid_str = f"  (pid {proxy_pid})" if proxy_pid else ""
        proxy_line = f"  proxy      running  {proxy_url}{pid_str}"
    else:
        proxy_line = "  proxy      stopped"

    # Web UI
    ui_up = False
    try:
        s = socket.socket()
        s.settimeout(0.5)
        s.connect(("127.0.0.1", 8787))
        s.close()
        ui_up = True
    except OSError:
        pass
    ui_line = "  web ui     running  http://127.0.0.1:8787" if ui_up else "  web ui     stopped"

    # Context
    ctx_line = "  context    none"
    if proxy_alive:
        try:
            with urllib.request.urlopen(f"{proxy_url}/control/context", timeout=1) as r:
                info = json.loads(r.read())
            ctx = info.get("active")
            if ctx:
                repo_part = f" · repo: {ctx['repo']}" if ctx.get("repo") else ""
                ctx_line = f"  context    {ctx['name']}  ({ctx['source']}{repo_part} · id={ctx['id']})"
        except Exception:
            pass
    else:
        ctx = get_open_context(db_path)
        if ctx:
            repo_part = f" · repo: {ctx['repo']}" if ctx.get("repo") else ""
            ctx_line = f"  context    {ctx['name']}  ({ctx['source']}{repo_part} · id={ctx['id']})"

    # Spend
    today_str = date.today().isoformat()
    summaries = get_context_summary(db_path)
    all_time = sum(r["total_cost"] or 0 for r in summaries)
    today_cost = 0.0
    today_calls = 0
    for r in summaries:
        started = (r["started_at"] or "")[:10]
        if started == today_str:
            today_cost += r["total_cost"] or 0
            today_calls += r["call_count"] or 0
    today_line = f"  today      ${today_cost:.4f}  ({today_calls} calls)"
    alltime_line = f"  all time   ${all_time:.4f}"

    print("\n".join([proxy_line, ui_line, ctx_line, today_line, alltime_line]))


def cmd_ui(args: argparse.Namespace) -> None:
    try:
        from tokenledger.web.server import run_ui
    except ImportError:
        print(
            "Error: web dependencies not installed.\n"
            "Install with: pip install tokenledger[proxy]",
            file=sys.stderr,
        )
        sys.exit(1)
    run_ui(host=args.host, port=args.port)


def cmd_report(args: argparse.Namespace) -> None:
    from tokenledger.storage.db import get_calls_for_context, get_context_summary, init_db

    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        print("Error: rich not installed.", file=sys.stderr)
        sys.exit(1)

    db_path = init_db()
    console = Console()
    summaries = get_context_summary(db_path)

    if not summaries:
        console.print("[dim]No recorded sessions yet.[/dim]")
        return

    table = Table(title="tokenledger — cost by context", show_lines=True)
    table.add_column("ID", style="dim", width=4)
    table.add_column("Context", style="bold")
    table.add_column("Source", style="dim")
    table.add_column("Calls", justify="right")
    table.add_column("Input tokens", justify="right")
    table.add_column("Output tokens", justify="right")
    table.add_column("Total cost", justify="right", style="green")

    for row in summaries:
        table.add_row(
            str(row["id"]),
            row["name"],
            row["source"],
            str(row["call_count"] or 0),
            f"{(row['total_input_tokens'] or 0):,}",
            f"{(row['total_output_tokens'] or 0):,}",
            f"${(row['total_cost'] or 0):.4f}",
        )

    console.print(table)

    if args.context_id is not None:
        calls = get_calls_for_context(args.context_id, db_path)
        if not calls:
            console.print(f"[dim]No calls for context id={args.context_id}[/dim]")
            return

        detail = Table(title=f"Calls — context {args.context_id}", show_lines=True)
        detail.add_column("Time", style="dim")
        detail.add_column("Model")
        detail.add_column("In", justify="right")
        detail.add_column("Out", justify="right")
        detail.add_column("Cost", justify="right", style="green")

        for call in calls:
            detail.add_row(
                call["timestamp"][:19].replace("T", " "),
                call["model"],
                f"{(call['input_tokens'] or 0):,}",
                f"{(call['output_tokens'] or 0):,}",
                f"${(call['total_cost'] or 0):.4f}",
            )

        console.print(detail)


def cmd_export(args: argparse.Namespace) -> None:
    import csv
    import json as _json
    from tokenledger.storage.db import get_conn, init_db

    db_path = init_db()
    fmt = args.format.lower()
    out = open(args.output, "w", newline="" if fmt == "csv" else None, encoding="utf-8") \
        if args.output else sys.stdout

    try:
        with get_conn(db_path) as conn:
            query = """
                SELECT
                    ca.id          AS call_id,
                    c.id           AS context_id,
                    c.name         AS context,
                    c.repo         AS repo,
                    c.source       AS source,
                    ca.timestamp,
                    ca.model,
                    ca.input_tokens,
                    ca.output_tokens,
                    ca.input_cost,
                    ca.output_cost,
                    ca.total_cost,
                    ca.request_id
                FROM calls ca
                LEFT JOIN contexts c ON c.id = ca.context_id
            """
            params: list = []
            if args.context_id is not None:
                query += " WHERE ca.context_id = ?"
                params.append(args.context_id)
            if args.repo:
                query += " AND c.repo = ?" if params else " WHERE c.repo = ?"
                params.append(args.repo)
            query += " ORDER BY ca.timestamp"
            rows = conn.execute(query, params).fetchall()

        if fmt == "csv":
            if not rows:
                return
            writer = csv.DictWriter(out, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(dict(r) for r in rows)
        else:
            _json.dump([dict(r) for r in rows], out, indent=2, default=str)
            out.write("\n")

        if args.output:
            print(f"Exported {len(rows)} calls to {args.output}", file=sys.stderr)
    finally:
        if args.output:
            out.close()


def _pid_on_port(port: int) -> int | None:
    """Return the PID of the process listening on the given TCP port, or None."""
    import subprocess
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}", "-sTCP:LISTEN"],
            capture_output=True, text=True,
        )
        pid_str = result.stdout.strip()
        return int(pid_str.splitlines()[0]) if pid_str else None
    except Exception:
        return None


def cmd_stop(args: argparse.Namespace) -> None:
    import json
    import os
    import signal
    from pathlib import Path
    from tokenledger.storage.db import default_db_path

    stopped_any = False

    # Stop proxy via PID from proxy.json
    info_path = Path(default_db_path()).parent / "proxy.json"
    proxy_pid = None
    proxy_port = 8080
    if info_path.exists():
        try:
            info = json.loads(info_path.read_text())
            proxy_pid = info.get("pid")
            proxy_port = info.get("port", 8080)
        except Exception:
            pass

    if proxy_pid:
        try:
            os.kill(proxy_pid, signal.SIGTERM)
            print(f"Stopped proxy  (pid {proxy_pid})")
            stopped_any = True
        except ProcessLookupError:
            print(f"Proxy not running  (stale pid {proxy_pid})")
        except PermissionError:
            print(f"Permission denied killing proxy pid {proxy_pid}", file=sys.stderr)
        info_path.unlink(missing_ok=True)
    else:
        # No proxy.json — try finding by port
        pid = _pid_on_port(proxy_port)
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                print(f"Stopped proxy  (pid {pid}, port {proxy_port})")
                stopped_any = True
            except Exception as exc:
                print(f"Could not stop proxy: {exc}", file=sys.stderr)
        else:
            print("Proxy not running.")

    # Stop web UI by finding the process on port 8787
    ui_pid = _pid_on_port(8787)
    if ui_pid:
        try:
            os.kill(ui_pid, signal.SIGTERM)
            print(f"Stopped web UI  (pid {ui_pid})")
            stopped_any = True
        except ProcessLookupError:
            print("Web UI not running.")
        except PermissionError:
            print(f"Permission denied killing web UI pid {ui_pid}", file=sys.stderr)
    else:
        print("Web UI not running.")

    if not stopped_any:
        print("Nothing was running.")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tokenledger",
        description="tokenledger — AI cost ledger for your work",
    )
    sub = parser.add_subparsers(dest="command")

    # serve
    serve = sub.add_parser("serve", help="Start the proxy server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument("--context", default=None, metavar="LABEL",
                       help="Set work context before starting (overrides git branch auto-detection)")

    # context
    ctx = sub.add_parser("context", help="Get or set the current work context")
    ctx.add_argument("label", nargs="?", help="Label for this work session (e.g. branch name)")
    ctx.add_argument("--clear", action="store_true", help="Close the current context")

    # ui
    ui = sub.add_parser("ui", help="Open the web dashboard")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=8787)

    # export
    export = sub.add_parser("export", help="Export call data to CSV or JSON")
    export.add_argument("--format", choices=["csv", "json"], default="csv",
                        help="Output format (default: csv)")
    export.add_argument("--output", "-o", default=None, metavar="FILE",
                        help="Write to file instead of stdout")
    export.add_argument("--context-id", type=int, default=None, metavar="ID",
                        help="Export a specific context only")
    export.add_argument("--repo", default=None, metavar="REPO",
                        help="Filter by repo name")

    # report
    report = sub.add_parser("report", help="Show cost breakdown by context")
    report.add_argument(
        "context_id",
        nargs="?",
        type=int,
        help="Show per-call detail for a specific context ID",
    )

    # install
    install_cmd = sub.add_parser("install", help="Add shell alias: claude → tokenledger claude")
    install_cmd.add_argument("--shell", choices=["bash", "zsh", "fish"], default=None,
                             help="Target shell (default: auto-detect from $SHELL)")
    install_cmd.add_argument("--dry-run", action="store_true",
                             help="Print what would be written without modifying any file")

    # status
    sub.add_parser("status", help="Show proxy, UI, and spend status")

    # stop
    sub.add_parser("stop", help="Stop the proxy and web UI")

    # claude
    claude_cmd = sub.add_parser("claude", help="Launch claude via tokenledger proxy")
    claude_cmd.add_argument(
        "claude_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed through to the claude binary",
    )
    claude_cmd.add_argument("--port", type=int, default=8080,
                            help="Proxy port to use/start (default: 8080)")
    claude_cmd.add_argument("--no-ui", action="store_true",
                            help="Do not start the web UI automatically")
    claude_cmd.add_argument("--summary", action="store_true",
                            help="Print cost summary after claude exits")

    args = parser.parse_args()

    if args.command == "serve":
        cmd_serve(args)
    elif args.command == "context":
        cmd_context(args)
    elif args.command == "ui":
        cmd_ui(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "install":
        cmd_install(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "claude":
        cmd_claude(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
