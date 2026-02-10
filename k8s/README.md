# K8s манифесты — telegram-mcp

## Структура

```
k8s/
├── kustomization.yaml      # Kustomize entry point
├── namespace.yaml           # ns-telegram
├── secret.yaml              # DB credentials, bot token
├── configmap.yaml           # URLs, конфигурация
├── tgdb-pvc.yaml            # PVC 10Gi для PostgreSQL
├── tgdb-statefulset.yaml    # PostgreSQL 16 StatefulSet
├── tgdb-service.yaml        # ClusterIP + NodePort 30436
├── tgapi-deployment.yaml    # FastAPI Deployment
├── tgapi-service.yaml       # ClusterIP + NodePort 30081
├── tgmcp-deployment.yaml    # Node.js MCP Deployment
├── tgmcp-service.yaml       # ClusterIP + NodePort 30335
├── tgweb-deployment.yaml    # SSL Mini App Deployment
└── tgweb-service.yaml       # ClusterIP + NodePort 30443
```

## Деплой

```bash
# 1. Сборка и импорт образов
./scripts/k3s_import_images.sh telegram-mcp

# 2. Заполнить секреты
kubectl -n ns-telegram create secret generic telegram-secrets \
  --from-literal=DB_USER=telegram \
  --from-literal=DB_PASSWORD=telegram \
  --from-literal=DB_NAME=telegram \
  --from-literal=TELEGRAM_BOT_TOKEN=<BOT_TOKEN> \
  --from-literal=MCP_HTTP_TOKEN=<MCP_TOKEN> \
  --dry-run=client -o yaml | kubectl apply -f -

# 3. Деплой
kubectl apply -k telegram-mcp/k8s/
```

## Порты (NodePort)

| Сервис | Compose порт | NodePort | Назначение |
|--------|-------------|----------|------------|
| tgdb   | 5436        | 30436    | PostgreSQL |
| tgapi  | 8081        | 30081    | HTTP API   |
| tgmcp  | 3335        | 30335    | MCP Bridge |
| tgweb  | 8443        | 30443    | SSL Mini App |

## Проброс 8443 → 30443

VPS socat отправляет трафик на pi5:8443. В K3s tgweb слушает на NodePort 30443.
Нужен iptables-проброс:

```bash
sudo iptables -t nat -A PREROUTING -p tcp --dport 8443 -j REDIRECT --to-port 30443
sudo iptables -t nat -A OUTPUT -o lo -p tcp --dport 8443 -j REDIRECT --to-port 30443
```

## Cross-namespace DNS

Другие модули обращаются к telegram-mcp через:
- `tgapi.ns-telegram.svc.cluster.local:8000`
- `tgmcp.ns-telegram.svc.cluster.local:3335`
- `tgweb.ns-telegram.svc.cluster.local:8000`
