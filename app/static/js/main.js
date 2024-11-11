import { setupKeyboardShortcuts } from './shortcuts.js';

document.addEventListener('DOMContentLoaded', () => {
    let currentEditingNote = null;
    let initialContent = null;
    let lastSavedContent = null;

    // Set initial state of all notes to non-editable
    document.querySelectorAll('.note-content').forEach(content => {
        content.contentEditable = 'false';
    });

    async function saveNoteContent(noteElement, content) {
        const noteId = noteElement.closest('.note').dataset.id;
        console.log('Saving note:', noteId, content);
        
        try {
            const response = await fetch(`/api/notes/${noteId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ content })
            });
            
            if (response.ok) {
                lastSavedContent = content;
                console.log('Save successful');
            }
        } catch (error) {
            console.error('Error saving note:', error);
        }
    }

    function makeNoteEditable(noteElement) {
        const contentDiv = noteElement.querySelector('.note-content');
        
        // If switching notes, save the current one first
        if (currentEditingNote && currentEditingNote !== noteElement) {
            const currentContent = currentEditingNote.querySelector('.note-content').textContent;
            if (currentContent !== lastSavedContent) {
                console.log('Saving previous note before switching');
                saveNoteContent(currentEditingNote, currentContent);
            }
            currentEditingNote.querySelector('.note-content').contentEditable = 'false';
            currentEditingNote.classList.remove('editing');
        }

        // Start editing new note
        contentDiv.contentEditable = 'true';
        noteElement.classList.add('editing');
        contentDiv.focus();
        currentEditingNote = noteElement;
        initialContent = contentDiv.textContent;
        lastSavedContent = initialContent;
        console.log('Started editing note, initial content:', initialContent);
    }

    // Handle clicking on notes
    document.addEventListener('click', (e) => {
        const noteElement = e.target.closest('.note');
        
        // If clicking inside a note's content
        if (noteElement && e.target.classList.contains('note-content')) {
            makeNoteEditable(noteElement);
        } 
        // If clicking outside any note
        else if (!noteElement && currentEditingNote) {
            const contentDiv = currentEditingNote.querySelector('.note-content');
            const finalContent = contentDiv.textContent;
            
            if (finalContent !== lastSavedContent) {
                console.log('Saving note before exit');
                saveNoteContent(currentEditingNote, finalContent);
            }
            
            contentDiv.contentEditable = 'false';
            currentEditingNote.classList.remove('editing');
            currentEditingNote = null;
            initialContent = null;
            lastSavedContent = null;
        }
    });

    // Polling for changes while editing
    setInterval(() => {
        if (currentEditingNote) {
            const currentContent = currentEditingNote.querySelector('.note-content').textContent;
            if (currentContent !== lastSavedContent) {
                console.log('Poll detected change, saving');
                saveNoteContent(currentEditingNote, currentContent);
            }
        }
    }, 2000);

    // Add note button handler
    document.getElementById('add-note-btn').addEventListener('click', async () => {
        const response = await fetch('/api/notes/new', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ content: '' })
        });
        
        if (response.ok) {
            window.location.reload();
        }
    });

    function stopEditing() {
        if (currentEditingNote) {
            const contentDiv = currentEditingNote.querySelector('.note-content');
            const finalContent = contentDiv.textContent;
            
            if (finalContent !== lastSavedContent) {
                console.log('Saving note before exit');
                saveNoteContent(currentEditingNote, finalContent);
            }
            
            contentDiv.contentEditable = 'false';
            currentEditingNote.classList.remove('editing');
            currentEditingNote = null;
            initialContent = null;
            lastSavedContent = null;
        }
    }

    // Setup keyboard shortcuts
    setupKeyboardShortcuts({
        stopEditing: stopEditing
        // Ready for more handlers
    });
}); 