// Bot « Ciné » du salon : petites fonctions pures pour l'affichage.

export const BOT_ID = 'bot:cine';

// Mêmes commandes et textes que COMMANDS dans backend/core/cinema_bot.py.
export const CINE_COMMANDS = [
    { command: '@ciné films', description: "Les films à l'affiche : clique sur un titre pour voir ses horaires." },
    { command: '@ciné ce soir', description: "Les séances d'aujourd'hui qui n'ont pas encore commencé." },
    { command: '@ciné demain', description: 'Les séances de demain.' },
    { command: '@ciné aide', description: 'Cette liste de commandes.' },
];

// Le panneau « ? » du salon : chaque commande, et qui voit la réponse.
export const HELP_SECTIONS = [
    {
        title: 'Horaires du Grand Sud',
        audience: 'Réponse visible par toi seul',
        commands: CINE_COMMANDS.filter((c) => c.command !== '@ciné aide'),
    },
    {
        title: 'Soirée film',
        audience: 'Visible par tout le salon (ou bouton 🍿)',
        commands: [
            { command: '@soirée coloc', description: 'Choisir ensemble un film à regarder ici, sur le serveur ou à demander.' },
            { command: '@soirée ciné', description: 'Choisir ensemble une séance ce soir au Grand Sud.' },
        ],
    },
    {
        title: 'Ranger le salon',
        audience: 'Tes échanges privés avec les bots s’effacent seuls après 10 min',
        commands: [
            { command: '@quit', description: 'Efface tout de suite tes commandes et les réponses des bots.' },
        ],
    },
];

// Même durée que PRIVATE_CHAT_TTL dans backend/core/store.py.
export const PRIVATE_TTL_MS = 10 * 60_000;

export function isExpiredPrivate(message, now = Date.now()) {
    return Boolean(message?.private) && now - new Date(message.created_at).getTime() > PRIVATE_TTL_MS;
}

// Même règle que is_clear_command dans backend/api.py.
export function isClearCommand(text) {
    return /^@(quit|effacer|clear)$/i.test((text || '').trim());
}

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
