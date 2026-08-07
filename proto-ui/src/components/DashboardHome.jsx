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
    return <article className={`group w-[calc((100%-60px)/6)] min-w-[230px] shrink-0 snap-start overflow-hidden rounded-xl border ${panelClass(isDarkMode)} shadow-sm transition duration-300 hover:-translate-y-0.5 hover:border-[#635bff]/60 hover:shadow-xl`}>
        <div className="flex min-h-40">
            <div className="relative w-24 shrink-0 overflow-hidden bg-slate-900 sm:w-28">
                {image ? <img src={image} alt={`Affiche de ${media?.title || item.title}`} className="h-full w-full object-cover transition duration-500 group-hover:scale-105" /> : <div className="flex h-full items-center justify-center p-4 text-center text-xs text-white/50">Affiche indisponible</div>}
                <div className="absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-black/75 to-transparent" />
                <span className="absolute bottom-3 left-3 rounded-full bg-black/65 px-2 py-1 text-[10px] font-mono font-bold text-white">{Math.round(item.percent || 0)} %</span>
            </div>
            <div className="flex min-w-0 flex-1 flex-col justify-between p-3">
                <div>
                    <p className="text-[10px] font-mono uppercase tracking-widest opacity-50">À reprendre</p>
                    <h3 className="mt-1 truncate text-sm font-semibold">{media?.title || item.title}</h3>
                    <p className="mt-1 truncate text-xs opacity-60">{episode}</p>
                    {item.last_played_at && <p className="mt-2 text-[10px] opacity-50">Vu le {dateLabel(item.last_played_at)}</p>}
                </div>
                <div className="mt-3">
                    <div className="mb-2 h-1.5 overflow-hidden rounded-full bg-black/10 dark:bg-white/10" aria-label={`${Math.round(item.percent || 0)} % regardé`}>
                        <div className="h-full rounded-full bg-[#635bff]" style={{width: `${Math.min(100, Math.max(0, item.percent || 0))}%`}} />
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                        <button type="button" onClick={() => onResume(item)} className="rounded-md bg-[#635bff] px-2 py-1.5 text-[10px] font-semibold text-white shadow-sm hover:bg-[#5048e5]">Reprendre</button>
                        {media && <button type="button" onClick={() => onOpenMedia(media)} className="rounded-md border border-current/15 px-2 py-1.5 text-[10px] font-semibold opacity-80 hover:border-[#635bff] hover:text-[#635bff]">Voir la fiche</button>}
                    </div>
                </div>
            </div>
        </div>
    </article>;
}

function RecommendationCard({ item, isDarkMode, onOpenDetails, onAddWatchlist, onWhyRecommendation }) {
    const [showWhy, setShowWhy] = useState(false);
    const image = posterUrl(item.poster_path);
    return <article className={`w-52 shrink-0 overflow-hidden rounded-2xl border ${panelClass(isDarkMode)} shadow-sm`}>
        <button type="button" className="group block w-full text-left" onClick={() => onOpenDetails(item)} aria-label={`Voir la fiche de ${item.title}`}>
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
                <button type="button" onClick={() => onOpenDetails(item)} className="rounded-md border border-current/15 px-2 py-1.5 text-[10px] font-semibold hover:border-[#635bff] hover:text-[#635bff]">Voir la fiche</button>
                <button type="button" onClick={() => { setShowWhy((value) => !value); onWhyRecommendation(item); }} className="rounded-md border border-current/15 px-2 py-1.5 text-[10px] font-semibold hover:border-[#635bff] hover:text-[#635bff]">Pourquoi ce film ?</button>
                <button type="button" onClick={() => onAddWatchlist(item)} className="w-full rounded-md bg-[#635bff]/10 px-2 py-1.5 text-[10px] font-semibold text-[#635bff] hover:bg-[#635bff]/20">Ajouter à ma watchlist</button>
            </div>
            {showWhy && <p className="mt-2 rounded-lg bg-[#635bff]/10 p-2 text-[10px] leading-4 text-[#635bff]">{item.explanation || 'Ce film correspond à ton profil de visionnage.'}</p>}
        </div>
    </article>;
}

