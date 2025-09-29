import { BaseModal } from './base-modal.js';
import { ModeContextInstance as ModeContext } from '../mode-manager/mode-context.js';

const MEMORY_ENDPOINT = '/api/memory';

export class MemoryModal extends BaseModal {
    constructor() {
        super('memoryModal', 'memory-modal');
        this._searchQuery = '';
        this._abortController = null;
    }

    getInitialModalState() {
        return {
            searchQuery: '',
            isLoading: false,
            error: null,
            currentPayload: null,
            previousNoteId: null
        };
    }

    openWithSearch(searchQuery) {
        this._searchQuery = typeof searchQuery === 'string' ? searchQuery : '';
        this.open();
    }

    onOpen() {
        document.body.classList.add('memory-modal-open');
        this.renderShell();
        this.updateModalState({
            searchQuery: this._searchQuery,
            isLoading: true,
            error: null,
            currentPayload: null,
            previousNoteId: null
        });
        this.fetchNextNote();
    }

    onClose() {
        document.body.classList.remove('memory-modal-open');
        if (this._abortController) {
            this._abortController.abort();
            this._abortController = null;
        }
        this._searchQuery = '';
        this.updateModalState({
            isLoading: false,
            error: null,
            currentPayload: null,
            previousNoteId: null
        });
        const container = this._getModalElement();
        if (container) {
            const noteTarget = container.querySelector('#memory-modal-note');
            if (noteTarget) {
                noteTarget.innerHTML = '';
            }
        }
    }

    shouldCloseOnClickOutside() {
        return true;
    }

    renderShell() {
        const modalElement = this._getModalElement();
        if (!modalElement) {
            throw new Error('Memory modal element not found');
        }

        modalElement.innerHTML = `
            <div class="modal-content memory-modal">
                <button class="close memory-modal-close" aria-label="Close memory mode">&times;</button>
                <div class="memory-modal-controls">
                    <button class="memory-btn memory-btn-less" data-outcome="-1">Less Often</button>
                    <button class="memory-btn memory-btn-same" data-outcome="0">Same</button>
                    <button class="memory-btn memory-btn-more" data-outcome="1">More Often</button>
                </div>
                <section class="memory-modal-note" id="memory-modal-note">
                    <div class="memory-modal-placeholder">Fetching note…</div>
                </section>
                <footer class="memory-modal-footer">
                    <span id="memory-modal-ratio">Ratio: --%</span>
                    <span id="memory-modal-counts">Pos: -- | Neg: --</span>
                    <span id="memory-modal-probability">Prob: --%</span>
                </footer>
            </div>
        `;

        const closeButton = modalElement.querySelector('.memory-modal-close');
        closeButton.addEventListener('click', () => this.close());

        modalElement.querySelectorAll('.memory-btn').forEach(button => {
            button.addEventListener('click', (event) => {
                const target = event.currentTarget;
                const outcome = Number.parseInt(target.getAttribute('data-outcome'), 10);
                this.handleFeedback(outcome);
            });
        });

        const noteArea = modalElement.querySelector('.memory-modal-note');
        if (noteArea) {
            ['click', 'mousedown', 'mouseup', 'keydown', 'keyup'].forEach(eventName => {
                noteArea.addEventListener(eventName, (event) => {
                    event.stopPropagation();
                });
            });
        }
    }

