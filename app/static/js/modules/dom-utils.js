import { CONFIG } from './config.js';

export const DOMUtils = {
    findNoteElement(element) {
        return element.closest(`.${CONFIG.CLASSES.NOTE}`);
    },

    getNoteContent(noteElement) {
        return noteElement.querySelector(`.${CONFIG.CLASSES.NOTE_CONTENT}`);
    },

    getNoteId(noteElement) {
        if (!noteElement) {
            throw new Error('Note element is required');
        }
        const noteId = noteElement.dataset.noteId;
        if (!noteId) {
            throw new Error('Note missing data-note-id');
        }
        return noteId;
    },

    setNoteEditable(noteElement, isEditable) {
        const content = this.getNoteContent(noteElement);
        if (!content) {
            throw new Error('Note missing content element');
        }
        const editableValue = isEditable ? 'true' : 'false';
        content.setAttribute('contenteditable', editableValue);
        content.contentEditable = editableValue;
        noteElement.classList.toggle(CONFIG.CLASSES.EDITING, isEditable);
    },

    hideCaret(noteElement) {
        const content = this.getNoteContent(noteElement);
        if (!content) {
            throw new Error('Note missing content element');
        }
        content.classList.add(CONFIG.CLASSES.CARET_HIDDEN);
    },

    revealCaret(noteElement) {
        const content = this.getNoteContent(noteElement);
        if (!content) {
            throw new Error('Note missing content element');
        }
        content.classList.remove(CONFIG.CLASSES.CARET_HIDDEN);
    },

    getNoteById(noteId) {
        if (!noteId) {
            throw new Error('Note ID is required');
        }
        const note = document.querySelector(`[data-note-id="${noteId}"]`);
        if (!note) {
            throw new Error(`Note not found: ${noteId}`);
        }
        return note;
    },

    getAllNotes() {
        return document.querySelectorAll(`.${CONFIG.CLASSES.NOTE}`);
    },

    focusNote(noteElement, cursorOffset) {
        const contentElement = this.getNoteContent(noteElement);
        if (!contentElement) {
            throw new Error('Note content element not found');
        }
        if (typeof cursorOffset !== 'number' || !Number.isInteger(cursorOffset)) {
            throw new Error('Cursor offset must be an integer');
        }

        ensureEditableContentNode(contentElement);

        contentElement.focus();
		this.setCursorOffset(noteElement, cursorOffset);
	},

	focusNoteEdge(noteElement, position) {
		if (position !== 'start' && position !== 'end') {
			throw new Error('DOMUtils.focusNoteEdge requires position start|end');
		}
		const normalizedPosition = position;
		const contentElement = this.getNoteContent(noteElement);
		if (!contentElement) {
			throw new Error('Note content element not found');
		}

        ensureEditableContentNode(contentElement);

        const selection = window.getSelection();
        if (!selection) {
            throw new Error('No selection found when trying to focus note edge');
        }

        const range = document.createRange();
        range.selectNodeContents(contentElement);
        range.collapse(normalizedPosition === 'start');

        contentElement.focus();
        selection.removeAllRanges();
        selection.addRange(range);
    },

    getCursorOffset(noteElement) {
        if (!noteElement) {
            throw new Error('Note element is required');
        }

        const selection = window.getSelection();
        if (!selection) {
            throw new Error('No selection found');
        }

        const content = this.getNoteContent(noteElement);
        if (!content) {
            throw new Error('Note missing content element');
        }

        if (!content.contains(selection.anchorNode)) {
            throw new Error('Selection not in note');
        }

        const path = this.getNodePath(selection.anchorNode, content);
        if (!path) {
            throw new Error('Could not find path to cursor');
        }

		let offset = 0;
		for (const node of path) {
			if (node === selection.anchorNode) {
				offset += selection.anchorOffset;
				break;
			}
			const textContent = node.textContent;
			if (typeof textContent === 'string') {
				offset += textContent.length;
			}
		}

        return offset;
    },

    setCursorOffset(noteElement, offset) {
        if (!noteElement) {
            throw new Error('Note element is required');
        }
        if (typeof offset !== 'number' || offset < 0) {
            throw new Error(`Invalid offset: ${offset}`);
        }

        const content = this.getNoteContent(noteElement);
        if (!content) {
            throw new Error('Note missing content element');
        }

		console.log("[DEBUG] Setting cursor at offset:", offset);

		const allTextRange = document.createRange();
		allTextRange.selectNodeContents(content);
		const allText = allTextRange.toString();

		if (offset > allText.length) {
			console.log("[DEBUG] Offset beyond content length, clamping to end");
			offset = allText.length;
		}

		const targetRange = findRangeAtOffset(content, offset);
		if (!targetRange) {
			throw new Error(`Could not find position at offset ${offset}`);
		}

		const selection = window.getSelection();
		if (!selection) {
			throw new Error('Could not get selection');
		}

		selection.removeAllRanges();
		selection.addRange(targetRange);
	},

    getCursorOffsetFromClick(noteElement, coordinates) {
        if (!noteElement) {
            throw new Error('Note element is required');
        }
        if (!coordinates) {
            throw new Error('Coordinates are required');
        }
        if (typeof coordinates.x !== 'number' || typeof coordinates.y !== 'number') {
            throw new Error('Invalid coordinates');
        }

        const range = document.caretRangeFromPoint(coordinates.x, coordinates.y);
        if (!range) {
            throw new Error('Could not create range from click point');
        }

        const content = this.getNoteContent(noteElement);
        if (!content) {
            throw new Error('Note missing content element');
        }

        if (!content.contains(range.startContainer)) {
            throw new Error('Click not in note content');
        }

        let offset = 0;
        const path = this.getNodePath(range.startContainer, content);
        if (!path) {
            throw new Error('Could not find path to clicked node');
        }

        const textRange = document.createRange();
        textRange.selectNodeContents(content);
        textRange.setEnd(range.startContainer, range.startOffset);
        const selectedText = textRange.toString();
        offset = selectedText.length;

        console.log("[DEBUG] Range-based offset:", offset);
        console.log("[DEBUG] Clicked node:", range.startContainer.nodeName);

        return offset;
    },

    getNoteContentHTML(noteElement) {
        if (!noteElement) {
            throw new Error('Note element is required');
        }
        const contentElement = this.getNoteContent(noteElement);
        if (!contentElement) {
            throw new Error('Note missing content element');
        }
        if (!(contentElement instanceof HTMLElement)) {
            throw new Error('Invalid content element type');
        }
        const html = contentElement.innerHTML;
        if (typeof html !== 'string') {
            throw new Error('Note content must be string');
        }
        return html;
    },

    getNoteContentHTMLById(noteId) {
        const noteElement = this.getNoteById(noteId);
        return this.getNoteContentHTML(noteElement);
    },

    getNodePath(node, ancestor) {
        if (!node || !ancestor) {
            return null;
        }

        const path = [];
        let current = node;

        while (current && current !== ancestor) {
            path.unshift(current);
            current = current.parentNode;
        }

        return current === ancestor ? path : null;
    },

	isNoteContent(element) {
		if (!element) {
			return false;
		}

		const classList = element.classList;
		if (classList && classList.contains(CONFIG.CLASSES.NOTE_CONTENT)) {
			return true;
		}
		return Boolean(element.closest(`.${CONFIG.CLASSES.NOTE_CONTENT}`));
	},

    isInSearchResults(coordinates) {
        if (!coordinates || !coordinates.x || !coordinates.y) {
            throw new Error('Valid coordinates required');
        }

        const searchResults = document.querySelector(`.${CONFIG.CLASSES.SEARCH_RESULTS}`);
        if (!searchResults) {
            throw new Error('Search results panel not found');
        }

        const rect = searchResults.getBoundingClientRect();
        return coordinates.x >= rect.left && 
               coordinates.x <= rect.right &&
               coordinates.y >= rect.top && 
               coordinates.y <= rect.bottom;
    },

    focusSearch() {
        const searchInput = document.querySelector(`.${CONFIG.CLASSES.SEARCH_INPUT}`);
        if (!searchInput) {
            throw new Error('Search input not found');
        }
        searchInput.focus();
    },
};

function findRangeAtOffset(container, targetOffset) {
    const walker = document.createTreeWalker(
        container,
        NodeFilter.SHOW_TEXT,
        null,
        false
    );

    let currentOffset = 0;
    let node = walker.nextNode();

    while (node) {
        const nodeLength = node.length;

        if (currentOffset + nodeLength >= targetOffset) {
            const range = document.createRange();
            range.setStart(node, targetOffset - currentOffset);
            range.collapse(true);
            return range;
        }

        currentOffset += nodeLength;
        node = walker.nextNode();
    }

    const range = document.createRange();
    range.selectNodeContents(container);
    range.collapse(false);
    return range;
}

function ensureEditableContentNode(contentElement) {
    if (!contentElement.firstChild) {
        contentElement.appendChild(document.createTextNode(''));
    }
}
