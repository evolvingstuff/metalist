# Offline Search-Suggestion Experiment

Compares MetaList's search-bar suggestions with alternatives on your own
namespace, before anything changes in MetaList. Not part of the shipped
package; needs nothing beyond MetaList's own packages.

```bash
.venv/bin/python -m experiments.search_suggestions --namespace NAME
.venv/bin/python -m experiments.search_suggestions --synthetic 3000
```

The namespace database is copied read-only into a temporary directory; only
the copy is unlocked (you type the password) and read, and it is deleted at the
end. Output is totals only: no tag names, note text or note ids.

## Completion (`completion.py`)

Replays your daily tag history (`search_history`, one count per tag per day,
up to a year). For each day after a 30-day warm-up, each ranking sees only
the earlier days; for every tag used that day we count the cheapest way to
pick it: k letters typed + down-arrow presses + Enter (first suggestion with
an empty bar = 1). Never in the 20 shown: its length + 1 (typed in full).

Rankings for an empty bar or a first tag:
- `today`: MetaList's: the most-used matching tag in the last 1, 7 and 30 days
  (ending the day before) fill the first slots, then matching tags by note
  count. Checked against MetaList's own functions during the run.
- `note_count`: matching tags by note count only.
- `all_time`: by all earlier uses; ties by note count.
- `decay_3d`, `decay_14d`, `decay_60d`: every earlier use counts, halving in
  weight every 3, 14 or 60 days.

Results are split by how often the tag had been used before.

Caveat: the history records tags used (searched, picked, on notes worked on),
not what was typed into the search bar, and nothing within a day.

## Association (`association.py`)

Cue test for remembering a rare tag: notes with an explicit rare tag (on 2–20
notes). Start from a tag also on the note (as if typed first) and see where the
target lands in the list after it, for three cues: the note's broadest tag
(100+ notes), a mid-sized tag (21–100), and its two broadest tags together. A
guard does the same for a common target (100+ notes) after a broad or
mid-sized first tag (tags on every note under the cue are skipped).

Orderings: `today` (MetaList's list after the tag and a space), `count` (notes
with both), `specificity` (lift: how much more common under the first tag),
`specificity, smoothed k=1/2/5` (notes with both ÷ (candidate's notes + k)),
`balanced` (share under the first tag × ln(lift)), `today+specificity` (rank
fusion). Scores: in the top 5 / 10 / 20 and MRR with nothing typed; then
keystrokes to pick the target with letters typed narrowing each ordering
(`today` asked of MetaList directly with the letters).

The size bands are this experiment's choices for one large namespace; they are
not product rules.

## Results

`docs/design/search-suggestion-learnings.md`. In short: today's ranking held
up; smoothed specificity finds forgotten rare tags more often after a narrower
first tag but makes common companions after a broad tag (`journal` then
`todo`) cost about 1.4 more keystrokes, so nothing changed.

Tests: `.venv/bin/python -m pytest -q experiments/search_suggestions/tests`.
