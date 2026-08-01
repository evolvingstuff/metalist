import assert from 'node:assert/strict';
import test from 'node:test';

import {
    buildLoginNamespaceOpeningCopy,
    buildLoginTitle,
    navigateNamespaceInCurrentTab,
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


test('navigateNamespaceInCurrentTab replaces the active tab without opening another tab', () => {
    const replacedUrls = [];
    const browserWindow = {
        location: {
            hostname: '10.0.0.31',
            replace(url) {
                replacedUrls.push(url);
            },
        },
        open() {
            throw new Error('namespace switching must not open a new tab');
        },
    };

    navigateNamespaceInCurrentTab(
        'http://127.0.0.1:8001/?namespace=cla',
        browserWindow,
    );

    assert.deepEqual(replacedUrls, ['http://10.0.0.31:8001/?namespace=cla']);
});
