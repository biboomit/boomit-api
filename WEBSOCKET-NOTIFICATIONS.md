# 🔔 Sistema de Notificaciones WebSocket

Este documento describe cómo funciona el sistema de notificaciones en tiempo real para análisis de IA completados.

## 📋 Características

- ✅ Notificaciones en tiempo real vía WebSocket
- ✅ Soporte para **Emerging Themes Analysis**
- ✅ Soporte para **AI Reviews Analysis** (sentimiento)
- ✅ Infraestructura reutilizable para futuros análisis
- ✅ Gestión automática de suscripciones por batch_id

---

## 🏗️ Arquitectura

```
┌─────────────┐      ┌──────────────┐      ┌────────────────┐
│  Frontend   │─────▶│  boomit-api  │─────▶│  OpenAI Batch  │
│             │◀─────│  (WebSocket) │      │      API       │
└─────────────┘      └──────────────┘      └────────────────┘
       ▲                     ▲                       │
       │                     │                       │
       │                     │                       ▼
       │              ┌──────────────┐      ┌────────────────┐
       │              │   Webhook    │◀─────│ download-batch │
       └──────────────│   Endpoint   │      │  (Cloud Run)   │
         Notificación └──────────────┘      └────────────────┘
                                                     ▲
                                                     │
                                              ┌──────────────┐
                                              │   BigQuery   │
                                              └──────────────┘
```

---

## 🔌 Endpoints

### 1. WebSocket Connection

**URL:** `wss://your-api.com/api/v1/ws/batch-status/{user_id}` (production) or `ws://localhost:8000/api/v1/ws/batch-status/{user_id}` (development)

**Authentication:** Required in production. Pass JWT token via `Sec-WebSocket-Protocol` header.

**Security:**

- ✅ Always use `wss://` (WebSocket Secure) in production to encrypt token transmission
- ✅ Tokens are sent via WebSocket subprotocol header (RFC 6455), not in URLs
- ✅ This prevents token leakage in server logs, browser history, and HTTP referrer headers
- ❌ Never use `ws://` in production - tokens would be transmitted in plain text

**Cliente envía:**

```json
{
	"action": "subscribe",
	"batch_id": "batch_xxx"
}
```

**Cliente recibe (cuando batch completa):**

```json
{
	"type": "batch_completed",
	"batch_id": "batch_xxx",
	"app_id": "com.example.app",
	"total_reviews_analyzed": 1500,
	"analyzed_at": "2025-12-01T10:30:00Z"
}
```

---

### 2. Webhook - Emerging Themes (download-emerging-themes-batch)

**URL:** `POST /api/v1/webhook/batch-completed`

**Payload:**

```json
{
	"batch_id": "batch_abc123",
	"analysis_id": "550e8400-e29b-41d4-a716-446655440000",
	"app_id": "com.example.app",
	"total_reviews_analyzed": 1500,
	"analysis_period_start": "2025-01-01",
	"analysis_period_end": "2025-01-31",
	"analyzed_at": "2025-01-31T10:30:00Z"
}
```

**Response:**

```json
{
	"status": "success",
	"message": "Batch completion notification sent to 3 user(s)",
	"batch_id": "batch_abc123",
	"subscribers_notified": 3
}
```

---

### 3. Webhook - AI Reviews Analysis (download-batch)

**URL:** `POST /api/v1/webhook/reviews-batch-completed`

**Payload:**

```json
{
	"batch_id": "batch_xyz789",
	"app_id": "com.example.app",
	"total_reviews_analyzed": 2500,
	"analyzed_at": "2025-12-01T15:45:00Z"
}
```

**Response:**

```json
{
	"status": "success",
	"message": "Reviews batch completion notification sent to 2 user(s)",
	"batch_id": "batch_xyz789",
	"subscribers_notified": 2
}
```

---

## 🔄 Flujo Completo (AI Reviews Analysis)

### Paso 1: Iniciar Análisis

