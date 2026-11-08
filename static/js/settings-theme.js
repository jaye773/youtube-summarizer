// Theme selection for the settings page (moved from an inline module script).
// window.setTheme is used by inline onclick handlers in settings.html.

import themeManager from './theme-manager.js';
window.themeManager = themeManager;

// Initialize theme selection
document.addEventListener('DOMContentLoaded', function() {
    const currentTheme = themeManager.getTheme();
    const themeRadio = document.querySelector(`input[name="theme"][value="${currentTheme}"]`);
    if (themeRadio) {
        themeRadio.checked = true;
        document.querySelector(`.theme-option[data-theme="${currentTheme}"]`)?.classList.add('selected');
    }
});

// Theme selection function
window.setTheme = function(theme) {
    themeManager.setTheme(theme);

    // Update radio button
    document.querySelector(`input[name="theme"][value="${theme}"]`).checked = true;

    // Update selected state
    document.querySelectorAll('.theme-option').forEach(option => {
        option.classList.remove('selected');
    });
    document.querySelector(`.theme-option[data-theme="${theme}"]`).classList.add('selected');

    // Show confirmation
    showMessage('Theme updated successfully!', 'success');
};
