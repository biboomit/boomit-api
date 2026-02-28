import os

from app.services.analytics_providers.base import AnalyticsProvider


MONIFIC_EXPLANATION = """
FORMATO DE analytics_data:
- dataset: uno de ["totales_globales_periodo", "totales_por_os", "serie_diaria_agregada",
  "funnel_por_os", "funnel_por_network", "totales_por_network",
  "serie_diaria_por_network", "top_campanas_mes", "serie_diaria_top"].

  * totales_globales_periodo: 1 fila con métricas agregadas del rango completo, incluye presupuesto y pacing.
  * totales_por_os: filas con totales por sistema operativo (os: Android, iOS, Web). KPIs pre-calculados.
  * serie_diaria_agregada: filas con métricas diarias TOTALES (sumadas, todos los OS) por fecha, CON CPAs y CVRs pre-calculados.
  * funnel_por_os: filas con las 3 etapas del funnel por OS (etapa_2_registro_simple, etapa_3_llenado_contrato, etapa_4_inversion_exitosa) y CVRs.
  * funnel_por_network: igual que funnel_por_os pero agrupado por network.
  * totales_por_network: filas con totales por plataforma publicitaria (network), KPIs pre-calculados.
  * serie_diaria_por_network: filas con métricas diarias desglosadas por network y fecha, SIN CPAs.
  * top_campanas_mes: hasta top_n campañas rankeadas por inversion_exitosa_count (luego inversión), con network y os.
  * serie_diaria_top: serie diaria solo de las top_n campañas (fecha, nombre_campana, network, os, métricas, CPAs).

- Campos comunes: inversion, registro_simple, llenado_contrato, inversion_exitosa_count, inversion_exitosa_monto,
  cpa_registro, cpa_llenado, cpa_inversion_exitosa, cvr_registro_llenado, cvr_llenado_inversion.
- Campos específicos por dataset:
  * totales_globales_periodo: incluye presupuesto, pacing_porcentaje, tracker_installs, impresiones, clicks,
    instalaciones, cvr_install_registro.
  * totales_por_os: incluye os, tracker_installs, impresiones, clicks, instalaciones, cvr_install_registro.
  * serie_diaria_agregada: incluye "fecha" (DATE), cpa_registro, cpa_llenado, cpa_inversion_exitosa,
    cvr_registro_llenado, cvr_llenado_inversion. Ya está agregado por fecha (todos los OS sumados).
  * funnel_por_os: incluye "os", etapa_2_registro_simple, etapa_3_llenado_contrato, etapa_4_inversion_exitosa,
    cvr_install_registro, cvr_registro_llenado, cvr_llenado_inversion.
  * funnel_por_network: incluye "network", etapa_2_registro_simple, etapa_3_llenado_contrato,
    etapa_4_inversion_exitosa, cvr_install_registro, cvr_registro_llenado, cvr_llenado_inversion.
  * totales_por_network: incluye "network", tracker_installs, impresiones, clicks, instalaciones,
    cvr_install_registro.
  * top_campanas_mes: incluye nombre_campana, network, os, cpa_registro, cpa_llenado, cpa_inversion_exitosa,
    cvr_registro_llenado, cvr_llenado_inversion.
  * serie_diaria_top: incluye "fecha" (DATE), nombre_campana, network, os, cpa_registro, cpa_llenado,
    cpa_inversion_exitosa.

- DIMENSIÓN PRINCIPAL DE SEGMENTACIÓN: "os" (sistema operativo: Android, iOS, Web).
  El análisis de rendimiento primario es por OS. Network es una dimensión secundaria.
- NOTA SEMÁNTICA CPA: "Mejor CPA" = valor MÁS BAJO (adquisición más barata). "Peor CPA" = valor MÁS ALTO. NUNCA invertir.
- Los KPIs (CPA/CVR) serán NULL si el denominador es 0; NO los trates como 0.
- Filtrado previo: source = 'Singular', excluye os = '', campañas 'unknown', network en ('Organic', 'Others').
  Requiere al menos una señal (inversion > 0 OR registro_simple > 0 OR llenado_contrato > 0 OR inversion_exitosa_count > 0).

DICCIONARIO DE DATOS:
- fecha: día del dato.
- os: sistema operativo (Android, iOS, Web).
- nombre_campana: identificador de campaña.
- network: plataforma publicitaria (ej: Google Ads, Meta, TikTok).
- inversion: gasto publicitario total.
- presupuesto: presupuesto máximo asignado.
- impresiones: impresiones servidas.
- clicks: clics generados.
- instalaciones: instalaciones (campo nativo de Singular, puede diferir de tracker_installs).
- tracker_installs: instalaciones atribuidas por tracker (etapa 1 del funnel de conversión).
- registro_simple: usuarios que completaron el registro simple — etapa 2 del funnel.
- llenado_contrato: usuarios que completaron el llenado de datos y firma de contrato — etapa 3 del funnel.
- inversion_exitosa_count: cantidad de inversiones exitosas (conversión final — KPI crítico).
- inversion_exitosa_monto: monto en dinero de las inversiones exitosas.
- cpa_registro = inversion / registro_simple.
- cpa_llenado = inversion / llenado_contrato.
- cpa_inversion_exitosa = inversion / inversion_exitosa_count (KPI FINAL CRÍTICO).
- cvr_install_registro = registro_simple / tracker_installs.
- cvr_registro_llenado = llenado_contrato / registro_simple.
- cvr_llenado_inversion = inversion_exitosa_count / llenado_contrato.
- pacing_porcentaje = inversion / presupuesto.
Funnel: Inversión → tracker_installs → Registro Simple → Llenado de Contrato → Inversión Exitosa.
CPA_inversion_exitosa es el KPI final crítico.

REGLAS POR BLOQUE (OBLIGATORIO - MÁXIMA PRIORIDAD):

Estas instrucciones ESPECÍFICAS por bloque tienen PRIORIDAD ABSOLUTA sobre todas las demás reglas.
Cada bloque problemático DEBE incluir los gráficos especificados a continuación.

BLOQUE: analisis_region
-----------------------
NOTA: Este proveedor segmenta principalmente por OS (Android, iOS, Web), NO por país.
OBJETIVO: Mostrar performance por sistema operativo
DATASET A USAR: totales_por_os (YA viene pre-agregado por os, NO necesitas agrupar)

GRÁFICOS OBLIGATORIOS (elegir 2):
  1) BAR_RANKING de inversion_exitosa_count por os
     - Dataset: totales_por_os (usar directamente)
     - Highcharts: type="bar", xAxis.categories=[os values], series.data=[inversion_exitosa_count por os]
     - Ordenar descendente por inversion_exitosa_count (el dataset ya viene ordenado)
  2) DONUT_SHARE de inversión por os
     - Dataset: totales_por_os
     - Highcharts: type="pie", innerSize="50%", series.data=[{name: os, y: inversión}]

INSIGHTS OBLIGATORIOS:
  - Identificar OS con mayor inversion_exitosa_count y mencionar su cpa_inversion_exitosa
  - Comparar eficiencia (cpa_inversion_exitosa) entre OS (Android vs iOS vs Web)
  - Calcular % de participación: inversion_exitosa_count del top OS / total de totales_globales_periodo
  - Mencionar cuántos OS tienen datos (contar filas de totales_por_os)

BLOQUE: cvr_indices
--------------------
OBJETIVO: Visualizar tasas de conversión del funnel y caídas por etapa
DATASETS A USAR:
  - funnel_por_os (para FUNNEL_CHART desglosado por OS y CVRs por etapa)
  - funnel_por_network (para comparar CVR entre plataformas)
  - totales_globales_periodo (para CVRs globales del período)

GRÁFICOS OBLIGATORIOS (2 gráficos):
  1) FUNNEL_CHART mostrando: Registro Simple → Llenado de Contrato → Inversión Exitosa
     - Dataset: totales_globales_periodo (usar campos registro_simple, llenado_contrato, inversion_exitosa_count)
     - Highcharts: type="funnel", data format: [["Tracker Installs", tracker_installs], ["Registro Simple", registro_simple], ["Llenado de Contrato", llenado_contrato], ["Inversión Exitosa", inversion_exitosa_count]]
     - IMPORTANTE: Formato de data DEBE ser array de arrays, NO objetos con name
     - Incluir plotOptions básicas: dataLabels enabled, center, neckWidth, neckHeight
  2) BAR_CHART de cvr_llenado_inversion por OS (la etapa más restrictiva del funnel)
     - Dataset: funnel_por_os (usar campo cvr_llenado_inversion por os)
     - Highcharts: type="bar", xAxis.categories=[os], series.data=[cvr_llenado_inversion]
     - ALTERNATIVA: Usar funnel_por_network si hay más variabilidad entre networks

INSIGHTS OBLIGATORIOS:
  - Identificar la etapa del funnel con mayor caída (comparar cvr_install_registro, cvr_registro_llenado, cvr_llenado_inversion de totales_globales_periodo)
  - Mencionar: "De cada 100 tracker installs, X completan registro, Y llenan el contrato y Z realizan inversión exitosa"
  - Comparar CVR entre OS usando funnel_por_os (qué OS convierte mejor en cada etapa)
  - Calcular % de caída en cada etapa: (1 - CVR) * 100

BLOQUE: evolucion_conversiones
-------------------------------
OBJETIVO: Mostrar tendencia temporal de conversiones y actividad del funnel
DATASET A USAR: serie_diaria_agregada (YA tiene totales diarios globales, CON CPAs pre-calculados)

GRÁFICOS OBLIGATORIOS (mínimo 1, máximo 2):
  1) LINE_TIME_SERIES de inversion_exitosa_count diario (OBLIGATORIO)
     - Dataset: serie_diaria_agregada (usar campo inversion_exitosa_count por fecha directamente)
     - Highcharts: type="line", xAxis.type="datetime"
  2) LINE_TIME_SERIES de registro_simple y llenado_contrato diarios (comparar etapas intermedias)
     - Dataset: serie_diaria_agregada (usar campos registro_simple y llenado_contrato)
     - Highcharts: type="line", 2 series en el mismo gráfico

INSIGHTS OBLIGATORIOS:
  - Identificar fecha con pico máximo de inversion_exitosa_count
  - Identificar fecha con mínimo inversion_exitosa_count (excluir días con valor=0)
  - Calcular tendencia: comparar promedio de primeros 7 días vs últimos 7 días del período
  - Mencionar días totales con datos (contar filas de serie_diaria_agregada)

BLOQUE: resultados_generales
-----------------------------
OBJETIVO: Overview general del período con KPIs clave y tendencia
DATASETS A USAR:
  - totales_globales_periodo (para KPI_CARD en narrative, incluye pacing)
  - serie_diaria_agregada (para gráficos de tendencia diaria — tiene CPA pre-calculado)

CONTENIDO OBLIGATORIO:
  1) KPI_CARD en narrativa (incluir en narrative):
     - Mostrar: Inversión total, Presupuesto, Pacing %, Inversiones exitosas total, CPA_inversion_exitosa global
     - También mostrar: Registro Simple total, Llenado de Contrato total
     - Formato: "En el período se invirtieron $X de un presupuesto de $Y (Z% pacing), generando N inversiones exitosas a un CPA de $W"

  2) COMBO_BAR_LINE_DUAL o 2 LINE_TIME_SERIES separados:
     - Barras=inversion_exitosa_count diario, Línea=cpa_inversion_exitosa diario
     - Dataset: serie_diaria_agregada (usar DIRECTAMENTE los campos fecha, inversion_exitosa_count, cpa_inversion_exitosa)
     - IMPORTANTE: El CPA diario ya está pre-calculado. NO recalcules manualmente.
     - PROHIBIDO: NO calcules CPA acumulado, running average, ni suavizado.

INSIGHTS OBLIGATORIOS:
  - Mencionar pacing_porcentaje: si está por encima o por debajo del esperado para el período
  - Identificar día con MEJOR CPA (valor más bajo de cpa_inversion_exitosa en serie_diaria_agregada)
  - Identificar día con PEOR CPA (valor más alto de cpa_inversion_exitosa en serie_diaria_agregada)
  - ADVERTENCIA: Días con muy pocas inversiones exitosas (ej: 1-2) tendrán CPA extremo. Mencionarlo como contexto.
  - Comparar inversión total vs presupuesto

BLOQUE: proyecciones
---------------------
OBJETIVO: Mostrar evolución temporal comparativa (NO calcular forecast futuro)
DATASET A USAR: serie_diaria_agregada (ya tiene métricas diarias agregadas con CPA pre-calculado)

LÓGICA DE AGRUPACIÓN DINÁMICA (según días disponibles en data_window):
  - Si data_window tiene >= 21 días: agrupar en bloques de 7 días. Titular "Semana 1", "Semana 2", etc.
  - Si data_window tiene 14-20 días: agrupar en bloques de 7 días. Solo habrá 2-3 semanas.
  - Si data_window tiene 7-13 días: dividir en 2 mitades iguales. Titular "Primera mitad" y "Segunda mitad".
  - Si data_window tiene < 7 días: NO generar gráfico semanal. Solo insight textual con tendencia general.
  IMPORTANTE: El número de bloques DEBE corresponder a los días REALES en los datos.
  NUNCA generar más bloques de los que los datos soportan.

GRÁFICOS OBLIGATORIOS (1 gráfico, si hay >= 7 días):
  1) COLUMN_CHART de comparación por período
     - Agrupar serie_diaria_agregada según la lógica de arriba
     - 2 series: inversion_exitosa_count promedio por bloque + CPA promedio ponderado (sum inversion / sum inversion_exitosa_count)
     - Usar doble eje Y
     - El título debe reflejar la agrupación real

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
  1) BAR_RANKING de campañas por inversion_exitosa_count
     - Dataset: top_campanas_mes (usar TODAS las filas disponibles, hasta un máximo de 10)
     - Highcharts: type="bar"
     - TÍTULO DINÁMICO: Si hay N campañas, titular "Top N Campañas por Inversiones Exitosas".
       NUNCA titular "Top 5" si solo hay 4 campañas.
  2) LINE_TIME_SERIES de inversión diaria + inversion_exitosa_count diario
     - Dataset: serie_diaria_agregada (usar directamente, ya viene agregado por fecha)
     - IMPORTANTE: Normalizar escalas o usar 2 ejes Y
INSIGHTS OBLIGATORIOS:
  - Mencionar campaña más exitosa (nombre + inversion_exitosa_count + CPA_inversion_exitosa)
  - Mencionar campaña menos eficiente (alto CPA, poca inversión exitosa)
  - Resumen ejecutivo: "Inversión total $X generó Y inversiones exitosas a un CPA de $Z"
  - Desglosar por OS (cuál generó más inversiones exitosas)

BLOQUE: aprendizajes
---------------------
OBJETIVO: Comparar performance entre OS y Networks
GRÁFICOS SUGERIDOS (1-2):
  1) BAR_RANKING de cpa_inversion_exitosa por OS
     - Dataset: totales_por_os (ranking directo de CPA por os)
     - Highcharts: type="bar", xAxis.categories=[os], series.data=[cpa_inversion_exitosa]
  2) COLUMN_CHART de inversion_exitosa_count por network
     - Dataset: totales_por_network (agrupar por network, sumar inversion_exitosa_count)
     - Highcharts: type="column"
INSIGHTS OBLIGATORIOS:
  - Comparar OS en términos de CPA y volumen de inversiones exitosas
  - Comparar networks (Google Ads vs Meta vs TikTok) en eficiencia y volumen
  - Identificar combinación OS + network más eficiente usando top_campanas_mes
  - Recomendar ajuste de budget hacia OS/network con mejor CPA
""".strip()


