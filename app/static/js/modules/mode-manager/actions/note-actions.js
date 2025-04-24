/**
 * Note Actions for ModeManager
 * 
 * Actions related to note creation and deletion
 */

import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { NotesAPI } from '../../api-client.js';
import { saveNote } from './content-actions.js';
import { switchNotes, selectNote } from './selection-actions.js';
import { refresh } from './ui-actions.js';

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