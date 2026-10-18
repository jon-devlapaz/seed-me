"""A session can run start to finish with no live viewer and no network socket (issue #6).

Every command runs through the real CLI in a subprocess where creating a socket raises and is counted.
"""

import json
from pathlib import Path
import subprocess
import sys
import textwrap

from test_seed_me_strict_format import SESSION, SessionCase, decision, run

HARNESS = textwrap.dedent('''
    import socket, sys
    sys.path.insert(0, sys.argv[1])
    import session
    def refuse(*args, **kwargs):
        with open(sys.argv[2], "a") as log:
            log.write("socket\\n")
        raise OSError("TEST: no sockets in a no-viewer session")
    socket.socket = refuse
    socket.create_connection = refuse
    sys.argv = ["session.py"] + sys.argv[3:]
    session.main()
''')


class NoViewerTests(SessionCase):
    def setUp(self):
        super().setUp()
        self.harness = Path(self.temp.name) / "harness.py"
        self.harness.write_text(HARNESS)
        self.sockets = Path(self.temp.name) / "sockets.log"

    def cli(self, *args):
        return subprocess.run([sys.executable, str(self.harness), str(SESSION.parent), str(self.sockets)]
                              + [str(a) for a in args], capture_output=True, text=True)

    def test_a_session_completes_with_no_viewer_and_no_socket(self):
        created = self.cli("init", "--root", self.root)
        self.assertEqual(created.returncode, 0, created.stderr)
        directory = Path(json.loads(created.stdout)["session"])
        checks = self.payloads / "checks.json"
        checks.write_text(json.dumps([{"statement": "Fixture goal is met", "kind": "judge", "source": "TEST operator"}]))
        result = self.cli("seed", "checks", "set", directory, checks)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.cli("seed", "checks", "show", directory).returncode, 0)
        self.assertEqual(self.cli("seed", "checks", "render", directory).returncode, 0)
        state = {"status": "active", "draft": {"goal": "Ship a fixture", "outcome": "A fixture outcome", "options": ["A: one"]},
                 "goal": "Ship a fixture", "origin": "goal", "current_question": None,
                 "nodes": [decision("goal", "user", answer="Ship a fixture"), decision("d1", "user", ["goal"])]}
        payload = self.payloads / "update.json"
        payload.write_text(json.dumps({"state": state, "expected_version": 0, "reason": "Recorded a fixture answer"}))
        self.assertEqual(self.cli("publish", directory, payload).returncode, 0)
        status = json.loads(self.cli("status", directory).stdout)
        self.assertEqual(status["viewer"], "not started")
        self.assertTrue(status["snapshot_current"], "a current saved view exists without a server")
        self.write_seed(directory)
        self.assertEqual(self.cli("seed", "confirm", directory, "--revision", "r1", "--source", "yes, confirm r1").returncode, 0)
        ended = self.cli("end", directory, "--status", "completed", "--reason", "Confirmed r1", "--no-viewer", "User chose no live viewer")
        self.assertEqual(ended.returncode, 0, ended.stderr)
        status = json.loads(self.cli("status", directory).stdout)
        self.assertEqual(status["viewer"], "declined: User chose no live viewer")
        self.assertTrue(status["handoff"]["verified"])
        self.assertTrue(status["snapshot_current"])
        self.assertFalse(self.sockets.exists(), "a no-viewer session opened a socket")

    def test_choosing_no_viewer_relaxes_no_completion_check(self):
        directory = self.complete_human([decision("goal", "user", answer="Ship a fixture"),
                                         decision("d1", "user", ["goal"], status="unresolved")])
        self.write_seed(directory, "status: confirmed for intake")
        for label, args in (("unresolved", ()), ("blank reason", ("--no-viewer", "  "))):
            with self.subTest(label):
                result = self.cli("end", directory, "--status", "completed", "--reason", "Try", *(args or ("--no-viewer", "User chose no live viewer")))
                self.assertEqual(result.returncode, 1)
        directory = self.complete_human()
        self.write_seed(directory, "status: confirmed for intake")
        result = self.cli("end", directory, "--status", "completed", "--reason", "Try", "--no-viewer", "User chose no live viewer")
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stderr, "no confirmation record")

    def test_without_a_viewer_or_a_reason_completion_is_still_refused(self):
        directory = self.complete_human()
        self.write_seed(directory)
        self.assertEqual(run("seed", "confirm", directory, "--revision", "r1", "--source", "yes").returncode, 0)
        result = run("end", directory, "--status", "completed", "--reason", "Try")
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stderr, "--no-viewer")


class NoViewerDocsTests(SessionCase):
    def test_the_lifecycle_names_a_truthful_no_viewer_reason_and_no_competing_startup_rule(self):
        skill = (SESSION.parents[1] / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn('"User chose no live viewer"', skill)
        self.assertNotIn("<why it could not run>", skill)
        lean = (SESSION.parents[1] / "references" / "lean-path.md").read_text(encoding="utf-8")
        self.assertIn("unless SKILL.md **Session lifecycle** step 2 says to skip it", lean)
