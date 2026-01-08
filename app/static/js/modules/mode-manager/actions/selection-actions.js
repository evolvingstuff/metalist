import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { DOMUtils } from '../../dom-utils.js';
import { detachEditorSurface } from '../../editor-toolbar.js';
import { actionSaveNote } from './content-actions.js';
import { actionRefreshAndMaybeSelect } from './ui-actions.js';
import { ensureNoteExpanded } from '../services/collapse-affordance-service.js';
import { clearTagBar } from '../services/tag-bar-service.js';

export async function actionSelectNote(noteId, options = {}) {
    const {
        initialCaretVisibility = 'hidden'
    } = options;
    let startedAt = performance.now();
    Logger.logAction('selectNote', { 
        noteId, 
        currentNoteId: ModeContext.currentNoteId 
    });

    if (!noteId) {
        throw new Error('Cannot select note: noteId is required');
    }

    if (ModeContext.isEditing) {
        if (ModeContext.currentNoteId === noteId) {
            Logger.logDebug('Note already selected, skipping', { noteId });
            return; 
        }

        await actionDeselectNote();
    }

    ModeContext.setCurrentNoteId(noteId);

    ModeContext.setEditing(true);

    if (initialCaretVisibility === 'hidden') {
        ModeContext.markCaretHidden();
    } else {
        ModeContext.markCaretVisible();
    }

    const newContent = await actionRefreshAndMaybeSelect({startedAt: startedAt});

    if (ModeContext.currentContent !== newContent) {
        ModeContext.setCurrentContent(newContent);
    }

    try {
        await ensureNoteExpanded(noteId);
    } catch (error) {
        Logger.logDebug('Note not present during ensureExpanded after refresh', {
            noteId,
            error: error.message
        }, Logger.LogCategory.DEBUG);
    }

    ModeContext.validate();
}

export async function actionDeselectNote() {
    let startedAt = performance.now();
    Logger.logAction('deselectNote', { 
        currentNoteId: ModeContext.currentNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty
    });

    const noteId = ModeContext.currentNoteId;

    if (!ModeContext.isEditing) {
        throw new Error('Cannot deselect note: not currently editing');
    }

    await actionSaveNote(noteId);

    ModeContext.setEditing(false);

    ModeContext.setCurrentNoteId(null);

    ModeContext.setCurrentContent(null);

    await actionRefreshAndMaybeSelect({startedAt: startedAt});

    ModeContext.validate();
}

export function actionExitEditingWithoutSavingOrRefreshing() {
    Logger.logAction('exit_editing_without_saving_or_refreshing', {
        currentNoteId: ModeContext.currentNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty
    });

    if (!ModeContext.isEditing) {
        throw new Error('Cannot exit editing locally: not currently editing');
    }
    if (ModeContext.isDirty) {
        throw new Error('Cannot exit editing locally while dirty');
    }

    const noteId = ModeContext.currentNoteId;
    if (!noteId) {
        throw new Error('Cannot exit editing locally: currentNoteId is missing');
    }

    const noteElement = DOMUtils.getNoteById(noteId);
    DOMUtils.setNoteEditable(noteElement, false);
    detachEditorSurface();
    clearTagBar();

    ModeContext.setEditing(false);
    ModeContext.setCurrentNoteId(null);

    if (ModeContext.currentContent !== null) {
        ModeContext.setCurrentContent(null);
    }

    ModeContext.validate();
}

export async function actionSwitchNotes(newNoteId, options = {}) {
    const {
        initialCaretVisibility = 'hidden'
    } = options;
    let startedAt = performance.now();
    Logger.logAction('switchNotes', { 
        currentNoteId: ModeContext.currentNoteId,
        newNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty
    });

    if (!newNoteId) {
        throw new Error('Cannot switch notes: newNoteId is required');
    }
        
    const currentNoteId = ModeContext.currentNoteId;

    if (currentNoteId === newNoteId) {
        Logger.logDebug('Already on this note, not switching', { noteId: newNoteId });
        return;
    }

    if (currentNoteId) {
        await actionSaveNote(currentNoteId);
    }

    const currentNoteElement = currentNoteId ? DOMUtils.getNoteById(currentNoteId) : null;

    if (currentNoteElement) {
        DOMUtils.setNoteEditable(currentNoteElement, false);
        clearTagBar();
    }

    if (ModeContext.currentContent === null) {
        throw new Error(`Programming error: Switching from note ${currentNoteId} but currentContent is null`);
    }

    ModeContext.setCurrentContent(null);

    ModeContext.setCurrentNoteId(newNoteId);

    if (initialCaretVisibility === 'hidden') {
        ModeContext.markCaretHidden();
    } else {
        ModeContext.markCaretVisible();
    }

    const newContent = await actionRefreshAndMaybeSelect({startedAt: startedAt});
    
    ModeContext.setCurrentContent(newContent);

    try {
        await ensureNoteExpanded(newNoteId);
    } catch (error) {
        Logger.logDebug('Note not present during ensureExpanded after refresh', {
            noteId: newNoteId,
            error: error.message
        }, Logger.LogCategory.DEBUG);
    }
  
    ModeContext.validate();
}
