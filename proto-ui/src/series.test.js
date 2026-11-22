import test from 'node:test';
import assert from 'node:assert/strict';
import { episodeCode, formatDuration, primaryEpisodeLabel, seasonAvailabilityLabel, seriesYears, tmdbStatusLabel } from './series.js';

test('episodeCode pads the episode number', () => {
    assert.equal(episodeCode(3, 7), 'S3:E07');
});

test('formatDuration reads like a streaming app', () => {
    assert.equal(formatDuration(40), '40 min');
    assert.equal(formatDuration(95), '1 h 35');
    assert.equal(formatDuration(120), '2 h');
    assert.equal(formatDuration(null), null);
});

test('seriesYears shows a range, an open range for running shows, or the fallback', () => {
    assert.equal(seriesYears({first_air_date: '2011-09-22', last_air_date: '2016-06-21', tmdb_status: 'Ended'}), '2011–2016');
    assert.equal(seriesYears({first_air_date: '2022-02-18', last_air_date: '2025-03-21', tmdb_status: 'Returning Series'}), '2022–');
    assert.equal(seriesYears(null, 2011), '2011');
    assert.equal(seriesYears(null, '—'), null);
});

test('tmdbStatusLabel translates TMDB statuses', () => {
    assert.equal(tmdbStatusLabel({tmdb_status: 'Ended'}), 'Terminée');
    assert.equal(tmdbStatusLabel({tmdb_status: 'Returning Series'}), 'En production');
    assert.equal(tmdbStatusLabel(null), null);
});

test('primaryEpisodeLabel follows the next-episode mode', () => {
    assert.equal(primaryEpisodeLabel({season_number: 2, episode_number: 5, mode: 'resume'}), 'Reprendre S2:E05');
    assert.equal(primaryEpisodeLabel({season_number: 1, episode_number: 1, mode: 'start'}), 'Commencer S1:E01');
    assert.equal(primaryEpisodeLabel({season_number: 3, episode_number: 2, mode: 'next'}), 'Lire S3:E02');
    assert.equal(primaryEpisodeLabel(null), null);
});

test('seasonAvailabilityLabel', () => {
    assert.equal(seasonAvailabilityLabel({availability: 'complete'}), 'Complète');
    assert.equal(seasonAvailabilityLabel({availability: 'partial', available: 8, aired: 22}), 'Partielle 8/22');
    assert.equal(seasonAvailabilityLabel({availability: null}), null);
});
