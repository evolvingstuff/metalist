import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { NotesAPI } from '../../api-client.js';
import { actionSaveNote } from './content-actions.js';
import { actionRefreshAndMaybeSelect } from './ui-actions.js';
import { CONFIG } from '../../config.js';
import { DOMUtils } from '../../dom-utils.js';
import { scrollNoteIntoView } from '../services/scroll-restoration-service.js';
import { detachEditorSurface } from '../../editor-toolbar.js';
import { clearTagBar } from '../services/tag-bar-service.js';

function applyScrollRestore(scrollRestore, contextLabel) {
    if (!scrollRestore || typeof scrollRestore !== 'object') {
        throw new Error(`${contextLabel} response missing scrollRestore object`);
    }

    const scrollY = scrollRestore.scrollY;
    if (typeof scrollY !== 'number' || scrollY < 0) {
        throw new Error(`${contextLabel} scrollRestore.scrollY must be a non-negative number`);
    }

    const scrollAnchor = scrollRestore.scrollAnchor;
    if (scrollAnchor !== null && typeof scrollAnchor !== 'object') {
        throw new Error(`${contextLabel} scrollRestore.scrollAnchor must be an object or null`);
    }

    ModeContext.updateActiveTabScroll(scrollY);
    ModeContext.updateActiveTabScrollAnchor(scrollAnchor, true);

    const viewAnchorRootId = typeof scrollRestore.viewAnchorRootId === 'string' && scrollRestore.viewAnchorRootId.length > 0
        ? scrollRestore.viewAnchorRootId
        : null;

    const focusNoteId = typeof scrollRestore.focusNoteId === 'string'
        ? scrollRestore.focusNoteId
        : '';

    const opType = scrollRestore.opType;
    if (typeof opType !== 'string' || opType.length === 0) {
        throw new Error(`${contextLabel} scrollRestore.opType must be a non-empty string`);
    }

    let editingNoteId;
    if (Object.prototype.hasOwnProperty.call(scrollRestore, 'editingNoteId')) {
        editingNoteId = scrollRestore.editingNoteId;
        if (editingNoteId !== null && typeof editingNoteId !== 'string') {
            throw new Error(`${contextLabel} scrollRestore.editingNoteId must be a string or null`);
        }
        if (typeof editingNoteId === 'string' && editingNoteId.length === 0) {
            throw new Error(`${contextLabel} scrollRestore.editingNoteId must be a non-empty string or null`);
        }
    }

    const anchorId = scrollAnchor && typeof scrollAnchor.anchorId === 'string' && scrollAnchor.anchorId.length > 0
        ? scrollAnchor.anchorId
        : null;

    return {
        visibleRootAnchorId: viewAnchorRootId || anchorId,
        focusNoteId,
        opType,
        editingNoteId,
    };
}

function _applyHistorySelectionState({
    shouldEdit,
    noteId,
    priorEditingNoteId,
}) {
    if (shouldEdit) {
        if (typeof noteId !== 'string' || noteId.length === 0) {
            throw new Error('History selection state requires a non-empty noteId when shouldEdit is true');
        }

        if (ModeContext.currentNoteId !== noteId) {
            ModeContext.setCurrentNoteId(noteId);
        }

        if (!ModeContext.isEditing) {
            ModeContext.setEditing(true);
        }

        ModeContext.markCaretVisible();
        return;
    }

    if (ModeContext.currentContent !== null) {
        ModeContext.setCurrentContent(null);
    }

    let cleanupTarget = null;
    if (typeof priorEditingNoteId === 'string' && priorEditingNoteId.length > 0) {
        cleanupTarget = document.querySelector(`[data-note-id="${priorEditingNoteId}"]`);
    }

    if (!cleanupTarget) {
        cleanupTarget = document.querySelector(`.${CONFIG.CLASSES.NOTE}.${CONFIG.CLASSES.EDITING}`);
    }

    if (cleanupTarget) {
        DOMUtils.setNoteEditable(cleanupTarget, false);
        DOMUtils.revealCaret(cleanupTarget);
    }

    detachEditorSurface();
    clearTagBar();

    if (ModeContext.isEditing) {
        ModeContext.setEditing(false);
    }

    if (ModeContext.currentNoteId !== null) {
        ModeContext.setCurrentNoteId(null);
    }
}

