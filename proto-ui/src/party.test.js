import assert from 'node:assert/strict';
import test from 'node:test';

import { PARTY_BOT_ID, isPartyActive, isPartyCommand, partyIdOf, partyStep, safeBookingUrl, voteSummary } from './party.js';

const state = (status, me = {}) => ({ status, me: { member: false, answered: false, votes: {}, ...me } });

test('reconnaît la carte de soirée', () => {
    assert.equal(PARTY_BOT_ID, 'bot:soiree');
    assert.equal(partyIdOf({ type: 'party', party_id: 'p1' }), 'p1');
    assert.equal(partyIdOf({ type: 'cine_films' }), null);
    assert.equal(partyIdOf(null), null);
});

test("donne l'étape de chacun", () => {
    assert.equal(partyStep(state('joining')), 'join');
    assert.equal(partyStep(state('joining', { member: true })), 'answer');
    assert.equal(partyStep(state('joining', { member: true, answered: true })), 'wait');
    assert.equal(partyStep(state('voting')), 'join');
    assert.equal(partyStep(state('voting', { member: true })), 'vote');
    assert.equal(partyStep(state('done')), 'result');
    assert.equal(partyStep(state('expired', { member: true })), 'over');
    assert.equal(partyStep(state('empty')), 'over');
});

test('sait si la soirée est en cours', () => {
    assert.equal(isPartyActive(state('joining')), true);
    assert.equal(isPartyActive(state('voting')), true);
    assert.equal(isPartyActive(state('done')), false);
    assert.equal(isPartyActive(null), false);
});

test('résume les votes', () => {
    assert.equal(voteSummary({ 1: { up: 2, down: 1 } }, 1), '👍 2 · 👎 1');
    assert.equal(voteSummary({}, 3), '👍 0 · 👎 0');
});

test('reconnaît la commande @soirée', () => {
    assert.equal(isPartyCommand('@Soiree coloc'), true);
    assert.equal(isPartyCommand('  @soirée'), true);
    assert.equal(isPartyCommand('@ciné films'), false);
    assert.equal(isPartyCommand('@soiréeX'), false);
});

test("n'ouvre que des liens de réservation web", () => {
    assert.equal(safeBookingUrl('https://cine/resa'), 'https://cine/resa');
    assert.equal(safeBookingUrl('javascript:alert(1)'), null);
    assert.equal(safeBookingUrl(null), null);
});

test('montre la recherche tant que les films ne sont pas là', () => {
    assert.equal(partyStep({ ...state('voting', { member: true }), proposals: [] }), 'searching');
    assert.equal(partyStep({ ...state('voting'), proposals: [] }), 'searching');
    assert.equal(partyStep({ ...state('voting', { member: true }), proposals: [{ rank: 1 }] }), 'vote');
});
