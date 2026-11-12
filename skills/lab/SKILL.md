---
name: lab
description: Plan, run and report a self-contained experiment in labs/NNN-slug/, including lineage (parents), figures, metrics and conclusion. Use for any experiment or numerical check.
---

# Running a lab

A lab is one experiment with one question. It's self-contained: someone should be able to read
`report.md`, look at `figures/`, and rerun it from the committed code and config.

## 1. Create
```bash
./dash labs                                     # find what this builds on
./dash lab-new --title "learning-rate sweep on the toy dataset" -p 1 -a agent:<you> \
   --hypothesis "Loss at step 1000 is minimised for lr in [1e-3, 3e-3]; larger lr diverges."
```
This creates `labs/NNN-slug/{lab.yaml, report.md, figures/}` with status `planned`.

**Parents**: list every lab whose *result motivated* this one or whose *code/checkpoint it reuses*.
Usually 1, sometimes 2+ (merging lines of work). Leave it empty only for a genuinely new line of work.
The lineage graph in the dashboard is built from this field.

## 2. Layout
```
labs/NNN-slug/
  lab.yaml        # metadata (keep current!)
  report.md       # the write-up
  config.yaml     # all hyperparameters + seed
  run.py          # entry point (imports from src/ where possible)
  figures/        # committed PNG/SVG shown in the dashboard
  results.json    # small summary numbers (committed)
  outputs/        # checkpoints, logs, raw arrays: git-ignored
```

## 3. Lifecycle
- Set `status: running` when you start. Set `done`, `failed` or `abandoned` when you finish.
  `failed` means the hypothesis was refuted or the method didn't work, which is a valid result, so write it up.
- Fill `metrics:` in `lab.yaml` with 2–5 headline numbers (they show in the graph panel), e.g.
  `{best_lr: "2e-3", final_loss: "0.41 ± 0.02"}`.
- Fill `conclusion:` with **one sentence** (it's shown on the dashboard home and in the graph).
- Link related wiki pages in `wiki:` and threads in `threads:`.

## 4. Report (`report.md`)
Goal → Setup (data, model, key hyperparameters, seeds, compute) → Results (figures with
`![](figures/x.png)`, tables, numbers with uncertainty) → Conclusion (proved / observed / conjectured)
→ Next steps (these may become child labs or `idea` threads).

## Rules
- Don't change a `done` lab's results. If you want to redo or extend it, create a child lab.
- Several seeds before claiming an effect. Report the spread.
- Reusable code → propose promoting it to `src/` (with tests) rather than copy-pasting between labs.
- Heavy files only in `outputs/`. Run `./dash check` before you finish.
- If a lab changes our understanding of a concept, update the wiki page and cite `[[lab:N]]`.
