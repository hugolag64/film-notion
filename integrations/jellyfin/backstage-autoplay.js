(() => {
    'use strict';

    const launchHash = window.location.hash;
    const detailsRoute = '#/details?';
    if (!launchHash.startsWith(detailsRoute)) return;

    const params = new URLSearchParams(launchHash.slice(detailsRoute.length));
    if (params.get('backstagePlay') !== '1' || !params.get('id')) return;

    const buttonArea = '#itemDetailPage .mainDetailButtons';
    const playSelector = 'button.btnPlay';
    const resumeSelector = 'button.btnResume, button.btnPlay[data-action="resume"]';
    const deadline = performance.now() + 15000;

    function finish() {
        window.clearInterval(timer);
        document.removeEventListener('click', onManualPlay, true);

        // Consume the marker so Back and Refresh do not restart playback.
        if (window.location.hash === launchHash) {
            params.delete('backstagePlay');
            const url = new URL(window.location.href);
            url.hash = `${detailsRoute}${params}`;
            window.history.replaceState(window.history.state, '', url);
        }
    }

    function onManualPlay(event) {
        if (!(event.target instanceof Element)) return;
        const button = event.target.closest(`${playSelector}, ${resumeSelector}`);
        if (button?.closest(buttonArea)) finish();
    }

    function findVisibleButton(area, selector) {
        return Array.from(area.querySelectorAll(selector)).find(button =>
            !button.disabled &&
            !button.closest('[hidden], .hide, [aria-hidden="true"]') &&
            button.getClientRects().length > 0 &&
            window.getComputedStyle(button).visibility === 'visible'
        );
    }

    function tryPlayback() {
        if (window.location.hash !== launchHash || performance.now() >= deadline) {
            finish();
            return;
        }

        if (document.visibilityState !== 'visible') return;
        const area = document.querySelector(buttonArea);
        if (!area) return;

        const button = findVisibleButton(area, resumeSelector) || findVisibleButton(area, playSelector);
        if (!button) return;

        finish();
        button.click();
    }

    document.addEventListener('click', onManualPlay, true);
    const timer = window.setInterval(tryPlayback, 150);
})();
