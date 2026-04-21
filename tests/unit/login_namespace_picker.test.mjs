import assert from 'node:assert/strict';
import test from 'node:test';

import {
    buildLoginTitle,
    parseLoginNamespaceCatalog,
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