```javascript
// Frontend solicita análisis
const response = await fetch("/api/v1/apps/reviews/ai-analysis", {
	method: "POST",
	headers: { "Content-Type": "application/json" },
	body: JSON.stringify({
		app_id: "com.example.app",
		parameters: {
			from_date: "2025-01-01",
			to_date: "2025-01-31",
		},
	}),
});

const { batch } = await response.json();
const batchId = batch.id; // "batch_xyz789"
```

### Paso 2: Conectar WebSocket

```javascript
// Conectar WebSocket con autenticación segura
const token = "your-jwt-token"; // Obtener del login

// Detectar entorno (producción vs desarrollo)
const isProduction = window.location.protocol === "https:";
const wsProtocol = isProduction ? "wss://" : "ws://";
const wsHost = isProduction ? "your-api.com" : "localhost:8000";

const ws = new WebSocket(
	`${wsProtocol}${wsHost}/api/v1/ws/batch-status/user123`,
	["jwt.bearer", token] // Protocol name + token as separate subprotocols
);

ws.onopen = () => {
	// Suscribirse al batch
	ws.send(
		JSON.stringify({
			action: "subscribe",
			batch_id: batchId,
		})
	);
};

ws.onmessage = (event) => {
	const data = JSON.parse(event.data);

	if (data.type === "subscribed") {
		console.log("✅ Suscrito al batch:", data.batch_id);
	}

	if (data.type === "batch_completed") {
		console.log("🎉 Análisis completado!");
		console.log("App:", data.app_id);
		console.log("Reviews analizados:", data.total_reviews_analyzed);
		// Recargar datos o mostrar notificación
	}
};
```

### Paso 3: Backend Procesa (Automático)

```
1. OpenAI procesa el batch (minutos/horas)
2. download-batch detecta completación
3. download-batch descarga resultados
4. download-batch sube a BigQuery
5. download-batch envía webhook a boomit-api
6. boomit-api notifica usuarios vía WebSocket
7. Frontend recibe notificación y actualiza UI
```

---

## ⚙️ Configuración

### Variables de Entorno (boomit-api)

```bash
# WebSocket Authentication
WEBSOCKET_AUTH_REQUIRED=false  # Set to true in production
SECRET_KEY=your-secret-key-here-change-in-production
ALGORITHM=HS256
```

**⚠️ Security Note:**

- Always use `WEBSOCKET_AUTH_REQUIRED=true` in production
- Tokens are sent via `Sec-WebSocket-Protocol` header (not in URLs)
- This prevents token exposure in server logs and browser history

### Variables de Entorno (download-batch)

```bash
BOOMIT_API_WEBHOOK_URL=https://your-boomit-api.com/api/v1
```

### Variables de Entorno (download-emerging-themes-batch)

```bash
BOOMIT_API_WEBHOOK_URL=https://your-boomit-api.com/api/v1
```

---

## 🧪 Testing

### Test WebSocket Connection

```bash
# Usando wscat (desarrollo local - ws://)
npm install -g wscat

# Con autenticación
wscat -c "ws://localhost:8000/api/v1/ws/batch-status/test_user" --subprotocol "jwt.bearer" --subprotocol "YOUR_JWT_TOKEN"

# Sin autenticación (solo desarrollo - WEBSOCKET_AUTH_REQUIRED=false)
wscat -c "ws://localhost:8000/api/v1/ws/batch-status/test_user"

# Para producción usar wss:// (WebSocket Secure)
wscat -c "wss://your-api.com/api/v1/ws/batch-status/test_user" --subprotocol "jwt.bearer" --subprotocol "YOUR_JWT_TOKEN"

# Enviar suscripción
{"action": "subscribe", "batch_id": "batch_test123"}
```

**Generar token para testing:**

```bash
# En la carpeta boomit-api-utils (fuera del workspace)
python generate_token.py test_user 24
```

### Test Webhook (Emerging Themes)

