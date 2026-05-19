import { NotesAPI } from '../../api-client.js';
import { ModeContextInstance as ModeContext } from '../mode-context.js';
import {
    DATE_FILTER_METRICS,
    enumerateIsoDates,
    getCountLevel,
    normalizeDateFilterMetric,
} from './date-filter-service.js';
import { setActiveDateFilter } from './date-filter-indicator-service.js';

let initialized = false;
let metric = DATE_FILTER_METRICS.CREATED;
let activityPayload = null;
let dragStartDate = null;
let dragHoverDate = null;
let shouldScrollToNewest = true;
let pointerListenersAttached = false;
let panelScrollListenerAttached = false;
let tooltipElement = null;

export function initializeRhsPanel() {
    if (initialized) {
        return;
    }
    initialized = true;
    metric = ModeContext.activeTabCalendarMetric;
    attachPointerListeners();
    attachPanelScrollListener();
    ModeContext.addListener((property) => {
        if (property === 'hoveredNoteId') {
            updateHoveredNoteDateHighlight();
        }
        if (property === 'activeTab') {
            metric = ModeContext.activeTabCalendarMetric;
            shouldScrollToNewest = ModeContext.activeTabCalendarScrollState.pinnedToNewest;
            void refreshRhsActivity({ preserveScroll: false });
        }
        if (property === 'searchQuery') {
            void refreshRhsActivity({ preserveScroll: false });
        }
    });
    renderRhsPanel();
    void refreshRhsActivity({ preserveScroll: false });
}

export async function refreshRhsActivity(options) {
    if (!options || typeof options !== 'object') {
        throw new Error('refreshRhsActivity requires an options object');
    }
    const preserveScroll = options.preserveScroll === true;
    if (!document.body.classList.contains('pref-show-rhs-panel')) {
        return;
    }
    const panelScrollTop = preserveScroll ? getRhsPanelScrollTop() : null;
    metric = ModeContext.activeTabCalendarMetric;
    const activeTabId = ModeContext.activeTabId;
    const searchQuery = typeof ModeContext.searchQuery === 'string' ? ModeContext.searchQuery : '';
    activityPayload = await NotesAPI.fetchActivity(searchQuery, metric, activeTabId);
    shouldScrollToNewest = !preserveScroll && ModeContext.activeTabCalendarScrollState.pinnedToNewest;
    renderRhsPanel();
    if (preserveScroll) {
        restoreRhsPanelScrollTop(panelScrollTop);
    }
}

export function renderRhsPanel() {
    hideDateTooltip();
    const container = document.getElementById('rhs-panel-content');
    if (!(container instanceof HTMLElement)) {
        throw new Error('rhs-panel-content element missing');
    }
    renderActivity(container);
}

