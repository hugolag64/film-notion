import { useCallback, useEffect, useState } from 'react';
import { answerParty, cancelParty, closeParty, fetchParty, joinParty, launchParty, voteParty } from '../api';
import { PARTY_POLL_MS, isPartyActive, partyStep, safeBookingUrl, voteSummary } from '../party';

const SOURCE_LABELS = { server: 'Sur le serveur', tmdb: 'À demander' };
const OVER_LABELS = { expired: 'Soirée expirée.', cancelled: 'Soirée annulée.' };

function Poster({ proposal, onOpenFilm }) {
    const image = proposal.poster_url
        ? <img src={proposal.poster_url} alt="" className="h-full w-full object-cover" />
        : <span className="flex h-full w-full items-center justify-center text-lg">🎬</span>;
    if (!proposal.tmdb_id || !onOpenFilm) return <span className="block h-16 w-11 shrink-0 overflow-hidden rounded-md bg-current/10">{image}</span>;
    return <button
        type="button"
        onClick={() => onOpenFilm({ tmdb_id: proposal.tmdb_id, title: proposal.title })}
        className="block h-16 w-11 shrink-0 overflow-hidden rounded-md bg-current/10 ring-[#635bff] hover:ring-2"
        aria-label={`Voir la fiche de ${proposal.title}`}
        title="Voir la fiche"
    >{image}</button>;
}

function Badge({ proposal }) {
    const label = proposal.showtime
        ? [proposal.showtime.time, proposal.showtime.version].filter(Boolean).join(' · ')
        : SOURCE_LABELS[proposal.source];
    return label ? <span className="rounded bg-[#635bff]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[#635bff]">{label}</span> : null;
}

function Questions({ questions, onSubmit, busy }) {
    const [answers, setAnswers] = useState({});
    const complete = questions.every((question) => answers[question.key]);
    return <div className="space-y-2">
        {questions.map((question) => <div key={question.key}>
            <p className="text-xs font-semibold">{question.label}</p>
            <div className="mt-1 flex flex-wrap gap-1">
                {question.options.map((option) => {
                    const active = answers[question.key] === option.value;
                    return <button
                        key={option.value}
                        type="button"
                        onClick={() => setAnswers((current) => ({ ...current, [question.key]: option.value }))}
                        aria-pressed={active}
                        className={`rounded-full border px-2.5 py-1 text-xs transition ${active ? 'border-[#635bff] bg-[#635bff] text-white' : 'border-current/20 hover:border-[#635bff]'}`}
                    >{option.label}</button>;
                })}
            </div>
        </div>)}
        <button type="button" disabled={!complete || busy} onClick={() => onSubmit(answers)} className="w-full rounded-lg bg-[#635bff] px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40">Valider</button>
    </div>;
}

