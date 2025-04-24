/**
 * Mouse Events Handler for ModeManager
 * 
 * Handles all mouse-based interactions:
 * - Clicks on various UI elements
 * - Input events in editable areas
 * - Drag and drop (future implementation)
 * 
 * Initially just observes and logs mouse events but doesn't
 * interfere with existing state machine behavior.
 */

import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { selectNote, deselectNote, switchNotes, deleteNote, createNote } from '../actions.js';
import { DOMUtils } from '../../dom-utils.js'; // Fix the path - go up one more level

/**
 * Initialize mouse event handlers
 * @returns {void}
 */
export function initMouseEvents() {
  // Register handlers in capture phase to ensure they run before state machine
  document.addEventListener('click', handleClick, { capture: true });
  
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
  if (!event) {
    throw new Error('handleClick called without an event object');
  }
  
  if (event.clientX === undefined || event.clientY === undefined) {
    throw new Error(`Invalid MouseEvent: missing coordinates (type: ${event.type})`);
  }
  
  if (!event.target) {
    throw new Error('Click event missing target element');
  }
  
  // Store coordinates for debugging purposes
  const coordinates = {
    x: event.clientX,
    y: event.clientY
  };
  
  // Analyze click target
  const noteContent = event.target.closest('.note-content');
  const searchField = event.target.closest('#search-input');
  const createButton = event.target.closest('.add-note');
  const deleteButton = event.target.closest('#trash-can');
  
  // Update mode based on what was clicked
  if (deleteButton) {
    // Only delete if there's a currently selected note
    const noteId = ModeContext.currentNoteId;
    
    if (noteId) {
      Logger.logDebug('Delete button clicked for current note', { 
        noteId,
        coordinates 
      }, Logger.LogCategory.EVENT);
      
      // Call the delete action on the currently selected note
      deleteNote(noteId);
    } else {
      // No note is currently selected, nothing to delete
      Logger.logNoop('Delete button clicked but no note is selected', { 
        coordinates 
      });
    }
  } else if (noteContent) {
    const noteElement = noteContent.closest('.note');
    if (!noteElement) {
      throw new Error('Found .note-content without parent .note element');
    }
    
    const noteId = noteElement.dataset.noteId;
    if (!noteId) {
      throw new Error('Note element missing data-note-id attribute');
    }
    
    // Validate the click was within the note content boundaries
    const rect = noteContent.getBoundingClientRect();
    if (!rect || typeof rect.left !== 'number' || typeof rect.right !== 'number' || 
        typeof rect.top !== 'number' || typeof rect.bottom !== 'number') {
      throw new Error(`Invalid bounding rect for note content: ${JSON.stringify(rect)}`);
    }
    
    const isWithinBounds = (
      coordinates.x >= rect.left &&
      coordinates.x <= rect.right &&
      coordinates.y >= rect.top &&
      coordinates.y <= rect.bottom
    );
    
    if (isWithinBounds) {
      // Only select the note if we're not already editing it
      if (!ModeContext.isEditing || ModeContext.currentNoteId !== noteId) {
        // Calculate cursor position BEFORE fragment loading replaces DOM
        try {
          // Get the cursor offset (character position) directly
          const cursorOffset = DOMUtils.getCursorOffsetFromClick(noteElement, coordinates);
          
          // Debug logging with proper category
          const content = DOMUtils.getNoteContent(noteElement);
          Logger.logDebug('Note content structure:', { 
            html: content.innerHTML,
            text: content.textContent,
            cursorOffset,
            coordinates,
            childNodes: Array.from(content.childNodes).map(node => ({
              type: node.nodeType,
              name: node.nodeName,
              text: node.textContent?.substring(0, 20)
            }))
          }, Logger.LogCategory.DEBUG);
          
          // Store the offset and noteId
          ModeContext._savedCursorOffset = { 
            offset: cursorOffset,
            noteId // Store which note this was for
          };
          
          Logger.logDebug('Stored cursor offset before fragment load', { 
            cursorOffset, 
            noteId 
          }, Logger.LogCategory.EVENT);
        } catch (error) {
          Logger.logError('Failed to calculate cursor offset', error);
        }
        
        // This was a real user click in the note - use action to select it
        if (ModeContext.currentNoteId) {
          switchNotes(noteId);
        } else {
          selectNote(noteId);
        }
        
        Logger.logDebug('Click in note content - selecting note', { 
          noteId,
          coordinates,
          isEditing: true
        }, Logger.LogCategory.EVENT);
      } else {
        // Already editing this note, no need to re-select
        Logger.logNoop('Click in already selected note - no action needed', { 
          noteId,
          coordinates,
          isEditing: true
        });
      }
    } else {
      // If already editing, deselect note
      if (ModeContext.isEditing) {
        deselectNote();
      }
      
      Logger.logDebug('Click near note but outside content bounds', {
        noteId,
        coordinates,
        elementBounds: {
          left: rect.left,
          right: rect.right,
          top: rect.top,
          bottom: rect.bottom
        },
        isEditing: false
      }, Logger.LogCategory.EVENT);
    }
  } else if (searchField) {
    ModeContext.setSearching(true);
    ModeContext.validate();
    Logger.logDebug('Click in search field', { coordinates }, Logger.LogCategory.EVENT);
  } else if (createButton) {
    Logger.logDebug('Create note button clicked', { coordinates }, Logger.LogCategory.EVENT);
    createNote();
  } else {
    // Click was not on any note or interactive element
    // Exit editing mode if we were editing
    if (ModeContext.isEditing) {
      deselectNote();
      
      Logger.logDebug('Click outside any note - exiting edit mode', {
        coordinates,
        isEditing: false,
        currentNoteId: null
      }, Logger.LogCategory.EVENT);
    }
  }
  
  // Don't prevent default or stop propagation - let event reach state machine
}