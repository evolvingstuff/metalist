const MENU_PADDING_PX = 8;
const SVG_NAMESPACE = 'http://www.w3.org/2000/svg';
const CONTEXT_MENU_ICONS = {
    add_child: [
        'M6 4h8',
        'M10 8V2',
        'M6 18h12',
        'M12 14v8',
        'M4 10v4c0 2.2 1.8 4 4 4h4',
    ],
    add_sibling: [
        'M12 4v8',
        'M8 8h8',
        'M5 18h14',
    ],
    arrow_top: [
        'M12 20V5',
        'M6 11l6-6 6 6',
        'M5 4h14',
    ],
    copy: [
        'M8 8h10v12H8z',
        'M6 16H4V4h10v2',
    ],
    download: [
        'M12 4v10',
        'M7 10l5 5 5-5',
        'M5 20h14',
    ],
    external: [
        'M14 4h6v6',
        'M10 14 20 4',
        'M18 13v7H4V6h7',
    ],
    image: [
        'M4 6h16v12H4z',
        'M8 10h.01',
        'M4 16l4-4 3 3 3-4 6 5',
    ],
    style: [
        'M4 17.5V20h2.5L18 8.5 15.5 6z',
        'M14 4l2-2 6 6-2 2',
        'M3 3l3 3',
    ],
    link: [
        'M9 12a3 3 0 0 1 3-3h3',
        'M15 12a3 3 0 0 1-3 3H9',
        'M8 8H7a4 4 0 0 0 0 8h1',
        'M16 8h1a4 4 0 0 1 0 8h-1',
    ],
    link_child: [
        'M9 8h4a3 3 0 0 1 0 6H9',
        'M8 11h6',
        'M6 4v10c0 2.2 1.8 4 4 4h4',
        'M14 16l2 2-2 2',
    ],
    paste: [
        'M8 5h8',
        'M9 3h6v4H9z',
        'M6 6h12v14H6z',
    ],
    paste_child: [
        'M8 5h8',
        'M9 3h6v4H9z',
        'M6 6h12v9H6z',
        'M10 19h8',
        'M14 15v8',
    ],
    tag: [
        'M4 4h7l9 9-7 7-9-9z',
        'M8 8h.01',
    ],
    trash: [
        'M5 7h14',
        'M9 7V4h6v3',
        'M8 10v9',
        'M12 10v9',
        'M16 10v9',
    ],
    zoom: [
        'M10 17a7 7 0 1 1 0-14 7 7 0 0 1 0 14z',
        'M15 15l5 5',
        'M10 7v6',
        'M7 10h6',
    ],
};

let menuElement = null;
let submenuElement = null;
let activeItems = [];
let activeSubmenuItems = [];
let activeSubmenuParent = null;
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

function ensureSubmenuElement() {
    if (submenuElement) {
        return submenuElement;
    }

    const element = document.createElement('div');
    element.id = 'context-submenu';
    element.className = 'context-menu context-menu-submenu';
    element.setAttribute('role', 'menu');
    element.style.display = 'none';
    document.body.appendChild(element);

    element.addEventListener('click', handleMenuClick);
    submenuElement = element;
    return element;
}

function handleMenuClick(event) {
    if (!event) {
        throw new Error('handleMenuClick called without event');
    }
    const target = event.target;
    if (!(target instanceof Element)) {
        return;
    }

    const button = target.closest('.context-menu-item');
    if (!button) {
        return;
    }

    const menuLevel = button.dataset.menuLevel;
    if (menuLevel !== 'root' && menuLevel !== 'submenu') {
        throw new Error('Context menu item missing menu level');
    }
    const items = menuLevel === 'submenu' ? activeSubmenuItems : activeItems;
    const indexAttr = button.dataset.index;
    if (typeof indexAttr !== 'string' || indexAttr.trim() === '') {
        throw new Error('Context menu item missing index');
    }
    const index = Number.parseInt(indexAttr, 10);
    if (!Number.isInteger(index) || index < 0 || index >= items.length) {
        throw new Error(`Context menu item index invalid: ${indexAttr}`);
    }

    const item = items[index];
    if (!item) {
        throw new Error('Context menu item missing in active items');
    }
    if (!item.enabled) {
        return;
    }
    if (Array.isArray(item.submenu)) {
        if (menuLevel !== 'root') {
            throw new Error('Nested context submenus are not supported');
        }
        event.preventDefault();
        event.stopPropagation();
        showSubmenuForButton(button, item.submenu);
        return;
    }
    if (typeof item.onSelect !== 'function') {
        throw new Error('Context menu leaf item missing onSelect handler');
    }

    event.preventDefault();
    event.stopPropagation();
    hideContextMenu();
    item.onSelect();
}

