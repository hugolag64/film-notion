export function groupEpisodesBySeason(episodes) {
    return episodes.reduce((seasons, episode) => {
        const seasonNumber = episode.season_number;
        if (!seasons[seasonNumber]) seasons[seasonNumber] = [];
        seasons[seasonNumber].push(episode);
        return seasons;
    }, {});
}

export function seriesProgressText(progress) {
    if (!progress) return 'Chargement de la progression…';
    return `${progress.watched} / ${progress.total} épisodes vus (${Math.round(progress.percentage)} %)`;
}

export function replaceEpisode(episodes, updatedEpisode) {
    return episodes.map((episode) => (
        // Merge: the PATCH answer lacks view-only fields (available, percent…).
        episode.id === updatedEpisode.id ? {...episode, ...updatedEpisode} : episode
    ));
}

export function episodeCode(seasonNumber, episodeNumber) {
    return `S${seasonNumber}:E${String(episodeNumber).padStart(2, '0')}`;
}

/** 95 → « 1 h 35 », 40 → « 40 min ». */
export function formatDuration(minutes) {
    if (!minutes || minutes <= 0) return null;
    const hours = Math.floor(minutes / 60);
    const rest = minutes % 60;
    if (!hours) return `${rest} min`;
    return rest ? `${hours} h ${String(rest).padStart(2, '0')}` : `${hours} h`;
}

/** « 2011–2016 », « 2022– » for a running show, « 2011 » for a single year. */
export function seriesYears(info, fallbackYear) {
    const first = info?.first_air_date?.slice(0, 4);
    const last = info?.last_air_date?.slice(0, 4);
    if (!first) return fallbackYear && fallbackYear !== '—' ? String(fallbackYear) : null;
    if (isRunning(info)) return `${first}–`;
    return last && last !== first ? `${first}–${last}` : first;
}

export function isRunning(info) {
    return ['Returning Series', 'In Production', 'Planned'].includes(info?.tmdb_status);
}

export function tmdbStatusLabel(info) {
    if (!info?.tmdb_status) return null;
    if (isRunning(info)) return 'En production';
    if (info.tmdb_status === 'Ended') return 'Terminée';
    if (info.tmdb_status === 'Canceled') return 'Annulée';
    return null;
}

export function formatAirDate(isoDate) {
    if (!isoDate) return null;
    const date = new Date(`${isoDate}T00:00:00`);
    if (Number.isNaN(date.getTime())) return null;
    return date.toLocaleDateString('fr-FR', {day: 'numeric', month: 'short', year: 'numeric'});
}

/** Label of the series' main button, from the server's next_episode pick. */
export function primaryEpisodeLabel(nextEpisode) {
    if (!nextEpisode) return null;
    const code = episodeCode(nextEpisode.season_number, nextEpisode.episode_number);
    if (nextEpisode.mode === 'resume') return `Reprendre ${code}`;
    if (nextEpisode.mode === 'start') return `Commencer ${code}`;
    return `Lire ${code}`;
}

/** Season availability chip: null when the server state is unknown. */
export function seasonAvailabilityLabel(season) {
    if (season.availability === 'complete') return 'Complète';
    if (season.availability === 'partial') return `Partielle ${season.available}/${season.aired}`;
    if (season.availability === 'missing') return 'Absente du serveur';
    return null;
}
