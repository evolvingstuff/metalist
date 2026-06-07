import { SoundsAPI } from '../api-client.js';
import { DEFAULT_SOUND_ID, SoundService } from '../sound-service.js';
import { BaseModal } from './base-modal.js';

function escapeHtml(value) {
    if (typeof value !== 'string') {
        return '';
    }
    return value
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function formatBytes(value) {
    if (!Number.isInteger(value) || value < 0) {
        throw new Error('formatBytes requires non-negative integer');
    }
    if (value < 1024) {
        return `${value} B`;
    }
    const kib = value / 1024;
    if (kib < 1024) {
        return `${kib.toFixed(1)} KB`;
    }
    return `${(kib / 1024).toFixed(1)} MB`;
}

function formatDuration(value) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
        throw new Error('formatDuration requires duration number');
    }
    return `${value.toFixed(1)}s`;
}

export class SoundManagerModal extends BaseModal {
    constructor() {
        super('soundManagerModal', 'sound-manager-modal');
        this._state = {
            loading: true,
            saving: false,
            title: '',
            file: null,
            library: null,
            error: '',
            status: '',
        };
        this._handleClick = this._handleClick.bind(this);
        this._handleInput = this._handleInput.bind(this);
    }

    open() {
        let modalElement = document.getElementById(this.modalElementId);
        if (!(modalElement instanceof HTMLElement)) {
            modalElement = document.createElement('div');
            modalElement.id = this.modalElementId;
            modalElement.className = 'modal sound-manager-modal';
            modalElement.style.display = 'none';
            document.body.appendChild(modalElement);
        }
        super.open();
    }

    onOpen() {
        const modalElement = this._modalElement();
        modalElement.addEventListener('click', this._handleClick);
        modalElement.addEventListener('input', this._handleInput);
        modalElement.addEventListener('change', this._handleInput);
        this._render();
        void this._load();
    }

    onClose() {
        const modalElement = this._modalElement();
        modalElement.removeEventListener('click', this._handleClick);
        modalElement.removeEventListener('input', this._handleInput);
        modalElement.removeEventListener('change', this._handleInput);
    }

    _modalElement() {
        const modalElement = document.getElementById(this.modalElementId);
        if (!(modalElement instanceof HTMLElement)) {
            throw new Error('Sound manager modal element missing');
        }
        return modalElement;
    }

    async _load() {
        this._state.loading = true;
        this._state.error = '';
        this._render();
        this._state.library = await SoundService.refreshLibrary();
        this._state.loading = false;
        this._render();
    }

    _render() {
        const modalElement = this._modalElement();
        const library = this._state.library;
        const usage = library ? library.usage : null;
        const sounds = library ? library.sounds : [];
        modalElement.innerHTML = `
            <div class="modal-content sound-manager-modal-content">
                <div class="sound-manager-header">
                    <h3>Sounds</h3>
                    <button type="button" class="secondary-btn" data-sound-manager-close>Close</button>
                </div>
                <div class="sound-manager-usage">
                    ${usage ? `
                        <span>${escapeHtml(formatBytes(usage.uploaded_bytes))} of ${escapeHtml(formatBytes(usage.max_uploaded_bytes))} used</span>
                        <span>Max ${escapeHtml(formatBytes(usage.max_sound_bytes))} / ${escapeHtml(formatDuration(usage.max_duration_seconds))} each</span>
                    ` : '<span>Loading usage...</span>'}
                </div>
                <div class="sound-manager-layout">
                    <section class="sound-manager-list">
                        ${this._state.loading ? '<p class="sound-manager-empty">Loading...</p>' : ''}
                        ${!this._state.loading && sounds.length === 0 ? '<p class="sound-manager-empty">No sounds</p>' : ''}
                        ${sounds.map((sound) => this._renderSoundRow(sound)).join('')}
                    </section>
                    <section class="sound-manager-upload">
                        <h4>Upload sound</h4>
                        <label class="sound-manager-field">
                            <span>Title</span>
                            <input id="sound-upload-title" type="text" value="${escapeHtml(this._state.title)}">
                        </label>
                        <label class="sound-manager-field">
                            <span>Audio file</span>
                            <input id="sound-upload-file" type="file" accept="audio/*">
                        </label>
                        <button type="button" class="primary-btn" data-sound-upload ${this._state.saving ? 'disabled' : ''}>Upload</button>
                        <p class="sound-manager-status">${escapeHtml(this._state.status)}</p>
                        <p class="sound-manager-error">${escapeHtml(this._state.error)}</p>
                    </section>
                </div>
            </div>
        `;
    }

