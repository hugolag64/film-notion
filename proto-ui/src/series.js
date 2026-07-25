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
        episode.id === updatedEpisode.id ? updatedEpisode : episode
    ));
}
