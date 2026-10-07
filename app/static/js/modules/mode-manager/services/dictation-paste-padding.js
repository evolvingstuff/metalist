// The separator (a space, a line break, or none for a one-tag field) so the
// inserted text never runs into the text around it.
export function padForInsertion(text, before, after, separator) {
    if (typeof text !== 'string' || typeof before !== 'string' || typeof after !== 'string') {
        throw new TypeError('padForInsertion requires strings');
    }
    if (separator !== ' ' && separator !== '\n' && separator !== '') {
        throw new TypeError('padForInsertion requires a space, a line break or no separator');
    }
    if (text === '' || separator === '') {
        return text;
    }
    let padded = text;
    if (before.length > 0 && !/\s$/.test(before)) {
        padded = `${separator}${padded}`;
    }
    if (after.length > 0 && !/^\s/.test(after)) {
        padded = `${padded}${separator}`;
    }
    return padded;
}
