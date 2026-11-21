(() => {
    'use strict';

    const requestType = 'backstage:play-request';
    const ackType = 'backstage:play-ack';
    const activeRequests = new Set();

    function currentItemId() {
        const hash = window.location.hash;
        if (!hash.startsWith('#/details?')) return null;
        return new URLSearchParams(hash.slice('#/details?'.length)).get('id');
    }

    function findPlayButton() {
        const area = document.querySelector('#itemDetailPage .mainDetailButtons')
            || document.querySelector('#itemDetailPage');
        if (!area) return null;

        return [...area.querySelectorAll('.btnResume, .btnPlay')].find(button => (
            !button.disabled
            && !button.classList.contains('hide')
            && button.getClientRects().length > 0
            && window.getComputedStyle(button).visibility === 'visible'
        )) || null;
    }

    function playbackStarted() {
        if (window.location.hash.startsWith('#/video')) return true;
        const video = document.querySelector('.videoPlayerContainer video');
        return Boolean(video && !video.paused && video.readyState >= 2);
    }

    function autoplayBlocked() {
        const video = document.querySelector('.videoPlayerContainer video');
        return Boolean(video && video.paused && video.readyState >= 2);
    }

    function playerVideo() {
        return document.querySelector('.videoPlayerContainer video');
    }

    // Chrome refuses audible autoplay in a tab the user never clicked
    // (NotAllowedError). Muted playback is always allowed, so start muted and
    // give the sound back on the user's first click or key press in the tab.
    function restoreSoundOnFirstInteraction() {
        const banner = document.createElement('div');
        banner.textContent = '🔇 Son coupé par le navigateur — clique ou appuie sur une touche pour l’activer';
        banner.style.cssText = 'position:fixed;top:16px;left:50%;transform:translateX(-50%);'
            + 'z-index:100000;padding:10px 18px;border-radius:999px;background:rgba(0,0,0,.8);'
            + 'color:#fff;font:600 15px sans-serif;cursor:pointer;pointer-events:none;';
        document.body.appendChild(banner);

        const unmute = event => {
            // Swallow this first interaction: Jellyfin would otherwise treat the
            // click or the space bar as play/pause.
            event.preventDefault();
            event.stopImmediatePropagation();
            const video = playerVideo();
            if (video) video.muted = false;
            banner.remove();
            window.removeEventListener('pointerdown', unmute, true);
            window.removeEventListener('click', swallowClick, true);
            window.removeEventListener('keydown', unmute, true);
        };
        let swallowed = false;
        const swallowClick = event => {
            if (swallowed) return;
            swallowed = true;
            event.preventDefault();
            event.stopImmediatePropagation();
        };
        window.addEventListener('pointerdown', unmute, true);
        window.addEventListener('click', swallowClick, true);
        window.addEventListener('keydown', unmute, true);
    }

    function startMuted(video) {
        video.muted = true;
        return Promise.resolve(video.play()).then(() => {
            restoreSoundOnFirstInteraction();
            return true;
        }, () => false);
    }

    function startPlayback(itemId, requestId = null, origin = '*') {
        itemId = String(itemId);
        if (currentItemId() !== itemId || activeRequests.has(itemId)) return;

        activeRequests.add(itemId);
        const startedAt = performance.now();
        let clicked = false;
        let clickAt = null;
        let mutedTried = false;
        let done = false;
        let timer;

        const finish = (started, reason = null) => {
            if (done) return;
            done = true;
            window.clearInterval(timer);
            activeRequests.delete(itemId);
            if (requestId && window.opener) {
                window.opener.postMessage({type: ackType, requestId, started, reason}, origin);
            }
        };

        timer = window.setInterval(() => {
            if (playbackStarted()) {
                finish(true);
                return;
            }

            if (clicked && !mutedTried && performance.now() - clickAt >= 1500 && autoplayBlocked()) {
                mutedTried = true;
                startMuted(playerVideo()).then(started => {
                    if (!started) {
                        finish(false, 'Le navigateur a bloqué la lecture automatique. Clique sur Lire dans Jellyfin.');
                    }
                });
                return;
            }

            if (performance.now() - startedAt >= 20000) {
                finish(false, 'Jellyfin n’a pas démarré la vidéo. Le navigateur peut bloquer la lecture automatique.');
                return;
            }

            if (clicked || currentItemId() !== itemId) return;
            const button = findPlayButton();
            if (!button) return;

            // A synthetic click can open Jellyfin's player, but Chrome may still
            // block audible autoplay. Never click again: that can pause or stop it.
            clicked = true;
            clickAt = performance.now();
            button.click();
        }, 250);
    }

    function handlePlayRequest(event) {
        const request = event.data;
        if (event.source !== window.opener || !request || request.type !== requestType
            || !request.requestId || !request.itemId) return;
        startPlayback(request.itemId, request.requestId, event.origin);
    }

    function handleLegacyLaunch() {
        if (new URLSearchParams(window.location.search).get('backstagePlay') !== '1') return;
        const itemId = currentItemId();
        if (!itemId) return;
        startPlayback(itemId);
    }

    window.addEventListener('message', handlePlayRequest);
    handleLegacyLaunch();
})();
