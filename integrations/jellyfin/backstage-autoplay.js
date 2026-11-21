(() => {
    'use strict';

    const launchHash = window.location.hash;
    const detailsRoute = '#/details?';
    if (!launchHash.startsWith(detailsRoute)) return;

    const params = new URLSearchParams(launchHash.slice(detailsRoute.length));
    const pageParams = new URLSearchParams(window.location.search);
    const markerInSearch = pageParams.get('backstagePlay') === '1';
    const markerInHash = params.get('backstagePlay') === '1';
    if ((!markerInSearch && !markerInHash) || !params.get('id')) return;

    const buttonArea = '#itemDetailPage';
    const deadline = performance.now() + 15000;

    function consumeMarker() {
        window.clearInterval(timer);
        document.removeEventListener('click', onManualPlay, true);

        // Consume the marker so Back and Refresh do not restart playback.
        if (window.location.hash === launchHash) {
            params.delete('backstagePlay');
            const url = new URL(window.location.href);
            url.hash = `${detailsRoute}${params}`;
            if (markerInSearch) {
                const currentPageParams = new URLSearchParams(url.search);
                currentPageParams.delete('backstagePlay');
                url.search = currentPageParams.toString();
            }
            window.history.replaceState(window.history.state, '', url);
        }
    }

    function stopWatching() {
        window.clearInterval(timer);
    }

    function isPlaybackButton(element) {
        if (!(element instanceof Element)) return false;
        const name = [
            element.getAttribute('aria-label'),
            element.getAttribute('title'),
            element.textContent,
            element.className,
            element.getAttribute('data-action'),
        ].filter(Boolean).join(' ').toLowerCase();
        return /btnplay|btnresume|\b(play|resume|lire|lecture|reprendre|continuer)\b/.test(name);
    }

    function onManualPlay(event) {
        if (!(event.target instanceof Element)) return;
        const button = event.target.closest('button, [role="button"], .button-flat');
        if (button?.closest(buttonArea) && isPlaybackButton(button)) consumeMarker();
    }

    function findVisibleButton(area, kind) {
        const candidates = Array.from(area.querySelectorAll('button, [role="button"], .button-flat'));
        const preferred = candidates.filter(button => {
            const classes = typeof button.className === 'string' ? button.className : '';
            const action = (button.getAttribute('data-action') || '').toLowerCase();
            return kind === 'resume'
                ? /btnResume/i.test(classes) || action === 'resume'
                : /btnPlay/i.test(classes) && action !== 'resume';
        });
        const labelled = candidates.filter(button => {
            if (!isPlaybackButton(button)) return false;
            const label = [button.getAttribute('aria-label'), button.getAttribute('title'), button.textContent]
                .filter(Boolean).join(' ').toLowerCase();
            return kind === 'resume'
                ? /resume|reprendre|continuer/.test(label)
                : /play|lire|lecture/.test(label) && !/resume|reprendre|continuer/.test(label);
        });
        return [...preferred, ...labelled].find(button =>
            !button.disabled &&
            !button.closest('[hidden], .hide, [aria-hidden="true"]') &&
            button.getClientRects().length > 0 &&
            window.getComputedStyle(button).visibility === 'visible'
        );
    }

    function tryPlayback() {
        if (window.location.hash !== launchHash) {
            stopWatching();
            return;
        }
        if (performance.now() >= deadline) {
            // Keep the launch marker if Jellyfin has not rendered a play control
            // yet. This lets the user start manually and avoids silently losing
            // the request when Jellyfin changes its details-page markup.
            stopWatching();
            return;
        }

        if (document.visibilityState !== 'visible') return;
        const area = document.querySelector(`${buttonArea} .mainDetailButtons`) || document.querySelector(buttonArea);
        if (!area) return;

        const button = findVisibleButton(area, 'resume') || findVisibleButton(area, 'play');
        if (!button) return;

        consumeMarker();
        button.click();
    }

    document.addEventListener('click', onManualPlay, true);
    const timer = window.setInterval(tryPlayback, 150);
})();