function RequestCard({ item, isDarkMode, onCancelRequest, cancellingRequest, onOpenRequest }) {
    const progress = item.progress_percent;
    const open = () => onOpenRequest(item);
    return <article role="button" tabIndex={0} onClick={open} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); } }} className={`flex min-w-[280px] shrink-0 cursor-pointer overflow-hidden rounded-xl border ${panelClass(isDarkMode)} shadow-sm transition hover:-translate-y-0.5 hover:border-[#635bff]/60`}>
        <div className="relative h-36 w-24 shrink-0 overflow-hidden bg-slate-900">
            {item.poster_url ? <img src={item.poster_url} alt={`Affiche de ${item.title}`} className="h-full w-full object-cover" /> : <div className="flex h-full items-center justify-center p-3 text-center text-[10px] text-white/50">Affiche indisponible</div>}
        </div>
        <div className="flex min-w-0 flex-1 flex-col justify-between p-3">
            <div>
                <p className="truncate text-sm font-semibold">{item.title}</p>
                <p className="mt-1 text-[11px] font-semibold text-[#635bff]">{item.status_label}</p>
                {progress !== null && progress !== undefined && <div className="mt-2"><div className="h-1.5 overflow-hidden rounded-full bg-black/10 dark:bg-white/10"><div className="h-full rounded-full bg-[#635bff]" style={{width: `${progress}%`}} /></div><p className="mt-1 text-[10px] opacity-55">{progress}%</p></div>}
            </div>
            {item.cancellable && <button type="button" onClick={(event) => { event.stopPropagation(); onCancelRequest(item.id); }} disabled={cancellingRequest === item.id} className="mt-2 self-start rounded-md border border-rose-500/30 px-2 py-1.5 text-[10px] font-semibold text-rose-500 hover:bg-rose-500/10 disabled:opacity-50">{cancellingRequest === item.id ? 'Annulation…' : 'Annuler la demande'}</button>}
        </div>
    </article>;
}

