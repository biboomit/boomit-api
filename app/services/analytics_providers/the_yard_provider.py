import os

from app.services.analytics_providers.base import AnalyticsProvider


THE_YARD_EXPLANATION = """
FORMATO DE analytics_data:
- dataset: uno de ["totales_globales_periodo", "totales_por_network", "serie_diaria_agregada",
  "serie_diaria_por_network", "funnel_por_network", "top_campanas_mes", "serie_diaria_top"].

  * totales_globales_periodo: 1 fila con métricas agregadas del rango completo, incluye presupuesto,
    pacing, daily_spend_rate y spend_remaining.
  * totales_por_network: filas con totales por plataforma publicitaria (Network). KPIs pre-calculados.
    Ordenado por lead_sin_spam DESC.
  * serie_diaria_agregada: filas con métricas diarias TOTALES (todos los networks sumados) por fecha.
    CPAs y cvr_sesion_lead pre-calculados.
  * serie_diaria_por_network: filas con métricas diarias desglosadas por Network y fecha. SIN CPAs.
  * funnel_por_network: filas con las 4 etapas del funnel por Network (etapa_1_sesiones,
    etapa_2_lead_sin_spam, etapa_3_lead_scheduled, etapa_4_lead_complete) y CVRs.
  * top_campanas_mes: hasta top_n campañas rankeadas por lead_sin_spam (luego inversión).
    Incluye nombre_campana, Network, y todos los KPIs y métricas de engagement.
  * serie_diaria_top: serie diaria solo de las top_n campañas con cpa_lead_sin_spam y cvr_sesion_lead.

- Campos comunes: inversion, sesiones, lead_sin_spam, lead_scheduled, lead_complete,
  cpa_lead_sin_spam, cpa_lead_scheduled, cpa_lead_complete, cvr_sesion_lead, cvr_lead_scheduled,
  cvr_scheduled_complete.
- Campos específicos por dataset:
  * totales_globales_periodo: incluye presupuesto, pacing_porcentaje, daily_spend_rate,
    spend_remaining, usuarios_totales, impresiones, clicks, conversiones, boomit_cta_book_a_tour,
    boomit_cta_enviar_form, lead_typ, leads_total.
  * totales_por_network: incluye "Network", usuarios_totales, impresiones, clicks, conversiones,
    leads_total.
  * serie_diaria_agregada: incluye "fecha" (DATE). CPAs y cvr_sesion_lead ya pre-calculados por día.
    NO incluye cvr_lead_scheduled ni cvr_scheduled_complete (calcular si necesario desde los valores).
  * serie_diaria_por_network: incluye "fecha" (DATE), "Network". SIN CPAs pre-calculados.
  * funnel_por_network: incluye "Network", etapa_1_sesiones, etapa_2_lead_sin_spam,
    etapa_3_lead_scheduled, etapa_4_lead_complete, cvr_sesion_lead, cvr_lead_scheduled,
    cvr_scheduled_complete.
  * top_campanas_mes: incluye nombre_campana, Network, boomit_cta_book_a_tour, boomit_cta_enviar_form,
    lead_typ, leads_total, cpa_lead_sin_spam, cpa_lead_scheduled, cpa_lead_complete,
    cvr_sesion_lead, cvr_lead_scheduled, cvr_scheduled_complete.
  * serie_diaria_top: incluye "fecha" (DATE), nombre_campana, Network, cpa_lead_sin_spam,
    cvr_sesion_lead.

- DIMENSIÓN PRINCIPAL DE SEGMENTACIÓN: "Network" (plataforma publicitaria).
  No hay segmentación por país ni OS — el análisis por "región" se hace via Network.
- FILTROS APLICADOS: solo flag_location='General'. Excluye networks Organic, Others y chatgpt*.
- NOTA SEMÁNTICA CPA: "Mejor CPA" = valor MÁS BAJO. "Peor CPA" = valor MÁS ALTO. NUNCA invertir.
- Los KPIs (CPA/CVR) serán NULL si el denominador es 0; NO los trates como 0.
- Etapa crítica del funnel: cvr_scheduled_complete (Scheduled → Tour Complete) es generalmente
  la más restrictiva. lead_complete (Tour Complete) es el KPI final de negocio.

DICCIONARIO DE DATOS:
- fecha: día del dato.
- nombre_campana: nombre de la campaña publicitaria.
- Network: plataforma publicitaria (Google Ads, Meta, TikTok, etc.).
- inversion: gasto publicitario total.
- presupuesto: presupuesto máximo asignado.
- sesiones: sesiones registradas — inicio útil del funnel de leads.
- usuarios_totales: usuarios totales registrados.
- impresiones: impresiones servidas por la campaña.
- clicks: clics generados.
- conversiones: conversiones registradas por plataforma.
- boomit_cta_book_a_tour: clics en CTA "Book a Tour" (intención de agendar visita).
- boomit_cta_enviar_form: clics en CTA "Enviar Formulario" (intención de contacto).
- lead_typ: leads thank-you-page (confirmación de formulario enviado).
- leads_total: total de leads brutos (incluye spam).
- lead_sin_spam: leads filtrados sin SPAM — etapa 2 del funnel, primer KPI de calidad.
- lead_scheduled: leads que agendaron una visita (Tour Scheduled o Contacted) — etapa 3.
- lead_complete: leads que completaron el tour (Tour Complete) — etapa 4, KPI FINAL CRÍTICO.
- cpa_lead_sin_spam = inversion / lead_sin_spam.
- cpa_lead_scheduled = inversion / lead_scheduled.
- cpa_lead_complete = inversion / lead_complete (KPI FINAL CRÍTICO).
- cvr_sesion_lead = lead_sin_spam / sesiones.
- cvr_lead_scheduled = lead_scheduled / lead_sin_spam.
- cvr_scheduled_complete = lead_complete / lead_scheduled (etapa más restrictiva del funnel).
- pacing_porcentaje = inversion / presupuesto.
- daily_spend_rate = inversion / días distintos del período.
- spend_remaining = presupuesto - inversion.
Funnel: Inversión → Sesiones → Lead Sin SPAM → Lead Scheduled → Lead Complete (Tour Complete).
CPA_lead_complete es el KPI final crítico de negocio.

REGLAS POR BLOQUE (OBLIGATORIO - MÁXIMA PRIORIDAD):

Estas instrucciones ESPECÍFICAS por bloque tienen PRIORIDAD ABSOLUTA sobre todas las demás reglas.
Cada bloque problemático DEBE incluir los gráficos especificados a continuación.

BLOQUE: analisis_region
-----------------------
NOTA: Este proveedor NO tiene datos por región geográfica ni OS. Usar "Network" como dimensión.
OBJETIVO: Mostrar performance por plataforma publicitaria (Network)
DATASET A USAR: totales_por_network (YA viene pre-agregado por Network, NO necesitas agrupar)

GRÁFICOS OBLIGATORIOS (elegir 2):
  1) BAR_RANKING de lead_sin_spam por Network
     - Dataset: totales_por_network (usar directamente)
     - Highcharts: type="bar", xAxis.categories=[networks], series.data=[lead_sin_spam por network]
     - Ordenar descendente por lead_sin_spam (el dataset ya viene ordenado)
  2) DONUT_SHARE de inversión por Network
     - Dataset: totales_por_network
     - Highcharts: type="pie", innerSize="50%", series.data=[{name: Network, y: inversión}]

INSIGHTS OBLIGATORIOS:
  - Identificar Network con mayor lead_sin_spam y mencionar su cpa_lead_sin_spam y cpa_lead_complete
  - Comparar eficiencia (cpa_lead_complete) entre Networks
  - Calcular % de participación: lead_sin_spam del top Network / total de totales_globales_periodo
  - Mencionar cuántos Networks tienen datos (contar filas de totales_por_network)

BLOQUE: cvr_indices
--------------------
OBJETIVO: Visualizar tasas de conversión del funnel de leads por Network
DATASETS A USAR:
  - funnel_por_network (para FUNNEL_CHART y CVRs por Network)
  - totales_globales_periodo (para CVRs globales del período)

GRÁFICOS OBLIGATORIOS (2 gráficos):
  1) FUNNEL_CHART mostrando: Sesiones → Lead Sin SPAM → Lead Scheduled → Lead Complete
     - Dataset: totales_globales_periodo (usar campos sesiones, lead_sin_spam, lead_scheduled,
       lead_complete)
     - Highcharts: type="funnel", data format: [["Sesiones", valor], ["Lead Sin SPAM", valor],
       ["Lead Scheduled", valor], ["Lead Complete", valor]]
     - IMPORTANTE: Formato de data DEBE ser array de arrays, NO objetos con name
     - Incluir plotOptions básicas: dataLabels enabled, center, neckWidth, neckHeight
  2) BAR_CHART de cvr_scheduled_complete por Network (etapa más restrictiva)
     - Dataset: funnel_por_network (usar campo cvr_scheduled_complete por Network)
     - Highcharts: type="bar", xAxis.categories=[networks], series.data=[cvr_scheduled_complete]
     - ALTERNATIVA: Usar cvr_lead_scheduled si cvr_scheduled_complete tiene muchos NULLs

INSIGHTS OBLIGATORIOS:
  - Identificar la etapa con mayor caída: comparar cvr_sesion_lead, cvr_lead_scheduled,
    cvr_scheduled_complete de totales_globales_periodo
  - Mencionar: "De cada 100 sesiones, X se convierten en lead, Y agendan y solo Z completan el tour"
  - Comparar CVR entre Networks usando funnel_por_network (qué plataforma genera leads de mayor calidad)
  - Calcular % de caída en cada etapa: (1 - CVR) * 100
  - Destacar diferencia entre boomit_cta_book_a_tour y lead_sin_spam (intención vs lead real)

BLOQUE: evolucion_conversiones
-------------------------------
OBJETIVO: Mostrar tendencia temporal de leads y engagement
DATASET A USAR: serie_diaria_agregada (YA tiene totales diarios globales, CPAs pre-calculados)

GRÁFICOS OBLIGATORIOS (mínimo 1, máximo 2):
  1) LINE_TIME_SERIES de lead_sin_spam diario (OBLIGATORIO)
     - Dataset: serie_diaria_agregada (usar campo lead_sin_spam por fecha directamente)
     - Highcharts: type="line", xAxis.type="datetime"
  2) LINE_TIME_SERIES de lead_scheduled y lead_complete diarios (comparar etapas avanzadas)
     - Dataset: serie_diaria_agregada
     - Highcharts: type="line", 2 series en el mismo gráfico
     - Escalar apropiadamente si los volúmenes difieren mucho

INSIGHTS OBLIGATORIOS:
  - Identificar fecha con pico máximo de lead_sin_spam
  - Identificar fecha con mínimo lead_sin_spam (excluir días con valor=0)
  - Calcular tendencia: comparar promedio primeros 7 días vs últimos 7 días del período
  - Mencionar días totales con datos (contar filas de serie_diaria_agregada)

BLOQUE: resultados_generales
-----------------------------
OBJETIVO: Overview general del período con KPIs clave, pacing y tendencia diaria
DATASETS A USAR:
  - totales_globales_periodo (para KPI_CARD en narrative, incluye pacing y budget metrics)
  - serie_diaria_agregada (para gráficos de tendencia diaria — CPA pre-calculado)

CONTENIDO OBLIGATORIO:
  1) KPI_CARD en narrativa (incluir en narrative):
     - Mostrar: Inversión total, Presupuesto, Pacing %, Lead Sin SPAM total,
       Lead Scheduled total, Lead Complete total, CPA_lead_complete global
     - También mostrar: daily_spend_rate, spend_remaining, boomit_cta_book_a_tour total
     - Formato: "En el período se invirtieron $X de un presupuesto de $Y (Z% pacing),
       generando N leads sin spam, M agendados y K tours completos a un CPA de $W"

  2) COMBO_BAR_LINE_DUAL o 2 LINE_TIME_SERIES separados:
     - Barras=lead_sin_spam diario, Línea=cpa_lead_sin_spam diario
     - Dataset: serie_diaria_agregada (usar DIRECTAMENTE fecha, lead_sin_spam, cpa_lead_sin_spam)
     - IMPORTANTE: CPA diario ya pre-calculado. NO recalcular manualmente.
     - PROHIBIDO: NO calcules CPA acumulado, running average ni suavizado.

INSIGHTS OBLIGATORIOS:
  - Mencionar pacing_porcentaje: si está por encima/debajo del esperado
  - Mencionar spend_remaining y daily_spend_rate para contextualizar el ritmo de gasto
  - Identificar día con MEJOR cpa_lead_sin_spam (valor más bajo en serie_diaria_agregada)
  - Identificar día con PEOR cpa_lead_sin_spam (valor más alto en serie_diaria_agregada)
  - ADVERTENCIA: Días con muy pocos leads (ej: 1-2) tendrán CPA extremo. Mencionarlo.
  - Relacionar boomit_cta_book_a_tour con lead_sin_spam: medir eficiencia de CTA vs lead real

BLOQUE: proyecciones
---------------------
OBJETIVO: Mostrar evolución temporal comparativa (NO calcular forecast futuro)
DATASET A USAR: serie_diaria_agregada (métricas diarias agregadas con CPA pre-calculado)

LÓGICA DE AGRUPACIÓN DINÁMICA (según días disponibles en data_window):
  - Si data_window tiene >= 21 días: agrupar en bloques de 7 días. Titular "Semana 1", etc.
  - Si data_window tiene 14-20 días: agrupar en bloques de 7 días. Solo 2-3 semanas.
  - Si data_window tiene 7-13 días: dividir en 2 mitades. Titular "Primera mitad" y "Segunda mitad".
  - Si data_window tiene < 7 días: NO generar gráfico. Solo insight textual con tendencia general.
  IMPORTANTE: Número de bloques DEBE corresponder a los días REALES en los datos.
  NUNCA generar más bloques de los que los datos soportan.

GRÁFICOS OBLIGATORIOS (1 gráfico, si hay >= 7 días):
  1) COLUMN_CHART de comparación por período
     - Agrupar serie_diaria_agregada según la lógica de arriba
     - 2 series: lead_sin_spam promedio por bloque + CPA promedio ponderado
       (sum inversion / sum lead_sin_spam)
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
  1) BAR_RANKING de campañas por lead_sin_spam
     - Dataset: top_campanas_mes (usar TODAS las filas disponibles, hasta un máximo de 10)
     - Highcharts: type="bar"
     - TÍTULO DINÁMICO: Si hay N campañas, titular "Top N Campañas por Lead Sin SPAM".
       NUNCA titular "Top 5" si solo hay 4 campañas.
  2) LINE_TIME_SERIES de inversión diaria + lead_sin_spam diario
     - Dataset: serie_diaria_agregada (usar directamente, ya viene agregado por fecha)
     - IMPORTANTE: Normalizar escalas o usar 2 ejes Y
INSIGHTS OBLIGATORIOS:
  - Mencionar campaña más exitosa (nombre + lead_sin_spam + cpa_lead_complete + Network)
  - Mencionar campaña menos eficiente (alto cpa_lead_sin_spam, pocos leads)
  - Resumen ejecutivo: "Inversión total $X generó Y leads sin spam, Z agendados y W tours completos
    a un CPA_complete de $C"
  - Relacionar boomit_cta_book_a_tour con leads efectivos: "X intenciones de agendar → Y leads"

BLOQUE: aprendizajes
---------------------
OBJETIVO: Comparar performance entre Networks y calidad del funnel
GRÁFICOS SUGERIDOS (1-2):
  1) BAR_RANKING de cpa_lead_complete por Network
     - Dataset: totales_por_network (ranking directo de CPA_complete por Network)
     - Highcharts: type="bar", xAxis.categories=[networks], series.data=[cpa_lead_complete]
  2) COLUMN_CHART de las 3 etapas del funnel por Network
     - Dataset: funnel_por_network (mostrar lead_sin_spam, lead_scheduled, lead_complete por Network)
     - Highcharts: type="column", 3 series agrupadas
INSIGHTS OBLIGATORIOS:
  - Comparar Networks en términos de volumen de leads y CPA_complete
  - Identificar Network con mejor tasa de conversión Scheduled → Complete (cvr_scheduled_complete)
  - Analizar calidad vs cantidad: ¿el Network con más leads tiene mejor CVR o CPA?
  - Mencionar si boomit_cta_book_a_tour correlaciona con lead_complete en top_campanas_mes
  - Recomendar ajuste de budget hacia Network con mejor CPA_complete
""".strip()


