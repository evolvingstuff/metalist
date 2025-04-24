/**
 * ModeManager Actions
 * 
 * Centralized actions for the ModeManager that encapsulate state changes
 * and ensure proper transitions between modes.
 * 
 * These actions serve as the bridge between raw events and state management,
 * ensuring consistent behavior regardless of what triggered the action.
 */

import { ModeContextInstance as ModeContext } from './mode-context.js';
import * as Logger from './mode-logger.js';
import { NotesAPI } from '../api-client.js';
import { DOMUtils } from '../dom-utils.js';

/**
 * Save the current note content
 * This persists the content to the server via API
 * @param {string} noteId - ID of the note to save
 * @returns {Promise} Promise resolving when save is complete
 * @throws {Error} If noteId is falsy or invalid
 */
export function saveNote(noteId) {
  // Validate input
  if (!noteId) {
    throw new Error('Cannot save note: noteId is required');
  }
  
  // Make sure we have a valid noteId and are in editing mode
  if (ModeContext.currentNoteId !== noteId) {
    throw new Error(`Cannot save note ${noteId} - not the current note being edited (${ModeContext.currentNoteId})`);
  }
  
  // Get note content
  const noteElement = DOMUtils.getNoteById(noteId);
  const contentHTML = DOMUtils.getNoteContentHTML(noteElement);
  
  // Skip saving if content hasn't changed
  if (!ModeContext.isDirty) {
    Logger.logDebug('Note not dirty, skipping save', { 
      noteId,
      contentLength: contentHTML.length
    }, Logger.LogCategory.DEBUG);
    return Promise.resolve(); // Return resolved promise for consistency
  }
  
  // Set loading state while we save
  ModeContext.setLoading(true);
  
  // Call the API to save the note
  return NotesAPI.saveNote(noteId, contentHTML)
    .then(response => {
      // Update state to reflect save
      ModeContext.setLastSavedContent(contentHTML);
      ModeContext.setDirty(false);
      
      // Log the action at a high level
      Logger.logAction('saveNote', { 
        noteId,
        contentLength: contentHTML.length,
        response
      });
      
      return response;
    })
    .catch(error => {
      Logger.logError(`Failed to save note ${noteId}`, error);
      throw error; // Re-throw for caller to handle
    })
    .finally(() => {
      // Clear loading state
      ModeContext.setLoading(false);
    });
}

/**
 * Refresh UI with latest content from server
 * Gets fragment from server and updates the DOM based on current context
 * Also handles editability and cursor positioning if a note is selected
 * @returns {Promise} Promise resolving when refresh is complete
 */
export function refresh() {
  // Always use the current note ID from context
  const noteId = ModeContext.currentNoteId;
  
  // Set loading state while we fetch content
  ModeContext.setLoading(true);
  
  // Call the API to get the fragment
  return NotesAPI.getFragment(noteId)
    .then(html => {
      // Update the notes container with new HTML
      const notesContainer = document.getElementById('notes-container');
      if (!notesContainer) {
        throw new Error('Notes container not found');
      }
      
      notesContainer.innerHTML = html;
      
      // If we have a current note, get its content and handle editability
      if (noteId) {
        try {
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
              try {
                // Use stored offset directly
                cursorOffset = ModeContext._savedCursorOffset.offset;
                
                // Clean up
                ModeContext._savedCursorOffset = null;
                
                Logger.logDebug('Using stored cursor offset', {
                  cursorOffset
                }, Logger.LogCategory.DEBUG);
              } catch (error) {
                Logger.logError('Failed to use stored cursor offset', error);
                // Fall back to default cursor position (end of content)
                const contentElement = DOMUtils.getNoteContent(noteElement);
                cursorOffset = contentElement.textContent.length || 0;
              }
            } else {
              // No stored offset available - default to end of content
              const contentElement = DOMUtils.getNoteContent(noteElement);
              cursorOffset = contentElement.textContent.length || 0;
            }
            
            // Focus the note with cursor at proper position
            DOMUtils.focusNote(noteElement, cursorOffset);
          }
          
          // Log the action at a high level with note ID
          Logger.logAction('refresh', { 
            noteId,
            contentLength: contentHtml.length,
            fragmentSize: html.length,
            editMode: ModeContext.isEditing
          });
          
          return contentHtml;
        } catch (error) {
          Logger.logError(`Error getting note content for ${noteId}`, error);
          throw error;
        }
      } else {
        // Log the action without note ID
        Logger.logAction('refresh', { 
          noteId: null,
          fragmentSize: html.length
        });
        
        return html;
      }
    })
    .catch(error => {
      Logger.logError(`Failed to refresh${noteId ? ` note ${noteId}` : ''}`, error);
      throw error;
    })
    .finally(() => {
      // Clear loading state
      ModeContext.setLoading(false);
    });
}

/**
 * Load a note's content
 * This fetches the fragment from server and updates DOM
 * @param {string} noteId - ID of the note to load
 * @returns {Promise} Promise resolving when loading is complete
 * @throws {Error} If noteId is falsy or invalid
 */
