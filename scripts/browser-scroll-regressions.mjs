import assert from 'node:assert/strict';

// Leaving edit mode keeps your place: the text you were working on (the caret,
// when it is on screen) or reading (the line about a third down the screen)
// stays at the same height once the note renders for viewing, with no visible
// jump. A collapsed note that collapses again stays in view. Clicking another
// note while editing keeps the clicked text under the pointer.

const SETTLE_MS = 1500;
const TOLERANCE_PX = 2;

function paragraphs(label, count) {
  return Array.from({length: count}, (_, index) =>
    `<p>${label} paragraph ${index + 1}: ordinary sentence text giving the line a realistic width.</p>`).join('');
}

const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

async function createFixture(page) {
  return page.evaluate(async content => {
    const {NotesAPI} = await import('/static/js/modules/api-client.js');
    const ids = [];
    // createNote(null, '') inserts at the top, so create bottom-up.
    for (const html of content) {
      const note = await NotesAPI.createNote(null, '');
      await NotesAPI.saveNote(note.id, html, '');
      ids.push(note.id);
    }
    return ids;
  }, [
    ...Array.from({length: 12}, (_, index) => paragraphs(`Below ${12 - index}`, 3)),
    paragraphs('Long', 60),
    ...Array.from({length: 12}, (_, index) => paragraphs(`Above ${12 - index}`, 3)),
  ]);
}

async function deleteFixture(page, ids) {
  await page.evaluate(async ids => {
    const {NotesAPI} = await import('/static/js/modules/api-client.js');
    for (const id of ids) await NotesAPI.deleteNote(id);
  }, ids);
}

async function reload(page) {
  await page.reload();
  await page.waitForSelector('[data-app-ready="true"]');
  await page.waitForNetworkIdle({idleTime: 300});
}

async function setCollapsed(page, noteId, collapsed) {
  await page.evaluate(async ({noteId, collapsed}) => {
    const {NotesAPI} = await import('/static/js/modules/api-client.js');
    if (collapsed) await NotesAPI.collapseNote(noteId);
    else await NotesAPI.expandNote(noteId);
  }, {noteId, collapsed});
  await reload(page);
}

async function runPaletteCommand(page, query) {
  await page.keyboard.down('Meta');
  await page.keyboard.press('/');
  await page.keyboard.up('Meta');
  await pause(400);
  await page.keyboard.type(query);
  await pause(300);
  await page.keyboard.press('Enter');
  await page.waitForNetworkIdle({idleTime: 300});
}

// Screen Y of the paragraph whose text starts with `prefix` (edit or view DOM).
function paragraphY(page, prefix) {
  return page.evaluate(prefix => {
    const paragraph = [...document.querySelectorAll('#notes-container p')].find(p => p.textContent.trim().startsWith(prefix));
    return paragraph ? paragraph.getBoundingClientRect().top : null;
  }, prefix);
}

function layout(page, noteId) {
  return page.evaluate(noteId => {
    const rect = document.querySelector(`[data-note-id="${noteId}"]`).getBoundingClientRect();
    const controls = document.querySelector('.controls').getBoundingClientRect();
    return {noteTop: rect.top, headerBottom: controls.bottom, viewportHeight: window.innerHeight};
  }, noteId);
}

async function scrollParagraphTo(page, prefix, viewportY) {
  const y = await paragraphY(page, prefix);
  assert.notEqual(y, null, `paragraph "${prefix}" not found`);
  await page.evaluate(delta => window.scrollBy(0, delta), y - viewportY);
  await pause(250);
}

async function waitForEditing(page, noteId) {
  await page.waitForFunction(async noteId => {
    const {ModeContextInstance: mode} = await import('/static/js/modules/mode-manager/mode-context.js');
    return mode.isEditing && mode.currentNoteId === noteId && !mode.isLoading;
  }, {}, noteId);
  await pause(400);
}

// Click near the start of a paragraph (page.click() would aim at the centre of
// a tall element and scroll to reach it).
async function clickParagraph(page, prefix) {
  const point = await page.evaluate(prefix => {
    const paragraph = [...document.querySelectorAll('#notes-container p')].find(p => p.textContent.trim().startsWith(prefix));
    const rect = paragraph.getBoundingClientRect();
    return {x: rect.left + 30, y: rect.top + Math.min(10, rect.height / 2)};
  }, prefix);
  await page.mouse.click(point.x, point.y);
}

// Escape, sampling the tracked paragraph's position on every frame until settled.
async function exitWithEscape(page, prefix) {
  await page.evaluate(prefix => {
    window.__scrollSamples = [];
    const sample = () => {
      const paragraph = [...document.querySelectorAll('#notes-container p')].find(p => p.textContent.trim().startsWith(prefix));
      if (paragraph) window.__scrollSamples.push(paragraph.getBoundingClientRect().top);
      if (window.__scrollSamples.length < 120) requestAnimationFrame(sample);
    };
    requestAnimationFrame(sample);
  }, prefix);
  await page.keyboard.press('Escape');
  await page.waitForFunction(async () => {
    const {ModeContextInstance: mode} = await import('/static/js/modules/mode-manager/mode-context.js');
    return !mode.isEditing && !mode.isLoading;
  });
  await pause(SETTLE_MS);
  return page.evaluate(() => window.__scrollSamples);
}

function assertStayed(label, before, after, samples) {
  assert.notEqual(after, null, `${label}: tracked paragraph missing after leaving edit mode`);
  assert.ok(Math.abs(after - before) <= TOLERANCE_PX,
    `${label}: the text should stay where it was on screen: y=${Math.round(before)} -> ${Math.round(after)}`);
  if (samples) {
    const worst = Math.max(...samples.map(y => Math.abs(y - before)));
    assert.ok(worst <= TOLERANCE_PX,
      `${label}: no frame may show a jump while leaving edit mode (worst frame was ${Math.round(worst)}px off)`);
  }
}

