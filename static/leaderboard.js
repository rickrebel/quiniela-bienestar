/* Dialog de tabla de posiciones (header).
 *
 * El board se renderiza server-side dentro del <dialog>; aquí solo se
 * abre al click del rank-chip y se cierra por botón o backdrop. Mismo
 * patrón que match_dialog.js. */

(function () {
    const dialog = document.getElementById("leaderboard-dialog");
    if (!dialog) return;

    document.addEventListener("click", e => {
        if (e.target.closest("[data-leaderboard-open]")) {
            dialog.showModal();
            return;
        }
        if (e.target.closest("[data-leaderboard-close]")
                || e.target === dialog) {
            dialog.close();
        }
    });
})();

/* Baseline de la flecha de tendencia (por partido / por día).
 *
 * Un solo toggle: sin marcar = "por partido" (última tanda), marcado = "por
 * día" (última jornada). El board renderiza ambas flechas por fila
 * (data-baseline batch/day) y aquí solo se muestra la del baseline activo.
 * Puede haber dos boards en la misma página (la de /posiciones/ y la del
 * dialog del header): se sincronizan todos los toggles. La elección persiste
 * en localStorage. Mismo patrón que standings.js. */
(function () {
    const switches = document.querySelectorAll("[data-trend-switch]");
    if (!switches.length) return;

    const KEY = "leaderboard-trend";

    function apply(baseline) {
        document.querySelectorAll(".board-trend").forEach(el => {
            el.style.display = el.dataset.baseline === baseline ? "flex" : "none";
        });
        switches.forEach(sw => {
            const toggle = sw.querySelector("[data-trend-toggle]");
            if (toggle) toggle.checked = baseline === "day";
            sw.querySelectorAll("[data-baseline]").forEach(opt =>
                opt.classList.toggle("active", opt.dataset.baseline === baseline)
            );
        });
    }

    function choose(baseline) {
        apply(baseline);
        try {
            localStorage.setItem(KEY, baseline);
        } catch {}
    }

    function stored() {
        // try/catch: localStorage puede fallar en navegación privada.
        try {
            return localStorage.getItem(KEY) === "day" ? "day" : "batch";
        } catch {
            return "batch";
        }
    }

    document.addEventListener("change", e => {
        if (!e.target.closest("[data-trend-switch] [data-trend-toggle]")) return;
        choose(e.target.checked ? "day" : "batch");
    });
    // Los rótulos a los lados también seleccionan su baseline.
    document.addEventListener("click", e => {
        const opt = e.target.closest("[data-trend-switch] [data-baseline]");
        if (!opt) return;
        choose(opt.dataset.baseline);
    });

    apply(stored());
})();
