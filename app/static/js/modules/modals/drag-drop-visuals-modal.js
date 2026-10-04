import { ApplicationState } from '../application-state.js';
import { BaseModal } from './base-modal.js';

// One window for every drag-and-drop visual. Each checkbox saves and applies
// as soon as it changes (the window closes like the others, with Escape or an
// outside click); dragging itself works the same either way.
export const DRAG_DROP_VISUAL_OPTIONS = [
    {
        key: 'pref.drag_ghost',
        label: 'Drag ghost',
        description: 'A dashed outline of the note and its visible children follows the pointer.',
    },
    {
        key: 'pref.drop_indicator',
        label: 'Drop indicator',
        description: 'A grey line shows where the note will land, with a faint outline on the note beside or above it.',
    },
    {
        key: 'pref.drag_direction_icon',
        label: 'Direction cursor',
        description: 'The cursor becomes an up, down, indent or outdent icon for the move a release would make.',
    },
];

function checkboxId(key) {
    return `drag-drop-visuals-${key.replace('pref.', '').replaceAll('_', '-')}`;
}

export class DragDropVisualsModal extends BaseModal {
    constructor(readSettings, saveSetting) {
        super('dragDropVisualsModal', 'drag-drop-visuals-modal');
        if (typeof readSettings !== 'function') {
            throw new Error('DragDropVisualsModal requires readSettings');
        }
        if (typeof saveSetting !== 'function') {
            throw new Error('DragDropVisualsModal requires saveSetting');
        }
        this._readSettings = readSettings;
        this._saveSetting = saveSetting;

        ApplicationState.own(this, 'DragDropVisualsModal', new.target === DragDropVisualsModal);
    }

    getInitialModalState() {
        return { settings: this._validatedSettings(this._readSettings()), saving: false };
    }

    _validatedSettings(settings) {
        if (!settings || typeof settings !== 'object') {
            throw new Error('Drag & drop visual settings must be an object');
        }
        const validated = {};
        for (const option of DRAG_DROP_VISUAL_OPTIONS) {
            if (typeof settings[option.key] !== 'boolean') {
                throw new Error(`Drag & drop visual setting ${option.key} must be boolean`);
            }
            validated[option.key] = settings[option.key];
        }
        return validated;
    }

    showModalElement() {
        let modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            modalElement = document.createElement('div');
            modalElement.id = this.modalElementId;
            modalElement.className = 'modal';
            modalElement.style.display = 'none';
            document.body.appendChild(modalElement);
        }
        this.renderModalContent();
        modalElement.style.display = 'block';
        const firstCheckbox = document.getElementById(checkboxId(DRAG_DROP_VISUAL_OPTIONS[0].key));
        if (firstCheckbox instanceof HTMLInputElement) {
            firstCheckbox.focus();
        }
    }

    renderModalContent() {
        const modalElement = document.getElementById(this.modalElementId);
        if (!modalElement) {
            throw new Error(`Modal element missing: ${this.modalElementId}`);
        }
        const state = this.getModalState();
        const settings = this._validatedSettings(state.settings);
        const disabled = state.saving === true ? ' disabled' : '';
        const rows = DRAG_DROP_VISUAL_OPTIONS.map((option) => `
                    <label class="drag-drop-visuals-toggle">
                        <input type="checkbox" id="${checkboxId(option.key)}"${settings[option.key] ? ' checked' : ''}${disabled}>
                        <span class="drag-drop-visuals-text">
                            <span class="drag-drop-visuals-title">${option.label}</span>
                            <span class="drag-drop-visuals-description">${option.description}</span>
                        </span>
                    </label>`).join('');

        modalElement.innerHTML = `
            <div class="modal-content drag-drop-visuals-modal-content">
                <h2>Drag &amp; Drop Visuals</h2>
                <p class="note-layout-description">Choose what appears while you drag notes to reorder, indent or outdent them. Changes apply immediately.</p>
                <div class="drag-drop-visuals-controls">${rows}
                </div>
            </div>
        `;
        this._setupEventListeners();
    }

    _setupEventListeners() {
        for (const option of DRAG_DROP_VISUAL_OPTIONS) {
            const checkbox = document.getElementById(checkboxId(option.key));
            if (!(checkbox instanceof HTMLInputElement)) {
                throw new Error(`Drag & drop visuals checkbox missing: ${option.key}`);
            }
            checkbox.onchange = async () => this._handleToggle(option.key, checkbox.checked);
        }
    }

    async _handleToggle(key, enabled) {
        this.updateModalState({ saving: true });
        this.renderModalContent();
        await this._saveSetting(key, enabled);
        this.updateModalState({ settings: this._validatedSettings(this._readSettings()), saving: false });
        this.renderModalContent();
        const checkbox = document.getElementById(checkboxId(key));
        if (checkbox instanceof HTMLInputElement) {
            checkbox.focus();
        }
    }
}
