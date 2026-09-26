import assert from 'node:assert/strict';
import test from 'node:test';

import { AUTOSAVE_STATUS, createAutosaveController } from '../../app/static/js/modules/excalidraw/excalidraw-autosave.js';

const settle = () => new Promise((resolve) => setImmediate(resolve));

function deferred() {
    const handle = {};
    handle.promise = new Promise((resolve) => {
        handle.resolve = resolve;
    });
    return handle;
}

// Timers that only fire when the test says so.
function manualTimers() {
    const pending = new Map();
    let nextId = 1;
    return {
        schedule(callback, delayMs) {
            const id = nextId;
            nextId += 1;
            pending.set(id, { callback, delayMs });
            return id;
        },
        cancel(id) {
            pending.delete(id);
        },
        async fire() {
            const due = Array.from(pending.values());
            pending.clear();
            for (const entry of due) {
                entry.callback();
            }
            await settle();
        },
        get count() {
            return pending.size;
        },
        get delays() {
            return Array.from(pending.values()).map((entry) => entry.delayMs);
        },
    };
}

function buildController(saveResults) {
    const timers = manualTimers();
    const statuses = [];
    const saves = [];
    const controller = createAutosaveController({
        delayMs: 2000,
        save: () => {
            saves.push(saves.length + 1);
            const next = saveResults.shift();
            if (next === undefined) {
                return { ok: true };
            }
            return typeof next === 'function' ? next() : next;
        },
        schedule: timers.schedule,
        cancel: timers.cancel,
        onStatus: (status) => statuses.push(status),
    });
    return { controller, timers, statuses, saves };
}

test('edits save once after the drawing has been idle for the delay', async () => {
    const { controller, timers, statuses, saves } = buildController([]);
    controller.noteChange();
    controller.noteChange();
    controller.noteChange();

    assert.equal(timers.count, 1);
    assert.deepEqual(timers.delays, [2000]);
    assert.equal(saves.length, 0);
    assert.equal(controller.status, AUTOSAVE_STATUS.UNSAVED);
    assert.equal(controller.isDirty, true);

    await timers.fire();

    assert.equal(saves.length, 1);
    assert.equal(controller.status, AUTOSAVE_STATUS.SAVED);
    assert.equal(controller.isDirty, false);
    assert.deepEqual(statuses, [AUTOSAVE_STATUS.UNSAVED, AUTOSAVE_STATUS.SAVING, AUTOSAVE_STATUS.SAVED]);
});

test('an edit made while a save is in flight is saved by a second save', async () => {
    const slowSave = deferred();
    const { controller, timers, statuses, saves } = buildController([() => slowSave.promise]);
    controller.noteChange();
    await timers.fire();
    assert.equal(controller.status, AUTOSAVE_STATUS.SAVING);

    controller.noteChange();
    assert.equal(controller.status, AUTOSAVE_STATUS.SAVING, 'status stays Saving while the first save runs');
    await timers.fire();
    assert.equal(saves.length, 1, 'only one save runs at a time');

    slowSave.resolve({ ok: true });
    await settle();
    assert.equal(controller.status, AUTOSAVE_STATUS.UNSAVED);
    assert.equal(timers.count, 1);

    await timers.fire();
    assert.equal(saves.length, 2);
    assert.equal(controller.status, AUTOSAVE_STATUS.SAVED);
    assert.deepEqual(statuses, [
        AUTOSAVE_STATUS.UNSAVED,
        AUTOSAVE_STATUS.SAVING,
        AUTOSAVE_STATUS.UNSAVED,
        AUTOSAVE_STATUS.SAVING,
        AUTOSAVE_STATUS.SAVED,
    ]);
});

test('a failed save keeps the changes and retries after the delay', async () => {
    const { controller, timers, saves } = buildController([{ ok: false, conflict: false }]);
    controller.noteChange();
    await timers.fire();

    assert.equal(controller.status, AUTOSAVE_STATUS.ERROR);
    assert.equal(controller.isDirty, true);
    assert.equal(timers.count, 1);

    await timers.fire();
    assert.equal(saves.length, 2);
    assert.equal(controller.status, AUTOSAVE_STATUS.SAVED);
});

test('a revision conflict stops autosave for the rest of the session', async () => {
    const { controller, timers, saves } = buildController([{ ok: false, conflict: true }]);
    controller.noteChange();
    await timers.fire();

    assert.equal(controller.status, AUTOSAVE_STATUS.CONFLICT);
    assert.equal(timers.count, 0);
    controller.noteChange();
    assert.equal(timers.count, 0, 'edits after a conflict are not scheduled');
    assert.equal(await controller.flush(), AUTOSAVE_STATUS.CONFLICT);
    assert.equal(saves.length, 1);
});

test('flush saves pending edits at once and cancels the idle timer', async () => {
    const { controller, timers, saves } = buildController([]);
    assert.equal(await controller.flush(), AUTOSAVE_STATUS.SAVED);
    assert.equal(saves.length, 0, 'nothing to save');

    controller.noteChange();
    assert.equal(await controller.flush(), AUTOSAVE_STATUS.SAVED);
    assert.equal(saves.length, 1);
    assert.equal(timers.count, 0);
});

test('flush waits for the save in flight and then saves later edits', async () => {
    const slowSave = deferred();
    const { controller, timers, saves } = buildController([() => slowSave.promise]);
    controller.noteChange();
    await timers.fire();
    controller.noteChange();

    const flushed = controller.flush();
    slowSave.resolve({ ok: true });

    assert.equal(await flushed, AUTOSAVE_STATUS.SAVED);
    assert.equal(saves.length, 2);
    assert.equal(controller.isDirty, false);
});

test('flush reports a failure instead of retrying forever', async () => {
    const { controller } = buildController([{ ok: false, conflict: false }]);
    controller.noteChange();
    assert.equal(await controller.flush(), AUTOSAVE_STATUS.ERROR);
    assert.equal(controller.isDirty, true);
});

test('stop cancels the pending save and waitForIdle waits for the one in flight', async () => {
    const slowSave = deferred();
    const { controller, timers, saves } = buildController([() => slowSave.promise]);
    controller.noteChange();
    await timers.fire();
    controller.noteChange();
    controller.stop();
    assert.equal(timers.count, 0);

    let idle = false;
    const waiting = controller.waitForIdle().then(() => {
        idle = true;
    });
    await settle();
    assert.equal(idle, false);
    slowSave.resolve({ ok: true });
    await waiting;
    assert.equal(idle, true);
    assert.equal(saves.length, 1);
    assert.equal(timers.count, 0, 'a stopped controller does not reschedule');
    controller.noteChange();
    assert.equal(timers.count, 0);
});

test('save must resolve to an ok flag', async () => {
    const { controller } = buildController([{ saved: true }]);
    controller.noteChange();
    await assert.rejects(controller.flush(), /must resolve to \{ ok: boolean \}/);
});

test('createAutosaveController validates its options', () => {
    const valid = {
        delayMs: 2000,
        save: () => ({ ok: true }),
        schedule: () => 1,
        cancel: () => {},
        onStatus: () => {},
    };
    assert.throws(() => createAutosaveController(null), /requires options/);
    assert.throws(() => createAutosaveController({ ...valid, delayMs: 1.5 }), /delayMs/);
    assert.throws(() => createAutosaveController({ ...valid, delayMs: -1 }), /delayMs/);
    for (const name of ['save', 'schedule', 'cancel', 'onStatus']) {
        assert.throws(() => createAutosaveController({ ...valid, [name]: null }), new RegExp(`${name} function`));
    }
});
