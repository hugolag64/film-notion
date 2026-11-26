import assert from 'node:assert/strict';
import test from 'node:test';

import { formatStars, journalFilmTarget, groupDiaryByMonth, listItemBadge, shouldOfferSeerrRequest, todayIsoDate } from './journal.js';

const NOW = new Date(2026, 10, 26);

test('diary groups: newest month first, undated entries last', () => {
    const entries = [
        { id: 'a', watched_on: '2026-11-22' },
        { id: 'b', watched_on: null },
        { id: 'c', watched_on: '2026-11-14' },
        { id: 'd', watched_on: '2026-10-03' },
    ];
    const groups = groupDiaryByMonth(entries);
    assert.deepEqual(groups.map((group) => group.key), ['2026-11', '2026-10', 'unknown']);
    assert.deepEqual(groups.map((group) => group.label), ['Novembre 2026', 'Octobre 2026', 'Date inconnue']);
    assert.deepEqual(groups[0].entries.map((entry) => entry.id), ['a', 'c']);
    assert.deepEqual(groups[2].entries.map((entry) => entry.id), ['b']);
});

test('diary groups: empty journal', () => {
    assert.deepEqual(groupDiaryByMonth([]), []);
});

test('stars: half points and no rating', () => {
    assert.equal(formatStars(4.5), '★★★★½');
    assert.equal(formatStars(3), '★★★');
    assert.equal(formatStars(0.5), '½');
    assert.equal(formatStars(null), '');
});

test('list badge: ready on the server', () => {
    assert.deepEqual(listItemBadge({ library: { state: 'available', ready: true } }, NOW), { label: 'Sur le serveur', tone: 'ready' });
});

test('list badge: tracked by the server but not ready', () => {
    const item = { release_date: '2024-01-01', library: { state: 'downloading', progress_percent: 40, ready: false } };
    assert.deepEqual(listItemBadge(item, NOW), { label: 'Téléchargement 40 %', tone: 'downloading' });
    assert.deepEqual(listItemBadge({ release_date: '2020-01-01', library: { state: 'requested', ready: false } }, NOW), { label: 'Demandé', tone: 'requested' });
});

test('list badge: outside the library, release date decides', () => {
    assert.deepEqual(listItemBadge({ release_date: '2026-12-17', library: null }, NOW), { label: 'Sort le 17/12', tone: 'upcoming' });
    assert.deepEqual(listItemBadge({ release_date: '2026-10-01', library: null }, NOW), { label: 'Au cinéma', tone: 'cinema' });
    assert.equal(listItemBadge({ release_date: '2020-01-01', library: null }, NOW), null);
    assert.equal(listItemBadge({ release_date: null, library: null }, NOW), null);
});

test('seerr offer: only for films neither on the server nor requested', () => {
    assert.equal(shouldOfferSeerrRequest({ added: true, item: { library: null } }), true);
    assert.equal(shouldOfferSeerrRequest({ added: true, item: { library: { state: 'requested' } } }), false);
    assert.equal(shouldOfferSeerrRequest(null), false);
});

test('today as a local ISO date', () => {
    assert.equal(todayIsoDate(new Date(2026, 0, 5, 23, 30)), '2026-01-05');
});

test('a journal film opens its library sheet when on the server, the TMDB sheet otherwise', () => {
    assert.deepEqual(
        journalFilmTarget({ tmdb_id: 857, media_id: 'm1', movie: { title: 'Ryan' } }),
        { kind: 'library', mediaId: 'm1' },
    );
    assert.deepEqual(
        journalFilmTarget({ tmdb_id: 389, media_id: null, movie: { title: 'Douze hommes en colère' } }),
        { kind: 'tmdb', film: { tmdb_id: 389, title: 'Douze hommes en colère' } },
    );
});
