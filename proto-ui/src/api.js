// API Client module for Backstage Python Backend

const API_BASE_URL = '/api';

export const SESSION_EXPIRED_EVENT = 'backstage:session-expired';

// A 401 on these endpoints is an expected answer (wrong password, not signed
// in yet), not the loss of an existing session.
const AUTH_PATHS_WITHOUT_SESSION = [
    '/auth/login', '/auth/setup', '/auth/status', '/auth/me',
    '/auth/forgot-password', '/auth/reset-password',
];

/** fetch() for the Backstage API: same-origin cookies, and a global signal
 *  when the session has expired so the app can return to the login screen
 *  instead of failing silently. */
async function apiFetch(input, init = {}) {
    const response = await fetch(input, {credentials: 'same-origin', ...init});
    if (response.status === 401) {
        const path = String(input).replace(API_BASE_URL, '').split('?')[0];
        const isPlainMeRead = path === '/auth/me' && (!init.method || init.method === 'GET');
        if (!AUTH_PATHS_WITHOUT_SESSION.includes(path) || (path === '/auth/me' && !isPlainMeRead)) {
            window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT));
        }
    }
    return response;
}

/** FastAPI returns `detail` as a string, or as a list of validation errors. */
function errorDetail(body, fallback) {
    const detail = body?.detail;
    if (typeof detail === 'string' && detail) return detail;
    if (Array.isArray(detail) && detail.length) {
        const first = detail[0];
        const field = Array.isArray(first?.loc) ? first.loc[first.loc.length - 1] : '';
        if (first?.type === 'string_too_short' && field === 'password') return 'Le mot de passe doit contenir au moins 8 caractères.';
        if (first?.type === 'string_too_short' && field === 'new_password') return 'Le mot de passe doit contenir au moins 8 caractères.';
        return 'Certains champs sont invalides. Vérifie ta saisie.';
    }
    return fallback;
}

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
    const response = await apiFetch(`${API_BASE_URL}/auth${path}`, {
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
        const error = new Error(errorDetail(body, 'Erreur d’authentification'));
        error.status = response.status;
        throw error;
    }
    return body;
}