class TheYardAnalyticsProvider(AnalyticsProvider):
    """
    Analytics provider for The Yard.

    Microservice: the-yard-dashboard-data
    Funnel: Sesiones → Lead Sin SPAM → Lead Scheduled → Lead Complete (Tour Complete)
    Primary segmentation: Network (advertising platform)
    Filters: flag_location='General', excludes Organic/Others/chatgpt* networks
    Datasets: totales_globales_periodo, totales_por_network, serie_diaria_agregada,
              serie_diaria_por_network, funnel_por_network, top_campanas_mes, serie_diaria_top
    """

    @property
    def service_url(self) -> str:
        return os.getenv(
            "THE_YARD_ANALYTICS_SERVICE_URL",
            "https://the-yard-dashboard-data-715418856987.us-central1.run.app",
        )

    @property
    def analytics_explanation(self) -> str:
        return THE_YARD_EXPLANATION

    @property
    def metrics_glossary(self) -> str:
        return (
            "\n**Glosario de Métricas de Marketing:**\n"
            "- **Inversión**: Gasto publicitario total (USD)\n"
            "- **Presupuesto**: Presupuesto máximo asignado para el período\n"
            "- **Pacing**: Porcentaje de ejecución del presupuesto = inversión / presupuesto\n"
            "- **Daily Spend Rate**: Ritmo de gasto diario = inversión / días del período\n"
            "- **Spend Remaining**: Presupuesto no ejecutado = presupuesto - inversión\n"
            "- **Sesiones**: Sesiones registradas — inicio del funnel de leads\n"
            "- **Boomit CTA Book a Tour**: Clics en el CTA de agendar visita (intención, no lead)\n"
            "- **Boomit CTA Enviar Form**: Clics en CTA de envío de formulario\n"
            "- **Lead Sin SPAM**: Leads filtrados sin spam — primer KPI de calidad de lead\n"
            "- **Lead Scheduled**: Leads que agendaron una visita o fueron contactados — etapa 3\n"
            "- **Lead Complete**: Leads que completaron el tour (Tour Complete) — KPI FINAL CRÍTICO\n"
            "- **CPA_lead_sin_spam**: Costo por lead sin spam = inversión / lead_sin_spam\n"
            "- **CPA_lead_scheduled**: Costo por lead agendado = inversión / lead_scheduled\n"
            "- **CPA_lead_complete**: Costo por tour completo = inversión / lead_complete (KPI FINAL)\n"
            "- **CVR_sesion_lead**: Tasa sesiones → lead sin spam\n"
            "- **CVR_lead_scheduled**: Tasa lead sin spam → lead scheduled\n"
            "- **CVR_scheduled_complete**: Tasa lead scheduled → tour complete (etapa más restrictiva)\n"
            "- **Network**: Plataforma publicitaria — dimensión principal de segmentación\n"
            "\n**Funnel de Conversión:** Inversión → Sesiones → Lead Sin SPAM → Lead Scheduled → Lead Complete"
        )

    @property
    def metrics_glossary_compact(self) -> str:
        return (
            "\n**Métricas clave:**\n"
            "- Inversión: gasto publicitario (USD)\n"
            "- Presupuesto / Pacing: presupuesto asignado y % de ejecución\n"
            "- Daily Spend Rate: ritmo de gasto diario\n"
            "- Spend Remaining: presupuesto no ejecutado\n"
            "- Lead Sin SPAM: leads filtrados sin spam (primer KPI de calidad)\n"
            "- Lead Scheduled: leads que agendaron visita (etapa 3)\n"
            "- Lead Complete: tours completados (KPI FINAL)\n"
            "- CPA_lead_complete: costo por tour completo = inversión / lead_complete\n"
            "- CVR_scheduled_complete: tasa scheduled → complete (etapa más restrictiva)\n"
            "- Network: segmentación principal (plataforma publicitaria)\n"
            "- Funnel: Inversión → Sesiones → Lead Sin SPAM → Lead Scheduled → Lead Complete"
        )
