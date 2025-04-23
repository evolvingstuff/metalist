/**
 * Keyboard Events Handler for ModeManager
 * 
 * Handles all keyboard interactions:
 * - Key presses (including special keys like Escape, Enter)
 * - Keyboard shortcuts with modifier keys
 * - Text input in editable areas
 * 
 * Initially just observes and logs keyboard events but doesn't
 * interfere with existing state machine behavior.
 */

import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';

/**
 * Initialize keyboard event handlers
 * @returns {void}
 */
export function initKeyboardEvents() {
  // Register handlers in capture phase to ensure they run before state machine
  document.addEventListener('keydown', handleKeyDown, { capture: true });
  
  Logger.logInit('Keyboard events handler');
}

/**
 * Handle keydown events
 * @param {KeyboardEvent} event - DOM keydown event
 */
function handleKeyDown(event) {
  // Store key state in context
  ModeContext.setKeyPressed(
    event.key,
    event.metaKey || event.ctrlKey,
    event.shiftKey
  );
  
  // Log event but don't modify state yet
  Logger.logDebug('Key pressed', {
    key: event.key,
    meta: event.metaKey || event.ctrlKey,
    shift: event.shiftKey
  });
  
  // Handle special keys
  switch (event.key) {
    case 'Escape':
      handleEscapeKey();
      break;
    case 'Enter':
      handleEnterKey(event);
      break;
    case '/':
      if (event.metaKey || event.ctrlKey) {
        handleSearchShortcut();
      }
      break;
    // More key handlers will be added here as needed
  }
  
  // Don't prevent default or stop propagation - let event reach state machine
}

/**
 * Handle Escape key
 * Used to cancel search, exit editing, etc.
 */
function handleEscapeKey() {
  if (ModeContext.isSearching) {
    ModeContext.setSearching(false);
    Logger.logDebug('Search cancelled via Escape key');
  }
  
  // Initially don't handle other escape scenarios
  // We'll expand this as we migrate more functionality
}

/**
 * Handle Enter key
 * @param {KeyboardEvent} event - Original keydown event
 */
function handleEnterKey(event) {
  // Just log for now - logic to be implemented later
  Logger.logDebug('Enter key pressed', {
    inEditor: ModeContext.isEditing,
    noteId: ModeContext.currentNoteId
  });
}

/**
 * Handle search shortcut (Cmd+/ or Ctrl+/)
 */
function handleSearchShortcut() {
  ModeContext.setSearching(true);
  Logger.logDebug('Search activated via keyboard shortcut');
  
  // Focus search input (will be implemented once we start handling events)
  // const searchInput = document.getElementById('search-input');
  // if (searchInput) searchInput.focus();
}