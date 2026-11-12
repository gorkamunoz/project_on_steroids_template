---
name: wiki
description: Write or update concept pages in wiki/ — one concept per page, cited to refs/, cross-linked, with math. Use when you learn or define something future agents need.
---

# Maintaining the wiki

The wiki is the project's compiled knowledge: definitions, results we rely on, notation, and what our
own labs established. It's for future agents who start with zero context.

## Before writing
- `./dash search <term>` and check `wiki/index.md`, then **update the existing page** if there is one.
- One concept per page. Slug = short kebab-case noun (`learning-rate`, `cross-validation`, `convergence-rate`).

## Create
```bash
./dash wiki-new convergence-rate --title "Convergence rate" -a agent:<you>
```
Then add the page to `wiki/index.md` under the right heading.

## Page shape
```markdown
---
title: Convergence rate
tags: [theory]
sources: [smith2020example]     # keys of refs/<key>/
status: draft                    # draft | stable (stable = checked by review)
updated: 2026-11-10
---
# Convergence rate
**In one sentence:** …
## Definition        (math with $...$ / $$...$$, consistent with wiki/notation if it exists)
## Why it matters here
## Known results     (cite [[ref:key]]; mark what is proved vs. conjectured)
## In our labs       ([[lab:N]] findings)
## Related           ([[other-slug]] links)
```

## Rules
- Every non-obvious claim cites a `[[ref:...]]`, a `[[lab:N]]`, or is marked *(conjecture)*.
- Use the project's notation consistently. If a notation page exists, follow it; otherwise propose one.
- Update `updated:` when you edit. Run `./dash check` (broken links, unknown sources).
