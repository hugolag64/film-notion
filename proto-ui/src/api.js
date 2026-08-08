// API Client module for Backstage Python Backend

const API_BASE_URL = '/api';

async function readResponseBody(response) {
    const text = await response.text();
    if (!text) return null;
    try {
        return JSON.parse(text);
    } catch {
        return {detail: text.trim()};
    }
}

async function authRequest(path, options = {}) {
    const response = await fetch(`${API_BASE_URL}/auth${path}`, {
        ...options,
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json',
            ...(options.headers || {}),
        },
    });
    let body = null;
    if (response.status !== 204) {
        body = await response.json().catch(() => null);
    }
    if (!response.ok) {
        const error = new Error(body?.detail || 'Erreur d’authentification');
        error.status = response.status;
        throw error;
    }
    return body;
}

async function recommendationRequest(path, options = {}) {
    const response = await fetch(`${API_BASE_URL}${path}`, {
        ...options,
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json',
            ...(options.headers || {}),
        },
    });
    const body = await response.json().catch(() => null);
    if (!response.ok) {
        const error = new Error(body?.detail || 'Erreur de recommandation');
        error.status = response.status;
        throw error;
    }
    return body;
}

export async function fetchAuthStatus() {
    return authRequest('/status');
}

export async function fetchCurrentUser() {
    try {
        return (await authRequest('/me')).user;
    } catch (error) {
        if (error.status === 401) return null;
        throw error;
    }
}

export async function setupAdmin(payload) {
    return (await authRequest('/setup', {method: 'POST', body: JSON.stringify(payload)})).user;
}

export async function login(payload) {
    return (await authRequest('/login', {method: 'POST', body: JSON.stringify(payload)})).user;
}

export async function changePassword(payload) {
    return authRequest('/change-password', {method: 'POST', body: JSON.stringify(payload)});
}

export async function requestPasswordReset(email) {
    return authRequest('/forgot-password', {
        method: 'POST', body: JSON.stringify({email}),
    });
}

export async function resetPassword(payload) {
    return authRequest('/reset-password', {method: 'POST', body: JSON.stringify(payload)});
}

export async function logout() {
    await authRequest('/logout', {method: 'POST'});
}

export async function fetchDevices() {
    return (await authRequest('/devices')).devices;
}

export async function revokeDevice(sessionId) {
    await authRequest(`/devices/${encodeURIComponent(sessionId)}`, {method: 'DELETE'});
}

export async function revokeOtherDevices() {
    return authRequest('/devices/revoke-others', {method: 'POST'});
}

export async function fetchUsers() {
    return (await authRequest('/users')).users;
}

export async function fetchJellyfinUsers() {
    return (await authRequest('/jellyfin-users')).users;
}

export async function linkJellyfinUser(userId, jellyfinUserId) {
    return (await authRequest(`/users/${encodeURIComponent(userId)}/jellyfin`, {
        method: 'PUT',
        body: JSON.stringify({jellyfin_user_id: jellyfinUserId || null}),
    })).user;
}

export async function createUser(payload) {
    return (await authRequest('/users', {method: 'POST', body: JSON.stringify(payload)})).user;
}

export async function updateUser(userId, payload) {
    return (await authRequest(`/users/${encodeURIComponent(userId)}`, {
        method: 'PATCH', body: JSON.stringify(payload),
    })).user;
}

export async function deleteUser(userId) {
    await authRequest(`/users/${encodeURIComponent(userId)}`, {method: 'DELETE'});
}

export function startRecommendationSession() {
    return recommendationRequest('/recommendations/sessions', {method: 'POST'});
}

export function answerRecommendation(sessionId, payload) {
    return recommendationRequest(`/recommendations/sessions/${encodeURIComponent(sessionId)}/answers`, {
        method: 'POST', body: JSON.stringify(payload),
    });
}

export function confirmRecommendation(sessionId, payload) {
    return recommendationRequest(`/recommendations/sessions/${encodeURIComponent(sessionId)}/confirm`, {
        method: 'POST', body: JSON.stringify(payload),
    });
}

export function finishRecommendation(sessionId) {
    return recommendationRequest(`/recommendations/sessions/${encodeURIComponent(sessionId)}/finish`, {method: 'POST'});
}

export function recordRecommendationEvent(payload) {
    return recommendationRequest('/recommendations/events', {
        method: 'POST', body: JSON.stringify(payload),
    });
}

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

export async function fetchTMDBRating(mediaId) {
    const response = await fetch(`${API_BASE_URL}/medias/${encodeURIComponent(mediaId)}/tmdb-rating`);
    if (!response.ok) throw new Error(`Failed to fetch TMDB rating: ${response.statusText}`);
    return response.json();
}

