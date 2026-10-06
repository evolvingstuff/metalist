import { ApplicationState } from '../application-state.js';
import { BaseModal } from './base-modal.js';

// One window for MetaList's visual cues: drag-and-drop feedback. Each checkbox saves and applies as soon as it
// changes (the window closes like the others, with Escape or an outside click).
// They only change what is shown; dragging works the same either way.
export const VISUAL_CUE_SECTIONS = [
    {
        title: 'Drag and drop',
        options: [
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
        ],
    },
];

export const VISUAL_CUE_OPTIONS = VISUAL_CUE_SECTIONS.flatMap((section) => section.options);

function checkboxId(key) {
    return `visual-cues-${key.replace('pref.', '').replaceAll('_', '-')}`;
}

export class VisualCuesModal extends BaseModal {
    constructor(readSettings, saveSetting) {
        super('visualCuesModal', 'visual-cues-modal');
        if (typeof readSettings !== 'function') {
            throw new Error('VisualCuesModal requires readSettings');
        }
        if (typeof saveSetting !== 'function') {
            throw new Error('VisualCuesModal requires saveSetting');
        }
        this._readSettings = readSettings;
        this._saveSetting = saveSetting;

        ApplicationState.own(this, 'VisualCuesModal', new.target === VisualCuesModal);
    }

    getInitialModalState() {
        return { settings: this._validatedSettings(this._readSettings()), saving: false };
    }

    _validatedSettings(settings) {
        if (!settings || typeof settings !== 'object') {
            throw new Error('Visual cue settings must be an object');
        }
        const validated = {};
        for (const option of VISUAL_CUE_OPTIONS) {
            if (typeof settings[option.key] !== 'boolean') {
                throw new Error(`Visual cue setting ${option.key} must be boolean`);
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
        const firstCheckbox = document.getElementById(checkboxId(VISUAL_CUE_OPTIONS[0].key));
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
        const sections = VISUAL_CUE_SECTIONS.map((section) => `
                <section class="visual-cues-section">
                    <h3 class="visual-cues-section-title">${section.title}</h3>${section.options.map((option) => `
                    <label class="visual-cues-toggle">
                        <input type="checkbox" id="${checkboxId(option.key)}"${settings[option.key] ? ' checked' : ''}${disabled}>
                        <span class="visual-cues-text">
                            <span class="visual-cues-title">${option.label}</span>
                            <span class="visual-cues-description">${option.description}</span>
                        </span>
                    </label>`).join('')}
                </section>`).join('');

        modalElement.innerHTML = `
            <div class="modal-content visual-cues-modal-content">
                <h2>Visual Cues</h2>
                <p class="note-layout-description">Choose the visual feedback shown while you drag notes and after you leave edit mode. Changes apply immediately.</p>
                <div class="visual-cues-controls">${sections}
                </div>
            </div>
        `;
        this._setupEventListeners();
    }

    _setupEventListeners() {
        for (const option of VISUAL_CUE_OPTIONS) {
            const checkbox = document.getElementById(checkboxId(option.key));
            if (!(checkbox instanceof HTMLInputElement)) {
                throw new Error(`Visual cue checkbox missing: ${option.key}`);
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
