// Line icons drawn the same on every device (emojis vary and get read aloud).
// Decorative by default: the text next to the icon carries the meaning.
const PATHS = {
    film: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4" /></>,
    eye: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
    pin: <><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6Z" /><path d="M12 14v7" /></>,
    bookmark: <path d="M6 3h12v18l-6-4-6 4V3Z" />,
    heart: <path d="M12 20s-7-4.4-9-8.6C1.6 8.4 3.4 5 6.7 5c2 0 3.3 1.1 4.3 2.5C12 6.1 13.3 5 15.3 5c3.3 0 5.1 3.4 3.7 6.4C19 15.6 12 20 12 20Z" />,
    sparkle: <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3ZM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8L19 16Z" />,
    server: <><rect x="3" y="4" width="18" height="7" rx="1.5" /><rect x="3" y="13" width="18" height="7" rx="1.5" /><path d="M7 7.5h.01M7 16.5h.01" /></>,
    disc: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="2.5" /></>,
    globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3Z" /></>,
    ticket: <path d="M3 8a2 2 0 0 0 2-2h14a2 2 0 0 0 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 0-2 2H5a2 2 0 0 0-2-2v-2a2 2 0 0 0 0-4V8ZM14 6v12" />,
    refresh: <path d="M20 11a8 8 0 0 0-14.3-4.9L4 8M4 4v4h4M4 13a8 8 0 0 0 14.3 4.9L20 16M20 20v-4h-4" />,
    note: <><path d="M5 3h10l4 4v14H5V3Z" /><path d="M9 11h6M9 15h6" /></>,
    bell: <path d="M6 16V11a6 6 0 1 1 12 0v5l2 2H4l2-2ZM10 20a2 2 0 0 0 4 0" />,
    check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
    close: <path d="M6 6l12 12M18 6L6 18" />,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    chat: <path d="M4 5h16v11H9l-5 4V5Z" />,
    smile: <><circle cx="12" cy="12" r="9" /><path d="M8.5 14.5c1 1.2 2.1 1.8 3.5 1.8s2.5-.6 3.5-1.8M9 9.5h.01M15 9.5h.01" /></>,
    send: <path d="M4 12l16-8-6 16-2.5-6.5L4 12Z" />,
    minus: <path d="M5 12h14" />,
};

export default function Icon({name, className = 'h-4 w-4', filled = false}) {
    return <svg
        viewBox="0 0 24 24"
        className={`inline-block shrink-0 ${className}`}
        fill={filled ? 'currentColor' : 'none'}
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        focusable="false"
    >{PATHS[name]}</svg>;
}
