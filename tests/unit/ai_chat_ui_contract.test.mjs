import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';


const TEMPLATE_URL = new URL('../../app/templates/index.html', import.meta.url);
const CSS_URL = new URL('../../app/static/css/main.css', import.meta.url);
const CONTROLLER_URL = new URL(
    '../../app/static/js/modules/ai-chat/ai-chat-panel-controller.js',
    import.meta.url,
);
const ENDPOINTS_URL = new URL(
    '../../app/static/js/modules/command-palette/endpoint-registry.js',
    import.meta.url,
);
const TAGS_URL = new URL('../../app/static/config/command_palette_tags.json', import.meta.url);


test('chat panel markup has a resizer, transcript, thinking region, and composer', () => {
    const template = readFileSync(TEMPLATE_URL, 'utf8');

    assert.match(template, /id="ai-chat-panel"/);
    assert.match(template, /id="ai-chat-resizer"/);
    assert.match(template, /id="ai-chat-resizer"[\s\S]*?tabindex="0"/);
    assert.match(template, /id="ai-chat-messages"/);
    assert.match(template, /id="ai-chat-input"/);
    assert.match(template, /id="ai-chat-send"/);
});


test('global controls place the shared chat toggle between menu and go-to-top', () => {
    const template = readFileSync(TEMPLATE_URL, 'utf8');
    const css = readFileSync(CSS_URL, 'utf8');
    const controller = readFileSync(CONTROLLER_URL, 'utf8');

    assert.match(
        template,
        /id="menu-button"[\s\S]*?id="chat-toggle-button"[\s\S]*?id="scroll-to-top-button"/,
    );
    assert.match(
        template,
        /id="chat-toggle-button"[\s\S]*?aria-pressed="false"[\s\S]*?<path d="M4 5h16v11H9l-5 4z"/,
    );
    assert.match(
        css,
        /\.chat-toggle-button svg\s*\{[^}]*width:\s*20px;[^}]*height:\s*20px;/s,
    );
    assert.match(controller, /toggle:\s*requireElement\('chat-toggle-button', HTMLButtonElement\)/);
    assert.match(controller, /elements\.toggle\.addEventListener\('click'[\s\S]*?this\._setVisible\(!isVisible\)/);
    assert.match(controller, /setAttribute\('aria-pressed', String\(isVisible\)\)/);
});


