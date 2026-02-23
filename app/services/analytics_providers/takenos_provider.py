import os

from app.services.analytics_providers.base import AnalyticsProvider


TAKENOS_EXPLANATION = """
FORMATO DE analytics_data:
- dataset: uno de ["totales_globales_periodo", "totales_por_region", "serie_diaria_agregada", "funnel_etapas", "top_campanas_mes", "serie_diaria_top"].
  * totales_globales_periodo: 1 fila con métricas agregadas del rango completo.
  * totales_por_region: 3-5 filas con totales por país (nombre_pais_campana).
  * serie_diaria_agregada: ~30 filas con totales diarios globales (todas las campañas sumadas por fecha).
  * funnel_etapas: 1 fila con las 3 etapas del funnel (etapa_1_install, etapa_2_apertura, etapa_3_FTD, cvr_1_to_2, cvr_2_to_3, cvr_1_to_3).
  * top_campanas_mes: hasta top_n campañas rankeadas por FTD (luego inversión).
  * serie_diaria_top: ~270 filas con serie diaria solo de esas top campañas.

- Campos comunes: inversion, install, apertura_cuenta_exitosa, FTD, cpa_install, cpa_apertura_cuenta_exitosa, cpa_FTD, CVR_install_FTD, CVR_install_apertura, CVR_apertura_FTD.
- Campos específicos por dataset:
  * serie_diaria_top y serie_diaria_agregada: incluyen campo "fecha" (DATE)
  * top_campanas_mes y serie_diaria_top: incluyen nombre_campana, Network, os, nombre_pais_campana
  * totales_por_region: incluye nombre_pais_campana
  * funnel_etapas: incluye etapa_1_install, etapa_2_apertura, etapa_3_FTD, cvr_1_to_2, cvr_2_to_3, cvr_1_to_3

- Los KPIs (CPA/CVR) serán NULL si el denominador es 0; NO los trates como 0.
- Filtrado previo: excluye campañas "unknown" y Network en ("Organic", "Others"), y descarta filas sin señal.

DICCIONARIO DE DATOS:
- fecha: día del dato.
- nombre_campana: identificador de campaña (plataforma, país, OS, objetivo).
- install: instalaciones generadas.
- apertura_cuenta_exitosa: registros completos tras instalar.
- FTD: primer depósito de usuario (First Time Deposit).
- inversion: gasto publicitario total.
- cpa_install = inversion / install.
- cpa_apertura_cuenta_exitosa = inversion / apertura_cuenta_exitosa.
- cpa_FTD = inversion / FTD.
- CVR_install_FTD = FTD / install.
- CVR_install_apertura = apertura_cuenta_exitosa / install.
- CVR_apertura_FTD = FTD / apertura_cuenta_exitosa.
Funnel: Inversión → Install → Apertura → FTD. CPA_FTD es el KPI final crítico.

REGLAS POR BLOQUE (OBLIGATORIO - MÁXIMA PRIORIDAD):

Estas instrucciones ESPECÍFICAS por bloque tienen PRIORIDAD ABSOLUTA sobre todas las demás reglas.
Cada bloque problemático DEBE incluir los gráficos especificados a continuación.

BLOQUE: analisis_region
-----------------------
OBJETIVO: Mostrar performance por país/región geográfica
DATASET A USAR: totales_por_region (YA viene pre-agregado por país, NO necesitas agrupar)

GRÁFICOS OBLIGATORIOS (elegir 2):
  1) BAR_RANKING de FTD por nombre_pais_campana
     - Dataset: totales_por_region (usar directamente, ya tiene FTD sumado por país)
     - Highcharts: type="bar", xAxis.categories=[países], series.data=[FTD por país]
     - Ordenar descendente por FTD (el dataset ya viene ordenado)
  2) DONUT_SHARE de inversión por nombre_pais_campana
     - Dataset: totales_por_region (usar directamente, ya tiene inversion sumada por país)
     - Highcharts: type="pie", innerSize="50%", series.data=[{name: país, y: inversión}]

INSIGHTS OBLIGATORIOS:
  - Identificar país con mayor FTD y mencionar su CPA_FTD (disponible en totales_por_region)
  - Comparar eficiencia (CPA_FTD) entre países usando datos de totales_por_region
  - Calcular % de participación: FTD del top país / sum(FTD de totales_globales_periodo)
  - Mencionar cuántos países tienen datos (contar filas de totales_por_region)

BLOQUE: cvr_indices
--------------------
OBJETIVO: Visualizar tasas de conversión del funnel y identificar caídas
DATASETS A USAR:
  - funnel_etapas (para el FUNNEL_CHART, ya tiene las 3 etapas y CVRs calculados)
  - serie_diaria_agregada (para la evolución temporal de CVR diario)

GRÁFICOS OBLIGATORIOS (2 gráficos):
  1) FUNNEL_CHART mostrando: install → apertura_cuenta_exitosa → FTD
     - Dataset: funnel_etapas (usar campos etapa_1_install, etapa_2_apertura, etapa_3_FTD)
     - Highcharts: type="funnel", data format: [["Install", valor], ["Apertura Cuenta", valor], ["FTD", valor]]
     - IMPORTANTE: Formato de data DEBE ser array de arrays, NO objetos con name
     - Incluir plotOptions básicas: dataLabels enabled, center, neckWidth, neckHeight
  2) LINE_TIME_SERIES de CVR_install_FTD diario O CVR por etapas
     - Dataset: serie_diaria_agregada (usar campo CVR_install_FTD por fecha, YA calculado)
     - Highcharts: type="line", xAxis.type="datetime", categories=[fechas], series.data=[CVR por día]
     - OPCIONAL: agregar 2da serie con CVR_install_apertura para comparar etapas

INSIGHTS OBLIGATORIOS:
  - Usar cvr_1_to_2 y cvr_2_to_3 de funnel_etapas para identificar la etapa con mayor caída
  - Calcular % de caída en cada etapa: (1 - CVR) * 100
  - Mencionar: "De cada 100 installs, X llegan a apertura y solo Y completan FTD"
  - Si hay CVR_install_apertura y CVR_apertura_FTD disponibles, compararlos
  - Comparar CVR_install_FTD del período (cvr_1_to_3 de funnel_etapas) vs objetivo si existe

BLOQUE: evolucion_conversiones
-------------------------------
OBJETIVO: Mostrar tendencia temporal de conversiones (FTD e installs)
DATASET A USAR: serie_diaria_agregada (YA tiene totales diarios globales, NO necesitas agrupar)

GRÁFICOS OBLIGATORIOS (mínimo 1, máximo 2):
  1) LINE_TIME_SERIES de FTD diario (OBLIGATORIO)
     - Dataset: serie_diaria_agregada (usar campo FTD por fecha directamente)
     - Highcharts: type="line", xAxis.type="datetime", xAxis.categories=[fechas ISO],
       series=[{name: "FTD Diario", data: [valores FTD por día]}]
     - Este dataset ya tiene la suma de todas las campañas por día
  2) LINE_TIME_SERIES de installs diarios (OBLIGATORIO en el mismo chart o separado)
     - Dataset: serie_diaria_agregada (usar campo install por fecha)
     - Highcharts: type="line", xAxis.type="datetime"
     - Puedes hacer 2 series en el mismo gráfico si las magnitudes son comparables

INSIGHTS OBLIGATORIOS:
  - Identificar fecha con pico máximo de FTD usando serie_diaria_agregada (ordenar desc por FTD)
  - Identificar fecha con mínimo FTD (excluir días con FTD=0 si los hay)
  - Explicar posible causa de mínimos: festivos, fines de semana (revisar día de la semana)
  - Calcular tendencia: comparar promedio de primeros 7 días vs últimos 7 días del período
  - Mencionar días totales con datos (contar filas de serie_diaria_agregada)

BLOQUE: resultados_generales
-----------------------------
OBJETIVO: Overview general del período con KPIs clave y tendencia
DATASETS A USAR:
  - totales_globales_periodo (para KPI_CARD en narrative)
  - serie_diaria_agregada (para gráficos de tendencia diaria)

CONTENIDO OBLIGATORIO:
  1) KPI_CARD en narrativa (NO es gráfico Highcharts, incluir en narrative):
     - Mostrar: Inversión total, FTD total, Installs totales, CPA_FTD promedio
     - Dataset: totales_globales_periodo
     - Formato: "En el período se invirtieron $X generando Y FTD con un CPA de $Z"
     - También mencionar CVR_install_FTD del período

  2) COMBO_BAR_LINE_DUAL o 2 LINE_TIME_SERIES separados (volumen + eficiencia):
     - Opción A (combo): Barras=FTD diario, Línea=CPA_FTD diario
     - Opción B (separado): Chart 1=LINE FTD diario, Chart 2=LINE CPA_FTD diario
     - Dataset: serie_diaria_agregada (usar campos FTD y cpa_FTD por fecha, YA calculados)
     - Si usas combo: yAxis[0] para FTD, yAxis[1] para CPA_FTD
     - NO necesitas agrupar, serie_diaria_agregada ya tiene totales diarios

INSIGHTS OBLIGATORIOS:
  - Calcular ROI implícito: FTD_total * valor_promedio_cliente (si disponible) / inversión_total
  - Identificar día con mejor CPA_FTD (ordenar serie_diaria_agregada asc por cpa_FTD)
  - Identificar día con peor CPA_FTD
  - Comparar inversión total vs presupuesto (si disponible en totales_globales_periodo)

BLOQUE: proyecciones
---------------------
OBJETIVO: Mostrar evolución semanal comparativa (NO calcular forecast futuro)
DATASET A USAR: serie_diaria_agregada (totales diarios globales)

GRÁFICOS OBLIGATORIOS (1 gráfico):
  1) COLUMN_CHART de comparación semanal (últimas 4 semanas)
     - Dataset: serie_diaria_agregada (agrupar por semana: dividir datos en 4 grupos de 7 días)
     - Highcharts: type="column", xAxis.categories=["Semana 1", "Semana 2", "Semana 3", "Semana 4"]
     - 2 series en el mismo gráfico:
       * Serie 1: FTD promedio por semana (sumar FTD de 7 días / 7)
       * Serie 2: CPA_FTD promedio ponderado por semana (sumar inversión semana / sumar FTD semana)
     - Usar doble eje Y: yAxis[0] para FTD promedio, yAxis[1] para CPA_FTD
     - Formato ejemplo:
       series: [
         {name: "FTD Promedio Diario", type: "column", data: [18.5, 22.3, 19.8, 24.1], yAxis: 0},
         {name: "CPA_FTD", type: "line", data: [62.5, 58.2, 55.8, 52.3], yAxis: 1}
       ]

INSIGHTS OBLIGATORIOS:
  - Comparar Semana 4 vs Semana 1: calcular % de mejora/empeoramiento en FTD promedio
  - Identificar mejor semana (mayor FTD promedio) y peor semana (menor FTD promedio)
  - Analizar si CPA_FTD mejoró o empeoró: comparar Semana 4 vs Semana 1
  - Mencionar EXPLÍCITAMENTE: "Basado en tendencia histórica semanal. NO se proyecta valor futuro por ciclo incompleto"
  - Indicar si tendencia es: "mejora sostenida semana a semana", "volatilidad sin patrón claro", o "deterioro progresivo"
  - Insight de eficiencia: "Si FTD sube y CPA baja = escalado eficiente. Si ambos suben = necesita optimización"

PROHIBIDO:
  - NO calcular proyecciones futuras ni forecast
  - NO inventar valores para fechas futuras o "Semana 5"
  - NO usar fórmulas de predicción
  - NO repetir el gráfico de FTD diario (ya existe en evolucion_conversiones)

BLOQUE: resumen_ejecutivo
--------------------------
OBJETIVO: Síntesis de alto nivel para stakeholders
GRÁFICOS OBLIGATORIOS (máximo 2):
  1) BAR_RANKING de top 5 campañas por FTD
     - Dataset: top_campanas_mes (tomar top 5)
     - Highcharts: type="bar", xAxis.categories=[nombres campañas], series.data=[FTD]
  2) LINE_TIME_SERIES de inversión diaria + FTD diario (2 series en mismo chart)
     - Dataset: serie_diaria_top (agrupar por fecha)
     - Highcharts: type="line", 2 series con diferentes colores
     - IMPORTANTE: Normalizar escalas o usar 2 ejes Y si magnitudes son muy diferentes
INSIGHTS OBLIGATORIOS:
  - Mencionar campaña más exitosa (nombre + FTD + CPA)
  - Mencionar campaña menos eficiente (alto CPA, bajo FTD)
  - Resumen ejecutivo: "Inversión total $X generó Y FTD a un CPA de $Z"

BLOQUE: aprendizajes
---------------------
OBJETIVO: Comparar performance entre Networks/plataformas
GRÁFICOS SUGERIDOS (1-2):
  1) BAR_RANKING de CPA_FTD por Network
     - Dataset: top_campanas_mes (agrupar por Network, calcular CPA_FTD promedio ponderado)
     - Highcharts: type="bar", xAxis.categories=[Networks], series.data=[CPA_FTD]
  2) COLUMN_CHART de FTD por Network
     - Dataset: top_campanas_mes (agrupar por Network, sumar FTD)
     - Highcharts: type="column"
INSIGHTS OBLIGATORIOS:
  - Comparar Google Ads vs Meta en términos de CPA y volumen
  - Identificar plataforma más eficiente y recomendar ajuste de budget
""".strip()


