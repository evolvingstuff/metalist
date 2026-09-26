// Whether the full-screen Excalidraw editor is open. While it is, MetaList's document-level
// keyboard, mouse, clipboard and drag handlers stand aside so Excalidraw receives every event.
// This module is a leaf: global event modules import it without creating import cycles.
import { ApplicationState } from '../application-state.js';

const editorState = ApplicationState.createFields('excalidraw-editor-state', {
    isOpen: false,
});

export function isExcalidrawEditorOpen() {
    return editorState.isOpen;
}

export function setExcalidrawEditorOpen(isOpen) {
    if (typeof isOpen !== 'boolean') {
        throw new Error('setExcalidrawEditorOpen requires a boolean');
    }
    if (editorState.isOpen === isOpen) {
        throw new Error(`Excalidraw editor is already ${isOpen ? 'open' : 'closed'}`);
    }
    editorState.isOpen = isOpen;
}

// Wrap a document-level MetaList handler so it ignores events while the diagram editor is open.
export function unlessDiagramEditorOpen(handler) {
    if (typeof handler !== 'function') {
        throw new Error('unlessDiagramEditorOpen requires a handler function');
    }
    return function handleUnlessDiagramEditorOpen(event) {
        if (editorState.isOpen) {
            return undefined;
        }
        return handler.call(this, event);
    };
}
