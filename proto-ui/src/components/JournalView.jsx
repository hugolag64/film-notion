import { useCallback, useEffect, useState } from 'react';
import { createJournalEntry, deleteJournalEntry, fetchJournal, searchTMDB, updateJournalEntry } from '../api';
import { formatStars, groupDiaryByMonth, journalFilmTarget } from '../journal';
import SeenDialog from './SeenDialog';
import TMDBSearchBox from './TMDBSearchBox';

const shortDate = (iso) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}` : null);

/** Private « Vu » journal of the signed-in user. */
export default function JournalView({ isDarkMode, onOpenLibraryFilm, onOpenFilm, onChanged, showToast }) {
    const [entries, setEntries] = useState(null);
    const [error, setError] = useState(null);
    const [dialog, setDialog] = useState(null);

    const load = useCallback(async () => {
        try {
            const data = await fetchJournal();
            setEntries(data.entries);
            setError(null);
        } catch (loadError) {
            setError(loadError.message);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    const save = async (payload) => {
        if (dialog.entry) {
            await updateJournalEntry(dialog.entry.id, payload);
            showToast(`« ${dialog.movie.title} » modifié dans ton journal.`);
        } else {
            await createJournalEntry({ tmdb_id: dialog.movie.tmdbId, ...payload });
            showToast(`« ${dialog.movie.title} » ajouté à ton journal.`);
        }
        setDialog(null);
        await load();
        onChanged?.();
    };

    const remove = async (entry) => {
        if (!window.confirm(`Supprimer « ${entry.movie.title} » de ton journal ?`)) return;
        try {
            await deleteJournalEntry(entry.id);
            await load();
            onChanged?.();
        } catch (removeError) {
            showToast(removeError.message, 'error');
        }
    };

    const muted = isDarkMode ? 'text-white/60' : 'text-[#425466]';
    const openFilm = (entry) => {
        const target = journalFilmTarget(entry);
        if (target.kind === 'library') onOpenLibraryFilm(target.mediaId);
        else onOpenFilm(target.film);
    };

    return <section aria-labelledby="journal-title">
        <div className={`mb-6 border-b pb-4 ${isDarkMode ? 'border-white/10' : 'border-[#e3e8ee]'}`}>
            <span className="text-xs font-mono font-bold uppercase tracking-widest text-[#635bff]">Rien que pour toi</span>
            <h1 id="journal-title" className={`mt-1 font-serif text-3xl font-bold tracking-tight ${isDarkMode ? 'text-white' : 'text-[#0a2540]'}`}>Journal</h1>
            <p className={`mt-1 text-sm ${muted}`}>Tout ce que tu as vu, au cinéma ou ailleurs. Tes colocs ne le voient pas.</p>
        </div>

        <TMDBSearchBox
            isDarkMode={isDarkMode}
            search={searchTMDB}
            placeholder="Ajouter un film vu…"
            actionLabel="Vu"
            onPick={(result) => setDialog({ movie: { tmdbId: result.tmdb_id, title: result.title, posterUrl: result.poster_url } })}
        />

        {error && <p role="alert" className="mt-6 text-sm text-rose-500">{error} <button type="button" onClick={load} className="underline">Réessayer</button></p>}
        {entries === null && !error && <p className={`mt-6 text-sm ${muted}`}>Chargement…</p>}
        {entries?.length === 0 && <p className={`mt-6 text-sm ${muted}`}>Ton journal est vide. Cherche un film ci-dessus ou touche « Vu » sur la fiche d’un film.</p>}

        {groupDiaryByMonth(entries || []).map((group) => <div key={group.key} className="mt-8">
            <h2 className="text-xs font-mono font-bold uppercase tracking-widest text-[#635bff]">{group.label}</h2>
            <ul className="mt-3 divide-y divide-black/5 dark:divide-white/10">
                {group.entries.map((entry) => <li key={entry.id} className="flex items-start gap-3 py-3">
                    <button type="button" onClick={() => openFilm(entry)} className="shrink-0 rounded transition hover:opacity-80 hover:ring-2 hover:ring-[#635bff]" aria-label={`Ouvrir la fiche de ${entry.movie.title}`}>
                        {entry.movie.poster_url
                            ? <img src={entry.movie.poster_url} alt="" className="h-20 w-14 rounded object-cover" loading="lazy" />
                            : <div className="h-20 w-14 rounded bg-black/10 dark:bg-white/10" />}
                    </button>
                    <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-baseline gap-x-2">
                            <button type="button" onClick={() => openFilm(entry)} className={`text-left font-semibold hover:text-[#635bff] ${isDarkMode ? 'text-white' : 'text-[#0a2540]'}`}>{entry.movie.title}</button>
                            {entry.movie.year && <span className={`text-xs ${muted}`}>{entry.movie.year}</span>}
                        </div>
                        <div className={`mt-0.5 flex flex-wrap items-center gap-x-2 text-sm ${muted}`}>
                            {shortDate(entry.watched_on) && <span>{shortDate(entry.watched_on)}</span>}
                            {entry.rating != null && <span className="text-amber-400" aria-label={`${entry.rating} sur 5`}>{formatStars(entry.rating)}</span>}
                            {entry.in_cinema && <span title="Vu au cinéma">🎬 Vu au cinéma</span>}
                        </div>
                        {entry.review && <p className={`mt-1 line-clamp-3 whitespace-pre-line text-sm ${isDarkMode ? 'text-white/80' : 'text-[#0a2540]/80'}`}>{entry.review}</p>}
                    </div>
                    <div className="flex shrink-0 flex-col gap-1 text-xs font-semibold sm:flex-row">
                        <button type="button" onClick={() => setDialog({ entry, movie: { tmdbId: entry.tmdb_id, title: entry.movie.title, posterUrl: entry.movie.poster_url } })} className="rounded px-2 py-1 text-[#635bff] hover:bg-[#635bff]/10">Modifier</button>
                        <button type="button" onClick={() => remove(entry)} className="rounded px-2 py-1 text-rose-500 hover:bg-rose-500/10">Supprimer</button>
                    </div>
                </li>)}
            </ul>
        </div>)}

        {dialog && <SeenDialog movie={dialog.movie} initial={dialog.entry || null} isDarkMode={isDarkMode} onSave={save} onClose={() => setDialog(null)} />}
    </section>;
}
