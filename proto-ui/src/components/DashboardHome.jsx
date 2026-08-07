import { useState } from 'react';

const posterUrl = (path, size = 'w500') => path
    ? (path.startsWith('http') ? path : `https://image.tmdb.org/t/p/${size}${path}`)
    : null;

const dateLabel = (value) => {
    if (!value) return '';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString('fr-FR', {
        day: 'numeric', month: 'short', year: 'numeric',
    });
};

const panelClass = (isDarkMode) => isDarkMode
    ? 'border-white/10 bg-white/[0.035] text-white'
    : 'border-[#e3e8ee] bg-white text-[#0a2540]';

function SectionHeading({ eyebrow, title, action, onAction, isDarkMode }) {
    return <div className="mb-5 flex items-end justify-between gap-4">
        <div>
            <p className="text-[10px] font-mono font-bold uppercase tracking-[0.24em] text-[#635bff]">{eyebrow}</p>
            <h2 className={`mt-1 text-2xl font-serif font-bold tracking-tight ${isDarkMode ? 'text-white' : 'text-[#0a2540]'}`}>{title}</h2>
        </div>
        {action && <button type="button" onClick={onAction} className="shrink-0 text-xs font-semibold text-[#635bff] hover:underline">{action}</button>}
    </div>;
}

function ContinueCard({ item, isDarkMode, onOpenMedia, onResume }) {
    const media = item.media;
    const image = posterUrl(media?.cover_url);
    const episode = item.series_title
        ? `${item.series_title}${item.season_number ? ` · S${item.season_number}E${item.episode_number || '?'}` : ''}`
        : media?.title || item.title;
    return <article className={`group overflow-hidden rounded-2xl border ${panelClass(isDarkMode)} shadow-sm transition duration-300 hover:-translate-y-0.5 hover:border-[#635bff]/60 hover:shadow-xl`}>
        <div className="flex min-h-52">
            <div className="relative w-36 shrink-0 overflow-hidden bg-slate-900 sm:w-44">
                {image ? <img src={image} alt={`Affiche de ${media?.title || item.title}`} className="h-full w-full object-cover transition duration-500 group-hover:scale-105" /> : <div className="flex h-full items-center justify-center p-4 text-center text-xs text-white/50">Affiche indisponible</div>}
                <div className="absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-black/75 to-transparent" />
                <span className="absolute bottom-3 left-3 rounded-full bg-black/65 px-2 py-1 text-[10px] font-mono font-bold text-white">{Math.round(item.percent || 0)} %</span>
            </div>
            <div className="flex min-w-0 flex-1 flex-col justify-between p-5">
                <div>
                    <p className="text-[10px] font-mono uppercase tracking-widest opacity-50">À reprendre</p>
                    <h3 className="mt-2 truncate text-xl font-semibold">{media?.title || item.title}</h3>
                    <p className="mt-1 truncate text-xs opacity-60">{episode}</p>
                    {item.last_played_at && <p className="mt-3 text-xs opacity-50">Vu le {dateLabel(item.last_played_at)}</p>}
                </div>
                <div className="mt-5">
                    <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-black/10 dark:bg-white/10" aria-label={`${Math.round(item.percent || 0)} % regardé`}>
                        <div className="h-full rounded-full bg-[#635bff]" style={{width: `${Math.min(100, Math.max(0, item.percent || 0))}%`}} />
                    </div>
                    <div className="flex flex-wrap gap-2">
                        <button type="button" onClick={() => onResume(item)} className="rounded-lg bg-[#635bff] px-3 py-2 text-xs font-semibold text-white shadow-sm hover:bg-[#5048e5]">Reprendre</button>
                        {media && <button type="button" onClick={() => onOpenMedia(media)} className="rounded-lg border border-current/15 px-3 py-2 text-xs font-semibold opacity-80 hover:border-[#635bff] hover:text-[#635bff]">Voir la fiche</button>}
                    </div>
                </div>
            </div>
        </div>
    </article>;
}

