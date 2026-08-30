# Search Notes

This skill is active because the agent selected `search_notes`. Produce one
focused MetaList query through the structured schema supplied by the inference
layer. There are no result pages.

The final user message is the current request. Use earlier conversation only when
the current request explicitly depends on it. Never carry an unrelated earlier
topic into a new query as either a positive or negative term.

MetaList search syntax:

- Unquoted terms match tags. `foo bar` requires both tags.
- Quoted phrases match exact note text. `"lorem ipsum"` requires that phrase.
- A leading minus excludes a tag or phrase.
- Uppercase `OR` separates clauses.
- Every clause must contain at least one positive term.

For a broad topical request, cover tag and text forms in the first query:
`foo OR "foo"` or `foo bar OR "foo bar"`. Prefer the narrowest query supported
by the request.

The tool returns one ordered, token-bounded payload containing full content for
matching notes. It reports how many trailing result trees were omitted. Do not
request another page. If omission materially limits the answer, say so.
