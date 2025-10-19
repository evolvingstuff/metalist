import { CONFIG } from '../../config.js';
import { ModeContextInstance as ModeContext } from '../mode-context.js';

function createNoteElement(noteId) {
    const noteElement = document.createElement('div');
    noteElement.classList.add(CONFIG.CLASSES.NOTE);
    noteElement.dataset.noteId = noteId;
    noteElement.dataset.parentId = '';
    noteElement.dataset.isCollapsed = 'false';

    const contentElement = document.createElement('div');
    contentElement.classList.add(CONFIG.CLASSES.NOTE_CONTENT);
    contentElement.setAttribute('contenteditable', 'true');
    noteElement.appendChild(contentElement);

    return noteElement;
}

function findChildById(parentElement, noteId) {
    if (!noteId) {
        return null;
    }
    return Array.from(parentElement.children).find((child) => child.dataset && child.dataset.noteId === noteId) || null;
}

function ensureChildContainer(noteElement) {
    let childContainer = noteElement.querySelector(':scope > .note-children');
    if (!childContainer) {
        childContainer = document.createElement('div');
        childContainer.classList.add('note-children');
        noteElement.appendChild(childContainer);
    }
    return childContainer;
}

function syncNoteHash(noteId, incomingHash) {
    const hasHash = ModeContext.hasNoteHash(noteId);
    if (hasHash) {
        const currentHash = ModeContext.getNoteHash(noteId);
        if (currentHash === incomingHash) {
            return;
        }
    }
    ModeContext.setNoteHash(noteId, incomingHash);
}

function removeStaleNotes(notesContainer, visibleIds) {
    const existingNotes = notesContainer.querySelectorAll('[data-note-id]');
    existingNotes.forEach((element) => {
        const noteId = element.dataset.noteId;
        if (!visibleIds.has(noteId)) {
            element.remove();
            if (ModeContext.hasNoteHash(noteId)) {
                ModeContext.removeNoteHash(noteId);
            }
        }
    });
}

function updateLockIcon(noteElement, lockedByOther) {
    let lockIcon = noteElement.querySelector(':scope > .lock-icon');
    if (lockedByOther) {
        if (!lockIcon) {
            lockIcon = document.createElement('span');
            lockIcon.classList.add('lock-icon');
            lockIcon.textContent = '🔒';
            noteElement.insertBefore(lockIcon, noteElement.firstChild);
        }
    } else if (lockIcon) {
        lockIcon.remove();
    }
}

function positionNote(noteElement, parentContainer, prevId, nextId) {
    const referenceNode = nextId ? findChildById(parentContainer, nextId) : null;
    if (noteElement.parentElement !== parentContainer) {
        parentContainer.insertBefore(noteElement, referenceNode);
        return;
    }

    if (referenceNode) {
        parentContainer.insertBefore(noteElement, referenceNode);
        return;
    }

    if (prevId) {
        const prevSibling = findChildById(parentContainer, prevId);
        if (prevSibling && prevSibling.nextElementSibling !== noteElement) {
            parentContainer.insertBefore(noteElement, prevSibling.nextElementSibling);
            return;
        }
    }

    parentContainer.appendChild(noteElement);
}

function cleanupChildContainers(notesContainer, parentsWithChildren) {
    const noteElements = notesContainer.querySelectorAll('[data-note-id]');
    noteElements.forEach((noteElement) => {
        const childContainer = noteElement.querySelector(':scope > .note-children');
        const noteId = noteElement.dataset.noteId;
        if (childContainer && !parentsWithChildren.has(noteId)) {
            childContainer.remove();
        }
    });
}

function shouldUpdateContent(noteId, incomingHash, isEditingByCurrentClient) {
    if (isEditingByCurrentClient) {
        if (!ModeContext.hasNoteHash(noteId)) {
            return true;
        }
        return ModeContext.getNoteHash(noteId) !== incomingHash;
    }
    return true;
}

