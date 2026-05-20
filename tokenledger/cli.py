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


def cmd_context(args: argparse.Namespace) -> None:
    from tokenledger.context.tracker import clear_context, set_manual_context
    from tokenledger.storage.db import get_open_context, init_db

    db_path = init_db()

    if args.clear:
        clear_context(db_path)
        print("Context cleared.")
        return

    if args.label:
        ctx_id = set_manual_context(args.label, db_path)
        print(f"Context set: '{args.label}' (id={ctx_id})")
        return

    # No args — show current context
    ctx = get_open_context(db_path)
    if ctx:
        print(f"Active context: '{ctx['name']}' (source={ctx['source']}, id={ctx['id']})")
    else:
        print("No active context. Use 'tokenledger context <label>' to set one.")


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

    # report
    report = sub.add_parser("report", help="Show cost breakdown by context")
    report.add_argument(
        "context_id",
        nargs="?",
        type=int,
        help="Show per-call detail for a specific context ID",
    )

    args = parser.parse_args()

    if args.command == "serve":
        cmd_serve(args)
    elif args.command == "context":
        cmd_context(args)
    elif args.command == "report":
        cmd_report(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
