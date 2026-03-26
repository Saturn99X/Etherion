# Contribution Logs

Welcome. This directory is where every contributor documents their work.

---

## Why this exists

Etherion is built on a simple conviction: **context is everything**. When an AI agent or a human contributor works without full system understanding, they break things. These logs exist to make sure no one ever has to work blind.

Every decision that was made, every bug that was fixed, every architecture that was changed — it's in here. Before you write a single line, read the most recent entries. You'll understand the system faster than any onboarding doc could teach you.

---

## Before you contribute

Your AI agent **must** read, in this order:

1. **`Z/tech.md`** — the complete technical architecture of the platform
2. **`Docs/etherion_docs/guide.md`** — structured documentation across all 12 platform areas
3. **The 3 most recent files in this directory** — current state, recent decisions, known issues

This is not optional. PRs submitted without the corresponding log entry will be closed.

---

## How to write your log

Create a file named `Logs/Daily/<your-email>` and use this structure:

```markdown
# Contribution Log: [Feature or Fix Name]

**Date**: YYYY-MM-DD
**Contributor**: @yourgithub

## Context
What was the state before your changes? What problem were you solving?

## Files Affected
- path/to/file.py — what changed and why

## Technical Explanation
How does it work? Be precise.

## Reasoning
Why these choices? What alternatives did you consider and reject?

## Testing
What was tested and how? What edge cases were checked?

## Z/tech.md Updates
Which section(s) did you add or update?
```

---

## Rules

- One file per contribution, named after your email
- No vague entries — write what actually happened
- If you changed architecture, update `Z/tech.md` and reference the section here
- If you fixed a bug, describe the root cause — not just the symptom
- If you don't know why something broke, say so — don't fabricate an explanation

---

## Questions

Open a GitHub issue with the `question` label, or reach out:

**architect@etherionai.com**
