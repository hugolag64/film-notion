export const ACTIVE_RENTAL_STATUSES = ['requested', 'downloading', 'available', 'keep_requested'];
export const DEFAULT_MAX_ACTIVE_RENTALS = 5;
export const DEFAULT_MAX_QUEUED_RENTALS = 10;

// Download states meaning "Radarr has nothing to download yet" (no release found on the indexer).
const WAITING_DOWNLOAD_STATES = ['requested', 'error'];

const STATUS_LABELS = {
    queued: 'En attente d’une source',
    requested: 'Demandé',
    downloading: 'En téléchargement',
    available: 'Disponible',
    keep_requested: 'Conservation demandée',
    kept: 'Conservé définitivement',
    expired: 'Expiré',
    cancelled: 'Annulé',
};

export const isActiveRental = (rental) => ACTIVE_RENTAL_STATUSES.includes(rental?.status);

/** A request still waiting for the indexer: it sits in the queue, not in the 5 rental slots. */
export const isQueuedRental = (rental) => rental?.status === 'requested'
    && (!rental.download_state || WAITING_DOWNLOAD_STATES.includes(rental.download_state));

/** Status shown to the flatmate: the stored status, refined with the live download state. */
export const rentalDisplayStatus = (rental) => {
    if (isQueuedRental(rental)) return 'queued';
    if (rental?.status === 'requested' && ['searching', 'downloading', 'imported'].includes(rental.download_state)) return 'downloading';
    return rental?.status;
};

export const rentalStatusLabel = (rentalOrStatus) => {
    const status = typeof rentalOrStatus === 'string' ? rentalOrStatus : rentalDisplayStatus(rentalOrStatus);
    return STATUS_LABELS[status] || 'En cours';
};

/** Rentals arrive newest first: keep the most recent rental of each media. */
export const indexRentalsByMedia = (rentals = []) => {
    const byMedia = {};
    for (const rental of rentals) {
        if (!byMedia[rental.media_id]) byMedia[rental.media_id] = rental;
    }
    return byMedia;
};

export const countRentalsInUse = (rentals = []) => rentals.filter((rental) => isActiveRental(rental) && !isQueuedRental(rental)).length;

export const countQueuedRentals = (rentals = []) => rentals.filter(isQueuedRental).length;

/** "expire dans 3 j", "expire aujourd'hui", or null when there is no deadline yet. */
export const rentalExpiryLabel = (rental, now = new Date()) => {
    if (!rental?.expires_at || !isActiveRental(rental)) return null;
    const days = Math.ceil((new Date(rental.expires_at).getTime() - now.getTime()) / 86_400_000);
    if (Number.isNaN(days)) return null;
    if (days <= 0) return 'expire aujourd’hui';
    return `expire dans ${days} j`;
};

/** « Person of Interest · Saison 2 » for a season rental, the plain title otherwise. */
export const rentalTitle = (rental, title) => (
    rental?.rental_scope === 'season' && rental.season_number ? `${title} · Saison ${rental.season_number}` : title
);
