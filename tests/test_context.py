"""Tests for tokenledger.context.tracker."""

from unittest.mock import patch

import pytest
from tokenledger.context.tracker import (
    clear_context,
    ensure_context,
    resolve_context,
    set_manual_context,
)
from tokenledger.storage.db import get_open_context, init_db


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path)
    return path


class TestResolveContext:
    def test_manual_label_takes_priority(self):
        name, source = resolve_context(manual_label="my-task")
        assert name == "my-task"
        assert source == "manual"

    def test_git_branch_detected(self):
        with patch(
            "tokenledger.context.tracker.detect_git_branch",
            return_value="feat/login",
        ):
            name, source = resolve_context()
        assert name == "feat/login"
        assert source == "git"

    def test_falls_back_to_untagged(self):
        with patch(
            "tokenledger.context.tracker.detect_git_branch",
            return_value=None,
        ):
            name, source = resolve_context()
        assert name == "untagged"
        assert source == "manual"


class TestEnsureContext:
    def test_opens_new_context(self, db):
        with patch(
            "tokenledger.context.tracker.detect_git_branch",
            return_value="feat/x",
        ):
            ctx_id = ensure_context(db_path=db)
        ctx = get_open_context(db)
        assert ctx is not None
        assert ctx["name"] == "feat/x"
        assert ctx["id"] == ctx_id

    def test_returns_same_context_if_unchanged(self, db):
        with patch(
            "tokenledger.context.tracker.detect_git_branch",
            return_value="feat/x",
        ):
            id1 = ensure_context(db_path=db)
            id2 = ensure_context(db_path=db)
        assert id1 == id2

    def test_opens_new_context_on_branch_change(self, db):
        with patch(
            "tokenledger.context.tracker.detect_git_branch",
            return_value="feat/x",
        ):
            id1 = ensure_context(db_path=db)

        with patch(
            "tokenledger.context.tracker.detect_git_branch",
            return_value="feat/y",
        ):
            id2 = ensure_context(db_path=db)

        assert id2 > id1
        ctx = get_open_context(db)
        assert ctx["name"] == "feat/y"


class TestManualContext:
    def test_set_manual_context(self, db):
        ctx_id = set_manual_context("sprint-5", db)
        ctx = get_open_context(db)
        assert ctx["name"] == "sprint-5"
        assert ctx["source"] == "manual"

    def test_clear_context(self, db):
        set_manual_context("sprint-5", db)
        clear_context(db)
        assert get_open_context(db) is None
