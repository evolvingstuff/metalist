import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { NotesAPI } from '../../api-client.js';
import { saveNote } from './content-actions.js';
import { refresh_and_maybe_select } from './ui-actions.js';

export async function undo() {
    Logger.logAction('undo', {
        currentNoteId: ModeContext.currentNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty,
        isSearching: ModeContext.isSearching
    });
    
    // Save current content if dirty
    if (ModeContext.isDirty && ModeContext.currentNoteId) {
        await saveNote(ModeContext.currentNoteId);
    }
    
    // Exit search mode if active
    if (ModeContext.isSearching) {
        ModeContext.setSearching(false);
    }
    
    // Set loading state
    ModeContext.setLoading(true);
    
    // Call undo API endpoint
    Logger.logAction('undo_api_call_start', { timestamp: Date.now() });
    
    const result = await NotesAPI.undo();
    
    Logger.logDebug('Undo API response', result, Logger.LogCategory.DEBUG);
    
    // Reset loading state as soon as we get a response
    ModeContext.setLoading(false);
    
    // If the server couldn't undo (no actions available)
    if (result.status === 'noop') {
        Logger.logAction('undo_noop', { message: result.message });
        return; // Nothing to do
    }
    
    // On success, clear state to force a fresh load
    if (result.status === 'success') {
        Logger.logAction('undo_success', { message: result.message });
        
        // Clear any dirty state
        if (ModeContext.isDirty) {
            ModeContext.setDirty(false);
        }
        
        // Always clear current content so refresh can set it properly
        if (ModeContext.currentContent !== null) {
            ModeContext.setCurrentContent(null);
        }
        
        // Clear current note ID if set to force a complete refresh
        // This ensures we get whatever the server thinks is selected now
        if (ModeContext.currentNoteId !== null) {
            ModeContext.setCurrentNoteId(null);
        }
        
        // If we were editing, exit edit mode to ensure clean state
        if (ModeContext.isEditing) {
            ModeContext.setEditing(false);
        }
    } else {
        // Anything other than success is an error
        throw new Error(`Undo failed: ${result.message || 'Unknown error'}`);
    }
    
    // Refresh UI to reflect changes
    const newContent = await refresh_and_maybe_select();
    
    // Update content if needed
    if (ModeContext.currentContent !== newContent && newContent !== null) {
        ModeContext.setCurrentContent(newContent);
    }
    
    // Validate state consistency
    ModeContext.validate();
}