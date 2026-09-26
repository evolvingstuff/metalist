import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const MAIN_CSS_URL = new URL('../../app/static/css/main.css', import.meta.url);

function extractRuleZIndex(cssText, selector) {
    const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const rulePattern = new RegExp(`(?:^|\\n)${escapedSelector}\\s*\\{[^}]*z-index:\\s*(\\d+)`, 's');
    const match = cssText.match(rulePattern);
    assert.ok(match, `Missing z-index rule for ${selector}`);
    return Number(match[1]);
}

test('full-screen note view covers the AI chat panel', async () => {
    const cssText = await readFile(MAIN_CSS_URL, 'utf8');
    const chatZIndex = extractRuleZIndex(cssText, '.ai-chat-panel');
    const fullscreenZIndex = extractRuleZIndex(cssText, '.note-fullscreen-overlay');

    assert.ok(fullscreenZIndex > chatZIndex, `${fullscreenZIndex} must exceed chat ${chatZIndex}`);
});

test('zoomed images appear above full-screen notes and the AI chat panel', async () => {
    const cssText = await readFile(MAIN_CSS_URL, 'utf8');
    const zoomZIndex = extractRuleZIndex(cssText, '.image-zoom-overlay');

    assert.ok(zoomZIndex > extractRuleZIndex(cssText, '.note-fullscreen-overlay'));
    assert.ok(zoomZIndex > extractRuleZIndex(cssText, '.ai-chat-panel'));
});

test('context menus and modals still open above full-screen notes', async () => {
    const cssText = await readFile(MAIN_CSS_URL, 'utf8');
    const fullscreenZIndex = extractRuleZIndex(cssText, '.note-fullscreen-overlay');
    const zoomZIndex = extractRuleZIndex(cssText, '.image-zoom-overlay');

    for (const selector of ['.context-menu', '.modal']) {
        const layer = extractRuleZIndex(cssText, selector);
        assert.ok(layer > fullscreenZIndex, `${selector} ${layer} must exceed full screen ${fullscreenZIndex}`);
        assert.ok(layer > zoomZIndex, `${selector} ${layer} must exceed image zoom ${zoomZIndex}`);
    }
});
