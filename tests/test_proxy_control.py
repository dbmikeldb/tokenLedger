"""Tests for proxy control routes, including /control/workspace."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

import tokenledger.proxy.server as srv


@pytest.fixture(autouse=True)
def reset_proxy_globals(tmp_path):
    """Restore module-level globals after each test."""
    orig_cwd = srv._workspace_cwd
    orig_override = srv._manual_override
    orig_db = srv._db_path

    db_path = str(tmp_path / "test.db")
    from tokenledger.storage.db import init_db
    init_db(db_path)
    srv._db_path = db_path

    yield

    srv._workspace_cwd = orig_cwd
    srv._manual_override = orig_override
    srv._db_path = orig_db


@pytest.mark.anyio
async def test_workspace_route_updates_cwd():
    async with AsyncClient(
        transport=ASGITransport(app=srv.app), base_url="http://test"
    ) as client:
        resp = await client.post("/control/workspace", json={"cwd": "/tmp/myrepo"})
    assert resp.status_code == 200
    assert resp.json()["workspace_cwd"] == "/tmp/myrepo"
    assert srv._workspace_cwd == "/tmp/myrepo"


@pytest.mark.anyio
async def test_workspace_route_rejects_empty_cwd():
    async with AsyncClient(
        transport=ASGITransport(app=srv.app), base_url="http://test"
    ) as client:
        resp = await client.post("/control/workspace", json={"cwd": ""})
    assert resp.status_code == 400
    assert "cwd required" in resp.json()["error"]


@pytest.mark.anyio
async def test_workspace_route_rejects_missing_cwd_key():
    async with AsyncClient(
        transport=ASGITransport(app=srv.app), base_url="http://test"
    ) as client:
        resp = await client.post("/control/workspace", json={})
    assert resp.status_code == 400
    assert "cwd required" in resp.json()["error"]
