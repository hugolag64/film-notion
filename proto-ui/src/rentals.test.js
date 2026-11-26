import assert from 'node:assert/strict';
import test from 'node:test';

import { isOpenRental, rentalCardBadge } from './rentals.js';

const NOW = new Date('2026-11-26T12:00:00Z');

test('open rentals: everything but expired or cancelled', () => {
    assert.equal(isOpenRental({ status: 'available' }), true);
    assert.equal(isOpenRental({ status: 'requested' }), true);
    assert.equal(isOpenRental({ status: 'expired' }), false);
    assert.equal(isOpenRental({ status: 'cancelled' }), false);
    assert.equal(isOpenRental(null), false);
});

test('card badge: days left on an available rental', () => {
    assert.deepEqual(rentalCardBadge({ status: 'available', expires_at: '2026-12-01T12:00:00Z' }, NOW), { label: 'Ta location · J-5', tone: 'rental' });
    assert.deepEqual(rentalCardBadge({ status: 'available', expires_at: '2026-11-20T12:00:00Z' }, NOW), { label: 'Ta location · J-0', tone: 'rental' });
    assert.deepEqual(rentalCardBadge({ status: 'available' }, NOW), { label: 'Ta location', tone: 'rental' });
});

test('card badge: kept films, and nothing for closed rentals', () => {
    assert.deepEqual(rentalCardBadge({ status: 'kept' }, NOW), { label: 'Gardé', tone: 'kept' });
    assert.deepEqual(rentalCardBadge({ status: 'keep_requested' }, NOW), { label: 'Gardé', tone: 'kept' });
    assert.equal(rentalCardBadge({ status: 'expired', expires_at: '2026-12-01T12:00:00Z' }, NOW), null);
    assert.equal(rentalCardBadge(undefined, NOW), null);
});

test('card badge: an unreadable deadline falls back to the plain label', () => {
    assert.deepEqual(rentalCardBadge({ status: 'available', expires_at: 'pas une date' }, NOW), { label: 'Ta location', tone: 'rental' });
});
