import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
const CONTROLLER_PATH = resolve(
    TEST_DIR,
    '../../app/static/js/modules/command-palette/command-palette-controller.js',
);

function readAsyncMethod(source, methodName) {
    const methodStart = source.indexOf(`    async ${methodName}() {`);
    assert.notEqual(methodStart, -1, `${methodName} method should exist`);
    const methodEnd = source.indexOf('\n    async ', methodStart + 1);
    assert.notEqual(methodEnd, -1, `${methodName} method end should exist`);
    return source.slice(methodStart, methodEnd);
}

test('Expand All and Collapse All explicitly disable note animations', () => {
    const source = readFileSync(CONTROLLER_PATH, 'utf8');

    for (const methodName of ['expandAll', 'collapseAll']) {
        const methodSource = readAsyncMethod(source, methodName);
        assert.match(
            methodSource,
            /actionRefreshAndMaybeSelect\(\{ animateNoteChanges: false \}\)/,
            `${methodName} should suppress note animations during its refresh`,
        );
    }
});