function renderActivity(container) {
    const scrollState = ModeContext.activeTabCalendarScrollState;
    const panelScrollTop = shouldScrollToNewest || scrollState.pinnedToNewest ? null : scrollState.scrollTop;
    container.innerHTML = '';

    const toggle = document.createElement('div');
    toggle.className = 'rhs-metric-toggle';
    toggle.appendChild(buildMetricButton(DATE_FILTER_METRICS.UPDATED, 'Updated'));
    toggle.appendChild(buildMetricButton(DATE_FILTER_METRICS.CREATED, 'Created'));
    container.appendChild(toggle);

    if (!activityPayload) {
        return;
    }
    const buckets = activityPayload.buckets && typeof activityPayload.buckets === 'object'
        ? activityPayload.buckets
        : {};
    const activeDates = Object.entries(buckets)
        .filter((entry) => Number.isInteger(entry[1]) && entry[1] > 0)
        .map((entry) => entry[0])
        .sort();
    if (activeDates.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'rhs-empty-state';
        empty.textContent = 'No activity in the current view';
        container.appendChild(empty);
        return;
    }
    const visibleMonths = getActiveMonths(activeDates);
    const maxCount = Math.max(0, ...Object.values(buckets).map((value) => Number.isInteger(value) ? value : 0));
    const selected = ModeContext.activeTabDateFilter;
    const selectedStart = selected && selected.metric === metric ? selected.startDate : null;
    const selectedEnd = selected && selected.metric === metric ? selected.endDate : null;

    const stack = document.createElement('div');
    stack.className = 'rhs-heatmap-stack';
    let previousMonth = null;
    for (const visibleMonth of visibleMonths) {
        if (previousMonth && getMonthOffset(previousMonth, visibleMonth) > 1) {
            appendGap(stack, getMonthOffset(previousMonth, visibleMonth) - 1);
        }
        const grid = document.createElement('div');
        grid.className = 'rhs-heatmap-grid';
        grid.dataset.month = visibleMonth;
        appendWeekdaySpacers(grid, getVisibleMonthStart(visibleMonth));
        const monthStart = getVisibleMonthStart(visibleMonth);
        const monthEnd = getMonthEnd(monthStart);
        const visibleMonthEnd = monthEnd <= activityPayload.rangeEnd ? monthEnd : activityPayload.rangeEnd;
        const monthDates = enumerateIsoDates(monthStart, visibleMonthEnd);
        for (const isoDate of monthDates) {
            const count = Number.isInteger(buckets[isoDate]) ? buckets[isoDate] : 0;
            const cell = document.createElement('button');
            cell.type = 'button';
            cell.className = 'rhs-heatmap-cell';
            cell.dataset.date = isoDate;
            cell.dataset.count = String(count);
            cell.dataset.month = visibleMonth;
            cell.dataset.level = String(getCountLevel(count, maxCount));
            cell.style.backgroundColor = getHeatColor(count, maxCount);
            cell.setAttribute('aria-label', `${isoDate}, ${count} ${metric}`);
            if (selectedStart && selectedEnd && isoDate >= selectedStart && isoDate <= selectedEnd) {
                cell.classList.add('is-selected');
            }
            wireCell(cell);
            grid.appendChild(cell);
        }
        stack.appendChild(grid);
        previousMonth = visibleMonth;
    }
    container.appendChild(stack);
    window.requestAnimationFrame(() => {
        const grids = stack.querySelectorAll('.rhs-heatmap-grid');
        for (const renderedGrid of grids) {
            drawMonthOutlines(renderedGrid);
        }
        updateHoveredNoteDateHighlight();
    });
    if (shouldScrollToNewest && ModeContext.hoveredNoteId === null) {
        maybeScrollRhsPanelToNewest();
    } else {
        restoreRhsPanelScrollTop(panelScrollTop);
    }

    function getVisibleMonthStart(visibleMonth) {
        const monthStart = `${visibleMonth}-01`;
        return monthStart >= activityPayload.rangeStart ? monthStart : activityPayload.rangeStart;
    }
}

function buildMetricButton(nextMetric, label) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'rhs-metric-button';
    button.textContent = label;
    button.setAttribute('aria-pressed', metric === nextMetric ? 'true' : 'false');
    button.addEventListener('click', () => {
        const normalizedMetric = normalizeDateFilterMetric(nextMetric);
        if (metric === normalizedMetric) {
            return;
        }
        metric = normalizedMetric;
        ModeContext.updateActiveTabCalendarMetric(metric);
        activityPayload = null;
        shouldScrollToNewest = true;
        renderRhsPanel();
        void refreshRhsActivity({ preserveScroll: false });
    });
    return button;
}

