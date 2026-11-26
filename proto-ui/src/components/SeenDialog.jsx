import { useState } from 'react';
import { createPortal } from 'react-dom';
import useLayer from '../useLayer';
import { formatStars, todayIsoDate } from '../journal';

const HALF_STEPS = [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5];

/**
 * « Vu » dialog: date (today by default, can be cleared → date inconnue),
 * half-star rating, review and « Vu au cinéma ». Shared by the library, the
 * journal and the lists.
 */
export default function SeenDialog({ movie, initial = null, isDarkMode, onSave, onClose }) {
    const layerRef = useLayer(true, onClose);
    const today = todayIsoDate();
    const [watchedOn, setWatchedOn] = useState(initial ? (initial.watched_on || '') : today);
    const [rating, setRating] = useState(initial?.rating ?? null);
    const [review, setReview] = useState(initial?.review || '');
    const [inCinema, setInCinema] = useState(Boolean(initial?.in_cinema));
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);

    const submit = async (event) => {
        event.preventDefault();
        setBusy(true);
        setError(null);
        try {
            await onSave({
                watched_on: watchedOn || null,
                rating,
                review: review.trim() || null,
                in_cinema: inCinema,
            });
        } catch (saveError) {
            setError(saveError?.message || 'Enregistrement impossible.');
            setBusy(false);
        }
    };

    const field = isDarkMode ? 'border-white/15 bg-black text-white' : 'border-[#e3e8ee] bg-white text-[#0a2540]';
    // Portal: the journal and lists live inside <main>, whose stacking
    // context would otherwise keep the sticky header above the dialog.
    return createPortal(<div
        ref={layerRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={`Vu : ${movie.title}`}
        className="fixed inset-0 z-[60] flex items-end justify-center bg-black/60 p-3 outline-none backdrop-blur-sm sm:items-center"
        onClick={onClose}
    >
        <form
            onSubmit={submit}
            onClick={(event) => event.stopPropagation()}
            className={`w-full max-w-md rounded-2xl border p-5 shadow-2xl ${isDarkMode ? 'border-white/10 bg-[#0a0a0a] text-white' : 'border-[#e3e8ee] bg-white text-[#0a2540]'}`}
        >
            <div className="flex items-center gap-3">
                {movie.posterUrl && <img src={movie.posterUrl} alt="" className="h-16 w-11 rounded object-cover" />}
                <div className="min-w-0">
                    <div className="text-xs font-mono font-bold uppercase tracking-wider text-[#635bff]">{initial ? 'Modifier' : 'Vu'}</div>
                    <h2 className="truncate font-serif text-lg font-bold">{movie.title}</h2>
                </div>
            </div>

            <label className="mt-4 block text-sm font-semibold">
                Date
                <div className="mt-1 flex gap-2">
                    <input type="date" value={watchedOn} max={today} onChange={(event) => setWatchedOn(event.target.value)} className={`min-w-0 flex-1 rounded-lg border px-3 py-2 ${field}`} />
                    {watchedOn && <button type="button" onClick={() => setWatchedOn('')} className="rounded-lg px-2 text-xs underline opacity-70">Date inconnue</button>}
                </div>
            </label>

            <fieldset className="mt-4">
                <legend className="text-sm font-semibold">Note {rating != null && <span className="ml-1 text-amber-400">{formatStars(rating)} · {String(rating).replace('.', ',')} / 5</span>}</legend>
                <div className="mt-1 flex flex-wrap gap-1" role="group" aria-label="Note">
                    {HALF_STEPS.map((step) => <button
                        key={step}
                        type="button"
                        aria-pressed={rating === step}
                        onClick={() => setRating(rating === step ? null : step)}
                        className={`h-9 min-w-9 rounded-lg border px-2 text-xs font-bold ${rating != null && step <= rating ? 'border-amber-400 bg-amber-400/20 text-amber-500' : isDarkMode ? 'border-white/15 text-white/70' : 'border-[#e3e8ee] text-[#425466]'}`}
                    >{String(step).replace('.', ',')}</button>)}
                    {rating != null && <button type="button" onClick={() => setRating(null)} className="px-2 text-xs underline opacity-70">Sans note</button>}
                </div>
            </fieldset>

            <label className="mt-4 block text-sm font-semibold">
                Critique
                <textarea value={review} onChange={(event) => setReview(event.target.value)} rows={3} maxLength={4000} className={`mt-1 w-full rounded-lg border px-3 py-2 font-normal ${field}`} placeholder="Facultatif" />
            </label>

            <label className="mt-3 flex items-center gap-2 text-sm font-semibold">
                <input type="checkbox" checked={inCinema} onChange={(event) => setInCinema(event.target.checked)} className="h-4 w-4 accent-[#635bff]" />
                Vu au cinéma
            </label>

            {error && <p role="alert" className="mt-3 text-sm text-rose-500">{error}</p>}

            <div className="mt-5 flex justify-end gap-2">
                <button type="button" onClick={onClose} className="rounded-lg px-3 py-2 text-sm font-semibold">Annuler</button>
                <button type="submit" disabled={busy} className="rounded-lg bg-[#635bff] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? 'Enregistrement…' : 'Enregistrer'}</button>
            </div>
        </form>
    </div>, document.body);
}
