import os

from app.services.analytics_providers.base import AnalyticsProvider


BANCO_BCT_EXPLANATION = """
FORMATO DE analytics_data:
- dataset: uno de ["totales_globales_periodo", "totales_por_network", "serie_diaria_por_network", "funnel_etapas", "top_campanas_mes"].
  * totales_globales_periodo: 1 fila con métricas agregadas del rango completo, incluye presupuesto y pacing.
  * totales_por_network: filas con totales por network (plataforma publicitaria).
  * serie_diaria_por_network: filas con métricas diarias desglosadas por network y fecha.
  * funnel_etapas: 1 fila con las 2 etapas del funnel (visita_landing, solicita_tc_enviada, cvr_landing_enviada).
  * top_campanas_mes: hasta top_n campañas rankeadas por solicita_tc_enviada (luego inversión).

- Campos comunes: inversion, visita_landing, solicita_tc_enviada, cpa_visita_landing, cpa_solicita_tc_enviada, cvr_landing_enviada.
- Campos específicos por dataset:
  * totales_globales_periodo: incluye presupuesto, pacing_porcentaje
  * serie_diaria_por_network: incluye campo "fecha" (DATE) y "network"
  * top_campanas_mes: incluye nombre_campana, network
  * totales_por_network: incluye network
  * funnel_etapas: incluye visita_landing, solicita_tc_enviada, cvr_landing_enviada

- NOTA: Este proveedor NO tiene datos de región/país ni sistema operativo.
  La dimensión principal de segmentación es "network" (plataforma publicitaria).
- NOTA: No existe dataset "serie_diaria_top" ni "serie_diaria_agregada".
  Para series temporales, usar "serie_diaria_por_network" (agregar por fecha si se requiere total diario).
- Los KPIs (CPA/CVR) serán NULL si el denominador es 0; NO los trates como 0.
- Filtrado previo: excluye campañas "unknown" y network en ("Organic", "Others"), requiere solicita_tc_enviada > 0.

DICCIONARIO DE DATOS:
- fecha: día del dato.
- nombre_campana: identificador de campaña.
- network: plataforma publicitaria (ej: Google Ads, Meta, TikTok).
- inversion: gasto publicitario total.
- presupuesto: presupuesto máximo asignado.
- visita_landing: visitas a la landing page generadas por la campaña.
- solicita_tc_enviada: solicitudes de tarjeta de crédito enviadas exitosamente (conversión final).
- cpa_visita_landing = inversion / visita_landing.
- cpa_solicita_tc_enviada = inversion / solicita_tc_enviada.
- cvr_landing_enviada = solicita_tc_enviada / visita_landing.
- pacing_porcentaje = inversion / presupuesto (% de ejecución del presupuesto).
Funnel: Inversión → Visita Landing → Solicita TC Enviada. CPA_solicita_tc_enviada es el KPI final crítico.

REGLAS POR BLOQUE (OBLIGATORIO - MÁXIMA PRIORIDAD):

Estas instrucciones ESPECÍFICAS por bloque tienen PRIORIDAD ABSOLUTA sobre todas las demás reglas.
Cada bloque problemático DEBE incluir los gráficos especificados a continuación.

BLOQUE: analisis_region
-----------------------
NOTA: Este proveedor NO tiene datos por región geográfica. Usar "network" como dimensión.
OBJETIVO: Mostrar performance por network/plataforma publicitaria
DATASET A USAR: totales_por_network (YA viene pre-agregado por network)

GRÁFICOS OBLIGATORIOS (elegir 2):
  1) BAR_RANKING de solicita_tc_enviada por network
     - Dataset: totales_por_network (usar directamente)
     - Highcharts: type="bar", xAxis.categories=[networks], series.data=[solicita_tc_enviada por network]
     - Ordenar descendente por solicita_tc_enviada
  2) DONUT_SHARE de inversión por network
     - Dataset: totales_por_network
     - Highcharts: type="pie", innerSize="50%", series.data=[{name: network, y: inversión}]

INSIGHTS OBLIGATORIOS:
  - Identificar network con mayor solicita_tc_enviada y mencionar su CPA
  - Comparar eficiencia (cpa_solicita_tc_enviada) entre networks
  - Calcular % de participación: solicita_tc_enviada del top network / total
  - Mencionar cuántos networks tienen datos

BLOQUE: cvr_indices
--------------------
OBJETIVO: Visualizar tasas de conversión del funnel y identificar caídas
DATASETS A USAR:
  - funnel_etapas (para el FUNNEL_CHART, tiene 2 etapas y CVR calculado)
  - serie_diaria_por_network (para evolución temporal, agregar por fecha)
  - totales_por_network (para comparar CVR entre networks)
GRÁFICOS OBLIGATORIOS (2 gráficos):
  1) FUNNEL_CHART mostrando: visita_landing → solicita_tc_enviada
     - Dataset: funnel_etapas (usar campos visita_landing, solicita_tc_enviada)
     - Highcharts: type="funnel", data format: [["Visita Landing", valor], ["Solicita TC Enviada", valor]]
     - IMPORTANTE: Formato de data DEBE ser array de arrays, NO objetos con name
     - Incluir plotOptions básicas: dataLabels enabled, center, neckWidth, neckHeight
  2) LINE_TIME_SERIES de totales_por_network mostrando evolución de CVR por network
     - Dataset: totales_por_network (usar network como categoría y cvr_landing_enviada como valor)
     - Highcharts: type="bar" 

INSIGHTS OBLIGATORIOS:
  - Usar cvr_landing_enviada de funnel_etapas para el CVR global del período
  - Calcular % de caída: (1 - cvr_landing_enviada) * 100
  - Mencionar: "De cada 100 visitas al landing, X completan la solicitud de TC"
  - Comparar CVR entre networks si hay datos en totales_por_network

BLOQUE: evolucion_conversiones
-------------------------------
OBJETIVO: Mostrar tendencia temporal de conversiones (solicita_tc_enviada y visita_landing)
DATASET A USAR: serie_diaria_por_network (agregar por fecha para obtener totales diarios)

GRÁFICOS OBLIGATORIOS (mínimo 1, máximo 2):
  1) LINE_TIME_SERIES de solicita_tc_enviada diario (OBLIGATORIO)
     - Dataset: serie_diaria_por_network (agrupar por fecha, sumar solicita_tc_enviada)
     - Highcharts: type="line", xAxis.type="datetime"
  2) LINE_TIME_SERIES de visita_landing diario (OBLIGATORIO en el mismo chart o separado)
     - Dataset: serie_diaria_por_network (agrupar por fecha, sumar visita_landing)

INSIGHTS OBLIGATORIOS:
  - Identificar fecha con pico máximo de solicita_tc_enviada
  - Identificar fecha con mínimo solicita_tc_enviada
  - Calcular tendencia: comparar promedio de primeros 7 días vs últimos 7 días del período
  - Mencionar días totales con datos

BLOQUE: resultados_generales
-----------------------------
OBJETIVO: Overview general del período con KPIs clave y tendencia
DATASETS A USAR:
  - totales_globales_periodo (para KPI_CARD en narrative, incluye pacing)
  - serie_diaria_por_network (para gráficos de tendencia diaria)

CONTENIDO OBLIGATORIO:
  1) KPI_CARD en narrativa (incluir en narrative):
     - Mostrar: Inversión total, Presupuesto, Pacing %, Solicitudes TC total, Visitas Landing total, CPA_solicita_tc_enviada
     - Formato: "En el período se invirtieron $X de un presupuesto de $Y (Z% pacing), generando N solicitudes de TC a un CPA de $W"

  2) COMBO_BAR_LINE_DUAL o 2 LINE_TIME_SERIES separados:
     - Barras=solicita_tc_enviada diario, Línea=cpa_solicita_tc_enviada diario
     - Dataset: serie_diaria_por_network (agrupar por fecha)

INSIGHTS OBLIGATORIOS:
  - Mencionar pacing_porcentaje: si está por encima o por debajo del esperado para el período
  - Identificar día con mejor CPA de solicitud TC
  - Identificar día con peor CPA de solicitud TC
  - Comparar inversión total vs presupuesto

BLOQUE: proyecciones
---------------------
OBJETIVO: Mostrar evolución semanal comparativa (NO calcular forecast futuro)
DATASET A USAR: serie_diaria_por_network (agrupar por fecha, luego por semana)

GRÁFICOS OBLIGATORIOS (1 gráfico):
  1) COLUMN_CHART de comparación semanal (últimas 4 semanas)
     - Agrupar serie_diaria_por_network por fecha, luego en bloques de 7 días
     - 2 series: solicita_tc_enviada promedio por semana + CPA promedio ponderado
     - Usar doble eje Y

INSIGHTS OBLIGATORIOS:
  - Comparar Semana 4 vs Semana 1
  - Mencionar EXPLÍCITAMENTE: "Basado en tendencia histórica semanal. NO se proyecta valor futuro"
  - Indicar si tendencia es: "mejora sostenida", "volatilidad sin patrón", o "deterioro progresivo"

PROHIBIDO:
  - NO calcular proyecciones futuras ni forecast
  - NO inventar valores para fechas futuras

BLOQUE: resumen_ejecutivo
--------------------------
OBJETIVO: Síntesis de alto nivel para stakeholders
GRÁFICOS OBLIGATORIOS (máximo 2):
  1) BAR_RANKING de top 5 campañas por solicita_tc_enviada
     - Dataset: top_campanas_mes (tomar top 5)
     - Highcharts: type="bar"
  2) LINE_TIME_SERIES de inversión diaria + solicita_tc_enviada diario
     - Dataset: serie_diaria_por_network (agrupar por fecha)
     - IMPORTANTE: Normalizar escalas o usar 2 ejes Y
INSIGHTS OBLIGATORIOS:
  - Mencionar campaña más exitosa (nombre + solicita_tc_enviada + CPA)
  - Mencionar campaña menos eficiente
  - Resumen ejecutivo: "Inversión total $X generó Y solicitudes TC a un CPA de $Z"

BLOQUE: aprendizajes
---------------------
OBJETIVO: Comparar performance entre Networks/plataformas
GRÁFICOS SUGERIDOS (1-2):
  1) BAR_RANKING de cpa_solicita_tc_enviada por Network
     - Dataset: top_campanas_mes (agrupar por network, calcular CPA promedio ponderado)
  2) COLUMN_CHART de solicita_tc_enviada por Network
     - Dataset: top_campanas_mes (agrupar por network, sumar solicita_tc_enviada)
INSIGHTS OBLIGATORIOS:
  - Comparar networks en términos de CPA y volumen de solicitudes
  - Identificar plataforma más eficiente y recomendar ajuste de budget
""".strip()


class BancoBctAnalyticsProvider(AnalyticsProvider):
    """
    Analytics provider for Banco BCT.

    Microservice: bancobct-dashboard-data
    Funnel: Visita Landing → Solicita TC Enviada
    Datasets: totales_globales_periodo, totales_por_network,
              serie_diaria_por_network, funnel_etapas,
              top_campanas_mes
    """

    @property
    def service_url(self) -> str:
        return os.getenv(
            "BANCOBCT_ANALYTICS_SERVICE_URL",
            "https://bancobct-dashboard-data-715418856987.us-central1.run.app",
        )

    @property
    def analytics_explanation(self) -> str:
        return BANCO_BCT_EXPLANATION
