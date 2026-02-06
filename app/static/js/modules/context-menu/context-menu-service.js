const MENU_PADDING_PX = 8;

let menuElement = null;
let activeItems = [];
let activeOnClose = null;
let initialized = false;

function ensureMenuElement() {
    if (menuElement) {
        return menuElement;
    }

    const element = document.createElement('div');
    element.id = 'context-menu';
    element.className = 'context-menu';
    element.setAttribute('role', 'menu');
    element.style.display = 'none';
    document.body.appendChild(element);

    element.addEventListener('click', handleMenuClick);
    menuElement = element;
    return element;
}

function handleMenuClick(event) {
    if (!event) {
        throw new Error('handleMenuClick called without event');
    }
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }

    const button = target.closest('.context-menu-item');
    if (!button) {
        return;
    }

    const indexAttr = button.dataset.index;
    if (typeof indexAttr !== 'string' || indexAttr.trim() === '') {
        throw new Error('Context menu item missing index');
    }
    const index = Number.parseInt(indexAttr, 10);
    if (!Number.isInteger(index) || index < 0 || index >= activeItems.length) {
        throw new Error(`Context menu item index invalid: ${indexAttr}`);
    }

    const item = activeItems[index];
    if (!item) {
        throw new Error('Context menu item missing in active items');
    }
    if (!item.enabled) {
        return;
    }
    if (typeof item.onSelect !== 'function') {
        throw new Error('Context menu item missing onSelect handler');
    }

    event.preventDefault();
    event.stopPropagation();
    hideContextMenu();
    item.onSelect();
}

function validateMenuItems(items) {
    if (!Array.isArray(items) || items.length === 0) {
        throw new Error('Context menu requires non-empty items array');
    }

    items.forEach((item, index) => {
        if (!item || typeof item !== 'object') {
            throw new Error(`Context menu item ${index} must be an object`);
        }
        if (typeof item.id !== 'string' || item.id.trim() === '') {
            throw new Error(`Context menu item ${index} missing id`);
        }
        if (typeof item.label !== 'string' || item.label.trim() === '') {
            throw new Error(`Context menu item ${index} missing label`);
        }
        if (typeof item.enabled !== 'boolean') {
            throw new Error(`Context menu item ${index} missing enabled boolean`);
        }
        if (typeof item.onSelect !== 'function') {
            throw new Error(`Context menu item ${index} missing onSelect handler`);
        }
    });
}

function resolvePosition(position, menuRect) {
    if (!position || typeof position !== 'object') {
        throw new Error('resolvePosition requires position object');
    }
    if (!menuRect) {
        throw new Error('resolvePosition requires menuRect');
    }

    const x = position.x;
    const y = position.y;
    if (typeof x !== 'number' || typeof y !== 'number') {
        throw new Error('Context menu position requires numeric x/y');
    }

    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    if (typeof viewportWidth !== 'number' || typeof viewportHeight !== 'number') {
        throw new Error('Viewport dimensions missing');
    }

    let left = x;
    let top = y;

    if (left + menuRect.width + MENU_PADDING_PX > viewportWidth) {
        left = viewportWidth - menuRect.width - MENU_PADDING_PX;
    }
    if (top + menuRect.height + MENU_PADDING_PX > viewportHeight) {
        top = viewportHeight - menuRect.height - MENU_PADDING_PX;
    }

    if (left < MENU_PADDING_PX) {
        left = MENU_PADDING_PX;
    }
    if (top < MENU_PADDING_PX) {
        top = MENU_PADDING_PX;
    }

    return { left, top };
}

function renderMenuItems(menu, items) {
    menu.innerHTML = '';
    items.forEach((item, index) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'context-menu-item';
        button.textContent = item.label;
        button.dataset.index = String(index);
        button.setAttribute('role', 'menuitem');
        if (!item.enabled) {
            button.disabled = true;
            button.classList.add('is-disabled');
        }
        menu.appendChild(button);
    });
}

function isContextMenuOpen() {
    return Boolean(menuElement && menuElement.classList.contains('is-visible'));
}

function handleGlobalMouseDown(event) {
    if (!isContextMenuOpen()) {
        return;
    }
    if (!event) {
        throw new Error('handleGlobalMouseDown called without event');
    }
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        hideContextMenu();
        return;
    }
    const menu = menuElement;
    if (!menu) {
        hideContextMenu();
        return;
    }
    if (menu.contains(target)) {
        return;
    }
    hideContextMenu();
}

function handleGlobalContextMenu(event) {
    if (!isContextMenuOpen()) {
        return;
    }
    if (!event) {
        throw new Error('handleGlobalContextMenu called without event');
    }
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        hideContextMenu();
        return;
    }
    const menu = menuElement;
    if (!menu) {
        hideContextMenu();
        return;
    }
    if (menu.contains(target)) {
        return;
    }
    hideContextMenu();
}

function handleGlobalKeyDown(event) {
    if (!isContextMenuOpen()) {
        return;
    }
    if (!event) {
        throw new Error('handleGlobalKeyDown called without event');
    }
    if (event.key === 'Escape') {
        hideContextMenu();
    }
}

function handleGlobalScroll() {
    if (isContextMenuOpen()) {
        hideContextMenu();
    }
}

function handleGlobalResize() {
    if (isContextMenuOpen()) {
        hideContextMenu();
    }
}

export function initContextMenuService() {
    if (initialized) {
        return;
    }

    document.addEventListener('mousedown', handleGlobalMouseDown, { capture: true });
    document.addEventListener('contextmenu', handleGlobalContextMenu, { capture: true });
    document.addEventListener('keydown', handleGlobalKeyDown, { capture: true });
    document.addEventListener('scroll', handleGlobalScroll, { capture: true });
    window.addEventListener('resize', handleGlobalResize);
    initialized = true;
}

export function showContextMenu(payload) {
    if (!payload || typeof payload !== 'object') {
        throw new Error('showContextMenu requires payload object');
    }

    const items = payload.items;
    const position = payload.position;
    validateMenuItems(items);

    const menu = ensureMenuElement();
    activeItems = items;
    activeOnClose = payload.onClose;

    renderMenuItems(menu, items);
    menu.style.display = 'block';
    menu.style.visibility = 'hidden';
    menu.style.left = '0px';
    menu.style.top = '0px';

    const rect = menu.getBoundingClientRect();
    const resolved = resolvePosition(position, rect);

    menu.style.left = `${resolved.left}px`;
    menu.style.top = `${resolved.top}px`;
    menu.style.visibility = 'visible';
    menu.classList.add('is-visible');
}

export function hideContextMenu() {
    if (!menuElement) {
        return;
    }
    if (menuElement.classList.contains('is-visible')) {
        menuElement.classList.remove('is-visible');
    }
    menuElement.style.display = 'none';
    menuElement.style.visibility = 'hidden';
    menuElement.innerHTML = '';
    activeItems = [];

    const onClose = activeOnClose;
    activeOnClose = null;
    if (typeof onClose === 'function') {
        onClose();
    }
}
