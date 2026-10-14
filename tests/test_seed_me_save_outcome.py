"""`publish` and `end` report what is durable when a write fails (issue #4).

Each case runs the real CLI in a subprocess with one fault injected at a write boundary, and asserts stdout, the
stderr diagnostic and the exit status. Temporary sessions only.
"""

import json
from pathlib import Path
import subprocess
import sys
import textwrap

from test_seed_me_strict_format import SESSION, SessionCase, decision, run

HARNESS = textwrap.dedent('''
    import sys
    sys.path.insert(0, sys.argv[1])
    import session
    fault, args = sys.argv[2], sys.argv[3:]
    real_text, real_load = session.atomic_write_text, session.load
    if fault == "view":
        def write_snapshot(directory):
            raise OSError("TEST fault saving the view")
        session.write_snapshot = write_snapshot
    elif fault in ("ledger", "ledger-unreadable"):
        def atomic_write(path, ledger):
            raise OSError("TEST fault before replacing the ledger")
        session.atomic_write = atomic_write
        if fault == "ledger-unreadable":
            calls = []
            def load(directory):
                calls.append(1)
                if len(calls) > 1:
                    raise OSError("TEST fault reading the ledger back")
                return real_load(directory)
            session.load = load
    sys.argv = ["session.py"] + args
    session.main()
''')


class SaveOutcomeCase(SessionCase):
    def setUp(self):
        super().setUp()
        self.harness = Path(self.temp.name) / "harness.py"
        self.harness.write_text(HARNESS)

    def faulted(self, fault, *args):
        return subprocess.run([sys.executable, str(self.harness), str(SESSION.parent), fault] + [str(a) for a in args],
                              capture_output=True, text=True)

    def session(self):
        return self.complete_human([decision("goal", "user", answer="Ship a fixture"), decision("d1", "user", ["goal"])])

    def change(self, directory, outcome="A changed outcome"):
        ledger = json.loads(run("read", directory).stdout)
        edit = json.loads(run("read", directory, "--editable").stdout)
        edit["state"]["draft"]["outcome"] = outcome
        edit["reason"] = "Recorded a change"
        payload = self.payloads / "change.json"
        payload.write_text(json.dumps(edit))
        return payload, ledger

    def diagnostic(self, stderr):
        lines = stderr.strip().splitlines()
        self.assertGreaterEqual(len(lines), 2, stderr)
        return lines[0], json.loads(lines[-1])

    def status(self, directory):
        return json.loads(run("status", directory).stdout)


class SavedButViewFailedTests(SaveOutcomeCase):
    def test_publish_reports_saved_with_a_repair_command_and_exits_zero(self):
        directory = self.session()
        payload, before = self.change(directory)
        result = self.faulted("view", "publish", directory, payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["version"], before["version"] + 1)
        message, diag = self.diagnostic(result.stderr)
        self.assertRegex(message, r"saved version %d, but the view was not saved" % (before["version"] + 1))
        self.assertEqual({k: diag[k] for k in ("save_state", "version", "view_state")},
                         {"save_state": "saved", "version": before["version"] + 1, "view_state": "stale"})
        self.assertEqual(diag["session"], str(directory))
        self.assertIn("viewer.py", diag["next_action"])
        self.assertFalse(self.status(directory)["snapshot_current"])

    def test_an_identical_retry_repairs_the_view_without_another_publication(self):
        directory = self.session()
        payload, _ = self.change(directory)
        self.assertEqual(self.faulted("view", "publish", directory, payload).returncode, 0)
        saved = json.loads(run("read", directory).stdout)
        retry = run("publish", directory, payload)
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertEqual(retry.stderr, "")
        self.assertEqual(json.loads(run("read", directory).stdout), saved)
        self.assertTrue(self.status(directory)["snapshot_current"])

    def test_the_documented_repair_command_works(self):
        directory = self.session()
        payload, _ = self.change(directory)
        self.faulted("view", "publish", directory, payload)
        repair = run_viewer_snapshot(directory)
        self.assertEqual(repair.returncode, 0, repair.stderr)
        self.assertTrue(self.status(directory)["snapshot_current"])

    def test_end_reports_completion_saved_and_a_repair_changes_no_answer(self):
        directory = self.session()
        result = self.faulted("view", "end", directory, "--status", "stopped", "--reason", "Fixture stop", "--no-viewer", "not under test")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "stopped")
        self.assertEqual(self.diagnostic(result.stderr)[1]["save_state"], "saved")
        stopped = json.loads(run("read", directory).stdout)
        repeat = self.end(directory, "stopped")
        self.assertEqual(repeat.returncode, 0, repeat.stderr)
        self.assertEqual(json.loads(run("read", directory).stdout), stopped)
        self.assertTrue(self.status(directory)["snapshot_current"])


