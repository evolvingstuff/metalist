# Move Fragment Updates to State Transitions

## Overview
Move fragment updates from API calls to state enter functions to make UI updates more explicit and state-driven.

## Tasks

### API Client Changes
- [ ] Remove `reloadOnSuccess` parameter from `_apiCall`
- [ ] Remove fragment fetching logic from `_apiCall`
- [ ] Update all API call sites to remove any `reloadOnSuccess` parameters

### State Machine Changes
- [ ] Add `fetchFragment` utility function to state machine controller
- [ ] Add fragment fetching to state enter functions:
  - [ ] idle state
  - [ ] editing state
  - [ ] searching state
- [ ] Remove FRAGMENT_LOADED event handling from event mapper

### Documentation
- [ ] Update state machine documentation with new fragment update flow
- [ ] Add comments explaining fragment update strategy
- [ ] Update API client documentation to remove reloadOnSuccess references