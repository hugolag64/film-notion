const STATUS_MAP = { watched: 'Terminé', watchlist: 'À regarder' };

export function normalizeStatus(status) {
    return STATUS_MAP[status] || (status === 'Terminé' ? 'Terminé' : 'À regarder');
}

export function filterAndSortMovies(movies, filters, sort) {
    const query = filters.query.trim().toLowerCase();
    const filtered = movies.filter(movie => {
        const text = `${movie.title} ${movie.director}`.toLowerCase();
        return (!query || text.includes(query))
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
