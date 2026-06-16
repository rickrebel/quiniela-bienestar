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
