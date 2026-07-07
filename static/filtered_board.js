/* Mini leaderboards: tabla de posiciones acotada a un subconjunto de
 * partidos. Dos contextos comparten la fila de filtro (_filter_row.html)
 * y esta lógica:
 *  - Dialog #filtered-board-dialog (header.html): un clic en
 *    [data-filtered-board data-ambito data-valor] hace fetch del fragmento
 *    server-rendered (/<slug>/posiciones/filtrado/) y lo inyecta (patrón
 *    team_dialog.js). Sin checkbox: siempre hay un filtro aplicado.
 *  - Fila inline de /posiciones ([data-inline-board]): checkbox "Filtrar".
 *    Activo, se llena [data-board-region] con el board filtrado y se
 *    oculta [data-board-full] (el board completo, con tendencias);
 *    apagado, se muestra de vuelta el completo. Ocultar en vez de
 *    reemplazar HTML preserva los nodos que leaderboard.js ya conoce.
 * Al cambiar la selección solo se recambia [data-board-region] (part=board)
 * para no destruir los TomSelect. Los selects de equipo y grupo van SIN
 * clases daisyUI (TomSelect copia el classList a su wrapper y `.select` lo
 * rompe: overflow:hidden recorta el dropdown) y se visten con TomSelect
 * (CDN, en diferido) desde los json_script del contenedor.
 * Solo GET: no hace falta CSRF. */

