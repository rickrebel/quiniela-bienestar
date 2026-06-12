# Métodos de agregación para el perfil "Ignorancia colectiva"

31 participantes predicen marcadores exactos (ej. 2-1). La literatura
distingue dos familias: agregar **cantidades** (goles por equipo, por
separado) y agregar **categorías** (el marcador completo o el signo
1X2). Catálogo con pros, contras y evidencia.

## Familia A — Agregación por cantidad (goles por equipo)

### A1. Media aritmética redondeada
Promedio de goles predichos para cada equipo, redondeado (1.7–0.9 → 2-1).

- **Pros**: el método con mejor respaldo empírico. En "Goal-line
  oracles" (Madsen, PLOS ONE 2025; Premier League 2022/23, multitudes
  de ~25 personas — escala casi idéntica a la nuestra) la media acertó
  50–52% de resultados y superó a *todos* los individuos en las 38
  jornadas (42–47%). La literatura de forecast combination (Armstrong)
  concluye que el promedio simple suele ganar a esquemas complejos.
- **Contras**: el redondeo destruye información (1.4 y 0.6 → 1-1);
  converge a marcadores conservadores (1-1, 1-0, 2-1) — nunca predice
  goleadas; sensible al primo que pone 7-0.

### A2. Mediana por equipo
Con 31 participantes (impar) siempre da un entero: cero redondeo.

- **Pros**: inmune a outliers y bromistas; es la "vox populi" original
  de Galton; robusta con muestras chicas.
- **Contras**: aún más conservadora que la media; en Madsen 2025 rindió
  peor (47.6% vs 52.1%).

### A3. Media recortada (trimmed mean) ~10–20%
Descartar los 3–6 valores extremos por cola y promediar el resto.

- **Pros**: robustez de la mediana + eficiencia de la media. Jose &
  Winkler (2008): recortes de 10–30% son "ligeramente más precisos que
  la media" y reducen el riesgo de errores grandes. Armstrong la
  recomienda con 5+ pronósticos.
- **Contras**: ganancia marginal; el % de recorte es arbitrario; sigue
  necesitando redondeo.

### A4. Poisson / Dixon-Coles sobre las medias de la multitud
Usar la media de goles como λ de dos distribuciones de Poisson; el
marcador agregado es el más probable de la matriz P(i)×P(j).
Dixon-Coles (1997) añade una corrección ρ para 0-0 y 1-1.

- **Pros**: usa los decimales completos (no redondea); fundamento
  sólido — los goles realmente siguen ~Poisson; produce de paso la
  probabilidad de cada marcador ("la multitud le da 12% al 2-1"),
  perfecto para visualizar. Dixon-Coles mejora ~15% sobre Poisson
  simple.
- **Contras**: el argmax cae casi siempre en 1-0/1-1/2-1; más difícil
  de explicar en el grupo de WhatsApp; requiere implementar el cálculo.

## Familia B — Agregación por categoría (votación)

### B1. Moda del marcador exacto
El marcador más repetido entre los 31.

- **Pros**: siempre es un marcador "votado por humanos", nunca un
  artefacto de redondeo; trivial de explicar.
- **Contras**: con ~20 marcadores plausibles, la moda puede ganar con
  4 votos (señal débil) y empatar seguido; trata 2-1 y 3-1 como
  categorías ajenas aunque son vecinas; hereda los sesgos de la
  mayoría (México).

### B2. Moda jerárquica: signo primero, marcador después
(1) Voto mayoritario sobre 1X2; (2) entre quienes votaron el signo
ganador, su marcador más frecuente; desempates por suma de goles
mediana.

- **Pros**: separa la decisión fácil (el signo: las multitudes aciertan
  ~50–54%) de la difícil (el exacto: techo ~10–12%); evita que una
  minoría compacta (8 votos al 1-1) le gane a una mayoría dispersa
  (16 votos a "gana A" repartidos en varios marcadores). Evidencia
  indirecta: seguir a la mayoría de tipsters amateur rindió +1.3% en
  68,339 eventos (Brown & Reade, EJOR 2019).
- **Contras**: heurística de quiniela, no método formal publicado; la
  segunda etapa opera sobre pocas personas.

## Familia C — Métodos avanzados (evaluados y descartados/aplazados)

### C1. Ponderación por desempeño histórico
Pesar a cada quien por sus puntos en jornadas previas.
**Descartado para el grupo**: inútil en jornada 1; con marcadores
exactos (~10% de acierto hasta para expertos) el track record converge
lentísimo y se sobreajusta a la suerte. Hallazgo de Brown & Reade: la
sabiduría viene de *toda* la multitud, no de los hábiles. Podría
añadirse como variante comparativa en fases finales.

### C2. "Surprisingly popular" (Prelec et al., Nature 2017)
Preguntar además "¿qué % crees que predirá lo mismo?" y elegir la
respuesta más popular *de lo esperado*. Reduce el error 21.3% vs
mayoría simple y es el único método que corrige mayorías sesgadas
(todos picando por México de corazón).
**Aplazado**: duplica la fricción del formulario y en deportes solo
funcionó con participantes conocedores (Lee et al. 2018). Candidato
divertido para la final.

### C3. Agregación bayesiana / extremización (Good Judgment Project)
Promedio de log-odds empujado lejos de 0.5. Ganó el torneo IARPA, pero
está diseñado para probabilidades de eventos binarios, no para
marcadores elicitied de legos. No aplica directo.

### C4. Mercado de predicción
El mejor agregador documentado en fútbol (Spann & Skiera 2009:
54.3% vs 42.6% de los tipsters), pero operativamente inviable para 31
familiares. Referencia, no opción.

## Método elegido (decisión 2026-06-11)

**Media recortada al 10% por equipo + matriz de Poisson** (A3 + A4,
sin la corrección Dixon-Coles para mantenerlo simple). El marcador
oficial es el argmax de la matriz; los empates de probabilidad se
resuelven a favor del signo con más probabilidad acumulada (el signo
vale 3 de los 5 puntos del pool y los empates no reciben bono de
diferencia) y, en última instancia, del local.

Implementación: `pool/services/aggregation.py` + command
`build_collective_profile`. Alternativas evaluadas y descartadas: moda
jerárquica (más narrable, menos información) y maximización de puntos
esperados contra la distribución empírica de los 31.

## Fuentes principales

- Madsen, "Goal-line oracles", PLOS ONE 2025 —
  https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0312487
- Jose & Winkler, "Simple robust averages of forecasts", IJF 2008 —
  https://www.sciencedirect.com/science/article/abs/pii/S0169207007000878
- Armstrong, "Combining Forecasts" —
  https://marketing.wharton.upenn.edu/wp-content/uploads/2020/07/96-JSA-Combining-Forecasts.pdf
- Brown & Reade, "The wisdom of amateur crowds", EJOR 2019 —
  https://www.sciencedirect.com/science/article/abs/pii/S0377221718306209
- Prelec, Seung & McCoy, Nature 2017 —
  https://www.nature.com/articles/nature21054
- Spann & Skiera, Journal of Forecasting 2009 —
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2479770
- Dixon-Coles (1997), implementación —
  https://dashee87.github.io/football/python/predicting-football-results-with-statistical-modelling-dixon-coles-and-time-weighting/
- Satopää et al., extremización —
  https://arxiv.org/pdf/1501.06943
- Groll et al., Mundial 2018 (híbrido + cuotas) —
  https://arxiv.org/pdf/1806.03208
