# MetaList AI and tagging

Explain MetaList from this reference, without pretending to inspect the user's
saved settings or notes. Defaults below do not establish their current values.

MetaList uses OpenAI; Ollama/local model support has been removed. AI agent
settings (also found by searching AI, LLM, or OpenAI in the menu) configures the
API key, model, **Maximum approximate evidence tokens**, and tagging batch token
window. **Maximum approximate evidence tokens** is the exact evidence/context
field label shown in the dialog; use this label when directing the user to it.
The defaults are gpt-5.6-luna, 500,000 evidence tokens and 100,000 tagging
batch tokens. The evidence field accepts 500–500,000. Evidence/context and tagging
batch window are different controls: 250k context means evidence 250,000, not
250,000 tagging tokens. Composer controls can change model and thinking level.

Evidence is the permitted result view active when Send is pressed, including
matching notes not yet rendered on screen. Privacy filtering happens before
counts or note data reach the model. Whole result trees are packed in visible
order into one token-limited payload. A tree is never divided: the first tree
that does not fit and all following trees are omitted. If the first tree alone
does not fit, the request fails visibly. Notes within retained trees are complete.
The limit estimates serialized evidence, not the entire conversation/model context.
Raising it can include more evidence and increase cost. A reference-source view
opened by an AI citation retains the originating search as the next Send scope.

General conversation needs no note retrieval. Product questions load selected
MetaList help skills on demand; skill text is transient and is not automatically
added to future turns. Explicit requests to generate/accept/remove tag proposals
use the separate proposal workflow. Asking about that workflow is not permission
to run it. The help action can explain and open dialogs only; it cannot set a
model/token limit or submit a form. If a user supplies a desired value, open the
appropriate settings and explain which field/value to save, honestly stating
that the value has not been changed automatically.

Proposed tags are separate from accepted tags. Tagging works on current-context
whole root trees, includes ancestors, randomizes roots before batching, and
collects results before atomic application. The vocabulary selector offers
existing only, new only, or both. Existing namespace vocabulary is shared across
batches; tags proposed in earlier batches are optional reuse vocabulary but
remain unaccepted. Existing pending proposals are not generated again. Above
one evidence budget, generation asks confirmation before proceeding. Tagging
batch size is independently configurable. Bulk accept/remove can target current
context or the namespace, optionally an exact tag. Successful bulk changes clear
undo/redo and create no bulk undo entry. There is no persistent rejection memory
or automatic background proposal generation. Individual proposal controls differ
from bulk operations; do not promise bulk undo.

Accepting a proposal converts it to an accepted tag. Removing/rejecting proposals
discards only pending, unaccepted proposals; it cannot remove accepted tags or
reverse a completed bulk acceptance. Do not offer proposal removal as a workaround
for missing bulk undo. Removing an accepted tag requires editing that note's tags,
which this chat workflow cannot do. An explanation of these limits does not itself
request opening the proposal-management dialog.

Manage tag proposals opens the bulk acceptance/removal form. Tagging prompt and
vocabulary opens instruction/vocabulary settings. Agent prompts shows packaged
system/final/tool prompts and registered skills, supports namespace overrides,
and Restore packaged defaults removes overrides. Help skills are editable there.
Overrides affect subsequent calls. A model's knowledge of an operation does not
make that operation available as a tool.

Chat history and its debug traces are session-only. Clear Chat/logout removes
them; a server restart removes them. A page reload in the same authenticated
session retains them. Export LLM history (download arrow in the chat header)
exports a list of input/output pairs, including actual provider requests,
attempts/retries/errors and activated skills. It makes no additional model call.
Agent Debug shows the latest run. The separate opt-in regression suite lives in
the source repo, excluded from PyPI; cases default to five trials with up to four
concurrent requests and report percentages and cached-token usage.
Neither export nor ordinary tests automatically sends a test suite to OpenAI.

The estimated spend display uses provider usage, tracks new/cached input, cache
writes and output, and is process-local. Resetting it does not affect billing.
Clear Chat does not reset costs. Interrupted calls with no final usage may be
absent. Stop cancels active work; Clear cancels and awaits it before clearing.
The developer eye reveals diagnostic activities. Model prose is not proof that
an action happened: actual menu acknowledgments and operation results are the
records. Past operation counts do not reveal exactly which tags were changed.
Never reconstruct a past operation from the current notes/proposals.
