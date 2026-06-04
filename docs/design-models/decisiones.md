# Decisiones de diseño de modelos

Este documento registra las decisiones **no obvias** o **controversiales**
tomadas durante la sesión de rediseño de modelos del proyecto. Su propósito es
que Ricardo las revise con calma: cada sección explica el contexto, qué se
decidió, qué alternativa se descartó y por qué, y deja marcado lo que sigue
**PENDIENTE DE REVISIÓN**.

---

## 1. Dos apps: `pool` y `tournament`

**Contexto.** El proyecto vivía en una sola app `quiniela` que mezclaba dos
dominios distintos: los usuarios y sus pronósticos por un lado, y los datos
deportivos del torneo por otro.

**Decisión.** Separar en dos apps con dependencia unidireccional:

- `pool` (antes `quiniela`): usuarios y pronósticos.
- `tournament` (nueva): datos deportivos (`Stadium`, `Stage`, `Team`,
  `Match`).

`pool` importa de `tournament`, nunca al revés. El usuario custom se declara
con `AUTH_USER_MODEL = "pool.User"`.

Como el proyecto está en fase inicial (sin datos en producción), las
migraciones se resetearon desde cero en lugar de migrar incrementalmente.

**Alternativa descartada.** Mantener una sola app. Se descartó porque la mezcla
de dominios dificulta el mantenimiento como desarrollador solo y oscurece qué
parte del sistema es "verdad deportiva" (sincronizable con fuentes externas) y
qué parte es "datos de los jugadores".

---

## 2. Convención `home`/`away` en vez de `a`/`b`

**Contexto.** El modelo viejo usaba `a`/`b` para distinguir a los dos equipos
de un partido y para los goles del pronóstico (`goals_a`/`goals_b`).

**Decisión.** Adoptar la convención estándar de football-data.org (FD):

- En `Match`: `home_team`/`away_team`, `home_goals`/`away_goals`.
- En `Prediction`: `home_goals`/`away_goals` (antes `goals_a`/`goals_b`).

Esto alinea el modelo con la fuente de datos externa y elimina la ambigüedad de
qué equipo es "a" y cuál "b".

**Alternativa descartada.** Conservar `a`/`b`. Se descartó porque obligaba a un
mapeo mental constante contra la API de FD y porque `home`/`away` es la
convención universal en datos de fútbol.

**PENDIENTE DE REVISIÓN.** El frontend (plantillas DTL, `static/submit.js` y
las vistas a fondo) **aún usa `a`/`b`**. La realineación a `home`/`away` se hará
en otra sesión.

---

## 3. Tiempo almacenado en UTC; hora local derivada por offset

**Contexto.** Los partidos ocurren en estadios de tres países (EE. UU.,
Canadá, México) con husos distintos, y los familiares que juegan están en
varias zonas (Ensenada, España, etc.). `USE_TZ` ya estaba en `True`.

**Decisión.** `Match.datetime` (un `DateTimeField`) guarda la fecha y hora en
**UTC**. La hora local del estadio se deriva en tiempo de presentación a partir
de `Stadium.utc_offset`, un entero (p. ej. `-6`) tomado tal cual de openfootball
(OF).

**Alternativa descartada.** Guardar zonas horarias IANA (p. ej.
`America/Mexico_City`) por estadio. Se descartó por sobre-ingeniería para una
quiniela familiar: los offsets que ya trae OF reflejan correctamente el horario
de verano de junio/julio de 2026, y la conversión a otras zonas (Ensenada,
España) es un problema de **visualización**, no de almacenamiento. Guardando en
UTC, cualquier zona se calcula al vuelo.

---

## 4. `Stage`: 6 filas, no 7 (FINAL absorbe el tercer lugar)

**Contexto.** football-data.org expone 7 claves de fase, separando
`THIRD_PLACE` y `FINAL`. Para la quiniela conviene tratar ambos como una sola
fase de cierre.

