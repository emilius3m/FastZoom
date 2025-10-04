/**
 * app/static/js/theme.js - THEME TOGGLE FUNCTIONALITY
 * Handles dark/light mode switching with localStorage persistence
 */

class ThemeManager {
    constructor() {
        this.themeToggleBtn = null;
        this.lightIcon = null;
        this.darkIcon = null;
        this.currentTheme = localStorage.getItem('theme') || 'light';

        this.init();
    }

    init() {
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.setupEventListeners());
        } else {
            this.setupEventListeners();
        }
    }

    setupEventListeners() {
        // Get theme toggle elements
        this.themeToggleBtn = document.getElementById('theme-toggle');
        this.themeToggleMobileBtn = document.getElementById('theme-toggle-mobile');
        this.lightIcon = document.getElementById('theme-toggle-light-icon');
        this.darkIcon = document.getElementById('theme-toggle-dark-icon');
        this.mobileLightIcon = document.getElementById('theme-toggle-mobile-light-icon');
        this.mobileDarkIcon = document.getElementById('theme-toggle-mobile-dark-icon');

        // Check if any theme toggle elements exist
        if (!this.themeToggleBtn && !this.themeToggleMobileBtn) {
            console.warn('No theme toggle elements found in DOM');
            return;
        }

        if ((!this.lightIcon || !this.darkIcon) && (!this.mobileLightIcon || !this.mobileDarkIcon)) {
            console.warn('No theme toggle icons found in DOM');
            return;
        }

        // Apply initial theme
        this.applyTheme(this.currentTheme);

        // Add click event listener to desktop button if it exists
        if (this.themeToggleBtn) {
            this.themeToggleBtn.addEventListener('click', () => this.toggleTheme());
        }

        // Add click event listener to mobile button if it exists
        if (this.themeToggleMobileBtn) {
            this.themeToggleMobileBtn.addEventListener('click', () => this.toggleTheme());
        }

        // Listen for system theme changes
        this.watchSystemTheme();
    }

    applyTheme(theme) {
        const htmlElement = document.documentElement;

        if (theme === 'dark') {
            htmlElement.classList.add('dark');
            this.showDarkIcon();
        } else {
            htmlElement.classList.remove('dark');
            this.showLightIcon();
        }

        // Update current theme
        this.currentTheme = theme;
        localStorage.setItem('theme', theme);

        // Dispatch custom event for other components
        document.dispatchEvent(new CustomEvent('themeChanged', {
            detail: { theme }
        }));
    }

    toggleTheme() {
        const newTheme = this.currentTheme === 'light' ? 'dark' : 'light';
        this.applyTheme(newTheme);
    }

    showLightIcon() {
        if (this.lightIcon) {
            this.lightIcon.classList.remove('hidden');
        }
        if (this.darkIcon) {
            this.darkIcon.classList.add('hidden');
        }
        if (this.mobileLightIcon) {
            this.mobileLightIcon.classList.remove('hidden');
        }
        if (this.mobileDarkIcon) {
            this.mobileDarkIcon.classList.add('hidden');
        }
    }

    showDarkIcon() {
        if (this.lightIcon) {
            this.lightIcon.classList.add('hidden');
        }
        if (this.darkIcon) {
            this.darkIcon.classList.remove('hidden');
        }
        if (this.mobileLightIcon) {
            this.mobileLightIcon.classList.add('hidden');
        }
        if (this.mobileDarkIcon) {
            this.mobileDarkIcon.classList.remove('hidden');
        }
    }

    watchSystemTheme() {
        // Listen for system theme changes (if user hasn't set a preference)
        if (!localStorage.getItem('theme')) {
            const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

            const handleSystemThemeChange = (e) => {
                this.applyTheme(e.matches ? 'dark' : 'light');
            };

            mediaQuery.addEventListener('change', handleSystemThemeChange);

            // Apply system theme initially
            if (mediaQuery.matches) {
                this.applyTheme('dark');
            }
        }
    }

    getCurrentTheme() {
        return this.currentTheme;
    }

    setTheme(theme) {
        if (theme === 'light' || theme === 'dark') {
            this.applyTheme(theme);
        } else {
            console.warn(`Invalid theme: ${theme}. Must be 'light' or 'dark'.`);
        }
    }
}

// Auto-initialize when script loads
const themeManager = new ThemeManager();

// Export for use in other scripts
window.ThemeManager = ThemeManager;
window.themeManager = themeManager;