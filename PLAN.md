# PKMS Reminder System Plan

## Goal

Implement a simple, reliable reminder system for a PKMS.

The system should be treated as **scheduled prompts**, not as a task manager, calendar system, workflow engine, habit tracker, or review engine.

Reminders can be:

- attached to a note, or standalone
- one-time, or recurring
- date-time based, or date-only
- surfaced in-app
- configured to disappear if missed, or remain visible until seen

Reminder creation and editing should be entirely UI-driven. Do not implement natural-language parsing in V1.

---

## First Implementation Slice

Start with **standalone reminders only**.

Do not expose raw note IDs in the reminder UI. Note-attached reminders are deferred until there is a proper note picker/search flow that lets the user select a note by recognizable content/title, not by UUID.

The first implementation should not include:

- note-attached reminder creation
- note ID entry fields
- note title search in the reminder registry
- jump-to-source-note actions

Keep the data model shaped so note attachment can be added later without changing the reminder concept, but reject attached reminders in the API until the UX exists.

---

## V1 Scope

### Must support

1. **Attachment mode**
   - attached to a note
   - unattached / standalone

2. **Schedule mode**
   - one-time
   - recurring

3. **Time mode**
   - date-time reminders
   - date-only reminders

4. **Delivery**
   - in-app only

5. **Missed-reminder behavior**
   - drop if missed
   - keep until seen

6. **Reminder management**
   - searchable live registry of current reminders
   - lightweight missed bucket for sticky reminders

7. **Core actions**
   - acknowledge
   - dismiss
   - mark done
   - pause
   - resume
   - edit
   - delete
   - skip next occurrence for recurring reminders

### Explicitly out of scope for V1

- natural-language input
- embedded note syntax for reminders
- event-relative reminders
- condition-based reminders
- task/project workflows
- habit tracking
- review / spaced repetition
- full reminder history / audit log
- browser/system push notifications
- service workers, push subscriptions, notification permissions, or Web Push/VAPID infrastructure
- advanced timezone travel behavior
- complex recurrence rules
- edit-only-this-occurrence semantics
- edit-this-and-future occurrence splitting
- complex snooze history or per-occurrence analytics

---

## Product Model

A reminder is a standalone object with:

- optional note attachment
- display title
- schedule definition
- missed-reminder policy
- lifecycle state
- minimal runtime state

### Product framing

Reminders are:

- scheduled prompts
- optionally linked to notes
- surfaced in-app according to user-selected persistence behavior

They are intentionally narrower than tasks.

---

## Core Concepts

### 1. Attachment

A reminder is either:

- **attached**
  - references a note
  - can default its title from the note title
  - should provide an affordance to jump to the source note

- **unattached**
  - standalone reminder
  - must have a title or strongly encouraged title

### 2. Schedule

A reminder is either:

- **one-time**
- **recurring**

### 3. Time mode

A reminder is either:

- **date-time**
  - fires at a specific instant
  - uses `scheduled_at` / `next_fire_at`

- **date-only**
  - applies to a local calendar date
  - does not imply morning, noon, or any default wall-clock time
  - fires on first non-idle app use on that local date

### 4. Delivery

Reminders are surfaced in-app only.

Privacy rule: reminders must not appear outside the unlocked, actively used MetaList app. If the app is closed, backgrounded, logged out, locked, or another person is using the laptop, reminder text must not appear through browser/system notifications.

Do not implement or model browser/system push notifications for reminders. That means no service worker reminder delivery, notification permission flow, push subscription storage, Web Push/VAPID sender, or multi-device push reconciliation. A future local desktop notification feature would need its own explicit design, must be opt-in, and must preserve the same privacy rule.

### 5. Missed behavior

Per reminder, the user chooses:

- **drop_if_missed**
  - if the user does not receive or see it in the relevant window, it disappears
  - it does not enter the missed bucket

- **keep_until_seen**
  - if missed, it remains visible until acknowledged or dismissed
  - it appears in the missed bucket

This is the most important product distinction in the design.

---

## Date-Time vs Date-Only Semantics

### Date-time reminders

A date-time reminder fires at a specific local instant.

Examples:

- `2026-06-08T09:00:00-07:00`
- every Monday at 09:00
- every 2 weeks on Friday at 16:30

Date-time reminders use `next_fire_at`.

### Date-only reminders

A date-only reminder is a calendar-day prompt gated by actual app engagement.

It should fire on:

```ts
first_non_idle_app_use_on_local_date
```

