import os

from app.services.analytics_providers.base import AnalyticsProvider


FLEX_BCT_EXPLANATION = """
FORMATO DE analytics_data:
- dataset: uno de ["totales_globales_periodo", "totales_por_region", "serie_diaria_agregada", "funnel_etapas", "top_campanas_mes", "serie_diaria_top"].
  * totales_globales_periodo: 1 fila con métricas agregadas del rango completo, incluye presupuesto y pacing.
  * totales_por_region: filas con totales por país (Pais).
  * serie_diaria_agregada: filas con métricas diarias TOTALES (sumadas across all campañas/networks) por fecha, CON CPI y CVRs pre-calculados.
  * funnel_etapas: 1 fila con las 3 etapas del funnel (etapa_1_impresiones, etapa_2_clicks, etapa_3_instalaciones, cvr_impresion_click, cvr_click_install, cvr_impresion_install).
  * top_campanas_mes: hasta top_n campañas rankeadas por instalaciones (luego inversión).
  * serie_diaria_top: serie diaria solo de las top_n campañas (incluye nombre_campana, network, OS, Pais).

- Campos comunes: inversion, presupuesto, instalaciones, clicks, impresiones, cpi, cpa_click, cpa_impresiones, ctr, cvr_click_install, cvr_impresion_install.
- Campos específicos por dataset:
  * totales_globales_periodo: incluye presupuesto, cpi global, ctr, cvr_click_install, cvr_impresion_install.
  * totales_por_region: incluye Pais, cpi por región, ctr, cvr_click_install.
  * serie_diaria_agregada: incluye campo "fecha" (DATE), cpi, cpa_click, ctr, cvr_click_install, cvr_impresion_install. Ya está agregado por fecha.
  * serie_diaria_top: incluye "fecha" (DATE), nombre_campana, network, OS, Pais.
  * top_campanas_mes: incluye nombre_campana, network, OS, Pais, cpi, ctr, cvr_click_install.
  * funnel_etapas: incluye etapa_1_impresiones, etapa_2_clicks, etapa_3_instalaciones, cvr_impresion_click, cvr_click_install, cvr_impresion_install.

- NOTA SEMÁNTICA CPI: "Mejor CPI" = valor MÁS BAJO (instalación más barata). "Peor CPI" = valor MÁS ALTO (instalación más cara). NUNCA invertir esta lógica.
- Los KPIs (CPI/CVR/CTR) serán NULL si el denominador es 0; NO los trates como 0.
- Filtrado previo: excluye campañas "unknown" y network en ("Organic", "Others"), requiere al menos una señal (inversion > 0 OR instalaciones > 0 OR clicks > 0 OR impresiones > 0).

DICCIONARIO DE DATOS:
- fecha: día del dato.
- nombre_campana: identificador de campaña.
- network: plataforma publicitaria (ej: Google Ads, Meta, TikTok).
- OS: sistema operativo (ej: Android, iOS).
- Pais: país de la campaña.
- inversion: gasto publicitario total.
- presupuesto: presupuesto máximo asignado.
- instalaciones: instalaciones generadas (conversión final — KPI crítico).
- clicks: clics generados por la campaña.
- impresiones: impresiones servidas por la campaña.
- cpi = inversion / instalaciones (Costo por Instalación — KPI final crítico).
- cpa_click = inversion / clicks (Costo por Clic).
- cpa_impresiones = inversion / impresiones (Costo por Impresión / CPM).
- ctr = clicks / impresiones (Click-Through Rate).
- cvr_click_install = instalaciones / clicks (Tasa de conversión Clic → Instalación).
- cvr_impresion_install = instalaciones / impresiones (Tasa de conversión Impresión → Instalación).
- cvr_impresion_click = clicks / impresiones (= CTR, en contexto de funnel).
Funnel: Inversión → Impresiones → Clicks → Instalaciones. CPI es el KPI final crítico.

REGLAS POR BLOQUE (OBLIGATORIO - MÁXIMA PRIORIDAD):

Estas instrucciones ESPECÍFICAS por bloque tienen PRIORIDAD ABSOLUTA sobre todas las demás reglas.
Cada bloque problemático DEBE incluir los gráficos especificados a continuación.

BLOQUE: analisis_region
-----------------------
OBJETIVO: Mostrar performance por país/región geográfica
DATASET A USAR: totales_por_region (YA viene pre-agregado por país, NO necesitas agrupar)

GRÁFICOS OBLIGATORIOS (elegir 2):
  1) BAR_RANKING de instalaciones por Pais
     - Dataset: totales_por_region (usar directamente, ya tiene instalaciones sumadas por país)
     - Highcharts: type="bar", xAxis.categories=[países], series.data=[instalaciones por país]
     - Ordenar descendente por instalaciones (el dataset ya viene ordenado)
  2) DONUT_SHARE de inversión por Pais
     - Dataset: totales_por_region (usar directamente, ya tiene inversion sumada por país)
     - Highcharts: type="pie", innerSize="50%", series.data=[{name: país, y: inversión}]

INSIGHTS OBLIGATORIOS:
  - Identificar país con mayor volumen de instalaciones y mencionar su CPI
  - Comparar eficiencia (cpi) entre países usando datos de totales_por_region
  - Calcular % de participación: instalaciones del top país / instalaciones totales de totales_globales_periodo
  - Mencionar cuántos países tienen datos (contar filas de totales_por_region)

BLOQUE: cvr_indices
--------------------
OBJETIVO: Visualizar tasas de conversión del funnel y identificar caídas
DATASETS A USAR:
  - funnel_etapas (para el FUNNEL_CHART, ya tiene las 3 etapas y CVRs calculados)
  - serie_diaria_agregada (para la evolución temporal de CTR y CVR diario)

GRÁFICOS OBLIGATORIOS (2 gráficos):
  1) FUNNEL_CHART mostrando: Impresiones → Clicks → Instalaciones
     - Dataset: funnel_etapas (usar campos etapa_1_impresiones, etapa_2_clicks, etapa_3_instalaciones)
     - Highcharts: type="funnel", data format: [["Impresiones", valor], ["Clicks", valor], ["Instalaciones", valor]]
     - IMPORTANTE: Formato de data DEBE ser array de arrays, NO objetos con name
     - Incluir plotOptions básicas: dataLabels enabled, center, neckWidth, neckHeight
  2) LINE_TIME_SERIES de CTR y CVR_click_install diario
     - Dataset: serie_diaria_agregada (usar campos ctr y cvr_click_install por fecha, YA calculados)
     - Highcharts: type="line", xAxis.type="datetime", 2 series con diferentes colores
     - OPCIONAL: agregar cvr_impresion_install como 3ra serie para comparar etapas

INSIGHTS OBLIGATORIOS:
  - Usar cvr_impresion_click y cvr_click_install de funnel_etapas para identificar la etapa con mayor caída
  - Calcular % de caída en cada etapa: (1 - CVR) * 100
  - Mencionar: "De cada 1000 impresiones, X generan clic y solo Y resultan en instalación"
  - Si hay ctr y cvr_click_install disponibles, comparar su evolución temporal

BLOQUE: evolucion_conversiones
-------------------------------
OBJETIVO: Mostrar tendencia temporal de conversiones (instalaciones y clicks)
DATASET A USAR: serie_diaria_agregada (YA tiene totales diarios globales, NO necesitas agrupar)

GRÁFICOS OBLIGATORIOS (mínimo 1, máximo 2):
  1) LINE_TIME_SERIES de instalaciones diarias (OBLIGATORIO)
     - Dataset: serie_diaria_agregada (usar campo instalaciones por fecha directamente)
     - Highcharts: type="line", xAxis.type="datetime", xAxis.categories=[fechas ISO],
       series=[{name: "Instalaciones Diarias", data: [valores instalaciones por día]}]
  2) LINE_TIME_SERIES de clicks diarios (OBLIGATORIO en el mismo chart o separado)
     - Dataset: serie_diaria_agregada (usar campo clicks por fecha)
     - Highcharts: type="line", xAxis.type="datetime"
     - Puedes hacer 2 series en el mismo gráfico si las magnitudes son comparables

INSIGHTS OBLIGATORIOS:
  - Identificar fecha con pico máximo de instalaciones
  - Identificar fecha con mínimo de instalaciones (excluir días con instalaciones=0 si los hay)
  - Calcular tendencia: comparar promedio de primeros 7 días vs últimos 7 días del período
  - Mencionar días totales con datos (contar filas de serie_diaria_agregada)

BLOQUE: resultados_generales
-----------------------------
OBJETIVO: Overview general del período con KPIs clave y tendencia
DATASETS A USAR:
  - totales_globales_periodo (para KPI_CARD en narrative, incluye presupuesto y pacing)
  - serie_diaria_agregada (para gráficos de tendencia diaria — YA tiene CPI pre-calculado por día)

CONTENIDO OBLIGATORIO:
  1) KPI_CARD en narrativa (incluir en narrative):
     - Mostrar: Inversión total, Presupuesto, Pacing %, Instalaciones totales, Clicks totales, Impresiones totales, CPI global
     - Dataset: totales_globales_periodo
     - Formato: "En el período se invirtieron $X de un presupuesto de $Y (Z% pacing), generando N instalaciones a un CPI de $W"

  2) COMBO_BAR_LINE_DUAL o 2 LINE_TIME_SERIES separados:
     - Barras=instalaciones diarias, Línea=cpi diario
     - Dataset: serie_diaria_agregada (usar DIRECTAMENTE los campos fecha, instalaciones, cpi)
     - IMPORTANTE: El CPI diario ya está pre-calculado en serie_diaria_agregada. NO recalcules manualmente.
     - PROHIBIDO: NO calcules CPI acumulado, running average, ni suavizado.
       Los valores de cpi de serie_diaria_agregada deben usarse TAL CUAL en la serie del gráfico.

INSIGHTS OBLIGATORIOS:
  - Calcular pacing: inversion / presupuesto * 100. Comentar si está por encima o por debajo del esperado para el período.
  - Identificar día con MEJOR CPI: el día con el valor MÁS BAJO de cpi en serie_diaria_agregada (más eficiente)
  - Identificar día con PEOR CPI: el día con el valor MÁS ALTO de cpi en serie_diaria_agregada (menos eficiente)
  - ADVERTENCIA: Días con muy pocas instalaciones (ej: 1-2) tendrán CPI extremo. Mencionarlo como contexto.
  - Comparar inversión total vs presupuesto

BLOQUE: proyecciones
---------------------
OBJETIVO: Mostrar evolución temporal comparativa (NO calcular forecast futuro)
DATASET A USAR: serie_diaria_agregada (ya tiene métricas diarias agregadas con CPI pre-calculado)

LÓGICA DE AGRUPACIÓN DINÁMICA (según días disponibles en data_window):
  - Si data_window tiene >= 21 días: agrupar en bloques de 7 días (semanas reales). Titular "Semana 1", "Semana 2", etc.
  - Si data_window tiene 14-20 días: agrupar en bloques de 7 días. Solo habrá 2-3 semanas.
  - Si data_window tiene 7-13 días: dividir en 2 mitades iguales. Titular "Primera mitad" y "Segunda mitad".
  - Si data_window tiene < 7 días: NO generar gráfico semanal. Solo incluir insight textual con tendencia general.
  IMPORTANTE: El número de bloques/semanas DEBE corresponder a los días REALES en los datos.
  NUNCA generar más bloques de los que los datos soportan.

GRÁFICOS OBLIGATORIOS (1 gráfico, si hay >= 7 días):
  1) COLUMN_CHART de comparación por período
     - Agrupar serie_diaria_agregada según la lógica de arriba
     - 2 series: instalaciones promedio por bloque + CPI promedio ponderado (sum inversión / sum instalaciones)
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

BLOQUE: resumen_ejecutivo
--------------------------
OBJETIVO: Síntesis de alto nivel para stakeholders
GRÁFICOS OBLIGATORIOS (máximo 2):
  1) BAR_RANKING de campañas por instalaciones
     - Dataset: top_campanas_mes (usar TODAS las filas disponibles, hasta un máximo de 10)
     - Highcharts: type="bar"
     - TÍTULO DINÁMICO: Contar las filas reales en top_campanas_mes.
       Si hay N campañas, titular "Top N Campañas por Instalaciones".
       NUNCA titular "Top 5" si solo hay 4 campañas.
  2) LINE_TIME_SERIES de inversión diaria + instalaciones diarias
     - Dataset: serie_diaria_agregada (usar directamente, ya viene agregado por fecha)
     - IMPORTANTE: Normalizar escalas o usar 2 ejes Y
INSIGHTS OBLIGATORIOS:
  - Mencionar campaña más exitosa (nombre + instalaciones + CPI)
  - Mencionar campaña menos eficiente (alto CPI, bajas instalaciones)
  - Resumen ejecutivo: "Inversión total $X generó Y instalaciones a un CPI de $Z"

BLOQUE: aprendizajes
---------------------
OBJETIVO: Comparar performance entre Networks/plataformas y OS
GRÁFICOS SUGERIDOS (1-2):
  1) BAR_RANKING de cpi por network
     - Dataset: top_campanas_mes (agrupar por network, calcular CPI promedio ponderado = sum inversión / sum instalaciones)
     - Highcharts: type="bar", xAxis.categories=[networks], series.data=[CPI ponderado]
  2) COLUMN_CHART de instalaciones por network y OS
     - Dataset: top_campanas_mes (agrupar por network o OS, sumar instalaciones)
     - Highcharts: type="column"
INSIGHTS OBLIGATORIOS:
  - Comparar networks en términos de CPI y volumen de instalaciones
  - Comparar OS (Android vs iOS) si hay datos diferenciados en top_campanas_mes
  - Identificar plataforma más eficiente y recomendar ajuste de budget
""".strip()


