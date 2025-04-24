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
import { createNote, deleteNote } from '../actions/note-actions.js';
import { deselectNote } from '../actions/selection-actions.js';

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
  if (!event) {
    throw new Error('handleKeyDown called without an event object');
  }
  
  if (typeof event.key !== 'string') {
    throw new Error(`Invalid KeyboardEvent: missing or invalid key property: ${event.key}`);
  }
  
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
  }, Logger.LogCategory.EVENT);
  
  // If in editing mode and key is a content-changing key, mark content as dirty
  if (ModeContext.isEditing) {
    // Ignore special keys and modifier-only key presses
    const isModifierKey = event.key === 'Control' || event.key === 'Alt' || 
                          event.key === 'Shift' || event.key === 'Meta';
    const isNavigationKey = event.key === 'ArrowUp' || event.key === 'ArrowDown' || 
                            event.key === 'ArrowLeft' || event.key === 'ArrowRight' ||
                            event.key === 'Home' || event.key === 'End' || 
                            event.key === 'PageUp' || event.key === 'PageDown';
    const isFunctionKey = event.key.startsWith('F') && event.key.length > 1; // F1-F12 keys
                            
    // Only mark as dirty for content-changing keys
    if (!isModifierKey && !isNavigationKey && !isFunctionKey && 
        !event.ctrlKey && !event.metaKey && event.key !== 'Escape') {
      
      // Let's log that we're about to mark content as dirty
      Logger.logDebug('Detected content-changing keypress', {
        key: event.key,
        noteId: ModeContext.currentNoteId
      }, Logger.LogCategory.EVENT);
      
      // Set the dirty flag if not already set
      if (!ModeContext.isDirty) {
        ModeContext.setDirty(true);
        Logger.logDebug('Content marked as dirty due to typing', {
          key: event.key,
          noteId: ModeContext.currentNoteId
        }, Logger.LogCategory.STATE);
      }
    }
  }
  
  // Handle special keys
  switch (event.key) {
    case 'Escape':
      handleEscapeKey();
      break;
    case 'Enter':
      if (event.metaKey) {
        handleCreateNoteShortcut(event);
      } else if (event.ctrlKey) {
        handleCreateNoteShortcut(event);
      } else {
        handleEnterKey(event);
      }
      break;
    case 'Backspace':
    case 'Delete':
      if (event.metaKey) {
        handleDeleteNoteShortcut(event);
      } else if (event.ctrlKey) {
        handleDeleteNoteShortcut(event);
      }
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
  if (ModeContext.isSearching === undefined) {
    throw new Error('ModeContext missing isSearching property in handleEscapeKey');
  }
  
  if (ModeContext.isSearching) {
    ModeContext.setSearching(false);
    ModeContext.validate();
    Logger.logDebug('Search cancelled via Escape key', {}, Logger.LogCategory.EVENT);
  }
  else if (ModeContext.isEditing) {
    // Call the action instead of modifying state directly
    deselectNote();
    
    Logger.logDebug('Editing cancelled via Escape key', {
      previousNoteId: ModeContext.currentNoteId // Will capture the ID before deselectNote completes
    }, Logger.LogCategory.EVENT);
  }
  else {
    // Escape pressed but no action was taken - log as NOOP
    Logger.logNoop('Escape key pressed but had no effect', {
      isSearching: ModeContext.isSearching,
      isEditing: ModeContext.isEditing
    });
  }
}

/**
 * Handle Enter key
 * @param {KeyboardEvent} event - Original keydown event
 */
function handleEnterKey(event) {
  if (!event) {
    throw new Error('handleEnterKey called without an event object');
  }
  
  if (ModeContext.isEditing === undefined) {
    throw new Error('ModeContext missing isEditing property in handleEnterKey');
  }
  
  // Just log for now - logic to be implemented later
  Logger.logDebug('Enter key pressed', {
    inEditor: ModeContext.isEditing,
    noteId: ModeContext.currentNoteId
  });
  
  // If we make any state changes in the future, we'd validate here
  // ModeContext.validate();
}

/**
 * Handle create note shortcut (Cmd+Enter or Ctrl+Enter)
 * @param {KeyboardEvent} event - Original keydown event
 */
function handleCreateNoteShortcut(event) {
  if (!event) {
    throw new Error('handleCreateNoteShortcut called without an event object');
  }
  
  // Log the shortcut activation
  Logger.logDebug('Create note shortcut triggered', {
    isEditing: ModeContext.isEditing,
    currentNoteId: ModeContext.currentNoteId
  }, Logger.LogCategory.EVENT);
  
  // Prevent default browser action
  event.preventDefault();
  
  // Call createNote which already handles context-aware creation
  createNote();
}

/**
 * Handle delete note shortcut (Cmd+Delete or Ctrl+Delete)
 * @param {KeyboardEvent} event - Original keydown event
 */
function handleDeleteNoteShortcut(event) {
  if (!event) {
    throw new Error('handleDeleteNoteShortcut called without an event object');
  }
  
  const noteId = ModeContext.currentNoteId;
  
  // Log the shortcut activation
  Logger.logDebug('Delete note shortcut triggered', {
    isEditing: ModeContext.isEditing,
    currentNoteId: noteId
  }, Logger.LogCategory.EVENT);
  
  // Prevent default browser action
  event.preventDefault();
  
  // Only try to delete if we have a note selected
  if (noteId) {
    // The deleteNote function already handles validation about editing state
    deleteNote(noteId);
  } else {
    // No note to delete - log as NOOP
    Logger.logNoop('Delete shortcut pressed but no note is selected', {
      isEditing: ModeContext.isEditing,
      currentNoteId: null
    });
  }
}

/**
 * Handle search shortcut (Cmd+/ or Ctrl+/)
 */
function handleSearchShortcut() {
  if (typeof ModeContext.setSearching !== 'function') {
    throw new Error('ModeContext missing setSearching method in handleSearchShortcut');
  }
  
  ModeContext.setSearching(true);
  ModeContext.validate();
  Logger.logDebug('Search activated via keyboard shortcut');
  
  // Focus search input (will be implemented once we start handling events)
  // const searchInput = document.getElementById('search-input');
  // if (searchInput) searchInput.focus();
}