It should not fire at an arbitrary default such as “morning.”

Examples:

- remind me on June 8
- every Monday, on first use
- every month on the 15th, on first use

Date-only reminders use `next_fire_date`, not just `next_fire_at`.

### Non-idle app use

Define “non-idle app use” centrally. A reasonable V1 definition:

```ts
type AppActivityKind = "idle" | "non_idle_use";

type AppActivityEvent = {
  kind: AppActivityKind;
  occurred_at: string; // ISO datetime
};
```

A non-idle use event should represent meaningful user presence in the app, not background sync, passive tab restore, hidden page load, or service worker activity.

Candidate V1 triggers:

- app gains focus and user is active
- user clicks, types, navigates, or opens a note
- user returns after idle timeout and performs interaction

Avoid counting:

- background sync
- notification permission checks
- automatic startup work
- invisible tabs
- hidden iframe or service worker events

The exact idle threshold can be simple in V1, e.g. app has foreground focus and receives a user interaction after being idle or inactive.

---

## Data Model

Use a single `reminders` table/object in V1. Avoid storing full occurrence history.

```ts
type ReminderStatus = "active" | "paused" | "done";

type ReminderAttachmentType = "attached" | "unattached";

type ReminderScheduleKind = "one_time" | "recurring";

type ReminderTimeMode = "date_time" | "date_only";

type ReminderPersistenceMode = "drop_if_missed" | "keep_until_seen";

type ReminderDateTriggerPolicy = "on_first_non_idle_use";

type Reminder = {
  id: string;

  // attachment
  note_id: string | null;

  // display
  title: string;

  // classification
  attachment_type: ReminderAttachmentType;
  schedule_kind: ReminderScheduleKind;
  time_mode: ReminderTimeMode;

  // date-time reminders
  scheduled_at: string | null; // ISO datetime, for one-time date-time reminders
  next_fire_at: string | null; // ISO datetime, for date-time reminders

  // date-only reminders
  scheduled_date: string | null; // YYYY-MM-DD, for one-time date-only reminders
  next_fire_date: string | null; // YYYY-MM-DD, for date-only reminders
  date_trigger_policy: ReminderDateTriggerPolicy | null;

  // recurring reminders
  recurrence_rule: RecurrenceRule | null;

  // visibility
  persistence_mode: ReminderPersistenceMode;

  // lifecycle
  status: ReminderStatus;

  // scheduling/runtime
  last_fired_at: string | null;   // ISO datetime, when the reminder was last emitted
  last_fired_date: string | null; // YYYY-MM-DD, mainly for date-only occurrence suppression
  last_seen_at: string | null;    // ISO datetime

  // lightweight missed state
  is_currently_missed: boolean;
  missed_since: string | null; // ISO datetime or local date boundary represented consistently
  missed_count: number;

  // optional simple snooze
  snoozed_until: string | null; // ISO datetime

  // metadata
  created_at: string;
  updated_at: string;
};
```

### Invariants

Exactly one of the date-time fields or date-only fields should be meaningful based on `time_mode`.

For `time_mode = "date_time"`:

```ts
scheduled_at or recurrence_rule is populated
next_fire_at is populated while active
scheduled_date is null
next_fire_date is null
date_trigger_policy is null
```

For `time_mode = "date_only"`:

```ts
scheduled_date or recurrence_rule is populated
next_fire_date is populated while active
next_fire_at is null
date_trigger_policy = "on_first_non_idle_use"
```

For one-time reminders:

```ts
schedule_kind = "one_time"
recurrence_rule = null
```

For recurring reminders:

```ts
schedule_kind = "recurring"
recurrence_rule != null
```

---

## Recurrence Rule Model

Keep recurrence intentionally narrow in V1.

```ts
type RecurrenceFrequency = "daily" | "weekly" | "monthly" | "yearly";

type RecurrenceEnd =
  | { type: "never" }
  | { type: "on_date"; value: string } // YYYY-MM-DD
  | { type: "after_count"; value: number };

type RecurrenceRule = {
  frequency: RecurrenceFrequency;
  interval: number; // every N units

  // weekly
  weekdays?: number[]; // choose 0-6 or 1-7 and keep consistent

  // monthly
  day_of_month?: number;

  // yearly
  month?: number;
  day?: number;

  end: RecurrenceEnd;

  // only used for date-time recurring reminders
  time_of_day?: string | null; // "HH:mm"

  // only used for date-only recurring reminders
  date_trigger_policy?: ReminderDateTriggerPolicy | null;
};
```

