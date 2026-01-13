import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { NotesAPI } from '../../api-client.js';
import { DOMUtils } from '../../dom-utils.js';
import { detachEditorSurface } from '../../editor-toolbar.js';
import { clearTagBar } from '../services/tag-bar-service.js';
import { scrollWindowToYFastAnimated } from '../services/animated-scroll-service.js';
import { scrollNoteIntoView } from '../services/scroll-restoration-service.js';
import { actionSaveNote } from './content-actions.js';
import { actionSwitchNotes, actionSelectNote } from './selection-actions.js';
import { actionRefreshAndMaybeSelect } from './ui-actions.js';

export async function deleteNote(noteId) {
    let startedAt = performance.now();

    let t1 = performance.now();

    Logger.logAction('deleteNote', {
        noteId,
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId
    });

    if (!noteId) {
        throw new Error('Cannot delete note: noteId is required');
    }

    if (ModeContext.currentNoteId !== noteId) {
        throw new Error(`Programming error: Deleting note ${noteId}, but currentNoteId is ${ModeContext.currentNoteId}`);
    }

    if (!ModeContext.isEditing) {
        throw new Error(`Programming error: Deleting current note ${noteId}, but isEditing is false`);
    }

    ModeContext.setEditing(false);
    ModeContext.setCurrentNoteId(null);

    if (ModeContext.currentContent !== null) {
        ModeContext.setCurrentContent(null);
    }
        
    if (ModeContext.isDirty) {
        ModeContext.setDirty(false);
    }

    ModeContext.setLoading(true);

    let t2 = performance.now();

    await NotesAPI.deleteNote(noteId);

    let t3 = performance.now()

    ModeContext.setLoading(false);

    await actionRefreshAndMaybeSelect({startedAt: startedAt, context: 'deleteNote'});

    let t4 = performance.now();
    console.log(`DEBUGZ: deleteNote t2 - t1 ${(t2-t1)} ms`)
    console.log(`DEBUGZ: deleteNote t3 - t2 ${(t3-t2)} ms`)
    console.log(`DEBUGZ: deleteNote t4 - t3 ${(t4-t3)} ms`)
    console.log(`DEBUGZ: deleteNote t4 - t1 ${(t4-t1)} ms`)
}

export async function deleteNoteOutsideEdit(noteId) {
    let startedAt = performance.now();

    Logger.logAction('deleteNoteOutsideEdit', {
        noteId,
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId,
        isLoading: ModeContext.isLoading
    });

    if (!noteId) {
        throw new Error('Cannot delete note: noteId is required');
    }

    if (ModeContext.isEditing) {
        throw new Error(`Programming error: deleteNoteOutsideEdit called while editing note ${ModeContext.currentNoteId}`);
    }

	const shouldManageLoading = !ModeContext.isLoading;
	if (shouldManageLoading) {
		ModeContext.setLoading(true);
	}

	await (async () => {
		await NotesAPI.deleteNote(noteId);

		if (ModeContext.currentNoteId === noteId) {
			ModeContext.setCurrentNoteId(null);
		}

		if (ModeContext.currentContent !== null) {
			ModeContext.setCurrentContent(null);
		}

		await actionRefreshAndMaybeSelect({ startedAt: startedAt, context: 'deleteNoteOutsideEdit'});
	})().finally(() => {
		if (shouldManageLoading && ModeContext.isLoading) {
			ModeContext.setLoading(false);
		}
	});
}

export async function createNote() {
    let startedAt = performance.now();

    Logger.logAction('createNote', {
        currentNoteId: ModeContext.currentNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty
    });

    const currentNoteId = ModeContext.currentNoteId;
    const shouldScrollToTopAfterCreate = !currentNoteId;

    if (ModeContext.isEditing && ModeContext.isDirty && currentNoteId) {
        await actionSaveNote(currentNoteId);
    }

    if (!(ModeContext.isEditing && ModeContext.isDirty && currentNoteId)) {
        ModeContext.setLoading(true);
    }

    let data;
    if (currentNoteId) {
                
        Logger.logDebug('Creating new sibling note after note', { 
            currentNoteId,
            searchQuery: ModeContext.searchQuery
        }, Logger.LogCategory.DEBUG);
        data = await NotesAPI.createSibling(currentNoteId, ModeContext.searchQuery);
    } else {
        // Find the first visible note to insert before
        const firstVisibleNote = document.querySelector('.note');
        const firstVisibleNoteId = firstVisibleNote ? firstVisibleNote.dataset.noteId : '';
                
        Logger.logDebug('Creating new note at top of list', {
            firstVisibleNoteId,
            searchQuery: ModeContext.searchQuery
        }, Logger.LogCategory.DEBUG);
        data = await NotesAPI.createNote(firstVisibleNoteId, ModeContext.searchQuery);
    }

    const newNoteId = data.id;

    ModeContext.setLoading(false);

    const caretOptions = { initialCaretVisibility: 'visible' };
    if (ModeContext.isEditing) {
        await actionSwitchNotes(newNoteId, caretOptions);
    } else {
        await actionSelectNote(newNoteId, caretOptions);
    }

	if (shouldScrollToTopAfterCreate) {
		scrollWindowToYFastAnimated(0);
	}
}