async function caretVisibleCase(page, longId, label) {
  // Entering edit mode puts the caret at the end of the note; typing scrolls there.
  await scrollParagraphTo(page, 'Long paragraph 1:', 200);
  await clickParagraph(page, 'Long paragraph 1:');
  await waitForEditing(page, longId);
  await page.keyboard.type(' ');
  await pause(400);
  const tracked = 'Long paragraph 60:';
  const before = await paragraphY(page, tracked);
  const samples = await exitWithEscape(page, tracked);
  assertStayed(`${label}, caret on screen`, before, await paragraphY(page, tracked), samples);
}

async function readingLineCase(page, longId, label) {
  await scrollParagraphTo(page, 'Long paragraph 1:', 200);
  await clickParagraph(page, 'Long paragraph 1:');
  await waitForEditing(page, longId);
  // The caret is at the note's end, off screen; read somewhere in the middle.
  const {headerBottom, viewportHeight} = await layout(page, longId);
  const readingLineY = headerBottom + (viewportHeight - headerBottom) / 3;
  await scrollParagraphTo(page, 'Long paragraph 30:', readingLineY - 5);
  const before = await paragraphY(page, 'Long paragraph 30:');
  await exitWithEscape(page, 'Long paragraph 30:');
  assertStayed(`${label}, caret off screen (reading line)`, before, await paragraphY(page, 'Long paragraph 30:'), null);
}

export async function checkExitEditScroll(page) {
  const ids = await createFixture(page);
  const longId = ids[12];
  // Run every case and report all failures together.
  const failures = [];
  const check = async (name, body) => {
    try {
      await body();
    } catch (error) {
      if (!(error instanceof assert.AssertionError)) throw error;
      failures.push(`${name}: ${error.message}`);
      if (await page.evaluate(async () => (await import('/static/js/modules/mode-manager/mode-context.js')).ModeContextInstance.isEditing)) {
        await page.keyboard.press('Escape');
        await pause(500);
      }
    }
  };
  try {
    // Expanded note: the caret's text, then the reading line, stay put.
    await setCollapsed(page, longId, false);
    await check('expanded, caret', () => caretVisibleCase(page, longId, 'expanded note'));
    await check('expanded, reading line', () => readingLineCase(page, longId, 'expanded note'));

    // Collapsed note with an edit: it is shown collapsed again after saving
    // (edits do not change a note's saved collapse state), so the collapsed row
    // stays in view, just below the search controls when it would be above them.
    await check('collapsed with edit', async () => {
      await setCollapsed(page, longId, true);
      await scrollParagraphTo(page, 'Long paragraph 1:', 200);
      await clickParagraph(page, 'Long paragraph 1:');
      await waitForEditing(page, longId);
      await page.keyboard.type(' ');
      await pause(400);
      await exitWithEscape(page, 'Long paragraph 1:');
      const collapsedLayout = await layout(page, longId);
      assert.ok(Math.abs(collapsedLayout.noteTop - (collapsedLayout.headerBottom + 8)) <= 4,
        `collapsed note with an edit: the collapsed row should sit just below the search controls ` +
        `(y≈${Math.round(collapsedLayout.headerBottom + 8)}), got y=${Math.round(collapsedLayout.noteTop)}`);
    });

    // Collapsed note without an edit: it collapses again; the collapsed row
    // stays in view, just below the search controls when it would be above them.
    await check('collapsed without edit', async () => {
    await setCollapsed(page, longId, true);
    await scrollParagraphTo(page, 'Long paragraph 1:', 200);
    await clickParagraph(page, 'Long paragraph 1:');
    await waitForEditing(page, longId);
    await page.evaluate(() => window.scrollBy(0, 1500));
    await pause(300);
    await exitWithEscape(page, 'Long paragraph 1:');
    const collapsedLayout = await layout(page, longId);
    assert.ok(Math.abs(collapsedLayout.noteTop - (collapsedLayout.headerBottom + 8)) <= 4,
      `collapsed note without an edit: the collapsed row should sit just below the search controls ` +
      `(y≈${Math.round(collapsedLayout.headerBottom + 8)}), got y=${Math.round(collapsedLayout.noteTop)}`);
    });

    // Sorted by content volume: typing changes the note's volume, so saving may
    // re-sort it; the caret's text still stays put.
    await setCollapsed(page, longId, false);
    await runPaletteCommand(page, 'Sort order: Content volume');
    await check('content-volume sort', () => caretVisibleCase(page, longId, 'content-volume sort'));
    await runPaletteCommand(page, 'Sort order: Normal');

    // Clicking another note while editing keeps the clicked text under the pointer.
    await check('click another note', async () => {
    await reload(page);
    await scrollParagraphTo(page, 'Long paragraph 1:', 200);
    await clickParagraph(page, 'Long paragraph 1:');
    await waitForEditing(page, longId);
    await scrollParagraphTo(page, 'Below 1 paragraph 1:', 400);
    const clickedBefore = await paragraphY(page, 'Below 1 paragraph 1:');
    await clickParagraph(page, 'Below 1 paragraph 1:');
    await waitForEditing(page, ids[11]);
    await pause(SETTLE_MS);
    assertStayed('clicking another note while editing', clickedBefore, await paragraphY(page, 'Below 1 paragraph 1:'), null);
    await page.keyboard.press('Escape');
    await pause(500);
    });
    assert.deepEqual(failures, [], `exit-edit scroll failures:\n${failures.join('\n')}`);
  } finally {
    await deleteFixture(page, ids);
    await reload(page);
  }
}