function wireCell(cell) {
    const showTooltip = (event) => {
        const isoDate = cell.dataset.date;
        showDateTooltip(isoDate, event.clientX, event.clientY);
    };
    cell.addEventListener('pointerenter', (event) => {
        showTooltip(event);
        if (dragStartDate) {
            dragHoverDate = cell.dataset.date;
            updateDragPreview();
        }
    });
    cell.addEventListener('pointermove', (event) => {
        showTooltip(event);
    });
    cell.addEventListener('mouseenter', (event) => {
        showTooltip(event);
    });
    cell.addEventListener('mousemove', (event) => {
        showTooltip(event);
    });
    cell.addEventListener('pointerleave', () => {
        hideDateTooltip();
    });
    cell.addEventListener('mouseleave', () => {
        hideDateTooltip();
    });
    cell.addEventListener('pointerdown', (event) => {
        event.preventDefault();
        dragStartDate = cell.dataset.date;
        dragHoverDate = dragStartDate;
        updateDragPreview();
    });
    cell.addEventListener('pointerup', commitDragSelection);
}

function attachPointerListeners() {
    if (pointerListenersAttached) {
        return;
    }
    if (typeof window.addEventListener !== 'function') {
        throw new Error('window.addEventListener is required for RHS panel pointer interactions');
    }
    pointerListenersAttached = true;
    window.addEventListener('pointerup', () => {
        if (!dragStartDate) {
            return;
        }
        commitDragSelection();
    });

    window.addEventListener('pointermove', (event) => {
        if (!dragStartDate) {
            return;
        }
        const target = document.elementFromPoint(event.clientX, event.clientY);
        if (!(target instanceof Element)) {
            return;
        }
        const cell = target.closest('.rhs-heatmap-cell[data-date]');
        if (!(cell instanceof HTMLElement)) {
            return;
        }
        dragHoverDate = cell.dataset.date;
        updateDragPreview();
    });
}

function attachPanelScrollListener() {
    if (panelScrollListenerAttached) {
        return;
    }
    const panel = document.getElementById('rhs-panel');
    if (!(panel instanceof HTMLElement)) {
        throw new Error('rhs-panel element missing');
    }
    panelScrollListenerAttached = true;
    panel.addEventListener('scroll', () => {
        updateRhsPanelScrollStateFromDom(panel);
    }, { passive: true });
}

function updateRhsPanelScrollStateFromDom(panel) {
    if (!(panel instanceof HTMLElement)) {
        throw new Error('updateRhsPanelScrollStateFromDom requires panel element');
    }
    if (!document.body.classList.contains('pref-show-rhs-panel')) {
        return;
    }
    const scrollTop = Math.max(0, Math.round(panel.scrollTop));
    const maxScrollTop = Math.max(0, Math.round(panel.scrollHeight - panel.clientHeight));
    let pinnedToNewest = false;
    if (maxScrollTop === 0) {
        pinnedToNewest = true;
    } else if (scrollTop >= maxScrollTop - 2) {
        pinnedToNewest = true;
    }
    ModeContext.updateActiveTabCalendarScroll(scrollTop, pinnedToNewest);
}

function commitDragSelection() {
    const startDate = dragStartDate;
    let endDate = dragHoverDate;
    dragStartDate = null;
    dragHoverDate = null;
    if (!startDate) {
        return;
    }
    if (!endDate) {
        endDate = startDate;
    }
    const normalizedStart = startDate <= endDate ? startDate : endDate;
    const normalizedEnd = startDate <= endDate ? endDate : startDate;
    const current = ModeContext.activeTabDateFilter;
    if (
        current
        && current.metric === metric
        && current.startDate === normalizedStart
        && current.endDate === normalizedEnd
    ) {
        void setActiveDateFilter(null);
        return;
    }
    void setActiveDateFilter({ metric, startDate: normalizedStart, endDate: normalizedEnd });
}

function updateDragPreview() {
    if (!dragStartDate || !dragHoverDate) {
        return;
    }
    const normalizedStart = dragStartDate <= dragHoverDate ? dragStartDate : dragHoverDate;
    const normalizedEnd = dragStartDate <= dragHoverDate ? dragHoverDate : dragStartDate;
    const cells = document.querySelectorAll('.rhs-heatmap-cell[data-date]');
    for (const cell of cells) {
        const isoDate = cell.dataset.date;
        cell.classList.toggle('is-drag-preview', isoDate >= normalizedStart && isoDate <= normalizedEnd);
    }
}