export function applyDifferentialView(payload) {
    if (!payload || !Array.isArray(payload.structure)) {
        throw new Error('Invalid differential payload');
    }

    const notesContainer = document.getElementById('notes-container');
    if (!notesContainer) {
        throw new Error('Notes container not found');
    }

    const visibleIds = new Set(payload.structure.map((entry) => entry.id));
    removeStaleNotes(notesContainer, visibleIds);

    const elementsById = new Map();
    const parentsWithChildren = new Set();
    const noteLocks = payload.locks || {};

    const parentContainerFor = (parentId) => {
        if (!parentId) {
            return notesContainer;
        }
        const parentElement = elementsById.get(parentId) || document.querySelector(`[data-note-id="${parentId}"]`);
        if (!parentElement) {
            throw new Error(`Parent note ${parentId} missing from DOM`);
        }
        elementsById.set(parentId, parentElement);
        return ensureChildContainer(parentElement);
    };

    for (const entry of payload.structure) {
        const noteId = entry.id;
        const parentId = entry.parentId || null;
        const noteData = payload.notes?.[noteId];
        if (!noteData) {
            throw new Error(`Missing payload for note ${noteId}`);
        }

        if (parentId) {
            parentsWithChildren.add(parentId);
        }

        const parentContainer = parentContainerFor(parentId);

        let noteElement = document.querySelector(`[data-note-id="${noteId}"]`);
        if (!noteElement) {
            noteElement = createNoteElement(noteId);
            parentContainer.insertBefore(noteElement, entry.nextId ? findChildById(parentContainer, entry.nextId) : null);
        } else {
            positionNote(noteElement, parentContainer, entry.prevId, entry.nextId);
        }

        elementsById.set(noteId, noteElement);

        const lockOwner = noteLocks[noteId];
        const lockedByOther = Boolean(lockOwner) && lockOwner !== payload.currentClientId;
        const isEditing = Boolean(noteData.flags?.isEditing);
        const editingByCurrentClient = isEditing && lockOwner === payload.currentClientId;

        noteElement.classList.add(CONFIG.CLASSES.NOTE);
        noteElement.classList.toggle('locked', lockedByOther);
        noteElement.classList.toggle('interactive', !lockedByOther);
        noteElement.classList.toggle(CONFIG.CLASSES.EDITING, isEditing && !lockedByOther);
        noteElement.classList.toggle('collapsed', Boolean(noteData.flags?.isCollapsed));
        noteElement.classList.toggle('memory-mode', Boolean(noteData.flags?.memoryMode));
        noteElement.classList.toggle('memory-selected', Boolean(noteData.flags?.memorySelected));

        noteElement.dataset.parentId = parentId || '';
        noteElement.dataset.isCollapsed = noteData.flags?.isCollapsed ? 'true' : 'false';

        updateLockIcon(noteElement, lockedByOther);

        const contentElement = noteElement.querySelector(':scope > .' + CONFIG.CLASSES.NOTE_CONTENT) || noteElement.querySelector(':scope > .note-content');
        if (!contentElement) {
            throw new Error(`Note ${noteId} missing content element`);
        }

        const contentEditable = lockedByOther || Boolean(noteData.flags?.memoryMode) ? 'false' : 'true';
        contentElement.setAttribute('contenteditable', contentEditable);

        if (shouldUpdateContent(noteId, entry.hash, editingByCurrentClient)) {
            contentElement.innerHTML = noteData.content;
        }

        syncNoteHash(noteId, entry.hash);
    }

    cleanupChildContainers(notesContainer, parentsWithChildren);

    if (payload.treeHash && ModeContext.rootHash !== payload.treeHash) {
        ModeContext.setRootHash(payload.treeHash);
    }

    return {
        notesContainer,
        editingNoteElement: payload.editingNoteId ? document.querySelector(`[data-note-id="${payload.editingNoteId}"]`) : null
    };
}
