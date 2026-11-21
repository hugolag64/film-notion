import { useCallback, useEffect, useRef, useState } from 'react';
import { answerRecommendation, confirmRecommendation, recordRecommendationEvent, startRecommendationSession } from '../api';

const primaryButton = 'rounded-lg bg-[#635bff] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50';
const secondaryButton = 'rounded-lg border border-current/20 px-4 py-2 text-sm font-semibold disabled:opacity-50';

function FilmCard({ film, isDarkMode, onRequest, confirming, busy, requested, error, onPick, onPlay }) {
    const [ask, setAsk] = useState(false);
    const image = film.poster_path && `https://image.tmdb.org/t/p/w342${film.poster_path}`;

    return (
        <article className={`flex h-full flex-col overflow-hidden rounded-xl border ${isDarkMode ? 'border-white/15 bg-white/[0.04]' : 'border-[#e3e8ee] bg-white'}`}>
            <div className="flex flex-1 gap-3 p-3">
                <div className="h-[108px] w-[72px] shrink-0 overflow-hidden rounded-md bg-slate-500/15">
                    {image && <img src={image} alt="" loading="lazy" className="h-full w-full object-cover" />}
                </div>
                <div className="min-w-0">
                    <h4 className="break-words font-semibold leading-snug">{film.title}</h4>
                    <p className="mt-1 text-xs opacity-70">
                        {[film.release_date?.slice(0, 4), film.vote_average > 0 ? `TMDB ${film.vote_average.toFixed(1)}/10` : null].filter(Boolean).join(' · ')}
                    </p>
                    <p className="mt-2 text-sm opacity-85">{film.explanation || film.overview}</p>
                </div>
            </div>
            <div className="px-3 pb-3">
                {film.action === 'play' && (
                    <button type="button" onClick={() => { onPick(film); onPlay(film.media_id); }} className={primaryButton}>Lire dans Jellyfin</button>
                )}
                {film.action === 'pending' && <p className="text-sm opacity-75">{requested ? 'Demande envoyée' : 'Demande en cours'}</p>}
                {(film.action === 'request' || film.action === 'rent') && (ask ? (
                    <div className="flex flex-wrap gap-2">
                        <button type="button" disabled={busy} className={primaryButton} onClick={async () => {
                            if (await onRequest(film)) setAsk(false);
                        }}>
                            {confirming ? 'En cours…' : 'Confirmer'}
                        </button>
                        <button type="button" disabled={busy} className={secondaryButton} onClick={() => setAsk(false)}>Annuler</button>
                    </div>
                ) : (
                    <button type="button" disabled={busy} className={secondaryButton} onClick={() => setAsk(true)}>
                        {film.action === 'rent' ? 'Louer pour regarder' : 'Demander via Seerr'}
                    </button>
                ))}
                {error && <p role="alert" className="mt-2 text-sm text-rose-500">{error}</p>}
            </div>
        </article>
    );
}

