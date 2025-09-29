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
                category: 'Navigation & Modes',
                items: [
                    { keys: 'Esc', description: 'Exit search or editing mode' },
                    { keys: `${modKey}+/`, description: 'Activate search mode' },
                    { keys: '?', description: 'Show this help dialog' }
                ]
            },
            {
                category: 'Note Creation',
                items: [
                    { keys: 'Enter', description: 'Create new note (in idle mode)' },
                    { keys: `${modKey}+Enter`, description: 'Create sibling note' },
                    { keys: `${modKey}+Shift+Enter`, description: 'Create child note' }
                ]
            },
            {
                category: 'Note Editing',
                items: [
                    { keys: 'Click note', description: 'Edit note' },
                    { keys: `${modKey}+Backspace`, description: 'Delete current note' },
                    { keys: `${modKey}+Delete`, description: 'Delete current note' },
                    { keys: 'Backspace/Delete', description: 'Delete hovered note (when idle)' }
                ]
            },
            {
                category: 'Note Movement',
                items: [
                    { keys: `${modKey}+↑`, description: 'Move current note up' },
                    { keys: `${modKey}+↓`, description: 'Move current note down' },
                    { keys: '↑', description: 'Move hovered note up (when idle)' },
                    { keys: '↓', description: 'Move hovered note down (when idle)' }
                ]
            },
            {
                category: 'Collapse/Expand',
                items: [
                    { keys: 'Space', description: 'Toggle collapse/expand hovered note' }
                ]
            },
            {
                category: 'Copy/Paste',
                items: [
                    { keys: `${modKey}+C`, description: 'Copy current note (in edit mode)' },
                    { keys: `${modKey}+V`, description: 'Paste note as sibling' },
                    { keys: `${modKey}+Shift+V`, description: 'Paste note as child' }
                ]
            },
            {
                category: 'Undo/Redo',
                items: [
                    { keys: `${modKey}+Z`, description: 'Undo last action' },
                    { keys: `${modKey}+Shift+Z`, description: 'Redo action' },
                    { keys: `${modKey}+Y`, description: 'Redo action' }
                ]
            },
            {
                category: 'Special Modals',
                items: [
                    { keys: `${modKey}+P`, description: 'Open password management' },
                    { keys: 'M', description: 'Open memory/search contexts (when idle)' }
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