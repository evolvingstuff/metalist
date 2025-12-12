import { CONFIG } from '../../config.js';
import { ModeContextInstance as ModeContext } from '../mode-context.js';

function logVDOM(action, details) {
    console.log(` [VDOM] ${action}`, details);
}

function diffSiblingOrder(currentIds, desiredIds) {
    const position = new Map(currentIds.map((id, idx) => [id, idx]));
    const working = currentIds.slice();
    const desiredSet = new Set(desiredIds);

    const ops = [];

    for (let i = working.length - 1; i >= 0; i -= 1) {
        const id = working[i];
        if (!desiredSet.has(id)) {
            working.splice(i, 1);
            position.delete(id);
            ops.push({ type: 'remove', id, fromIndex: i });
        }
    }

    for (let target = 0; target < desiredIds.length; target += 1) {
        const id = desiredIds[target];
        const existingIndex = position.has(id) ? position.get(id) : -1;

        if (existingIndex === -1) {
            working.splice(target, 0, id);
            ops.push({ type: 'insert', id, toIndex: target });

            for (let i = target + 1; i < working.length; i += 1) {
                position.set(working[i], i);
            }
            position.set(id, target);
            continue;
        }

        if (existingIndex === target) {
            continue;
        }

        working.splice(existingIndex, 1);
        working.splice(target, 0, id);
        ops.push({ type: 'move', id, fromIndex: existingIndex, toIndex: target });

        const start = Math.min(existingIndex, target);
        const end = Math.max(existingIndex, target);
        for (let i = start; i <= end; i += 1) {
            position.set(working[i], i);
        }
    }

    return ops;
}

function diffNoteForest(currentChildren, desiredChildren, parentId = null, results = []) {
    const currentIds = currentChildren.map((node) => node.id);
    const desiredIds = desiredChildren.map((node) => node.id);

    const currentById = new Map(currentChildren.map((node) => [node.id, node]));
    const desiredById = new Map(desiredChildren.map((node) => [node.id, node]));

    const orderOps = diffSiblingOrder(currentIds, desiredIds).map((op) => {
        if (op.type === 'remove') {
            return { ...op, node: currentById.get(op.id) };
        }
        if (op.type === 'insert') {
            return { ...op, node: desiredById.get(op.id) };
        }
        return op;
    });

    if (orderOps.length > 0) {
        results.push({ parentId, operations: orderOps });
    }

    for (const id of desiredIds) {
        if (!currentById.has(id)) {
            continue;
        }
        const currentNode = currentById.get(id);
        const desiredNode = desiredById.get(id);
        diffNoteForest(currentNode.children, desiredNode.children, id, results);
    }

    return results;
}

