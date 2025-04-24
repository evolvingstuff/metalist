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
export async function saveNote(noteId) {
  Logger.logAction('saveNote', { noteId });
  
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
  const response = await NotesAPI.saveNote(noteId, contentHTML);
  
  // Update state to reflect save
  ModeContext.setLastSavedContent(contentHTML);
  ModeContext.setDirty(false);
  
  // Clear loading state
  ModeContext.setLoading(false);
  
  // Return response
  return response;
}

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
  return await refresh();
}

/**
 * Select a note and enter editing mode
 * If already editing, will save and deselect the current note first
 * @param {string} noteId - ID of the note to select
 * @throws {Error} If noteId is falsy or invalid
 */
export async function selectNote(noteId) {
  Logger.logAction('selectNote', { 
    noteId, 
    currentNoteId: ModeContext.currentNoteId 
  });
  
  // Validate input
  if (!noteId) {
    throw new Error('Cannot select note: noteId is required');
  }
  
  // If we're currently editing a note, save and deselect it first
  if (ModeContext.isEditing) {
    if (ModeContext.currentNoteId === noteId) {
      Logger.logDebug('Note already selected, skipping', { noteId });
      return; // Already selected this note
    }
    
    // Save and deselect the current note
    await deselectNote();
  }
  
  // Now select the new note
  ModeContext.setCurrentNoteId(noteId);
  
  // Refresh to get note content and make it editable
  await refresh();
  
  // Enter editing mode
  ModeContext.setEditing(true);
  
  // Validate the resulting state
  ModeContext.validate();
}

/**
 * Deselect the current note and exit editing mode
 * Will save content if dirty
 * @throws {Error} If not currently editing (fail fast approach)
 */
export async function deselectNote() {
  Logger.logAction('deselectNote', { 
    currentNoteId: ModeContext.currentNoteId,
    isEditing: ModeContext.isEditing,
    isDirty: ModeContext.isDirty
  });
  
  // Get the current state
  const noteId = ModeContext.currentNoteId;
  const isEditing = ModeContext.isEditing;
  const isDirty = ModeContext.isDirty;
  
  // Validate we're actually editing
  if (!isEditing) {
    throw new Error('Cannot deselect note: not currently editing');
  }
  
  // Save if dirty
  if (isDirty && noteId) {
    await saveNote(noteId);
  }
  
  // Exit editing mode (only if we're currently editing, to avoid redundant state changes)
  if (isEditing) {
    ModeContext.setEditing(false);
  }
  
  // Get the note element before clearing the note ID
  const noteElement = noteId ? DOMUtils.getNoteById(noteId) : null;
  
  // Clear current note ID
  if (noteId) {
    ModeContext.setCurrentNoteId(null);
  }
  
  // Make the note non-editable
  if (noteElement) {
    DOMUtils.setNoteEditable(noteElement, false);
  }
  
  // Clear content
  if (ModeContext.currentContent !== null) {
    ModeContext.setCurrentContent(null);
  }
  
  // Validate the resulting state
  ModeContext.validate();
}

/**
 * Switch from the current note to a different note
 * Will save the current note if dirty before switching
 * @param {string} newNoteId - ID of the note to switch to
 * @returns {Promise} Promise resolving when switch is complete
 * @throws {Error} If newNoteId is falsy, or same as current note
 */
export async function switchNotes(newNoteId) {
  Logger.logAction('switchNotes', { 
    currentNoteId: ModeContext.currentNoteId,
    newNoteId,
    isEditing: ModeContext.isEditing,
    isDirty: ModeContext.isDirty
  });
  
  // Validate input
  if (!newNoteId) {
    throw new Error('Cannot switch notes: newNoteId is required');
  }
  
  const currentNoteId = ModeContext.currentNoteId;
  
  // Validate we're not switching to the same note
  if (currentNoteId === newNoteId) {
    Logger.logDebug('Already on this note, not switching', { noteId: newNoteId });
    return;
  }
  
  // If we have a current note and it's dirty, save it
  if (ModeContext.isDirty && currentNoteId) {
    await saveNote(currentNoteId);
  }
  
  // Get the current note element
  const currentNoteElement = currentNoteId ? DOMUtils.getNoteById(currentNoteId) : null;
  
  // Make the current note non-editable
  if (currentNoteElement) {
    DOMUtils.setNoteEditable(currentNoteElement, false);
  }
  
  // Validate content is not null (fail fast)
  if (ModeContext.currentContent === null) {
    throw new Error(`Programming error: Switching from note ${currentNoteId} but currentContent is null`);
  }
  
  // Clear current content before switching to prevent redundant state change errors
  ModeContext.setCurrentContent(null);
  
  // Set the new note ID and keep editing mode active
  ModeContext.setCurrentNoteId(newNoteId);
  
  // Use refresh to load the new content
  await refresh();
  
  // Validate the resulting state
  ModeContext.validate();
}

