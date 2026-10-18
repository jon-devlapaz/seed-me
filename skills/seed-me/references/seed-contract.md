# Seed contract (artifact contract)

Read this before drafting the seed (SKILL.md Step 5.1). The displayed and saved revision must contain:

- Line 1, exactly one of three values and nothing else on that line: `status: draft` for every
  revision not yet confirmed, `status: confirmed for intake` only after the human affirms and the
  helper writes it, and `status: simulated` for an agent-mode session. The file is
  `<session>/seed-contract.md` in every case, saved beside `ledger.json`.
- Then the title and provenance: originator when known, a `revision:` line with the revision label and
  the date, and, once confirmed, the helper's `Confirmed by:` line, which says the seed is
  not approved for implementation.
- **You are confirming** box under a `## You are confirming` heading (the completion gate checks for it) directly after the title and provenance lines, five short lines: the goal; what gets built;
  what does not; what the user accepted unchanged (with the accepted-versus-chosen count);
  what is still unknown — plus any earlier decision this reverses.
- Problem statement: current behavior, evidence, and why it matters.
- Proposed outcome: desired user-visible results and success criteria.
- Acceptance criteria: generated only from the session's `seed-checks.json` records using
  `session.py seed checks render <session>`. Paste the entire output unchanged, including its
  `## Acceptance criteria` heading and final blank line. Never hand-write or parse criteria Markdown.
  Downstream consumers read the records, not the rendered section. See **Check records** below.
- Affected users and systems: relevant repositories, modules, and execution paths.
- Constraints and boundaries: non-negotiables, exclusions, and rejected alternatives.
- Accepted decisions and assumed defaults: the output of `session.py seed decisions "<session>"`,
  pasted unchanged. It lists each settled or deferred node with its authority, source and
  dependencies, then every `assumed` entry labelled as not confirmed by the user. The ledger
  owns this text; `seed confirm` refuses a seed whose copy is not current. Add rationale below it.
- **Knowledge map**, in plain words, four parts:
  1. *What we know, with proof:* each item has its receipt and the date it was observed, and, for a fact that can
     change, a re-check trigger (`observed 2026-09-29; re-check if X changes or after N days`).
  2. *What we know we don't know:* each item with its owner and how to find out.
  3. *What we have not read:* the close checklist's unread material.
  4. *What could surprise us:* the `Probe:` lines, `Where we did not look:`, and what would tell us we were
     wrong (a concrete signal, not a mood).
- Evidence and uncertainty: inspected paths, measurements, unverified hypotheses,
  assumptions, what we haven't read (from the close checklist), and repeat
  surprises with their citations. Carry a `Grounded in:` list of paths actually read
  this session. Flag a stale watch: any cited source older than the session start
  or since modified is suspect until re-read. Record verified origins and state
  gaps explicitly rather than inventing missing provenance.
- Suggested first slice: the smallest implementation step that would start
  resolving the problem, labeled proposal only, stated as an exact first
  command with its working directory. Non-binding: it seeds Stage 01
  approach drafting without preempting design or authorizing work.
- Risks and verification: consequential failure modes, mitigations, and testable
  acceptance criteria; distinguish proposed checks from completed verification.
- Open questions and deferrals: only non-blocking items, with reasons and revisit
  conditions. Unresolved blockers still prevent confirmation and saving.
- Owners and next steps: for each open blocker, the owning decider and gate; for each
  item to be read later, who will read it; for each repeat surprise, its guardrail.
  Map each to ledger status: known → settled (evidence), needs a decision →
  unresolved (blocker), watch → parked or risk, repeat surprise → risk with guardrail.
- Downstream handoff: the session folder is the handoff: `<session>/seed-contract.md` together with
  `ledger.json`, which a consumer needs to see that the session completed with a human, and
  `seed-confirmation.json` and `seed-checks.json`. A consumer checks `session.py status <session>`: `handoff.verified` is true
  only while the seed, decisions and check records are exactly what was confirmed. It proves content, not who
  confirmed it. The viewer page is not required. This artifact
  is discovery input, not an implementation plan,
  approved specification, or review receipt. Preserve accepted constraints when
  deriving downstream plans or specifications; follow the selected workflow's
  active contract and surface conflicts rather than silently replacing decisions.
  Do not preselect a downstream profile or fabricate stage approval.

## Check records

The helper CLI is:

```sh
python3 "<skill>/scripts/session.py" seed checks set "<session>" "<input.json>"
python3 "<skill>/scripts/session.py" seed checks show "<session>"
python3 "<skill>/scripts/session.py" seed checks render "<session>"
```

`set` replaces all records atomically under the session writer lock; it requires an active session
and leaves the seed untouched. Input and `show` output are a non-empty JSON array, in check order.
`render` prints a deterministic, LF-terminated Acceptance criteria section containing indented JSON
with sorted keys; it does not edit the seed. All fields are non-empty strings (no NUL); no coercion.
Unknown kinds and fields are refused. Exact schema (required fields unless marked optional):

- Every record: `statement`, `kind`, `source`.
- `kind: "cmd"`: also `cmd`, `expect`, `cwd`. Copy the exact command and expected output from the settled check.
- `kind: "provisional"`: also `expect`, `cwd`, `missing`; optional `cmd` is a proposed command.
  Record what must exist before it can run. This does not block confirmation and is not verification.
  Implementation replaces it with a real check once runnable.
- `kind: "judge"`: no additional required fields; optional `how_to_judge` describes human judgment.
  It is not a runnable command or completed verification.

`cwd` is relative to the repository root (`.` means that root). Absolute paths, any `..` path
component, backslashes and drive-letter paths are refused. The helper never executes checks.
The source names the actual decision or evidence, not invented command provenance.

`seed confirm` requires the exact rendered section and stores canonical records' SHA-256 alongside
seed-byte and decision hashes in `seed-confirmation.json` (schema version 2). Record changes,
missing or invalid records, or any seed-byte change invalidate `handoff.verified`; a new displayed
draft and confirmation are required. There is no compatibility path for old Markdown-only seeds
or version-1 confirmation records. Changing records alone does not regenerate or reconfirm the seed.

Label technical proposals as proposals unless explicitly accepted; downstream
workflows own subsequent specification and implementation approval.
