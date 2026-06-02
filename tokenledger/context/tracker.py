"""Work context tracking.

Determines the current work context from git branch auto-detection or
a manually set label, and manages open/close lifecycle in the database.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tokenledger.storage.db import (
    close_context,
    get_open_context,
    open_context,
)


def detect_git_branch(cwd: str | None = None) -> str | None:
    """Return the current git branch name from cwd, or the most recently
    active git repo under the home directory if cwd is not in a repo."""
    branch = _git_branch_at(cwd or str(Path.home()))
    if branch:
        return branch
    return _most_active_git_branch()


def _git_branch_at(cwd: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=cwd, timeout=2,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            return branch if branch and branch != "HEAD" else None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _git_repo_at(cwd: str) -> str:
    """Return the repo name (directory basename of the git root), or ''."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, cwd=cwd, timeout=2,
        )
        if result.returncode == 0:
            toplevel = result.stdout.strip()
            return Path(toplevel).name if toplevel else ""
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return ""


def _most_active_git_branch() -> str | None:
    """Scan repos under home and return the branch from the repo whose
    .git/index was modified most recently. The index updates on git
    operations and staging, making it a reliable signal for the actively
    worked-on repo rather than just the last branch switch."""
    home = Path.home()
    best: tuple[float, str] | None = None
    candidates = list(home.glob("*/.git/index")) + list(home.glob("*/*/.git/index"))
    for index_file in candidates:
        try:
            mtime = index_file.stat().st_mtime
            if best and mtime <= best[0]:
                continue
            branch = _git_branch_at(str(index_file.parent.parent))
            if branch:
                best = (mtime, branch)
        except OSError:
            pass
    return best[1] if best else None


def resolve_context(
    manual_label: str | None = None,
    cwd: str | None = None,
) -> tuple[str, str, str]:
    """Return (context_name, source, repo) for the current work session.

    Priority: manual label > git branch > 'untagged'
    """
    if manual_label:
        return manual_label, "manual", ""
    branch = detect_git_branch(cwd)
    if branch:
        effective_cwd = cwd or str(Path.home())
        repo = _git_repo_at(effective_cwd) or _repo_from_most_active(cwd)
        return branch, "git", repo
    return "untagged", "manual", ""


def _repo_from_most_active(cwd: str | None) -> str:
    """Return the repo name from the repo whose .git/index was modified most recently."""
    home = Path.home()
    best: tuple[float, str] | None = None
    candidates = list(home.glob("*/.git/index")) + list(home.glob("*/*/.git/index"))
    for index_file in candidates:
        try:
            mtime = index_file.stat().st_mtime
            if best and mtime <= best[0]:
                continue
            repo = _git_repo_at(str(index_file.parent.parent))
            if repo:
                best = (mtime, repo)
        except OSError:
            pass
    return best[1] if best else ""


def ensure_context(
    manual_label: str | None = None,
    cwd: str | None = None,
    db_path: str | None = None,
) -> int:
    """Return the active context_id, opening a new one if the context has changed."""
    name, source, repo = resolve_context(manual_label, cwd)
    existing = get_open_context(db_path)

    if existing is not None:
        if existing["name"] == name and existing["repo"] == repo:
            return existing["id"]
        close_context(existing["id"], db_path)

    return open_context(name, source, repo, db_path)


def set_manual_context(label: str, db_path: str | None = None) -> int:
    """Explicitly open a named context, closing any open one first."""
    existing = get_open_context(db_path)
    if existing is not None:
        close_context(existing["id"], db_path)
    return open_context(label, "manual", "", db_path)


def clear_context(db_path: str | None = None) -> None:
    """Close the current context without opening a new one."""
    existing = get_open_context(db_path)
    if existing is not None:
        close_context(existing["id"], db_path)