### Supported recurrence UI/options in V1

- every day
- every weekday
- every week on selected days
- every month on day N
- every year on month/day
- every N days / weeks / months / years
- ends never
- ends on date
- ends after N times

### Not required in V1

- first/last weekday of month
- business-day logic
- complex calendar rules
- timezone travel handling
- DST sophistication beyond normal local scheduling
- per-occurrence editing

---

## Runtime Scheduling Semantics

Use deterministic scheduling functions.

The scheduler should:

- identify due date-time reminders
- identify eligible date-only reminders on non-idle app use
- emit in-app events
- update `last_fired_at`
- update `last_fired_date` for date-only reminders
- update `next_fire_at` for date-time recurring reminders
- update `next_fire_date` for date-only recurring reminders
- mark sticky missed reminders as missed when appropriate

Keep scheduling logic centralized so UI and runtime remain consistent.

---

## Date-Time Reminder Evaluation

### One-time date-time reminder

`schedule_kind = "one_time"` and `time_mode = "date_time"`.

The reminder is due when:

```ts
now >= scheduled_at
```

When fired:

- update `last_fired_at`
- if `drop_if_missed`, deliver if possible, then mark done or remove from active runtime flow
- if `keep_until_seen`, mark missed if not seen/acknowledged
- for one-time reminders, mark `done` after successful non-sticky delivery or after final dismissal depending on UX choice

### Recurring date-time reminder

`schedule_kind = "recurring"` and `time_mode = "date_time"`.

The reminder is due when:

```ts
now >= next_fire_at
```

When fired:

- update `last_fired_at`
- compute next occurrence immediately
- update `next_fire_at`
- if `keep_until_seen`, current missed state may remain visible until user handles it
- do not create a full occurrence record

---

## Date-Only Reminder Evaluation

### One-time date-only reminder

`schedule_kind = "one_time"` and `time_mode = "date_only"`.

The reminder is eligible when:

```ts
localDate(now) === scheduled_date
```

It should fire only on first non-idle app use on that local date:

```ts
function shouldFireOneTimeDateOnlyReminder(
  reminder: Reminder,
  now: Date,
  appActivity: AppActivityEvent
): boolean {
  const today = localDate(now);

  return (
    reminder.status === "active" &&
    reminder.time_mode === "date_only" &&
    reminder.schedule_kind === "one_time" &&
    reminder.scheduled_date === today &&
    reminder.last_fired_date !== today &&
    appActivity.kind === "non_idle_use"
  );
}
```

When fired:

- emit the reminder
- set `last_fired_at = now`
- set `last_fired_date = localDate(now)`
- for `drop_if_missed`, mark done after delivery
- for `keep_until_seen`, keep visible until acknowledged/dismissed

### Recurring date-only reminder

`schedule_kind = "recurring"` and `time_mode = "date_only"`.

The reminder is eligible when:

```ts
localDate(now) === next_fire_date
```

It should fire only on first non-idle app use on that local date.

When fired:

- emit the reminder
- set `last_fired_at = now`
- set `last_fired_date = localDate(now)`
- compute the next eligible recurrence date
- set `next_fire_date`
- if `keep_until_seen`, keep visible until acknowledged/dismissed
- do not create full occurrence history

### Date-only reminder missed semantics

Date-only reminders do not fire at midnight, morning, or any arbitrary wall-clock instant.

Missed behavior is evaluated relative to app usage.

#### `drop_if_missed`

If the eligible date passes and the user never has non-idle app use on that date:

- drop the occurrence silently
- do not add to missed bucket
- for one-time reminders, mark done or expired
- for recurring reminders, advance to the next eligible date

#### `keep_until_seen`

If the eligible date passes and the user never has non-idle app use on that date:

- on the next non-idle app use, surface it as missed
- set `is_currently_missed = true`
- set `missed_since` to the missed date or a consistent timestamp representing that missed date
- increment `missed_count`
- keep it visible until acknowledged/dismissed

This preserves the app-centric semantics while still supporting reliable sticky reminders.

---

## Missed Reminder Model

Do not build a full history system in V1. Implement lightweight missed-state tracking.

### Fields used

- `last_fired_at`
- `last_fired_date`
- `is_currently_missed`
- `missed_since`
- `missed_count`
- `last_seen_at`

### Semantics for `drop_if_missed`

If the scheduled time/date passes and the reminder is not delivered/seen in its intended context:

