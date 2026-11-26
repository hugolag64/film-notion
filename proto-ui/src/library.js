const STATUS_MAP = { watched: 'Terminé', watchlist: 'À regarder' };

export function normalizeStatus(status) {
    const normalized = STATUS_MAP[status] || status;
    return ['Terminé', 'Terminée', 'En cours', 'À regarder'].includes(normalized)
        ? normalized
        : 'À regarder';
}

/** Lowercase, accents and punctuation removed: « Amélie » and « amelie » match. */
export function normalizeSearchText(value) {
    return String(value ?? '')
        .normalize('NFD')
        .replace(/[̀-ͯ]/g, '')
        .toLowerCase()
        .replace(/œ/g, 'oe')
        .replace(/æ/g, 'ae')
        .replace(/[^a-z0-9]+/g, ' ')
        .trim();
}

function editDistance(a, b, limit) {
    if (Math.abs(a.length - b.length) > limit) return limit + 1;
    let previous = Array.from({length: b.length + 1}, (_, index) => index);
    for (let i = 1; i <= a.length; i += 1) {
        const current = [i];
        let rowMin = i;
        for (let j = 1; j <= b.length; j += 1) {
            const cost = a[i - 1] === b[j - 1] ? 0 : 1;
            current[j] = Math.min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost);
            rowMin = Math.min(rowMin, current[j]);
        }
        if (rowMin > limit) return limit + 1;
        previous = current;
    }
    return previous[b.length];
}

// Typos allowed per word: none for short words (too many false hits),
// one from 4 letters, two from 8.
const allowedTypos = (token) => (token.length >= 8 ? 2 : token.length >= 4 ? 1 : 0);

/** Distance between a typed word and the closest word of the text; also
 *  compares with word starts so a half-typed word still matches. */
function tokenDistance(token, words) {
    const limit = allowedTypos(token);
    let best = limit + 1;
    for (const word of words) {
        if (word.startsWith(token)) return 0;
        if (!limit) continue;
        best = Math.min(
            best,
            editDistance(token, word, limit),
            word.length > token.length ? editDistance(token, word.slice(0, token.length), limit) : best,
        );
        if (best === 0) return 0;
    }
    return best;
}

const PLACEHOLDER_ACTOR = 'Acteur principal';
const EXACT_MATCH_MAX_SCORE = 2;

/**
 * How well a title matches what was typed: lower is better, null when it
 * does not match. Exact text beats typos; the title beats the director.
 */
export function searchScore(movie, query) {
    const needle = normalizeSearchText(query);
    if (!needle) return 0;
    const title = normalizeSearchText(`${movie.title} ${movie.originalTitle || ''}`);
    const cast = (movie.cast || []).filter((name) => name !== PLACEHOLDER_ACTOR);
    const people = normalizeSearchText(`${movie.director || ''} ${cast.join(' ')}`);
    if (title.startsWith(needle)) return 0;
    if (title.includes(needle)) return 1;
    if (people.includes(needle)) return 2;
    const words = `${title} ${people}`.split(' ').filter(Boolean);
    let total = 0;
    for (const token of needle.split(' ')) {
        const distance = tokenDistance(token, words);
        if (distance > allowedTypos(token)) return null;
        total += distance;
    }
    return 3 + total;
}

/** Scored matches; typo matches only count when nothing matches exactly,
 *  so « dune » does not also bring « June ». */
function scoredMatches(movies, query) {
    const scored = movies
        .map((movie) => ({movie, score: searchScore(movie, query)}))
        .filter((item) => item.score !== null);
    return scored.some((item) => item.score <= EXACT_MATCH_MAX_SCORE)
        ? scored.filter((item) => item.score <= EXACT_MATCH_MAX_SCORE)
        : scored;
}

/** Library titles matching a search, best first. */
export function searchLibrary(movies, query) {
    return scoredMatches(movies, query)
        .sort((a, b) => a.score - b.score || String(a.movie.title).localeCompare(String(b.movie.title), 'fr'))
        .map((item) => item.movie);
}

export function filterAndSortMovies(movies, filters, sort) {
    const query = filters.query.trim();
    const matching = query ? new Set(scoredMatches(movies, query).map((item) => item.movie)) : null;
    const filtered = movies.filter(movie => {
        return (!matching || matching.has(movie))
            && (!filters.genre || movie.genre.includes(filters.genre))
            && (!filters.director || movie.director === filters.director)
            && (!filters.status || movie.status === filters.status)
            && (!filters.support || movie.supports.includes(filters.support));
    });
    const factor = sort.direction === 'asc' ? 1 : -1;
    return filtered.sort((a, b) => {
        const value = movie => sort.key === 'title' ? movie.title.toLowerCase()
            : sort.key === 'year' ? Number(movie.year) || 0
                : sort.key === 'rating' ? Number(movie.rating) || 0
                    : new Date(movie.createdAt || 0).getTime();
        return value(a) < value(b) ? -factor : value(a) > value(b) ? factor : 0;
    });
}

export function filterOptions(movies, field) {
    const values = movies.flatMap(movie => Array.isArray(movie[field]) ? movie[field] : [movie[field]]);
    return [...new Set(values.filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b), 'fr'));
}

// Shareable address of a fiche: /film/<id> or /serie/<id>.
export function mediaPath(media) {
    if (!media?.id) return undefined;
    return `/${media.type === 'Série' ? 'serie' : 'film'}/${encodeURIComponent(media.id)}`;
}

export function parseMediaPath(pathname) {
    const match = /^\/(film|serie)\/([^/]+)\/?$/.exec(pathname || '');
    if (!match) return null;
    try {
        return {kind: match[1], id: decodeURIComponent(match[2])};
    } catch {
        return null;
    }
}

/** A requested film released less than this many days ago is shown as « Au cinéma ». */
export const CINEMA_WINDOW_DAYS = 120;

/** Films view: ready on Jellyfin (or not tracked by the server at all) → grid, otherwise « En route ». */
export function libraryPlacement(mediaId, states) {
    const entry = states?.[mediaId];
    return !entry || entry.ready ? 'grid' : 'enRoute';
}

const localDay = (date) => [date.getFullYear(), date.getMonth() + 1, date.getDate()];
const dayNumber = ([year, month, day]) => Date.UTC(year, month - 1, day) / 86_400_000;
const pad2 = (value) => String(value).padStart(2, '0');

/** The single colored badge of a film on its way to the server. */
export function enRouteBadge(releaseDate, entry, now = new Date()) {
    const state = entry?.state;
    if (state === 'downloading') {
        const progress = entry.progress_percent;
        return { label: progress == null ? 'Téléchargement' : `Téléchargement ${progress} %`, tone: 'downloading' };
    }
    if (state === 'searching') return { label: 'Recherche', tone: 'searching' };
    if (state === 'error') return { label: 'Erreur', tone: 'error' };
    if (state === 'available' || state === 'imported') return { label: 'Bientôt prêt', tone: 'downloading' };

    const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(releaseDate || '');
    if (match) {
        const release = [Number(match[1]), Number(match[2]), Number(match[3])];
        const daysSince = dayNumber(localDay(now)) - dayNumber(release);
        if (daysSince < 0) return { label: `Sort le ${pad2(release[2])}/${pad2(release[1])}`, tone: 'upcoming' };
        if (daysSince < CINEMA_WINDOW_DAYS) return { label: 'Au cinéma', tone: 'cinema' };
    }
    return { label: 'Demandé', tone: 'requested' };
}