function createNoteElement(noteId) {
    const noteElement = document.createElement('div');
    noteElement.classList.add(CONFIG.CLASSES.NOTE);
    noteElement.dataset.noteId = noteId;
    noteElement.dataset.parentId = '';
    noteElement.dataset.isCollapsed = 'false';

    const collapseToggle = document.createElement('button');
    collapseToggle.classList.add('note-collapse-toggle');
    collapseToggle.type = 'button';
    collapseToggle.setAttribute('aria-label', 'Collapse note');
    collapseToggle.setAttribute('title', 'Collapse');
    noteElement.appendChild(collapseToggle);

    const contentElement = document.createElement('div');
    contentElement.classList.add(CONFIG.CLASSES.NOTE_CONTENT);
    contentElement.setAttribute('contenteditable', 'false');
    noteElement.appendChild(contentElement);

    return noteElement;
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

export function applyDifferentialView(payload, options = {}) {
    if (!payload || !Array.isArray(payload.structure)) {
        throw new Error('Invalid differential payload');
    }

    const previousHashes = options.previousHashes || {};

    const notesContainer = document.getElementById('notes-container');
    if (!notesContainer) {
        throw new Error('Notes container not found');
    }

    const elementCache = new Map();
    const currentForest = buildDomForest(notesContainer, elementCache);
    const desired = buildDesiredForest(payload.structure, payload.notes || {});

    const diffResults = diffNoteForest(currentForest, desired.roots);
    let vdomOperations = 0;
    const insertedIds = new Set();

    const noteLocks = payload.locks || {};

    const parentContainerCache = new Map();
    const ensureParentContainer = (parentId) => {
        const key = parentId || '__root__';
        if (parentContainerCache.has(key)) {
            return parentContainerCache.get(key);
        }
        if (!parentId) {
            parentContainerCache.set(key, notesContainer);
            return notesContainer;
        }
        const parentElement = elementCache.get(parentId) || document.querySelector(`[data-note-id="${parentId}"]`);
        if (!parentElement) {
            throw new Error(`Parent note ${parentId} missing from DOM`);
        }
        const container = ensureChildContainer(parentElement);
        parentContainerCache.set(key, container);
        return container;
    };

    for (const { parentId, operations } of diffResults) {
        const parentContainer = ensureParentContainer(parentId);
        for (const op of operations) {
            if (op.type === 'remove') {
                const node = op.node;
                if (!node) {
                    throw new Error(`Remove operation missing node for ${op.id}`);
                }
                const element = elementCache.get(op.id);
                if (!element) {
                    continue;
                }
                const ids = collectSubtreeIds(node);
                element.remove();
                ids.forEach((id) => {
                    elementCache.delete(id);
                    if (ModeContext.hasNoteHash(id)) {
                        ModeContext.removeNoteHash(id);
                    }
                });
                logVDOM('removed note', { noteId: op.id, parentId });
                vdomOperations += 1;
                continue;
            }

            if (op.type === 'insert') {
                const node = op.node;
                if (!node) {
                    throw new Error(`Insert operation missing node for ${op.id}`);
                }
                const reference = findNoteChildAt(parentContainer, op.toIndex);
                const element = createNoteSubtree(node, desired.nodeById, elementCache, insertedIds);
                parentContainer.insertBefore(element, reference);
                logVDOM('inserted note', { noteId: op.id, parentId, index: op.toIndex });
                vdomOperations += 1;
                continue;
            }

            if (op.type === 'move') {
                const element = elementCache.get(op.id);
                if (!element) {
                    throw new Error(`Move target ${op.id} missing from DOM`);
                }
                const reference = findNoteChildAt(parentContainer, op.toIndex);
                if (reference !== element) {
                    parentContainer.insertBefore(element, reference);
                    logVDOM('moved note', { noteId: op.id, parentId, from: op.fromIndex, to: op.toIndex });
                    vdomOperations += 1;
                }
            }
        }
    }

    for (const entry of payload.structure) {
        const noteId = entry.id;
        const parentId = entry.parentId || '';
        const noteElement = elementCache.get(noteId) || document.querySelector(`[data-note-id="${noteId}"]`);
        if (!noteElement) {
            throw new Error(`Note ${noteId} missing from DOM after diff`);
        }

        elementCache.set(noteId, noteElement);

        const noteData = payload.notes?.[noteId] || null;
        const incomingHash = typeof entry.hash === 'string' ? entry.hash : null;
        const previousHash = Object.prototype.hasOwnProperty.call(previousHashes, noteId)
            ? previousHashes[noteId]
            : (noteElement.dataset.contentHash || null);

        if (insertedIds.has(noteId) && !noteData) {
            throw new Error(`New note ${noteId} missing payload data`);
        }
        const existingFlags = {
            isEditing: noteElement.classList.contains(CONFIG.CLASSES.EDITING),
            isCollapsed: noteElement.classList.contains('collapsed'),
            memoryMode: noteElement.classList.contains('memory-mode'),
            memorySelected: noteElement.classList.contains('memory-selected'),
        };
        const flags = noteData?.flags || existingFlags;

        const lockOwner = noteLocks[noteId];
        const lockedByOther = Boolean(lockOwner) && lockOwner !== payload.currentClientId;
        const isEditing = Boolean(flags.isEditing);
        const editingByCurrentClient = isEditing && lockOwner === payload.currentClientId;

        noteElement.dataset.parentId = parentId;
        noteElement.dataset.isCollapsed = Boolean(flags.isCollapsed).toString();

        noteElement.classList.add(CONFIG.CLASSES.NOTE);
        noteElement.classList.toggle('locked', lockedByOther);
        noteElement.classList.toggle('interactive', !lockedByOther);
        noteElement.classList.toggle(CONFIG.CLASSES.EDITING, isEditing && !lockedByOther);
        noteElement.classList.toggle('collapsed', Boolean(flags.isCollapsed));
        noteElement.classList.toggle('memory-mode', Boolean(flags.memoryMode));
        noteElement.classList.toggle('memory-selected', Boolean(flags.memorySelected));

        updateLockIcon(noteElement, lockedByOther);

        const contentElement = noteElement.querySelector(':scope > .' + CONFIG.CLASSES.NOTE_CONTENT) || noteElement.querySelector(':scope > .note-content');
        if (!contentElement) {
            throw new Error(`Note ${noteId} missing content element`);
        }

        const shouldBeEditable = isEditing && !lockedByOther && !Boolean(flags.memoryMode);
        const contentEditable = shouldBeEditable ? 'true' : 'false';
        contentElement.setAttribute('contenteditable', contentEditable);
        contentElement.contentEditable = contentEditable;

        const shouldRenderContent = Boolean(noteData)
            && !editingByCurrentClient
            && (
                insertedIds.has(noteId)
                || incomingHash === null
                || previousHash === null
                || previousHash !== incomingHash
            );

        if (shouldRenderContent) {
            contentElement.innerHTML = noteData.content;
            logVDOM('replaced note content', { noteId });
            vdomOperations += 1;
            if (incomingHash) {
                noteElement.dataset.contentHash = incomingHash;
            }
        } else if (incomingHash && noteElement.dataset.contentHash !== incomingHash && !editingByCurrentClient) {
            noteElement.dataset.contentHash = incomingHash;
        }
    }

    removeEmptyChildContainers(notesContainer);

    if (payload.treeHash && ModeContext.rootHash !== payload.treeHash) {
        ModeContext.setRootHash(payload.treeHash);
    }

    return {
        notesContainer,
        editingNoteElement: payload.editingNoteId ? document.querySelector(`[data-note-id="${payload.editingNoteId}"]`) : null,
        vdomOperations,
    };
}

function buildDomForest(container, elementCache) {
    const result = [];
    const children = Array.from(container.children);
    for (const child of children) {
        if (!child.dataset || !child.dataset.noteId) {
            continue;
        }
        const noteId = child.dataset.noteId;
        elementCache.set(noteId, child);
        const childContainer = child.querySelector(':scope > .note-children');
        const descendants = childContainer ? buildDomForest(childContainer, elementCache) : [];
        result.push({ id: noteId, element: child, children: descendants });
    }
    return result;
}

function buildDesiredForest(structure, notes) {
    const nodeById = new Map();
    const roots = [];
    const rootIds = new Set();

    const getOrCreate = (id) => {
        if (!nodeById.has(id)) {
            nodeById.set(id, { id, entry: null, data: null, children: [] });
        }
        return nodeById.get(id);
    };

    for (const entry of structure) {
        if (!entry || typeof entry !== 'object') {
            throw new Error('Malformed structure entry');
        }
        const { id, parentId = null } = entry;
        if (typeof id !== 'string') {
            throw new Error('Structure entry missing id');
        }
        const node = getOrCreate(id);
        node.entry = entry;
        node.data = notes[id] || null;

        if (parentId) {
            const parentNode = getOrCreate(parentId);
            if (!parentNode.children.some((child) => child.id === id)) {
                parentNode.children.push(node);
            }
        } else if (!rootIds.has(id)) {
            roots.push(node);
            rootIds.add(id);
        }
    }

    return { roots, nodeById };
}

function findNoteChildAt(parentContainer, index) {
    if (index === parentContainer.children.length) {
        return null;
    }
    let seen = 0;
    for (const child of Array.from(parentContainer.children)) {
        if (child.dataset && child.dataset.noteId) {
            if (seen === index) {
                return child;
            }
            seen += 1;
        }
    }
    return null;
}

function createNoteSubtree(node, nodeById, elementCache, insertedIds) {
    const { id } = node;
    const noteElement = createNoteElement(id);
    elementCache.set(id, noteElement);
    if (insertedIds) {
        insertedIds.add(id);
    }

    if (node.children.length > 0) {
        const container = ensureChildContainer(noteElement);
        for (const child of node.children) {
            const resolvedChild = nodeById.get(child.id) || child;
            const childElement = createNoteSubtree(resolvedChild, nodeById, elementCache, insertedIds);
            container.appendChild(childElement);
        }
    }

    return noteElement;
}

function collectSubtreeIds(node) {
    const ids = [node.id];
    for (const child of node.children) {
        ids.push(...collectSubtreeIds(child));
    }
    return ids;
}

function removeEmptyChildContainers(notesContainer) {
    const noteElements = notesContainer.querySelectorAll('[data-note-id]');
    noteElements.forEach((noteElement) => {
        const childContainer = noteElement.querySelector(':scope > .note-children');
        if (childContainer && childContainer.querySelectorAll(':scope > [data-note-id]').length === 0) {
            childContainer.remove();
        }
    });
}