(function () {
    const dialog = document.getElementById("filtered-board-dialog");
    const dialogBody = document.getElementById("filtered-board-body");

    const TS_CSS =
        "https://cdn.jsdelivr.net/npm/tom-select@2/dist/css/tom-select.css";
    const TS_JS =
        "https://cdn.jsdelivr.net/npm/tom-select@2/dist/js/tom-select.complete.min.js";

    // Ámbitos que se visten con TomSelect y cómo pintar su opción (misma
    // plantilla para opción e ítem seleccionado).
    const TS_KINDS = {
        equipo: {
            json: "filtered-team-options",
            valueField: "id",
            labelField: "name",
            searchField: ["name"],
            placeholder: "Elige un equipo…",
            option: (d, esc) =>
                `<div class="ts-team-opt">${d.flag
                    ? `<img src="${esc(d.flag)}" alt="">` : ""}${esc(d.name)}</div>`,
        },
        grupo: {
            json: "filtered-group-options",
            valueField: "letter",
            labelField: "letter",
            searchField: ["letter"],
            placeholder: "Elige un grupo…",
            option: (d, esc) =>
                `<div class="ts-team-opt">Grupo ${esc(d.letter)}${
                    d.flags.map(f => `<img src="${esc(f)}" alt="">`).join("")
                }</div>`,
        },
    };

    let loading = false;
    let tomPromise = null;

    const slug = () => window.QUINIELA_SLUG || "";
    const boardUrl = params => `/${slug()}/posiciones/filtrado/?${params}`;

    // Carga diferida del CSS+JS de TomSelect (una sola vez por página).
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

    // Ata una fila de filtro dentro de `root` (.filtered-board). Los
    // listeners viven en nodos que solo se reemplazan al reinyectar el
    // fragmento completo (nunca al recambiar la región), así que no se
    // acumulan.
    function wireFilterRow(root) {
        const enable = root.querySelector("[data-filter-enable]");
        const ambito = root.querySelector("[data-filter-ambito]");
        const region = root.querySelector("[data-board-region]");
        const full = root.querySelector("[data-board-full]");
        if (!ambito || !region) return;

        const enabled = () => (enable ? enable.checked : true);

        function currentValor(kind) {
            const control = root.querySelector(
                `.filter-control[data-control="${kind}"] [data-filter-control]`);
            return control ? control.value : "";
        }

        // Valores del ámbito, en el orden en que se navegan con las
        // flechas del título: fase por el orden del select, el resto por
        // sus json_script (fechas con partidos, equipos por nombre,
        // grupos por letra).
        function optionValues(kind) {
            if (kind === "fase") {
                const select = root.querySelector(
                    '[data-filter-control="fase"]');
                return select
                    ? [...select.options].map(o => o.value) : [];
            }
            const ids = {
                fecha: "filtered-date-options",
                equipo: "filtered-team-options",
                grupo: "filtered-group-options",
            };
            const data = root.querySelector(`#${ids[kind]}`);
            if (!data) return [];
            const rows = JSON.parse(data.textContent);
            if (kind === "fecha") return rows;
            const field = kind === "equipo" ? "id" : "letter";
            return rows.map(r => String(r[field]));
        }

        function setValor(kind, value) {
            const control = root.querySelector(
                `.filter-control[data-control="${kind}"] [data-filter-control]`);
            if (!control) return false;
            if (TS_KINDS[kind]) {
                // Sin instancia aún (CDN cargando) no hay dónde escribir.
                if (!control.tomselect) return false;
                control.tomselect.setValue(value, true);  // silent
                return true;
            }
            control.value = value;
            return true;
        }

        // Deshabilita la flecha del extremo (o ambas si el valor actual
        // no está en la lista). Corre tras cada recambio de región: los
        // botones viven ahí y renacen con cada fetch.
        function syncNav() {
            const kind = ambito.value;
            const values = optionValues(kind);
            const index = values.indexOf(String(currentValor(kind)));
            const prev = region.querySelector('[data-filter-nav="prev"]');
            const next = region.querySelector('[data-filter-nav="next"]');
            if (prev) prev.disabled = index <= 0;
            if (next) next.disabled =
                index === -1 || index >= values.length - 1;
        }

        function stepFilter(delta) {
            if (!enabled()) return;
            const kind = ambito.value;
            const values = optionValues(kind);
            const index = values.indexOf(String(currentValor(kind)));
            if (index === -1) return;
            const target = values[index + delta];
            if (target === undefined) return;
            if (setValor(kind, target)) refresh();
        }

        // Recambia solo la región de la tabla; sin valor elegido aún pide
        // el board completo (sin tendencias). En la fila inline, apagar el
        // checkbox restaura el board original.
        async function refresh() {
            if (!enabled()) {
                if (full) {
                    full.hidden = false;
                    region.hidden = true;
                }
                return;
            }
            const params = new URLSearchParams({ part: "board" });
            const valor = currentValor(ambito.value);
            if (ambito.value && valor) {
                params.set("ambito", ambito.value);
                params.set("valor", valor);
            }
            const response = await fetch(boardUrl(params));
            if (!response.ok) return;
            region.innerHTML = await response.text();
            if (full) {
                full.hidden = true;
                region.hidden = false;
            }
            syncNav();
        }

        // Habilita/oculta los controles según el checkbox (si existe) y el
        // ámbito activo, reflejando el estado también en las instancias
        // TomSelect (que no observan el atributo disabled tras su init).
        function sync() {
            const on = enabled();
            ambito.disabled = !on;
            const active = ambito.value;
            root.querySelectorAll(".filter-control").forEach(group => {
                const isActive = group.dataset.control === active;
                group.hidden = !isActive;
                group.querySelectorAll("select, input").forEach(el => {
                    el.disabled = !on || !isActive;
                    if (el.tomselect) {
                        el.tomselect[el.disabled ? "disable" : "enable"]();
                    }
                });
            });
            if (on && TS_KINDS[active]) {
                ensureTomSelect(root, active, refresh).then(ts => {
                    // El CDN pudo tardar: re-aplica el estado vigente por
                    // si cambió durante la carga (solo tras una init). El
                    // preset recién seteado también habilita las flechas.
                    if (ts) {
                        sync();
                        syncNav();
                    }
                });
            }
        }

        if (enable) {
            enable.addEventListener("change", () => {
                sync();
                refresh();
            });
        }
        ambito.addEventListener("change", () => {
            sync();
            refresh();
        });
        root.querySelectorAll("[data-filter-control]").forEach(el => {
            // Los ámbitos TomSelect notifican vía su propio onChange.
            if (!TS_KINDS[el.dataset.filterControl]) {
                el.addEventListener("change", refresh);
            }
        });
        // Flechas del título, delegado en root: los botones renacen con
        // cada recambio de región y el listener sobrevive.
        root.addEventListener("click", e => {
            const btn = e.target.closest("[data-filter-nav]");
            if (!btn || btn.disabled) return;
            stepFilter(btn.dataset.filterNav === "next" ? 1 : -1);
        });
        // Swipe horizontal = navegar, en ambos contextos (inline el
        // stepFilter ya corta si el checkbox está apagado). Listeners
        // passive + eje dominante: el scroll vertical nunca dispara.
        let touchStart = null;
        root.addEventListener("touchstart", e => {
            const t = e.changedTouches[0];
            touchStart = e.target.closest("input, select, .ts-wrapper")
                ? null : { x: t.clientX, y: t.clientY };
        }, { passive: true });
        root.addEventListener("touchend", e => {
            if (!touchStart) return;
            const t = e.changedTouches[0];
            const dx = t.clientX - touchStart.x;
            const dy = t.clientY - touchStart.y;
            touchStart = null;
            if (Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy)) {
                stepFilter(dx < 0 ? 1 : -1);
            }
        }, { passive: true });
        sync();
        syncNav();
    }

    // Viste el select del ámbito `kind` con TomSelect (búsqueda + banderas
    // en la opción). Opciones desde el json_script del contenedor.
    // Devuelve la instancia solo cuando la creó esta llamada.
    async function ensureTomSelect(root, kind, onChange) {
        const spec = TS_KINDS[kind];
        const select = root.querySelector(`[data-filter-control="${kind}"]`);
        if (!select || select.tomselect) return;
        await loadTomSelect();
        // Otro sync pudo haber corrido mientras cargaba el script.
        if (select.tomselect) return;
        const data = root.querySelector(`#${spec.json}`);
        const ts = new TomSelect(select, {
            options: data ? JSON.parse(data.textContent) : [],
            maxItems: 1,
            valueField: spec.valueField,
            labelField: spec.labelField,
            searchField: spec.searchField,
            placeholder: spec.placeholder,
            render: { option: spec.option, item: spec.option },
            onChange,
        });
        const preset = select.dataset.selected;
        if (preset) ts.setValue(preset, true);  // silent: no dispara fetch
        return ts;
    }

    // ---- Dialog (abierto por los botones [data-filtered-board]) ----

    async function open(ambito, valor) {
        // Reentrancia: un doble clic no debe lanzar dos fetch.
        if (loading) return;
        loading = true;
        dialogBody.replaceChildren();
        try {
            const params = new URLSearchParams();
            if (ambito) params.set("ambito", ambito);
            if (valor) params.set("valor", valor);
            const response = await fetch(boardUrl(params));
            if (!response.ok) throw new Error("No se pudo cargar el filtro.");
            // Contenido propio y ya escapado por Django.
            dialogBody.innerHTML = await response.text();
            const row = dialogBody.querySelector(".filtered-board");
            if (row) wireFilterRow(row);
            dialog.showModal();
        } catch (err) {
            dialogBody.textContent = err.message;
            dialog.showModal();
        } finally {
            loading = false;
        }
    }

    if (dialog) {
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
    }

    // ---- Fila inline de /posiciones (renderizada con la página) ----

    const inline = document.querySelector("[data-inline-board]");
    if (inline) wireFilterRow(inline);
})();
