"""The web UI's approval workflow survives a server restart.

Each step runs the real FastAPI app in a fresh Python process pointed at the
same state file, so nothing carries over in memory: a run started by one
"server" is listed, approved and then refused a second decision by later ones.

Skipped when the `ui` extra is not installed, which is the case in CI by
design (pyproject.toml keeps the web layer out of the gates). Run it locally
with `pip install -e .[ui]`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

REPO = Path(__file__).resolve().parents[1]


def _server_process(db: Path, body: str) -> dict:
    """One 'server lifetime': import the app against `db`, run `body`, exit."""
    script = textwrap.dedent(
        """
            import json, sys
            from fastapi.testclient import TestClient
            from ui.api.app import app
            client = TestClient(app)
            """
    ) + textwrap.dedent(body)
    env = {**os.environ, "DOCKET_UI_STATE_DB": str(db), "GROQ_API_KEY": ""}
    done = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=REPO,
        env=env,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_a_run_started_before_a_restart_is_approved_after_it(tmp_path: Path) -> None:
    db = tmp_path / "docket-ui.sqlite"

    started = _server_process(
        db,
        """
        r = client.post("/api/runs", json={
            "purchase_order": "4507000477", "purchase_order_item": "00060",
            "mode": "deterministic"})
        assert r.status_code == 200, r.text
        print(json.dumps({"run_id": r.json()["run_id"], "status": r.json()["status"],
                          "durable": client.get("/api/meta").json()["persistence"]["durable"]}))
        """,
    )
    assert started["status"] == "awaiting_approval"
    assert started["durable"] is True
    run_id = started["run_id"]

    decided = _server_process(
        db,
        f"""
        listed = [r["run_id"] for r in client.get("/api/runs").json()["runs"]]
        r = client.post("/api/runs/{run_id}/decision", json={{
            "decision": "approve", "approver": "user_approver",
            "reason": "reviewed supporting evidence"}})
        assert r.status_code == 200, r.text
        print(json.dumps({{"listed": listed, "status": r.json()["run"]["status"],
                          "memory_record": r.json()["memory_record"] is not None}}))
        """,
    )
    assert decided == {"listed": [run_id], "status": "approved", "memory_record": True}

    after = _server_process(
        db,
        f"""
        run = client.get("/api/runs/{run_id}").json()
        again = client.post("/api/runs/{run_id}/decision", json={{
            "decision": "approve", "approver": "user_approver", "reason": "twice"}})
        memory = client.get("/api/memory/vendorID_0103").json()["records"]
        print(json.dumps({{"status": run["status"], "second": again.status_code,
                          "memory": len(memory)}}))
        """,
    )
    assert after == {"status": "approved", "second": 409, "memory": 1}


def test_memory_mode_is_still_available_and_says_so(tmp_path: Path) -> None:
    meta = _server_process(
        Path("memory"),
        """
        print(json.dumps(client.get("/api/meta").json()["persistence"]))
        """,
    )
    assert meta["durable"] is False
    assert "lost when the server stops" in meta["note"]
