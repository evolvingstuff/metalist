# Activity Calendar

## Purpose
- The right-side lane can show a vertical activity calendar for the current tab; it is hidden by default and can be enabled from the command palette or right-click menu.
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
- The global `↑` button also jumps the calendar back to newest activity; it remains enabled at page top when the calendar is scrolled away from newest.
- The heatmap uses current search context and counts matching notes, including child notes, so searching `journal` shows activity for matching `journal` notes throughout the tree.
- Each visible month keeps the calendar-shaped outline; boundary months render inactive days before the first active day, and the newest partial week is padded with inactive cells so the outline stays contiguous.
- Hovering notes scrolls the matching date into view immediately. The note-driven green calendar-cell highlight appears and clears instantly, while the date tooltip still delays/fades in for non-edit hover movement.
- An actively edited note counts as the effective hovered note for the calendar. Its matching date stays highlighted while editing, and its date tooltip appears immediately instead of using the hover delay.

## Right-Click Controls
- Right-click either lane to open the shared view menu with both tabs and calendar visibility actions.
- `Cmd/Ctrl+/` also exposes dynamic `Show/Hide tabs` and `Show/Hide calendar view` actions.
- The visible calendar keeps a 160px minimum rail width. In the intermediate desktop range the app shell moves left and the note area narrows as needed, reserving a non-overlapping calendar column beside the global controls. The side rails still hide at the narrow/mobile breakpoint.
