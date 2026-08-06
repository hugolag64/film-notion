import { useEffect, useState } from 'react';
import { answerRecommendation, confirmRecommendation, startRecommendationSession } from '../api';

const posterUrl = (path) => path ? `https://image.tmdb.org/t/p/w500${path}` : null;

function PosterCard({ option, onSelect, isDarkMode }) {
    const image = posterUrl(option.poster_path);
    return <button type="button" onClick={() => onSelect(option)} className={`group overflow-hidden rounded-2xl border text-left transition duration-300 hover:-translate-y-1 hover:border-[#635bff] ${isDarkMode ? 'border-white/10 bg-white/[0.03]' : 'border-[#e3e8ee] bg-white'}`}>
        <div className="aspect-[2/3] overflow-hidden bg-slate-900">
            {image ? <img src={image} alt="" className="h-full w-full object-cover transition duration-500 group-hover:scale-105" /> : <div className="flex h-full items-center justify-center px-5 text-center text-xs text-white/50">Affiche indisponible</div>}
        </div>
        <div className="p-3"><p className="font-semibold">{option.title}</p><p className="mt-1 text-xs opacity-60">{option.release_date?.slice(0, 4) || '—'} · TMDB {option.vote_average?.toFixed(1) || '—'}</p></div>
    </button>;
}

function ChoiceOption({ option, onSelect, isDarkMode }) {
    return <button type="button" onClick={() => onSelect(option)} className={`group flex w-full items-center justify-between gap-4 rounded-2xl border p-4 text-left transition duration-200 hover:-translate-y-0.5 hover:border-[#635bff] hover:shadow-lg ${isDarkMode ? 'border-white/10 bg-white/[0.03]' : 'border-[#e3e8ee] bg-white'}`}>
        <span><span className="block font-semibold">{option.label}</span><span className="mt-1 block text-xs opacity-60">{option.description}</span></span>
        <span className="text-lg text-[#635bff] transition-transform group-hover:translate-x-1">→</span>
    </button>;
}

