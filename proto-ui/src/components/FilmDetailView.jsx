import useLayer from '../useLayer';

export default function FilmDetailView({ media, isDarkMode, onClose, url, children }) {
    // Escape, Back button, focus trap and focus return are handled by useLayer.
    const layerRef = useLayer(true, onClose, url);

    return <div
        ref={layerRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={`Fiche de ${media?.title || 'film'}`}
        className={`${isDarkMode ? 'bg-black/80' : 'bg-black/65'} fixed inset-0 z-50 flex items-center justify-center p-3 outline-none backdrop-blur-md animate-fade-in-smooth cursor-pointer sm:p-6`}
        onClick={onClose}
    >
        {children}
    </div>;
}
