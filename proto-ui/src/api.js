// API Client module for Backstage Python Backend

const API_BASE_URL = '/api';

/**
 * Fetch all media items from SQLite database via FastAPI.
 */
export async function fetchMedias() {
    try {
        const response = await fetch(`${API_BASE_URL}/medias`);
        if (!response.ok) {
            throw new Error(`Failed to fetch medias: ${response.statusText}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error fetching medias:', error);
        throw error;
    }
}

/**
 * Update media fields (rating, review/userNotes, watched_in_cinema, watched_date, etc.).
 */
export async function updateMedia(mediaId, payload) {
    try {
        const response = await fetch(`${API_BASE_URL}/medias/${mediaId}`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            throw new Error(`Failed to update media: ${response.statusText}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error updating media:', error);
        throw error;
    }
}

export async function fetchAvailability(mediaId) {
    const response = await fetch(`${API_BASE_URL}/medias/${mediaId}/availability`);
    if (!response.ok) throw new Error(`Disponibilité impossible: ${response.statusText}`);
    return response.json();
}

export function getPlaybackManifest(mediaId) {
    return `${API_BASE_URL}/medias/${encodeURIComponent(mediaId)}/playback/manifest`;
}

export async function fetchMediaServerOptions(mediaType) {
    const response = await fetch(`${API_BASE_URL}/media-server/options?media_type=${encodeURIComponent(mediaType)}`);
    if (!response.ok) throw new Error((await response.json()).detail || 'Service non configuré');
    return response.json();
}

export async function requestAcquisition(mediaId, payload) {
    const response = await fetch(`${API_BASE_URL}/medias/${mediaId}/acquisition`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error((await response.json()).detail || 'Demande impossible');
    return response.json();
}

export async function syncMediaServer() {
    const response = await fetch(`${API_BASE_URL}/media-server/sync`, {method: 'POST'});
    if (!response.ok) throw new Error((await response.json()).detail || 'Synchronisation impossible');
    return response.json();
}

export async function importMediaServerLibrary() {
    const response = await fetch(`${API_BASE_URL}/media-server/import`, {method: 'POST'});
    if (!response.ok) throw new Error((await response.json()).detail || 'Import impossible');
    return response.json();
}

export async function fetchMediaServerActivity() {
    const response = await fetch(`${API_BASE_URL}/media-server/activity`);
    if (!response.ok) throw new Error((await response.json()).detail || 'Activité indisponible');
    return response.json();
}

/**
 * Search TMDB for movies by query.
 */
export async function searchTMDB(query) {
    try {
        const response = await fetch(`${API_BASE_URL}/tmdb/search?query=${encodeURIComponent(query)}`);
        if (!response.ok) {
            throw new Error(`Failed to search TMDB: ${response.statusText}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error searching TMDB:', error);
        throw error;
    }
}

/**
 * Relink a media item to a specific TMDB movie ID.
 */
export async function relinkTMDB(mediaId, tmdbId) {
    try {
        const response = await fetch(`${API_BASE_URL}/medias/${mediaId}/relink_tmdb`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ tmdb_id: tmdbId }),
        });
        if (!response.ok) {
            throw new Error(`Failed to relink TMDB: ${response.statusText}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error relinking TMDB:', error);
        throw error;
    }
}

export async function createMediaFromTMDB(tmdbId) {
    const response = await fetch(`${API_BASE_URL}/medias/from_tmdb`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({tmdb_id: tmdbId}),
    });
    if (!response.ok) throw new Error(`Failed to create media: ${response.statusText}`);
    return response.json();
}

export async function searchTMDBTV(query) {
    const response = await fetch(`${API_BASE_URL}/tmdb/search/tv?query=${encodeURIComponent(query)}`);
    if (!response.ok) throw new Error(`Failed to search TV: ${response.statusText}`);
    return response.json();
}

export async function searchTMDBPerson(query) {
    const response = await fetch(`${API_BASE_URL}/tmdb/search/person?query=${encodeURIComponent(query)}`);
    if (!response.ok) throw new Error(`Failed to search TMDB people: ${response.statusText}`);
    return response.json();
}

export async function createSeriesFromTMDB(tmdbId) {
    const response = await fetch(`${API_BASE_URL}/series/from_tmdb`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({tmdb_id: tmdbId}),
    });
    if (!response.ok) throw new Error(`Failed to create series: ${response.statusText}`);
    return response.json();
}

export async function fetchSeriesEpisodes(mediaId) {
    const response = await fetch(`${API_BASE_URL}/medias/${mediaId}/episodes`);
    if (!response.ok) throw new Error(`Failed to fetch series episodes: ${response.statusText}`);
    return response.json();
}

export async function updateEpisode(episodeId, watched) {
    const response = await fetch(`${API_BASE_URL}/episodes/${episodeId}`, {
        method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({watched}),
    });
    if (!response.ok) throw new Error(`Failed to update episode: ${response.statusText}`);
    return response.json();
}

export async function refreshSeriesFromTMDB(mediaId) {
    const response = await fetch(`${API_BASE_URL}/series/${mediaId}/refresh`, { method: 'POST' });
    if (!response.ok) throw new Error(`Failed to refresh series: ${response.statusText}`);
    return response.json();
}