export async function actionUndo() {
    let startedAt = performance.now();
    let visibleRootAnchorId = null;
    let focusNoteId = '';
    const restoreEditing = ModeContext.isEditing;
    const restoreEditingNoteId = ModeContext.currentNoteId;
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
    const result = await NotesAPI.undo().finally(() => {
        if (ModeContext.isLoading) {
            ModeContext.setLoading(false);
        }
    });
    Logger.logDebug('Undo API response', result, Logger.LogCategory.DEBUG);

    if (result.status === 'noop') {
        Logger.logAction('undo_noop', { message: result.message });
        return; 
    }

    if (result.status === 'success') {
        Logger.logAction('undo_success', { message: result.message });

        const restored = applyScrollRestore(result.scrollRestore, 'Undo');
        visibleRootAnchorId = restored.visibleRootAnchorId;
        focusNoteId = restored.focusNoteId;
        const opType = restored.opType;

        if (ModeContext.isDirty) {
            ModeContext.setDirty(false);
        }

			if (opType === 'edit_mode') {
			if (typeof restored.editingNoteId === 'undefined') {
				throw new Error('Undo edit_mode response missing scrollRestore.editingNoteId');
			}
			const nextEditingNoteId = restored.editingNoteId;
			const shouldEdit = nextEditingNoteId !== null;
			const noteId = nextEditingNoteId;
			_applyHistorySelectionState({ shouldEdit, noteId, priorEditingNoteId: restoreEditingNoteId });
			} else {
				let opDeletesEditingTarget = false;
				if (opType === 'create_note') {
					opDeletesEditingTarget = true;
				} else if (opType === 'paste_subtree') {
					opDeletesEditingTarget = true;
				}

			// IMPORTANT: treat server-provided focusNoteId as scroll guidance, not as an
			// implicit "start editing this note" directive. Otherwise undoing a prior
			// collapse/move op while editing causes the editor to jump to unrelated notes.
			const shouldKeepEditing = Boolean(restoreEditing) && !opDeletesEditingTarget;
			if (shouldKeepEditing && (typeof restoreEditingNoteId !== 'string' || restoreEditingNoteId.length === 0)) {
				throw new Error('Invariant violation: restoreEditing is true but restoreEditingNoteId is empty');
			}

				let shouldEdit = false;
				let noteId = null;
				if (shouldKeepEditing) {
					shouldEdit = true;
					noteId = restoreEditingNoteId;
				} else if (opDeletesEditingTarget && Boolean(restoreEditing) && Boolean(focusNoteId)) {
					// Undoing a paste/create deletes the note that was actively edited; restore editing
					// to the server-provided focus target (typically the paste target).
					shouldEdit = true;
					noteId = focusNoteId;
				} else if (opType === 'delete_subtree' && Boolean(focusNoteId)) {
					// Undoing a delete should restore the deleted note subtree and re-enter
					// editing on the restored root.
					shouldEdit = true;
					noteId = focusNoteId;
				}
				_applyHistorySelectionState({ shouldEdit, noteId, priorEditingNoteId: restoreEditingNoteId });
			}
		} else {
        
        throw new Error(`Undo failed: ${result.message || 'Unknown error'}`);
    }

    const newContent = await actionRefreshAndMaybeSelect({ startedAt, context: 'actionUndo', visibleRootAnchorId });

    ModeContext.restoreScrollForActiveTab();
    if (focusNoteId) {
		window.setTimeout(() => {
			scrollNoteIntoView(focusNoteId, {});
		}, 300);
	}

    if (ModeContext.currentContent !== newContent && newContent !== null) {
        ModeContext.setCurrentContent(newContent);
    }

    ModeContext.validate();
}

export async function actionRedo() {
    let startedAt = performance.now();
    let visibleRootAnchorId = null;
    let focusNoteId = '';
    const restoreEditing = ModeContext.isEditing;
    const restoreEditingNoteId = ModeContext.currentNoteId;
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
    const result = await NotesAPI.redo().finally(() => {
        if (ModeContext.isLoading) {
            ModeContext.setLoading(false);
        }
    });
    Logger.logDebug('Redo API response', result, Logger.LogCategory.DEBUG);

    if (result.status === 'noop') {
        Logger.logAction('redo_noop', { message: result.message });
        return; 
    }

    if (result.status === 'success') {
        Logger.logAction('redo_success', { message: result.message });

        const restored = applyScrollRestore(result.scrollRestore, 'Redo');
        visibleRootAnchorId = restored.visibleRootAnchorId;
        focusNoteId = restored.focusNoteId;
        const opType = restored.opType;

        if (ModeContext.isDirty) {
            ModeContext.setDirty(false);
        }

		if (opType === 'edit_mode') {
            if (typeof restored.editingNoteId === 'undefined') {
                throw new Error('Redo edit_mode response missing scrollRestore.editingNoteId');
            }
            const nextEditingNoteId = restored.editingNoteId;
            const shouldEdit = nextEditingNoteId !== null;
            const noteId = nextEditingNoteId;
			_applyHistorySelectionState({ shouldEdit, noteId, priorEditingNoteId: restoreEditingNoteId });
			} else {
				const opDeletesEditingTarget = opType === 'delete_subtree';
				let opRecreatesFocusTarget = false;
				if (opType === 'create_note') {
					opRecreatesFocusTarget = true;
				} else if (opType === 'paste_subtree') {
					opRecreatesFocusTarget = true;
				}
				const shouldKeepEditing = Boolean(restoreEditing) && !opDeletesEditingTarget && !opRecreatesFocusTarget;
	            if (shouldKeepEditing && (typeof restoreEditingNoteId !== 'string' || restoreEditingNoteId.length === 0)) {
	                throw new Error('Invariant violation: restoreEditing is true but restoreEditingNoteId is empty');
	            }

	            // Redo should not jump the editor to focusNoteId for collapse/move/update.
	            // But redo of create/paste should select the newly (re)created note.
	            let shouldEdit = false;
	            let noteId = null;
	            if (opRecreatesFocusTarget && Boolean(focusNoteId)) {
	                shouldEdit = true;
	                noteId = focusNoteId;
	            } else if (shouldKeepEditing) {
	                shouldEdit = true;
	                noteId = restoreEditingNoteId;
	            }
				_applyHistorySelectionState({ shouldEdit, noteId, priorEditingNoteId: restoreEditingNoteId });
			}
    } else {
        
        throw new Error(`Redo failed: ${result.message || 'Unknown error'}`);
    }

    const newContent = await actionRefreshAndMaybeSelect({ startedAt, context: 'actionRedo', visibleRootAnchorId });

    ModeContext.restoreScrollForActiveTab();
    if (focusNoteId) {
		window.setTimeout(() => {
			scrollNoteIntoView(focusNoteId, {});
		}, 300);
	}

    if (ModeContext.currentContent !== newContent && newContent !== null) {
        ModeContext.setCurrentContent(newContent);
    }

    ModeContext.validate();
}