class MonificAnalyticsProvider(AnalyticsProvider):
    """
    Analytics provider for Monific.

    Microservice: monific-dashboard-data
    Funnel: tracker_installs → Registro Simple → Llenado de Contrato → Inversión Exitosa
    Primary segmentation: OS (Android, iOS, Web)
    Datasets: totales_globales_periodo, totales_por_os, serie_diaria_agregada,
              funnel_por_os, funnel_por_network,
              totales_por_network, serie_diaria_por_network,
              top_campanas_mes, serie_diaria_top
    """

    @property
    def service_url(self) -> str:
        return os.getenv(
            "MONIFIC_ANALYTICS_SERVICE_URL",
            "https://monific-dashboard-data-715418856987.us-central1.run.app",
        )

    @property
    def analytics_explanation(self) -> str:
        return MONIFIC_EXPLANATION

    @property
    def metrics_glossary(self) -> str:
        return (
            "\n**Glosario de Métricas de Marketing:**\n"
            "- **Inversión**: Gasto publicitario total (USD)\n"
            "- **Presupuesto**: Presupuesto máximo asignado para el período\n"
            "- **Pacing**: Porcentaje de ejecución del presupuesto = inversión / presupuesto\n"
            "- **Tracker Installs**: Instalaciones atribuidas por tracker (Singular) — inicio del funnel\n"
            "- **Registro Simple**: Usuarios que completaron el registro en la app — etapa 2 del funnel\n"
            "- **Llenado de Contrato**: Usuarios que completaron llenado de datos y firmaron contrato — etapa 3\n"
            "- **Inversión Exitosa (count)**: Cantidad de inversiones exitosas realizadas — KPI crítico (conversión final)\n"
            "- **Inversión Exitosa (monto)**: Monto total en dinero de las inversiones exitosas\n"
            "- **CPA_registro**: Costo por registro simple = inversión / registro_simple\n"
            "- **CPA_llenado**: Costo por llenado de contrato = inversión / llenado_contrato\n"
            "- **CPA_inversion_exitosa**: Costo por inversión exitosa = inversión / inversion_exitosa_count (KPI FINAL)\n"
            "- **CVR_install_registro**: Tasa conversión tracker_installs → registro simple\n"
            "- **CVR_registro_llenado**: Tasa conversión registro simple → llenado de contrato\n"
            "- **CVR_llenado_inversion**: Tasa conversión llenado de contrato → inversión exitosa\n"
            "- **OS**: Sistema operativo — dimensión principal de segmentación (Android, iOS, Web)\n"
            "\n**Funnel de Conversión:** Inversión → Tracker Installs → Registro Simple → Llenado de Contrato → Inversión Exitosa"
        )

    @property
    def metrics_glossary_compact(self) -> str:
        return (
            "\n**Métricas clave:**\n"
            "- Inversión: gasto publicitario (USD)\n"
            "- Presupuesto / Pacing: presupuesto asignado y % de ejecución\n"
            "- Tracker Installs: instalaciones atribuidas (inicio del funnel)\n"
            "- Registro Simple: usuarios registrados en la app (etapa 2)\n"
            "- Llenado de Contrato: firma y llenado de datos completado (etapa 3)\n"
            "- Inversión Exitosa: inversiones completadas (KPI crítico)\n"
            "- CPA_inversion_exitosa: costo por inversión exitosa = inversión / inversion_exitosa_count\n"
            "- CVR_llenado_inversion: tasa conversión llenado → inversión exitosa (etapa más restrictiva)\n"
            "- OS: segmentación principal (Android, iOS, Web)\n"
            "- Funnel: Inversión → Tracker Installs → Registro Simple → Llenado de Contrato → Inversión Exitosa"
        )
