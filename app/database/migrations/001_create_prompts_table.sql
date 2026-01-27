-- Crear tabla para gestión de prompts dinámicos
-- Ejecutar: bq query --use_legacy_sql=false < 001_create_prompts_table.sql

CREATE TABLE IF NOT EXISTS `marketing-dwh-specs.DWH.AI_PROMPTS` (
  prompt_id STRING NOT NULL OPTIONS(description="UUID único del prompt"),
  prompt_key STRING NOT NULL OPTIONS(description="Identificador del tipo de prompt (ej: report_generation_highchart)"),
  prompt_version INT64 NOT NULL OPTIONS(description="Número de versión autoincremental por prompt_key"),
  prompt_content STRING NOT NULL OPTIONS(description="Contenido completo del template del prompt"),
  variables JSON OPTIONS(description="Lista de variables que requiere el template"),
  description STRING OPTIONS(description="Descripción del cambio realizado en esta versión"),
  is_active BOOL NOT NULL OPTIONS(description="Indica si esta versión está activa"),
  created_by STRING NOT NULL OPTIONS(description="Email del usuario que creó esta versión"),
  created_at TIMESTAMP NOT NULL OPTIONS(description="Fecha y hora de creación"),
  validated BOOL OPTIONS(description="Indica si el prompt pasó la validación"),
  validation_error STRING OPTIONS(description="Mensaje de error si la validación falló")
)
PARTITION BY DATE(created_at)
CLUSTER BY prompt_key, is_active
OPTIONS(
  description="Tabla para gestión de prompts dinámicos de OpenAI. Permite versionado y activación de diferentes versiones sin modificar código.",
  labels=[("component", "ai"), ("purpose", "prompt_management")]
);

-- Crear índice para búsquedas rápidas por prompt_key activo
-- BigQuery no usa índices tradicionales, pero el CLUSTER BY ya optimiza esto

-- Comentarios sobre el uso:
-- 1. Cada prompt_key solo puede tener UNA versión con is_active=true
-- 2. El prompt_version se incrementa automáticamente en la aplicación
-- 3. Para activar una versión antigua: UPDATE is_active de todas a false, luego la deseada a true
-- 4. La partición por fecha ayuda a consultas históricas eficientes
