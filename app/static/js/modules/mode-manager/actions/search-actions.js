/**
 * Search Actions for ModeManager
 * 
 * Actions related to entering and exiting search mode
 */

import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { DOMUtils } from '../../dom-utils.js';
import { deselectNote } from './selection-actions.js';

/**
 * Enter search mode, exiting any other modes first
 * If currently editing, will save and deselect the note first
 */
export async function enterSearchMode() {
  Logger.logAction('enterSearchMode');
  
  // If we're editing a note, save and deselect it first
  if (ModeContext.isEditing) {
    await deselectNote();
  }
  
  // Follow ABC pattern - only set if it's changing
  if (!ModeContext.isSearching) {
    ModeContext.setSearching(true);
  }
  
  // Focus the search field
  DOMUtils.focusSearchField();
  
  // Validate the resulting state
  ModeContext.validate();
}

/**
 * Exit search mode
 */
export function exitSearchMode() {
  Logger.logAction('exitSearchMode');
  
  // Follow ABC pattern - only set if it's changing
  if (ModeContext.isSearching) {
    ModeContext.setSearching(false);
  }
  
  // Validate the resulting state
  ModeContext.validate();
}