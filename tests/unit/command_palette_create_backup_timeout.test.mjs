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

    const waitIndex = source.indexOf('await waitForCommandAvailability({', source.indexOf('async createBackup()'));
    const runIndex = source.indexOf("CommandGate.run('commandPalette.createBackup'", source.indexOf('async createBackup()'));
    assert.ok(waitIndex >= 0, 'createBackup should wait for browser command availability');
    assert.ok(waitIndex < runIndex, 'createBackup should wait before entering CommandGate');
    assert.match(
        source.slice(runIndex, source.indexOf('async logout()', runIndex)),
        /if \(backupResult === null\) \{\s*throw new Error\(/,
        'createBackup must not silently discard a dropped command',
    );
});
