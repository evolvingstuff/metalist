# Luna help and menu results — 2026-09-17

Each case ran **five times**, per request. Candidate: `gpt-5.6-luna`, thinking off. Output judge: Luna, thinking low. All inputs are synthetic; no personal notes. Results are samples, not guarantees.

| Run | Cases | Correct | Incorrect | Errors | % correct | Estimated cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Initial help suite | 99 | 480/495 | 15 | 0 | 96.97% | $0.17004991 |
| Existing routing suite with help enabled | 24 | 105/120 | 15 | 0 | 87.50% | $0.01312602 |
| Four revised help checks | 4 | 20/20 | 0 | 0 | 100.00% | $0.01002466 |

## Interpretation

- Initial help: 91 structured action checks and eight judged output checks. The four follow-up checks are a separate sample, not a rerun of all 99 under the final prompt.
- Namespace-versus-search comparison originally required only the data skill. The model loaded data plus search in all five attempts; both are relevant. That expectation was broadened explicitly. The original report is preserved.
- The privacy topic description now names gray notes on chat hover. The help prompt now asks for the exact menu ID and leaves execution status to the application. All four targeted follow-up cases passed 5/5.
- Existing routing: ten failures loaded tags rather than the expected AI skill for tagging help/hypotheticals. The tags skill contains relevant proposal and undo documentation. These are restrictive expectation failures, not unauthorized operations. Their original failures remain visible in the raw score. After reviewing the actual skill documents, those two fixtures now accept either skill: rescoring the same saved outputs gives **115/120 (95.83%)**, with five incorrect and zero errors. This is an expectation correction, not a new model run or a prompt improvement. Five quoted-command explanations chose ordinary respond rather than loading product help; that is a help-routing coverage gap.
- Initial output failures: one premature opening claim (addressed in the follow-up), two search explanation judgments, and one formatting judgment. Search included a real clause-count wording error and a potentially over-strict judgment about quoted text; the judge itself also misstated the term count. Review verdicts rather than assuming the judge is always correct.
- No keyword intent classifier or validator override is involved. Instructor checks schema structure; fixtures score actions, and output cases use the configured LLM judge.

## Per-case scores

### Initial help suite

