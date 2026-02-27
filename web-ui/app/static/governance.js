/**
 * GovernanceModule — переиспользуемый модуль управления демократией.
 * Извлечён из governance.html для шаринга между /p/{slug} и /c/{id}/manage.
 *
 * API:
 *   GovernanceModule.init(opts)   — запустить модуль
 *   GovernanceModule.pause()      — приостановить polling
 *   GovernanceModule.resume()     — возобновить polling
 *   GovernanceModule.destroy()    — полностью остановить
 *   GovernanceModule.refresh()    — принудительный re-fetch
 *   GovernanceModule.getData()    — текущие данные (D)
 *
 * opts:
 *   apiBase      — базовый URL API (напр. '/p/SLUG/governance' или '/api/governance/CHATID')
 *   initData     — Telegram initData строка
 *   containerId  — ID корневого элемента (по умолчанию 'gov-root')
 *   pollInterval — интервал polling в мс (по умолчанию 15000)
 *   onData       — коллбек при получении данных (необязательно)
 *   onSetup      — коллбек при setup_required (необязательно)
 */
var GovernanceModule = (function() {
    'use strict';

    // ── Helpers ──
    function escHtml(s) {
        if (!s) return '';
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    // ── State ──
    var _apiBase = '';
    var _chatId = '';
    var _initData = '';
    var _pollTimer = null;
    var _pollInterval = 15000;
    var _paused = false;
    var _destroyed = false;
    var D = null;
    var _cuDone = false;
    var _sheetChart = null;
    var _sheetStack = [];
    var _deepPID = null;
    var _onDataCb = null;
    var _onSetupCb = null;

    function $(id) { return document.getElementById(id); }
    function esc(s) { return s ? s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') : ''; }

    // ── Toast ──
    function showToast(msg) {
        var el = document.createElement('div');
        el.className = 'bee-toast';
        el.textContent = msg;
        document.body.appendChild(el);
        requestAnimationFrame(function() { el.classList.add('bee-toast--visible'); });
        setTimeout(function() {
            el.classList.remove('bee-toast--visible');
            setTimeout(function() { el.remove(); }, 300);
        }, 2500);
    }

    // ── Sheet Stack ──
    function sheetOpen(title, body, toolbar) {
        var cur = document.getElementById('bee-sheet-body');
        if (document.querySelector('.bee-sheet.active') && cur) {
            _sheetStack.push({
                title: document.getElementById('bee-sheet-title').textContent,
                body: cur.innerHTML,
                toolbar: document.getElementById('bee-sheet-toolbar').innerHTML
            });
        }
        BeeKit.sheet.open(title, body, toolbar);
    }
    function sheetBack() {
        if (_sheetStack.length) {
            var prev = _sheetStack.pop();
            BeeKit.sheet.open(prev.title, prev.body, prev.toolbar);
        } else {
            BeeKit.sheet.close();
        }
    }
    function sheetClose() {
        _sheetStack = [];
        if (_sheetChart) { _sheetChart.dispose(); _sheetChart = null; }
        BeeKit.sheet.close();
    }

    // ── Name helpers ──
    function cName(c) { return c.first_name || (c.username ? '@' + c.username : 'ID ' + c.user_id); }
    function profileUrl(uid) { return '/profile?user_id=' + uid + '&initData=' + encodeURIComponent(_initData || ''); }

    // ── Timer helpers ──
    function timerStr(dl) {
        var diff = new Date(dl).getTime() - Date.now();
        if (diff <= 0) return '\u0417\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e';
        var d = Math.floor(diff / 864e5), h = Math.floor((diff % 864e5) / 36e5), m = Math.floor((diff % 36e5) / 6e4);
        var parts = []; if (d) parts.push(d + '\u0434'); if (h) parts.push(h + '\u0447'); parts.push(m + '\u043c');
        return parts.join(' ');
    }
    function timeAgo(iso) {
        if (!iso) return '';
        var diff = Date.now() - new Date(iso).getTime();
        var m = Math.floor(diff / 6e4); if (m < 60) return m + '\u043c \u043d\u0430\u0437\u0430\u0434';
        var h = Math.floor(m / 60); if (h < 24) return h + '\u0447 \u043d\u0430\u0437\u0430\u0434';
        return Math.floor(h / 24) + '\u0434 \u043d\u0430\u0437\u0430\u0434';
    }

    // ── Fetch / Poll ──
    function _headers(extra) {
        var h = {};
        if (_initData) h['X-Init-Data'] = _initData;
        if (extra) { for (var k in extra) h[k] = extra[k]; }
        return h;
    }

    function _fetchData() {
        if (_destroyed) return;
        fetch(_apiBase + '/data', { headers: _headers() })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (_destroyed) return;
                _onDataReceived(data);
            })
            .catch(function(e) { console.warn('GovernanceModule fetch error:', e); });
    }

    function _onDataReceived(data) {
        var loadEl = $('gov-loading');
        if (loadEl) loadEl.style.display = 'none';
        if (data.setup_required) {
            var setupEl = $('gov-setup');
            var dashEl = $('gov-dashboard');
            if (setupEl) setupEl.style.display = '';
            if (dashEl) dashEl.style.display = 'none';
            if (_onSetupCb) _onSetupCb(data);
            return;
        }
        var setupEl2 = $('gov-setup');
        var dashEl2 = $('gov-dashboard');
        if (setupEl2) setupEl2.style.display = 'none';
        if (dashEl2) dashEl2.style.display = '';
        D = data;
        render(data);
        if (_deepPID) { openProposalSheet(parseInt(_deepPID)); _deepPID = null; }
        if (_onDataCb) _onDataCb(data);
    }

    function _startPoll() {
        _fetchData();
        if (_pollTimer) clearInterval(_pollTimer);
        _pollTimer = setInterval(function() {
            if (!_paused && !_destroyed) _fetchData();
        }, _pollInterval);
    }

    function _refreshGov() {
        _fetchData();
    }

    // ── Regime icons/names ──
    var rI = {democracy:'\ud83d\uddf3',autocracy:'\ud83d\udc51',technocracy:'\u2699\ufe0f',demarchy:'\ud83c\udfb2',gerontocracy:'\ud83c\udfe3',consensus:'\ud83e\udd1d',liquid_democracy:'\ud83d\udd17',parliament:'\ud83c\udfe3',meritocracy:'\ud83d\udcca',oligarchy:'\ud83d\udcb0',constitutional_monarchy:'\ud83d\udc51\ud83c\udfe3'};
    var rN = {democracy:'\u0414\u0435\u043c\u043e\u043a\u0440\u0430\u0442\u0438\u044f',autocracy:'\u0410\u0432\u0442\u043e\u043a\u0440\u0430\u0442\u0438\u044f',technocracy:'\u0422\u0435\u0445\u043d\u043e\u043a\u0440\u0430\u0442\u0438\u044f',demarchy:'\u0414\u0435\u043c\u0430\u0440\u0445\u0438\u044f',gerontocracy:'\u0413\u0435\u0440\u043e\u043d\u0442\u043e\u043a\u0440\u0430\u0442\u0438\u044f',consensus:'\u041a\u043e\u043d\u0441\u0435\u043d\u0441\u0443\u0441',liquid_democracy:'Liquid Democracy',parliament:'\u041f\u0430\u0440\u043b\u0430\u043c\u0435\u043d\u0442',meritocracy:'\u041c\u0435\u0440\u0438\u0442\u043e\u043a\u0440\u0430\u0442\u0438\u044f',oligarchy:'\u041e\u043b\u0438\u0433\u0430\u0440\u0445\u0438\u044f',constitutional_monarchy:'\u041a\u043e\u043d\u0441\u0442. \u041c\u043e\u043d\u0430\u0440\u0445\u0438\u044f'};

    // ── Render Dashboard ──
    function render(data) {
        var d = data.dashboard || data;
        var regime = d.regime || {};
        var stats = d.stats || {};
        var treasury = d.treasury || {};
        var cfg = data.regime_config || {};
        var my = d.my_citizenship;
        var vr = data.vote_results || {};

        // Context header
        var ctxTitle = $('gov-ctx-title');
        if (ctxTitle) ctxTitle.textContent = (rI[regime.type] || '\ud83c\udfe3') + ' ' + (rN[regime.type] || regime.type || 'Governance');
        var mc = stats.member_count || 0;
        var sub = [];
        if (cfg.quorum) sub.push('\u041a\u0432\u043e\u0440\u0443\u043c ' + Math.round(cfg.quorum * 100) + '%');
        if (cfg.threshold) sub.push('\u041f\u043e\u0440\u043e\u0433 ' + Math.round(cfg.threshold * 100) + '%');
        if (mc) sub.push(mc + ' \u0443\u0447.');
        var ctxSub = $('gov-ctx-sub');
        if (ctxSub) ctxSub.textContent = sub.join(' \u00b7 ');

        // My status — compact row
        if (my) {
            var myEl = $('gov-my');
            if (myEl) {
                myEl.style.display = '';
                var sL = {guest:'\ud83d\udc64 \u0413\u043e\u0441\u0442\u044c',citizen:'\ud83c\udfe3 \u0413\u0440\u0430\u0436\u0434\u0430\u043d\u0438\u043d',exile:'\ud83d\udeab \u0418\u0437\u0433\u043d\u0430\u043d'};
                var sB = my.status === 'citizen' ? 'bee-badge--success' : my.status === 'exile' ? 'bee-badge--error' : 'bee-badge--outline';
                myEl.innerHTML =
                    '<div style="display:flex;align-items:center;gap:10px">' +
                    '<span class="bee-badge ' + sB + '">' + (sL[my.status] || my.status) + '</span>' +
                    (my.role ? '<span class="bee-badge">' + esc(my.role) + '</span>' : '') +
                    '<span style="flex:1"></span>' +
                    '<span style="font-size:18px;font-weight:700;color:var(--accent)" id="gov-my-ip">' + (my.ip_balance || 0).toFixed(1) + '</span>' +
                    '<span style="font-size:12px;color:var(--tg-theme-hint-color)">⭐</span>' +
                    '<span style="font-size:14px;color:var(--tg-theme-hint-color)">\u203a</span>' +
                    '</div>';
                if (!_cuDone && typeof BeeFX !== 'undefined') {
                    BeeFX.countUp($('gov-my-ip'), 0, my.ip_balance || 0, {decimals: 1});
                }
            }
        }

        // Stats grid
        var statsEl = $('gov-stats');
        if (statsEl) {
            var cl = mc > 0 ? (stats.citizen_count || 0) + '/' + mc : '' + (stats.citizen_count || 0);
            statsEl.innerHTML =
                '<div class="bee-stat"><div class="bee-stat-value">' + cl + '</div><div class="bee-stat-label">\u0413\u0440\u0430\u0436\u0434\u0430\u043d</div></div>' +
                '<div class="bee-stat"><div class="bee-stat-value">' + mc + '</div><div class="bee-stat-label">\u0423\u0447\u0430\u0441\u0442\u043d.</div></div>' +
                '<div class="bee-stat"><div class="bee-stat-value">' + (stats.total_proposals || 0) + '</div><div class="bee-stat-label">\u041f\u0440\u0435\u0434\u043b\u043e\u0436.</div></div>' +
                '<div class="bee-stat"><div class="bee-stat-value">' + (stats.active_proposals || 0) + '</div><div class="bee-stat-label">\u0410\u043a\u0442\u0438\u0432\u043d.</div></div>';
        }

        // Treasury
        if (treasury && treasury.balance !== undefined) {
            var tEl = $('gov-treasury');
            if (tEl) {
                tEl.style.display = '';
                tEl.innerHTML =
                    '<div style="display:flex;align-items:center;gap:10px">' +
                    '<span style="font-size:20px">\ud83c\udfe6</span>' +
                    '<span style="font-weight:600">\u041a\u0430\u0437\u043d\u0430</span>' +
                    '<span style="flex:1"></span>' +
                    '<span style="font-size:16px;font-weight:700;color:var(--accent)" id="gov-tr-bal">' + (treasury.balance || 0).toFixed(1) + '</span>' +
                    '<span style="font-size:12px;color:var(--tg-theme-hint-color)">⭐ \u00b7 ' + Math.round((treasury.tax_rate || 0) * 100) + '%</span>' +
                    '<span style="font-size:14px;color:var(--tg-theme-hint-color)">\u203a</span>' +
                    '</div>';
                if (!_cuDone && typeof BeeFX !== 'undefined') {
                    BeeFX.countUp($('gov-tr-bal'), 0, treasury.balance || 0, {decimals: 1});
                }
            }
        }
        _cuDone = true;

        // Active proposals
        var active = d.active_proposals || [];
        var aList = $('gov-active-list');
        var aCount = $('gov-active-count');
        if (aCount) aCount.textContent = active.length || '';
        if (aList) {
            if (active.length) {
                aList.innerHTML = active.map(function(p) { return pCard(p, vr[p.id]); }).join('');
                var emptyEl = $('gov-active-empty');
                if (emptyEl) emptyEl.style.display = 'none';
            } else {
                aList.innerHTML = '';
                var emptyEl2 = $('gov-active-empty');
                if (emptyEl2) emptyEl2.style.display = '';
            }
        }

        // Create button
        var createWrap = $('gov-create-wrap');
        if (createWrap) createWrap.style.display = (my && my.status === 'citizen') ? '' : 'none';

        // Recent decisions
        var recent = d.recent_decisions || [];
        if (recent.length) {
            var recentCard = $('gov-recent-card');
            if (recentCard) recentCard.style.display = '';
            var recentList = $('gov-recent-list');
            if (recentList) recentList.innerHTML = recent.map(function(p) { return pCard(p, vr[p.id]); }).join('');
        }

        // Top citizens — podium
        var top = data.top_citizens || [];
        if (top.length) {
            var topCard = $('gov-top-card');
            if (topCard) topCard.style.display = '';
            var podium = top.slice(0, 3);
            var topPodium = $('gov-top-podium');
            if (topPodium) {
                topPodium.innerHTML = podium.map(function(c, i) {
                    var sizes = ['48px', '40px', '40px'];
                    var name = cName(c);
                    var letter = name.charAt(0).toUpperCase();
                    return '<div class="bee-podium-item" onclick="window.location=\'' + profileUrl(c.user_id) + '\'" style="cursor:pointer">' +
                        '<div class="bee-medal bee-medal--' + ['gold', 'silver', 'bronze'][i] + '" style="width:' + sizes[i] + ';height:' + sizes[i] + ';font-size:16px;display:flex;align-items:center;justify-content:center;margin:0 auto">' + letter + '</div>' +
                        '<div class="bee-podium-name">' + esc(name) + '</div>' +
                        '<div class="bee-podium-value">' + (c.ip_balance || 0).toFixed(1) + ' ⭐</div>' +
                        '</div>';
                }).join('');
            }
            var topRest = $('gov-top-rest');
            if (topRest) {
                var rest = top.slice(3);
                topRest.innerHTML = rest.map(function(c, i) {
                    return '<div class="bee-rank-item bee-ripple" data-haptic="selection" onclick="window.location=\'' + profileUrl(c.user_id) + '\'" style="cursor:pointer">' +
                        '<div class="bee-rank-pos">' + (i + 4) + '</div>' +
                        '<div class="bee-rank-name">' + esc(cName(c)) + '</div>' +
                        '<div class="bee-rank-value">' + (c.ip_balance || 0).toFixed(1) + ' ⭐</div>' +
                        '</div>';
                }).join('');
            }
        }

        // Constitution preview
        var constitution = data.constitution || [];
        if (constitution.length) {
            var constCard = $('gov-const-card');
            if (constCard) constCard.style.display = '';
            var constCount = $('gov-const-count');
            if (constCount) constCount.textContent = constitution.length;
            var constPreview = $('gov-const-preview');
            if (constPreview) {
                var preview = constitution.slice(0, 3);
                constPreview.innerHTML = preview.map(function(a) {
                    return '<div class="bee-list-item bee-ripple" data-haptic="selection" onclick="openConstitutionSheet()" style="cursor:pointer">' +
                        '<div class="bee-list-icon" style="font-size:12px;color:var(--tg-theme-hint-color);min-width:28px;text-align:center">\u00a7' + esc(a.article_num) + '</div>' +
                        '<div class="bee-list-content"><div class="bee-list-title" style="font-size:13px">' + esc(a.title) + '</div></div>' +
                        (a.immutable ? '<div class="bee-list-right"><span style="font-size:12px">\ud83d\udd12</span></div>' : '') +
                        '</div>';
                }).join('');
            }
        }

        // Plugins
        var plugins = data.plugins || [];
        if (plugins.length) {
            var plCard = $('gov-plugins-card');
            if (plCard) plCard.style.display = '';
            var plList = $('gov-plugins-list');
            if (plList) plList.innerHTML = plugins.map(function(pl) {
                return '<span class="bee-badge" style="margin:0 4px 4px 0">' + esc(pl.plugin_slug) + '</span>';
            }).join('');
        }

        // Council
        var councilData = data.council;
        var ei = data.engine_info || {};
        var councilCard = $('gov-council-card');
        if (councilCard) {
            if (councilData && councilData.length > 0 && ei.is_council) {
                councilCard.style.display = '';
                var councilCount = $('gov-council-count');
                if (councilCount) councilCount.textContent = councilData.length;
                var councilList = $('gov-council-list');
                if (councilList) {
                    councilList.innerHTML = councilData.map(function(m) {
                        return '<div class="bee-list__item" style="display:flex;align-items:center;gap:8px;padding:8px 0">'
                            + '<div style="width:32px;height:32px;border-radius:50%;background:var(--tg-theme-secondary-bg-color);display:flex;align-items:center;justify-content:center;font-size:14px">'
                            + (m.role === 'chair' ? '\ud83d\udc51' : '\ud83d\udc64') + '</div>'
                            + '<div style="flex:1;min-width:0"><div style="font-weight:600;font-size:13px">' + cName(m) + '</div>'
                            + '<div style="font-size:11px;opacity:0.6">' + (m.role || 'member') + '</div></div></div>';
                    }).join('');
                }
            } else {
                councilCard.style.display = 'none';
            }
        }

        // Petitions
        var petData = data.petitions;
        var petCard = $('gov-petitions-card');
        if (petCard) {
            if (petData && petData.items && petData.items.length > 0) {
                petCard.style.display = '';
                var petCount = $('gov-petitions-count');
                if (petCount) petCount.textContent = petData.total || petData.items.length;
                var petEmpty = $('gov-petitions-empty');
                if (petEmpty) petEmpty.style.display = 'none';
                var petList = $('gov-petitions-list');
                if (petList) {
                    petList.innerHTML = petData.items.map(function(p) {
                        var pct = p.total_citizens > 0 ? Math.round(p.signature_count / p.total_citizens * 100) : 0;
                        var thPct = Math.round(p.threshold * 100);
                        var typeIcons = {general: '\u270d\ufe0f', regime_change: '\ud83d\udd25', referendum: '\ud83d\uddf3'};
                        return '<div class="bee-list__item bee-ripple" data-haptic="selection" onclick="openPetitionSheet(' + p.id + ')" style="cursor:pointer;padding:10px 0">'
                            + '<div style="display:flex;align-items:center;justify-content:space-between">'
                            + '<div style="flex:1;min-width:0"><div style="font-weight:600;font-size:13px">' + (typeIcons[p.petition_type] || '') + ' ' + esc(p.title) + '</div>'
                            + '<div style="font-size:11px;opacity:0.6;margin-top:2px">' + p.signature_count + ' \u043f\u043e\u0434\u043f\u0438\u0441\u0435\u0439 \u00b7 \u043f\u043e\u0440\u043e\u0433 ' + thPct + '%</div></div>'
                            + '<div class="bee-badge" style="font-size:11px">' + pct + '%</div></div>'
                            + '<div style="margin-top:6px;height:4px;border-radius:2px;background:var(--tg-theme-secondary-bg-color);overflow:hidden">'
                            + '<div style="height:100%;width:' + Math.min(pct / (p.threshold * 100) * 100, 100) + '%;background:var(--tg-theme-button-color);border-radius:2px;transition:width .3s"></div></div></div>';
                    }).join('');
                }
            } else {
                petCard.style.display = '';
                var petEmpty2 = $('gov-petitions-empty');
                if (petEmpty2) petEmpty2.style.display = '';
                var petList2 = $('gov-petitions-list');
                if (petList2) petList2.innerHTML = '';
                var petCount2 = $('gov-petitions-count');
                if (petCount2) petCount2.textContent = '0';
            }
        }

        // Delegations (liquid_democracy)
        var delegData = data.delegations;
        var delegCard = $('gov-delegations-card');
        if (delegCard) {
            if (delegData && regime.type === 'liquid_democracy') {
                delegCard.style.display = '';
                var power = delegData.power || 1;
                var delegPower = $('gov-deleg-power');
                if (delegPower) delegPower.innerHTML = '\ud83d\udcaa Voting Power: <strong>' + power + '</strong>' + (power > 1 ? ' (' + (power - 1) + ' \u0434\u0435\u043b\u0435\u0433\u0438\u0440\u043e\u0432\u0430\u043d\u043e)' : '');
                var given = delegData.given || [];
                var delegList = $('gov-delegations-list');
                if (delegList) {
                    if (given.length > 0) {
                        delegList.innerHTML = given.map(function(d) {
                            var dName = d.delegate_first_name || '@' + d.delegate_username || 'ID ' + d.delegate_id;
                            var ava = '/api/avatars/user/' + d.delegate_id;
                            return '<div class="bee-list__item" style="display:flex;align-items:center;gap:10px;padding:8px 0">'
                                + '<img src="' + ava + '" onerror="this.style.display=\'none\'" style="width:32px;height:32px;border-radius:50%;object-fit:cover;flex-shrink:0">'
                                + '<div style="flex:1;min-width:0"><div style="font-weight:600;font-size:13px">\u2192 ' + escHtml(dName) + '</div>'
                                + '<div style="font-size:11px;opacity:0.6">' + d.topic + '</div></div>'
                                + '<button class="bee-btn bee-btn--sm" data-haptic="impact" onclick="revokeDelegation(\'' + d.topic + '\')">\u041e\u0442\u043e\u0437\u0432\u0430\u0442\u044c</button></div>';
                        }).join('');
                    } else {
                        delegList.innerHTML = '<div style="text-align:center;padding:12px 0;font-size:13px;opacity:0.6">\u041d\u0435\u0442 \u0434\u0435\u043b\u0435\u0433\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0439</div>';
                    }
                }
            } else {
                delegCard.style.display = 'none';
            }
        }

        if (typeof BeeFX !== 'undefined') BeeFX.initFadeIn();
    }

    // ── Proposal Card ──
    var sIc = {discussion:'\ud83d\udcac',voting:'\ud83d\uddf3',passed:'\u2705',rejected:'\u274c',expired:'\u23f0',decided_yes:'\ud83d\udc51\u2705',decided_no:'\ud83d\udc51\u274c'};

    function pCard(p, vr) {
        var myV = D && D.my_votes ? D.my_votes[p.id] : null;
        var mvH = myV ? ' <span style="font-size:11px;vertical-align:middle">' + ({for:'\u2705',against:'\u274c',abstain:'\ud83e\udd37'}[myV] || '') + '</span>' : '';
        var progH = '';
        if (vr && vr.quorum_progress) {
            var pct = Math.round(vr.quorum_progress * 100);
            progH = '<div class="gov-micro-progress" style="margin-top:6px"><div class="gov-micro-fill" style="width:' + pct + '%"></div></div>';
        }
        return '<div class="bee-list-item bee-ripple gov-proposal-card" data-haptic="selection" onclick="openProposalSheet(' + p.id + ')" style="cursor:pointer">' +
            '<div class="bee-list-icon" style="font-size:18px">' + (sIc[p.status] || '\ud83d\udccb') + '</div>' +
            '<div class="bee-list-content">' +
            '<div class="bee-list-title">' + esc(p.title) + mvH + '</div>' +
            '<div class="bee-list-subtitle">' +
            (p.author_name ? '<span class="gov-author-link" onclick="event.stopPropagation();window.location=\'' + profileUrl(p.author_id) + '\'">' + esc(p.author_name) + '</span> \u00b7 ' : '') +
            timeAgo(p.created_at) +
            '</div>' +
            progH +
            '</div></div>';
    }

    // ── SHEET: Proposal Detail ──
    function openProposalSheet(pid) {
        var d = D ? (D.dashboard || D) : {};
        var all = (d.active_proposals || []).concat(d.recent_decisions || []);
        var p = null;
        for (var i = 0; i < all.length; i++) { if (all[i].id === pid) { p = all[i]; break; } }
        var vr = D && D.vote_results ? D.vote_results[pid] : null;

        var h = '';
        if (p) h = buildProposalHTML(p, vr, pid);
        else h = '<div style="text-align:center;padding:20px;color:var(--tg-theme-hint-color)">\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430...</div>';

        sheetOpen(p ? p.title : '\u041f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0435', h, '');

        fetch(_apiBase + '/proposal/' + pid, {headers: _headers()})
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.error) return;
            var pp = data.proposal || p;
            var rr = data.results || vr;
            if (data.my_vote && D) {
                if (!D.my_votes) D.my_votes = {};
                D.my_votes[pid] = data.my_vote;
            }
            var body = document.getElementById('bee-sheet-body');
            if (body) {
                body.innerHTML = buildProposalHTML(pp, rr, pid, data.arguments, data.my_vote);
                initSheetChart(rr);
                BeeKit.initAccordions();
            }
        }).catch(function() {});

        setTimeout(function() { initSheetChart(vr); }, 50);
    }
    window.openProposalSheet = openProposalSheet;

    function buildProposalHTML(p, vr, pid, args, myVote) {
        if (!myVote && D && D.my_votes) myVote = D.my_votes[pid];
        var h = '';

        // Meta
        var meta = [];
        if (p.author_name) {
            meta.push('<a style="color:var(--accent);text-decoration:none" href="' + profileUrl(p.author_id) + '">' + esc(p.author_name) + '</a>');
        }
        if (p.proposal_type) meta.push(p.proposal_type);
        meta.push(timeAgo(p.created_at));
        h += '<div style="font-size:13px;color:var(--tg-theme-hint-color);margin-bottom:8px">' + meta.join(' \u00b7 ') + '</div>';

        if (p.description) {
            h += '<div style="font-size:14px;line-height:1.5;margin-bottom:12px">' + esc(p.description) + '</div>';
        }

        // Timeline
        var phases = ['discussion', 'voting', 'result'];
        var icons = {discussion: '\ud83d\udcac', voting: '\ud83d\uddf3', result: '\ud83d\udcca'};
        var labels = {discussion: '\u041e\u0431\u0441\u0443\u0436\u0434.', voting: '\u0413\u043e\u043b\u043e\u0441\u043e\u0432.', result: '\u0420\u0435\u0437\u0443\u043b\u044c\u0442.'};
        var ci = p.status === 'discussion' ? 0 : p.status === 'voting' ? 1 : 2;
        h += '<div class="gov-timeline">';
        for (var i = 0; i < 3; i++) {
            var cls = i < ci ? 'gov-tl--done' : i === ci ? 'gov-tl--active' : '';
            h += '<div class="gov-tl ' + cls + '"><span class="gov-tl-icon">' + icons[phases[i]] + '</span><span class="gov-tl-label">' + labels[phases[i]] + '</span></div>';
            if (i < 2) h += '<div class="gov-tl-conn"></div>';
        }
        var dl = p.status === 'discussion' ? p.discussion_end : p.status === 'voting' ? p.voting_end : null;
        if (dl) {
            var diff = new Date(dl).getTime() - Date.now();
            var urgent = diff > 0 && diff < 36e5;
            h += '<div class="gov-timer' + (urgent ? ' gov-timer--urgent' : '') + '">\u23f1 ' + timerStr(dl) + '</div>';
        }
        h += '</div>';

        // Result badge
        if (['passed', 'rejected', 'expired', 'decided_yes', 'decided_no'].indexOf(p.status) >= 0) {
            var ri = {passed: ['\u2705', '\u041f\u0420\u0418\u041d\u042f\u0422\u041e', 'passed'], rejected: ['\u274c', '\u041e\u0422\u041a\u041b\u041e\u041d\u0415\u041d\u041e', 'rejected'], expired: ['\u23f0', '\u0418\u0421\u0422\u0415\u041a\u041b\u041e', 'expired'], decided_yes: ['\ud83d\udc51\u2705', '\u041e\u0414\u041e\u0411\u0420\u0415\u041d\u041e', 'passed'], decided_no: ['\ud83d\udc51\u274c', '\u041e\u0422\u041a\u041b\u041e\u041d\u0415\u041d\u041e', 'rejected']};
            var r = ri[p.status] || ['\ud83d\udccb', p.status, ''];
            h += '<div class="gov-result gov-result--' + r[2] + '"><span class="gov-result-icon">' + r[0] + '</span><span class="gov-result-text">' + r[1] + '</span></div>';
        }

        // Chart + Quorum
        if (vr) {
            var qPct = Math.round((vr.quorum_progress || 0) * 100);
            h += '<div style="margin:12px 0">';
            h += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px"><span style="font-size:12px;color:var(--tg-theme-hint-color)">\u041a\u0432\u043e\u0440\u0443\u043c</span>' +
                '<div class="bee-progress" style="flex:1"><div class="bee-progress-fill" style="width:' + qPct + '%"></div></div>' +
                '<span style="font-size:12px;color:var(--tg-theme-hint-color)">' + vr.total_votes + ' (' + qPct + '%)</span></div>';
            h += '<div id="gov-sheet-chart" style="height:200px;width:100%"></div>';
            h += '</div>';
        }

        // Vote buttons
        var canVote = p.status === 'voting' || p.status === 'discussion';
        if (canVote) {
            var choices = [
                {c: 'for', icon: '\u2705', label: '\u0417\u0430'},
                {c: 'against', icon: '\u274c', label: '\u041f\u0440\u043e\u0442\u0438\u0432'},
                {c: 'abstain', icon: '\ud83e\udd37', label: '\u0412\u043e\u0437\u0434\u0435\u0440\u0436.'}
            ];
            h += '<div class="gov-vote-group">';
            choices.forEach(function(ch) {
                var sel = myVote === ch.c ? ' gov-vote-btn--sel' : '';
                h += '<button class="bee-btn bee-ripple gov-vote-btn' + sel + '" data-haptic="impact" onclick="castVote(' + pid + ',\'' + ch.c + '\')" style="flex:1">' + ch.icon + ' ' + ch.label + '</button>';
            });
            h += '</div>';
            if (myVote) {
                var cL = {for: '\u2705 \u0417\u0430', against: '\u274c \u041f\u0440\u043e\u0442\u0438\u0432', abstain: '\ud83e\udd37 \u0412\u043e\u0437\u0434\u0435\u0440\u0436\u0443\u0441\u044c'};
                h += '<div style="text-align:center;font-size:13px;color:var(--tg-theme-hint-color);margin-top:8px">\u0412\u0430\u0448 \u0433\u043e\u043b\u043e\u0441: <b>' + (cL[myVote] || myVote) + '</b> <button class="gov-cancel-btn" onclick="cancelVote(' + pid + ')">\u043e\u0442\u043c\u0435\u043d\u0438\u0442\u044c</button></div>';
            }
        }

        // AI summary
        if (p.llm_summary) {
            h += '<div style="margin-top:12px;padding:12px;border-radius:8px;background:var(--accent-glow,rgba(255,193,7,.08))">' +
                '<div class="bee-badge" style="margin-bottom:6px">\ud83e\udd16 AI</div>' +
                '<div style="font-size:13px;line-height:1.5;white-space:pre-wrap">' + esc(p.llm_summary) + '</div></div>';
        }

        // Arguments
        if (args) {
            var fA = args['for'] || [], aA = args['against'] || [];
            h += '<div style="margin-top:12px">';
            h += '<div style="display:flex;gap:12px">';
            h += '<div style="flex:1"><div style="font-size:13px;font-weight:600;color:#4CAF50;margin-bottom:4px">\ud83d\udcd7 \u0417\u0430 (' + fA.length + ')</div>';
            h += fA.length ? fA.map(function(a) {
                return '<div style="padding:6px 0;border-bottom:1px solid rgba(128,128,128,.1);font-size:12px;line-height:1.4">' + esc(a.text) + '<div style="font-size:10px;color:var(--tg-theme-hint-color);margin-top:2px">' + timeAgo(a.created_at) + '</div></div>';
            }).join('') : '<div style="font-size:12px;color:var(--tg-theme-hint-color);padding:4px 0">\u2014</div>';
            h += '</div>';
            h += '<div style="flex:1"><div style="font-size:13px;font-weight:600;color:#F44336;margin-bottom:4px">\ud83d\udcd5 \u041f\u0440\u043e\u0442\u0438\u0432 (' + aA.length + ')</div>';
            h += aA.length ? aA.map(function(a) {
                return '<div style="padding:6px 0;border-bottom:1px solid rgba(128,128,128,.1);font-size:12px;line-height:1.4">' + esc(a.text) + '<div style="font-size:10px;color:var(--tg-theme-hint-color);margin-top:2px">' + timeAgo(a.created_at) + '</div></div>';
            }).join('') : '<div style="font-size:12px;color:var(--tg-theme-hint-color);padding:4px 0">\u2014</div>';
            h += '</div></div>';
            if (canVote && p.status === 'discussion') {
                h += '<button class="bee-btn bee-btn--outline bee-ripple" data-haptic="selection" style="width:100%;margin-top:8px" onclick="openArgSheet(' + pid + ')">\u002b \u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0430\u0440\u0433\u0443\u043c\u0435\u043d\u0442</button>';
            }
            h += '</div>';
        }

        return h;
    }

    function initSheetChart(vr) {
        if (!vr || typeof echarts === 'undefined') return;
        var el = document.getElementById('gov-sheet-chart');
        if (!el) return;
        if (_sheetChart) { _sheetChart.dispose(); _sheetChart = null; }
        _sheetChart = echarts.init(el, null, {renderer: 'svg'});
        var votes = vr.votes || {};
        var hint = getComputedStyle(document.body).getPropertyValue('--tg-hint').trim() || '#999';
        _sheetChart.setOption({
            tooltip: {trigger: 'item', formatter: '{b}: {c} ({d}%)'},
            legend: {bottom: 0, textStyle: {color: hint, fontSize: 11}},
            series: [{
                type: 'pie', radius: ['42%', '70%'], center: ['50%', '44%'],
                avoidLabelOverlap: true,
                itemStyle: {borderRadius: 6, borderColor: 'transparent', borderWidth: 2},
                label: {show: true, position: 'inside', formatter: '{c}', fontSize: 13, fontWeight: 600, color: '#fff'},
                data: [
                    {value: votes['for'] || 0, name: '\u0417\u0430', itemStyle: {color: '#4CAF50'}},
                    {value: votes['against'] || 0, name: '\u041f\u0440\u043e\u0442\u0438\u0432', itemStyle: {color: '#F44336'}},
                    {value: votes['abstain'] || 0, name: '\u0412\u043e\u0437\u0434\u0435\u0440\u0436.', itemStyle: {color: '#9E9E9E'}}
                ].filter(function(d) { return d.value > 0; }),
                emphasis: {itemStyle: {shadowBlur: 10, shadowColor: 'rgba(0,0,0,.3)'}}
            }]
        });
    }

    // ── SHEET: My Status ──
    window.openMySheet = function() {
        var d = D ? (D.dashboard || D) : {};
        var my = d.my_citizenship;
        if (!my) return;
        var sL = {guest: '\ud83d\udc64 \u0413\u043e\u0441\u0442\u044c', citizen: '\ud83c\udfe3 \u0413\u0440\u0430\u0436\u0434\u0430\u043d\u0438\u043d', exile: '\ud83d\udeab \u0418\u0437\u0433\u043d\u0430\u043d\u043d\u0438\u043a'};
        var sB = my.status === 'citizen' ? 'bee-badge--success' : my.status === 'exile' ? 'bee-badge--error' : 'bee-badge--outline';
        var h = '<div style="text-align:center;margin-bottom:16px">' +
            '<span class="bee-badge ' + sB + '" style="font-size:14px;padding:6px 14px">' + (sL[my.status] || my.status) + '</span>' +
            (my.role ? ' <span class="bee-badge" style="font-size:14px;padding:6px 14px">' + esc(my.role) + '</span>' : '') +
            '</div>';
        h += '<div class="bee-stat-grid" style="margin-bottom:16px">' +
            '<div class="bee-stat"><div class="bee-stat-value">' + (my.ip_balance || 0).toFixed(1) + '</div><div class="bee-stat-label">⭐ Баланс</div></div>' +
            '<div class="bee-stat"><div class="bee-stat-value">' + (my.total_earned || 0).toFixed(1) + '</div><div class="bee-stat-label">\u0417\u0430\u0440\u0430\u0431\u043e\u0442\u0430\u043d\u043e</div></div>' +
            '<div class="bee-stat"><div class="bee-stat-value">' + (my.total_spent || 0).toFixed(1) + '</div><div class="bee-stat-label">\u041f\u043e\u0442\u0440\u0430\u0447\u0435\u043d\u043e</div></div>' +
            '</div>';
        if (my.citizen_since) {
            h += '<div style="font-size:13px;color:var(--tg-theme-hint-color);text-align:center">\u0413\u0440\u0430\u0436\u0434\u0430\u043d\u0438\u043d \u0441 ' + new Date(my.citizen_since).toLocaleDateString('ru-RU') + '</div>';
        }
        if (my.status === 'guest') {
            h += '<div style="text-align:center;margin-top:16px;padding:12px;border-radius:8px;background:var(--accent-glow,rgba(255,193,7,.08))">' +
                '<div style="font-size:14px;font-weight:600;margin-bottom:4px">\u0421\u0442\u0430\u043d\u044c\u0442\u0435 \u0433\u0440\u0430\u0436\u0434\u0430\u043d\u0438\u043d\u043e\u043c</div>' +
                '<div style="font-size:12px;color:var(--tg-theme-hint-color)">\u0423\u0447\u0430\u0441\u0442\u0432\u0443\u0439\u0442\u0435 \u0432 \u0433\u043e\u043b\u043e\u0441\u043e\u0432\u0430\u043d\u0438\u044f\u0445 \u0438 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u044f\u0445</div></div>';
        }
        h += '<a class="bee-btn bee-btn--outline bee-ripple" data-haptic="selection" href="' + profileUrl(my.user_id) + '" style="display:block;margin-top:16px;text-align:center;text-decoration:none">\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043f\u0440\u043e\u0444\u0438\u043b\u044c</a>';
        sheetOpen('\u041c\u043e\u0439 \u0441\u0442\u0430\u0442\u0443\u0441', h, '');
    };

    // ── SHEET: Regime Config ──
    function listRow(icon, title, value) {
        return '<div class="bee-list-item"><div class="bee-list-icon" style="font-size:16px">' + icon + '</div><div class="bee-list-content"><div class="bee-list-title" style="font-size:14px">' + title + '</div></div><div class="bee-list-right" style="font-size:14px;font-weight:500">' + value + '</div></div>';
    }

    window.openRegimeSheet = function() {
        var cfg = D ? D.regime_config || {} : {};
        var d = D ? (D.dashboard || D) : {};
        var regime = d.regime || {};
        var h = '<div class="bee-list">';
        h += listRow('\ud83c\udfe3', '\u0422\u0438\u043f \u0440\u0435\u0436\u0438\u043c\u0430', rN[regime.type] || regime.type);
        h += listRow('\ud83d\uddf3', '\u041a\u0432\u043e\u0440\u0443\u043c', Math.round((cfg.quorum || 0.25) * 100) + '%');
        h += listRow('\u2696\ufe0f', '\u041f\u043e\u0440\u043e\u0433 \u043f\u0440\u0438\u043d\u044f\u0442\u0438\u044f', Math.round((cfg.threshold || 0.5) * 100) + '%');
        h += listRow('\ud83d\udcac', '\u041e\u0431\u0441\u0443\u0436\u0434\u0435\u043d\u0438\u0435', (cfg.discussion_hours || 24) + '\u0447');
        h += listRow('\u23f1', '\u0413\u043e\u043b\u043e\u0441\u043e\u0432\u0430\u043d\u0438\u0435', (cfg.voting_hours || 48) + '\u0447');
        h += listRow('\ud83d\udcb0', '\u041d\u0430\u043b\u043e\u0433', Math.round((cfg.tax_rate || 0.1) * 100) + '%');
        h += listRow('\ud83c\udf1f', '\u041d\u0430\u0447\u0430\u043b\u044c\u043d\u044b\u0435 \u2b50', '' + (cfg.initial_ip || 20));
        h += listRow('\ud83d\udccb', '\u041c\u0430\u043a\u0441. \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445', '' + (cfg.max_active_proposals || 3));
        if (regime.installed_at) {
            h += listRow('\ud83d\udcc5', '\u0423\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e', new Date(regime.installed_at).toLocaleDateString('ru-RU'));
        }
        h += '</div>';
        sheetOpen('\u2699\ufe0f \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0440\u0435\u0436\u0438\u043c\u0430', h, '');
    };

    // ── SHEET: Leaderboard ──
    window.openLeaderboardSheet = function() {
        var top = D ? D.top_citizens || [] : [];
        var h = '';
        if (!top.length) {
            h = '<div style="text-align:center;padding:20px;color:var(--tg-theme-hint-color)">\u041d\u0435\u0442 \u0433\u0440\u0430\u0436\u0434\u0430\u043d</div>';
        } else {
            h = '<div class="bee-rank-list">';
            top.forEach(function(c, i) {
                var medals = ['\ud83e\udd47', '\ud83e\udd48', '\ud83e\udd49'];
                var m = i < 3 ? medals[i] : (i + 1) + '.';
                var hi = c.user_id === (D.dashboard && D.dashboard.my_citizenship ? D.dashboard.my_citizenship.user_id : 0);
                h += '<div class="bee-rank-item' + (hi ? ' highlighted' : '') + ' bee-ripple" data-haptic="selection" onclick="window.location=\'' + profileUrl(c.user_id) + '\'" style="cursor:pointer">' +
                    '<div class="bee-rank-pos" style="font-size:16px">' + m + '</div>' +
                    '<div class="bee-rank-name">' + esc(cName(c)) + '</div>' +
                    '<div class="bee-rank-value">' + (c.ip_balance || 0).toFixed(1) + ' ⭐</div>' +
                    '</div>';
            });
            h += '</div>';
        }
        sheetOpen('\ud83c\udfc6 \u0420\u0435\u0439\u0442\u0438\u043d\u0433 \u0433\u0440\u0430\u0436\u0434\u0430\u043d', h, '');
    };

    // ── SHEET: Constitution ──
    window.openConstitutionSheet = function() {
        var articles = D ? D.constitution || [] : [];
        var h = '';
        if (!articles.length) {
            h = '<div style="text-align:center;padding:20px;color:var(--tg-theme-hint-color)">\u041a\u043e\u043d\u0441\u0442\u0438\u0442\u0443\u0446\u0438\u044f \u043d\u0435 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0430</div>';
        } else {
            h = articles.map(function(a) {
                return '<div data-bee-accordion>' +
                    '<div class="bee-accordion__header" style="display:flex;align-items:center;gap:8px;padding:10px 0;cursor:pointer">' +
                    '<span style="font-size:12px;color:var(--tg-theme-hint-color);min-width:28px">\u00a7' + esc(a.article_num) + '</span>' +
                    '<span style="font-size:14px;font-weight:500;flex:1">' + esc(a.title) + '</span>' +
                    (a.immutable ? '<span class="bee-badge bee-badge--outline" style="font-size:10px">\ud83d\udd12</span>' : '') +
                    '</div>' +
                    '<div class="bee-accordion__content" style="padding:0 0 12px 36px;font-size:13px;line-height:1.5;color:var(--tg-theme-hint-color)">' +
                    esc(a.text) +
                    '</div></div>';
            }).join('<div class="bee-divider"></div>');
        }
        sheetOpen('\ud83d\udcdc \u041a\u043e\u043d\u0441\u0442\u0438\u0442\u0443\u0446\u0438\u044f (' + articles.length + ' \u0441\u0442.)', h, '');
        setTimeout(function() { BeeKit.initAccordions(); }, 50);
    };

    // ── SHEET: Treasury ──
    window.openTreasurySheet = function() {
        var d = D ? (D.dashboard || D) : {};
        var t = d.treasury || {};
        var h = '<div class="bee-stat-grid">' +
            '<div class="bee-stat"><div class="bee-stat-value">' + (t.balance || 0).toFixed(1) + '</div><div class="bee-stat-label">⭐ Баланс</div></div>' +
            '<div class="bee-stat"><div class="bee-stat-value">' + Math.round((t.tax_rate || 0) * 100) + '%</div><div class="bee-stat-label">\u041d\u0430\u043b\u043e\u0433\u043e\u0432\u0430\u044f \u0441\u0442\u0430\u0432\u043a\u0430</div></div>' +
            '</div>' +
            '<div class="bee-divider" style="margin:12px 0"></div>' +
            '<div class="bee-list">' +
            listRow('\ud83d\udcb8', '\u0421\u043e\u0431\u0440\u0430\u043d\u043e \u043d\u0430\u043b\u043e\u0433\u043e\u0432', (t.total_taxed || 0).toFixed(1) + ' ⭐') +
            listRow('\ud83d\udcb3', '\u041f\u043e\u0442\u0440\u0430\u0447\u0435\u043d\u043e', (t.total_spent || 0).toFixed(1) + ' ⭐') +
            '</div>';
        sheetOpen('\ud83c\udfe6 \u041a\u0430\u0437\u043d\u0430', h, '');
    };

    // ── SHEET: Create Proposal ──
    window.openCreateSheet = function() {
        sheetOpen(
            '\u041d\u043e\u0432\u043e\u0435 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0435',
            '<input id="cp-title" type="text" maxlength="100" placeholder="\u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435" class="bee-input" style="width:100%;margin-bottom:8px">' +
            '<textarea id="cp-desc" maxlength="2000" rows="3" placeholder="\u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 (\u043d\u0435\u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e)" class="bee-textarea" style="width:100%;margin-bottom:8px"></textarea>' +
            '<select id="cp-type" class="bee-select" style="width:100%"><option value="general">\u041e\u0431\u0449\u0435\u0435</option><option value="rule">\u041f\u0440\u0430\u0432\u0438\u043b\u043e</option><option value="budget">\u0411\u044e\u0434\u0436\u0435\u0442</option></select>',
            '<button class="bee-btn bee-ripple" data-haptic="impact" onclick="submitProposal()">\u0421\u043e\u0437\u0434\u0430\u0442\u044c</button>'
        );
    };

    // ── SHEET: Add Argument ──
    window.openArgSheet = function(pid) {
        sheetOpen(
            '\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u0430\u0440\u0433\u0443\u043c\u0435\u043d\u0442',
            '<div style="margin-bottom:12px"><label class="bee-radio"><input type="radio" name="arg-side" value="for" checked> \ud83d\udcd7 \u0417\u0430</label> <label class="bee-radio"><input type="radio" name="arg-side" value="against"> \ud83d\udcd5 \u041f\u0440\u043e\u0442\u0438\u0432</label></div>' +
            '<textarea id="arg-text" maxlength="500" rows="4" placeholder="\u0412\u0430\u0448 \u0430\u0440\u0433\u0443\u043c\u0435\u043d\u0442..." class="bee-textarea" style="width:100%"></textarea>' +
            '<input type="hidden" id="arg-pid" value="' + pid + '">',
            '<button class="bee-btn bee-ripple" data-haptic="impact" onclick="submitArgument()">\u041e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c</button>'
        );
    };

    // ── Actions ──
    window.castVote = function(pid, choice) {
        if (window.haptic) haptic('impact', 'medium');
        if (typeof BeeFX !== 'undefined' && BeeFX.clickSpark) {
            var sheetBody = document.getElementById('bee-sheet-body');
            if (sheetBody) BeeFX.clickSpark(sheetBody);
        }
        fetch(_apiBase + '/vote', {
            method: 'POST', headers: _headers({'Content-Type': 'application/json'}),
            body: JSON.stringify({proposal_id: pid, choice: choice})
        }).then(function(r) { return r.json(); }).then(function(data) {
            if (!data.error) {
                if (window.haptic) haptic('notification', 'success');
                showToast('\u0413\u043e\u043b\u043e\u0441 \u0443\u0447\u0442\u0451\u043d');
                if (D) { if (!D.my_votes) D.my_votes = {}; D.my_votes[pid] = choice; }
                if (data.current_results && D && D.vote_results) D.vote_results[pid] = data.current_results;
                openProposalSheet(pid);
            } else { if (window.haptic) haptic('notification', 'error'); showToast(data.message || data.error); }
        }).catch(function() { showToast('\u041e\u0448\u0438\u0431\u043a\u0430 \u0441\u0435\u0442\u0438'); });
    };

    window.cancelVote = function(pid) {
        if (window.haptic) haptic('impact', 'light');
        fetch(_apiBase + '/vote', {
            method: 'DELETE', headers: _headers({'Content-Type': 'application/json'}),
            body: JSON.stringify({proposal_id: pid})
        }).then(function(r) { return r.json(); }).then(function(data) {
            if (!data.error) {
                if (window.haptic) haptic('notification', 'success');
                showToast('\u0413\u043e\u043b\u043e\u0441 \u043e\u0442\u043c\u0435\u043d\u0451\u043d');
                if (D && D.my_votes) delete D.my_votes[pid];
                if (data.current_results && D && D.vote_results) D.vote_results[pid] = data.current_results;
                openProposalSheet(pid);
            } else { showToast(data.message || data.error); }
        }).catch(function() { showToast('\u041e\u0448\u0438\u0431\u043a\u0430 \u0441\u0435\u0442\u0438'); });
    };

    window.submitProposal = function() {
        var t = $('cp-title');
        if (!t || !t.value.trim()) { showToast('\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435'); return; }
        fetch(_apiBase + '/proposal', {
            method: 'POST', headers: _headers({'Content-Type': 'application/json'}),
            body: JSON.stringify({chat_id: D && D.dashboard ? D.dashboard.chat_id : 0, title: t.value.trim(), description: ($('cp-desc') || {}).value || '', proposal_type: ($('cp-type') || {}).value || 'general'})
        }).then(function(r) { return r.json(); }).then(function(data) {
            if (!data.error) { if (window.haptic) haptic('notification', 'success'); showToast('\u041f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u0441\u043e\u0437\u0434\u0430\u043d\u043e'); BeeKit.sheet.close(); }
            else showToast(data.message || data.error);
        });
    };

    window.submitArgument = function() {
        var side = document.querySelector('input[name="arg-side"]:checked');
        var text = $('arg-text');
        var pidEl = $('arg-pid');
        if (!side || !text || !text.value.trim()) { showToast('\u0417\u0430\u043f\u043e\u043b\u043d\u0438\u0442\u0435 \u0430\u0440\u0433\u0443\u043c\u0435\u043d\u0442'); return; }
        var pid = pidEl ? parseInt(pidEl.value) : 0;
        fetch(_apiBase + '/argument', {
            method: 'POST', headers: _headers({'Content-Type': 'application/json'}),
            body: JSON.stringify({proposal_id: pid, side: side.value, text: text.value.trim()})
        }).then(function(r) { return r.json(); }).then(function(data) {
            if (!data.error) { if (window.haptic) haptic('notification', 'success'); showToast('\u0410\u0440\u0433\u0443\u043c\u0435\u043d\u0442 \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d'); BeeKit.sheet.close(); openProposalSheet(pid); }
            else showToast(data.message || '\u041e\u0448\u0438\u0431\u043a\u0430');
        });
    };

    window.setupRegime = function(type) {
        if (window.haptic) haptic('impact', 'heavy');
        fetch(_apiBase + '/setup', {
            method: 'POST', headers: _headers({'Content-Type': 'application/json'}),
            body: JSON.stringify({regime_type: type})
        }).then(function(r) { return r.json(); }).then(function(data) {
            if (!data.error) { if (window.haptic) haptic('notification', 'success'); showToast('Governance \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d!'); var el = $('gov-setup'); if (el) el.style.display = 'none'; _refreshGov(); }
            else showToast(data.message || data.error);
        });
    };

    window.doSync = function() {
        if (window.haptic) haptic('impact', 'light');
        var btn = $('gov-sync-btn');
        if (btn) btn.style.opacity = '0.4';
        fetch(_apiBase + '/sync', {
            method: 'POST', headers: _headers()
        }).then(function(r) { return r.json(); }).then(function(data) {
            if (btn) btn.style.opacity = '';
            if (!data.error) showToast('\u0421\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0430\u0446\u0438\u044f \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430');
            else showToast(data.error);
        }).catch(function() { if (btn) btn.style.opacity = ''; showToast('\u041e\u0448\u0438\u0431\u043a\u0430'); });
    };

    // ── Change Regime ──
    window.changeRegime = function(type) {
        if (window.haptic) haptic('impact', 'heavy');
        fetch(_apiBase + '/change-regime', {
            method: 'POST', headers: _headers({'Content-Type': 'application/json'}),
            body: JSON.stringify({regime_type: type})
        }).then(function(r) { return r.json(); }).then(function(data) {
            if (!data.error) {
                if (window.haptic) haptic('notification', 'success');
                showToast('\u0420\u0435\u0436\u0438\u043c \u0438\u0437\u043c\u0435\u043d\u0451\u043d!');
                BeeKit.sheet.close();
                _refreshGov();
            } else { showToast(data.message || data.error); }
        });
    };

    // ── SHEET: Change Regime ──
    window.openChangeRegimeSheet = function() {
        var d = D ? (D.dashboard || D) : {};
        var regime = d.regime || {};
        var types = [
            {t: 'democracy', i: '\ud83d\uddf3', n: '\u0414\u0435\u043c\u043e\u043a\u0440\u0430\u0442\u0438\u044f', d: '\u0420\u0435\u0448\u0435\u043d\u0438\u044f \u0433\u043e\u043b\u043e\u0441\u043e\u0432\u0430\u043d\u0438\u0435\u043c'},
            {t: 'autocracy', i: '\ud83d\udc51', n: '\u0410\u0432\u0442\u043e\u043a\u0440\u0430\u0442\u0438\u044f', d: '\u0415\u0434\u0438\u043d\u043e\u043b\u0438\u0447\u043d\u0430\u044f \u0432\u043b\u0430\u0441\u0442\u044c'},
            {t: 'technocracy', i: '\u2699\ufe0f', n: '\u0422\u0435\u0445\u043d\u043e\u043a\u0440\u0430\u0442\u0438\u044f', d: '\u0421\u043e\u0432\u0435\u0442 \u044d\u043a\u0441\u043f\u0435\u0440\u0442\u043e\u0432'},
            {t: 'demarchy', i: '\ud83c\udfb2', n: '\u0414\u0435\u043c\u0430\u0440\u0445\u0438\u044f', d: '\u0421\u043b\u0443\u0447\u0430\u0439\u043d\u044b\u0439 \u0441\u043e\u0432\u0435\u0442'},
            {t: 'gerontocracy', i: '\ud83c\udfe3', n: '\u0413\u0435\u0440\u043e\u043d\u0442\u043e\u043a\u0440\u0430\u0442\u0438\u044f', d: '\u0412\u043b\u0430\u0441\u0442\u044c \u0441\u0442\u0430\u0440\u0435\u0439\u0448\u0438\u043d'},
            {t: 'consensus', i: '\ud83e\udd1d', n: '\u041a\u043e\u043d\u0441\u0435\u043d\u0441\u0443\u0441', d: '\u0415\u0434\u0438\u043d\u043e\u0433\u043b\u0430\u0441\u043d\u043e\u0435 \u0440\u0435\u0448\u0435\u043d\u0438\u0435'},
            {t: 'liquid_democracy', i: '\ud83d\udd17', n: 'Liquid Democracy', d: '\u0414\u0435\u043b\u0435\u0433\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u0433\u043e\u043b\u043e\u0441\u043e\u0432'}
        ];
        var h = '<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px">';
        types.forEach(function(r) {
            var dis = r.t === regime.type ? ' disabled style="opacity:0.4;padding:14px 8px;flex-direction:column;display:flex;align-items:center;gap:4px"' : ' onclick="changeRegime(\'' + r.t + '\')" style="padding:14px 8px;flex-direction:column;display:flex;align-items:center;gap:4px"';
            h += '<button class="bee-btn bee-ripple" data-haptic="impact"' + dis + '>' +
                '<span style="font-size:24px">' + r.i + '</span>' +
                '<span style="font-weight:600;font-size:13px">' + r.n + '</span>' +
                '<span style="font-size:10px;opacity:0.7">' + r.d + '</span></button>';
        });
        h += '</div>';
        sheetOpen('\ud83d\udd04 \u0421\u043c\u0435\u043d\u0438\u0442\u044c \u0440\u0435\u0436\u0438\u043c', h, '');
    };

    // ── Petitions ──
    function openPetitionSheet(petId) {
        if (window.haptic) haptic('impact', 'light');
        fetch(_apiBase + '/petition/' + petId, {headers: _headers()})
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var p = data.petition || {};
            var signed = data.has_signed;
            var pct = p.total_citizens > 0 ? Math.round(p.signature_count / p.total_citizens * 100) : 0;
            var thPct = Math.round(p.threshold * 100);
            var typeLabels = {general: '\u041e\u0431\u0449\u0430\u044f', regime_change: '\u0421\u043c\u0435\u043d\u0430 \u0440\u0435\u0436\u0438\u043c\u0430', referendum: '\u0420\u0435\u0444\u0435\u0440\u0435\u043d\u0434\u0443\u043c'};
            var html = '<div style="padding:4px 0">'
                + '<div style="font-size:13px;opacity:0.6;margin-bottom:8px">' + (typeLabels[p.petition_type] || p.petition_type) + ' \u00b7 ' + (p.author_name || '') + '</div>'
                + (p.description ? '<div style="font-size:13px;margin-bottom:12px">' + esc(p.description) + '</div>' : '')
                + '<div style="margin-bottom:12px"><div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px"><span>' + p.signature_count + ' \u043f\u043e\u0434\u043f\u0438\u0441\u0435\u0439</span><span>\u043f\u043e\u0440\u043e\u0433 ' + thPct + '%</span></div>'
                + '<div style="height:6px;border-radius:3px;background:var(--tg-theme-secondary-bg-color);overflow:hidden"><div style="height:100%;width:' + Math.min(pct / thPct * 100, 100) + '%;background:var(--tg-theme-button-color);border-radius:3px"></div></div></div>';
            if (p.status === 'active' && !signed) {
                html += '<button class="bee-btn bee-ripple" data-haptic="impact" onclick="signPetition(' + p.id + ')" style="width:100%">\u270d\ufe0f \u041f\u043e\u0434\u043f\u0438\u0441\u0430\u0442\u044c \u043f\u0435\u0442\u0438\u0446\u0438\u044e</button>';
            } else if (signed) {
                html += '<div style="text-align:center;padding:8px;font-size:13px;opacity:0.7">\u2705 \u0412\u044b \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043b\u0438 \u044d\u0442\u0443 \u043f\u0435\u0442\u0438\u0446\u0438\u044e</div>';
            }
            if (p.status === 'triggered') {
                html += '<div style="text-align:center;padding:8px;font-size:13px;color:var(--tg-theme-button-color)">\ud83d\uddf3 \u041f\u0435\u0442\u0438\u0446\u0438\u044f \u0441\u043e\u0437\u0434\u0430\u043b\u0430 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0435 #' + (p.triggered_proposal_id || '') + '</div>';
            }
            html += '</div>';
            sheetOpen(esc(p.title), html, '');
        });
    }
    window.openPetitionSheet = openPetitionSheet;

    window.signPetition = function(petId) {
        if (window.haptic) haptic('impact', 'light');
        fetch(_apiBase + '/petition/' + petId + '/sign', {
            method: 'POST', headers: _headers({'Content-Type': 'application/json'})
        }).then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.error) { showToast(data.message || data.error); return; }
            showToast('\u270d\ufe0f \u041f\u043e\u0434\u043f\u0438\u0441\u044c \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d\u0430!');
            if (data.triggered) showToast('\ud83d\uddf3 \u041f\u0435\u0442\u0438\u0446\u0438\u044f \u0441\u043e\u0437\u0434\u0430\u043b\u0430 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0435!');
            sheetClose();
            _refreshGov();
        });
    };

    window.openCreatePetitionSheet = function() {
        if (window.haptic) haptic('impact', 'light');
        var html = '<div style="padding:4px 0">'
            + '<div class="bee-field" style="margin-bottom:12px"><label class="bee-field__label">\u0422\u0438\u043f</label>'
            + '<select id="pet-type" class="bee-input" style="width:100%">'
            + '<option value="general">\u041e\u0431\u0449\u0430\u044f \u043f\u0435\u0442\u0438\u0446\u0438\u044f</option>'
            + '<option value="regime_change">\u0421\u043c\u0435\u043d\u0430 \u0440\u0435\u0436\u0438\u043c\u0430</option>'
            + '<option value="referendum">\u0420\u0435\u0444\u0435\u0440\u0435\u043d\u0434\u0443\u043c</option></select></div>'
            + '<div class="bee-field" style="margin-bottom:12px"><label class="bee-field__label">\u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435</label>'
            + '<input type="text" id="pet-title" class="bee-input" placeholder="\u041e \u0447\u0451\u043c \u043f\u0435\u0442\u0438\u0446\u0438\u044f?" style="width:100%"></div>'
            + '<div class="bee-field" style="margin-bottom:12px"><label class="bee-field__label">\u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435</label>'
            + '<textarea id="pet-desc" class="bee-input" rows="3" placeholder="\u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438..." style="width:100%;resize:vertical"></textarea></div>'
            + '<button class="bee-btn bee-ripple" data-haptic="impact" onclick="submitPetition()" style="width:100%">\u270d\ufe0f \u0421\u043e\u0437\u0434\u0430\u0442\u044c \u043f\u0435\u0442\u0438\u0446\u0438\u044e</button>'
            + '</div>';
        sheetOpen('\u270d\ufe0f \u041d\u043e\u0432\u0430\u044f \u043f\u0435\u0442\u0438\u0446\u0438\u044f', html, '');
    };

    window.submitPetition = function() {
        var title = document.getElementById('pet-title').value.trim();
        if (!title) { showToast('\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435'); return; }
        if (window.haptic) haptic('impact', 'light');
        fetch(_apiBase + '/petition', {
            method: 'POST', headers: _headers({'Content-Type': 'application/json'}),
            body: JSON.stringify({
                petition_type: document.getElementById('pet-type').value,
                title: title,
                description: document.getElementById('pet-desc').value.trim()
            })
        }).then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.error) { showToast(data.message || data.error); return; }
            showToast('\u2705 \u041f\u0435\u0442\u0438\u0446\u0438\u044f \u0441\u043e\u0437\u0434\u0430\u043d\u0430!');
            sheetClose();
            _refreshGov();
        });
    };

    // ── Delegations ──
    var _delegCitizens = [];
    var _delegSelectedUid = null;

    window.openDelegateSheet = function() {
        if (window.haptic) haptic('impact', 'light');
        _delegSelectedUid = null;
        var html = '<div style="padding:4px 0">'
            + '<div class="bee-field" style="margin-bottom:12px"><label class="bee-field__label">\u0414\u0435\u043b\u0435\u0433\u0430\u0442</label>'
            + '<input type="text" id="deleg-search" class="bee-input" placeholder="\u041d\u0430\u0447\u043d\u0438\u0442\u0435 \u0432\u0432\u043e\u0434\u0438\u0442\u044c \u0438\u043c\u044f..." style="width:100%" autocomplete="off"></div>'
            + '<div id="deleg-list" style="max-height:240px;overflow-y:auto;margin-bottom:12px">'
            + '<div style="text-align:center;opacity:0.5;padding:16px">\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430...</div></div>'
            + '<div class="bee-field" style="margin-bottom:12px"><label class="bee-field__label">\u0422\u0435\u043c\u0430</label>'
            + '<select id="deleg-topic" class="bee-input" style="width:100%">'
            + '<option value="all">\u0412\u0441\u0435 \u0442\u0435\u043c\u044b</option></select></div>'
            + '<button class="bee-btn bee-ripple" data-haptic="impact" onclick="submitDelegation()" style="width:100%">\ud83d\udd17 \u0414\u0435\u043b\u0435\u0433\u0438\u0440\u043e\u0432\u0430\u0442\u044c</button>'
            + '</div>';
        sheetOpen('\ud83d\udd17 \u0414\u0435\u043b\u0435\u0433\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0433\u043e\u043b\u043e\u0441', html, '');
        // Загружаем граждан
        fetch('/api/chatdata/' + _chatId + '/citizens?status=citizen&limit=100', {headers: _headers()})
            .then(function(r) { return r.json(); })
            .then(function(data) {
                _delegCitizens = (data.items || []).filter(function(c) {
                    // Исключаем себя
                    var me = window.Telegram && Telegram.WebApp.initDataUnsafe && Telegram.WebApp.initDataUnsafe.user;
                    return !me || c.user_id !== me.id;
                });
                _renderDelegList('');
            });
        // Поиск с debounce
        var timer = null;
        setTimeout(function() {
            var inp = document.getElementById('deleg-search');
            if (inp) inp.addEventListener('input', function() {
                clearTimeout(timer);
                var q = this.value;
                timer = setTimeout(function() { _renderDelegList(q); }, 150);
            });
        }, 100);
    };

    function _renderDelegList(query) {
        var el = document.getElementById('deleg-list');
        if (!el) return;
        var q = (query || '').toLowerCase();
        var filtered = _delegCitizens.filter(function(c) {
            if (!q) return true;
            return (c.first_name || '').toLowerCase().indexOf(q) >= 0
                || (c.username || '').toLowerCase().indexOf(q) >= 0;
        });
        if (!filtered.length) {
            el.innerHTML = '<div style="text-align:center;opacity:0.5;padding:16px">' + (q ? '\u041d\u0438\u043a\u043e\u0433\u043e \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e' : '\u041d\u0435\u0442 \u0433\u0440\u0430\u0436\u0434\u0430\u043d') + '</div>';
            return;
        }
        el.innerHTML = filtered.map(function(c) {
            var sel = c.user_id === _delegSelectedUid;
            var ava = '/api/avatars/user/' + c.user_id;
            var name = c.first_name || 'User';
            var uname = c.username ? ' @' + c.username : '';
            return '<div onclick="selectDelegate(' + c.user_id + ')" style="display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:10px;cursor:pointer;'
                + (sel ? 'background:var(--bee-accent,#3b82f6);color:#fff' : 'background:var(--bee-card,#1e1e1e)')
                + ';margin-bottom:4px;transition:background .15s">'
                + '<img src="' + ava + '" onerror="this.style.display=\'none\'" style="width:36px;height:36px;border-radius:50%;object-fit:cover;flex-shrink:0">'
                + '<div style="min-width:0;flex:1"><div style="font-weight:600;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + escHtml(name) + '</div>'
                + (uname ? '<div style="font-size:11px;opacity:0.6">' + escHtml(uname) + '</div>' : '')
                + '</div>'
                + (sel ? '<span style="font-size:16px">\u2713</span>' : '')
                + '</div>';
        }).join('');
    }

    window.selectDelegate = function(uid) {
        if (window.haptic) haptic('selection');
        _delegSelectedUid = uid;
        _renderDelegList(document.getElementById('deleg-search') ? document.getElementById('deleg-search').value : '');
    };

    window.submitDelegation = function() {
        if (!_delegSelectedUid) { showToast('\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0435\u043b\u0435\u0433\u0430\u0442\u0430'); return; }
        if (window.haptic) haptic('impact', 'light');
        fetch(_apiBase + '/delegate', {
            method: 'POST', headers: _headers({'Content-Type': 'application/json'}),
            body: JSON.stringify({delegate_id: _delegSelectedUid, topic: document.getElementById('deleg-topic').value})
        }).then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.error) { showToast(data.message || data.error); return; }
            showToast('\u2705 \u0413\u043e\u043b\u043e\u0441 \u0434\u0435\u043b\u0435\u0433\u0438\u0440\u043e\u0432\u0430\u043d!');
            sheetClose();
            _refreshGov();
        });
    };

    window.revokeDelegation = function(topic) {
        if (window.haptic) haptic('impact', 'light');
        fetch(_apiBase + '/delegate', {
            method: 'DELETE', headers: _headers({'Content-Type': 'application/json'}),
            body: JSON.stringify({topic: topic})
        }).then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.error) { showToast(data.message || data.error); return; }
            showToast('\u2705 \u0414\u0435\u043b\u0435\u0433\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u043e\u0442\u043e\u0437\u0432\u0430\u043d\u043e');
            _refreshGov();
        });
    };

    // ── Exports ──
    return {
        regimeIcons: rI,
        regimeNames: rN,
        showToast: showToast,
        listRow: listRow,

        init: function(opts) {
            opts = opts || {};
            _apiBase = opts.apiBase || '';
            _chatId = opts.chatId || _apiBase.split('/').pop() || '';
            _initData = opts.initData || (window.Telegram && Telegram.WebApp.initData) || '';
            _pollInterval = opts.pollInterval || 15000;
            _onDataCb = opts.onData || null;
            _onSetupCb = opts.onSetup || null;
            _destroyed = false;
            _paused = false;

            var urlP = new URLSearchParams(window.location.search);
            _deepPID = urlP.get('proposal');

            // Override sheet close to clear chart
            var _origSheetClose = BeeKit.sheet.close;
            BeeKit.sheet.close = function() {
                _sheetStack = [];
                if (_sheetChart) { _sheetChart.dispose(); _sheetChart = null; }
                _origSheetClose();
            };

            _startPoll();
        },

        pause: function() {
            _paused = true;
        },

        resume: function() {
            _paused = false;
            _refreshGov();
        },

        destroy: function() {
            _destroyed = true;
            _paused = true;
            if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
            D = null;
        },

        refresh: _refreshGov,

        getData: function() { return D; }
    };
})();