/**
 * Delete the currently selected note
 * @param {string} noteId - ID of the note to delete
 * @returns {Promise} Promise resolving when deletion is complete
 */
export async function deleteNote(noteId) {
  Logger.logAction('deleteNote', { 
    noteId,
    isEditing: ModeContext.isEditing,
    currentNoteId: ModeContext.currentNoteId
  });
  
  // Validate input
  if (!noteId) {
    throw new Error('Cannot delete note: noteId is required');
  }
  
  // Validate the note ID matches the current note
  if (ModeContext.currentNoteId !== noteId) {
    throw new Error(`Programming error: Deleting note ${noteId}, but currentNoteId is ${ModeContext.currentNoteId}`);
  }
  
  // Validate we're in editing mode
  if (!ModeContext.isEditing) {
    throw new Error(`Programming error: Deleting current note ${noteId}, but isEditing is false`);
  }
  
  // Clear editing state before API call
  ModeContext.setEditing(false);
  ModeContext.setCurrentNoteId(null);
  
  // Only clear content and dirty if they have values to avoid redundant state changes
  if (ModeContext.currentContent !== null) {
    ModeContext.setCurrentContent(null);
  }
  
  if (ModeContext.isDirty) {
    ModeContext.setDirty(false);
  }
  
  // Set loading state for API call
  ModeContext.setLoading(true);
  
  // Do the API call
  await NotesAPI.deleteNote(noteId);
  
  // Clear loading state before calling refresh
  ModeContext.setLoading(false);
  
  // Now that state is fully cleared, refresh the UI
  return await refresh();
}

/**
 * Create a new note
 * - If no note is selected, creates at top of list
 * - If a note is selected, creates a new sibling after that note
 * @returns {Promise} Promise resolving when creation is complete
 */
export async function createNote() {
  Logger.logAction('createNote', {
    currentNoteId: ModeContext.currentNoteId,
    isEditing: ModeContext.isEditing,
    isDirty: ModeContext.isDirty
  });
  
  // Check if we currently have a note selected
  const currentNoteId = ModeContext.currentNoteId;
  
  // If we're editing and have unsaved changes, save first
  if (ModeContext.isEditing && ModeContext.isDirty && currentNoteId) {
    await saveNote(currentNoteId);
  }
  
  // Only set loading=true if we didn't just call saveNote
  // (which would have already handled the loading state)
  if (!(ModeContext.isEditing && ModeContext.isDirty && currentNoteId)) {
    ModeContext.setLoading(true);
  }
  
  // Choose the right API call based on selection state
  let data;
  if (currentNoteId) {
    // Create a sibling after the currently selected note
    Logger.logDebug('Creating new sibling note after note', { 
      currentNoteId 
    }, Logger.LogCategory.ACTION);
    data = await NotesAPI.createSibling(currentNoteId);
  } else {
    // No note selected, create at top of list
    Logger.logDebug('Creating new note at top of list', {}, Logger.LogCategory.ACTION);
    data = await NotesAPI.createNote();
  }
  
  // API returns the new note ID
  const newNoteId = data.id;
  
  // Clear loading state
  ModeContext.setLoading(false);
  
  // Select the new note to start editing it
  // Use switchNotes if we're already editing, otherwise selectNote
  if (ModeContext.isEditing) {
    return await switchNotes(newNoteId);
  } else {
    return await selectNote(newNoteId);
  }
}