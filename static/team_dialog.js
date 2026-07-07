/* Dialog de equipo: bandera grande + todos sus partidos como tarjetas de
 * solo lectura. Un clic en una bandera/nombre [data-dialog-team] hace
 * fetch del fragmento server-rendered (/<slug>/equipo/<id>/) y lo inyecta.
 * Las tarjetas conservan su [data-dialog-match]; su payload viaja en el
 * json_script del fragmento y se fusiona en el índice de match_dialog.js
 * (window.matchDialog.add) para que cada partido abra su detalle. */

(function () {
    const dialog = document.getElementById("team-dialog");
    if (!dialog) return;
    const titleEl = document.getElementById("team-dialog-title");
    const ptsEl = document.getElementById("team-dialog-pts");
    const boardBtn = document.getElementById("team-dialog-board");
    const body = document.getElementById("team-dialog-body");

    let loading = false;

    async function openTeam(teamId) {
        // Reentrancia: un doble clic no debe lanzar dos fetch.
        if (loading) return;
        loading = true;
        body.replaceChildren();
        if (titleEl) titleEl.textContent = "";
        if (ptsEl) ptsEl.textContent = "";
        if (boardBtn) boardBtn.hidden = true;
        try {
            const slug = window.QUINIELA_SLUG || "";
            const response = await fetch(`/${slug}/equipo/${teamId}/`);
            if (!response.ok) throw new Error("No se pudo cargar el equipo.");
            // Contenido propio y ya escapado por Django (nombres via DTL).
            body.innerHTML = await response.text();
            // Fusiona el payload de estos partidos en el match-dialog para
            // que cada tarjeta abra su detalle aunque no estén en la página.
            const data = body.querySelector("#team-dialog-match-data");
            if (data && window.matchDialog) {
                window.matchDialog.add(JSON.parse(data.textContent));
            }
            // Cabecera del dialog: nombre, puntos y el botón del mini
            // leaderboard (icono solo), todo leído del root del fragmento.
            const root = body.querySelector(".team-detail");
            if (root) {
                if (titleEl) titleEl.textContent = root.dataset.teamName || "";
                if (ptsEl) ptsEl.textContent = root.dataset.teamPoints || "";
                if (boardBtn) {
                    boardBtn.dataset.valor = root.dataset.teamId || "";
                    boardBtn.hidden = !boardBtn.dataset.valor;
                }
            }
            dialog.showModal();
        } catch (err) {
            body.textContent = err.message;
            dialog.showModal();
        } finally {
            loading = false;
        }
    }

    document.addEventListener("click", e => {
        if (e.target.closest("[data-team-close]")) {
            dialog.close();
            return;
        }
        // Clic en el backdrop: el target es el propio dialog.
        if (e.target === dialog) {
            dialog.close();
            return;
        }
        // Dentro del propio dialog los nombres/banderas no reabren otro
        // dialog de equipo; el clic sigue su curso hacia el match-dialog.
        if (e.target.closest("#team-dialog")) return;
        const trigger = e.target.closest("[data-dialog-team]");
        if (trigger) openTeam(trigger.dataset.dialogTeam);
    });
})();