- do not keep it around
- do not show it in the missed bucket
- for one-time reminders, mark done/expired
- for recurring reminders, advance to next occurrence

### Semantics for `keep_until_seen`

If the reminder fires or is discovered as missed and has not been seen/acknowledged:

```ts
is_currently_missed = true
missed_since = fire_time_or_missed_date
missed_count += 1
```

It remains visible in-app until the user dismisses or acknowledges it.

---

## Lifecycle States

Keep the state machine small.

### Reminder definition status

```ts
type ReminderStatus = "active" | "paused" | "done";
```

### Runtime display state

Runtime display state can be derived:

- scheduled
- due now
- missed
- snoozed

`missed` only meaningfully applies to reminders with:

```ts
persistence_mode = "keep_until_seen"
```

Avoid adding extra lifecycle states unless a concrete UX requirement appears.

---

## User Actions

### Acknowledge

Resolves the currently visible reminder or missed state.

For recurring reminders, this does not stop future recurrence.

```ts
is_currently_missed = false
last_seen_at = now
```

### Dismiss

Equivalent to acknowledge unless the UI wants softer wording.

For recurring reminders, this does not stop future recurrence.

### Mark done

Permanently stops the reminder.

```ts
status = "done"
next_fire_at = null
next_fire_date = null
is_currently_missed = false
```

### Pause

Temporarily disables future firing.

```ts
status = "paused"
```

The reminder remains in the registry.

### Resume

Reactivates a paused reminder and recomputes the next fire time/date from now.

```ts
status = "active"
next_fire_at or next_fire_date = computeNext(...)
```

### Delete

Removes the reminder definition.

### Skip next occurrence

For recurring reminders only.

Date-time reminder:

```ts
next_fire_at = computeNextDateTimeOccurrence(after: next_fire_at)
```

Date-only reminder:

```ts
next_fire_date = computeNextDateOnlyOccurrence(after: next_fire_date)
```

### Snooze

Optional simple V1 action.

Snooze should only suppress current surfacing until a specific date-time.

```ts
snoozed_until = some_future_datetime
```

Do not implement snooze history or analytics in V1.

---

## UI: Creation Flow

Reminder creation should be fully UI-driven and branching.

### Step 1: What is this reminder for?

Options:

- this note
- standalone reminder

Behavior:

- if launched from a note, preselect “this note”
- if standalone, no note reference

### Step 2: What kind of time?

Options:

- date and time
- date only

For date-only, explain behavior in UI:

> Shows on first use of the app that day.

Avoid labels such as “morning” or “all day” if they imply a wall-clock delivery time.

### Step 3: When should it happen?

Options:

- once
- repeat

### Step 4A: If once + date-time

Fields:

- date picker
- time picker

### Step 4B: If once + date-only

Fields:

- date picker

Display summary:

```text
June 8 · on first use
```

### Step 4C: If repeat + date-time

Fields:

- preset:
  - daily
  - weekday
  - weekly
  - monthly
  - yearly
  - custom
- time of day
- weekday selection where relevant
- interval where relevant
- end condition:
  - never
  - on date
  - after N times

### Step 4D: If repeat + date-only

Fields:

- preset:
  - daily
  - weekday
  - weekly
  - monthly
  - yearly
  - custom
- no time of day
- weekday selection where relevant
- interval where relevant
- end condition:
  - never
  - on date
  - after N times

Display summaries:

```text
Every Monday · on first use
Every month on the 15th · on first use
Every 3 days · on first use
```

### Step 5: If you miss it?

Options:

- forget it
- keep showing it until I see it

Map to:

```ts
"drop_if_missed"
"keep_until_seen"
```

### Step 6: Title

- optional for attached reminders
- default to note title if empty
- required or strongly encouraged for standalone reminders

---

## UI: Edit Flow

Editing should expose the same structured model as creation.

### Editable fields

- title
- attachment, if allowed
- one-time vs recurring
- date-time vs date-only
- date/time or recurrence rule
- missed-reminder behavior
- active / paused / done

### V1 simplification

Do not support:

- edit only this occurrence
- edit this and future occurrences
- split recurring series

All edits apply to the reminder definition as a whole.

If editing changes schedule or time mode, recompute `next_fire_at` or `next_fire_date` from the edited definition.

---

## UI: Registry

The registry is the main management surface.

It should answer:

- what live reminders exist
- which are attached vs standalone
- which are one-time vs recurring
- which are date-time vs date-only
- which are active vs paused
- which are currently missed
- what fires next

