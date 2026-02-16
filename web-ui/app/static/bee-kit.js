/**
 * BeeKit — переиспользуемый UI toolkit для Telegram Mini App.
 * Компоненты: Bottom Sheet, Accordion, Stale Indicator, Dashboard Poll, Auto-Haptic.
 */
(function() {
    'use strict';

    function $(id) { return document.getElementById(id); }

    // ── Bottom Sheet ──────────────────────────────────────────────

    var sheet = {
        open: function(title, bodyHtml, toolbarHtml) {
            $('bee-sheet-title').textContent = title || '';
            $('bee-sheet-toolbar').innerHTML = toolbarHtml || '';
            $('bee-sheet-body').innerHTML = bodyHtml || '';
            $('bee-sheet-overlay').classList.add('active');
            $('bee-sheet').classList.add('active');
            if (window.haptic) haptic('impact', 'light');
        },
        close: function() {
            $('bee-sheet-overlay').classList.remove('active');
            $('bee-sheet').classList.remove('active');
        },
        _init: function() {
            var overlay = $('bee-sheet-overlay');
            var close = $('bee-sheet-close');
            if (overlay) overlay.addEventListener('click', sheet.close);
            if (close) close.addEventListener('click', sheet.close);
        }
    };

    // ── Accordion ─────────────────────────────────────────────────

    function initAccordions() {
        var items = document.querySelectorAll('[data-bee-accordion]');
        for (var i = 0; i < items.length; i++) {
            (function(el) {
                var header = el.querySelector('.bee-accordion__header');
                if (!header || header._beeReady) return;
                header._beeReady = true;
                header.addEventListener('click', function() {
                    el.classList.toggle('bee-accordion--open');
                    if (window.haptic) haptic('selection');
                });
            })(items[i]);
        }
    }

    // ── Stale Data Indicator ──────────────────────────────────────

    var stale = {
        _el: null,
        _get: function() {
            if (!stale._el) {
                stale._el = $('bee-stale');
                if (!stale._el) {
                    var el = document.createElement('div');
                    el.id = 'bee-stale';
                    el.className = 'bee-stale';
                    var bar = $('bee-bar');
                    if (bar && bar.parentNode) {
                        bar.parentNode.insertBefore(el, bar.nextSibling);
                    } else {
                        document.body.appendChild(el);
                    }
                    stale._el = el;
                }
            }
            return stale._el;
        },
        show: function(msg) {
            var el = stale._get();
            el.textContent = msg || 'Данные могут быть устаревшими';
            el.classList.add('bee-stale--visible');
        },
        hide: function() {
            var el = stale._get();
            el.classList.remove('bee-stale--visible');
        }
    };

    // ── Dashboard Poll ────────────────────────────────────────────

    function poll(url, intervalMs, opts) {
        opts = opts || {};
        var onData = opts.onData || function() {};
        var onError = opts.onError || function() {};
        var onAccessDenied = opts.onAccessDenied || function() {};
        var staleAfter = opts.staleAfter || 3;
        var initData = opts.initData || '';
        var started = false;
        var failCount = 0;

        function doFetch() {
            var headers = {};
            if (initData) headers['X-Init-Data'] = initData;

            fetch(url, { headers: headers })
                .then(function(r) {
                    if (r.status === 403 || r.status === 401) {
                        onAccessDenied(r.status);
                        return null;
                    }
                    if (!r.ok) {
                        failCount++;
                        if (failCount >= staleAfter) stale.show();
                        if (!started) onError(r.status);
                        return null;
                    }
                    return r.json();
                })
                .then(function(data) {
                    if (!data) return;
                    failCount = 0;
                    stale.hide();
                    if (!started) {
                        started = true;
                        var loading = $('mod-loading');
                        var content = $('mod-content');
                        // Crossfade: skeleton fade-out → content fade-in
                        if (loading) {
                            loading.style.transition = 'opacity .2s ease';
                            loading.style.opacity = '0';
                            setTimeout(function() { loading.style.display = 'none'; }, 220);
                        }
                        if (content) {
                            content.style.opacity = '0';
                            content.style.transition = 'opacity .3s ease';
                            content.style.display = '';
                            requestAnimationFrame(function() {
                                requestAnimationFrame(function() {
                                    content.style.opacity = '1';
                                });
                            });
                        }
                    }
                    onData(data);
                })
                .catch(function(e) {
                    console.warn('BeeKit.poll error:', e);
                    failCount++;
                    if (failCount >= staleAfter) stale.show();
                    if (!started) onError(0);
                });
        }

        doFetch();
        return setInterval(doFetch, intervalMs);
    }

    // ── Auto-Haptic ───────────────────────────────────────────────

    function initAutoHaptic() {
        document.addEventListener('click', function(e) {
            var el = e.target.closest('[data-haptic]');
            if (el && window.haptic) {
                var type = el.getAttribute('data-haptic') || 'impact';
                haptic(type, 'light');
            }
        }, true);
    }

    // ── Init ──────────────────────────────────────────────────────

    function init() {
        sheet._init();
        initAccordions();
        initAutoHaptic();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // MutationObserver для динамически добавленных аккордеонов
    var obs = new MutationObserver(function() { initAccordions(); });
    obs.observe(document.body || document.documentElement, { childList: true, subtree: true });

    // ── Public API ────────────────────────────────────────────────

    window.BeeKit = {
        sheet: sheet,
        stale: stale,
        poll: poll,
        initAccordions: initAccordions
    };
})();
