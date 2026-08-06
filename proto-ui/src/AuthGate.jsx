import { useEffect, useState } from 'react';
import { fetchAuthStatus, fetchCurrentUser, login, logout, requestPasswordReset, setupAdmin } from './api';
import { AuthContext } from './auth-context';
import PasswordResetPage from './PasswordResetPage';

function AuthForm({setupRequired, onSubmit, onForgotPassword, error, loading}) {
    const [displayName, setDisplayName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmation, setConfirmation] = useState('');
    const [rememberDevice, setRememberDevice] = useState(true);

    const submit = async (event) => {
        event.preventDefault();
        await onSubmit({
            ...(setupRequired ? {
                display_name: displayName,
                password_confirmation: confirmation,
            } : {remember_device: rememberDevice}),
            email,
            password,
        });
    };

    return (
        <main className="auth-shell">
            <form className="auth-card" onSubmit={submit}>
                <p className="auth-kicker">BACKSTAGE</p>
                <h1>{setupRequired ? 'Créer votre compte administrateur' : 'Bienvenue'}</h1>
                <p className="auth-subtitle">
                    {setupRequired ? 'Configurez le premier compte de votre bibliothèque.' : 'Connectez-vous pour accéder à votre bibliothèque.'}
                </p>
                {setupRequired && (
                    <label>
                        Nom affiché
                        <input required value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
                    </label>
                )}
                <label>
                    Email
                    <input required type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} />
                </label>
                <label>
                    Mot de passe
                    <input required minLength={8} type="password" autoComplete={setupRequired ? 'new-password' : 'current-password'} value={password} onChange={(event) => setPassword(event.target.value)} />
                </label>
                {setupRequired && (
                    <label>
                        Confirmer le mot de passe
                        <input required type="password" autoComplete="new-password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
                    </label>
                )}
                {!setupRequired && (
                    <label className="auth-checkbox">
                        <input type="checkbox" checked={rememberDevice} onChange={(event) => setRememberDevice(event.target.checked)} />
                        Se souvenir de cet appareil pendant 30 jours
                    </label>
                )}
                {error && <p className="auth-error" role="alert">{error}</p>}
                <button className="auth-submit" type="submit" disabled={loading}>
                    {loading ? 'Connexion…' : setupRequired ? 'Créer le compte' : 'Se connecter'}
                </button>
                {!setupRequired && <button className="auth-link-button" type="button" onClick={onForgotPassword}>Mot de passe oublié ?</button>}
            </form>
        </main>
    );
}

function ForgotPasswordForm({onBack}) {
    const [email, setEmail] = useState('');
    const [error, setError] = useState('');
    const [sent, setSent] = useState(false);
    const [loading, setLoading] = useState(false);

    const submit = async (event) => {
        event.preventDefault();
        setError('');
        setLoading(true);
        try {
            await requestPasswordReset(email);
            setSent(true);
        } catch (requestError) {
            setError(requestError.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <main className="auth-shell">
            <form className="auth-card" onSubmit={submit}>
                <p className="auth-kicker">BACKSTAGE</p>
                <h1>Mot de passe oublié</h1>
                {sent ? (
                    <p className="auth-subtitle">Si un compte correspond, un e-mail vient d’être envoyé.</p>
                ) : (
                    <>
                        <p className="auth-subtitle">Saisissez l’adresse e-mail enregistrée par l’administrateur.</p>
                        <label>
                            Email
                            <input required type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} />
                        </label>
                        {error && <p className="auth-error" role="alert">{error}</p>}
                        <button className="auth-submit" type="submit" disabled={loading}>
                            {loading ? 'Envoi…' : 'Envoyer le lien'}
                        </button>
                    </>
                )}
                <button className="auth-link-button" type="button" onClick={onBack}>Retour à la connexion</button>
            </form>
        </main>
    );
}

function AuthenticatedGate({children}) {
    const [state, setState] = useState('loading');
    const [user, setUser] = useState(null);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        let active = true;
        (async () => {
            try {
                const status = await fetchAuthStatus();
                if (!active) return;
                if (status.setup_required) {
                    setState('setup');
                    return;
                }
                const currentUser = await fetchCurrentUser();
                if (!active) return;
                setUser(currentUser);
                setState(currentUser ? 'authenticated' : 'login');
            } catch (requestError) {
                if (active) {
                    setError(requestError.message);
                    setState('error');
                }
            }
        })();
        return () => { active = false; };
    }, []);

    const submit = async (payload) => {
        setLoading(true);
        setError('');
        try {
            const authenticatedUser = state === 'setup' ? await setupAdmin(payload) : await login(payload);
            setUser(authenticatedUser);
            setState('authenticated');
        } catch (requestError) {
            setError(requestError.message);
        } finally {
            setLoading(false);
        }
    };

    const signOut = async () => {
        await logout();
        setUser(null);
        setState('login');
    };

    if (state === 'loading') return <main className="auth-shell"><p>Chargement…</p></main>;
    if (state === 'error') return <main className="auth-shell"><p className="auth-error">{error}</p></main>;
    if (state === 'forgot') {
        return <ForgotPasswordForm onBack={() => { setError(''); setState('login'); }} />;
    }
    if (state === 'setup' || state === 'login') {
        return <AuthForm
            setupRequired={state === 'setup'}
            onSubmit={submit}
            onForgotPassword={() => { setError(''); setState('forgot'); }}
            error={error}
            loading={loading}
        />;
    }

    return (
        <AuthContext.Provider value={{user, setUser, logout: signOut}}>
            {children}
        </AuthContext.Provider>
    );
}
export default function AuthGate({children}) {
    if (window.location.pathname === '/reset-password') {
        return <PasswordResetPage token={new URLSearchParams(window.location.search).get('token')} />;
    }
    return <AuthenticatedGate>{children}</AuthenticatedGate>;
}