function validateMenuItems(items, depth) {
    if (!Number.isInteger(depth) || depth < 0) {
        throw new Error('validateMenuItems requires non-negative depth');
    }
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
        const hasSubmenu = item.submenu !== undefined;
        if (hasSubmenu) {
            if (depth > 0) {
                throw new Error('Nested context submenus are not supported');
            }
            if (item.onSelect !== undefined) {
                throw new Error(`Context menu submenu item ${index} cannot have onSelect`);
            }
            validateMenuItems(item.submenu, depth + 1);
        } else if (typeof item.onSelect !== 'function') {
            throw new Error(`Context menu item ${index} missing onSelect handler`);
        }
        if (item.separated !== undefined && typeof item.separated !== 'boolean') {
            throw new Error(`Context menu item ${index} separated must be boolean when provided`);
        }
        if (item.icon !== undefined && typeof item.icon !== 'string') {
            throw new Error(`Context menu item ${index} icon must be string when provided`);
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

function resolveSubmenuPosition(parentRect, submenuRect) {
    if (!parentRect || !submenuRect) {
        throw new Error('resolveSubmenuPosition requires menu rectangles');
    }
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    if (typeof viewportWidth !== 'number' || typeof viewportHeight !== 'number') {
        throw new Error('Viewport dimensions missing');
    }

    let left = parentRect.right - 1;
    if (left + submenuRect.width + MENU_PADDING_PX > viewportWidth) {
        left = parentRect.left - submenuRect.width + 1;
    }
    let top = parentRect.top - 6;
    if (top + submenuRect.height + MENU_PADDING_PX > viewportHeight) {
        top = viewportHeight - submenuRect.height - MENU_PADDING_PX;
    }
    if (left < MENU_PADDING_PX) {
        left = MENU_PADDING_PX;
    }
    if (top < MENU_PADDING_PX) {
        top = MENU_PADDING_PX;
    }
    return { left, top };
}

function renderMenuItems(menu, items, menuLevel) {
    if (menuLevel !== 'root' && menuLevel !== 'submenu') {
        throw new Error('renderMenuItems requires a valid menu level');
    }
    menu.innerHTML = '';
    items.forEach((item, index) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'context-menu-item';
        button.dataset.index = String(index);
        button.dataset.menuLevel = menuLevel;
        button.setAttribute('role', 'menuitem');

        const icon = createMenuIcon(item.icon);
        if (icon) {
            button.appendChild(icon);
        }

        const label = document.createElement('span');
        label.className = 'context-menu-item-label';
        label.textContent = item.label;
        button.appendChild(label);

        if (Array.isArray(item.submenu)) {
            button.classList.add('has-submenu');
            button.setAttribute('aria-haspopup', 'menu');
            button.setAttribute('aria-expanded', 'false');
            const arrow = document.createElement('span');
            arrow.className = 'context-menu-submenu-arrow';
            arrow.textContent = '›';
            arrow.setAttribute('aria-hidden', 'true');
            button.appendChild(arrow);
        }

        if (item.separated === true) {
            button.classList.add('is-separated');
        }
        if (!item.enabled) {
            button.disabled = true;
            button.classList.add('is-disabled');
        }
        if (menuLevel === 'root') {
            button.addEventListener('mouseenter', () => {
                if (Array.isArray(item.submenu) && item.enabled) {
                    showSubmenuForButton(button, item.submenu);
                    return;
                }
                hideSubmenu();
            });
            button.addEventListener('focus', () => {
                if (Array.isArray(item.submenu) && item.enabled) {
                    showSubmenuForButton(button, item.submenu);
                    return;
                }
                hideSubmenu();
            });
        }
        menu.appendChild(button);
    });
}

function showSubmenuForButton(parentButton, submenuItems) {
    if (!(parentButton instanceof HTMLButtonElement)) {
        throw new Error('showSubmenuForButton requires parent button');
    }
    validateMenuItems(submenuItems, 1);

    hideSubmenu();
    const submenu = ensureSubmenuElement();
    activeSubmenuItems = submenuItems;
    activeSubmenuParent = parentButton;
    parentButton.classList.add('is-submenu-open');
    parentButton.setAttribute('aria-expanded', 'true');

    renderMenuItems(submenu, submenuItems, 'submenu');
    submenu.style.display = 'block';
    submenu.style.visibility = 'hidden';
    submenu.style.left = '0px';
    submenu.style.top = '0px';

    const parentRect = parentButton.getBoundingClientRect();
    const submenuRect = submenu.getBoundingClientRect();
    const resolved = resolveSubmenuPosition(parentRect, submenuRect);
    submenu.style.left = `${resolved.left}px`;
    submenu.style.top = `${resolved.top}px`;
    submenu.style.visibility = 'visible';
    submenu.classList.add('is-visible');
}

function hideSubmenu() {
    if (activeSubmenuParent) {
        activeSubmenuParent.classList.remove('is-submenu-open');
        activeSubmenuParent.setAttribute('aria-expanded', 'false');
    }
    activeSubmenuParent = null;
    activeSubmenuItems = [];
    if (!submenuElement) {
        return;
    }
    submenuElement.classList.remove('is-visible');
    submenuElement.style.display = 'none';
    submenuElement.style.visibility = 'hidden';
    submenuElement.innerHTML = '';
}

function createMenuIcon(iconName) {
    if (typeof iconName !== 'string' || iconName.length === 0) {
        return null;
    }
    const paths = CONTEXT_MENU_ICONS[iconName];
    if (!Array.isArray(paths)) {
        throw new Error(`Unknown context menu icon: ${iconName}`);
    }

    const svg = document.createElementNS(SVG_NAMESPACE, 'svg');
    svg.classList.add('context-menu-item-icon');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');

    paths.forEach((pathData) => {
        const path = document.createElementNS(SVG_NAMESPACE, 'path');
        path.setAttribute('d', pathData);
        svg.appendChild(path);
    });
    return svg;
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
    if (!(target instanceof Element)) {
        hideContextMenu();
        return;
    }
    const menu = menuElement;
    if (!menu) {
        hideContextMenu();
        return;
    }
    if (menu.contains(target) || (submenuElement && submenuElement.contains(target))) {
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
    if (!(target instanceof Element)) {
        hideContextMenu();
        return;
    }
    const menu = menuElement;
    if (!menu) {
        hideContextMenu();
        return;
    }
    if (menu.contains(target) || (submenuElement && submenuElement.contains(target))) {
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
    validateMenuItems(items, 0);

    const menu = ensureMenuElement();
    activeItems = items;
    activeOnClose = payload.onClose;

    hideSubmenu();
    renderMenuItems(menu, items, 'root');
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
    hideSubmenu();
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