export async function fetchTMDBMovieDetails(tmdbId) {
    const response = await fetch(`${API_BASE_URL}/tmdb/movies/${encodeURIComponent(tmdbId)}`);
    if (!response.ok) throw new Error(`Failed to fetch TMDB movie details: ${response.statusText}`);
    return response.json();
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

export async function updatePersonalMedia(mediaId, payload) {
    const response = await fetch(`${API_BASE_URL}/medias/${encodeURIComponent(mediaId)}/personal`, {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || `Failed to update personal media: ${response.statusText}`);
    }
    return response.json();
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

export async function fetchRentals() {
    const response = await fetch(`${API_BASE_URL}/rentals`);
    if (!response.ok) throw new Error((await response.json()).detail || 'Locations indisponibles');
    return response.json();
}

export async function requestRentalKeep(rentalId) {
    const response = await fetch(`${API_BASE_URL}/rentals/${rentalId}/keep`, {method: 'POST'});
    if (!response.ok) throw new Error((await response.json()).detail || 'Demande de conservation impossible');
    return response.json();
}

export async function fetchKeepRequests() {
    const response = await fetch(`${API_BASE_URL}/admin/rentals/keep-requests`);
    if (!response.ok) throw new Error((await response.json()).detail || 'Demandes indisponibles');
    return (await response.json()).requests;
}

export async function fetchCleanupPreview() {
    const response = await fetch(`${API_BASE_URL}/admin/rentals/cleanup-preview`);
    if (!response.ok) throw new Error((await response.json()).detail || 'Simulation indisponible');
    return response.json();
}

export async function fetchStorageStatus() {
    const response = await fetch(`${API_BASE_URL}/admin/storage/status`);
    if (!response.ok) throw new Error((await response.json()).detail || 'Stockage indisponible');
    return response.json();
}

export async function fetchAdminDashboard() {
    const response = await fetch(`${API_BASE_URL}/admin/dashboard`);
    if (!response.ok) throw new Error((await response.json()).detail || 'Tableau de bord indisponible');
    return response.json();
}

export async function fetchBackupStatus() {
    const response = await fetch(`${API_BASE_URL}/admin/system/backup`);
    if (!response.ok) throw new Error((await response.json()).detail || 'Sauvegarde indisponible');
    return response.json();
}

export async function createBackup() {
    const response = await fetch(`${API_BASE_URL}/admin/system/backup`, {method: 'POST'});
    if (!response.ok) throw new Error((await response.json()).detail || 'Sauvegarde impossible');
    return response.json();
}

export async function verifyBackup() {
    const response = await fetch(`${API_BASE_URL}/admin/system/backup/verify`, {method: 'POST'});
    if (!response.ok) throw new Error((await response.json()).detail || 'Vérification impossible');
    return response.json();
}

async function rentalDecision(rentalId, action) {
    const response = await fetch(`${API_BASE_URL}/admin/rentals/${rentalId}/${action}`, {method: 'POST'});
    if (!response.ok) throw new Error((await response.json()).detail || 'Action impossible');
    return response.json();
}

export const acceptKeepRequest = (rentalId) => rentalDecision(rentalId, 'keep');
export const refuseKeepRequest = (rentalId) => rentalDecision(rentalId, 'refuse');
export const extendRental = (rentalId) => rentalDecision(rentalId, 'extend');

export async function fetchNotifications() {
    const response = await fetch(`${API_BASE_URL}/notifications`);
    if (!response.ok) throw new Error((await response.json()).detail || 'Notifications indisponibles');
    return (await response.json()).notifications;
}

export async function markNotificationRead(notificationId) {
    const response = await fetch(`${API_BASE_URL}/notifications/${notificationId}/read`, {method: 'POST'});
    if (!response.ok) throw new Error((await response.json()).detail || 'Notification indisponible');
    return response.json();
}

export async function fetchMediaServerStatus() {
    const response = await fetch(`${API_BASE_URL}/media-server/status`);
    if (!response.ok) throw new Error('État des services indisponible');
    return response.json();
}

export async function syncMediaServer() {
    const response = await fetch(`${API_BASE_URL}/media-server/sync`, {method: 'POST'});
    const body = await readResponseBody(response);
    if (!response.ok) throw new Error(body?.detail || 'Synchronisation impossible');
    return body;
}

export async function importMediaServerLibrary() {
    const response = await fetch(`${API_BASE_URL}/media-server/import`, {method: 'POST'});
    const body = await readResponseBody(response);
    if (!response.ok) throw new Error(body?.detail || 'Import impossible');
    return body;
}

export async function fetchMediaServerActivity() {
    const response = await fetch(`${API_BASE_URL}/media-server/activity`);
    const body = await readResponseBody(response);
    if (!response.ok) throw new Error(body?.detail || 'Activité indisponible');
    return body;
}

export async function syncPlayback() {
    const response = await fetch(`${API_BASE_URL}/playback/sync`, {method: 'POST'});
    if (!response.ok) throw new Error((await response.json()).detail || 'Progression indisponible');
    return response.json();
}

export async function fetchPlaybackSummary() {
    const response = await fetch(`${API_BASE_URL}/playback/summary`);
    if (!response.ok) throw new Error((await response.json()).detail || 'Progression indisponible');
    return response.json();
}

export async function fetchDashboard() {
    const response = await fetch(`${API_BASE_URL}/dashboard`, {credentials: 'same-origin'});
    const body = await readResponseBody(response);
    if (!response.ok) throw new Error(body?.detail || body?.message || 'Dashboard indisponible');
    return body;
}

export async function addRecommendationToWatchlist(tmdbId) {
    const response = await fetch(`${API_BASE_URL}/recommendations/watchlist`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tmdb_id: tmdbId}),
    });
    if (!response.ok) throw new Error((await response.json()).detail || 'Ajout à la watchlist impossible');
    return response.json();
}

export async function createSeerrRequest(tmdbId, mediaType = 'movie') {
    const response = await fetch(`${API_BASE_URL}/seerr/requests`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tmdb_id: tmdbId, media_type: mediaType}),
    });
    if (!response.ok) throw new Error((await response.json()).detail || 'Demande Seerr impossible');
    return response.json();
}

export async function cancelSeerrRequest(requestId) {
    const response = await fetch(`${API_BASE_URL}/seerr/requests/${encodeURIComponent(requestId)}`, {
        method: 'DELETE',
        credentials: 'same-origin',
    });
    if (!response.ok) throw new Error((await response.json()).detail || 'Annulation impossible');
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
