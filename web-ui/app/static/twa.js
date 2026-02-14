/**
 * TWA (Telegram Web App) bootstrap — Bee Design System.
 *
 * - Инициализация Telegram.WebApp
 * - Обработка start_param (Direct Link Mini Apps)
 * - Передача themeParams в CSS
 * - Загрузочный экран (Lottie)
 * - Toast-уведомления
 * - HapticFeedback
 * - BackButton
 * - TON Connect (опционально)
 */

(function () {
    "use strict";

    var tg = window.Telegram && window.Telegram.WebApp;

    // ── Telegram WebApp init ──────────────────
    if (tg) {
        tg.ready();
        tg.expand();

        // start_param используется для Direct Link
        var startParam = tg.initDataUnsafe && tg.initDataUnsafe.start_param;

        // Direct Link: start_param → редирект на /p/{slug} с initData
        if (startParam && window.location.pathname === "/") {
            window.location.replace("/p/" + startParam + "?initData=" + encodeURIComponent(tg.initData));
            return;
        }

        // Hub: без start_param → передать initData серверу для рендера hub
        if (!startParam && tg.initData && window.location.pathname === "/" && !window.location.search) {
            window.location.replace("/?initData=" + encodeURIComponent(tg.initData));
            return;
        }

        // Страница /p/{slug} без initData → добавить initData и перезагрузить
        if (tg.initData && window.location.pathname.indexOf("/p/") === 0 && window.location.search.indexOf("initData") === -1) {
            var sep = window.location.search ? "&" : "?";
            window.location.replace(window.location.pathname + window.location.search + sep + "initData=" + encodeURIComponent(tg.initData));
            return;
        }

        // Страница /profile без initData → добавить initData и перезагрузить
        if (tg.initData && window.location.pathname === "/profile" && window.location.search.indexOf("initData") === -1) {
            var sep2 = window.location.search ? "&" : "?";
            window.location.replace("/profile" + window.location.search + sep2 + "initData=" + encodeURIComponent(tg.initData));
            return;
        }

        // Применяем Telegram-тему к CSS-переменным
        if (tg.themeParams) {
            var root = document.documentElement;
            var entries = Object.entries(tg.themeParams);
            for (var i = 0; i < entries.length; i++) {
                root.style.setProperty(
                    "--tg-theme-" + camelToKebab(entries[i][0]),
                    entries[i][1]
                );
            }
        }

        // BackButton (показываем на всех страницах кроме главной)
        if (tg.BackButton && window.location.pathname !== "/") {
            tg.BackButton.show();
            tg.BackButton.onClick(function () {
                if (window.history.length > 1) {
                    window.history.back();
                } else {
                    tg.close();
                }
            });
        }
    }

    // ── Загрузочный экран ─────────────────────
    function hideLoading() {
        var el = document.getElementById("bee-loading");
        if (el && !el.classList.contains("hidden")) {
            el.classList.add("hidden");
            setTimeout(function () { el.remove(); }, 500);
        }
    }

    if (document.readyState === "complete" || document.readyState === "interactive") {
        setTimeout(hideLoading, 200);
    } else {
        document.addEventListener("DOMContentLoaded", function () {
            setTimeout(hideLoading, 200);
        });
    }

    // Fallback: максимум 4 секунды загрузки
    setTimeout(hideLoading, 4000);

    window.hideLoading = hideLoading;

    // ── Toast-уведомления ─────────────────────
    /**
     * Показать toast-уведомление.
     * @param {string} text
     * @param {string} [type] — 'success' | 'error' | '' (нейтральный)
     * @param {number} [duration] — мс (по умолчанию 3000)
     */
    window.showToast = function (text, type, duration) {
        var container = document.getElementById("toast-container");
        if (!container) return;

        var toast = document.createElement("div");
        toast.className = "bee-toast" + (type ? " bee-toast--" + type : "");
        toast.textContent = text;

        container.appendChild(toast);

        haptic("notification", type === "error" ? "error" : "success");

        setTimeout(function () {
            toast.remove();
        }, duration || 3000);
    };

    // ── Haptic Feedback ───────────────────────
    /**
     * @param {string} type — 'impact' | 'notification' | 'selection'
     * @param {string} [style] — impact: 'light'|'medium'|'heavy';
     *                           notification: 'success'|'warning'|'error'
     */
    function haptic(type, style) {
        if (!tg || !tg.HapticFeedback) return;
        try {
            if (type === "impact") {
                tg.HapticFeedback.impactOccurred(style || "light");
            } else if (type === "notification") {
                tg.HapticFeedback.notificationOccurred(style || "success");
            } else if (type === "selection") {
                tg.HapticFeedback.selectionChanged();
            }
        } catch (e) { /* ignore */ }
    }

    window.haptic = haptic;

    // ── Fullscreen toggle (по запросу) ──────
    window.toggleFullscreen = function() {
        if (!tg) return;
        try {
            if (tg.isFullscreen) {
                tg.exitFullscreen();
            } else if (tg.requestFullscreen) {
                tg.requestFullscreen();
            }
        } catch (e) { /* не поддерживается */ }
    };

    // ── TON Connect ───────────────────────────
    var tonBtn = document.getElementById("ton-connect-btn");
    if (tonBtn && window.TON_CONNECT_UI) {
        try {
            var tonConnectUI = new TON_CONNECT_UI.TonConnectUI({
                manifestUrl: window.location.origin + "/static/tonconnect-manifest.json",
                buttonRootId: "ton-connect-btn",
            });

            tonConnectUI.onStatusChange(function (wallet) {
                var input = document.getElementById("wallet-address");
                if (input && wallet) {
                    input.value = wallet.account.address;
                    tonBtn.style.display = "none";
                }
            });

            tonBtn.style.display = "block";
        } catch (e) {
            console.warn("TON Connect init failed:", e);
        }
    }

    // ── Stars оплата ──────────────────────────
    window.payWithStars = function (invoiceUrl) {
        if (!tg) return Promise.reject(new Error("Not in Telegram"));
        return new Promise(function (resolve, reject) {
            tg.openInvoice(invoiceUrl, function (status) {
                if (status === "paid") {
                    resolve(status);
                } else {
                    reject(new Error("Payment " + status));
                }
            });
        });
    };

    // ── Sticky Header: scroll shadow + liquid glass ──
    function initHeader() {
        var bar = document.getElementById('bee-bar');
        if (!bar) return;

        // Scroll → shadow + усиление glass при прокрутке
        var glassInstance = null;

        window.addEventListener('scroll', function() {
            var scrolled = window.scrollY > 8;
            bar.classList.toggle('scrolled', scrolled);
        }, { passive: true });

        // Liquid glass на pill (центральный элемент), НЕ на весь бар
        if (window.beeGlass && window.beeGlass.isSupported()) {
            var colorScheme = 'system';
            if (tg && tg.colorScheme) {
                colorScheme = tg.colorScheme;
            }

            var centerPill = bar.querySelector('.bee-bar__center');
            if (centerPill && centerPill.offsetWidth > 0) {
                glassInstance = window.beeGlass.apply(centerPill, {
                    effect: 'regular',
                    colorScheme: colorScheme,
                    borderRadius: 20,
                    displacementScale: 70,
                    shadow: true,
                    specular: true,
                    animate: true,
                });
            }

            // Liquid glass на action buttons (☰, ⚙) — без тени и блика
            var actionBtns = bar.querySelectorAll('.bee-bar__action');
            for (var i = 0; i < actionBtns.length; i++) {
                var btn = actionBtns[i];
                if (btn.offsetWidth > 0) {
                    window.beeGlass.apply(btn, {
                        effect: 'clear',
                        colorScheme: colorScheme,
                        borderRadius: 14,
                        displacementScale: 30,
                        shadow: false,
                        specular: false,
                        animate: true,
                    });
                }
            }

            // Liquid glass на обёртку поиска — смягчённый
            var searchWrap = document.getElementById('hub-search-wrap');
            if (searchWrap && searchWrap.offsetWidth > 0) {
                window.beeGlass.apply(searchWrap, {
                    effect: 'regular',
                    colorScheme: colorScheme,
                    borderRadius: 14,
                    displacementScale: 40,
                    shadow: false,
                    specular: false,
                    animate: true,
                });
            }

            // Liquid glass на кнопку фильтров — смягчённый
            var filterToggle = document.getElementById('filter-toggle');
            if (filterToggle && filterToggle.offsetWidth > 0) {
                window.beeGlass.apply(filterToggle, {
                    effect: 'clear',
                    colorScheme: colorScheme,
                    borderRadius: 14,
                    displacementScale: 35,
                    shadow: false,
                    specular: false,
                    animate: true,
                });
            }

        }

        // Аватар из Telegram
        if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) {
            var u = tg.initDataUnsafe.user;
            var avatar = document.getElementById('bar-avatar');
            if (avatar && u.photo_url) {
                avatar.style.backgroundImage = 'url(' + u.photo_url + ')';
                avatar.style.backgroundSize = 'cover';
                avatar.textContent = '';
            }

            // Аватар на странице профиля
            var profileAvatar = document.getElementById('profile-avatar');
            if (profileAvatar && u.photo_url) {
                profileAvatar.style.backgroundImage = 'url(' + u.photo_url + ')';
                profileAvatar.textContent = '';
            }
        }

        // Клик по pill → переход на профиль
        var pillEl = bar.querySelector('.bee-bar__center');
        if (pillEl) {
            pillEl.style.cursor = 'pointer';
            pillEl.addEventListener('click', function() {
                if (window.haptic) window.haptic('impact', 'light');
                var tgApp = window.Telegram && window.Telegram.WebApp;
                if (tgApp && tgApp.initData) {
                    window.location.href = '/profile?initData=' + encodeURIComponent(tgApp.initData);
                } else {
                    window.location.href = '/profile';
                }
            });
        }
    }

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        setTimeout(initHeader, 50);
    } else {
        document.addEventListener('DOMContentLoaded', initHeader);
    }

    // ── Утилиты ───────────────────────────────
    function camelToKebab(str) {
        return str.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
    }
})();
