# 🚀 Batch Triggers - Autenticación Segura con Cloud Run

Este documento explica cómo el frontend triggerea los jobs de Cloud Run de manera **segura** sin exponer credenciales.

---

## 🔒 Problema de Seguridad

❌ **NO HACER - Inseguro:**
```javascript
// ❌ Frontend llamando directamente a Cloud Run
// Esto requeriría exponer tokens de service account (muy peligroso)
fetch('https://download-emerging-themes-batch.../upload-data', {
  headers: {
    'Authorization': 'Bearer SERVICE_ACCOUNT_TOKEN' // ⚠️ NUNCA exponer esto
  }
});
```

**¿Por qué es peligroso?**
- Los tokens de Cloud Run tienen permisos elevados (service account)
- Cualquier usuario puede inspeccionar el frontend y robar el token
- Permite acceso no autorizado a tus servicios de GCP

---

## ✅ Solución: Proxy a través de boomit-api

### Arquitectura Segura

```
┌─────────────┐      ┌──────────────┐      ┌─────────────────┐
│  Frontend   │─────▶│  boomit-api  │─────▶│   Cloud Run     │
│   (JWT)     │      │  (Proxy)     │      │ (Service Acct)  │
└─────────────┘      └──────────────┘      └─────────────────┘
   Usuario               Tu servidor            Google Cloud
   Token JWT         Valida JWT +            Token automático
                     Genera token CR          (workload identity)
```

**Ventajas:**
- ✅ Frontend solo usa su JWT normal (ya tienen uno)
- ✅ boomit-api valida permisos del usuario
- ✅ Service account tokens nunca expuestos
- ✅ Logs centralizados de quién triggerea qué
- ✅ Control de acceso granular

---

## 📡 Endpoints Disponibles

### 1. Trigger Emerging Themes Batch

**URL:** `POST /api/v1/batch/emerging-themes/trigger`

**Autenticación:** JWT token (mismo que usas para todo)

**Request:**
```json
{
  "batch_id": "batch_abc123",
  "app_id": "com.example.app"
}
```

**Response (200):**
```json
{
  "status": "success",
  "message": "Batch processing triggered successfully",
  "batch_id": "batch_abc123",
  "cloud_run_response": {
    "message": "Data uploaded successfully"
  }
}
```

**Errores:**
- `401 Unauthorized` - JWT inválido o expirado
- `503 Service Unavailable` - Cloud Run no disponible
- `500 Internal Server Error` - Error en Cloud Run

---

### 2. Trigger Reviews Analysis Batch

**URL:** `POST /api/v1/batch/reviews-analysis/trigger`

**Autenticación:** JWT token

**Request:**
```json
{
  "batch_id": "batch_xyz789",
  "app_id": "com.example.app"
}
```

**Response:** Igual que emerging themes

---

## 💻 Ejemplo de Uso en Frontend

### JavaScript/TypeScript

```javascript
// Obtener el JWT token (ya lo tienes para otras llamadas API)
const token = localStorage.getItem('authToken'); // o de donde lo obtengas
const userId = "31c5cb3d-ab5e-4530-bc93-731e50b408cf"; // Del token JWT

// PASO 1: Conectar WebSocket
const ws = new WebSocket(
  `ws://35.239.154.7:8000/api/v1/ws/batch-status/${userId}`,
  ["jwt.bearer", token]
);

ws.onopen = () => {
  console.log("✅ WebSocket conectado");
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  if (message.type === 'batch_completed') {
    console.log('🎉 ¡Análisis completado!', message);
    alert(`Análisis completado: ${message.total_reviews_analyzed} reviews`);
  }
};

// PASO 2: Crear análisis (tu endpoint existente)
const createAnalysis = async () => {
  const response = await fetch('http://35.239.154.7:8000/api/v1/apps/emerging-themes', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}` // ✅ Tu JWT normal
    },
    body: JSON.stringify({
      app_id: 'com.example.app',
      start_date: '2025-01-01',
      end_date: '2025-01-31'
    })
  });
  
  const data = await response.json();
  return data.batch_id;
};

// PASO 3: Suscribirse al batch
const subscribeToBatch = (batchId) => {
  ws.send(JSON.stringify({
    action: 'subscribe',
    batch_id: batchId
  }));
};

// PASO 4: Triggear Cloud Run a través de boomit-api (NUEVO)
const triggerCloudRun = async (batchId, appId) => {
  try {
    const response = await fetch(
      'http://35.239.154.7:8000/api/v1/batch/emerging-themes/trigger',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}` // ✅ El mismo JWT
        },
        body: JSON.stringify({
          batch_id: batchId,
          app_id: appId
        })
      }
    );
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${await response.text()}`);
    }
    
    const result = await response.json();
    console.log('✅ Cloud Run triggered:', result);
    return result;
    
  } catch (error) {
    console.error('❌ Error triggering Cloud Run:', error);
    throw error;
  }
};

// FLUJO COMPLETO
const runFullAnalysis = async () => {
  try {
    // 1. Crear análisis
    const batchId = await createAnalysis();
    console.log('📊 Análisis creado:', batchId);
    
    // 2. Suscribirse a notificaciones
    subscribeToBatch(batchId);
    
    // 3. Triggear procesamiento en Cloud Run
    await triggerCloudRun(batchId, 'com.example.app');
    
    console.log('⏳ Procesando... recibirás notificación vía WebSocket');
    
  } catch (error) {
    console.error('❌ Error:', error);
    alert('Error al iniciar análisis: ' + error.message);
  }
};

// Ejecutar
runFullAnalysis();
```

---

## 🔧 Configuración Backend (boomit-api)

### Variables de Entorno

Agregar a `.env`:

