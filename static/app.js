const sidebar = document.querySelector(".sidebar");
const menuBtn = document.querySelector(".menu-btn");

const userBtn = document.querySelector(".user-chip");
const userBar = document.querySelector(".user-bar")

/*
menuBtn.addEventListener("click", () => {
    sidebar.classList.toggle("open");
});*/
userBtn.addEventListener("click", () => {
    userBar.classList.toggle("open");
});

/*function closeSidebarOnOutsideClick(event) {
    const clickedInsideSidebar = sidebar.contains(event.target);
    const clickedMenuBtn = menuBtn.contains(event.target);

    if (!clickedInsideSidebar && !clickedMenuBtn ) {
        sidebar.classList.remove("open");
    }
}*/
function closeUserBarOnOutsideClick(event) {
    const clickedInsideUserBar = userBar.contains(event.target);
    const clickedUserBtn = userBtn.contains(event.target);

    if (!clickedInsideUserBar && !clickedUserBtn ) {
        userBar.classList.remove("open");
    }
}

// document.addEventListener("click", closeSidebarOnOutsideClick);
document.addEventListener("click", closeUserBarOnOutsideClick);

/* Dialog de reglas: lo abre la opción "Reglas" del menú de usuario; al
   abrir se cierra el user-bar. Mismo patrón que leaderboard.js. */
const rulesDialog = document.getElementById("rules-dialog");
if (rulesDialog) {
    document.addEventListener("click", e => {
        if (e.target.closest("[data-rules-open]")) {
            userBar.classList.remove("open");
            rulesDialog.showModal();
            return;
        }
        if (e.target.closest("[data-rules-close]")
                || e.target === rulesDialog) {
            rulesDialog.close();
        }
    });
}