**Decisión.** Modelar 6 fases. Las claves FD `THIRD_PLACE` y `FINAL` se
colapsan en una única fase `FINAL` (chip "finales"). El partido por el tercer
lugar y la final se distinguen por `Match.of_number`:

- `103` = partido por el tercer lugar.
- `104` = final.

Se definen constantes `THIRD_PLACE_NUMBER` / `FINAL_NUMBER` y propiedades
`is_final` / `is_third_place` en el modelo `Match`.

**Falso amigo importante (terminología ES ↔ FD).** En español, "dieciseisavos"
= Round of 32 = clave FD `LAST_32` (¡**no** `LAST_16`!); "octavos" = Round of 16
= clave FD `LAST_16`. Hay que tener cuidado de no confundirlos.

Las 6 fases, con `(key, name, short_name, order)`:

| key | name | short_name | order |
|---|---|---|---|
| `GROUP_STAGE` | Fase de grupos | grupos | 1 |
| `LAST_32` | Dieciseisavos de final | 16avos | 2 |
| `LAST_16` | Octavos de final | octavos | 3 |
| `QUARTER_FINALS` | Cuartos de final | cuartos | 4 |
| `SEMI_FINALS` | Semifinales | semis | 5 |
| `FINAL` | Finales | finales | 6 |

**Alternativa descartada.** Crear 7 fases siguiendo a FD al pie de la letra. Se
descartó porque "tercer lugar" no es una fase de eliminación real, sino un
partido extra dentro del cierre del torneo; tratarlo como fase aparte complicaba
la navegación por chips sin aportar valor.

**PENDIENTE DE REVISIÓN.** Los colores hex de cada fase son **tentativos**;
Ricardo los ajustará.

---

## 5. `decided_by` como CHOICES (no FK)

**Contexto.** Un partido de eliminatoria puede resolverse en tiempo regular,
tiempo extra o penales.

**Decisión.** `decided_by` es un campo con CHOICES de tres valores fijos:
`REGULAR` / `EXTRA_TIME` / `PENALTY_SHOOTOUT`. En FD, `score.duration` provee
este valor.

Cuando hubo penales, `score.fullTime` de FD queda **empatado**; el marcador de
la tanda se guarda aparte en `home_penalties` / `away_penalties`.

**Alternativa descartada.** Modelar `decided_by` como FK a un modelo/tabla. Se
descartó por sobre-ingeniería: es un enum cerrado de tres valores que no tiene
atributos propios ni va a crecer.

**Nota relevante para el sync futuro.** El detalle tiro a tiro de la tanda y las
tarjetas (`bookings`) **no** vienen en el endpoint de lista de partidos de FD,
solo en el endpoint de detalle `/matches/{id}`. Esto importará al implementar la
sincronización de resultados en vivo.

---

## 6. Tarjetas: totales por equipo

**Contexto.** Se quiere poder mostrar tarjetas amarillas y rojas por partido.

**Decisión.** Cuatro campos nulables en `Match`: `home_yellow`, `away_yellow`,
`home_red`, `away_red`. Son **totales por equipo**, pensados para llenarse
contando el arreglo `bookings[]` del endpoint de detalle de FD.

**Alternativa descartada (implícita).** Modelar cada tarjeta como una fila
(jugador, minuto, tipo). Se descartó porque la quiniela no necesita el detalle
por incidencia; basta el agregado por equipo.

---

## 7. `Stadium` obligatorio en `Match`; sin modelo País

**Contexto.** Los 104 partidos del Mundial 2026 traen su campo `ground`
(estadio) en OF.

**Decisión.**

- La FK `Match → Stadium` es **NOT NULL** y con `on_delete=PROTECT` (no se
  borra un estadio que tiene partidos).
- No hay modelo `Country`. `Stadium.country` es un campo con CHOICES limitado a
  las tres sedes: `us` / `ca` / `mx`.
- `Stadium.coords` se guarda como el string crudo que entrega OF (sin parsear a
  lat/long).

