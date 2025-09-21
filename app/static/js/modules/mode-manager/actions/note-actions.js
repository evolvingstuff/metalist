import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { NotesAPI } from '../../api-client.js';
import { actionSaveNote } from './content-actions.js';
import { actionSwitchNotes, actionSelectNote } from './selection-actions.js';
import { actionRefreshAndMaybeSelect } from './ui-actions.js';

export async function deleteNote(noteId) {
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

    await NotesAPI.deleteNote(noteId);

    ModeContext.setLoading(false);

    await actionRefreshAndMaybeSelect();

    return;
}

export async function deleteNoteOutsideEdit(noteId) {
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

    try {
        await NotesAPI.deleteNote(noteId);

        if (ModeContext.currentNoteId === noteId) {
            ModeContext.setCurrentNoteId(null);
        }

        if (ModeContext.currentContent !== null) {
            ModeContext.setCurrentContent(null);
        }

        await actionRefreshAndMaybeSelect({ skipLoadingState: true });
    } finally {
        if (shouldManageLoading && ModeContext.isLoading) {
            ModeContext.setLoading(false);
        }
    }
}

export async function createNote() {
    Logger.logAction('createNote', {
        currentNoteId: ModeContext.currentNoteId,
        isEditing: ModeContext.isEditing,
        isDirty: ModeContext.isDirty
    });

    const currentNoteId = ModeContext.currentNoteId;

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
        const firstVisibleNoteId = firstVisibleNote ? firstVisibleNote.dataset.noteId : null;
                
        Logger.logDebug('Creating new note at top of list', {
            firstVisibleNoteId,
            searchQuery: ModeContext.searchQuery
        }, Logger.LogCategory.DEBUG);
        data = await NotesAPI.createNote(firstVisibleNoteId, ModeContext.searchQuery);
    }

    const newNoteId = data.id;

    ModeContext.setLoading(false);

    if (ModeContext.isEditing) {
        return await actionSwitchNotes(newNoteId);
    } else {
        return await actionSelectNote(newNoteId);
    }
}

export async function createChildNote() {
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
    
    const data = await NotesAPI.createChild(currentNoteId);
    const newNoteId = data.id;

    ModeContext.setLoading(false);

    if (ModeContext.isEditing) {
        return await actionSwitchNotes(newNoteId);
    } else {
        return await actionSelectNote(newNoteId);
    }
}

export async function moveNoteUp(noteId) {
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

    if (ModeContext.isEditing && noteId === ModeContext.currentNoteId) {
        ModeContext.setSavedCursorOffset(noteId, window.getSelection().focusOffset);
    }

    ModeContext.setLoading(true);
    
    try {
        await NotesAPI.moveNoteUp(noteId);
    } finally {
        ModeContext.setLoading(false);
    }

    const newContent = await actionRefreshAndMaybeSelect();

    if (ModeContext.currentContent !== newContent) {
        ModeContext.setCurrentContent(newContent);
    }
}

export async function moveNoteDown(noteId) {
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

    if (ModeContext.isEditing && noteId === ModeContext.currentNoteId) {
        ModeContext.setSavedCursorOffset(noteId, window.getSelection().focusOffset);
    }

    ModeContext.setLoading(true);
    
    try {
        await NotesAPI.moveNoteDown(noteId);
    } finally {
        ModeContext.setLoading(false);
    }

    const newContent = await actionRefreshAndMaybeSelect();

    if (ModeContext.currentContent !== newContent) {
        ModeContext.setCurrentContent(newContent);
    }
}

async function setNoteCollapse(noteId, collapsed) {
    Logger.logAction('setNoteCollapse', {
        noteId,
        collapsed,
        isEditing: ModeContext.isEditing,
        hoveredNoteId: ModeContext.hoveredNoteId
    });

    if (!noteId) {
        throw new Error('Cannot change collapse state: noteId is required');
    }

    if (ModeContext.isEditing) {
        throw new Error(`Programming error: Attempted to change collapse state for ${noteId} while editing`);
    }

    ModeContext.setLoading(true);

    try {
        if (collapsed) {
            await NotesAPI.collapseNote(noteId);
        } else {
            await NotesAPI.expandNote(noteId);
        }
        await actionRefreshAndMaybeSelect({ skipLoadingState: true });
    } finally {
        if (ModeContext.isLoading) {
            ModeContext.setLoading(false);
        }
    }
}

export async function collapseNote(noteId) {
    await setNoteCollapse(noteId, true);
}

export async function expandNote(noteId) {
    await setNoteCollapse(noteId, false);
}

export async function actionCopyNote() {
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
    await NotesAPI.copyNote(currentNoteId);
    
    // No need to store clipboard state client-side anymore
}

export async function actionPasteNoteSibling() {
    const currentNoteId = ModeContext.currentNoteId;
    
    Logger.logAction('actionPasteNoteSibling', { 
        currentNoteId,
        isEditing: ModeContext.isEditing
    });

    if (!currentNoteId) {
        throw new Error('Cannot paste sibling: no note selected');
    }

    if (ModeContext.isDirty) {
        await actionSaveNote(currentNoteId);
    }

    ModeContext.setLoading(true);

    const response = await NotesAPI.pasteNoteSibling(currentNoteId);
    const newNoteId = response.id;

    ModeContext.setCurrentNoteId(newNoteId);
    
    ModeContext.setLoading(false);

    await actionRefreshAndMaybeSelect();
}

export async function actionPasteNoteChild() {
    const currentNoteId = ModeContext.currentNoteId;
    
    Logger.logAction('actionPasteNoteChild', { 
        currentNoteId,
        isEditing: ModeContext.isEditing
    });

    if (!currentNoteId) {
        throw new Error('Cannot paste child: no note selected');
    }

    if (ModeContext.isDirty) {
        await actionSaveNote(currentNoteId);
    }

    ModeContext.setLoading(true);

    const response = await NotesAPI.pasteNoteChild(currentNoteId);
    const newNoteId = response.id;

    ModeContext.setCurrentNoteId(newNoteId);
    
    ModeContext.setLoading(false);

    await actionRefreshAndMaybeSelect();
}
