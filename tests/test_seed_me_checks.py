"""Issue #16: records, not a Markdown parser, own acceptance checks.

Fixture copied unchanged from
/tmp/tinkery-TEST-stacker-KZcCiq/sessions/37bc32a6-e13d-4558-ab44-6d00fabbd54a/seed-contract.md
(real Stacker r1, 2026-10-18). Never edit that original.
"""
import hashlib
import json
from pathlib import Path

from test_seed_me_strict_format import SessionCase, run

FIXTURE = Path(__file__).parent / "fixtures/stacker-r1-seed-contract.md"
STACKER = [
    {"statement": "Matches the tink-arcade style and theme.", "kind": "judge",
     "source": "Stacker r1: Acceptance criteria, first check",
     "how_to_judge": "Inspect Stacker alongside existing cabinets; launch checks alone do not establish visual quality."},
    {"statement": "Has working sounds.", "kind": "provisional", "cwd": ".",
     "expect": "Successful actions produce audible feedback; repeated playback remains audible, mute works, and audio failure does not prevent play.",
     "missing": "Stacker-specific event-to-sound assertions and a repeat-playback invocation, followed by listening on the intended device.",
     "source": "Stacker r1: Acceptance criteria, second check; DESIGN.md:147-164,194-200"},
    {"statement": "Just works with the right mechanics as the game has.", "kind": "provisional", "cwd": ".",
     "expect": "Source-grounded stacking, alignment loss, progression, loss and top-win assertions pass; correct timing can win, aiming for the top without a collect-or-continue checkpoint.",
     "missing": "Read source rules, map settled choices, and add deterministic Stacker assertions including overlap width and zero-overlap loss.",
     "source": "Stacker r1: Acceptance criteria, third check"},
]
COMMAND = {"statement": "Registered cabinets pass integration checks.", "kind": "cmd",
           "cmd": "python3 -B scripts/check_arcade.py", "expect": "PASS; exit status 0", "cwd": ".",
           "source": "scripts/check_arcade.py:37-60 (proposed TEST example, not run)"}


