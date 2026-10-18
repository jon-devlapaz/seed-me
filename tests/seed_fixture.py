"""Shared fixture: the saved seed a session needs before `end --status completed`."""
import json
from pathlib import Path


def save_seed(session, directory, status_line=None):
    """Write `<session>/seed-contract.md` with the line 1 a completed session needs (confirmed, or simulated for a simulated session).

    A confirmed seed also gets the confirmation record `seed confirm` would write for the current decisions, so the
    session's own checks are what `end` tests. Tests that are about ledger behavior, not about confirmation, use this
    instead of running `seed confirm`. An explicit `status_line` is written as given, with no record.
    """
    directory = Path(directory)
    ledger = session.load(directory)
    record = status_line is None and ledger.get("operator", "human") == "human"
    if status_line is None:
        status_line = session.STATUS_CONFIRMED if record else session.STATUS_SIMULATED
    checks = [{"statement": "Fixture goal is met", "kind": "judge", "source": "TEST operator"}]
    session.set_checks(directory, checks)
    path = directory / session.SEED_FILE
    path.write_text(status_line + "\n# Seed contract: fixture\nrevision: r1        date: 2026-10-06\n\n## You are confirming\n- Goal: fixture\n\n"
                    + session.checks_block(checks) + session.decisions_block(ledger), encoding="utf-8")
    if record:
        digest = session.sha256(path.read_bytes())
        (directory / session.CONFIRMATION_FILE).write_text(json.dumps({
            "schema_version": 2, "checks_sha256": session.checks_digest(checks), "session_id": ledger["session_id"], "operator": "human", "revision": "r1",
            "source": "TEST fixture confirmation", "confirmed_at": "2026-10-06T00:00:00+00:00",
            "seed_sha256": digest, "decisions_sha256": session.decisions_digest(ledger)}))
