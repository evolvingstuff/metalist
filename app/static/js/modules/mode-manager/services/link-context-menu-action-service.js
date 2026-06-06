function requireLinkContext(linkContext) {
    if (linkContext === null || typeof linkContext !== 'object') {
        throw new Error('Link action requires linkContext object');
    }
    const href = linkContext.href;
    if (typeof href !== 'string') {
        throw new Error('Link action requires linkContext.href');
    }
    if (href.length === 0) {
        throw new Error('Link action requires linkContext.href');
    }
}

function isHashOnlyHref(rawHref) {
    if (typeof rawHref !== 'string') {
        throw new Error('isHashOnlyHref requires rawHref string');
    }
    return rawHref.trim().startsWith('#');
}

export function resolveLinkContextFromElement(element) {
    if (!(element instanceof HTMLElement)) {
        return null;
    }
    const anchor = element.closest('a[href]');
    if (!(anchor instanceof HTMLAnchorElement)) {
        return null;
    }

    const rawHref = anchor.getAttribute('href');
    if (typeof rawHref !== 'string' || rawHref.trim().length === 0) {
        return null;
    }
    if (isHashOnlyHref(rawHref)) {
        return null;
    }

    const resolvedHref = typeof anchor.href === 'string' && anchor.href.length > 0
        ? anchor.href
        : rawHref.trim();
    if (resolvedHref.length === 0) {
        return null;
    }

    return {
        href: resolvedHref,
    };
}

export async function copyLinkToClipboard(linkContext) {
    requireLinkContext(linkContext);
    const clipboard = navigator.clipboard;
    if (!clipboard || typeof clipboard.writeText !== 'function') {
        throw new Error('navigator.clipboard.writeText is required to copy links');
    }
    await clipboard.writeText(linkContext.href);
}

export async function openLinkInNewTabFromContext(linkContext) {
    requireLinkContext(linkContext);
    window.open(linkContext.href, '_blank', 'noopener,noreferrer');
}
