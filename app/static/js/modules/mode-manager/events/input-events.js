/**
 * Input Events Handler for ModeManager
 * 
 * Handles all input-based interactions:
 * - Text input in note content
 * - Search field input
 * - Form inputs (future implementation)
 */

import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { selectNote } from '../actions.js';

/**
 * Initialize input event handlers
 * @returns {void}
 */
export function initInputEvents() {
  // Register handlers in capture phase to ensure they run before state machine
  document.addEventListener('input', handleInput, { capture: true });
  
  Logger.logInit('Input events handler');
}

/**
 * Handle input events
 * @param {Event} event - DOM input event
 */
function handleInput(event) {
  if (!event) {
    throw new Error('handleInput called without an event object');
  }
  
  if (!event.target) {
    throw new Error('Input event missing target element');
  }
  
  const noteContent = event.target.closest('.note-content');
  const searchField = event.target.closest('#search-input');
  
  if (noteContent) {
    const noteElement = noteContent.closest('.note');
    if (!noteElement) {
      throw new Error('Found .note-content without parent .note element in input handler');
    }
    
    const noteId = noteElement.dataset.noteId;
    if (!noteId) {
      throw new Error('Note element missing data-note-id attribute in input handler');
    }
    
    // Set dirty flag since content has changed
    ModeContext.setDirty(true);
    
    // Ensure we're in editing mode for this note
    if (!ModeContext.isEditing || ModeContext.currentNoteId !== noteId) {
      selectNote(noteId);
    }
    
    Logger.logDebug('Note content changed', { noteId }, Logger.LogCategory.EVENT);
  } else if (searchField) {
    if (searchField.value === undefined) {
      throw new Error('Search field has no value property');
    }
    
    const searchQuery = searchField.value;
    ModeContext.setSearchQuery(searchQuery);
    ModeContext.setSearching(true);
    ModeContext.validate();
    
    Logger.logDebug('Search query changed', { query: searchQuery }, Logger.LogCategory.EVENT);
  }
}