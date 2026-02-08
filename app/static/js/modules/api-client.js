import { CONFIG } from './config.js';
import { DOMUtils } from './dom-utils.js';
import { ModeContextInstance as ModeContext } from './mode-manager/mode-context.js';
import { ErrorHandler } from './error-handler.js';
import { computeScrollAnchor } from './mode-manager/services/scroll-anchor-service.js';

function captureViewportSnapshot() {
    return {
        scrollY: Math.max(0, Math.round(window.scrollY)),
        scrollAnchor: computeScrollAnchor({ anchorBias: 'auto' }),
    };
}

function captureUndoContext() {
    const tabId = ModeContext.activeTabId;
    if (typeof tabId !== 'string' || tabId.length === 0) {
        throw new Error('ModeContext.activeTabId must be a non-empty string');
    }

    const epoch = ModeContext.undoContextEpoch;
    if (!Number.isInteger(epoch) || epoch < 0) {
        throw new Error('ModeContext.undoContextEpoch must be a non-negative integer');
    }

    const searchQuery = ModeContext.searchQuery;
    if (searchQuery !== null && typeof searchQuery !== 'string') {
        throw new Error('ModeContext.searchQuery must be a string or null');
    }

    const normalizedSearch = searchQuery === null ? '' : searchQuery;
    return `tab:${tabId}|search:${normalizedSearch}|epoch:${epoch}`;
}