class TakenosAnalyticsProvider(AnalyticsProvider):
    """
    Analytics provider for Takenos.

    Microservice: takenos-dashboard-data
    Funnel: Install → Apertura Cuenta Exitosa → FTD
    Datasets: totales_globales_periodo, totales_por_region,
              serie_diaria_agregada, funnel_etapas,
              top_campanas_mes, serie_diaria_top
    """

    @property
    def service_url(self) -> str:
        return os.getenv(
            "TAKENOS_ANALYTICS_SERVICE_URL",
            os.getenv(
                "ANALYTICS_SERVICE_URL",
                "https://takenos-dashboard-data-715418856987.us-central1.run.app",
            ),
        )

    @property
    def analytics_explanation(self) -> str:
        return TAKENOS_EXPLANATION

    @property
    def metrics_glossary(self) -> str:
        return (
            "\n**Glosario de Métricas de Marketing:**\n"
            "- **Inversión**: Gasto publicitario total (USD)\n"
            "- **Install**: Número de instalaciones generadas por la campaña\n"
            "- **Apertura cuenta exitosa**: Registros completos después de instalar\n"
            "- **FTD (First Time Deposit)**: Primer depósito de usuario - métrica crítica de conversión final\n"
            "- **CPA_install**: Costo por instalación = inversión / install\n"
            "- **CPA_apertura_cuenta_exitosa**: Costo por apertura exitosa = inversión / apertura_cuenta_exitosa\n"
            "- **CPA_FTD**: Costo por primer depósito = inversión / FTD (KPI crítico)\n"
            "- **CVR_install_FTD**: Tasa de conversión = FTD / install\n"
            "\n**Funnel de Conversión:** Inversión → Install → Apertura → FTD"
        )

    @property
    def metrics_glossary_compact(self) -> str:
        return (
            "\n**Métricas clave:**\n"
            "- Inversión: gasto publicitario (USD)\n"
            "- Install: instalaciones\n"
            "- Apertura cuenta exitosa: registros completos\n"
            "- FTD: primer depósito (KPI crítico)\n"
            "- CPA_FTD: costo por FTD = inversión / FTD\n"
            "- CVR_install_FTD: tasa conversión = FTD / install\n"
            "- Funnel: Inversión → Install → Apertura → FTD"
        )
