from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_seed_me_session import session, node, SCRIPT


class TestDelegatedOrigin(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="TEST-seed-delegation-")
        self.addCleanup(self.temp.cleanup)
        self.directory = session.create(Path(self.temp.name))
        self.state = session.editable(session.load(self.directory))
        self.delegation = {
            "agent": "TEST agent Claude",
            "authorizing_operator": "TEST operator",
            "authorization_source": 'TEST chat turn 7: "confirm this TEST goal for me"\nExact second line.',
            "door": "two-way",
            "blast_radius": "small",
        }
        goal = node("goal", answer="Investigate a TEST fixture")
        goal.update(authority="delegated", authority_source="TEST agent confirmation turn 8",
                    evidence=["TEST fixture:1: throwaway goal"], delegation=deepcopy(self.delegation))
        self.state.update(goal=goal["answer"], origin="goal", nodes=[goal])

    def publish(self, state=None):
        return session.publish(self.directory, self.state if state is None else state,
                               session.load(self.directory)["version"], "TEST goal confirmation")

    def test_official_cli_publication_and_readback_preserve_exact_attribution(self):
        payload = self.directory / "update.json"
        payload.write_text(json.dumps({"expected_version": 0, "state": self.state, "reason": "TEST delegation"}))
        result = subprocess.run([sys.executable, str(SCRIPT), "publish", str(self.directory), str(payload)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([sys.executable, str(SCRIPT), "read", str(self.directory), "--editable"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        root = json.loads(result.stdout)["state"]["nodes"][0]
        self.assertEqual(root, self.state["nodes"][0])
        self.assertEqual(root["authority"], "delegated")
        self.assertEqual(root["delegation"], self.delegation)
        block = session.decisions_block(session.load(self.directory))
        self.assertIn("[delegated]", block)
        self.assertIn(json.dumps(self.delegation, ensure_ascii=False, sort_keys=True), block)
        self.assertNotIn("[user]", block)

    def test_missing_or_blank_delegation_fields_are_refused_without_writes(self):
        before = (self.directory / "ledger.json").read_bytes()
        for field in self.delegation:
            for bad in (None, "", " ", 7):
                with self.subTest(field=field, bad=bad):
                    state = deepcopy(self.state)
                    if bad is None:
                        del state["nodes"][0]["delegation"][field]
                    else:
                        state["nodes"][0]["delegation"][field] = bad
                    with self.assertRaises(ValueError):
                        self.publish(state)
                    self.assertEqual((self.directory / "ledger.json").read_bytes(), before)

    def test_missing_delegation_and_ineligible_classes_are_refused(self):
        for delegation in (None, {}, "TEST authorization", {**self.delegation, "door": "one-way"},
                           {**self.delegation, "blast_radius": "large"},
                           {**self.delegation, "extra": "not supported"}):
            with self.subTest(delegation=delegation):
                self.directory = session.create(self.directory.parent)
                state = deepcopy(self.state)
                if delegation is None:
                    del state["nodes"][0]["delegation"]
                else:
                    state["nodes"][0]["delegation"] = delegation
                with self.assertRaises(ValueError):
                    self.publish(state)

    def test_delegation_cannot_be_labeled_user_or_simulated_or_attached_elsewhere(self):
        for authority in ("user", "simulated"):
            state = deepcopy(self.state)
            state["nodes"][0]["authority"] = authority
            if authority == "simulated":
                state["operator"] = "simulated"
            with self.subTest(authority=authority), self.assertRaises(ValueError):
                session.validate(state)
        state = deepcopy(self.state)
        state["nodes"][0].update(authority="user")
        delegation = state["nodes"][0].pop("delegation")
        other = node("other", answer="TEST ordinary choice")
        other.update(authority="delegated", evidence=["TEST evidence"], delegation=delegation)
        state["nodes"].append(other)
        with self.assertRaises(ValueError):
            self.publish(state)

    def test_published_agent_cannot_be_relabelled_as_operator(self):
        saved = self.publish()
        state = session.editable(saved)
        state["nodes"][0].update(authority="user", authority_source="operator typed confirm")
        state["nodes"][0].pop("delegation")
        with self.assertRaisesRegex(ValueError, "origin.*attribution"):
            self.publish(state)
        self.assertEqual(session.load(self.directory), saved)

    def test_published_delegation_cannot_be_replaced(self):
        saved = self.publish()
        for field in self.delegation:
            state = session.editable(saved)
            state["nodes"][0]["delegation"][field] += " changed"
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.publish(state)
        self.assertEqual(session.load(self.directory), saved)

    def test_readback_refuses_missing_or_ineligible_stored_delegation(self):
        saved = self.publish()
        for field in self.delegation:
            bad = deepcopy(saved)
            del bad["nodes"][0]["delegation"][field]
            session.atomic_write(self.directory / "ledger.json", bad)
            with self.subTest(field=field), self.assertRaises(ValueError):
                session.load(self.directory)
        bad = deepcopy(saved)
        bad["nodes"][0]["delegation"]["door"] = "one-way"
        session.atomic_write(self.directory / "ledger.json", bad)
        with self.assertRaises(ValueError):
            session.load(self.directory)

    def test_user_origin_readback_and_decisions_remain_unchanged(self):
        state = deepcopy(self.state)
        root = state["nodes"][0]
        root.pop("delegation")
        root.update(authority="user", authority_source="TEST operator explicitly confirmed", evidence=[])
        saved = self.publish(state)
        before = (self.directory / "ledger.json").read_bytes()
        self.assertEqual(session.editable(session.load(self.directory)), state)
        self.assertEqual(session.load(self.directory), saved)
        self.assertEqual((self.directory / "ledger.json").read_bytes(), before)
        self.assertEqual(session.decisions_block(saved),
                         "## Decisions (from the ledger)\n"
                         "- goal [user] Investigate a TEST fixture (source: TEST operator explicitly confirmed)\n"
                         "\n## Assumed (not confirmed by you)\n- none\n")

    def test_seed_receipt_remains_separate_and_covers_delegation_bytes(self):
        import seed_fixture
        saved = self.publish()
        seed_fixture.save_seed(session, self.directory)
        self.assertTrue(session.status(self.directory)["handoff"]["verified"])
        receipt = json.loads((self.directory / session.CONFIRMATION_FILE).read_text())
        self.assertEqual(set(receipt), session.CONFIRMATION_FIELDS)
        self.assertEqual(receipt["source"], "TEST fixture confirmation")
        self.assertNotEqual(receipt["source"], self.delegation["authorization_source"])
        saved["nodes"][0]["delegation"]["authorization_source"] += " changed"
        self.assertNotEqual(session.decisions_digest(saved), receipt["decisions_sha256"])
        session.atomic_write(self.directory / "ledger.json", saved)
        self.assertFalse(session.status(self.directory)["handoff"]["verified"])

    def test_goal_delegation_is_not_seed_confirmation_or_implementation_permission(self):
        self.publish()
        status = session.status(self.directory)
        self.assertFalse(status["handoff"]["verified"])
        self.assertFalse((self.directory / session.CONFIRMATION_FILE).exists())
        with self.assertRaises(ValueError):
            session.end(self.directory, "completed", "TEST goal alone", no_viewer="TEST no viewer")
