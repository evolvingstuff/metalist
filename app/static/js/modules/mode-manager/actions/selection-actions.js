import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { DOMUtils } from '../../dom-utils.js';
import { detachEditorSurface } from '../../editor-toolbar.js';
import { actionSaveNote } from './content-actions.js';
import { NotesAPI } from '../../api-client.js';
import { actionRefreshAndMaybeSelect } from './ui-actions.js';
import { ensureNoteExpanded } from '../services/collapse-affordance-service.js';
import { clearTagBar } from '../services/tag-bar-service.js';

export async function actionSelectNote(noteId, options) {
	if (options === null || typeof options !== 'object') {
		throw new Error('actionSelectNote requires options object');
	}
	if (!Object.prototype.hasOwnProperty.call(options, 'initialCaretVisibility')) {
		throw new Error('actionSelectNote requires options.initialCaretVisibility');
	}
	const initialCaretVisibility = options.initialCaretVisibility;
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

	await NotesAPI.recordEditModeTransition(null, noteId);

    const newContent = await actionRefreshAndMaybeSelect({startedAt: startedAt});

    if (ModeContext.currentContent !== newContent) {
        ModeContext.setCurrentContent(newContent);
    }

	const maybeNoteElement = document.querySelector(`[data-note-id="${noteId}"]`);
	if (maybeNoteElement) {
		await ensureNoteExpanded(noteId);
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

    await NotesAPI.recordEditModeTransition(noteId, null);

    await actionRefreshAndMaybeSelect({startedAt: startedAt});

    ModeContext.validate();
}

export async function actionSaveAndExitEditingWithoutRefreshing() {
    Logger.logAction('save_and_exit_editing_without_refresh', {
        currentNoteId: ModeContext.currentNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty,
    });

    if (!ModeContext.isEditing) {
        throw new Error('Cannot save and exit editing locally: not currently editing');
    }

    const noteId = ModeContext.currentNoteId;
    if (!noteId) {
        throw new Error('Cannot save and exit editing locally: currentNoteId is missing');
    }

    await actionSaveNote(noteId);

    const shouldManageLoading = !ModeContext.isLoading;
    if (shouldManageLoading) {
        ModeContext.setLoading(true);
    }

    await (async () => {
        await NotesAPI.recordEditModeTransition(noteId, null);
    })().finally(() => {
        if (shouldManageLoading && ModeContext.isLoading) {
            ModeContext.setLoading(false);
        }
    });

    actionExitEditingWithoutSavingOrRefreshing();
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

export async function actionSwitchNotes(newNoteId, options) {
	if (options === null || typeof options !== 'object') {
		throw new Error('actionSwitchNotes requires options object');
	}
	if (!Object.prototype.hasOwnProperty.call(options, 'initialCaretVisibility')) {
		throw new Error('actionSwitchNotes requires options.initialCaretVisibility');
	}
	const initialCaretVisibility = options.initialCaretVisibility;
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

	const maybeNoteElement = document.querySelector(`[data-note-id="${newNoteId}"]`);
	if (maybeNoteElement) {
		await ensureNoteExpanded(newNoteId);
	}
  
    ModeContext.validate();
}
