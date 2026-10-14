"""A completed handoff holds exactly the seed and decisions a human confirmed in that session (issue #3).

Every unsafe case runs through the real `session.py` CLI against temporary sessions. Each legitimate edit is saved
and checked first, so a failed setup can never count as a safe refusal.
"""

import importlib.util
import json
from pathlib import Path
import shutil
import unittest
from unittest import mock

from test_seed_me_strict_format import DRAFT, SESSION, SOURCE, SessionCase, decision, run

spec = importlib.util.spec_from_file_location("seed_me_session_integrity", SESSION)
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)

RECORD = "seed-confirmation.json"


class HandoffCase(SessionCase):
    def snapshot(self, directory):
        return {name: (directory / name).read_bytes() if (directory / name).exists() else None
                for name in ("seed-contract.md", "ledger.json", RECORD)}

    def status(self, directory):
        result = run("status", directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def confirm(self, directory, revision="r1", source=SOURCE, sha256=None):
        if sha256 is None:
            sha256 = self.status(directory)["seed"]["sha256"]
        return run("seed", "confirm", directory, "--revision", revision, "--source", source, "--sha256", sha256)

    def confirmed(self):
        directory = self.complete_human()
        self.write_seed(directory)
        result = self.confirm(directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        return directory

    def edit(self, directory, mutate, reason="A legitimate later edit"):
        """Publish a change through the CLI and prove it saved, so it is setup, not the refusal under test."""
        ledger = json.loads(run("read", directory).stdout)
        state = session.editable(ledger)
        mutate(state)
        payload = self.payloads / "edit.json"
        payload.write_text(json.dumps({"state": state, "expected_version": ledger["version"], "reason": reason}))
        result = run("publish", directory, payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(session.editable(json.loads(run("read", directory).stdout)), {**state, "assumed": state.get("assumed", [])})
        return result

    def refuse_completion(self, directory, pattern):
        before = self.snapshot(directory)
        result = self.end(directory)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertRegex(result.stderr, pattern)
        self.assertEqual(self.snapshot(directory), before)
        self.assertEqual(json.loads(run("read", directory).stdout)["status"], "active")


class CompletionRoutesTests(HandoffCase):
    def test_a_confirmed_unchanged_session_completes_and_verifies(self):
        directory = self.confirmed()
        result = self.end(directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.status(directory)["handoff"], {"verified": True, "reason": "revision r1 as confirmed"})

    def test_publish_cannot_complete_a_session(self):
        directory = self.complete_human()
        before = self.snapshot(directory)
        ledger = json.loads(run("read", directory).stdout)
        state = session.editable(ledger)
        state["status"] = "completed"
        payload = self.payloads / "complete.json"
        payload.write_text(json.dumps({"state": state, "expected_version": ledger["version"], "reason": "Skip the seed"}))
        result = run("publish", directory, payload)
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stderr, r"publish cannot complete")
        self.assertEqual(self.snapshot(directory), before)

    def test_publish_cannot_complete_even_a_confirmed_session(self):
        directory = self.confirmed()
        before = self.snapshot(directory)
        ledger = json.loads(run("read", directory).stdout)
        state = session.editable(ledger)
        state["status"] = "completed"
        payload = self.payloads / "complete.json"
        payload.write_text(json.dumps({"state": state, "expected_version": ledger["version"], "reason": "Bypass end"}))
        self.assertEqual(run("publish", directory, payload).returncode, 1)
        self.assertEqual(self.snapshot(directory), before)

    def test_missing_seed_is_refused(self):
        directory = self.complete_human()
        self.refuse_completion(directory, r"seed-contract\.md")


class StaleConfirmationTests(HandoffCase):
    def test_a_changed_decision_needs_renewed_confirmation(self):
        directory = self.confirmed()
        self.edit(directory, lambda s: s["nodes"][1].update(answer="A different answer"))
        self.refuse_completion(directory, r"decisions changed after revision r1")

    def test_a_new_assumption_needs_renewed_confirmation(self):
        directory = self.confirmed()
        self.edit(directory, lambda s: s.update(assumed=[{"text": "Remote export", "why": "TEST change"}]))
        self.refuse_completion(directory, r"decisions changed")

    def test_an_added_settled_decision_needs_renewed_confirmation(self):
        directory = self.confirmed()
        revision = json.loads(run("read", directory).stdout)["revision"]
        self.edit(directory, lambda s: s["nodes"].append(decision("d2", "user", ["goal"], answer="Keep 30 days")))
        self.assertEqual(json.loads(run("read", directory).stdout)["revision"], revision, "premise counter did not move")
        self.refuse_completion(directory, r"decisions changed")

    def test_a_changed_draft_outcome_needs_renewed_confirmation(self):
        directory = self.confirmed()
        self.edit(directory, lambda s: s["draft"].update(outcome="A different outcome"))
        self.refuse_completion(directory, r"decisions changed")

    def test_an_edited_seed_that_keeps_its_label_is_refused(self):
        directory = self.confirmed()
        path = directory / "seed-contract.md"
        path.write_bytes(path.read_bytes().replace(b"a fixture goal", b"another goal"))
        self.refuse_completion(directory, r"seed changed after revision r1")

    def test_another_sessions_confirmed_seed_is_refused(self):
        directory = self.complete_human()
        other = self.confirmed()
        shutil.copy(other / "seed-contract.md", directory / "seed-contract.md")
        self.refuse_completion(directory, r"no confirmation record")
        shutil.copy(other / RECORD, directory / RECORD)
        self.refuse_completion(directory, r"another session")

    def test_a_label_edited_between_display_and_confirmation_is_refused(self):
        directory = self.complete_human()
        path = self.write_seed(directory)
        displayed = self.status(directory)["seed"]["sha256"]
        path.write_bytes(path.read_bytes().replace(b"a fixture goal", b"something else"))
        before = self.snapshot(directory)
        result = self.confirm(directory, sha256=displayed)
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stderr, r"changed after it was displayed")
        self.assertEqual(self.snapshot(directory), before)

    def test_reconfirming_a_new_revision_restores_completion(self):
        directory = self.confirmed()
        self.edit(directory, lambda s: s["nodes"][1].update(answer="A different answer"))
        self.write_seed(directory, revision="r2")
        self.assertEqual(self.confirm(directory, revision="r2").returncode, 0)
        result = self.end(directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.status(directory)["handoff"]["reason"], "revision r2 as confirmed")


class ValidFlowControlsTests(HandoffCase):
    def test_an_exact_republish_and_a_repeated_end_keep_the_approval(self):
        directory = self.confirmed()
        ledger = json.loads(run("read", directory).stdout)
        payload = self.payloads / "same.json"
        payload.write_text(json.dumps({"state": session.editable(ledger), "expected_version": ledger["version"], "reason": "Retry"}))
        self.assertEqual(run("publish", directory, payload).returncode, 0)
        self.assertEqual(json.loads(run("read", directory).stdout)["version"], ledger["version"])
        self.assertEqual(self.end(directory).returncode, 0)
        self.assertEqual(self.end(directory).returncode, 0)

    def test_status_and_the_viewer_record_do_not_invalidate_the_approval(self):
        directory = self.confirmed()
        self.status(directory)
        (directory / "viewer.json").write_text(json.dumps({"declined": "TEST", "at": "2026-10-06"}))
        self.assertTrue(self.status(directory)["handoff"]["verified"])

    def test_a_moved_intact_session_still_completes(self):
        directory = self.confirmed()
        moved = directory.parent.parent / "moved" / directory.name
        moved.parent.mkdir()
        shutil.move(directory, moved)
        result = self.end(moved)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.status(moved)["handoff"]["verified"])

    def test_a_simulated_session_completes_and_is_never_verified_as_human(self):
        directory = self.complete_simulated()
        self.write_seed(directory, "status: simulated")
        self.assertEqual(self.end(directory).returncode, 0)
        handoff = self.status(directory)["handoff"]
        self.assertFalse(handoff["verified"])
        self.assertRegex(handoff["reason"], "simulated")


