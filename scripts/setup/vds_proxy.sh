#!/usr/bin/env bash
# vds_proxy.sh — Автоматика socat-прокси на VDS.
#
# Читает config/nodes.json, для каждого route генерирует systemd unit
# и деплоит на VDS через SSH.
#
# Использование:
#   ./scripts/setup/vds_proxy.sh deploy   # Деплой socat unit на все VDS
#   ./scripts/setup/vds_proxy.sh status   # Проверка статуса прокси
#   ./scripts/setup/vds_proxy.sh remove   # Удаление прокси
#   ./scripts/setup/vds_proxy.sh show     # Показать конфигурацию (dry-run)
#
# Требования: jq, ssh, systemctl (на VDS), socat (на VDS)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
NODES_CONFIG="${NODES_CONFIG:-$REPO_ROOT/config/nodes.json}"
UNIT_PREFIX="socat-proxy"

# ── Цвета ─────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_err()   { echo -e "${RED}[ERR]${NC} $*"; }

# ── Проверки ──────────────────────────────────────────

check_deps() {
    if ! command -v jq &>/dev/null; then
        log_err "jq не найден. Установите: sudo apt install jq"
        exit 1
    fi
    if [[ ! -f "$NODES_CONFIG" ]]; then
        log_err "Файл нод не найден: $NODES_CONFIG"
        exit 1
    fi
}

# ── Helpers ───────────────────────────────────────────

# Получить ssh_user и tailscale_ip ноды по имени
get_node_ssh() {
    local name="$1"
    local user ip
    user=$(jq -r ".nodes[] | select(.name == \"$name\") | .ssh_user // \"root\"" "$NODES_CONFIG")
    ip=$(jq -r ".nodes[] | select(.name == \"$name\") | .tailscale_ip // .public_ip" "$NODES_CONFIG")
    if [[ -z "$ip" || "$ip" == "null" ]]; then
        log_err "Не удалось определить IP для ноды '$name'"
        return 1
    fi
    echo "${user}@${ip}"
}

# Получить tailscale_ip целевой ноды
get_target_ip() {
    local name="$1"
    local ip
    ip=$(jq -r ".nodes[] | select(.name == \"$name\") | .tailscale_ip" "$NODES_CONFIG")
    if [[ -z "$ip" || "$ip" == "null" ]]; then
        log_err "Не удалось определить Tailscale IP для ноды '$name'"
        return 1
    fi
    echo "$ip"
}

# Имя systemd unit для route
unit_name() {
    local service="$1" port="$2"
    echo "${UNIT_PREFIX}-${service}-${port}"
}

# Сгенерировать содержимое systemd unit
generate_unit() {
    local service="$1" listen_port="$2" target_ip="$3" target_port="$4" desc="$5"
    cat <<UNIT
[Unit]
Description=socat proxy: ${desc}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/socat TCP-LISTEN:${listen_port},fork,reuseaddr TCP:${target_ip}:${target_port}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
}

# ── Итерация по routes ────────────────────────────────

# Вызывает callback для каждого route:
#   callback proxy_ssh service port target_ip target_port description unit
iterate_routes() {
    local callback="$1"
    local count
    count=$(jq '.routes | length' "$NODES_CONFIG")

    if [[ "$count" -eq 0 ]]; then
        log_warn "Нет маршрутов в $NODES_CONFIG"
        return 0
    fi

    for i in $(seq 0 $((count - 1))); do
        local service port proxy_node target_node target_port desc
        service=$(jq -r ".routes[$i].service" "$NODES_CONFIG")
        port=$(jq -r ".routes[$i].port" "$NODES_CONFIG")
        proxy_node=$(jq -r ".routes[$i].proxy_node" "$NODES_CONFIG")
        target_node=$(jq -r ".routes[$i].target_node" "$NODES_CONFIG")
        target_port=$(jq -r ".routes[$i].target_port" "$NODES_CONFIG")
        desc=$(jq -r ".routes[$i].description // .routes[$i].service" "$NODES_CONFIG")

        local proxy_ssh target_ip unit
        proxy_ssh=$(get_node_ssh "$proxy_node") || continue
        target_ip=$(get_target_ip "$target_node") || continue
        unit=$(unit_name "$service" "$port")

        "$callback" "$proxy_ssh" "$service" "$port" "$target_ip" "$target_port" "$desc" "$unit"
    done
}

# ── Команды ───────────────────────────────────────────

