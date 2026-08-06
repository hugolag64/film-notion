import { useEffect } from 'react';

export default function FilmDetailView({ media, isDarkMode, onClose, children }) {
    useEffect(() => {
        const handleEscape = (event) => {
            if (event.key === 'Escape') onClose();
        };
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        window.addEventListener('keydown', handleEscape);
        return () => {
            document.body.style.overflow = previousOverflow;
            window.removeEventListener('keydown', handleEscape);
        };
    }, [onClose]);

    return <div className={`${isDarkMode ? 'bg-black/80' : 'bg-black/65'} fixed inset-0 z-50 flex items-center justify-center p-3 backdrop-blur-md animate-fade-in-smooth cursor-pointer sm:p-6`} onClick={onClose} aria-label={`Fiche de ${media?.title || 'film'}`}>
        {children}
    </div>;
}
