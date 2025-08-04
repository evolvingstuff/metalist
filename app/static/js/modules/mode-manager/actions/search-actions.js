import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { actionDeselectNote } from './selection-actions.js';

export async function actionEnterSearchMode() {
    Logger.logAction('enterSearchMode');

    if (ModeContext.isEditing) {
        await actionDeselectNote();
    }

    if (!ModeContext.isSearching) {
        ModeContext.setSearching(true);
    }

    ModeContext.validate();
}

export function actionExitSearchMode() {
    Logger.logAction('exitSearchMode');

    ModeContext.setSearching(false);

    ModeContext.validate();
}