    async fetchNextNote(feedback = null) {
        const state = this.getModalState();
        const body = {
            searchQuery: state.searchQuery
        };

        if (state.previousNoteId) {
            body.previousNoteId = state.previousNoteId;
        }

        if (feedback !== null && feedback !== undefined) {
            body.feedback = feedback;
        }

        if (this._abortController) {
            this._abortController.abort();
        }
        this._abortController = new AbortController();

        this.updateModalState({ isLoading: true, error: null });
        this.renderLoading();
        this.setButtonsDisabled(true);

        try {
            const response = await fetch(MEMORY_ENDPOINT, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(body),
                signal: this._abortController.signal
            });

            if (!response.ok) {
                if (response.status === 404) {
                    throw new Error('No notes available for the current view. Refine your search or add notes.');
                }
                const errorPayload = await response.json().catch(() => ({}));
                const detail = errorPayload?.detail || response.statusText;
                throw new Error(`Memory request failed: ${detail}`);
            }

            const payload = await response.json();
            this.updateModalState({
                isLoading: false,
                currentPayload: payload,
                previousNoteId: payload.noteId,
                error: null
            });
            this.renderPayload(payload);
            this.setButtonsDisabled(false);
        } catch (error) {
            if (error.name === 'AbortError') {
                return;
            }
            console.error('Memory modal fetch failed', error);
            this.updateModalState({ isLoading: false, error: error.message });
            this.renderError(error.message);
            this.setButtonsDisabled(false);
        } finally {
            this._abortController = null;
        }
    }

    handleFeedback(outcome) {
        if (typeof outcome !== 'number' || !Number.isInteger(outcome)) {
            throw new Error(`Invalid feedback outcome: ${outcome}`);
        }
        if (outcome < -1 || outcome > 1) {
            throw new Error(`Feedback outcome out of range: ${outcome}`);
        }

        const state = this.getModalState();
        if (state.isLoading) {
            return;
        }

        this.fetchNextNote(outcome);
    }

    renderLoading() {
        const modalElement = this._getModalElement();
        if (!modalElement) {
            return;
        }
        const noteTarget = modalElement.querySelector('#memory-modal-note');
        if (noteTarget) {
            noteTarget.innerHTML = '<div class="memory-modal-placeholder">Fetching note…</div>';
        }
        const ratio = modalElement.querySelector('#memory-modal-ratio');
        if (ratio) {
            ratio.textContent = 'Loading…';
        }
        const counts = modalElement.querySelector('#memory-modal-counts');
        if (counts) {
            counts.textContent = '';
        }
        const prob = modalElement.querySelector('#memory-modal-probability');
        if (prob) {
            prob.textContent = '';
        }
    }

    renderError(message) {
        const modalElement = this._getModalElement();
        if (!modalElement) {
            return;
        }
        const noteTarget = modalElement.querySelector('#memory-modal-note');
        if (noteTarget) {
            noteTarget.innerHTML = `<div class="memory-modal-error">${message}</div>`;
        }
    }

    renderPayload(payload) {
        const modalElement = this._getModalElement();
        if (!modalElement) {
            return;
        }
        const noteTarget = modalElement.querySelector('#memory-modal-note');
        if (noteTarget) {
            noteTarget.innerHTML = `<div class="memory-note-wrapper">${payload.html}</div>`;
            const highlighted = noteTarget.querySelector('.memory-selected');
            if (highlighted) {
                highlighted.scrollIntoView({ block: 'start', behavior: 'smooth' });
            } else {
                noteTarget.scrollTop = 0;
            }
        }

        const ratioEl = modalElement.querySelector('#memory-modal-ratio');
        if (ratioEl) {
            const ratioPercent = (payload.stats.ratio * 100).toFixed(1);
            ratioEl.textContent = `Ratio: ${ratioPercent}%`;
        }

        const counts = modalElement.querySelector('#memory-modal-counts');
        if (counts) {
            counts.textContent = `Pos: ${payload.stats.positive.toFixed(0)} | Neg: ${payload.stats.negative.toFixed(0)}`;
        }

        const prob = modalElement.querySelector('#memory-modal-probability');
        if (prob) {
            const probability = (payload.probability * 100).toFixed(1);
            prob.textContent = `Prob: ${probability}%`;
        }
    }

    setButtonsDisabled(disabled) {
        const modalElement = this._getModalElement();
        if (!modalElement) {
            return;
        }
        modalElement.querySelectorAll('.memory-btn').forEach(button => {
            button.disabled = disabled;
        });
    }

    _getModalElement() {
        return document.getElementById(this.modalElementId);
    }
}
