import React, { useCallback, useState, useEffect, useRef } from 'react';
import AccountPanel from './AccountPanel';
import AdminCenter from './components/AdminCenter';
import Icon from './components/Icon';
import RecommendationFlow from './components/RecommendationFlow';
import FilmDetailView from './components/FilmDetailView';
import DashboardHome from './components/DashboardHome';
import TMDBMoviePreview from './components/TMDBMoviePreview';
import NotificationBell from './components/NotificationBell';
import ChatDock from './components/ChatDock';
import JournalView from './components/JournalView';
import SeenDialog from './components/SeenDialog';
import useLayer from './useLayer';
import { useAuth } from './auth-context';
import { fetchPlaybackHealth, fetchMedias, updateMedia, deleteMedia, updatePersonalMedia, searchTMDB, searchTMDBPerson, relinkTMDB, createMediaFromTMDB, searchTMDBTV, createSeriesFromTMDB, fetchSeriesEpisodes, updateEpisode, updateSeasonWatched, refreshSeriesFromTMDB, fetchAvailability, fetchJellyfinPlaybackTarget, fetchMediaServerOptions, fetchMediaServerStatus, requestAcquisition, fetchRentals, requestRentalKeep, cancelRental, fetchMediaServerActivity, syncMediaServer, syncPlayback, fetchLibraryAvailability, fetchTMDBRating, fetchTMDBMovieDetails, fetchDashboard, addRecommendationToWatchlist, createSeerrRequest, cancelSeerrRequest, createJournalEntry } from './api';
import { enRouteBadge, filterAndSortMovies, filterOptions, libraryPlacement, normalizeStatus, mediaPath, parseMediaPath, searchLibrary } from './library';

// Read once, before anything changes the address bar.
const INITIAL_DEEP_LINK = parseMediaPath(window.location.pathname);
import { replaceEpisode } from './series';
import SeriesDetailView from './components/SeriesDetailView';
import { DEFAULT_MAX_ACTIVE_RENTALS, DEFAULT_MAX_QUEUED_RENTALS, countQueuedRentals, countRentalsInUse, indexRentalsByMedia, isOpenRental, isQueuedRental, rentalCardBadge, rentalExpiryLabel, rentalStatusLabel } from './rentals';

const ALL_GENRES = [
    'Action', 'Aventure', 'Animation', 'Biopic', 'Comédie', 'Crime',
    'Documentaire', 'Drame', 'Familial', 'Fantastique', 'Guerre',
    'Histoire', 'Horreur', 'Musique', 'Mystère', 'Romance',
    'Science-Fiction', 'Thriller', 'Western'
];

// Helper SVG Star Component with explicit outlines for empty/half/full states
const StarIcon = ({ fillRatio = 0, size = 20, isDarkMode = false }) => {
    const gradientId = React.useId();
    const strokeColor = "#f59e0b"; // Vibrant amber outline
    const emptyFill = isDarkMode ? "rgba(255, 255, 255, 0.08)" : "#f1f5f9"; // Soft background for empty star outline

    return (
        <svg width={size} height={size} viewBox="0 0 24 24" className="inline-block transition-transform hover:scale-110 select-none">
            <defs>
                <linearGradient id={gradientId}>
                    <stop offset="50%" stopColor="#f59e0b" />
                    <stop offset="50%" stopColor={emptyFill} />
                </linearGradient>
            </defs>
            <path
                d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"
                fill={fillRatio === 1 ? "#f59e0b" : fillRatio === 0.5 ? `url(#${gradientId})` : emptyFill}
                stroke={strokeColor}
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
        </svg>
    );
};

// Fallback initial data if API is offline
const INITIAL_MOVIES = [];

// TMDB still answers some TV genres in English, even in French.
const GENRE_TRANSLATIONS = {
    'Action & Adventure': 'Action & Aventure',
    'Sci-Fi & Fantasy': 'Science-Fiction & Fantastique',
    'War & Politics': 'Guerre & Politique',
    Kids: 'Enfants',
    News: 'Actualités',
    Reality: 'Téléréalité',
    Soap: 'Feuilleton',
    Talk: 'Talk-show',
};
const translateGenre = (genre) => GENRE_TRANSLATIONS[genre] || genre;

const LIBRARY_BATCH_SIZE = 48;
// One color per badge meaning, shared by the library cards and the « En route » row.
const BADGE_TONE_CLASSES = {
    cinema: 'bg-rose-600/90',
    upcoming: 'bg-amber-500/90',
    requested: 'bg-slate-600/90',
    searching: 'bg-sky-600/90',
    downloading: 'bg-[#635bff]/90',
    rental: 'bg-[#635bff]/90',
    error: 'bg-red-600/90',
    kept: 'bg-emerald-600/90',
};
// A roommate should hear back within seconds when the media server is down.
const PLAYER_TARGET_TIMEOUT_MS = 10000;
const PLAYER_ACK_TIMEOUT_MS = 15000;

/** Callback ref: calls `onVisible` when the element scrolls near the viewport. */
const observeLibrarySentinel = (onVisible) => (element) => {
    if (!element || typeof IntersectionObserver === 'undefined') return undefined;
    const observer = new IntersectionObserver((entries) => {
        if (entries.some((entry) => entry.isIntersecting)) onVisible();
    }, {rootMargin: '600px 0px'});
    observer.observe(element);
    return () => observer.disconnect();
};

/** 169 -> "2 h 49", 95 -> "1 h 35", 45 -> "45 min". */
const formatRuntime = (minutes) => {
    const hours = Math.floor(minutes / 60);
    const rest = minutes % 60;
    if (!hours) return `${rest} min`;
    return `${hours} h ${String(rest).padStart(2, '0')}`;
};

const getMediaAction = (mediaType, availability, isAdmin = true) => {
    if (availability?.jellyfin_id) {
        return { label: 'Lire', canPlay: true, disabled: false };
    }
    if (availability?.state === 'downloading') {
        return { label: 'Téléchargement en cours', canPlay: false, disabled: true };
    }
    if (availability?.state === 'imported') {
        const provider = mediaType === 'Série' ? 'Sonarr' : 'Radarr';
        return { label: `Téléchargé côté ${provider} — Jellyfin non confirmé`, canPlay: false, disabled: true };
    }
    if (['requested', 'searching'].includes(availability?.state)) {
        return { label: 'Demande envoyée — pas encore disponible sur Jellyfin', canPlay: false, disabled: true };
    }
    return {
        label: mediaType === 'Série'
            ? (isAdmin ? 'Demander cette série' : 'Louer une saison')
            : (isAdmin ? 'Demander ce film' : 'Louer ce film'),
        canPlay: false,
        disabled: false,
    };
};

const parseMediaList = (value, fallback = []) => {
    if (Array.isArray(value)) return value;
    if (typeof value !== 'string' || !value.trim()) return fallback;
    try {
        const parsed = JSON.parse(value);
        return Array.isArray(parsed) ? parsed : [value];
    } catch {
        return [value];
    }
};

const mapMediaToMovie = (media, index = 0) => {
    try {
        const tagsList = parseMediaList(media.tags);
        const castList = parseMediaList(media.cast, []);
        const categories = parseMediaList(media.categories, ['Film']).map(translateGenre);
        const supports = parseMediaList(media.support);
        let rawRating = 0;
        if (typeof media.rating === 'string' && media.rating.trim()) {
            const starMatches = media.rating.match(/⭐️|⭐|★/g);
            rawRating = starMatches?.length || parseFloat(media.rating) || 0;
        } else if (typeof media.rating === 'number') {
            rawRating = media.rating;
        }
        const numericRating = Math.min(5, Math.max(0, rawRating));

        return {
            id: media.id || `media-${index}`,
            type: media.type || 'Film',
            title: media.title || 'Sans titre',
            originalTitle: media.original_title || '',
            tmdbId: media.tmdb_id || null,
            director: media.director || (media.type === 'Série' ? 'Créateur inconnu' : 'Réalisateur inconnu'),
            year: media.release_date ? (new Date(media.release_date).getFullYear() || '—') : '—',
            releaseDate: media.release_date || null,
            genre: categories,
            poster: media.cover_url || 'https://images.unsplash.com/photo-1536440136628-849c177e76a1?auto=format&fit=crop&w=600&q=80',
            backdrop: media.backdrop_url || media.cover_url || 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?auto=format&fit=crop&w=1200&q=80',
            hasBackdrop: Boolean(media.backdrop_url),
            synopsis: media.synopsis || 'Aucun synopsis disponible pour le moment.',
            cast: castList.length > 0 ? castList : ['Acteur principal'],
            rating: numericRating,
            userNotes: media.review || '',
            status: numericRating > 0 ? 'Terminé' : normalizeStatus(media.status || 'À regarder'),
            isFavorite: tagsList.includes('Favoris'),
            isWatchlist: Boolean(media.is_watchlist),
            runtime: '', // real runtime comes from TMDB when the detail opens (tmdbRating.runtime)
            supports,
            support: media.support || null,
            ratingCount: 1,
            watchedInCinema: media.watched_in_cinema || false,
            watchedDate: media.watched_date || '',
            createdAt: media.created_at || '',
        };
    } catch (itemError) {
        console.error('Erreur mapping item', media?.title, itemError);
        return null;
    }
};

