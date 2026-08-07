import React, { useState, useEffect, useRef } from 'react';
import Hls from 'hls.js';
import AccountPanel from './AccountPanel';
import AdminCenter from './components/AdminCenter';
import RecommendationFlow from './components/RecommendationFlow';
import FilmDetailView from './components/FilmDetailView';
import { useAuth } from './auth-context';
import { fetchMedias, updateMedia, updatePersonalMedia, searchTMDB, searchTMDBPerson, relinkTMDB, createMediaFromTMDB, searchTMDBTV, createSeriesFromTMDB, fetchSeriesEpisodes, updateEpisode, refreshSeriesFromTMDB, fetchAvailability, getPlaybackManifest, fetchMediaServerOptions, fetchMediaServerStatus, requestAcquisition, fetchRentals, requestRentalKeep, fetchMediaServerActivity, syncPlayback, fetchTMDBRating } from './api';
import { filterAndSortMovies, filterOptions, normalizeStatus } from './library';
import { groupEpisodesBySeason, replaceEpisode, seriesProgressText } from './series';

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

const getMediaAction = (mediaType, availability) => {
    if (availability?.jellyfin_id) {
        return { label: 'Lire', canPlay: true, disabled: false };
    }
    if (availability?.state === 'downloading') {
        return { label: 'Téléchargement en cours', canPlay: false, disabled: true };
    }
    if (availability?.state === 'imported') {
        return { label: 'Indexation Jellyfin en cours', canPlay: false, disabled: true };
    }
    if (['requested', 'searching'].includes(availability?.state)) {
        return { label: 'Demande en cours', canPlay: false, disabled: true };
    }
    return {
        label: mediaType === 'Série' ? 'Demander cette série' : 'Demander ce film',
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
        const categories = parseMediaList(media.categories, ['Film']);
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
            director: media.director || 'Réalisateur inconnu',
            year: media.release_date ? (new Date(media.release_date).getFullYear() || '—') : '—',
            genre: categories,
            poster: media.cover_url || 'https://images.unsplash.com/photo-1536440136628-849c177e76a1?auto=format&fit=crop&w=600&q=80',
            backdrop: media.backdrop_url || media.cover_url || 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?auto=format&fit=crop&w=1200&q=80',
            synopsis: media.synopsis || 'Aucun synopsis disponible pour le moment.',
            cast: castList.length > 0 ? castList : ['Acteur principal'],
            rating: numericRating,
            userNotes: media.review || '',
            status: numericRating > 0 ? 'Terminé' : normalizeStatus(media.status || 'À regarder'),
            isFavorite: tagsList.includes('Favoris'),
            isWatchlist: Boolean(media.is_watchlist),
            runtime: '120 min',
            supports,
            support: media.support || null,
            ratingCount: 1,
            watchedInCinema: media.watched_in_cinema || false,
            watchedDate: media.watched_date || '',
            createdAt: media.created_at || '',
            localStreamUrl: `http://hp-prodesk.local:8090/stream/${media.id}.mkv`,
        };
    } catch (itemError) {
        console.error('Erreur mapping item', media?.title, itemError);
        return null;
    }
};

