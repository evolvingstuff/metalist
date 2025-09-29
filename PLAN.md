# PLAN: Rendered clipboard export

1. Understand current clipboard export pipeline
   - Trace `handleCopyNoteShortcut` flow through `NotesAPI.exportNoteAsHtml` and the helpers in `app/models/utils.py`.
   - Confirm how Markdown is currently stored/rendered so we know what “editing view” vs “rendered view” entails.

2. Generate rendered HTML for clipboard use
   - Identify or add a server-side utility that takes note content and produces the non-editing/rendered HTML (mirror of what templates use).
   - Adjust the export endpoint or copy handler so the HTML sent to the system clipboard matches the rendered version while the internal note clipboard stays unchanged.

3. Update tests and docs
   - Add focused unit coverage for the new render path and update any relevant docs/guides about clipboard behavior.
   - Manually verify copy/paste into an external editor matches rendered output.