function RecommendationCard({ item, isDarkMode, onOpenMedia, onAddWatchlist, onWhyRecommendation }) {
    const [showWhy, setShowWhy] = useState(false);
    const image = posterUrl(item.poster_path);
    const pseudoMedia = {
        id: `tmdb-${item.tmdb_id}`,
        tmdbId: item.tmdb_id,
        title: item.title,
        type: 'Film',
        poster: image,
        backdrop: posterUrl(item.backdrop_path, 'w780'),
        synopsis: item.overview || 'Aucun synopsis disponible.',
        year: item.release_date?.slice(0, 4) || '—',
        rating: 0,
        genre: [],
        cast: [],
        supports: [],
        status: 'À regarder',
    };
    return <article className={`w-52 shrink-0 overflow-hidden rounded-2xl border ${panelClass(isDarkMode)} shadow-sm`}>
        <button type="button" className="group block w-full text-left" onClick={() => onOpenMedia(pseudoMedia)} aria-label={`Voir la fiche de ${item.title}`}>
            <div className="relative aspect-[2/3] overflow-hidden bg-slate-900">
                {image ? <img src={image} alt={`Affiche de ${item.title}`} className="h-full w-full object-cover transition duration-500 group-hover:scale-105" /> : <div className="flex h-full items-center justify-center p-4 text-center text-xs text-white/50">Affiche indisponible</div>}
                <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 to-transparent px-3 pb-3 pt-10 text-white">
                    <span className="text-[10px] font-mono font-bold">TMDB {item.vote_average ? item.vote_average.toFixed(1) : '—'}</span>
                </div>
            </div>
            <div className="p-3">
                <h3 className="truncate text-sm font-semibold">{item.title}</h3>
                <p className="mt-1 text-[11px] opacity-55">{item.release_date?.slice(0, 4) || 'Année inconnue'}</p>
            </div>
        </button>
        <div className="border-t border-current/10 p-3">
            <div className="flex flex-wrap gap-1.5">
                <button type="button" onClick={() => onOpenMedia(pseudoMedia)} className="rounded-md border border-current/15 px-2 py-1.5 text-[10px] font-semibold hover:border-[#635bff] hover:text-[#635bff]">Voir la fiche</button>
                <button type="button" onClick={() => { setShowWhy((value) => !value); onWhyRecommendation(item); }} className="rounded-md border border-current/15 px-2 py-1.5 text-[10px] font-semibold hover:border-[#635bff] hover:text-[#635bff]">Pourquoi ce film ?</button>
                <button type="button" onClick={() => onAddWatchlist(item)} className="w-full rounded-md bg-[#635bff]/10 px-2 py-1.5 text-[10px] font-semibold text-[#635bff] hover:bg-[#635bff]/20">Ajouter à ma watchlist</button>
            </div>
            {showWhy && <p className="mt-2 rounded-lg bg-[#635bff]/10 p-2 text-[10px] leading-4 text-[#635bff]">{item.reasons?.[0] || 'Ce film correspond à ton profil de visionnage.'}</p>}
        </div>
    </article>;
}

const activityIcon = {
    media_added: '＋', media_interacted: '★', availability: '↗', rental: '⇩', notification: '•',
};

function DashboardSkeleton({ isDarkMode }) {
    return <div className="space-y-10" aria-label="Chargement du dashboard">
        {[['CONTINUER', 'Continuer à regarder'], ['POUR VOUS', 'Pour vous']].map(([eyebrow, title]) => <section key={title}><SectionHeading eyebrow={eyebrow} title={title} isDarkMode={isDarkMode} /><div className="grid gap-4 md:grid-cols-2"><div className="h-52 animate-pulse rounded-2xl bg-current/10" /><div className="hidden h-52 animate-pulse rounded-2xl bg-current/10 md:block" /></div></section>)}
    </div>;
}

