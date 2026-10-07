# seed-me

`seed-me` stress-tests your architectural plan or technical decision through a focused, single-question interview before you write code.

## Install

Install this skill with [Tink](https://github.com/jon-devlapaz/tink):

```console
tink skill add jon-devlapaz/seed-me
```

## How it works

- **Investigates facts first:** Checks repository code, configs, and schemas before asking you anything. If a fact is discoverable, it won't interrupt you for it.
- **One decision at a time:** Paces questions one by one with a clear recommendation grounded in workspace evidence, keeping cognitive load low.
- **Durable discovery artifact:** Once all blockers are resolved and confirmed, saves the accepted plan as `<session>/seed-contract.md`, beside the interview's `ledger.json`, as intake for downstream implementation. The folder is the handoff, and line 1 of the seed is `status: draft`, `status: confirmed for intake` or `status: simulated`.

## Interview format

```text
Question 1 of 3 ready (2 waiting on earlier answers)
❓ <Title>: <the consequence or tradeoff needing your judgment, one line>
📜 What I found: <verbatim quote ≤2 lines> (<exact path>:<line>, session observation); ...
Option A: <choice> — <benefit and cost compared with B>. Undo cost: <cheap | moderate | hard>.
Option B: <choice> — <benefit and cost compared with A>. Undo cost: <cheap | moderate | hard>.
👤 Owner: <named decider or role> — To decide: <the answer needed to settle this> — Why it matters: <what it unblocks or endangers>.
Against my suggestion: <the strongest case for the other option>.
➡️ My suggestion: <A or B>, grounded in the lines above. Confidence: <low | medium | high>.
   Checked: <what I verified>. Inference: <what I conclude from it, still uncertain>.
   Assumptions: <what I assumed, not confirmed>. Not checked: <what I did not verify>.
   I would change my suggestion if: <what would change my mind>. Proposed number: <any figure I invented for you to change, or "none">.
Ledger: <the viewer URL on either path, or its saved HTML snapshot if the server cannot run>
```

Full contract: [`skills/seed-me/SKILL.md`](skills/seed-me/SKILL.md)
Operational references: [`ledger-transitions.md`](skills/seed-me/references/ledger-transitions.md)
