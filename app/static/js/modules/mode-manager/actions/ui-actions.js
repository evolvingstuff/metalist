import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { NotesAPI } from '../../api-client.js';
import { DOMUtils } from '../../dom-utils.js';
import { CONFIG } from '../../config.js';
import { highlightCommentsOnRender } from '../events/input-events.js';
import { updateCollapseAffordances } from '../services/collapse-affordance-service.js';
import { applyDifferentialView } from '../services/differential-view-service.js';

function updatePerfOverlay(roundtripMs, renderMs, totalMs) {
    let overlay = document.getElementById('perf-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'perf-overlay';
        overlay.style.position = 'fixed';
        overlay.style.bottom = '8px';
        overlay.style.right = '8px';
        overlay.style.padding = '4px 8px';
        overlay.style.borderRadius = '4px';
        overlay.style.background = 'rgba(0, 0, 0, 0.7)';
        overlay.style.color = '#fff';
        overlay.style.fontSize = '12px';
        overlay.style.fontFamily = 'monospace';
        overlay.style.zIndex = '9999';
        document.body.appendChild(overlay);
    }

    const roundtrip = Number(roundtripMs.toFixed(2));
    const render = Number(renderMs.toFixed(2));
    const total = Number(totalMs.toFixed(2));

    const rowStyle = 'padding-top: 2px; padding-bottom: 2px;';
    const labelStyle = 'padding: 0 14px 0 6px; white-space: nowrap;';
    const valueStyle = 'text-align: right; min-width: 70px; padding: 0 14px;';
    const dividerColor = 'rgba(255, 255, 255, 0.25)';
    const labelCellBaseStyle = `${labelStyle} ${rowStyle} border-right: 1px solid ${dividerColor};`;
    const valueCellBaseStyle = `${valueStyle} ${rowStyle};`;
    const bottomBorderStyle = `border-bottom: 1px solid ${dividerColor};`;

    overlay.innerHTML = `
        <table style="border-collapse: collapse;">
            <tbody>
                <tr>
                    <td style="${labelCellBaseStyle} ${bottomBorderStyle}">server trip</td>
                    <td style="${valueCellBaseStyle} ${bottomBorderStyle}">${roundtrip}ms</td>
                </tr>
                <tr>
                    <td style="${labelCellBaseStyle} ${bottomBorderStyle}">client render</td>
                    <td style="${valueCellBaseStyle} ${bottomBorderStyle}">${render}ms</td>
                </tr>
                <tr>
                    <td style="${labelCellBaseStyle}">total</td>
                    <td style="${valueCellBaseStyle}">${total}ms</td>
                </tr>
            </tbody>
        </table>
    `;
}

export async function actionRefreshAndMaybeSelect(options = {}) {
    Logger.logAction('refresh_and_maybe_select', { 
        noteId: ModeContext.currentNoteId,
        isEditing: ModeContext.isEditing
    });

    const noteId = ModeContext.currentNoteId;

    const shouldManageLoading = !options.skipLoadingState;
    if (shouldManageLoading && !ModeContext.isLoading) {
        ModeContext.setLoading(true);
    }

    const requestStartedAt = performance.now();
    const viewResponse = await NotesAPI.fetchView(noteId, ModeContext.searchQuery);
    if (!viewResponse || typeof viewResponse.snapshot !== 'object') {
        throw new Error('notes.view response missing snapshot payload');
    }
    const { snapshot } = viewResponse;
    ModeContext.syncNoteHashesFromSnapshot(snapshot);
    const roundtripMs = performance.now() - requestStartedAt;
    console.log(' [PERF] notes.view roundtrip:', {
        ms: Number(roundtripMs.toFixed(2))
    });

    if (snapshot) {
        console.log(' [SNAPSHOT] notes.view payload:', snapshot);
    }

    const renderStartedAt = performance.now();
    const diffResult = applyDifferentialView(snapshot);
    const notesContainer = diffResult.notesContainer;
    if (!notesContainer) {
        throw new Error('Notes container not found after diff application');
    }
    requestAnimationFrame(() => updateCollapseAffordances(notesContainer));

    // If this is initial page load, fade in the entire app
    if (ModeContext.isInitialPageLoad) {
        const appContainer = document.getElementById('app');
        if (appContainer) {
            appContainer.classList.add('loaded');
        }
        ModeContext.markInitialPageLoadComplete();
    }

    let contentHtml = null;
    let result = null;

    if (noteId) {
        const noteElement = DOMUtils.getNoteById(noteId);
        contentHtml = DOMUtils.getNoteContentHTML(noteElement);

        if (ModeContext.isEditing) {
                        
            DOMUtils.setNoteEditable(noteElement, true);
            
            // Highlight comments immediately when entering edit mode
            const noteContentElement = DOMUtils.getNoteContent(noteElement);
            highlightCommentsOnRender(noteContentElement);

            let cursorOffset = 0;
                        
            const savedOffset = ModeContext.savedCursorOffset;
            if (savedOffset && savedOffset.noteId === noteId) {
                                
                cursorOffset = savedOffset.offset;

                ModeContext.clearSavedCursorOffset();
                                
                Logger.logDebug('Using stored cursor offset', {
                    cursorOffset
                }, Logger.LogCategory.DEBUG);
            } else {
                // Use configured default cursor position when no saved offset
                const contentElement = DOMUtils.getNoteContent(noteElement);
                if (CONFIG.EDITOR.DEFAULT_CURSOR_POSITION === 'END') {
                    cursorOffset = contentElement.textContent.length || 0;
                } else {
                    // Default to START
                    cursorOffset = 0;
                }
            }

            DOMUtils.focusNote(noteElement, cursorOffset);
        }

        if (shouldManageLoading && ModeContext.isLoading) {
            ModeContext.setLoading(false);
        }
        result = contentHtml;
    } else {
                
        if (shouldManageLoading && ModeContext.isLoading) {
            ModeContext.setLoading(false);
        }
        result = null;
    }

    const renderEndedAt = performance.now();
    const renderMs = renderEndedAt - renderStartedAt;
    const totalMs = renderEndedAt - requestStartedAt;
    console.log(' [PERF] notes.view render:', {
        ms: Number(renderMs.toFixed(2))
    });
    updatePerfOverlay(roundtripMs, renderMs, totalMs);

    return result;
}
