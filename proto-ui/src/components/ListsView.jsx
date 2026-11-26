import { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import {
    addFilmListItem, createFilmList, createJournalEntry, deleteFilmList, fetchFilmList, fetchFilmLists,
    removeFilmListItem, renameFilmList, searchTMDB,
} from '../api';
import { BADGE_TONE_CLASSES, listItemBadge, shouldOfferSeerrRequest } from '../journal';
import useLayer from '../useLayer';
import SeenDialog from './SeenDialog';
import TMDBSearchBox from './TMDBSearchBox';

function SeerrOfferDialog({ film, isDarkMode, onAnswer }) {
    const layerRef = useLayer(true, () => onAnswer(false));
    return createPortal(<div
        ref={layerRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="seerr-offer-title"
        className="fixed inset-0 z-[60] flex items-end justify-center bg-black/60 p-3 outline-none backdrop-blur-sm sm:items-center"
        onClick={() => onAnswer(false)}
    >
        <div onClick={(event) => event.stopPropagation()} className={`w-full max-w-sm rounded-2xl border p-5 shadow-2xl ${isDarkMode ? 'border-white/10 bg-[#0a0a0a] text-white' : 'border-[#e3e8ee] bg-white text-[#0a2540]'}`}>
            <h2 id="seerr-offer-title" className="font-serif text-lg font-bold">Demander aussi sur le serveur ?</h2>
            <p className={`mt-2 text-sm ${isDarkMode ? 'text-white/70' : 'text-[#425466]'}`}>
                « {film.title} » n’est pas sur le serveur. Le demander l’ajoutera à la bibliothèque dès qu’il sera disponible. Il reste dans la liste dans tous les cas.
            </p>
            <div className="mt-5 flex justify-end gap-2">
                <button type="button" onClick={() => onAnswer(false)} className="rounded-lg px-3 py-2 text-sm font-semibold">Non</button>
                <button type="button" onClick={() => onAnswer(true)} className="rounded-lg bg-[#635bff] px-4 py-2 text-sm font-semibold text-white">Oui, le demander</button>
            </div>
        </div>
    </div>, document.body);
}

/** Shared film lists: every flatmate can create, rename, fill and empty them. */
export default function ListsView({ isDarkMode, showToast, onRequestOnServer, onJournalChanged }) {
    const [lists, setLists] = useState(null);
    const [openId, setOpenId] = useState(null);
    const [detail, setDetail] = useState(null);
    const [newName, setNewName] = useState('');
    const [error, setError] = useState(null);
    const [seerrOffer, setSeerrOffer] = useState(null);
    const [seenMovie, setSeenMovie] = useState(null);

    const loadLists = useCallback(async () => {
        try {
            setLists(await fetchFilmLists());
            setError(null);
        } catch (loadError) {
            setError(loadError.message);
        }
    }, []);

    const loadDetail = useCallback(async (listId) => {
        try {
            setDetail(await fetchFilmList(listId));
            setError(null);
        } catch (loadError) {
            if (loadError.status === 404) {
                showToast('Cette liste a été supprimée.', 'info');
                setOpenId(null);
                loadLists();
                return;
            }
            setError(loadError.message);
        }
    }, [loadLists, showToast]);

    useEffect(() => { loadLists(); }, [loadLists]);
    useEffect(() => {
        setDetail(null);
        if (openId) loadDetail(openId);
    }, [openId, loadDetail]);

    const run = async (action) => {
        try {
            await action();
        } catch (actionError) {
            showToast(actionError.message, 'error');
        }
    };

    const create = (event) => {
        event.preventDefault();
        run(async () => {
            const created = await createFilmList(newName);
            setNewName('');
            await loadLists();
            setOpenId(created.id);
        });
    };

    const rename = () => {
        const name = window.prompt('Nouveau nom de la liste', detail.name);
        if (name == null || name.trim() === detail.name) return;
        run(async () => {
            await renameFilmList(detail.id, name);
            await loadDetail(detail.id);
        });
    };

    const remove = () => {
        if (!window.confirm(`Supprimer la liste « ${detail.name} » pour tous les colocs ?`)) return;
        run(async () => {
            await deleteFilmList(detail.id);
            setOpenId(null);
            await loadLists();
        });
    };

    const addFilm = (result) => run(async () => {
        const added = await addFilmListItem(detail.id, result.tmdb_id);
        await loadDetail(detail.id);
        if (!added.added) {
            showToast('Déjà dans la liste.', 'info');
            return;
        }
        if (shouldOfferSeerrRequest(added)) setSeerrOffer({ tmdb_id: result.tmdb_id, title: added.item.title });
    });

    const answerSeerrOffer = async (yes) => {
        const film = seerrOffer;
        setSeerrOffer(null);
        if (!yes) return;
        await run(async () => {
            await onRequestOnServer(film);
            await loadDetail(detail.id);
        });
    };

    const saveSeen = async (payload) => {
        await createJournalEntry({ tmdb_id: seenMovie.tmdbId, ...payload });
        showToast(`« ${seenMovie.title} » ajouté à ton journal.`);
        setSeenMovie(null);
        await loadDetail(detail.id);
        onJournalChanged?.();
    };

    const removeFilm = (item) => run(async () => {
        await removeFilmListItem(detail.id, item.tmdb_id);
        await loadDetail(detail.id);
    });

    const muted = isDarkMode ? 'text-white/60' : 'text-[#425466]';
    const title = isDarkMode ? 'text-white' : 'text-[#0a2540]';
    const card = isDarkMode ? 'border-white/10 bg-[#0a0a0a]' : 'border-[#e3e8ee] bg-white';

    if (openId) {
        return <section aria-labelledby="list-title">
            <button type="button" onClick={() => { setOpenId(null); loadLists(); }} className="text-sm font-semibold text-[#635bff]">← Toutes les listes</button>
            {error && <p role="alert" className="mt-4 text-sm text-rose-500">{error}</p>}
            {!detail && !error && <p className={`mt-4 text-sm ${muted}`}>Chargement…</p>}
            {detail && <>
                <div className={`mb-6 mt-3 flex flex-wrap items-end justify-between gap-3 border-b pb-4 ${isDarkMode ? 'border-white/10' : 'border-[#e3e8ee]'}`}>
                    <div>
                        <span className="text-xs font-mono font-bold uppercase tracking-widest text-[#635bff]">Liste partagée · {detail.items.length} film{detail.items.length > 1 ? 's' : ''}</span>
                        <h1 id="list-title" className={`mt-1 font-serif text-3xl font-bold tracking-tight ${title}`}>{detail.name}</h1>
                    </div>
                    <div className="flex gap-2 text-sm font-semibold">
                        <button type="button" onClick={rename} className="rounded-lg px-3 py-1.5 text-[#635bff] hover:bg-[#635bff]/10">Renommer</button>
                        <button type="button" onClick={remove} className="rounded-lg px-3 py-1.5 text-rose-500 hover:bg-rose-500/10">Supprimer</button>
                    </div>
                </div>
                <TMDBSearchBox isDarkMode={isDarkMode} search={searchTMDB} placeholder="Ajouter un film à la liste…" actionLabel="Ajouter" onPick={addFilm} />
                {detail.items.length === 0 && <p className={`mt-6 text-sm ${muted}`}>Aucun film pour l’instant. Cherche un film ci-dessus pour l’ajouter.</p>}
                <ul className="mt-6 grid gap-3 sm:grid-cols-2">
                    {detail.items.map((item) => {
                        const badge = listItemBadge(item);
                        return <li key={item.tmdb_id} className={`flex gap-3 rounded-xl border p-3 ${card}`}>
                            {item.poster_url
                                ? <img src={item.poster_url} alt="" className="h-24 w-16 shrink-0 rounded object-cover" loading="lazy" />
                                : <div className="h-24 w-16 shrink-0 rounded bg-black/10 dark:bg-white/10" />}
                            <div className="flex min-w-0 flex-1 flex-col">
                                <div className={`font-semibold ${title}`}>{item.title} {item.year && <span className={`text-xs font-normal ${muted}`}>{item.year}</span>}</div>
                                <div className="mt-1 flex flex-wrap items-center gap-2">
                                    {badge && <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-mono font-bold text-white ${BADGE_TONE_CLASSES[badge.tone]}`}>{badge.label}</span>}
                                    {item.seen_by_me && <span className="text-xs font-semibold text-emerald-500">✓ Vu</span>}
                                </div>
                                <div className={`mt-1 text-xs ${muted}`}>ajouté par {item.added_by_me ? 'toi' : item.added_by_name}</div>
                                <div className="mt-auto flex gap-1 pt-2 text-xs font-semibold">
                                    <button type="button" onClick={() => setSeenMovie({ tmdbId: item.tmdb_id, title: item.title, posterUrl: item.poster_url })} className="rounded px-2 py-1 text-[#635bff] hover:bg-[#635bff]/10">Vu</button>
                                    <button type="button" onClick={() => removeFilm(item)} className="rounded px-2 py-1 text-rose-500 hover:bg-rose-500/10">Retirer</button>
                                </div>
                            </div>
                        </li>;
                    })}
                </ul>
            </>}
            {seerrOffer && <SeerrOfferDialog film={seerrOffer} isDarkMode={isDarkMode} onAnswer={answerSeerrOffer} />}
            {seenMovie && <SeenDialog movie={seenMovie} isDarkMode={isDarkMode} onSave={saveSeen} onClose={() => setSeenMovie(null)} />}
        </section>;
    }

    return <section aria-labelledby="lists-title">
        <div className={`mb-6 border-b pb-4 ${isDarkMode ? 'border-white/10' : 'border-[#e3e8ee]'}`}>
            <span className="text-xs font-mono font-bold uppercase tracking-widest text-[#635bff]">Entre colocs</span>
            <h1 id="lists-title" className={`mt-1 font-serif text-3xl font-bold tracking-tight ${title}`}>Listes</h1>
            <p className={`mt-1 text-sm ${muted}`}>Des listes de films communes, même hors de la bibliothèque. Tout le monde peut les modifier.</p>
        </div>
        <form onSubmit={create} className="flex gap-2">
            <input value={newName} onChange={(event) => setNewName(event.target.value)} maxLength={60} placeholder="Nouvelle liste (ex. Films à voir au ciné)" aria-label="Nom de la nouvelle liste" className={`min-w-0 flex-1 rounded-xl border px-4 py-2.5 text-sm outline-none focus:border-[#635bff] ${isDarkMode ? 'border-white/15 bg-black text-white placeholder:text-white/40' : 'border-[#e3e8ee] bg-white text-[#0a2540]'}`} />
            <button type="submit" disabled={!newName.trim()} className="shrink-0 rounded-xl bg-[#635bff] px-4 text-sm font-semibold text-white disabled:opacity-50">Créer</button>
        </form>
        {error && <p role="alert" className="mt-6 text-sm text-rose-500">{error} <button type="button" onClick={loadLists} className="underline">Réessayer</button></p>}
        {lists === null && !error && <p className={`mt-6 text-sm ${muted}`}>Chargement…</p>}
        {lists?.length === 0 && <p className={`mt-6 text-sm ${muted}`}>Aucune liste pour l’instant.</p>}
        <ul className="mt-6 grid gap-3 sm:grid-cols-2">
            {(lists || []).map((filmList) => <li key={filmList.id}>
                <button type="button" onClick={() => setOpenId(filmList.id)} className={`w-full rounded-xl border p-4 text-left transition hover:border-[#635bff] ${card}`}>
                    <div className={`font-semibold ${title}`}>{filmList.name}</div>
                    <div className={`mt-1 text-xs ${muted}`}>{filmList.item_count} film{filmList.item_count > 1 ? 's' : ''} · créée par {filmList.created_by_name}</div>
                </button>
            </li>)}
        </ul>
    </section>;
}