export const NotesAPI = {
                
    async _apiCall(url, options) {
        if (typeof url !== 'string') {
            throw new Error('NotesAPI._apiCall requires url string');
        }
        if (options === null || typeof options !== 'object') {
            throw new Error('NotesAPI._apiCall requires options object');
        }
        try {
            const claimSession = Boolean(options.claimSession);
            const fetchOptions = { ...options };
            delete fetchOptions.claimSession;

            // Add sync context to request body for non-GET requests
            let requestBody = fetchOptions.body;
            let requestPayload = null;
            if (fetchOptions.method && fetchOptions.method !== 'GET') {
                const syncContext = {
                    clientId: ModeContext.clientId,
                    lastUpdateUUID: ModeContext.lastUpdateUUID,
                    undoContext: captureUndoContext(),
                };

                if (claimSession) {
                    syncContext.viewport = captureViewportSnapshot();
                }
                
                if (requestBody) {
                    // Merge sync context with existing body
                    const existingBody = JSON.parse(requestBody);
                    requestPayload = {
                        ...existingBody,
                        ...syncContext
                    };
                    requestBody = JSON.stringify(requestPayload);
                } else {
                    // Just send sync context
                    requestPayload = syncContext;
                    requestBody = JSON.stringify(syncContext);
                }
            }
                                                
            if (CONFIG.DEBUG.LOG_API_CALLS) {
                const isNotesView = url === CONFIG.API.NOTES.VIEW;
                const bodySummary = isNotesView && requestPayload
                    ? {
                        editingNoteId: requestPayload.editingNoteId,
                        search: requestPayload.search,
                        clientNoteUuidHashesCount: requestPayload.clientNoteUuidHashes && typeof requestPayload.clientNoteUuidHashes === 'object'
                            ? Object.keys(requestPayload.clientNoteUuidHashes).length
                            : 0,
                        lastUpdateUUID: requestPayload.lastUpdateUUID,
                    }
                    : requestPayload;

                console.log(' [API] Request:', {
                    url: url,
                    method: fetchOptions.method || 'GET',
                    body: bodySummary,
                    headers: fetchOptions.headers
                });
            }

            // Add auth token if it exists
            const authToken = localStorage.getItem('auth_token');
            if (CONFIG.DEBUG.LOG_API_CALLS) {
                console.log('[API] Auth token from localStorage:', authToken ? 'EXISTS' : 'NOT FOUND');
            }
            
            const headers = {
                'Content-Type': 'application/json',
                ...fetchOptions.headers
            };

            const tabId = sessionStorage.getItem('metalist_tab_id');
            if (!tabId) {
                throw new Error('metalist_tab_id missing from sessionStorage');
            }
            headers['X-Metalist-Tab-Id'] = tabId;
            if (claimSession) {
                headers['X-Metalist-Claim'] = '1';
            }
            
            if (authToken) {
                headers['Authorization'] = `Bearer ${authToken}`;
                if (CONFIG.DEBUG.LOG_API_CALLS) {
                    console.log('[API] Added Authorization header');
                }
            } else {
                if (CONFIG.DEBUG.LOG_API_CALLS) {
                    console.log('[API] No auth token, no Authorization header added');
                }
            }
            
            if (CONFIG.DEBUG.LOG_API_CALLS) {
                console.log('[API] Final headers:', headers);
            }

            const response = await fetch(url, {
                ...fetchOptions,
                body: requestBody,
                headers: headers
            });

            if (!response.ok) {
                // Use centralized error handling
                ErrorHandler.handleApiError(null, response);
                throw new Error(`API call failed: ${response.status} ${response.statusText}`);
            }

            const data = await response.json();

            if (CONFIG.DEBUG.LOG_API_CALLS) {
                const isNotesView = url === CONFIG.API.NOTES.VIEW;
                const responseSummary = isNotesView && data && typeof data === 'object'
                    ? {
                        updateUUID: data.updateUUID,
                        snapshotStructureCount: Array.isArray(data.snapshot?.structure) ? data.snapshot.structure.length : 0,
                        snapshotNotesCount: data.snapshot?.notes && typeof data.snapshot.notes === 'object'
                            ? Object.keys(data.snapshot.notes).length
                            : 0,
                    }
                    : data;

                console.log(' [API] Response:', {
                    url: url,
                    status: response.status,
                    data: responseSummary
                });
            }
            
            // Extract and store update UUID if present
            if (data && data.updateUUID) {
                ModeContext.setLastUpdateUUID(data.updateUUID);
                if (CONFIG.DEBUG.LOG_API_CALLS) {
                    console.log(' [API] Updated sync UUID:', data.updateUUID);
                }
            }
                                                
            return data;
        } catch (error) {
            console.error(' [API] Error:', error);
            
            // Handle network errors (when fetch throws)
			if (!error.message.includes('API call failed:')) {
				// This is a network/connectivity error, not an HTTP error response
				ErrorHandler.handleApiError(error, null);
			}
            
            throw error;
        }
    },

    async createNote(firstVisibleNoteId, searchQuery) {
        const body = {
            first_visible_note_id: firstVisibleNoteId,
            search_query: searchQuery,
        };

        return this._apiCall(CONFIG.API.NOTES.CREATE, {
            method: 'POST',
            claimSession: true,
            body: JSON.stringify(body)
        });
    },

    async createSibling(noteId, searchQuery) {
        const body = {
            search_query: searchQuery,
        };

        return this._apiCall(CONFIG.API.NOTES.CREATE_SIBLING(noteId), { 
            method: 'POST',
            claimSession: true,
            body: JSON.stringify(body)
        });
    },

    async createChild(noteId, searchQuery) {
        const body = {
            search_query: searchQuery,
        };

        return this._apiCall(CONFIG.API.NOTES.CREATE_CHILD(noteId), { 
            method: 'POST',
            claimSession: true,
            body: JSON.stringify(body)
        });
    },

    async updateNote(noteId, content, tags) {
        return this._apiCall(CONFIG.API.NOTES.UPDATE(noteId), {
            method: 'PUT',
            claimSession: true,
            body: JSON.stringify({ content, tags })
        });
    },

    async saveNote(noteId, content, tags) {
        return this._apiCall(CONFIG.API.NOTES.SAVE(noteId), {
            method: 'PUT',
            claimSession: true,
            body: JSON.stringify({ content, tags })
        }); 
    },

    async toggleTodo(noteId) {
        return this._apiCall(CONFIG.API.NOTES.TOGGLE_TODO(noteId), {
            method: 'POST',
            claimSession: true
        });
    },

    async moveNote(noteId, siblingId, position, newParentId) {
        const body = {
            sibling_id: siblingId,
            position: position?.toUpperCase()
        };
                                
        if (newParentId !== undefined) {
            body.new_parent_id = newParentId;
        }

        return this._apiCall(CONFIG.API.NOTES.MOVE(noteId), {
            method: 'POST',
            claimSession: true,
            body: JSON.stringify(body)
        });
    },

    async moveNoteRelative(noteId, direction) {
        console.log('Moving note:', { noteId, direction });
                                
        const noteElement = DOMUtils.getNoteById(noteId);
        console.log('Note element:', noteElement);
        if (!noteElement) {
            throw new Error('Note element not found');
        }

        const siblingElement = direction === 'before' ? 
            noteElement.previousElementSibling : 
            noteElement.nextElementSibling;
        console.log('Sibling element:', siblingElement);
                                                
        if (!siblingElement) {
            console.log('No sibling found in direction:', direction);
            return;
        }

        const siblingId = DOMUtils.getNoteId(siblingElement);
        console.log('Found sibling:', { siblingId });

        const payload = { 
            position: direction.toUpperCase(),
            sibling_id: siblingId
        };
        console.log('Sending payload:', payload);

        return this._apiCall(CONFIG.API.NOTES.MOVE(noteId), {
            method: 'POST',
            claimSession: true,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
    },

    async deleteNote(noteId) {
        return this._apiCall(CONFIG.API.NOTES.DELETE(noteId), { method: 'DELETE', claimSession: true });
    },

    async collapseNote(noteId) {
        return this._apiCall(CONFIG.API.NOTES.COLLAPSE(noteId), {
            method: 'POST',
            claimSession: true,
        });
    },

    async expandNote(noteId) {
        return this._apiCall(CONFIG.API.NOTES.EXPAND(noteId), {
            method: 'POST',
            claimSession: true,
        });
    },

    async setCollapsedBulk(noteIds, collapsed) {
        if (!Array.isArray(noteIds)) {
            throw new Error('NotesAPI.setCollapsedBulk requires noteIds array');
        }
        for (const noteId of noteIds) {
            if (typeof noteId !== 'string' || noteId.length === 0) {
                throw new Error('NotesAPI.setCollapsedBulk requires noteIds to be non-empty strings');
            }
        }
        if (typeof collapsed !== 'boolean') {
            throw new Error('NotesAPI.setCollapsedBulk requires collapsed boolean');
        }

        const body = {
            note_ids: noteIds,
            collapsed: collapsed,
        };

        return this._apiCall(CONFIG.API.NOTES.SET_COLLAPSED_BULK, {
            method: 'POST',
            claimSession: true,
            body: JSON.stringify(body),
        });
    },

    async setCollapsedInContext(searchQuery, collapsed) {
        if (typeof searchQuery !== 'string') {
            throw new Error('NotesAPI.setCollapsedInContext requires searchQuery string');
        }
        if (typeof collapsed !== 'boolean') {
            throw new Error('NotesAPI.setCollapsedInContext requires collapsed boolean');
        }

        const body = {
            search_query: searchQuery,
            collapsed: collapsed,
        };

        return this._apiCall(CONFIG.API.NOTES.SET_COLLAPSED_IN_CONTEXT, {
            method: 'POST',
            claimSession: true,
            body: JSON.stringify(body),
        });
    },

    async undo() {
        const undoContext = captureUndoContext();
        const url = `${CONFIG.API.NOTES.UNDO}?client_id=${encodeURIComponent(ModeContext.clientId)}&undoContext=${encodeURIComponent(undoContext)}`;
        return this._apiCall(url, { method: 'POST', claimSession: true });
    },

    async redo() {
        const undoContext = captureUndoContext();
        const url = `${CONFIG.API.NOTES.REDO}?client_id=${encodeURIComponent(ModeContext.clientId)}&undoContext=${encodeURIComponent(undoContext)}`;
        return this._apiCall(url, { method: 'POST', claimSession: true });
    },

    async recordEditModeTransition(beforeEditingNoteId, afterEditingNoteId) {
        const body = {
            beforeEditingNoteId,
            afterEditingNoteId,
        };
        return this._apiCall(CONFIG.API.NOTES.EDIT_MODE, {
            method: 'POST',
            claimSession: true,
            body: JSON.stringify(body),
        });
    },

    getNoteElement(noteId) {
        const noteElement = document.querySelector(`[data-note-id="${noteId}"]`);
        if (!noteElement) {
            throw new Error(`Note not found: ${noteId}`);
        }
        return noteElement;
    },

    getNoteContentElement(noteId) {
        const noteElement = document.querySelector(`[data-note-id="${noteId}"]`);
        if (!noteElement) {
            throw new Error(`Note not found: ${noteId}`);
        }
        return noteElement.querySelector('.note-content');
    },

    async fetchView(noteId, searchQuery, tabId, visibleRootAnchorId) {
        if (typeof noteId === 'undefined') {
            throw new Error('NotesAPI.fetchView requires noteId (use null when not editing)');
        }
        if (typeof searchQuery === 'undefined') {
            throw new Error('NotesAPI.fetchView requires searchQuery (use null when empty)');
        }
        if (typeof tabId !== 'string') {
            throw new Error('NotesAPI.fetchView requires tabId string');
        }
        if (typeof visibleRootAnchorId === 'undefined') {
            throw new Error('NotesAPI.fetchView requires visibleRootAnchorId (use null when unknown)');
        }
        const payload = {
            clientId: ModeContext.clientId,
            editingNoteId: noteId,
            search: searchQuery,
            tabId,
            clientNoteUuidHashes: ModeContext.getNoteHashPayload(),
            visibleRootAnchorId,
        };

        const response = await this._apiCall(CONFIG.API.NOTES.VIEW, {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        return response;
    },

    async fetchSearchSuggestions(query) {
        if (typeof query !== 'string') {
            throw new Error('NotesAPI.fetchSearchSuggestions requires query string');
        }
        const payload = { query };
        return this._apiCall(CONFIG.API.NOTES.SEARCH_SUGGESTIONS, {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    },

    async fetchTagSuggestions(noteId, anchors, prefix, contentHtml) {
        if (typeof noteId !== 'string' || noteId.length === 0) {
            throw new Error('NotesAPI.fetchTagSuggestions requires noteId string');
        }
        if (!Array.isArray(anchors)) {
            throw new Error('NotesAPI.fetchTagSuggestions requires anchors array');
        }
        if (typeof prefix !== 'string') {
            throw new Error('NotesAPI.fetchTagSuggestions requires prefix string');
        }
        if (typeof contentHtml !== 'string') {
            throw new Error('NotesAPI.fetchTagSuggestions requires contentHtml string');
        }
        const payload = {
            note_id: noteId,
            anchors: anchors,
            prefix: prefix,
            content_html: contentHtml
        };
        return this._apiCall(CONFIG.API.NOTES.TAG_SUGGESTIONS, {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    },

    async moveNoteUp(noteId) {
        const noteElement = this.getNoteElement(noteId);
        const prevSibling = noteElement.previousElementSibling;
        if (!prevSibling || !prevSibling.classList.contains(CONFIG.CLASSES.NOTE)) return;

        const parentId = noteElement.dataset.parentId;
        let parentIdOrNull = null;
        if (typeof parentId === 'string' && parentId.length > 0) {
            parentIdOrNull = parentId;
        }
                                
        await this.moveNote(
            noteId,
            DOMUtils.getNoteId(prevSibling),
            'BEFORE',
            parentIdOrNull
        );
    },

    async moveNoteDown(noteId) {
        const noteElement = this.getNoteElement(noteId);
        const nextSibling = noteElement.nextElementSibling;
        if (!nextSibling || !nextSibling.classList.contains(CONFIG.CLASSES.NOTE)) return;

        const parentId = noteElement.dataset.parentId;
        let parentIdOrNull = null;
        if (typeof parentId === 'string' && parentId.length > 0) {
            parentIdOrNull = parentId;
        }
                                
        await this.moveNote(
            noteId,
            DOMUtils.getNoteId(nextSibling),
            'AFTER',
            parentIdOrNull
        );
    },

    async indentNote(noteId, visiblePrevId) {
        if (typeof visiblePrevId !== 'string' || visiblePrevId.length === 0) {
            throw new Error('NotesAPI.indentNote requires visiblePrevId string');
        }
        const body = {
            visible_prev_id: visiblePrevId,
        };
        return this._apiCall(CONFIG.API.NOTES.INDENT(noteId), {
            method: 'POST',
            claimSession: true,
            body: JSON.stringify(body)
        });
    },

    async outdentNote(noteId, searchQuery) {
        const body = {
            search_query: searchQuery,
        };
        return this._apiCall(CONFIG.API.NOTES.OUTDENT(noteId), {
            method: 'POST',
            claimSession: true,
            body: JSON.stringify(body)
        });
    },

    async copyNote(noteId) {
        return this._apiCall(CONFIG.API.NOTES.COPY(noteId), {
            method: 'POST'
        });
    },

    async exportNoteAsHtml(noteId) {
        let url = CONFIG.API.NOTES.EXPORT_HTML(noteId);
        url += `?client_id=${encodeURIComponent(ModeContext.clientId)}`;
        
        return this._apiCall(url, {
            method: 'GET'
        });
    },

    async pasteNoteSibling(targetNoteId) {
        const body = {
            search_query: ModeContext.searchQuery,
        };
        return this._apiCall(CONFIG.API.NOTES.PASTE_SIBLING(targetNoteId), {
            method: 'POST',
            claimSession: true,
            body: JSON.stringify(body),
        });
    },

    async pasteNoteChild(targetNoteId) {
        const body = {
            search_query: ModeContext.searchQuery,
        };
        return this._apiCall(CONFIG.API.NOTES.PASTE_CHILD(targetNoteId), {
            method: 'POST',
            claimSession: true,
            body: JSON.stringify(body),
        });
    },

    // Note locks removed: single-tab session ownership enforces exclusivity.
};
