import { useCallback, useEffect, useState } from 'react';
import { createUser, deleteUser, fetchJellyfinUsers, fetchUsers, linkJellyfinUser, updateUser } from '../api';

export default function UserManagement({isDarkMode, currentUser, onError, onNotice, onChanged}) {
    const [users, setUsers] = useState([]);
    const [jellyfinUsers, setJellyfinUsers] = useState([]);
    const [expandedUserId, setExpandedUserId] = useState(null);
    const [jellyfinLoading, setJellyfinLoading] = useState(false);
    const [jellyfinSaving, setJellyfinSaving] = useState({});
    const [adminPasswords, setAdminPasswords] = useState({});
    const [newUser, setNewUser] = useState({display_name: '', email: '', password: ''});

    const refresh = useCallback(async () => {
        setJellyfinLoading(true);
        try {
            setUsers(await fetchUsers());
            setJellyfinUsers(await fetchJellyfinUsers());
            await onChanged?.();
        } catch (requestError) {
            onError?.(requestError.message);
        } finally {
            setJellyfinLoading(false);
        }
    }, [onChanged, onError]);

    useEffect(() => {
        refresh();
    }, [refresh]);

    const handleCreateUser = async (event) => {
        event.preventDefault();
        try {
            await createUser(newUser);
            setNewUser({display_name: '', email: '', password: ''});
            onNotice?.('Utilisateur créé.');
            await refresh();
        } catch (requestError) {
            onError?.(requestError.message);
        }
    };

    const handleUserUpdate = async (target, fields) => {
        try {
            const updatedUser = await updateUser(target.id, fields);
            setUsers((current) => current.map((item) => item.id === target.id ? {...item, ...updatedUser} : item));
            onNotice?.(`Compte de ${target.display_name} mis à jour.`);
            await onChanged?.();
        } catch (requestError) {
            onError?.(requestError.message);
        }
    };

    const handleJellyfinLink = async (target, jellyfinUserId) => {
        const previousJellyfinUserId = target.jellyfin_user_id || null;
        const nextJellyfinUserId = jellyfinUserId || null;
        setJellyfinSaving((current) => ({...current, [target.id]: true}));
        setUsers((current) => current.map((item) => item.id === target.id ? {...item, jellyfin_user_id: nextJellyfinUserId} : item));
        try {
            await linkJellyfinUser(target.id, nextJellyfinUserId);
            onNotice?.(`Compte Jellyfin de ${target.display_name} mis à jour.`);
            await onChanged?.();
        } catch (requestError) {
            setUsers((current) => current.map((item) => item.id === target.id ? {...item, jellyfin_user_id: previousJellyfinUserId} : item));
            onError?.(requestError.message);
        } finally {
            setJellyfinSaving((current) => ({...current, [target.id]: false}));
        }
    };

    const handleUserDelete = async (target) => {
        if (target.id === currentUser?.id) {
            onError?.('Un administrateur ne peut pas supprimer son propre compte.');
            return;
        }
        if (!window.confirm(`Supprimer définitivement le compte ${target.display_name} ?`)) return;
        try {
            await deleteUser(target.id);
            setExpandedUserId(null);
            onNotice?.(`Compte de ${target.display_name} supprimé.`);
            await refresh();
        } catch (requestError) {
            onError?.(requestError.message);
        }
    };

    const handleAdminPassword = async (target) => {
        const password = adminPasswords[target.id] || '';
        if (password.length < 8) {
            onError?.('Le mot de passe doit contenir au moins 8 caractères.');
            return;
        }
        try {
            await updateUser(target.id, {password});
            setAdminPasswords((current) => ({...current, [target.id]: ''}));
            onNotice?.(`Mot de passe de ${target.display_name} modifié.`);
        } catch (requestError) {
            onError?.(requestError.message);
        }
    };

    const text = isDarkMode ? 'text-white' : 'text-[#0a2540]';
    const muted = isDarkMode ? 'text-white/60' : 'text-[#425466]';
    const card = isDarkMode ? 'border-white/10 bg-white/[0.03]' : 'border-[#e3e8ee] bg-white';

    return (
        <div className={`space-y-4 ${text}`}>
            <div>
                <h3 className="text-lg font-semibold">Utilisateurs et droits</h3>
                <p className={`mt-1 text-sm ${muted}`}>Clique sur un compte pour afficher ses actions d’administration.</p>
            </div>

            <div className="space-y-3">
                {users.map((target) => {
                    const expanded = expandedUserId === target.id;
                    return (
                        <article key={target.id} className={`rounded-xl border ${card}`}>
                            <button type="button" className="flex w-full items-center justify-between gap-3 p-4 text-left" onClick={() => setExpandedUserId(expanded ? null : target.id)} aria-expanded={expanded}>
                                <span>
                                    <span className="block font-semibold">{target.display_name}</span>
                                    <span className={`block text-xs ${muted}`}>{target.email}</span>
                                </span>
                                <span className="flex items-center gap-2">
                                    <span className={`rounded-full border px-2 py-1 text-[10px] font-semibold uppercase tracking-wider ${target.is_active ? '' : 'text-rose-500'}`}>{target.role}</span>
                                    <span className={`text-xs ${muted}`}>{expanded ? 'Masquer' : 'Gérer'}</span>
                                </span>
                            </button>

                            {expanded && (
                                <div className="grid gap-3 border-t border-inherit p-4 text-sm" onClick={(event) => event.stopPropagation()}>
                                    <div className="flex flex-wrap items-center gap-2">
                                        <input value={target.display_name} onChange={(event) => setUsers((current) => current.map((item) => item.id === target.id ? {...item, display_name: event.target.value} : item))} className="min-w-48 flex-1 rounded border bg-transparent px-2 py-2" aria-label={`Nom de ${target.email}`} />
                                        <button type="button" className="rounded border border-[#635bff] px-3 py-2 text-xs text-[#635bff]" onClick={() => handleUserUpdate(target, {display_name: target.display_name})}>Enregistrer</button>
                                    </div>
                                    <div className="grid gap-2 sm:grid-cols-2">
                                        <label className="grid gap-1 text-xs">
                                            Association Jellyfin
                                            <select value={target.jellyfin_user_id || ''} onChange={(event) => handleJellyfinLink(target, event.target.value)} disabled={jellyfinLoading || jellyfinSaving[target.id]} className="rounded border bg-transparent px-2 py-2" aria-label={`Compte Jellyfin de ${target.email}`}>
                                                <option value="">Non associé</option>
                                                {jellyfinUsers.map((jellyfinUser) => {
                                                    const linkedToOther = users.some((item) => item.id !== target.id && item.jellyfin_user_id === jellyfinUser.id);
                                                    return <option key={jellyfinUser.id} value={jellyfinUser.id} disabled={linkedToOther}>{jellyfinUser.name}{linkedToOther ? ' — déjà associé' : ''}</option>;
                                                })}
                                            </select>
                                        </label>
                                        <label className="grid gap-1 text-xs">
                                            Rôle
                                            <select value={target.role} onChange={(event) => handleUserUpdate(target, {role: event.target.value})} className="rounded border bg-transparent px-2 py-2">
                                                <option value="user">Utilisateur</option>
                                                <option value="admin">Administrateur</option>
                                            </select>
                                        </label>
                                    </div>
                                    <div className="flex flex-wrap items-center gap-2">
                                        <input type="password" minLength="8" placeholder="Nouveau mot de passe" value={adminPasswords[target.id] || ''} onChange={(event) => setAdminPasswords((current) => ({...current, [target.id]: event.target.value}))} className="min-w-52 flex-1 rounded border bg-transparent px-2 py-2" aria-label={`Nouveau mot de passe de ${target.email}`} />
                                        <button type="button" className="rounded border px-3 py-2 text-xs" onClick={() => handleAdminPassword(target)}>Définir</button>
                                        <button type="button" className="rounded border px-3 py-2 text-xs text-[#635bff]" onClick={() => handleUserUpdate(target, {is_active: !target.is_active})}>{target.is_active ? 'Désactiver' : 'Activer'}</button>
                                        <button type="button" className="rounded border border-rose-500 px-3 py-2 text-xs text-rose-500" onClick={() => handleUserDelete(target)} disabled={target.id === currentUser?.id}>Supprimer</button>
                                    </div>
                                    <p className={`text-xs ${target.is_active ? 'text-emerald-500' : 'text-rose-500'}`}>{target.is_active ? 'Compte actif' : 'Compte désactivé'}</p>
                                </div>
                            )}
                        </article>
                    );
                })}
            </div>

            <form className={`grid gap-2 rounded-xl border p-4 ${card} sm:grid-cols-3`} onSubmit={handleCreateUser}>
                <h4 className="font-semibold sm:col-span-3">Créer un utilisateur</h4>
                <input required placeholder="Nom" value={newUser.display_name} onChange={(event) => setNewUser({...newUser, display_name: event.target.value})} className="rounded border bg-transparent px-2 py-2 text-sm" />
                <input required type="email" placeholder="Email" value={newUser.email} onChange={(event) => setNewUser({...newUser, email: event.target.value})} className="rounded border bg-transparent px-2 py-2 text-sm" />
                <input required minLength="8" type="password" placeholder="Mot de passe (8 caractères min.)" value={newUser.password} onChange={(event) => setNewUser({...newUser, password: event.target.value})} className="rounded border bg-transparent px-2 py-2 text-sm" />
                <button className="rounded bg-[#635bff] px-3 py-2 text-sm font-semibold text-white sm:col-span-3" type="submit">Créer un utilisateur</button>
            </form>
        </div>
    );
}
