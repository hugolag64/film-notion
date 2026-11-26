// Bot « Ciné » du salon : petites fonctions pures pour l'affichage.

export const BOT_ID = 'bot:cine';

// Mêmes commandes et textes que COMMANDS dans backend/core/cinema_bot.py.
export const CINE_COMMANDS = [
    { command: '@ciné films', description: "Les films à l'affiche : clique sur un titre pour voir ses horaires." },
    { command: '@ciné ce soir', description: "Les séances d'aujourd'hui qui n'ont pas encore commencé." },
    { command: '@ciné demain', description: 'Les séances de demain.' },
    { command: '@ciné aide', description: 'Cette liste de commandes.' },
];

// Les deux bots du salon : « Ciné » et « Soirée ».
const BOT_IDS = new Set([BOT_ID, 'bot:soiree']);

export function isBotMessage(message) {
    return BOT_IDS.has(message?.author?.id);
}

export function filmButtons(payload) {
    return payload?.type === 'cine_films' && Array.isArray(payload.films) ? payload.films : [];
}

export function helpCommands(payload) {
    return payload?.type === 'cine_help' && Array.isArray(payload.commands) ? payload.commands : [];
}

export function showtimeLine(showtime) {
    return showtime.version ? `${showtime.time} · ${showtime.version}` : showtime.time;
}

export function isCineCommand(text) {
    const folded = (text || '').trim().normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    return /^@cine(\s|$)/.test(folded);
}
