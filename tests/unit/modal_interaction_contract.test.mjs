import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import test from 'node:test';


const BASE_MODAL_URL = new URL('../../app/static/js/modules/modals/base-modal.js', import.meta.url);
const MAIN_CSS_URL = new URL('../../app/static/css/main.css', import.meta.url);
const MODALS_ROOT_URL = new URL('../../app/static/js/modules/modals/', import.meta.url);
const IMAGE_CHOICE_URL = new URL(
    '../../app/static/js/modules/mode-manager/services/image-file-insert-choice-modal-service.js',
    import.meta.url,
);
const CONTEXT_MENU_URL = new URL(
    '../../app/static/js/modules/context-menu/context-menu-service.js',
    import.meta.url,
);


function readModalSource(filename) {
    return readFileSync(new URL(filename, MODALS_ROOT_URL), 'utf8');
}


function modalSourceEntries() {
    return readdirSync(MODALS_ROOT_URL)
        .filter((filename) => filename.endsWith('.js'))
        .map((filename) => ({ filename, source: readModalSource(filename) }));
}


test('BaseModal supports a universal close button, Escape, outside click, and Enter actions', () => {
    const source = readFileSync(BASE_MODAL_URL, 'utf8');

    assert.match(source, /className = 'modal-close-button'/);
    assert.match(source, /textContent = '×'/);
    assert.match(source, /title = 'Close \(Esc\)'/);
    assert.match(source, /closeButton\.onclick = \(\) => this\.requestClose\(\)/);
    assert.match(source, /event\.key === 'Escape'/);
    assert.match(source, /this\.requestClose\(\)/);
    assert.match(source, /event\.target === event\.currentTarget/);
    assert.match(source, /\[data-modal-enter-action\]/);
});


test('modal render replacement reinstalls the universal close button', () => {
    const source = readFileSync(BASE_MODAL_URL, 'utf8');

    assert.match(source, /_wrapModalContentRenderer\(\)/);
    assert.match(source, /renderModalContent\.apply\(this, args\)/);
    assert.match(source, /this\._installModalCloseButton\(\)/);
});


test('the universal modal close control is circular and upper-right aligned', () => {
    const source = readFileSync(MAIN_CSS_URL, 'utf8');
    const ruleStart = source.indexOf('.modal-content .modal-close-button');
    const ruleEnd = source.indexOf('.modal-content .modal-close-button:hover', ruleStart);
    assert.notEqual(ruleStart, -1);
    assert.notEqual(ruleEnd, -1);
    const ruleSource = source.slice(ruleStart, ruleEnd);

    assert.match(ruleSource, /position:\s*absolute/);
    assert.match(ruleSource, /top:\s*16px/);
    assert.match(ruleSource, /right:\s*16px/);
    assert.match(ruleSource, /border-radius:\s*50%/);
});


test('modal sources do not render dismiss-only Close or OK footer buttons', () => {
    for (const { filename, source } of modalSourceEntries()) {
        assert.doesNotMatch(source, />\s*(?:Close|OK)\s*</, `${filename} has a dismiss-only button`);
    }
});


test('BaseModal outside-click detection survives modal content replacement during a click', () => {
    const source = readFileSync(BASE_MODAL_URL, 'utf8');
    const handlerStart = source.indexOf('    handleClickOutside(event) {');
    const handlerEnd = source.indexOf('    _wrapModalContentRenderer()', handlerStart);
    assert.notEqual(handlerStart, -1);
    assert.notEqual(handlerEnd, -1);
    const handlerSource = source.slice(handlerStart, handlerEnd);

    assert.match(handlerSource, /event\.target === event\.currentTarget/);
    assert.doesNotMatch(handlerSource, /querySelector/);
});


test('every modal with a primary button declares or implements Enter behavior', () => {
    for (const { filename, source } of modalSourceEntries()) {
        if (!source.includes('primary-btn')) {
            continue;
        }
        const hasDeclaredAction = source.includes('data-modal-enter-action');
        const hasCustomHandler = source.includes('onKeyDown(event)') || source.includes('handleKeyDown(event)');
        assert.equal(
            hasDeclaredAction || hasCustomHandler,
            true,
            `${filename} must support Enter`,
        );
    }
});


test('formerly blocking modals allow outside-click closing', () => {
    const modalFiles = [
        'backup-restore-modal.js',
        'backup-result-modal.js',
        'backup-retention-modal.js',
        'backup-settings-modal.js',
        'delete-namespace-modal.js',
        'namespace-modals.js',
        'password-modal.js',
    ];

    for (const filename of modalFiles) {
        const source = readModalSource(filename);
        assert.doesNotMatch(
            source,
            /shouldCloseOnClickOutside\(\)\s*\{\s*return false;/,
            `${filename} must allow outside-click closing`,
        );
    }
});


test('delete namespace modal starts in loading state before its async onOpen hook', () => {
    const source = readModalSource('delete-namespace-modal.js');
    const initialStateStart = source.indexOf('    getInitialModalState() {');
    const initialStateEnd = source.indexOf('    shouldCloseOnClickOutside()', initialStateStart);
    assert.notEqual(initialStateStart, -1);
    assert.notEqual(initialStateEnd, -1);
    const initialStateSource = source.slice(initialStateStart, initialStateEnd);

    assert.match(initialStateSource, /loading:\s*true,/);
});


test('the only BaseModal outside-click override has an explicit equivalent handler', () => {
    for (const { filename, source } of modalSourceEntries()) {
        const disablesBaseOutsideClick = /shouldCloseOnClickOutside\(\)\s*\{\s*return false;/.test(source);
        if (!disablesBaseOutsideClick) {
            continue;
        }
        assert.equal(filename, 'ontology-modal.js');
        assert.match(source, /_handleMouseDownOutside\(event\)/);
        assert.match(source, /_handleMouseDownOutside[\s\S]*?this\.close\(\)/);
    }
});


test('image insert choice supports the universal close button, Escape, outside click, and Enter', () => {
    const source = readFileSync(IMAGE_CHOICE_URL, 'utf8');

    assert.match(source, /class="modal-close-button"/);
    assert.match(source, /title="Close \(Esc\)"/);
    assert.match(source, /event\.target === modalElement/);
    assert.match(source, /event\.key === 'Escape'/);
    assert.match(source, /event\.key === 'Enter'/);
});


test('context menus support Escape, outside click, and Enter', () => {
    const source = readFileSync(CONTEXT_MENU_URL, 'utf8');

    assert.match(source, /event\.key === 'Escape'/);
    assert.match(source, /handleGlobalMouseDown/);
    assert.match(source, /event\.key (?:===|!==) 'Enter'/);
});
