FINAL_RESPONSE_REQUEST
Structured basis: {basis}
Answer the user's original request directly. If a current-run search_notes
TOOL_RESULT exists, synthesize the substantive, non-redundant evidence in its
`notes[].content_text`; do not substitute general knowledge or treat `note_id` as
a handle requiring another read. To cite a supporting note, copy its exact
`note_id` from a TOOL_RESULT in this run and wrap that copied value in double square
brackets. Never invent or imitate a UUID, and never print a bare UUID. Do not
mention this control message.
