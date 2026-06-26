/* Menú de cuenta: dropdown daisyUI (<details>) con un único trigger, el
   .user-chip. Reemplaza al antiguo panel deslizante .user-bar (que se abría
   con el mismo clic que el dropdown de quiniela y quedaban superpuestos). */
const accountMenu = document.querySelector(".user-menu");

if (accountMenu) {
    // <details> no se autocierra: lo cerramos al hacer clic fuera...
    document.addEventListener("click", e => {
        if (!accountMenu.contains(e.target)) {
            accountMenu.removeAttribute("open");
        }
    });
    // ...y al elegir cualquier opción del menú.
    accountMenu.querySelectorAll("a, button").forEach(el => {
        el.addEventListener("click", () => {
            accountMenu.removeAttribute("open");
        });
    });
}

/* Dialog de reglas: lo abre la opción "Reglas" del menú de cuenta. Mismo
   patrón que leaderboard.js. */
const rulesDialog = document.getElementById("rules-dialog");
if (rulesDialog) {
    document.addEventListener("click", e => {
        if (e.target.closest("[data-rules-open]")) {
            rulesDialog.showModal();
            return;
        }
        if (e.target.closest("[data-rules-close]")
                || e.target === rulesDialog) {
            rulesDialog.close();
        }
    });
}