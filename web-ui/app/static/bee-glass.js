/**
 * Bee Liquid Glass — двухслойный SVG displacement + backdrop-filter.
 *
 * Адаптация liquid-glass от Shu Ding (https://github.com/shuding/liquid-glass)
 * Фичи вдохновлены callstack/liquid-glass (https://github.com/callstack/liquid-glass)
 * Лицензия: MIT. Оригинальный автор displacement map: Shu Ding, 2025.
 *
 * Техника двухслойного glass (итерация 2):
 * 1. Дочерний div .bee-glass-refract:
 *    - backdrop-filter: blur() saturate() — захватывает и блюрит фон
 *    - filter: url(#svgFilter) — применяет SVG displacement к РЕЗУЛЬТАТУ backdrop-filter
 * 2. Результат: рефракция (линзовое искажение) на краях стекла видна,
 *    потому что displacement применяется ПОСЛЕ backdrop-filter.
 *
 * Ключевые отличия от итерации 1:
 * - Фон элемента transparent (не rgba)
 * - displacement scale 100 (было 35) — реально видимое искажение
 * - DPR 0.75 (было 0.5) — чётче рефракция
 * - Tint opacity 0.08/0.12 (было 0.25/0.35) — не перекрывает эффект
 * - computedScale = прямое значение (без деления на dpr*40)
 */
