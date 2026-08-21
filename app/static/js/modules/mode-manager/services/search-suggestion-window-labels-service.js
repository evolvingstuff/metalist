export function formatSearchSuggestionWindowLabel(windowDays) {
    if (!Number.isInteger(windowDays) || windowDays < 1) {
        throw new Error('Search suggestion windowDays must be a positive integer');
    }
    if (windowDays === 1) {
        return 'today';
    }
    return `recent ${windowDays} days`;
}


export function buildSearchSuggestionWindowLabelMap(suggestions, personalizedSuggestions) {
    if (!Array.isArray(suggestions)) {
        throw new Error('Search suggestions must be an array');
    }
    if (!Array.isArray(personalizedSuggestions)) {
        throw new Error('Personalized search suggestions must be an array');
    }
    const visibleTags = new Set();
    for (const tag of suggestions) {
        if (typeof tag !== 'string' || tag.length === 0) {
            throw new Error('Search suggestions must contain non-empty strings');
        }
        if (visibleTags.has(tag)) {
            throw new Error('Search suggestions must be unique');
        }
        visibleTags.add(tag);
    }

    const labelByTag = new Map();
    for (const selection of personalizedSuggestions) {
        if (!selection || typeof selection !== 'object' || Array.isArray(selection)) {
            throw new Error('Personalized search suggestion must be an object');
        }
        if (typeof selection.tag !== 'string' || selection.tag.length === 0) {
            throw new Error('Personalized search suggestion tag must be non-empty');
        }
        if (!visibleTags.has(selection.tag)) {
            throw new Error('Personalized search suggestion must be visible');
        }
        if (labelByTag.has(selection.tag)) {
            throw new Error('Personalized search suggestion tags must be unique');
        }
        labelByTag.set(
            selection.tag,
            formatSearchSuggestionWindowLabel(selection.windowDays),
        );
    }
    return labelByTag;
}


export function buildSearchSuggestionPresentation(
    suggestions,
    personalizedSuggestions,
    showWindowLabels,
) {
    if (typeof showWindowLabels !== 'boolean') {
        throw new Error('showWindowLabels must be boolean');
    }
    const labelByTag = buildSearchSuggestionWindowLabelMap(
        suggestions,
        personalizedSuggestions,
    );
    return suggestions.map((tag) => {
        let windowLabel = '';
        if (showWindowLabels && labelByTag.has(tag)) {
            windowLabel = labelByTag.get(tag);
        }
        return { tag, windowLabel };
    });
}
