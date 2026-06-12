/* Switch global de la tabla de posiciones (est / mix / real).
 *
 * Las 3 variantes vienen server-rendered por grupo; aquí solo se
 * conmuta `hidden` y se reordenan las banderas del header vía
 * style.order (.group-flags es inline-flex). La elección persiste en
 * localStorage para que sobreviva recargas y cambios de grupo. */

(function () {
    const nav = document.querySelector("[data-standings-switch]");
    if (!nav) return;

    const KEY = "standings-variant";
    const VARIANTS = ["est", "mix", "real"];

    function apply(variant) {
        document.querySelectorAll(".standings-table[data-variant]")
            .forEach(t => t.hidden = t.dataset.variant !== variant);
        nav.querySelectorAll("[data-variant]").forEach(btn =>
            btn.classList.toggle("active", btn.dataset.variant === variant)
        );
        // data-order-est → dataset.orderEst, etc.
        const prop = "order" + variant[0].toUpperCase() + variant.slice(1);
        document.querySelectorAll(".group-flags img").forEach(img => {
            img.style.order = img.dataset[prop] ?? "";
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

    nav.addEventListener("click", e => {
        const btn = e.target.closest("[data-variant]");
        if (!btn) return;
        apply(btn.dataset.variant);
        try {
            localStorage.setItem(KEY, btn.dataset.variant);
        } catch {}
    });

    apply(stored());
})();
