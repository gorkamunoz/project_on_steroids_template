---
name: refs
description: Add an external source (paper, book, code, dataset) to the immutable refs/ archive with provenance metadata. Use before citing anything in the wiki.
---

# Adding a reference

`refs/` is an append-only archive: what we read and where it came from. **Never edit or delete
existing files in `refs/`.** If metadata is wrong, add a `correction:` note in a thread and ask the human.

## Steps
1. Key = `firstauthorYEARfirstword` in lowercase, e.g. `smith2020example`. Check `refs/` for duplicates.
2. Create `refs/<key>/ref.yaml`:
```yaml
title: An Example Paper Title
authors: Jane Smith, John Doe
year: 2020
venue: Some Conference
url: https://arxiv.org/abs/0000.00000
doi: ""
added: 2026-11-10
added_by: agent:<you>
notes: |
  One paragraph: why this matters for us, which results we use (theorem/section numbers).
```
3. Optionally save the PDF as `refs/<key>/paper.pdf` (if it's openly available).
4. Put the knowledge in the wiki (`sources: [<key>]`), not in `refs/`.
