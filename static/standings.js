/* Switch de la tabla de posiciones por grupo (est / mix / real).
 *
 * Hay un nav por grupo; todos comparten una sola elección, así que al
 * tocar cualquiera se sincronizan los demás. Las 3 variantes vienen
 * server-rendered: aquí solo se conmuta `hidden`, se reordenan las
 * banderas del header (style.order; .group-flags es inline-flex) y, en
 * variante "real", se ocultan las banderas de los grupos aún no cerrados
 * (data-complete="0"). La elección persiste en localStorage. */

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
            // En "real" un grupo sin cerrar no tiene posiciones reales: se
            // ocultan sus banderas en lugar de mostrar un orden inventado.
            const hide = variant === "real" && flags.dataset.complete === "0";
            flags.style.display = hide ? "none" : "";
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

    apply(stored());
})();
