"""The seed's decisions come from the ledger, so the two files cannot disagree on what was decided (#9, F09).

The ledger owns every decision and assumption. `seed decisions` prints them as the seed's Decisions and Assumed
sections; `seed confirm` and completion refuse a seed that does not carry that output verbatim. Every case runs the real
`session.py` CLI against temporary sessions, and every refusal is checked to leave the files alone.
"""

import json
import unittest

from test_seed_me_strict_format import DRAFT, SIMULATED, SessionCase, decision, run


def deferred(node_id, parents=()):
    return {"id": node_id, "kind": "decision", "status": "deferred", "prerequisites": list(parents), "evidence": [],
            "owner": "project owner", "gate": "choose later", "defer_reason": "Not needed for the first slice",
            "revisit_condition": "a second user\nasks for it"}


class DecisionsCase(SessionCase):
    def edit(self, directory, mutate):
        """Publish a change through the CLI and prove it saved, so it is setup, not the refusal under test."""
        payload = json.loads(run("read", directory, "--editable").stdout)
        mutate(payload["state"])
        payload["reason"] = "A legitimate later edit"
        path = self.payloads / "edit.json"
        path.write_text(json.dumps(payload))
        result = run("publish", directory, path)
        self.assertEqual(result.returncode, 0, result.stderr)

    def refuse_confirm(self, directory, pattern, revision="r1"):
        before = self.snapshot(directory)
        result = self.confirm(directory, revision=revision)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertRegex(result.stderr, pattern)
        self.assertEqual(self.snapshot(directory), before)


class RenderTests(DecisionsCase):
    def test_the_block_lists_settled_and_deferred_decisions_and_assumptions_from_the_ledger(self):
        directory = self.complete_human([
            decision("goal", "user", answer="Ship a fixture"),
            decision("d1", "user", ["goal"], answer="Keep it local,\n  one machine"),
            deferred("d2", ["goal"]),
            {"id": "d3", "kind": "decision", "status": "superseded", "prerequisites": [], "evidence": [],
             "owner": "project owner", "gate": "replaced by d1"}])
        self.edit(directory, lambda s: s.update(assumed=[{"text": "Python 3.9 or later", "why": "already required"}]))
        ledger = (directory / "ledger.json").read_bytes()
        self.assertEqual(self.decisions(directory), "\n".join([
            "## Decisions (from the ledger)",
            '- goal [user] Ship a fixture (source: chat: "an explicit answer")',
            '- d1 [user] Keep it local, one machine (source: chat: "an explicit answer") (after: goal)',
            "- d2 deferred: Not needed for the first slice (revisit if: a second user asks for it) (after: goal)",
            "",
            "## Assumed (not confirmed by you)",
            "- Python 3.9 or later (why: already required)",
            ""]))
        self.assertEqual((directory / "ledger.json").read_bytes(), ledger, "printing the block changed the ledger")

    def test_no_assumptions_is_said_once(self):
        directory = self.complete_human()
        self.assertTrue(self.decisions(directory).endswith("## Assumed (not confirmed by you)\n- none\n"))


class ConfirmTests(DecisionsCase):
    def test_a_seed_carrying_the_current_block_confirms_and_completes(self):
        directory = self.complete_human()
        self.write_seed(directory)
        self.assertEqual(self.confirm(directory).returncode, 0)
        result = self.end(directory)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_new_draft_with_the_old_decision_line_is_refused_naming_it(self):
        """The dogfood case: D1 changed after r1 was confirmed; r2 updated its prose but not its D1 line."""
        directory = self.complete_human()
        self.write_seed(directory)
        self.assertEqual(self.confirm(directory).returncode, 0)
        stale = self.decisions(directory)
        self.edit(directory, lambda s: s["nodes"][1].update(answer="A different answer"))
        path = directory / "seed-contract.md"
        path.write_bytes(path.read_bytes().split(b"\n## Decisions (from the ledger)")[0]
                         .replace(b"status: confirmed for intake", DRAFT.encode(), 1)
                         .replace(b"revision: r1", b"revision: r2", 1) + b"\n" + stale.encode())
        path.write_bytes(b"\n".join(line for line in path.read_bytes().split(b"\n") if not line.startswith(b"Confirmed by:")))
        self.refuse_confirm(directory, r"cannot confirm: the seed's decisions do not match the ledger \(not current: d1\)"
                            r".*seed decisions", revision="r2")

    def test_an_assumption_missing_from_the_seed_is_refused_naming_it(self):
        directory = self.complete_human()
        self.write_seed(directory)
        self.edit(directory, lambda s: s.update(assumed=[{"text": "Remote export", "why": "TEST change"}]))
        self.refuse_confirm(directory, r"not current: assumed 'Remote export'")

    def test_a_seed_with_no_block_is_refused_naming_every_entry(self):
        directory = self.complete_human()
        path = self.write_seed(directory)
        path.write_bytes(path.read_bytes().split(b"\n## Decisions (from the ledger)")[0] + b"\n")
        self.refuse_confirm(directory, r"not current: goal, d1, assumed\)")

    def test_a_reordered_block_is_refused(self):
        directory = self.complete_human()
        path = self.write_seed(directory)
        lines = path.read_bytes().split(b"\n")
        first = lines.index(b"## Decisions (from the ledger)") + 1
        lines[first], lines[first + 1] = lines[first + 1], lines[first]
        path.write_bytes(b"\n".join(lines))
        self.refuse_confirm(directory, r"incomplete or out of order")

    def test_the_block_inside_another_line_does_not_count(self):
        directory = self.complete_human()
        path = self.write_seed(directory)
        path.write_bytes(path.read_bytes().replace(b"\n## Decisions (from the ledger)", b"\nx## Decisions (from the ledger)"))
        self.refuse_confirm(directory, r"do not match the ledger")


class CompletionTests(DecisionsCase):
    def test_a_simulated_seed_without_the_current_block_cannot_complete(self):
        directory = self.complete_simulated()
        path = self.write_seed(directory, SIMULATED)
        good = path.read_bytes()
        path.write_bytes(good.split(b"\n## Decisions (from the ledger)")[0] + b"\n")
        before = self.snapshot(directory)
        result = self.end(directory)
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stderr, r"cannot complete: the seed's decisions do not match the ledger")
        self.assertEqual(self.snapshot(directory), before)
        path.write_bytes(good)
        result = self.end(directory)
        self.assertEqual(result.returncode, 0, result.stderr)


class DocumentationTests(unittest.TestCase):
    def test_the_skill_tells_agents_to_paste_the_block(self):
        from test_seed_me_strict_format import SKILL
        for name in ("SKILL.md", "references/lean-path.md", "references/seed-contract.md"):
            with self.subTest(name=name):
                self.assertIn("seed decisions", (SKILL / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
