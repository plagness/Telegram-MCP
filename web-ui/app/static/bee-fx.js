/**
 * BeeFX — визуальные эффекты для Telegram Mini App.
 * Портировано из react-bits (vanilla JS, без React).
 * Компоненты: CountUp, RevealText, FadeIn, Spotlight, ClickSpark, Ripple.
 */
(function() {
    'use strict';

    // ── CountUp — анимация чисел ────────────────────────────────────

    function countUp(el, from, to, opts) {
        opts = opts || {};
        var duration = opts.duration || 1500;
        var decimals = opts.decimals != null ? opts.decimals : 0;
        var prefix = opts.prefix || '';
        var suffix = opts.suffix || '';
        var sep = opts.separator != null ? opts.separator : ' ';

        function format(n) {
            var parts = n.toFixed(decimals).split('.');
            if (sep) parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, sep);
            return prefix + parts.join('.') + suffix;
        }

        function easeOut(t) { return t * (2 - t); }

        function run() {
            var start = performance.now();
            el.textContent = format(from);

            function tick(now) {
                var t = Math.min((now - start) / duration, 1);
                var val = from + (to - from) * easeOut(t);
                el.textContent = format(val);
                if (t < 1) requestAnimationFrame(tick);
            }

            requestAnimationFrame(tick);
        }

        // IntersectionObserver — запуск при видимости
        if ('IntersectionObserver' in window) {
            var obs = new IntersectionObserver(function(entries) {
                if (entries[0].isIntersecting) {
                    obs.disconnect();
                    run();
                }
            }, { threshold: 0.1 });
            obs.observe(el);
        } else {
            run();
        }
    }

    // ── RevealText — посимвольное раскрытие ─────────────────────────

    function revealText(el, opts) {
        opts = opts || {};
        var mode = opts.mode || 'blur';      // 'blur' | 'slide' | 'both'
        var by = opts.by || 'char';           // 'char' | 'word'
        var delay = opts.delay != null ? opts.delay : 40;
        var once = opts.once !== false;

        var text = el.textContent;
        el.textContent = '';
        el.setAttribute('aria-label', text);

        var parts = by === 'word' ? text.split(/(\s+)/) : text.split('');
        var spans = [];

        for (var i = 0; i < parts.length; i++) {
            var span = document.createElement('span');
            span.textContent = parts[i] || '';
            // Пробел без анимации
            if (/^\s+$/.test(parts[i])) {
                span.style.whiteSpace = 'pre';
                el.appendChild(span);
                continue;
            }
            span.className = 'bee-char' + (mode === 'slide' ? ' bee-char--slide' : '');
            span.style.transitionDelay = (spans.length * delay) + 'ms';
            el.appendChild(span);
            spans.push(span);
        }

        function reveal() {
            for (var j = 0; j < spans.length; j++) {
                spans[j].classList.add('bee-char--visible');
            }
        }

        if ('IntersectionObserver' in window) {
            var obs = new IntersectionObserver(function(entries) {
                if (entries[0].isIntersecting) {
                    if (once) obs.disconnect();
                    reveal();
                }
            }, { threshold: 0.1 });
            obs.observe(el);
        } else {
            reveal();
        }
    }

    // ── FadeIn + Stagger — каскадное появление при скролле ──────────

    var fadeObserver = null;

    function initFadeIn() {
        if (!('IntersectionObserver' in window)) {
            // Fallback: показать всё сразу
            var all = document.querySelectorAll('.bee-fade-in');
            for (var i = 0; i < all.length; i++) all[i].classList.add('bee-fade-in--visible');
            return;
        }

        if (fadeObserver) fadeObserver.disconnect();

        fadeObserver = new IntersectionObserver(function(entries) {
            for (var i = 0; i < entries.length; i++) {
                if (!entries[i].isIntersecting) continue;
                var el = entries[i].target;
                fadeObserver.unobserve(el);

                // Авто-стаггер: считаем индекс среди видимых сиблингов с .bee-fade-in
                var staggerDelay = 0;
                var customDelay = el.getAttribute('data-fade-delay');
                if (customDelay) {
                    staggerDelay = parseInt(customDelay, 10) || 0;
                } else {
                    var siblings = el.parentNode ? el.parentNode.querySelectorAll(':scope > .bee-fade-in') : [];
                    for (var j = 0; j < siblings.length; j++) {
                        if (siblings[j] === el) { staggerDelay = j * 50; break; }
                    }
                }

                if (staggerDelay > 0) {
                    el.style.transitionDelay = staggerDelay + 'ms';
                }
                el.classList.add('bee-fade-in--visible');
            }
        }, { threshold: 0.1 });

        var items = document.querySelectorAll('.bee-fade-in:not(.bee-fade-in--visible)');
        for (var k = 0; k < items.length; k++) fadeObserver.observe(items[k]);
    }

    // ── Spotlight — подсветка за пальцем ────────────────────────────

    function initSpotlight() {
        document.addEventListener('touchmove', function(e) {
            var el = e.target.closest('[data-spotlight]');
            if (!el || !e.touches.length) return;
            var rect = el.getBoundingClientRect();
            var x = e.touches[0].clientX - rect.left;
            var y = e.touches[0].clientY - rect.top;
            el.style.setProperty('--spot-x', x + 'px');
            el.style.setProperty('--spot-y', y + 'px');
        }, { passive: true });

        document.addEventListener('touchend', function(e) {
            var el = e.target.closest('[data-spotlight]');
            if (el) {
                el.style.removeProperty('--spot-x');
                el.style.removeProperty('--spot-y');
            }
        }, { passive: true });
    }

    // ── ClickSpark — искры при тапе ─────────────────────────────────

    function clickSpark(container, opts) {
        opts = opts || {};
        var count = opts.count || 8;
        var size = opts.size || 10;
        var radius = opts.radius || 15;
        var duration = opts.duration || 400;
        var color = opts.color || null;

        function getAccent() {
            if (color) return color;
            return getComputedStyle(document.body).getPropertyValue('--accent').trim() || '#FFC107';
        }

        function easeOut(t) { return 1 - Math.pow(1 - t, 3); }

        container.addEventListener('touchstart', function handler(e) {
            if (!e.touches.length) return;
            var rect = container.getBoundingClientRect();
            var cx = e.touches[0].clientX - rect.left;
            var cy = e.touches[0].clientY - rect.top;

            var canvas = document.createElement('canvas');
            canvas.width = rect.width;
            canvas.height = rect.height;
            canvas.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none;z-index:10';
            container.style.position = container.style.position || 'relative';
            container.appendChild(canvas);
            var ctx = canvas.getContext('2d');
            var c = getAccent();

            var sparks = [];
            for (var i = 0; i < count; i++) {
                sparks.push({ angle: (2 * Math.PI * i) / count });
            }

            var start = performance.now();

            function draw(now) {
                var t = Math.min((now - start) / duration, 1);
                var eased = easeOut(t);
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.strokeStyle = c;
                ctx.lineWidth = 2;
                ctx.lineCap = 'round';
                ctx.globalAlpha = 1 - eased;

                for (var j = 0; j < sparks.length; j++) {
                    var s = sparks[j];
                    var dist = eased * radius;
                    var len = size * (1 - eased);
                    var x1 = cx + dist * Math.cos(s.angle);
                    var y1 = cy + dist * Math.sin(s.angle);
                    var x2 = cx + (dist + len) * Math.cos(s.angle);
                    var y2 = cy + (dist + len) * Math.sin(s.angle);
                    ctx.beginPath();
                    ctx.moveTo(x1, y1);
                    ctx.lineTo(x2, y2);
                    ctx.stroke();
                }

                if (t < 1) {
                    requestAnimationFrame(draw);
                } else {
                    container.removeChild(canvas);
                }
            }

            requestAnimationFrame(draw);
        }, { passive: true });
    }

    // ── Ripple — Material Design touch feedback ─────────────────────

    function initRipple() {
        document.addEventListener('touchstart', function(e) {
            var el = e.target.closest('.bee-ripple, [data-ripple]');
            if (!el || !e.touches.length) return;

            var rect = el.getBoundingClientRect();
            var x = e.touches[0].clientX - rect.left;
            var y = e.touches[0].clientY - rect.top;
            var dim = Math.max(rect.width, rect.height) * 2;

            var wave = document.createElement('span');
            wave.className = 'bee-ripple__wave';
            wave.style.width = wave.style.height = dim + 'px';
            wave.style.left = (x - dim / 2) + 'px';
            wave.style.top = (y - dim / 2) + 'px';

            el.appendChild(wave);

            wave.addEventListener('animationend', function() {
                if (wave.parentNode) wave.parentNode.removeChild(wave);
            });
        }, { passive: true });
    }

    // ── Auto-Init ───────────────────────────────────────────────────

    function init() {
        initFadeIn();
        initSpotlight();
        initRipple();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // MutationObserver для динамически добавленных .bee-fade-in
    var fxObs = new MutationObserver(function(mutations) {
        var needRefresh = false;
        for (var i = 0; i < mutations.length; i++) {
            if (mutations[i].addedNodes.length) { needRefresh = true; break; }
        }
        if (needRefresh && fadeObserver) {
            var items = document.querySelectorAll('.bee-fade-in:not(.bee-fade-in--visible)');
            for (var k = 0; k < items.length; k++) fadeObserver.observe(items[k]);
        }
    });
    fxObs.observe(document.body || document.documentElement, { childList: true, subtree: true });

    // ── Public API ──────────────────────────────────────────────────

    window.BeeFX = {
        countUp: countUp,
        revealText: revealText,
        clickSpark: clickSpark,
        initFadeIn: initFadeIn,
        initSpotlight: initSpotlight,
        initRipple: initRipple
    };
})();