test('chat layout defaults to one third and narrows the notes shell', () => {
    const css = readFileSync(CSS_URL, 'utf8');

    assert.match(css, /--ai-chat-width:\s*33\.333vw;/);
    assert.match(css, /--ai-chat-min-notes-width:\s*480px;/);
    assert.match(
        css,
        /--ai-chat-effective-width:\s*clamp\(\s*280px,\s*var\(--ai-chat-width\),\s*calc\(100vw - var\(--ai-chat-min-notes-width\)\)\s*\);/,
    );
    assert.match(
        css,
        /body\.pref-show-ai-chat #app\s*\{[\s\S]*?width:\s*calc\(\s*100%\s*\+ \(2 \* var\(--app-page-padding\)\)\s*- var\(--ai-chat-effective-width\)\s*\);/,
    );
    assert.match(
        css,
        /body\.pref-show-ai-chat #app\s*\{[\s\S]*?margin-left:\s*calc\(-1 \* var\(--app-page-padding\)\);[\s\S]*?margin-right:\s*0;/,
    );
    assert.match(
        css,
        /--ai-chat-control-edge:\s*9px;/,
    );
    assert.match(
        css,
        /body\.pref-show-ai-chat \.global-controls\s*\{[\s\S]*?right:\s*calc\(var\(--ai-chat-effective-width\) \+ var\(--ai-chat-control-edge\)\);/,
    );
    assert.match(
        css,
        /\.ai-chat-panel\s*\{[\s\S]*?width:\s*var\(--ai-chat-effective-width\);/,
    );
    assert.match(css, /\.ai-chat-resizer[\s\S]*?cursor:\s*col-resize;/);
    assert.match(css, /\.ai-chat-resizer:focus-visible::after/);
    assert.match(css, /body\.pref-show-ai-chat\.pref-show-rhs-panel[\s\S]*?\.rhs-panel[\s\S]*?display:\s*none/);
});


test('notes keep symmetric gutters and spend gutter space before note width', () => {
    const css = readFileSync(CSS_URL, 'utf8');

    assert.match(
        css,
        /--app-min-visible-gutter:\s*calc\(var\(--side-rail-edge\) \+ 30px \+ 8px\);/,
    );
    assert.match(
        css,
        /\.container\s*\{[\s\S]*?max-width:\s*var\(--app-shell-width\);[\s\S]*?box-sizing:\s*border-box;/,
    );
    assert.match(
        css,
        /padding-inline:\s*clamp\([\s\S]*?calc\(var\(--app-min-visible-gutter\) - var\(--app-page-padding\)\)[\s\S]*?calc\(\(100% - var\(--app-content-width\)\) \/ 2\)[\s\S]*?5rem/,
    );
    assert.match(
        css,
        /body\.pref-show-ai-chat \.container\s*\{[\s\S]*?padding-inline:\s*clamp\([\s\S]*?var\(--app-min-visible-gutter\)[\s\S]*?calc\(\(100% - var\(--app-content-width\)\) \/ 2\)[\s\S]*?5rem/,
    );
});


test('small windows temporarily hide active chat without changing its preference', () => {
    const css = readFileSync(CSS_URL, 'utf8');
    const controller = readFileSync(CONTROLLER_URL, 'utf8');

    assert.match(
        css,
        /@media \(max-width:\s*760px\), \(max-height:\s*300px\)\s*\{[\s\S]*?body\.pref-show-ai-chat \.ai-chat-panel\s*\{[^}]*display:\s*none;[^}]*\}/,
    );
    assert.match(
        css,
        /@media \(max-width:\s*760px\), \(max-height:\s*300px\)[\s\S]*?body\.pref-show-ai-chat #app\s*\{[^}]*width:\s*min\(var\(--app-shell-width\), 100%\);[^}]*margin:\s*0 auto;/,
    );
    assert.match(
        css,
        /@media \(max-width:\s*760px\), \(max-height:\s*300px\)[\s\S]*?body\.pref-show-ai-chat \.global-controls\s*\{[^}]*right:\s*var\(--side-rail-edge\);/,
    );
    assert.doesNotMatch(controller, /ai-chat-responsive-hidden/);
});


test('empty chat does not render explanatory filler text', () => {
    const template = readFileSync(TEMPLATE_URL, 'utf8');
    const css = readFileSync(CSS_URL, 'utf8');
    const controller = readFileSync(CONTROLLER_URL, 'utf8');

    assert.doesNotMatch(template, /Chat directly with your configured Ollama model/);
    assert.doesNotMatch(template, /id="ai-chat-empty"/);
    assert.doesNotMatch(css, /\.ai-chat-empty/);
    assert.doesNotMatch(controller, /ai-chat-empty/);
});


test('chat messages use directional bubbles without repeated speaker labels', () => {
    const css = readFileSync(CSS_URL, 'utf8');
    const controller = readFileSync(CONTROLLER_URL, 'utf8');

    assert.match(css, /\.ai-chat-message-user[\s\S]*?border-bottom-right-radius:\s*0;/);
    assert.match(css, /\.ai-chat-message-assistant[\s\S]*?border-bottom-left-radius:\s*0;/);
    assert.doesNotMatch(controller, /ai-chat-message-role/);
});


test('streaming thinking renders three animated dots', () => {
    const css = readFileSync(CSS_URL, 'utf8');
    const controller = readFileSync(CONTROLLER_URL, 'utf8');

    assert.match(controller, /ai-chat-thinking-dots/);
    assert.match(controller, /index < 3/);
    assert.match(css, /@keyframes ai-chat-thinking-dot/);
    assert.match(css, /prefers-reduced-motion:\s*reduce/);
});


test('command menu contains chat toggle and AI agent configuration actions', () => {
    const endpointSource = readFileSync(ENDPOINTS_URL, 'utf8');
    const tagConfig = JSON.parse(readFileSync(TAGS_URL, 'utf8'));

    assert.match(endpointSource, /id:\s*'pref\.show_ai_chat'/);
    assert.match(endpointSource, /id:\s*'form\.ai_agent_settings'/);
    assert.ok(tagConfig.endpoints.some((endpoint) => endpoint.id === 'pref.show_ai_chat'));
    assert.ok(tagConfig.endpoints.some((endpoint) => endpoint.id === 'form.ai_agent_settings'));
});
