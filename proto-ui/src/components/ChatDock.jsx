import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import Icon from './Icon';
import { fetchChatMessages, fetchFilmShowtimes, postChatMessage, startParty } from '../api';
import { PARTY_BOT_ID, isPartyCommand, partyIdOf } from '../party';
import PartyCard from './PartyCard';
import { HELP_SECTIONS, PRIVATE_TTL_MS, filmButtons, helpCommands, isBotMessage, isCineCommand, isClearCommand, isExpiredPrivate, showtimeLine } from '../cinema';
import { useAuth } from '../auth-context';

// A shared room for everyone on the server. Polling keeps it simple: fast
// while the panel is open, slow while it is folded (just enough for the badge).
const OPEN_POLL_MS = 3_000;
const FOLDED_POLL_MS = 15_000;
const MAX_LENGTH = 500;
const OPEN_KEY = 'backstage.chat.open';
const LAST_READ_KEY = 'backstage.chat.lastRead';

const EMOJIS = [
    '😀', '😂', '🤣', '😊', '😍', '🥰', '😎', '🤩',
    '😉', '😏', '🤔', '🙄', '😴', '😱', '😭', '😡',
    '🥲', '🤯', '🥳', '😬', '🤫', '🫠', '👀', '💀',
    '👍', '👎', '👏', '🙌', '🙏', '🤝', '💪', '✌️',
    '❤️', '💔', '🔥', '✨', '💯', '🎉', '⭐', '🏆',
    '🎬', '🍿', '🎞️', '📺', '🎥', '🎟️', '🥤', '🛋️',
];

// Typed shortcuts turned into emojis on send.
const SHORTCUTS = [
    [/(^|\s):\)(?=\s|$)/g, '$1🙂'], [/(^|\s):D(?=\s|$)/g, '$1😄'], [/(^|\s);\)(?=\s|$)/g, '$1😉'],
    [/(^|\s):\((?=\s|$)/g, '$1🙁'], [/(^|\s):p(?=\s|$)/gi, '$1😛'], [/(^|\s)<3(?=\s|$)/g, '$1❤️'],
    [/:popcorn:/g, '🍿'], [/:fire:/g, '🔥'], [/:film:/g, '🎬'],
];
const withEmojis = (text) => SHORTCUTS.reduce((result, [pattern, emoji]) => result.replace(pattern, emoji), text);

const readStorage = (key, fallback) => {
    try {
        const value = window.localStorage.getItem(key);
        return value === null ? fallback : JSON.parse(value);
    } catch {
        return fallback;
    }
};
const writeStorage = (key, value) => {
    try {
        window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
        // Private mode or blocked storage: the chat still works, it just forgets.
    }
};

