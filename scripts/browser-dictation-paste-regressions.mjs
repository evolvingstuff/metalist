import assert from 'node:assert/strict';

// Dictated text (for example from Superwhisper) pasted into the search bar or
// the tag bar becomes the user's existing tags; one undo brings back exactly
// what was pasted (docs/ui/dictation-paste.md).

const DICTATED = 'Neural network, neural network. Neural-Dash Network.';

async function idle(page) {
  await page.waitForFunction(async () => {
    const {ModeContextInstance: mode} = await import('/static/js/modules/mode-manager/mode-context.js');
    return !mode.isLoading;
  });
  await page.waitForNetworkIdle({idleTime: 300});
}

// Synthetic paste of plain text into the focused element.
function paste(page, selector, text) {
  return page.evaluate(({selector, text}) => {
    const input = document.querySelector(selector);
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
    const data = new DataTransfer();
    data.setData('text/plain', text);
    input.dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true}));
  }, {selector, text});
}

function valueOf(page, selector) {
  return page.evaluate(selector => document.querySelector(selector).value, selector);
}

async function waitForValue(page, selector, expected, label) {
  try {
    await page.waitForFunction(({selector, expected}) => document.querySelector(selector).value === expected,
      {timeout: 5000}, {selector, expected});
  } catch (error) {
    assert.equal(await valueOf(page, selector), expected, label);
    throw error;
  }
}

// The browser's own undo for the focused field (what Cmd/Ctrl+Z runs there;
// synthetic shortcuts do not reach native editing commands on macOS).
function undo(page) {
  return page.evaluate(() => {
    if (!document.execCommand('undo')) throw new Error('undo was refused');
  });
}

// The real Cmd/Ctrl+Z shortcut: MetaList's own handler sees it and the browser
// runs its native undo (on macOS synthetic keys need the editing command).
async function undoShortcut(page) {
  if (process.platform === 'darwin') {
    await page.keyboard.down('Meta');
    await page.keyboard.down('z', {commands: ['undo']});
    await page.keyboard.up('z');
    await page.keyboard.up('Meta');
    return;
  }
  await page.keyboard.down('Control');
  await page.keyboard.press('z');
  await page.keyboard.up('Control');
}

function noteText(page, noteId) {
  return page.evaluate(noteId => document.querySelector(`[data-note-id="${noteId}"] .note-content`).textContent, noteId);
}

// Synthetic paste into the note's content at the end of its text.
function pasteIntoNote(page, noteId, text) {
  return page.evaluate(({noteId, text}) => {
    const content = document.querySelector(`[data-note-id="${noteId}"] .note-content`);
    content.focus();
    const range = document.createRange();
    range.selectNodeContents(content.lastElementChild);
    range.collapse(false);
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(range);
    const data = new DataTransfer();
    data.setData('text/plain', text);
    content.dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true}));
  }, {noteId, text});
}

function fatalText(page) {
  return page.evaluate(() => {
    const overlay = document.getElementById('fatal-error-overlay');
    return overlay ? overlay.textContent : '';
  });
}

export async function checkDictationPaste(page) {
  await page.reload();
  await page.waitForSelector('[data-app-ready="true"]');
  await idle(page);
  const noteId = await page.evaluate(async () => {
    const {NotesAPI} = await import('/static/js/modules/api-client.js');
    const note = await NotesAPI.createNote(null, '');
    await NotesAPI.saveNote(note.id, '<p>Dictation paste fixture</p>', 'neural-network python');
    return note.id;
  });
  try {
    await page.reload();
    await page.waitForSelector('[data-app-ready="true"]');
    await idle(page);

    // Search bar: the dictated phrase becomes the existing tag, and searches.
    await paste(page, '#search-input', DICTATED);
    await waitForValue(page, '#search-input', 'neural-network', 'search paste: dictated text becomes the existing tag');
    await idle(page);
    // One undo brings back exactly what was pasted.
    await undo(page);
    await waitForValue(page, '#search-input', DICTATED, 'search paste: one undo restores the pasted text');
    await page.evaluate(() => {
      const input = document.getElementById('search-input');
      input.select();
    });
    await page.keyboard.press('Backspace');
    await idle(page);

    // Tag bar: known tags are not added again, unknown words become new tags.
    const point = await page.evaluate(noteId => {
      const rect = document.querySelector(`[data-note-id="${noteId}"] .note-content p`).getBoundingClientRect();
      return {x: rect.left + 30, y: rect.top + Math.min(10, rect.height / 2)};
    }, noteId);
    await page.mouse.click(point.x, point.y);
    await page.waitForFunction(async noteId => {
      const {ModeContextInstance: mode} = await import('/static/js/modules/mode-manager/mode-context.js');
      return mode.isEditing && mode.currentNoteId === noteId && !mode.isLoading;
    }, {timeout: 10000}, noteId);
    await page.waitForSelector(`[data-note-id="${noteId}"] .note-tag-bar-input`, {visible: true});
    const tagBar = `[data-note-id="${noteId}"] .note-tag-bar-input`;
    await paste(page, tagBar, 'Neural network, transformers.');
    await waitForValue(page, tagBar, 'neural-network python transformers', 'tag bar paste: known tags kept once, a new word becomes a tag');
    await undo(page);
    // The tag bar's live clean-up drops the comma, as it does when typing one.
    await waitForValue(page, tagBar, 'neural-network python Neural network transformers.', 'tag bar paste: one undo restores the pasted text');
    // Back to the original tags for the next part (as if typed).
    await page.evaluate(selector => {
      const input = document.querySelector(selector);
      input.value = 'neural-network python';
      input.dispatchEvent(new Event('input', {bubbles: true}));
    }, tagBar);

    // Note content: the text before "start tags" goes into the note, the words
    // after it into the tag bar; one undo removes both.
    const textBefore = await noteText(page, noteId);
    await pasteIntoNote(page, noteId, ' More text. Start tags. GPT, transformer.');
    await waitForValue(page, tagBar, 'neural-network python GPT transformer', 'note paste: the words after the tag phrase become tags');
    assert.equal(await noteText(page, noteId), `${textBefore} More text.`, 'note paste: the text before the tag phrase goes into the note');
    await page.focus(`[data-note-id="${noteId}"] .note-content`);
    await undoShortcut(page);
    await waitForValue(page, tagBar, 'neural-network python', 'note paste: one undo removes the added tags');
    assert.equal(await noteText(page, noteId), textBefore, 'note paste: the same undo removes the pasted text');
    // Only tags: the note's text is untouched and one undo removes the tags.
    await pasteIntoNote(page, noteId, 'Start tags LLM');
    await waitForValue(page, tagBar, 'neural-network python LLM', 'note paste: only tags');
    assert.equal(await noteText(page, noteId), textBefore, 'note paste: no text added when only tags were dictated');
    await undoShortcut(page);
    await waitForValue(page, tagBar, 'neural-network python', 'note paste: undo removes tags pasted alone');
    assert.equal(await noteText(page, noteId), textBefore, 'note paste: undoing tags pasted alone leaves the text');
    await page.keyboard.press('Escape');
    await idle(page);
    assert.equal(await fatalText(page), '', 'dictation paste: no fatal error');
  } finally {
    await page.evaluate(async noteId => {
      const {NotesAPI} = await import('/static/js/modules/api-client.js');
      await NotesAPI.deleteNote(noteId);
    }, noteId);
  }
}
