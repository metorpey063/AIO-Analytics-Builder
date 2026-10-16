/**
 * AIO Analytics Builder — Shared UI utilities
 */

function showResult(elementId, ok, message) {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.textContent = message;
    el.className = 'test-result ' + (ok === null ? 'loading' : ok ? 'ok' : 'err');
}
