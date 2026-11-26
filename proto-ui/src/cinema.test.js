import assert from 'node:assert/strict';
import test from 'node:test';

import { CINE_COMMANDS, filmButtons, helpCommands, isBotMessage, isCineCommand, showtimeLine } from './cinema.js';

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
