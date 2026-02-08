/**
 * TWA (Telegram Web App) bootstrap.
 *
 * - Инициализация Telegram.WebApp
 * - Передача themeParams
 * - TON Connect (опционально)
 */

(function () {
    "use strict";

    // Инициализация Telegram Web App
    const tg = window.Telegram?.WebApp;
    if (tg) {
        tg.ready();
        tg.expand();

        // Применяем тему
        if (tg.themeParams) {
            const root = document.documentElement;
            for (const [key, value] of Object.entries(tg.themeParams)) {
                root.style.setProperty(`--tg-theme-${camelToKebab(key)}`, value);
            }
        }
    }

    // TON Connect (инициализируется если на странице есть кнопка #ton-connect-btn)
    const tonBtn = document.getElementById("ton-connect-btn");
    if (tonBtn && window.TON_CONNECT_UI) {
        try {
            const tonConnectUI = new TON_CONNECT_UI.TonConnectUI({
                manifestUrl: `${window.location.origin}/static/tonconnect-manifest.json`,
                buttonRootId: "ton-connect-btn",
            });

            tonConnectUI.onStatusChange(function (wallet) {
                const input = document.getElementById("wallet-address");
                if (input && wallet) {
                    input.value = wallet.account.address;
                    tonBtn.style.display = "none";
                }
            });

            // Показать кнопку TON Connect
            tonBtn.style.display = "block";
        } catch (e) {
            console.warn("TON Connect init failed:", e);
        }
    }

    // Stars оплата через TWA
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

    function camelToKebab(str) {
        return str.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
    }
})();
