---
name: notes
description: Maintain the working-notes LaTeX document (notes/) that compiles all derivations of the project, and release tagged PDF versions for the human to print and review. Use when asked to write up derivations in the notes, to compile the notes, or to release a new version.
---

# Working notes (LaTeX → versioned PDF)

`notes/` is the long-form record of the theory: every definition, assumption, statement and full proof,
in reading order. It's an internal working document that the human prints and reviews, **not a paper**:
no abstract, no marketing, no related-work padding. The wiki keeps short per-concept summaries and points
to the notes for full derivations. The notes point back to wiki pages and labs.

## Layout
```
notes/main.tex              preamble + \input of sections in reading order (from skills/notes/template)
notes/sections/macros.tex   notation macros (keep in sync with wiki/notation.md)
notes/sections/NN-name.tex  one file per part: 01-setting, 02-main-result, ...
notes/refs.bib              BibTeX (keys = refs/ keys, e.g. smith2020example)
notes/figures/              figures (PDF/PNG), copied from labs, never linked into labs/
notes/build/                draft builds (git-ignored)
notes/versions/vNNN/        RELEASED, IMMUTABLE: pdf, flattened tex, diff pdf, version.yaml
```
First time: `./dash notes init` copies the template.

## Writing rules
- **Every result has a status** (macro right after `\begin{theorem}` etc.; it's shown in the margin):
  `\proved` (complete proof in the notes), `\provedelsewhere{key}`, `\numerical{N}` (evidence from lab N;
  use the `observation` environment), `\conjectured` (use `conjecture`), `\needscheck` (a proof written
  but not yet verified). Never state something as a theorem unless the proof is complete.
- Full derivations: no steps skipped "by inspection". State assumptions explicitly, with `assumption` envs,
  and reference them in each statement (`under \cref{ass:finite-support}`).
- Labels: `def:`, `ass:`, `thm:`, `lem:`, `prop:`, `eq:`, `sec:`, then a kebab-case name. Use `\cref`.
  Never renumber or rename existing labels without reason, because the human's review comments refer to them.
- Notation lives in `sections/macros.tex`. Use macros instead of retyping symbols.
- Link out: `\lab{3}`, `\wiki{some-concept}`, `\thread{12}` (clickable in the PDF).
- `\todo{...}` notes are fine in drafts. Before a release, resolve them or list them in the changelog.

## Workflow
1. Edit `notes/sections/*.tex`.
2. `./dash notes build` until it prints `✓ built` with no ERROR/WARN lines (undefined refs, citations).
   Check the result by reading the text back: `pdftotext -layout notes/build/main.pdf - | less`.
3. **Release only when asked** (a thread says "new version" / "compile the notes for review"), or when a
   thread explicitly allows it:
   ```bash
   ./dash notes release -m "one-line summary" -c "change 1" -c "change 2" --thread <id> -a agent:<you>
   ```
   This builds a stamped PDF (version and date on every page), freezes `notes/versions/vNNN/`, creates
   `notes-vNNN-diff.pdf` (latexdiff against the previous version), and **commits `notes/` and tags
   `notes-vNNN`** by itself. Don't commit notes/ separately for a release.
4. Reply on the thread with the link `http://localhost:<port>/notes/vNNN`, and name the sections the human
   should focus on.

## Rules
- Never edit or delete anything in `notes/versions/`. A correction means a new version.
- The changelog (`-c`) is for the human's review: what is new or changed, and what to check. Put the most
  important item first.
- If the human's review comments arrive (a thread referencing "p.3 l.25" of vNNN), open that version's PDF or
  flattened tex to find the spot, fix it in `sections/`, and release a new version when asked.