**Alternativa descartada.** Modelar un `Country` propio y/o parsear coordenadas
a campos numéricos. Se descartó por sobre-ingeniería: con tres países fijos un
CHOICES basta, y las coordenadas no se usan para cálculos, solo (eventualmente)
para mostrar.

---

## 8. Sin modelo `Area`; solo `Team.confederation`

**Contexto.** FD expone un recurso `Area` jerárquico (continente, país, etc.),
pesado y con relaciones anidadas.

**Decisión.** Descartar `Area`. Se guarda únicamente `Team.confederation`, un
CHOICES con los seis valores: `UEFA` / `CONMEBOL` / `CONCACAF` / `CAF` / `AFC` /
`OFC`, tomado del campo `confed` de OF. **No** se guarda `continent`.

**Alternativa descartada.** Importar la jerarquía `Area` de FD. Se descartó por
sobre-ingeniería: la quiniela solo necesita saber a qué confederación pertenece
un equipo, y eso ya viene plano en OF.

---

## 9. `Team.group_name` como CHOICES; standings por ORM

**Contexto.** El modelo viejo tenía campos calculados en el equipo (puntos,
ganados, empates, goles, tarjetas) y la noción de grupo como dato.

**Decisión.**

- El grupo se modela como `Team.group_name`, un CHOICES de `A` a `L`. Vive
  **solo** en `Team`; en `Match` el grupo se **deriva** (no se denormaliza).
- Se eliminan los campos calculados del modelo viejo (points, won_games, draws,
  goles, tarjetas). Los standings se calcularán con **agregaciones del ORM**, no
  se guardan.

**Alternativa descartada.** Crear un modelo `Group` con FK desde `Team`. Se
descartó porque los grupos no tienen atributos propios (son meras etiquetas
A–L); un CHOICES es suficiente y evita una tabla vacía de contenido.

**Alternativa descartada (campos calculados).** Persistir puntos y estadísticas
en `Team`. Se descartó porque son datos derivables de los partidos: guardarlos
introduce riesgo de desincronización. Se calculan on-the-fly con el ORM.

---

## 10. `Team.name_es`: nombre corto en español

**Contexto.** Los nombres oficiales de las fuentes son largos o están en inglés
(p. ej. "República Democrática del Congo", "Czech Republic", "Qatar").

**Decisión.** Añadir `Team.name_es`, un nombre corto en español para mostrar en
la UI ("Congo", "Chequia", "Catar", etc.). Los valores viven en un JSON manual
en `db/jsons/manual/team_names_es.json`, indexado por `fifa_code`.

**Alternativa descartada (implícita).** Derivar el nombre en español
automáticamente o dejar el nombre de la fuente. Se descartó porque las
traducciones cortas son criterio editorial humano (qué tan corto, qué grafía) y
conviene curarlas a mano.

---

## 11. Join OF ↔ FD de equipos por código (`fifa_code` == `tla`)

**Contexto.** Hay que cruzar los equipos de openfootball (seed base) con los de
football-data.org (que aporta `fd_id` y resultados).

**Decisión.** El join se hace por **código**: `fifa_code` de OF == `tla` de FD.
El **único** código que difiere es Uruguay: OF dice `URU`, FD dice `URY`. Se
resuelve con un override de un solo elemento `{"URU": "URY"}` en el command de
carga.

**Por qué código y no nombre.** Los nombres difieren en 5 casos (Czech
Republic/Czechia, Bosnia & Herzegovina/Bosnia-Herzegovina, USA/United States,
Cape Verde/Cape Verde Islands, DR Congo/Congo DR), pero en todos esos el `tla`
sí empata. Usar el código como llave evita esa fricción de nombres; basta el
único override de Uruguay.

---

## 12. Mapeo OF ↔ FD de partidos (`of_number` ↔ `fd_id`)

**Contexto.** Cada partido tiene un identificador en cada fuente: `of_number`
(de OF) y `fd_id` (de FD). Hay que cruzarlos 1:1 para los 104 partidos.

