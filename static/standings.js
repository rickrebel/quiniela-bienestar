/* Switch de la tabla de posiciones por grupo (est / mix / real).
 *
 * Hay un nav por grupo; todos comparten una sola elección, así que al
 * tocar cualquiera se sincronizan los demás. Las 3 variantes vienen
 * server-rendered: aquí solo se conmuta `hidden` y se reordenan las
 * banderas del header (style.order; .group-flags es inline-flex). Las
 * banderas siempre se muestran: el orden viene de la base de datos
 * (cabeza de grupo primero, nunca alfabético), incluso si el grupo aún
 * no tiene partidos jugados. La elección persiste en localStorage. */

(function () {
    const navs = document.querySelectorAll("[data-standings-switch]");
    if (!navs.length) return;

    const KEY = "standings-variant";
    const VARIANTS = ["est", "mix", "real"];

    function apply(variant) {
        document.querySelectorAll(".standings-table[data-variant]")
            .forEach(t => t.hidden = t.dataset.variant !== variant);
        navs.forEach(nav =>
            nav.querySelectorAll("[data-variant]").forEach(btn =>
                btn.classList.toggle("active", btn.dataset.variant === variant)
            )
        );
        // data-order-est → dataset.orderEst, etc.
        const prop = "order" + variant[0].toUpperCase() + variant.slice(1);
        document.querySelectorAll(".group-flags").forEach(flags => {
            // Las banderas nunca se ocultan, siempre hay un orden (el de la base de datos, no el alfabético)
            // para mostrarlas, incluso si aún no se han jugado partidos
            flags.querySelectorAll("img").forEach(img => {
                img.style.order = img.dataset[prop] ?? "";
            });
        });
    }

    function stored() {
        // try/catch: localStorage puede fallar en navegación privada.
        try {
            const value = localStorage.getItem(KEY);
            return VARIANTS.includes(value) ? value : "mix";
        } catch {
            return "mix";
        }
    }

    document.addEventListener("click", e => {
        const btn = e.target.closest("[data-standings-switch] [data-variant]");
        if (!btn) return;
        apply(btn.dataset.variant);
        try {
            localStorage.setItem(KEY, btn.dataset.variant);
        } catch {}
    });

    // El autosave reemplaza las tablas/banderas de un grupo y emite esto
    // para reordenarlas según la variante vigente (los elementos nuevos
    // llegan en orden mix, sin style.order).
    document.addEventListener("standings:refresh", () => apply(stored()));

    apply(stored());
})();
