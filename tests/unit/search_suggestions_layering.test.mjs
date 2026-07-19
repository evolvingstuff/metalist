import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const MAIN_CSS_URL = new URL('../../app/static/css/main.css', import.meta.url);
const KEYBOARD_EVENTS_URL = new URL(
    '../../app/static/js/modules/mode-manager/events/keyboard-events.js',
    import.meta.url,
);

function extractRuleZIndex(cssText, selector) {
    const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const rulePattern = new RegExp(`${escapedSelector}\\s*\\{[^}]*z-index:\\s*(\\d+)`, 's');
    const match = cssText.match(rulePattern);
    assert.ok(match, `Missing z-index rule for ${selector}`);
    return Number(match[1]);
}

test('visible search suggestions raise sticky controls above the tabs overlay', async () => {
    const cssText = await readFile(MAIN_CSS_URL, 'utf8');
    const tabsZIndex = extractRuleZIndex(cssText, '#search-contexts-list');
    const openSuggestionsZIndex = extractRuleZIndex(
        cssText,
        '.controls:has(.search-suggestions:not([hidden]):not(:empty))',
    );

    assert.ok(openSuggestionsZIndex > tabsZIndex);
});

test('Enter blank-tab creation does not hide the tabs overlay', async () => {
    const sourceText = await readFile(KEYBOARD_EVENTS_URL, 'utf8');
    const functionStart = sourceText.indexOf('function handleEnterKey(event)');
    const functionEnd = sourceText.indexOf('function handleCreateNoteShortcut(event)', functionStart);
    assert.ok(functionStart >= 0, 'Missing handleEnterKey');
    assert.ok(functionEnd > functionStart, 'Missing handleEnterKey boundary');

    const handleEnterKeySource = sourceText.slice(functionStart, functionEnd);
    assert.match(handleEnterKeySource, /keyboard\.enter\.blank_search_context/);
    assert.doesNotMatch(handleEnterKeySource, /hideSearchContextsOverlay\s*\(/);
});