    _renderSoundRow(sound) {
        if (!sound || typeof sound !== 'object') {
            throw new Error('_renderSoundRow requires sound');
        }
        let isBuiltin = false;
        if (sound.id === DEFAULT_SOUND_ID) {
            isBuiltin = true;
        } else if (sound.is_builtin === true) {
            isBuiltin = true;
        }
        return `
            <article class="sound-manager-row" data-sound-id="${escapeHtml(sound.id)}">
                <div class="sound-manager-row-main">
                    <input class="sound-manager-title-input" type="text" value="${escapeHtml(sound.title)}" ${isBuiltin ? 'disabled' : ''} data-sound-title-input>
                    <span>${escapeHtml(formatBytes(sound.size_bytes))} · ${escapeHtml(formatDuration(sound.duration_seconds))}</span>
                </div>
                <div class="sound-manager-actions">
                    <button type="button" data-sound-preview>Preview</button>
                    ${isBuiltin ? '' : '<button type="button" data-sound-rename>Rename</button>'}
                    ${isBuiltin ? '' : '<button type="button" data-sound-delete>Delete</button>'}
                </div>
            </article>
        `;
    }

    _handleInput(event) {
        const target = event.target;
        if (!(target instanceof HTMLInputElement)) {
            return;
        }
        if (target.id === 'sound-upload-title') {
            this._state.title = target.value;
            return;
        }
        if (target.id === 'sound-upload-file') {
            const files = target.files;
            if (!(files instanceof FileList) || files.length === 0) {
                this._state.file = null;
                return;
            }
            this._state.file = files[0];
        }
    }

    async _handleClick(event) {
        const target = event.target;
        if (!(target instanceof HTMLElement)) {
            return;
        }
        if (target.closest('[data-sound-manager-close]')) {
            this.close();
            return;
        }
        if (target.closest('[data-sound-upload]')) {
            await this._upload();
            return;
        }
        const row = target.closest('[data-sound-id]');
        if (!(row instanceof HTMLElement)) {
            return;
        }
        const soundId = row.getAttribute('data-sound-id');
        if (typeof soundId !== 'string' || soundId.length === 0) {
            throw new Error('Sound row missing id');
        }
        if (target.closest('[data-sound-preview]')) {
            await this._preview(soundId);
            return;
        }
        if (target.closest('[data-sound-rename]')) {
            const input = row.querySelector('[data-sound-title-input]');
            if (!(input instanceof HTMLInputElement)) {
                throw new Error('Sound rename input missing');
            }
            await this._rename(soundId, input.value);
            return;
        }
        if (target.closest('[data-sound-delete]')) {
            await this._delete(soundId);
        }
    }

    async _preview(soundId) {
        const result = await SoundService.playSound(soundId);
        if (result.status === 'played') {
            this._state.status = 'Preview playing';
        } else {
            this._state.status = `Preview failed: ${result.message}`;
        }
        this._state.error = '';
        this._render();
    }

    async _upload() {
        if (this._state.saving) {
            return;
        }
        if (!(this._state.file instanceof File)) {
            this._state.error = 'Choose an audio file first';
            this._render();
            return;
        }
        this._state.saving = true;
        this._state.error = '';
        this._state.status = '';
        this._render();
        await SoundsAPI.uploadSound({
            title: this._state.title,
            file: this._state.file,
        }).finally(() => {
            this._state.saving = false;
        });
        this._state.title = '';
        this._state.file = null;
        this._state.status = 'Sound uploaded';
        await this._load();
        this._render();
    }

    async _rename(soundId, title) {
        this._state.error = '';
        await SoundsAPI.updateSound(soundId, { title });
        this._state.status = 'Sound renamed';
        await this._load();
    }

    async _delete(soundId) {
        this._state.error = '';
        await SoundsAPI.deleteSound(soundId);
        this._state.status = 'Sound deleted';
        await this._load();
    }
}