function updateHoveredNoteDateHighlight() {
    const cells = document.querySelectorAll('.rhs-heatmap-cell[data-date]');
    for (const cell of cells) {
        cell.classList.remove('is-note-hovered-date');
    }
    if (!isRhsPanelVisible()) {
        hideDateTooltip();
        return;
    }
    const hoveredNoteId = ModeContext.hoveredNoteId;
    if (hoveredNoteId === null) {
        hideDateTooltip();
        return;
    }
    if (typeof hoveredNoteId !== 'string' || hoveredNoteId.length === 0) {
        throw new Error('ModeContext.hoveredNoteId must be null or non-empty string');
    }
    const noteElement = document.querySelector(`.note[data-note-id="${hoveredNoteId}"]`);
    if (!(noteElement instanceof HTMLElement)) {
        return;
    }
    const metadata = parseMetadata(noteElement);
    const timestamp = metric === DATE_FILTER_METRICS.CREATED ? metadata.createdAt : metadata.updatedAt;
    if (typeof timestamp !== 'string' || timestamp.length < 10) {
        throw new Error(`Hovered note ${hoveredNoteId} missing ${metric} timestamp metadata`);
    }
    const isoDate = timestamp.slice(0, 10);
    const matchingCell = document.querySelector(`.rhs-heatmap-cell[data-date="${isoDate}"]`);
    if (matchingCell instanceof HTMLElement) {
        matchingCell.classList.add('is-note-hovered-date');
        scrollHeatmapCellIntoView(matchingCell);
        showDateTooltipForCell(isoDate, matchingCell);
        return;
    }
    hideDateTooltip();
}

function isRhsPanelVisible() {
    const panel = document.getElementById('rhs-panel');
    if (!(panel instanceof HTMLElement)) {
        return false;
    }
    if (!document.body.classList.contains('pref-show-rhs-panel')) {
        return false;
    }
    return panel.getClientRects().length > 0;
}

function scrollHeatmapCellIntoView(cell) {
    const panel = document.getElementById('rhs-panel');
    if (!(panel instanceof HTMLElement)) {
        return;
    }
    const cellRect = cell.getBoundingClientRect();
    const panelRect = panel.getBoundingClientRect();
    const toggle = panel.querySelector('.rhs-metric-toggle');
    const stickyBottom = toggle instanceof HTMLElement
        ? toggle.getBoundingClientRect().bottom
        : panelRect.top;
    const topLimit = Math.max(panelRect.top, stickyBottom) + 8;
    const bottomLimit = panelRect.bottom - 8;
    if (cellRect.top < topLimit) {
        panel.scrollTop -= topLimit - cellRect.top;
        updateRhsPanelScrollStateFromDom(panel);
        return;
    }
    if (cellRect.bottom > bottomLimit) {
        panel.scrollTop += cellRect.bottom - bottomLimit;
        updateRhsPanelScrollStateFromDom(panel);
    }
}

function maybeScrollRhsPanelToNewest() {
    if (!shouldScrollToNewest) {
        return;
    }
    const panel = document.getElementById('rhs-panel');
    if (!(panel instanceof HTMLElement)) {
        return;
    }
    shouldScrollToNewest = false;
    window.requestAnimationFrame(() => {
        panel.scrollTop = panel.scrollHeight;
        updateRhsPanelScrollStateFromDom(panel);
        window.requestAnimationFrame(() => {
            panel.scrollTop = panel.scrollHeight;
            updateRhsPanelScrollStateFromDom(panel);
        });
    });
}

function getRhsPanelScrollTop() {
    const panel = document.getElementById('rhs-panel');
    if (!(panel instanceof HTMLElement)) {
        return null;
    }
    return panel.scrollTop;
}