| Case | Correct | Incorrect | Errors |
| --- | ---: | ---: | ---: |
| help-context-value | 5/5 | 0 | 0 |
| help-guard-no-delete | 5/5 | 0 | 0 |
| help-guard-unsupported-note-edit | 5/5 | 0 | 0 |
| help-menu-action-collapse_all | 5/5 | 0 | 0 |
| help-menu-action-export_html | 5/5 | 0 | 0 |
| help-menu-action-open_keyboard_shortcuts_help | 5/5 | 0 | 0 |
| help-menu-action-reset_all_preferences | 5/5 | 0 | 0 |
| help-menu-command_palette | 5/5 | 0 | 0 |
| help-menu-form-change_password | 5/5 | 0 | 0 |
| help-menu-form-manage_namespace_ports | 5/5 | 0 | 0 |
| help-menu-form-reminders | 5/5 | 0 | 0 |
| help-menu-form-search_suggestion_statistics | 5/5 | 0 | 0 |
| help-menu-form-version_info | 5/5 | 0 | 0 |
| help-menu-pref-show_note_tags | 5/5 | 0 | 0 |
| help-menu-view-all_notes | 4/5 | 1 | 0 |
| help-menu-view-sort_mode-normal | 5/5 | 0 | 0 |
| help-output-context | 4/5 | 1 | 0 |
| help-output-search | 3/5 | 2 | 0 |
| help-quoted-current-user | 5/5 | 0 | 0 |
| help-route-editing | 5/5 | 0 | 0 |
| help-route-latex | 5/5 | 0 | 0 |
| help-route-namespace | 0/5 | 5 | 0 |
| help-route-references | 5/5 | 0 | 0 |
| help-route-skill-edit | 5/5 | 0 | 0 |
| help-route-theme | 5/5 | 0 | 0 |
| help-guard-hidden-shell | 5/5 | 0 | 0 |
| help-guard-no-open | 5/5 | 0 | 0 |
| help-menu-action-alphabetize_root_notes_asc | 5/5 | 0 | 0 |
| help-menu-action-create_backup | 5/5 | 0 | 0 |
| help-menu-action-fully_collapse_all | 5/5 | 0 | 0 |
| help-menu-action-prioritize_tag_back | 5/5 | 0 | 0 |
| help-menu-action-reset_updated_at_to_created_at | 5/5 | 0 | 0 |
| help-menu-form-add_password | 5/5 | 0 | 0 |
| help-menu-form-cloud_ai_privacy | 5/5 | 0 | 0 |
| help-menu-form-note_layout_appearance | 5/5 | 0 | 0 |
| help-menu-form-remove_password | 5/5 | 0 | 0 |
| help-menu-form-session_timeout | 5/5 | 0 | 0 |
| help-menu-pref-animated_transitions | 5/5 | 0 | 0 |
| help-menu-pref-show_search_results_count | 5/5 | 0 | 0 |
| help-menu-view-sort_mode-alphabetical | 5/5 | 0 | 0 |
| help-menu-view-sort_mode-updated | 5/5 | 0 | 0 |
| help-output-formatting | 4/5 | 1 | 0 |
| help-output-skills | 5/5 | 0 | 0 |
| help-route-api-key | 5/5 | 0 | 0 |
| help-route-floating | 5/5 | 0 | 0 |
| help-route-markdown | 5/5 | 0 | 0 |
| help-route-ontology | 5/5 | 0 | 0 |
| help-route-reminder | 5/5 | 0 | 0 |
| help-route-snooze | 5/5 | 0 | 0 |
| help-route-undo | 5/5 | 0 | 0 |
| help-guard-hypothetical | 5/5 | 0 | 0 |
| help-guard-quoted-open | 5/5 | 0 | 0 |
| help-menu-action-alphabetize_root_notes_desc | 5/5 | 0 | 0 |
| help-menu-action-edit_tag_relationships | 5/5 | 0 | 0 |
| help-menu-action-fully_expand_all | 5/5 | 0 | 0 |
| help-menu-action-prioritize_tag_front | 5/5 | 0 | 0 |
| help-menu-action-reset_view_filters | 5/5 | 0 | 0 |
| help-menu-form-agent_prompts | 5/5 | 0 | 0 |
| help-menu-form-create_namespace | 5/5 | 0 | 0 |
| help-menu-form-proposals | 5/5 | 0 | 0 |
| help-menu-form-rename_current_namespace | 5/5 | 0 | 0 |
| help-menu-form-switch_namespace | 5/5 | 0 | 0 |
| help-menu-pref-show_ai_chat | 5/5 | 0 | 0 |
| help-menu-pref-show_tab_ui | 5/5 | 0 | 0 |
| help-menu-view-sort_mode-content_volume | 5/5 | 0 | 0 |
| help-menu-view-untagged_notes | 5/5 | 0 | 0 |
| help-output-ports | 5/5 | 0 | 0 |
| help-output-tagging | 5/5 | 0 | 0 |
| help-route-cloud-privacy | 0/5 | 5 | 0 |
| help-route-followup | 5/5 | 0 | 0 |
| help-route-menu | 5/5 | 0 | 0 |
| help-route-password-exclusion | 5/5 | 0 | 0 |
| help-route-restore | 5/5 | 0 | 0 |
| help-route-tag-inheritance | 5/5 | 0 | 0 |
| help-route-untagged | 5/5 | 0 | 0 |
| help-guard-no-bulk-accept | 5/5 | 0 | 0 |
| help-guard-unknown-menu | 5/5 | 0 | 0 |
| help-menu-action-attach_file_to_current_note | 5/5 | 0 | 0 |
| help-menu-action-expand_all | 5/5 | 0 | 0 |
| help-menu-action-logout | 5/5 | 0 | 0 |
| help-menu-action-remove_all_tag_suggestions_current_context | 5/5 | 0 | 0 |
| help-menu-action-trim_unused_files | 5/5 | 0 | 0 |
| help-menu-form-ai_agent_settings | 5/5 | 0 | 0 |
| help-menu-form-delete_current_namespace | 5/5 | 0 | 0 |
| help-menu-form-random_password_generator | 5/5 | 0 | 0 |
| help-menu-form-restore_backup | 5/5 | 0 | 0 |
| help-menu-form-tagging_prompt | 5/5 | 0 | 0 |
| help-menu-pref-show_backlinks | 5/5 | 0 | 0 |
| help-menu-pref-theme | 5/5 | 0 | 0 |
| help-menu-view-sort_mode-created | 5/5 | 0 | 0 |
| help-output-backup | 5/5 | 0 | 0 |
| help-output-privacy | 5/5 | 0 | 0 |
| help-privacy-destination | 5/5 | 0 | 0 |
| help-route-context-limit | 5/5 | 0 | 0 |
| help-route-history-export | 5/5 | 0 | 0 |
| help-route-model-settings | 5/5 | 0 | 0 |
| help-route-ports | 5/5 | 0 | 0 |
| help-route-search-syntax | 5/5 | 0 | 0 |
| help-route-tagging-help | 5/5 | 0 | 0 |