### Registry fields

Suggested display fields:

- title
- attachment info
- note title if attached
- standalone badge if unattached
- schedule summary
- time mode
- missed behavior
- next fire time/date
- status

### Required filters

- active / paused / done
- attached / standalone
- one-time / recurring
- date-time / date-only
- currently missed
- source note

### Required sorting

- next fire time/date
- created date
- updated date
- title

### Search

Search should match:

- reminder title
- attached note title

Optional later:

- attached note content

V1 recommendation: title + note title only.

---

## UI: Missed Bucket

Do not build a full history page.

Build a lightweight missed surface for sticky reminders only.

### Missed bucket includes

Only reminders where:

```ts
is_currently_missed = true
persistence_mode = "keep_until_seen"
```

### Each item should show

- title
- note title if attached
- when it was missed
- recurrence / one-time summary
- time mode
- actions

### Actions

- acknowledge / dismiss
- mark done
- open linked note, if attached
- edit reminder
- pause reminder
- snooze, if implemented

---

## Display Rules

### Attached reminders

Display:

- reminder title
- linked note title
- affordance to jump to source note

Default title behavior:

- if user leaves title blank, default to note title

### Standalone reminders

Display:

- reminder title
- schedule summary

Default title behavior:

- require or strongly encourage explicit title
- do not rely on schedule alone to identify it

### Date-time schedule summaries

Examples:

```text
June 8, 9:00 AM
Every Monday at 9:00 AM
Every 2 weeks on Friday at 4:30 PM
```

### Date-only schedule summaries

Examples:

```text
June 8 · on first use
Every Monday · on first use
Every month on the 15th · on first use
```

---

## Scheduling / Background Processing

Implementation depends on platform, but the system needs a scheduler that can run in two ways:

1. **Time-based checks**
   - used for date-time reminders
   - checks due `next_fire_at`

2. **App-activity-based checks**
   - used for date-only reminders
   - triggered by non-idle app use
   - checks due or missed `next_fire_date`

### Scheduler responsibilities

The scheduler should:

- identify due reminders
- trigger notification/in-app surfacing
- update `last_fired_at`
- update `last_fired_date`
- update `next_fire_at` for date-time recurring reminders
- update `next_fire_date` for date-only recurring reminders
- mark sticky missed reminders as missed when appropriate
- drop expired occurrences for `drop_if_missed`

### Agent guidance

Use deterministic scheduling functions:

```ts
type ReminderEvaluationResult = {
  should_emit: boolean;
  emitted_events: ReminderRuntimeEvent[];
  updated_reminder: Reminder;
};

function evaluateReminder(
  reminder: Reminder,
  now: Date,
  context: ReminderEvaluationContext
): ReminderEvaluationResult;
```

Where context includes:

```ts
type ReminderEvaluationContext = {
  local_date: string; // YYYY-MM-DD
  app_activity?: AppActivityEvent;
};
```

Keep side effects outside evaluation:

```ts
evaluateReminder(...)
persistReminder(...)
renderInAppReminder(...)
```

---

## Suggested Derived Helpers

Implement reusable functions:

```ts
function isReminderAttached(reminder: Reminder): boolean;

function isReminderRecurring(reminder: Reminder): boolean;

function isReminderDateOnly(reminder: Reminder): boolean;

function getReminderDisplayTitle(
  reminder: Reminder,
  noteTitle?: string
): string;

function getReminderScheduleSummary(reminder: Reminder): string;

function getReminderNextFireLabel(reminder: Reminder): string | null;

function computeNextDateTimeOccurrence(
  reminder: Reminder,
  after: Date
): string | null;

function computeNextDateOnlyOccurrence(
  reminder: Reminder,
  afterLocalDate: string
): string | null;

function shouldFireDateTimeReminder(
  reminder: Reminder,
  now: Date
): boolean;

function shouldFireDateOnlyReminder(
  reminder: Reminder,
  now: Date,
  appActivity: AppActivityEvent
): boolean;

function shouldMarkDateOnlyReminderMissed(
  reminder: Reminder,
  now: Date,
  appActivity: AppActivityEvent
): boolean;

function fireReminder(
  reminder: Reminder,
  now: Date
): Reminder;

function acknowledgeReminder(
  reminder: Reminder,
  now: Date
): Reminder;

function dismissReminder(
  reminder: Reminder,
  now: Date
): Reminder;

function skipNextOccurrence(
  reminder: Reminder,
  now: Date
): Reminder;

function snoozeReminder(
  reminder: Reminder,
  snoozedUntil: Date
): Reminder;
```