export default function DashboardHome({
    data, isDarkMode, loading, error, onRetry, onOpenMedia, onResume,
    onAddWatchlist, onWhyRecommendation, onOpenLibrary, onOpenRecommendations,
}) {
    if (loading && !data) return <DashboardSkeleton isDarkMode={isDarkMode} />;
    if (error && !data) return <div className={`rounded-2xl border p-10 text-center ${panelClass(isDarkMode)}`}><p className="text-sm">{error}</p><button type="button" onClick={onRetry} className="mt-4 rounded-lg bg-[#635bff] px-4 py-2 text-xs font-semibold text-white">Réessayer</button></div>;

    const dashboard = data || {continue_watching: [], recommendations: [], activity: [], availability: []};
    const continueWatching = dashboard.continue_watching || [];
    const recommendations = dashboard.recommendations || [];
    const activity = dashboard.activity || [];
    const availability = dashboard.availability || [];
    return <div className="series-portal space-y-12">
        <section>
            <SectionHeading eyebrow="REPRENDRE" title="Continuer à regarder" action="Voir ma bibliothèque" onAction={onOpenLibrary} isDarkMode={isDarkMode} />
            {continueWatching.length ? <div className="grid gap-4 md:grid-cols-2">{continueWatching.map((item) => <ContinueCard key={`${item.jellyfin_id}-${item.media_id || item.title}`} item={item} isDarkMode={isDarkMode} onOpenMedia={onOpenMedia} onResume={onResume} />)}</div> : <div className={`rounded-2xl border p-8 ${panelClass(isDarkMode)}`}><p className="text-sm font-semibold">Aucun programme en cours.</p><p className="mt-1 text-xs opacity-60">Commence un film ou une série depuis ta bibliothèque, et ta reprise apparaîtra ici.</p><button type="button" onClick={onOpenLibrary} className="mt-4 rounded-lg border border-[#635bff]/40 px-3 py-2 text-xs font-semibold text-[#635bff]">Explorer la bibliothèque</button></div>}
        </section>

        <section>
            <SectionHeading eyebrow="SÉLECTION PERSONNELLE" title="Pour vous" action="Choisir un film" onAction={onOpenRecommendations} isDarkMode={isDarkMode} />
            {recommendations.length ? <div className="dashboard-scroll flex gap-4 overflow-x-auto pb-3" aria-label="Recommandations personnalisées">{recommendations.map((item) => <RecommendationCard key={item.tmdb_id} item={item} isDarkMode={isDarkMode} onOpenMedia={onOpenMedia} onAddWatchlist={onAddWatchlist} onWhyRecommendation={onWhyRecommendation} />)}</div> : <div className={`rounded-2xl border p-8 ${panelClass(isDarkMode)}`}><p className="text-sm font-semibold">Les recommandations seront disponibles dès que TMDB sera connecté.</p><p className="mt-1 text-xs opacity-60">Tu peux déjà parcourir ta bibliothèque ou lancer une sélection personnalisée.</p></div>}
        </section>

        <section>
            <SectionHeading eyebrow="VOTRE ESPACE" title="Mon activité récente et ma bibliothèque" action="Ouvrir la bibliothèque" onAction={onOpenLibrary} isDarkMode={isDarkMode} />
            <div className="grid gap-5 lg:grid-cols-[1.35fr_1fr]">
                <div className={`rounded-2xl border p-5 ${panelClass(isDarkMode)}`}>
                    <h3 className="text-sm font-semibold">Activité récente</h3>
                    {activity.length ? <div className="mt-4 divide-y divide-current/10">{activity.map((item) => <button type="button" key={item.id} onClick={() => item.media_id && onOpenMedia({id: item.media_id})} className="flex w-full items-center gap-3 py-3 text-left first:pt-0 last:pb-0 hover:text-[#635bff]"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#635bff]/10 text-sm font-semibold text-[#635bff]">{activityIcon[item.kind] || '•'}</span><span className="min-w-0 flex-1"><span className="block truncate text-xs font-semibold">{item.title}</span><span className="mt-0.5 block truncate text-[11px] opacity-55">{item.label}</span></span><span className="shrink-0 text-[10px] opacity-45">{dateLabel(item.created_at)}</span></button>)}</div> : <p className="mt-4 text-xs opacity-60">Ton activité apparaîtra ici au fil de tes actions.</p>}
                </div>
                <div className={`rounded-2xl border p-5 ${panelClass(isDarkMode)}`}>
                    <h3 className="text-sm font-semibold">Disponibilité et téléchargements</h3>
                    {availability.length ? <div className="mt-4 space-y-3">{availability.map((item) => <div key={item.media_id} className="flex items-center gap-3"><div className="h-11 w-8 shrink-0 overflow-hidden rounded bg-slate-800">{item.poster && <img src={item.poster} alt="" className="h-full w-full object-cover" />}</div><div className="min-w-0 flex-1"><p className="truncate text-xs font-semibold">{item.title}</p><p className={`mt-0.5 text-[10px] ${item.state === 'error' ? 'text-rose-500' : item.state === 'available' ? 'text-emerald-500' : 'text-[#635bff]'}`}>{item.status_label}{item.progress_percent !== null && item.progress_percent !== undefined ? ` · ${item.progress_percent}%` : ''}</p>{item.last_error && <p className="truncate text-[10px] text-rose-500">{item.last_error}</p>}</div></div>)}</div> : <p className="mt-4 text-xs opacity-60">Aucun téléchargement ou demande en cours.</p>}
                </div>
            </div>
        </section>
    </div>;
}