### Existing routing suite with help enabled

| Case | Correct | Incorrect | Errors |
| --- | ---: | ---: | ---: |
| synthetic-accept-current | 5/5 | 0 | 0 |
| synthetic-accept-filtered | 5/5 | 0 | 0 |
| synthetic-acknowledge-correction | 5/5 | 0 | 0 |
| synthetic-changed-scope-retry | 5/5 | 0 | 0 |
| synthetic-compare-saved | 5/5 | 0 | 0 |
| synthetic-elliptical-continuation | 5/5 | 0 | 0 |
| synthetic-empty-scope | 5/5 | 0 | 0 |
| synthetic-general-knowledge | 5/5 | 0 | 0 |
| synthetic-generate-current | 5/5 | 0 | 0 |
| synthetic-generate-topic | 5/5 | 0 | 0 |
| synthetic-hello | 5/5 | 0 | 0 |
| synthetic-help-then-explicit-action | 5/5 | 0 | 0 |
| synthetic-hypothetical-accept | 0/5 | 5 | 0 |
| synthetic-inspect-current-proposals | 5/5 | 0 | 0 |
| synthetic-papers-without-notes-word | 5/5 | 0 | 0 |
| synthetic-past-operation-count | 5/5 | 0 | 0 |
| synthetic-quoted-command | 0/5 | 5 | 0 |
| synthetic-refresh-saved-answer | 5/5 | 0 | 0 |
| synthetic-reject-current | 5/5 | 0 | 0 |
| synthetic-remove-current | 5/5 | 0 | 0 |
| synthetic-remove-filtered | 5/5 | 0 | 0 |
| synthetic-rewrite-conversation | 5/5 | 0 | 0 |
| synthetic-summarize-notes | 5/5 | 0 | 0 |
| synthetic-tagging-help | 0/5 | 5 | 0 |

### Four revised help checks

| Case | Correct | Incorrect | Errors |
| --- | ---: | ---: | ---: |
| help-menu-view-all_notes | 5/5 | 0 | 0 |
| help-route-cloud-privacy | 5/5 | 0 | 0 |
| help-route-namespace | 5/5 | 0 | 0 |
| help-output-context | 5/5 | 0 | 0 |

## Full local evidence

Input/output pairs, provider usage, parsed decisions and judge reasons are retained locally:

- `/tmp/metalist-help-live-five-20260917/report.json`
- `/tmp/metalist-help-existing-five-20260917/report.json`
- `/tmp/metalist-help-focused-five-20260917/report.json`

These `/tmp` files are temporary local artifacts; the compact results above are the repository record. No release artifacts contain this regression suite.

## Encryption knowledge correction

The screenshot question was reproduced with the incomplete frozen privacy skill: **0/5** met the new output criteria. The same question with the expanded skill scored **5/5**. Candidate checks covered six new cases plus the existing cloud privacy output case, each five times. All inputs are synthetic.

| Case | Correct | Incorrect | Errors |
| --- | ---: | ---: | ---: |
| help-output-encryption-at-rest | 5/5 | 0 | 0 |
| help-output-encryption-backups | 5/5 | 0 | 0 |
| help-output-encryption-logs-memory | 5/5 | 0 | 0 |
| help-output-encryption-metadata | 5/5 | 0 | 0 |
| help-output-encryption-passwordless | 5/5 | 0 | 0 |
| help-route-encryption | 5/5 | 0 | 0 |
| help-output-privacy | 5/5 | 0 | 0 |

Total: **35/35**; 0 incorrect; 0 errors. Routing uses structural assertions; six output cases use explicit per-criterion Luna judgments. Judgments remain reviewable, not guarantees. No intent keywords or answer keywords override model behavior.

Estimated cost: baseline $0.00797572; candidate $0.05467284.

Local full baseline: `/tmp/metalist-encryption-help-baseline-20260917/report.json`.
Local full candidate: `/tmp/metalist-encryption-help-candidate-20260917/report.json`.

The privacy skill is still loaded only on demand. Its expansion covers encrypted attachments/tags/state, plaintext structural metadata, unprotected namespaces, immutable backup state/passwords, logs and unlocked memory. This adds knowledge, not an encryption implementation change or an audit of personal databases.
