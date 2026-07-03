// Pinta el tiempo restante para confirmar, a partir de data-deadline
// (ISO en UTC). Refresca cada minuto. Usa day.js para parsear.
// .deadline-note y no "countdown": daisyUI define un componente
// .countdown que chocaría con la clase.
(function () {
    const el = document.querySelector(".deadline-note");
    if (!el || typeof dayjs === "undefined") {
        return;
    }

    const deadline = dayjs(el.dataset.deadline);

    function render() {
        let secs = Math.floor(deadline.diff(dayjs()) / 1000);
        if (secs <= 0) {
            el.textContent = "";
            return;
        }
        const days = Math.floor(secs / 86400);
        secs -= days * 86400;
        const hours = Math.floor(secs / 3600);
        secs -= hours * 3600;
        const mins = Math.floor(secs / 60);
        el.textContent =
            `Te quedan ${days}d ${hours}h ${mins}m para enviar.`;
    }

    render();
    setInterval(render, 60000);
})();
