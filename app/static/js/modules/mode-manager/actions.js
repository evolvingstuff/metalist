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

/**
 * Select a note and enter editing mode
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
  
  // If we're in search mode, exit it first
  if (ModeContext.isSearching) {
    ModeContext.setSearching(false);
    Logger.logDebug('Exiting search mode to edit note', { noteId }, Logger.LogCategory.STATE);
  }
  
  // Now enter editing mode with the new note
  ModeContext.setCurrentNoteId(noteId);
  ModeContext.setEditing(true);
  ModeContext.validate();
  
  // Log the action at a high level
  Logger.logAction('selectNote', { 
    noteId,
    wasSearching: ModeContext.isSearching
  });
}

/**
 * Deselect the current note and exit editing mode
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
  
  // Exit editing mode
  ModeContext.setEditing(false);
  ModeContext.setCurrentNoteId(null);
  ModeContext.validate();
  
  // Log the action at a high level
  Logger.logAction('deselectNote', { 
    previousNoteId: noteId 
  });
}