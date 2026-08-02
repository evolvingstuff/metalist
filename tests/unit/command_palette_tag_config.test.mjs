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

test('create backup action matches backup and create queries', () => {
    const source = readFileSync(TAG_CONFIG_PATH, 'utf8');
    const payload = JSON.parse(source);
    const createBackup = payload.endpoints.find((endpoint) => endpoint.id === 'action.create_backup');

    assert.ok(createBackup, 'expected action.create_backup endpoint in command palette tag config');
    assert.equal(createBackup.tags.includes('backups'), true);
    assert.equal(createBackup.tags.includes('create'), true);
});

test('reminders action matches notification queries', () => {
    const source = readFileSync(TAG_CONFIG_PATH, 'utf8');
    const payload = JSON.parse(source);
    const reminders = payload.endpoints.find((endpoint) => endpoint.id === 'form.reminders');

    assert.ok(reminders, 'expected form.reminders endpoint in command palette tag config');
    assert.equal(reminders.tags.includes('notification'), true);
    assert.equal(reminders.tags.includes('notifications'), true);
});

test('animated transitions preference matches motion queries', () => {
    const source = readFileSync(TAG_CONFIG_PATH, 'utf8');
    const payload = JSON.parse(source);
    const animatedTransitions = payload.endpoints.find((endpoint) => endpoint.id === 'pref.animated_transitions');

    assert.ok(animatedTransitions, 'expected pref.animated_transitions endpoint in command palette tag config');
    assert.equal(animatedTransitions.tags.includes('animated'), true);
    assert.equal(animatedTransitions.tags.includes('motion'), true);
    assert.equal(animatedTransitions.tags.includes('disable'), true);
});

test('keyboard shortcuts action matches cheatsheet queries', () => {
    const source = readFileSync(TAG_CONFIG_PATH, 'utf8');
    const payload = JSON.parse(source);
    const shortcuts = payload.endpoints.find(
        (endpoint) => endpoint.id === 'action.open_keyboard_shortcuts_help',
    );

    assert.ok(shortcuts, 'expected keyboard shortcuts endpoint in command palette tag config');
    assert.equal(shortcuts.tags.includes('cheatsheet'), true);
});


test('note layout action matches appearance and hierarchy queries', () => {
    const source = readFileSync(TAG_CONFIG_PATH, 'utf8');
    const payload = JSON.parse(source);
    const noteLayout = payload.endpoints.find(
        (endpoint) => endpoint.id === 'form.note_layout_appearance',
    );

    assert.ok(noteLayout, 'expected note layout endpoint in command palette tag config');
    assert.equal(noteLayout.tags.includes('layout'), true);
    assert.equal(noteLayout.tags.includes('appearance'), true);
    assert.equal(noteLayout.tags.includes('hierarchy'), true);
});
