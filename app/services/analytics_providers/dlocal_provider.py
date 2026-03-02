import os

from app.services.analytics_providers.base import AnalyticsProvider


DLOCAL_EXPLANATION = """
FORMATO DE analytics_data:
- dataset: uno de ["totales_globales_periodo",
  "serie_diaria_agregada", "funnel_por_etapa",
  "top_campanas_mes", "serie_diaria_top"].

  * totales_globales_periodo: 1 fila con métricas agregadas del rango completo, incluye presupuesto,
    pacing, daily_spend_rate y spend_remaining.
  * serie_diaria_agregada: filas con métricas diarias TOTALES (todos los networks sumados)
    por fecha. CPAs y CVRs pre-calculados.
  * funnel_por_etapa: 3 filas, una por cada etapa del funnel (Usuarios Totales, Users Click Contact
    Sales, Contact Sales Submission). Campos: etapa, orden, valor, cvr_desde_anterior.
    Ordenado por orden (1→2→3). cvr_desde_anterior es NULL para la etapa 1.
  * top_campanas_mes: hasta top_n campañas rankeadas por contact_sales_submission (luego inversión).
    Incluye nombre_campana, pais, network, estrategia, flag_payin_payout (informativo), y KPIs.
  * serie_diaria_top: serie diaria solo de las top_n campañas con CPAs y CVRs pre-calculados.

- Campos comunes: inversion, usuarios_totales, users_click_contact_sales, contact_sales_submission,
  cpa_click_contact_sales, cpa_submission, cvr_users_click, cvr_click_submission.
- Campos específicos por dataset:
  * totales_globales_periodo: incluye presupuesto, pacing_porcentaje, daily_spend_rate, spend_remaining,
    costo_gads, costo_linkedin, costo_bing, sesiones.
  * serie_diaria_agregada: incluye "fecha" (DATE). CPAs y CVRs ya pre-calculados por día.
  * funnel_por_etapa: incluye "etapa" (nombre de la etapa), "orden" (1, 2 o 3),
    "valor" (volumen de esa etapa), "cvr_desde_anterior" (tasa de conversión desde la etapa previa, NULL para etapa 1).
  * top_campanas_mes: incluye nombre_campana, pais, network, estrategia, flag_payin_payout,
    cpa_click_contact_sales, cpa_submission, cvr_users_click, cvr_click_submission.
  * serie_diaria_top: incluye "fecha" (DATE), nombre_campana, pais, network, estrategia,
    cpa_click_contact_sales, cpa_submission, cvr_users_click, cvr_click_submission.

- DIMENSIÓN PRINCIPAL DE SEGMENTACIÓN: "network" (Google Ads, Meta, TikTok Ads).
  FILTROS FIJOS: estrategia = 'Others', flag_payin_payout = 'Others', pais = 'United States'.
  Estas 3 dimensiones están pre-filtradas a un único valor cada una — no hay desglose por ellas.
- NOTA SEMÁNTICA CPA: "Mejor CPA" = valor MÁS BAJO. "Peor CPA" = valor MÁS ALTO. NUNCA invertir.
- Los KPIs (CPA/CVR) serán NULL si el denominador es 0; NO los trates como 0.
- Filtrado previo: network filtrado a ('Google Ads', 'Meta', 'TikTok Ads'). estrategia filtrado a 'Others' (valor único fijo).
  flag_payin_payout filtrado a 'Others'. Solo incluye datos de United States (filtro geográfico fijo).
  Requiere al menos una señal
  (inversion > 0 OR usuarios_totales > 0 OR contact_sales_submission > 0).

DICCIONARIO DE DATOS:
- fecha: día del dato.
- nombre_campana: nombre de la campaña publicitaria.
- pais: país de la campaña (FILTRADO FIJO a United States — todos los registros son de US).
- network: plataforma publicitaria (Google Ads, Meta, TikTok Ads). Filtrado a estos 3 valores.
- estrategia: clasificación estratégica interna de la campaña (FILTRADO FIJO a 'Others' — todos los registros tienen este valor).
- flag_payin_payout: indicador Payin/Payout/Handbook (FILTRADO FIJO a 'Others' — todos los registros tienen este valor).
- inversion: gasto publicitario total (costo_gads + costo_linkedin + costo_bing).
- costo_gads: inversión en Google Ads.
- costo_linkedin: inversión en LinkedIn Ads.
- costo_bing: inversión en Bing Ads.
- presupuesto: presupuesto máximo asignado.
- sesiones: sesiones registradas en GA4.
- usuarios_totales: usuarios totales registrados en GA4 — etapa 1 del funnel.
- users_click_contact_sales: usuarios únicos que hicieron clic en Contact Sales — etapa 2 del funnel.
- contact_sales_submission: formularios enviados desde Contact Sales — etapa 3, KPI FINAL CRÍTICO.
- click_contact_sales: clics totales (no usuarios únicos) en Contact Sales.
- users_click_contact_sales_sub: usuarios únicos que enviaron el formulario Contact Sales.
- cpa_click_contact_sales = inversion / users_click_contact_sales.
- cpa_submission = inversion / contact_sales_submission (KPI FINAL CRÍTICO).
- cvr_users_click = users_click_contact_sales / usuarios_totales.
- cvr_click_submission = contact_sales_submission / users_click_contact_sales.
- pacing_porcentaje = inversion / presupuesto.
- daily_spend_rate = inversion / días distintos del período.
- spend_remaining = presupuesto - inversion (presupuesto no ejecutado).
Funnel: Inversión → Usuarios Totales → Users Click Contact Sales → Contact Sales Submission.
CPA_submission es el KPI final crítico.

REGLAS POR BLOQUE (OBLIGATORIO - MÁXIMA PRIORIDAD):

Estas instrucciones ESPECÍFICAS por bloque tienen PRIORIDAD ABSOLUTA sobre todas las demás reglas.
Cada bloque problemático DEBE incluir los gráficos especificados a continuación.

BLOQUE: analisis_region
-----------------------
OBJETIVO: Mostrar performance por network — dimensión principal de segmentación en Dlocal US
NOTA: Todos los datos son de United States, estrategia='Others' (filtros fijos). El desglose relevante es por network.
DATASET A USAR: top_campanas_mes (agrupar por network para obtener métricas por plataforma)

GRÁFICOS OBLIGATORIOS (elegir 2):
  1) BAR_RANKING de contact_sales_submission por network
     - Dataset: top_campanas_mes (agrupar por network, sumar contact_sales_submission)
     - Highcharts: type="bar", xAxis.categories=[networks], series.data=[submissions por network]
  2) DONUT_SHARE de inversión por network
     - Dataset: top_campanas_mes (agrupar por network, sumar inversion)
     - Highcharts: type="pie", innerSize="50%", series.data=[{name: network, y: inversión}]

INSIGHTS OBLIGATORIOS:
  - Comparar Google Ads vs Meta vs TikTok Ads en volumen de submissions e inversión
  - Identificar qué network tiene mejor CPA (menor cpa_submission)
  - Calcular % de participación de cada network en el total de submissions
  - Mencionar que los datos corresponden exclusivamente a United States, estrategia='Others'

BLOQUE: cvr_indices
--------------------
OBJETIVO: Visualizar tasas de conversión del funnel por etapa
DATASETS A USAR:
  - funnel_por_etapa (3 filas: una por etapa del funnel, con volumen y CVR desde etapa anterior)
  - totales_globales_periodo (para CVRs globales del período)

GRÁFICOS OBLIGATORIOS (2 gráficos):
  1) FUNNEL_CHART mostrando: Usuarios Totales → Click Contact Sales → Contact Sales Submission
     - Dataset: funnel_por_etapa (usar directamente: data = filas ordenadas por "orden",
       format: [[etapa, valor], [etapa, valor], [etapa, valor]])
     - Highcharts: type="funnel", data format: [["Usuarios Totales", valor],
       ["Click Contact Sales", valor], ["Contact Sales Submission", valor]]
     - IMPORTANTE: Formato de data DEBE ser array de arrays, NO objetos con name
     - Incluir plotOptions básicas: dataLabels enabled, center, neckWidth, neckHeight
  2) BAR_CHART de cvr_desde_anterior por etapa (tasa de conversión de cada transición)
     - Dataset: funnel_por_etapa (usar filas con orden 2 y 3, que tienen cvr_desde_anterior)
     - Highcharts: type="bar", xAxis.categories=[etapa 2, etapa 3], series.data=[cvr_desde_anterior]

INSIGHTS OBLIGATORIOS:
  - Identificar la transición del funnel con mayor caída usando cvr_desde_anterior
  - Mencionar: "De cada 100 usuarios, X hacen clic en Contact Sales y solo Y envían la solicitud"
  - Calcular % de caída en cada transición: (1 - cvr_desde_anterior) * 100
  - Usar los valores directamente de funnel_por_etapa (ya pre-calculados)

BLOQUE: evolucion_conversiones
-------------------------------
OBJETIVO: Mostrar tendencia temporal de conversiones y engagement
DATASET A USAR: serie_diaria_agregada (YA tiene totales diarios globales, CON CVRs pre-calculados)

GRÁFICOS OBLIGATORIOS (mínimo 1, máximo 2):
  1) LINE_TIME_SERIES de contact_sales_submission diario (OBLIGATORIO)
     - Dataset: serie_diaria_agregada (usar campo contact_sales_submission por fecha directamente)
     - Highcharts: type="line", xAxis.type="datetime"
  2) LINE_TIME_SERIES de users_click_contact_sales y contact_sales_submission (comparar etapas)
     - Dataset: serie_diaria_agregada
     - Highcharts: type="line", 2 series en el mismo gráfico con doble eje Y si las magnitudes difieren

INSIGHTS OBLIGATORIOS:
  - Identificar fecha con pico máximo de contact_sales_submission
  - Identificar fecha con mínimo contact_sales_submission (excluir días con valor=0)
  - Calcular tendencia: comparar promedio primeros 7 días vs últimos 7 días del período
  - Mencionar días totales con datos (contar filas de serie_diaria_agregada)

BLOQUE: resultados_generales
-----------------------------
OBJETIVO: Overview general del período con KPIs clave, pacing y tendencia diaria
DATASETS A USAR:
  - totales_globales_periodo (para KPI_CARD en narrative, incluye pacing y budget metrics)
  - serie_diaria_agregada (para gráficos de tendencia diaria — CPA ya pre-calculado)

CONTENIDO OBLIGATORIO:
  1) KPI_CARD en narrativa (incluir en narrative):
     - Mostrar: Inversión total, Presupuesto, Pacing %, Contact Sales Submissions total,
       CPA_submission global, daily_spend_rate, spend_remaining
     - También mostrar desglose por plataforma: costo_gads, costo_linkedin, costo_bing
     - Formato: "En el período se invirtieron $X de un presupuesto de $Y (Z% pacing), generando
       N submissions a un CPA de $W. Rytmo diario: $D/día, restante: $R"

  2) COMBO_BAR_LINE_DUAL o 2 LINE_TIME_SERIES separados:
     - Barras=contact_sales_submission diario, Línea=cpa_submission diario
     - Dataset: serie_diaria_agregada (usar DIRECTAMENTE fecha, contact_sales_submission, cpa_submission)
     - IMPORTANTE: CPA diario ya pre-calculado. NO recalcular manualmente.
     - PROHIBIDO: NO calcules CPA acumulado, running average, ni suavizado.

INSIGHTS OBLIGATORIOS:
  - Mencionar pacing_porcentaje: si está por encima o por debajo del esperado para el período
  - Mencionar spend_remaining y daily_spend_rate para contextualizar el ritmo de gasto
  - Identificar día con MEJOR CPA_submission (valor más bajo en serie_diaria_agregada)
  - Identificar día con PEOR CPA_submission (valor más alto en serie_diaria_agregada)
  - ADVERTENCIA: Días con muy pocas submissions (ej: 1-2) tendrán CPA extremo. Mencionarlo.
  - Comparar inversión por plataforma (Google Ads vs Meta vs TikTok Ads) usando totales_globales_periodo

BLOQUE: proyecciones
---------------------
OBJETIVO: Mostrar evolución temporal comparativa (NO calcular forecast futuro)
DATASET A USAR: serie_diaria_agregada (métricas diarias agregadas con CPA pre-calculado)

LÓGICA DE AGRUPACIÓN DINÁMICA (según días disponibles en data_window):
  - Si data_window tiene >= 21 días: agrupar en bloques de 7 días. Titular "Semana 1", etc.
  - Si data_window tiene 14-20 días: agrupar en bloques de 7 días. Solo 2-3 semanas.
  - Si data_window tiene 7-13 días: dividir en 2 mitades. Titular "Primera mitad" y "Segunda mitad".
  - Si data_window tiene < 7 días: NO generar gráfico. Solo insight textual con tendencia general.
  IMPORTANTE: Número de bloques DEBE corresponder a los días REALES. NUNCA generar más bloques
  de los que los datos soportan.

GRÁFICOS OBLIGATORIOS (1 gráfico, si hay >= 7 días):
  1) COLUMN_CHART de comparación por período
     - Agrupar serie_diaria_agregada según la lógica de arriba
     - 2 series: contact_sales_submission promedio por bloque + CPA promedio ponderado
       (sum inversion / sum contact_sales_submission)
     - Usar doble eje Y
     - El título debe reflejar la agrupación real

INSIGHTS OBLIGATORIOS:
  - Comparar último bloque vs primer bloque
  - Mencionar EXPLÍCITAMENTE: "Basado en tendencia histórica. NO se proyecta valor futuro"
  - Indicar tendencia: "mejora sostenida", "volatilidad sin patrón", o "deterioro progresivo"
  - Mencionar cuántos días de datos reales hay y cómo se agruparon

PROHIBIDO:
  - NO calcular proyecciones futuras ni forecast
  - NO inventar valores para fechas futuras
  - NO fabricar datos para completar semanas inexistentes en los datos

BLOQUE: resumen_ejecutivo
--------------------------
OBJETIVO: Síntesis de alto nivel para stakeholders
GRÁFICOS OBLIGATORIOS (máximo 2):
  1) BAR_RANKING de campañas por contact_sales_submission
     - Dataset: top_campanas_mes (usar TODAS las filas disponibles, hasta un máximo de 10)
     - Highcharts: type="bar"
     - TÍTULO DINÁMICO: Si hay N campañas, titular "Top N Campañas por Contact Sales Submissions".
       NUNCA titular "Top 5" si solo hay 4 campañas.
  2) LINE_TIME_SERIES de inversión diaria + contact_sales_submission diario
     - Dataset: serie_diaria_agregada (usar directamente, ya viene agregado por fecha)
     - IMPORTANTE: Normalizar escalas o usar 2 ejes Y
INSIGHTS OBLIGATORIOS:
  - Mencionar campaña más exitosa (nombre + contact_sales_submission + cpa_submission + pais)
  - Mencionar campaña menos eficiente (alto cpa_submission, pocas submissions)
  - Resumen ejecutivo: "Inversión total $X generó Y submissions a un CPA de $Z"
  - Desglosar por network (cuál network generó más submissions)

BLOQUE: aprendizajes
---------------------
OBJETIVO: Comparar performance entre plataformas (network)
GRÁFICOS SUGERIDOS (1-2):
  1) BAR_RANKING de cpa_submission por network
     - Dataset: top_campanas_mes (agrupar por network, calcular CPA ponderado)
     - Highcharts: type="bar", xAxis.categories=[networks], series.data=[cpa_submission]
  2) COLUMN_CHART de contact_sales_submission por network
     - Dataset: top_campanas_mes (agrupar por network, sumar contact_sales_submission)
     - Highcharts: type="column"
INSIGHTS OBLIGATORIOS:
  - Comparar networks (Google Ads vs Meta vs TikTok Ads) en eficiencia (CPA) y volumen de submissions
  - Identificar network más eficiente usando top_campanas_mes
  - Comparar plataformas usando costo_gads/linkedin/bing de totales_globales_periodo
  - Recomendar ajuste de budget hacia network con mejor CPA
  - Recordar que todos los datos son de United States, estrategia='Others' (filtros fijos)
""".strip()


