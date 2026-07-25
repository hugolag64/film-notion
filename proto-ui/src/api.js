// API Client module for Backstage Python Backend

const API_BASE_URL = 'http://localhost:8090/api';

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

/**
 * Trigger local stream simulation on HP ProDesk server.
 */
export async function triggerStream(mediaId) {
    try {
        const response = await fetch(`${API_BASE_URL}/medias/${mediaId}/stream`, {
            method: 'POST',
        });
        if (!response.ok) {
            throw new Error(`Failed to trigger stream: ${response.statusText}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error triggering stream:', error);
        throw error;
    }
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
