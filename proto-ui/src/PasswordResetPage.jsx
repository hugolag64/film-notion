import { useState } from 'react';
import { resetPassword } from './api';

export default function PasswordResetPage({token}) {
    const [newPassword, setNewPassword] = useState('');
    const [confirmation, setConfirmation] = useState('');
    const [error, setError] = useState(token ? '' : 'Lien de réinitialisation manquant.');
    const [success, setSuccess] = useState(false);
    const [loading, setLoading] = useState(false);

    const submit = async (event) => {
        event.preventDefault();
        if (!token) return;
        setError('');
        setLoading(true);
        try {
            await resetPassword({
                token,
                new_password: newPassword,
                password_confirmation: confirmation,
            });
            setSuccess(true);
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
                <h1>Réinitialiser le mot de passe</h1>
                {success ? (
                    <>
                        <p className="auth-subtitle">Votre mot de passe a été modifié.</p>
                        <a className="auth-link" href="/">Retour à la connexion</a>
                    </>
                ) : (
                    <>
                        <p className="auth-subtitle">Choisissez un nouveau mot de passe d’au moins 8 caractères.</p>
                        <label>
                            Nouveau mot de passe
                            <input required minLength={8} type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} />
                        </label>
                        <label>
                            Confirmer le mot de passe
                            <input required minLength={8} type="password" autoComplete="new-password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
                        </label>
                        {error && <p className="auth-error" role="alert">{error}</p>}
                        <button className="auth-submit" type="submit" disabled={loading || !token}>
                            {loading ? 'Modification…' : 'Modifier le mot de passe'}
                        </button>
                        <a className="auth-link" href="/">Retour à la connexion</a>
                    </>
                )}
            </form>
        </main>
    );
}