export function loadNote(noteId) {
  // Validate input
  if (!noteId) {
    throw new Error('Cannot load note: noteId is required');
  }
  
  // Validate state - fail fast if in an unexpected state
  if (ModeContext.isDirty) {
    const errorMsg = `Programming error: Cannot load note ${noteId} while dirty flag is set. Current note should be saved or deselected first.`;
    Logger.logError(errorMsg);
    throw new Error(errorMsg);
  }
  
  // Set the noteId in context first
  ModeContext.setCurrentNoteId(noteId);
  
  // Then use refresh to load the content
  return refresh();
}

/**
 * Select a note and enter editing mode
 * If already editing, will save and deselect the current note first
 * @param {string} noteId - ID of the note to select
 * @throws {Error} If noteId is falsy or invalid
 */
export function selectNote(noteId) {
  // Validate input
  if (!noteId) {
    throw new Error('Cannot select note: noteId is required');
  }
  
  // Check for redundant selection
  if (ModeContext.isEditing && ModeContext.currentNoteId === noteId) {
    const errorMsg = `Redundant note selection: note ${noteId} is already selected and in edit mode`;
    Logger.logError(errorMsg);
    throw new Error(errorMsg);
  }
  
  // If already editing a different note, deselect it first (which also saves it)
  if (ModeContext.isEditing) {
    deselectNote();
  }
  
  // If we're in search mode, exit it first
  if (ModeContext.isSearching) {
    ModeContext.setSearching(false);
    Logger.logDebug('Exiting search mode to edit note', { noteId }, Logger.LogCategory.STATE);
  }
  
  // Set the note ID in context and enter editing mode
  ModeContext.setCurrentNoteId(noteId);
  ModeContext.setEditing(true);
  
  // Use refresh to load content (which will now handle cursor positioning)
  return refresh()
    .then(() => {
      // Validate the resulting state after refresh
      ModeContext.validate();
      
      // Log the action completion
      Logger.logAction('selectNote', { 
        noteId,
        wasSearching: ModeContext.isSearching
      });
    })
    .catch(error => {
      Logger.logError(`Failed to select note ${noteId}`, error);
    });
}

/**
 * Deselect the current note and exit editing mode
 * Will save content if dirty
 * @throws {Error} If not currently editing (fail fast approach)
 */
export function deselectNote() {
  // Validate current state - fail fast if inconsistent
  if (!ModeContext.isEditing) {
    throw new Error('Cannot deselect note: not currently in editing mode');
  }
  
  if (!ModeContext.currentNoteId) {
    throw new Error('Inconsistent state: editing mode active but no currentNoteId');
  }
  
  const noteId = ModeContext.currentNoteId;
  
  // Chain operations to avoid redundant state changes
  // First save if dirty, then deselect
  let promise = Promise.resolve();
  
  if (ModeContext.isDirty) {
    // First save if needed
    promise = saveNote(noteId);
  }
  
  return promise.then(() => {
    // Now exit editing mode and clear all note-related state
    ModeContext.setEditing(false);
    ModeContext.setCurrentNoteId(null);
    ModeContext.setCurrentContent(null);  // Clear content when deselecting
    
    // Refresh UI based on new context (no selected note)
    return refresh();
  })
  .then(() => {
    // Validate the resulting state
    ModeContext.validate();
    
    // Log the action at a high level
    Logger.logAction('deselectNote', { 
      previousNoteId: noteId 
    });
  })
  .catch(error => {
    Logger.logError(`Error during deselect note flow: ${error.message}`, error);
    throw error;
  });
}

/**
 * Switch from the current note to a different note
 * Will save the current note if dirty before switching
 * @param {string} newNoteId - ID of the note to switch to
 * @returns {Promise} Promise resolving when switch is complete
 * @throws {Error} If newNoteId is falsy, or same as current note
 */
export function switchNotes(newNoteId) {
  // Validate input
  if (!newNoteId) {
    throw new Error('Cannot switch notes: newNoteId is required');
  }
  
  // Make sure we're in editing mode
  if (!ModeContext.isEditing) {
    return selectNote(newNoteId); // Just select if not already editing
  }
  
  // Get current note ID
  const currentNoteId = ModeContext.currentNoteId;
  if (!currentNoteId) {
    throw new Error('Inconsistent state: editing mode active but no currentNoteId');
  }
  
  // Check for redundant switch (switching to the same note)
  if (currentNoteId === newNoteId) {
    const message = `Redundant switch: note ${newNoteId} is already selected`;
    Logger.logDebug(message, {}, Logger.LogCategory.NOOP);
    return Promise.resolve(); // Nothing to do
  }
  
  // First save current note if dirty
  let promise = Promise.resolve();
  if (ModeContext.isDirty) {
    promise = saveNote(currentNoteId);
  }
  
  // Then switch to the new note
  return promise.then(() => {
    // Set the new note ID and keep editing mode active
    ModeContext.setCurrentNoteId(newNoteId);
    
    // Use refresh to load the new content
    return refresh();
  })
  .then(() => {
    // Validate the resulting state
    ModeContext.validate();
    
    // Log the action completion
    Logger.logAction('switchNotes', { 
      fromNoteId: currentNoteId, 
      toNoteId: newNoteId 
    });
  })
  .catch(error => {
    Logger.logError(`Failed to switch from note ${currentNoteId} to ${newNoteId}`, error);
    throw error;
  });
}