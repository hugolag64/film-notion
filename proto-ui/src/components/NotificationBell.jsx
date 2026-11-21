import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchNotifications, markNotificationRead } from '../api';

const POLL_INTERVAL_MS = 60_000;

const timeLabel = (value) => {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('fr-FR', {
        day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
    });
};

export default function NotificationBell({ isDarkMode }) {
    const [notifications, setNotifications] = useState([]);
    const [open, setOpen] = useState(false);
    const containerRef = useRef(null);

    const refresh = useCallback(async () => {
        try {
            setNotifications(await fetchNotifications());
        } catch {
            // The bell is a convenience: a failed poll keeps the previous list.
        }
    }, []);

    useEffect(() => {
        refresh();
        const timer = window.setInterval(refresh, POLL_INTERVAL_MS);
        return () => window.clearInterval(timer);
    }, [refresh]);

    useEffect(() => {
        if (!open) return undefined;
        const close = (event) => {
            if (event.type === 'keydown' ? event.key === 'Escape' : !containerRef.current?.contains(event.target)) setOpen(false);
        };
        document.addEventListener('mousedown', close);
        document.addEventListener('keydown', close);
        return () => {
            document.removeEventListener('mousedown', close);
            document.removeEventListener('keydown', close);
        };
    }, [open]);

    const unread = notifications.filter((item) => !item.read_at);

    const markRead = async (notification) => {
        if (notification.read_at) return;
        try {
            await markNotificationRead(notification.id);
        } finally {
            await refresh();
        }
    };

    const markAllRead = async () => {
        await Promise.allSettled(unread.map((item) => markNotificationRead(item.id)));
        await refresh();
    };

    const toggle = () => {
        if (!open) refresh();
        setOpen((value) => !value);
    };

    return <div ref={containerRef} className="relative">
        <button
            type="button"
            onClick={toggle}
            className={`relative flex h-9 w-9 items-center justify-center rounded-full border text-base transition-all ${isDarkMode ? 'border-white/15 hover:bg-white/10' : 'border-[#e3e8ee] hover:bg-[#f6f9fc]'}`}
            aria-label={unread.length ? `Notifications, ${unread.length} non lue${unread.length > 1 ? 's' : ''}` : 'Notifications'}
            aria-expanded={open}
            title="Notifications"
        >
            <span aria-hidden="true">🔔</span>
            {unread.length > 0 && <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[9px] font-bold text-white">{unread.length > 9 ? '9+' : unread.length}</span>}
        </button>
        {open && <div className={`absolute right-0 top-full z-[80] mt-2 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border shadow-2xl ${isDarkMode ? 'border-white/10 bg-[#0e0e11] text-white' : 'border-[#e3e8ee] bg-white text-[#0a2540]'}`} role="dialog" aria-label="Notifications">
            <div className="flex items-center justify-between border-b border-current/10 px-4 py-3">
                <p className="text-sm font-semibold">Notifications</p>
                {unread.length > 0 && <button type="button" onClick={markAllRead} className="text-[11px] font-semibold text-[#635bff] hover:underline">Tout marquer comme lu</button>}
            </div>
            <div className="max-h-96 overflow-y-auto">
                {notifications.length === 0 && <p className="px-4 py-6 text-center text-xs opacity-60">Aucune notification pour l’instant.</p>}
                {notifications.slice(0, 20).map((notification) => <button
                    key={notification.id}
                    type="button"
                    onClick={() => markRead(notification)}
                    className={`flex w-full gap-2 border-b border-current/5 px-4 py-3 text-left text-xs last:border-0 hover:bg-[#635bff]/5 ${notification.read_at ? 'opacity-55' : ''}`}
                >
                    <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${notification.read_at ? 'bg-transparent' : 'bg-[#635bff]'}`} aria-hidden="true" />
                    <span className="min-w-0">
                        <span className="block leading-5">{notification.message}</span>
                        <span className="mt-1 block text-[10px] opacity-55">{timeLabel(notification.created_at)}</span>
                    </span>
                </button>)}
            </div>
        </div>}
    </div>;
}