```bash
# Cloud Run Services URLs
EMERGING_THEMES_CLOUD_RUN_URL=https://download-emerging-themes-batch-715418856987.us-central1.run.app
REVIEWS_ANALYSIS_CLOUD_RUN_URL=https://download-batch-715418856987.us-central1.run.app
```

### Service Account (GKE/Cloud Run)

Para que boomit-api pueda autenticarse con Cloud Run, necesitas configurar **Workload Identity**:

#### 1. Crear Service Account (si no existe)

```bash
# Crear service account
gcloud iam service-accounts create boomit-api-sa \
  --display-name="Boomit API Service Account"

# Dar permisos para invocar Cloud Run
gcloud run services add-iam-policy-binding download-emerging-themes-batch \
  --member="serviceAccount:boomit-api-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker" \
  --region=us-central1

gcloud run services add-iam-policy-binding download-batch \
  --member="serviceAccount:boomit-api-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker" \
  --region=us-central1
```

#### 2. Configurar Workload Identity (si boomit-api está en GKE)

```bash
# Vincular service account de K8s con service account de GCP
gcloud iam service-accounts add-iam-policy-binding \
  boomit-api-sa@PROJECT_ID.iam.gserviceaccount.com \
  --role roles/iam.workloadIdentityUser \
  --member "serviceAccount:PROJECT_ID.svc.id.goog[NAMESPACE/KSA_NAME]"
```

#### 3. Deployment YAML (GKE)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: boomit-api
spec:
  template:
    metadata:
      annotations:
        # Habilitar workload identity
        iam.gke.io/gcp-service-account: boomit-api-sa@PROJECT_ID.iam.gserviceaccount.com
    spec:
      serviceAccountName: boomit-api-ksa
      containers:
      - name: boomit-api
        image: gcr.io/PROJECT_ID/boomit-api:latest
        env:
        - name: EMERGING_THEMES_CLOUD_RUN_URL
          value: "https://download-emerging-themes-batch-715418856987.us-central1.run.app"
```

---

## 🧪 Testing

### Test Local (sin autenticación Cloud Run)

Para development local, el código intenta sin token si falla la generación:

```bash
# En .env local
EMERGING_THEMES_CLOUD_RUN_URL=http://localhost:8080  # Tu Cloud Run local
```

### Test con wscat

```bash
# 1. Crear análisis
curl -X POST http://localhost:8000/api/v1/apps/emerging-themes \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT" \
  -d '{
    "app_id": "com.example.app",
    "start_date": "2025-01-01",
    "end_date": "2025-01-31"
  }'

# Response: { "batch_id": "batch_abc123", ... }

# 2. Triggear Cloud Run
curl -X POST http://localhost:8000/api/v1/batch/emerging-themes/trigger \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT" \
  -d '{
    "batch_id": "batch_abc123",
    "app_id": "com.example.app"
  }'

# Response: { "status": "success", ... }
```

---

## 🔐 Seguridad

### ✅ Buenas Prácticas Implementadas

1. **JWT Validation**: Solo usuarios autenticados pueden triggerar
2. **Service Account Isolation**: Cada servicio con permisos mínimos
3. **No Token Exposure**: Service account tokens nunca llegan al cliente
4. **Audit Logging**: Todos los triggers logueados con user_id
5. **Timeouts**: 30s timeout para evitar hanging requests

### 🚨 Importante

- **NUNCA** expongas variables de environment con tokens en el frontend
- **NUNCA** pongas service account keys en el código
- **SIEMPRE** usa Workload Identity en producción
- **SIEMPRE** valida JWT antes de triggerar Cloud Run

---

## 📊 Monitoreo

### Logs en boomit-api

```
INFO: User 31c5cb3d-ab5e-4530-bc93-731e50b408cf triggering emerging themes batch batch_abc123
INFO: ✅ Successfully triggered Cloud Run for batch batch_abc123
```

### Logs en Cloud Run

```
INFO: Received batch processing request for batch_abc123
INFO: Successfully uploaded 1500 rows to BigQuery
INFO: ✅ Webhook notification sent successfully
```

---

## 🆘 Troubleshooting

### Error: "Failed to authenticate with Cloud Run service"

**Causa:** Service account no configurado o sin permisos

**Solución:**
1. Verificar que service account existe
2. Verificar permisos de `roles/run.invoker`
3. Verificar workload identity binding

```bash
# Verificar permisos
gcloud run services get-iam-policy download-emerging-themes-batch --region=us-central1
```

### Error: "Could not connect to batch processing service"

**Causa:** URL de Cloud Run incorrecta o servicio no disponible

**Solución:**
1. Verificar variable `EMERGING_THEMES_CLOUD_RUN_URL`
2. Verificar que Cloud Run está deployed y running
3. Verificar networking (VPC, firewall)

### Error: 401 Unauthorized al triggerar

**Causa:** JWT inválido o expirado

**Solución:**
1. Verificar que el token está presente en header
2. Regenerar token si expiró
3. Verificar `SECRET_KEY` en backend

---

## 🎯 Resumen

- ✅ **Frontend**: Solo usa JWT (no cambia nada en autenticación)
- ✅ **Backend**: Proxy seguro con service account automático
- ✅ **Cloud Run**: Recibe requests autenticadas de boomit-api
- ✅ **Seguridad**: Tokens de service account nunca expuestos
- ✅ **Auditoría**: Logs completos de quién triggerea qué

**Flujo simplificado:**
```
Frontend (JWT) → boomit-api → Cloud Run → BigQuery → Webhook → WebSocket → Frontend
```

¿Preguntas? Revisa los ejemplos de código arriba o contacta al equipo de desarrollo.
