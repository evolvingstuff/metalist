# Differential Delta Plan

Refer to `docs/design/differential-view-protocol.md` for the definitive request/response contract, reconciliation flow, and testing guidance. This plan defers all protocol specifics to that document.

## Implementation Checklist
- [ ] Server: update `/api/notes/view` to accept the JSON POST payload and generate the diff response as documented.
- [ ] Client: post the hash tuples, apply the diff response to the DOM, and maintain the hash cache.
- [ ] Instrumentation/docs: keep the design doc current and confirm perf improvements.

