export const DATE_FILTER_METRICS = Object.freeze({
    UPDATED: 'updated',
    CREATED: 'created',
});

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export function normalizeDateFilterMetric(metric) {
    if (typeof metric !== 'string') {
        throw new Error('date filter metric must be a string');
    }
    const normalized = metric.trim().toLowerCase();
    if (normalized !== DATE_FILTER_METRICS.UPDATED && normalized !== DATE_FILTER_METRICS.CREATED) {
        throw new Error(`Unsupported date filter metric: ${metric}`);
    }
    return normalized;
}

export function normalizeDateFilter(dateFilter) {
    if (dateFilter === null) {
        return null;
    }
    if (!dateFilter || typeof dateFilter !== 'object') {
        throw new Error('dateFilter must be an object or null');
    }
    const metric = normalizeDateFilterMetric(dateFilter.metric);
    const startDate = normalizeIsoDate(dateFilter.startDate, 'dateFilter.startDate');
    const endDate = normalizeIsoDate(dateFilter.endDate, 'dateFilter.endDate');
    if (startDate > endDate) {
        throw new Error('dateFilter.startDate must be before or equal to dateFilter.endDate');
    }
    return { metric, startDate, endDate };
}

export function getDateFilterLabel(dateFilter) {
    const normalized = normalizeDateFilter(dateFilter);
    if (normalized === null) {
        return '';
    }
    const metricLabel = normalized.metric === DATE_FILTER_METRICS.CREATED ? 'CREATED' : 'UPDATED';
    if (normalized.startDate === normalized.endDate) {
        return `${metricLabel} ${normalized.startDate}`;
    }
    return `${metricLabel} ${normalized.startDate} - ${normalized.endDate}`;
}

export function enumerateIsoDates(startDate, endDate) {
    const start = parseIsoDate(startDate);
    const end = parseIsoDate(endDate);
    if (start > end) {
        throw new Error('startDate must be before or equal to endDate');
    }
    const dates = [];
    const cursor = new Date(start.getTime());
    while (cursor <= end) {
        dates.push(formatIsoDate(cursor));
        cursor.setUTCDate(cursor.getUTCDate() + 1);
    }
    return dates;
}

export function getMonthKey(isoDate) {
    normalizeIsoDate(isoDate, 'isoDate');
    return isoDate.slice(0, 7);
}

export function getMonthLabel(monthKey) {
    if (!/^\d{4}-\d{2}$/.test(monthKey)) {
        throw new Error('monthKey must use YYYY-MM');
    }
    const date = new Date(`${monthKey}-01T00:00:00Z`);
    return date.toLocaleString(undefined, { month: 'short', year: 'numeric', timeZone: 'UTC' });
}

export function getCountLevel(count, maxCount) {
    if (!Number.isInteger(count) || count < 0) {
        throw new Error('count must be a non-negative integer');
    }
    if (!Number.isInteger(maxCount) || maxCount < 0) {
        throw new Error('maxCount must be a non-negative integer');
    }
    if (count === 0 || maxCount === 0) {
        return 0;
    }
    return Math.max(1, Math.min(5, Math.ceil((count / maxCount) * 5)));
}

function normalizeIsoDate(value, fieldName) {
    if (typeof value !== 'string' || !DATE_RE.test(value)) {
        throw new Error(`${fieldName} must use YYYY-MM-DD`);
    }
    return value;
}

function parseIsoDate(value) {
    normalizeIsoDate(value, 'date');
    return new Date(`${value}T00:00:00Z`);
}

function formatIsoDate(date) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) {
        throw new Error('formatIsoDate requires a valid Date');
    }
    return date.toISOString().slice(0, 10);
}
