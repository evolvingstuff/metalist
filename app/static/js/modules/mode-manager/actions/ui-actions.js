/**
 * UI Actions for ModeManager
 * 
 * Actions related to UI updates, fragments, and DOM manipulation
 */

import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { NotesAPI } from '../../api-client.js';
import { DOMUtils } from '../../dom-utils.js';

/**
 * Refresh UI with latest content from server
 * Gets fragment from server and updates the DOM based on current context
 * Also handles editability and cursor positioning if a note is selected
 * @param {Object} options - Options for refresh
 * @param {boolean} options.skipLoadingState - If true, doesn't set/clear loading state (for composing actions)
 * @returns {Promise} Promise resolving when refresh is complete
 */
export async function refresh(options = {}) {
  Logger.logAction('refresh', { 
    noteId: ModeContext.currentNoteId,
    isEditing: ModeContext.isEditing
  });
  
  // Always use the current note ID from context
  const noteId = ModeContext.currentNoteId;
  
  // Set loading state if not already set and not skipped
  const shouldManageLoading = !options.skipLoadingState;
  if (shouldManageLoading && !ModeContext.isLoading) {
    ModeContext.setLoading(true);
  }
  
  // Call the API to get the fragment
  const html = await NotesAPI.getFragment(noteId);
  
  // Update the notes container with new HTML
  const notesContainer = document.getElementById('notes-container');
  if (!notesContainer) {
    throw new Error('Notes container not found');
  }
  
  notesContainer.innerHTML = html;
  
  // If we have a current note, get its content and handle editability
  if (noteId) {
    const noteElement = DOMUtils.getNoteById(noteId);
    const contentHtml = DOMUtils.getNoteContentHTML(noteElement);
    
    // Store content in context
    ModeContext.setCurrentContent(contentHtml);
    
    // If we're in editing mode, make the note editable and position cursor
    if (ModeContext.isEditing) {
      // Make note editable
      DOMUtils.setNoteEditable(noteElement, true);
      
      // Position cursor and focus the note
      let cursorOffset = 0;
      
      if (ModeContext._savedCursorOffset && ModeContext._savedCursorOffset.noteId === noteId) {
        // Use stored offset directly
        cursorOffset = ModeContext._savedCursorOffset.offset;
        
        // Clean up
        ModeContext._savedCursorOffset = null;
        
        Logger.logDebug('Using stored cursor offset', {
          cursorOffset
        }, Logger.LogCategory.DEBUG);
      } else {
        // No stored offset available - default to end of content
        const contentElement = DOMUtils.getNoteContent(noteElement);
        cursorOffset = contentElement.textContent.length || 0;
      }
      
      // Focus the note with cursor at proper position
      DOMUtils.focusNote(noteElement, cursorOffset);
    }
    
    // Clean up loading state if needed following ABC pattern
    if (shouldManageLoading && ModeContext.isLoading) {
      ModeContext.setLoading(false);
    }
    
    return contentHtml;
  } else {
    // Clean up loading state if needed following ABC pattern
    if (shouldManageLoading && ModeContext.isLoading) {
      ModeContext.setLoading(false);
    }
    
    return html;
  }
}

/**
 * Load a note's content
 * This fetches the fragment from server and updates DOM
 * @param {string} noteId - ID of the note to load
 * @returns {Promise} Promise resolving when loading is complete
 * @throws {Error} If noteId is falsy or invalid
 */
export async function loadNote(noteId) {
  Logger.logAction('loadNote', { noteId });
  
  // Validate input
  if (!noteId) {
    throw new Error('Cannot load note: noteId is required');
  }
  
  // Just call refresh, but pass the noteId to override the current one
  // This is a convenience function that delegates to refresh
  return await refresh({ noteId });
}