export async function createChildNote() {
    let startedAt = performance.now();

    Logger.logAction('createChildNote', {
        currentNoteId: ModeContext.currentNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty
    });

    const currentNoteId = ModeContext.currentNoteId;

    if (!currentNoteId) {
        Logger.logDebug('Cannot create child note: no parent note selected', {}, Logger.LogCategory.DEBUG);
        return await createNote();
    }

    if (ModeContext.isEditing && ModeContext.isDirty && currentNoteId) {
        await actionSaveNote(currentNoteId);
    }

    if (!(ModeContext.isEditing && ModeContext.isDirty && currentNoteId)) {
        ModeContext.setLoading(true);
    }

    Logger.logDebug('Creating new child note under parent', { 
        parentNoteId: currentNoteId 
    }, Logger.LogCategory.DEBUG);
    
    const data = await NotesAPI.createChild(currentNoteId, ModeContext.searchQuery);
    const newNoteId = data.id;

    ModeContext.setLoading(false);

    const caretOptions = { initialCaretVisibility: 'visible' };
    if (ModeContext.isEditing) {
        return await actionSwitchNotes(newNoteId, caretOptions);
    } else {
        return await actionSelectNote(newNoteId, caretOptions);
    }
}

export async function moveNoteUp(noteId) {
    let startedAt = performance.now();

    Logger.logAction('moveNoteUp', {
        noteId,
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId,
        isDirty: ModeContext.isDirty
    });

    if (!noteId) {
        throw new Error('Cannot move note: noteId is required');
    }

    if (ModeContext.isDirty && noteId === ModeContext.currentNoteId) {
        await actionSaveNote(noteId);
    }

	ModeContext.setLoading(true);

	await NotesAPI.moveNoteUp(noteId).finally(() => {
		ModeContext.setLoading(false);
	});

    if (ModeContext.isEditing) {
        ModeContext.markCaretHidden();
    }

    const newContent = await actionRefreshAndMaybeSelect({startedAt: startedAt, context: 'moveNoteUp'});

    if (ModeContext.currentContent !== newContent) {
        ModeContext.setCurrentContent(newContent);
    }
}

export async function moveNoteDown(noteId) {
    let startedAt = performance.now();

    Logger.logAction('moveNoteDown', {
        noteId,
        isEditing: ModeContext.isEditing,
        currentNoteId: ModeContext.currentNoteId,
        isDirty: ModeContext.isDirty
    });

    if (!noteId) {
        throw new Error('Cannot move note: noteId is required');
    }

    if (ModeContext.isDirty && noteId === ModeContext.currentNoteId) {
        await actionSaveNote(noteId);
    }

	ModeContext.setLoading(true);

	await NotesAPI.moveNoteDown(noteId).finally(() => {
		ModeContext.setLoading(false);
	});

    if (ModeContext.isEditing) {
        ModeContext.markCaretHidden();
    }

    const newContent = await actionRefreshAndMaybeSelect({startedAt: startedAt, context: 'moveNoteDown'});

    if (ModeContext.currentContent !== newContent) {
        ModeContext.setCurrentContent(newContent);
    }
}

