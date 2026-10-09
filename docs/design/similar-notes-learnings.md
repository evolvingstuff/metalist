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

## Related

- The note link picker (insert a link to a note by searching for it in a
  dialog) came out of the same discussion and is pursued separately.
- Other experiments on suggestions: `tag-suggestion-learnings.md`,
  `search-suggestion-learnings.md`.