const timeLabel = (value) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    const sameDay = date.toDateString() === new Date().toDateString();
    return date.toLocaleString('fr-FR', sameDay
        ? { hour: '2-digit', minute: '2-digit' }
        : { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
};

const initials = (name) => (name || '?').trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toUpperCase();

// Only the emojis: shown big, like in messaging apps.
const isEmojiOnly = (text) => /^(\p{Extended_Pictographic}|\p{Emoji_Component}|‍|️|\s){1,12}$/u.test(text) && !/[0-9#*]/.test(text);

function Avatar({ author, isDarkMode, bot }) {
    if (bot) return <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm ${isDarkMode ? 'bg-white/10' : 'bg-[#635bff]/10'}`} aria-hidden="true">{author.id === PARTY_BOT_ID ? '🍿' : '🎬'}</span>;
    return author.avatar_url
        ? <img src={author.avatar_url} alt="" className="h-7 w-7 shrink-0 rounded-full object-cover" />
        : <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${isDarkMode ? 'bg-white/10' : 'bg-[#635bff]/10 text-[#635bff]'}`} aria-hidden="true">{initials(author.display_name)}</span>;
}

// Showtimes of one film, opened under a bot message for the person who clicked.
function FilmShowtimes({ state, isDarkMode }) {
    const muted = isDarkMode ? 'text-white/60' : 'text-[#425466]';
    if (state.status === 'loading') return <p className={`mt-1 px-1 text-xs ${muted}`}>Chargement des horaires…</p>;
    if (state.status === 'error') return <p className="mt-1 px-1 text-xs text-rose-500">Horaires indisponibles pour le moment</p>;
    const { data } = state;
    if (data.stale) return <p className="mt-1 px-1 text-xs text-rose-500">Horaires indisponibles</p>;
    return <div className={`mt-1 w-full rounded-xl border px-3 py-2 text-xs ${isDarkMode ? 'border-white/10 bg-black/40' : 'border-[#e3e8ee] bg-white'}`}>
        <p className="mb-1 font-semibold">{data.title}</p>
        {data.days.length === 0 && <p className={muted}>Plus de séance prévue.</p>}
        {data.days.map((day) => <div key={day.date} className="mt-1">
            <p className={`font-semibold capitalize ${muted}`}>{day.label}</p>
            <ul className="mt-0.5 flex flex-wrap gap-1">
                {day.showtimes.map((showtime) => <li key={`${showtime.time}-${showtime.version}-${showtime.booking_url}`}>
                    {showtime.booking_url
                        ? <a href={showtime.booking_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 rounded-md bg-[#635bff]/10 px-1.5 py-0.5 text-[#635bff] hover:bg-[#635bff]/20" title="Réserver">{showtimeLine(showtime)} 🎟</a>
                        : <span className="inline-flex rounded-md bg-current/10 px-1.5 py-0.5">{showtimeLine(showtime)}</span>}
                </li>)}
            </ul>
        </div>)}
    </div>;
}

export default function ChatDock({ isDarkMode, onOpenFilm }) {
    const { user } = useAuth();
    const [open, setOpen] = useState(() => readStorage(OPEN_KEY, false));
    const [messages, setMessages] = useState([]);
    const [lastRead, setLastRead] = useState(() => readStorage(LAST_READ_KEY, 0));
    const [draft, setDraft] = useState('');
    const [sending, setSending] = useState(false);
    const [error, setError] = useState('');
    const [showEmojis, setShowEmojis] = useState(false);
    const [showCineHelp, setShowCineHelp] = useState(false);
    const [showPartyPicker, setShowPartyPicker] = useState(false);
    const [openFilm, setOpenFilm] = useState(null); // { messageId, siteId, status, data }
    const lastIdRef = useRef(null);
    const listRef = useRef(null);
    const inputRef = useRef(null);
    const stickToBottom = useRef(true);

    const merge = useCallback((incoming) => {
        if (!incoming.length) return;
        setMessages((current) => {
            const known = new Set(current.map((message) => message.id));
            const fresh = incoming.filter((message) => !known.has(message.id));
            return fresh.length ? [...current, ...fresh].slice(-200) : current;
        });
        lastIdRef.current = Math.max(lastIdRef.current ?? 0, ...incoming.map((message) => message.id));
    }, []);

    const refresh = useCallback(async () => {
        if (document.hidden) return;
        try {
            merge(await fetchChatMessages(lastIdRef.current));
        } catch {
            // A missed poll is harmless: the next one catches up from the same cursor.
        }
    }, [merge]);

    useEffect(() => {
        refresh();
        const timer = window.setInterval(refresh, open ? OPEN_POLL_MS : FOLDED_POLL_MS);
        window.addEventListener('visibilitychange', refresh);
        return () => {
            window.clearInterval(timer);
            window.removeEventListener('visibilitychange', refresh);
        };
    }, [open, refresh]);

    useEffect(() => writeStorage(OPEN_KEY, open), [open]);

    // Les échanges privés avec les bots s'effacent seuls : le serveur ne les renvoie plus, on les retire ici.
    useEffect(() => {
        const timer = window.setInterval(() => {
            const now = Date.now();
            setMessages((current) => (current.some((message) => isExpiredPrivate(message, now))
                ? current.filter((message) => !isExpiredPrivate(message, now))
                : current));
        }, 30_000);
        return () => window.clearInterval(timer);
    }, []);

    const newestId = messages.at(-1)?.id ?? 0;
    useEffect(() => {
        if (!open || newestId <= lastRead) return;
        setLastRead(newestId);
        writeStorage(LAST_READ_KEY, newestId);
    }, [open, newestId, lastRead]);

    useLayoutEffect(() => {
        const list = listRef.current;
        if (open && list && stickToBottom.current) list.scrollTop = list.scrollHeight;
    }, [open, messages]);

    useEffect(() => {
        if (open) inputRef.current?.focus();
    }, [open]);

    const unread = messages.filter((message) => message.id > lastRead && message.author.id !== user?.id).length;

    const send = async (event) => {
        event?.preventDefault();
        const body = withEmojis(draft.trim());
        if (!body || sending) return;
        setSending(true);
        setError('');
        try {
            stickToBottom.current = true;
            const result = await postChatMessage(body);
            if (isClearCommand(body)) setMessages((current) => current.filter((message) => !message.private));
            else merge([result]);
            setDraft('');
            setShowEmojis(false);
            setShowCineHelp(false);
            // The bot answers right away: fetch its reply without waiting for the next poll.
            if (isCineCommand(body) || isPartyCommand(body)) refresh();
        } catch (sendError) {
            setError(sendError.message || 'Message non envoyé');
        } finally {
            setSending(false);
            inputRef.current?.focus();
        }
    };

    const insertEmoji = (emoji) => {
        const input = inputRef.current;
        const start = input?.selectionStart ?? draft.length;
        const end = input?.selectionEnd ?? draft.length;
        const next = (draft.slice(0, start) + emoji + draft.slice(end)).slice(0, MAX_LENGTH);
        setDraft(next);
        window.requestAnimationFrame(() => {
            input?.focus();
            const caret = start + emoji.length;
            input?.setSelectionRange(caret, caret);
        });
    };

    const putCommand = (command) => {
        setDraft(command);
        setShowCineHelp(false);
        setShowEmojis(false);
        window.requestAnimationFrame(() => {
            const input = inputRef.current;
            input?.focus();
            input?.setSelectionRange(command.length, command.length);
        });
    };

    const toggleFilm = async (messageId, siteId) => {
        if (openFilm?.messageId === messageId && openFilm?.siteId === siteId) {
            setOpenFilm(null);
            return;
        }
        setOpenFilm({ messageId, siteId, status: 'loading' });
        const same = (current) => current?.messageId === messageId && current?.siteId === siteId;
        try {
            const data = await fetchFilmShowtimes(siteId);
            setOpenFilm((current) => (same(current) ? { messageId, siteId, status: 'ok', data } : current));
        } catch {
            setOpenFilm((current) => (same(current) ? { messageId, siteId, status: 'error' } : current));
        }
    };

    const launchParty = async (mode) => {
        setShowPartyPicker(false);
        setError('');
        try {
            stickToBottom.current = true;
            await startParty(mode);
            refresh();
        } catch (partyError) {
            setError(partyError.message || 'Soirée non lancée');
        }
    };

    const onKeyDown = (event) => {
        if (event.key === 'Enter' && !event.shiftKey) send(event);
        if (event.key === 'Escape') {
            event.stopPropagation();
            if (showEmojis) setShowEmojis(false);
            else if (showCineHelp) setShowCineHelp(false);
            else if (showPartyPicker) setShowPartyPicker(false);
            else setOpen(false);
        }
    };

    const surface = isDarkMode ? 'border-white/10 bg-[#0e0e11]/95 text-white' : 'border-[#e3e8ee] bg-white/95 text-[#0a2540]';
    const dockPosition = 'bottom-[calc(4.25rem+env(safe-area-inset-bottom))] right-4 lg:bottom-5 lg:right-5';

    if (!open) {
        return <button
            type="button"
            onClick={() => setOpen(true)}
            className={`chat-fab fixed z-[60] flex h-12 w-12 items-center justify-center rounded-full bg-[#635bff] text-white shadow-[0_8px_24px_rgba(99,91,255,0.45)] transition-transform hover:scale-105 ${dockPosition}`}
            aria-label={unread ? `Ouvrir le salon, ${unread} message${unread > 1 ? 's' : ''} non lu${unread > 1 ? 's' : ''}` : 'Ouvrir le salon'}
            title="Salon"
        >
            <Icon name="chat" className="h-5 w-5" />
            {unread > 0 && <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-rose-500 px-1 text-xs font-bold ring-2 ring-white/80">{unread > 9 ? '9+' : unread}</span>}
        </button>;
    }

    return <section
        className={`chat-panel fixed z-[60] flex h-[min(32rem,calc(100dvh-8rem))] w-[min(22rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border shadow-2xl backdrop-blur-xl ${surface} ${dockPosition}`}
        aria-label="Salon"
    >
        <header className="flex items-center gap-2 border-b border-current/10 px-4 py-3">
            <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" aria-hidden="true" />
            <h2 className="flex-1 text-sm font-semibold">Salon</h2>
            <button type="button" onClick={() => setOpen(false)} className="flex h-8 w-8 items-center justify-center rounded-full hover:bg-current/10" aria-label="Réduire le salon" title="Réduire">
                <Icon name="minus" className="h-4 w-4" />
            </button>
        </header>

        <ol
            ref={listRef}
            onScroll={(event) => {
                const list = event.currentTarget;
                stickToBottom.current = list.scrollHeight - list.scrollTop - list.clientHeight < 40;
            }}
            className="flex-1 space-y-1 overflow-y-auto px-3 py-3"
            aria-live="polite"
        >
            {messages.length === 0 && <li className="flex h-full flex-col items-center justify-center gap-2 text-center text-xs opacity-75">
                <span className="text-3xl" aria-hidden="true">🍿</span>
                Personne n’a encore rien dit. Lance la conversation !
            </li>}
            {messages.map((message, index) => {
                const mine = message.author.id === user?.id;
                const bot = isBotMessage(message);
                const films = filmButtons(message.payload);
                const commands = helpCommands(message.payload);
                const partyId = partyIdOf(message.payload);
                const previous = messages[index - 1];
                const grouped = previous?.author.id === message.author.id
                    && new Date(message.created_at) - new Date(previous.created_at) < 5 * 60_000;
                const big = isEmojiOnly(message.body);
                return <li key={message.id} className={`flex items-end gap-2 ${mine ? 'flex-row-reverse' : ''} ${grouped ? '' : 'pt-2'}`}>
                    {!mine && (grouped ? <span className="w-7 shrink-0" /> : <Avatar author={message.author} isDarkMode={isDarkMode} bot={bot} />)}
                    <div className={`flex min-w-0 max-w-[78%] flex-col ${mine ? 'items-end' : 'items-start'}`}>
                        {!grouped && <span className="mb-0.5 px-1 text-[11px] opacity-70">
                            {mine ? 'Toi' : message.author.display_name} · {timeLabel(message.created_at)}
                        </span>}
                        <p className={big
                            ? 'chat-pop text-3xl leading-tight'
                            : `chat-pop whitespace-pre-wrap break-words rounded-2xl px-3 py-1.5 text-sm leading-snug ${mine
                                ? 'rounded-br-md bg-[#635bff] text-white'
                                : isDarkMode ? 'rounded-bl-md bg-white/10' : 'rounded-bl-md bg-[#f1f4f8]'}`}
                        >{message.body}</p>
                        {message.private && <span className="mt-0.5 px-1 text-[10px] opacity-60" title="Tape @quit pour l’effacer tout de suite">🔒 Visible par toi seul · s’efface dans {Math.round(PRIVATE_TTL_MS / 60_000)} min</span>}
                        {films.length > 0 && <div className="mt-1 flex flex-wrap gap-1">
                            {films.map((film) => {
                                const active = openFilm?.messageId === message.id && openFilm?.siteId === film.site_id;
                                return <button
                                    key={film.site_id}
                                    type="button"
                                    onClick={() => toggleFilm(message.id, film.site_id)}
                                    aria-expanded={active}
                                    className={`rounded-full border px-2.5 py-1 text-xs font-semibold transition ${active
                                        ? 'border-[#635bff] bg-[#635bff] text-white'
                                        : isDarkMode ? 'border-white/15 hover:border-[#635bff]' : 'border-[#e3e8ee] bg-white hover:border-[#635bff]'}`}
                                    title={film.tracked ? 'Dans une de vos listes' : undefined}
                                >{film.tracked ? '★ ' : ''}{film.title}</button>;
                            })}
                        </div>}
                        {openFilm?.messageId === message.id && <FilmShowtimes state={openFilm} isDarkMode={isDarkMode} />}
                        {commands.length > 0 && <ul className="mt-1 w-full space-y-1">
                            {commands.map((item) => <li key={item.command}>
                                <button type="button" onClick={() => putCommand(item.command)} className={`w-full rounded-lg border px-2 py-1 text-left text-xs transition hover:border-[#635bff] ${isDarkMode ? 'border-white/15' : 'border-[#e3e8ee] bg-white'}`}>
                                    <span className="font-semibold text-[#635bff]">{item.command}</span>
                                    <span className="block opacity-75">{item.description}</span>
                                </button>
                            </li>)}
                        </ul>}
                        {partyId && <PartyCard partyId={partyId} isDarkMode={isDarkMode} onOpenFilm={onOpenFilm} />}
                    </div>
                </li>;
            })}
        </ol>

        <form onSubmit={send} className="relative border-t border-current/10 p-2">
            {showEmojis && <div className={`absolute bottom-full left-2 right-2 mb-2 grid grid-cols-8 gap-0.5 rounded-xl border p-2 shadow-xl ${surface}`} role="listbox" aria-label="Emojis">
                {EMOJIS.map((emoji) => <button
                    key={emoji}
                    type="button"
                    onClick={() => insertEmoji(emoji)}
                    className="flex h-8 items-center justify-center rounded-lg text-xl transition-transform hover:scale-125 hover:bg-current/10"
                    aria-label={`Ajouter ${emoji}`}
                >{emoji}</button>)}
            </div>}
            {showCineHelp && <div className={`absolute bottom-full left-2 right-2 mb-2 max-h-80 overflow-y-auto rounded-xl border p-2 shadow-xl ${surface}`} role="group" aria-label="Aide du salon">
                <p className="px-1 pb-1 text-xs font-semibold">Aide du salon</p>
                <p className="px-1 pb-2 text-[11px] opacity-75">Clique sur une commande pour l’écrire, puis envoie-la.</p>
                {HELP_SECTIONS.map((section) => <div key={section.title} className="mb-2 last:mb-0">
                    <p className="px-1 text-xs font-semibold">{section.title}</p>
                    <p className="px-1 pb-1 text-[11px] opacity-60">{section.audience}</p>
                    <ul className="space-y-1">
                        {section.commands.map((item) => <li key={item.command}>
                            <button type="button" onClick={() => putCommand(item.command)} className="w-full rounded-lg px-2 py-1 text-left text-xs hover:bg-current/10">
                                <span className="font-semibold text-[#635bff]">{item.command}</span>
                                <span className="block opacity-75">{item.description}</span>
                            </button>
                        </li>)}
                    </ul>
                </div>)}
            </div>}
            {showPartyPicker && <div className={`absolute bottom-full left-2 right-2 mb-2 rounded-xl border p-2 shadow-xl ${surface}`} role="group" aria-label="Lancer une soirée film">
                <p className="px-1 pb-1 text-xs font-semibold">Lancer une soirée film</p>
                <div className="grid grid-cols-2 gap-1">
                    <button type="button" onClick={() => launchParty('coloc')} className="rounded-lg px-2 py-2 text-left text-xs hover:bg-current/10">
                        <span className="block font-semibold text-[#635bff]">🛋️ Coloc</span>
                        <span className="opacity-75">Un film ici, sur le serveur ou à demander</span>
                    </button>
                    <button type="button" onClick={() => launchParty('cinema')} className="rounded-lg px-2 py-2 text-left text-xs hover:bg-current/10">
                        <span className="block font-semibold text-[#635bff]">🎟️ Ciné ce soir</span>
                        <span className="opacity-75">Une séance au Grand Sud</span>
                    </button>
                </div>
            </div>}
            {error && <p className="px-2 pb-1 text-xs text-rose-500" role="alert">{error}</p>}
            <div className="flex items-end gap-1">
                <button
                    type="button"
                    onClick={() => { setShowCineHelp(false); setShowPartyPicker(false); setShowEmojis((value) => !value); }}
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full hover:bg-current/10 ${showEmojis ? 'text-[#635bff]' : ''}`}
                    aria-label="Choisir un emoji"
                    aria-expanded={showEmojis}
                    title="Emojis"
                >
                    <Icon name="smile" className="h-5 w-5" />
                </button>
                <button
                    type="button"
                    onClick={() => { setShowEmojis(false); setShowPartyPicker(false); setShowCineHelp((value) => !value); }}
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-base font-bold hover:bg-current/10 ${showCineHelp ? 'bg-[#635bff]/10 text-[#635bff]' : ''}`}
                    aria-label="Aide : les commandes du salon"
                    aria-expanded={showCineHelp}
                    title="Aide"
                >?</button>
                <button
                    type="button"
                    onClick={() => { setShowEmojis(false); setShowCineHelp(false); setShowPartyPicker((value) => !value); }}
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-lg hover:bg-current/10 ${showPartyPicker ? 'bg-[#635bff]/10' : ''}`}
                    aria-label="Lancer une soirée film"
                    aria-expanded={showPartyPicker}
                    title="Soirée film"
                >🍿</button>
                <textarea
                    ref={inputRef}
                    value={draft}
                    onChange={(event) => setDraft(event.target.value.slice(0, MAX_LENGTH))}
                    onKeyDown={onKeyDown}
                    rows={1}
                    placeholder="Écris un message…"
                    aria-label="Message"
                    className={`max-h-24 min-h-9 flex-1 resize-none rounded-2xl border px-3 py-2 text-sm outline-none focus:border-[#635bff] ${isDarkMode ? 'border-white/15 bg-black/40 placeholder-white/40' : 'border-[#e3e8ee] bg-[#f6f9fc] placeholder-[#425466]/50'}`}
                />
                <button
                    type="submit"
                    disabled={!draft.trim() || sending}
                    className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#635bff] text-white transition-opacity disabled:opacity-40"
                    aria-label="Envoyer"
                    title="Envoyer (Entrée)"
                >
                    <Icon name="send" className="h-4 w-4" />
                </button>
            </div>
        </form>
    </section>;
}