async function recommendationRequest(path, options = {}) {
    const response = await apiFetch(`${API_BASE_URL}${path}`, {
        ...options,
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json',
            ...(options.headers || {}),
        },
    });
    const body = await response.json().catch(() => null);
    if (!response.ok) {
        const error = new Error(errorDetail(body, 'Erreur de recommandation'));
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

export async function completeInitialPasswordChange(payload) {
    return (await authRequest('/change-initial-password', {
        method: 'POST', body: JSON.stringify(payload),
    })).user;
}

export async function uploadMyAvatar(file) {
    const response = await apiFetch(`${API_BASE_URL}/auth/me/avatar`, {
        method: 'PUT', credentials: 'same-origin',
        headers: file.type ? {'Content-Type': file.type} : {}, body: file,
    });
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(errorDetail(body, 'Impossible d’enregistrer la photo'));
    return body.user;
}

export async function removeMyAvatar() {
    return (await authRequest('/me/avatar', {method: 'DELETE'})).user;
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

export function startRecommendationSession({ guided = false } = {}) {
    return recommendationRequest(`/recommendations/sessions${guided ? '?guided=true' : ''}`, {method: 'POST'});
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
        const response = await apiFetch(`${API_BASE_URL}/medias`);
        if (!response.ok) {
            throw new Error(`Impossible de charger la bibliothèque (erreur ${response.status}).`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error fetching medias:', error);
        throw error;
    }
}

export async function fetchTMDBRating(mediaId) {
    const response = await apiFetch(`${API_BASE_URL}/medias/${encodeURIComponent(mediaId)}/tmdb-rating`);
    if (!response.ok) throw new Error(`Failed to fetch TMDB rating: ${response.statusText}`);
    return response.json();
}

export async function fetchTMDBMovieDetails(tmdbId) {
    const response = await apiFetch(`${API_BASE_URL}/tmdb/movies/${encodeURIComponent(tmdbId)}`);
    if (!response.ok) throw new Error(`Failed to fetch TMDB movie details: ${response.statusText}`);
    return response.json();
}

/**
 * Update media fields (rating, review/userNotes, watched_in_cinema, watched_date, etc.).
 */
export async function updateMedia(mediaId, payload) {
    try {
        const response = await apiFetch(`${API_BASE_URL}/medias/${mediaId}`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            throw new Error(`La modification n’a pas pu être enregistrée (erreur ${response.status}).`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error updating media:', error);
        throw error;
    }
}

export async function updatePersonalMedia(mediaId, payload) {
    const response = await apiFetch(`${API_BASE_URL}/medias/${encodeURIComponent(mediaId)}/personal`, {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(errorDetail(detail, `La modification n’a pas pu être enregistrée (erreur ${response.status}).`));
    }
    return response.json();
}

export async function fetchAvailability(mediaId) {
    const response = await apiFetch(`${API_BASE_URL}/medias/${mediaId}/availability`);
    if (!response.ok) throw new Error(`Disponibilité impossible: ${response.statusText}`);
    return response.json();
}

export function getPlaybackManifest(mediaId, seasonNumber, episodeNumber, audioStreamIndex, subtitleStreamIndex, startTimeTicks) {
    const path = `${API_BASE_URL}/medias/${encodeURIComponent(mediaId)}/playback/manifest`;
    const params = new URLSearchParams();
    if (seasonNumber !== undefined && episodeNumber !== undefined) {
        params.set('season_number', seasonNumber);
        params.set('episode_number', episodeNumber);
    }
    if (audioStreamIndex !== undefined && audioStreamIndex !== null) params.set('audio_stream_index', audioStreamIndex);
    if (subtitleStreamIndex !== undefined && subtitleStreamIndex !== null) params.set('subtitle_stream_index', subtitleStreamIndex);
    if (startTimeTicks > 0) params.set('start_time_ticks', Math.floor(startTimeTicks));
    return params.size ? `${path}?${params}` : path;
}

export async function fetchPlaybackOptions(mediaId, seasonNumber, episodeNumber) {
    const path = `${API_BASE_URL}/medias/${encodeURIComponent(mediaId)}/playback/options`;
    const params = new URLSearchParams();
    if (seasonNumber !== undefined && episodeNumber !== undefined) {
        params.set('season_number', seasonNumber);
        params.set('episode_number', episodeNumber);
    }
    const response = await apiFetch(params.size ? `${path}?${params}` : path);
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Pistes Jellyfin indisponibles'));
    return response.json();
}

export async function fetchJellyfinPlaybackTarget(mediaId, seasonNumber, episodeNumber, {timeoutMs} = {}) {
    const path = `${API_BASE_URL}/medias/${encodeURIComponent(mediaId)}/playback/jellyfin-target`;
    const params = new URLSearchParams();
    if (seasonNumber !== undefined && episodeNumber !== undefined) {
        params.set('season_number', seasonNumber);
        params.set('episode_number', episodeNumber);
    }
    const controller = timeoutMs ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
    let response;
    try {
        response = await apiFetch(params.size ? `${path}?${params}` : path, {
            credentials: 'same-origin',
            signal: controller?.signal,
        });
    } finally {
        if (timer) clearTimeout(timer);
    }
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(errorDetail(body, 'Ouverture de Jellyfin impossible'));
    if (!body?.url || !body?.item_id) throw new Error('La cible de lecture Jellyfin est invalide');
    return body;
}

export async function fetchMediaServerOptions(mediaType) {
    const response = await apiFetch(`${API_BASE_URL}/media-server/options?media_type=${encodeURIComponent(mediaType)}`);
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Service non configuré'));
    return response.json();
}

export async function requestAcquisition(mediaId, payload) {
    const response = await apiFetch(`${API_BASE_URL}/medias/${mediaId}/acquisition`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Demande impossible'));
    return response.json();
}

export async function fetchRentals() {
    const response = await apiFetch(`${API_BASE_URL}/rentals`);
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Locations indisponibles'));
    return response.json();
}

export async function requestRentalKeep(rentalId) {
    const response = await apiFetch(`${API_BASE_URL}/rentals/${rentalId}/keep`, {method: 'POST'});
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Demande de conservation impossible'));
    return response.json();
}

export async function cancelRental(rentalId) {
    const response = await apiFetch(`${API_BASE_URL}/rentals/${rentalId}/cancel`, {method: 'POST'});
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Annulation impossible'));
    return response.json();
}

export async function fetchKeepRequests() {
    const response = await apiFetch(`${API_BASE_URL}/admin/rentals/keep-requests`);
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Demandes indisponibles'));
    return (await response.json()).requests;
}

export async function fetchAdminRentals() {
    const response = await apiFetch(`${API_BASE_URL}/admin/rentals`);
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Locations indisponibles'));
    return (await response.json()).rentals || [];
}

export async function fetchCleanupPreview() {
    const response = await apiFetch(`${API_BASE_URL}/admin/rentals/cleanup-preview`);
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Simulation indisponible'));
    return response.json();
}

export async function fetchStorageStatus() {
    const response = await apiFetch(`${API_BASE_URL}/admin/storage/status`);
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Stockage indisponible'));
    return response.json();
}

export async function fetchStorageOverview() {
    const response = await apiFetch(`${API_BASE_URL}/admin/storage/candidates`);
    const body = await readResponseBody(response);
    if (!response.ok) throw new Error(errorDetail(body, 'Candidats de stockage indisponibles'));
    return body || {candidates: [], history: []};
}

export async function fetchStorageCandidates() {
    return (await fetchStorageOverview()).candidates || [];
}

export async function fetchStorageCleanupHistory() {
    return (await fetchStorageOverview()).history || [];
}

export async function setStorageProtection(mediaId, protectedValue) {
    const response = await apiFetch(`${API_BASE_URL}/admin/storage/candidates/${encodeURIComponent(mediaId)}/protection`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({protected: protectedValue}),
    });
    const body = await readResponseBody(response);
    if (!response.ok) throw new Error(errorDetail(body, 'Protection impossible'));
    return body;
}

export async function deleteExpiredRentals() {
    const response = await apiFetch(`${API_BASE_URL}/admin/storage/expired/delete`, {method: 'POST'});
    const body = await readResponseBody(response);
    if (!response.ok) throw new Error(errorDetail(body, 'Suppression impossible'));
    return body;
}

/** Films ready on Jellyfin, plus the download state of every film the server tracks. */
export async function fetchLibraryAvailability() {
    const response = await apiFetch(`${API_BASE_URL}/library/available`);
    if (!response.ok) throw new Error('Disponibilités indisponibles');
    const body = await response.json();
    return { mediaIds: body.media_ids || [], states: body.states || {} };
}

export async function deleteMedia(mediaId, { deleteFiles = false } = {}) {
    const query = deleteFiles ? '?delete_files=true' : '';
    const response = await apiFetch(`${API_BASE_URL}/medias/${encodeURIComponent(mediaId)}${query}`, {method: 'DELETE'});
    const body = await readResponseBody(response);
    if (!response.ok) throw new Error(errorDetail(body, 'Suppression impossible'));
    return body;
}

export async function deleteStorageCandidate(mediaId) {
    const response = await apiFetch(`${API_BASE_URL}/admin/storage/candidates/${encodeURIComponent(mediaId)}`, {method: 'DELETE'});
    const body = await readResponseBody(response);
    if (!response.ok) throw new Error(errorDetail(body, 'Suppression impossible'));
    return body;
}

export async function fetchAdminDashboard() {
    const response = await apiFetch(`${API_BASE_URL}/admin/dashboard`);
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Tableau de bord indisponible'));
    return response.json();
}

export async function fetchBackupStatus() {
    const response = await apiFetch(`${API_BASE_URL}/admin/system/backup`);
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Sauvegarde indisponible'));
    return response.json();
}

export async function createBackup() {
    const response = await apiFetch(`${API_BASE_URL}/admin/system/backup`, {method: 'POST'});
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Sauvegarde impossible'));
    return response.json();
}

export async function verifyBackup() {
    const response = await apiFetch(`${API_BASE_URL}/admin/system/backup/verify`, {method: 'POST'});
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Vérification impossible'));
    return response.json();
}

async function rentalDecision(rentalId, action) {
    const response = await apiFetch(`${API_BASE_URL}/admin/rentals/${rentalId}/${action}`, {method: 'POST'});
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Action impossible'));
    return response.json();
}

export const acceptKeepRequest = (rentalId) => rentalDecision(rentalId, 'keep');
export const refuseKeepRequest = (rentalId) => rentalDecision(rentalId, 'refuse');
export const extendRental = (rentalId) => rentalDecision(rentalId, 'extend');
export const revokeRental = (rentalId) => rentalDecision(rentalId, 'revoke');

export async function fetchNotifications() {
    const response = await apiFetch(`${API_BASE_URL}/notifications`);
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Notifications indisponibles'));
    return (await response.json()).notifications;
}

export async function markNotificationRead(notificationId) {
    const response = await apiFetch(`${API_BASE_URL}/notifications/${notificationId}/read`, {method: 'POST'});
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Notification indisponible'));
    return response.json();
}

export async function fetchChatMessages(afterId = null) {
    const query = afterId ? `?after=${encodeURIComponent(afterId)}` : '';
    const response = await apiFetch(`${API_BASE_URL}/chat/messages${query}`);
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Salon indisponible'));
    return (await response.json()).messages;
}

export async function postChatMessage(body) {
    const response = await apiFetch(`${API_BASE_URL}/chat/messages`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({body}),
    });
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Message non envoyé'));
    return response.json();
}

export async function fetchMediaServerStatus() {
    const response = await apiFetch(`${API_BASE_URL}/media-server/status`);
    if (!response.ok) throw new Error('État des services indisponible');
    return response.json();
}

export async function syncMediaServer() {
    const response = await apiFetch(`${API_BASE_URL}/media-server/sync`, {method: 'POST'});
    const body = await readResponseBody(response);
    if (!response.ok) throw new Error(errorDetail(body, 'Synchronisation impossible'));
    return body;
}

export async function importMediaServerLibrary() {
    const response = await apiFetch(`${API_BASE_URL}/media-server/import`, {method: 'POST'});
    const body = await readResponseBody(response);
    if (!response.ok) throw new Error(errorDetail(body, 'Import impossible'));
    return body;
}

export async function fetchMediaServerActivity() {
    const response = await apiFetch(`${API_BASE_URL}/media-server/activity`);
    const body = await readResponseBody(response);
    if (!response.ok) throw new Error(errorDetail(body, 'Activité indisponible'));
    return body;
}

export async function syncPlayback() {
    const response = await apiFetch(`${API_BASE_URL}/playback/sync`, {method: 'POST'});
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Progression indisponible'));
    return response.json();
}

export async function fetchPlaybackSummary() {
    const response = await apiFetch(`${API_BASE_URL}/playback/summary`);
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Progression indisponible'));
    return response.json();
}

export async function fetchDashboard() {
    const response = await apiFetch(`${API_BASE_URL}/dashboard`, {credentials: 'same-origin'});
    const body = await readResponseBody(response);
    if (!response.ok) throw new Error(errorDetail(body, body?.message || 'Dashboard indisponible'));
    return body;
}

export async function addRecommendationToWatchlist(tmdbId) {
    const response = await apiFetch(`${API_BASE_URL}/recommendations/watchlist`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tmdb_id: tmdbId}),
    });
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Ajout à la watchlist impossible'));
    return response.json();
}

export async function createSeerrRequest(tmdbId, mediaType = 'movie', options = {}) {
    const response = await apiFetch(`${API_BASE_URL}/seerr/requests`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tmdb_id: tmdbId, media_type: mediaType, ...options}),
    });
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Demande Seerr impossible'));
    return response.json();
}

