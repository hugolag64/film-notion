import { enRouteBadge } from './library.js';

const MONTHS = [
    'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
    'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
];

/** Journal page: entries grouped by month, newest first, undated ones last. */
export function groupDiaryByMonth(entries) {
    const groups = new Map();
    const unknown = [];
    for (const entry of entries || []) {
        const match = /^(\d{4})-(\d{2})/.exec(entry.watched_on || '');
        if (!match) {
            unknown.push(entry);
            continue;
        }
        const key = `${match[1]}-${match[2]}`;
        if (!groups.has(key)) {
            groups.set(key, { key, label: `${MONTHS[Number(match[2]) - 1]} ${match[1]}`, entries: [] });
        }
        groups.get(key).entries.push(entry);
    }
    const dated = [...groups.values()].sort((a, b) => (a.key < b.key ? 1 : -1));
    return unknown.length ? [...dated, { key: 'unknown', label: 'Date inconnue', entries: unknown }] : dated;
}

/** A rating out of 5 by half points, as stars: 4.5 → ★★★★½. */
export function formatStars(rating) {
    if (rating == null) return '';
    const full = Math.floor(rating);
    return '★'.repeat(full) + (rating - full >= 0.5 ? '½' : '');
}

/** The single badge of a film in a shared list. */
export function listItemBadge(item, now = new Date()) {
    if (item?.library?.ready) return { label: 'Sur le serveur', tone: 'ready' };
    if (item?.library) return enRouteBadge(item.release_date, item.library, now);
    const badge = enRouteBadge(item?.release_date, null, now);
    return badge.tone === 'upcoming' || badge.tone === 'cinema' ? badge : null;
}

/** After adding a film to a list: offer a server request when it is neither there nor requested. */
export function shouldOfferSeerrRequest(addResult) {
    return Boolean(addResult?.item) && addResult.item.library == null;
}

const pad2 = (value) => String(value).padStart(2, '0');

/** Today's date, in local time, as YYYY-MM-DD. */
export function todayIsoDate(now = new Date()) {
    return `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())}`;
}