class DlocalAnalyticsProvider(AnalyticsProvider):
    """
    Analytics provider for Dlocal.

    Microservice: dlocal-dashboard-data
    Funnel: Usuarios Totales → Users Click Contact Sales → Contact Sales Submission
    Geographic filter: United States only (pre-filtered)
    Primary segmentation: network (Google Ads, Meta, TikTok Ads)
    Fixed filters: estrategia='Others', flag_payin_payout='Others', pais='United States'
    Networks: Google Ads, Meta, TikTok Ads
    Datasets: totales_globales_periodo,
              serie_diaria_agregada, funnel_por_etapa,
              top_campanas_mes, serie_diaria_top
    """

    @property
    def service_url(self) -> str:
        return os.getenv(
            "DLOCAL_ANALYTICS_SERVICE_URL",
            "https://dlocal-dashboard-data-715418856987.us-central1.run.app",
        )

    @property
    def analytics_explanation(self) -> str:
        return DLOCAL_EXPLANATION

    @property
    def metrics_glossary(self) -> str:
        return (
            "\n**Glosario de Métricas de Marketing:**\n"
            "- **Inversión**: Gasto publicitario total (Google Ads + Meta + TikTok Ads)\n"
            "- **Presupuesto**: Presupuesto máximo asignado para el período\n"
            "- **Pacing**: Porcentaje de ejecución del presupuesto = inversión / presupuesto\n"
            "- **Daily Spend Rate**: Ritmo de gasto diario = inversión / días del período\n"
            "- **Spend Remaining**: Presupuesto no ejecutado = presupuesto - inversión\n"
            "- **Usuarios Totales**: Usuarios registrados en GA4 — inicio del funnel\n"
            "- **Users Click Contact Sales**: Usuarios únicos que hicieron clic en Contact Sales — etapa 2\n"
            "- **Contact Sales Submission**: Formularios enviados desde Contact Sales — KPI FINAL CRÍTICO\n"
            "- **CPA_click_contact_sales**: Costo por clic en Contact Sales = inversión / users_click_contact_sales\n"
            "- **CPA_submission**: Costo por submission = inversión / contact_sales_submission (KPI FINAL)\n"
            "- **CVR_users_click**: Tasa conversión usuarios → clic = users_click_contact_sales / usuarios_totales\n"
            "- **CVR_click_submission**: Tasa conversión clic → submission = submission / users_click_contact_sales\n"
            "- **País**: Filtro fijo a United States (no hay desglose multi-país)\n"
            "- **Estrategia**: Filtro fijo a 'Others' (no hay desglose multi-estrategia)\n"
            "\n**Funnel de Conversión:** Inversión → Usuarios Totales → Click Contact Sales → Contact Sales Submission"
        )

    @property
    def metrics_glossary_compact(self) -> str:
        return (
            "\n**Métricas clave:**\n"
            "- Inversión: gasto total (Google Ads + Meta + TikTok Ads)\n"
            "- Presupuesto / Pacing: presupuesto asignado y % de ejecución\n"
            "- Daily Spend Rate: ritmo de gasto diario\n"
            "- Spend Remaining: presupuesto no ejecutado\n"
            "- Usuarios Totales: usuarios GA4 (inicio del funnel)\n"
            "- Users Click Contact Sales: usuarios únicos que clicaron en Contact Sales\n"
            "- Contact Sales Submission: formularios enviados (KPI FINAL)\n"
            "- CPA_submission: costo por submission = inversión / submission\n"
            "- CVR_click_submission: tasa clic → submission (etapa más restrictiva)\n"
            "- Segmentación: network (Google Ads / Meta / TikTok Ads), país fijo: US, estrategia fija: Others\n"
            "- Funnel: Inversión → Usuarios Totales → Click Contact Sales → Contact Sales Submission"
        )