class ChecksTests(SessionCase):
    def set_checks(self, directory, records):
        payload = self.payloads / "checks.json"
        payload.write_text(json.dumps(records))
        return run("seed", "checks", "set", directory, payload)

    def render(self, directory):
        result = run("seed", "checks", "render", directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def prepared(self, records=None):
        directory = self.complete_human()
        self.assertEqual(self.set_checks(directory, records or STACKER).returncode, 0)
        self.write_seed(directory)
        return directory

    def test_stacker_exposes_ambiguous_markdown_and_round_trips_three_records(self):
        original = FIXTURE.read_bytes()
        criteria = original.decode().split("## Acceptance criteria\n")[1].split("\n## Affected")[0]
        self.assertIn("cmd: python3 -B scripts/check_arcade.py", criteria)
        self.assertIn("you judge:", criteria)  # two kinds mixed in one item
        self.assertEqual(criteria.count("Provisional:"), 2)
        self.assertEqual(criteria.count("cmd: not yet established"), 2)
        self.assertIn("cwd: /Users/", criteria)  # machine-specific, not repo-relative
        directory = self.prepared()
        rendered = self.render(directory)
        self.assertEqual(rendered, self.render(directory))
        self.assertEqual(json.loads(rendered.split("```json\n", 1)[1].split("\n```", 1)[0]), STACKER)
        self.assertEqual(json.loads(run("seed", "checks", "show", directory).stdout), STACKER)
        self.assertIn(rendered, (directory / "seed-contract.md").read_text())
        self.assertEqual(self.confirm(directory).returncode, 0)
        self.assertTrue(json.loads(run("status", directory).stdout)["handoff"]["verified"])
        self.assertEqual(FIXTURE.read_bytes(), original)

    def test_every_kind_round_trips_without_coercion(self):
        records = [COMMAND, *STACKER, {**STACKER[1], "cmd": "python3 proposed_sound_check.py"}]
        directory = self.prepared(records)
        self.assertEqual(json.loads(run("seed", "checks", "show", directory).stdout), records)
        rendered = self.render(directory)
        self.assertEqual(rendered, "## Acceptance criteria\n\n```json\n" + json.dumps(records, sort_keys=True, ensure_ascii=False, indent=2) + "\n```\n\n")
        self.assertEqual(json.loads(rendered.split("```json\n", 1)[1].split("\n```", 1)[0]), records)
        self.assertEqual(self.confirm(directory).returncode, 0)

    def test_invalid_records_are_refused_without_writes(self):
        directory = self.prepared()
        invalid = [None, {}, [], ["check"], [{**COMMAND, "kind": "unknown"}],
                   [{**COMMAND, "extra": "no"}], [{**STACKER[0], "cwd": "."}]]
        for record in (COMMAND, STACKER[0], STACKER[1]):
            for field in record.keys() - {"how_to_judge"}:
                invalid.append([{k: v for k, v in record.items() if k != field}])
            for field in record:
                invalid.extend([[{**record, field: value}] for value in ("", "  ", "\u0000", None, 7, [])])
        invalid += [[{**COMMAND, "cwd": p}] for p in ("/tmp/TEST", "..", "a/../b", "../x", "C:\\TEST", "a\\..\\b")]
        for records in invalid:
            with self.subTest(records=records):
                before = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
                result = self.set_checks(directory, records)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual({p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}, before)

    def test_record_edit_invalidates_confirmation_even_with_seed_unchanged(self):
        directory = self.prepared()
        self.assertEqual(self.confirm(directory).returncode, 0)
        seed = (directory / "seed-contract.md").read_bytes()
        self.assertEqual(self.set_checks(directory, [COMMAND]).returncode, 0)
        self.assertEqual((directory / "seed-contract.md").read_bytes(), seed)
        self.assertFalse(json.loads(run("status", directory).stdout)["handoff"]["verified"])
        self.assertEqual(self.end(directory).returncode, 1)
        self.write_seed(directory, revision="r2")
        self.assertEqual(self.confirm(directory, revision="r2").returncode, 0)
        self.assertEqual(self.end(directory).returncode, 0)
        self.assertEqual(self.set_checks(directory, STACKER).returncode, 1)

    def test_confirmation_binds_the_canonical_records_digest(self):
        directory = self.prepared()
        self.assertEqual(self.confirm(directory).returncode, 0)
        record_path = directory / "seed-confirmation.json"
        record = json.loads(record_path.read_text())
        self.assertEqual(record["schema_version"], 2)
        self.assertEqual(len(record["checks_sha256"]), 64)
        checks_path = directory / "seed-checks.json"
        checks_path.write_text(json.dumps(STACKER, sort_keys=True, separators=(",", ":")))
        self.assertTrue(json.loads(run("status", directory).stdout)["handoff"]["verified"])
        record["checks_sha256"] = "0" * 64
        record_path.write_text(json.dumps(record))
        handoff = json.loads(run("status", directory).stdout)["handoff"]
        self.assertFalse(handoff["verified"])
        self.assertIn("checks changed", handoff["reason"])

    def test_missing_records_and_legacy_confirmations_are_not_upgraded(self):
        directory = self.prepared()
        records = directory / "seed-checks.json"
        saved = records.read_bytes()
        records.unlink()
        self.assertEqual(self.confirm(directory).returncode, 1)
        self.assertFalse((directory / "seed-confirmation.json").exists())
        records.write_bytes(saved)
        self.assertEqual(self.confirm(directory).returncode, 0)
        record_path = directory / "seed-confirmation.json"
        record = json.loads(record_path.read_text())
        record.pop("checks_sha256")
        record["schema_version"] = 1
        record_path.write_text(json.dumps(record))
        self.assertFalse(json.loads(run("status", directory).stdout)["handoff"]["verified"])
        self.assertEqual(json.loads(record_path.read_text()), record)

    def test_commands_are_data_and_multiline_values_cannot_inject_markdown(self):
        directory = self.complete_human()
        marker = self.payloads / "must-not-exist"
        record = {**COMMAND, "cmd": "touch " + str(marker),
                  "statement": "A statement\n## Another heading\n```\n", "cwd": "tests/fixtures"}
        self.assertEqual(self.set_checks(directory, [record]).returncode, 0)
        self.write_seed(directory)
        self.assertEqual(self.confirm(directory).returncode, 0)
        self.assertFalse(marker.exists())
        self.assertEqual(json.loads(run("seed", "checks", "show", directory).stdout), [record])

    def refuse_admission(self, transform, profile="lean"):
        directory = self.prepared()
        if profile != "lean":
            self.write_seed(directory, profile=profile)
        path = directory / "seed-contract.md"
        section = self.render(directory)
        draft = path.read_text()
        self.assertEqual(self.confirm(directory).returncode, 0)
        confirmed = path.read_text()
        receipt_path = directory / "seed-confirmation.json"
        receipt = json.loads(receipt_path.read_text())
        with self.subTest(route="confirm"):
            path.write_text(transform(draft, section))
            before = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
            result = self.confirm(directory)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertRegex(result.stderr, "checks|cannot confirm")
            self.assertEqual({p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}, before)
        # Keep all receipt hashes consistent: verification must check admission, not just byte drift.
        path.write_text(transform(confirmed, section))
        receipt["seed_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        receipt_path.write_text(json.dumps(receipt))
        before = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
        with self.subTest(route="verify"):
            result = run("status", directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)["handoff"]["verified"])
            self.assertEqual({p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}, before)
            self.assertEqual(self.end(directory).returncode, 1)
            self.assertEqual({p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}, before)

    def test_extra_handwritten_acceptance_sections_are_refused(self):
        for heading in ("## Acceptance checks", "### Acceptance criteria", "  ## Acceptance checks ###",
                        "## ACCEPTANCE CRITERIA", "## Acceptance criteria ##", "# Acceptance criteria",
                        "Acceptance checks\n-----------------"):
            with self.subTest(heading=heading):
                extra = heading + "\nTEST additional requirement\ncmd: false\nexpect: exit zero\ncwd: .\n\n"
                self.refuse_admission(lambda body, section: body.replace(section, section + extra, 1))

    def test_a_canonical_section_only_inside_a_fence_is_refused(self):
        for fence, interior in (("````markdown", ""), ("~~~~markdown", "```\n")):
            with self.subTest(fence=fence):
                closing = fence[:4]
                def transform(body, section):
                    return body.replace(section, fence + "\n" + interior + section + "## End example\n" + closing + "\n\n", 1)
                self.refuse_admission(transform)
                self.refuse_admission(lambda body, section: transform(body, section) + "\n## Acceptance checks\ncmd: false\n")

    def test_full_and_lean_templates_keep_the_same_rendered_checks(self):
        for profile in ("full", "lean"):
            for eol, last_eol in (("\n", True), ("\r\n", True), ("\r\n", False)):
                with self.subTest(profile=profile, eol=eol, last_eol=last_eol):
                    directory = self.prepared()
                    path = self.write_seed(directory, profile=profile, eol=eol, last_eol=last_eol)
                    before = path.read_bytes()
                    self.assertIn(self.render(directory).encode(), before)
                    result = self.confirm(directory)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    after = path.read_bytes()
                    note = next(line for line in after.splitlines(keepends=True) if line.startswith(b"Confirmed by:"))
                    self.assertEqual(after.replace(note, b"", 1).replace(b"status: confirmed for intake", b"status: draft", 1), before)
                    self.assertTrue(json.loads(run("status", directory).stdout)["handoff"]["verified"])

    def test_cr_separated_reviewer_headings_are_refused(self):
        for profile in ("full", "lean"):
            for extra in ("\nTEST prefix\r## Acceptance checks\rTEST unrecorded requirement\rcmd: false\r",
                          "\nTEST prefix\r\r**Acceptance**\r_checks_\r----\rTEST unrecorded requirement\rcmd: false\r"):
                with self.subTest(profile=profile, extra=extra):
                    self.refuse_admission(lambda body, section: body + extra, profile=profile)

    def test_lone_cr_is_refused_even_without_headings_or_inside_opaque_content(self):
        for profile in ("full", "lean"):
            for extra in ("\nTEST prose\rmore prose\n", "\n<!-- TEST comment\rhidden -->\n",
                          "\n```text\nTEST code\rdata\n```\n"):
                with self.subTest(profile=profile, extra=extra):
                    self.refuse_admission(lambda body, section: body + extra, profile=profile)

    def test_template_headings_must_be_literal_complete_and_ordered(self):
        for changed in ("## **Goal**", "## goal", "Goal", "## Evidence", "  ## Goal", "Goal\n----"):
            with self.subTest(changed=changed):
                self.refuse_admission(lambda body, section: body.replace("## Goal\n", changed + "\n", 1))
        self.refuse_admission(lambda body, section: body.replace("## Goal\n", "## TEMP\n", 1)
                              .replace("## Now  (the agent keeps these current)\n", "## Goal\n", 1)
                              .replace("## TEMP\n", "## Now  (the agent keeps these current)\n", 1))

    def test_multiline_setext_headings_after_other_sections_are_refused(self):
        for title in ("**Acceptance**\n_checks_\n-----------------",
                      "[**Acceptance**](https://example.test)\n_criteria_\n================="):
            with self.subTest(title=title):
                self.refuse_admission(lambda body, section: body + "\n" + title + "\nTEST unrecorded requirement\ncmd: false\n")

    def test_body_prose_refuses_headings_of_any_title_or_nesting(self):
        for heading in ("## Security override", "### Nested note", "> ## Quoted override",
                        "- ## List override", "    ## Indented override", "Other\nstray title\n----",
                        "Other\nstray title\n- ", "> Other\n> stray title\n> -\t",
                        "- Other\n  stray title\n  - "):
            with self.subTest(heading=heading):
                self.refuse_admission(lambda body, section: body + "\n" + heading + "\nTEST extra body\n")

    def test_inline_markup_cannot_hide_extra_acceptance_headings(self):
        for title in ("**Acceptance checks**", "_Acceptance criteria_", "`Acceptance checks`",
                      "Accept**ance**  CHECKS", "<em>Acceptance</em>&nbsp;<code>checks</code>",
                      "[Acceptance checks][checks-ref]", "~~Acceptance criteria~~"):
            with self.subTest(title=title):
                extra = "## " + title + "\nTEST unrecorded requirement\ncmd: false\n\n"
                self.refuse_admission(lambda body, section: body.replace(section, section + extra, 1))

    def test_a_canonical_section_only_inside_an_html_comment_is_refused(self):
        for closing in ("-->\n\n", ""):
            with self.subTest(closing=closing):
                self.refuse_admission(lambda body, section: body.replace(
                    section, "<!--\n" + section + "## End example\n" + closing, 1))

    def test_nested_link_markup_cannot_hide_acceptance_titles(self):
        for heading in (
            '## [**aCcEpTaNcE** `checks`](https://example.test/a_(b) "link title")',
            '## [Acceptance **checks**](<https://example.test/a_(b)> "title ) text")',
            '**[Acceptance](https://example.test)** _criteria_\n-----------------',
            '## Acceptance <!-- hidden note -->[checks](https://example.test)',
        ):
            with self.subTest(heading=heading):
                extra = heading + "\nTEST unrecorded requirement\ncmd: false\n\n"
                self.refuse_admission(lambda body, section: body.replace(section, section + extra, 1))

    def test_commented_examples_and_comment_text_in_records_do_not_hide_real_checks(self):
        directory = self.prepared([{**COMMAND, "statement": "Literal <!-- in a record is data"}])
        path = directory / "seed-contract.md"
        section = self.render(directory)
        example = "<!--\n````markdown\n" + section + "## **Acceptance checks**\n````\n-->\n\n"
        path.write_text(path.read_text().replace(section, example + section, 1))
        result = self.confirm(directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(run("status", directory).stdout)["handoff"]["verified"])

    def test_fenced_examples_do_not_hide_the_real_canonical_section(self):
        directory = self.prepared()
        path = directory / "seed-contract.md"
        section = self.render(directory)
        example = "````markdown\n" + section + "## Acceptance checks\nexample only\n````\n\n"
        path.write_text(path.read_text().replace(section, example + section, 1))
        self.assertEqual(self.confirm(directory).returncode, 0)
        self.assertTrue(json.loads(run("status", directory).stdout)["handoff"]["verified"])

    def test_confirm_refuses_missing_duplicate_or_handwritten_section(self):
        directory = self.prepared()
        path = directory / "seed-contract.md"
        original = path.read_text()
        section = self.render(directory)
        for replacement in ("", section + section, section.replace("Matches", "Different"), "## Acceptance criteria\nhandwritten\n\n"):
            with self.subTest(replacement=replacement):
                path.write_text(original.replace(section, replacement))
                before = path.read_bytes()
                result = self.confirm(directory)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("checks", result.stderr)
                self.assertEqual(path.read_bytes(), before)
        path.write_text(original)
        self.assertEqual(self.confirm(directory).returncode, 0)
        (directory / "seed-checks.json").write_text("[]")
        self.assertFalse(json.loads(run("status", directory).stdout)["handoff"]["verified"])
