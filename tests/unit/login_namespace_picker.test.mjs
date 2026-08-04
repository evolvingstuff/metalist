import assert from 'node:assert/strict';
import test from 'node:test';

import {
    buildLoginNamespaceOpeningCopy,
    buildLoginTitle,
    navigateNamespaceInNewTab,
    openPendingNamespaceTab,
    parseLoginNamespaceCatalog,
    rewriteNamespaceUrlPreservingCurrentHost,
} from '../../app/static/js/modules/login-namespace-picker.js';


test('buildLoginTitle omits the default namespace suffix', () => {
    assert.equal(buildLoginTitle('default'), 'MetaList');
});


test('buildLoginTitle appends non-default namespace suffix', () => {
    assert.equal(buildLoginTitle('cla'), 'MetaList [cla]');
});


test('parseLoginNamespaceCatalog preserves plain namespace labels', () => {
    const catalog = parseLoginNamespaceCatalog({
        current_namespace: 'default',
        namespaces: ['default', 'cla'],
    });

    assert.deepEqual(catalog, {
        currentNamespace: 'default',
        namespaces: ['default', 'cla'],
    });
});


test('buildLoginNamespaceOpeningCopy returns explicit loading text', () => {
    assert.deepEqual(buildLoginNamespaceOpeningCopy('cla'), {
        loadingMessage: 'Connecting to cla on its configured port…',
        loadingTitle: 'Switching namespace…',
        statusText: 'Opening cla…',
        subtitle: 'Opening cla…',
    });
});


test('rewriteNamespaceUrlPreservingCurrentHost swaps only the browser host', () => {
    const rewritten = rewriteNamespaceUrlPreservingCurrentHost(
        'http://127.0.0.1:8001/namespace-deleted?job=123',
        {
            hostname: '10.0.0.31',
        },
    );

    assert.equal(rewritten, 'http://10.0.0.31:8001/namespace-deleted?job=123');
});


test('namespace switching opens and navigates another tab without replacing the active tab', () => {
    const pendingTabUrls = [];
    const openedTabs = [];
    const pendingTab = {
        closed: false,
        location: {
            replace(url) {
                pendingTabUrls.push(url);
            },
        },
        opener: {},
    };
    const browserWindow = {
        location: {
            hostname: '10.0.0.31',
            replace() {
                throw new Error('namespace switching must leave the active tab open');
            },
        },
        open(url, target) {
            openedTabs.push({ target, url });
            return pendingTab;
        },
    };

    const openedTab = openPendingNamespaceTab(browserWindow);
    navigateNamespaceInNewTab(
        'http://127.0.0.1:8001/?namespace=cla',
        browserWindow,
        openedTab,
    );

    assert.deepEqual(openedTabs, [{ target: '_blank', url: 'about:blank' }]);
    assert.equal(pendingTab.opener, null);
    assert.deepEqual(pendingTabUrls, ['http://10.0.0.31:8001/?namespace=cla']);
});


test('openPendingNamespaceTab fails loudly when the browser blocks the tab', () => {
    assert.throws(
        () => openPendingNamespaceTab({ open: () => null }),
        /Browser blocked the namespace tab/,
    );
});
