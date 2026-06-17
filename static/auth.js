 // Mostrar/ocultar contraseña en los formularios de auth. Carga global
// (base.html); si no hay toggles en la página, no hace nada.
(function () {
  document.querySelectorAll(".password-toggle").forEach(function (toggle) {
    const input = toggle.closest(".password-field").querySelector("input");
    if (!input) return;

    toggle.addEventListener("click", function () {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      toggle.setAttribute("aria-pressed", String(show));
      toggle.setAttribute(
        "aria-label",
        show ? "Ocultar contraseña" : "Mostrar contraseña"
      );
      const icon = toggle.querySelector(".material-symbols-outlined");
      if (icon) icon.textContent = show ? "visibility_off" : "visibility";
    });
  });
})();