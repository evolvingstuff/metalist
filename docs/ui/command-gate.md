# Command Gate (Client Busy/Loading Model)

## Goal
Prevent UI lockups and request interleaving by centralizing “busy” handling.

## Core Rule
All **user-initiated server-bound actions** must run through `CommandGate.run(name, asyncFn)`.

`CommandGate` responsibilities:
- Set/clear `ModeContext.isLoading` (the only place allowed to call `ModeContext.setLoading(...)`).
- Drop inputs while busy (no queueing/coalescing/replay).
- Maintain a watchdog timer that throws if a command never finishes.

## Why
- Keyboard/mouse handlers globally ignore input when `ModeContext.isLoading` is true.
- Before `CommandGate`, multiple async paths flipped `isLoading` manually; any missed `setLoading(false)` could hard-freeze the UI.
- Background loops (polling/infinite-scroll/tab-state) can interleave with user commands unless explicitly blocked.

## Implementation
- `CommandGate`: `app/static/js/modules/mode-manager/services/command-gate-service.js`

## Background Traffic Policy
Background loops must not generate traffic while a user command is in-flight.
Pattern:
- Add `if (CommandGate.isBusy()) return;` at the top of the poller.

## Adding a New User Action
1. Wrap the action:
   - `void CommandGate.run('some.action', async () => { ... })`
2. Do not call `ModeContext.setLoading(true/false)` directly.
3. If you need refresh, call `actionRefreshAndMaybeSelect(...)` inside the gate.

