import assert from 'node:assert/strict';
import test from 'node:test';

import { filterAndSortMovies, normalizeSearchText, searchLibrary, searchScore } from './library.js';

const film = (title, director = '', extra = {}) => ({
    title, director, genre: [], supports: [], status: 'À regarder', cast: [], ...extra,
});

const NOLAN = [
    film('Inception', 'Christopher Nolan'),
    film('Interstellar', 'Christopher Nolan'),
    film('Oppenheimer', 'Christopher Nolan'),
    film('Dunkerque', 'Christopher Nolan'),
    film('Tenet', 'Christopher Nolan'),
    film('Memento', 'Christopher Nolan'),
    film('Le Fabuleux Destin d’Amélie Poulain', 'Jean-Pierre Jeunet'),
    film('Intouchables', 'Olivier Nakache'),
];

test('accents, case and punctuation are ignored', () => {
    assert.equal(normalizeSearchText('  Amélie — Œuvre!'), 'amelie oeuvre');
    assert.deepEqual(searchLibrary(NOLAN, 'amelie').map((m) => m.title), ['Le Fabuleux Destin d’Amélie Poulain']);
});

test('one typo in a long title still finds it', () => {
    assert.deepEqual(searchLibrary(NOLAN, 'inteqstellar').map((m) => m.title), ['Interstellar']);
    assert.deepEqual(searchLibrary(NOLAN, 'opennheimer').map((m) => m.title), ['Oppenheimer']);
});

test('a director name returns all their films, not five', () => {
    assert.equal(searchLibrary(NOLAN, 'nolan').length, 6);
    assert.equal(searchLibrary(NOLAN, 'nolam').length, 6);
});

test('half-typed words match, short words need no typo', () => {
    assert.deepEqual(searchLibrary(NOLAN, 'interst').map((m) => m.title), ['Interstellar']);
    assert.equal(searchScore(film('Tenet'), 'xyz'), null);
});

test('exact title matches come before typo matches', () => {
    const titles = searchLibrary([film('Dune'), film('Dunkerque'), film('June')], 'dune').map((m) => m.title);
    assert.deepEqual(titles, ['Dune']);
    assert.deepEqual(searchLibrary([film('June')], 'dune').map((m) => m.title), ['June']);
});

test('the library grid uses the same tolerant search', () => {
    const sort = { key: 'title', direction: 'asc' };
    const result = filterAndSortMovies(NOLAN, { query: 'inteqstellar', genre: '', director: '', status: '', support: '' }, sort);
    assert.deepEqual(result.map((m) => m.title), ['Interstellar']);
});

test('the placeholder actor name is not searchable', () => {
    assert.equal(searchScore(film('Tenet', '', {cast: ['Acteur principal']}), 'acteur'), null);
});

test('a fiche has a shareable path, and the path leads back to it', async () => {
    const { mediaPath, parseMediaPath } = await import('./library.js');
    assert.equal(mediaPath({id: 'abc 1', type: 'Film'}), '/film/abc%201');
    assert.equal(mediaPath({id: 's1', type: 'Série'}), '/serie/s1');
    assert.equal(mediaPath(null), undefined);
    assert.deepEqual(parseMediaPath('/film/abc%201'), {kind: 'film', id: 'abc 1'});
    assert.deepEqual(parseMediaPath('/serie/s1/'), {kind: 'serie', id: 's1'});
    assert.equal(parseMediaPath('/'), null);
    assert.equal(parseMediaPath('/reset-password'), null);
    assert.equal(parseMediaPath('/film/%E0%A4%A'), null);
});
