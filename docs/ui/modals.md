# Modal Architecture Pattern

## Overview

This document defines the standard pattern for implementing modal dialogs in the application. All modals must follow this architecture for consistency and maintainability.

## Design Principles

### 1. **Centralized State Management**
- **ALL modal state lives in ModeContext** - no exceptions
- Modal-specific state stored in `ModeContext.modalState = {modalName: {...}}`
- Modal lifecycle managed via `ModeContext.modalStack = []` (empty = no modals open)

### 2. **Clean State Enforcement**
- **Notes must be closed** (exit editing mode) before opening any modal
- **BaseModal throws error** if opening when application is in active state:
  - `ModeContext.currentNoteId` exists (editing state)
  - In searching state  
  - Any other "active" state that should be closed first
- Caller responsible for cleaning state before attempting to open modal
- Modal callers are expected to clean state before opening a modal.

### 3. **Event Handling Integration**
- Follow existing pattern in `keyboard-events.js` (like Esc key handler)
- Keyboard events still fire but check modal state and defer appropriately
- Operations like Cmd+Enter (new note) require modal to be closed first
- Modal has precedence - if modal open, modal-specific logic handles events

## File Organization

```
app/static/js/modules/modals/
├── base-modal.js       # BaseModal class with state enforcement
└── password-modal.js   # Password management modal
└── note-layout-appearance-modal.js # Namespace-scoped note layout presets + preview
└── [future-modal].js   # Other modals follow same pattern
```

## Implementation Pattern

### BaseModal Class

All modals extend BaseModal which provides:

1. **State Validation**
   - Throws error if opening with dirty application state
   - Enforces clean state requirement

2. **ModeContext Integration**  
   - Updates `ModeContext.modalStack` on open/close
   - Sets modal-specific state in `ModeContext.modalState`

3. **Common Event Handling**
   - `Escape` closes every modal
   - Clicking outside the modal content closes every modal
   - `Enter` activates the modal's single declared primary action; modals with multi-step or input-specific behavior implement the equivalent explicitly
   - Focus management

### Modal Opening Flow

1. User triggers a modal from the command palette or another UI control.
2. Handler checks current application state
3. If editing/searching → save + exit editing and/or exit search first
4. Attempt `new ModalClass().open()`
5. BaseModal enforces clean state (throws error if dirty)
6. Modal opens and updates `ModeContext.modalStack`
7. Modal-specific initialization runs

### Modal State Management

```javascript
// Example modal state structure
ModeContext.modalState = {
  passwordModal: {
    mode: 'create', // 'create' | 'change' | 'remove'
    currentStep: 1,
    formData: {...},
    isProcessing: false
  }
};

// Modal stack for stacking support
ModeContext.modalStack = ['passwordModal']; // Active modals in order
```

### Keyboard Event Integration

```javascript
// In keyboard-events.js
function handleKeyDown(event) {
  // Check if modal is open
  if (ModeContext.modalStack.length > 0) {
    const activeModal = ModeContext.modalStack[ModeContext.modalStack.length - 1];
    // Defer to modal-specific event handling
    return deferToModal(activeModal, event);
  }
  
  // Normal application event handling
  // ...
}
```

## Modal Lifecycle

### Opening a Modal
1. Validate clean application state
2. Add to modal stack
3. Set modal-specific state
4. Show modal UI
5. Set up modal-specific event listeners

### Closing a Modal  
1. Clean up modal-specific event listeners
2. Remove modal-specific state
3. Remove from modal stack
4. Hide modal UI
5. Return focus to application

### Modal Stacking
- Modals can stack via `ModeContext.modalStack`
- Top modal receives events
- Closing top modal reveals previous modal
- Rarely used but architecture supports it

## Example Implementation

### BaseModal Class Structure
```javascript
class BaseModal {
  constructor(modalName) {
    this.modalName = modalName;
  }
  
  open() {
    this.validateCleanState();
    this.addToModalStack();
    this.setupModalState();
    this.showModal();
    this.setupEventListeners();
  }
  
  close() {
    this.cleanupEventListeners();
    this.hideModal();
    this.removeModalState();
    this.removeFromModalStack();
  }
  
  validateCleanState() {
    if (ModeContext.currentNoteId) {
      throw new Error('Cannot open modal while editing note');
    }
    if (ModeContext.isSearching) {
      throw new Error('Cannot open modal while in search mode');
    }
    // Add other state validations
  }
}
```

### Keyboard Shortcut Handler
```javascript
// In keyboard-events.js
if (event.metaKey && event.key === 'p') {
  event.preventDefault();
  
  // Clean state first
  if (ModeContext.currentNoteId) {
    await exitEditingMode();
  }
  
  // Open modal
  const passwordModal = new PasswordModal();
  passwordModal.open();
}
```

## Benefits of This Architecture

1. **Consistency** - All modals follow same pattern
2. **State Safety** - Clean state enforcement prevents conflicts
3. **Integration** - Works seamlessly with existing ModeContext system
4. **Scalability** - Easy to add new modals following same pattern
5. **Maintainability** - Clear separation of concerns
6. **Debuggability** - All state centralized and inspectable

## Future Considerations

- Modal animations/transitions
- Modal size variants (small, medium, large)
- Modal positioning (center, top, custom)
- Nested modal content (tabs within modals)
- Modal templates for common patterns

All future enhancements must maintain compatibility with this base architecture.
