import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';

const source = readFileSync(new URL('../../app/static/js/modules/mode-manager/actions/content-actions.js', import.meta.url), 'utf8')
    .replace(/^import .*;\n/gm, '').replace(/^export /gm, '');

function harness() {
    const saves = [];
    const expansionChecks = [];
    const expansion = {async persist() { return false; }};
    const note = {innerHTML:'<p>Choas</p>', dataset:{noteTags:''}, tags:''};
    const mode = {
        currentNoteId:'note-1', currentContent:note.innerHTML, lastSavedContent:null,
        isDirty:false, editSessionHasEdits:false, isActive:false,
        setCurrentContent(value) { assert.notEqual(this.currentContent, value); this.currentContent = value; },
        setLastSavedContent(value) { assert.notEqual(this.lastSavedContent, value); this.lastSavedContent = value; },
        setDirty(value) { assert.notEqual(this.isDirty, value); this.isDirty = value; },
        markEditSessionHasEdits() { assert.equal(this.editSessionHasEdits, false); this.editSessionHasEdits = true; },
    };
    const dependencies = {
        ModeContext:mode,
        Logger:{logAction() {}, logDebug() {}, LogCategory:{DEBUG:'debug', STATE:'state'}},
        NotesAPI:{async saveNote(...args) { saves.push(args); return {status:'success'}; }},
        DOMUtils:{getNoteContentHTML:element => element.innerHTML},
        document:{querySelector:() => note},
        getTagBarValue:element => element.tags,
        setTagBarValue(element, value) { element.tags = value; element.dataset.noteTags = value; },
        async persistExpandedEditSessionIfNeeded() {
            expansionChecks.push(mode.editSessionHasEdits);
            return expansion.persist();
        },
        sanitizeNoteHtmlForStorage:html => html.replaceAll(' data-render-only="true"', ''),
    };
    const actions = new Function(...Object.keys(dependencies), `${source}\nreturn {actionSaveNote, actionSaveNoteOnIdle};`)(...Object.values(dependencies));
    return {note, mode, saves, expansionChecks, expansion, ...actions};
}

for (const saveAction of ['actionSaveNote', 'actionSaveNoteOnIdle']) {
    test(`${saveAction} captures external correction once and records edit before collapse persistence`, async () => {
        const h = harness();
        h.note.innerHTML = '<p>Chaos</p>';
        await h[saveAction]('note-1');
        assert.deepEqual(h.saves, [['note-1', '<p>Chaos</p>', '']]);
        assert.deepEqual(h.expansionChecks, [true]);
        assert.equal(h.mode.currentContent, h.note.innerHTML);
        assert.equal(h.mode.lastSavedContent, '<p>Chaos</p>');
        assert.equal(h.mode.isDirty, false);
        await h[saveAction]('note-1');
        assert.equal(h.saves.length, 1, 'Repeated observation must not create duplicate saves');
    });

    test(`${saveAction} ignores changes that disappear during storage sanitization`, async () => {
        const h = harness();
        h.note.innerHTML = '<p data-render-only="true">Choas</p>';
        await h[saveAction]('note-1');
        assert.deepEqual(h.saves, []);
        assert.equal(h.mode.editSessionHasEdits, false);
    });

    test(`${saveAction} includes a later correction arriving during expansion persistence`, async () => {
        const h = harness();
        h.note.innerHTML = '<p>Chaos</p>';
        h.expansion.persist = async () => {
            h.note.innerHTML = '<p>Foundation and Chaos</p>';
            return true;
        };
        await h[saveAction]('note-1');
        assert.deepEqual(h.saves, [['note-1', '<p>Foundation and Chaos</p>', '']]);
        assert.equal(h.mode.currentContent, h.note.innerHTML);
        assert.equal(h.mode.isDirty, false);
    });
}

test('tag-only save still persists tags without claiming a content edit', async () => {
    const h = harness();
    h.note.tags = 'books';
    await h.actionSaveNote('note-1');
    assert.deepEqual(h.saves, [['note-1', '<p>Choas</p>', 'books']]);
    assert.equal(h.mode.editSessionHasEdits, false);
});

test('save rejects an uninitialized active-editor snapshot', async () => {
    const h = harness();
    h.mode.currentContent = null;
    await assert.rejects(h.actionSaveNote('note-1'), /requires its current content snapshot/);
    assert.deepEqual(h.saves, []);
});
