import { BaseModal } from './base-modal.js';
import { ModeContextInstance as ModeContext } from '../mode-manager/mode-context.js';
import { CONFIG } from '../config.js';
import { buildSessionHeaders } from '../session-auth.js';

const MEMORY_ENDPOINT = `${CONFIG.API.MEMORY.BASE}`;

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
                <div class="memory-modal-controls">
                    <button class="memory-btn memory-btn-less" data-outcome="-1">Less Often</button>
                    <button class="memory-btn memory-btn-same" data-outcome="0">Same</button>
                    <button class="memory-btn memory-btn-more" data-outcome="1">More Often</button>
                </div>
                <section class="memory-modal-note" id="memory-modal-note">
                    <div class="memory-modal-placeholder">Fetching note…</div>
                </section>
                <footer class="memory-modal-footer">
                    <span id="memory-modal-counts">Less: -- | More: --</span>
                    <span id="memory-modal-probability">Prob: --%</span>
                </footer>
            </div>
        `;

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

	async fetchNextNote(feedback) {
		if (typeof feedback === 'undefined') {
			feedback = null;
		}
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
		const controller = new AbortController();
		this._abortController = controller;

        this.updateModalState({ isLoading: true, error: null });
        this.renderLoading();
        this.setButtonsDisabled(true);

		await (async () => {
			const response = await fetch(MEMORY_ENDPOINT, {
				method: 'POST',
				headers: buildSessionHeaders(true),
				body: JSON.stringify(body),
				signal: controller.signal
			}).catch((error) => {
				if (error && error.name === 'AbortError') {
					return null;
				}
				throw error;
			});

			if (response === null) {
				return;
			}

			if (!response.ok) {
				if (response.status === 404) {
					throw new Error('No notes available for the current view. Refine your search or add notes.');
				}
				const errorPayload = await response.json().catch(() => null);
				let detail = null;
				if (errorPayload && typeof errorPayload.detail === 'string') {
					detail = errorPayload.detail;
				} else {
					detail = response.statusText;
				}
				throw new Error(`Memory request failed: ${detail}`);
			}

			const payload = await response.json();
			if (this._abortController !== controller) {
				return;
			}
			this.updateModalState({
				isLoading: false,
				currentPayload: payload,
				previousNoteId: payload.noteId,
				error: null
			});
			this.renderPayload(payload);
			this.setButtonsDisabled(false);
		})().catch((error) => {
			if (this._abortController !== controller) {
				return;
			}
			console.error('Memory modal fetch failed', error);
			this.updateModalState({ isLoading: false, error: error.message });
			this.renderError(error.message);
			this.setButtonsDisabled(false);
		}).finally(() => {
			if (this._abortController === controller) {
				this._abortController = null;
			}
		});
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
        const counts = modalElement.querySelector('#memory-modal-counts');
        if (counts) {
            counts.textContent = 'Less: -- | More: --';
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

        const counts = modalElement.querySelector('#memory-modal-counts');
        if (counts) {
            counts.textContent = `Less: ${payload.stats.negative.toFixed(0)} | More: ${payload.stats.positive.toFixed(0)}`;
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
