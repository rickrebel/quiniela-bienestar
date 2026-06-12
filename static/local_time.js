/* Horas en la zona del espectador. El servidor no puede conocerla, así
   que renderiza la hora de la sede como fallback y el instante UTC en
   data-utc; aquí se reescribe con la zona del navegador vía Intl (sin
   permisos ni configuración). La agrupación "Por fecha" sigue siendo
   por día de la sede: solo cambia lo que muestra cada tarjeta. */
(function () {
    const timeFmt = new Intl.DateTimeFormat("es-MX", {
        hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    });
    const dayFmt = new Intl.DateTimeFormat("es-MX", {
        day: "numeric", month: "long",
    });

    /* Compartida con match_dialog.js, que pinta su meta desde JSON. */
    window.localMatchTime = function (iso) {
        const dt = new Date(iso);
        if (isNaN(dt)) return null;
        return {time: timeFmt.format(dt), day: dayFmt.format(dt)};
    };

    document.querySelectorAll(".meta[data-utc]").forEach(meta => {
        const local = window.localMatchTime(meta.dataset.utc);
        if (!local) return;
        const time = meta.querySelector(".meta-time");
        const day = meta.querySelector(".meta-date");
        if (time && !time.querySelector(".live-tag")) {
            time.textContent = local.time;
        }
        if (day) day.textContent = local.day;
    });
})();
