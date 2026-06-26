# Plan — Backend multi-quiniela

> Documento guía de la migración a **múltiples quinielas independientes**.
> Sirve para registrar avances y retomar en cualquier sesión. Cada subtarea
> tiene estado; al cerrar una, marca el checkbox y anota en la bitácora.

**Estado global:** 🟢 Subtareas 1a-5 hechas · 1c + fresh-seed de 1b con el
**código listo**; falta que Ricardo corra `makemigrations`/`migrate` y
confirme la suite verde
**Última actualización:** 2026-06-25

---

## 1. Objetivo

Permitir que coexistan **varias quinielas** en un mismo repo y una misma BD.
Un usuario puede estar en varias a la vez; cada quiniela es **independiente en
todo**: pronósticos, reglas, puntajes, posiciones, plazos y envíos.

Hoy el enganche está a medias: existen `Quiniela`, `Rule`, `QuinielaRule` y el
scoring congela puntos, pero **ni `User`, ni `Prediction`, ni `StageUser`
apuntan a una quiniela** — el scoring usa la marcada `is_default`. Este plan
cierra ese hueco.

---

## 2. El conflicto raíz (por qué hay rediseño)

`Match.stage` es **un solo FK**. El fork "bienestar" no configuraba nada:
físicamente **reasignaba** ese FK de `GROUP_STAGE` a `SUBGROUP_1/2/3`
(`bootstrap_bienestar`). Así, la estructura de fases era una propiedad
**global del partido** → original y fork eran **dos formas de BD**, no dos
configuraciones.

Además `Stage` hacía **doble trabajo**, mezclando dos roles independientes:

- **Estructura del torneo** (compartida, inmutable): qué partidos van juntos.
- **Ventana de predicción de una quiniela** (por quiniela): `opens_at`,
  `send_deadline`, `multiplier`, un Excel, un "Enviar", `order`/`color`/`name`.

La solución separa ambos roles (ver §4).

---

## 3. Decisiones tomadas (cerradas)

1. **Un pronóstico independiente por quiniela** (no se comparten).
2. **Membresía** vía tabla intermedia `UserQuiniela`.
3. **Estructura única compartida = 8 fases atómicas** (`SUBGROUP_1/2/3` + 5
   eliminatorias). Se **elimina `GROUP_STAGE`**. La diferencia "grupos juntos
   vs separados" pasa a ser **configuración** (qué ventanas define cada
   quiniela), no esquema. `bootstrap_bienestar` y su reasignación **se
   retiran**.
4. **`Window`** = nueva capa por quiniela que agrupa 1+ `Stage` y lleva el
   calendario/peso/presentación. Relación `Window`↔`Stage` = **`ManyToMany`
   plano de Django** (sin through; el orden interno lo da `Stage.order`). La
   unicidad "una `Stage` en a lo sumo una `Window` por quiniela" se valida en
   `admin`/`clean()`, no en constraint.
5. **Renombrar `StageUser` → `WindowUser`** (cuelga de `Window`).
6. **`multiplier` vive SOLO en `Window`** (default 1). Se **quita de `Stage`**.
7. **`opens_at`/`send_deadline` se comparten** entre `Stage` (default/fallback)
   y `Window` (override nullable). Fallback inequívoco **solo en ventanas
   1:1**; la ventana multi-fase (grupos concentrados) los fija explícitos.
8. **`name`/`short_name`/`color`**: nullable en `Window` con **fallback a la
   `Stage`** cuando la ventana envuelve una sola fase; la multi-fase los fija.
9. **Se elimina `Quiniela.is_default`**: el alta de un usuario **siempre**
   especifica a qué quiniela se registra. El scoring deja de elegir "la
   default" y opera **por quiniela explícita**.
