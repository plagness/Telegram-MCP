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

        // Direct Link: start_param → редирект на /p/{slug}
        var startParam = tg.initDataUnsafe && tg.initDataUnsafe.start_param;
        if (startParam && window.location.pathname === "/") {
            window.location.replace("/p/" + startParam);
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

    // ── Утилиты ───────────────────────────────
    function camelToKebab(str) {
        return str.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
    }
})();
