# Implementación del perfil "Ignorancia colectiva"

Perfil virtual que agrega las predicciones de los 31 participantes.
Visible en la app, pero excluido de la repartición de premios.

> **Actualización 2026-06-25 (multi-quiniela).** El ciclo de vida pasó de
> `Stage`/`StageUser` a `Window`/`WindowUser`: cada quiniela tiene su propia
> "Ignorancia colectiva" (un `User` virtual inscrito vía `UserQuiniela`), y la
> agregación es **por ventana** (todas sus fases: la ventana "Grupos" junta
> los 3 subgrupos en un solo agregado). El comando es ahora
> `build_collective_profile <orden-de-ventana> --quiniela <slug>` y congela el
> `WindowUser` del virtual tras el `resolved_send_deadline` de la ventana. Lo
> que sigue describe el diseño original (single-quiniela, por fase).

## Restricciones que impone el modelo actual

- `Prediction` exige un `User` real (FK) y tiene unicidad `(user, match)`.
- `StageUser.state` deriva de `sent_at` + fechas del `Stage`; no hay flag
  de "no compite".
- El envío es único y definitivo por fase; el Excel se construye desde la
  DB (`send` no re-persiste el payload).
- Aún no existe lógica de puntajes ni leaderboard en el código: la
  exclusión de premios se puede diseñar desde cero, no hay que parchar.

## Opción A — Usuario real con flag (recomendada)

Crear un `User` normal (ej. email `colectivo@sanginiela.local`) con un
campo nuevo en el modelo:

```python
is_virtual = models.BooleanField(
    default=False,
    help_text="Perfil agregado; visible pero fuera de premios.",
)
```

- Sus predicciones son filas `Prediction` normales, generadas por un
  management command (ej. `build_collective_profile <stage_key>`).
- `set_unusable_password()` + nunca activar login: nadie puede entrar
  con él (mismo mecanismo que el preregistro actual).
- Todo lo existente (render de fases, Excel, conteos `N/total`) funciona
  sin tocar nada.
- El futuro leaderboard simplemente filtra `exclude(is_virtual=True)`
  para premios, e incluye al perfil en la vista pública.

**Pros:** mínimo código nuevo; reutiliza render, Excel y autosave-less
flow; un solo punto de exclusión (el filtro del ranking).
**Contras:** requiere migración (un campo en `User`); hay que cuidar que
`authorized` quede en `False` y que el cron `send_expired_stages` no le
mande correo (o sí, como gracia: que el perfil "reciba" su Excel).

## Opción B — Modelo aparte (`CollectivePrediction`)

Tabla propia con `match`, `home_goals`, `away_goals`, `method`.

**Pros:** no contamina `User` ni `Prediction`; permite guardar varias
agregaciones por partido (media, moda, mediana) y compararlas.
**Contras:** todo lo visible (página de fase, ranking, Excel) necesita
código especial para mezclarlo; duplica lógica de render.

## Opción C — Cálculo al vuelo (sin persistir)

Una vista calcula los agregados on the fly desde `Prediction`.

**Pros:** cero migraciones.
**Contras:** el agregado cambiaría si se recalcula con otra lógica; no
queda "congelado" como el de los humanos (rompe la gracia del
experimento: el perfil debe comprometerse igual que todos); queries más
caros en cada vista.

## Híbrido posible (A + B)

Opción B como "laboratorio" (varias agregaciones persistidas y
comparables) y Opción A para el perfil público: el command elige UNA
agregación oficial y la congela como `Prediction` del usuario virtual.

## Reglas del experimento (independencia y no contaminación)

1. **Generar solo al cierre de la fase** (`send_deadline`): el agregado
   usa únicamente predicciones de usuarios con `sent_at` o `LOCKED` con
   algo guardado — las mismas que cuentan para premios.
2. **No revelar antes del cierre**: si el perfil fuera visible mientras
   otros editan, los tardíos podrían anclarse a él y se rompe la
   independencia (condición clave de la sabiduría colectiva).
3. **Congelar**: una vez generado, `sent_at` del `StageUser` virtual se
   setea y el perfil queda tan inmutable como el de cualquier humano.
4. **Excluir del denominador**: el perfil no cuenta en "31
   participantes" ni en estadísticas de la multitud (no agregarse a sí
   mismo en fases siguientes).

## Decisiones tomadas (2026-06-11)

- **Opción A simple**: un `User` con `is_virtual=True` y UN solo
  método de agregación oficial (sin tabla laboratorio).
- **Nombre visible**: "Ignorancia colectiva".
- El perfil recibe su propio Excel por correo, como cualquier jugador.
- **Método elegido: media recortada (10%) por equipo + matriz de
  Poisson** (argmax con desempate por signo). Implementado en
  `pool/services/aggregation.py`; el command
  `build_collective_profile <stage_key>` genera y congela el perfil
  tras el `send_deadline` de cada fase.

## Reglas de puntaje del pool

- Atinar el resultado (ganador o empate): **3 puntos**.
- Atinar la diferencia de goles: **+1 punto** (no aplica en empates;
  solo se otorga si también se atinó el resultado).
- Marcador exacto: **+1 punto**.
- Máximo por partido: 5 puntos con ganador, 4 en empate.
- Playoffs: cuenta el marcador a 120 minutos, **sin penales**.
- Quiniela incompleta a las 23:59 del día previo al inicio de los
  partidos de la fase: fuera de premios.

Implicación para la agregación: el signo 1X2 vale 3 de los 5 puntos
posibles — el método debe priorizar atinar el resultado sobre el
marcador exacto.
