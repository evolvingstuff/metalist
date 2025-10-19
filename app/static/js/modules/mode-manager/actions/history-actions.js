import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { NotesAPI } from '../../api-client.js';
import { actionSaveNote } from './content-actions.js';
import { actionRefreshAndMaybeSelect } from './ui-actions.js';
import { CONFIG } from '../../config.js';
import { DOMUtils } from '../../dom-utils.js';

export async function actionUndo() {
    let startedAt = performance.now();
    Logger.logAction('undo', {
        currentNoteId: ModeContext.currentNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty,
        isSearching: ModeContext.isSearching
    });

    if (ModeContext.isDirty && ModeContext.currentNoteId) {
        await actionSaveNote(ModeContext.currentNoteId);
    }

    if (ModeContext.isSearching) {
        ModeContext.setSearching(false);
    }

    ModeContext.setLoading(true);

    Logger.logAction('undo_api_call_start', { timestamp: Date.now() });
    
    const result = await NotesAPI.undo();
    
    Logger.logDebug('Undo API response', result, Logger.LogCategory.DEBUG);

    ModeContext.setLoading(false);

    if (result.status === 'noop') {
        Logger.logAction('undo_noop', { message: result.message });
        return; 
    }

    if (result.status === 'success') {
        Logger.logAction('undo_success', { message: result.message });

        if (ModeContext.isDirty) {
            ModeContext.setDirty(false);
        }

        if (ModeContext.currentContent !== null) {
            ModeContext.setCurrentContent(null);
        }

        if (ModeContext.currentNoteId !== null) {
            ModeContext.setCurrentNoteId(null);
        }

        if (ModeContext.isEditing) {
            ModeContext.setEditing(false);
        }
    } else {
        
        throw new Error(`Undo failed: ${result.message || 'Unknown error'}`);
    }

    const newContent = await actionRefreshAndMaybeSelect({startedAt: startedAt, context: 'actionUndo'});

    if (ModeContext.currentContent !== newContent && newContent !== null) {
        ModeContext.setCurrentContent(newContent);
    }

    ModeContext.validate();
}

export async function actionRedo() {
    let startedAt = performance.now();
    Logger.logAction('redo', {
        currentNoteId: ModeContext.currentNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty,
        isSearching: ModeContext.isSearching
    });

    if (ModeContext.isDirty && ModeContext.currentNoteId) {
        await actionSaveNote(ModeContext.currentNoteId);
    }

    if (ModeContext.isSearching) {
        ModeContext.setSearching(false);
    }

    ModeContext.setLoading(true);

    Logger.logAction('redo_api_call_start', { timestamp: Date.now() });
    
    const result = await NotesAPI.redo();
    
    Logger.logDebug('Redo API response', result, Logger.LogCategory.DEBUG);

    ModeContext.setLoading(false);

    if (result.status === 'noop') {
        Logger.logAction('redo_noop', { message: result.message });
        return; 
    }

    if (result.status === 'success') {
        Logger.logAction('redo_success', { message: result.message });

        if (ModeContext.isDirty) {
            ModeContext.setDirty(false);
        }

        if (ModeContext.currentContent !== null) {
            ModeContext.setCurrentContent(null);
        }

        if (ModeContext.currentNoteId !== null) {
            ModeContext.setCurrentNoteId(null);
        }

        if (ModeContext.isEditing) {
            ModeContext.setEditing(false);
        }
    } else {
        
        throw new Error(`Redo failed: ${result.message || 'Unknown error'}`);
    }

    const newContent = await actionRefreshAndMaybeSelect({startedAt: startedAt, context: 'actionRedo'});

    if (ModeContext.currentContent !== newContent && newContent !== null) {
        ModeContext.setCurrentContent(newContent);
    }

    ModeContext.validate();
}