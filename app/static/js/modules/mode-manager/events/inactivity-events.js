import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { actionSaveNoteOnIdle } from '../actions/content-actions.js';

const CHECK_INTERVAL = 500;
const CONTENT_INACTIVITY_THRESHOLD = 60000;  // 60 seconds for debugging 

let contentCheckTimer = null;

function initContentAutoSave() {
    
    contentCheckTimer = setInterval(checkAndSaveContent, CHECK_INTERVAL);
    
    Logger.logInit('Content auto-save initialized');
}

function checkAndSaveContent() {
    
    if (!ModeContext.isEditing || !ModeContext.isDirty) {
        return;
    }
    
    const lastChangeTime = ModeContext.lastContentChangeTime;

    const timeSinceLastChange = Date.now() - lastChangeTime;

    if (timeSinceLastChange >= CONTENT_INACTIVITY_THRESHOLD) {
        Logger.logDebug('Auto-saving content after inactivity', {
            noteId: ModeContext.currentNoteId,
            inactivityDuration: timeSinceLastChange
        });

        actionSaveNoteOnIdle(ModeContext.currentNoteId);

    }
}

export { initContentAutoSave };