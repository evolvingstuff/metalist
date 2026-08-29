# Select Relevant Evidence

This skill is active because the complete frozen result scope fits on one evidence
page. Select the small set of exact evidence note IDs that the final response writer
may see.

- Treat the current user's exact request as the relevance criterion.
- Treat the active MetaList search query and frozen scope only as candidate-set
  context. A note does not become relevant merely because it matches that broader
  query or appears in the same result tree.
- Select a note only when its disclosed content directly supports an answer to the
  current request. Exclude unrelated siblings, neighboring topics, and generic
  background that does not answer the narrower question.
- Use the nested hierarchy to understand context, but select the exact child note
  that contains the supporting content rather than its root or a sibling.
- Copy only exact `note_id` values present in `candidate_evidence_page`. Never invent,
  alter, or infer an ID.
- Order selected IDs by usefulness. Select at most 12. Return an empty list if no
  candidate directly answers the request.
- Return only the structured `EvidenceSelection` required by the inference schema.
  Do not draft prose, citations, a References section, or follow-up actions.
