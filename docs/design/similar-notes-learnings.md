# Similar Notes: Tried and Dropped

In October 2026 we built and used a "Show Similar Notes" action (right-click a
note → a temporary view of the notes most similar to it), then removed it. This
records why, so the idea is not retried without a new answer to the problems
below.

## What was built

- Similarity = half shared words (TF-IDF cosine over each note's own text) +
  half shared tags (rarity-weighted; inherited tags at half weight; meta tags
  ignored). Plain Python, in memory, no AI embeddings.
- At most 20 matches, each at least 15% similar. The view reused the
  Referenced-by machinery: the matches as an ordinary note-id search (each
  with its ancestors and descendants, non-matching siblings redacted), and a
  `similarity:<note id>` sort mode putting the starting note's root first and
  the other roots by their best match.

## Why it was dropped

- **Most notes are not self-contained documents.** Many are short and only
  make sense with their parents and children. Comparing a note's own words and
  tags found superficial keyword overlap, not related ideas, for most notes.
- **Too slow and clunky in use.** Expanding or collapsing inside the view
  lagged noticeably (the similarity order was recomputed on every view
  refresh), on top of building the index for about 107,000 notes.

## Lessons

- Decide what "a document" is before measuring similarity between notes. In
  an outliner it is closer to a subtree than to a single note; any future
  attempt would need the note's context (ancestors, descendants), at a higher
  cost.
- Building it and using it on real notes was the right test: the problem was
  obvious within minutes of use and invisible in unit tests.
- Implementation notes for anyone retrying: search keeps only characters
  allowed in tags (a `similar:` search term lost its colons), so ordering
  belongs in a sort mode rather than in search syntax; an in-memory index of
  note text must be cleared with the other sensitive caches on lock.

## The note link picker, also dropped

A dialog (`Cmd+K` while editing, or right-click → Insert Note Link…) that
searched for a note and inserted `[[UUID]]` (Link) or `![[UUID]]` (Embed) at
the caret, with the copied note offered first. It was built and removed before
use because it duplicated, worse, what already works:

- **Linking already works:** search for the note in a tab, `Cmd+C` it, go back
  and `Cmd+R` (embed) or `Shift+Cmd+R` (child). Turning an embed into a link
  is deleting one `!`.
- **The dialog was a second, weaker search:** no tag suggestions (so misspelled
  or forgotten tags make notes hard to find) and no tree context, only a first
  line and the parent's first line. If you want the parent, link the parent.
- **Two ways to do the same thing** for the gain of a few fewer keystrokes.

What survived: `[[UUID]]` containing exactly a note or file id is always a
link, even when the note has a `[[ ]]` formatting wrapper tag
(`docs/ui/references.md`).

## Related

- The note link picker came out of the same discussion and was also built and
  dropped (see below).
- Other experiments on suggestions: `tag-suggestion-learnings.md`,
  `search-suggestion-learnings.md`.
