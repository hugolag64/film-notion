import { useCallback, useEffect, useState } from 'react';
import { acceptKeepRequest, createBackup, deleteStorageCandidate, extendRental, fetchAdminDashboard, fetchBackupStatus, fetchCleanupPreview, fetchKeepRequests, fetchMediaServerActivity, fetchMediaServerStatus, fetchStorageOverview, fetchStorageStatus, fetchUsers, refuseKeepRequest, setStorageProtection, verifyBackup, importMediaServerLibrary, syncMediaServer } from '../api';
import { useAuth } from '../auth-context';
import UserManagement from './UserManagement';

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

function availabilityLabel(state) {
    return {
        requested: 'Demandé',
        searching: 'Recherche',
        downloading: 'Téléchargement',
        imported: 'Téléchargé — Jellyfin non confirmé',
        available: 'Disponible sur Jellyfin',
        error: 'Erreur',
    }[state] || state;
}

function formatBytes(value) {
    if (!value) return '0 octet';
    const units = ['octets', 'Ko', 'Mo', 'Go', 'To'];
    let amount = value;
    let unit = 0;
    while (amount >= 1024 && unit < units.length - 1) {
        amount /= 1024;
        unit += 1;
    }
    return `${amount >= 10 || unit === 0 ? Math.round(amount) : amount.toFixed(1)} ${units[unit]}`;
}

const protectionLabels = {
    favorite: 'Favori',
    active_rental: 'Location active',
    recently_added: 'Ajouté il y a moins de 14 jours',
    recently_watched: 'Visionné il y a moins de 30 jours',
    manual: 'Protection manuelle',
};

