---
name: review
description: Critically review a lab, wiki page or proof for errors, unsupported claims and reproducibility problems, and report findings as a thread. Use when asked to review or before marking wiki pages stable.
---

# Reviewing

Your job is to find problems, not to rewrite. Be specific and point to the line or figure.

## Checklist
**Labs:** Does the setup actually test the hypothesis? Seeds/variance reported? Are the baselines fair?
Do the figures support the conclusion sentence? Can it be reproduced from committed files? Are the
`parents` correct?
**Wiki/theory:** Are the definitions precise and the notation consistent? Is every claim cited or marked
as conjecture? For proofs, check each step, the quantifiers, the hidden assumptions, and the edge cases
(degenerate cases!).

## Output
Post a `question` or `decision` thread titled `Review: <thing>` linking the item, with findings ranked
**blocking / should fix / nit**. Small objective fixes (typos, broken links) you may apply directly
and list in the thread. If a wiki page passes, set its `status: stable`.
