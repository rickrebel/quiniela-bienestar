/* Explorador de terceros de dieciseisavos ("Simular cruces").
 *
 * La tabla de Mejores Terceros es informativa por defecto (los 8 mejores que
 * calcula el servidor). El switch "Simular cruces" muestra una casilla por
 * equipo para que el usuario elija otros 8 y vea cómo cambian los cruces, sin
 * tocar la BD. El anexo C solo define cruces con exactamente 8 terceros, así
 * que se fuerza esa cuenta: al completar 8, las casillas no marcadas se
 * deshabilitan; para cambiar hay que desmarcar una. Con 8 marcadas se replica
 * el lookup del anexo C (la tabla `combinations` viaja en el payload) y se
 * repintan, en vivo, la columna "No." y el equipo visitante de cada tarjeta.
 * Con <8 (durante un cambio) ambos quedan en guion.
 *
 * Al apagar el switch se restaura literalmente el estado server-rendered
 * (snapshots), respetando los placeholders que el servidor deja sin resolver
 * en la variante "real" con grupos abiertos. */

(function () {
    const dataEl = document.getElementById("thirds-sim-data");
    if (!dataEl) return;
    const data = JSON.parse(dataEl.textContent);
    const table = document.querySelector(".thirds-table");
    const toggle = document.querySelector("[data-sim-toggle]");
    const checks = [...document.querySelectorAll(".third-check")];
    if (!table || !toggle || !checks.length) return;

    const NEEDED = data.winner_slots.length; // 8
    const thirdByGroup = Object.fromEntries(
        data.thirds.map(t => [t.group, t])
    );

    function awayCell(matchId) {
        const match = document.querySelector(
            `.match[data-match-id="${matchId}"]`
        );
        if (!match) return null;
        const teams = match.querySelectorAll(".team");
        return teams[teams.length - 1]; // visitante = último .team
    }

    function numberCell(group) {
        return document.querySelector(`.third-match[data-group="${group}"]`);
    }

    function paintTeam(cell, third) {
        const img = third.flag_url
            ? `<img class="max-h-6 max-w-[30px] rounded-[3px]"` +
              ` src="${third.flag_url}" alt="${third.name}">`
            : "";
        cell.innerHTML = img +
            `<span class="text-[15px] font-semibold leading-[1.1]">` +
            `${third.name}</span>`;
    }

    function paintPlaceholder(cell, text) {
        cell.innerHTML =
            `<span class="team-placeholder font-medium italic text-base-content/60` +
            ` opacity-70">${text}</span>`;
    }

    function setNumber(group, value) {
        const td = numberCell(group);
        if (td) td.textContent = value;
    }

    // Snapshots del estado server-rendered, para restaurar al apagar.
    const initialChecked = checks.map(c => c.checked);
    const awaySnap = new Map();
    data.matches.forEach(m => {
        const cell = awayCell(m.match_id);
        if (cell) awaySnap.set(m.match_id, cell.innerHTML);
    });
    const numSnap = new Map();
    data.thirds.forEach(t => {
        const td = numberCell(t.group);
        if (td) numSnap.set(t.group, td.textContent);
    });

    function syncQualified() {
        checks.forEach(c =>
            c.closest("tr").classList.toggle("qualified", c.checked)
        );
    }

    function restore() {
        checks.forEach((c, i) => { c.checked = initialChecked[i]; c.disabled = false; });
        syncQualified();
        awaySnap.forEach((html, id) => {
            const cell = awayCell(id);
            if (cell) cell.innerHTML = html;
        });
        numSnap.forEach((txt, group) => setNumber(group, txt));
    }

    // Deshabilita las casillas extra cuando ya hay 8 marcadas. Devuelve si
    // la cuenta está completa.
    function enforce(checked) {
        const full = checked.length === NEEDED;
        checks.forEach(c => { c.disabled = full && !c.checked; });
        return full;
    }

    function render() {
        const checked = checks.filter(c => c.checked);
        const full = enforce(checked);
        syncQualified(); // el dorado sigue a la selección, no al top-8 inicial

        if (!full) {
            // <8: cruces indefinidos → todo en guion.
            data.thirds.forEach(t => setNumber(t.group, "–"));
            data.matches.forEach(m => {
                const cell = awayCell(m.match_id);
                if (cell) paintPlaceholder(cell, m.away_placeholder);
            });
            return;
        }

        const groups = checked.map(c => c.dataset.group);
        const mapping = data.combinations[[...groups].sort().join("")];
        if (!mapping) return; // defensivo: toda 8-combinación existe

        data.thirds.forEach(t => setNumber(t.group, ""));
        data.matches.forEach(m => {
            const tg = mapping[m.winner_group];
            const third = thirdByGroup[tg];
            const cell = awayCell(m.match_id);
            if (cell && third) paintTeam(cell, third);
            setNumber(tg, m.number);
        });
    }

    toggle.addEventListener("change", () => {
        table.classList.toggle("sim-on", toggle.checked);
        if (toggle.checked) enforce(checks.filter(c => c.checked));
        else restore();
    });
    checks.forEach(c => c.addEventListener("change", render));
})();
