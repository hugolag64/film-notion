import assert from 'node:assert/strict';
import test from 'node:test';

import { CINE_COMMANDS, HELP_SECTIONS, filmButtons, helpCommands, isBotMessage, isCineCommand, isClearCommand, isExpiredPrivate, showtimeLine } from './cinema.js';

test('reconnaît les messages du bot', () => {
    assert.equal(isBotMessage({ author: { id: 'bot:cine' } }), true);
    assert.equal(isBotMessage({ author: { id: 'bot:soiree' } }), true);
    assert.equal(isBotMessage({ author: { id: 'hugo' } }), false);
    assert.equal(isBotMessage(null), false);
});

test('extrait les boutons de films', () => {
    assert.deepEqual(
        filmButtons({ type: 'cine_films', films: [{ site_id: 1, title: 'Dune', tracked: true }] }),
        [{ site_id: 1, title: 'Dune', tracked: true }],
    );
    assert.deepEqual(filmButtons(null), []);
    assert.deepEqual(filmButtons({ type: 'cine_help' }), []);
});

test("extrait les commandes d'aide", () => {
    assert.equal(helpCommands({ type: 'cine_help', commands: [{ command: '@ciné films' }] }).length, 1);
    assert.deepEqual(helpCommands(undefined), []);
});

test('formate une séance', () => {
    assert.equal(showtimeLine({ time: '20:00', version: 'VF 3D' }), '20:00 · VF 3D');
    assert.equal(showtimeLine({ time: '20:00', version: '' }), '20:00');
});

test("l'aide liste les quatre commandes", () => {
    assert.deepEqual(CINE_COMMANDS.map((c) => c.command), ['@ciné films', '@ciné ce soir', '@ciné demain', '@ciné aide']);
    assert.ok(CINE_COMMANDS.every((c) => c.description));
});

test('repère un message adressé au bot', () => {
    assert.equal(isCineCommand('@ciné films'), true);
    assert.equal(isCineCommand('  @CINE demain'), true);
    assert.equal(isCineCommand('@cinéma'), false);
    assert.equal(isCineCommand('salut @ciné'), false);
});

test('help sections list every command and say who sees the answer', () => {
    assert.deepEqual(HELP_SECTIONS.map((s) => s.title), ['Horaires du Grand Sud', 'Soirée film', 'Ranger le salon']);
    assert.deepEqual(HELP_SECTIONS[0].commands.map((c) => c.command), ['@ciné films', '@ciné ce soir', '@ciné demain']);
    assert.deepEqual(HELP_SECTIONS[1].commands.map((c) => c.command), ['@soirée coloc', '@soirée ciné']);
    assert.match(HELP_SECTIONS[0].audience, /toi seul/);
    assert.match(HELP_SECTIONS[1].audience, /tout le salon/);
    assert.ok(HELP_SECTIONS.every((s) => s.commands.every((c) => c.description)));
});

test('isClearCommand reconnaît @quit et ses variantes', () => {
    assert.equal(isClearCommand(' @QUIT '), true);
    assert.equal(isClearCommand('@effacer'), true);
    assert.equal(isClearCommand('@quit maintenant'), false);
    assert.equal(isClearCommand('quit'), false);
});

test('isExpiredPrivate ne retire que les messages privés de plus de 10 min', () => {
    const now = Date.parse('2026-11-26T20:00:00Z');
    const old = '2026-11-26T19:49:00Z';
    assert.equal(isExpiredPrivate({ private: true, created_at: old }, now), true);
    assert.equal(isExpiredPrivate({ private: false, created_at: old }, now), false);
    assert.equal(isExpiredPrivate({ private: true, created_at: '2026-11-26T19:55:00Z' }, now), false);
});
