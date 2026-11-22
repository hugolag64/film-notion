import { useEffect, useMemo, useRef, useState } from 'react';
import FilmDetailView from './FilmDetailView';
import Icon from './Icon';
import { isActiveRental, rentalStatusLabel } from '../rentals';
import {
    episodeCode, formatAirDate, formatDuration, groupEpisodesBySeason, primaryEpisodeLabel,
    seasonAvailabilityLabel, seriesYears, tmdbStatusLabel,
} from '../series';

const ACCENT = '#635bff';

/**
 * Series fiche, streaming-app style: hero + one main action, progress stats,
 * a season picker and rich episode rows, then an « À propos » section.
 * All data and actions come from the parent; this component only keeps UI state.
 */
export default function SeriesDetailView({
    series, url, episodes, view, loading, isDarkMode, isAdmin, mediaAction,
    onClose, onPlayEpisode, onToggleEpisode, onSetSeasonWatched, onStatusChange,
    onShare, onToggleWatchlist, onAcquire, onRefresh, refreshing, onUseOriginalTitle,
    rentalPanel, seasonRentals = [], onRequestParts,
}) {
    const [backdropFailed, setBackdropFailed] = useState(false);
    const [menuOpen, setMenuOpen] = useState(false);
    const [expanded, setExpanded] = useState({});
    const [busySeason, setBusySeason] = useState(null);
    const [downloadOpen, setDownloadOpen] = useState(false);
    const [pickerOpen, setPickerOpen] = useState(false);
    const [pickedSeasons, setPickedSeasons] = useState([]);
    // Requests sent from this fiche: the server only tracks the series as a whole.
    const [requested, setRequested] = useState({});
    const [sending, setSending] = useState(null);
    const episodesRef = useRef(null);
    const menuRef = useRef(null);
    const downloadRef = useRef(null);

    const seasonGroups = useMemo(() => groupEpisodesBySeason(episodes), [episodes]);
    const seasons = useMemo(() => {
        const summaries = new Map((view?.seasons || []).map((season) => [season.season_number, season]));
        return Object.keys(seasonGroups).map(Number).sort((a, b) => a - b).map((number) => {
            const list = seasonGroups[number];
            return {
                name: `Saison ${number}`, availability: null, available: 0, aired: list.length,
                ...summaries.get(number),
                season_number: number,
                total: list.length,
                // Live count: follows optimistic episode toggles before the server answers.
                watched: list.filter((episode) => episode.watched).length,
            };
        });
    }, [seasonGroups, view?.seasons]);

    const nextEpisode = view?.next_episode || null;
    const [selectedSeason, setSelectedSeason] = useState(null);
    const activeSeason = selectedSeason ?? nextEpisode?.season_number ?? seasons[0]?.season_number ?? null;
    const season = seasons.find((item) => item.season_number === activeSeason) || seasons[0];
    const seasonEpisodes = season ? seasonGroups[season.season_number] || [] : [];

    useEffect(() => {
        if (!menuOpen && !downloadOpen) return undefined;
        const close = (event) => {
            if (!menuRef.current?.contains(event.target)) setMenuOpen(false);
            if (!downloadRef.current?.contains(event.target)) setDownloadOpen(false);
        };
        document.addEventListener('mousedown', close);
        return () => document.removeEventListener('mousedown', close);
    }, [menuOpen, downloadOpen]);

    const info = view?.info;
    const stats = view?.stats;
    const watchedCount = episodes.filter((episode) => episode.watched).length;
    const airedCount = stats?.aired ?? episodes.length;
    const watchedPercent = airedCount ? Math.round((watchedCount * 100) / airedCount) : 0;
    const years = seriesYears(info, series.year);
    const statusLabel = tmdbStatusLabel(info);
    const seasonCount = seasons.length;
    const metaParts = [
        years,
        seasonCount ? `${seasonCount} saison${seasonCount > 1 ? 's' : ''}` : null,
        (series.genre || []).slice(0, 3).join(', ') || null,
        statusLabel,
    ].filter(Boolean);
    const isDone = ['Terminé', 'Terminée'].includes(series.status);
    const creator = series.director && !/inconnu/i.test(series.director) ? series.director : null;
    const cast = (series.cast || []).filter((name) => name && name !== 'Acteur principal');

    const scrollToEpisodes = () => episodesRef.current?.scrollIntoView({behavior: 'smooth', block: 'start'});

    const rentalForSeason = (number) => seasonRentals.find((rental) => rental.season_number === number && isActiveRental(rental));
    const isSeasonComplete = (item) => item?.availability === 'complete';

    /** Send a request once; `key` marks what this fiche shows as « demandé ». */
    const request = async (key, payload, label) => {
        if (!onRequestParts || sending) return;
        setSending(key);
        try {
            if (await onRequestParts(payload, label)) setRequested((current) => ({...current, [key]: true}));
        } finally {
            setSending(null);
        }
    };
    const requestSeason = (number) => request(`s${number}`, {seasons: [number]}, `Saison ${number}`);
    const requestEpisode = (episode) => request(
        episode.id,
        {episodes: [{season_number: episode.season_number, episode_number: episode.episode_number}]},
        episodeCode(episode.season_number, episode.episode_number),
    );
    const requestPicked = async () => {
        const numbers = [...pickedSeasons].sort((a, b) => a - b);
        if (!numbers.length) return;
        await request(`s${numbers.join('-')}`, {seasons: numbers}, numbers.length > 1 ? `Saisons ${numbers.join(', ')}` : `Saison ${numbers[0]}`);
        setRequested((current) => Object.fromEntries([...Object.entries(current), ...numbers.map((number) => [`s${number}`, true])]));
        setPickerOpen(false);
        setPickedSeasons([]);
    };

    // One main action, chosen from what the viewer can actually do.
    let primary;
    if (mediaAction.canPlay && nextEpisode?.available) {
        primary = {label: primaryEpisodeLabel(nextEpisode), onClick: () => onPlayEpisode(nextEpisode), icon: 'play'};
    } else if (mediaAction.canPlay) {
        primary = {label: 'Choisir un épisode', onClick: scrollToEpisodes, icon: 'play'};
    } else if (mediaAction.disabled) {
        primary = {label: mediaAction.label, disabled: true};
    } else if (isAdmin) {
        primary = {label: 'Télécharger', onClick: () => setDownloadOpen((open) => !open), icon: 'download'};
    } else if (season) {
        const rented = rentalForSeason(season.season_number) || requested[`s${season.season_number}`];
        primary = rented
            ? {label: `Saison ${season.season_number} louée`, disabled: true, icon: 'check'}
            : {label: `Louer la saison ${season.season_number}`, onClick: () => requestSeason(season.season_number), icon: 'ticket'};
    } else {
        primary = {label: mediaAction.label, disabled: true};
    }
    const missingSeasons = seasons.filter((item) => !isSeasonComplete(item));

    const setSeasonWatched = async (watched) => {
        // Stay on this season: otherwise the picker follows the next episode away.
        setSelectedSeason(season.season_number);
        setBusySeason(season.season_number);
        try { await onSetSeasonWatched(season.season_number, watched); } finally { setBusySeason(null); }
    };

    const card = isDarkMode ? 'border-white/10 bg-white/5' : 'border-[#e3e8ee] bg-white';
    const muted = isDarkMode ? 'text-white/60' : 'text-[#425466]';
    const seasonAllWatched = season && season.watched >= season.total;

    return <FilmDetailView media={series} isDarkMode={isDarkMode} onClose={onClose} url={url}>
        <div
            className={`film-detail-enter flex h-[min(94vh,980px)] w-full max-w-5xl flex-col overflow-y-auto rounded-2xl border shadow-2xl cursor-default ${isDarkMode ? 'border-white/10 bg-[#0a0a0a] text-white' : 'border-[#e3e8ee] bg-[#f6f9fc] text-[#0a2540]'}`}
            onClick={(event) => event.stopPropagation()}
        >
            {/* Hero */}
            <div className="relative aspect-[16/9] max-h-[540px] w-full shrink-0 overflow-hidden bg-slate-950">
                {series.hasBackdrop && !backdropFailed ? (
                    <img src={series.backdrop} alt="" onError={() => setBackdropFailed(true)} className="h-full w-full object-cover" />
                ) : (
                    <div className="relative h-full w-full overflow-hidden bg-gradient-to-br from-[#1a1c29] via-[#0d101d] to-[#04060c]">
                        <img src={series.poster} alt="" className="absolute inset-0 h-full w-full scale-110 object-cover opacity-35 blur-2xl" />
                        <img src={series.poster} alt="" className="absolute right-6 top-6 hidden h-[62%] rounded-lg border border-white/20 object-cover shadow-2xl sm:block md:right-10" />
                    </div>
                )}
                <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black via-black/50 to-transparent" />
                <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-black/70 via-black/10 to-transparent" />
                <button type="button" onClick={onClose} aria-label="Fermer la fiche" className="absolute right-4 top-4 z-10 flex h-9 w-9 items-center justify-center rounded-full border border-white/20 bg-black/60 text-white backdrop-blur-md transition hover:bg-black/90">
                    <Icon name="close" />
                </button>
                <div className="absolute inset-x-5 bottom-5 text-white md:inset-x-8 md:bottom-7">
                    <span className="rounded px-2 py-0.5 text-xs font-mono font-bold" style={{background: ACCENT}}>SÉRIE</span>
                    <h2 className="mt-2 text-3xl font-serif font-bold leading-tight drop-shadow md:text-5xl">{series.title}</h2>
                    <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-white/80 md:text-sm">
                        {metaParts.map((part, index) => <span key={part}>{index > 0 && <span className="mr-2 opacity-50">·</span>}{part}</span>)}
                        {info?.vote_average && <span className="inline-flex items-center gap-1"><span className="opacity-50">·</span><Icon name="star" filled className="h-3.5 w-3.5 text-amber-400" />{info.vote_average.toFixed(1)}</span>}
                    </p>
                    <div className="mt-4 flex flex-wrap items-center gap-2">
                        <div ref={downloadRef} className="relative">
                            <button type="button" onClick={primary.onClick} disabled={primary.disabled || Boolean(sending)} aria-haspopup={primary.icon === 'download' ? 'menu' : undefined} aria-expanded={primary.icon === 'download' ? downloadOpen : undefined} className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-white px-5 text-sm font-semibold text-black shadow-lg transition hover:bg-white/90 disabled:cursor-not-allowed disabled:bg-white/60">
                                {primary.icon && <Icon name={primary.icon} filled={primary.icon === 'play'} className="h-4 w-4" />}{primary.label}{primary.icon === 'download' && <span aria-hidden="true" className="text-xs opacity-60">▾</span>}
                            </button>
                            {downloadOpen && <div role="menu" className={`absolute bottom-12 left-0 z-20 w-72 overflow-hidden rounded-xl border py-1 text-sm shadow-2xl ${isDarkMode ? 'border-white/10 bg-[#141414] text-white' : 'border-[#e3e8ee] bg-white text-[#0a2540]'}`}>
                                {!mediaAction.canPlay && <MenuItem onClick={() => { setDownloadOpen(false); onAcquire(); }}>Toute la série</MenuItem>}
                                {season && !isSeasonComplete(season) && <MenuItem onClick={() => { setDownloadOpen(false); requestSeason(season.season_number); }}>{season.name} (saison complète)</MenuItem>}
                                {missingSeasons.length > 1 && <MenuItem onClick={() => { setDownloadOpen(false); setPickerOpen(true); }}>Choisir des saisons…</MenuItem>}
                                <p className="px-4 py-2 text-xs opacity-60">Pour un seul épisode, utilise l’icône ⇩ dans la liste.</p>
                            </div>}
                        </div>
                        {isAdmin && mediaAction.canPlay && missingSeasons.length > 0 && <button type="button" onClick={() => setDownloadOpen((open) => !open)} aria-label="Télécharger des saisons manquantes" title="Télécharger des saisons manquantes" className="inline-flex h-11 w-11 items-center justify-center rounded-lg border border-white/30 bg-black/30 text-white/90 backdrop-blur-md transition hover:bg-black/50">
                            <Icon name="download" className="h-4 w-4" />
                        </button>}
                        {nextEpisode?.mode === 'resume' && mediaAction.canPlay && nextEpisode.available && <span className="text-xs text-white/70">{Math.round(nextEpisode.percent)} % vu</span>}
                        <button type="button" onClick={onToggleWatchlist} aria-pressed={series.isWatchlist} className={`inline-flex min-h-11 items-center gap-1.5 rounded-lg border px-3 text-sm backdrop-blur-md transition ${series.isWatchlist ? 'border-white bg-white/20 text-white' : 'border-white/30 bg-black/30 text-white/90 hover:bg-black/50'}`}>
                            <Icon name={series.isWatchlist ? 'check' : 'pin'} className="h-4 w-4" />Watchlist
                        </button>
                        <button type="button" onClick={onShare} aria-label={`Partager le lien de ${series.title}`} title="Partager le lien" className="inline-flex h-11 w-11 items-center justify-center rounded-lg border border-white/30 bg-black/30 text-white/90 backdrop-blur-md transition hover:bg-black/50">
                            <Icon name="send" className="h-4 w-4" />
                        </button>
                        <div ref={menuRef} className="relative">
                            <button type="button" onClick={() => setMenuOpen((open) => !open)} aria-haspopup="menu" aria-expanded={menuOpen} aria-label="Plus d’actions" className="inline-flex h-11 w-11 items-center justify-center rounded-lg border border-white/30 bg-black/30 text-white/90 backdrop-blur-md transition hover:bg-black/50">
                                <Icon name="more" className="h-5 w-5" />
                            </button>
                            {menuOpen && <div role="menu" className={`absolute bottom-12 left-0 z-20 w-64 overflow-hidden rounded-xl border py-1 text-sm shadow-2xl ${isDarkMode ? 'border-white/10 bg-[#141414] text-white' : 'border-[#e3e8ee] bg-white text-[#0a2540]'}`}>
                                <MenuItem onClick={() => { setMenuOpen(false); onStatusChange(isDone ? 'À regarder' : 'Terminée'); }}>{isDone ? 'Remettre « À regarder »' : 'Marquer la série comme vue'}</MenuItem>
                                {isAdmin && <MenuItem onClick={() => { setMenuOpen(false); onRefresh(); }} disabled={refreshing}>{refreshing ? 'Actualisation…' : 'Actualiser depuis TMDB'}</MenuItem>}
                                {isAdmin && series.originalTitle && series.originalTitle !== series.title && <MenuItem onClick={() => { setMenuOpen(false); onUseOriginalTitle(); }}>Utiliser le titre original</MenuItem>}
                            </div>}
                        </div>
                    </div>
                </div>
            </div>

            <div className="space-y-5 p-4 md:p-6">
                {/* Availability notice when the series cannot be played */}
                {!mediaAction.canPlay && <div className={`rounded-xl border p-4 text-sm ${card}`}>
                    <p className="font-semibold">Cette série n’est pas encore sur le serveur</p>
                    <p className={`mt-1 text-xs ${muted}`}>{isAdmin ? 'Lance une demande de téléchargement depuis le bouton principal.' : 'Demande-la à l’administrateur.'}</p>
                </div>}
                {rentalPanel}

                {/* Stats */}
                <section aria-label="Où tu en es" className={`grid grid-cols-2 gap-px overflow-hidden rounded-xl border md:grid-cols-4 ${isDarkMode ? 'border-white/10 bg-white/10' : 'border-[#e3e8ee] bg-[#e3e8ee]'}`}>
                    <Stat isDarkMode={isDarkMode} label="Épisodes vus" value={`${watchedCount} / ${airedCount}`}>
                        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-current/10"><div className="series-progress-fill h-full rounded-full" style={{width: `${watchedPercent}%`, background: ACCENT}} /></div>
                    </Stat>
                    <Stat isDarkMode={isDarkMode} label="Sur le serveur" value={stats?.available != null ? `${stats.available} / ${airedCount}` : '—'} hint={stats?.available == null ? 'Non relié au serveur' : null} />
                    <Stat isDarkMode={isDarkMode} label="Temps restant" value={formatDuration(stats?.remaining_minutes) || (watchedCount >= airedCount && airedCount ? 'Terminé' : '—')} />
                    <Stat isDarkMode={isDarkMode} label={info?.next_air_date ? 'Prochaine diffusion' : 'À suivre'}
                        value={info?.next_air_date ? formatAirDate(info.next_air_date) : nextEpisode ? episodeCode(nextEpisode.season_number, nextEpisode.episode_number) : '—'}
                        hint={info?.next_air_date && info.next_season_number ? episodeCode(info.next_season_number, info.next_episode_number) : nextEpisode?.title} />
                </section>

                {pickerOpen && <section aria-label="Choisir des saisons à télécharger" className={`rounded-xl border p-4 ${card}`}>
                    <div className="flex items-center justify-between gap-3">
                        <h3 className="text-sm font-semibold">Saisons à télécharger</h3>
                        <button type="button" onClick={() => setPickerOpen(false)} aria-label="Fermer" className="opacity-60 hover:opacity-100"><Icon name="close" /></button>
                    </div>
                    <p className={`mt-1 text-xs ${muted}`}>Chaque saison est cherchée en entier : les packs de saison sont privilégiés.</p>
                    <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
                        {missingSeasons.map((item) => <label key={item.season_number} className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border px-3 text-sm ${isDarkMode ? 'border-white/10' : 'border-[#e3e8ee]'}`}>
                            <input type="checkbox" checked={pickedSeasons.includes(item.season_number)} onChange={(event) => setPickedSeasons((current) => event.target.checked ? [...current, item.season_number] : current.filter((number) => number !== item.season_number))} className="h-4 w-4 accent-[#635bff]" />
                            <span className="flex-1">{item.name}</span>
                            {seasonAvailabilityLabel(item) && <span className="text-xs opacity-60">{item.availability === 'partial' ? `${item.available}/${item.aired}` : '—'}</span>}
                        </label>)}
                    </div>
                    <button type="button" onClick={requestPicked} disabled={!pickedSeasons.length || Boolean(sending)} className="mt-3 inline-flex min-h-11 items-center gap-2 rounded-lg px-4 text-sm font-semibold text-white disabled:opacity-50" style={{background: ACCENT}}>
                        <Icon name="download" className="h-4 w-4" />{pickedSeasons.length ? `Télécharger ${pickedSeasons.length} saison${pickedSeasons.length > 1 ? 's' : ''}` : 'Coche les saisons voulues'}
                    </button>
                </section>}

                {/* Episodes */}
                <section ref={episodesRef} aria-label="Épisodes" className="scroll-mt-4">
                    {loading && !episodes.length && <div className="space-y-3" aria-busy="true">
                        {[0, 1, 2].map((index) => <div key={index} className={`h-24 animate-pulse rounded-xl border ${card}`} />)}
                    </div>}
                    {!loading && !episodes.length && <div className={`rounded-xl border p-6 text-center text-sm ${card}`}>
                        <p>La liste des épisodes n’a pas pu être chargée depuis TMDB.</p>
                        {isAdmin && <button type="button" onClick={onRefresh} disabled={refreshing} className="mt-3 rounded-lg px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50" style={{background: ACCENT}}>{refreshing ? 'Actualisation…' : 'Actualiser depuis TMDB'}</button>}
                    </div>}
                    {season && <>
                        <div className="mb-3 flex flex-wrap items-center gap-3">
                            {seasons.length > 1 ? (
                                <label className="relative">
                                    <span className="sr-only">Choisir la saison</span>
                                    <select value={season.season_number} onChange={(event) => setSelectedSeason(Number(event.target.value))} className={`min-h-11 cursor-pointer appearance-none rounded-lg border py-2 pl-4 pr-10 text-base font-semibold ${isDarkMode ? 'border-white/15 bg-white/5 text-white' : 'border-[#e3e8ee] bg-white text-[#0a2540]'}`}>
                                        {seasons.map((item) => <option key={item.season_number} value={item.season_number}>{item.name}</option>)}
                                    </select>
                                    <span aria-hidden="true" className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs opacity-60">▼</span>
                                </label>
                            ) : <h3 className="text-lg font-semibold">{season.name}</h3>}
                            <span className={`text-xs ${muted}`}>
                                {season.total} épisode{season.total > 1 ? 's' : ''} · {season.watched}/{season.total} vu{season.watched > 1 ? 's' : ''}
                                {season.air_date && ` · ${season.air_date.slice(0, 4)}`}
                            </span>
                            {seasonAvailabilityLabel(season) && <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${season.availability === 'complete' ? 'bg-emerald-500/15 text-emerald-600' : season.availability === 'partial' ? 'bg-amber-500/15 text-amber-600' : 'bg-current/10 opacity-70'}`}>{seasonAvailabilityLabel(season)}</span>}
                            <SeasonAction
                                isAdmin={isAdmin} rental={rentalForSeason(season.season_number)}
                                requested={requested[`s${season.season_number}`]} busy={sending === `s${season.season_number}`}
                                complete={isSeasonComplete(season)} onRequest={() => requestSeason(season.season_number)}
                            />
                            <button type="button" onClick={() => setSeasonWatched(!seasonAllWatched)} disabled={busySeason === season.season_number} className={`ml-auto inline-flex min-h-9 items-center gap-1.5 rounded-lg border px-3 text-xs font-semibold transition disabled:opacity-50 ${isDarkMode ? 'border-white/15 hover:bg-white/10' : 'border-[#e3e8ee] bg-white hover:bg-[#f6f9fc]'}`}>
                                <Icon name={seasonAllWatched ? 'minus' : 'check'} className="h-3.5 w-3.5" />{seasonAllWatched ? 'Tout marquer non vu' : 'Tout marquer vu'}
                            </button>
                        </div>
                        {season.overview && <p className={`mb-3 text-sm leading-6 ${muted}`}>{season.overview}</p>}

                        <ol className={`divide-y overflow-hidden rounded-xl border ${isDarkMode ? 'divide-white/10 border-white/10 bg-white/[0.03]' : 'divide-[#e3e8ee] border-[#e3e8ee] bg-white'}`}>
                            {seasonEpisodes.map((episode) => {
                                const isNext = nextEpisode?.id === episode.id;
                                const playable = mediaAction.canPlay && episode.available && !episode.upcoming;
                                const meta = [formatDuration(episode.runtime), formatAirDate(episode.air_date)].filter(Boolean).join(' · ');
                                const isOpen = expanded[episode.id];
                                return <li key={episode.id} className={`flex gap-3 p-3 md:gap-4 md:p-4 ${isNext ? (isDarkMode ? 'bg-[#635bff]/10' : 'bg-[#635bff]/5') : ''}`}>
                                    <button type="button" onClick={playable ? () => onPlayEpisode(episode) : undefined} disabled={!playable} aria-label={playable ? `Lire ${episodeCode(episode.season_number, episode.episode_number)} ${episode.title}` : undefined} className="group relative aspect-video w-28 shrink-0 overflow-hidden rounded-lg bg-slate-800 disabled:cursor-default sm:w-40">
                                        {episode.still_url
                                            ? <img src={episode.still_url} alt="" loading="lazy" className={`h-full w-full object-cover ${episode.upcoming ? 'opacity-40' : ''}`} />
                                            : <div className="flex h-full w-full items-center justify-center font-mono text-sm text-white/40">E{String(episode.episode_number).padStart(2, '0')}</div>}
                                        {playable && <span className="absolute inset-0 flex items-center justify-center bg-black/0 transition group-hover:bg-black/40"><span className="flex h-9 w-9 items-center justify-center rounded-full bg-black/60 text-white opacity-0 transition group-hover:opacity-100"><Icon name="play" filled className="h-4 w-4" /></span></span>}
                                        {episode.percent > 0 && <span className="absolute inset-x-0 bottom-0 h-1 bg-white/30"><span className="block h-full" style={{width: `${episode.percent}%`, background: ACCENT}} /></span>}
                                    </button>
                                    <div className="min-w-0 flex-1">
                                        <div className="flex items-start gap-2">
                                            <div className="min-w-0 flex-1">
                                                <p className="truncate text-sm font-semibold">
                                                    <span className="mr-1.5 font-mono text-xs" style={{color: ACCENT}}>{episode.episode_number}.</span>
                                                    <span className={episode.watched ? 'opacity-60' : ''}>{episode.title}</span>
                                                </p>
                                                <p className={`mt-0.5 text-xs ${muted}`}>
                                                    {meta}
                                                    {isNext && <span className="ml-2 font-semibold" style={{color: ACCENT}}>{nextEpisode.mode === 'resume' ? 'En cours' : 'À suivre'}</span>}
                                                </p>
                                            </div>
                                            <button type="button" onClick={() => { setSelectedSeason(season.season_number); onToggleEpisode(episode); }} aria-pressed={episode.watched} aria-label={episode.watched ? `Marquer ${episode.title} comme non vu` : `Marquer ${episode.title} comme vu`} title={episode.watched ? 'Vu — cliquer pour annuler' : 'Marquer comme vu'} className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border transition ${episode.watched ? 'border-transparent text-white' : isDarkMode ? 'border-white/20 text-white/50 hover:border-white/50' : 'border-[#cfd7df] text-[#8898aa] hover:border-[#635bff] hover:text-[#635bff]'}`} style={episode.watched ? {background: ACCENT} : undefined}>
                                                <Icon name="check" className="h-4 w-4" />
                                            </button>
                                        </div>
                                        {episode.synopsis && <button type="button" onClick={() => setExpanded((current) => ({...current, [episode.id]: !isOpen}))} className={`mt-1.5 w-full text-left text-xs leading-5 ${muted} ${isOpen ? 'block' : 'line-clamp-2'}`} aria-expanded={isOpen}>
                                            {episode.synopsis}
                                        </button>}
                                        <p className="mt-1.5 text-xs">
                                            {episode.upcoming
                                                ? <span className="font-semibold text-amber-600">À venir{episode.air_date ? ` · ${formatAirDate(episode.air_date)}` : ''}</span>
                                                : !episode.available && (view?.has_server || !mediaAction.canPlay) ? <span className="inline-flex items-center gap-2">
                                                    <span className={muted}>{requested[episode.id] ? 'Téléchargement demandé' : 'Non téléchargé'}</span>
                                                    {isAdmin && !requested[episode.id] && !isSeasonComplete(season) && <button type="button" onClick={() => requestEpisode(episode)} disabled={Boolean(sending)} className="inline-flex items-center gap-1 rounded-md border px-2 py-1 font-semibold transition hover:border-[#635bff] hover:text-[#635bff] disabled:opacity-50" aria-label={`Télécharger seulement ${episodeCode(episode.season_number, episode.episode_number)}`}>
                                                        <Icon name="download" className="h-3.5 w-3.5" />Cet épisode
                                                    </button>}
                                                </span> : null}
                                        </p>
                                    </div>
                                </li>;
                            })}
                        </ol>
                    </>}
                </section>

                {/* About */}
                <section aria-label="À propos" className={`rounded-xl border p-5 ${card}`}>
                    <h3 className="text-xs font-mono uppercase tracking-widest opacity-75">À propos</h3>
                    <p className="mt-3 text-sm leading-6 opacity-85">{series.synopsis || 'Aucun synopsis disponible.'}</p>
                    <dl className="mt-4 grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
                        {creator && <About label="Création" value={creator} muted={muted} />}
                        {(series.genre || []).length > 0 && <About label="Genres" value={series.genre.join(' · ')} muted={muted} />}
                        {cast.length > 0 && <About label="Distribution" value={cast.join(' · ')} muted={muted} wide />}
                        {series.originalTitle && series.originalTitle !== series.title && <About label="Titre original" value={series.originalTitle} muted={muted} />}
                        {statusLabel && <About label="Diffusion" value={statusLabel} muted={muted} />}
                    </dl>
                </section>
            </div>
        </div>
    </FilmDetailView>;
}

function SeasonAction({isAdmin, rental, requested, busy, complete, onRequest}) {
    if (complete) return null;
    if (rental) return <span className="rounded-full bg-[#635bff]/15 px-2.5 py-1 text-xs font-semibold text-[#635bff]">Louée · {rentalStatusLabel(rental)}</span>;
    if (requested) return <span className="rounded-full bg-[#635bff]/15 px-2.5 py-1 text-xs font-semibold text-[#635bff]">{isAdmin ? 'Téléchargement demandé' : 'Location demandée'}</span>;
    return <button type="button" onClick={onRequest} disabled={busy} className="inline-flex min-h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-semibold text-white transition disabled:opacity-50" style={{background: ACCENT}}>
        <Icon name={isAdmin ? 'download' : 'ticket'} className="h-3.5 w-3.5" />
        {busy ? 'Envoi…' : isAdmin ? 'Télécharger la saison' : 'Louer la saison'}
    </button>;
}

function MenuItem({children, onClick, disabled}) {
    return <button type="button" role="menuitem" onClick={onClick} disabled={disabled} className="block w-full px-4 py-2.5 text-left transition hover:bg-current/5 disabled:opacity-50">{children}</button>;
}

function Stat({label, value, hint, children, isDarkMode}) {
    return <div className={`p-4 ${isDarkMode ? 'bg-[#0f0f10]' : 'bg-white'}`}>
        <p className="text-xs font-mono uppercase tracking-wider opacity-60">{label}</p>
        <p className="mt-1 text-lg font-semibold">{value}</p>
        {hint && <p className="mt-0.5 truncate text-xs opacity-60">{hint}</p>}
        {children}
    </div>;
}

function About({label, value, muted, wide}) {
    return <div className={wide ? 'sm:col-span-2' : ''}>
        <dt className={`text-xs ${muted}`}>{label}</dt>
        <dd className="mt-0.5">{value}</dd>
    </div>;
}
