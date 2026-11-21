const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const script = fs.readFileSync(path.join(__dirname, 'backstage-autoplay.js'), 'utf8');

function createHarness(itemId = 'jellyfin-item-123') {
    const intervals = new Map();
    let nextIntervalId = 1;
    const listeners = new Map();
    const acknowledgements = [];
    let clickCount = 0;
    let now = 0;
    let mutedPlayAllowed = true;
    const banners = [];
    const video = {
        paused: true,
        readyState: 0,
        muted: false,
        play() {
            if (this.muted && mutedPlayAllowed) {
                this.paused = false;
                return Promise.resolve();
            }
            return Promise.reject(new Error('NotAllowedError'));
        },
    };
    const opener = {
        postMessage(message, origin) {
            acknowledgements.push({message, origin});
        },
    };
    const button = {
        className: 'button-flat btnPlay detailButton emby-button',
        classList: {contains: () => false},
        disabled: false,
        getClientRects() { return [{}]; },
        click() { clickCount += 1; },
    };
    const root = {querySelectorAll: () => [button]};
    const window = {
        opener,
        location: {search: '', hash: `#/details?id=${itemId}&serverId=server`},
        addEventListener(name, listener) { listeners.set(name, listener); },
        removeEventListener(name, listener) {
            if (listeners.get(name) === listener) listeners.delete(name);
        },
        setInterval(callback) {
            const id = nextIntervalId++;
            intervals.set(id, callback);
            return id;
        },
        clearInterval(id) { intervals.delete(id); },
        getComputedStyle: () => ({visibility: 'visible'}),
    };
    const context = {
        window,
        document: {
            querySelector: selector => selector === '.videoPlayerContainer video' ? video : root,
            createElement: () => {
                const banner = {style: {}, remove() { banners.splice(banners.indexOf(banner), 1); }};
                return banner;
            },
            body: {appendChild: banner => banners.push(banner)},
        },
        URLSearchParams,
        performance: {now: () => now},
    };
    vm.runInNewContext(script, context, {filename: 'backstage-autoplay.js'});
    return {
        window,
        opener,
        listeners,
        intervals,
        acknowledgements,
        video,
        banners,
        getClickCount: () => clickCount,
        denyMutedPlay: () => { mutedPlayAllowed = false; },
        setNow: value => { now = value; },
        setPlaying: () => { video.paused = false; video.readyState = 4; },
        setBlocked: () => { video.paused = true; video.readyState = 4; },
    };
}

test('clicks play once and acknowledges only after the video is playing', () => {
    const harness = createHarness();
    harness.listeners.get('message')({
        source: harness.opener,
        origin: 'http://backstage.local:8090',
        data: {type: 'backstage:play-request', requestId: 'request-1', itemId: 'jellyfin-item-123'},
    });

    assert.equal(harness.intervals.size, 1);
    const poll = [...harness.intervals.values()][0];
    poll();
    assert.equal(harness.getClickCount(), 1);
    assert.equal(harness.acknowledgements.length, 0, 'a button click is not proof that playback started');

    harness.setPlaying();
    poll();

    assert.equal(harness.acknowledgements.length, 1);
    assert.equal(harness.acknowledgements[0].message.type, 'backstage:play-ack');
    assert.equal(harness.acknowledgements[0].message.requestId, 'request-1');
    assert.equal(harness.acknowledgements[0].message.started, true);
    assert.equal(harness.acknowledgements[0].origin, 'http://backstage.local:8090');
});

test('ignores playback requests from windows other than the opener', () => {
    const harness = createHarness();
    harness.listeners.get('message')({
        source: {},
        origin: 'http://attacker.local',
        data: {type: 'backstage:play-request', requestId: 'request-2', itemId: 'jellyfin-item-123'},
    });

    assert.equal(harness.intervals.size, 0);
    assert.equal(harness.getClickCount(), 0);
    assert.equal(harness.acknowledgements.length, 0);
});

function requestAndBlock(harness, requestId) {
    harness.listeners.get('message')({
        source: harness.opener,
        origin: 'http://backstage.local:8090',
        data: {type: 'backstage:play-request', requestId, itemId: 'jellyfin-item-123'},
    });
    const poll = [...harness.intervals.values()][0];
    poll();
    harness.setNow(2000);
    harness.setBlocked();
    poll();
    return poll;
}

const flush = () => new Promise(resolve => setImmediate(resolve));

test('falls back to muted playback when Chrome blocks audible autoplay', async () => {
    const harness = createHarness();
    const poll = requestAndBlock(harness, 'request-3');
    await flush();

    assert.equal(harness.getClickCount(), 1, 'never clicks play twice');
    assert.equal(harness.video.muted, true);
    assert.equal(harness.video.paused, false);
    assert.equal(harness.banners.length, 1, 'tells the user how to get the sound back');

    poll();
    assert.equal(harness.acknowledgements.length, 1);
    assert.equal(harness.acknowledgements[0].message.started, true);

    const event = {preventDefault() {}, stopImmediatePropagation() {}};
    harness.listeners.get('pointerdown')(event);
    assert.equal(harness.video.muted, false, 'first interaction restores the sound');
    assert.equal(harness.banners.length, 0);
});

test('reports a failure when even muted playback is refused', async () => {
    const harness = createHarness();
    harness.denyMutedPlay();
    requestAndBlock(harness, 'request-4');
    await flush();

    assert.equal(harness.getClickCount(), 1);
    assert.equal(harness.acknowledgements[0].message.started, false);
    assert.match(harness.acknowledgements[0].message.reason, /bloqué la lecture automatique/);
});