export default function RecommendationFlow({ isDarkMode, onClose, onPlay }) {
    const [sessionId, setSessionId] = useState(null);
    const [state, setState] = useState('loading');
    const [question, setQuestion] = useState(null);
    const [selected, setSelected] = useState([]);
    const [results, setResults] = useState([]);
    const [visibleCount, setVisibleCount] = useState(6);
    const [quota, setQuota] = useState(null);
    const [error, setError] = useState('');
    const [answering, setAnswering] = useState(false);
    const [pendingRequest, setPendingRequest] = useState(null);
    const [requested, setRequested] = useState({});
    const [requestError, setRequestError] = useState(null);
    const started = useRef(false);

    const start = useCallback(async () => {
        setState('loading');
        setError('');
        setSelected([]);
        setResults([]);
        setVisibleCount(6);
        setRequested({});
        setRequestError(null);
        try {
            const response = await startRecommendationSession({ guided: true });
            setSessionId(response.session_id);
            setQuota(response.quota);
            setQuestion(response.question);
            setState(response.state);
        } catch (err) {
            setError(err.message);
            setState(err.status === 429 ? 'quota_exhausted' : 'error');
        }
    }, []);

    useEffect(() => {
        if (started.current) return;
        started.current = true;
        start();
    }, [start]);

    const answer = async (choices) => {
        if (answering) return;
        setAnswering(true);
        setError('');
        try {
            const response = await answerRecommendation(sessionId, {
                answer: choices.length ? 'picked' : 'skipped',
                question_index: question.question_index,
                choices,
            });
            setSelected([]);
            setQuestion(response.question);
            setResults(response.results || []);
            setState(response.state);
        } catch (err) {
            setError(err.message || 'Impossible d’enregistrer cette réponse.');
            if (err.status === 503) setState('error');
        } finally {
            setAnswering(false);
        }
    };

    const request = async (film) => {
        if (pendingRequest !== null) return false;
        setPendingRequest(film.tmdb_id);
        setRequestError(null);
        try {
            const response = await confirmRecommendation(sessionId, { tmdb_id: film.tmdb_id, download: true });
            setResults(items => items.map(item => item.tmdb_id === film.tmdb_id
                ? { ...item, action: response.action, media_id: response.media_id || item.media_id }
                : item));
            setRequested(current => ({ ...current, [film.tmdb_id]: !response.already_requested }));
            return true;
        } catch (err) {
            setRequestError({ id: film.tmdb_id, message: err.message || 'Demande impossible.' });
            return false;
        } finally {
            setPendingRequest(null);
        }
    };

    const rememberFilm = (film, event_type) => recordRecommendationEvent({
        session_id: sessionId, media_id: film.media_id, value: String(film.tmdb_id), event_type,
    }).catch(() => {});

    const showMore = () => {
        const count = visibleCount + 6;
        results.slice(visibleCount, count).forEach(film => rememberFilm(film, 'shown'));
        setVisibleCount(count);
    };

    const renderFilm = (film) => (
        <FilmCard key={film.tmdb_id} film={film} isDarkMode={isDarkMode} onRequest={request}
            busy={pendingRequest !== null} confirming={pendingRequest === film.tmdb_id}
            requested={requested[film.tmdb_id]} onPick={item => rememberFilm(item, 'confirmed')} onPlay={onPlay}
            error={requestError?.id === film.tmdb_id ? requestError.message : null} />
    );
    const text = isDarkMode ? 'text-white' : 'text-[#0a2540]';
    const muted = isDarkMode ? 'text-white/65' : 'text-[#425466]';
    const panel = isDarkMode ? 'bg-[#111111] border-white/10' : 'bg-white border-[#e3e8ee]';
    const multi = question?.max_choices === 2;

    return (
        <div className="fixed inset-0 z-[95] flex items-center justify-center bg-black/80 p-3 backdrop-blur-md sm:p-6" onClick={onClose}>
            <section role="dialog" aria-modal="true" aria-labelledby="pick-film-title"
                className={`flex max-h-[94vh] min-h-[min(65vh,520px)] w-full max-w-5xl flex-col overflow-y-auto rounded-2xl border shadow-2xl ${panel} ${text}`}
                onClick={event => event.stopPropagation()}>
                <header className="flex items-center justify-between gap-4 border-b border-inherit px-5 py-4 sm:px-8">
                    <div>
                        <h2 id="pick-film-title" className="text-xl font-semibold">Choisir un film</h2>
                        {quota && !quota.unlimited && <p className={`mt-1 text-xs ${muted}`}>{quota.remaining} sur {quota.limit} sélections encore disponibles aujourd’hui</p>}
                    </div>
                    <button type="button" onClick={onClose} className={secondaryButton}>Fermer</button>
                </header>
                <div className="flex flex-1 flex-col justify-center px-5 py-6 sm:px-8">
                    {state === 'loading' && <p role="status" className={`text-center ${muted}`}>Ouverture du questionnaire…</p>}
                    {state === 'quota_exhausted' && <p role="status" className={`text-center ${muted}`}>{error} Reviens demain pour une nouvelle sélection.</p>}
                    {(state === 'error' || state === 'empty') && (
                        <div className="text-center">
                            <p className={muted}>{error || 'Aucun film ne correspond à cette sélection. Essaie avec moins de critères.'}</p>
                            <button type="button" className={`mt-5 ${secondaryButton}`} onClick={start}>Nouvelle sélection</button>
                        </div>
                    )}
                    {state === 'question' && question && (
                        <div className="mx-auto w-full max-w-xl">
                            <p className={`mb-2 text-sm ${muted}`}>Question {question.question_index + 1} sur {question.max_questions}</p>
                            <h3 className="text-2xl font-semibold">{question.prompt}</h3>
                            {multi && <p className={`mt-1 text-sm ${muted}`}>Choisis jusqu’à deux genres.</p>}
                            <div className={`mt-5 grid gap-2 ${multi ? 'grid-cols-2 sm:grid-cols-3' : ''}`}>
                                {question.options.map(option => {
                                    const active = selected.includes(option.answer);
                                    return (
                                        <button key={option.answer} type="button" aria-pressed={multi ? active : undefined}
                                            disabled={answering || (multi && selected.length >= question.max_choices && !active)}
                                            className={`text-left ${active ? primaryButton : secondaryButton}`}
                                            onClick={() => multi ? setSelected(current => active
                                                ? current.filter(value => value !== option.answer)
                                                : [...current, option.answer]) : answer([option.answer])}>
                                            {option.label}
                                        </button>
                                    );
                                })}
                            </div>
                            <div className="mt-5 flex flex-wrap gap-2">
                                {multi && <button type="button" className={primaryButton} disabled={answering || !selected.length} onClick={() => answer(selected)}>Continuer</button>}
                                <button type="button" className={secondaryButton} disabled={answering} onClick={() => answer([])}>Passer</button>
                            </div>
                            {answering && <p className={`mt-3 text-sm ${muted}`} role="status">Un instant…</p>}
                            {error && <p className="mt-3 text-sm text-rose-500" role="alert">{error}</p>}
                        </div>
                    )}
                    {state === 'result' && (
                        <div>
                            <h3 className="mb-3 text-xl font-semibold">Nos premiers choix</h3>
                            <div className="grid gap-3 sm:grid-cols-2">{results.slice(0, 2).map(renderFilm)}</div>
                            {results.length > 2 && <>
                                <h3 className="mb-3 mt-6 text-lg font-semibold">Autres idées</h3>
                                <div className="grid gap-3 sm:grid-cols-2">{results.slice(2, visibleCount).map(renderFilm)}</div>
                            </>}
                            <div className="mt-6 flex flex-wrap gap-2">
                                {results.length > visibleCount && <button type="button" className={primaryButton} onClick={showMore}>D’autres idées</button>}
                                <button type="button" disabled={pendingRequest !== null} className={secondaryButton} onClick={start}>Nouvelle sélection</button>
                            </div>
                        </div>
                    )}
                </div>
            </section>
        </div>
    );
}
