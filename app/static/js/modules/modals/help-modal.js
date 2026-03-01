/**
 * HelpModal - Display keyboard shortcuts and commands
 *
 * Shows comprehensive list of all available keyboard shortcuts
 * Triggered by pressing '?' in idle mode
 */

import { BaseModal } from './base-modal.js';
import { ModeContextInstance as ModeContext } from '../mode-manager/mode-context.js';

export class HelpModal extends BaseModal {
    constructor() {
        super('help', 'help-modal');
    }

    /**
     * Create and show the modal element with shortcuts list
     */
    showModalElement() {
        let modalElement = document.getElementById(this.modalElementId);

        // Create modal element if it doesn't exist
        if (!modalElement) {
            modalElement = document.createElement('div');
            modalElement.id = this.modalElementId;
            modalElement.className = 'modal';
            modalElement.style.display = 'none';
            document.body.appendChild(modalElement);
        }

        // Build the shortcuts content
        const shortcutsHTML = this.buildShortcutsHTML();

        modalElement.innerHTML = `
            <div class="modal-content help-modal-content">
                <span class="close">&times;</span>
                <h2>Keyboard Shortcuts</h2>
                <div class="help-shortcuts-container">
                    ${shortcutsHTML}
                </div>
            </div>
        `;

        // Add close button handler
        const closeBtn = modalElement.querySelector('.close');
        if (closeBtn) {
            closeBtn.onclick = () => this.close();
        }

        modalElement.style.display = 'block';
    }

    /**
     * Build HTML for shortcuts list organized by category
     */
    buildShortcutsHTML() {
        const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
        const modKey = isMac ? '⌘' : 'Ctrl';

        const shortcuts = [
            {
                category: 'Global',
                items: [
                    { keys: `${modKey}+/`, description: 'Open command palette' },
                    { keys: '?', description: 'Show this help dialog (idle mode)' },
                    { keys: 'Esc', description: 'Exit search/edit mode or close top modal' }
                ]
            },
            {
                category: 'When Editing',
                items: [
                    { keys: 'Tab', description: 'Toggle focus between note content and tag bar' },
                    { keys: `${modKey}+Enter`, description: 'Create sibling note' },
                    { keys: `${modKey}+Shift+Enter`, description: 'Create child note' },
                    { keys: `${modKey}+←`, description: 'Outdent note one level' },
                    { keys: `${modKey}+→`, description: 'Indent note one level' },
                    { keys: `${modKey}+C`, description: 'Copy selection (or whole note if no selection)' },
                    { keys: `${modKey}+X`, description: 'Cut selection (or whole note if no selection)' },
                    { keys: `${modKey}+V`, description: 'Paste note as sibling in note-clipboard mode' },
                    { keys: `${modKey}+Shift+V`, description: 'Paste note as child in note-clipboard mode' },
                    { keys: `${modKey}+R`, description: 'Copy as embedded reference from last copied note' },
                    { keys: `${modKey}+S`, description: 'Split note at selection/caret' },
                    { keys: `${modKey}+J`, description: 'Join note with next sibling' },
                    { keys: `${modKey}+P`, description: 'Save/exit edit mode, then open password modal' },
                    { keys: `${modKey}+Backspace`, description: 'Delete selected note' },
                    { keys: `${modKey}+Delete`, description: 'Delete selected note' }
                ]
            },
            {
                category: 'Navigation & Structure',
                items: [
                    { keys: 'Enter', description: 'Create new root note (idle, or when search input is focused)' },
                    { keys: 'Space', description: 'Toggle collapse/expand hovered note' },
                    { keys: 'Backspace/Delete', description: 'Delete hovered note (idle mode)' },
                    { keys: `${modKey}+↑`, description: 'Move selected note up' },
                    { keys: `${modKey}+↓`, description: 'Move selected note down' }
                ]
            },
            {
                category: 'Undo / Redo',
                items: [
                    { keys: `${modKey}+Z`, description: 'Undo' },
                    { keys: `${modKey}+Shift+Z`, description: 'Redo' },
                    { keys: `${modKey}+Y`, description: 'Redo' }
                ]
            },
            {
                category: 'Modals & Tools',
                items: [
                    { keys: `${modKey}+;`, description: 'Edit tag relationships' },
                    { keys: 'M', description: 'Open memory/search contexts (idle mode)' }
                ]
            }
        ];

        return shortcuts.map(section => `
            <div class="help-section">
                <h3 class="help-category">${section.category}</h3>
                <div class="help-shortcuts">
                    ${section.items.map(item => `
                        <div class="help-shortcut-row">
                            <span class="help-keys">${item.keys}</span>
                            <span class="help-description">${item.description}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `).join('');
    }

    /**
     * Override to prevent click outside from closing
     * (users may want to reference this while using the app)
     */
    shouldCloseOnClickOutside() {
        return true;
    }
}