export async function cancelSeerrRequest(requestId) {
    const response = await apiFetch(`${API_BASE_URL}/seerr/requests/${encodeURIComponent(requestId)}`, {
        method: 'DELETE',
        credentials: 'same-origin',
    });
    if (!response.ok) throw new Error(errorDetail(await response.json().catch(() => null), 'Annulation impossible'));
    return response.json();
}

/**
 * Search TMDB for movies by query.
 */
export async function searchTMDB(query) {
    try {
        const response = await apiFetch(`${API_BASE_URL}/tmdb/search?query=${encodeURIComponent(query)}`);
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
        const response = await apiFetch(`${API_BASE_URL}/medias/${mediaId}/relink_tmdb`, {
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
    const response = await apiFetch(`${API_BASE_URL}/medias/from_tmdb`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({tmdb_id: tmdbId}),
    });
    if (!response.ok) throw new Error(`Failed to create media: ${response.statusText}`);
    return response.json();
}

export async function searchTMDBTV(query) {
    const response = await apiFetch(`${API_BASE_URL}/tmdb/search/tv?query=${encodeURIComponent(query)}`);
    if (!response.ok) throw new Error(`Failed to search TV: ${response.statusText}`);
    return response.json();
}

export async function searchTMDBPerson(query) {
    const response = await apiFetch(`${API_BASE_URL}/tmdb/search/person?query=${encodeURIComponent(query)}`);
    if (!response.ok) throw new Error(`Failed to search TMDB people: ${response.statusText}`);
    return response.json();
}

export async function createSeriesFromTMDB(tmdbId) {
    const response = await apiFetch(`${API_BASE_URL}/series/from_tmdb`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({tmdb_id: tmdbId}),
    });
    if (!response.ok) throw new Error(`Failed to create series: ${response.statusText}`);
    return response.json();
}

export async function fetchSeriesEpisodes(mediaId) {
    const response = await apiFetch(`${API_BASE_URL}/medias/${mediaId}/episodes`);
    if (!response.ok) throw new Error(`Failed to fetch series episodes: ${response.statusText}`);
    return response.json();
}

export async function updateEpisode(episodeId, watched) {
    const response = await apiFetch(`${API_BASE_URL}/episodes/${episodeId}`, {
        method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({watched}),
    });
    if (!response.ok) throw new Error(`L’épisode n’a pas pu être mis à jour (erreur ${response.status}).`);
    return response.json();
}

export async function refreshSeriesFromTMDB(mediaId) {
    const response = await apiFetch(`${API_BASE_URL}/series/${mediaId}/refresh`, { method: 'POST' });
    if (!response.ok) throw new Error(`Failed to refresh series: ${response.statusText}`);
    return response.json();
}

export async function fetchPlaybackHealth() {
    const response = await apiFetch(`${API_BASE_URL}/media-server/health`);
    if (!response.ok) return 'unknown';
    const body = await readResponseBody(response);
    return body?.playback || 'unknown';
}

export async function updateSeasonWatched(mediaId, seasonNumber, watched) {
    const response = await apiFetch(`${API_BASE_URL}/medias/${encodeURIComponent(mediaId)}/seasons/${seasonNumber}/watched`, {
        method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({watched}),
    });
    if (!response.ok) throw new Error(`La saison n’a pas pu être mise à jour (erreur ${response.status}).`);
    return response.json();
}

async function journalRequest(path, init, fallback) {
    const response = await apiFetch(`${API_BASE_URL}${path}`, init);
    if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        const error = new Error(errorDetail(detail, `${fallback} (erreur ${response.status}).`));
        error.status = response.status;
        throw error;
    }
    return response.status === 204 ? null : response.json();
}