async function setNoteCollapse(noteId, collapsed) {
    let startedAt = performance.now();

    Logger.logAction('setNoteCollapse', {
        noteId,
        collapsed,
        isEditing: ModeContext.isEditing,
        hoveredNoteId: ModeContext.hoveredNoteId
    });

    if (!noteId) {
        throw new Error('Cannot change collapse state: noteId is required');
    }

    if (ModeContext.isLoading) {
        Logger.logNoop('Collapse/expand ignored while request in-flight', {
            noteId,
            collapsed,
            activeTab: ModeContext.activeTabId
        });
        return;
    }

    if (ModeContext.isEditing) {
        const editingNoteId = ModeContext.currentNoteId;
        if (!editingNoteId) {
            throw new Error('Invariant violation: isEditing is true but currentNoteId is null');
        }

        Logger.logDebug('Collapse toggle clicked while editing; exiting edit mode first', {
            editingNoteId,
            targetNoteId: noteId,
            collapsed
        }, Logger.LogCategory.EVENT);

        if (ModeContext.isDirty) {
            await actionSaveNote(editingNoteId);
        }

        const editingNoteElement = DOMUtils.getNoteById(editingNoteId);
        DOMUtils.setNoteEditable(editingNoteElement, false);
        DOMUtils.revealCaret(editingNoteElement);
        detachEditorSurface();
        clearTagBar();

        ModeContext.setEditing(false);
        ModeContext.setCurrentNoteId(null);
        if (ModeContext.currentContent !== null) {
            ModeContext.setCurrentContent(null);
        }
    }

    // Block UI while performing the collapse/expand operation
    ModeContext.setLoading(true);
    if (collapsed) {
        await NotesAPI.collapseNote(noteId);
    } else {
        await NotesAPI.expandNote(noteId);
    }
    // Release the lock before asking for a view refresh; refresh manages its own lock
    ModeContext.setLoading(false);
    await actionRefreshAndMaybeSelect({ startedAt: startedAt, context: 'setNoteCollapse' });
}

export async function collapseNote(noteId) {
    await setNoteCollapse(noteId, true);
}

export async function expandNote(noteId) {
    await setNoteCollapse(noteId, false);
}

export async function actionCopyNote() {
    ModeContext._requestStartedAt = performance.now();

    const currentNoteId = ModeContext.currentNoteId;
    
    Logger.logAction('actionCopyNote', { 
        currentNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty
    });

    if (!currentNoteId) {
        throw new Error('Cannot copy note: no note selected');
    }

    // Save the note first if it's dirty to ensure we copy the current edited content
    if (ModeContext.isDirty) {
        await actionSaveNote(currentNoteId);
    }

    // Call the server to serialize the note tree to clipboard
    const response = await NotesAPI.copyNote(currentNoteId);

    // No need to store clipboard state client-side anymore
    return response;
}

export async function actionPasteNoteSibling() {
    const currentNoteId = ModeContext.currentNoteId;

    Logger.logAction('actionPasteNoteSibling', {
        currentNoteId,
        isEditing: ModeContext.isEditing
    });

    if (!ModeContext.isEditing || !currentNoteId) {
        throw new Error('Cannot paste sibling: no note selected');
    }

    if (ModeContext.isDirty) {
        await actionSaveNote(currentNoteId);
    }

    ModeContext.setLoading(true);
    const response = await NotesAPI.pasteNoteSibling(currentNoteId);
    ModeContext.setLoading(false);

    const newNoteId = response.id;
    if (typeof newNoteId !== 'string' || newNoteId.length === 0) {
        throw new Error('Paste sibling response missing new note id');
    }

    await actionSwitchNotes(newNoteId, { initialCaretVisibility: 'hidden' });
    window.requestAnimationFrame(() => {
        scrollNoteIntoView(newNoteId, {});
    });
}

export async function actionPasteNoteChild() {
    const currentNoteId = ModeContext.currentNoteId;
    
    Logger.logAction('actionPasteNoteChild', { 
        currentNoteId,
        isEditing: ModeContext.isEditing
    });

    if (!ModeContext.isEditing || !currentNoteId) {
        throw new Error('Cannot paste child: no note selected');
    }

    if (ModeContext.isDirty) {
        await actionSaveNote(currentNoteId);
    }

    ModeContext.setLoading(true);
    const response = await NotesAPI.pasteNoteChild(currentNoteId);
    ModeContext.setLoading(false);

    const newNoteId = response.id;
    if (typeof newNoteId !== 'string' || newNoteId.length === 0) {
        throw new Error('Paste child response missing new note id');
    }

    await actionSwitchNotes(newNoteId, { initialCaretVisibility: 'hidden' });
    window.requestAnimationFrame(() => {
        scrollNoteIntoView(newNoteId, {});
    });
}
