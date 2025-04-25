/**
 * Selection Actions for ModeManager
 * 
 * Actions related to selecting, deselecting, and switching between notes
 */

import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { DOMUtils } from '../../dom-utils.js';
import { saveNote } from './content-actions.js';
import { refresh } from './ui-actions.js';
import { exitSearchMode } from './search-actions.js';

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
  
  // Enter editing mode BEFORE refresh so cursor positioning works
  ModeContext.setEditing(true);
  
  // Refresh to get note content and make it editable
  await refresh();
  
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