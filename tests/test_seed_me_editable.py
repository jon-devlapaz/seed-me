"""`read --editable` is the supported start of every publication (issue #5).

Runs the real CLI against temporary sessions, including the documented SKILL.md commands as written.
"""

import json
import re
import subprocess
import sys

from test_seed_me_strict_format import SKILL, SessionCase, decision, run

HELPER_FIELDS = {"history", "revision", "premise_version", "reviewed_version"}


class EditableReadTests(SessionCase):
    def counters(self):
        """A session whose nodes already carry every helper-owned counter."""
        directory = self.complete_human([decision("goal", "user", answer="Ship a fixture"),
                                         decision("d1", "user", ["goal"])])
        nodes = json.loads(run("read", directory).stdout)["nodes"]
        self.assertTrue(all(HELPER_FIELDS <= set(n) for n in nodes), nodes)
        return directory

    def editable(self, directory):
        result = run("read", directory, "--editable")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def publish_payload(self, directory, payload):
        path = self.payloads / "update.json"
        path.write_text(json.dumps(payload))
        return run("publish", directory, path)

    def test_the_old_two_field_recipe_fails_and_names_the_fields(self):
        directory = self.counters()
        ledger = json.loads(run("read", directory).stdout)
        state = {k: ledger[k] for k in ("status", "draft", "goal", "origin", "current_question", "nodes")}
        for node in state["nodes"]:
            node.pop("history"), node.pop("revision")
        result = self.publish_payload(directory, {"state": state, "expected_version": ledger["version"], "reason": "Old recipe"})
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stderr, r"premise_version, reviewed_version.*read --editable")

    def test_two_publications_in_a_row_work_from_editable_reads(self):
        directory = self.counters()
        for outcome in ("First changed outcome", "Second changed outcome"):
            payload = self.editable(directory)
            payload["state"]["draft"]["outcome"] = outcome
            payload["reason"] = "Recorded " + outcome
            result = self.publish_payload(directory, payload)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(run("read", directory).stdout)["draft"]["outcome"], outcome)

    def test_editable_output_has_every_editable_field_and_no_helper_field(self):
        directory = self.counters()
        payload = self.editable(directory)
        version = json.loads(run("read", directory).stdout)["version"]
        self.assertEqual(set(payload), {"expected_version", "state"})
        self.assertEqual(payload["expected_version"], version)
        self.assertEqual(set(payload["state"]), {"status", "draft", "goal", "origin", "current_question", "nodes",
                                                 "assumed", "operator"})
        self.assertFalse(any(HELPER_FIELDS & set(n) for n in payload["state"]["nodes"]))

    def test_assumptions_and_operator_survive_the_round_trip(self):
        directory = self.counters()
        payload = self.editable(directory)
        payload["state"]["assumed"] = [{"text": "Local only", "why": "TEST assumption"}]
        payload["reason"] = "Record an assumption"
        self.assertEqual(self.publish_payload(directory, payload).returncode, 0)
        again = self.editable(directory)
        self.assertEqual(again["state"]["assumed"], [{"text": "Local only", "why": "TEST assumption"}])
        self.assertEqual(again["state"]["operator"], "human")

    def test_reading_changes_no_files_and_plain_read_is_unchanged(self):
        directory = self.counters()
        before = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
        plain = run("read", directory).stdout
        self.editable(directory)
        self.assertEqual({p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}, before)
        self.assertEqual(json.loads(plain), json.loads((directory / "ledger.json").read_text()))

    def test_an_unchanged_round_trip_is_a_no_op(self):
        directory = self.counters()
        payload = self.editable(directory)
        payload["reason"] = "Nothing changed"
        before = (directory / "ledger.json").read_bytes()
        self.assertEqual(self.publish_payload(directory, payload).returncode, 0)
        self.assertEqual((directory / "ledger.json").read_bytes(), before)

    def test_stale_duplicate_and_helper_owned_writes_are_still_refused(self):
        directory = self.counters()
        cases = {
            "stale": (lambda p: p.update(expected_version=p["expected_version"] - 1) or p["state"]["draft"].update(outcome="x"),
                      r"stale"),
            "duplicate id": (lambda p: p["state"]["nodes"].append(dict(p["state"]["nodes"][1])), r"duplicate node id"),
            "helper field": (lambda p: p["state"]["nodes"][1].update(history=[]), r"invalid node fields: history"),
            "simulated authority": (lambda p: p["state"]["nodes"][1].update(authority="simulated"), r"authority"),
        }
        for label, (damage, pattern) in cases.items():
            with self.subTest(label):
                payload = self.editable(directory)
                payload["reason"] = "TEST " + label
                damage(payload)
                before = (directory / "ledger.json").read_bytes()
                result = self.publish_payload(directory, payload)
                self.assertEqual(result.returncode, 1)
                self.assertRegex(result.stderr, pattern)
                self.assertEqual((directory / "ledger.json").read_bytes(), before)


class DocumentedCommandsTests(SessionCase):
    def test_the_skill_md_read_and_publish_commands_run_as_written(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        block = next(b for b in re.findall(r"```sh\n(.*?)```", text, re.S) if "--editable" in b)
        lines = [line.strip() for line in block.strip().splitlines()]
        self.assertEqual(len(lines), 2, lines)
        directory = self.complete_human([decision("goal", "user", answer="Ship a fixture"), decision("d1", "user", ["goal"])])

        def shell(line):
            line = line.replace("<skill>", str(SKILL)).replace("<session>", str(directory)).replace("python3", sys.executable, 1)
            return subprocess.run(["sh", "-c", line], capture_output=True, text=True)

        for outcome in ("Edited once", "Edited twice"):
            read = shell(lines[0])
            self.assertEqual(read.returncode, 0, read.stderr)
            update = directory / "update.json"
            payload = json.loads(update.read_text())
            payload["state"]["draft"]["outcome"] = outcome
            payload["reason"] = "Documented flow: " + outcome
            update.write_text(json.dumps(payload))
            published = shell(lines[1])
            self.assertEqual(published.returncode, 0, published.stderr)
            self.assertEqual(json.loads(run("read", directory).stdout)["draft"]["outcome"], outcome)
