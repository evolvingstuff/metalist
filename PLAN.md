# PLAN: Learned Tag Suggestions

Goal: rank tag-bar suggestions with a learned model that uses a note's content,
its place in the hierarchy, and the tags already on it, and keeps adapting
while the server runs. Search suggestions are out of scope for now.

The work is staged so that nothing changes in the app until an offline
experiment on the user's own notes shows a clear gain over today's ranking.

## Phase 1: Offline experiment (no app behavior changes)

A local script, run by the user against their own namespace, that prints only
aggregate metrics. No note text, tag names or note IDs appear in its output or
leave the machine.

### 1.1 Data and test split
- Load notes (content, explicit tags, parent/sibling/child structure,
  `created_at`) and the ontology (implied tags, synonyms).
- Time split: train on notes created before a cutoff, test on notes created
  after it (also report a second cutoff for stability).
- Targets are explicit tags only. Inherited and ontology-implied tags are
  context, never targets.
- No future leakage: a test note's context uses only notes that existed when it
  was created. Tag addition dates are not stored, so tags on older notes are
  their current tags; the report says so.
- Simulated partial tagging: each test note gives cases with 0, 1, 2, …
  of its explicit tags already present, predicting the rest.
- Two moments: empty tag bar, and the first letter of the target typed.

### 1.2 Candidate generators
Each proposes up to ~100 candidate tags with a score:
- Nearest neighbors over notes (TF-IDF text plus hierarchy tags plus present
  tags, each block weighted).
- Naive Bayes per tag on note text (incremental counts).
- Tag co-occurrence with context tags (ancestors, siblings, present tags).
- Hierarchy: tags on ancestors, siblings and descendants.
- Today's ranking (`suggest_tags_for_note`) as one more source.

### 1.3 Ranker inputs, per (note, candidate tag)
- Generator scores: neighbor score, Naive Bayes score, today's rank.
- Hierarchy: nearest ancestor with the tag and its distance; co-occurrence with
  ancestor tags (max, mean); fraction of siblings with it; fraction of the
  subtree with it; depth.
- Present tags: co-occurrence with the note's present tags (max, mean).
- Ontology: candidate implied by or synonym of a present/inherited tag
  (filtered out as redundant, also kept as a flag for analysis).
- Content: tag name or its segments appear in the text.
- Tag usage: note count, recency of use (decayed counts from tag activity).

### 1.4 Models compared
1. Today's ranking (baseline).
2. Nearest neighbors alone.
3. Logistic regression on the ranker inputs (no interactions).
4. Gradient-boosted trees, yes/no objective, shallow trees, early stopping on
   the later notes, monotonic constraints where the direction is obvious.
5. Gradient-boosted trees with a ranking objective (LambdaMART family).

Library for the experiment: whichever is convenient (likely LightGBM),
installed only in the experiment environment, not added to MetaList's
dependencies.

### 1.5 Metrics
- Recall@5 and MRR (rank of the first correct tag), precision@1.
- Split by: number of present tags (0, 1, 2+), empty bar vs first letter,
  and tag frequency bucket (rare / medium / common).
- An ablation with tag-name words removed from the text, to see whether models
  learn concepts or just spot the tag's name.
- Training time and per-note scoring time.

### 1.6 Decision point
Review results with the user. Proceed to Phase 2 only if the best model clearly
beats the baseline (target to agree on, e.g. +10 points recall@5 on the empty
bar) at acceptable latency.

## Phase 2: In-app ranking (only after Phase 1 approval)

- Models live in memory only, rebuilt after unlock; nothing derived from notes
  is written to disk (no schema change, no new encrypted storage).
- Neighbor index and Naive Bayes counts update on each note save.
- Ranker inputs are computed fresh per request from current data.
- The ranker retrains in the background (after N saves or when idle) and is
  swapped in atomically; suggestions never wait on training.
- Today's ranking remains the fallback only until the model is ready after
  unlock, never as a silent error path (failures surface loudly).
- The suggestion list stays stable while typing (interaction principles).
- Shipping dependency chosen by packaging: wheels for Windows, macOS and Linux
  on Python 3.10–3.14, no separately installed OpenMP, reasonable size. Verify
  on the full release matrix.
- Explanations available per suggestion (top contributing inputs).
- Update `docs/ui/tag-bar.md`, `docs/AI-SUMMARY.md`, and the help skills.

## Phase 3: Feedback logging (later, separate decision)

- Record per tag-bar session: suggestions shown with positions, the one picked,
  tags typed in full without being offered, and rejected AI tag proposals.
- Encrypted like other user data; this is a schema change (version bump,
  migration, encryption audit, security docs).
- Use picks over skipped higher suggestions as ranking pairs; tune recency
  weighting from real behavior.

## Open questions
- How the Phase 1 script reads an encrypted namespace: the user runs it and
  enters their password themselves (the agent never handles it), or it runs
  inside the unlocked server as a local-only command.
- Which namespace(s) to evaluate on.
- The improvement threshold that justifies Phase 2.
