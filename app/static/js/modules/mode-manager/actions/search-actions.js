import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { actionDeselectNote } from './selection-actions.js';

export async function actionEnterSearchMode() {
    Logger.logAction('enterSearchMode');

    if (ModeContext.isEditing) {
        await actionDeselectNote();
    }

    // Reference navigation and keyboard shortcuts can enter search mode while it is already active.
    if (!ModeContext.isSearching) {
        ModeContext.setSearching(true);
    }

    ModeContext.validate();
}

export function actionExitSearchMode() {
    Logger.logAction('exitSearchMode');

    // Multiple event paths use exitSearchMode as cleanup after selecting or opening notes.
    if (ModeContext.isSearching) {
        ModeContext.setSearching(false);
    }

    ModeContext.validate();
}
