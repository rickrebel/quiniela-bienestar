# "Ignorancia colectiva": por qué este experimento tiene 120 años de evidencia a favor

*Documento de justificación del perfil agregado de la sanginiela.
Mundial 2026 · 31 participantes.*

## La tesis

Si 31 personas predicen marcadores de forma **independiente** y sus
predicciones se **agregan** con una regla estadística, el perfil
resultante tenderá a superar a la gran mayoría de los individuos — no
porque el grupo sea listo, sino porque los errores individuales, al ser
distintos entre sí, se cancelan al promediarse. La señal (lo que todos
saben a medias) queda; el ruido (lo que cada quien inventa) se anula.
Por eso el nombre "Ignorancia colectiva" es un chiste con trampa: la
ignorancia individual es justamente la materia prima del método.

## La evidencia fundacional

**Galton y el buey (1906).** En una feria de Plymouth, ~800 personas
pagaron por estimar el peso de un buey faenado. Francis Galton —que
esperaba demostrar la torpeza del vulgo— encontró que la mediana de las
apuestas fue 1,207 libras contra un peso real de 1,198: error menor al
1%. La media fue todavía mejor: 1,197 libras, error de **una libra**
(0.08%), mejor que cualquier experto ganadero presente. Lo publicó en
*Nature* (1907) como "Vox Populi". Nadie en esa feria era experto; el
agregado sí.

**Surowiecki (2004).** *The Wisdom of Crowds* sistematizó el fenómeno
con casos duros: el mercado bursátil identificó a Morton Thiokol (el
fabricante de los O-rings) como responsable del desastre del Challenger
en días, seis meses antes que la comisión presidencial; y en 1968 la
Marina de EE.UU. localizó el submarino hundido USS Scorpion a 220
yardas del punto real combinando bayesianamente las apuestas de varios
expertos — ninguno de los cuales, individualmente, acertó.

## La evidencia en fútbol

No es solo bueyes y submarinos; el efecto está medido en nuestro
deporte y a nuestra escala:

- **Madsen (PLOS ONE, 2025)**: multitudes de ~25 personas (casi
  nuestras 31) predijeron goles de la Premier League 2022/23. El
  agregado superó a **todos los participantes individuales en las 38
  jornadas**: ~50–52% de resultados correctos contra 42–47% del mejor
  humano. Ninguna persona le ganó al promedio ni una sola jornada
  sostenidamente.
- **Spann & Skiera (Journal of Forecasting, 2009)**: en tres temporadas
  de Bundesliga, los agregadores colectivos (mercados de predicción:
  54.3% de aciertos; cuotas: 53.7%) aplastaron a los pronosticadores
  individuales (42.6%) — apenas mejores que el azar (38%).
- **Brown & Reade (EJOR, 2019)**: sobre 68,339 eventos, seguir a la
  mayoría de una comunidad de tipsters amateur generó retorno positivo
  (+1.3%) donde los tipsters individuales perdían. Hallazgo clave para
  nosotros: la sabiduría "proviene de toda la multitud, no de los
  expertos" — los re gueyes suman.
- **Mundiales**: los mejores modelos académicos (Groll et al., ganador
  del torneo de predicción del Mundial 2018; el "bookmaker consensus"
  de Zeileis para 2022) no compiten contra la multitud: la incorporan,
  usando el consenso de cuotas como su mejor insumo.

## Más allá del deporte

- **Iowa Electronic Markets**: contra 964 encuestas en cinco elecciones
  presidenciales de EE.UU., el agregado del mercado estuvo más cerca
  del resultado el 74% de las veces (error medio: 1.34 puntos).
- **Good Judgment Project (Tetlock, torneo IARPA 2011–2015)**: equipos
  de pronosticadores comunes, bien agregados, fueron >30% más precisos
  que analistas de inteligencia **con información clasificada**. La
  agregación estadística fue parte central de la receta ganadora.
- **Prelec et al. (Nature, 2017)**: refinamientos sobre el voto simple
  reducen el error otro 21% — el campo sigue vivo y mejorando.

## Por qué funcionaría con nosotros (las cuatro condiciones)

Surowiecki identificó cuándo una multitud es sabia, y la sanginiela las
cumple casi por diseño:

1. **Diversidad**: 31 personas con niveles de afición distintos — del
   que ve todo hasta el que pica por colores de camiseta.
2. **Independencia**: cada quien envía en secreto antes del cierre;
   nadie ve las predicciones ajenas. (Por eso el perfil colectivo se
   calculará y revelará *solo después* del cierre de cada fase: Lorenz
   et al., PNAS 2011, demostraron que con que la gente vea el promedio
   de los demás, el efecto se destruye.)
3. **Descentralización**: conocimiento local disperso — quien sigue la
   J-League, quien vio las eliminatorias de África.
4. **Agregación**: la regla estadística del perfil (ver
   `aggregation_methods.md`).

## Honestidad intelectual: cuándo falla y qué esperamos

La agregación cancela errores *independientes*, no los compartidos. Si
los 31 inflamos a México por amor a la camiseta, el promedio hereda el
sesgo intacto (Babad & Katz 1991 documentaron el "wishful betting";
Madsen 2025 midió cómo multitudes enteras sobreestiman a los equipos
famosos). El perfil tampoco predecirá nunca una goleada sorpresa: los
agregados son estructuralmente conservadores.

Y calibremos: el marcador más común del fútbol (1-1) ocurre ~11% de
las veces; acertar exactos arriba del 12–15% ya es nivel élite. La
predicción del experimento no es "el perfil acertará todo", sino algo
más preciso y más interesante: **terminará en el tercio superior de la
tabla, arriba de la mayoría de nosotros, sin saber nada que no
sepamos.** Si 120 años de evidencia se sostienen, la Ignorancia
colectiva nos va a dar una lección de humildad — y si no, habremos
documentado una excepción divertida. El experimento gana en ambos
casos. Por eso no compite por los premios: no sería justo apostar
contra un fenómeno con este historial.

---

*Fuentes completas con URLs en `aggregation_methods.md`. Referencias
centrales: Galton, "Vox Populi", Nature (1907); Surowiecki, The Wisdom
of Crowds (2004); Madsen, PLOS ONE (2025); Spann & Skiera, Journal of
Forecasting (2009); Brown & Reade, EJOR (2019); Lorenz et al., PNAS
(2011); Prelec et al., Nature (2017); Tetlock & Gardner,
Superforecasting (2015).*
