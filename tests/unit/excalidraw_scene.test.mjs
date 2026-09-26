import assert from 'node:assert/strict';
import test from 'node:test';

import { UserInputRejected } from '../../app/static/js/modules/expected-errors.js';
import {
    EXCALIDRAW_AUTOSAVE_DELAY_MS,
    EXCALIDRAW_PREVIEW_VARIANTS,
    buildEmptySceneJson,
    computeSceneVersion,
    currentPreviewVariant,
    parseSceneJson,
    previewExportAppState,
    sceneFingerprint,
} from '../../app/static/js/modules/excalidraw/excalidraw-scene.js';

test('a new diagram is an empty Excalidraw scene that parses back', () => {
    const scene = parseSceneJson(buildEmptySceneJson());
    assert.equal(scene.type, 'excalidraw');
    assert.deepEqual(scene.elements, []);
    assert.deepEqual(scene.files, {});
    assert.equal(EXCALIDRAW_AUTOSAVE_DELAY_MS, 2000);
    assert.deepEqual(EXCALIDRAW_PREVIEW_VARIANTS, ['light', 'dark']);
});

test('parseSceneJson rejects files that are not Excalidraw scenes as user input', () => {
    assert.throws(() => parseSceneJson('{not json'), (error) => error instanceof UserInputRejected && /not JSON/.test(error.message));
    for (const text of ['null', '[]', '{"type":"other","elements":[]}', '{"type":"excalidraw"}', '{"type":"excalidraw","elements":{}}']) {
        assert.throws(() => parseSceneJson(text), UserInputRejected, text);
    }
    assert.throws(() => parseSceneJson(null), (error) => !(error instanceof UserInputRejected));
});

test('computeSceneVersion sums element versions like Excalidraw', () => {
    assert.equal(computeSceneVersion([]), 0);
    assert.equal(computeSceneVersion([{ version: 3 }, { version: 7 }]), 10);
    assert.throws(() => computeSceneVersion([{ version: '3' }]), /integer version/);
    assert.throws(() => computeSceneVersion(null), /elements array/);
});

test('sceneFingerprint changes with drawing content and embedded files only', () => {
    const files = { b: {}, a: {} };
    assert.equal(sceneFingerprint(10, files), sceneFingerprint(10, { a: {}, b: {} }));
    assert.notEqual(sceneFingerprint(10, files), sceneFingerprint(11, files));
    assert.notEqual(sceneFingerprint(10, files), sceneFingerprint(10, { a: {} }));
    assert.throws(() => sceneFingerprint(-1, files), /non-negative integer/);
    assert.throws(() => sceneFingerprint(1, null), /files map/);
});

test('previews are transparent unless the drawing has its own canvas colour', () => {
    for (const background of ['#ffffff', '#FFFFFF', '#fff', 'white', 'transparent']) {
        const appState = { viewBackgroundColor: background, gridSize: null };
        const light = previewExportAppState(appState, 'light');
        assert.equal(light.exportBackground, false, background);
        assert.equal(light.exportWithDarkMode, false);
        assert.equal(light.exportPadding, 16);
        assert.equal(light.gridSize, null);
        assert.equal(previewExportAppState(appState, 'dark').exportWithDarkMode, true);
        assert.deepEqual(appState, { viewBackgroundColor: background, gridSize: null }, 'input is not modified');
    }
    assert.equal(previewExportAppState({ viewBackgroundColor: '#ffec99' }, 'dark').exportBackground, true);
    assert.throws(() => previewExportAppState({}, 'sepia'), /Unknown preview variant/);
    assert.throws(() => previewExportAppState(null, 'light'), /appState/);
});

test('currentPreviewVariant follows the app theme on the document element', () => {
    const hadElement = 'Element' in globalThis;
    class FakeElement {
        constructor(theme) {
            this.theme = theme;
        }

        getAttribute(name) {
            return name === 'data-theme' ? this.theme : null;
        }
    }
    const previous = globalThis.Element;
    globalThis.Element = FakeElement;
    try {
        assert.equal(currentPreviewVariant(new FakeElement('dark')), 'dark');
        assert.equal(currentPreviewVariant(new FakeElement('light')), 'light');
        assert.equal(currentPreviewVariant(new FakeElement(null)), 'light');
        assert.throws(() => currentPreviewVariant({}), /document element/);
    } finally {
        if (hadElement) {
            globalThis.Element = previous;
        } else {
            delete globalThis.Element;
        }
    }
});
