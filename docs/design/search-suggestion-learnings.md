# Search Suggestions: What the Offline Experiment Taught Us

In October 2026, after the tag-bar work (`tag-suggestion-learnings.md`), we
tested whether the search-bar suggestions could be improved the same way. They
could not: today's ranking held up, and the one promising change hurt the
most common search pattern. Nothing in MetaList changed. This note records
why, so the question need not be reopened without new evidence. The experiment
is in `experiments/search_suggestions/` (see its README); it prints totals
only and can be rerun as history grows.

Measured on one namespace: about 107,500 notes, 10,900 tags in search, and 49
days of tag-activity history.

## What search suggestions are for

Two jobs, discussed before measuring:

- **Completion:** you know the tag and want to type less (`j` + Enter for
  `journal`). The first slot matters most. The same goal applies to the tag
  bar.
- **Recognition:** you cannot remember a tag, or whether you tagged something
  at all. Typing letters cannot help; the list has to remind you. This was
  the main frustration: rare things are hard to find.

The tag bar has a note to work from (its text, its place in the tree); the
search bar does not. Search can only use your history, the tags already typed,
and how tags co-occur across notes. Ideas dismissed for that reason or for
poor fit: suggesting tags from words in notes (that is text search, and tags
are easier to remember than words), a separate region for recent rare tags
(recent ones are the ones you remember), showing last-used dates (noise).
Search suggestions stay limited to positive tags (no `-tag`, `OR`, quotes).

## How today's ranking works

- Empty bar or first tag: the most-used matching tag in each of the last 1, 7
  and 30 days (by default) takes the first slots, then matching tags by note
  count.
- After one or more tags: only candidates that still leave results for all
  typed tags appear. They are ordered by overlap (Jaccard): notes with both
  the candidate and the typed tags, divided by notes with either. This
  already favors specific companions over tags that are common everywhere
  (`search_index.suggest_tag_completions`).

## Completion: replaying daily history

For each day, every method sees only earlier days; for each tag used that day
we count the cheapest way to pick it (letters typed + down-arrows + Enter).
After a 30-day warm-up only 19 days could be scored (863 tag uses).

| Method | Keystrokes (all) | Used 21+ times | 4–20 | 1–3 |
|---|---|---|---|---|
| Today (1/7/30-day windows) | **3.60** | 2.79 | **3.73** | **4.35** |
| Note count only | 4.42 | 3.71 | 4.86 | 5.12 |
| Smooth recency, 14-day half-life | 3.60 | **2.63** | 3.88 | 4.62 |

History helps a lot (about 0.8 keystrokes over note count alone); smooth
recency does not beat the fixed windows (slightly better for constant tags,
slightly worse for rarer ones). Conclusion: no change. With far more history
the comparison could be rerun.

## Recognition: the cue test

For notes with a rare tag (on 2–20 notes), pretend the search starts from a
tag you remember that is also on the note, and see where the rare tag lands in
the list after it (nothing typed), and how many keystrokes it takes to pick
(letters typed narrowing each list).

Orderings compared after the first tag: today's overlap; plain co-occurrence
count; specificity (how much more common the candidate is under the first tag
than overall, i.e. lift); specificity smoothed (notes with both ÷ (the
candidate's notes + k), so a one-off tag cannot outrank a real subtopic);
balanced (share × log lift); and a rank fusion of today with specificity.

Rare tag in the top 5 / top 20, by what you start from:

| First tag | Today | Specificity, smoothed k=2 |
|---|---|---|
| Broad (on 100+ notes) | 0.0% / 0.1% | 0.0% / 0.5% |
| Mid-sized (21–100 notes) | 29.9% / 68.5% | **43.5% / 82.9%** |
| The note's two broadest tags | 1.3% / 2.5% | 2.0% / 5.1% |

Guard: a common second tag (on 100+ notes) after a broad first tag, the
everyday pattern (`journal` then `todo`):

| | Today | Specificity, smoothed k=2 | Today + specificity |
|---|---|---|---|
| Keystrokes | **3.56** | 4.99 | 4.09 |
| 2 keys or fewer | **22.7%** | 8.9% | 12.4% |

Findings:

- From a broad tag, no ordering can surface a forgotten rare tag: hundreds of
  rare tags live entirely under it and look the same. Two broad tags together
  barely help.
- From a narrower first tag, specificity finds rare tags much more often, with
  the same result for k = 1, 2 and 5 (so not tuned to one value). Plain count
  is useless there (0.3% top 5); today's overlap is a middle ground.
- Specificity pushes common companions down. After a mid-sized tag that costs
  little once a letter is typed (+0.1 keystrokes), but after a broad tag it
  costs about 1.4 keystrokes and breaks `j` + Enter. The guard failed, so it
  was not shipped.
- Today's overlap ordering is a good compromise between finding rare and
  common companions; no tested ordering beats it on both.

## Lessons about the method

- **Beware overfitting.** Many orderings and cues were tried on one dataset,
  and later tests were designed after earlier results. Mitigations used:
  parameter-free orderings only, a decision fixed before checking the guard,
  smoothing values checked for robustness rather than picked, and a rule that
  a failed guard means no change rather than a special case.
- **Avoid size cut-offs in product rules.** "Mid-sized" (21–100 notes) only
  means something at this namespace's scale; a rule using it would not carry
  to a namespace of 200 notes. Ratios like specificity are scale-free.
- **The cue test is a simulation** of how one might hunt for a rare tag; it
  cannot show that searches actually happen that way.

## Possible future work

- Rerun the completion replay once there are many months of tag history.
- Rerun the whole experiment on another namespace (`--namespace NAME`) before
  trusting any change.
- Recording which suggestions were shown, picked, skipped, or typed in full
  (with query order) would allow testing on real searches rather than
  replays; it needs a schema change and a privacy decision.
- Forgotten rare tags may need something other than ranking, such as easier
  browsing of what lies under a tag.