class ReadOnlyVerificationTests(HandoffCase):
    def test_a_seed_edited_after_completion_is_reported_without_changing_files(self):
        directory = self.confirmed()
        self.assertEqual(self.end(directory).returncode, 0)
        path = directory / "seed-contract.md"
        path.write_bytes(path.read_bytes() + b"- Also: an unconfirmed line\n")
        before = self.snapshot(directory)
        handoff = self.status(directory)["handoff"]
        self.assertEqual(handoff, {"verified": False, "reason": "the seed changed after revision r1 was confirmed"})
        self.assertEqual(self.snapshot(directory), before)

    def test_a_legacy_confirmed_seed_is_unverified_and_left_alone(self):
        directory = self.complete_human()
        self.write_seed(directory, "status: confirmed for intake")
        before = self.snapshot(directory)
        self.assertRegex(self.status(directory)["handoff"]["reason"], "no confirmation record")
        self.assertEqual(self.snapshot(directory), before)
        self.refuse_completion(directory, r"no confirmation record.*confirm it again")

    def test_a_malformed_record_is_no_record(self):
        directory = self.confirmed()
        (directory / RECORD).write_text('{"session_id": "x"}')
        self.refuse_completion(directory, r"no confirmation record")


class WriteBoundaryTests(HandoffCase):
    def draft(self):
        directory = self.complete_human()
        path = self.write_seed(directory)
        return directory, session.sha256(path.read_bytes())

    def test_a_failed_seed_write_leaves_a_draft_that_cannot_complete_and_can_be_retried(self):
        directory, displayed = self.draft()
        real = session.atomic_write_text

        def fail_on_seed(path, content, mode=None):
            if Path(path).name == "seed-contract.md":
                raise OSError("TEST fault writing the seed")
            return real(path, content, mode)

        with mock.patch.object(session, "atomic_write_text", side_effect=fail_on_seed):
            with self.assertRaises(OSError):
                session.confirm_seed(directory, "r1", SOURCE, displayed)
        self.assertEqual((directory / "seed-contract.md").read_text().split("\n")[0], DRAFT)
        self.assertFalse(session.verify_handoff(directory)["verified"])
        self.assertEqual(self.confirm(directory).returncode, 0)
        self.assertEqual(self.end(directory).returncode, 0)

    def test_a_failed_record_write_changes_nothing(self):
        directory, displayed = self.draft()
        before = self.snapshot(directory)
        real = session.atomic_write_text

        def fail_on_record(path, content, mode=None):
            if Path(path).name == RECORD:
                raise OSError("TEST fault writing the record")
            return real(path, content, mode)

        with mock.patch.object(session, "atomic_write_text", side_effect=fail_on_record):
            with self.assertRaises(OSError):
                session.confirm_seed(directory, "r1", SOURCE, displayed)
        self.assertEqual(self.snapshot(directory), before)

    def test_a_competing_writer_blocks_confirmation(self):
        directory, displayed = self.draft()
        before = self.snapshot(directory)
        with session.writer(directory):
            with self.assertRaisesRegex(ValueError, "already has a writer"):
                session.confirm_seed(directory, "r1", SOURCE, displayed)
        self.assertEqual(self.snapshot(directory), before)


class DocsTests(unittest.TestCase):
    def test_the_documented_confirm_command_passes_the_displayed_sha256(self):
        skill = (SESSION.parents[1] / "SKILL.md").read_text(encoding="utf-8")
        command = next(line for line in skill.splitlines() if "session.py\" seed confirm" in line)
        self.assertIn("--sha256", command)


if __name__ == "__main__":
    unittest.main()
