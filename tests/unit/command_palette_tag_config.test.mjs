import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const TEST_DIR = dirname(fileURLToPath(import.meta.url));
const TAG_CONFIG_PATH = resolve(
    TEST_DIR,
    '../../app/static/config/command_palette_tags.json',
);

test('create backup action matches the plural backups query', () => {
    const source = readFileSync(TAG_CONFIG_PATH, 'utf8');
    const payload = JSON.parse(source);
    const createBackup = payload.endpoints.find((endpoint) => endpoint.id === 'action.create_backup');

    assert.ok(createBackup, 'expected action.create_backup endpoint in command palette tag config');
    assert.equal(createBackup.tags.includes('backups'), true);
});
