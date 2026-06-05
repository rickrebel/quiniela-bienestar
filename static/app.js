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
