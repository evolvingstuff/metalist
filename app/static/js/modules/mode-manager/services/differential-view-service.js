import { CONFIG } from '../../config.js';
import { ModeContextInstance as ModeContext } from '../mode-context.js';

function logVDOM(action, details) {
    console.log(` [VDOM] ${action}`, details);
}

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
            logVDOM('removed note', { noteId });
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
        logVDOM('moved note parent', {
            noteId: noteElement.dataset.noteId,
            newParentId: parentContainer.closest('[data-note-id]')?.dataset?.noteId || null
        });
        return;
    }

    if (referenceNode) {
        if (noteElement.nextElementSibling !== referenceNode) {
            parentContainer.insertBefore(noteElement, referenceNode);
            logVDOM('reordered note (before nextId)', {
                noteId: noteElement.dataset.noteId,
                nextId,
            });
        }
        return;
    }

    if (prevId) {
        const prevSibling = findChildById(parentContainer, prevId);
        if (prevSibling && prevSibling.nextElementSibling !== noteElement) {
            parentContainer.insertBefore(noteElement, prevSibling.nextElementSibling);
            logVDOM('reordered note (after prevId)', {
                noteId: noteElement.dataset.noteId,
                prevId,
            });
            return;
        }
    }

    parentContainer.appendChild(noteElement);
    logVDOM('appended note', {
        noteId: noteElement.dataset.noteId,
        parentId: parentContainer.closest('[data-note-id]')?.dataset?.noteId || null,
    });
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
    const parentContainers = new Map();
    const childrenByParent = new Map();
    const parentsWithChildren = new Set();
    const noteLocks = payload.locks || {};

    const containerKey = (parentId) => parentId || '__root__';

    const parentContainerFor = (parentId) => {
        const key = containerKey(parentId);
        if (parentContainers.has(key)) {
            return parentContainers.get(key);
        }

        if (!parentId) {
            parentContainers.set(key, notesContainer);
            return notesContainer;
        }

        const parentElement = elementsById.get(parentId) || document.querySelector(`[data-note-id="${parentId}"]`);
        if (!parentElement) {
            throw new Error(`Parent note ${parentId} missing from DOM`);
        }
        elementsById.set(parentId, parentElement);
        const container = ensureChildContainer(parentElement);
        parentContainers.set(key, container);
        return container;
    };

    for (const entry of payload.structure) {
        const noteId = entry.id;
        const parentId = entry.parentId || null;
        const noteData = payload.notes?.[noteId] || null;

        if (parentId) {
            parentsWithChildren.add(parentId);
        }

        const parentContainer = parentContainerFor(parentId);

        let noteElement = document.querySelector(`[data-note-id="${noteId}"]`);
        if (!noteElement) {
            noteElement = createNoteElement(noteId);
            parentContainer.appendChild(noteElement);
            logVDOM('created note element', { noteId, parentId });
            if (!noteData) {
                throw new Error(`New note ${noteId} missing payload data`);
            }
        } else if (!parentContainer.contains(noteElement)) {
            parentContainer.appendChild(noteElement);
            logVDOM('moved note to parent', { noteId, parentId });
        }

        elementsById.set(noteId, noteElement);

        const lockOwner = noteLocks[noteId];
        const lockedByOther = Boolean(lockOwner) && lockOwner !== payload.currentClientId;
        const flags = noteData?.flags || {
            isEditing: noteElement.classList.contains(CONFIG.CLASSES.EDITING),
            isCollapsed: noteElement.classList.contains('collapsed'),
            memoryMode: noteElement.classList.contains('memory-mode'),
            memorySelected: noteElement.classList.contains('memory-selected'),
        };

        const isEditing = Boolean(flags.isEditing);
        const editingByCurrentClient = isEditing && lockOwner === payload.currentClientId;

        noteElement.classList.add(CONFIG.CLASSES.NOTE);
        noteElement.classList.toggle('locked', lockedByOther);
        noteElement.classList.toggle('interactive', !lockedByOther);
        noteElement.classList.toggle(CONFIG.CLASSES.EDITING, isEditing && !lockedByOther);
        noteElement.classList.toggle('collapsed', Boolean(flags.isCollapsed));
        noteElement.classList.toggle('memory-mode', Boolean(flags.memoryMode));
        noteElement.classList.toggle('memory-selected', Boolean(flags.memorySelected));

        noteElement.dataset.parentId = parentId || '';
        noteElement.dataset.isCollapsed = Boolean(flags.isCollapsed).toString();

        updateLockIcon(noteElement, lockedByOther);

        const contentElement = noteElement.querySelector(':scope > .' + CONFIG.CLASSES.NOTE_CONTENT) || noteElement.querySelector(':scope > .note-content');
        if (!contentElement) {
            throw new Error(`Note ${noteId} missing content element`);
        }

        const contentEditable = lockedByOther || Boolean(flags.memoryMode) ? 'false' : 'true';
        contentElement.setAttribute('contenteditable', contentEditable);

        if (noteData && shouldUpdateContent(noteId, entry.hash, editingByCurrentClient)) {
            contentElement.innerHTML = noteData.content;
            logVDOM('replaced note content', { noteId });
        }

        syncNoteHash(noteId, entry.hash);
        logVDOM('synced note hash', { noteId, hash: entry.hash });

        const key = containerKey(parentId);
        if (!childrenByParent.has(key)) {
            childrenByParent.set(key, []);
        }
        childrenByParent.get(key).push(noteId);
    }

    for (const [key, orderedIds] of childrenByParent.entries()) {
        const parentId = key === '__root__' ? null : key;
        const parentContainer = parentContainerFor(parentId);
        for (const noteId of orderedIds) {
            const element = elementsById.get(noteId);
            if (!element) {
                throw new Error(`Unable to reorder note ${noteId}: element missing`);
            }
            if (parentContainer.lastElementChild !== element) {
                parentContainer.appendChild(element);
                logVDOM('reordered note', { noteId, parentId });
            }
        }
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
