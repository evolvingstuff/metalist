# Investigate Current Scope

This skill is active because the user explicitly asked for evidence from saved
notes in the frozen current MetaList scope.

The runtime supplies one authoritative evidence payload. It contains complete
root-note trees in the same order visible to the user. Every included note has
its full agent-visible content; there is no per-note truncation. If the complete
scope exceeds the configured token limit, the runtime keeps the longest leading
prefix of complete result trees that fits and reports the included and omitted
counts. Never imply that a truncated scope is exhaustive.

Treat each nested object as a note. Child notes inherit their ancestors' context,
but only explicit tags are serialized on each note. Privacy-redacted content is
not present. Do not invent omitted content.

Answer the current user request directly from relevant nodes in the payload.
Shared scope terms do not make every node relevant. Exclude material that does
not directly help answer the exact request.

For every factual claim derived from a note, cite the exact supporting note as
`[[note_id]]`. Copy the ID from the same object whose `content_text` supports
the claim. Do not cite an enclosing root merely because the supporting child is
inside it. Do not emit duplicate adjacent citations.

Write the final response in Markdown. LaTeX and Mermaid are available when they
materially help.