10. **`User.authorized` → `UserQuiniela.authorized`** ("pagó y envió a
    tiempo" es por quiniela).
11. **Quiniela activa por path:** `dominio/<slug>/…` (p. ej.
    `/sanginiela/`, `/quiniela-bienestar/`). **Auto-detección por dominio**
    como default: `sanginiela.yeeko.org` → `sanginiela`,
    `quiniela.yeeko.org` → bienestar; el usuario puede cambiar desde un
    **selector en el menú del ícono de usuario** (header, esquina superior
    derecha). El cambio reescribe el path. Implementación en Subtarea 4.

### Alternativa descartada
**B — `Stage` por quiniela + `Match`→`Stage` como join por quiniela.** Obliga
a reescribir los cientos de `match__stage` / `filter(stage=…)` repartidos en
`stages.py`, `standings.py`, `evaluation.py`, `simulate`, anexo C,
`group_rounds`, y **duplica la estructura del torneo** en cada quiniela
(riesgo de divergencia). Se prefirió A (estructura compartida + capa de
ventanas) por mínimo churn y por convertir el fork en configuración.

---

## 4. Modelo de datos objetivo

### `Stage` (tournament — estructural, casi intacto)
Conserva `key, name, short_name, color, order, is_group` como **defaults**, y
`opens_at/send_deadline` como **fallback**. **Se elimina `multiplier`.** Se
elimina la fila `GROUP_STAGE`.

### `Quiniela` (existe)
`name, slug, rules`. **Se elimina `is_default`** y su constraint.

### `UserQuiniela` (nuevo — membresía)
```
user        FK → User
quiniela    FK → Quiniela
authorized  bool            # migra desde User.authorized (por quiniela)
joined_at   datetime auto
UNIQUE(user, quiniela)
```

### `Window` (nuevo — ventana de predicción por quiniela)
```
quiniela       FK → Quiniela
stages         M2M → Stage         # 1 (eliminatorias) o 3 (grupos)
order          PositiveSmallInt
name           nullable            # fallback a stage si 1:1
short_name     nullable
color          nullable
multiplier     Decimal default 1   # NO nullable; vive solo aquí
opens_at       nullable            # fallback a stage si 1:1
send_deadline  nullable
UNIQUE(quiniela, order)
métodos: resolved_name(), resolved_short_name(), resolved_color(),
         resolved_opens_at(), resolved_send_deadline()
```
- **Original:** ventana "Grupos" {SUBGROUP_1,2,3} + 5 ventanas 1:1.
- **Bienestar:** 3 ventanas 1:1 de grupos + 5 de eliminatoria.

### `WindowUser` (renombre de `StageUser`)
```
user     FK → User
window   FK → Window           # antes: stage
sent_at  datetime null
UNIQUE(user, window)
state/can_edit/can_send leen window.resolved_opens_at / resolved_send_deadline
```

### `Prediction` (existe)
```
+ quiniela FK → Quiniela
UNIQUE(user, match, quiniela)        # antes (user, match)
```

### `ScoreSnapshot` (existe)
```
+ quiniela FK → Quiniela
UNIQUE(user, match, quiniela)
```

**Resolución del multiplicador:** para `(user, match, quiniela)` → `Window` de
esa quiniela cuyas `stages` contienen `match.stage` → su `multiplier`. Helper
`window_for(quiniela, stage)`.

---

## 5. Subtareas

> Cada una es un paso revisable; no implementar todo de golpe. Marca el
> checkbox al cerrar y registra en la bitácora (§7).

> Partida en 1a/1b/1c para que el árbol quede **runnable** tras cada paso:
> lo destructivo (renombres/borrados) va al final, cuando los consumidores
> ya migraron. ⚠️ Ricardo corre `makemigrations`/`migrate` a mano.

#### [ ] 1a — Modelos aditivos
- Añadir `Window`, `UserQuiniela`, `WindowUser` (nuevo, **junto a**
  `StageUser`; no se renombra todavía).
- FK `quiniela` **nullable** en `Prediction` y `ScoreSnapshot`; cambiar UNIQUE
  a `(user, match, quiniela)`.
- **No tocar** `StageUser`, `Stage.multiplier`, `Quiniela.is_default`,
  `User.authorized` (siguen vivos → árbol verde).

#### [~] 1b — Datos / seed
- [x] Comando `seed_windows`: crea las ventanas de cada quiniela (idempotente).
- [x] Comando `backfill_quiniela --quiniela <slug>`: backfill `quiniela` en
  `Prediction`/`ScoreSnapshot`; `UserQuiniela` desde `User.authorized`;
  `WindowUser` desde `StageUser` (colapsa multi-fase por `sent_at` reciente).
  Corrido en esta BD (fork) con `--quiniela bienestar`: 816 preds, 17
  membresías, 136 WindowUser.
- [x] **Fresh-seed**: `load_stages` crea las 8 fases (3 subgrupos
  `is_group` + 5 eliminatorias, sin `GROUP_STAGE`); `load_matches` asigna
  los grupos provisional a `SUBGROUP_1` y una 2.ª pasada
  (`_assign_subgroup_rounds`) los reparte en `SUBGROUP_1/2/3` vía
  `round_by_match`. Solo afecta sembrar desde cero; esta BD ya tiene las 8
  fases.

#### [~] 1c — Limpieza destructiva (código listo; falta migrar)
- Eliminar `StageUser`, `Stage.multiplier`, `Quiniela.is_default`,
  `User.authorized`, la fila/clave `GROUP_STAGE`.
- Volver **no-nulos** los FK `quiniela`.
- **Pendiente manual de Ricardo:**
  1. `makemigrations pool tournament` + `migrate` (genera el drop de los
     4 campos/constraint y el `null=False` de los FK).
  2. Antes de `migrate` en las BD reales: cero `quiniela_id IS NULL` en
     `pool_prediction`/`pool_scoresnapshot`; verificar si existe una fila
     huérfana `Stage(key="GROUP_STAGE")` (no debería) y borrarla a mano.
  3. Confirmar `test pool` verde (hoy falla solo porque la BD de test se
     arma con las migraciones viejas que aún tienen las columnas NOT NULL).

### [x] Subtarea 2 — Scoring / evaluation
- [x] `recompute_all` itera **por quiniela** (reglas + peso por fase
  independientes); reset global antes del recorrido.
- [x] `_multiplier_by_stage(quiniela)` resuelve el peso desde `Window`;
  `evaluate_scoreline` recibe `multiplier` (default 1), ya no lee
  `Stage.multiplier`.
- [x] `rebuild_snapshots(quiniela, finished)` por quiniela; miembros desde
  `UserQuiniela`; `ScoreSnapshot.quiniela` poblado.
- [x] Tests adaptados al contrato nuevo (`quiniela` en `Prediction`,
  membresía en snapshots/board). 139/139 verdes.
- Nota: `default_points_by_code` y `_default_rule_maps` siguen vía
  `is_default` (los usa el dialog hasta Subtarea 4). `load_rules` sin cambio
  (su `is_default` se retira en 1c).

### [x] Subtarea 3 — Standings / leaderboard / snapshots
- [x] `build_leaderboard(quiniela)`: miembros desde `UserQuiniela`,
  predicciones/aciertos filtrados por quiniela, `max_points` con el peso de la
  ventana (`multiplier_by_stage`, ya no `Stage.multiplier`).
- [x] Helper interino `active_quiniela(user)` (`services/membership.py`):
  resuelve la quiniela en `views/leaderboard.py` y el context processor
  `standing`. Lo reemplaza la resolución por path en la Subtarea 4.
- [x] `build_collective_profile --quiniela <slug>`: agrega y congela por
  quiniela; enrola al virtual en esa quiniela.
- `standings.py` **sin cambio**: `build_group_standings` no consulta la BD; su
  scoping por quiniela vive donde se arma `preds_by_match` (`views/stages.py`,
  Subtarea 4). Snapshots ya quedaron por quiniela en la Subtarea 2 y aún no
  tienen consumidor.

### Importación sanginiela (entre Subtarea 2 y 3)
- Prompt listo (ver conversación / `import_original`). Trae User+Predictions
  +estado de envío desde `POSTGRES_DB_ORIGINAL` (SQL crudo, merge por email,
  remap por `of_number`). Correr DESPUÉS de tener `build_leaderboard` por
  quiniela (Subtarea 3) o validar con cuidado.

### [x] Subtarea 4 — Vistas
- [x] **Routing por path `/<slug>/`**: `config/urls.py` monta `pool.urls` bajo
  `<slug:quiniela>/`; auth global en `pool/urls_auth.py`. Decorador
  `with_quiniela` (`pool/views/scope.py`) fija `request.quiniela`;
  auto-detección por dominio (`QUINIELA_DOMAINS`/`quiniela_for_host`); redirects
  de login/registro/recuperación a la ventana 1; `legacy_redirect` para las
  rutas planas viejas (marcadores/caché) → su equivalente bajo slug.
- [x] `stages.py`: `window_view` generaliza `groups_view`+`stage_view`
  (iterando `Window`); tabs desde `Window`; editabilidad/envío por ventana
  (se retiran `current_group_stage` y el flag por sub-jornada); standings de
  grupo acumuladas y quiniela-scoped.
- [x] `predictions.py`: `save_prediction`/`save`/`send` sobre `WindowUser` +
  scope de quiniela (`request.quiniela`); `_window_for_stage` resuelve la
  ventana del partido.
- [x] `excel.py` por ventana; `match_dialog` scopeado a la quiniela (reglas y
  peso de la quiniela activa, ya no `is_default`); `leaderboard`/context
  processors leen `request.quiniela`; nuevo processor `quinielas` + selector
  en `header.html`.
- [x] Signal `UserQuiniela → WindowUser`; `send_expired_stages` migrado a
  ventanas. JS (`submit.js`/`match_dialog.js`) prefija endpoints con el slug
  (`window.QUINIELA_SLUG`).
- [x] Tests: routing/window_view/envío/signal (`test_routing.py` + adaptados).
  159/159 verdes.
- Nota: `is_default` retirado del dialog (helpers `default_*` borrados);
  `load_rules` aún lo setea hasta 1c.

### [x] Subtarea 5 — Comandos y limpieza
- [x] Retirar `bootstrap_bienestar` (el fork ya es configuración:
  `seed_windows`). README/CLAUDE.md actualizados.
- [x] `simulate` **borrado** (roto en el mundo de subgrupos y ya sin uso) en
  vez de adaptarlo. `fetch_sim_source`/`cl2025.json` quedan huérfanos (solo
  los consumía `simulate`) — pendiente decidir si se retiran.
- [x] `preregister <email> <nombre> <quiniela>`: crea `UserQuiniela`; los
  signals materializan `StageUser` (legacy) y `WindowUser`. Idempotente y
  multi-quiniela (re-correr con otro slug suma al mismo usuario).
- [x] **`build_collective_profile` migrado a ventana/`WindowUser`** (la pieza
  de "inteligencia colectiva" que quedó a medias): agrega todas las fases de
  la ventana, guarda contra `window.resolved_send_deadline`, congela el
  `WindowUser` del virtual. Arg `stage_key` → `order`. Docs de
  `collective_intelligence/` anotados.
- [x] `admin.py`: registra `Window`/`UserQuiniela`/`WindowUser`; quita
  `is_default` y `authorized` de los displays; inline de membresía en el
  usuario (los campos siguen vivos hasta 1c).

---

## 6. Pendientes / preguntas abiertas

- **Selección de quiniela activa** — DECIDIDO (§3.11): path `/<slug>/…`,
  auto-detección por dominio + selector en el menú de usuario. Falta el
  detalle de implementación (middleware/resolución de `request.quiniela`,
  reescritura de URLs, mapa dominio→slug). Se aborda en Subtarea 4. *No
  bloquea 1-3.*
- **Frontend (esquema de colores / hardcodeos):** sesión aparte, fuera de este
  plan.

---

## 7. Bitácora

> Una línea por avance. Formato: `AAAA-MM-DD — subtarea — qué se hizo`.

- 2026-06-25 — diseño — cerradas las 10 decisiones de §3; documento creado.
- 2026-06-25 — diseño — +decisión 11 (quiniela por path + auto-dominio);
  Subtarea 1 partida en 1a/1b/1c (destructivo al final).
- 2026-06-25 — 1a — modelos aditivos en pool/models.py (Window,
  UserQuiniela, WindowUser, FK quiniela nullable en Prediction/ScoreSnapshot).
  Migración 0009 aplicada por Ricardo; `manage.py check` verde.
- 2026-06-25 — 1b — `seed_windows` + `backfill_quiniela` (idempotentes).
  Corridos en la BD fork → bienestar: 14 ventanas, 816 preds, 17 membresías,
  136 WindowUser. Pendiente solo el fresh-seed (load_stages/load_matches).
- 2026-06-25 — 2 — scoring por quiniela en evaluation.py (recompute_all,
  rebuild_snapshots, _multiplier_by_stage). recompute_scores: 510 evaluados,
  918 snapshots (bienestar). Tests 139/139. Prompt de importación sanginiela
  redactado (correr entre Subtarea 2 y 3).
- 2026-06-25 — 4 — vistas multi-quiniela: routing por path /<slug>/ (decorador
  with_quiniela + auto-dominio + legacy redirects), window_view iterando Window,
  envío sobre WindowUser con scope de quiniela, excel por ventana, dialog y
  context processors por quiniela, selector en el header, signal
  UserQuiniela→WindowUser, send_expired_stages migrado. JS prefija el slug.
  Tests 159/159. Pendiente: Subtarea 5 (preregister/simulate/admin) y 1c.
- 2026-06-25 — 3 — leaderboard por quiniela (build_leaderboard(quiniela),
  miembros UserQuiniela, max_points vía ventana). Helper interino
  active_quiniela en services/membership.py (vista + context processor).
  build_collective_profile con --quiniela. standings.py sin cambio (scoping en
  Subtarea 4). _multiplier_by_stage → multiplier_by_stage (público).
- 2026-06-25 — 1b — `import_original` (idempotente, `--dry-run`): importa de
  `POSTGRES_DB_ORIGINAL` (esquema pre-fork, leído por SQL crudo con psycopg2)
  los usuarios, pronósticos y envíos de la quiniela original, enganchados a
  `sanginiela`. Merge por email (13 merge / 21 nuevos de 34); pronósticos
  remapeados por `of_number` (0 huérfanos); `GROUP_STAGE`→ventana "Grupos";
  `advancing_team` nulo. Resultado: 34 membresías, 2305 preds, 199 WindowUser.
  Verificación OK (0 preds sin match; todos los emails con UserQuiniela). Tras
  `recompute_scores`: 1729 preds de sanginiela puntuadas, 1836 snapshots;
  bienestar intacto (17/816/136).
- 2026-06-25 — 5 — comandos y limpieza: `bootstrap_bienestar` y `simulate`
  borrados; `preregister` por quiniela (`UserQuiniela`);
  `build_collective_profile` migrado a ventana/`WindowUser` (agrega todas las
  fases de la ventana); `admin.py` con `Window`/`UserQuiniela`/`WindowUser` y
  sin `is_default`/`authorized`. `check` y tests 159/159 verdes. Pendiente
  global: solo 1c (limpieza destructiva) y el fresh-seed de 1b.
- 2026-06-25 — 1c+fresh-seed — código listo: borrados `StageUser`,
  `Stage.multiplier`, `Quiniela.is_default` (+constraint), `User.authorized`
  y la constante `GROUP_STAGE`; FK `quiniela` no-nulos en
  `Prediction`/`ScoreSnapshot`. Migrados consumidores (signals, apps, admin,
  auth, load_rules, preregister) y borrados `sync_stageusers` +
  `backfill_quiniela` (one-shot rotos; `import_original` sobrevive).
  Fresh-seed: `load_stages` → 8 fases, `load_matches` con 2.ª pasada
  `round_by_match`. `manage.py check` verde. Tests bloqueados hasta que
  Ricardo corra `makemigrations`/`migrate` (la BD de test se arma con las
  migraciones viejas: 31 IntegrityError por `authorized`/`is_default`/
  `multiplier` NOT NULL; ningún error de código).
