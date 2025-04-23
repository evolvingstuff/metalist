/**
 * Mouse Events Handler for ModeManager
 * 
 * Handles all mouse-based interactions:
 * - Clicks on various UI elements
 * - Focus/blur events
 * - Input events in editable areas
 * - Drag and drop (future implementation)
 * 
 * Initially just observes and logs mouse events but doesn't
 * interfere with existing state machine behavior.
 */

import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';

/**
 * Initialize mouse event handlers
 * @returns {void}
 */
export function initMouseEvents() {
  // Register handlers in capture phase to ensure they run before state machine
  document.addEventListener('click', handleClick, { capture: true });
  document.addEventListener('input', handleInput, { capture: true });
  document.addEventListener('focusin', handleFocus, { capture: true });
  document.addEventListener('focusout', handleBlur, { capture: true });
  
  // Future implementations:
  // document.addEventListener('dragstart', handleDragStart, { capture: true });
  // document.addEventListener('drop', handleDrop, { capture: true });
  
  Logger.logInit('Mouse events handler');
}

/**
 * Handle click events
 * @param {MouseEvent} event - DOM click event
 */
function handleClick(event) {
  // Store click target and coordinates
  ModeContext.setClickTarget(event.target, {
    x: event.clientX,
    y: event.clientY
  });
  
  // Analyze click target
  const noteContent = event.target.closest('.note-content');
  const searchField = event.target.closest('#search-input');
  const createButton = event.target.closest('#create-note-button');
  
  // Update mode based on what was clicked
  if (noteContent) {
    const noteElement = noteContent.closest('.note');
    const noteId = noteElement?.dataset.noteId;
    
    ModeContext.setCurrentNoteId(noteId);
    ModeContext.setEditing(true);
    ModeContext.setSearching(false);
    
    Logger.logDebug('Click in note content', { noteId });
  } else if (searchField) {
    ModeContext.setSearching(true);
    Logger.logDebug('Click in search field');
  } else if (createButton) {
    Logger.logDebug('Create note button clicked');
    // Future implementation: ModeContext.createNewNote();
  }
  
  // Don't prevent default or stop propagation - let event reach state machine
}

/**
 * Handle input events
 * @param {Event} event - DOM input event
 */
function handleInput(event) {
  const noteContent = event.target.closest('.note-content');
  const searchField = event.target.closest('#search-input');
  
  if (noteContent) {
    ModeContext.setEditing(true);
    Logger.logDebug('Note content changed');
    
    // Get current content for future dirty state tracking
    // const content = noteContent.textContent || noteContent.innerText;
    // ModeContext.setCurrentContent(content);
  } else if (searchField) {
    const searchQuery = searchField.value;
    ModeContext.setSearchQuery(searchQuery);
    ModeContext.setSearching(true);
    
    Logger.logDebug('Search query changed', { query: searchQuery });
  }
}

/**
 * Handle focus events
 * @param {FocusEvent} event - DOM focusin event
 */
function handleFocus(event) {
  const searchField = event.target.closest('#search-input');
  const noteContent = event.target.closest('.note-content');
  
  if (searchField) {
    ModeContext.setSearching(true);
    Logger.logDebug('Search field focused');
  } else if (noteContent) {
    const noteElement = noteContent.closest('.note');
    const noteId = noteElement?.dataset.noteId;
    
    ModeContext.setCurrentNoteId(noteId);
    ModeContext.setEditing(true);
    
    Logger.logDebug('Note content focused', { noteId });
  }
}

/**
 * Handle blur events
 * @param {FocusEvent} event - DOM focusout event
 */
function handleBlur(event) {
  const searchField = event.target.closest('#search-input');
  const noteContent = event.target.closest('.note-content');
  
  if (searchField) {
    // Only exit search mode if search is empty
    if (!ModeContext.searchQuery) {
      ModeContext.setSearching(false);
      Logger.logDebug('Search field blurred and empty');
    }
  } else if (noteContent) {
    // Don't exit editing mode yet - that will depend on our app design
    // Just log for now
    Logger.logDebug('Note content blurred', { 
      noteId: ModeContext.currentNoteId 
    });
  }
}