export default function PartyCard({ partyId, isDarkMode, onOpenFilm }) {
    const [state, setState] = useState(null);
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);

    const load = useCallback(async () => {
        try {
            setState(await fetchParty(partyId));
        } catch (loadError) {
            setError(loadError.message);
        }
    }, [partyId]);

    useEffect(() => { load(); }, [load]);

    const active = isPartyActive(state);
    useEffect(() => {
        if (!active) return undefined;
        const timer = window.setInterval(() => { if (!document.hidden) load(); }, PARTY_POLL_MS);
        return () => window.clearInterval(timer);
    }, [active, load]);

    const act = async (action) => {
        setBusy(true);
        setError('');
        try {
            setState(await action());
        } catch (actionError) {
            setError(actionError.message);
            load();
        } finally {
            setBusy(false);
        }
    };

    const frame = `mt-1 w-full rounded-xl border px-3 py-2 text-xs ${isDarkMode ? 'border-white/10 bg-black/40' : 'border-[#e3e8ee] bg-white'}`;
    if (!state) return <div className={frame}>{error ? <p className="text-rose-500">{error}</p> : 'Chargement de la soirée…'}</div>;

    const step = partyStep(state);
    const starter = state.me.starter;
    const winner = state.proposals.find((proposal) => proposal.rank === state.winner_rank);
    const primary = 'w-full rounded-lg bg-[#635bff] px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40';

    return <div className={frame} aria-live="polite">
        <p className="mb-1 font-semibold">🍿 Soirée {state.mode === 'cinema' ? 'ciné' : 'coloc'}</p>
        {state.members.length > 0 && <p className="mb-2 opacity-75">
            Partants : {state.members.map((member) => `${member.name}${member.answered ? ' ✓' : ''}`).join(', ')}
        </p>}

        {step === 'join' && <button type="button" disabled={busy} onClick={() => act(() => joinParty(partyId))} className={primary}>Je suis partant</button>}

        {step === 'answer' && <Questions questions={state.questions} busy={busy} onSubmit={(answers) => act(() => answerParty(partyId, answers))} />}

        {step === 'wait' && (starter
            ? <button type="button" disabled={busy} onClick={() => act(() => launchParty(partyId))} className={primary}>{busy ? 'Recherche des films…' : 'On lance'}</button>
            : <p className="opacity-75">En attente du lancement par {state.starter.name}.</p>)}

        {step === 'vote' && <div className="space-y-2">
            {state.proposals.map((proposal) => {
                const mine = state.me.votes[proposal.rank];
                return <div key={proposal.rank} className="flex gap-2">
                    <Poster proposal={proposal} onOpenFilm={onOpenFilm} />
                    <div className="min-w-0 flex-1">
                        <p className="font-semibold">{proposal.title}</p>
                        <Badge proposal={proposal} />
                        {proposal.reason && <p className="mt-0.5 opacity-75">{proposal.reason}</p>}
                        <div className="mt-1 flex items-center gap-1">
                            {[1, -1].map((value) => <button
                                key={value}
                                type="button"
                                disabled={busy}
                                onClick={() => act(() => voteParty(partyId, proposal.rank, value))}
                                aria-pressed={mine === value}
                                aria-label={`${value > 0 ? 'Pour' : 'Contre'} ${proposal.title}`}
                                className={`rounded-md border px-2 py-0.5 ${mine === value ? 'border-[#635bff] bg-[#635bff]/15' : 'border-current/20'}`}
                            >{value > 0 ? '👍' : '👎'}</button>)}
                            <span className="ml-1 opacity-75">{voteSummary(state.scores, proposal.rank)}</span>
                        </div>
                    </div>
                </div>;
            })}
            {starter && <button type="button" disabled={busy} onClick={() => act(() => closeParty(partyId))} className="w-full rounded-lg border border-current/20 px-3 py-1.5 font-semibold">Clore le vote</button>}
        </div>}

        {step === 'result' && winner && <div className="flex gap-2">
            <Poster proposal={winner} onOpenFilm={onOpenFilm} />
            <div className="min-w-0 flex-1">
                <p className="font-semibold">🏆 {winner.title}</p>
                <Badge proposal={winner} />
                <div className="mt-1">
                    {winner.showtime
                        ? safeBookingUrl(winner.showtime.booking_url) && <a href={safeBookingUrl(winner.showtime.booking_url)} target="_blank" rel="noopener noreferrer" className="inline-block rounded-md bg-[#635bff] px-2 py-1 font-semibold text-white">Réserver la séance</a>
                        : winner.tmdb_id && onOpenFilm && <button type="button" onClick={() => onOpenFilm({ tmdb_id: winner.tmdb_id, title: winner.title })} className="rounded-md bg-[#635bff] px-2 py-1 font-semibold text-white">Voir la fiche</button>}
                </div>
            </div>
        </div>}

        {step === 'searching' && <p className="opacity-75">Recherche des films…</p>}

        {step === 'over' && <p className="opacity-75">{OVER_LABELS[state.status] || 'Pas de proposition ce soir.'}</p>}

        {starter && isPartyActive(state) && <button type="button" disabled={busy} onClick={() => act(() => cancelParty(partyId))} className="mt-2 w-full text-center text-[11px] underline opacity-60 hover:opacity-100">Annuler la soirée</button>}

        {error && <p className="mt-1 text-rose-500" role="alert">{error}</p>}
    </div>;
}