(function() {
    'use strict';

    // ── Feature Detection ─────────────────────

    var _supported = null;

    function checkSupport() {
        if (_supported !== null) return _supported;
        var el = document.createElement('div');
        el.style.cssText = 'backdrop-filter:blur(1px);-webkit-backdrop-filter:blur(1px)';
        var hasBackdrop = !!el.style.backdropFilter || !!el.style.webkitBackdropFilter;
        var hasSVG = typeof document.createElementNS === 'function';
        _supported = hasBackdrop && hasSVG;
        return _supported;
    }

    // ── Effect Presets ────────────────────────

    var PRESETS = {
        // regular — стандартный liquid glass с рефракцией на краях
        regular: {
            displacementScale: 100,
            blur: 16,
            saturate: 180,
            brightness: 105,
            contrast: 100,
            shadow: true,
            specular: true,
        },
        // clear — прозрачное стекло, минимальный blur, сильная рефракция
        clear: {
            displacementScale: 120,
            blur: 6,
            saturate: 140,
            brightness: 110,
            contrast: 100,
            shadow: true,
            specular: true,
        },
        // none — без эффекта
        none: {
            displacementScale: 0,
            blur: 0,
            saturate: 100,
            brightness: 100,
            contrast: 100,
            shadow: false,
            specular: false,
        },
    };

    // ── Color Scheme Defaults ─────────────────
    // Тонкий tint — НЕ перекрывает рефракцию

    var SCHEMES = {
        light: {
            tintColor: 'rgba(255, 255, 255, 0.08)',
            shadowColor: 'rgba(0, 0, 0, 0.08)',
            specularColor: 'rgba(255, 255, 255, 0.45)',
            borderColor: 'rgba(255, 255, 255, 0.35)',
        },
        dark: {
            tintColor: 'rgba(40, 40, 40, 0.12)',
            shadowColor: 'rgba(0, 0, 0, 0.25)',
            specularColor: 'rgba(255, 255, 255, 0.12)',
            borderColor: 'rgba(255, 255, 255, 0.08)',
        },
    };

    function resolveScheme(name) {
        if (name === 'light' || name === 'dark') return SCHEMES[name];
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return SCHEMES.dark;
        }
        return SCHEMES.light;
    }

    // ── Математические утилиты ──────────────

    function smoothStep(a, b, t) {
        t = Math.max(0, Math.min(1, (t - a) / (b - a)));
        return t * t * (3 - 2 * t);
    }

    function vecLength(x, y) {
        return Math.sqrt(x * x + y * y);
    }

    function roundedRectSDF(x, y, w, h, r) {
        var qx = Math.abs(x) - w + r;
        var qy = Math.abs(y) - h + r;
        return Math.min(Math.max(qx, qy), 0) + vecLength(Math.max(qx, 0), Math.max(qy, 0)) - r;
    }

    // ── Генератор displacement map ──────────

    var _counter = 0;

    function generateDisplacementFilter(opts) {
        var w = opts.width || 300;
        var h = opts.height || 56;
        var scale = opts.displacementScale || 100;
        var borderRadius = opts.borderRadius != null ? opts.borderRadius : 18;
        var id = 'bee-glass-' + (++_counter);

        if (scale <= 0) {
            return { svg: null, filterId: null, canvas: null };
        }

        var aspect = w / h;
        var rectW = 0.48;
        var rectH = rectW / aspect;
        var sdfRadius = borderRadius > 0 ? (borderRadius / Math.min(w, h)) * 2 : 0.01;

        // Canvas для displacement map (0.75 DPR — баланс качества и производительности)
        var canvas = document.createElement('canvas');
        var dpr = 0.75;
        var cw = Math.round(w * dpr);
        var ch = Math.round(h * dpr);
        canvas.width = cw;
        canvas.height = ch;
        var ctx = canvas.getContext('2d');

        var data = new Uint8ClampedArray(cw * ch * 4);
        var maxDisp = 0;
        var raw = [];

        for (var i = 0; i < data.length; i += 4) {
            var px = (i / 4) % cw;
            var py = Math.floor(i / 4 / cw);
            var ux = px / cw - 0.5;
            var uy = py / ch - 0.5;

            var dist = roundedRectSDF(ux, uy, rectW, rectH, sdfRadius);
            var disp = smoothStep(0.8, 0, dist - 0.12);
            var scaled = smoothStep(0, 1, disp);

            var dx = ux * scaled - ux;
            var dy = uy * scaled - uy;

            maxDisp = Math.max(maxDisp, Math.abs(dx), Math.abs(dy));
            raw.push(dx, dy);
        }

        if (maxDisp === 0) maxDisp = 1;
        maxDisp *= 0.5;

        var idx = 0;
        for (var j = 0; j < data.length; j += 4) {
            data[j]     = (raw[idx++] / maxDisp + 0.5) * 255;
            data[j + 1] = (raw[idx++] / maxDisp + 0.5) * 255;
            data[j + 2] = 0;
            data[j + 3] = 255;
        }

        ctx.putImageData(new ImageData(data, cw, ch), 0, 0);
        var dataUrl = canvas.toDataURL();

        // Прямое значение scale — без нормализации через dpr*40
        var computedScale = scale;

        // SVG filter
        var svgNS = 'http://www.w3.org/2000/svg';
        var xlinkNS = 'http://www.w3.org/1999/xlink';

        var svg = document.createElementNS(svgNS, 'svg');
        svg.setAttribute('width', '0');
        svg.setAttribute('height', '0');
        svg.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none;';

        var defs = document.createElementNS(svgNS, 'defs');
        var filter = document.createElementNS(svgNS, 'filter');
        filter.setAttribute('id', id);
        filter.setAttribute('filterUnits', 'userSpaceOnUse');
        filter.setAttribute('colorInterpolationFilters', 'sRGB');
        filter.setAttribute('x', '0');
        filter.setAttribute('y', '0');
        filter.setAttribute('width', w.toString());
        filter.setAttribute('height', h.toString());

        var feImage = document.createElementNS(svgNS, 'feImage');
        feImage.setAttributeNS(xlinkNS, 'href', dataUrl);
        feImage.setAttribute('result', 'dispMap');
        feImage.setAttribute('width', w.toString());
        feImage.setAttribute('height', h.toString());

        var feDisp = document.createElementNS(svgNS, 'feDisplacementMap');
        feDisp.setAttribute('in', 'SourceGraphic');
        feDisp.setAttribute('in2', 'dispMap');
        feDisp.setAttribute('scale', computedScale.toString());
        feDisp.setAttribute('xChannelSelector', 'R');
        feDisp.setAttribute('yChannelSelector', 'G');

        filter.appendChild(feImage);
        filter.appendChild(feDisp);
        defs.appendChild(filter);
        svg.appendChild(defs);

        return { svg: svg, filterId: id, canvas: canvas };
    }

    // ── Tint Overlay ──────────────────────────

    function createTintOverlay(el, color) {
        var overlay = document.createElement('div');
        overlay.className = 'bee-glass-tint';
        overlay.style.cssText =
            'position:absolute;top:0;left:0;right:0;bottom:0;' +
            'background:' + color + ';' +
            'pointer-events:none;border-radius:inherit;' +
            'transition:background 0.3s ease;z-index:1;';
        var pos = getComputedStyle(el).position;
        if (pos === 'static') el.style.position = 'relative';
        el.insertBefore(overlay, el.firstChild);
        return overlay;
    }

    // ── Specular Highlight ────────────────────

    function applySpecular(el, color) {
        var highlight = document.createElement('div');
        highlight.className = 'bee-glass-specular';
        highlight.style.cssText =
            'position:absolute;top:0;left:0;right:0;height:1px;' +
            'background:linear-gradient(90deg,transparent 5%,' + color + ' 30%,' + color + ' 70%,transparent 95%);' +
            'pointer-events:none;border-radius:inherit;' +
            'transition:opacity 0.3s ease;z-index:2;';
        var pos = getComputedStyle(el).position;
        if (pos === 'static') el.style.position = 'relative';
        el.insertBefore(highlight, el.firstChild);
        return highlight;
    }

    // ── Squircle Corners ──────────────────────

    function applySquircle(el, radius) {
        if (radius > 0) {
            el.style.borderRadius = radius + 'px';
            el.style.webkitBorderRadiusCurve = 'continuous';
            el.style.setProperty('border-radius-curve', 'continuous');
        }
    }

    // ── Публичный API ─────────────────────────

    /**
     * Применить liquid glass к элементу (двухслойный подход).
     *
     * Вместо backdrop-filter с url(#svg) на самом элементе,
     * создаём дочерний div .bee-glass-refract:
     * - backdrop-filter: blur() saturate() — захватывает фон
     * - filter: url(#svgDisplacement) — рефракция применяется к результату
     *
     * @param {HTMLElement} el — целевой элемент
     * @param {Object} opts — опции (см. PRESETS)
     * @returns {Object} — { filterId, effect, setEffect, setTint, destroy }
     */
    function applyLiquidGlass(el, opts) {
        if (!el) return null;
        opts = opts || {};

        if (!checkSupport()) {
            el.style.background = 'rgba(128, 128, 128, 0.15)';
            return {
                filterId: null,
                effect: 'none',
                setEffect: function() {},
                setTint: function() {},
                destroy: function() { el.style.background = ''; },
            };
        }

        // Preset
        var effectName = opts.effect || 'regular';
        var preset = PRESETS[effectName] || PRESETS.regular;

        // Merge: opts override preset
        var displacementScale = opts.displacementScale != null ? opts.displacementScale : preset.displacementScale;
        var blur = opts.blur != null ? opts.blur : preset.blur;
        var saturate = opts.saturate != null ? opts.saturate : preset.saturate;
        var brightness = opts.brightness != null ? opts.brightness : preset.brightness;
        var contrast = opts.contrast != null ? opts.contrast : preset.contrast;
        var showShadow = opts.shadow != null ? opts.shadow : preset.shadow;
        var showSpecular = opts.specular != null ? opts.specular : preset.specular;
        var borderRadius = opts.borderRadius != null ? opts.borderRadius : 0;
        var animate = opts.animate !== false;

        // Color scheme
        var schemeName = opts.colorScheme || 'system';
        var scheme = resolveScheme(schemeName);
        var tintColor = opts.tintColor || scheme.tintColor;

        var w = opts.width || el.offsetWidth || 300;
        var h = opts.height || el.offsetHeight || 56;

        // Элемент должен быть position:relative и overflow:hidden
        var pos = getComputedStyle(el).position;
        if (pos === 'static') el.style.position = 'relative';

        // Фон элемента — transparent (liquid glass должен быть прозрачным)
        el.style.background = 'transparent';

        // Squircle corners
        if (opts.squircle) {
            applySquircle(el, borderRadius);
        }

        // Displacement filter
        var result = generateDisplacementFilter({
            width: w,
            height: h,
            borderRadius: borderRadius,
            displacementScale: displacementScale,
        });

        if (result.svg) {
            document.body.appendChild(result.svg);
        }

        // ── ДВУХСЛОЙНЫЙ ПОДХОД ──────────────────
        // Дочерний div .bee-glass-refract:
        // - backdrop-filter захватывает и блюрит контент ПОД элементом
        // - filter: url(#svg) применяет displacement к РЕЗУЛЬТАТУ backdrop
        // Итого: рефракция на краях видна, потому что displacement
        // работает с уже захваченным и заблюренным изображением

        var glassLayer = document.createElement('div');
        glassLayer.className = 'bee-glass-refract';

        var backdropParts = [];
        if (blur > 0) backdropParts.push('blur(' + blur + 'px)');
        if (saturate !== 100) backdropParts.push('saturate(' + saturate + '%)');
        if (brightness !== 100) backdropParts.push('brightness(' + brightness + '%)');
        if (contrast !== 100) backdropParts.push('contrast(' + contrast + '%)');

        var backdropValue = backdropParts.join(' ');
        var filterValue = result.filterId ? 'url(#' + result.filterId + ')' : 'none';

        glassLayer.style.cssText =
            'position:absolute;inset:0;z-index:-1;pointer-events:none;border-radius:inherit;' +
            'backdrop-filter:' + backdropValue + ';' +
            '-webkit-backdrop-filter:' + backdropValue + ';' +
            'filter:' + filterValue + ';';

        if (animate) {
            glassLayer.style.transition = 'backdrop-filter 0.3s ease,-webkit-backdrop-filter 0.3s ease,filter 0.3s ease';
        }

        el.insertBefore(glassLayer, el.firstChild);

        // Shadow (глубина стекла)
        if (showShadow) {
            el.style.boxShadow = '0 2px 16px ' + scheme.shadowColor +
                ', inset 0 0 0 0.5px ' + scheme.borderColor;
        }

        // Tint overlay (тонкий — не перекрывает рефракцию)
        var tintEl = null;
        if (tintColor) {
            tintEl = createTintOverlay(el, tintColor);
        }

        // Specular highlight
        var specularEl = null;
        if (showSpecular) {
            specularEl = applySpecular(el, scheme.specularColor);
        }

        // Пометка
        el.dataset.beeGlass = result.filterId || effectName;
        el.dataset.beeGlassEffect = effectName;

        // ── Resize handler ──────────────────

        var resizeTimer;
        function onResize() {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(function() {
                var newW = el.offsetWidth;
                var newH = el.offsetHeight;
                if (newW > 0 && newH > 0 && (newW !== w || newH !== h)) {
                    destroy();
                    applyLiquidGlass(el, Object.assign({}, opts, { width: newW, height: newH }));
                }
            }, 200);
        }
        window.addEventListener('resize', onResize);

        // ── System color scheme change ──────

        var mediaQuery = null;
        var onSchemeChange = null;
        if (schemeName === 'system' && window.matchMedia) {
            mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
            onSchemeChange = function() {
                var newScheme = resolveScheme('system');
                if (tintEl) tintEl.style.background = opts.tintColor || newScheme.tintColor;
                if (specularEl) {
                    specularEl.style.background =
                        'linear-gradient(90deg,transparent 5%,' + newScheme.specularColor + ' 30%,' +
                        newScheme.specularColor + ' 70%,transparent 95%)';
                }
                if (showShadow) {
                    el.style.boxShadow = '0 2px 16px ' + newScheme.shadowColor +
                        ', inset 0 0 0 0.5px ' + newScheme.borderColor;
                }
            };
            if (mediaQuery.addEventListener) {
                mediaQuery.addEventListener('change', onSchemeChange);
            }
        }

        // ── Destroy ─────────────────────────

        function destroy() {
            window.removeEventListener('resize', onResize);
            if (mediaQuery && onSchemeChange && mediaQuery.removeEventListener) {
                mediaQuery.removeEventListener('change', onSchemeChange);
            }
            if (result.svg && result.svg.parentNode) {
                result.svg.parentNode.removeChild(result.svg);
            }
            if (glassLayer && glassLayer.parentNode) {
                glassLayer.parentNode.removeChild(glassLayer);
            }
            if (tintEl && tintEl.parentNode) {
                tintEl.parentNode.removeChild(tintEl);
            }
            if (specularEl && specularEl.parentNode) {
                specularEl.parentNode.removeChild(specularEl);
            }
            el.style.boxShadow = '';
            el.style.background = '';
            delete el.dataset.beeGlass;
            delete el.dataset.beeGlassEffect;
        }

        // ── Dynamic setters ─────────────────

        function setEffect(name) {
            destroy();
            applyLiquidGlass(el, Object.assign({}, opts, { effect: name }));
        }

        function setTint(color) {
            if (tintEl) {
                tintEl.style.background = color || 'transparent';
            }
        }

        return {
            filterId: result.filterId,
            effect: effectName,
            setEffect: setEffect,
            setTint: setTint,
            destroy: destroy,
        };
    }

    // ── Экспорт ───────────────────────────────

    window.beeGlass = {
        apply: applyLiquidGlass,
        /** Поддерживает ли браузер liquid glass */
        isSupported: checkSupport,
        /** Доступные пресеты */
        presets: Object.keys(PRESETS),
    };
})();
