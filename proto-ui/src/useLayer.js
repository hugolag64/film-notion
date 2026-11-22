import { useEffect, useRef } from 'react';

/*
 * One stack for every overlay (detail sheet, dialogs, admin, account…).
 * - Escape and the browser/phone Back button close the TOP layer only.
 * - Each open layer adds a history entry, so Back closes it instead of
 *   leaving the app.
 * - Focus moves into the layer, Tab stays inside it, and focus returns to
 *   the element that opened it when it closes.
 * - Everything outside the top layer is made `inert` (no clicks, no focus,
 *   hidden from screen readers), except elements marked data-layer-keep.
 */
const stack = [];
let popsToIgnore = 0;
let listening = false;

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusables(container) {
    return [...container.querySelectorAll(FOCUSABLE)].filter((element) => element.getClientRects().length > 0);
}

let inertElements = [];

function refreshInert() {
    inertElements.forEach((element) => element.removeAttribute('inert'));
    inertElements = [];
    const container = stack[stack.length - 1]?.ref.current;
    if (!container) return;
    // Walk up to <body>, marking every sibling of the layer's ancestors.
    for (let node = container; node && node !== document.body; node = node.parentElement) {
        const parent = node.parentElement;
        if (!parent) break;
        for (const sibling of parent.children) {
            if (sibling === node || sibling.hasAttribute('inert') || sibling.hasAttribute('data-layer-keep')) continue;
            if (['SCRIPT', 'STYLE'].includes(sibling.tagName)) continue;
            sibling.setAttribute('inert', '');
            inertElements.push(sibling);
        }
    }
}

function onPopState() {
    if (popsToIgnore > 0) {
        popsToIgnore -= 1;
        return;
    }
    const top = stack[stack.length - 1];
    if (top) {
        top.closedByHistory = true;
        top.close();
    }
}

function onKeyDown(event) {
    const top = stack[stack.length - 1];
    if (!top) return;
    if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        top.close();
        return;
    }
    const container = top.ref.current;
    if (event.key !== 'Tab' || !container) return;
    const items = focusables(container);
    if (!items.length) {
        event.preventDefault();
        container.focus();
        return;
    }
    const first = items[0];
    const last = items[items.length - 1];
    const inside = container.contains(document.activeElement);
    if (event.shiftKey && (document.activeElement === first || !inside)) {
        event.preventDefault();
        last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !inside)) {
        event.preventDefault();
        first.focus();
    }
}

function ensureListeners() {
    if (listening) return;
    listening = true;
    window.addEventListener('popstate', onPopState);
    // Capture phase: runs before any component-level Escape handler.
    window.addEventListener('keydown', onKeyDown, true);
}

/**
 * Register an overlay while `open` is true. Returns a ref to put on the
 * dialog container (it receives focus when nothing inside is focusable).
 * `url` (optional) is shown in the address bar while the layer is open, so
 * the page can be shared; closing it brings the previous address back.
 */
export default function useLayer(open, onClose, url) {
    const ref = useRef(null);
    const closeRef = useRef(onClose);
    closeRef.current = onClose;
    const urlRef = useRef(url);
    urlRef.current = url;

    useEffect(() => {
        if (!open) return undefined;
        ensureListeners();
        const opener = document.activeElement;
        const entry = {ref, closedByHistory: false, close: () => closeRef.current?.()};
        stack.push(entry);
        window.history.pushState({backstageLayer: stack.length}, '', urlRef.current || window.location.href);

        const frame = window.requestAnimationFrame(() => {
            refreshInert();
            const container = ref.current;
            if (!container || container.contains(document.activeElement)) return;
            const autofocus = container.querySelector('[autofocus], [data-autofocus]');
            (autofocus || focusables(container)[0] || container).focus({preventScroll: true});
        });

        return () => {
            window.cancelAnimationFrame(frame);
            const index = stack.indexOf(entry);
            if (index !== -1) stack.splice(index, 1);
            refreshInert();
            if (!entry.closedByHistory) {
                // Closed from the UI: drop the history entry we added.
                popsToIgnore += 1;
                window.history.back();
            }
            if (opener instanceof HTMLElement && opener.isConnected) opener.focus({preventScroll: true});
        };
    }, [open]);

    return ref;
}