```bash
curl -X POST http://localhost:8000/api/v1/webhook/batch-completed \
  -H "Content-Type: application/json" \
  -d '{
    "batch_id": "batch_test_emerging_themes_001",
    "analysis_id": "et123456",
    "app_id": "com.test.app",
    "total_reviews_analyzed": 1500,
    "analysis_period_start": "2025-09-01",
    "analysis_period_end": "2025-11-30",
    "analyzed_at": "2025-12-01T15:45:00Z"
  }'
```

### Test Webhook (AI Reviews) - PowerShell

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/webhook/batch-completed" -Method POST -ContentType "application/json" -Body '{
  "batch_id": "batch_test_emerging_themes_001",
  "analysis_id": "et123456",
  "app_id": "com.test.app",
  "total_reviews_analyzed": 1500,
  "analysis_period_start": "2025-09-01",
  "analysis_period_end": "2025-11-30",
  "analyzed_at": "2025-12-01T15:45:00Z"
}'
```

---

## 📊 Monitoreo

### Logs en boomit-api

```
✅ User test_user connected. Total connections: 1
📬 User test_user subscribed to batch batch_test_emerging_themes_001
📢 Notifying 1 users about batch batch_test_emerging_themes_001
✉️ Notification sent to user test_user
❌ User test_user disconnected. Total connections: 1
```

### Logs en download-batch

```
Successfully uploaded 2500 rows to BigQuery table your-project.dataset.table
Sending webhook notification to https://your-api.com/api/v1/webhook/reviews-batch-completed
✅ Webhook notification sent successfully for batch batch_test_emerging_themes_001
```

---

## 🔒 Seguridad

### Autenticación WebSocket

**Método actual:** `Sec-WebSocket-Protocol` header (RFC 6455) + TLS (wss://)

**¿Por qué es seguro?**

- ✅ **wss:// (TLS)** encripta toda la comunicación incluyendo tokens
- ✅ Tokens **NO** aparecen en URLs
- ✅ No se registran en server logs estándar
- ✅ No se guardan en historial del navegador
- ✅ No se exponen vía HTTP Referrer headers
- ✅ Cumple con estándar WebSocket oficial (RFC 6455)

**⚠️ Nunca uses:**

```javascript
// ❌ INSEGURO - Token en query string
const ws = new WebSocket("ws://api.com/ws/...?token=SECRET");

// ❌ INSEGURO - ws:// sin TLS en producción (token en texto plano)
const ws = new WebSocket("ws://api.com/ws/...", ["jwt.bearer", token]);

// ✅ SEGURO - wss:// con TLS + token en subprotocol
const ws = new WebSocket("wss://api.com/ws/...", ["jwt.bearer", token]);

// ✅ OK para desarrollo local
const ws = new WebSocket("ws://localhost:8000/ws/...", ["jwt.bearer", token]);
```

**Configuración recomendada:**

- **Desarrollo**: `WEBSOCKET_AUTH_REQUIRED=false` + `ws://localhost`
- **Producción**: `WEBSOCKET_AUTH_REQUIRED=true` + `wss://` (TLS obligatorio)

---

## 🚀 Ventajas

1. **Experiencia de Usuario Mejorada**: No necesita refrescar la página
2. **Escalable**: Soporta múltiples usuarios suscritos al mismo batch
3. **Resiliente**: Si webhook falla, no afecta el upload a BigQuery
4. **Reutilizable**: Misma infraestructura para múltiples tipos de análisis
5. **Desacoplado**: Servicios independientes comunicándose vía HTTP/WebSocket

---

## 🔮 Futuras Mejoras

- [x] Autenticación JWT en WebSocket
- [ ] Persistencia de notificaciones perdidas
- [ ] Retry automático de webhooks fallidos
- [ ] Notificaciones por email como fallback
- [ ] Panel de administración para ver conexiones activas
- [ ] Métricas de latencia de notificaciones

---

## 👥 Soporte

Para preguntas o issues, contacta al equipo de desarrollo.
