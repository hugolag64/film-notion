import { useCallback, useEffect, useState } from 'react';
import { createUser, deleteUser, fetchDevices, fetchUsers, revokeDevice, revokeOtherDevices, updateUser } from './api';
import { useAuth } from './auth-context';

export default function AccountPanel({isDarkMode, onClose}) {
    const {user, setUser, logout} = useAuth();
    const [devices, setDevices] = useState([]);
    const [users, setUsers] = useState([]);
    const [displayName, setDisplayName] = useState(user.display_name);
    const [newUser, setNewUser] = useState({display_name: '', email: '', password: ''});
    const [error, setError] = useState('');
    const [savingName, setSavingName] = useState(false);

    const refresh = useCallback(async () => {
        try {
            setError('');
            setDevices(await fetchDevices());
            if (user.role === 'admin') setUsers(await fetchUsers());
        } catch (requestError) {
            setError(requestError.message);
        }
    }, [user.role]);

    useEffect(() => { refresh(); }, [refresh]);

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

    const handleUserUpdate = async (target, fields) => {
        try {
            await updateUser(target.id, fields);
            await refresh();
        } catch (requestError) {
            setError(requestError.message);
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

                <form className="mb-8 flex flex-wrap items-end gap-2" onSubmit={handleNameSave}>
                    <label className="grid min-w-56 flex-1 gap-1 text-sm">
                        Nom du compte
                        <input required value={displayName} onChange={(event) => setDisplayName(event.target.value)} className="rounded border bg-transparent px-2 py-2" />
                    </label>
                    <button className="rounded bg-[#635bff] px-3 py-2 text-sm font-semibold text-white" type="submit" disabled={savingName}>
                        {savingName ? 'Enregistrement…' : 'Enregistrer'}
                    </button>
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
                        <h3 className="mb-3 font-semibold">Utilisateurs</h3>
                        <div className="mb-4 space-y-2">
                            {users.map((target) => (
                                <div key={target.id} className={`flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 text-sm ${isDarkMode ? 'border-white/10' : 'border-[#e3e8ee]'}`}>
                                    <div>
                                        <p>{target.display_name} <span className={`text-xs ${muted}`}>{target.email}</span></p>
                                        <p className={`text-xs ${target.is_active ? 'text-emerald-500' : 'text-rose-500'}`}>{target.is_active ? 'Actif' : 'Désactivé'}</p>
                                    </div>
                                    <div className="flex items-center gap-2">
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
