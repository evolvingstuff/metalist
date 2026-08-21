import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';


const AUTH_SOURCE_URL = new URL('../../app/static/js/modules/auth.js', import.meta.url);


test('encrypted login always shows and completes the database progress flow', async () => {
    const source = await readFile(AUTH_SOURCE_URL, 'utf8');
    const loginStart = source.indexOf('async handleLogin(event)');
    const loginEnd = source.indexOf('async logout()', loginStart);
    assert.notEqual(loginStart, -1);
    assert.notEqual(loginEnd, -1);

    const loginSource = source.slice(loginStart, loginEnd);
    const progressPanelIndex = loginSource.indexOf('this._showLoginLoadingPanel(');
    const browserPaintIndex = loginSource.indexOf('await this._waitForBrowserPaint();');
    const loginRequestIndex = loginSource.indexOf('fetch(CONFIG.API.AUTH.LOGIN');
    const progressFlowIndex = loginSource.indexOf('await this._runHydrationFlow();');

    assert.ok(progressPanelIndex >= 0);
    assert.ok(browserPaintIndex > progressPanelIndex);
    assert.ok(loginRequestIndex > browserPaintIndex);
    assert.ok(progressFlowIndex > loginRequestIndex);
    assert.match(loginSource, /data\.hydration_required !== true/);
    assert.doesNotMatch(loginSource, /if \(data\.hydration_required\)\s*\{/);
    assert.match(
        source,
        /Hydration failed during \$\{failedPhase\}: \$\{failedMessage\}/,
    );
    assert.match(source, /_startLoadingElapsedTimer\(\)/);
    assert.match(source, /_stopLoadingElapsedTimer\(\)/);
    assert.match(source, /formatElapsedDuration/);
});


test('login template exposes elapsed startup time without claiming every hydration is a restart', async () => {
    const templateUrl = new URL('../../app/templates/index.html', import.meta.url);
    const templateSource = await readFile(templateUrl, 'utf8');

    assert.match(templateSource, /id="login-loading-elapsed"/);
    assert.doesNotMatch(templateSource, /First-time load after a server restart/);
});


test('encrypted hydration hides the duplicate page subtitle above the progress panel', async () => {
    const source = await readFile(AUTH_SOURCE_URL, 'utf8');
    const hydrationStart = source.indexOf('_showHydrationUI()');
    const hydrationEnd = source.indexOf('_updateHydrationUI(status)', hydrationStart);

    assert.ok(hydrationStart >= 0);
    assert.ok(hydrationEnd > hydrationStart);
    assert.match(source.slice(hydrationStart, hydrationEnd), /this\._hideLoginSubtitle\(\);/);
    assert.match(
        source,
        /_setLoginSubtitle\(text\)[\s\S]*subtitle\.textContent = text;[\s\S]*subtitle\.hidden = false;/,
    );
});


test('post-login startup failures do not return to the password form', async () => {
    const source = await readFile(AUTH_SOURCE_URL, 'utf8');
    const loginStart = source.indexOf('async handleLogin(event)');
    const loginEnd = source.indexOf('async logout()', loginStart);
    const loginSource = source.slice(loginStart, loginEnd);
    const failedResponseBranch = loginSource.indexOf('if (!response.ok)');
    const modeManagerInitialization = loginSource.indexOf('await window.ModeManager.init({});');
    const loginFailureCatch = loginSource.indexOf('catch (error)');

    assert.ok(failedResponseBranch >= 0);
    assert.ok(loginFailureCatch < failedResponseBranch);
    assert.ok(modeManagerInitialization > loginFailureCatch);
    assert.doesNotMatch(
        loginSource.slice(modeManagerInitialization),
        /this\.showLoginModal\(\)/,
    );
});


test('post-login startup failures expose the underlying browser error', async () => {
    const source = await readFile(AUTH_SOURCE_URL, 'utf8');
    const loginStart = source.indexOf('async handleLogin(event)');
    const loginEnd = source.indexOf('async logout()', loginStart);
    const loginSource = source.slice(loginStart, loginEnd);

    assert.match(loginSource, /let startupPhase = 'reading the login response'/);
    assert.match(loginSource, /startupPhase = 'hydrating the workspace'/);
    assert.match(loginSource, /startupPhase = 'initializing the workspace UI'/);
    assert.match(loginSource, /const errorMessage = error instanceof Error/);
    assert.match(loginSource, /const diagnosticMessage = `\$\{startupPhase\}: \$\{errorMessage\}`/);
    assert.match(loginSource, /loadingMessage\.textContent[\s\S]*\$\{diagnosticMessage\}/);
    assert.doesNotMatch(loginSource, /window\.alert\(/);
    assert.match(loginSource, /throw new Error\(errorMessage\)/);
});
