import { ModeContextInstance as ModeContext } from '../mode-context.js';
import * as Logger from '../mode-logger.js';
import { deselectNote } from './selection-actions.js';

export async function enterSearchMode() {
    Logger.logAction('enterSearchMode');

    if (ModeContext.isEditing) {
        await deselectNote();
    }

    ModeContext.setSearching(true);

    ModeContext.validate();
}

export function exitSearchMode() {
    Logger.logAction('exitSearchMode');

    ModeContext.setSearching(false);

    ModeContext.validate();
}