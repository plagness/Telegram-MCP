# Сетевая архитектура

Telegram Mini App требует публичный HTTPS. Сервер (Raspberry Pi 5) находится за NAT — доступ через VDS-прокси в Tailscale mesh-сети.

---

## Схема

```
Пользователь (Telegram)
    │
    │ HTTPS :8443
    ▼
VDS — публичный IP, домен tg.example.com
    │ socat TCP proxy
    │ Tailscale mesh
    ▼
Pi5 — hostPort :8443
    │ K3s pod
    ▼
tgweb (uvicorn + TLS :8000)
    │ direct DB / HTTP
    ▼
tgdb (PostgreSQL :5432)
tgapi (FastAPI :8000)
```

---

## Компоненты

### 1. VDS (прокси)

VDS с публичным IP и Tailscale выполняет TCP-проброс через `socat`:

```
socat TCP-LISTEN:8443,fork,reuseaddr TCP:<tailscale_ip_pi5>:8443
```

Запускается как systemd unit. Автоматика деплоя — `scripts/setup/vds_proxy.sh`.

### 2. Tailscale mesh

Все ноды в одной Tailscale сети. Трафик идёт через WireGuard-туннель.

### 3. K3s hostPort

tgweb использует `hostPort: 8443` в deployment — порт доступен на хосте Pi5 напрямую (без NodePort/LoadBalancer).

> **Важно:** `iptables REDIRECT` конфликтует с kube-proxy. Используем `hostPort` вместо iptables.

### 4. TLS

tgweb запускается с SSL (uvicorn `--ssl-certfile` / `--ssl-keyfile`). Сертификат Let's Encrypt, получен через DNS-01 challenge.

> **Важно:** В K3s контейнеры не видят симлинки hostPath. Монтировать реальные файлы: `/opt/certs/letsencrypt/`.

---

## Реестр нод (nodes.json)

Все ноды и маршруты описаны в `config/nodes.json` (gitignored, шаблон: `config/nodes.example.json`):

```json
{
  "nodes": [
    {
      "name": "vds-1",
      "public_ip": "203.0.113.10",
      "tailscale_ip": "100.64.0.10",
      "domain": "tg.example.com",
      "ssh_user": "root",
      "ports": {"socat": [8443]},
      "ram_gb": 2.0,
      "active": true
    },
    {
      "name": "k3s-node",
      "tailscale_ip": "100.64.0.1",
      "ports": {"k3s_host": [8443, 30081, 30335, 30443]},
      "ram_gb": 8.0,
      "active": true
    }
  ],
  "routes": [
    {
      "domain": "tg.example.com",
      "port": 8443,
      "proxy_node": "vds-1",
      "target_node": "k3s-node",
      "target_port": 8443,
      "service": "tgweb",
      "ssl": true,
      "description": "Telegram Mini App (HTTPS)"
    }
  ]
}
```

**API:** `GET /v1/web/nodes` — реестр нод (требует роль).

---

## Автоматика прокси (vds_proxy.sh)

Скрипт `scripts/setup/vds_proxy.sh` читает `nodes.json` и управляет socat на VDS:

```bash
# Показать конфигурацию (dry-run)
./scripts/setup/vds_proxy.sh show

# Деплой systemd units на все VDS
./scripts/setup/vds_proxy.sh deploy

# Проверить статус
./scripts/setup/vds_proxy.sh status

# Удалить прокси
./scripts/setup/vds_proxy.sh remove
```

**Что делает deploy:**
1. Подключается к VDS по SSH (через Tailscale IP)
2. Устанавливает socat если отсутствует
3. Создаёт systemd unit `socat-proxy-{service}-{port}.service`
4. Включает и запускает сервис

**Переменные:**
- `NODES_CONFIG` — путь к nodes.json (по умолчанию `config/nodes.json`)

---

## Порты

| Сервис | Порт контейнера | K3s NodePort / hostPort | Описание |
|--------|----------------|-------------------------|----------|
| tgweb | 8000 | hostPort:8443 | Mini App (HTTPS) |
| tgapi | 8000 | NodePort:30081 | REST API |
| tgmcp | 3335 | NodePort:30335 | MCP сервер |
| tgdb | 5432 | NodePort:30436 | PostgreSQL |
| tgweb | 8000 | NodePort:30443 | Web UI (альтернативный) |

---

## DNS

```
tg.example.com  A  <публичный IP VDS>
```

---

## Troubleshooting

### socat прокси не работает

```bash
# На VDS: проверить что socat слушает
ss -tlnp | grep 8443

# Проверить systemd unit
systemctl status socat-proxy-tgweb-8443

# Логи
journalctl -u socat-proxy-tgweb-8443 -f
```

### Нет доступа через Tailscale

```bash
# Проверить связность
tailscale ping <node-name>

# Проверить что порт слушает на Pi5
ssh <node> 'ss -tlnp | grep 8443'
```

### Mini App не открывается

1. Проверить DNS: `dig tg.example.com`
2. Проверить TLS: `curl -sk -v https://tg.example.com:8443/health`
3. Проверить socat: `ssh <vds> 'systemctl status socat-proxy-tgweb-8443'`
4. Проверить pod: `kubectl -n ns-telegram get pods`
