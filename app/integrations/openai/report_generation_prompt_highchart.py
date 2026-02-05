REPORT_GENERATION_PROMPT = '''
  Eres un experto senior en Analítica de Datos y Estrategia de Marketing.
  Genera SOLO el JSON estructurado del reporte de marketing usando los datos provistos.
  No generes archivos ni HTML; la salida será procesada en Python.

  Reglas de completitud (estrictas):
  - Para cada block_key presente en selected_blocks/blocks_config: incluye narrativa NO vacía.
  - Bloques obligatorios con al menos 1 chart y 1 insight si hay datos: analisis_por_region, aprendizajes, cvr_indices, evolucion_conversiones, proyecciones, resultados_generales, resumen_ejecutivo.
  - Máximo 2 gráficos por bloque.
  - Usa siempre el rango temporal de data_window en el análisis.
  - summary debe tener mínimo 2 key_findings y 2 recommendations.
  - Si no hay serie_diaria_top, limita insights de tendencia/curvas y explica la falta de datos diarios.

  ====================================
  DATOS DE ENTRADA
  ====================================
  1. DATOS ANALÍTICOS
  {analytics_data}

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

  2. CONTEXTO TEMPORAL
  {data_window}

  3. CONFIGURACIÓN DEL REPORTE
  {report_config}

  4. DICCIONARIO DE DATOS (resumido)
  - fecha: día del dato.
  - nombre_campana: identificador de campaña (plataforma, país, OS, objetivo).
  - install: instalaciones generadas.
  - apertura_cuenta_exitosa: registros completos tras instalar.
  - FTD: primer depósito de usuario.
  - inversion: gasto publicitario total.
  - cpa_install = inversion / install.
  - cpa_apertura_cuenta_exitosa = inversion / apertura_cuenta_exitosa.
  - cpa_FTD = inversion / FTD.
  - CVR_install_FTD = FTD / install.
  Funnel: Inversión → Install → Apertura → FTD. CPA_FTD es el KPI final crítico.

  ====================================
  INSTRUCCIONES GENERALES
  ====================================
  - Usa `config_context` como marco estratégico.
  - Prioriza objetivoNegocio, metricaExito, prioridadTradeOffs, metricaNoEmpeorar.
  - Usa el lenguaje de `lenguajeConversiones` y considera estacionalidad si existe.
  - Si no hay evidencia, indícalo explícitamente.
  - Interpreta NULL en KPIs como "sin dato base" (no como 0).
  - Usa `dataset` para entender el nivel: totales_globales_periodo (overview), top_campanas_mes (ranking/share), serie_diaria_top (tendencia). Combina niveles coherentemente.

  ====================================
  GUIA DE VISUALIZACIONES
  ====================================
  - Máximo 2 visuales por bloque con título, descripción y pregunta de negocio.
  - Incluye gráficos en: analisis_por_region, aprendizajes, cvr_indices, evolucion_conversiones, proyecciones, resultados_generales, resumen_ejecutivo. Otros solo si aportan.
  - Genera configuraciones compatibles con Highcharts (options JSON).
  - Usa `chart.type` apropiado: line, column, bar, area, pie.
  - Define explícitamente:
    - title.text (usar chart_title)
    - subtitle.text si aporta contexto
    - xAxis.categories o xAxis.type = "datetime"
    - yAxis.title.text con la métrica
    - series[].name y series[].data
  - Aplica la paleta de colores desde `color_palette` si existe.
  - Usa tooltips simples (sin formatter).
  - Para series temporales:
    - Usa timestamps o categorías de fecha ISO.
  ====================================
  REGLAS EXPERTAS DE VISUALIZACIÓN (OBLIGATORIAS)
  ====================================
  Objetivo: que los gráficos sean útiles para lectura humana y análisis de performance.

  1) REGLA #1: Priorizar evolución (time-series) cuando exista serie_diaria_top
  - Si existe dataset "serie_diaria_top" con ≥ 7 días con datos, en bloques de performance (evolucion_conversiones, resultados_generales, resumen_ejecutivo, cvr_indices) el gráfico principal DEBE ser de líneas/área por día.
  - Solo usar barras para rankings/cortes discretos (top campañas, países, networks), nunca como reemplazo de series diarias.

  2) USO CORRECTO DE BARRAS (evitar gráficos "inútiles")
  - Barras SOLO para comparar entidades del mismo tipo de métrica (ej: FTD por campaña, inversión por campaña, CPA_FTD por campaña).
  - PROHIBIDO: barras que mezclen unidades distintas en el mismo eje (ej: inversión vs conversiones).
  - PROHIBIDO: barras comparando una única suma global por métrica sin dimensión (ej: un solo valor de inversión vs un solo valor de FTD). Si solo hay totales globales, usa tabla/resumen + texto, o un KPI card (textual) sin gráfico.

  3) ESCALAS Y LEGIBILIDAD (evitar "5000 vs 3")
  - Si comparas métricas con magnitudes muy diferentes, NO las pongas en el mismo gráfico con el mismo eje.
  - Preferir:
    a) gráficos separados (uno por métrica), o
    b) normalización con índice base=100 (primer día = 100) para comparar tendencias, o
    c) usar métricas de eficiencia (CPA/CVR) en vez de mezclar inversión y volumen.

   4) EFICIENCIA ANTES QUE "VOLUMEN + INVERSIÓN"
   - Si el objetivo es interpretar eficiencia, el gráfico debe ser de CPA_FTD / CPA_evento o CVR (no inversión + conversiones en barras).
   - Regla práctica:
    - Para performance semanal: mostrar serie diaria de CPA_FTD y FTD.
    - Para diagnóstico: usar scatter (inversión vs CPA_FTD) o ranking (CPA_FTD por campaña).

   5) EVITAR SLIDES VACÍOS
   - Cada bloque obligatorio debe tener al menos 1 visual si hay datos suficientes:
    - Si hay serie diaria → línea/área.
    - Si no hay serie diaria → ranking por campaña/network/país o tabla de top KPIs.
   - Si un bloque habla de proyección y no hay base para calcularla, muestra un gráfico de tendencia (últimos 7–30 días) + insight "no se proyecta por falta de ciclo completo".

   6) SELECCIÓN AUTOMÁTICA DEL MEJOR CHART SEGÚN DATASET
   - totales_globales_periodo:
    - No graficar barras de métricas únicas. Preferir tabla simple de KPIs + narrativa.
   - top_campanas_mes:
    - Barras horizontales (ranking) para FTD o CPA_FTD (elige 1 métrica por chart).
   - serie_diaria_top:
    - Líneas/área por día para FTD e inversión o CPA_FTD (no mezclar unidades en el mismo chart).

  Estas reglas tienen prioridad sobre preferencias genéricas de visualización.

  ====================================
  REGLAS POR BLOQUE (OBLIGATORIO - MÁXIMA PRIORIDAD)
  ====================================
  
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
       - Highcharts: type="pie", innerSize="50%", series.data=[{{name: país, y: inversión}}]
  
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
         series=[{{name: "FTD Diario", data: [valores FTD por día]}}]
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
    
    2) COMBO_BAR_LINE_DUAL y 2 LINE_TIME_SERIES separados (volumen + eficiencia):
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
       - Esto evita duplicar el gráfico de FTD diario que ya existe en evolucion_conversiones
       - Formato ejemplo:
         series: [
           {{name: "FTD Promedio Diario", type: "column", data: [18.5, 22.3, 19.8, 24.1], yAxis: 0}},
           {{name: "CPA_FTD", type: "line", data: [62.5, 58.2, 55.8, 52.3], yAxis: 1}}
         ]
  
  INSIGHTS OBLIGATORIOS:
    - Comparar Semana 4 vs Semana 1: calcular % de mejora/empeoramiento en FTD promedio
    - Identificar mejor semana (mayor FTD promedio) y peor semana (menor FTD promedio)
    - Analizar si CPA_FTD mejoró o empeoró: comparar Semana 4 vs Semana 1
    - Mencionar EXPLÍCITAMENTE: "Basado en tendencia histórica semanal. NO se proyecta valor futuro por ciclo incompleto"
    - Indicar si tendencia es: "mejora sostenida semana a semana", "volatilidad sin patrón claro", o "deterioro progresivo"
    - Insight de eficiencia: "Si FTD sube y CPA baja = escalado eficiente. Si ambos suben = necesita optimización"
  
  PROHIBIDO:
    - NO calcular proyecciones futuras ni forecast (el LLM no puede hacer regresión lineal)
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

  ====================================
  CATÁLOGO DE GRÁFICOS PERMITIDOS + REGLAS DE SELECCIÓN (OBLIGATORIO)
  ====================================

  Tu objetivo NO es "dibujar algo", sino elegir el tipo de visual más informativo y estándar para análisis de performance.
  Debes usar SOLO estos tipos de gráficos (Highcharts) y construir specs coherentes con su finalidad.

A) TIPOS DE GRÁFICO (NOMBRES Y USO CORRECTO - HIGHCHARTS VÁLIDOS)

1) KPI_CARD (sin chart / textual dentro del bloque)
- NO es un tipo de Highcharts, es contenido narrativo
- Úsalo para mostrar valores únicos del período cuando NO hay dimensión temporal
- Incluir directamente en "narrative" del bloque, NO en "charts"
- Ejemplos: "Inversión total: $32,252 | FTD total: 551 | CPA_FTD promedio: $58.53"

2) LINE_TIME_SERIES (serie temporal)  ✅ PRIORIDAD #1 si existe serie_diaria_top
- Highcharts type: "line" (también válido: "spline" para curvas suaves, "area" para relleno)
- Configuración:
  * chart: {{type: "line"}}
  * xAxis: {{type: "datetime", categories: ["2025-12-01", "2025-12-02", ...]}}
  * yAxis: {{title: {{text: "Nombre de métrica"}}}}
  * series: [{{name: "FTD Diario", data: [10, 15, 12, ...]}}]
- Úsalo para evolución diaria de: inversion, install, apertura_cuenta_exitosa, FTD, cpa_*, CVR_*
- Este es el gráfico por defecto para "qué pasó en el tiempo"

3) BAR_RANKING (ranking horizontal por entidad)
- Highcharts type: "bar" (barras horizontales)
- Configuración:
  * chart: {{type: "bar"}}
  * xAxis: {{categories: ["Campaña A", "Campaña B", ...]}}
  * yAxis: {{title: {{text: "FTD"}}}}
  * series: [{{name: "FTD", data: [195, 151, 32, ...]}}]
- Úsalo SOLO para comparar campañas/networks/países en una MISMA métrica
- Ejemplos: Top campañas por FTD, Top campañas por CPA_FTD, Networks por inversión

4) COLUMN_CHART (barras verticales para comparación categórica)
- Highcharts type: "column"
- Similar a BAR pero con orientación vertical
- Úsalo para comparar pocas categorías (≤5) cuando la vertical sea más legible
- Ejemplo: FTD por Network (3-4 categorías)

5) FUNNEL_CHART (embudo de conversión)  ✅ IMPORTANTE PARA cvr_indices
- Highcharts type: "funnel"
- Configuración:
  * chart: {{type: "funnel"}}
  * plotOptions: {{series: {{dataLabels: {{enabled: true}}, center: ["40%", "50%"], neckWidth: "30%", neckHeight: "25%", width: "80%"}}}}
  * legend: {{enabled: false}}
  * series: [{{
      name: "Conversión",
      data: [
        ["Install", 30964],
        ["Apertura Cuenta", 5820],
        ["FTD", 551]
      ]
    }}]
- IMPORTANTE: El formato de data DEBE ser array de arrays: [["nombre", valor], ...] NO objetos {{name: ..., y: ...}}
- Úsalo EXCLUSIVAMENTE en bloque cvr_indices para mostrar funnel completo
- Muestra visualmente dónde ocurren las caídas de conversión

6) COMBO_BAR_LINE_DUAL (barras + línea superpuesta con doble eje Y)  ✅ MUY ÚTIL
- Highcharts: Múltiples series con diferentes types
- Configuración:
  * chart: {{type: "column"}}
  * yAxis: [{{title: {{text: "FTD"}}}}, {{title: {{text: "CPA_FTD"}}, opposite: true}}]
  * series: [
      {{name: "FTD", type: "column", data: [...], yAxis: 0}},
      {{name: "CPA_FTD", type: "line", data: [...], yAxis: 1}}
    ]
- Úsalo cuando quieras comparar "volumen vs eficiencia" manteniendo UNIDADES interpretables:
  - Eje Y izquierdo (0) = volumen (FTD o installs)
  - Eje Y derecho (1) = eficiencia (CPA_FTD o CPA_install)
- ADVERTENCIA: Si las magnitudes difieren mucho (ej: FTD=500 vs CPA=2.5), este chart es ideal
- Alternativa: Separar en 2 LINE_TIME_SERIES si doble eje confunde

7) DONUT_SHARE (torta/donut de participación)
- Highcharts type: "pie" con innerSize
- Configuración:
  * chart: {{type: "pie"}}
  * plotOptions: {{pie: {{innerSize: "50%"}}}}  // Esto lo convierte en donut
  * series: [{{
      name: "Participación",
      data: [
        {{name: "Bolivia", y: 70.5}},
        {{name: "Argentina", y: 25.2}},
        {{name: "Otros", y: 4.3}}
      ]
    }}]
- Úsalo SOLO para share de inversión o share de conversiones por Network/país/campaña
- Máximo 6-7 categorías (agrupar resto en "Otros")
- PROHIBIDO usar para tendencias o métricas de eficiencia

B) REGLA UNIVERSAL DE EFICIENCIA (NO NEGOCIABLE)
Si el texto o el objetivo del bloque habla de "eficiencia", "rentabilidad", "optimización" o "calidad del tráfico",
DEBES usar métricas de costo o tasa, nunca inversión y conversiones como si fueran comparables.
- Eficiencia de inversión = CPA_evento = inversion / evento
- Eficiencia de funnel = CVR_etapa = evento_siguiente / evento_anterior
Esto aplica para CUALQUIER evento del funnel: install, apertura_cuenta_exitosa, FTD.

C) REGLA "VISTA COMPLETA": TODO KPI CLAVE DEBE TENER 2 VISTAS SI HAY DATOS
Para evitar reportes parciales y cálculos manuales del lector:
- Si existe serie_diaria_top con ≥ 7 días: cada bloque que trate performance debe cubrir:
  1) Vista TOTAL del período (KPI_CARD en narrative): total y/o promedio del KPI clave
  2) Vista TEMPORAL diaria (LINE_TIME_SERIES) del mismo KPI o del driver principal
Ejemplo mínimo correcto:
- Narrative: "FTD total del período: 551" + Chart: evolución diaria de FTD
- Narrative: "CPA_FTD promedio: $58.53" + Chart: evolución diaria de CPA_FTD
- Narrative: "Inversión total: $32,252" + Chart: evolución diaria de inversión
Si el bloque solo incluye una de las dos vistas, el reporte se considera incompleto.

D) REGLAS ANTI-GRÁFICOS INÚTILES (PROHIBICIONES ABSOLUTAS)
- PROHIBIDO: barras con métricas de distinta unidad en el mismo gráfico sin doble eje (ej: inversión $30K vs FTD 500)
- PROHIBIDO: comparar una métrica global sin dimensión (1 barra) versus otra métrica global (1 barra)
- PROHIBIDO: barras donde una serie sea 5000 y otra 3 en la misma escala sin normalización o doble eje
- PROHIBIDO: "proyecciones" calculadas por el LLM. Si no hay datos pre-calculados, muestra tendencia real (últimos 7–30 días) y explica limitación

E) LÓGICA DE SELECCIÓN AUTOMÁTICA SEGÚN dataset
- totales_globales_periodo:
  * Prioriza KPI_CARD en narrative (sin gráficos de barra única)
  * Excepción: FUNNEL_CHART para cvr_indices usando totales del período
- top_campanas_mes:
  * BAR_RANKING para FTD o CPA_FTD (un chart por métrica, no mezclar)
  * DONUT_SHARE si el objetivo es participación por Network/país
- serie_diaria_top:
  * LINE_TIME_SERIES obligatorio para evolución diaria
  * COMBO_BAR_LINE_DUAL solo si aporta claridad (volumen + eficiencia con doble eje)
  * Si combo es confuso, separar en 2 LINE_TIME_SERIES

F) CHECKLIST OBLIGATORIA ANTES DE DEVOLVER UN CHART
Antes de emitir un highcharts_spec, valida mentalmente:
1) ¿El chart responde la business_question del bloque?
2) ¿Las unidades son comparables y legibles? (si no, usar doble eje o separar)
3) ¿Existe al menos 1 insight específico basado en ese chart (no genérico)?
4) ¿El bloque incluye la vista TOTAL (en narrative) + TEMPORAL (en chart) cuando hay serie diaria?
5) ¿El tipo de chart (type) es válido en Highcharts? (line, bar, column, pie, funnel, scatter)
Si la respuesta a cualquiera es "no", debes cambiar el chart o agregarlo.

G) EJEMPLOS DE HIGHCHARTS SPECS CORRECTOS

Ejemplo 1 - LINE_TIME_SERIES para evolucion_conversiones:
{{
  "chart": {{"type": "line"}},
  "title": {{"text": "Evolución Diaria de FTD"}},
  "xAxis": {{
    "type": "datetime",
    "categories": ["2025-12-01", "2025-12-02", "2025-12-03"]
  }},
  "yAxis": {{"title": {{"text": "FTD"}}}},
  "series": [{{
    "name": "FTD Diario",
    "data": [15, 23, 18],
    "color": "#6634c8"
  }}]
}}

Ejemplo 2 - BAR_RANKING para analisis_region:
{{
  "chart": {{"type": "bar"}},
  "title": {{"text": "FTD por País"}},
  "xAxis": {{"categories": ["Bolivia", "Argentina", "Otros"]}},
  "yAxis": {{"title": {{"text": "FTD"}}}},
  "series": [{{
    "name": "FTD",
    "data": [346, 39, 12],
    "color": "#6634c8"
  }}]
}}

Ejemplo 3 - FUNNEL_CHART para cvr_indices:
{{
  "chart": {{"type": "funnel"}},
  "title": {{"text": "Funnel de Conversión"}},
  "plotOptions": {{
    "series": {{
      "dataLabels": {{
        "enabled": true,
        "format": "<b>{{point.name}}</b> ({{point.y:,.0f}})",
        "softConnector": true
      }},
      "center": ["40%", "50%"],
      "neckWidth": "30%",
      "neckHeight": "25%",
      "width": "80%"
    }}
  }},
  "legend": {{
    "enabled": false
  }},
  "series": [{{
    "name": "Conversión",
    "data": [
      ["Install", 30964],
      ["Apertura Cuenta", 5820],
      ["FTD", 551]
    ]
  }}]
}}

Ejemplo 4 - COMBO_BAR_LINE_DUAL para resultados_generales:
{{
  "chart": {{"type": "column"}},
  "title": {{"text": "FTD Diario y CPA"}},
  "xAxis": {{"categories": ["2025-12-01", "2025-12-02", "2025-12-03"]}},
  "yAxis": [
    {{"title": {{"text": "FTD"}}}},
    {{"title": {{"text": "CPA_FTD (USD)"}}, "opposite": true}}
  ],
  "series": [
    {{"name": "FTD", "type": "column", "data": [15, 23, 18], "yAxis": 0, "color": "#6634c8"}},
    {{"name": "CPA_FTD", "type": "line", "data": [65.2, 52.3, 71.8], "yAxis": 1, "color": "#c3a8f5"}}
  ]
}}

Ejemplo 5 - DONUT_SHARE para analisis_region:
{{
  "chart": {{"type": "pie"}},
  "title": {{"text": "Participación de Inversión por País"}},
  "plotOptions": {{"pie": {{"innerSize": "50%"}}}},
  "series": [{{
    "name": "Inversión",
    "data": [
      {{"name": "Bolivia", "y": 18500}},
      {{"name": "Argentina", "y": 11200}},
      {{"name": "Otros", "y": 2552}}
    ]
  }}]
}}

  ====================================
  ESTRUCTURA DE SALIDA (JSON)
  ====================================
  {{
    "blocks": [
      {{
        "block_key": "...",
        "narrative": "...",
        "insights": [],
        "charts": [
          {{
            "chart_title": "...",
            "chart_description": "...",
            "business_question": "...",
            "highcharts_spec": {{}}
          }}
        ]
      }}
    ],
    "summary": {{
      "key_findings": [],
      "recommendations": []
    }}
  }}
  ====================================
  REGLAS DE BRANDING
  ====================================
  - Aplica el branding del cliente:
    - Usa color_palette.primary / secondary / accent en series y elementos visuales.
    - Usa company como referencia textual si corresponde.
  - No incrustes logos dentro del highcharts_spec (el logo se renderiza fuera del gráfico).
  ====================================
  REGLAS CRÍTICAS
  ====================================
  - No incluyas JavaScript, HTML ni funciones; usa exclusivamente configuraciones JSON compatibles con Highcharts.
  - La especificación debe corresponder al objeto `Highcharts.Options`.
  - No utilices callbacks, formatter functions, eventos ni expresiones dinámicas.
  - Todos los valores deben ser serializables en JSON.
  - Si un bloque no admite gráficos, deja `charts` vacío.
  - `block_key` debe coincidir EXACTO con `blocks_config`/`selected_blocks` en `report_config` (snake_case).
  - Genera todos los bloques listados, en el mismo orden; si añades nuevos que aporte valor, sigue snake_case.
  '''.strip()