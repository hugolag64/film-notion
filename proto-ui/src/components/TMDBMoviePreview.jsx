function panelClass(isDarkMode) {
    return isDarkMode
        ? 'border-white/10 bg-[#0a0a0a] text-white'
        : 'border-[#e3e8ee] bg-white text-[#0a2540]';
}

export default function TMDBMoviePreview({
    movie, recommendation, isDarkMode, loading, error, watchlistBusy, requestBusy, onClose, onAddWatchlist, onRequestSeerr,
}) {
    return <div
        className="fixed inset-0 z-[70] flex items-center justify-center bg-black/75 p-3 backdrop-blur-md sm:p-6"
        onClick={onClose}
        role="dialog"
        aria-modal="true"
        aria-label={movie?.title ? `Fiche TMDB de ${movie.title}` : 'Fiche TMDB'}
    >
        <section
            className={`flex max-h-[92vh] w-full max-w-4xl flex-col overflow-y-auto rounded-2xl border shadow-2xl ${panelClass(isDarkMode)}`}
            onClick={(event) => event.stopPropagation()}
        >
            <div className="relative min-h-56 shrink-0 overflow-hidden bg-slate-950 sm:min-h-72">
                {movie?.backdrop_url && <img src={movie.backdrop_url} alt="" className="absolute inset-0 h-full w-full object-cover opacity-50" />}
                <div className="absolute inset-0 bg-gradient-to-t from-black via-black/45 to-transparent" />
                <button type="button" onClick={onClose} className="absolute right-4 top-4 z-10 rounded-full bg-black/60 px-3 py-2 text-xs text-white">✕</button>
                <div className="absolute bottom-5 left-5 right-5 flex items-end gap-4 text-white sm:left-8 sm:right-8">
                    {movie?.poster_url && <img src={movie.poster_url} alt={`Affiche de ${movie.title}`} className="hidden h-32 w-22 rounded-lg object-cover shadow-xl sm:block" />}
                    <div className="min-w-0">
                        <span className="rounded bg-[#01b4e4] px-2 py-1 text-[10px] font-mono font-bold">TMDB</span>
                        <h2 className="mt-2 text-2xl font-serif font-bold sm:text-4xl">{loading ? 'Chargement…' : movie?.title || 'Fiche indisponible'}</h2>
                        {movie && <p className="mt-1 text-xs text-white/75">{movie.release_date?.slice(0, 4) || '—'} · {movie.runtime ? `${movie.runtime} min` : 'Durée inconnue'}</p>}
                    </div>
                </div>
            </div>

            {loading && <p className="p-8 text-center text-sm opacity-60">Récupération des détails TMDB…</p>}
            {error && <div className="p-8 text-center"><p className="text-sm text-rose-500">{error}</p><button type="button" onClick={onClose} className="mt-4 rounded-lg border px-3 py-2 text-xs font-semibold">Fermer</button></div>}
            {!loading && !error && movie && <div className="space-y-5 p-5 sm:p-8">
                <div className="flex flex-wrap items-center gap-3">
                    <span className="rounded-full bg-[#01b4e4]/10 px-3 py-1.5 text-sm font-bold text-[#01b4e4]">★ {typeof movie.vote_average === 'number' ? movie.vote_average.toFixed(1) : '—'} / 10</span>
                    <span className="text-xs opacity-55">{movie.vote_count ? `${movie.vote_count.toLocaleString('fr-FR')} votes utilisateurs` : 'Votes indisponibles'}</span>
                    {movie.genres?.map((genre) => <span key={genre} className="rounded-full border border-current/10 px-2.5 py-1 text-[11px] opacity-70">{genre}</span>)}
                </div>

                <div className="grid gap-5 md:grid-cols-[1fr_220px]">
                    <div>
                        <p className="text-[10px] font-mono font-bold uppercase tracking-[0.2em] text-[#635bff]">Synopsis</p>
                        <p className="mt-2 text-sm leading-6 opacity-80">{movie.overview || 'Aucun synopsis disponible.'}</p>
                        <div className="mt-5 grid gap-3 text-xs sm:grid-cols-2">
                            <div><span className="block opacity-50">Réalisateur</span><strong>{movie.director || '—'}</strong></div>
                            <div><span className="block opacity-50">Titre original</span><strong>{movie.original_title || movie.title}</strong></div>
                        </div>
                    </div>
                    <div>
                        <p className="text-[10px] font-mono font-bold uppercase tracking-[0.2em] text-[#635bff]">Casting</p>
                        <ul className="mt-2 space-y-1.5 text-xs opacity-80">{(movie.cast || []).map((actor) => <li key={actor}>• {actor}</li>)}</ul>
                    </div>
                </div>

                <div className="flex flex-wrap justify-end gap-2 border-t border-current/10 pt-5">
                    <button type="button" onClick={onClose} className="rounded-lg border border-current/15 px-4 py-2 text-xs font-semibold">Fermer</button>
                    <button type="button" onClick={() => onAddWatchlist(recommendation)} disabled={watchlistBusy} className="rounded-lg border border-[#635bff]/40 px-4 py-2 text-xs font-semibold text-[#635bff] disabled:opacity-50">
                        {watchlistBusy ? 'Ajout…' : 'Ajouter à ma watchlist'}
                    </button>
                    <button type="button" onClick={() => onRequestSeerr(recommendation)} disabled={requestBusy} className="rounded-lg bg-[#635bff] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">
                        {requestBusy ? 'Demande…' : 'Demander à Seerr'}
                    </button>
                </div>
            </div>}
        </section>
    </div>;
}
