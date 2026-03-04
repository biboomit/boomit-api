import os

from app.services.analytics_providers.base import AnalyticsProvider


BANCO_BCT_EXPLANATION = """
FORMATO DE analytics_data:
- dataset: uno de ["totales_globales_periodo", "totales_por_network", "serie_diaria_por_network", "serie_diaria_agregada", "funnel_etapas", "top_campanas_mes"].
  * totales_globales_periodo: 1 fila con métricas agregadas del rango completo, incluye presupuesto y pacing.
  * totales_por_network: filas con totales por network (plataforma publicitaria).
  * serie_diaria_por_network: filas con métricas diarias desglosadas por network y fecha (SIN CPA pre-calculado).
  * serie_diaria_agregada: filas con métricas diarias TOTALES (sumadas across all networks) por fecha, CON CPA y CVR pre-calculados. Usar este dataset para análisis de tendencia diaria de CPA y CVR.
  * funnel_etapas: 1 fila con las 2 etapas del funnel (visita_landing, solicita_tc_enviada, cvr_landing_enviada).
  * top_campanas_mes: hasta top_n campañas rankeadas por solicita_tc_enviada (luego inversión).

- Campos comunes: inversion, visita_landing, solicita_tc_enviada, cpa_visita_landing, cpa_solicita_tc_enviada, cvr_landing_enviada.
- Campos específicos por dataset:
  * totales_globales_periodo: incluye presupuesto, pacing_porcentaje
  * serie_diaria_por_network: incluye campo "fecha" (DATE) y "network". NO tiene CPA pre-calculado.
  * serie_diaria_agregada: incluye campo "fecha" (DATE), cpa_visita_landing, cpa_solicita_tc_enviada, cvr_landing_enviada. Ya está agregado por fecha (todos los networks sumados).
  * top_campanas_mes: incluye nombre_campana, network
  * totales_por_network: incluye network
  * funnel_etapas: incluye visita_landing, solicita_tc_enviada, cvr_landing_enviada

- NOTA: Este proveedor NO tiene datos de región/país ni sistema operativo.
  La dimensión principal de segmentación es "network" (plataforma publicitaria).
- NOTA: No existe dataset "serie_diaria_top".
  Para series temporales por network, usar "serie_diaria_por_network".
  Para series temporales TOTALES con CPA/CVR pre-calculado, usar "serie_diaria_agregada".
- NOTA SEMÁNTICA CPA: "Mejor CPA" = valor MÁS BAJO (adquisición más barata). "Peor CPA" = valor MÁS ALTO (adquisición más cara). NUNCA invertir esta lógica.
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
  - serie_diaria_agregada (para gráficos de tendencia diaria — YA tiene CPA pre-calculado por día)

CONTENIDO OBLIGATORIO:
  1) KPI_CARD en narrativa (incluir en narrative):
     - Mostrar: Inversión total, Presupuesto, Pacing %, Solicitudes TC total, Visitas Landing total, CPA_solicita_tc_enviada
     - Formato: "En el período se invirtieron $X de un presupuesto de $Y (Z% pacing), generando N solicitudes de TC a un CPA de $W"

  2) COMBO_BAR_LINE_DUAL o 2 LINE_TIME_SERIES separados:
     - Barras=solicita_tc_enviada diario, Línea=cpa_solicita_tc_enviada diario
     - Dataset: serie_diaria_agregada (usar DIRECTAMENTE los campos fecha, solicita_tc_enviada, cpa_solicita_tc_enviada)
     - IMPORTANTE: El CPA diario ya está pre-calculado en serie_diaria_agregada. NO recalcules manualmente.
     - IMPORTANTE: Cada valor de cpa_solicita_tc_enviada en serie_diaria_agregada es el CPA PUNTUAL de ese día
       (inversión del día / solicitudes del día), NO un acumulado.
     - PROHIBIDO: NO calcules CPA acumulado, running average, media móvil ni suavizado.
       Los valores de cpa_solicita_tc_enviada de serie_diaria_agregada deben usarse TAL CUAL en la serie del gráfico.
       Si el gráfico muestra [2.53, 2.51, 1.66, 1.45, 1.91, 1.13, 2.46, 16.95, 2.44, 2.31], esos son los valores correctos.
       NO los reemplaces por una serie suavizada como [1.94, 1.82, 2.0, 2.08, ...].

INSIGHTS OBLIGATORIOS:
  - Mencionar pacing_porcentaje: si está por encima o por debajo del esperado para el período
  - Identificar día con MEJOR CPA de solicitud TC: "Mejor CPA" = el día con el valor MÁS BAJO de cpa_solicita_tc_enviada
    en serie_diaria_agregada (día más eficiente, adquisición más barata)
  - Identificar día con PEOR CPA de solicitud TC: "Peor CPA" = el día con el valor MÁS ALTO de cpa_solicita_tc_enviada
    en serie_diaria_agregada (día menos eficiente, adquisición más cara)
  - ADVERTENCIA: Días con muy pocas solicitudes (ej: 1-2) tendrán CPA extremo. Mencionarlo como contexto.
  - Comparar inversión total vs presupuesto

BLOQUE: proyecciones
---------------------
OBJETIVO: Mostrar evolución temporal comparativa (NO calcular forecast futuro)
DATASET A USAR: serie_diaria_agregada (ya tiene métricas diarias agregadas con CPA pre-calculado)

LÓGICA DE AGRUPACIÓN DINÁMICA (según días disponibles en data_window):
  - Si data_window tiene >= 21 días: agrupar en bloques de 7 días (semanas reales). Titular "Semana 1", "Semana 2", etc.
  - Si data_window tiene 14-20 días: agrupar en bloques de 7 días. Solo habrá 2-3 semanas. Titular según las semanas reales.
  - Si data_window tiene 7-13 días: dividir en 2 mitades iguales. Titular "Primera mitad" y "Segunda mitad".
  - Si data_window tiene < 7 días: NO generar gráfico semanal. Solo incluir insight textual con tendencia general.
  IMPORTANTE: El número de bloques/semanas DEBE corresponder a los días REALES en los datos.
  NUNCA generar más bloques de los que los datos soportan.

GRÁFICOS OBLIGATORIOS (1 gráfico, si hay >= 7 días):
  1) COLUMN_CHART de comparación por período
     - Agrupar serie_diaria_agregada según la lógica de arriba
     - 2 series: solicita_tc_enviada promedio por bloque + CPA promedio ponderado (sum inversión / sum solicitudes)
     - Usar doble eje Y
     - El título debe reflejar la agrupación real (ej: "Comparación Semanal" solo si hay semanas completas)

INSIGHTS OBLIGATORIOS:
  - Comparar último bloque vs primer bloque
  - Mencionar EXPLÍCITAMENTE: "Basado en tendencia histórica. NO se proyecta valor futuro"
  - Indicar si tendencia es: "mejora sostenida", "volatilidad sin patrón", o "deterioro progresivo"
  - Mencionar cuántos días de datos reales hay y cómo se agruparon

PROHIBIDO:
  - NO calcular proyecciones futuras ni forecast
  - NO inventar valores para fechas futuras
  - NO fabricar datos para completar semanas que no existen en los datos
  - NO mostrar 4 semanas si los datos tienen menos de 28 días

BLOQUE: resumen_ejecutivo
--------------------------
OBJETIVO: Síntesis de alto nivel para stakeholders
GRÁFICOS OBLIGATORIOS (máximo 2):
  1) BAR_RANKING de campañas por solicita_tc_enviada
     - Dataset: top_campanas_mes (usar TODAS las filas disponibles, hasta un máximo de 10)
     - Highcharts: type="bar"
     - TÍTULO DINÁMICO: Contar las filas reales en top_campanas_mes.
       Si hay N campañas, titular "Top N Campañas por Solicitudes de TC".
       Si las campañas listadas representan el 100% del total de solicitudes, titular
       "Campañas por Solicitudes de TC" (sin "Top N", porque son TODAS).
       NUNCA titular "Top 5" si solo hay 4 campañas.
  2) LINE_TIME_SERIES de inversión diaria + solicita_tc_enviada diario
     - Dataset: serie_diaria_agregada (usar directamente, ya viene agregado por fecha)
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

    @property
    def metrics_glossary(self) -> str:
        return (
            "\n**Glosario de Métricas de Marketing:**\n"
            "- **Inversión**: Gasto publicitario total (USD)\n"
            "- **Presupuesto**: Presupuesto máximo asignado para el período\n"
            "- **Pacing**: Porcentaje de ejecución del presupuesto = inversión / presupuesto\n"
            "- **Visita Landing**: Visitas a la landing page generadas por la campaña\n"
            "- **Solicita TC Enviada**: Solicitudes de tarjeta de crédito enviadas exitosamente - KPI crítico de conversión final\n"
            "- **CPA_visita_landing**: Costo por visita al landing = inversión / visita_landing\n"
            "- **CPA_solicita_tc_enviada**: Costo por solicitud de TC = inversión / solicita_tc_enviada (KPI crítico)\n"
            "- **CVR_landing_enviada**: Tasa de conversión = solicita_tc_enviada / visita_landing\n"
            "\n**Funnel de Conversión:** Inversión → Visita Landing → Solicita TC Enviada"
        )

    @property
    def metrics_glossary_compact(self) -> str:
        return (
            "\n**Métricas clave:**\n"
            "- Inversión: gasto publicitario (USD)\n"
            "- Presupuesto / Pacing: presupuesto asignado y % de ejecución\n"
            "- Visita Landing: visitas a la landing page\n"
            "- Solicita TC Enviada: solicitudes de TC enviadas (KPI crítico)\n"
            "- CPA_solicita_tc_enviada: costo por solicitud TC = inversión / solicita_tc_enviada\n"
            "- CVR_landing_enviada: tasa conversión = solicita_tc_enviada / visita_landing\n"
            "- Funnel: Inversión → Visita Landing → Solicita TC Enviada"
        )
