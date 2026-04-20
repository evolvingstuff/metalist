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

test('createBackup configures a longer CommandGate watchdog timeout', () => {
    const source = readFileSync(CONTROLLER_PATH, 'utf8');
    const match = source.match(
        /async createBackup\(\) \{[\s\S]*?CommandGate\.run\('commandPalette\.createBackup', async \(\) => \{[\s\S]*?\},\s*\{\s*timeoutMs:\s*(\d+),\s*\}\s*\)/,
    );

    assert.ok(match, 'createBackup should pass explicit timeoutMs to CommandGate.run');
    assert.equal(Number(match[1]), 120000);
});
