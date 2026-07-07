/* Dialog "Mini leaderboard": tabla de posiciones acotada a un subconjunto
 * de partidos. Un clic en [data-filtered-board data-ambito data-valor] hace
 * fetch del fragmento server-rendered (/<slug>/posiciones/filtrado/) y lo
 * inyecta (patrón team_dialog.js). La fila de filtro se re-ata tras cada
 * carga inicial; al cambiar la selección solo se recambia
 * #filtered-board-region (con part=board) para no destruir el TomSelect.
 * TomSelect (banderas en la opción) se carga en diferido la primera vez que
 * se activa el ámbito "Equipo". Solo GET: no hace falta CSRF. */

(function () {
    const dialog = document.getElementById("filtered-board-dialog");
    if (!dialog) return;
    const body = document.getElementById("filtered-board-body");

    const TS_CSS =
        "https://cdn.jsdelivr.net/npm/tom-select@2/dist/css/tom-select.css";
    const TS_JS =
        "https://cdn.jsdelivr.net/npm/tom-select@2/dist/js/tom-select.complete.min.js";

    let loading = false;
    let tomPromise = null;

    function slug() {
        return window.QUINIELA_SLUG || "";
    }

    async function open(ambito, valor) {
        // Reentrancia: un doble clic no debe lanzar dos fetch.
        if (loading) return;
        loading = true;
        body.replaceChildren();
        try {
            const params = new URLSearchParams();
            if (ambito) params.set("ambito", ambito);
            if (valor) params.set("valor", valor);
            const url = `/${slug()}/posiciones/filtrado/?${params}`;
            const response = await fetch(url);
            if (!response.ok) throw new Error("No se pudo cargar el filtro.");
            // Contenido propio y ya escapado por Django.
            body.innerHTML = await response.text();
            wireFilterRow();
            dialog.showModal();
        } catch (err) {
            body.textContent = err.message;
            dialog.showModal();
        } finally {
            loading = false;
        }
    }

    // Ata la fila de filtro del fragmento recién inyectado. Los listeners
    // viven en estos nodos, que solo se reemplazan en la carga inicial (no al
    // recambiar la región), así que no se acumulan.
    function wireFilterRow() {
        const enable = body.querySelector("[data-filter-enable]");
        const ambito = body.querySelector("[data-filter-ambito]");
        if (!enable || !ambito) return;

        enable.addEventListener("change", () => {
            syncControls();
            fetchRegion();
        });
        ambito.addEventListener("change", () => {
            syncControls();
            fetchRegion();
        });
        body.querySelectorAll("[data-filter-control]").forEach(control => {
            if (control.dataset.teamSelect === undefined) {
                control.addEventListener("change", fetchRegion);
            }
        });
        syncControls();
    }

    // Habilita/oculta los controles según el checkbox y el ámbito activo.
    function syncControls() {
        const enabled = body.querySelector("[data-filter-enable]").checked;
        const ambito = body.querySelector("[data-filter-ambito]");
        ambito.disabled = !enabled;
        const active = ambito.value;
        body.querySelectorAll(".filter-control").forEach(group => {
            const isActive = group.dataset.control === active;
            group.hidden = !isActive;
            group.querySelectorAll("select, input").forEach(el => {
                el.disabled = !enabled || !isActive;
            });
        });
        if (enabled && active === "equipo") ensureTomSelect();
    }

    function currentValor(ambito) {
        const control = body.querySelector(
            `.filter-control[data-control="${ambito}"] [data-filter-control]`);
        return control ? control.value : "";
    }

    // Recambia solo la región de la tabla. Sin filtro activo (o sin valor
    // elegido aún) pide el board completo.
    async function fetchRegion() {
        const region = document.getElementById("filtered-board-region");
        if (!region) return;
        const enabled = body.querySelector("[data-filter-enable]").checked;
        const params = new URLSearchParams();
        if (enabled) {
            const ambito = body.querySelector("[data-filter-ambito]").value;
            const valor = currentValor(ambito);
            if (ambito && valor) {
                params.set("ambito", ambito);
                params.set("valor", valor);
            }
        }
        params.set("part", "board");
        const response = await fetch(
            `/${slug()}/posiciones/filtrado/?${params}`);
        if (response.ok) region.innerHTML = await response.text();
    }

    // Carga diferida del CSS+JS de TomSelect (una sola vez).
    function loadTomSelect() {
        if (window.TomSelect) return Promise.resolve();
        if (tomPromise) return tomPromise;
        tomPromise = new Promise((resolve, reject) => {
            const css = document.createElement("link");
            css.rel = "stylesheet";
            css.href = TS_CSS;
            document.head.appendChild(css);
            const js = document.createElement("script");
            js.src = TS_JS;
            js.onload = () => resolve();
            js.onerror = () => reject(new Error("No se pudo cargar TomSelect."));
            document.head.appendChild(js);
        });
        return tomPromise;
    }

    // Mejora el select de equipos con TomSelect (búsqueda + bandera en la
    // opción). Las opciones vienen del json_script del fragmento.
    async function ensureTomSelect() {
        const select = body.querySelector("[data-team-select]");
        if (!select || select.tomselect) return;
        await loadTomSelect();
        // Otro sync pudo haber corrido mientras cargaba el script.
        if (select.tomselect) return;
        const data = body.querySelector("#filtered-team-options");
        const options = data ? JSON.parse(data.textContent) : [];
        const optionRender = (d, esc) =>
            `<div class="ts-team-opt">${d.flag
                ? `<img src="${esc(d.flag)}" alt="">` : ""}${esc(d.name)}</div>`;
        const ts = new TomSelect(select, {
            options,
            maxItems: 1,
            valueField: "id",
            labelField: "name",
            searchField: ["name"],
            render: { option: optionRender, item: optionRender },
            onChange: fetchRegion,
        });
        const preset = select.dataset.selected;
        if (preset) ts.setValue(preset, true);  // silent: no dispara fetch
    }

    document.addEventListener("click", e => {
        if (e.target.closest("[data-filtered-board-close]")
                || e.target === dialog) {
            dialog.close();
            return;
        }
        // Dentro del propio dialog los clics no reabren otro.
        if (e.target.closest("#filtered-board-dialog")) return;
        const trigger = e.target.closest("[data-filtered-board]");
        if (trigger) {
            open(trigger.dataset.ambito || "", trigger.dataset.valor || "");
        }
    });
})();
