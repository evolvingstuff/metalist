import assert from 'node:assert/strict';
import test from 'node:test';

import {
    buildLoginNamespaceOpeningCopy,
    buildLoginTitle,
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