function restoreRhsPanelScrollTop(scrollTop) {
    if (scrollTop === null) {
        return;
    }
    if (!Number.isFinite(scrollTop)) {
        throw new Error('RHS panel scrollTop must be finite');
    }
    const panel = document.getElementById('rhs-panel');
    if (!(panel instanceof HTMLElement)) {
        return;
    }
    window.requestAnimationFrame(() => {
        panel.scrollTop = scrollTop;
        updateRhsPanelScrollStateFromDom(panel);
    });
}

function getActiveMonths(activeDates) {
    const months = [];
    let previousMonth = null;
    for (const isoDate of activeDates) {
        const month = isoDate.slice(0, 7);
        if (month !== previousMonth) {
            months.push(month);
            previousMonth = month;
        }
    }
    return months;
}

function appendWeekdaySpacers(grid, isoDate) {
    const firstDate = new Date(`${isoDate}T00:00:00Z`);
    for (let i = 0; i < firstDate.getUTCDay(); i += 1) {
        const spacer = document.createElement('span');
        spacer.className = 'rhs-heatmap-spacer';
        grid.appendChild(spacer);
    }
}

function appendGap(grid, skippedMonthCount) {
    assertPositiveInteger(skippedMonthCount, 'skippedMonthCount');
    const gap = document.createElement('div');
    gap.className = 'rhs-heatmap-gap';
    gap.setAttribute('aria-label', `${skippedMonthCount} inactive month${skippedMonthCount === 1 ? '' : 's'} skipped`);
    gap.textContent = '...';
    grid.appendChild(gap);
}

function drawMonthOutlines(grid) {
    const oldOverlay = grid.querySelector('.rhs-heatmap-month-outline-layer');
    if (oldOverlay) {
        oldOverlay.remove();
    }
    const cells = Array.from(grid.querySelectorAll('.rhs-heatmap-cell[data-month]'));
    if (cells.length === 0) {
        return;
    }
    const gridRect = grid.getBoundingClientRect();
    const cellsByMonth = new Map();
    for (const cell of cells) {
        const month = cell.dataset.month;
        if (!cellsByMonth.has(month)) {
            cellsByMonth.set(month, []);
        }
        cellsByMonth.get(month).push(cell);
    }
    const overlay = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    overlay.classList.add('rhs-heatmap-month-outline-layer');
    overlay.setAttribute('viewBox', `0 0 ${gridRect.width} ${gridRect.height}`);
    overlay.setAttribute('aria-hidden', 'true');
    for (const monthCells of cellsByMonth.values()) {
        const pathData = buildMonthOutlinePath(monthCells, gridRect);
        if (pathData.length === 0) {
            continue;
        }
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        const underlay = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        underlay.classList.add('rhs-heatmap-month-outline-underlay');
        underlay.setAttribute('d', pathData);
        overlay.appendChild(underlay);
        path.classList.add('rhs-heatmap-month-outline');
        path.setAttribute('d', pathData);
        overlay.appendChild(path);
    }
    grid.appendChild(overlay);
}

function getHeatColor(count, maxCount) {
    if (!Number.isInteger(count) || count < 0) {
        throw new Error('Heatmap count must be a non-negative integer');
    }
    if (!Number.isInteger(maxCount) || maxCount < 1) {
        throw new Error('Heatmap maxCount must be a positive integer');
    }
    if (count === 0) {
        return 'rgb(243, 244, 246)';
    }
    const ratio = Math.log(count + 1) / Math.log(maxCount + 1);
    const channel = Math.round(243 - (ratio * 226));
    return `rgb(${channel}, ${channel}, ${channel})`;
}

function showDateTooltip(isoDate, clientX, clientY) {
    if (typeof isoDate !== 'string' || isoDate.length === 0) {
        throw new Error('Heatmap date tooltip requires an ISO date');
    }
    if (!Number.isFinite(clientX) || !Number.isFinite(clientY)) {
        throw new Error('Heatmap date tooltip requires finite pointer coordinates');
    }
    if (!tooltipElement) {
        tooltipElement = document.createElement('div');
        tooltipElement.className = 'rhs-date-tooltip';
        document.body.appendChild(tooltipElement);
    }
    tooltipElement.textContent = isoDate;
    tooltipElement.style.left = `${clientX + 10}px`;
    tooltipElement.style.top = `${clientY + 10}px`;
    tooltipElement.hidden = false;
}