export default function BackstagePrototype() {
    const {user} = useAuth();
    const isAdmin = user?.role === 'admin';
    const [movies, setMovies] = useState(INITIAL_MOVIES);
    const [activeView, setActiveView] = useState('dashboard');
    const [dashboardData, setDashboardData] = useState(null);
    const [dashboardLoading, setDashboardLoading] = useState(true);
    const [dashboardError, setDashboardError] = useState(null);
    const [collection, setCollection] = useState('Films');
    const [catalogueLoading, setLoading] = useState(true);
    const [catalogueError, setError] = useState(null);
    const [activeFilter, setActiveFilter] = useState('all'); // 'all' | 'watched' | 'unwatched' | 'watchlist' | 'favorite'
    const [selectedMovie, setSelectedMovie] = useState(null);
    const [tmdbRating, setTMDBRating] = useState({mediaId: null, loading: false, rating: null});
    const libraryScrollTop = useRef(0);
    // A shared link (/film/<id>, /serie/<id>) opens that fiche once the library is loaded.
    // The address goes back to "/" first, so Back closes the fiche instead of leaving.
    const pendingDeepLink = useRef(INITIAL_DEEP_LINK);
    useEffect(() => {
        if (INITIAL_DEEP_LINK && parseMediaPath(window.location.pathname)) window.history.replaceState(window.history.state, '', '/');
    }, []);
    const [selectedSeries, setSelectedSeries] = useState(null);
    const [seriesEpisodes, setSeriesEpisodes] = useState([]);
    const [, setSeriesProgress] = useState(null);
    const [seriesView, setSeriesView] = useState(null);
    const [seriesLoading, setSeriesLoading] = useState(false);
    const [seriesRefreshing, setSeriesRefreshing] = useState(false);
    const seriesViewTimer = useRef(null);
    const seriesRequestId = useRef(0);
    const selectedSeriesId = useRef(null);
    const episodeUpdateQueue = useRef(Promise.resolve());
    const episodeIntents = useRef(new Map());
    const [searchQuery, setSearchQuery] = useState('');
    const [headerSearchResults, setHeaderSearchResults] = useState([]);
    const [headerSearchTotal, setHeaderSearchTotal] = useState({count: 0, total: 0, collection: 'Films'});
    const [headerSearchLoading, setHeaderSearchLoading] = useState(false);
    const [headerSearchOpen, setHeaderSearchOpen] = useState(false);
    // Below the lg breakpoint the search field lives in a second header row,
    // opened from a search icon, so it never overlaps the header buttons.
    const [mobileSearchOpen, setMobileSearchOpen] = useState(false);
    const mobileSearchInputRef = useRef(null);
    const headerSearchRequest = useRef(0);
    const [filters, setFilters] = useState({ genre: '', director: '', status: '', support: '' });
    const [sort, setSort] = useState({ key: 'createdAt', direction: 'desc' });
    const [showAddDialog, setShowAddDialog] = useState(false);
    // Library film being logged as « Vu » (opens SeenDialog).
    const [seenDialogMovie, setSeenDialogMovie] = useState(null);
    const [libraryWindow, setLibraryWindow] = useState({key: '', count: LIBRARY_BATCH_SIZE});
    const [addQuery, setAddQuery] = useState('');
    const [addResults, setAddResults] = useState([]);
    const [addSearching, setAddSearching] = useState(false);
    const addSearchId = useRef(0);
    const [addLoading, setAddLoading] = useState(false);
    const [mediaAvailability, setMediaAvailability] = useState(null);
    const [mediaServerError, setMediaServerError] = useState(null);
    const [mediaServerOptions, setMediaServerOptions] = useState(null);
    const [showAcquisitionModal, setShowAcquisitionModal] = useState(false);
    const [availabilityByMedia, setAvailabilityByMedia] = useState({});
    const [availableMediaIds, setAvailableMediaIds] = useState(() => new Set());
    const [onlyAvailable, setOnlyAvailable] = useState(false);
    const [onlyMine, setOnlyMine] = useState(false);
    const [libraryStates, setLibraryStates] = useState({});
    const [rentalsByMedia, setRentalsByMedia] = useState({});
    const [rentals, setRentals] = useState([]);
    const [maxActiveRentals, setMaxActiveRentals] = useState(DEFAULT_MAX_ACTIVE_RENTALS);
    const [maxQueuedRentals, setMaxQueuedRentals] = useState(DEFAULT_MAX_QUEUED_RENTALS);
    const [acquisitionBusy, setAcquisitionBusy] = useState(false);
    const [pendingSeerrFilm, setPendingSeerrFilm] = useState(null);
    const [actorQuery, setActorQuery] = useState('');
    const [actorSuggestions, setActorSuggestions] = useState([]);
    const [actorSearchLoading, setActorSearchLoading] = useState(false);
    const [acquisitionForm, setAcquisitionForm] = useState({ quality_profile_id: '', language_profile_id: '', root_folder: '', monitor: 'all' });
    const [isDarkMode, setIsDarkMode] = useState(false); // Theme toggle state
    const [showAccountPanel, setShowAccountPanel] = useState(false);
    const [showAdminCenter, setShowAdminCenter] = useState(false);
    const [playbackHealth, setPlaybackHealth] = useState('unknown');
    const [showRecommendationFlow, setShowRecommendationFlow] = useState(false);
    const [tmdbPreview, setTMDBPreview] = useState({open: false, loading: false, movie: null, recommendation: null, error: null});
    const [tmdbWatchlistBusy, setTMDBWatchlistBusy] = useState(false);
    const [seerrRequestBusy, setSeerrRequestBusy] = useState(false);
    const [cancellingRequest, setCancellingRequest] = useState(null);

    // TMDB Relink Modal State
    const [showRelinkModal, setShowRelinkModal] = useState(false);
    const [showNotesModal, setShowNotesModal] = useState(false);
    const [tmdbSearchQuery, setTmdbSearchQuery] = useState('');
    const [tmdbResults, setTmdbResults] = useState([]);
    const [tmdbLoading, setTmdbLoading] = useState(false);
    const [tmdbError, setTmdbError] = useState(null);

    const loadDashboard = async () => {
        try {
            setDashboardLoading(true);
            const data = await fetchDashboard();
            setDashboardData(data);
            setDashboardError(null);
        } catch (error) {
            console.error('Erreur de chargement du dashboard:', error);
            setDashboardError(error.message || 'Dashboard indisponible.');
        } finally {
            setDashboardLoading(false);
        }
    };

    const handleSearchTMDB = async (query) => {
        if (!query || !query.trim()) return;
        try {
            setTmdbLoading(true);
            setTmdbError(null);
            const results = await searchTMDB(query);
            setTmdbResults(results || []);
        } catch (err) {
            console.error('Erreur recherche TMDB:', err);
            setTmdbError('Impossible de rechercher sur TMDB.');
        } finally {
            setTmdbLoading(false);
        }
    };

    const selectedMedia = selectedMovie || selectedSeries;
    const selectedMovieId = selectedMovie?.id;
    const mediaAction = getMediaAction(selectedMedia?.type, mediaAvailability?.availability, isAdmin);
    const selectedRental = selectedMedia?.id ? rentalsByMedia[selectedMedia.id] : null;
    const playbackOffline = mediaAction.canPlay && playbackHealth === 'offline';

    const openMovie = (movie) => {
        libraryScrollTop.current = window.scrollY;
        setSelectedMovie(movie);
    };

    const shareMedia = async (media) => {
        const url = `${window.location.origin}${mediaPath(media)}`;
        try {
            if (navigator.share) {
                await navigator.share({title: media.title, url});
                return;
            }
            await navigator.clipboard.writeText(url);
            showToast('Lien copié — envoie-le à tes colocs.');
        } catch (error) {
            if (error?.name !== 'AbortError') showToast(`Copie impossible. Voici le lien : ${url}`, 'info');
        }
    };

    const closeMovie = useCallback(() => {
        setSelectedMovie(null);
        window.requestAnimationFrame(() => window.scrollTo(0, libraryScrollTop.current));
    }, []);

    useEffect(() => {
        if (!selectedMovieId) {
            setTMDBRating({mediaId: null, loading: false, rating: null});
            return undefined;
        }

        let cancelled = false;
        const mediaId = selectedMovieId;
        setTMDBRating({mediaId, loading: true, rating: null});
        fetchTMDBRating(mediaId)
            .then(({rating, runtime, tmdb_id: resolvedTMDBId}) => {
                if (!cancelled) {
                    setTMDBRating({mediaId, loading: false, rating, runtime: runtime || null});
                    if (resolvedTMDBId) {
                        setSelectedMovie((current) => current?.id === mediaId ? {...current, tmdbId: resolvedTMDBId} : current);
                    }
                }
            })
            .catch(() => {
                if (!cancelled) setTMDBRating({mediaId, loading: false, rating: null});
            });

        return () => { cancelled = true; };
    }, [selectedMovieId]);

    const loadRentals = () => fetchRentals().then((result) => {
        const nextRentals = result.rentals || [];
        setRentals(nextRentals);
        setRentalsByMedia(indexRentalsByMedia(nextRentals));
        if (result.max_active_rentals) setMaxActiveRentals(result.max_active_rentals);
        if (result.max_queued_rentals) setMaxQueuedRentals(result.max_queued_rentals);
    }).catch(() => {});

    const openJellyfinPlayer = (mediaId, seasonNumber, episodeNumber) => {
        if (!mediaId) return;
        // Open synchronously inside the user's click so the browser does not
        // block the tab while the authenticated Backstage API resolves Jellyfin.
        const playerWindow = window.open('about:blank', '_blank');
        if (!playerWindow) {
            showToast('Ton navigateur a bloqué le lecteur : autorise les fenêtres surgissantes pour Backstage, puis réessaie.', 'error');
            return;
        }

        const requestId = globalThis.crypto?.randomUUID?.()
            || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
        let sendInterval;
        let timeout;
        let expectedOrigin;
        const cleanup = () => {
            window.clearInterval(sendInterval);
            window.clearTimeout(timeout);
            window.removeEventListener('message', onPlaybackAck);
        };
        const onPlaybackAck = (event) => {
            if (event.source !== playerWindow || event.origin !== expectedOrigin
                || event.data?.type !== 'backstage:play-ack'
                || event.data?.requestId !== requestId) return;
            cleanup();
            if (!event.data.started) {
                showToast(event.data.reason || 'Le lecteur n’a pas pu démarrer la lecture. Réessaie dans un instant.', 'error');
            }
        };
        window.addEventListener('message', onPlaybackAck);
        showToast('Ouverture du lecteur…', 'info');

        fetchJellyfinPlaybackTarget(mediaId, seasonNumber, episodeNumber, {timeoutMs: PLAYER_TARGET_TIMEOUT_MS}).then((target) => {
            if (playerWindow.closed) {
                cleanup();
                return;
            }
            expectedOrigin = new URL(target.url).origin;
            playerWindow.location.replace(target.url);
            const message = {
                type: 'backstage:play-request',
                requestId,
                itemId: target.item_id,
            };
            sendInterval = window.setInterval(() => {
                if (playerWindow.closed) {
                    cleanup();
                    return;
                }
                playerWindow.postMessage(message, expectedOrigin);
            }, 400);
            timeout = window.setTimeout(() => {
                cleanup();
                showToast(isAdmin ? 'Jellyfin a ouvert la fiche, mais son script de lecture ne répond pas. Mets à jour le script JavaScript Injector.' : 'Le lecteur s’est ouvert mais la lecture ne démarre pas. Appuie sur Lecture dans le lecteur.', 'error');
            }, PLAYER_ACK_TIMEOUT_MS);
        }).catch((error) => {
            cleanup();
            if (!playerWindow.closed) playerWindow.close();
            const unreachable = 'Le lecteur ne répond pas pour le moment. Réessaie dans quelques minutes, ou préviens l’administrateur.';
            showToast(error.name === 'AbortError' || !isAdmin ? unreachable : (error.message || unreachable), 'error');
        });
    };

    const openPlayer = () => openJellyfinPlayer(selectedMedia?.id);
    const openEpisodePlayer = (episode) => openJellyfinPlayer(
        selectedSeries?.id, episode.season_number, episode.episode_number,
    );

    useEffect(() => {
        if (!selectedMedia?.id) return;
        let cancelled = false;
        const loadAvailability = () => fetchAvailability(selectedMedia.id)
            .then((result) => {
                if (cancelled) return;
                setMediaAvailability(result);
                const availability = result?.availability;
                const onServer = Boolean(availability?.jellyfin_id)
                    || ['imported', 'available'].includes(availability?.state);
                if (onServer) {
                    refreshCanonicalMedia(selectedMedia.id).catch((error) => {
                        console.error('Erreur de synchronisation du média serveur:', error);
                    });
                }
            })
            .catch(() => { if (!cancelled) setMediaAvailability(null); });
        setMediaAvailability(null);
        loadAvailability();
        window.addEventListener('focus', loadAvailability);
        return () => {
            cancelled = true;
            window.removeEventListener('focus', loadAvailability);
        };
    }, [selectedMedia?.id]);

    useEffect(() => {
        if (!selectedMedia?.id || !mediaAction.canPlay) return undefined;
        let cancelled = false;
        fetchPlaybackHealth()
            .then((state) => { if (!cancelled) setPlaybackHealth(state); })
            .catch(() => { if (!cancelled) setPlaybackHealth('unknown'); });
        return () => { cancelled = true; };
    }, [selectedMedia?.id, mediaAction.canPlay]);

    useEffect(() => {
        setActorQuery('');
        setActorSuggestions([]);
    }, [selectedMovie?.id]);

    useEffect(() => {
        const query = actorQuery.trim();
        if (query.length < 2) {
            setActorSuggestions([]);
            setActorSearchLoading(false);
            return undefined;
        }
        let cancelled = false;
        const timer = window.setTimeout(async () => {
            setActorSearchLoading(true);
            try {
                const results = await searchTMDBPerson(query);
                if (!cancelled) setActorSuggestions(results || []);
            } catch (error) {
                console.error('Erreur recherche acteur TMDB:', error);
                if (!cancelled) setActorSuggestions([]);
            } finally {
                if (!cancelled) setActorSearchLoading(false);
            }
        }, 250);
        return () => {
            cancelled = true;
            window.clearTimeout(timer);
        };
    }, [actorQuery]);

    useEffect(() => {
        if (!user?.id) return;
        loadRentals();
        loadDashboard();
        syncPlayback().catch((error) => {
            console.error('Erreur synchronisation progression Jellyfin:', error);
        });
    }, [user?.id, user?.jellyfin_user_id]);

    const [toastNotification, setToastNotification] = useState(null);

    const showToast = (message, type = 'success') => {
        setToastNotification({ message, type });
        setTimeout(() => {
            setToastNotification((prev) => (prev?.message === message ? null : prev));
        }, 4000);
    };

    const openAcquisition = async () => {
        if (!isAdmin) {
            setMediaServerError(null);
            setShowAcquisitionModal(true);
            return;
        }
        try {
            setMediaServerError(null);
            let options;
            try {
                options = await fetchMediaServerOptions(selectedMedia.type || 'Film');
            } catch (optionsError) {
                const status = await fetchMediaServerStatus();
                if (!status.seerr?.configured) throw optionsError;
                options = { quality_profiles: [], language_profiles: [], root_folders: [] };
            }
            setMediaServerOptions(options);
            setAcquisitionForm({
                quality_profile_id: options.default_quality_profile_id || options.quality_profiles?.[0]?.id || '',
                language_profile_id: options.language_profiles?.[0]?.id || '',
                root_folder: options.root_folders?.[0]?.path || '', monitor: 'all',
            });
            setShowAcquisitionModal(true);
        } catch (error) {
            const errorMsg = error.message || 'Impossible d\'ouvrir le formulaire d\'ajout au serveur.';
            setMediaServerError(errorMsg);
            showToast(`Erreur serveur : ${errorMsg}`, 'error');
        }
    };

    const prepareSeerrFilmRequest = async (result) => {
        setAddLoading(true);
        setMediaServerError(null);
        try {
            const options = await fetchMediaServerOptions('Film');
            setMediaServerOptions(options);
            setAcquisitionForm({
                quality_profile_id: options.default_quality_profile_id || options.quality_profiles?.[0]?.id || '',
                language_profile_id: '',
                root_folder: options.root_folders?.[0]?.path || '',
                monitor: 'all',
            });
            setPendingSeerrFilm(result);
            setShowAddDialog(false);
            setShowAcquisitionModal(true);
        } catch (error) {
            setMediaServerError(error.message || 'Impossible de charger les profils Radarr.');
            showToast(error.message || 'Impossible de préparer la demande Seerr.', 'error');
        } finally {
            setAddLoading(false);
        }
    };

    const submitAcquisition = async () => {
        setAcquisitionBusy(true);
        try {
            if (pendingSeerrFilm) {
                const result = await createSeerrRequest(pendingSeerrFilm.tmdb_id, 'movie', {
                    quality_profile_id: acquisitionForm.quality_profile_id ? Number(acquisitionForm.quality_profile_id) : null,
                    root_folder: acquisitionForm.root_folder || null,
                });
                setShowAcquisitionModal(false);
                setPendingSeerrFilm(null);
                setMediaServerError(null);
                showToast(result.already_requested
                    ? `« ${pendingSeerrFilm.title} » est déjà demandé ou disponible.`
                    : `Demande Seerr envoyée pour « ${pendingSeerrFilm.title} » avec le profil choisi.`, 'success');
                await refreshLibraryState({sync: true});
                return;
            }
            const result = await requestAcquisition(selectedMedia.id, isAdmin ? {
                ...acquisitionForm,
                quality_profile_id: acquisitionForm.quality_profile_id ? Number(acquisitionForm.quality_profile_id) : null,
                root_folder: acquisitionForm.root_folder || null,
                language_profile_id: acquisitionForm.language_profile_id ? Number(acquisitionForm.language_profile_id) : null,
            } : {});
            setMediaAvailability({ availability: result.availability, playback_url: null });
            if (result.rental) setRentalsByMedia((current) => ({...current, [selectedMedia.id]: result.rental}));
            setShowAcquisitionModal(false);
            if (isAdmin) showToast(result.already_requested
                ? `« ${selectedMedia?.title} » est déjà demandé ou sur le serveur : aucune nouvelle demande envoyée.`
                : `"${selectedMedia?.title}" a bien été ajouté au serveur !`, 'success');
            else if (!result.rental) showToast(`« ${selectedMedia?.title} » est déjà dans la bibliothèque commune : bonne séance !`, 'success');
            else showToast(result.rental.status === 'available'
                ? `« ${selectedMedia?.title} » est loué et déjà disponible.`
                : `« ${selectedMedia?.title} » est loué : tu seras prévenu dès qu’il sera disponible.`, 'success');
            await Promise.all([refreshLibraryState({sync: isAdmin}), isAdmin ? null : loadRentals()]);
        } catch (error) {
            const errorMsg = error.message || (isAdmin ? 'Erreur lors de l\'ajout au serveur.' : 'Location impossible.');
            setMediaServerError(errorMsg);
            showToast(isAdmin ? `Échec de l'ajout au serveur : ${errorMsg}` : errorMsg, 'error');
        } finally {
            setAcquisitionBusy(false);
        }
    };

    const keepRental = async (rental = selectedRental) => {
        if (!rental?.id) return;
        try {
            const result = await requestRentalKeep(rental.id);
            setRentalsByMedia((current) => ({...current, [rental.media_id]: result.rental}));
            setRentals((current) => current.map((item) => item.id === rental.id ? result.rental : item));
            showToast('Demande de conservation envoyée.', 'success');
        } catch (error) {
            showToast(error.message || 'Demande impossible.', 'error');
        }
    };

    const cancelQueuedRental = async (rental = selectedRental) => {
        if (!rental?.id) return;
        const title = movies.find((movie) => movie.id === rental.media_id)?.title || 'ce film';
        if (!window.confirm(`Annuler la demande pour « ${title} » ?\n\nLe film n’a pas encore été trouvé : il sera retiré de la file d’attente.`)) return;
        try {
            const result = await cancelRental(rental.id);
            showToast(result.warning || `Demande pour « ${title} » annulée.`, result.warning ? 'error' : 'success');
            await Promise.all([loadRentals(), refreshLibraryState()]);
        } catch (error) {
            showToast(error.message || 'Annulation impossible.', 'error');
            await loadRentals();
        }
    };

    const handleRelinkMovie = async (mediaId, tmdbId) => {
        try {
            setLoading(true);
            const updated = await relinkTMDB(mediaId, tmdbId);
            await loadRealMedias();
            if (selectedMovie && selectedMovie.id === mediaId) {
                replaceCanonicalMedia(updated);
            }
            setShowRelinkModal(false);
        } catch (err) {
            console.error('Erreur réassociation TMDB:', err);
            setTmdbError('Échec de la réassociation avec TMDB.');
        } finally {
            setLoading(false);
        }
    };

    const handleDeleteMovie = async (movie) => {
        if (!movie?.id) return;
        if (!window.confirm(`Supprimer « ${movie.title} » de la bibliothèque ?\n\nLa fiche, les notes et l’historique de visionnage associés seront effacés.`)) return;
        const availability = availabilityByMedia[movie.id];
        const hasServerFiles = availability?.provider === 'radarr' && availability?.arr_id;
        const deleteFiles = Boolean(hasServerFiles) && window.confirm(`Supprimer aussi les fichiers de « ${movie.title} » sur le serveur (Radarr) ?\n\nOK : supprimer les fichiers (irréversible)\nAnnuler : garder les fichiers sur le disque`);
        try {
            setLoading(true);
            await deleteMedia(movie.id, { deleteFiles });
            setMovies((current) => current.filter((item) => item.id !== movie.id));
            setAvailabilityByMedia((current) => {
                const { [movie.id]: _removed, ...rest } = current;
                return rest;
            });
            closeMovie();
            showToast(`« ${movie.title} » a été supprimé${deleteFiles ? ', fichiers compris' : ''}.`, 'success');
        } catch (err) {
            showToast(err.message || 'Suppression impossible.', 'error');
        } finally {
            setLoading(false);
        }
    };

    const replaceCanonicalMedia = (rawMedia) => {
        const mapped = mapMediaToMovie(rawMedia);
        if (!mapped) return null;
        setMovies((current) => current.map((movie) => movie.id === mapped.id ? mapped : movie));
        setSelectedMovie((current) => current?.id === mapped.id ? mapped : current);
        setSelectedSeries((current) => current?.id === mapped.id ? mapped : current);
        return mapped;
    };

    const refreshCanonicalMedia = async (mediaId) => {
        const data = await fetchMedias();
        const rawMedia = (data || []).find((media) => media.id === mediaId);
        return rawMedia ? replaceCanonicalMedia(rawMedia) : null;
    };

    // Load real movies from Python FastAPI backend
    const loadRealMedias = async () => {
        try {
            setLoading(true);
            const data = await fetchMedias();
            const mapped = (data || []).map(mapMediaToMovie).filter(Boolean);

            setMovies(mapped);
            setError(null);
            const link = pendingDeepLink.current;
            if (link) {
                pendingDeepLink.current = null;
                const target = mapped.find((media) => media.id === link.id);
                if (!target) showToast('Ce titre n’est plus dans la bibliothèque.', 'info');
                else if (target.type === 'Série') openSeries(target);
                else openMovie(target);
            }
        } catch (err) {
            console.error('Erreur de chargement des médias:', err);
            setError('La bibliothèque n’a pas pu être chargée. Vérifie ta connexion, puis réessaie.');
        } finally {
            setLoading(false);
        }
    };

    const refreshAvailabilityByMedia = async () => {
        if (user?.role !== 'admin') return;
        try {
            const activity = await fetchMediaServerActivity();
            const items = activity.items || [];
            setAvailabilityByMedia(Object.fromEntries(items.map(item => [item.media_id, item])));
        } catch {
            setAvailabilityByMedia({});
        }
    };

    const refreshAvailableMediaIds = () => fetchLibraryAvailability()
        .then(({mediaIds, states}) => {
            setAvailableMediaIds(new Set(mediaIds));
            setLibraryStates(states);
        })
        .catch(() => {});

    const refreshLibraryState = async ({sync = false} = {}) => {
        await loadRealMedias();
        await Promise.all([refreshAvailabilityByMedia(), refreshAvailableMediaIds()]);
        if (sync && user?.role === 'admin') {
            syncMediaServer()
                .then(async () => {
                    await loadRealMedias();
                    await refreshAvailabilityByMedia();
                })
                .catch((error) => {
                    console.error('Erreur de synchronisation du serveur:', error);
                });
        }
    };

    useEffect(() => {
        if (!user?.id) return undefined;
        const refresh = (sync = false) => refreshLibraryState({sync}).catch((error) => {
            console.error('Erreur de rafraîchissement du catalogue:', error);
        });
        refresh(user.role === 'admin');
        const interval = window.setInterval(() => refresh(false), 60000);
        const handleFocus = () => refresh(false);
        window.addEventListener('focus', handleFocus);
        return () => {
            window.clearInterval(interval);
            window.removeEventListener('focus', handleFocus);
        };
    }, [user?.id, user?.role]);

    // « Vu » on a library film: log it in the journal (which also marks it
    // seen in the library). Films never linked to TMDB fall back to the
    // plain « seen » state.
    const openLibrarySeen = async (movie) => {
        let tmdbId = movie.tmdbId;
        if (!tmdbId) {
            try {
                tmdbId = (await fetchTMDBRating(movie.id))?.tmdb_id || null;
            } catch {
                tmdbId = null;
            }
        }
        if (!tmdbId) {
            try {
                replaceCanonicalMedia(await updatePersonalMedia(movie.id, { status: 'Terminé' }));
                showToast(`« ${movie.title} » marqué comme vu.`);
            } catch (err) {
                if (err?.status !== 401) showToast(err?.message || 'La modification n’a pas pu être enregistrée.', 'error');
            }
            return;
        }
        setSeenDialogMovie({ mediaId: movie.id, tmdbId, title: movie.title, posterUrl: movie.poster || null });
    };

    const saveLibrarySeen = async (payload) => {
        const target = seenDialogMovie;
        await createJournalEntry({ tmdb_id: target.tmdbId, ...payload });
        setSeenDialogMovie(null);
        await refreshCanonicalMedia(target.mediaId);
        showToast(`« ${target.title} » ajouté à ton journal.`);
    };

    const openLibraryFilmById = (mediaId) => {
        const local = movies.find((movie) => movie.id === mediaId);
        if (local) openDashboardMedia(local);
        else showToast('Ce film n’est plus dans la bibliothèque.', 'info');
    };

    const openDashboardMedia = (media) => {
        if (!media) return;
        const local = movies.find((movie) => movie.id === media.id);
        const resolved = local || (media.poster ? media : mapMediaToMovie(media));
        if (!resolved) return;
        if (resolved.type === 'Série') openSeries(resolved);
        else openMovie(resolved);
    };

    const resumeDashboardItem = (item) => {
        const media = item.media;
        const local = movies.find((movie) => movie.id === media?.id);
        const availability = media?.id ? availabilityByMedia[media.id] : null;
        if (local && availability?.jellyfin_id) {
            setMediaAvailability({availability});
            openJellyfinPlayer(local.id);
            return;
        }
        openDashboardMedia(media);
        showToast('La lecture directe sera disponible après la synchronisation du serveur.', 'error');
    };

    const addDashboardRecommendationToWatchlist = async (recommendation) => {
        try {
            setTMDBWatchlistBusy(true);
            await addRecommendationToWatchlist(recommendation.tmdb_id);
            await Promise.all([loadRealMedias(), loadDashboard()]);
            setTMDBPreview((current) => ({...current, open: false}));
            showToast(`« ${recommendation.title} » a été ajouté à ta watchlist.`);
        } catch (error) {
            showToast(error.message || 'Ajout à la watchlist impossible.', 'error');
        } finally {
            setTMDBWatchlistBusy(false);
        }
    };

    const openTMDBPreview = async (recommendation) => {
        setTMDBPreview({open: true, loading: true, movie: null, recommendation, error: null});
        try {
            const movie = await fetchTMDBMovieDetails(recommendation.tmdb_id);
            setTMDBPreview({open: true, loading: false, movie, recommendation, error: null});
        } catch (error) {
            setTMDBPreview({open: true, loading: false, movie: null, recommendation, error: error.message || 'Fiche TMDB indisponible.'});
        }
    };

    // Keeps the query: the library grid filters on it with the same search.
    const showAllSearchResults = () => {
        const query = searchQuery;
        setHeaderSearchOpen(false);
        setMobileSearchOpen(false);
        setActiveView('library');
        changeCollection(headerSearchTotal.collection);
        setSearchQuery(query);
    };

    const openHeaderSearchResult = (result) => {
        setHeaderSearchOpen(false);
        setMobileSearchOpen(false);
        setSearchQuery('');
        if (result.source === 'library') {
            setCollection(result.media.type === 'Série' ? 'Séries' : 'Films');
            setActiveView('library');
            openMovie(result.media);
            return;
        }
        if (isAdmin) {
            prepareSeerrFilmRequest({tmdb_id: result.tmdb_id, title: result.title});
            return;
        }
        openTMDBPreview({tmdb_id: result.tmdb_id, title: result.title});
    };

    const requestRecommendationOnSeerr = async (recommendation) => {
        if (!recommendation?.tmdb_id) return;
        try {
            setSeerrRequestBusy(true);
            const result = await createSeerrRequest(recommendation.tmdb_id, 'movie');
            await Promise.all([loadDashboard(), isAdmin ? null : loadRentals(), isAdmin ? null : loadRealMedias()]);
            setTMDBPreview((current) => ({...current, open: false}));
            showToast(isAdmin
                ? (result?.already_requested
                    ? `« ${recommendation.title} » est déjà demandé ou disponible : pas de doublon.`
                    : `« ${recommendation.title} » a été demandé à Seerr.`)
                : `« ${recommendation.title} » est loué : retrouve-le dans « Mes locations » sur l’accueil.`);
        } catch (error) {
            showToast(error.message || 'Demande Seerr impossible.', 'error');
        } finally {
            setSeerrRequestBusy(false);
        }
    };

    const cancelDashboardRequest = async (requestId) => {
        try {
            setCancellingRequest(requestId);
            await cancelSeerrRequest(requestId);
            await loadDashboard();
            showToast('Demande Seerr annulée.');
        } catch (error) {
            showToast(error.message || 'Annulation impossible.', 'error');
        } finally {
            setCancellingRequest(null);
        }
    };

    const explainDashboardRecommendation = (recommendation) => {
        showToast(recommendation.explanation || 'Ce film correspond à ton profil de visionnage.');
    };


    const collectionMedias = movies.filter((movie) => movie.type === (collection === 'Séries' ? 'Série' : 'Film'));
    const topGenres = Object.entries(collectionMedias.reduce((counts, movie) => {
        movie.genre.forEach((genre) => { counts[genre] = (counts[genre] || 0) + 1; });
        return counts;
    }, {})).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([genre]) => genre);
    const filteredMovies = filterAndSortMovies(collectionMedias, { ...filters, query: searchQuery }, sort)
        .filter(movie => activeFilter === 'all' || activeFilter === 'watched' ? activeFilter === 'all' || ['Terminé', 'Terminée'].includes(movie.status)
            : activeFilter === 'unwatched' ? !['Terminé', 'Terminée'].includes(movie.status)
                : activeFilter === 'watchlist' ? movie.isWatchlist : movie.isFavorite)
        .filter((movie) => !onlyAvailable || availableMediaIds.has(movie.id))
        .filter((movie) => !onlyMine || isOpenRental(rentalsByMedia[movie.id]));
    // Films only: what the server tracks but cannot play yet sits in the « En route » row.
    const enRouteMovies = collection === 'Films' ? filteredMovies.filter((movie) => libraryPlacement(movie.id, libraryStates) === 'enRoute') : [];
    const gridMovies = enRouteMovies.length ? filteredMovies.filter((movie) => libraryPlacement(movie.id, libraryStates) === 'grid') : filteredMovies;
    // Progressive rendering: 48 posters at a time instead of the whole catalogue.
    // The window resets whenever the collection, filters, sort or search change.
    const libraryKey = JSON.stringify([collection, filters, sort, searchQuery, activeFilter, onlyAvailable, onlyMine]);
    const visibleCount = libraryWindow.key === libraryKey ? libraryWindow.count : LIBRARY_BATCH_SIZE;
    const visibleMovies = gridMovies.slice(0, visibleCount);
    const showMoreMovies = () => setLibraryWindow({key: libraryKey, count: visibleCount + LIBRARY_BATCH_SIZE});

    useEffect(() => {
        const query = searchQuery.trim();
        const requestId = ++headerSearchRequest.current;
        if (query.length < 2) {
            setHeaderSearchResults([]);
            setHeaderSearchLoading(false);
            return undefined;
        }
        const timer = window.setTimeout(async () => {
            setHeaderSearchLoading(true);
            try {
                const results = collection === 'Séries' ? [] : await searchTMDB(query);
                if (requestId === headerSearchRequest.current) {
                    const allLibraryMatches = searchLibrary(movies, query);
                    // The button opens one tab, so it counts what that tab will show.
                    const films = allLibraryMatches.filter((media) => media.type !== 'Série').length;
                    const series = allLibraryMatches.length - films;
                    setHeaderSearchTotal(films >= series
                        ? {count: films, total: allLibraryMatches.length, collection: 'Films'}
                        : {count: series, total: allLibraryMatches.length, collection: 'Séries'});
                    const libraryMatches = allLibraryMatches
                        .slice(0, 5)
                        .map((media) => ({source: 'library', media, title: media.title, year: media.year, poster: media.poster}));
                    const libraryIds = new Set(libraryMatches.map((item) => String(item.media.tmdbId || item.media.title).toLocaleLowerCase()));
                    const tmdbMatches = (results || []).filter((item) => !libraryIds.has(String(item.tmdb_id || item.title).toLocaleLowerCase()))
                        .slice(0, 5)
                        .map((item) => ({source: 'tmdb', ...item}));
                    setHeaderSearchResults([...libraryMatches, ...tmdbMatches]);
                }
            } catch {
                if (requestId === headerSearchRequest.current) {
                    // TMDB down: library results still deserve to be shown.
                    const allLibraryMatches = searchLibrary(movies, query);
                    const films = allLibraryMatches.filter((media) => media.type !== 'Série').length;
                    setHeaderSearchTotal({count: films, total: allLibraryMatches.length, collection: 'Films'});
                    setHeaderSearchResults(allLibraryMatches.slice(0, 5)
                        .map((media) => ({source: 'library', media, title: media.title, year: media.year, poster: media.poster})));
                }
            } finally {
                if (requestId === headerSearchRequest.current) setHeaderSearchLoading(false);
            }
        }, 300);
        return () => window.clearTimeout(timer);
    }, [searchQuery, movies, collection]);

    // Toggle Favorite
    const toggleFavorite = async (id, e) => {
        if (e) e.stopPropagation();
        const target = movies.find(m => m.id === id);
        if (!target) return;
        const newFav = !target.isFavorite;

        try {
            const updated = await updatePersonalMedia(id, { is_favorite: newFav });
            replaceCanonicalMedia(updated);
        } catch (err) {
            console.error('API update failed:', err);
            if (err?.status !== 401) showToast(err?.message || 'La modification n’a pas pu être enregistrée.', 'error');
        }
    };

    const toggleWatchlist = async (id) => {
        const target = movies.find((movie) => movie.id === id);
        if (!target) return;
        try {
            const updated = await updatePersonalMedia(id, { is_watchlist: !target.isWatchlist });
            replaceCanonicalMedia(updated);
        } catch (err) {
            console.error('API Watchlist update failed:', err);
            if (err?.status !== 401) showToast(err?.message || 'La modification n’a pas pu être enregistrée.', 'error');
        }
    };

    // Update Rating
    const handleRate = async (id, rating) => {
        const wasInWatchlist = Boolean(movies.find((m) => m.id === id)?.isWatchlist);
        try {
            const updated = await updatePersonalMedia(id, { rating: String(rating), status: 'Terminé' });
            replaceCanonicalMedia(updated);
            showToast(`Noté ${String(rating).replace('.', ',')} / 5 — marqué comme vu${wasInWatchlist ? ' et retiré de ta watchlist' : ''}.`);
        } catch (err) {
            console.error('API update failed:', err);
            if (err?.status !== 401) showToast(err?.message || 'La modification n’a pas pu être enregistrée.', 'error');
        }
    };

    // Toggle Watched In Cinema
    const toggleCinema = async (id) => {
        const target = movies.find(m => m.id === id);
        if (!target) return;
        const newCinema = !target.watchedInCinema;

        setMovies(prev =>
            prev.map(m => m.id === id ? { ...m, watchedInCinema: newCinema } : m)
        );
        if (selectedMovie && selectedMovie.id === id) {
            setSelectedMovie(prev => prev ? { ...prev, watchedInCinema: newCinema } : null);
        }

        try {
            await updateMedia(id, { watched_in_cinema: newCinema });
        } catch (err) {
            console.error('API update failed:', err);
            if (err?.status !== 401) showToast(err?.message || 'La modification n’a pas pu être enregistrée.', 'error');
        }
    };

    // Update Watched Date
    const handleDateChange = async (id, date) => {
        setMovies(prev =>
            prev.map(m => m.id === id ? { ...m, watchedDate: date } : m)
        );
        if (selectedMovie && selectedMovie.id === id) {
            setSelectedMovie(prev => prev ? { ...prev, watchedDate: date } : null);
        }

        try {
            await updateMedia(id, { watched_date: date });
        } catch (err) {
            console.error('API update failed:', err);
            if (err?.status !== 401) showToast(err?.message || 'La modification n’a pas pu être enregistrée.', 'error');
        }
    };

    // Update Status ("À regarder", "Terminé", "À télécharger", etc.)
    const handleStatusChange = async (id, newStatus) => {
        try {
            const updated = await updatePersonalMedia(id, { status: newStatus });
            replaceCanonicalMedia(updated);
        } catch (err) {
            console.error('API update status failed:', err);
            if (err?.status !== 401) showToast(err?.message || 'La modification n’a pas pu être enregistrée.', 'error');
        }
    };

    // Update Support (Multi-selection: "Serveur", "Physique", "Streaming", "Cinéma")
    const handleSupportChange = async (id, targetSupport) => {
        const movie = movies.find(m => m.id === id);
        if (!movie) return;

        let currentSupports = Array.isArray(movie.supports) && movie.supports.length > 0
            ? [...movie.supports]
            : (movie.support ? [movie.support] : []);

        if (currentSupports.includes(targetSupport)) {
            currentSupports = currentSupports.filter(s => s !== targetSupport);
        } else {
            currentSupports.push(targetSupport);
        }

        const supportJson = JSON.stringify(currentSupports);
        const watchedInCinema = currentSupports.includes('Cinéma');

        try {
            await updateMedia(id, { support: supportJson, watched_in_cinema: watchedInCinema });
            await refreshCanonicalMedia(id);
        } catch (err) {
            console.error('API update support failed:', err);
            if (err?.status !== 401) showToast(err?.message || 'La modification n’a pas pu être enregistrée.', 'error');
        }
    };

    // Update Notes
    const handleNotesChange = async (id, notes) => {
        try {
            const updated = await updatePersonalMedia(id, { review: notes });
            replaceCanonicalMedia(updated);
        } catch (err) {
            console.error('API update failed:', err);
            if (err?.status !== 401) showToast(err?.message || 'La modification n’a pas pu être enregistrée.', 'error');
        }
    };

    // Add / Remove Genre
    const handleAddGenre = async (id, newGenre) => {
        const target = movies.find(m => m.id === id);
        if (!target || target.genre.includes(newGenre)) return;
        const updated = [...target.genre, newGenre];

        setMovies(prev => prev.map(m => m.id === id ? { ...m, genre: updated } : m));
        if (selectedMovie && selectedMovie.id === id) {
            setSelectedMovie(prev => prev ? { ...prev, genre: updated } : null);
        }
        try {
            await updateMedia(id, { categories: updated });
        } catch (err) {
            console.error('API update genre failed:', err);
            if (err?.status !== 401) showToast(err?.message || 'La modification n’a pas pu être enregistrée.', 'error');
        }
    };

    const handleRemoveGenre = async (id, genreToRemove) => {
        const target = movies.find(m => m.id === id);
        if (!target) return;
        const updated = target.genre.filter(g => g !== genreToRemove);

        setMovies(prev => prev.map(m => m.id === id ? { ...m, genre: updated } : m));
        if (selectedMovie && selectedMovie.id === id) {
            setSelectedMovie(prev => prev ? { ...prev, genre: updated } : null);
        }
        try {
            await updateMedia(id, { categories: updated });
        } catch (err) {
            console.error('API update genre failed:', err);
            if (err?.status !== 401) showToast(err?.message || 'La modification n’a pas pu être enregistrée.', 'error');
        }
    };

    // Add / Remove Cast Actor
    const handleAddCastActor = async (id, actorName) => {
        if (!actorName || !actorName.trim()) return;
        const target = movies.find(m => m.id === id);
        if (!target) return;
        const canonicalName = actorName.trim();
        if (target.cast.some((actor) => actor.toLocaleLowerCase() === canonicalName.toLocaleLowerCase())) return;
        const updated = [...target.cast, canonicalName];

        setMovies(prev => prev.map(m => m.id === id ? { ...m, cast: updated } : m));
        if (selectedMovie && selectedMovie.id === id) {
            setSelectedMovie(prev => prev ? { ...prev, cast: updated } : null);
        }
        try {
            await updateMedia(id, { cast: updated });
        } catch (err) {
            console.error('API update cast failed:', err);
            if (err?.status !== 401) showToast(err?.message || 'La modification n’a pas pu être enregistrée.', 'error');
        }
    };

    const selectCastActor = (person) => {
        if (!selectedMovie || !person?.name) return;
        handleAddCastActor(selectedMovie.id, person.name);
        setActorQuery('');
        setActorSuggestions([]);
    };

    const handleRemoveCastActor = async (id, actorIndex) => {
        const target = movies.find(m => m.id === id);
        if (!target) return;
        const updated = target.cast.filter((_, idx) => idx !== actorIndex);

        setMovies(prev => prev.map(m => m.id === id ? { ...m, cast: updated } : m));
        if (selectedMovie && selectedMovie.id === id) {
            setSelectedMovie(prev => prev ? { ...prev, cast: updated } : null);
        }
        try {
            await updateMedia(id, { cast: updated });
        } catch (err) {
            console.error('API update cast failed:', err);
            if (err?.status !== 401) showToast(err?.message || 'La modification n’a pas pu être enregistrée.', 'error');
        }
    };

    const addFromTMDB = async (tmdbId) => {
        setAddLoading(true);
        try {
            const created = collection === 'Séries'
                ? await createSeriesFromTMDB(tmdbId)
                : await createMediaFromTMDB(tmdbId);
            await loadRealMedias();
            setShowAddDialog(false);
            if (collection === 'Séries') {
                await openSeries({
                    ...created,
                    poster: created.cover_url,
                    backdrop: created.backdrop_url,
                    year: created.release_date ? new Date(created.release_date).getFullYear() : '—',
                });
            }
            else setSelectedMovie(created);
        } catch (error) {
            showToast(error.message || 'Impossible d’ajouter ce titre.', 'error');
        } finally { setAddLoading(false); }
    };

    const searchToAdd = async (query = addQuery) => {
        const trimmed = query.trim();
        const requestId = ++addSearchId.current;
        if (trimmed.length < 2) {
            setAddResults([]);
            setAddSearching(false);
            return;
        }
        setAddSearching(true);
        try {
            const results = isAdmin && collection === 'Séries'
                ? await searchTMDBTV(trimmed)
                : await searchTMDB(trimmed);
            // Ignore answers to an older query: the user kept typing.
            if (requestId === addSearchId.current) setAddResults(results);
        } catch {
            if (requestId === addSearchId.current) setAddResults([]);
        } finally {
            if (requestId === addSearchId.current) setAddSearching(false);
        }
    };

    // Live search: results refresh while typing, debounced to spare TMDB.
    useEffect(() => {
        if (!showAddDialog) return undefined;
        const timer = window.setTimeout(() => searchToAdd(addQuery), 350);
        return () => window.clearTimeout(timer);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [addQuery, showAddDialog, collection]);

    // Overlays: Escape / Back close the top one, focus is trapped and restored.
    const addDialogRef = useLayer(showAddDialog, () => setShowAddDialog(false));
    const acquisitionDialogRef = useLayer(showAcquisitionModal, () => setShowAcquisitionModal(false));
    const relinkDialogRef = useLayer(showRelinkModal && Boolean(selectedMovie), () => setShowRelinkModal(false));
    const notesDialogRef = useLayer(showNotesModal && Boolean(selectedMovie), () => setShowNotesModal(false));

    const changeCollection = (nextCollection) => {
        if (nextCollection === collection) return;
        setCollection(nextCollection);
        setActiveFilter('all');
        setFilters({ genre: '', director: '', status: '', support: '' });
        setSearchQuery('');
    };

    const openSeries = async (series) => {
        const requestId = ++seriesRequestId.current;
        selectedSeriesId.current = series.id;
        setSelectedSeries({
            ...series,
            type: 'Série',
            originalTitle: series.originalTitle || series.original_title || '',
            tmdbId: series.tmdbId || series.tmdb_id || null,
            poster: series.poster || series.cover_url,
            backdrop: series.backdrop || series.backdrop_url,
            hasBackdrop: series.hasBackdrop ?? Boolean(series.backdrop_url),
            genre: series.genre || series.categories || [],
            year: series.year || (series.release_date ? new Date(series.release_date).getFullYear() : '—'),
        });
        setSeriesEpisodes([]);
        setSeriesProgress(null);
        setSeriesView(null);
        setSeriesLoading(true);
        try {
            const details = await fetchSeriesEpisodes(series.id);
            if (requestId !== seriesRequestId.current || selectedSeriesId.current !== series.id) return;
            applySeriesDetails(details);
        } catch (error) {
            console.error('Impossible de charger les épisodes de la série:', error);
        } finally {
            if (requestId === seriesRequestId.current) setSeriesLoading(false);
        }
    };

    const applySeriesDetails = (details, {keepEpisodes = false} = {}) => {
        if (!keepEpisodes) setSeriesEpisodes(details.episodes || []);
        setSeriesProgress(details.progress);
        setSeriesView({
            seasons: details.seasons || [], stats: details.stats || null, info: details.info || null,
            next_episode: details.next_episode || null, has_server: Boolean(details.has_server),
        });
    };

    // After watch toggles settle, refresh the server-computed parts (next episode, stats).
    const scheduleSeriesViewRefresh = (mediaId) => {
        window.clearTimeout(seriesViewTimer.current);
        seriesViewTimer.current = window.setTimeout(async () => {
            if (selectedSeriesId.current !== mediaId || episodeIntents.current.size) return;
            try {
                const details = await fetchSeriesEpisodes(mediaId);
                if (selectedSeriesId.current === mediaId && !episodeIntents.current.size) {
                    applySeriesDetails(details, {keepEpisodes: true});
                }
            } catch (error) {
                console.error('Impossible de rafraîchir la fiche série:', error);
            }
        }, 700);
    };

    /** Ask for some seasons/episodes of the open series (rental of one season for a flatmate). */
    const requestSeriesParts = async (payload, label) => {
        const media = selectedSeries;
        if (!media) return false;
        try {
            const result = await requestAcquisition(media.id, payload);
            if (result.availability) setMediaAvailability((current) => ({...(current || {}), availability: result.availability}));
            if (result.season_available) showToast(`${label} de « ${media.title} » est déjà sur le serveur : bonne séance !`, 'success');
            else if (result.rental) showToast(`${label} de « ${media.title} » est louée : tu seras prévenu dès qu’elle sera disponible.`, 'success');
            else showToast(`Téléchargement demandé : ${label} de « ${media.title} ».`, 'success');
            if (!isAdmin) await loadRentals();
            return true;
        } catch (error) {
            showToast(error.message || 'Demande impossible.', 'error');
            return false;
        }
    };

    const setSeasonWatched = async (seasonNumber, watched) => {
        const mediaId = selectedSeriesId.current;
        if (!mediaId) return;
        try {
            const details = await updateSeasonWatched(mediaId, seasonNumber, watched);
            if (selectedSeriesId.current !== mediaId) return;
            applySeriesDetails(details);
            setSelectedSeries((current) => current ? { ...current, status: details.progress?.status || current.status } : null);
            setMovies((current) => current.map((movie) => (
                movie.id === mediaId && details.progress ? { ...movie, status: details.progress.status } : movie
            )));
        } catch (error) {
            showToast(error.message || 'La saison n’a pas pu être mise à jour.', 'error');
        }
    };

    const closeSeries = () => {
        seriesRequestId.current += 1;
        selectedSeriesId.current = null;
        setSelectedSeries(null);
    };

    const useOriginalSeriesTitle = async () => {
        if (!selectedSeries?.originalTitle || selectedSeries.originalTitle === selectedSeries.title) return;
        const updated = await updateMedia(selectedSeries.id, { title: selectedSeries.originalTitle });
        setSelectedSeries((current) => current ? { ...current, title: updated.title } : null);
        setMovies((current) => current.map((media) => media.id === updated.id ? { ...media, title: updated.title } : media));
    };

    const refreshSelectedSeries = async () => {
        if (!selectedSeries || seriesRefreshing) return;
        setSeriesRefreshing(true);
        try {
            const refreshed = await refreshSeriesFromTMDB(selectedSeries.id);
            const mapped = {
                ...selectedSeries,
                tmdbId: refreshed.tmdb_id || selectedSeries.tmdbId,
                originalTitle: refreshed.original_title || selectedSeries.originalTitle,
                director: refreshed.director || selectedSeries.director,
                genre: refreshed.categories || selectedSeries.genre,
                synopsis: refreshed.synopsis || selectedSeries.synopsis,
                poster: refreshed.cover_url || selectedSeries.poster,
                backdrop: refreshed.backdrop_url || selectedSeries.backdrop,
                hasBackdrop: Boolean(refreshed.backdrop_url) || selectedSeries.hasBackdrop,
                year: refreshed.release_date ? new Date(refreshed.release_date).getFullYear() : selectedSeries.year,
            };
            setSelectedSeries(mapped);
            setMovies((current) => current.map((media) => media.id === refreshed.id ? { ...media, ...mapped, status: refreshed.status } : media));
            const details = await fetchSeriesEpisodes(refreshed.id);
            applySeriesDetails(details);
        } catch (error) {
            console.error('Impossible d’actualiser la série depuis TMDB:', error);
        } finally {
            setSeriesRefreshing(false);
        }
    };

    const toggleEpisode = (episode) => {
        const optimisticEpisode = { ...episode, watched: !episode.watched };
        const previousIntent = episodeIntents.current.get(episode.id);
        const intentId = (previousIntent?.id || 0) + 1;
        episodeIntents.current.set(episode.id, { id: intentId, watched: optimisticEpisode.watched });
        setSeriesEpisodes((current) => replaceEpisode(current, optimisticEpisode));
        const mediaId = episode.media_id;
        episodeUpdateQueue.current = episodeUpdateQueue.current
            .catch(() => undefined)
            .then(async () => {
                try {
                    const result = await updateEpisode(episode.id, optimisticEpisode.watched);
                    setMovies((current) => current.map((movie) => (
                        movie.id === mediaId ? { ...movie, status: result.progress.status } : movie
                    )));
                    const isCurrentSeries = selectedSeriesId.current === mediaId;
                    const isLatestIntent = episodeIntents.current.get(episode.id)?.id === intentId;
                    if (isLatestIntent) {
                        episodeIntents.current.delete(episode.id);
                    }
                    if (!isCurrentSeries) return;
                    if (isLatestIntent) {
                        setSeriesEpisodes((current) => replaceEpisode(current, result.episode));
                    }
                    setSeriesProgress(result.progress);
                    setSelectedSeries((current) => current ? { ...current, status: result.progress.status } : null);
                    scheduleSeriesViewRefresh(mediaId);
                } catch (error) {
                    console.error('Impossible de mettre à jour cet épisode:', error);
                    const isCurrentSeries = selectedSeriesId.current === mediaId;
                    if (episodeIntents.current.get(episode.id)?.id === intentId) {
                        episodeIntents.current.delete(episode.id);
                    }
                    if (!isCurrentSeries) return;
                    const details = await fetchSeriesEpisodes(mediaId);
                    if (selectedSeriesId.current === mediaId) {
                        setSeriesEpisodes((details.episodes || []).map((serverEpisode) => {
                            const pendingIntent = episodeIntents.current.get(serverEpisode.id);
                            return pendingIntent ? { ...serverEpisode, watched: pendingIntent.watched } : serverEpisode;
                        }));
                        setSeriesProgress(details.progress);
                    }
                }
            });
    };


    return (
        <div className={`min-h-screen pb-[calc(3.5rem+env(safe-area-inset-bottom))] lg:pb-0 font-sans antialiased selection:bg-[#635bff] selection:text-white flex flex-col transition-colors duration-300 ${isDarkMode ? 'bg-[#0a0a0a] text-white' : 'bg-[#f6f9fc] text-[#0a2540]'
            }`}>
            <a href="#contenu" className="skip-link" onClick={(event) => { event.preventDefault(); document.getElementById('contenu')?.focus(); }}>Aller au contenu</a>
            {/* Toast Floating Notification Banner */}
            {toastNotification && (
                <div className={`fixed top-5 right-5 z-[100] max-w-md px-4 py-3 rounded-xl shadow-2xl border backdrop-blur-md flex items-center justify-between gap-3 animate-slide-left-smooth ${
                    toastNotification.type === 'error'
                        ? 'bg-rose-950/90 border-rose-500/50 text-rose-100'
                        : toastNotification.type === 'info'
                            ? 'bg-slate-900/90 border-[#635bff]/50 text-white'
                            : 'bg-emerald-950/90 border-emerald-500/50 text-emerald-100'
                }`} role={toastNotification.type === 'error' ? 'alert' : 'status'} data-layer-keep>
                    <div className="flex items-center gap-2.5 text-xs font-semibold">
                        <span className="text-base" aria-hidden="true">{toastNotification.type === 'error' ? <Icon name="close" /> : toastNotification.type === 'info' ? <Icon name="clock" /> : <Icon name="check" />}</span>
                        <span>{toastNotification.message}</span>
                    </div>
                    <button
                        onClick={() => setToastNotification(null)}
                        className="text-white/60 hover:text-white text-xs p-1"
                    >
                        ✕
                    </button>
                </div>
            )}

            {/* Top Header */}
            <header className={`border-b sticky top-0 z-40 backdrop-blur-xl transition-colors duration-300 ${isDarkMode ? 'border-white/10 bg-black/90' : 'border-[#e3e8ee] bg-white/90 shadow-sm'
                }`}>
                <div className="mx-auto flex min-h-16 w-full max-w-[1536px] flex-wrap items-center justify-between gap-x-4 px-4 sm:px-6 lg:grid lg:h-16 lg:grid-cols-[auto_minmax(0,1fr)_auto] lg:flex-nowrap">
                    <div className="flex h-16 shrink-0 items-center gap-3 sm:gap-4 lg:h-auto">
                        <img src="/static/Logo.png" alt="Backstage" className="h-9 w-auto object-contain sm:h-10" />
                        <div className="hidden sm:block">
                            <span className={`font-serif italic font-bold text-xl tracking-tighter ${isDarkMode ? 'text-white' : 'text-[#0a2540]'
                                }`}>
                                BACKSTAGE
                            </span>
                        </div>
                    </div>

                    <div className={`${mobileSearchOpen ? 'flex' : 'hidden'} order-last basis-full items-center pb-3 lg:order-none lg:flex lg:basis-auto lg:min-w-0 lg:justify-self-center lg:gap-5 lg:pb-0`}>
                    <nav className="hidden shrink-0 lg:block" aria-label="Navigation principale">
                        <div className={`flex items-center gap-6 whitespace-nowrap text-sm font-semibold ${isDarkMode ? 'text-white/60' : 'text-[#425466]'}`}>
                            {[['dashboard', 'Accueil'], ['library', 'Films'], ['library', 'Séries'], ['journal', 'Journal']].map(([view, label]) => {
                                const selected = view === 'library' ? activeView === 'library' && collection === label : activeView === view;
                                return <button key={label} type="button" onClick={() => view === 'library' ? (setActiveView('library'), changeCollection(label)) : setActiveView(view)} className={`border-b-2 px-1 pb-2 pt-2 transition-all ${selected ? 'border-b-2 border-[#635bff] text-[#635bff]' : 'border-transparent hover:border-[#635bff]/40 hover:text-[#635bff]'}`}>
                                    {label}
                                </button>;
                            })}
                        </div>
                    </nav>
                    <div className="relative w-full lg:w-40 lg:min-w-[8rem] lg:shrink xl:w-56" onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setHeaderSearchOpen(false); }}>
                            <input
                                ref={mobileSearchInputRef}
                                type="search"
                                aria-label={collection === 'Séries' ? 'Rechercher une série' : 'Rechercher un film'}
                                placeholder={collection === 'Séries' ? 'Série, créateur…' : 'Film, réalisateur…'}
                                value={searchQuery}
                                onFocus={() => setHeaderSearchOpen(true)}
                                onChange={(e) => { setSearchQuery(e.target.value); setHeaderSearchOpen(true); }}
                                onKeyDown={(event) => {
                                    if (event.key === 'Escape') { setHeaderSearchOpen(false); setMobileSearchOpen(false); }
                                    if (event.key === 'Enter' && headerSearchResults[0]) openHeaderSearchResult(headerSearchResults[0]);
                                }}
                                className={`w-full rounded-lg border px-3 py-2.5 text-base outline-none transition-all lg:py-2 lg:text-xs ${isDarkMode
                                    ? 'bg-white/5 border-white/15 focus:border-[#635bff] text-white placeholder-white/40'
                                    : 'bg-[#f6f9fc] border-[#e3e8ee] focus:border-[#635bff] text-[#0a2540] placeholder-[#425466]/50'
                                    }`}
                            />
                            {headerSearchOpen && searchQuery.trim().length >= 2 && <div className={`absolute left-0 right-0 top-[calc(100%+8px)] z-50 max-h-[65vh] overflow-y-auto lg:min-w-[320px] rounded-xl border p-2 shadow-2xl ${isDarkMode ? 'border-white/10 bg-[#111318] text-white' : 'border-[#e3e8ee] bg-white text-[#0a2540]'}`}>
                                <p className="px-2 pb-1 pt-1 text-xs font-mono font-bold uppercase tracking-widest opacity-75">Résultats</p>
                                {headerSearchLoading && <p className="px-2 py-3 text-xs opacity-75">Recherche en cours…</p>}
                                {!headerSearchLoading && headerSearchResults.length === 0 && <p className="px-2 py-3 text-xs opacity-75">Aucun titre trouvé. Essaie un autre nom.</p>}
                                {!headerSearchLoading && headerSearchResults.filter((result) => result.source === 'library').map((result) => <button key={`${result.source}-${result.tmdb_id || result.media?.id}`} type="button" onClick={() => openHeaderSearchResult(result)} className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition hover:bg-[#635bff]/10">
                                    <span className="h-12 w-8 shrink-0 overflow-hidden rounded bg-current/10">{(result.poster || result.poster_url) && <img src={result.poster || result.poster_url} alt="" className="h-full w-full object-cover" />}</span>
                                    <span className="min-w-0 flex-1"><span className="block truncate text-xs font-semibold">{result.title}</span><span className="mt-0.5 block text-xs opacity-75">{result.year || result.release_date?.slice(0, 4) || 'Année inconnue'} · {result.source === 'library' ? 'Dans ma bibliothèque' : (isAdmin ? 'Disponible sur TMDB' : 'Pas encore sur le serveur')}</span></span>
                                </button>)}
                                {!headerSearchLoading && headerSearchTotal.total > 5 && headerSearchTotal.count > 0 && <button type="button" onClick={showAllSearchResults} className="mt-1 w-full rounded-lg border border-[#635bff]/30 px-2 py-2 text-xs font-semibold text-[#635bff] transition hover:bg-[#635bff]/10">Voir les {headerSearchTotal.count} {headerSearchTotal.collection === 'Séries' ? 'séries' : 'films'} dans la bibliothèque</button>}
                                {!headerSearchLoading && headerSearchResults.filter((result) => result.source !== 'library').map((result) => <button key={`${result.source}-${result.tmdb_id || result.media?.id}`} type="button" onClick={() => openHeaderSearchResult(result)} className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition hover:bg-[#635bff]/10">
                                    <span className="h-12 w-8 shrink-0 overflow-hidden rounded bg-current/10">{(result.poster || result.poster_url) && <img src={result.poster || result.poster_url} alt="" className="h-full w-full object-cover" />}</span>
                                    <span className="min-w-0 flex-1"><span className="block truncate text-xs font-semibold">{result.title}</span><span className="mt-0.5 block text-xs opacity-75">{result.year || result.release_date?.slice(0, 4) || 'Année inconnue'} · {result.source === 'library' ? 'Dans ma bibliothèque' : (isAdmin ? 'Disponible sur TMDB' : 'Pas encore sur le serveur')}</span></span>
                                </button>)}
                                {!headerSearchLoading && headerSearchResults.some((result) => result.source === 'tmdb') && <p className="px-2 pb-1 pt-2 text-xs opacity-75">{isAdmin ? 'Choisis un résultat TMDB pour ouvrir la demande de téléchargement.' : 'Un titre pas encore sur le serveur ? Ouvre-le pour le louer.'}</p>}
                            </div>}
                        </div>
                    </div>

                    <div className="flex h-16 min-w-0 items-center gap-1.5 sm:gap-2 lg:h-auto lg:justify-self-end">
                        <button
                            type="button"
                            onClick={() => {
                                const next = !mobileSearchOpen;
                                setMobileSearchOpen(next);
                                if (next) window.requestAnimationFrame(() => mobileSearchInputRef.current?.focus());
                                else setHeaderSearchOpen(false);
                            }}
                            className={`flex h-11 w-11 items-center justify-center rounded-full border lg:hidden ${mobileSearchOpen ? 'border-[#635bff] text-[#635bff]' : isDarkMode ? 'border-white/15 text-white/80' : 'border-[#e3e8ee] text-[#425466]'}`}
                            aria-label={mobileSearchOpen ? 'Fermer la recherche' : 'Rechercher'}
                            aria-expanded={mobileSearchOpen}
                        >
                            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                                {mobileSearchOpen
                                    ? <path strokeLinecap="round" d="M6 6l12 12M18 6 6 18" />
                                    : <><circle cx="11" cy="11" r="6.5" /><path strokeLinecap="round" d="m16 16 4.5 4.5" /></>}
                            </svg>
                        </button>
                        {(isAdmin || collection !== 'Séries') && <button onClick={() => setShowAddDialog(true)} className="hidden whitespace-nowrap bg-[#635bff] px-3 py-2 text-xs font-semibold text-white shadow-md transition-all hover:bg-[#5048e5] lg:block">
                            {isAdmin ? (collection === 'Séries' ? 'Ajouter une série' : 'Ajouter un film') : 'Louer un film'}
                        </button>}
                        {user?.role === 'admin' && <button onClick={() => setShowAdminCenter(true)} className="hidden rounded-lg border border-[#635bff]/40 px-3 py-2 text-xs font-semibold text-[#635bff] lg:block" title="Ouvrir l’administration">
                            Administration
                        </button>}
                        <NotificationBell isDarkMode={isDarkMode} />
                        <button onClick={() => setShowAccountPanel(true)} className="flex h-11 items-center gap-2 rounded-lg border px-2 text-xs font-semibold lg:h-auto lg:px-2.5 lg:py-1.5" title="Ouvrir le compte" aria-label={`Ouvrir le compte de ${user?.display_name || 'l’utilisateur'}`}>
                            {user?.avatar_url
                                ? <img src={user.avatar_url} alt="" className="h-7 w-7 rounded-full object-cover" />
                                : <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[#635bff] text-xs font-bold text-white" aria-hidden="true">{(user?.display_name || 'Compte').charAt(0).toUpperCase()}</span>}
                            <span className="hidden xl:inline">{user?.display_name || 'Compte'}</span>
                        </button>
                        <button
                            onClick={() => setIsDarkMode(!isDarkMode)}
                            className={`flex h-11 w-11 items-center justify-center rounded-full border text-base transition-all lg:h-9 lg:w-9 ${isDarkMode
                                ? 'border-white/15 bg-white/5 text-white/80 hover:bg-white/10'
                                : 'border-[#e3e8ee] bg-[#f6f9fc] text-[#425466] hover:bg-[#ebeef3]'
                                }`}
                            title="Changer de thème"
                            aria-label={isDarkMode ? 'Activer le mode clair' : 'Activer le mode sombre'}
                        >
                            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M20.2 15.4A8.5 8.5 0 0 1 8.6 3.8 8.5 8.5 0 1 0 20.2 15.4Z" />
                            </svg>
                        </button>
                    </div>
                </div>
            </header>

            {/* Bottom tab bar: primary navigation below the lg breakpoint (phones, tablets). */}
            <nav
                aria-label="Navigation principale"
                className={`fixed inset-x-0 bottom-0 z-40 border-t pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden ${isDarkMode ? 'border-white/10 bg-black/90' : 'border-[#e3e8ee] bg-white/95 shadow-[0_-2px_10px_rgba(10,37,64,0.06)]'}`}
            >
                <div className="mx-auto flex max-w-xl items-stretch justify-around">
                    {[
                        {key: 'dashboard', label: 'Accueil', selected: activeView === 'dashboard', onClick: () => setActiveView('dashboard'), icon: <path strokeLinecap="round" strokeLinejoin="round" d="M3.5 10.5 12 4l8.5 6.5V20a1 1 0 0 1-1 1h-5v-6h-5v6h-5a1 1 0 0 1-1-1z" />},
                        {key: 'films', label: 'Films', selected: activeView === 'library' && collection === 'Films', onClick: () => { setActiveView('library'); changeCollection('Films'); }, icon: <><rect x="3.5" y="5" width="17" height="14" rx="2" /><path strokeLinecap="round" d="M3.5 9h17M3.5 15h17M8 5v14M16 5v14" /></>},
                        {key: 'series', label: 'Séries', selected: activeView === 'library' && collection === 'Séries', onClick: () => { setActiveView('library'); changeCollection('Séries'); }, icon: <><rect x="3.5" y="6" width="17" height="12" rx="2" /><path strokeLinecap="round" strokeLinejoin="round" d="M9 21h6M8.5 2.5 12 6l3.5-3.5" /></>},
                        {key: 'carnet', label: 'Carnet', selected: activeView === 'journal' || activeView === 'lists', onClick: () => setActiveView('journal'), icon: <><path strokeLinecap="round" strokeLinejoin="round" d="M6 3.5h11a1.5 1.5 0 0 1 1.5 1.5v14a1.5 1.5 0 0 1-1.5 1.5H6z" /><path strokeLinecap="round" d="M6 3.5v17M9.5 8h5.5M9.5 11.5h5.5" /></>},
                        {key: 'add', label: isAdmin ? 'Ajouter' : 'Louer', selected: showAddDialog, onClick: () => setShowAddDialog(true), icon: <><circle cx="12" cy="12" r="8.5" /><path strokeLinecap="round" d="M12 8v8M8 12h8" /></>},
                        ...(user?.role === 'admin' ? [{key: 'admin', label: 'Admin', selected: showAdminCenter, onClick: () => setShowAdminCenter(true), icon: <><circle cx="12" cy="12" r="3" /><path strokeLinecap="round" strokeLinejoin="round" d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1" /></>}] : []),
                    ].map((tab) => (
                        <button
                            key={tab.key}
                            type="button"
                            onClick={() => { setMobileSearchOpen(false); tab.onClick(); }}
                            aria-current={tab.selected && ['dashboard', 'films', 'series', 'carnet'].includes(tab.key) ? 'page' : undefined}
                            className={`flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 px-1 text-xs font-semibold transition-colors ${tab.selected ? 'text-[#635bff]' : isDarkMode ? 'text-white/70' : 'text-[#425466]'}`}
                        >
                            <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">{tab.icon}</svg>
                            {tab.label}
                        </button>
                    ))}
                </div>
            </nav>

            {showAccountPanel &&<AccountPanel isDarkMode={isDarkMode} onClose={() => setShowAccountPanel(false)} />}
            <ChatDock isDarkMode={isDarkMode} />
            {seenDialogMovie && <SeenDialog movie={seenDialogMovie} isDarkMode={isDarkMode} onSave={saveLibrarySeen} onClose={() => setSeenDialogMovie(null)} />}
            {showAdminCenter && user?.role === 'admin' && <AdminCenter isDarkMode={isDarkMode} onClose={() => setShowAdminCenter(false)} onMediaChanged={loadRealMedias} />}
            {showRecommendationFlow && <RecommendationFlow isDarkMode={isDarkMode} onClose={() => setShowRecommendationFlow(false)} onPlay={openJellyfinPlayer} />}
            {tmdbPreview.open && <TMDBMoviePreview
                movie={tmdbPreview.movie}
                recommendation={tmdbPreview.recommendation}
                isDarkMode={isDarkMode}
                loading={tmdbPreview.loading}
                error={tmdbPreview.error}
                watchlistBusy={tmdbWatchlistBusy}
                requestBusy={seerrRequestBusy}
                onClose={() => setTMDBPreview((current) => ({...current, open: false}))}
                onAddWatchlist={addDashboardRecommendationToWatchlist}
                onRequestSeerr={requestRecommendationOnSeerr}
                isAdmin={user?.role === 'admin'}
            />}

                {/* Main App Layout */}
                <div className="flex-1 max-w-[1536px] w-full mx-auto flex p-6 gap-8">
                {activeView === 'library' && <aside className="hidden">
                    {/* Filter Card */}
                    <div className={`rounded-2xl p-4 flex flex-col gap-4 transition-colors duration-300 border ${isDarkMode
                        ? 'bg-[#0a0a0a]/90 backdrop-blur-md border-white/10 shadow-2xl'
                        : 'bg-white border-[#e3e8ee] shadow-sm'
                        }`}>
                        <div className="flex items-center justify-between px-2 pt-1">
                            <span className={`text-xs font-mono uppercase tracking-widest font-bold ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                                }`}>
                                NAVIGATION
                            </span>
                            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                        </div>

                        <nav className="space-y-1.5">
                            {[
                                { id: 'all', label: collection === 'Séries' ? 'Toutes les séries' : 'Tous les films', icon: 'film', count: collectionMedias.length },
                                { id: 'watched', label: collection === 'Séries' ? 'Séries terminées' : 'Films vus', icon: 'eye', count: collectionMedias.filter(m => ['Terminé', 'Terminée'].includes(m.status)).length },
                                { id: 'watchlist', label: 'Watchlist', icon: 'pin', count: collectionMedias.filter(m => m.isWatchlist).length },
                                { id: 'unwatched', label: collection === 'Séries' ? 'Séries à regarder' : 'À regarder', icon: 'bookmark', count: collectionMedias.filter(m => !['Terminé', 'Terminée'].includes(m.status)).length },
                                { id: 'favorite', label: 'Favoris', icon: 'heart', count: collectionMedias.filter(m => m.isFavorite).length },
                            ].map((item) => (
                                <button
                                    key={item.id}
                                    onClick={() => setActiveFilter(item.id)}
                                    className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-medium transition-all duration-200 cursor-pointer ${activeFilter === item.id
                                        ? 'bg-[#635bff] text-white shadow-md font-semibold'
                                        : isDarkMode
                                            ? 'text-white/70 hover:text-white hover:bg-white/5 border border-transparent'
                                            : 'text-[#425466] hover:text-[#0a2540] hover:bg-[#f6f9fc] border border-transparent'
                                        }`}
                                >
                                    <div className="flex items-center gap-3">
                                        <Icon name={item.icon} />
                                        <span>{item.label}</span>
                                    </div>
                                    <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded-full ${activeFilter === item.id
                                        ? 'bg-white/20 text-white'
                                        : isDarkMode
                                            ? 'bg-white/5 text-white/50 border border-white/10'
                                            : 'bg-[#f6f9fc] text-[#425466] border border-[#e3e8ee]'
                                        }`}>
                                        {item.count}
                                    </span>
                                </button>
                            ))}
                        </nav>

                        <button
                            type="button"
                            onClick={() => setShowRecommendationFlow(true)}
                            className="group relative mt-1 w-full overflow-hidden rounded-xl bg-gradient-to-br from-[#635bff] via-[#705cf6] to-[#a855f7] px-4 py-3 text-left text-white shadow-lg shadow-[#635bff]/25 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-xl hover:shadow-[#635bff]/35"
                            title="Choisir un film en quelques questions"
                        >
                            <span className="absolute -right-5 -top-7 h-20 w-20 rounded-full bg-white/20 blur-xl transition-transform duration-300 group-hover:scale-125" />
                            <span className="relative flex items-center justify-between gap-2">
                                <span>
                                    <span className="block text-xs font-mono uppercase tracking-widest text-white/70">Sélection personnalisée</span>
                                    <span className="mt-1 block text-sm font-semibold"><Icon name="sparkle" className="mr-1 h-4 w-4 align-[-2px]" />Choisir un film</span>
                                </span>
                                <span className="text-lg transition-transform duration-200 group-hover:translate-x-0.5">→</span>
                            </span>
                        </button>
                    </div>

                    {/* Genres Card */}
                    <div className={`rounded-2xl p-4 flex flex-col gap-3 transition-colors duration-300 border ${isDarkMode
                        ? 'bg-[#0a0a0a]/90 backdrop-blur-md border-white/10 shadow-xl'
                        : 'bg-white border-[#e3e8ee] shadow-sm'
                        }`}>
                        <span className={`text-xs font-mono uppercase tracking-widest font-bold px-2 ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                            }`}>
                            GENRES
                        </span>
                        <div className="flex flex-wrap gap-1.5 px-1">
                            {topGenres.map((genre) => (
                                <button
                                    type="button"
                                    key={genre}
                                    aria-pressed={filters.genre === genre}
                                    onClick={() => setFilters((prev) => ({ ...prev, genre: prev.genre === genre ? '' : genre }))}
                                    className={`text-xs font-mono px-3 py-1 rounded-full cursor-pointer transition-all duration-200 border ${filters.genre === genre ? '!border-[#635bff] !bg-[#635bff] !text-white ' : ''}${isDarkMode
                                        ? 'bg-white/5 hover:bg-[#635bff]/20 hover:border-[#635bff]/40 border-white/10 text-white/80'
                                        : 'bg-[#f6f9fc] hover:bg-[#635bff]/10 hover:border-[#635bff]/40 border-[#e3e8ee] text-[#0a2540]'
                                        }`}
                                >
                                    #{genre}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Quick Stats Box */}
                    <div className={`mt-auto border rounded-2xl p-4 relative overflow-hidden shadow-lg ${isDarkMode
                        ? 'bg-gradient-to-br from-slate-900 to-black border-white/10 text-white'
                        : 'bg-gradient-to-br from-[#0a2540] to-[#1a365d] border-[#0a2540] text-white'
                        }`}>
                        <div className="absolute top-0 right-0 w-24 h-24 bg-[#635bff]/20 rounded-full blur-2xl pointer-events-none" />
                        <div className="text-xs font-mono uppercase text-[#635bff] tracking-widest font-bold mb-1">
                            ★ INSIGHTS COLLECTION
                        </div>
                        <div className="text-2xl font-serif text-white font-bold">
                            {movies.filter(m => m.rating === 5).length} / {movies.length}
                        </div>
                        <p className="text-xs text-white/70 mt-1">
                            Chefs-d'œuvre notés 5 étoiles dans ta bibliothèque.
                        </p>
                    </div>
                </aside>}

                {/* Main Content Area */}
                <main id="contenu" tabIndex={-1} key={collection} className="series-portal flex-1 min-w-0 outline-none">
                    {activeView === 'journal' ? <JournalView
                        isDarkMode={isDarkMode}
                        onOpenLibraryFilm={openLibraryFilmById}
                        onChanged={loadRealMedias}
                        showToast={showToast}
                    /> : activeView === 'dashboard' ? <DashboardHome
                        data={dashboardData}
                        isDarkMode={isDarkMode}
                        loading={dashboardLoading}
                        error={dashboardError}
                        onRetry={loadDashboard}
                        onOpenMedia={openDashboardMedia}
                        onResume={resumeDashboardItem}
                        onAddWatchlist={addDashboardRecommendationToWatchlist}
                        onWhyRecommendation={explainDashboardRecommendation}
                        onOpenTMDBDetails={openTMDBPreview}
                        onCancelRequest={cancelDashboardRequest}
                        cancellingRequest={cancellingRequest}
                        isAdmin={isAdmin}
                        rentals={rentals}
                        maxActiveRentals={maxActiveRentals}
                        maxQueuedRentals={maxQueuedRentals}
                        onCancelRental={cancelQueuedRental}
                        medias={movies}
                        onKeepRental={keepRental}
                        onRentFilm={() => { setActiveView('library'); changeCollection('Films'); setShowAddDialog(true); }}
                        onOpenLibrary={() => setActiveView('library')}
                        onOpenRecommendations={() => setShowRecommendationFlow(true)}
                    /> : <>
                    {collection === 'Séries' && !isAdmin && (
                        <div role="note" className={`mb-5 rounded-xl border px-4 py-3 text-sm ${isDarkMode ? 'border-[#635bff]/30 bg-[#635bff]/10 text-white/85' : 'border-[#635bff]/25 bg-[#635bff]/5 text-[#0a2540]'}`}>
                            <strong className="font-semibold">Envie d’une saison ?</strong>{' '}
                            Ouvre une série pour louer une saison, ou demande-la à l’administrateur.
                        </div>
                    )}
                    {/* Header Section */}
                    <div className={`flex items-end justify-between mb-6 pb-4 border-b ${isDarkMode ? 'border-white/10' : 'border-[#e3e8ee]'
                        }`}>
                        <div>
                            <span className="text-xs font-mono uppercase tracking-widest text-[#635bff] font-bold">
                                ★ CATALOGUE SÉLECTIONNÉ
                            </span>
                            <h1 className={`text-3xl font-serif font-bold tracking-tight mt-1 ${isDarkMode ? 'text-white' : 'text-[#0a2540]'
                                }`}>
                                {collection === 'Séries' && (activeFilter === 'all' ? 'Toutes les séries' : activeFilter === 'watched' ? 'Séries terminées' : activeFilter === 'unwatched' ? 'Séries à regarder' : activeFilter === 'watchlist' ? 'Watchlist' : 'Favoris')}
                                {collection === 'Films' && <>
                                {activeFilter === 'all' && 'Tous les Films'}
                                {activeFilter === 'watched' && 'Films Vus'}
                                {activeFilter === 'unwatched' && 'À regarder'}
                                {activeFilter === 'watchlist' && 'Watchlist'}
                                {activeFilter === 'favorite' && 'Favoris'}
                                </>}
                            </h1>
                        </div>
                        <div className="flex flex-col items-end gap-2">
                            {collection === 'Films' && <button type="button" onClick={() => setShowRecommendationFlow(true)} className="inline-flex min-h-11 items-center gap-1.5 rounded-lg bg-gradient-to-br from-[#635bff] to-[#a855f7] px-4 py-2 text-sm font-semibold text-white shadow-md shadow-[#635bff]/25 transition hover:-translate-y-0.5" title="Choisir un film en quelques questions"><Icon name="sparkle" />Choisir un film</button>}
                            <div className={`text-xs font-mono ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                                }`}>
                                {gridMovies.length} Titre{gridMovies.length > 1 ? 's' : ''} affiché{gridMovies.length > 1 ? 's' : ''}
                            </div>
                        </div>
                    </div>

                    <div className="flex flex-wrap gap-2 mb-6">
                        <select aria-label="Trier par" value={sort.key} onChange={e => setSort(prev => ({ ...prev, key: e.target.value }))} className="text-xs rounded border px-2 py-1.5"><option value="createdAt">Date d'ajout</option><option value="title">Titre</option><option value="year">Année</option><option value="rating">Note</option></select>
                        <button onClick={() => setSort(prev => ({ ...prev, direction: prev.direction === 'asc' ? 'desc' : 'asc' }))} className="text-xs rounded border px-2 py-1.5">{sort.direction === 'asc' ? '↑ Croissant' : '↓ Décroissant'}</button>
                        {[['genre', 'Genre', filterOptions(collectionMedias, 'genre')], ['director', collection === 'Séries' ? 'Créateur' : 'Réalisateur', filterOptions(collectionMedias, 'director')], ['status', 'Statut', ['À regarder', 'En cours', 'Terminé', 'Terminée']], ['support', 'Support', filterOptions(collectionMedias, 'supports')]].map(([key, label, options]) => <select key={key} aria-label={`Filtrer par ${label.toLowerCase()}`} value={filters[key]} onChange={e => setFilters(prev => ({ ...prev, [key]: e.target.value }))} className="text-xs rounded border px-2 py-1.5"><option value="">{label}</option>{options.map(option => <option key={option} value={option}>{option}</option>)}</select>)}
                        <button type="button" onClick={() => setOnlyAvailable((value) => !value)} aria-pressed={onlyAvailable} className={`rounded border px-2 py-1.5 text-xs font-semibold transition ${onlyAvailable ? 'border-emerald-500 bg-emerald-500 text-white' : 'border-emerald-500/40 text-emerald-600 hover:bg-emerald-500/10'}`} title={collection === 'Séries' ? 'Séries présentes sur le serveur' : 'Films prêts à être lus sur le serveur'}>▶ Disponible maintenant</button>
                        <button type="button" onClick={() => setOnlyMine((value) => !value)} aria-pressed={onlyMine} className={`rounded border px-2 py-1.5 text-xs font-semibold transition ${onlyMine ? 'border-[#635bff] bg-[#635bff] text-white' : 'border-[#635bff]/40 text-[#635bff] hover:bg-[#635bff]/10'}`} title="Les titres que tu as loués">Mes locations</button>
                        <button onClick={() => { setFilters({ genre: '', director: '', status: '', support: '' }); setOnlyAvailable(false); setOnlyMine(false); }} className="text-xs text-[#635bff] px-2">Réinitialiser</button>
                    </div>

                    <div className="category-rail mb-7" aria-label="Explorer par catégorie">
                        <div className="mb-3 flex items-center justify-between gap-3"><div><p className="text-xs font-mono font-bold uppercase tracking-[0.2em] text-[#635bff]">CATÉGORIES</p><h2 className={`mt-1 text-lg font-serif font-bold ${isDarkMode ? 'text-white' : 'text-[#0a2540]'}`}>Explorer par catégorie</h2></div><button type="button" onClick={() => setFilters((current) => ({...current, genre: ''}))} className="text-xs font-semibold text-[#635bff] hover:underline">Toutes</button></div>
                        <div className="flex gap-2 overflow-x-auto pb-1">{ALL_GENRES.filter((genre) => collectionMedias.some((movie) => movie.genre.includes(genre))).map((genre) => { const count = collectionMedias.filter((movie) => movie.genre.includes(genre)).length; return <button type="button" key={genre} onClick={() => setFilters((current) => ({...current, genre}))} className={`shrink-0 rounded-full border px-3 py-2 text-xs font-semibold transition ${filters.genre === genre ? 'border-[#635bff] bg-[#635bff] text-white shadow-md' : isDarkMode ? 'border-white/10 bg-white/5 text-white/70 hover:border-[#635bff]/60' : 'border-[#e3e8ee] bg-white text-[#425466] hover:border-[#635bff]/60 hover:text-[#635bff]'}`}>{genre}<span className="ml-1.5 opacity-75">{count}</span></button>; })}</div>
                    </div>

                    {catalogueError && (
                        <div role="alert" className={`mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4 text-sm ${isDarkMode ? 'border-rose-400/30 bg-rose-500/10 text-rose-100' : 'border-rose-200 bg-rose-50 text-rose-900'}`}>
                            <span>{catalogueError}</span>
                            <button type="button" onClick={loadRealMedias} className="rounded-lg bg-[#635bff] px-3 py-2 text-xs font-semibold text-white">Réessayer</button>
                        </div>
                    )}

                    {catalogueLoading && movies.length === 0 && !catalogueError && (
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-5" aria-busy="true" aria-label="Chargement de la bibliothèque">
                            {Array.from({length: 12}, (_, index) => <div key={index} className="aspect-[2/3] animate-pulse rounded-xl bg-current/10" />)}
                        </div>
                    )}

                    {enRouteMovies.length > 0 && (
                        <section aria-label="En route" className="mb-8">
                            <h2 className={`mb-3 text-lg font-serif font-bold ${isDarkMode ? 'text-white' : 'text-[#0a2540]'}`}>En route <span className="ml-1 text-xs font-mono opacity-60">{enRouteMovies.length}</span></h2>
                            <div className="flex gap-3 overflow-x-auto pb-2">
                                {enRouteMovies.map((movie) => {
                                    const badge = enRouteBadge(movie.releaseDate, libraryStates[movie.id]);
                                    return (
                                        <button type="button" key={movie.id} onClick={() => openMovie(movie)} className="group w-28 shrink-0 text-left">
                                            <div className="relative aspect-[2/3] w-full overflow-hidden rounded-lg bg-slate-900">
                                                <img src={movie.poster} alt={movie.title} loading="lazy" decoding="async" className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105" />
                                                <span className={`absolute left-1.5 top-1.5 rounded-md px-1.5 py-0.5 text-[8.5px] font-mono font-bold text-white shadow backdrop-blur-md ${BADGE_TONE_CLASSES[badge.tone]}`}>{badge.label}</span>
                                            </div>
                                            <p className={`mt-1.5 truncate text-xs font-semibold group-hover:text-[#635bff] ${isDarkMode ? 'text-white' : 'text-[#0a2540]'}`}>{movie.title}</p>
                                        </button>
                                    );
                                })}
                            </div>
                            <h2 className={`mt-6 text-lg font-serif font-bold ${isDarkMode ? 'text-white' : 'text-[#0a2540]'}`}>Bibliothèque</h2>
                        </section>
                    )}

                    {/* 2/3 Poster Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-5">
                        {visibleMovies.map((movie) => (
                            <div
                                key={movie.id}
                                onClick={() => movie.type === 'Série' ? openSeries(movie) : openMovie(movie)}
                                className={`group relative flex flex-col rounded-xl overflow-hidden border transition-all duration-300 cursor-pointer transform hover:-translate-y-1.5 ${isDarkMode
                                    ? 'bg-[#0a0a0a] border-white/10 hover:border-[#635bff]/60 shadow-xl'
                                    : 'bg-white border-[#e3e8ee] hover:border-[#635bff] hover:shadow-xl shadow-sm'
                                    }`}
                            >
                                {/* Poster Container (Aspect Ratio 2/3) */}
                                <div className="relative aspect-[2/3] w-full overflow-hidden bg-slate-900">
                                    <img
                                        src={movie.poster}
                                        alt={movie.title}
                                        loading="lazy"
                                        decoding="async"
                                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                                    />
                                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent opacity-75 group-hover:opacity-30 transition-opacity" />

                                    {/* Rental badge and favorite */}
                                    <div className="absolute top-2.5 left-2.5 right-2.5 flex justify-start gap-1 pointer-events-none">
                                        <div className="flex w-full items-center gap-1 pointer-events-auto">
                                            {(() => {
                                                const badge = rentalCardBadge(rentalsByMedia[movie.id]);
                                                return badge && <span className={`text-[8.5px] font-mono font-bold px-1.5 py-0.5 rounded-md shadow backdrop-blur-md text-white ${BADGE_TONE_CLASSES[badge.tone]}`}>{badge.label}</span>;
                                            })()}
                                            <button
                                                type="button"
                                                onClick={(e) => toggleFavorite(movie.id, e)}
                                                aria-label={movie.isFavorite ? `Retirer ${movie.title} des favoris` : `Ajouter ${movie.title} aux favoris`}
                                                aria-pressed={movie.isFavorite}
                                                className="group/fav -my-2.5 -mr-2.5 ml-auto flex h-11 w-11 shrink-0 items-center justify-center"
                                            >
                                                <span aria-hidden="true" className="flex h-7 w-7 items-center justify-center rounded-full bg-black/60 text-xs text-white/80 backdrop-blur-md transition-all group-hover/fav:bg-black/80">
                                                    <Icon name="heart" filled={movie.isFavorite} className={`h-3.5 w-3.5 ${movie.isFavorite ? 'text-rose-500' : ''}`} />
                                                </span>
                                            </button>
                                        </div>
                                    </div>

                                    {/* Rating Stars Overlay */}
                                    <div className="absolute bottom-2.5 left-2.5 flex items-center gap-0.5 backdrop-blur-sm bg-black/40 px-1.5 py-0.5 rounded-md">
                                        {(() => {
                                            const rating = parseFloat(movie.rating) || 0;
                                            return [1, 2, 3, 4, 5].map((idx) => {
                                                const fillRatio = rating >= idx ? 1 : rating >= idx - 0.5 ? 0.5 : 0;
                                                return <StarIcon key={idx} fillRatio={fillRatio} size={13} isDarkMode={true} />;
                                            });
                                        })()}
                                    </div>
                                </div>

                                {/* Card Meta */}
                                <div className={`p-3.5 flex flex-col flex-1 justify-between ${isDarkMode ? 'bg-[#0a0a0a]' : 'bg-white'
                                    }`}>
                                    <div>
                                        <h2 className={`text-sm font-semibold truncate group-hover:text-[#635bff] transition-colors ${isDarkMode ? 'text-white' : 'text-[#0a2540]'
                                            }`}>
                                            {movie.title}
                                        </h2>
                                        <p className={`text-xs truncate mt-0.5 ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                                            }`}>
                                            {movie.director} • {movie.year}
                                        </p>
                                    </div>

                                    <div className={`mt-3 flex items-center justify-between text-xs font-mono border-t pt-2 ${isDarkMode ? 'text-white/40 border-white/5' : 'text-[#425466] border-[#e3e8ee]'
                                        }`}>
                                        <span>{movie.runtime}</span>
                                        <span className="font-semibold text-[#635bff]">{['Terminé', 'Terminée'].includes(movie.status) ? 'Vu' : movie.status}</span>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>

                    {visibleMovies.length < gridMovies.length && (
                        <div ref={observeLibrarySentinel(showMoreMovies)} className="mt-8 flex flex-col items-center gap-2">
                            <button type="button" onClick={showMoreMovies} className={`min-h-11 rounded-lg border px-5 text-sm font-semibold transition ${isDarkMode ? 'border-white/15 hover:bg-white/10' : 'border-[#e3e8ee] bg-white hover:bg-[#f6f9fc]'}`}>
                                Afficher plus de titres
                            </button>
                            <p className={`text-xs ${isDarkMode ? 'text-white/50' : 'text-[#425466]'}`}>{visibleMovies.length} sur {gridMovies.length}</p>
                        </div>
                    )}

                    {filteredMovies.length === 0 && !catalogueLoading && !catalogueError && (
                        <div className={`py-20 text-center font-mono text-sm ${isDarkMode ? 'text-white/40' : 'text-[#425466]'
                            }`}>
                            {collection === 'Séries' ? 'Aucune série ne correspond à ce filtre.' : 'Aucun film ne correspond à ce filtre.'}
                        </div>
                    )}
                    </>}
                </main>
            </div>


            {selectedSeries && (
                <SeriesDetailView
                    key={selectedSeries.id}
                    series={selectedSeries}
                    url={mediaPath(selectedSeries)}
                    episodes={seriesEpisodes}
                    view={seriesView}
                    loading={seriesLoading}
                    isDarkMode={isDarkMode}
                    isAdmin={isAdmin}
                    mediaAction={mediaAction}
                    onClose={closeSeries}
                    onPlayEpisode={openEpisodePlayer}
                    onToggleEpisode={toggleEpisode}
                    onSetSeasonWatched={setSeasonWatched}
                    onStatusChange={(status) => handleStatusChange(selectedSeries.id, status)}
                    onShare={() => shareMedia(selectedSeries)}
                    onToggleWatchlist={() => toggleWatchlist(selectedSeries.id)}
                    onAcquire={openAcquisition}
                    onRefresh={refreshSelectedSeries}
                    refreshing={seriesRefreshing}
                    onUseOriginalTitle={useOriginalSeriesTitle}
                    seasonRentals={rentals.filter((rental) => rental.media_id === selectedSeries.id && rental.rental_scope === 'season')}
                    onRequestParts={requestSeriesParts}
                    rentalPanel={selectedRental && (
                        <div className="rounded-xl border border-[#635bff]/30 bg-[#635bff]/5 p-4 text-xs">
                            <div>Location : <strong>{rentalStatusLabel(selectedRental)}</strong></div>
                            {rentalExpiryLabel(selectedRental) && <div className="mt-1 opacity-70">Location : {rentalExpiryLabel(selectedRental)} (le {new Date(selectedRental.expires_at).toLocaleDateString('fr-FR')})</div>}
                            {isQueuedRental(selectedRental) && <div className="mt-1 opacity-70">Demande prise en compte : la série n’est pas encore dans Jellyfin. Elle apparaîtra ici dès qu’elle sera disponible.</div>}
                            {isQueuedRental(selectedRental) && <button onClick={() => cancelQueuedRental()} className="mr-2 mt-2 rounded border border-rose-500/50 px-2 py-1 font-semibold text-rose-500">Annuler la demande</button>}
                            {selectedRental.status === 'available' && <button onClick={() => keepRental()} className="mt-2 rounded border border-[#635bff] px-2 py-1 font-semibold text-[#635bff]">Demander à conserver</button>}
                        </div>
                    )}
                />
            )}


            {/* Centered cinematic film detail */}
            {selectedMovie && (
                <FilmDetailView media={selectedMovie} isDarkMode={isDarkMode} onClose={closeMovie} url={mediaPath(selectedMovie)}>
                    <div
                        className={`film-detail-enter flex h-[min(94vh,980px)] w-full max-w-5xl flex-col overflow-y-auto rounded-2xl border shadow-2xl cursor-default ${isDarkMode
                            ? 'bg-[#0a0a0a] text-white border-white/10'
                            : 'bg-[#f6f9fc] text-[#0a2540] border-[#e3e8ee]'
                            }`}
                        onClick={(e) => e.stopPropagation()}
                    >
                        {/* Hero Horizontal Movie Backdrop Header */}
                        <div className="relative aspect-[16/9] w-full bg-slate-950 overflow-hidden shrink-0 group">
                            {selectedMovie.backdrop && selectedMovie.backdrop !== selectedMovie.poster ? (
                                <>
                                    {/* Ambient Blurred Background for Vertical Covers */}
                                    <img
                                        src={selectedMovie.backdrop}
                                        alt={selectedMovie.title}
                                        className="absolute inset-0 w-full h-full object-cover blur-xl opacity-40 scale-110"
                                    />

                                    {/* Main Banner Image (Full horizontal cover / fitted) */}
                                    <img
                                        src={selectedMovie.backdrop}
                                        alt={selectedMovie.title}
                                        className="relative w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                                    />
                                </>
                            ) : (
                                /* Clean Horizontal Fallback Header when no horizontal backdrop exists */
                                <div className="relative w-full h-full bg-gradient-to-br from-[#1a1c29] via-[#0d101d] to-[#04060c] flex items-center px-6 gap-5 overflow-hidden">
                                    <img
                                        src={selectedMovie.poster}
                                        alt={selectedMovie.title}
                                        className="absolute right-[-10%] top-[-20%] w-[70%] opacity-20 blur-2xl object-cover pointer-events-none"
                                    />
                                    <div className="relative z-10 w-20 h-28 rounded-lg overflow-hidden border border-white/20 shadow-2xl shrink-0">
                                        <img src={selectedMovie.poster} alt={selectedMovie.title} className="w-full h-full object-cover" />
                                    </div>
                                    <div className="relative z-10 text-white flex-1 min-w-0">
                                        <span className="text-xs font-mono uppercase bg-[#635bff] text-white px-2 py-0.5 rounded font-bold shadow">
                                            FICHE CINÉMA
                                        </span>
                                        <h3 className="text-xl font-serif font-bold mt-1 truncate drop-shadow">{selectedMovie.title}</h3>
                                        <p className="text-xs text-white/70 font-mono mt-0.5 truncate">{selectedMovie.director} • {selectedMovie.year}</p>
                                    </div>
                                </div>
                            )}

                            {/* Cinematic Dark Overlays */}
                            <div className="absolute inset-0 bg-gradient-to-t from-[#0a0a0a] via-[#0a0a0a]/40 to-transparent pointer-events-none" />
                            <div className="absolute inset-0 bg-gradient-to-r from-[#0a0a0a]/60 to-transparent pointer-events-none" />

                            {/* Close Button */}
                            <button
                                onClick={closeMovie}
                                className="absolute top-4 right-4 w-9 h-9 rounded-full bg-black/60 hover:bg-black/90 text-white flex items-center justify-center text-sm transition-all border border-white/20 backdrop-blur-md cursor-pointer z-10"
                                title="Fermer la fiche (ou cliquer à côté)"
                            >
                                ✕
                            </button>

                            {/* Header Info Overlay */}
                            <div className="absolute bottom-4 left-6 right-6 flex items-end justify-between">
                                <div>
                                    <div className="flex items-center gap-2 mb-1.5">
                                        <span className="text-xs font-mono uppercase bg-[#635bff] text-white px-2 py-0.5 rounded font-bold shadow-md">
                                            FICHE CINÉMA
                                        </span>
                                        <span className="text-xs font-mono text-white/70">{selectedMovie.year}</span>
                                        {selectedMovie.supports?.filter((support) => ['Serveur', 'Physique', 'Streaming', 'Cinéma'].includes(support)).map((support) => (
                                            <span key={support} className="text-xs font-mono uppercase bg-[#d9351c] text-white px-2 py-0.5 rounded-full font-bold shadow">
                                                {support}
                                            </span>
                                        ))}
                                    </div>

                                    <h2 className="text-3xl font-serif font-bold text-white tracking-tight leading-tight drop-shadow-md">
                                        {selectedMovie.title}
                                    </h2>
                                    <p className="text-xs text-white/80 mt-1 font-mono">
                                        Réalisé par {selectedMovie.director}{tmdbRating.mediaId === selectedMovie.id && tmdbRating.runtime ? ` • ${formatRuntime(tmdbRating.runtime)}` : ''}
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* Dark Mode / Light Mode Metadata Content */}
                        <div className={`p-6 space-y-5 flex-1 transition-colors duration-300 ${isDarkMode ? 'bg-[#000000]' : 'bg-[#f6f9fc]'
                            }`}>
                            {/* Statut & Support Direct Selectors Box */}
                            <div className={`p-4 rounded-xl border shadow-sm space-y-3.5 transition-colors duration-300 ${isDarkMode ? 'bg-[#0a0a0a] border-white/10' : 'bg-white border-[#e3e8ee]'
                                }`}>
                                <h3 className={`text-xs font-mono uppercase tracking-wider font-bold ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                                    }`}>
                                    MON SUIVI
                                </h3>

                                {/* Statut Selector */}
                                <div>
                                    <label className={`block text-xs font-semibold mb-1.5 ${isDarkMode ? 'text-white/70' : 'text-[#0a2540]'}`}>
                                        Statut du film :
                                    </label>
                                    <div className="flex flex-wrap gap-1.5">
                                        {[
                                            { id: 'À regarder', label: <><Icon name="bookmark" className="mr-1 h-3.5 w-3.5 align-[-2px]" />À regarder</>, color: 'bg-amber-500/20 text-amber-300 border-amber-500/40' },
                                            { id: 'watched', label: <><Icon name="eye" className="mr-1 h-3.5 w-3.5 align-[-2px]" />Terminé (Vu)</>, color: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' },
                                        ].map((st) => (
                                            <button
                                                key={st.id}
                                                onClick={() => handleStatusChange(selectedMovie.id, st.id)}
                                                className={`text-xs px-3 py-1.5 rounded-lg border font-medium cursor-pointer transition-all ${(st.id === 'watched' ? ['Terminé', 'Terminée'].includes(selectedMovie.status) : selectedMovie.status === st.id)
                                                    ? `${st.color} font-bold shadow-sm scale-105`
                                                    : isDarkMode
                                                        ? 'bg-white/5 border-white/10 text-white/60 hover:bg-white/10 hover:text-white'
                                                        : 'bg-[#f6f9fc] border-[#e3e8ee] text-[#425466] hover:bg-[#ebeef3] hover:text-[#0a2540]'
                                                    }`}
                                            >
                                                {st.label}
                                            </button>
                                        ))}
                                        <button
                                            type="button"
                                            onClick={() => toggleWatchlist(selectedMovie.id)}
                                            className={`text-xs px-3 py-1.5 rounded-lg border font-medium cursor-pointer transition-all ${selectedMovie.isWatchlist
                                                ? 'bg-blue-500/20 text-blue-500 border-blue-500/40 font-bold shadow-sm scale-105'
                                                : isDarkMode
                                                    ? 'bg-white/5 border-white/10 text-white/60 hover:bg-white/10 hover:text-white'
                                                    : 'bg-[#f6f9fc] border-[#e3e8ee] text-[#425466] hover:bg-[#ebeef3] hover:text-[#0a2540]'
                                                }`}
                                        >
                                            <Icon name="pin" className="mr-1 h-3.5 w-3.5 align-[-2px]" />Watchlist
                                        </button>
                                    </div>
                                </div>

                                {/* Support Selector (admin catalogue) */}
                                {isAdmin && <div className="border-t pt-3 border-white/5">
                                    <label className={`block text-xs font-semibold mb-1.5 ${isDarkMode ? 'text-white/70' : 'text-[#0a2540]'}`}>
                                        Support / Emplacement :
                                    </label>
                                    <div className="flex flex-wrap gap-1.5">
                                        {[
                                            { id: 'Serveur', label: <><Icon name="server" className="mr-1 h-3.5 w-3.5 align-[-2px]" />Serveur</> },
                                            { id: 'Physique', label: <><Icon name="disc" className="mr-1 h-3.5 w-3.5 align-[-2px]" />Physique</> },
                                            { id: 'Streaming', label: <><Icon name="globe" className="mr-1 h-3.5 w-3.5 align-[-2px]" />Streaming</> },
                                            { id: 'Cinéma', label: <><Icon name="ticket" className="mr-1 h-3.5 w-3.5 align-[-2px]" />Salle Cinéma</> },
                                        ].map((sup) => {
                                            const activeSupports = Array.isArray(selectedMovie.supports) && selectedMovie.supports.length > 0
                                                ? selectedMovie.supports
                                                : (selectedMovie.support ? [selectedMovie.support] : []);
                                            const isSelected = activeSupports.includes(sup.id);
                                            return (
                                                <button
                                                    key={sup.id}
                                                    onClick={() => handleSupportChange(selectedMovie.id, sup.id)}
                                                    className={`text-xs px-3 py-1.5 rounded-lg border font-medium cursor-pointer transition-all ${isSelected
                                                        ? 'bg-[#635bff] border-[#635bff] text-white font-bold shadow-md scale-105'
                                                        : isDarkMode
                                                            ? 'bg-white/5 border-white/10 text-white/60 hover:bg-white/10 hover:text-white'
                                                            : 'bg-[#f6f9fc] border-[#e3e8ee] text-[#425466] hover:bg-[#ebeef3] hover:text-[#0a2540]'
                                                        }`}
                                                >
                                                    {sup.label}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>}
                            </div>

                            {/* Cinema & Viewing Experience Box (Emplacement juste en dessous du support quand Cinéma est sélectionné) */}
                            {isAdmin && ((Array.isArray(selectedMovie.supports) ? selectedMovie.supports.includes('Cinéma') : selectedMovie.support === 'Cinéma') || selectedMovie.watchedInCinema) && (
                                <div className={`p-4 rounded-xl border shadow-sm space-y-3 transition-all duration-300 border-amber-500/30 ${isDarkMode ? 'bg-[#0a0a0a]' : 'bg-white'
                                    }`}>
                                    <div className="flex items-center justify-between">
                                        <h3 className="text-xs font-mono uppercase tracking-wider font-bold text-amber-500 flex items-center gap-1.5">
                                            <Icon name="ticket" />EXPÉRIENCE DE VISIONNAGE CINÉMA
                                        </h3>
                                        <span className="text-xs font-mono text-amber-500/80 bg-amber-500/10 px-2 py-0.5 rounded font-bold">
                                            SALLE OBSCURE
                                        </span>
                                    </div>

                                    <div className="grid grid-cols-2 gap-3">
                                        {/* Cinema Toggle */}
                                        <div className={`flex items-center justify-between p-3 rounded-xl border ${isDarkMode ? 'bg-white/5 border-white/10' : 'bg-[#f6f9fc] border-[#e3e8ee]'
                                            }`}>
                                            <div className="flex items-center gap-2.5">
                                                <Icon name="ticket" className="h-5 w-5" />
                                                <div>
                                                    <div className={`text-xs font-semibold ${isDarkMode ? 'text-white' : 'text-[#0a2540]'}`}>Séance Cinéma</div>
                                                    <div className={`text-xs font-mono ${isDarkMode ? 'text-white/40' : 'text-[#425466]'}`}>Vu en salle</div>
                                                </div>
                                            </div>
                                            <button
                                                onClick={() => toggleCinema(selectedMovie.id)}
                                                className={`w-10 h-6 rounded-full transition-colors relative cursor-pointer ${selectedMovie.watchedInCinema ? 'bg-emerald-500' : isDarkMode ? 'bg-white/20' : 'bg-slate-300'
                                                    }`}
                                            >
                                                <span className={`w-4 h-4 rounded-full bg-white absolute top-1 transition-transform ${selectedMovie.watchedInCinema ? 'left-5' : 'left-1'
                                                    }`} />
                                            </button>
                                        </div>

                                        {/* Date Picker */}
                                        <div className={`p-3 rounded-xl border flex flex-col justify-center ${isDarkMode ? 'bg-white/5 border-white/10' : 'bg-[#f6f9fc] border-[#e3e8ee]'
                                            }`}>
                                            <div className={`text-xs font-semibold mb-1 ${isDarkMode ? 'text-white' : 'text-[#0a2540]'}`}>Date de visionnage</div>
                                            <input
                                                aria-label="Date de visionnage"
                                                type="date"
                                                value={selectedMovie.watchedDate || ''}
                                                onChange={(e) => handleDateChange(selectedMovie.id, e.target.value)}
                                                className={`w-full text-xs rounded px-2 py-1 outline-none font-mono border ${isDarkMode
                                                    ? 'bg-black border-white/20 text-white focus:border-[#635bff]'
                                                    : 'bg-white border-[#e3e8ee] text-[#0a2540] focus:border-[#635bff]'
                                                    }`}
                                            />
                                        </div>
                                    </div>
                                </div>
                            )}

                            <div className={`flex items-center justify-between gap-4 rounded-xl border p-4 shadow-sm ${isDarkMode ? 'border-white/10 bg-[#0a0a0a]' : 'border-[#e3e8ee] bg-white'}`}>
                                <div className="flex min-w-0 items-center gap-3">
                                    <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${mediaAction.canPlay ? 'bg-emerald-500 text-white' : 'bg-[#635bff] text-white'}`} aria-hidden="true">{mediaAction.canPlay ? '✓' : '+'}</div>
                                    <div className="min-w-0"><p className="text-sm font-semibold">{mediaAction.canPlay ? 'Disponible dans ta bibliothèque' : mediaAction.disabled ? mediaAction.label : 'Ce film n’est pas encore disponible'}</p><p className="mt-0.5 truncate text-xs opacity-75">{playbackOffline ? <span className="font-semibold text-amber-600">Serveur de lecture hors ligne — réessaie dans quelques minutes</span> : mediaAction.canPlay ? 'Prêt à regarder' : (isAdmin ? 'Lancer une demande de téléchargement via Seerr' : selectedMedia?.type === 'Série' ? 'Demande-la à l’admin' : 'Location de 21 jours, lisible dès la fin du téléchargement')}</p></div>
                                </div>
                                <div className="flex shrink-0 items-center gap-2">
                                <button type="button" onClick={() => shareMedia(selectedMovie)} className={`rounded-lg border px-3 py-2.5 text-xs font-semibold transition ${isDarkMode ? 'border-white/15 text-white/70 hover:bg-white/10' : 'border-[#e3e8ee] text-[#425466] hover:bg-[#f6f9fc]'}`} aria-label={`Partager le lien de ${selectedMovie.title}`} title="Partager le lien"><Icon name="send" /></button>
                                <button type="button" onClick={(event) => toggleFavorite(selectedMovie.id, event)} className={`rounded-lg border px-3 py-2.5 text-xs font-semibold transition ${selectedMovie.isFavorite ? 'border-red-500/40 bg-red-500/10 text-red-500' : isDarkMode ? 'border-white/15 text-white/70 hover:bg-white/10' : 'border-[#e3e8ee] text-[#425466] hover:bg-[#f6f9fc]'}`} aria-label={selectedMovie.isFavorite ? 'Retirer des favoris' : 'Ajouter aux favoris'}>{selectedMovie.isFavorite ? '♥' : '♡'}</button>
                                <button
                                    onClick={mediaAction.disabled ? undefined : mediaAction.canPlay ? openPlayer : openAcquisition}
                                    disabled={mediaAction.disabled}
                                    className={mediaAction.canPlay
                                        ? 'flex items-center gap-2 whitespace-nowrap rounded-lg bg-emerald-500 px-4 py-2.5 text-sm font-bold text-white shadow-md transition-all hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60'
                                        : 'flex items-center gap-2 whitespace-nowrap rounded-lg bg-[#635bff] px-4 py-2.5 text-xs font-semibold text-white shadow-md transition-all hover:bg-[#5048e5] disabled:cursor-not-allowed disabled:opacity-60'}
                                >
                                    {mediaAction.canPlay && <span aria-hidden="true" className="text-base leading-none">▶</span>}
                                    <span>{mediaAction.label}</span>
                                </button>
                                </div>
                            </div>

                            {selectedRental && (
                                <div className={`mt-4 rounded-xl border p-4 text-xs ${isDarkMode ? 'border-[#635bff]/30 bg-[#635bff]/10' : 'border-[#635bff]/30 bg-[#635bff]/5'}`}>
                                    <div>Location : <strong>{rentalStatusLabel(selectedRental)}</strong></div>
                                    {rentalExpiryLabel(selectedRental) && <div className="mt-1 opacity-70">Location : {rentalExpiryLabel(selectedRental)} (le {new Date(selectedRental.expires_at).toLocaleDateString('fr-FR')})</div>}
                                    {isQueuedRental(selectedRental) && <div className="mt-1 opacity-70">Demande prise en compte : le film n’est pas encore dans Jellyfin. Il apparaîtra ici dès qu’il sera disponible.</div>}{isQueuedRental(selectedRental) && <button onClick={() => cancelQueuedRental()} className="mr-2 mt-2 rounded border border-rose-500/50 px-2 py-1 font-semibold text-rose-500">Annuler la demande</button>}{selectedRental.status === 'available' && <button onClick={() => keepRental()} className="mt-2 rounded border border-[#635bff] px-2 py-1 font-semibold text-[#635bff]">Demander à conserver</button>}
                                </div>
                            )}

                            {/* 5-Star Rating System with Half-Star Precision & Side Score */}
                            <div className={`p-4 rounded-xl border shadow-sm flex items-center justify-between transition-colors duration-300 ${isDarkMode ? 'bg-[#0a0a0a] border-white/10' : 'bg-white border-[#e3e8ee]'
                                }`}>
                                <div>
                                    <div className={`text-xs font-mono uppercase tracking-wider font-bold ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                                        }`}>
                                        VOTRE NOTE
                                    </div>
                                    <div className={`text-xs mt-0.5 ${isDarkMode ? 'text-white/60' : 'text-[#425466]'}`}>
                                        Évaluation par demi-étoiles
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() => openLibrarySeen(selectedMovie)}
                                        className="mt-2 rounded-lg border border-[#635bff] px-3 py-1.5 text-xs font-semibold text-[#635bff] hover:bg-[#635bff]/10"
                                    >
                                        Vu
                                    </button>
                                </div>

                                <div className="flex flex-wrap items-center justify-end gap-3">
                                    {/* 5 star buttons, 44 px each (touch friendly). Tapping the
                                        current star again removes half a star: 4 → 3,5. */}
                                    <div className="flex items-center select-none" role="group" aria-label="Ma note">
                                        {[1, 2, 3, 4, 5].map((starIndex) => {
                                            const rating = Number(selectedMovie.rating) || 0;
                                            const fillRatio = rating >= starIndex ? 1 : rating >= starIndex - 0.5 ? 0.5 : 0;
                                            const nextRating = rating === starIndex ? starIndex - 0.5 : starIndex;

                                            return (
                                                <button
                                                    key={starIndex}
                                                    type="button"
                                                    onClick={() => handleRate(selectedMovie.id, nextRating)}
                                                    className="flex h-11 w-11 items-center justify-center rounded-lg transition-transform hover:scale-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#635bff]"
                                                    aria-label={rating === starIndex ? `Noter ${String(starIndex - 0.5).replace('.', ',')} sur 5` : `Noter ${starIndex} sur 5`}
                                                    aria-pressed={rating >= starIndex - 0.5}
                                                    title={rating === starIndex ? `Toucher encore : ${String(starIndex - 0.5).replace('.', ',')} / 5` : `${starIndex} / 5`}
                                                >
                                                    <StarIcon fillRatio={fillRatio} size={26} isDarkMode={isDarkMode} />
                                                </button>
                                            );
                                        })}
                                    </div>

                                    {/* Score Next to Stars */}
                                    <div className="text-right">
                                        <span className="text-base font-bold font-mono text-amber-400">
                                            {selectedMovie.rating > 0 ? `${selectedMovie.rating} / 5` : '— / 5'}
                                        </span>
                                    </div>
                                    <div className="h-10 w-px bg-black/10 dark:bg-white/10" aria-hidden="true" />
                                    <div className="min-w-[140px] text-left sm:text-right">
                                        <div className={`text-xs font-mono uppercase tracking-wider font-bold ${isDarkMode ? 'text-white/50' : 'text-[#425466]'}`}>
                                            NOTE DU PUBLIC
                                        </div>
                                        <div className="mt-1 text-base font-bold font-mono text-[#01b4e4]" aria-live="polite">
                                            {tmdbRating.mediaId !== selectedMovie.id || tmdbRating.loading
                                                ? 'Chargement…'
                                                : typeof tmdbRating.rating === 'number'
                                                    ? `${tmdbRating.rating.toFixed(1)} / 10`
                                                    : 'Note indisponible'}
                                        </div>
                                    </div>
                                </div>
                            </div>



                            {/* Synopsis */}
                            <div className={`p-4 rounded-xl border shadow-sm transition-colors duration-300 ${isDarkMode ? 'bg-[#0a0a0a] border-white/10' : 'bg-white border-[#e3e8ee]'
                                }`}>
                                <h3 className={`text-xs font-mono uppercase tracking-wider mb-2 font-bold ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                                    }`}>
                                    SYNOPSIS
                                </h3>
                                <p className={`text-xs leading-relaxed ${isDarkMode ? 'text-white/80' : 'text-[#0a2540]'}`}>
                                    {selectedMovie.synopsis}
                                </p>
                            </div>

                            {/* Cast & Genres Grid */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                {/* Casting Principal avec suppression / ajout */}
                                <div className={`p-4 rounded-xl border shadow-sm transition-colors duration-300 ${isDarkMode ? 'bg-[#0a0a0a] border-white/10' : 'bg-white border-[#e3e8ee]'
                                    }`}>
                                    <h3 className={`text-xs font-mono uppercase tracking-wider mb-2 font-bold ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                                        }`}>
                                        ACTEURS PRINCIPAUX (CASTING)
                                    </h3>
                                    <ul className={`space-y-1.5 text-xs mb-3 ${isDarkMode ? 'text-white/80' : 'text-[#0a2540]'}`}>
                                        {selectedMovie.cast.map((actor, idx) => (
                                            <li key={idx} className="flex items-center justify-between group">
                                                <span className="truncate flex items-center gap-1.5">
                                                    <span className="text-[#635bff] font-bold">•</span> {actor}
                                                </span>
                                                {isAdmin && <button
                                                    onClick={() => handleRemoveCastActor(selectedMovie.id, idx)}
                                                    className="opacity-0 group-hover:opacity-100 text-xs text-red-400 hover:text-red-600 px-1 transition-opacity cursor-pointer"
                                                    title="Retirer l'acteur"
                                                >
                                                    ✕
                                                </button>}
                                            </li>
                                        ))}
                                    </ul>
                                    {isAdmin && <div className="relative">
                                        <input
                                            aria-label="Ajouter un acteur"
                                            name="actorInput"
                                            type="text"
                                            value={actorQuery}
                                            onChange={(e) => setActorQuery(e.target.value)}
                                            onKeyDown={(e) => {
                                                if (e.key === 'Enter' && actorSuggestions[0]) {
                                                    e.preventDefault();
                                                    selectCastActor(actorSuggestions[0]);
                                                }
                                            }}
                                            placeholder="Rechercher un acteur TMDB..."
                                            className={`flex-1 text-xs px-2 py-1 rounded border outline-none font-sans ${isDarkMode
                                                ? 'bg-black border-white/20 text-white placeholder-white/40 focus:border-[#635bff]'
                                                : 'bg-[#f6f9fc] border-[#e3e8ee] text-[#0a2540] placeholder-[#425466]/50 focus:border-[#635bff]'
                                                }`}
                                        />
                                        {(actorSearchLoading || actorSuggestions.length > 0) && <div className={`absolute left-0 right-0 top-full z-20 mt-1 overflow-hidden rounded-lg border shadow-lg ${isDarkMode ? 'border-white/15 bg-[#161616]' : 'border-[#e3e8ee] bg-white'}`}>
                                            {actorSearchLoading && <div className="px-3 py-2 text-xs opacity-75">Recherche TMDB…</div>}
                                            {!actorSearchLoading && actorSuggestions.map((person) => <button key={person.tmdb_id} type="button" onClick={() => selectCastActor(person)} className={`flex w-full items-center gap-2 px-2 py-1.5 text-left text-xs hover:bg-[#635bff]/10 ${isDarkMode ? 'text-white' : 'text-[#0a2540]'}`}>
                                                {person.profile_url ? <img src={person.profile_url} alt="" className="h-8 w-8 rounded-full object-cover" /> : <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#635bff]/10 text-[#635bff]">•</span>}
                                                <span><strong className="block">{person.name}</strong><span className="opacity-75">{person.known_for_department || 'Acteur'}</span></span>
                                            </button>)}
                                        </div>}
                                    </div>}
                                </div>

                                {/* Genres avec sélection complète */}
                                <div className={`p-4 rounded-xl border shadow-sm transition-colors duration-300 ${isDarkMode ? 'bg-[#0a0a0a] border-white/10' : 'bg-white border-[#e3e8ee]'
                                    }`}>
                                    <h3 className={`text-xs font-mono uppercase tracking-wider mb-2 font-bold ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                                        }`}>
                                        GENRES DU FILM
                                    </h3>
                                    <div className="flex flex-wrap gap-1.5 mb-3">
                                        {selectedMovie.genre.map((g, idx) => (
                                            <span
                                                key={idx}
                                                className={`text-xs font-mono px-2.5 py-0.5 rounded-full border flex items-center gap-1 ${isDarkMode
                                                    ? 'bg-white/5 text-white/80 border-white/10'
                                                    : 'bg-[#f6f9fc] text-[#0a2540] border-[#e3e8ee]'
                                                    }`}
                                            >
                                                #{g}
                                                {isAdmin && selectedMovie.genre.length > 1 && (
                                                    <button
                                                        onClick={() => handleRemoveGenre(selectedMovie.id, g)}
                                                        className="text-xs hover:text-red-500 font-bold ml-0.5 cursor-pointer"
                                                        title="Supprimer ce genre"
                                                    >
                                                        ✕
                                                    </button>
                                                )}
                                            </span>
                                        ))}
                                    </div>
                                    {/* Dropdown de sélection des genres */}
                                    {isAdmin && <select
                                        aria-label="Ajouter un genre"
                                        onChange={(e) => {
                                            if (e.target.value) {
                                                handleAddGenre(selectedMovie.id, e.target.value);
                                                e.target.value = '';
                                            }
                                        }}
                                        defaultValue=""
                                        className={`w-full text-xs px-2 py-1 rounded border outline-none font-sans cursor-pointer ${isDarkMode
                                            ? 'bg-black border-white/20 text-white/80 focus:border-[#635bff]'
                                            : 'bg-[#f6f9fc] border-[#e3e8ee] text-[#0a2540] focus:border-[#635bff]'
                                            }`}
                                    >
                                        <option value="" disabled>+ Ajouter un genre à la liste...</option>
                                        {ALL_GENRES.filter(g => !selectedMovie.genre.includes(g)).map((g) => (
                                            <option key={g} value={g}>{g}</option>
                                        ))}
                                    </select>}
                                </div>
                            </div>

                            {/* User Notes Box avec auto-resize et option Plein Écran */}
                            <div className={`p-4 rounded-xl border shadow-sm transition-colors duration-300 ${isDarkMode ? 'bg-[#0a0a0a] border-white/10' : 'bg-white border-[#e3e8ee]'
                                }`}>
                                <div className="flex items-center justify-between mb-2">
                                    <h3 className={`text-xs font-mono uppercase tracking-wider font-bold ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                                        }`}>
                                        VOS NOTES PERSONNELLES
                                    </h3>
                                    <button
                                        onClick={() => setShowNotesModal(true)}
                                        className="text-xs font-mono text-[#635bff] hover:underline flex items-center gap-1 font-semibold cursor-pointer"
                                        title="Agrandir en mode lecture / écriture plein écran"
                                    >
                                        <span>⤢ Plein écran</span>
                                    </button>
                                </div>
                                <textarea
                                    aria-label="Mes notes"
                                    rows={3}
                                    value={selectedMovie.userNotes}
                                    onChange={(e) => {
                                        const notes = e.target.value;
                                        handleNotesChange(selectedMovie.id, notes);
                                        e.target.style.height = 'auto';
                                        e.target.style.height = `${e.target.scrollHeight}px`;
                                    }}
                                    onFocus={(e) => {
                                        e.target.style.height = 'auto';
                                        e.target.style.height = `${e.target.scrollHeight}px`;
                                    }}
                                    placeholder="Ajoute tes impressions…"
                                    className={`w-full text-xs p-3 rounded-lg border focus:border-[#635bff] focus:ring-1 focus:ring-[#635bff] outline-none transition-all font-sans resize-y min-h-[90px] ${isDarkMode
                                        ? 'border-white/15 bg-black text-white placeholder-white/30'
                                        : 'border-[#e3e8ee] bg-[#f6f9fc] text-[#0a2540] placeholder-[#425466]/40'
                                        }`}
                                />
                            </div>
                        </div>

                        {/* Drawer Footer Actions (ID Label Removed) */}
                        <div className={`p-4 border-t flex justify-between items-center transition-colors duration-300 ${isDarkMode ? 'border-white/10 bg-[#0a0a0a]' : 'border-[#e3e8ee] bg-white'
                            }`}>
                            <div className="flex items-center gap-2">
                                {isAdmin && <button
                                    onClick={() => {
                                        setTmdbSearchQuery(selectedMovie.title);
                                        setTmdbResults([]);
                                        setShowRelinkModal(true);
                                        handleSearchTMDB(selectedMovie.title);
                                    }}
                                    className={`px-3 py-1.5 rounded text-xs font-mono border flex items-center gap-1.5 transition-all cursor-pointer ${isDarkMode
                                        ? 'bg-[#635bff]/20 border-[#635bff]/40 text-[#635bff] hover:bg-[#635bff]/30 font-bold'
                                        : 'bg-[#635bff]/10 border-[#635bff]/30 text-[#635bff] hover:bg-[#635bff]/20 font-bold'
                                        }`}
                                    title="Changer d'association TMDB si le film est incorrect"
                                >
                                    <span className="flex items-center gap-1.5"><Icon name="refresh" />Réassocier TMDB</span>
                                </button>}
                            </div>

                            <button
                                onClick={closeMovie}
                                className={`text-xs font-semibold px-4 py-2 rounded-lg transition-all cursor-pointer shadow ${isDarkMode
                                    ? 'bg-white/10 hover:bg-white/20 border border-white/20 text-white'
                                    : 'bg-[#0a2540] hover:bg-black text-white'
                                    }`}
                            >
                                Fermer
                            </button>
                        </div>
                    </div>
                </FilmDetailView>
            )}

            {/* TMDB Search & Relink Modal */}
            {showAddDialog && (
                <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/70 p-4 pt-[8vh]" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowAddDialog(false); }}>
                    <div className={`flex max-h-[84vh] w-full max-w-xl flex-col overflow-hidden rounded-xl shadow-2xl outline-none ${isDarkMode ? 'bg-[#0e0e11] text-white' : 'bg-white text-[#0a2540]'}`} role="dialog" aria-modal="true" ref={addDialogRef} tabIndex={-1} aria-label={isAdmin ? (collection === 'Séries' ? 'Ajouter une série' : 'Ajouter un film') : 'Louer un film'}>
                        <div className="border-b border-current/10 p-5 pb-4">
                            <div className="mb-3 flex items-center justify-between"><h2 className="font-serif text-lg font-bold">{isAdmin ? (collection === 'Séries' ? 'Ajouter une série' : 'Ajouter un film') : 'Louer un film'}</h2><button type="button" onClick={() => setShowAddDialog(false)} className="rounded px-2 py-1 text-sm opacity-75 hover:opacity-100" aria-label="Fermer (Échap)" title="Fermer (Échap)">✕</button></div>
                            <div className="relative"><input autoFocus aria-label="Titre à rechercher" value={addQuery} onChange={e => setAddQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && searchToAdd()} placeholder={collection === 'Séries' ? 'Titre de la série' : 'Titre du film'} className={`w-full rounded-lg border px-3 py-2.5 pr-24 outline-none focus:border-[#635bff] ${isDarkMode ? 'border-white/15 bg-white/5' : 'border-[#e3e8ee]'}`}/><span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs opacity-75">{addSearching ? 'Recherche…' : addQuery.trim().length >= 2 ? `${addResults.length} résultat${addResults.length > 1 ? 's' : ''}` : ''}</span></div>
                        </div>
                        <div className={`flex-1 space-y-2 overflow-y-auto p-5 pt-4 ${addSearching ? 'opacity-75' : ''}`}>
                            {addLoading && <p className="text-sm opacity-70">Ajout en cours…</p>}
                            {!addLoading && addQuery.trim().length < 2 && <p className="py-6 text-center text-sm opacity-75">Tape au moins 2 lettres : les résultats s’affichent au fur et à mesure.</p>}
                            {!addLoading && !addSearching && addQuery.trim().length >= 2 && addResults.length === 0 && <p className="py-6 text-center text-sm opacity-75">Aucun résultat sur TMDB.</p>}
                            {!addLoading && addResults.map(result => <button type="button" key={result.tmdb_id} onClick={() => isAdmin ? (collection === 'Séries' ? addFromTMDB(result.tmdb_id) : prepareSeerrFilmRequest(result)) : (setShowAddDialog(false), openTMDBPreview({tmdb_id: result.tmdb_id, title: result.title}))} className={`flex w-full items-center gap-3 rounded-lg border p-2 text-left transition hover:border-[#635bff] ${isDarkMode ? 'border-white/10 hover:bg-white/5' : 'border-[#e3e8ee] hover:bg-[#f6f9fc]'}`}>
                                {result.poster_url ? <img src={result.poster_url} alt="" loading="lazy" className="h-16 w-11 shrink-0 rounded object-cover" /> : <span className="flex h-16 w-11 shrink-0 items-center justify-center rounded bg-current/10 text-lg opacity-40"><Icon name="film" className="h-5 w-5" /></span>}
                                <span className="min-w-0"><strong className="block truncate">{result.title}</strong><span className="text-xs opacity-75">{result.release_date?.slice(0, 4) || 'Date inconnue'}</span>{result.overview && <span className="mt-0.5 line-clamp-1 block text-xs opacity-75">{result.overview}</span>}</span>
                            </button>)}
                        </div>
                    </div>
                </div>
            )}

            {showAcquisitionModal && selectedMedia && !isAdmin && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4" onClick={() => setShowAcquisitionModal(false)} role="presentation">
                    <div ref={acquisitionDialogRef} tabIndex={-1} className={`w-full max-w-md rounded-2xl border p-6 shadow-2xl outline-none ${isDarkMode ? 'border-white/10 bg-[#0e0e11] text-white' : 'border-[#e3e8ee] bg-white text-[#0a2540]'}`} onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={`Louer ${selectedMedia.title}`}>
                        <p className="text-xs font-mono font-bold uppercase tracking-[0.2em] text-[#635bff]">Location</p>
                        <h2 className="mt-1 font-serif text-xl font-bold">Louer « {selectedMedia.title} »</h2>
                        <ul className="mt-4 space-y-2 text-sm opacity-80">
                            <li>• Téléchargé sur le serveur, tu es prévenu quand il est prêt.</li>
                            <li>• Disponible <strong>21 jours</strong>, puis 7 jours après ta première lecture.</li>
                            <li>• Tu pourras demander à le garder définitivement.</li>
                        </ul>
                        <p className={`mt-4 rounded-lg px-3 py-2 text-xs font-semibold ${countQueuedRentals(rentals) >= maxQueuedRentals ? 'bg-rose-500/10 text-rose-500' : 'bg-[#635bff]/10 text-[#635bff]'}`}>
                            {countRentalsInUse(rentals)}/{maxActiveRentals} locations en cours · {countQueuedRentals(rentals)}/{maxQueuedRentals} en attente{countQueuedRentals(rentals) >= maxQueuedRentals ? ' : file pleine, annule une demande en attente pour en ajouter une.' : ''}
                        </p>
                        <p className="mt-2 text-xs opacity-75">Pas encore trouvé sur l’indexeur ? Il reste en file d’attente et se télécharge tout seul dès qu’il sort, sans entamer tes 21 jours.</p>
                        {mediaServerError && <p className="mt-3 text-xs text-rose-500">{mediaServerError}</p>}
                        <div className="mt-6 flex justify-end gap-2">
                            <button type="button" onClick={() => setShowAcquisitionModal(false)} className="rounded-lg border border-current/15 px-4 py-2 text-xs font-semibold">Annuler</button>
                            <button type="button" onClick={submitAcquisition} disabled={acquisitionBusy || countQueuedRentals(rentals) >= maxQueuedRentals} className="rounded-lg bg-[#635bff] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">{acquisitionBusy ? 'Location…' : 'Louer ce film'}</button>
                        </div>
                    </div>
                </div>
            )}

            {showAcquisitionModal && (selectedMedia || pendingSeerrFilm) && isAdmin && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4">
                    <div ref={acquisitionDialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-label="Demande de téléchargement" className="w-full max-w-md rounded-xl bg-white p-5 text-[#0a2540] outline-none">
                        <h2 className="font-serif text-lg font-bold">{pendingSeerrFilm ? `Demander ${pendingSeerrFilm.title} à Seerr` : `Ajouter ${selectedMedia.title} au serveur`}</h2>
                        {pendingSeerrFilm && <p className="mt-2 text-xs text-slate-600">Après validation, Backstage enverra la demande à Seerr avec le profil choisi. Seerr doit avoir « Enable Automatic Search » activé pour lancer immédiatement la recherche Radarr.</p>}
                        {!pendingSeerrFilm && selectedMedia?.type === 'Film' && <p className="mt-2 text-xs text-slate-600">Le profil choisi sera transmis à Seerr. Pour lancer la recherche Radarr automatiquement, active « Enable Automatic Search » dans les réglages Services de Seerr.</p>}
                        <div className="mt-4 space-y-3">
                            <select aria-label="Profil de qualité" className="w-full rounded border p-2" value={acquisitionForm.quality_profile_id} onChange={e => setAcquisitionForm({...acquisitionForm, quality_profile_id: e.target.value})}>
                                {mediaServerOptions?.quality_profiles?.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                            </select>
                            {selectedMedia?.type === 'Série' && <select aria-label="Profil de langue" className="w-full rounded border p-2" value={acquisitionForm.language_profile_id} onChange={e => setAcquisitionForm({...acquisitionForm, language_profile_id: e.target.value})}>
                                {mediaServerOptions?.language_profiles?.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                            </select>}
                            <select aria-label="Dossier de destination" className="w-full rounded border p-2" value={acquisitionForm.root_folder} onChange={e => setAcquisitionForm({...acquisitionForm, root_folder: e.target.value})}>
                                {mediaServerOptions?.root_folders?.map(folder => <option key={folder.path} value={folder.path}>{folder.path}</option>)}
                            </select>
                            {selectedMedia?.type === 'Série' && <select aria-label="Épisodes à suivre" className="w-full rounded border p-2" value={acquisitionForm.monitor} onChange={e => setAcquisitionForm({...acquisitionForm, monitor: e.target.value})}><option value="all">Toutes les saisons</option><option value="future">Saisons futures</option></select>}
                        </div>
                        {mediaServerError && <p className="mt-3 text-xs text-red-600">{mediaServerError}</p>}
                        <div className="mt-5 flex justify-end gap-2"><button onClick={() => { setShowAcquisitionModal(false); setPendingSeerrFilm(null); setMediaServerError(null); }}>Annuler</button><button className="rounded bg-[#635bff] px-3 py-2 text-white disabled:opacity-50" disabled={acquisitionBusy} onClick={submitAcquisition}>{acquisitionBusy ? 'Envoi…' : pendingSeerrFilm ? 'Confirmer la demande' : 'Demander'}</button></div>
                    </div>
                </div>
            )}

            {showRelinkModal && selectedMovie && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-fade-in">
                    <div ref={relinkDialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-label="Réassocier avec TMDB" className={`w-full max-w-xl rounded-2xl border shadow-2xl overflow-hidden flex flex-col max-h-[85vh] outline-none ${isDarkMode ? 'bg-[#0e0e11] border-white/20 text-white' : 'bg-white border-[#e3e8ee] text-[#0a2540]'
                        }`}>
                        {/* Modal Header */}
                        <div className="p-4 border-b border-white/10 flex items-center justify-between bg-black/30">
                            <div>
                                <h3 className="text-base font-bold font-serif flex items-center gap-2">
                                    <span className="flex items-center gap-1.5"><Icon name="film" />Réassocier avec TMDB</span>
                                </h3>
                                <p className="text-xs text-white/60 font-mono mt-0.5">
                                    Film actuel : <strong className="text-white">{selectedMovie.title}</strong>
                                </p>
                            </div>
                            <button
                                onClick={() => setShowRelinkModal(false)}
                                className="w-8 h-8 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-sm"
                            >
                                ✕
                            </button>
                        </div>

                        {/* Search Input Bar */}
                        <div className="p-4 border-b border-white/10 space-y-2">
                            <form
                                onSubmit={(e) => {
                                    e.preventDefault();
                                    handleSearchTMDB(tmdbSearchQuery);
                                }}
                                className="flex gap-2"
                            >
                                <input
                                    aria-label="Rechercher sur TMDB"
                                    type="text"
                                    value={tmdbSearchQuery}
                                    onChange={(e) => setTmdbSearchQuery(e.target.value)}
                                    placeholder="Rechercher le titre exact ou l'année sur TMDB..."
                                    className={`flex-1 text-xs px-3 py-2 rounded-lg border outline-none font-sans ${isDarkMode
                                        ? 'bg-black border-white/20 text-white focus:border-[#635bff]'
                                        : 'bg-[#f6f9fc] border-[#e3e8ee] text-[#0a2540] focus:border-[#635bff]'
                                        }`}
                                />
                                <button
                                    type="submit"
                                    className="bg-[#635bff] hover:bg-[#5048e5] text-white text-xs font-semibold px-4 py-2 rounded-lg transition-all cursor-pointer shrink-0"
                                >
                                    {tmdbLoading ? 'Recherche...' : 'Rechercher'}
                                </button>
                            </form>
                            {tmdbError && <p className="text-xs text-red-400 font-mono">{tmdbError}</p>}
                        </div>

                        {/* TMDB Candidates List */}
                        <div className="p-4 overflow-y-auto space-y-3 flex-1">
                            {tmdbLoading ? (
                                <div className={`text-center py-8 text-xs font-mono ${isDarkMode ? 'text-white/50' : 'text-[#425466]/70'}`}>
                                    Recherche des correspondances TMDB en cours...
                                </div>
                            ) : tmdbResults.length === 0 ? (
                                <div className={`text-center py-8 text-xs font-mono ${isDarkMode ? 'text-white/50' : 'text-[#425466]/70'}`}>
                                    Aucun film trouvé sur TMDB pour "{tmdbSearchQuery}". Essaie un autre mot-clé.
                                </div>
                            ) : (
                                tmdbResults.map((r) => (
                                    <div
                                        key={r.tmdb_id}
                                        onClick={() => handleRelinkMovie(selectedMovie.id, r.tmdb_id)}
                                        className={`flex gap-4 p-3 rounded-xl border transition-all cursor-pointer group ${isDarkMode
                                            ? 'bg-white/5 border-white/10 hover:border-[#635bff] hover:bg-white/10'
                                            : 'bg-[#f6f9fc] border-[#e3e8ee] hover:border-[#635bff] hover:bg-white'
                                            }`}
                                    >
                                        <div className="w-16 aspect-[2/3] bg-slate-800 rounded-lg overflow-hidden shrink-0 shadow">
                                            {r.poster_url ? (
                                                <img src={r.poster_url} alt={r.title} className="w-full h-full object-cover group-hover:scale-105 transition-transform" />
                                            ) : (
                                                <div className="w-full h-full flex items-center justify-center text-xs text-white/40">Pas d'image</div>
                                            )}
                                        </div>

                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center justify-between">
                                                <h4 className={`text-sm font-bold ${isDarkMode ? 'text-white' : 'text-[#0a2540]'} group-hover:text-[#635bff] transition-colors truncate`}>
                                                    {r.title}
                                                </h4>
                                                <span className={`text-xs font-mono px-2 py-0.5 rounded shrink-0 ${isDarkMode ? 'bg-white/10 text-white/70' : 'bg-[#0a2540]/5 text-[#425466]'}`}>
                                                    {r.release_date ? new Date(r.release_date).getFullYear() : '—'}
                                                </span>
                                            </div>
                                            <p className={`text-xs mt-1 line-clamp-2 leading-relaxed ${isDarkMode ? 'text-white/70' : 'text-[#425466]'}`}>
                                                {r.overview || 'Aucun synopsis.'}
                                            </p>
                                            <div className="mt-2 text-xs font-mono text-[#635bff] font-bold">
                                                ID TMDB: {r.tmdb_id} • Cliquer pour réassocier →
                                            </div>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* Fullscreen Notes Modal */}
            {showNotesModal && selectedMovie && (
                <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/85 backdrop-blur-md p-4 animate-fade-in">
                    <div ref={notesDialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-label="Notes personnelles" className={`w-full max-w-3xl h-[80vh] rounded-2xl border shadow-2xl overflow-hidden flex flex-col outline-none ${isDarkMode ? 'bg-[#0a0a0a] border-white/20 text-white' : 'bg-white border-[#e3e8ee] text-[#0a2540]'}`}>
                        <div className="p-4 border-b border-white/10 flex items-center justify-between bg-black/30">
                            <div>
                                <h3 className="text-base font-bold font-serif flex items-center gap-2">
                                    <span className="flex items-center gap-1.5"><Icon name="note" />Notes personnelles — {selectedMovie.title}</span>
                                </h3>
                                <p className="text-xs opacity-75 font-mono mt-0.5">Édition / Lecture confort en plein écran</p>
                            </div>
                            <button
                                onClick={() => setShowNotesModal(false)}
                                className="w-8 h-8 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-sm cursor-pointer"
                            >
                                ✕
                            </button>
                        </div>
                        <div className="p-6 flex-1 flex flex-col">
                            <textarea
                                aria-label="Mes notes"
                                value={selectedMovie.userNotes}
                                onChange={(e) => {
                                    const notes = e.target.value;
                                    handleNotesChange(selectedMovie.id, notes);
                                }}
                                placeholder="Écris ici tes notes, analyses et impressions…"
                                className={`w-full flex-1 p-4 rounded-xl border text-sm font-sans leading-relaxed outline-none focus:border-[#635bff] focus:ring-1 focus:ring-[#635bff] resize-none ${isDarkMode
                                    ? 'bg-black/50 border-white/15 text-white placeholder-white/30'
                                    : 'bg-[#f6f9fc] border-[#e3e8ee] text-[#0a2540] placeholder-[#425466]/40'
                                }`}
                            />
                        </div>
                        <div className="p-4 border-t border-white/10 flex justify-between items-center bg-black/10">
                            <span className="text-xs font-mono opacity-75">Sauvegarde automatique</span>
                            <button
                                onClick={() => setShowNotesModal(false)}
                                className="bg-[#635bff] hover:bg-[#5048e5] text-white text-xs font-semibold px-5 py-2.5 rounded-xl cursor-pointer"
                            >
                                Terminer
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