Keep display helpers separate from mutation logic.

---

## Open Product Decisions

These should not block V1 unless the implementation requires a hard choice.

### 1. Exact definition of non-idle use

Need to decide:

- foreground app focus is enough?
- first user interaction after focus?
- first meaningful app action?
- what idle timeout?

Recommendation:

- V1: require foreground app plus user interaction
- do not count background startup or sync

### 2. External notification capability

Decision:

- browser/system push is not part of the reminder system
- do not model push as a reminder delivery channel
- keep reminder delivery in-app unless a separate local-notification design is explicitly requested later

### 3. Search scope for attached reminders

Need to decide:

- reminder title only
- reminder title + note title
- note content too

Recommendation:

- V1: reminder title + note title

### 4. Done semantics for recurring reminders

Recommendation:

- acknowledge/dismiss = resolve current visible reminder
- done = permanently stop reminder
- pause = temporarily disable future firing
- skip next = advance one recurrence

### 5. One-time date-only reminders after missed sticky display

Need to decide whether acknowledging a sticky missed one-time date-only reminder marks it done automatically.

Recommendation:

- yes, for one-time reminders
- recurring reminders continue after acknowledgement

---

## Non-Goals

Avoid scope creep into:

- task management
- workflows/projects
- event-relative scheduling
- habit tracking
- spaced repetition/review systems
- complex notification analytics
- full history/audit/event sourcing
- advanced timezone logic
- natural-language scheduling
- calendar interoperability
- arbitrary automation conditions

---

## Implementation Order

### Phase 1: Data + core runtime

Implement:

- reminder schema
- recurrence rule schema
- create/update/delete reminder storage
- `next_fire_at` calculation for date-time reminders
- `next_fire_date` calculation for date-only reminders
- due date-time detection
- non-idle app-use date-only detection
- sticky missed-state tracking

### Phase 2: Creation and edit UI

Implement:

- reminder builder flow
- reminder edit flow
- attached/unattached creation paths
- date-time vs date-only selection
- recurrence configuration UI
- schedule summaries

### Phase 3: Registry

Implement:

- searchable reminder registry
- filters
- sorting
- note-linked display
- active/paused/done management
- date-only display labels

### Phase 4: Missed bucket

Implement:

- missed-only surface for sticky reminders
- acknowledge/dismiss actions
- jump-to-note action
- pause/edit actions
- optional simple snooze

### Phase 5: Polish

Implement:

- better schedule summaries
- skip-next for recurring reminders
- default title improvements
- better empty states
- tests for date-only missed behavior

---

## Acceptance Criteria

V1 is complete when:

1. A user can create a reminder:
   - attached to a note
   - standalone

2. A user can choose:
   - once
   - recurring

3. A user can choose:
   - date-time
   - date-only

4. A user can choose:
   - forget if missed
   - keep until seen

5. Date-time reminders:
   - compute next fire time
   - fire when due
   - handle recurring schedules
   - handle missed sticky reminders

6. Date-only reminders:
   - fire on first non-idle app use on the relevant local date
   - do not use arbitrary default times such as morning
   - drop silently if missed and configured as `drop_if_missed`
   - surface as missed on next non-idle app use if configured as `keep_until_seen`

7. The user can:
   - search/filter live reminders
   - view currently missed sticky reminders
   - edit/pause/resume/delete reminders
   - acknowledge/dismiss reminders
   - mark reminders done
   - skip next occurrence for recurring reminders

8. The system avoids:
   - full occurrence history
   - task semantics
   - natural-language parsing
   - event-relative or condition-based reminders
   - browser/system push notifications

---

## Guidance for the Coding Agent

Build the smallest coherent system matching this plan.

Priorities:

1. keep the model simple
2. separate scheduling from missed-reminder persistence
3. model date-only reminders as app-use-gated calendar-day prompts
4. keep reminder creation fully UI-driven
5. optimize for note-attached and standalone reminders equally
6. avoid task-manager scope creep
7. avoid full history unless explicitly requested later

The most important architectural invariant:

```text
A reminder is not an occurrence stream.
A reminder is a definition with one current runtime state.
```

For date-only reminders, the most important product invariant:

```text
A date-only reminder does not fire at a default time.
It fires on first non-idle app use on the relevant local date.
```

This keeps the system app-centric, reliable where needed, and small enough for V1.
