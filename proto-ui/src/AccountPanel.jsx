import { useCallback, useEffect, useState } from 'react';
import { changePassword, fetchDevices, fetchNotifications, markNotificationRead, revokeDevice, revokeOtherDevices, updateUser } from './api';
import { useAuth } from './auth-context';

export default function AccountPanel({isDarkMode, onClose}) {
    const {user, setUser, logout} = useAuth();
    const [devices, setDevices] = useState([]);
    const [notifications, setNotifications] = useState([]);
    const [displayName, setDisplayName] = useState(user.display_name);
    const [passwordForm, setPasswordForm] = useState({current_password: '', new_password: '', password_confirmation: ''});
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [savingName, setSavingName] = useState(false);

    const refresh = useCallback(async () => {
        try {
            setError('');
            setDevices(await fetchDevices());
            setNotifications(await fetchNotifications());
        } catch (requestError) {
            setError(requestError.message);
        }
    }, []);

    useEffect(() => {
        refresh();
    }, [refresh]);

    const handleNameSave = async (event) => {
        event.preventDefault();
        try {
            setSavingName(true);
            setError('');
            const updatedUser = await updateUser(user.id, {display_name: displayName});
            setUser(updatedUser);
            setNotice('Nom du compte mis à jour.');
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

    const text = isDarkMode ? 'text-white' : 'text-[#0a2540]';
    const muted = isDarkMode ? 'text-white/60' : 'text-[#425466]';
    const panel = isDarkMode ? 'bg-[#111111] border-white/10' : 'bg-white border-[#e3e8ee]';

    return (
        <div className="fixed inset-0 z-[80] bg-black/50 p-4 sm:p-8" onClick={onClose}>
            <section className={`mx-auto max-h-full max-w-3xl overflow-y-auto rounded-2xl border p-6 shadow-2xl ${panel} ${text}`} onClick={(event) => event.stopPropagation()}>
                <div className="mb-6 flex items-start justify-between gap-4">
                    <div>
                        <p className="text-xs font-mono uppercase tracking-widest text-[#635bff]">Mon compte</p>
                        <h2 className="mt-1 text-2xl font-semibold">{user.display_name}</h2>
                        <p className={`text-sm ${muted}`}>{user.email} · {user.role === 'admin' ? 'Administrateur' : 'Utilisateur'}</p>
                    </div>
                    <button className="rounded-lg border px-3 py-1.5 text-sm" onClick={onClose}>Fermer</button>
                </div>

                {error && <p className="mb-4 rounded-lg bg-rose-500/10 p-3 text-sm text-rose-500" role="alert">{error}</p>}
                {notice && <p className="mb-4 rounded-lg bg-emerald-500/10 p-3 text-sm text-emerald-500" role="status">{notice}</p>}

                {notifications.length > 0 && (
                    <div className="mb-8">
                        <h3 className="mb-3 font-semibold">Mes notifications</h3>
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
                    <button className="rounded bg-[#635bff] px-3 py-2 text-sm font-semibold text-white" type="submit" disabled={savingName}>{savingName ? 'Enregistrement…' : 'Enregistrer'}</button>
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
                        <h3 className="font-semibold">Mes appareils mémorisés</h3>
                        <button type="button" className="text-xs text-[#635bff]" onClick={async () => { await revokeOtherDevices(); await refresh(); }}>Révoquer les autres</button>
                    </div>
                    <div className="space-y-2">
                        {devices.map((device) => (
                            <div key={device.id} className={`flex items-center justify-between gap-3 rounded-lg border p-3 text-sm ${isDarkMode ? 'border-white/10' : 'border-[#e3e8ee]'}`}>
                                <div>
                                    <p>{device.user_agent || 'Navigateur inconnu'} {device.current && <span className="text-xs text-[#635bff]">(actuel)</span>}</p>
                                    <p className={`text-xs ${muted}`}>Dernière activité : {new Date(device.last_seen_at).toLocaleString()}</p>
                                </div>
                                <button type="button" className="text-xs text-rose-500" onClick={async () => { await revokeDevice(device.id); await refresh(); }}>Révoquer</button>
                            </div>
                        ))}
                        {devices.length === 0 && <p className={`rounded-lg border p-3 text-sm ${muted}`}>Aucun appareil mémorisé.</p>}
                    </div>
                </div>

                <button type="button" className="rounded-lg border border-rose-500/40 px-3 py-2 text-sm text-rose-500" onClick={logout}>Se déconnecter</button>
            </section>
        </div>
    );
}
