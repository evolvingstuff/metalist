/**
 * Content Actions for ModeManager
 * 
 * Actions related to content manipulation (editing, saving)
 */

import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { NotesAPI } from '../../api-client.js';
import { DOMUtils } from '../../dom-utils.js';

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