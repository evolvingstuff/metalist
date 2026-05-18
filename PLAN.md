# PLAN: RHS Activity Heatmap + Note Inspector

## Goal
Use the currently underused right-hand side as a context panel:
- Idle/default state: activity heatmap for date-based browsing.
- Hover state: note metadata inspector.
- Selected/edit state: pinned note metadata inspector.

Dates must stay out of the search box. Date filtering is view state, similar to sort mode, and composes with the current tab search query without mutating it.

## Product Decisions
- Search box remains only for content/tag search.
- Heatmap selection creates a per-tab date filter, not search syntax.
- Date filter appears as a dismissible pill/banner near the existing sort indicator.
- Date filter composes with the active search query:
  - `journal` + updated range May 12-18 means notes matching `journal` AND the selected updated-date range.
  - Clearing search does not clear the date filter.
  - Clearing the date pill does not clear search.
- Date filter is per-tab and persisted with tab state, matching sort/search/scroll behavior.
- Initial heatmap metrics:
  - `Updated`
  - `Created`
- No `Completed` metric for now because there is no completed-note concept.
- Hover inspector should not duplicate note body text. It should show metadata only.

## UX Model
### RHS States
- Idle: show activity heatmap, metric toggle, selected date/range summary, and optionally a short recent activity list.
- Hover note: temporarily show metadata for the hovered note.
- Selected note: pin metadata for the selected note.
- Edit mode: pin metadata for the note being edited.

### Date Filter UI
- Single-day selection: `UPDATED MAY 18, 2026  x`
- Range selection: `UPDATED MAY 12-18, 2026  x`
- The pill should be visually consistent with the existing sort-mode indicator.
- Exit paths:
  - Click `x` on the date filter pill.
  - Click the active heatmap selection again.
  - Press `Esc` when it is safe to clear transient view filters.
  - Command palette action: `Clear date filter`.

### Heatmap Interaction
- Show a GitHub-style calendar with month labels and day orientation.
- Hover square shows the exact day and metric count.
- Click selects one local calendar day.
- Drag selects an inclusive local date range.
- Selecting a date/range updates the active tab date filter.
- Heatmap selection visually reflects the active tab's current date filter.

### Inspector Content
Show metadata that is not already obvious in the main list:
- Created timestamp.
- Updated timestamp.
- Tags.
- Inherited tags.
- Parent/path summary.
- Direct child count.
- Subtree count.
- Attachment/embed/reference counts when available.
- In search mode, optionally show why the note is visible if that data is already available or can be added cleanly.

## Data Model
Add per-tab date filter state alongside existing tab fields:
```json
{
  "dateFilter": {
    "metric": "updated",
    "startDate": "2026-05-12",
    "endDate": "2026-05-18"
  }
}
```

Rules:
- `metric` is required when a filter exists and must be `created` or `updated`.
- `startDate` and `endDate` are required ISO local dates.
- Range is inclusive.
- `startDate <= endDate`.
- No optional fields inside an active filter; absence of a filter is represented by `dateFilter: null`.

## Backend Plan
1. Extend tab-state normalization/persistence to include `dateFilter`.
2. Add a route or extend an existing tab-state route to set/clear the active tab date filter.
3. Extend view snapshot input so `/api2/notes/view` applies the active tab date filter in addition to the current search query.
4. Implement date filtering in the snapshot/search layer without adding date terms to search syntax.
5. Add heatmap data endpoint or include compact heatmap metadata in the view payload:
   - Counts by local date.
   - Counts for both supported metrics or for the currently selected metric.
   - Enough bounds to render the current year/recent year.
6. Ensure all normal runtime reads use in-memory note state, not SQLite lookups.
7. Include date-filter state in undo epoch/global-boundary logic if changing the filter should isolate undo/redo like sort/search contexts.

## Frontend Plan
1. Add RHS shell layout that can render idle activity or note inspector states.
2. Add heatmap component:
   - Month labels.
   - Metric segmented control.
   - Hover details.
   - Click and drag range selection.
   - Selected range highlighting.
3. Add date-filter indicator pill near the existing sort indicator.
4. Wire date filter actions through `CommandGate.run(...)`.
5. Persist active tab date filter through ModeContext/tab-state services.
6. Update `/notes/view` refresh flow so changing date filter resets scroll/windowing safely.
7. Add note hover/selection signals to drive RHS inspector without stealing focus.
8. Ensure edit mode pins the current note inspector and ignores hover churn.

## Search Semantics
Date filtering composes after normal search semantics:
- Existing tag/text search determines matching note candidates and tree context.
- Date filter constrains the matching set by note `created_at` or `updated_at`.
- Ancestors needed for context may still render, consistent with current search tree inclusion.
- Non-matching descendants should remain redacted/hidden consistently with current search behavior.

Open detail to settle during implementation:
- Whether a root is included when any note in its subtree matches the search and date filter, or whether date filtering applies only to the specific note-level matches produced by search. Prefer the latter for predictability.

## Testing Plan
### Backend
- Unit tests for date-filter validation in tab state.
- Snapshot/search tests for:
  - created single-day filter.
  - updated date range filter.
  - date filter composed with tag search.
  - date filter clearing restores previous search-only result set.
  - ancestor context remains available for matching descendants.
- Heatmap aggregation tests for local-date bucket counts.

### Frontend
- JS unit tests for date range selection and formatting.
- JS unit tests for ModeContext/tab-state date filter persistence.
- UI tests/manual verification for:
  - click day.
  - drag range.
  - clear pill.
  - search + date filter composition.
  - tab switching restores independent date filters.
  - hover inspector switches back to heatmap when hover ends.
  - selected/editing note pins inspector.

## Documentation Updates
- Update `docs/AI-SUMMARY.md` after implementation.
- Add or update UI docs for RHS panel/date filtering, likely under `docs/ui/`.
- Do not modify `docs/ui/search-syntax.md` to add date syntax; if touched, only clarify that dates are intentionally outside search syntax.

## Acceptance Criteria
- RHS is useful in idle state with a rendered heatmap.
- Heatmap can select one day or a date range.
- Date filter composes with current search without changing the search input text.
- Date filter is visible and easy to exit.
- Date filter persists per tab and restores on tab switch/reload.
- Hovered notes show metadata in RHS.
- Selected/editing notes pin metadata in RHS.
- Tests cover backend filtering and frontend selection behavior.