export default function RecommendationFlow({ isDarkMode, onClose }) {
    const [session, setSession] = useState(null);
    const [state, setState] = useState('loading');
    const [question, setQuestion] = useState(null);
    const [result, setResult] = useState(null);
    const [questionCount, setQuestionCount] = useState(0);
    const [quota, setQuota] = useState(null);
    const [error, setError] = useState('');
    const [confirmation, setConfirmation] = useState(null);
    const [confirming, setConfirming] = useState(false);

    const start = async () => {
        try {
            setState('loading');
            setError('');
            setResult(null);
            setConfirmation(null);
            const response = await startRecommendationSession();
            setSession(response.session);
            setQuota(response.quota || null);
            setQuestion(response.question);
            setQuestionCount(response.question?.question_index ?? response.session?.question_count ?? 0);
            setState(response.state);
        } catch (requestError) {
            setError(requestError.message || 'Impossible de lancer la recommandation.');
            setState(requestError.status === 429 ? 'quota_exhausted' : 'error');
        }
    };

    useEffect(() => { start(); }, []);

    const answer = async (payload) => {
        if (!session?.id) return;
        try {
            setState('loading');
            const response = await answerRecommendation(session.id, payload);
            setQuestion(response.question);
            setResult(response.result);
            setQuota(response.quota || quota);
            setQuestionCount((current) => response.question?.question_index ?? current + 1);
            setState(response.state);
        } catch (requestError) {
            setError(requestError.message || 'Réponse impossible.');
            setState('error');
        }
    };

    const confirm = async () => {
        if (!session?.id || !result?.tmdb_id || confirming) return;
        try {
            setConfirming(true);
            setError('');
            const response = await confirmRecommendation(session.id, { tmdb_id: result.tmdb_id, download: true });
            setConfirmation(response);
        } catch (requestError) {
            setError(requestError.message || 'Impossible d’ajouter le film.');
        } finally {
            setConfirming(false);
        }
    };

    const text = isDarkMode ? 'text-white' : 'text-[#0a2540]';
    const muted = isDarkMode ? 'text-white/60' : 'text-[#425466]';
    const panel = isDarkMode ? 'bg-[#111111] border-white/10' : 'bg-white border-[#e3e8ee]';
    const questionNumber = (question?.question_index ?? questionCount) + 1;

    return <div className="fixed inset-0 z-[95] flex items-center justify-center bg-black/80 p-3 backdrop-blur-md sm:p-6" onClick={onClose}>
        <section className={`flex h-[min(94vh,820px)] w-full max-w-5xl flex-col overflow-y-auto rounded-2xl border shadow-2xl ${panel} ${text}`} onClick={(event) => event.stopPropagation()}>
            <header className="flex items-center justify-between gap-4 border-b border-inherit px-5 py-4 sm:px-8">
                <div><p className="text-[10px] font-mono uppercase tracking-[0.24em] text-[#635bff]">Sélection personnelle</p><h2 className="mt-1 text-2xl font-semibold">Trouve ton prochain film</h2>{quota && <p className={`mt-1 text-xs ${muted}`}>{quota.unlimited ? 'Sessions illimitées' : `${quota.remaining} session${quota.remaining > 1 ? 's' : ''} restante${quota.remaining > 1 ? 's' : ''} aujourd’hui`}</p>}</div>
                <button type="button" onClick={onClose} className="rounded-lg border px-3 py-2 text-xs font-semibold">Fermer</button>
            </header>
            <main className="flex flex-1 flex-col justify-center px-5 py-8 sm:px-12">
                {state === 'loading' && <p className={`text-center ${muted}`}>Je cherche une piste qui te ressemble…</p>}
                {state === 'quota_exhausted' && <div className="mx-auto max-w-md text-center"><p className={`text-lg ${muted}`}>Tu as utilisé tes 2 sélections du jour.</p><p className={`mt-2 text-sm ${muted}`}>La prochaine session sera disponible demain.</p><button type="button" onClick={onClose} className="mt-5 rounded-lg border px-4 py-2 text-sm font-semibold">Fermer</button></div>}
                {state === 'error' && <div className="mx-auto max-w-md text-center"><p className="text-rose-500">{error}</p><button type="button" onClick={start} className="mt-5 rounded-lg bg-[#635bff] px-4 py-2 text-sm font-semibold text-white">Réessayer</button></div>}
                {state === 'empty' && <div className="mx-auto max-w-md text-center"><p className={`text-lg ${muted}`}>Je n’ai pas encore assez de données pour te proposer un film.</p><button type="button" onClick={start} className="mt-5 rounded-lg border px-4 py-2 text-sm font-semibold">Recommencer</button></div>}
                {state === 'question' && question && <div className="mx-auto w-full max-w-3xl"><div className="mb-8 flex items-center justify-between text-xs"><span className={muted}>Affinons la sélection</span><span className="font-mono text-[#635bff]">{questionNumber} / {question.max_questions ?? 5}</span></div><h3 className="mb-7 text-center text-2xl font-semibold">{question.prompt}</h3>{question.type === 'choice' ? <div className="mx-auto grid max-w-xl gap-3">{question.options.map((option) => <ChoiceOption key={option.answer} option={option} onSelect={(selected) => answer({ answer: selected.answer, value: selected.value })} isDarkMode={isDarkMode} />)}</div> : <div className="grid gap-5 sm:grid-cols-2">{question.options.map((option) => <PosterCard key={option.tmdb_id} option={option} onSelect={(selected) => answer({ answer: 'picked', value: String(selected.tmdb_id) })} isDarkMode={isDarkMode} />)}</div>}{question.type === 'compare' && <div className="mt-7 flex flex-wrap justify-center gap-2"><button type="button" onClick={() => answer({ answer: 'not_now', value: String(question.options[0].tmdb_id) })} className="rounded-full border px-3 py-2 text-xs">Pas maintenant</button><button type="button" onClick={() => answer({ answer: 'less_like_this', value: String(question.options[0].tmdb_id) })} className="rounded-full border px-3 py-2 text-xs">Pas mon style</button><button type="button" onClick={() => answer({ answer: 'already_seen', value: String(question.options[0].tmdb_id) })} className="rounded-full border px-3 py-2 text-xs">Déjà vu</button><button type="button" onClick={() => answer({ answer: 'surprise' })} className="rounded-full border px-3 py-2 text-xs">Surprise</button></div>}</div>}
                {state === 'result' && result && <div className="mx-auto w-full max-w-2xl text-center"><p className={`text-xs uppercase tracking-[0.2em] ${muted}`}>Ma recommandation</p><div className="mx-auto mt-5 max-w-xs"><PosterCard option={result} onSelect={() => {}} isDarkMode={isDarkMode} /></div><p className={`mt-5 text-sm ${muted}`}>Choisi à partir de tes notes, de ton historique et de tes réponses.</p>{confirmation ? <div className={`mx-auto mt-5 max-w-md rounded-xl border p-4 text-sm ${confirmation.download_error ? 'border-amber-400/40 text-amber-700' : 'border-emerald-400/40 text-emerald-700'}`}>{confirmation.download_error ? `Film ajouté, mais téléchargement non lancé : ${confirmation.download_error}` : confirmation.availability ? 'Film ajouté à la bibliothèque. Téléchargement demandé.' : 'Film ajouté à la bibliothèque.'}</div> : <button type="button" onClick={confirm} disabled={confirming} className="mt-6 rounded-lg bg-[#635bff] px-5 py-3 text-sm font-semibold text-white disabled:opacity-50">{confirming ? 'Ajout en cours…' : 'Ajouter et télécharger'}</button>}<div className="mt-6 flex justify-center gap-2"><button type="button" onClick={start} className="rounded-lg border px-4 py-2 text-sm font-semibold">Nouvelle sélection</button><button type="button" onClick={onClose} className="rounded-lg border px-4 py-2 text-sm font-semibold">Retour à la bibliothèque</button></div>{error && <p className="mt-4 text-sm text-rose-500">{error}</p>}</div>}
            </main>
        </section>
    </div>;
}