function RequestDetailModal({ item, isDarkMode, onClose, onCancelRequest, cancellingRequest }) {
    return <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/25 p-4" onClick={onClose} role="presentation">
        <section className={`w-full max-w-lg overflow-hidden rounded-2xl border shadow-2xl ${panelClass(isDarkMode)}`} onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={`Détails de la demande ${item.title}`}>
            <div className="flex items-start gap-4 p-5">
                <div className="h-32 w-22 shrink-0 overflow-hidden rounded-lg bg-slate-900">
                    {item.poster_url ? <img src={item.poster_url} alt={`Affiche de ${item.title}`} className="h-full w-full object-cover" /> : <div className="flex h-full items-center justify-center p-3 text-center text-[10px] text-white/50">Affiche indisponible</div>}
                </div>
                <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-3"><div><p className="text-[10px] font-mono uppercase tracking-[0.2em] text-[#635bff]">Demande Seerr</p><h2 className="mt-1 text-xl font-serif font-bold">{item.title}</h2></div><button type="button" onClick={onClose} className="rounded-full border border-current/10 px-2.5 py-1 text-xs opacity-70 hover:opacity-100" aria-label="Fermer">×</button></div>
                    <p className="mt-3 text-sm font-semibold text-[#635bff]">{item.status_label}</p>
                    {item.progress_percent !== null && item.progress_percent !== undefined && <><div className="mt-3 h-2 overflow-hidden rounded-full bg-black/10 dark:bg-white/10"><div className="h-full rounded-full bg-[#635bff]" style={{width: `${item.progress_percent}%`}} /></div><p className="mt-1 text-[11px] opacity-55">{item.progress_percent}%</p></>}
                </div>
            </div>
            <div className="flex justify-end gap-2 border-t border-current/10 px-5 py-4">
                {item.cancellable && <button type="button" onClick={() => onCancelRequest(item.id)} disabled={cancellingRequest === item.id} className="rounded-lg border border-rose-500/30 px-3 py-2 text-xs font-semibold text-rose-500 disabled:opacity-50">{cancellingRequest === item.id ? 'Annulation…' : 'Annuler la demande'}</button>}
                <button type="button" onClick={onClose} className="rounded-lg bg-[#635bff] px-3 py-2 text-xs font-semibold text-white">Fermer</button>
            </div>
        </section>
    </div>;
}

function RequestsManagerModal({ requests, isDarkMode, onClose, onDeleteRequest, cancellingRequest }) {
    return <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose} role="presentation">
        <section className={`w-full max-w-2xl overflow-hidden rounded-2xl border shadow-2xl ${panelClass(isDarkMode)}`} onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Gérer les demandes">
            <div className="flex items-center justify-between border-b border-current/10 px-5 py-4"><div><p className="text-[10px] font-mono uppercase tracking-[0.2em] text-[#635bff]">File Seerr</p><h2 className="mt-1 text-xl font-serif font-bold">Mes demandes</h2></div><button type="button" onClick={onClose} className="rounded-full border border-current/10 px-2.5 py-1 text-xs opacity-70 hover:opacity-100" aria-label="Fermer">×</button></div>
            <div className="max-h-[65vh] overflow-y-auto p-3">
                {requests.length ? <div className="divide-y divide-current/10">{requests.map((item) => <div key={item.id} className="flex items-center gap-3 px-2 py-3"><div className="h-14 w-10 shrink-0 overflow-hidden rounded bg-slate-900">{item.poster_url && <img src={item.poster_url} alt="" className="h-full w-full object-cover" />}</div><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{item.title}</p><p className="mt-1 text-[11px] opacity-55">Date : {dateLabel(item.updated_at || item.created_at) || '—'} · {item.media_type === 'tv' ? 'Série' : 'Film'}</p></div><span className="shrink-0 rounded-full bg-[#635bff]/10 px-2 py-1 text-[11px] font-semibold text-[#635bff]">{item.status_label}</span><button type="button" onClick={() => onDeleteRequest(item.id)} disabled={cancellingRequest === item.id} className="shrink-0 rounded-lg border border-rose-500/30 px-2.5 py-1.5 text-[10px] font-semibold text-rose-500 disabled:opacity-50">{cancellingRequest === item.id ? '…' : 'Supprimer'}</button></div>)}</div> : <p className="p-8 text-center text-sm opacity-60">Aucune demande active.</p>}
            </div>
        </section>
    </div>;
}

const activityIcon = {
    media_added: '＋', media_interacted: '★', availability: '↗', rental: '⇩', notification: '•',
};

function DashboardSkeleton({ isDarkMode }) {
    return <div className="space-y-10" aria-label="Chargement du dashboard">
        {[['CONTINUER', 'Continuer à regarder'], ['POUR VOUS', 'Pour vous']].map(([eyebrow, title]) => <section key={title}><SectionHeading eyebrow={eyebrow} title={title} isDarkMode={isDarkMode} /><div className="flex gap-3 overflow-hidden"><div className="h-40 min-w-[230px] flex-1 animate-pulse rounded-xl bg-current/10" /><div className="hidden h-40 min-w-[230px] flex-1 animate-pulse rounded-xl bg-current/10 sm:block" /></div></section>)}
    </div>;
}

