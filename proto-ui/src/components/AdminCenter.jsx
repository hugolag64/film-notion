import { useCallback, useEffect, useState } from 'react';
import {
    fetchAdminDashboard,
    fetchKeepRequests,
    fetchMediaServerActivity,
    fetchMediaServerStatus,
    fetchStorageStatus,
    fetchUsers,
    importMediaServerLibrary,
    syncMediaServer,
} from '../api';

const SECTIONS = [
    ['overview', 'Vue d’ensemble'],
    ['activity', 'Activité serveur'],
    ['requests', 'Demandes'],
    ['users', 'Utilisateurs'],
    ['storage', 'Stockage'],
    ['services', 'Services'],
    ['settings', 'Paramètres'],
];

function formatDate(value) {
    if (!value) return '—';
    return new Date(value).toLocaleString('fr-FR');
}

export default function AdminCenter({ isDarkMode, onClose, onMediaChanged }) {
    const [section, setSection] = useState('overview');
    const [dashboard, setDashboard] = useState(null);
    const [activity, setActivity] = useState(null);
    const [keepRequests, setKeepRequests] = useState([]);
    const [users, setUsers] = useState([]);
    const [storage, setStorage] = useState(null);
    const [services, setServices] = useState(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState('');

    const load = useCallback(async () => {
        try {
            setError('');
            const [nextDashboard, nextActivity, nextKeepRequests, nextUsers, nextStorage, nextServices] = await Promise.all([
                fetchAdminDashboard(),
                fetchMediaServerActivity(),
                fetchKeepRequests(),
                fetchUsers(),
                fetchStorageStatus(),
                fetchMediaServerStatus(),
            ]);
            setDashboard(nextDashboard);
            setActivity(nextActivity);
            setKeepRequests(nextKeepRequests);
            setUsers(nextUsers);
            setStorage(nextStorage);
            setServices(nextServices);
        } catch (requestError) {
            setError(requestError.message || 'Impossible de charger le centre d’administration.');
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const refresh = () => {
        setRefreshing(true);
        load();
    };

    const syncAndRefresh = async () => {
        try {
            setRefreshing(true);
            await syncMediaServer();
            await load();
            await onMediaChanged?.();
        } catch (requestError) {
            setError(requestError.message || 'Synchronisation impossible.');
            setRefreshing(false);
        }
    };

    const importAndRefresh = async () => {
        try {
            setRefreshing(true);
            await importMediaServerLibrary();
            await load();
            await onMediaChanged?.();
        } catch (requestError) {
            setError(requestError.message || 'Import impossible.');
            setRefreshing(false);
        }
    };

    const text = isDarkMode ? 'text-white' : 'text-[#0a2540]';
    const muted = isDarkMode ? 'text-white/60' : 'text-[#425466]';
    const panel = isDarkMode ? 'bg-[#111111] border-white/10' : 'bg-white border-[#e3e8ee]';
    const card = isDarkMode ? 'border-white/10 bg-white/[0.03]' : 'border-[#e3e8ee] bg-white';

    return (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 p-3 backdrop-blur-md sm:p-6" onClick={onClose}>
            <section className={`flex h-[min(94vh,900px)] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border shadow-2xl ${panel} ${text}`} onClick={(event) => event.stopPropagation()}>
                <header className="flex flex-wrap items-center justify-between gap-3 border-b border-inherit px-5 py-4 sm:px-7">
                    <div>
                        <p className="text-[10px] font-mono uppercase tracking-[0.24em] text-[#635bff]">Backstage / Admin</p>
                        <h2 className="mt-1 text-2xl font-semibold">Centre d’administration</h2>
                    </div>
                    <div className="flex items-center gap-2">
                        <button type="button" className="rounded-lg border px-3 py-2 text-xs font-semibold" onClick={refresh} disabled={refreshing}>
                            {refreshing ? 'Actualisation…' : 'Actualiser'}
                        </button>
                        <button type="button" className="rounded-lg border px-3 py-2 text-xs font-semibold" onClick={onClose}>Fermer</button>
                    </div>
                </header>

                <div className="flex min-h-0 flex-1 flex-col sm:flex-row">
                    <nav className={`flex shrink-0 gap-1 overflow-x-auto border-b p-3 sm:w-52 sm:flex-col sm:overflow-y-auto sm:border-b-0 sm:border-r ${isDarkMode ? 'border-white/10' : 'border-[#e3e8ee]'}`} aria-label="Administration">
                        {SECTIONS.map(([id, label]) => (
                            <button key={id} type="button" onClick={() => setSection(id)} className={`whitespace-nowrap rounded-lg px-3 py-2 text-left text-xs font-semibold transition ${section === id ? 'bg-[#635bff] text-white' : isDarkMode ? 'text-white/60 hover:bg-white/10 hover:text-white' : 'text-[#425466] hover:bg-[#f6f9fc] hover:text-[#0a2540]'}`}>
                                {label}
                            </button>
                        ))}
                    </nav>

                    <main className="min-h-0 flex-1 overflow-y-auto p-5 sm:p-7">
                        {error && <p className="mb-5 rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-500" role="alert">{error}</p>}
                        {loading ? <p className={muted}>Chargement du centre d’administration…</p> : (
                            <>
                                {section === 'overview' && <div className="space-y-5">
                                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                                        {[
                                            ['Expirations proches', dashboard?.expiring?.length || 0],
                                            ['Téléchargements', dashboard?.downloads?.length || 0],
                                            ['Erreurs', dashboard?.errors?.length || 0],
                                            ['Demandes de conservation', keepRequests.length],
                                        ].map(([label, value]) => <div key={label} className={`rounded-xl border p-4 ${card}`}><p className={`text-xs ${muted}`}>{label}</p><p className="mt-2 text-3xl font-semibold">{value}</p></div>)}
                                    </div>
                                    <div className="grid gap-3 lg:grid-cols-2">
                                        <div className={`rounded-xl border p-4 ${card}`}><h3 className="font-semibold">Stockage</h3><p className={`mt-2 text-sm ${muted}`}>{storage ? `${storage.temporary_gb} Go temporaires · ${storage.min_free_gb ?? '—'} Go libres` : 'État indisponible'}</p></div>
                                        <div className={`rounded-xl border p-4 ${card}`}><h3 className="font-semibold">Utilisateurs</h3><p className={`mt-2 text-sm ${muted}`}>{users.length} compte(s) configuré(s)</p></div>
                                    </div>
                                </div>}

                                {section === 'activity' && <div className="space-y-4"><div className="flex flex-wrap gap-2"><button type="button" className="rounded-lg bg-[#635bff] px-3 py-2 text-xs font-semibold text-white" onClick={syncAndRefresh} disabled={refreshing}>Synchroniser les services</button><button type="button" className="rounded-lg border px-3 py-2 text-xs font-semibold" onClick={importAndRefresh} disabled={refreshing}>Importer la bibliothèque</button></div><div className="space-y-2">{(activity?.items || []).length === 0 && <p className={muted}>Aucune activité serveur.</p>}{(activity?.items || []).map((item) => <div key={`${item.provider}-${item.media_id}`} className={`rounded-xl border p-4 ${card}`}><div className="flex flex-wrap items-center justify-between gap-2"><strong>{item.title || item.media_id}</strong><span className={`text-xs font-semibold ${item.state === 'error' ? 'text-rose-500' : 'text-[#635bff]'}`}>{item.state}</span></div><p className={`mt-1 text-xs ${muted}`}>{item.provider}{item.progress_percent != null ? ` · ${item.progress_percent}%` : ''}{item.last_synced_at ? ` · ${formatDate(item.last_synced_at)}` : ''}</p>{item.last_error && <p className="mt-2 text-xs text-rose-500">{item.last_error}</p>}</div>)}</div></div>}

                                {section === 'requests' && <div className="space-y-3"><h3 className="text-lg font-semibold">Demandes de conservation</h3>{keepRequests.length === 0 && <p className={muted}>Aucune demande en attente.</p>}{keepRequests.map((item) => <div key={item.rental.id} className={`rounded-xl border p-4 ${card}`}><p className="font-semibold">{item.media_title}</p><p className={`mt-1 text-xs ${muted}`}>{item.requester_name} · expire le {formatDate(item.rental.expires_at)}</p></div>)}</div>}

                                {section === 'users' && <div className="space-y-3"><h3 className="text-lg font-semibold">Utilisateurs et droits</h3>{users.map((item) => <div key={item.id} className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4 ${card}`}><div><p className="font-semibold">{item.display_name}</p><p className={`text-xs ${muted}`}>{item.email}</p></div><span className="rounded-full border px-2 py-1 text-[10px] font-semibold uppercase tracking-wider">{item.role}</span></div>)}</div>}

                                {section === 'storage' && <div className="space-y-4"><h3 className="text-lg font-semibold">Stockage et quotas</h3><div className={`rounded-xl border p-4 ${card}`}>{storage ? <><p className="text-sm">Espace temporaire : {storage.temporary_gb} Go / {storage.temporary_max_gb} Go</p><p className={`mt-1 text-sm ${muted}`}>Espace libre : {storage.min_free_gb ?? '—'} Go · seuil : {storage.min_free_threshold_gb ?? '—'} Go</p></> : <p className={muted}>État du stockage indisponible.</p>}</div>{(dashboard?.quotas || []).map((quota) => <div key={quota.user_id} className={`rounded-xl border p-4 ${card}`}><p className="font-semibold">{quota.display_name}</p><p className={`mt-1 text-xs ${muted}`}>{quota.active_rentals}/{quota.max_active_rentals} locations · {quota.temporary_bytes} octets temporaires</p></div>)}</div>}

                                {section === 'services' && <div className="grid gap-3 sm:grid-cols-2">{Object.entries(services || {}).map(([name, status]) => <div key={name} className={`rounded-xl border p-4 ${card}`}><p className="font-semibold capitalize">{name}</p><p className={`mt-2 text-sm ${status.configured ? 'text-emerald-500' : muted}`}>{status.configured ? 'Configuré' : 'Non configuré'}</p></div>)}</div>}

                                {section === 'settings' && <div className={`rounded-xl border p-4 ${card}`}><h3 className="text-lg font-semibold">Paramètres</h3><p className={`mt-2 text-sm ${muted}`}>Les réglages d’administration seront regroupés ici progressivement. Les sauvegardes restent reportées jusqu’à la réception du disque dédié.</p></div>}
                            </>
                        )}
                    </main>
                </div>
            </section>
        </div>
    );
}