export default function BackstagePrototype() {
    const {user} = useAuth();
    const [movies, setMovies] = useState(INITIAL_MOVIES);
    const [collection, setCollection] = useState('Films');
    const [, setLoading] = useState(true);
    const [, setError] = useState(null);
    const [activeFilter, setActiveFilter] = useState('all'); // 'all' | 'watched' | 'unwatched' | 'watchlist' | 'favorite'
    const [selectedMovie, setSelectedMovie] = useState(null);
    const [tmdbRating, setTMDBRating] = useState({mediaId: null, loading: false, rating: null});
    const libraryScrollTop = useRef(0);
    const [selectedSeries, setSelectedSeries] = useState(null);
    const [seriesEpisodes, setSeriesEpisodes] = useState([]);
    const [seriesProgress, setSeriesProgress] = useState(null);
    const [openSeasons, setOpenSeasons] = useState({});
    const [openEpisodes, setOpenEpisodes] = useState({});
    const [seriesTab, setSeriesTab] = useState('details');
    const [seriesRefreshing, setSeriesRefreshing] = useState(false);
    const seriesRequestId = useRef(0);
    const selectedSeriesId = useRef(null);
    const episodeUpdateQueue = useRef(Promise.resolve());
    const episodeIntents = useRef(new Map());
    const episodeClickTimers = useRef(new Map());
    const [searchQuery, setSearchQuery] = useState('');
    const [filters, setFilters] = useState({ genre: '', director: '', status: '', support: '' });
    const [sort, setSort] = useState({ key: 'createdAt', direction: 'desc' });
    const [showAddDialog, setShowAddDialog] = useState(false);
    const [addQuery, setAddQuery] = useState('');
    const [addResults, setAddResults] = useState([]);
    const [addLoading, setAddLoading] = useState(false);
    const [mediaAvailability, setMediaAvailability] = useState(null);
    const [mediaServerError, setMediaServerError] = useState(null);
    const [mediaServerOptions, setMediaServerOptions] = useState(null);
    const [showAcquisitionModal, setShowAcquisitionModal] = useState(false);
    const [availabilityByMedia, setAvailabilityByMedia] = useState({});
    const [rentalsByMedia, setRentalsByMedia] = useState({});
    const [actorQuery, setActorQuery] = useState('');
    const [actorSuggestions, setActorSuggestions] = useState([]);
    const [actorSearchLoading, setActorSearchLoading] = useState(false);
    const [acquisitionForm, setAcquisitionForm] = useState({ quality_profile_id: '', language_profile_id: '', root_folder: '', monitor: 'all' });
    const [playerMedia, setPlayerMedia] = useState(null);
    const [playerLoading, setPlayerLoading] = useState(false);
    const [playerError, setPlayerError] = useState(null);
    const videoRef = useRef(null);
    const hlsRef = useRef(null);
    const [isDarkMode, setIsDarkMode] = useState(false); // Theme toggle state
    const [showAccountPanel, setShowAccountPanel] = useState(false);
    const [showAdminCenter, setShowAdminCenter] = useState(false);
    const [showRecommendationFlow, setShowRecommendationFlow] = useState(false);

    // TMDB Relink Modal State
    const [showRelinkModal, setShowRelinkModal] = useState(false);
    const [showNotesModal, setShowNotesModal] = useState(false);
    const [tmdbSearchQuery, setTmdbSearchQuery] = useState('');
    const [tmdbResults, setTmdbResults] = useState([]);
    const [tmdbLoading, setTmdbLoading] = useState(false);
    const [tmdbError, setTmdbError] = useState(null);

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
    const mediaAction = getMediaAction(selectedMedia?.type, mediaAvailability?.availability);
    const selectedRental = selectedMedia?.id ? rentalsByMedia[selectedMedia.id] : null;

    const openMovie = (movie) => {
        libraryScrollTop.current = window.scrollY;
        setSelectedMovie(movie);
    };

    const closeMovie = () => {
        setSelectedMovie(null);
        window.requestAnimationFrame(() => window.scrollTo(0, libraryScrollTop.current));
    };

    useEffect(() => {
        if (!selectedMovie) return undefined;
        const handleEscape = (event) => {
            if (event.key === 'Escape') closeMovie();
        };
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        window.addEventListener('keydown', handleEscape);
        return () => {
            document.body.style.overflow = previousOverflow;
            window.removeEventListener('keydown', handleEscape);
        };
    }, [selectedMovie]);

    useEffect(() => {
        if (!selectedMovieId) {
            setTMDBRating({mediaId: null, loading: false, rating: null});
            return undefined;
        }

        let cancelled = false;
        const mediaId = selectedMovieId;
        setTMDBRating({mediaId, loading: true, rating: null});
        fetchTMDBRating(mediaId)
            .then(({rating}) => {
                if (!cancelled) setTMDBRating({mediaId, loading: false, rating});
            })
            .catch(() => {
                if (!cancelled) setTMDBRating({mediaId, loading: false, rating: null});
            });

        return () => { cancelled = true; };
    }, [selectedMovieId]);

    const loadRentals = () => fetchRentals().then((result) => {
        setRentalsByMedia(Object.fromEntries((result.rentals || []).map((rental) => [rental.media_id, rental])));
    }).catch(() => {});

    const closePlayer = () => {
        setPlayerMedia(null);
        setPlayerError(null);
        setPlayerLoading(false);
    };

    const openPlayer = () => {
        if (!selectedMedia?.id || !mediaAvailability?.availability?.jellyfin_id) return;
        setPlayerError(null);
        setPlayerLoading(true);
        setPlayerMedia({
            title: selectedMedia.title,
            manifestUrl: getPlaybackManifest(selectedMedia.id),
        });
    };

    useEffect(() => {
        if (!playerMedia || !videoRef.current) return undefined;
        const video = videoRef.current;
        const manifestUrl = playerMedia.manifestUrl;
        let hls;

        const handleReady = () => setPlayerLoading(false);
        const handleError = () => {
            setPlayerLoading(false);
            setPlayerError('Impossible de démarrer la lecture de ce média.');
        };
        video.addEventListener('loadeddata', handleReady);
        video.addEventListener('error', handleError);

        if (video.canPlayType('application/vnd.apple.mpegurl')) {
            video.src = manifestUrl;
            video.play().catch(() => {});
        } else if (Hls.isSupported()) {
            hls = new Hls({ enableWorker: true });
            hlsRef.current = hls;
            hls.on(Hls.Events.MANIFEST_PARSED, () => {
                setPlayerLoading(false);
                video.play().catch(() => {});
            });
            hls.on(Hls.Events.ERROR, (_event, data) => {
                if (data.fatal) handleError();
            });
            hls.loadSource(manifestUrl);
            hls.attachMedia(video);
        } else {
            handleError();
        }

        return () => {
            video.removeEventListener('loadeddata', handleReady);
            video.removeEventListener('error', handleError);
            hls?.destroy();
            hlsRef.current = null;
            video.pause();
            video.removeAttribute('src');
            video.load();
        };
    }, [playerMedia]);

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
        fetchMediaServerActivity().then((activity) => {
            const items = activity.items || [];
            setAvailabilityByMedia(Object.fromEntries(items.map(item => [item.media_id, item])));
        }).catch(() => {});
    }, []);

    useEffect(() => {
        if (!user?.id) return;
        loadRentals();
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
                quality_profile_id: options.quality_profiles?.[0]?.id || '',
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

    const submitAcquisition = async () => {
        try {
            const result = await requestAcquisition(selectedMedia.id, {
                ...acquisitionForm,
                quality_profile_id: acquisitionForm.quality_profile_id ? Number(acquisitionForm.quality_profile_id) : null,
                root_folder: acquisitionForm.root_folder || null,
                language_profile_id: acquisitionForm.language_profile_id ? Number(acquisitionForm.language_profile_id) : null,
            });
            setMediaAvailability({ availability: result.availability, playback_url: null });
            if (result.rental) setRentalsByMedia((current) => ({...current, [selectedMedia.id]: result.rental}));
            setShowAcquisitionModal(false);
            showToast(`"${selectedMedia?.title}" a bien été ajouté au serveur !`, 'success');
            fetchMediaServerActivity().then((activity) => {
                const items = activity.items || [];
                setAvailabilityByMedia(Object.fromEntries(items.map(item => [item.media_id, item])));
            }).catch(() => {});
        } catch (error) {
            const errorMsg = error.message || 'Erreur lors de l\'ajout au serveur.';
            setMediaServerError(errorMsg);
            showToast(`Échec de l'ajout au serveur : ${errorMsg}`, 'error');
        }
    };

    const keepRental = async () => {
        if (!selectedRental?.id) return;
        try {
            const result = await requestRentalKeep(selectedRental.id);
            setRentalsByMedia((current) => ({...current, [selectedMedia.id]: result.rental}));
            showToast('Demande de conservation envoyée.', 'success');
        } catch (error) {
            showToast(error.message || 'Demande impossible.', 'error');
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
            console.log('API Medias chargées:', data?.length);
            const mapped = (data || []).map(mapMediaToMovie).filter(Boolean);

            setMovies(mapped);
            setError(null);
        } catch (err) {
            console.error('Erreur de chargement des médias:', err);
            setError('Impossible de se connecter au serveur Python (port 8090).');
        } finally {
            setLoading(false);
        }
    };


    useEffect(() => {
        loadRealMedias();
    }, []);

    const collectionMedias = movies.filter((movie) => movie.type === (collection === 'Séries' ? 'Série' : 'Film'));
    const filteredMovies = filterAndSortMovies(collectionMedias, { ...filters, query: searchQuery }, sort)
        .filter(movie => activeFilter === 'all' || activeFilter === 'watched' ? activeFilter === 'all' || ['Terminé', 'Terminée'].includes(movie.status)
            : activeFilter === 'unwatched' ? !['Terminé', 'Terminée'].includes(movie.status)
                : activeFilter === 'watchlist' ? movie.isWatchlist : movie.isFavorite);

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
        }
    };

    // Update Rating
    const handleRate = async (id, rating) => {
        try {
            const updated = await updatePersonalMedia(id, { rating: String(rating), status: 'Terminé' });
            replaceCanonicalMedia(updated);
        } catch (err) {
            console.error('API update failed:', err);
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
        }
    };

    // Update Status ("À regarder", "Terminé", "À télécharger", etc.)
    const handleStatusChange = async (id, newStatus) => {
        try {
            const updated = await updatePersonalMedia(id, { status: newStatus });
            replaceCanonicalMedia(updated);
        } catch (err) {
            console.error('API update status failed:', err);
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
        }
    };

    // Update Notes
    const handleNotesChange = async (id, notes) => {
        try {
            const updated = await updatePersonalMedia(id, { review: notes });
            replaceCanonicalMedia(updated);
        } catch (err) {
            console.error('API update failed:', err);
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
        } finally { setAddLoading(false); }
    };

    const searchToAdd = async () => {
        if (!addQuery.trim()) return;
        setAddLoading(true);
        try {
            setAddResults(collection === 'Séries'
                ? await searchTMDBTV(addQuery)
                : await searchTMDB(addQuery));
        } finally { setAddLoading(false); }
    };

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
            genre: series.genre || series.categories || [],
            year: series.year || (series.release_date ? new Date(series.release_date).getFullYear() : '—'),
        });
        setSeriesEpisodes([]);
        setSeriesProgress(null);
        setOpenSeasons({});
        setSeriesTab('details');
        try {
            const details = await fetchSeriesEpisodes(series.id);
            if (requestId !== seriesRequestId.current || selectedSeriesId.current !== series.id) return;
            setSeriesEpisodes(details.episodes || []);
            setSeriesProgress(details.progress);
            const firstSeason = details.progress?.seasons?.[0]?.season_number;
            if (firstSeason !== undefined) setOpenSeasons({ [firstSeason]: true });
        } catch (error) {
            console.error('Impossible de charger les épisodes de la série:', error);
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
                year: refreshed.release_date ? new Date(refreshed.release_date).getFullYear() : selectedSeries.year,
            };
            setSelectedSeries(mapped);
            setMovies((current) => current.map((media) => media.id === refreshed.id ? { ...media, ...mapped, status: refreshed.status } : media));
            const details = await fetchSeriesEpisodes(refreshed.id);
            setSeriesEpisodes(details.episodes || []);
            setSeriesProgress(details.progress);
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

    const handleEpisodeClick = (episodeId) => {
        const timer = window.setTimeout(() => {
            episodeClickTimers.current.delete(episodeId);
            setOpenEpisodes((current) => ({ ...current, [episodeId]: !current[episodeId] }));
        }, 220);
        episodeClickTimers.current.set(episodeId, timer);
    };

    const handleEpisodeDoubleClick = (event, episode) => {
        event.preventDefault();
        const timer = episodeClickTimers.current.get(episode.id);
        if (timer) {
            window.clearTimeout(timer);
            episodeClickTimers.current.delete(episode.id);
        }
        toggleEpisode(episode);
    };

    return (
        <div className={`min-h-screen font-sans antialiased selection:bg-[#635bff] selection:text-white flex flex-col transition-colors duration-300 ${isDarkMode ? 'bg-[#0a0a0a] text-white' : 'bg-[#f6f9fc] text-[#0a2540]'
            }`}>
            {/* Toast Floating Notification Banner */}
            {toastNotification && (
                <div className={`fixed top-5 right-5 z-[100] max-w-md px-4 py-3 rounded-xl shadow-2xl border backdrop-blur-md flex items-center justify-between gap-3 animate-slide-left-smooth ${
                    toastNotification.type === 'error'
                        ? 'bg-rose-950/90 border-rose-500/50 text-rose-100'
                        : 'bg-emerald-950/90 border-emerald-500/50 text-emerald-100'
                }`}>
                    <div className="flex items-center gap-2.5 text-xs font-semibold">
                        <span className="text-base">{toastNotification.type === 'error' ? '❌' : '✅'}</span>
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
                <div className="max-w-[1536px] mx-auto px-6 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <img src="/static/Logo.png" alt="Backstage" className="h-10 w-auto object-contain" />
                        <div>
                            <span className={`font-serif italic font-bold text-xl tracking-tighter ${isDarkMode ? 'text-white' : 'text-[#0a2540]'
                                }`}>
                                BACKSTAGE
                            </span>
                            <span className="text-[10px] font-mono uppercase tracking-widest text-[#635bff] block font-semibold -mt-1">
                                FILM VAULT • {isDarkMode ? 'DARK CINEMA' : 'STRIPE LIGHT'}
                            </span>
                        </div>
                    </div>

                    <div className="flex items-center gap-4">
                        <div className={`flex rounded-lg border p-1 text-xs font-semibold ${isDarkMode ? 'border-white/15 bg-white/5' : 'border-[#e3e8ee] bg-[#f6f9fc]'}`} aria-label="Films | Séries">
                            {['Films', 'Séries'].map((item) => (
                                <button key={item} onClick={() => changeCollection(item)} className={`rounded-md px-3 py-1.5 transition-all ${collection === item ? 'bg-[#635bff] text-white shadow-sm' : isDarkMode ? 'text-white/60 hover:text-white' : 'text-[#425466] hover:text-[#0a2540]'}`}>
                                    {item}
                                </button>
                            ))}
                        </div>
                        {/* Light / Dark Mode Switcher Button */}
                        <button
                            onClick={() => setIsDarkMode(!isDarkMode)}
                            className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium border flex items-center gap-2 transition-all cursor-pointer ${isDarkMode
                                ? 'bg-white/10 border-white/20 text-amber-300 hover:bg-white/20'
                                : 'bg-[#f6f9fc] border-[#e3e8ee] text-slate-700 hover:bg-[#ebeef3]'
                                }`}
                            title="Changer de thème"
                        >
                            <span>{isDarkMode ? '☀️ Mode Clair' : '🌙 Mode Sombre'}</span>
                        </button>

                        {/* Search Input */}
                        <div className="relative">
                            <input
                                type="text"
                                placeholder={collection === 'Séries' ? 'Rechercher une série, créateur...' : 'Rechercher un film, réalisateur...'}
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className={`text-xs rounded-lg px-3 py-2 w-72 transition-all outline-none border ${isDarkMode
                                    ? 'bg-white/5 border-white/15 focus:border-[#635bff] text-white placeholder-white/40'
                                    : 'bg-[#f6f9fc] border-[#e3e8ee] focus:border-[#635bff] text-[#0a2540] placeholder-[#425466]/50'
                                    }`}
                            />
                        </div>

                        <button onClick={() => setShowAddDialog(true)} className="bg-[#635bff] hover:bg-[#5048e5] text-white text-xs font-semibold px-4 py-2 rounded-lg transition-all shadow-md cursor-pointer">
                            {collection === 'Séries' ? '+ Ajouter une série' : '+ Ajouter un film'}
                        </button>
                        {user?.role === 'admin' && <button onClick={() => setShowAdminCenter(true)} className="rounded-lg border border-[#635bff]/40 px-3 py-2 text-xs font-semibold text-[#635bff]" title="Ouvrir l’administration">
                            Administration
                        </button>}
                        <button onClick={() => setShowAccountPanel(true)} className="rounded-lg border px-3 py-2 text-xs font-semibold" title="Ouvrir le compte">
                            {user?.display_name || 'Compte'}
                        </button>
                    </div>
                </div>
            </header>

            {showAccountPanel && <AccountPanel isDarkMode={isDarkMode} onClose={() => setShowAccountPanel(false)} />}
            {showAdminCenter && user?.role === 'admin' && <AdminCenter isDarkMode={isDarkMode} onClose={() => setShowAdminCenter(false)} onMediaChanged={loadRealMedias} />}
            {showRecommendationFlow && <RecommendationFlow isDarkMode={isDarkMode} onClose={() => setShowRecommendationFlow(false)} />}

            {/* Main App Layout with Dynamic Floating Sidebar */}
            <div className="flex-1 max-w-[1536px] w-full mx-auto flex p-6 gap-8">
                {/* Floating Sidebar */}
                <aside className="w-64 shrink-0 flex flex-col gap-6 sticky top-22 h-[calc(100vh-7rem)]">
                    {/* Filter Card */}
                    <div className={`rounded-2xl p-4 flex flex-col gap-4 transition-colors duration-300 border ${isDarkMode
                        ? 'bg-[#0a0a0a]/90 backdrop-blur-md border-white/10 shadow-2xl'
                        : 'bg-white border-[#e3e8ee] shadow-sm'
                        }`}>
                        <div className="flex items-center justify-between px-2 pt-1">
                            <span className={`text-[10px] font-mono uppercase tracking-widest font-bold ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                                }`}>
                                NAVIGATION
                            </span>
                            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                        </div>

                        <nav className="space-y-1.5">
                            {[
                                { id: 'all', label: collection === 'Séries' ? 'Toutes les séries' : 'Tous les films', icon: '🎬', count: collectionMedias.length },
                                { id: 'watched', label: collection === 'Séries' ? 'Séries terminées' : 'Films vus', icon: '👁️', count: collectionMedias.filter(m => ['Terminé', 'Terminée'].includes(m.status)).length },
                                { id: 'watchlist', label: 'Watchlist', icon: '📌', count: collectionMedias.filter(m => m.isWatchlist).length },
                                { id: 'unwatched', label: collection === 'Séries' ? 'Séries à regarder' : 'À regarder', icon: '🔖', count: collectionMedias.filter(m => !['Terminé', 'Terminée'].includes(m.status)).length },
                                { id: 'favorite', label: 'Favoris', icon: '❤️', count: collectionMedias.filter(m => m.isFavorite).length },
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
                                        <span className="text-sm">{item.icon}</span>
                                        <span>{item.label}</span>
                                    </div>
                                    <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full ${activeFilter === item.id
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
                                    <span className="block text-[10px] font-mono uppercase tracking-widest text-white/70">Sélection personnalisée</span>
                                    <span className="mt-1 block text-sm font-semibold">✨ Choisir un film</span>
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
                        <span className={`text-[10px] font-mono uppercase tracking-widest font-bold px-2 ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                            }`}>
                            GENRES
                        </span>
                        <div className="flex flex-wrap gap-1.5 px-1">
                            {['Horror', 'Sci-Fi', 'Drama', 'Romance', 'Crime'].map((genre) => (
                                <button
                                    key={genre}
                                    className={`text-[11px] font-mono px-3 py-1 rounded-full cursor-pointer transition-all duration-200 border ${isDarkMode
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
                        <div className="text-[10px] font-mono uppercase text-[#635bff] tracking-widest font-bold mb-1">
                            ★ INSIGHTS COLLECTION
                        </div>
                        <div className="text-2xl font-serif text-white font-bold">
                            {movies.filter(m => m.rating === 5).length} / {movies.length}
                        </div>
                        <p className="text-[11px] text-white/70 mt-1">
                            Chef-d'œuvres notés 5 étoiles dans votre bibliothèque.
                        </p>
                    </div>
                </aside>

                {/* Main Content Area */}
                <main key={collection} className="series-portal flex-1 min-w-0">
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
                        <div className={`text-xs font-mono ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                            }`}>
                            {filteredMovies.length} Titre{filteredMovies.length > 1 ? 's' : ''} affiché{filteredMovies.length > 1 ? 's' : ''}
                        </div>
                    </div>

                    <div className="flex flex-wrap gap-2 mb-6">
                        <select value={sort.key} onChange={e => setSort(prev => ({ ...prev, key: e.target.value }))} className="text-xs rounded border px-2 py-1.5"><option value="createdAt">Date d'ajout</option><option value="title">Titre</option><option value="year">Année</option><option value="rating">Note</option></select>
                        <button onClick={() => setSort(prev => ({ ...prev, direction: prev.direction === 'asc' ? 'desc' : 'asc' }))} className="text-xs rounded border px-2 py-1.5">{sort.direction === 'asc' ? '↑ Croissant' : '↓ Décroissant'}</button>
                        {[['genre', 'Genre', filterOptions(collectionMedias, 'genre')], ['director', 'Réalisateur', filterOptions(collectionMedias, 'director')], ['status', 'Statut', ['À regarder', 'En cours', 'Terminé', 'Terminée']], ['support', 'Support', filterOptions(collectionMedias, 'supports')]].map(([key, label, options]) => <select key={key} value={filters[key]} onChange={e => setFilters(prev => ({ ...prev, [key]: e.target.value }))} className="text-xs rounded border px-2 py-1.5"><option value="">{label}</option>{options.map(option => <option key={option} value={option}>{option}</option>)}</select>)}
                        <button onClick={() => setFilters({ genre: '', director: '', status: '', support: '' })} className="text-xs text-[#635bff] px-2">Réinitialiser</button>
                    </div>

                    {/* 2/3 Poster Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-6">
                        {filteredMovies.map((movie) => (
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
                                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                                    />
                                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent opacity-50 group-hover:opacity-30 transition-opacity" />

                                    {/* Support pills and favorite */}
                                    <div className="absolute top-2.5 left-2.5 right-2.5 flex justify-start gap-1 pointer-events-none">
                                        <div className="flex w-full items-center gap-1 pointer-events-auto">
                                            {(Array.isArray(movie.supports) ? movie.supports : (movie.support ? [movie.support] : [])).filter((sup) => ['Serveur', 'Physique', 'Streaming', 'Cinéma'].includes(sup)).slice(0, 2).map((sup, idx) => (
                                                <span
                                                    key={idx}
                                                    className={`text-[8.5px] font-mono font-bold px-1.5 py-0.5 rounded-md shadow backdrop-blur-md text-white ${sup === 'Cinéma'
                                                        ? 'bg-rose-600/90'
                                                        : sup === 'Serveur'
                                                            ? 'bg-purple-600/90'
                                                            : sup === 'Physique'
                                                                ? 'bg-amber-600/90'
                                                                : 'bg-sky-600/90'
                                                        }`}
                                                >
                                                    {sup === 'Cinéma' ? '🍿 Cinéma' : sup === 'Serveur' ? '🖥️ Serveur' : sup === 'Physique' ? '📀 Physique' : '🌐 Streaming'}
                                                </span>
                                            ))}
                                            {availabilityByMedia[movie.id] && <span className="text-[8.5px] font-mono font-bold px-1.5 py-0.5 rounded-md bg-[#635bff]/90 text-white shadow">{availabilityByMedia[movie.id].state === 'available' ? 'Disponible' : availabilityByMedia[movie.id].state === 'imported' ? 'Possédé' : availabilityByMedia[movie.id].state === 'downloading' ? `${availabilityByMedia[movie.id].progress_percent || 0}%` : availabilityByMedia[movie.id].state === 'searching' ? 'Recherche' : availabilityByMedia[movie.id].state === 'error' ? 'Erreur' : 'Demandé'}</span>}
                                            <button
                                                onClick={(e) => toggleFavorite(movie.id, e)}
                                                className="w-6 h-6 rounded-full bg-black/60 backdrop-blur-md flex items-center justify-center text-xs hover:bg-black/80 transition-all text-white/80 shrink-0 ml-auto"
                                            >
                                                {movie.isFavorite ? '❤️' : '🤍'}
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
                                        <p className={`text-[11px] truncate mt-0.5 ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                                            }`}>
                                            {movie.director} • {movie.year}
                                        </p>
                                    </div>

                                    <div className={`mt-3 flex items-center justify-between text-[10px] font-mono border-t pt-2 ${isDarkMode ? 'text-white/40 border-white/5' : 'text-[#425466] border-[#e3e8ee]'
                                        }`}>
                                        <span>{movie.runtime}</span>
                                        <span className="font-semibold text-[#635bff]">{['Terminé', 'Terminée'].includes(movie.status) ? 'Vu' : movie.status}</span>
                                    </div>
                                    {movie.type === 'Série' && (
                                        <div className="series-progress mt-2 text-[10px] font-mono text-[#635bff]">
                                            Suivi des épisodes disponible
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>

                    {filteredMovies.length === 0 && (
                        <div className={`py-20 text-center font-mono text-sm ${isDarkMode ? 'text-white/40' : 'text-[#425466]'
                            }`}>
                            Aucun film ne correspond à ce filtre.
                        </div>
                    )}
                </main>
            </div>


            {selectedSeries && (
                <div className="fixed inset-0 z-50 flex justify-end bg-black/80 backdrop-blur-md animate-fade-in-smooth" onClick={closeSeries}>
                    <section className={`w-full max-w-xl h-full overflow-y-auto border-l shadow-2xl ${isDarkMode ? 'bg-[#0a0a0a] text-white border-white/10' : 'bg-[#f6f9fc] text-[#0a2540] border-[#e3e8ee]'}`} onClick={(event) => event.stopPropagation()}>
                        <div className="relative h-52 overflow-hidden bg-slate-950">
                            <img src={selectedSeries.backdrop || selectedSeries.poster} alt="" className="h-full w-full object-cover opacity-50 blur-sm scale-110" />
                            <div className="absolute inset-0 bg-gradient-to-t from-black via-black/45 to-transparent" />
                            <button onClick={closeSeries} className="absolute right-4 top-4 rounded-full bg-black/60 px-3 py-2 text-xs text-white">✕</button>
                            <div className="absolute bottom-5 left-6 right-6 text-white">
                                <span className="rounded bg-[#635bff] px-2 py-1 text-[10px] font-mono font-bold">FICHE SÉRIE</span>
                                <h2 className="mt-2 text-3xl font-serif font-bold">{selectedSeries.title}</h2>
                                <p className="mt-1 text-xs text-white/70">{selectedSeries.director} • {selectedSeries.year}</p>
                            </div>
                        </div>

                        <div className="p-5">
                            <div className={`mb-5 flex rounded-xl border p-1 ${isDarkMode ? 'border-white/10 bg-white/5' : 'border-[#e3e8ee] bg-white'}`}>
                                {[['details', 'Détails'], ['episodes', 'Épisodes']].map(([tab, label]) => <button key={tab} onClick={() => setSeriesTab(tab)} className={`flex-1 rounded-lg px-3 py-2 text-xs font-semibold transition ${seriesTab === tab ? 'bg-[#635bff] text-white shadow-lg' : 'opacity-60 hover:opacity-100'}`}>{label}</button>)}
                            </div>

                            {seriesTab === 'details' && <div className="space-y-5 animate-fade-in-smooth">
                                {selectedSeries.originalTitle && selectedSeries.originalTitle !== selectedSeries.title && <div className={`rounded-xl border p-4 ${isDarkMode ? 'border-white/10 bg-white/5' : 'border-[#e3e8ee] bg-white'}`}>
                                    <p className="text-[10px] font-mono uppercase tracking-widest opacity-60">Titre original</p>
                                    <div className="mt-2 flex items-center justify-between gap-3"><strong>{selectedSeries.originalTitle}</strong><button onClick={useOriginalSeriesTitle} className="rounded-lg border border-[#635bff]/40 px-3 py-1.5 text-xs font-semibold text-[#635bff]">Utiliser comme titre principal</button></div>
                                </div>}
                                <div className={`rounded-xl border p-4 ${isDarkMode ? 'border-white/10 bg-white/5' : 'border-[#e3e8ee] bg-white'}`}>
                                    <div className="flex items-center justify-between gap-3"><p className="text-[10px] font-mono uppercase tracking-widest opacity-60">Synopsis</p><button onClick={refreshSelectedSeries} disabled={seriesRefreshing} className="rounded-lg bg-[#635bff] px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50">{seriesRefreshing ? 'Actualisation…' : 'Actualiser TMDB'}</button></div>
                                    <p className="mt-3 text-sm leading-6 opacity-80">{selectedSeries.synopsis || 'Aucun synopsis disponible.'}</p>
                                    <button
                                        onClick={mediaAction.disabled ? undefined : mediaAction.canPlay ? openPlayer : openAcquisition}
                                        disabled={mediaAction.disabled}
                                        className="mt-3 rounded-lg bg-[#635bff] px-3 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                                    >
                                        {mediaAction.label}
                                    </button>
                                    {selectedRental && (
                                        <div className="mt-3 rounded-lg border border-[#635bff]/30 bg-[#635bff]/5 p-3 text-xs">
                                            <div>Location : <strong>{selectedRental.status === 'keep_requested' ? 'conservation demandée' : selectedRental.status === 'kept' ? 'Conservé définitivement' : selectedRental.status}</strong></div>
                                            {selectedRental.expires_at && <div className="mt-1 opacity-70">Expire le {new Date(selectedRental.expires_at).toLocaleDateString('fr-FR')}</div>}
                                            {selectedRental.status === 'available' && <button onClick={keepRental} className="mt-2 rounded border border-[#635bff] px-2 py-1 font-semibold text-[#635bff]">Demander à conserver</button>}
                                        </div>
                                    )}
                                </div>
                                <div className={`rounded-xl border p-4 ${isDarkMode ? 'border-white/10 bg-white/5' : 'border-[#e3e8ee] bg-white'}`}>
                                    <p className="text-[10px] font-mono uppercase tracking-widest opacity-60">Informations</p>
                                    <div className="mt-3 grid grid-cols-2 gap-4 text-sm"><div><span className="block text-xs opacity-60">Créateur</span>{selectedSeries.director || '—'}</div><div><span className="block text-xs opacity-60">Statut</span>{selectedSeries.status || 'À regarder'}</div><div className="col-span-2"><span className="block text-xs opacity-60">Genres</span>{(selectedSeries.genre || []).join(' • ') || '—'}</div><div className="col-span-2"><span className="block text-xs opacity-60">Casting</span>{(selectedSeries.cast || []).join(' • ') || '—'}</div></div>
                                    <div className="mt-4 flex flex-wrap gap-2">
                                        {['À regarder', 'Terminé'].map((status) => <button key={status} onClick={() => handleStatusChange(selectedSeries.id, status)} className={`rounded-lg border px-3 py-1.5 text-xs ${selectedSeries.status === status ? 'border-[#635bff] bg-[#635bff]/10 text-[#635bff]' : 'opacity-70'}`}>{status}</button>)}
                                        <button type="button" onClick={() => toggleWatchlist(selectedSeries.id)} className={`rounded-lg border px-3 py-1.5 text-xs ${selectedSeries.isWatchlist ? 'border-blue-500/40 bg-blue-500/10 text-blue-500' : 'opacity-70'}`}>📌 Watchlist</button>
                                    </div>
                                </div>
                            </div>}

                            {seriesTab === 'episodes' && <div className="space-y-4 animate-fade-in-smooth">
                            <div className={`series-progress rounded-xl border p-4 ${isDarkMode ? 'border-white/10 bg-white/5' : 'border-[#e3e8ee] bg-white'}`}>
                                <div className="flex items-center justify-between gap-3 text-xs font-mono">
                                    <strong>Progression générale</strong>
                                    <span>{seriesProgressText(seriesProgress)}</span>
                                </div>
                                <div className="mt-3 h-2 overflow-hidden rounded-full bg-black/10 dark:bg-white/10">
                                    <div className="series-progress-fill h-full rounded-full bg-[#635bff]" style={{ width: `${seriesProgress?.percentage || 0}%` }} />
                                </div>
                            </div>

                            {Object.entries(groupEpisodesBySeason(seriesEpisodes)).map(([seasonNumber, episodes]) => {
                                const progress = seriesProgress?.seasons?.find((season) => String(season.season_number) === seasonNumber);
                                const isOpen = openSeasons[seasonNumber];
                                return (
                                    <div key={seasonNumber} className={`overflow-hidden rounded-xl border ${isDarkMode ? 'border-white/10' : 'border-[#e3e8ee] bg-white'}`}>
                                        <button onClick={() => setOpenSeasons((current) => ({ ...current, [seasonNumber]: !isOpen }))} className="flex w-full items-center justify-between gap-3 p-4 text-left">
                                            <span className="font-semibold">Saison {seasonNumber}</span>
                                            <span className="text-xs font-mono text-[#635bff]">{progress ? `${progress.watched} / ${progress.total} • ${Math.round(progress.percentage)} %` : 'Chargement…'} {isOpen ? '⌃' : '⌄'}</span>
                                        </button>
                                        <div className="h-1 bg-black/10 dark:bg-white/10"><div className="series-progress-fill h-full bg-[#635bff]" style={{ width: `${progress?.percentage || 0}%` }} /></div>
                                        <div className={`season-content ${isOpen ? 'season-content-open' : ''}`}><div className="divide-y divide-black/10 dark:divide-white/10">
                                            {episodes.map((episode) => (
                                                <div key={episode.id} onClick={() => handleEpisodeClick(episode.id)} onDoubleClick={(event) => handleEpisodeDoubleClick(event, episode)} className="cursor-pointer p-3 text-sm">
                                                    <div className="flex items-center gap-3">
                                                    <input type="checkbox" checked={episode.watched} onClick={(event) => event.stopPropagation()} onChange={() => toggleEpisode(episode)} className="h-4 w-4 accent-[#635bff]" />
                                                    <span className="font-mono text-xs text-[#635bff]">E{String(episode.episode_number).padStart(2, '0')}</span>
                                                    <span className={episode.watched ? 'line-through opacity-50' : ''}>{episode.title}</span>
                                                    </div>
                                                    {openEpisodes[episode.id] && <p className="ml-7 mt-2 text-xs leading-relaxed opacity-70">{episode.synopsis || 'Aucun synopsis disponible pour cet épisode.'}</p>}
                                                </div>
                                            ))}
                                        </div></div>
                                    </div>
                                );
                            })}
                            {!seriesEpisodes.length && <p className="py-8 text-center text-xs font-mono opacity-60">Aucun épisode disponible.</p>}
                            </div>}
                        </div>
                    </section>
                </div>
            )}


            {/* Centered cinematic film detail */}
            {selectedMovie && (
                <FilmDetailView media={selectedMovie} isDarkMode={isDarkMode} onClose={closeMovie}>
                    <div
                        className={`flex h-[min(94vh,980px)] w-full max-w-5xl flex-col overflow-y-auto rounded-2xl border shadow-2xl animate-fade-in-smooth cursor-default ${isDarkMode
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
                                        <span className="text-[9px] font-mono uppercase bg-[#635bff] text-white px-2 py-0.5 rounded font-bold shadow">
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
                                        <span className="text-[9px] font-mono uppercase bg-[#635bff] text-white px-2 py-0.5 rounded font-bold shadow-md">
                                            FICHE CINÉMA
                                        </span>
                                        <span className="text-xs font-mono text-white/70">{selectedMovie.year}</span>
                                        {selectedMovie.supports?.filter((support) => ['Serveur', 'Physique', 'Streaming', 'Cinéma'].includes(support)).map((support) => (
                                            <span key={support} className="text-[9px] font-mono uppercase bg-[#d9351c] text-white px-2 py-0.5 rounded-full font-bold shadow">
                                                {support}
                                            </span>
                                        ))}
                                    </div>

                                    <h2 className="text-3xl font-serif font-bold text-white tracking-tight leading-tight drop-shadow-md">
                                        {selectedMovie.title}
                                    </h2>
                                    <p className="text-xs text-white/80 mt-1 font-mono">
                                        Réalisé par {selectedMovie.director} • {selectedMovie.runtime}
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
                                <h3 className={`text-[10px] font-mono uppercase tracking-wider font-bold ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                                    }`}>
                                    ⚙️ STATUT & SUPPORT DE STOCKAGE
                                </h3>

                                {/* Statut Selector */}
                                <div>
                                    <label className={`block text-[11px] font-semibold mb-1.5 ${isDarkMode ? 'text-white/70' : 'text-[#0a2540]'}`}>
                                        Statut du film :
                                    </label>
                                    <div className="flex flex-wrap gap-1.5">
                                        {[
                                            { id: 'À regarder', label: '🔖 À regarder', color: 'bg-amber-500/20 text-amber-300 border-amber-500/40' },
                                            { id: 'watched', label: '👁️ Terminé (Vu)', color: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' },
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
                                            📌 Watchlist
                                        </button>
                                    </div>
                                </div>

                                {/* Support Selector */}
                                <div className="border-t pt-3 border-white/5">
                                    <label className={`block text-[11px] font-semibold mb-1.5 ${isDarkMode ? 'text-white/70' : 'text-[#0a2540]'}`}>
                                        Support / Emplacement :
                                    </label>
                                    <div className="flex flex-wrap gap-1.5">
                                        {[
                                            { id: 'Serveur', label: '🖥️ Serveur' },
                                            { id: 'Physique', label: '📀 Physique' },
                                            { id: 'Streaming', label: '🌐 Streaming' },
                                            { id: 'Cinéma', label: '🍿 Salle Cinéma' },
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
                                </div>
                            </div>

                            {/* Cinema & Viewing Experience Box (Emplacement juste en dessous du support quand Cinéma est sélectionné) */}
                            {((Array.isArray(selectedMovie.supports) ? selectedMovie.supports.includes('Cinéma') : selectedMovie.support === 'Cinéma') || selectedMovie.watchedInCinema) && (
                                <div className={`p-4 rounded-xl border shadow-sm space-y-3 transition-all duration-300 border-amber-500/30 ${isDarkMode ? 'bg-[#0a0a0a]' : 'bg-white'
                                    }`}>
                                    <div className="flex items-center justify-between">
                                        <h3 className="text-[10px] font-mono uppercase tracking-wider font-bold text-amber-500 flex items-center gap-1.5">
                                            🍿 EXPÉRIENCE DE VISIONNAGE CINÉMA
                                        </h3>
                                        <span className="text-[10px] font-mono text-amber-500/80 bg-amber-500/10 px-2 py-0.5 rounded font-bold">
                                            SALLE OBSCURE
                                        </span>
                                    </div>

                                    <div className="grid grid-cols-2 gap-3">
                                        {/* Cinema Toggle */}
                                        <div className={`flex items-center justify-between p-3 rounded-xl border ${isDarkMode ? 'bg-white/5 border-white/10' : 'bg-[#f6f9fc] border-[#e3e8ee]'
                                            }`}>
                                            <div className="flex items-center gap-2.5">
                                                <span className="text-xl">🎟️</span>
                                                <div>
                                                    <div className={`text-xs font-semibold ${isDarkMode ? 'text-white' : 'text-[#0a2540]'}`}>Séance Cinéma</div>
                                                    <div className={`text-[10px] font-mono ${isDarkMode ? 'text-white/40' : 'text-[#425466]'}`}>Vu en salle</div>
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

                            {/* HP ProDesk Local Server Launch Banner */}
                            <div className="bg-gradient-to-r from-[#0a2540] to-[#000000] p-4 rounded-xl text-white shadow-lg flex items-center justify-between border border-[#635bff]/30">
                                <div className="flex items-center gap-3">
                                    <div className="w-10 h-10 rounded-lg bg-[#635bff] flex items-center justify-center text-lg font-mono font-bold shadow-md">
                                        ▶
                                    </div>
                                    <div>
                                        <div className="text-xs font-semibold uppercase tracking-wider font-mono text-emerald-400 flex items-center gap-1.5">
                                            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                                            HP PRODESK SERVEUR CONNECTÉ
                                        </div>
                                        <div className="text-[11px] font-mono text-white/70 mt-0.5 truncate max-w-[240px]">
                                            {selectedMovie.localStreamUrl || 'hp-prodesk.local'}
                                        </div>
                                    </div>
                                </div>
                                <button
                                    onClick={mediaAction.disabled ? undefined : mediaAction.canPlay ? openPlayer : openAcquisition}
                                    disabled={mediaAction.disabled}
                                    className={mediaAction.canPlay
                                        ? 'bg-emerald-500 hover:bg-emerald-400 focus-visible:ring-2 focus-visible:ring-emerald-300 text-white text-sm font-bold px-5 py-3 rounded-xl transition-all shadow-lg shadow-emerald-950/40 cursor-pointer flex items-center gap-2 whitespace-nowrap'
                                        : 'bg-[#635bff] hover:bg-[#5048e5] focus-visible:ring-2 focus-visible:ring-[#a9a3ff] text-white text-xs font-semibold px-4 py-2 rounded-lg transition-all shadow-md cursor-pointer flex items-center gap-2 whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-60'}
                                >
                                    {mediaAction.canPlay && <span aria-hidden="true" className="text-base leading-none">▶</span>}
                                    <span>{mediaAction.label}</span>
                                </button>
                            </div>

                            {selectedRental && (
                                <div className={`mt-4 rounded-xl border p-4 text-xs ${isDarkMode ? 'border-[#635bff]/30 bg-[#635bff]/10' : 'border-[#635bff]/30 bg-[#635bff]/5'}`}>
                                    <div>Location : <strong>{selectedRental.status === 'keep_requested' ? 'conservation demandée' : selectedRental.status === 'kept' ? 'Conservé définitivement' : selectedRental.status}</strong></div>
                                    {selectedRental.expires_at && <div className="mt-1 opacity-70">Expire le {new Date(selectedRental.expires_at).toLocaleDateString('fr-FR')}</div>}
                                    {selectedRental.status === 'available' && <button onClick={keepRental} className="mt-2 rounded border border-[#635bff] px-2 py-1 font-semibold text-[#635bff]">Demander à conserver</button>}
                                </div>
                            )}

                            {/* 5-Star Rating System with Half-Star Precision & Side Score */}
                            <div className={`p-4 rounded-xl border shadow-sm flex items-center justify-between transition-colors duration-300 ${isDarkMode ? 'bg-[#0a0a0a] border-white/10' : 'bg-white border-[#e3e8ee]'
                                }`}>
                                <div>
                                    <div className={`text-[10px] font-mono uppercase tracking-wider font-bold ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                                        }`}>
                                        VOTRE NOTE
                                    </div>
                                    <div className={`text-xs mt-0.5 ${isDarkMode ? 'text-white/60' : 'text-[#425466]'}`}>
                                        Évaluation par demi-étoiles
                                    </div>
                                </div>

                                <div className="flex flex-wrap items-center justify-end gap-3">
                                    {/* 5 Interactive Stars with Half-Star Click Zones */}
                                    <div className="flex items-center gap-1 text-2xl select-none">
                                        {[1, 2, 3, 4, 5].map((starIndex) => {
                                            const rating = selectedMovie.rating || 0;
                                            const fillRatio = rating >= starIndex ? 1 : rating >= starIndex - 0.5 ? 0.5 : 0;

                                            return (
                                                <div key={starIndex} className="relative cursor-pointer hover:scale-110 transition-transform flex items-center">
                                                    {/* Visual Star Display */}
                                                    <StarIcon fillRatio={fillRatio} size={22} isDarkMode={isDarkMode} />
                                                    {/* Left Half Click Overlay */}
                                                    <button
                                                        type="button"
                                                        onClick={() => handleRate(selectedMovie.id, starIndex - 0.5)}
                                                        className="absolute top-0 left-0 w-1/2 h-full opacity-0 z-10 cursor-pointer"
                                                        title={`${starIndex - 0.5} / 5`}
                                                    />
                                                    {/* Right Half Click Overlay */}
                                                    <button
                                                        type="button"
                                                        onClick={() => handleRate(selectedMovie.id, starIndex)}
                                                        className="absolute top-0 right-0 w-1/2 h-full opacity-0 z-10 cursor-pointer"
                                                        title={`${starIndex} / 5`}
                                                    />
                                                </div>
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
                                        <div className={`text-[10px] font-mono uppercase tracking-wider font-bold ${isDarkMode ? 'text-white/50' : 'text-[#425466]'}`}>
                                            UTILISATEURS <span className="text-[#01b4e4]">TMDB</span>
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
                                <h3 className={`text-[10px] font-mono uppercase tracking-wider mb-2 font-bold ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
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
                                    <h3 className={`text-[10px] font-mono uppercase tracking-wider mb-2 font-bold ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                                        }`}>
                                        ACTEURS PRINCIPAUX (CASTING)
                                    </h3>
                                    <ul className={`space-y-1.5 text-xs mb-3 ${isDarkMode ? 'text-white/80' : 'text-[#0a2540]'}`}>
                                        {selectedMovie.cast.map((actor, idx) => (
                                            <li key={idx} className="flex items-center justify-between group">
                                                <span className="truncate flex items-center gap-1.5">
                                                    <span className="text-[#635bff] font-bold">•</span> {actor}
                                                </span>
                                                <button
                                                    onClick={() => handleRemoveCastActor(selectedMovie.id, idx)}
                                                    className="opacity-0 group-hover:opacity-100 text-[10px] text-red-400 hover:text-red-600 px-1 transition-opacity cursor-pointer"
                                                    title="Retirer l'acteur"
                                                >
                                                    ✕
                                                </button>
                                            </li>
                                        ))}
                                    </ul>
                                    <div className="relative">
                                        <input
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
                                            className={`flex-1 text-[11px] px-2 py-1 rounded border outline-none font-sans ${isDarkMode
                                                ? 'bg-black border-white/20 text-white placeholder-white/40 focus:border-[#635bff]'
                                                : 'bg-[#f6f9fc] border-[#e3e8ee] text-[#0a2540] placeholder-[#425466]/50 focus:border-[#635bff]'
                                                }`}
                                        />
                                        {(actorSearchLoading || actorSuggestions.length > 0) && <div className={`absolute left-0 right-0 top-full z-20 mt-1 overflow-hidden rounded-lg border shadow-lg ${isDarkMode ? 'border-white/15 bg-[#161616]' : 'border-[#e3e8ee] bg-white'}`}>
                                            {actorSearchLoading && <div className="px-3 py-2 text-[11px] opacity-60">Recherche TMDB…</div>}
                                            {!actorSearchLoading && actorSuggestions.map((person) => <button key={person.tmdb_id} type="button" onClick={() => selectCastActor(person)} className={`flex w-full items-center gap-2 px-2 py-1.5 text-left text-[11px] hover:bg-[#635bff]/10 ${isDarkMode ? 'text-white' : 'text-[#0a2540]'}`}>
                                                {person.profile_url ? <img src={person.profile_url} alt="" className="h-8 w-8 rounded-full object-cover" /> : <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#635bff]/10 text-[#635bff]">•</span>}
                                                <span><strong className="block">{person.name}</strong><span className="opacity-60">{person.known_for_department || 'Acteur'}</span></span>
                                            </button>)}
                                        </div>}
                                    </div>
                                </div>

                                {/* Genres avec sélection complète */}
                                <div className={`p-4 rounded-xl border shadow-sm transition-colors duration-300 ${isDarkMode ? 'bg-[#0a0a0a] border-white/10' : 'bg-white border-[#e3e8ee]'
                                    }`}>
                                    <h3 className={`text-[10px] font-mono uppercase tracking-wider mb-2 font-bold ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                                        }`}>
                                        GENRES DU FILM
                                    </h3>
                                    <div className="flex flex-wrap gap-1.5 mb-3">
                                        {selectedMovie.genre.map((g, idx) => (
                                            <span
                                                key={idx}
                                                className={`text-[11px] font-mono px-2.5 py-0.5 rounded-full border flex items-center gap-1 ${isDarkMode
                                                    ? 'bg-white/5 text-white/80 border-white/10'
                                                    : 'bg-[#f6f9fc] text-[#0a2540] border-[#e3e8ee]'
                                                    }`}
                                            >
                                                #{g}
                                                {selectedMovie.genre.length > 1 && (
                                                    <button
                                                        onClick={() => handleRemoveGenre(selectedMovie.id, g)}
                                                        className="text-[9px] hover:text-red-500 font-bold ml-0.5 cursor-pointer"
                                                        title="Supprimer ce genre"
                                                    >
                                                        ✕
                                                    </button>
                                                )}
                                            </span>
                                        ))}
                                    </div>
                                    {/* Dropdown de sélection des genres */}
                                    <select
                                        onChange={(e) => {
                                            if (e.target.value) {
                                                handleAddGenre(selectedMovie.id, e.target.value);
                                                e.target.value = '';
                                            }
                                        }}
                                        defaultValue=""
                                        className={`w-full text-[11px] px-2 py-1 rounded border outline-none font-sans cursor-pointer ${isDarkMode
                                            ? 'bg-black border-white/20 text-white/80 focus:border-[#635bff]'
                                            : 'bg-[#f6f9fc] border-[#e3e8ee] text-[#0a2540] focus:border-[#635bff]'
                                            }`}
                                    >
                                        <option value="" disabled>+ Ajouter un genre à la liste...</option>
                                        {ALL_GENRES.filter(g => !selectedMovie.genre.includes(g)).map((g) => (
                                            <option key={g} value={g}>{g}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>

                            {/* User Notes Box avec auto-resize et option Plein Écran */}
                            <div className={`p-4 rounded-xl border shadow-sm transition-colors duration-300 ${isDarkMode ? 'bg-[#0a0a0a] border-white/10' : 'bg-white border-[#e3e8ee]'
                                }`}>
                                <div className="flex items-center justify-between mb-2">
                                    <h3 className={`text-[10px] font-mono uppercase tracking-wider font-bold ${isDarkMode ? 'text-white/50' : 'text-[#425466]'
                                        }`}>
                                        VOS NOTES PERSONNELLES
                                    </h3>
                                    <button
                                        onClick={() => setShowNotesModal(true)}
                                        className="text-[11px] font-mono text-[#635bff] hover:underline flex items-center gap-1 font-semibold cursor-pointer"
                                        title="Agrandir en mode lecture / écriture plein écran"
                                    >
                                        <span>⤢ Plein écran</span>
                                    </button>
                                </div>
                                <textarea
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
                                    placeholder="Ajoutez vos impressions..."
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
                                <button
                                    onClick={(e) => toggleFavorite(selectedMovie.id, e)}
                                    className={`px-3 py-1.5 rounded text-xs font-mono border flex items-center gap-1.5 transition-all cursor-pointer ${selectedMovie.isFavorite
                                        ? 'bg-red-500/10 border-red-500/40 text-red-500 font-bold'
                                        : isDarkMode
                                            ? 'bg-white/5 border-white/20 text-white/70 hover:bg-white/10'
                                            : 'bg-[#f6f9fc] border-[#e3e8ee] text-[#425466] hover:bg-[#ebeef3]'
                                        }`}
                                >
                                    <span>{selectedMovie.isFavorite ? '❤️ Favori' : '🤍 Favori'}</span>
                                </button>

                                <button
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
                                    <span>🔄 Réassocier TMDB</span>
                                </button>
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
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
                    <div className="w-full max-w-xl rounded-xl bg-white p-5 text-[#0a2540]">
                        <div className="flex justify-between items-center mb-3"><h2 className="font-serif text-lg font-bold">{collection === 'Séries' ? 'Ajouter une série' : 'Ajouter un film'}</h2><button onClick={() => setShowAddDialog(false)}>✕</button></div>
                        <div className="flex gap-2"><input value={addQuery} onChange={e => setAddQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && searchToAdd()} placeholder={collection === 'Séries' ? 'Titre de la série' : 'Titre du film'} className="flex-1 rounded border px-3 py-2"/><button onClick={searchToAdd} className="rounded bg-[#635bff] px-3 py-2 text-white">Rechercher</button></div>
                        <div className="mt-4 space-y-2">{addLoading ? 'Chargement…' : addResults.map(result => <button key={result.tmdb_id} onClick={() => addFromTMDB(result.tmdb_id)} className="block w-full rounded border p-3 text-left hover:border-[#635bff]"><strong>{result.title}</strong> {result.release_date?.slice(0, 4)}</button>)}</div>
                    </div>
                </div>
            )}

            {showAcquisitionModal && selectedMedia && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4">
                    <div className="w-full max-w-md rounded-xl bg-white p-5 text-[#0a2540]">
                        <h2 className="font-serif text-lg font-bold">Ajouter {selectedMedia.title} au serveur</h2>
                        <div className="mt-4 space-y-3">
                            <select className="w-full rounded border p-2" value={acquisitionForm.quality_profile_id} onChange={e => setAcquisitionForm({...acquisitionForm, quality_profile_id: e.target.value})}>
                                {mediaServerOptions?.quality_profiles?.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                            </select>
                            {selectedMedia.type === 'Série' && <select className="w-full rounded border p-2" value={acquisitionForm.language_profile_id} onChange={e => setAcquisitionForm({...acquisitionForm, language_profile_id: e.target.value})}>
                                {mediaServerOptions?.language_profiles?.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                            </select>}
                            <select className="w-full rounded border p-2" value={acquisitionForm.root_folder} onChange={e => setAcquisitionForm({...acquisitionForm, root_folder: e.target.value})}>
                                {mediaServerOptions?.root_folders?.map(folder => <option key={folder.path} value={folder.path}>{folder.path}</option>)}
                            </select>
                            {selectedMedia.type === 'Série' && <select className="w-full rounded border p-2" value={acquisitionForm.monitor} onChange={e => setAcquisitionForm({...acquisitionForm, monitor: e.target.value})}><option value="all">Toutes les saisons</option><option value="future">Saisons futures</option></select>}
                        </div>
                        {mediaServerError && <p className="mt-3 text-xs text-red-600">{mediaServerError}</p>}
                        <div className="mt-5 flex justify-end gap-2"><button onClick={() => setShowAcquisitionModal(false)}>Annuler</button><button className="rounded bg-[#635bff] px-3 py-2 text-white" onClick={submitAcquisition}>Demander</button></div>
                    </div>
                </div>
            )}

            {showRelinkModal && selectedMovie && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-fade-in">
                    <div className={`w-full max-w-xl rounded-2xl border shadow-2xl overflow-hidden flex flex-col max-h-[85vh] ${isDarkMode ? 'bg-[#0e0e11] border-white/20 text-white' : 'bg-white border-[#e3e8ee] text-[#0a2540]'
                        }`}>
                        {/* Modal Header */}
                        <div className="p-4 border-b border-white/10 flex items-center justify-between bg-black/30">
                            <div>
                                <h3 className="text-base font-bold font-serif flex items-center gap-2">
                                    <span>🎬 Réassocier avec TMDB</span>
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
                                    Aucun film trouvé sur TMDB pour "{tmdbSearchQuery}". Essayez un autre mot-clé.
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
                                                <div className="w-full h-full flex items-center justify-center text-[10px] text-white/40">Pas d'image</div>
                                            )}
                                        </div>

                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center justify-between">
                                                <h4 className={`text-sm font-bold ${isDarkMode ? 'text-white' : 'text-[#0a2540]'} group-hover:text-[#635bff] transition-colors truncate`}>
                                                    {r.title}
                                                </h4>
                                                <span className={`text-[10px] font-mono px-2 py-0.5 rounded shrink-0 ${isDarkMode ? 'bg-white/10 text-white/70' : 'bg-[#0a2540]/5 text-[#425466]'}`}>
                                                    {r.release_date ? new Date(r.release_date).getFullYear() : '—'}
                                                </span>
                                            </div>
                                            <p className={`text-xs mt-1 line-clamp-2 leading-relaxed ${isDarkMode ? 'text-white/70' : 'text-[#425466]'}`}>
                                                {r.overview || 'Aucun synopsis.'}
                                            </p>
                                            <div className="mt-2 text-[10px] font-mono text-[#635bff] font-bold">
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
                    <div className={`w-full max-w-3xl h-[80vh] rounded-2xl border shadow-2xl overflow-hidden flex flex-col ${isDarkMode ? 'bg-[#0a0a0a] border-white/20 text-white' : 'bg-white border-[#e3e8ee] text-[#0a2540]'}`}>
                        <div className="p-4 border-b border-white/10 flex items-center justify-between bg-black/30">
                            <div>
                                <h3 className="text-base font-bold font-serif flex items-center gap-2">
                                    <span>📝 Notes Personnelles — {selectedMovie.title}</span>
                                </h3>
                                <p className="text-xs opacity-60 font-mono mt-0.5">Édition / Lecture confort en plein écran</p>
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
                                value={selectedMovie.userNotes}
                                onChange={(e) => {
                                    const notes = e.target.value;
                                    handleNotesChange(selectedMovie.id, notes);
                                }}
                                placeholder="Écrivez vos notes longues, analyses et impressions ici..."
                                className={`w-full flex-1 p-4 rounded-xl border text-sm font-sans leading-relaxed outline-none focus:border-[#635bff] focus:ring-1 focus:ring-[#635bff] resize-none ${isDarkMode
                                    ? 'bg-black/50 border-white/15 text-white placeholder-white/30'
                                    : 'bg-[#f6f9fc] border-[#e3e8ee] text-[#0a2540] placeholder-[#425466]/40'
                                }`}
                            />
                        </div>
                        <div className="p-4 border-t border-white/10 flex justify-between items-center bg-black/10">
                            <span className="text-xs font-mono opacity-50">Sauvegarde automatique</span>
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

            {/* Full-screen Jellyfin player */}
            {playerMedia && (
                <div className="fixed inset-0 z-[70] flex flex-col bg-black">
                    <div className="w-full h-full bg-[#0a0a0a] overflow-hidden flex flex-col">
                        <div className="p-4 bg-black flex items-center justify-between border-b border-white/10">
                            <div className="flex items-center gap-2">
                                <span className="w-3 h-3 rounded-full bg-emerald-500 animate-pulse" />
                                <span className="text-xs font-mono font-bold text-white">
                                    JELLYFIN PLAYER • {playerMedia.title}
                                </span>
                            </div>
                            <button
                                onClick={closePlayer}
                                className="text-white/60 hover:text-white text-xs font-mono px-3 py-1 bg-white/10 rounded"
                            >
                                ✕ Fermer le lecteur
                            </button>
                        </div>
                        <div className="relative flex-1 min-h-0 bg-black flex items-center justify-center group">
                            <video ref={videoRef} controls autoPlay playsInline className="relative z-10 w-full h-full object-contain" />
                            {playerLoading && !playerError && (
                                <div className="absolute inset-0 z-20 flex items-center justify-center text-white/80 bg-black/40">
                                    <div className="text-center space-y-3">
                                        <div className="w-12 h-12 border-4 border-white/20 border-t-emerald-400 rounded-full animate-spin mx-auto" />
                                        <p className="text-sm">Préparation du flux Jellyfin…</p>
                                    </div>
                                </div>
                            )}
                            {playerError && (
                                <div className="absolute inset-0 z-30 flex items-center justify-center text-white bg-black/70 p-6">
                                    <div className="text-center space-y-4 max-w-md">
                                        <p className="text-lg font-semibold">Lecture impossible</p>
                                        <p className="text-sm text-white/70">{playerError}</p>
                                        <button onClick={closePlayer} className="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 font-semibold cursor-pointer">Fermer</button>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