function showDateTooltipForCell(isoDate, cell) {
    if (!(cell instanceof HTMLElement)) {
        throw new Error('Heatmap date tooltip requires a cell element');
    }
    if (!isRhsPanelVisible()) {
        hideDateTooltip();
        return;
    }
    const rect = cell.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
        hideDateTooltip();
        return;
    }
    const clientX = rect.right + 4;
    const clientY = rect.top + (rect.height / 2);
    showDateTooltip(isoDate, clientX, clientY);
}

function hideDateTooltip() {
    if (tooltipElement) {
        tooltipElement.hidden = true;
    }
}

function buildMonthOutlinePath(monthCells, gridRect) {
    const grid = monthCells[0].parentElement;
    if (!(grid instanceof HTMLElement)) {
        throw new Error('Heatmap cell parent must be an element');
    }
    const allCells = Array.from(grid.querySelectorAll('.rhs-heatmap-cell[data-date]'));
    if (allCells.length === 0) {
        throw new Error('Heatmap outline requires rendered day cells');
    }
    const allRects = allCells.map((cell) => {
        const rect = cell.getBoundingClientRect();
        return {
            left: Math.round(rect.left - gridRect.left),
            top: Math.round(rect.top - gridRect.top),
            right: Math.round(rect.right - gridRect.left),
            bottom: Math.round(rect.bottom - gridRect.top),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
        };
    });
    const columnLefts = uniqueSortedNumbers(allRects.map((rect) => rect.left));
    const rowTops = uniqueSortedNumbers(allRects.map((rect) => rect.top));
    const cellWidth = allRects[0].width;
    const cellHeight = allRects[0].height;
    const columnGap = columnLefts.length > 1 ? columnLefts[1] - columnLefts[0] - cellWidth : 0;
    const rowGap = rowTops.length > 1 ? rowTops[1] - rowTops[0] - cellHeight : 0;
    if (columnGap < 0 || rowGap < 0) {
        throw new Error('Heatmap rendered coordinates overlap');
    }
    const halfColumnGap = columnGap / 2;
    const halfRowGap = rowGap / 2;
    const slots = monthCells.map((cell) => {
        const rect = cell.getBoundingClientRect();
        const left = Math.round(rect.left - gridRect.left);
        const top = Math.round(rect.top - gridRect.top);
        return {
            col: findNumberIndex(columnLefts, left),
            row: findNumberIndex(rowTops, top),
            left: left - halfColumnGap,
            top: top - halfRowGap,
            right: Math.round(rect.right - gridRect.left) + halfColumnGap,
            bottom: Math.round(rect.bottom - gridRect.top) + halfRowGap,
        };
    });
    const slotKeys = new Set(slots.map((slot) => `${slot.col},${slot.row}`));
    const edges = [];
    for (const slot of slots) {
        if (!slotKeys.has(`${slot.col},${slot.row - 1}`)) {
            edges.push([[slot.left, slot.top], [slot.right, slot.top]]);
        }
        if (!slotKeys.has(`${slot.col + 1},${slot.row}`)) {
            edges.push([[slot.right, slot.top], [slot.right, slot.bottom]]);
        }
        if (!slotKeys.has(`${slot.col},${slot.row + 1}`)) {
            edges.push([[slot.right, slot.bottom], [slot.left, slot.bottom]]);
        }
        if (!slotKeys.has(`${slot.col - 1},${slot.row}`)) {
            edges.push([[slot.left, slot.bottom], [slot.left, slot.top]]);
        }
    }
    return edges.map((edge) => `M ${edge[0][0]} ${edge[0][1]} L ${edge[1][0]} ${edge[1][1]}`).join(' ');
}

