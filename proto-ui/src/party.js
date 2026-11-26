// Soirée film du salon : petites fonctions pures pour la carte.

export const PARTY_BOT_ID = 'bot:soiree';
export const PARTY_POLL_MS = 3_000;

export function partyIdOf(payload) {
    return payload?.type === 'party' && payload.party_id ? payload.party_id : null;
}

export function isPartyActive(state) {
    return state?.status === 'joining' || state?.status === 'voting';
}

export function partyStep(state) {
    const me = state?.me || {};
    if (state?.status === 'done') return 'result';
    if (state?.status === 'joining') {
        if (!me.member) return 'join';
        return me.answered ? 'wait' : 'answer';
    }
    if (state?.status === 'voting') return me.member ? 'vote' : 'join';
    return 'over';
}

export function voteSummary(scores, rank) {
    const score = scores?.[rank] || { up: 0, down: 0 };
    return `👍 ${score.up} · 👎 ${score.down}`;
}

export function isPartyCommand(text) {
    const folded = (text || '').trim().normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    return /^@soiree(\s|$)/.test(folded);
}

export function safeBookingUrl(url) {
    return typeof url === 'string' && /^https?:\/\//i.test(url) ? url : null;
}