cmd_show() {
    log_info "Конфигурация прокси из $NODES_CONFIG"
    echo ""

    _show_route() {
        local proxy_ssh="$1" service="$2" port="$3" target_ip="$4" target_port="$5" desc="$6" unit="$7"
        echo -e "  ${CYAN}${service}${NC} :${port} → ${target_ip}:${target_port}"
        echo -e "    VDS: ${proxy_ssh}"
        echo -e "    Unit: ${unit}.service"
        echo -e "    Описание: ${desc}"
        echo ""
    }

    iterate_routes _show_route
}

cmd_deploy() {
    log_info "Деплой socat-прокси на VDS..."
    echo ""

    _deploy_route() {
        local proxy_ssh="$1" service="$2" port="$3" target_ip="$4" target_port="$5" desc="$6" unit="$7"
        local unit_content
        unit_content=$(generate_unit "$service" "$port" "$target_ip" "$target_port" "$desc")
        local unit_path="/etc/systemd/system/${unit}.service"

        log_info "[$service:$port] → ${proxy_ssh} (${target_ip}:${target_port})"

        # Проверить наличие socat на VDS
        if ! ssh -o ConnectTimeout=5 "$proxy_ssh" "command -v socat" &>/dev/null; then
            log_warn "socat не найден на $proxy_ssh, устанавливаю..."
            ssh "$proxy_ssh" "apt-get update -qq && apt-get install -y -qq socat" || {
                log_err "Не удалось установить socat на $proxy_ssh"
                return 1
            }
        fi

        # Записать unit файл
        echo "$unit_content" | ssh "$proxy_ssh" "cat > $unit_path"

        # Активировать и запустить
        ssh "$proxy_ssh" "systemctl daemon-reload && systemctl enable --now ${unit}.service" 2>/dev/null

        # Проверить статус
        if ssh "$proxy_ssh" "systemctl is-active ${unit}.service" &>/dev/null; then
            log_ok "[$service:$port] запущен"
        else
            log_err "[$service:$port] не запустился"
            ssh "$proxy_ssh" "journalctl -u ${unit}.service --no-pager -n 5" 2>/dev/null || true
        fi
        echo ""
    }

    iterate_routes _deploy_route
    log_ok "Деплой завершён"
}

cmd_status() {
    log_info "Статус socat-прокси..."
    echo ""

    _status_route() {
        local proxy_ssh="$1" service="$2" port="$3" target_ip="$4" target_port="$5" desc="$6" unit="$7"
        local status
        if status=$(ssh -o ConnectTimeout=5 "$proxy_ssh" "systemctl is-active ${unit}.service" 2>/dev/null); then
            log_ok "[$service:$port] $status (${proxy_ssh})"
        else
            log_err "[$service:$port] ${status:-unreachable} (${proxy_ssh})"
        fi
    }

    iterate_routes _status_route
}

cmd_remove() {
    log_info "Удаление socat-прокси с VDS..."
    echo ""

    _remove_route() {
        local proxy_ssh="$1" service="$2" port="$3" target_ip="$4" target_port="$5" desc="$6" unit="$7"
        local unit_path="/etc/systemd/system/${unit}.service"

        log_info "[$service:$port] удаляю с ${proxy_ssh}..."
        ssh -o ConnectTimeout=5 "$proxy_ssh" \
            "systemctl stop ${unit}.service 2>/dev/null; \
             systemctl disable ${unit}.service 2>/dev/null; \
             rm -f $unit_path; \
             systemctl daemon-reload" 2>/dev/null

        log_ok "[$service:$port] удалён"
    }

    iterate_routes _remove_route
    log_ok "Удаление завершено"
}

# ── Main ──────────────────────────────────────────────

usage() {
    echo "Использование: $0 {deploy|status|remove|show}"
    echo ""
    echo "  deploy  — Деплой socat systemd units на VDS (по routes из nodes.json)"
    echo "  status  — Проверить статус всех прокси"
    echo "  remove  — Остановить и удалить все прокси с VDS"
    echo "  show    — Показать конфигурацию (dry-run)"
    echo ""
    echo "Переменные:"
    echo "  NODES_CONFIG  — путь к nodes.json (по умолчанию: config/nodes.json)"
}

main() {
    check_deps

    case "${1:-}" in
        deploy) cmd_deploy ;;
        status) cmd_status ;;
        remove) cmd_remove ;;
        show)   cmd_show ;;
        -h|--help|help) usage ;;
        *)
            usage
            exit 1
            ;;
    esac
}

main "$@"
