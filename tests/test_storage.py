"""Tests for tokenledger.storage.db."""

import pytest
from tokenledger.storage.db import (
    close_context,
    get_calls_for_context,
    get_context_summary,
    get_open_context,
    init_db,
    open_context,
    record_call,
)


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path)
    return path


class TestContextLifecycle:
    def test_open_and_retrieve(self, db):
        ctx_id = open_context("feat/auth", "git", db)
        ctx = get_open_context(db)
        assert ctx is not None
        assert ctx["name"] == "feat/auth"
        assert ctx["source"] == "git"
        assert ctx["id"] == ctx_id

    def test_close_context(self, db):
        ctx_id = open_context("feat/auth", "git", db)
        close_context(ctx_id, db)
        assert get_open_context(db) is None

    def test_most_recent_open_returned(self, db):
        open_context("first", "manual", db)
        close_context(1, db)
        open_context("second", "git", db)
        ctx = get_open_context(db)
        assert ctx["name"] == "second"

    def test_no_open_context_returns_none(self, db):
        assert get_open_context(db) is None


class TestCallRecording:
    def test_record_and_retrieve(self, db):
        ctx_id = open_context("feat/test", "git", db)
        record_call(
            context_id=ctx_id,
            model="claude-sonnet-4-20250514",
            input_tokens=500,
            output_tokens=200,
            input_cost=0.0015,
            output_cost=0.003,
            total_cost=0.0045,
            request_id="req_123",
            db_path=db,
        )
        calls = get_calls_for_context(ctx_id, db)
        assert len(calls) == 1
        assert calls[0]["model"] == "claude-sonnet-4-20250514"
        assert calls[0]["input_tokens"] == 500
        assert calls[0]["request_id"] == "req_123"

    def test_call_without_context(self, db):
        record_call(
            context_id=None,
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
            input_cost=0.0001,
            output_cost=0.0002,
            total_cost=0.0003,
            request_id=None,
            db_path=db,
        )
        calls = get_calls_for_context(None, db)
        assert len(calls) == 1


class TestSummaryQuery:
    def test_summary_aggregates_correctly(self, db):
        ctx_id = open_context("feat/x", "git", db)
        for i in range(3):
            record_call(
                context_id=ctx_id,
                model="claude-sonnet-4-20250514",
                input_tokens=100,
                output_tokens=50,
                input_cost=0.0003,
                output_cost=0.00075,
                total_cost=0.00105,
                request_id=None,
                db_path=db,
            )
        summaries = get_context_summary(db)
        assert len(summaries) == 1
        assert summaries[0]["call_count"] == 3
        assert abs(summaries[0]["total_cost"] - 0.00315) < 1e-9

    def test_empty_db_returns_no_summaries(self, db):
        assert get_context_summary(db) == []
