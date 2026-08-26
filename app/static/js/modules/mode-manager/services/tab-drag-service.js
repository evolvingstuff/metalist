function validateTabId(tabId, fieldName) {
    if (typeof tabId !== 'string' || tabId.length === 0) {
        throw new Error(`${fieldName} must be a non-empty string`);
    }
}

export function reorderTabOrderToHoveredSlot(tabOrder, draggedTabId, hoveredTabId) {
    if (!Array.isArray(tabOrder) || tabOrder.length === 0) {
        throw new Error('tabOrder must be a non-empty array');
    }
    validateTabId(draggedTabId, 'draggedTabId');
    validateTabId(hoveredTabId, 'hoveredTabId');

    const uniqueTabIds = new Set(tabOrder);
    if (uniqueTabIds.size !== tabOrder.length) {
        throw new Error('tabOrder must not contain duplicates');
    }
    for (let index = 0; index < tabOrder.length; index += 1) {
        validateTabId(tabOrder[index], `tabOrder[${index}]`);
    }

    const draggedIndex = tabOrder.indexOf(draggedTabId);
    if (draggedIndex === -1) {
        throw new Error(`tabOrder missing draggedTabId: ${draggedTabId}`);
    }
    const hoveredIndex = tabOrder.indexOf(hoveredTabId);
    if (hoveredIndex === -1) {
        throw new Error(`tabOrder missing hoveredTabId: ${hoveredTabId}`);
    }
    if (draggedIndex === hoveredIndex) {
        throw new Error('draggedTabId and hoveredTabId must identify different tabs');
    }

    const nextOrder = tabOrder.slice();
    nextOrder.splice(draggedIndex, 1);
    nextOrder.splice(hoveredIndex, 0, draggedTabId);

    if (nextOrder.length !== tabOrder.length) {
        throw new Error('tab reorder changed the number of tabs');
    }
    return nextOrder;
}
