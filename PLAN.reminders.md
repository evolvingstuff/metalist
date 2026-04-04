# Reminder System Plan

## Goal

Implement a **simple, reliable reminder system** for a PKMS with the following constraints:

- Reminders can be either:
  - **attached to a note**, or
  - **unattached**
- Reminders can be either:
  - **one-time**, or
  - **recurring**
- Reminder creation/editing should be **entirely UI-driven**
- No natural-language reminder parsing
- No task/project semantics
- No event-relative reminders
- No condition-based reminders
- No review/spaced-repetition features
- No full reminder history in V1
- Support different behavior for **missed reminders** on a **per-reminder** basis

This system should be treated as **scheduled prompts**, not a task manager and not a review engine.

---

## V1 Scope

### Must support

1. **Attachment mode**
   - attached to a note
   - unattached

2. **Schedule mode**
   - one-time
   - recurring

3. **Delivery mode**
   - in-app
   - push
   - both

4. **Missed-reminder behavior**
   - drop if missed
   - keep until seen

5. **Reminder management**
   - searchable live registry of current reminders
   - lightweight missed bucket for sticky reminders

### Explicitly out of scope for V1

- natural language input
- embedded note syntax for reminders
- event-relative reminders
- condition-like reminders
- review / spaced repetition
- full reminder history / audit log
- advanced timezone behavior
- task workflows
- complex per-occurrence editing semantics

---

## Product Model

A reminder is a standalone object with:

- an optional note attachment
- a schedule
- a delivery policy
- a missed-reminder policy
- a lifecycle state

### Product framing

Reminders are:

- **scheduled prompts**
- optionally linked to a note
- delivered according to user-selected persistence behavior

This is intentionally narrower than a task system.

---

## Core Concepts

### 1. Attachment

A reminder is either:

- **attached**
  - references a note
- **unattached**
  - standalone reminder with no note reference

### 2. Schedule

A reminder is either:

- **one-time**
- **recurring**

### 3. Delivery

Per reminder, the user chooses:

- **in-app**
- **push**
- **both**

### 4. Missed behavior

Per reminder, the user chooses:

- **drop_if_missed**
  - if the user is not around when it fires, it disappears
- **keep_until_seen**
  - if missed, it remains visible until acknowledged/dismissed

This is the most important product distinction in the design.

---

## Data Model

Use a single `reminders` table/object in V1. Avoid storing full occurrence history.

## Reminder schema

```ts
type ReminderStatus = "active" | "paused" | "done";

type ReminderAttachmentType = "attached" | "unattached";

type ReminderScheduleKind = "one_time" | "recurring";

type ReminderDeliveryChannel = "in_app" | "push" | "both";

type ReminderPersistenceMode = "drop_if_missed" | "keep_until_seen";

type Reminder = {
  id: string;

  // attachment
  note_id: string | null;

  // display
  title: string;

  // derived or explicit classification
  attachment_type: ReminderAttachmentType;
  schedule_kind: ReminderScheduleKind;

  // one-time
  scheduled_at: string | null; // ISO datetime

  // recurring
  recurrence_rule: RecurrenceRule | null;

  // delivery
  delivery_channel: ReminderDeliveryChannel;
  persistence_mode: ReminderPersistenceMode;

  // lifecycle
  status: ReminderStatus;

  // scheduling/runtime
  next_fire_at: string | null;     // ISO datetime
  last_fired_at: string | null;    // ISO datetime
  last_seen_at: string | null;     // ISO datetime

  // lightweight missed state
  is_currently_missed: boolean;
  missed_since: string | null;     // ISO datetime
  missed_count: number;

  // metadata
  created_at: string;
  updated_at: string;
};
```

---

## Recurrence Rule Model

Keep recurrence intentionally narrow in V1.

