import { useCallback, useEffect, useState } from 'react';
import { acceptKeepRequest, changePassword, createUser, deleteUser, extendRental, fetchCleanupPreview, fetchDevices, fetchJellyfinUsers, fetchKeepRequests, fetchNotifications, fetchStorageStatus, fetchUsers, linkJellyfinUser, markNotificationRead, refuseKeepRequest, revokeDevice, revokeOtherDevices, updateUser } from './api';
import { useAuth } from './auth-context';

export default function AccountPanel({isDarkMode, onClose}) {
    const {user, setUser, logout} = useAuth();
    const [devices, setDevices] = useState([]);
    const [users, setUsers] = useState([]);
    const [jellyfinUsers, setJellyfinUsers] = useState([]);
    const [jellyfinLoading, setJellyfinLoading] = useState(false);
    const [jellyfinSaving, setJellyfinSaving] = useState({});
    const [displayName, setDisplayName] = useState(user.display_name);
    const [newUser, setNewUser] = useState({display_name: '', email: '', password: ''});
    const [passwordForm, setPasswordForm] = useState({current_password: '', new_password: '', password_confirmation: ''});
    const [adminPasswords, setAdminPasswords] = useState({});
    const [keepRequests, setKeepRequests] = useState([]);
    const [notifications, setNotifications] = useState([]);
    const [cleanupPreview, setCleanupPreview] = useState(null);
    const [cleanupLoading, setCleanupLoading] = useState(false);
    const [storageStatus, setStorageStatus] = useState(null);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [savingName, setSavingName] = useState(false);

    const refresh = useCallback(async () => {
        try {
            setError('');
            setDevices(await fetchDevices());
            setNotifications(await fetchNotifications());
            if (user.role === 'admin') {
                setUsers(await fetchUsers());
                setKeepRequests(await fetchKeepRequests());
                try {
                    setStorageStatus(await fetchStorageStatus());
                } catch {
                    setStorageStatus(null);
                }
            }
        } catch (requestError) {
            setError(requestError.message);
        }
    }, [user.role]);

    const refreshJellyfinUsers = useCallback(async () => {
        if (user.role !== 'admin') return;
        try {
            setJellyfinLoading(true);
            setJellyfinUsers(await fetchJellyfinUsers());
        } catch (requestError) {
            setError(requestError.message);
        } finally {
            setJellyfinLoading(false);
        }
    }, [user.role]);

    useEffect(() => {
        refresh();
        refreshJellyfinUsers();
    }, [refresh, refreshJellyfinUsers]);

    const handleCreateUser = async (event) => {
        event.preventDefault();
        try {
            await createUser(newUser);
            setNewUser({display_name: '', email: '', password: ''});
            await refresh();
        } catch (requestError) {
            setError(requestError.message);
        }
    };

    const handleNameSave = async (event) => {
        event.preventDefault();
        try {
            setSavingName(true);
            setError('');
            const updatedUser = await updateUser(user.id, {display_name: displayName});
            setUser(updatedUser);
        } catch (requestError) {
            setError(requestError.message);
        } finally {
            setSavingName(false);
        }
    };

    const handlePasswordChange = async (event) => {
        event.preventDefault();
        try {
            setError('');
            setNotice('');
            await changePassword(passwordForm);
            setPasswordForm({current_password: '', new_password: '', password_confirmation: ''});
            setNotice('Mot de passe modifié. Les autres appareils ont été déconnectés.');
            await refresh();
        } catch (requestError) {
            setError(requestError.message);
        }
    };

    const handleUserUpdate = async (target, fields) => {
        try {
            await updateUser(target.id, fields);
            await refresh();
        } catch (requestError) {
            setError(requestError.message);
        }
    };

    const handleJellyfinLink = async (target, jellyfinUserId) => {
        const previousJellyfinUserId = target.jellyfin_user_id || null;
        const nextJellyfinUserId = jellyfinUserId || null;
        setJellyfinSaving((current) => ({...current, [target.id]: true}));
        setUsers((current) => current.map((item) => item.id === target.id
            ? {...item, jellyfin_user_id: nextJellyfinUserId}
            : item));
        try {
            const updatedUser = await linkJellyfinUser(target.id, nextJellyfinUserId);
            if (target.id === user.id) setUser(updatedUser);
            setNotice(`Compte Jellyfin de ${target.display_name} mis à jour.`);
            await refresh();
        } catch (requestError) {
            setUsers((current) => current.map((item) => item.id === target.id
                ? {...item, jellyfin_user_id: previousJellyfinUserId}
                : item));
            setError(requestError.message);
        } finally {
            setJellyfinSaving((current) => ({...current, [target.id]: false}));
        }
    };

    const handleUserDelete = async (target) => {
        if (!window.confirm(`Supprimer définitivement le compte ${target.display_name} ?`)) return;
        try {
            await deleteUser(target.id);
            await refresh();
        } catch (requestError) {
            setError(requestError.message);
        }
    };

    const handleAdminPassword = async (target) => {
        const password = adminPasswords[target.id] || '';
        if (password.length < 8) {
            setError('Le mot de passe doit contenir au moins 8 caractères.');
            return;
        }
        try {
            setError('');
            setNotice('');
            await updateUser(target.id, {password});
            setAdminPasswords((current) => ({...current, [target.id]: ''}));
            setNotice(`Mot de passe de ${target.display_name} modifié.`);
            await refresh();
        } catch (requestError) {
            setError(requestError.message);
        }
    };

    const handleRetentionAction = async (rentalId, action, noticeText) => {
        try {
            setError('');
            await action(rentalId);
            setNotice(noticeText);
            await refresh();
        } catch (requestError) {
            setError(requestError.message);
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

    return (
        <div className="fixed inset-0 z-[80] bg-black/50 p-4 sm:p-8" onClick={onClose}>
            <section className={`mx-auto max-h-full max-w-3xl overflow-y-auto rounded-2xl border p-6 shadow-2xl ${panel} ${text}`} onClick={(event) => event.stopPropagation()}>
                <div className="mb-6 flex items-start justify-between gap-4">
                    <div>
                        <p className="text-xs font-mono uppercase tracking-widest text-[#635bff]">Compte</p>
                        <h2 className="mt-1 text-2xl font-semibold">{user.display_name}</h2>
                        <p className={`text-sm ${muted}`}>{user.email} · {user.role}</p>
                    </div>
                    <button className="rounded-lg border px-3 py-1.5 text-sm" onClick={onClose}>Fermer</button>
                </div>

                {error && <p className="mb-4 rounded-lg bg-rose-500/10 p-3 text-sm text-rose-500" role="alert">{error}</p>}
                {notice && <p className="mb-4 rounded-lg bg-emerald-500/10 p-3 text-sm text-emerald-500" role="status">{notice}</p>}

                {notifications.length > 0 && (
                    <div className="mb-8">
                        <h3 className="mb-3 font-semibold">Notifications</h3>
                        <div className="space-y-2">
                            {notifications.map((notification) => (
                                <button key={notification.id} type="button" onClick={async () => { if (!notification.read_at) { await markNotificationRead(notification.id); await refresh(); } }} className={`block w-full rounded-lg border p-3 text-left text-sm ${notification.read_at ? 'opacity-60' : 'border-[#635bff]'}`}>
                                    <p>{notification.message}</p>
                                    <p className={`mt-1 text-xs ${muted}`}>{new Date(notification.created_at).toLocaleString()}</p>
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                <form className="mb-8 flex flex-wrap items-end gap-2" onSubmit={handleNameSave}>
                    <label className="grid min-w-56 flex-1 gap-1 text-sm">
                        Nom du compte
                        <input required value={displayName} onChange={(event) => setDisplayName(event.target.value)} className="rounded border bg-transparent px-2 py-2" />
                    </label>
                    <button className="rounded bg-[#635bff] px-3 py-2 text-sm font-semibold text-white" type="submit" disabled={savingName}>
                        {savingName ? 'Enregistrement…' : 'Enregistrer'}
                    </button>
                </form>

                <form className="mb-8 grid gap-2 sm:grid-cols-3" onSubmit={handlePasswordChange}>
                    <h3 className="sm:col-span-3 font-semibold">Changer mon mot de passe</h3>
                    <input required type="password" autoComplete="current-password" placeholder="Mot de passe actuel" value={passwordForm.current_password} onChange={(event) => setPasswordForm({...passwordForm, current_password: event.target.value})} className="rounded border bg-transparent px-2 py-2 text-sm" />
                    <input required minLength="8" type="password" autoComplete="new-password" placeholder="Nouveau mot de passe (8 min.)" value={passwordForm.new_password} onChange={(event) => setPasswordForm({...passwordForm, new_password: event.target.value})} className="rounded border bg-transparent px-2 py-2 text-sm" />
                    <input required minLength="8" type="password" autoComplete="new-password" placeholder="Confirmer le nouveau mot de passe" value={passwordForm.password_confirmation} onChange={(event) => setPasswordForm({...passwordForm, password_confirmation: event.target.value})} className="rounded border bg-transparent px-2 py-2 text-sm" />
                    <button className="rounded bg-[#635bff] px-3 py-2 text-sm font-semibold text-white sm:col-span-3" type="submit">Modifier mon mot de passe</button>
                </form>

                <div className="mb-8">
                    <div className="mb-3 flex items-center justify-between">
                        <h3 className="font-semibold">Appareils mémorisés</h3>
                        <button className="text-xs text-[#635bff]" onClick={async () => { await revokeOtherDevices(); await refresh(); }}>Révoquer les autres</button>
                    </div>
                    <div className="space-y-2">
                        {devices.map((device) => (
                            <div key={device.id} className={`flex items-center justify-between gap-3 rounded-lg border p-3 text-sm ${isDarkMode ? 'border-white/10' : 'border-[#e3e8ee]'}`}>
                                <div>
                                    <p>{device.user_agent || 'Navigateur inconnu'} {device.current && <span className="text-xs text-[#635bff]">(actuel)</span>}</p>
                                    <p className={`text-xs ${muted}`}>Dernière activité : {new Date(device.last_seen_at).toLocaleString()}</p>
                                </div>
                                <button className="text-xs text-rose-500" onClick={async () => { await revokeDevice(device.id); await refresh(); }}>Révoquer</button>
                            </div>
                        ))}
                    </div>
                </div>

                {user.role === 'admin' && (
                    <div>
                        <div className="mb-8">
                            <h3 className="mb-3 font-semibold">Espace de stockage</h3>
                            {storageStatus ? (
                                <div className={`rounded-lg border p-3 text-sm ${storageStatus.low_space || storageStatus.temporary_quota_reached ? 'border-amber-500' : ''}`}>
                                    <p>
                                        Libre : {storageStatus.min_free_gb === null ? 'inconnu' : `${storageStatus.min_free_gb} Go`}
                                        {' '} / seuil {storageStatus.min_free_threshold_gb} Go
                                    </p>
                                    <p className={muted}>
                                        Locations temporaires : {storageStatus.temporary_gb} Go / {storageStatus.temporary_max_gb} Go
                                    </p>
                                    {(storageStatus.low_space || storageStatus.temporary_quota_reached) && <p className="mt-1 text-amber-600">Les nouvelles locations sont bloquées jusqu'à libération d'espace.</p>}
                                </div>
                            ) : <p className={`rounded-lg border p-3 text-sm ${muted}`}>État du stockage indisponible.</p>}
                        </div>
                        <div className="mb-8">
                            <h3 className="mb-3 font-semibold">Demandes de conservation</h3>
                            <div className="space-y-2">
                                {keepRequests.length === 0 && <p className={`rounded-lg border p-3 text-sm ${muted}`}>Aucune demande en attente.</p>}
                                {keepRequests.map((item) => (
                                    <div key={item.rental.id} className="rounded-lg border p-3 text-sm">
                                        <div className="flex flex-wrap items-start justify-between gap-3">
                                            <div>
                                                <p className="font-semibold">{item.media_title}</p>
                                                <p className={`text-xs ${muted}`}>{item.requester_name}</p>
                                                <p className={`text-xs ${muted}`}>Expire le {item.rental.expires_at ? new Date(item.rental.expires_at).toLocaleDateString() : '—'}</p>
                                            </div>
                                            <div className="flex flex-wrap gap-2">
                                                <button type="button" className="rounded bg-emerald-600 px-2 py-1 text-xs font-semibold text-white" onClick={() => handleRetentionAction(item.rental.id, acceptKeepRequest, 'Film conservé définitivement.')}>Conserver définitivement</button>
                                                <button type="button" className="rounded border border-rose-500 px-2 py-1 text-xs text-rose-500" onClick={() => handleRetentionAction(item.rental.id, refuseKeepRequest, 'Demande refusée.')}>Refuser</button>
                                                <button type="button" className="rounded border border-[#635bff] px-2 py-1 text-xs text-[#635bff]" onClick={() => handleRetentionAction(item.rental.id, extendRental, 'Location prolongée de 7 jours.')}>Prolonger de 7 jours</button>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div className="mb-8">
                            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                                <h3 className="font-semibold">Aperçu du nettoyage (simulation)</h3>
                                <button type="button" className="rounded border border-[#635bff] px-2 py-1 text-xs text-[#635bff]" onClick={handleCleanupPreview} disabled={cleanupLoading}>
                                    {cleanupLoading ? 'Analyse…' : 'Analyser les expirations'}
                                </button>
                            </div>
                            {cleanupPreview && <>
                                <p className={`mb-3 rounded-lg border p-3 text-xs ${muted}`}>Aucune suppression réelle. {cleanupPreview.message}</p>
                                <div className="space-y-2">
                                    {cleanupPreview.items.length === 0 && <p className={`rounded-lg border p-3 text-sm ${muted}`}>Aucun contenu arrivé à expiration.</p>}
                                    {cleanupPreview.items.map((item) => (
                                        <div key={item.rental_id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-sm">
                                            <div><strong>{item.media_title}</strong><p className={`text-xs ${muted}`}>{item.expires_at ? `Expiré le ${new Date(item.expires_at).toLocaleDateString()}` : 'Sans expiration'}</p></div>
                                            <span className={item.action === 'protected' ? 'text-emerald-600' : 'text-amber-600'}>{item.action === 'protected' ? `Protégé : ${item.reason}` : 'Serait supprimé'}</span>
                                        </div>
                                    ))}
                                </div>
                            </>}
                        </div>
                        <h3 className="mb-3 font-semibold">Utilisateurs</h3>
                        <div className="mb-4 space-y-2">
                            {users.map((target) => (
                                <div key={target.id} className={`flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 text-sm ${isDarkMode ? 'border-white/10' : 'border-[#e3e8ee]'}`}>
                                    <div>
                                        <div className="flex flex-wrap items-center gap-2">
                                            <input
                                                value={target.display_name}
                                                onChange={(event) => setUsers((current) => current.map((item) => item.id === target.id ? {...item, display_name: event.target.value} : item))}
                                                className="w-36 rounded border bg-transparent px-2 py-1 text-sm"
                                                aria-label={`Nom de ${target.email}`}
                                            />
                                            <button className="text-xs text-[#635bff]" onClick={() => handleUserUpdate(target, {display_name: target.display_name})}>Enregistrer</button>
                                        </div>
                                        <p className={`text-xs ${muted}`}>{target.email}</p>
                                        <p className={`text-xs ${target.is_active ? 'text-emerald-500' : 'text-rose-500'}`}>{target.is_active ? 'Actif' : 'Désactivé'}</p>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <select
                                            value={target.jellyfin_user_id || ''}
                                            onChange={(event) => handleJellyfinLink(target, event.target.value)}
                                            disabled={jellyfinLoading || jellyfinSaving[target.id]}
                                            className="max-w-48 rounded border bg-transparent px-2 py-1 text-xs"
                                            aria-label={`Compte Jellyfin de ${target.email}`}
                                        >
                                            <option value="">Jellyfin : Non associé</option>
                                            {jellyfinUsers.map((jellyfinUser) => {
                                                const linkedToOther = users.some((item) => item.id !== target.id && item.jellyfin_user_id === jellyfinUser.id);
                                                return (
                                                    <option key={jellyfinUser.id} value={jellyfinUser.id} disabled={linkedToOther}>
                                                        {jellyfinUser.name}{linkedToOther ? ' — déjà associé' : ''}
                                                    </option>
                                                );
                                            })}
                                        </select>
                                        <input
                                            type="password"
                                            minLength="8"
                                            placeholder="Nouveau mot de passe"
                                            value={adminPasswords[target.id] || ''}
                                            onChange={(event) => setAdminPasswords((current) => ({...current, [target.id]: event.target.value}))}
                                            className="w-36 rounded border bg-transparent px-2 py-1 text-xs"
                                            aria-label={`Nouveau mot de passe de ${target.email}`}
                                        />
                                        <button type="button" className="text-xs text-[#635bff]" onClick={() => handleAdminPassword(target)}>Définir</button>
                                        <select value={target.role} onChange={(event) => handleUserUpdate(target, {role: event.target.value})} className="rounded border bg-transparent px-2 py-1 text-xs">
                                            <option value="user">Utilisateur</option>
                                            <option value="admin">Administrateur</option>
                                        </select>
                                        <button className="text-xs text-[#635bff]" onClick={() => handleUserUpdate(target, {is_active: !target.is_active})}>
                                            {target.is_active ? 'Désactiver' : 'Activer'}
                                        </button>
                                        <button className="text-xs text-rose-500" onClick={() => handleUserDelete(target)}>Supprimer</button>
                                    </div>
                                </div>
                            ))}
                        </div>
                        <form className="grid gap-2 sm:grid-cols-3" onSubmit={handleCreateUser}>
                            <input required placeholder="Nom" value={newUser.display_name} onChange={(event) => setNewUser({...newUser, display_name: event.target.value})} className="rounded border bg-transparent px-2 py-2 text-sm" />
                            <input required type="email" placeholder="Email" value={newUser.email} onChange={(event) => setNewUser({...newUser, email: event.target.value})} className="rounded border bg-transparent px-2 py-2 text-sm" />
                            <input required minLength="8" type="password" placeholder="Mot de passe (8 caractères min.)" value={newUser.password} onChange={(event) => setNewUser({...newUser, password: event.target.value})} className="rounded border bg-transparent px-2 py-2 text-sm" />
                            <button className="rounded bg-[#635bff] px-3 py-2 text-sm font-semibold text-white sm:col-span-3" type="submit">Créer un utilisateur</button>
                        </form>
                    </div>
                )}

                <button className="mt-8 rounded-lg border border-rose-500/40 px-3 py-2 text-sm text-rose-500" onClick={logout}>Se déconnecter</button>
            </section>
        </div>
    );
}