class FlexBctAnalyticsProvider(AnalyticsProvider):
    """
    Analytics provider for Flex BCT.

    Microservice: flex-dashboard-data
    Funnel: Impresiones → Clicks → Instalaciones
    Datasets: totales_globales_periodo, totales_por_region,
              serie_diaria_agregada, funnel_etapas,
              top_campanas_mes, serie_diaria_top
    """

    @property
    def service_url(self) -> str:
        return os.getenv(
            "FLEXBCT_ANALYTICS_SERVICE_URL",
            "https://flex-dashboard-data-715418856987.us-central1.run.app",
        )

    @property
    def analytics_explanation(self) -> str:
        return FLEX_BCT_EXPLANATION

    @property
    def metrics_glossary(self) -> str:
        return (
            "\n**Glosario de Métricas de Marketing:**\n"
            "- **Inversión**: Gasto publicitario total (USD)\n"
            "- **Presupuesto**: Presupuesto máximo asignado para el período\n"
            "- **Pacing**: Porcentaje de ejecución del presupuesto = inversión / presupuesto\n"
            "- **Impresiones**: Impresiones servidas por la campaña\n"
            "- **Clicks**: Clics generados por la campaña\n"
            "- **Instalaciones**: Instalaciones generadas — KPI crítico de conversión final\n"
            "- **CPI**: Costo por Instalación = inversión / instalaciones (KPI crítico)\n"
            "- **CTR**: Click-Through Rate = clicks / impresiones\n"
            "- **CVR_click_install**: Tasa de conversión Clic → Instalación = instalaciones / clicks\n"
            "- **CVR_impresion_install**: Tasa de conversión Impresión → Instalación = instalaciones / impresiones\n"
            "\n**Funnel de Conversión:** Inversión → Impresiones → Clicks → Instalaciones"
        )

    @property
    def metrics_glossary_compact(self) -> str:
        return (
            "\n**Métricas clave:**\n"
            "- Inversión: gasto publicitario (USD)\n"
            "- Presupuesto / Pacing: presupuesto asignado y % de ejecución\n"
            "- Impresiones: impresiones servidas\n"
            "- Clicks: clics generados\n"
            "- Instalaciones: instalaciones generadas (KPI crítico)\n"
            "- CPI: costo por instalación = inversión / instalaciones (KPI crítico)\n"
            "- CTR: click-through rate = clicks / impresiones\n"
            "- CVR_click_install: tasa conversión clic → instalación\n"
            "- Funnel: Inversión → Impresiones → Clicks → Instalaciones"
        )
