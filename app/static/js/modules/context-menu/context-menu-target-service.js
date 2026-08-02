export function isContextMenuInteractionTarget(target) {
    if (!target || typeof target.closest !== 'function') {
        return false;
    }
    return target.closest('.context-menu') !== null;
}