export default function DashboardHome({
    data, isDarkMode, loading, error, onRetry, onOpenMedia, onResume,
    onAddWatchlist, onWhyRecommendation, onOpenLibrary, onOpenRecommendations, onOpenTMDBDetails,
    onCancelRequest, cancellingRequest,
}) {
    const [selectedRequest, setSelectedRequest] = useState(null);
    const [showRequestsManager, setShowRequestsManager] = useState(false);
    if (loading && !data) return <DashboardSkeleton isDarkMode={isDarkMode} />;
    if (error && !data) return <div className={`rounded-2xl border p-10 text-center ${panelClass(isDarkMode)}`}><p className="text-sm">{error}</p><button type="button" onClick={onRetry} className="mt-4 rounded-lg bg-[#635bff] px-4 py-2 text-xs font-semibold text-white">Réessayer</button></div>;

    const dashboard = data || {continue_watching: [], recommendations: [], activity: [], availability: []};
    const continueWatching = dashboard.continue_watching || [];
    const recommendations = dashboard.recommendations || [];
    const requests = dashboard.requests || [];
    const activity = dashboard.activity || [];
    const availability = dashboard.availability || [];
    return <div className="series-portal space-y-12">
        <section>
            <SectionHeading eyebrow="REPRENDRE" title="Continuer à regarder" action="Voir ma bibliothèque" onAction={onOpenLibrary} isDarkMode={isDarkMode} />
            {continueWatching.length ? <div className="flex gap-3 overflow-x-auto pb-3 snap-x snap-mandatory" aria-label="Reprises en cours">{continueWatching.map((item) => <ContinueCard key={`${item.jellyfin_id}-${item.media_id || item.title}`} item={item} isDarkMode={isDarkMode} onOpenMedia={onOpenMedia} onResume={onResume} />)}</div> : <div className={`rounded-2xl border p-8 ${panelClass(isDarkMode)}`}><p className="text-sm font-semibold">Aucun programme en cours.</p><p className="mt-1 text-xs opacity-60">Commence un film ou une série depuis ta bibliothèque, et ta reprise apparaîtra ici.</p><button type="button" onClick={onOpenLibrary} className="mt-4 rounded-lg border border-[#635bff]/40 px-3 py-2 text-xs font-semibold text-[#635bff]">Explorer la bibliothèque</button></div>}
        </section>

        <section>
            <SectionHeading eyebrow="TÉLÉCHARGEMENTS" title="Mes demandes" action="Gérer les demandes" onAction={() => setShowRequestsManager(true)} isDarkMode={isDarkMode} />
            {requests.length ? <div className="flex gap-3 overflow-x-auto pb-3" aria-label="Mes demandes Seerr">{requests.map((item) => <RequestCard key={item.id} item={item} isDarkMode={isDarkMode} onCancelRequest={onCancelRequest} cancellingRequest={cancellingRequest} onOpenRequest={setSelectedRequest} />)}</div> : <div className={`rounded-2xl border p-6 ${panelClass(isDarkMode)}`}><p className="text-sm font-semibold">Aucune demande en cours.</p><p className="mt-1 text-xs opacity-60">Ouvre la fiche d’un film et demande-le à Seerr pour le retrouver ici.</p></div>}
        </section>

        <section>
            <SectionHeading eyebrow="SÉLECTION PERSONNELLE" title="Pour vous" action="Choisir un film" onAction={onOpenRecommendations} isDarkMode={isDarkMode} />
            {recommendations.length ? <div className="dashboard-scroll flex gap-4 overflow-x-auto pb-3" aria-label="Recommandations personnalisées">{recommendations.map((item) => <RecommendationCard key={item.tmdb_id} item={item} isDarkMode={isDarkMode} onOpenDetails={onOpenTMDBDetails} onAddWatchlist={onAddWatchlist} onWhyRecommendation={onWhyRecommendation} />)}</div> : <div className={`rounded-2xl border p-8 ${panelClass(isDarkMode)}`}><p className="text-sm font-semibold">Les recommandations seront disponibles dès que TMDB sera connecté.</p><p className="mt-1 text-xs opacity-60">Tu peux déjà parcourir ta bibliothèque ou lancer une sélection personnalisée.</p></div>}
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
        {selectedRequest && <RequestDetailModal item={selectedRequest} isDarkMode={isDarkMode} onClose={() => setSelectedRequest(null)} onCancelRequest={onCancelRequest} cancellingRequest={cancellingRequest} />}
        {showRequestsManager && <RequestsManagerModal requests={requests} isDarkMode={isDarkMode} onClose={() => setShowRequestsManager(false)} onDeleteRequest={onCancelRequest} cancellingRequest={cancellingRequest} />}
    </div>;
}
