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
 * Save the current note content
 * This is a simplified version without actual API calls
 * @param {string} noteId - ID of the note to save
 * @throws {Error} If noteId is falsy or invalid
 */
export function saveNote(noteId) {
  // Validate input
  if (!noteId) {
    throw new Error('Cannot save note: noteId is required');
  }
  
  // For now, we'll simulate capturing content
  const content = document.querySelector(`[data-note-id="${noteId}"] .note-content`);
  const contentText = content ? (content.textContent || content.value || '') : '';
  
  // Store it in context (in a real app, this would make an API call)
  ModeContext.setCurrentContent(contentText);
  
  // Mark as not dirty since we "saved" it
  if (ModeContext.isDirty) {
    ModeContext.setDirty(false);
  }
  
  // Log the action at a high level
  Logger.logAction('saveNote', { 
    noteId,
    contentLength: contentText.length
  });
}

/**
 * Load a note's content
 * This is a simplified version without actual API calls
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
  
  // Set loading state while we fetch content
  ModeContext.setLoading(true);
  
  // In a real implementation, this would be an API call
  // For now, simulate with a timeout
  return new Promise((resolve) => {
    setTimeout(() => {
      // Simulate getting content from server
      const dummyContent = `Note content for ${noteId}`;
      
      // Store content in context
      ModeContext.setCurrentContent(dummyContent);
      
      // Clear loading state
      ModeContext.setLoading(false);
      
      // Reset dirty state for the newly loaded note
      if (ModeContext.isDirty) {
        ModeContext.setDirty(false);
      }
      
      // Log the action at a high level
      Logger.logAction('loadNote', { 
        noteId,
        contentLength: dummyContent.length
      });
      
      resolve(dummyContent);
    }, 100); // Simulate network delay
  });
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
  
  // First load the note content
  loadNote(noteId)
    .then(() => {
      // Now that content is loaded, enter editing mode
      ModeContext.setCurrentNoteId(noteId);
      ModeContext.setEditing(true);
      
      // Validate the resulting state
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
  
  // First save the note if needed
  if (ModeContext.isDirty) {
    saveNote(noteId);
  }
  
  // Now exit editing mode and clear all note-related state
  ModeContext.setEditing(false);
  ModeContext.setCurrentNoteId(null);
  ModeContext.setCurrentContent(null);  // Clear content when deselecting
  
  // Validate the resulting state
  ModeContext.validate();
  
  // Log the action at a high level
  Logger.logAction('deselectNote', { 
    previousNoteId: noteId 
  });
}