import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { actionSaveNoteOnIdle } from '../actions/content-actions.js';

// Settings
const CHECK_INTERVAL = 500;
const CONTENT_INACTIVITY_THRESHOLD = 10000; // Save after 10 seconds of no changes

// Timer reference
let contentCheckTimer = null;

/**
 * Initialize the content auto-save timer
 */
function initContentAutoSave() {
    // Start the timer that periodically checks for content inactivity
    contentCheckTimer = setInterval(checkAndSaveContent, CHECK_INTERVAL);
    
    Logger.logInit('Content auto-save initialized');
}

/**
 * Check if content has been inactive and save if needed
 */
function checkAndSaveContent() {
    // Only proceed if editing a note and content is dirty
    if (!ModeContext.isEditing || !ModeContext.isDirty) {
        return;
    }
    
    const lastChangeTime = ModeContext.lastContentChangeTime;
    
    // // Skip if there's no content change timestamp yet
    // if (!lastChangeTime) {
    //     // Initialize it now so we have a reference point
    //     ModeContext.setLastContentChangeTime(Date.now());
    //     return;
    // }
    
    const timeSinceLastChange = Date.now() - lastChangeTime;
    
    // If content hasn't changed for the threshold period, save it
    if (timeSinceLastChange >= CONTENT_INACTIVITY_THRESHOLD) {
        Logger.logDebug('Auto-saving content after inactivity', {
            noteId: ModeContext.currentNoteId,
            inactivityDuration: timeSinceLastChange
        });
        
        // Save the content
        actionSaveNoteOnIdle(ModeContext.currentNoteId);
        
        // // Update the timestamp to prevent multiple saves
        // ModeContext.setLastContentChangeTime(Date.now());
    }
}

export { initContentAutoSave };