function uniqueSortedNumbers(values) {
    const sorted = [...new Set(values)].sort((left, right) => left - right);
    if (sorted.length === 0) {
        throw new Error('Expected at least one rendered heatmap coordinate');
    }
    return sorted;
}

function findNumberIndex(values, target) {
    const index = values.indexOf(target);
    if (index === -1) {
        throw new Error('Rendered heatmap coordinate was not indexed');
    }
    return index;
}

function getMonthOffset(startMonth, endMonth) {
    const startYear = Number(startMonth.slice(0, 4));
    const startMonthIndex = Number(startMonth.slice(5, 7)) - 1;
    const endYear = Number(endMonth.slice(0, 4));
    const endMonthIndex = Number(endMonth.slice(5, 7)) - 1;
    return ((endYear - startYear) * 12) + endMonthIndex - startMonthIndex;
}

function assertPositiveInteger(value, label) {
    if (!Number.isInteger(value) || value < 1) {
        throw new Error(`${label} must be a positive integer`);
    }
}

function getMonthEnd(isoDate) {
    const year = Number(isoDate.slice(0, 4));
    const monthIndex = Number(isoDate.slice(5, 7)) - 1;
    const endDate = new Date(Date.UTC(year, monthIndex + 1, 0));
    return endDate.toISOString().slice(0, 10);
}

function renderInspector(container, noteElement, titleText) {
    container.innerHTML = '';
    const title = document.createElement('h2');
    title.className = 'rhs-section-title';
    title.textContent = titleText;
    container.appendChild(title);

    const panel = document.createElement('div');
    panel.className = 'rhs-inspector';
    const tags = typeof noteElement.dataset.noteTags === 'string' ? noteElement.dataset.noteTags : '';
    const metadata = parseMetadata(noteElement);
    appendRow(panel, 'Created', formatTimestamp(metadata.createdAt));
    appendRow(panel, 'Updated', formatTimestamp(metadata.updatedAt));
    const trimmedTags = tags.trim();
    appendRow(panel, 'Tags', trimmedTags.length > 0 ? trimmedTags : 'none');
    if (metadata.inheritedTags.length > 0) {
        appendRow(panel, 'Inherited', metadata.inheritedTags.join(' '));
    }
    appendRow(panel, 'Path', metadata.path.map((entry) => {
        if (typeof entry.label === 'string' && entry.label.length > 0) {
            return entry.label;
        }
        return entry.id;
    }).join(' / '));
    container.appendChild(panel);
}

function parseMetadata(noteElement) {
    const raw = typeof noteElement.dataset.noteMetadata === 'string' ? noteElement.dataset.noteMetadata : '{}';
    const parsed = JSON.parse(raw);
    return {
        createdAt: typeof parsed.createdAt === 'string' ? parsed.createdAt : '',
        updatedAt: typeof parsed.updatedAt === 'string' ? parsed.updatedAt : '',
        inheritedTags: Array.isArray(parsed.inheritedTags) ? parsed.inheritedTags.filter((tag) => typeof tag === 'string') : [],
        path: Array.isArray(parsed.path) ? parsed.path.filter((entry) => entry && typeof entry === 'object') : [],
        childCount: Number.isInteger(parsed.childCount) ? parsed.childCount : 0,
        subtreeCount: Number.isInteger(parsed.subtreeCount) ? parsed.subtreeCount : 0,
    };
}

function appendRow(panel, labelText, valueText) {
    const row = document.createElement('div');
    row.className = 'rhs-inspector-row';
    const label = document.createElement('div');
    label.className = 'rhs-inspector-label';
    label.textContent = labelText;
    const value = document.createElement('div');
    value.className = 'rhs-inspector-value';
    value.textContent = valueText;
    row.append(label, value);
    panel.appendChild(row);
}

function formatTimestamp(value) {
    if (typeof value !== 'string' || value.length === 0) {
        return 'missing';
    }
    return value.replace('T', ' ').replace(/\.\d+/, '');
}
