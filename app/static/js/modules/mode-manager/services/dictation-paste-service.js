import { ApplicationState } from '../../application-state.js';
import { NotesAPI } from '../../api-client.js';
import { padForInsertion } from './dictation-paste-padding.js';

// Pasting into the search bar or the tag bar turns dictated text (for example
// from Superwhisper: "Neural network, neural network. Neural-Dash Network.")
// into the user's tags. The server holds the tag list, so it does the cleanup
// (app/services/dictation_cleanup.py, docs/ui/dictation-paste.md). Typing is
// never changed, only pastes.
//
// The pasted text is first inserted as is, then replaced with the cleaned text,
// as two native edits: one Cmd+Z brings back exactly what was pasted.
const moduleState = ApplicationState.createFields('dictation-paste-service', {
    rawInsertInProgress: false,
});

// True while the pasted text is being inserted as is: input handlers leave it
// alone (no enforcement rewrite, which would break native undo, and no search).
export function isDictationRawInsertInProgress() {
    return moduleState.rawInsertInProgress;
}

function requireTarget(target) {
    if (target !== 'search' && target !== 'tags') {
        throw new Error(`Unknown dictation paste target: ${target}`);
    }
}

function insertAsNativeEdit(input, text) {
    let inserted;
    if (text === '') {
        inserted = document.execCommand('delete', false);
    } else {
        inserted = document.execCommand('insertText', false, text);
    }
    if (!inserted) {
        throw new Error('The browser refused to insert pasted text');
    }
}

export async function pasteDictatedText(input, target, pastedText) {
    if (!(input instanceof HTMLInputElement)) {
        throw new TypeError('pasteDictatedText requires an input element');
    }
    requireTarget(target);
    if (typeof pastedText !== 'string') {
        throw new TypeError('pasteDictatedText requires the pasted text');
    }
    // An input holds one line.
    const raw = pastedText.replace(/[\r\n]+/g, ' ');
    const start = input.selectionStart;
    const end = input.selectionEnd;
    if (typeof start !== 'number' || typeof end !== 'number') {
        throw new Error('Paste target input has no selection');
    }
    // The field without the text being replaced: tags already there are not added again.
    const response = await NotesAPI.cleanDictationPaste(raw, target, `${input.value.slice(0, start)} ${input.value.slice(end)}`);
    if (!response || typeof response.text !== 'string') {
        throw new Error('Dictation paste cleanup returned no text');
    }
    input.focus();
    // Insert where the selection is now (the user may have moved it meanwhile).
    const insertStart = input.selectionStart;
    const textBefore = input.value.slice(0, insertStart);
    const textAfter = input.value.slice(input.selectionEnd);
    const rawPadded = padForInsertion(raw, textBefore, textAfter);
    // A failed insert throws (fatal), so the flag needs no other reset.
    moduleState.rawInsertInProgress = true;
    insertAsNativeEdit(input, rawPadded);
    moduleState.rawInsertInProgress = false;
    input.setSelectionRange(insertStart, insertStart + rawPadded.length);
    insertAsNativeEdit(input, padForInsertion(response.text, textBefore, textAfter));
}

// Paste listener for the search input and the tag bar input.
export function handleDictationPasteEvent(event, target) {
    if (!event || !event.clipboardData) {
        throw new Error('Dictation paste requires a paste event with clipboard data');
    }
    requireTarget(target);
    const pastedText = event.clipboardData.getData('text/plain');
    if (pastedText === '') {
        return;
    }
    event.preventDefault();
    void pasteDictatedText(event.target, target, pastedText);
}