class NotSavedTests(SaveOutcomeCase):
    def test_a_fault_before_the_ledger_is_replaced_keeps_the_old_ledger(self):
        directory = self.session()
        payload, before = self.change(directory)
        ledger_bytes = (directory / "ledger.json").read_bytes()
        result = self.faulted("ledger", "publish", directory, payload)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        _, diag = self.diagnostic(result.stderr)
        self.assertEqual((diag["save_state"], diag["version"]), ("not_saved", before["version"]))
        self.assertEqual((directory / "ledger.json").read_bytes(), ledger_bytes)

    def test_a_refused_update_says_not_saved(self):
        directory = self.session()
        payload, _ = self.change(directory)
        data = json.loads(payload.read_text())
        data["expected_version"] -= 1
        payload.write_text(json.dumps(data))
        result = run("publish", directory, payload)
        self.assertEqual(result.returncode, 1)
        message, diag = self.diagnostic(result.stderr)
        self.assertRegex(message, "stale")
        self.assertEqual(diag["save_state"], "not_saved")

    def test_another_session_is_untouched(self):
        directory, other = self.session(), self.session()
        before = (other / "ledger.json").read_bytes()
        payload, _ = self.change(directory)
        self.faulted("view", "publish", directory, payload)
        self.faulted("ledger", "publish", directory, payload)
        self.assertEqual((other / "ledger.json").read_bytes(), before)


class UnknownTests(SaveOutcomeCase):
    def test_an_unreadable_outcome_is_never_reported_as_saved_or_not_saved(self):
        directory = self.session()
        payload, _ = self.change(directory)
        result = self.faulted("ledger-unreadable", "publish", directory, payload)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        _, diag = self.diagnostic(result.stderr)
        self.assertEqual((diag["save_state"], diag["version"], diag["view_state"]), ("unknown", None, "unknown"))
        self.assertIn("status", diag["next_action"])


class SuccessUnchangedTests(SaveOutcomeCase):
    def test_a_normal_publish_prints_the_ledger_and_nothing_on_stderr(self):
        directory = self.session()
        payload, _ = self.change(directory)
        result = run("publish", directory, payload)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(json.loads(result.stdout), json.loads((directory / "ledger.json").read_text()))


def run_viewer_snapshot(directory):
    return subprocess.run([sys.executable, str(SESSION.with_name("viewer.py")), str(directory), "--snapshot"],
                          capture_output=True, text=True)


class PythonPathTests(SaveOutcomeCase):
    def test_publish_raises_a_structured_outcome_that_carries_the_saved_result(self):
        import importlib.util
        from unittest import mock
        spec = importlib.util.spec_from_file_location("seed_me_session_outcome", SESSION)
        session = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(session)
        directory = self.session()
        ledger = session.load(directory)
        state = session.editable(ledger)
        state["draft"]["outcome"] = "Python path change"
        with mock.patch.object(session, "write_snapshot", side_effect=OSError("TEST fault")):
            with self.assertRaises(session.SaveOutcome) as caught:
                session.publish(directory, state, ledger["version"], "TEST")
        self.assertEqual((caught.exception.save_state, caught.exception.result["version"]), ("saved", ledger["version"] + 1))
        self.assertIsInstance(caught.exception, OSError)