const jsonBody = (method, payload) => ({
    method,
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
});

/** Journal « Vu » : entries of the signed-in user only. */
export async function fetchJournal() {
    return journalRequest('/journal', {}, 'Le journal n’a pas pu être chargé');
}

export async function createJournalEntry(payload) {
    return journalRequest('/journal', jsonBody('POST', payload), 'Le film n’a pas pu être ajouté au journal');
}

export async function updateJournalEntry(entryId, payload) {
    return journalRequest(`/journal/${encodeURIComponent(entryId)}`, jsonBody('PATCH', payload), 'L’entrée n’a pas pu être modifiée');
}

export async function deleteJournalEntry(entryId) {
    return journalRequest(`/journal/${encodeURIComponent(entryId)}`, {method: 'DELETE'}, 'L’entrée n’a pas pu être supprimée');
}

/** Shared film lists (every flatmate sees and edits them). */
export async function fetchFilmLists() {
    return journalRequest('/lists', {}, 'Les listes n’ont pas pu être chargées');
}

export async function createFilmList(name) {
    return journalRequest('/lists', jsonBody('POST', {name}), 'La liste n’a pas pu être créée');
}

export async function renameFilmList(listId, name) {
    return journalRequest(`/lists/${encodeURIComponent(listId)}`, jsonBody('PATCH', {name}), 'La liste n’a pas pu être renommée');
}

export async function deleteFilmList(listId) {
    return journalRequest(`/lists/${encodeURIComponent(listId)}`, {method: 'DELETE'}, 'La liste n’a pas pu être supprimée');
}

export async function fetchFilmList(listId) {
    return journalRequest(`/lists/${encodeURIComponent(listId)}`, {}, 'La liste n’a pas pu être chargée');
}

export async function addFilmListItem(listId, tmdbId) {
    return journalRequest(`/lists/${encodeURIComponent(listId)}/items`, jsonBody('POST', {tmdb_id: tmdbId}), 'Le film n’a pas pu être ajouté à la liste');
}

export async function removeFilmListItem(listId, tmdbId) {
    return journalRequest(`/lists/${encodeURIComponent(listId)}/items/${encodeURIComponent(tmdbId)}`, {method: 'DELETE'}, 'Le film n’a pas pu être retiré');
}
