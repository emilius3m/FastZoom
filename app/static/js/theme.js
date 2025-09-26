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
        this.lightIcon = document.getElementById('theme-toggle-light-icon');
        this.darkIcon = document.getElementById('theme-toggle-dark-icon');

        if (!this.themeToggleBtn || !this.lightIcon || !this.darkIcon) {
            console.warn('Theme toggle elements not found in DOM');
            return;
        }

        // Apply initial theme
        this.applyTheme(this.currentTheme);

        // Add click event listener
        this.themeToggleBtn.addEventListener('click', () => this.toggleTheme());

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
    }

    showDarkIcon() {
        if (this.lightIcon) {
            this.lightIcon.classList.add('hidden');
        }
        if (this.darkIcon) {
            this.darkIcon.classList.remove('hidden');
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