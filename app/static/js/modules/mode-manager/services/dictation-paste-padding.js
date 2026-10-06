// Spaces so the inserted text never runs into the tags around it.
export function padForInsertion(text, before, after) {
    if (typeof text !== 'string' || typeof before !== 'string' || typeof after !== 'string') {
        throw new TypeError('padForInsertion requires strings');
    }
    if (text === '') {
        return '';
    }
    let padded = text;
    if (before.length > 0 && !/\s$/.test(before)) {
        padded = ` ${padded}`;
    }
    if (after.length > 0 && !/^\s/.test(after)) {
        padded = `${padded} `;
    }
    return padded;
}