```ts
type RecurrenceFrequency = "daily" | "weekly" | "monthly" | "yearly";

type RecurrenceEnd =
  | { type: "never" }
  | { type: "on_date"; value: string } // ISO date
  | { type: "after_count"; value: number };

type RecurrenceRule = {
  frequency: RecurrenceFrequency;
  interval: number; // every N units

  // weekly
  weekdays?: number[]; // 0-6 or 1-7, choose one convention and keep it consistent

  // monthly
  day_of_month?: number;

  // yearly
  month?: number;
  day?: number;

  end: RecurrenceEnd;

  // optional time component if recurring fires at a specific time
  time_of_day?: string | null; // "HH:mm"
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
- DST edge-case sophistication beyond normal local scheduling

---

## Runtime Scheduling Semantics

## One-time reminders

- `scheduled_at` is the fire time
- when fired:
  - update `last_fired_at`
  - if `persistence_mode = drop_if_missed`:
    - send/display if possible
    - then mark done or clear from active runtime flow
  - if `persistence_mode = keep_until_seen`:
    - if not seen, mark as missed and keep visible

## Recurring reminders

- `next_fire_at` tracks the next scheduled occurrence
- when fired:
  - update `last_fired_at`
  - compute next occurrence immediately
  - if `keep_until_seen`, current missed state can remain visible until user handles it
- V1 does **not** need full per-occurrence records

### Important simplification

Do **not** build an occurrence/event log in V1.
Only keep enough state to answer:

- what exists now
- what fires next
- what is currently missed/overdue
- what has been seen recently enough to suppress sticky state

---

## Missed Reminder Model

Instead of a full history system, implement only lightweight missed-state tracking.

### Fields used

- `last_fired_at`
- `is_currently_missed`
- `missed_since`
- `missed_count`

### Semantics

#### For `drop_if_missed`

- if the scheduled time passes and the user does not receive/see it in time, do not keep it around
- do not show in missed bucket

#### For `keep_until_seen`

- if the reminder fires and is not seen/acknowledged, mark:
  - `is_currently_missed = true`
  - `missed_since = fire_time`
  - increment `missed_count`
- keep it visible in-app until the user dismisses/acknowledges it

This provides the reliability value of “missed reminders” without full history complexity.

---

## Lifecycle States

Keep the state machine small.

### Reminder definition status

- `active`
- `paused`
- `done`

### Runtime display state (derived, not necessarily stored separately)

- scheduled
- due now
- missed

### Notes

- `missed` only meaningfully applies to sticky reminders (`keep_until_seen`)
- avoid introducing extra states unless a concrete UX requirement appears

---

## UI: Creation Flow

Reminder creation should be fully UI-driven and branching.

## Reminder builder flow

### Step 1: What is this reminder for?

Options:

- **This note**
- **Standalone reminder**

Behavior:

- if launched from a note, preselect “This note”
- if standalone, no note reference

### Step 2: When should it happen?

Options:

- **Once**
- **Repeat**

### Step 3A: If once

Fields:

- date picker
- optional time picker
- all-day toggle (optional, if product supports date-only reminders)

### Step 3B: If repeat

Fields:

- preset:
  - daily
  - weekday
  - weekly
  - monthly
  - yearly
  - custom
- for weekly:
  - choose weekdays
- for custom:
  - every N units
- end condition:
  - never
  - on date
  - after N times

### Step 4: How should it reach you?

Options:

- in-app
- push
- both

### Step 5: If you miss it?

Options:

- forget it
- keep showing it until I see it

### Step 6: Title

- optional for attached reminders
  - default to note title if empty
- required or strongly encouraged for unattached reminders

---

## UI: Edit Flow

Editing should expose the same structured model as creation.

### Editable fields

- title
- attachment (possibly read-only if attached-from-note flow should remain fixed)
- one-time vs recurring
- time/date / recurrence rule
- delivery channel
- missed-reminder behavior
- active / paused / done

### V1 simplification

Do **not** support:
- edit only this occurrence
- edit this and future occurrences
- series splitting semantics

All edits apply to the reminder definition as a whole.

---

## UI: Registry

The registry is the main management surface.

It should answer:

- what live reminders exist
- which are attached vs unattached
- which are one-time vs recurring
- which are active vs paused
- which are currently missed
- what fires next

## Registry columns / fields to show

Suggested display fields:

- title
- attachment info
  - note title if attached
  - standalone badge if unattached
- schedule summary
- delivery mode
- missed behavior
- next fire time
- status

## Required filters

- active / paused / done
- attached / unattached
- one-time / recurring
- delivery type
- currently missed
- source note

## Required sorting

- next fire time
- created date
- updated date
- title

## Search

Search should match:

- reminder title
- attached note title
- optionally attached note content later, but not required for V1

---

## UI: Missed Bucket

Do not build a full history page.
Build a lightweight “missed” surface for sticky reminders only.

### Missed bucket includes

- reminders with `is_currently_missed = true`
- only reminders with `persistence_mode = keep_until_seen`

### Each item should show

- title
- note title if attached
- when it was missed
- recurrence / one-time summary
- actions

### Actions

- acknowledge / dismiss
- mark done
- open linked note (if attached)
- edit reminder
- pause reminder

---

## Key User Actions

Support these in V1:

- acknowledge
- dismiss
- mark done
- pause
- resume
- edit
- delete

### Additional useful action

- **skip next occurrence** for recurring reminders

This is helpful and still within reasonable scope.

### Out of scope for V1

- edit this occurrence only
- convert to task
- per-occurrence snooze history
- complex occurrence inspection

---

## Display Rules

## Attached reminders

Display:

- reminder title
- linked note title
- affordance to jump to source note

Default title behavior:

- if user leaves title blank, default to note title

## Unattached reminders

Display:

- reminder title only

Default title behavior:

- require or strongly encourage explicit title
- do not rely on schedule alone to identify it

---

## Scheduling / Background Processing

Implementation will depend on platform, but the system needs a scheduler that:

- identifies due reminders
- triggers notification/in-app surfacing
- updates `last_fired_at`
- updates `next_fire_at` for recurring reminders
- marks sticky missed reminders as missed when appropriate

### Agent guidance

Use a deterministic scheduling function:

- input: current reminder record + current time
- output:
  - should fire now?
  - updated reminder record
  - any emitted notification/in-app events

Keep this logic centralized so UI and runtime stay consistent.

---

## Suggested Derived Helpers

Implement reusable functions:

```ts
function isReminderAttached(reminder: Reminder): boolean;
function isReminderRecurring(reminder: Reminder): boolean;
function getReminderDisplayTitle(reminder: Reminder, noteTitle?: string): string;
function getReminderScheduleSummary(reminder: Reminder): string;
function getReminderNextFireAt(reminder: Reminder): string | null;
function isReminderCurrentlyMissed(reminder: Reminder, now: Date): boolean;
function fireReminder(reminder: Reminder, now: Date): Reminder;
function acknowledgeReminder(reminder: Reminder, now: Date): Reminder;
function dismissReminder(reminder: Reminder, now: Date): Reminder;
function skipNextOccurrence(reminder: Reminder, now: Date): Reminder;
```

Keep display helpers separate from mutation logic.

---

## Open Product Decisions

The coding agent should preserve room for these, but not block V1 on them.

### 1. All-day one-time reminders
Need decision:
- supported in V1
- or require a time

Recommendation:
- support date-only reminders if the PKMS already has date-only UI patterns

### 2. Push capability
Need decision:
- platform supports push now
- or only in-app in first implementation

Recommendation:
- model `delivery_channel` now even if push arrives later

### 3. Search scope for attached reminders
Need decision:
- search reminder title only
- or reminder title + note title
- or note content too

Recommendation:
- V1: title + note title only

### 4. Done semantics for recurring reminders
Need decision:
- “done” permanently stops recurrence
- or only resolves current missed state

Recommendation:
- use:
  - **dismiss/acknowledge** = resolve current visible reminder
  - **done** = permanently stop reminder

---

## Non-Goals

The agent should avoid scope creep into:

- task management
- workflows/projects
- event-relative scheduling
- habit tracking
- spaced repetition/review systems
- complex notification analytics
- full history/audit/event sourcing
- advanced timezone logic

---

## Implementation Order

### Phase 1: Data + core runtime

Implement:

- reminder schema
- recurrence rule schema
- create/update/delete reminder storage
- `next_fire_at` calculation
- due reminder detection
- sticky missed-state tracking

### Phase 2: Creation and edit UI

Implement:

- reminder builder flow
- reminder edit flow
- attached/unattached creation paths
- recurrence configuration UI

### Phase 3: Registry

Implement:

- searchable reminder registry
- filters
- sorting
- note-linked display
- active/paused/done management

### Phase 4: Missed bucket

Implement:

- missed-only surface for sticky reminders
- acknowledge/dismiss actions
- jump-to-note action
- pause/edit actions

### Phase 5: polish

Implement:

- better schedule summaries
- skip-next for recurring reminders
- default title improvements
- better empty states and registry UX

---

## Acceptance Criteria

V1 is complete when:

1. A user can create a reminder:
   - attached to a note
   - or unattached

2. A user can choose:
   - once
   - or recurring

3. A user can choose:
   - in-app
   - push
   - or both

4. A user can choose:
   - forget if missed
   - or keep until seen

5. The system can:
   - compute next fire time
   - fire due reminders
   - keep sticky missed reminders visible
   - avoid storing full history

6. The user can:
   - search/filter live reminders
   - view currently missed sticky reminders
   - edit/pause/delete reminders

---

## Guidance for the Coding Agent

Build the smallest coherent system matching the plan.

Priorities:

1. keep the model simple
2. separate scheduling from missed-reminder persistence
3. keep reminder creation fully UI-driven
4. optimize for note-attached and unattached reminders equally
5. avoid task-manager scope creep
6. do not add full history unless explicitly requested later

The most important architectural decision is to treat these as:

- reminder definitions with optional note attachment
- simple runtime state
- lightweight missed-state tracking

and **not** as a full event/occurrence history system.