function StorageCleanup({candidates, history, card, muted, onChanged, onError, onNotice}) {
    const [busyId, setBusyId] = useState(null);
    const [filter, setFilter] = useState('all');
    const visibleCandidates = candidates.filter((candidate) => filter === 'all' || (filter === 'protected' ? candidate.protected : !candidate.protected));

    const toggleProtection = async (candidate) => {
        try {
            setBusyId(candidate.media_id);
            await setStorageProtection(candidate.media_id, !candidate.protection_reasons.includes('manual'));
            await onChanged();
        } catch (requestError) {
            onError(requestError.message);
        } finally {
            setBusyId(null);
        }
    };

    const removeCandidate = async (candidate) => {
        if (candidate.protected || !window.confirm(`Supprimer « ${candidate.title} » de Radarr et du disque ?\n\nEspace libéré estimé : ${formatBytes(candidate.size_bytes)}\nLa fiche Backstage sera conservée.`)) return;
        try {
            setBusyId(candidate.media_id);
            const result = await deleteStorageCandidate(candidate.media_id);
            onNotice(`${candidate.title} supprimé. ${formatBytes(result.freed_bytes)} libérés.`);
            await onChanged();
        } catch (requestError) {
            onError(requestError.message);
        } finally {
            setBusyId(null);
        }
    };

    return <div className={`rounded-xl border p-4 ${card}`}>
        <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-lg font-semibold">Libérer de l’espace</h3><p className={`mt-1 text-sm ${muted}`}>Films présents sur le disque. Les protections empêchent toute suppression accidentelle.</p></div><div className="flex items-center gap-2"><select className="rounded border bg-transparent px-2 py-1 text-xs" value={filter} onChange={(event) => setFilter(event.target.value)} aria-label="Filtrer le nettoyage"><option value="all">Tous</option><option value="protected">Protégés</option><option value="deletable">Supprimables</option></select><button type="button" className="rounded border px-2 py-1 text-xs" onClick={onChanged}>Actualiser</button></div></div>
        {visibleCandidates.length === 0 ? <p className={`mt-4 rounded-lg border p-3 text-sm ${muted}`}>Aucun film dans ce filtre.</p> : <div className="mt-4 space-y-2">{visibleCandidates.map((candidate) => <div key={candidate.media_id} className="rounded-lg border p-3"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-semibold">{candidate.title}</p><p className={`mt-1 text-xs ${muted}`}>{formatBytes(candidate.size_bytes)}{candidate.last_played_at ? ` · dernière lecture ${formatDate(candidate.last_played_at)}` : ''}{candidate.added_at ? ` · ajouté le ${formatDate(candidate.added_at)}` : ''}</p></div><span className={candidate.protected ? 'text-xs font-semibold text-amber-600' : 'text-xs font-semibold text-emerald-600'}>{candidate.protected ? 'Protégé' : 'Supprimable'}</span></div>{candidate.protection_reasons.length > 0 && <p className={`mt-2 text-xs ${muted}`}>{candidate.protected ? candidate.protection_reasons.map((reason) => protectionLabels[reason] || reason).join(' · ') : `Suggestion de conservation : ${candidate.protection_reasons.map((reason) => protectionLabels[reason] || reason).join(' · ')}`}</p>}<div className="mt-3 flex flex-wrap gap-2"><button type="button" className="rounded border px-2 py-1 text-xs" onClick={() => toggleProtection(candidate)} disabled={busyId === candidate.media_id}>{candidate.protection_reasons.includes('manual') ? 'Retirer la protection' : 'Protéger manuellement'}</button><button type="button" className="rounded bg-rose-600 px-2 py-1 text-xs font-semibold text-white disabled:opacity-50" onClick={() => removeCandidate(candidate)} disabled={busyId === candidate.media_id || candidate.protected}>{busyId === candidate.media_id ? 'Opération…' : 'Supprimer du disque'}</button></div></div>)}</div>}
        {history.length > 0 && <div className="mt-5"><h4 className="text-sm font-semibold">Historique des suppressions</h4><div className="mt-2 space-y-1">{history.slice(0, 5).map((entry) => <p key={entry.id} className={`text-xs ${muted}`}>{entry.media_title} · {formatBytes(entry.size_bytes)} · {formatDate(entry.deleted_at)}</p>)}</div></div>}
    </div>;
}

export default function AdminCenter({isDarkMode, onClose, onMediaChanged}) {
    const {user} = useAuth();
    const [section, setSection] = useState('overview');
    const [dashboard, setDashboard] = useState(null);
    const [activity, setActivity] = useState(null);
    const [keepRequests, setKeepRequests] = useState([]);
    const [users, setUsers] = useState([]);
    const [storage, setStorage] = useState(null);
    const [storageCandidates, setStorageCandidates] = useState([]);
    const [storageCleanupHistory, setStorageCleanupHistory] = useState([]);
    const [services, setServices] = useState(null);
    const [backupStatus, setBackupStatus] = useState(null);
    const [cleanupPreview, setCleanupPreview] = useState(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [backupLoading, setBackupLoading] = useState(false);
    const [backupVerifying, setBackupVerifying] = useState(false);
    const [cleanupLoading, setCleanupLoading] = useState(false);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');

    const load = useCallback(async () => {
        try {
            setError('');
            const [nextDashboard, nextActivity, nextKeepRequests, nextUsers, nextStorage, nextServices, nextBackup, nextStorageOverview] = await Promise.all([
                fetchAdminDashboard(),
                fetchMediaServerActivity(),
                fetchKeepRequests(),
                fetchUsers(),
                fetchStorageStatus(),
                fetchMediaServerStatus(),
                fetchBackupStatus().catch(() => null),
                fetchStorageOverview().catch(() => ({candidates: [], history: []})),
            ]);
            setDashboard(nextDashboard);
            setActivity(nextActivity);
            setKeepRequests(nextKeepRequests);
            setUsers(nextUsers);
            setStorage(nextStorage);
            setServices(nextServices);
            setBackupStatus(nextBackup);
            setStorageCandidates(nextStorageOverview.candidates || []);
            setStorageCleanupHistory(nextStorageOverview.history || []);
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

    const handleRetentionAction = async (rentalId, action, noticeText) => {
        try {
            setError('');
            await action(rentalId);
            setNotice(noticeText);
            await load();
        } catch (requestError) {
            setError(requestError.message);
        }
    };

    const handleBackup = async () => {
        try {
            setBackupLoading(true);
            setError('');
            await createBackup();
            setNotice('Sauvegarde créée et vérifiée.');
            setBackupStatus(await fetchBackupStatus());
        } catch (requestError) {
            setError(requestError.message);
        } finally {
            setBackupLoading(false);
        }
    };

    const handleBackupVerify = async () => {
        try {
            setBackupVerifying(true);
            setError('');
            await verifyBackup();
            setNotice('La dernière sauvegarde est lisible et intègre.');
        } catch (requestError) {
            setError(requestError.message);
        } finally {
            setBackupVerifying(false);
        }
    };

    const handleCleanupPreview = async () => {
        try {
            setCleanupLoading(true);
            setError('');
            setCleanupPreview(await fetchCleanupPreview());
        } catch (requestError) {
            setError(requestError.message);
        } finally {
            setCleanupLoading(false);
        }
    };

    const text = isDarkMode ? 'text-white' : 'text-[#0a2540]';
    const muted = isDarkMode ? 'text-white/60' : 'text-[#425466]';
    const panel = isDarkMode ? 'bg-[#111111] border-white/10' : 'bg-white border-[#e3e8ee]';
    const card = isDarkMode ? 'border-white/10 bg-white/[0.03]' : 'border-[#e3e8ee] bg-white';
    const openSection = (nextSection) => setSection(nextSection);

    return (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 p-3 backdrop-blur-md sm:p-6" onClick={onClose}>
            <section className={`flex h-[min(94vh,900px)] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border shadow-2xl ${panel} ${text}`} onClick={(event) => event.stopPropagation()}>
                <header className="flex flex-wrap items-center justify-between gap-3 border-b border-inherit px-5 py-4 sm:px-7">
                    <div>
                        <p className="text-[10px] font-mono uppercase tracking-[0.24em] text-[#635bff]">Backstage / Admin</p>
                        <h2 className="mt-1 text-2xl font-semibold">Centre d’administration</h2>
                    </div>
                    <div className="flex items-center gap-2">
                        <button type="button" className="rounded-lg border px-3 py-2 text-xs font-semibold" onClick={refresh} disabled={refreshing}>{refreshing ? 'Actualisation…' : 'Actualiser'}</button>
                        <button type="button" className="rounded-lg border px-3 py-2 text-xs font-semibold" onClick={onClose}>Fermer</button>
                    </div>
                </header>

                <div className="flex min-h-0 flex-1 flex-col sm:flex-row">
                    <nav className={`flex shrink-0 gap-1 overflow-x-auto border-b p-3 sm:w-52 sm:flex-col sm:overflow-y-auto sm:border-b-0 sm:border-r ${isDarkMode ? 'border-white/10' : 'border-[#e3e8ee]'}`} aria-label="Administration">
                        {SECTIONS.map(([id, label]) => <button key={id} type="button" onClick={() => openSection(id)} className={`whitespace-nowrap rounded-lg px-3 py-2 text-left text-xs font-semibold transition ${section === id ? 'bg-[#635bff] text-white' : isDarkMode ? 'text-white/60 hover:bg-white/10 hover:text-white' : 'text-[#425466] hover:bg-[#f6f9fc] hover:text-[#0a2540]'}`}>{label}</button>)}
                    </nav>

                    <main className="min-h-0 flex-1 overflow-y-auto p-5 sm:p-7">
                        {error && <p className="mb-4 rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-500" role="alert">{error}</p>}
                        {notice && <p className="mb-4 rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-emerald-500" role="status">{notice}</p>}
                        {loading ? <p className={muted}>Chargement du centre d’administration…</p> : (
                            <>
                                {section === 'overview' && <div className="space-y-5">
                                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                                        <button type="button" onClick={() => openSection('requests')} className={`rounded-xl border p-4 text-left transition hover:border-[#635bff] ${card}`}><p className={`text-xs ${muted}`}>Expirations proches</p><p className="mt-2 text-3xl font-semibold">{dashboard?.expiring?.length || 0}</p></button>
                                        <button type="button" onClick={() => openSection('activity')} className={`rounded-xl border p-4 text-left transition hover:border-[#635bff] ${card}`}><p className={`text-xs ${muted}`}>Téléchargements</p><p className="mt-2 text-3xl font-semibold">{dashboard?.downloads?.length || 0}</p></button>
                                        <button type="button" onClick={() => openSection('activity')} className={`rounded-xl border p-4 text-left transition hover:border-[#635bff] ${card}`}><p className={`text-xs ${muted}`}>Erreurs</p><p className="mt-2 text-3xl font-semibold">{dashboard?.errors?.length || 0}</p></button>
                                        <button type="button" onClick={() => openSection('requests')} className={`rounded-xl border p-4 text-left transition hover:border-[#635bff] ${card}`}><p className={`text-xs ${muted}`}>Demandes de conservation</p><p className="mt-2 text-3xl font-semibold">{keepRequests.length}</p></button>
                                    </div>
                                    <div className="grid gap-3 lg:grid-cols-2">
                                        <button type="button" onClick={() => openSection('storage')} className={`rounded-xl border p-4 text-left transition hover:border-[#635bff] ${card}`}><h3 className="font-semibold">Stockage</h3><p className={`mt-2 text-sm ${muted}`}>{storage ? `${storage.temporary_gb} Go temporaires · ${storage.min_free_gb ?? '—'} Go libres` : 'État indisponible'}</p></button>
                                        <button type="button" onClick={() => openSection('users')} className={`rounded-xl border p-4 text-left transition hover:border-[#635bff] ${card}`}><h3 className="font-semibold">Utilisateurs</h3><p className={`mt-2 text-sm ${muted}`}>{users.length} compte(s) configuré(s) · cliquer pour gérer</p></button>
                                    </div>
                                </div>}

                                {section === 'activity' && <div className="space-y-4"><div className="flex flex-wrap gap-2"><button type="button" className="rounded-lg bg-[#635bff] px-3 py-2 text-xs font-semibold text-white" onClick={syncAndRefresh} disabled={refreshing}>Synchroniser les services</button><button type="button" className="rounded-lg border px-3 py-2 text-xs font-semibold" onClick={importAndRefresh} disabled={refreshing}>Importer la bibliothèque</button></div><div className="space-y-2">{(activity?.items || []).length === 0 && <p className={muted}>Aucune activité serveur.</p>}{(activity?.items || []).map((item) => <div key={`${item.provider}-${item.media_id}`} className={`rounded-xl border p-4 ${card}`}><div className="flex flex-wrap items-center justify-between gap-2"><strong>{item.title || item.media_id}</strong><span className={`text-xs font-semibold ${item.state === 'error' ? 'text-rose-500' : 'text-[#635bff]'}`}>{availabilityLabel(item.state)}</span></div><p className={`mt-1 text-xs ${muted}`}>{item.media_type || 'Média'} · {item.provider}{item.progress_percent != null ? ` · ${item.progress_percent}%` : ''}{item.last_synced_at ? ` · ${formatDate(item.last_synced_at)}` : ''}</p>{item.last_error && <p className="mt-2 text-xs text-rose-500">{item.last_error}</p>}</div>)}</div></div>}

                                {section === 'requests' && <div className="space-y-3"><h3 className="text-lg font-semibold">Demandes de conservation</h3>{keepRequests.length === 0 && <p className={`rounded-lg border p-3 text-sm ${muted}`}>Aucune demande en attente.</p>}{keepRequests.map((item) => <div key={item.rental.id} className={`rounded-xl border p-4 ${card}`}><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-semibold">{item.media_title}</p><p className={`mt-1 text-xs ${muted}`}>{item.requester_name} · expire le {formatDate(item.rental.expires_at)}</p></div><div className="flex flex-wrap gap-2"><button type="button" className="rounded bg-emerald-600 px-2 py-1 text-xs font-semibold text-white" onClick={() => handleRetentionAction(item.rental.id, acceptKeepRequest, 'Film conservé définitivement.')}>Conserver</button><button type="button" className="rounded border border-rose-500 px-2 py-1 text-xs text-rose-500" onClick={() => handleRetentionAction(item.rental.id, refuseKeepRequest, 'Demande refusée.')}>Refuser</button><button type="button" className="rounded border border-[#635bff] px-2 py-1 text-xs text-[#635bff]" onClick={() => handleRetentionAction(item.rental.id, extendRental, 'Location prolongée de 7 jours.')}>Prolonger</button></div></div></div>)}</div>}

                                {section === 'users' && <UserManagement isDarkMode={isDarkMode} currentUser={user} onError={setError} onNotice={setNotice} onChanged={load} />}

                                {section === 'storage' && <div className="space-y-4"><h3 className="text-lg font-semibold">Stockage et quotas</h3><div className={`rounded-xl border p-4 ${card}`}>{storage ? <><p className="text-sm">Espace temporaire : {storage.temporary_gb} Go / {storage.temporary_max_gb} Go</p><p className={`mt-1 text-sm ${muted}`}>Espace libre : {storage.min_free_gb ?? '—'} Go · seuil : {storage.min_free_threshold_gb ?? '—'} Go</p></> : <p className={muted}>État du stockage indisponible.</p>}</div>{(dashboard?.quotas || []).map((quota) => <div key={quota.user_id} className={`rounded-xl border p-4 ${card}`}><p className="font-semibold">{quota.display_name}</p><p className={`mt-1 text-xs ${muted}`}>{quota.active_rentals}/{quota.max_active_rentals} locations · {quota.temporary_bytes} octets temporaires</p></div>)}<StorageCleanup candidates={storageCandidates} history={storageCleanupHistory} card={card} muted={muted} onChanged={load} onError={setError} onNotice={setNotice} /></div>}

                                {section === 'services' && <div className="grid gap-3 sm:grid-cols-2">{Object.entries(services || {}).map(([name, status]) => <div key={name} className={`rounded-xl border p-4 ${card}`}><p className="font-semibold capitalize">{name}</p><p className={`mt-2 text-sm ${status.configured ? 'text-emerald-500' : muted}`}>{status.configured ? 'Configuré' : 'Non configuré'}</p></div>)}</div>}

                                {section === 'settings' && <div className="space-y-5"><div className={`rounded-xl border p-4 ${card}`}><div className="flex flex-wrap items-center justify-between gap-2"><div><h3 className="text-lg font-semibold">Sauvegarde</h3><p className={`mt-1 text-sm ${muted}`}>Pilotage des sauvegardes de la bibliothèque.</p></div><div className="flex gap-2"><button type="button" className="rounded border border-[#635bff] px-3 py-2 text-xs text-[#635bff]" onClick={handleBackup} disabled={backupLoading}>{backupLoading ? 'Sauvegarde…' : 'Sauvegarder maintenant'}</button><button type="button" className="rounded border px-3 py-2 text-xs" onClick={handleBackupVerify} disabled={backupVerifying || !backupStatus?.latest}>{backupVerifying ? 'Vérification…' : 'Vérifier'}</button></div></div>{backupStatus?.latest ? <p className={`mt-3 rounded-lg border p-3 text-sm ${backupStatus.latest.integrity === 'ok' ? '' : 'border-rose-500 text-rose-500'}`}>Dernière sauvegarde : {formatDate(backupStatus.latest.created_at)} · {Math.round(backupStatus.latest.size_bytes / 1024)} Ko · {backupStatus.latest.integrity === 'ok' ? 'Intègre' : 'À vérifier'}</p> : <p className={`mt-3 rounded-lg border p-3 text-sm ${muted}`}>Aucune sauvegarde détectée.</p>}</div><div className={`rounded-xl border p-4 ${card}`}><div className="flex flex-wrap items-center justify-between gap-2"><div><h3 className="text-lg font-semibold">Aperçu du nettoyage</h3><p className={`mt-1 text-sm ${muted}`}>Simulation uniquement : aucune suppression automatique.</p></div><button type="button" className="rounded border border-[#635bff] px-3 py-2 text-xs text-[#635bff]" onClick={handleCleanupPreview} disabled={cleanupLoading}>{cleanupLoading ? 'Analyse…' : 'Analyser les expirations'}</button></div>{cleanupPreview && <div className="mt-3 space-y-2"><p className={`rounded-lg border p-3 text-xs ${muted}`}>{cleanupPreview.message}</p>{cleanupPreview.items.map((item) => <div key={item.rental_id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-sm"><span>{item.media_title}</span><span className={item.action === 'protected' ? 'text-emerald-600' : 'text-amber-600'}>{item.action === 'protected' ? `Protégé : ${item.reason}` : 'Serait supprimé'}</span></div>)}</div>}</div><div className={`rounded-xl border p-4 ${card}`}><h3 className="text-lg font-semibold">Paramètres</h3><p className={`mt-2 text-sm ${muted}`}>Les réglages de pilotage sont regroupés ici. Les sauvegardes peuvent rester désactivées selon la configuration du serveur.</p></div></div>}
                            </>
                        )}
                    </main>
                </div>
            </section>
        </div>
    );
}