**Decisión.** El cruce se hace por la pareja **(datetime UTC + `tla` del equipo
local)**, aplicando el override URU → URY. Con eso los 104 partidos cruzan 1:1.

Sobre `of_number`:

- En eliminatorias se toma el campo `num` de OF (73..104).
- En fase de grupos OF no trae número, así que se asignan `1..72` por **orden
  cronológico**. **No** son necesariamente los números oficiales FIFA.

**PENDIENTE DE REVISIÓN.** Si Ricardo quiere usar los números oficiales FIFA de
la fase de grupos en lugar del orden cronológico.

---

## 13. Fuentes de datos y organización de archivos

**Contexto.** El proyecto combina dos fuentes externas y debe poder sembrarse de
forma reproducible y offline.

**Decisión.**

- **OF (openfootball)** es el **seed base**: estructura del torneo, estadios,
  banderas, grupos. Se consulta una sola vez y se commitea en
  `db/jsons/of/{worldcup,stadiums,teams}.json`.
- **FD (football-data.org)** aporta el `fd_id` y los resultados. Se commitearon
  snapshots en `db/jsons/fd/{teams,matches}.json` para un seed offline
  reproducible.
- Los JSON viejos se movieron a `db/jsons/legacy/`.
- Los **resultados en vivo** se obtendrán a futuro vía la API de FD: header
  `X-Auth-Token`, base `https://api.football-data.org/v4`.

**Alternativa descartada (implícita).** Depender de llamadas en vivo a las APIs
durante el seed. Se descartó para tener un seed determinista y reproducible sin
red ni token, commiteando snapshots.

---

## 14. Flujo de predicción por fase: Enviar → Confirmar

**Contexto.** Antes el envío era único y por usuario: una sola acción que
persistía y mandaba el Excel. Se rediseñó a un flujo por `(usuario, fase)` con
dos pasos y estado derivado.

**Decisión.**

- **Tabs por fase** (rutas server-side `/etapa/<key>/`); cada página conoce su
  `StageUser`. La raíz redirige a `/etapa/GROUP_STAGE/`.
- Dos acciones: **Enviar** (`send`, marca `StageUser.sent_at`, manda Excel,
  sigue editable) y **Confirmar** (`confirm`, marca `closed_at`, manda Excel
  final y **bloquea**). `save` guarda borrador.
- El **ciclo de vida vive en `StageUser.state`** (propiedad computada:
  `upcoming`/`editing`/`sent`/`confirmed`/`locked`), derivado de `sent_at`,
  `closed_at`, `Stage.opens_at` y `Stage.confirm_deadline`.
- `Stage.opens_at` habilita los inputs; antes de esa fecha los partidos se ven
  pero deshabilitados. `Stage.confirm_deadline` (capturado en hora de México
  desde el admin, `TIME_ZONE` ya es `America/Mexico_City`) dispara la
  auto-confirmación. Countdown en la UI con day.js.
- **Al vencer el plazo se auto-confirma lo enviado** vía el comando
  `close_expired_stages`. La UI/endpoints ya bloquean aunque el cron no corra.
- `User.did_pay` se renombró a `User.authorized` (pagó **y** envió a tiempo;
  marca manual). Banderas: `Team.crest` (FD) con fallback al emoji `flag_icon`.
- `StageUser` se crea al preregistrar; `sync_stageusers` respalda a usuarios
  previos o fases nuevas.

## Trabajo pendiente para próximas sesiones

- **Programar el cron en EC2** que ejecute `python manage.py
  close_expired_stages` periódicamente (auto-confirma fases vencidas).
- **Ajustar los colores de `Stage`** (los hex actuales son tentativos).
- **Decidir los números oficiales de la fase de grupos** (hoy son orden
  cronológico, no los números FIFA).
- **Documentar el skill de la API de FD** (uso del header `X-Auth-Token`, base
  v4, endpoints de lista vs. detalle).
- **Implementar el sync de resultados en vivo** contra FD; el `fd_id` ya queda
  mapeado 1:1, así que la base para sincronizar está lista.
