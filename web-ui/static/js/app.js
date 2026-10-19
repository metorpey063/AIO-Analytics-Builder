/**
 * AIO Analytics Builder — Shared UI utilities
 */

function showResult(elementId, ok, message) {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.textContent = message;
    el.className = 'test-result ' + (ok === null ? 'loading' : ok ? 'ok' : 'err');
}

// Collapsible guide steps — only top-level title toggles
document.addEventListener('click', (e) => {
    const strong = e.target.closest('.guide-step > div > strong:first-child');
    if (strong) {
        const step = strong.closest('.guide-step');
        if (step) step.classList.toggle('collapsed');
    }
});

// Copy button
function copyText(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
        btn.classList.add('copied');
        btn.textContent = '✓';
        setTimeout(() => { btn.classList.remove('copied'); btn.textContent = '⧉'; }, 1500);
    });
}

// Check for updates on page load
document.addEventListener('DOMContentLoaded', checkVersion);

async function checkVersion() {
    try {
        const r = await fetch('/api/version');
        const j = await r.json();
        const btn = document.getElementById('update-btn');

        if (j.update_available) {
            btn.className = 'update-btn update-btn-active';
            btn.disabled = false;
            btn.title = `Update available: v${j.remote} (you have v${j.local})`;
            const versionEl = document.getElementById('brand-version');
            versionEl.textContent = `v${j.local} — update available`;
            versionEl.classList.add('version-outdated');

            // Show update banner at top of page
            const existing = document.getElementById('update-banner');
            if (!existing) {
                const banner = document.createElement('div');
                banner.id = 'update-banner';
                banner.className = 'update-banner';
                banner.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`
                    + `<span><strong>A new version of AIO is available</strong> (v${j.remote}). Click the <strong>update button</strong> in the upper left to update.</span>`
                    + `<button onclick="this.parentElement.remove()" class="update-banner-close">&times;</button>`;
                const content = document.querySelector('.content');
                if (content) content.prepend(banner);
            }
        } else {
            btn.className = 'update-btn update-btn-gray';
            btn.disabled = true;
            btn.title = `Up to date (v${j.local})`;
        }
    } catch (e) {
        // Silently fail — offline or no git
    }
}

async function runUpdate() {
    const btn = document.getElementById('update-btn');
    btn.classList.add('spinning');
    btn.disabled = true;

    try {
        const r = await fetch('/api/update', {method: 'POST'});
        const j = await r.json();

        if (j.ok && j.updated) {
            btn.className = 'update-btn update-success';
            document.getElementById('brand-version').textContent = 'Restarting...';
            // Server restarts automatically — wait for it to come back, then reload
            async function waitForServer() {
                for (let i = 0; i < 15; i++) {
                    await new Promise(r => setTimeout(r, 1000));
                    try {
                        const ping = await fetch('/api/version', {signal: AbortSignal.timeout(2000)});
                        if (ping.ok) { location.reload(); return; }
                    } catch (e) { /* server still restarting */ }
                }
                document.getElementById('brand-version').textContent = 'Restart timed out';
                if (confirm('Server restart took too long. Reload manually?')) location.reload();
            }
            waitForServer();
        } else if (j.ok) {
            btn.className = 'update-btn update-btn-gray';
            btn.disabled = true;
            btn.title = 'Already up to date';
        } else {
            btn.title = 'Update failed: ' + j.output;
            btn.classList.add('update-error');
            setTimeout(() => { btn.classList.remove('update-error'); btn.disabled = false; }, 3000);
        }
    } catch (e) {
        btn.title = 'Update failed: ' + e.message;
    }

    btn.classList.remove('spinning');
}
