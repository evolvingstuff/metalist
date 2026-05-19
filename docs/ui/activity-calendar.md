# Activity Calendar

## Purpose
- The right-side lane can show a vertical activity calendar for the current tab.
- Dates are not part of search syntax. Calendar selection is tab view state that composes with the current search result set.

## Metrics
- `Created` is the default and leftmost metric.
- `Updated` is the second metric.
- Metric choice is persisted per tab with tab state.

## Date Filtering
- Clicking a day selects that local date.
- Dragging across days selects an inclusive local date range.
- Clicking the active selected date/range clears the date filter.
- The date filter appears as a dismissible pill above the main view.
- Changing the search input clears the active date/range filter.
- Clearing the date filter does not clear the search input.

## Calendar State
- Calendar scroll position is persisted per tab.
- The calendar starts pinned to newest activity for fresh/default state.
- The heatmap uses current search context, so searching `journal` shows activity for visible `journal` results only.
- Each visible month keeps the calendar-shaped outline; boundary months render inactive days before the first active day, and the newest partial week is padded with inactive cells so the outline stays contiguous.

## Right-Click Controls
- Right-click the left lane to show/hide tabs.
- Right-click the right lane to show/hide the calendar view.
- `Cmd/Ctrl+/` also exposes `Toggle tabs` and `Toggle calendar view`.
