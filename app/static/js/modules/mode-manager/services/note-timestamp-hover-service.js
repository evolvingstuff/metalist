export function formatNoteTimestamp(isoTimestamp, options) {
    if (typeof isoTimestamp !== 'string' || isoTimestamp.length === 0) {
        throw new Error('formatNoteTimestamp requires a non-empty ISO timestamp');
    }
    if (!options || typeof options !== 'object' || Array.isArray(options)) {
        throw new Error('formatNoteTimestamp requires options object');
    }

    const timestampMilliseconds = Date.parse(isoTimestamp);
    if (!Number.isFinite(timestampMilliseconds)) {
        throw new Error(`formatNoteTimestamp received invalid ISO timestamp: ${isoTimestamp}`);
    }

    let locale;
    if (Object.prototype.hasOwnProperty.call(options, 'locale')) {
        if (typeof options.locale !== 'string' || options.locale.length === 0) {
            throw new Error('formatNoteTimestamp locale must be a non-empty string');
        }
        locale = options.locale;
    }

    const formatOptions = {
        dateStyle: 'medium',
        timeStyle: 'short',
    };
    if (Object.prototype.hasOwnProperty.call(options, 'timeZone')) {
        if (typeof options.timeZone !== 'string' || options.timeZone.length === 0) {
            throw new Error('formatNoteTimestamp timeZone must be a non-empty string');
        }
        formatOptions.timeZone = options.timeZone;
    }

    return new Intl.DateTimeFormat(locale, formatOptions).format(
        new Date(timestampMilliseconds),
    );
}

export function formatBrowserNoteTimestamp(isoTimestamp) {
    return formatNoteTimestamp(isoTimestamp, {});
}

export function syncNoteTimestampDataset(noteElement, metadata, formatTimestamp) {
    if (!noteElement || typeof noteElement !== 'object' || !noteElement.dataset) {
        throw new Error('syncNoteTimestampDataset requires an element with a dataset');
    }
    if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) {
        throw new Error('syncNoteTimestampDataset requires metadata object');
    }
    if (typeof metadata.createdAt !== 'string' || metadata.createdAt.length === 0) {
        throw new Error('syncNoteTimestampDataset requires metadata.createdAt');
    }
    if (typeof metadata.updatedAt !== 'string' || metadata.updatedAt.length === 0) {
        throw new Error('syncNoteTimestampDataset requires metadata.updatedAt');
    }
    if (typeof formatTimestamp !== 'function') {
        throw new Error('syncNoteTimestampDataset requires formatTimestamp function');
    }

    noteElement.dataset.noteCreatedDisplay = formatTimestamp(metadata.createdAt);
    noteElement.dataset.noteUpdatedDisplay = formatTimestamp(metadata.updatedAt);
}
