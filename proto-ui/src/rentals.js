export const ACTIVE_RENTAL_STATUSES = ['requested', 'downloading', 'available', 'keep_requested'];
export const DEFAULT_MAX_ACTIVE_RENTALS = 5;

const STATUS_LABELS = {
    requested: 'Demandé',
    downloading: 'En téléchargement',
    available: 'Disponible',
    keep_requested: 'Conservation demandée',
    kept: 'Conservé définitivement',
    expired: 'Expiré',
    cancelled: 'Annulé',
};

export const rentalStatusLabel = (status) => STATUS_LABELS[status] || 'En cours';

export const isActiveRental = (rental) => ACTIVE_RENTAL_STATUSES.includes(rental?.status);

/** Rentals arrive newest first: keep the most recent rental of each media. */
export const indexRentalsByMedia = (rentals = []) => {
    const byMedia = {};
    for (const rental of rentals) {
        if (!byMedia[rental.media_id]) byMedia[rental.media_id] = rental;
    }
    return byMedia;
};

export const countActiveRentals = (rentals = []) => rentals.filter(isActiveRental).length;

/** "expire dans 3 j", "expire aujourd'hui", or null when there is no deadline yet. */
export const rentalExpiryLabel = (rental, now = new Date()) => {
    if (!rental?.expires_at || !isActiveRental(rental)) return null;
    const days = Math.ceil((new Date(rental.expires_at).getTime() - now.getTime()) / 86_400_000);
    if (Number.isNaN(days)) return null;
    if (days <= 0) return 'expire aujourd’hui';
    return `expire dans ${days} j`;
};
