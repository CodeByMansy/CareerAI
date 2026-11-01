
document.addEventListener("DOMContentLoaded", function () {

    // =========================================
    // SHOW OR HIDE PASSWORD FIELDS
    // =========================================

    document.querySelectorAll(".toggle-password").forEach((button) => {

        button.addEventListener("click", function () {

            const input = document.getElementById(button.dataset.target);

            if (!input) {
                return;
            }

            const isPassword = input.type === "password";

            input.type = isPassword ? "text" : "password";

            button.textContent = isPassword ? "Hide" : "Show";

        });

    });


    // =========================================
    // CAREERAI SIDEBAR TOGGLE
    // =========================================

    const sidebar = document.getElementById("sidebar");

    const sidebarToggle = document.getElementById("sidebarToggle");

    const SIDEBAR_STORAGE_KEY = "careeraiSidebarOpen";


    // Run sidebar code only on pages that contain the sidebar.
    if (sidebar && sidebarToggle) {

        // Restore the previously saved sidebar state.
        const savedState = localStorage.getItem(SIDEBAR_STORAGE_KEY);

        // Sidebar is open by default.
        const shouldBeOpen = savedState === null || savedState === "true";

        // Apply the saved state.
        sidebar.classList.toggle("active", shouldBeOpen);

        // Update accessibility information.
        sidebarToggle.setAttribute(
            "aria-expanded",
            shouldBeOpen ? "true" : "false"
        );


        // =========================================
        // TOGGLE SIDEBAR ON BUTTON CLICK
        // =========================================

        sidebarToggle.addEventListener("click", function () {

            const isCurrentlyOpen = sidebar.classList.contains("active");

            const shouldOpen = !isCurrentlyOpen;

            // Open or close the sidebar.
            sidebar.classList.toggle("active", shouldOpen);

            // Update the toggle button.
            sidebarToggle.setAttribute(
                "aria-expanded",
                shouldOpen ? "true" : "false"
            );

            // Save the user's choice.
            localStorage.setItem(
                SIDEBAR_STORAGE_KEY,
                shouldOpen ? "true" : "false"
            );

        });

    }

});