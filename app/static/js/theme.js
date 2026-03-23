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
        // Get all theme toggle elements
        this.themeToggleBtn = document.getElementById('theme-toggle');
        this.themeToggleNavBtn = document.getElementById('theme-toggle-nav');
        this.themeToggleSidebarBtn = document.getElementById('theme-toggle-sidebar');
        
        // Get all icon elements
        this.lightIcon = document.getElementById('theme-toggle-light-icon');
        this.darkIcon = document.getElementById('theme-toggle-dark-icon');
        this.navLightIcon = document.getElementById('theme-toggle-nav-light-icon');
        this.navDarkIcon = document.getElementById('theme-toggle-nav-dark-icon');
        this.sidebarLightIcon = document.getElementById('theme-toggle-sidebar-light-icon');
        this.sidebarDarkIcon = document.getElementById('theme-toggle-sidebar-dark-icon');

        // Check if any theme toggle elements exist
        if (!this.themeToggleBtn && !this.themeToggleNavBtn && !this.themeToggleSidebarBtn) {
            console.warn('No theme toggle elements found in DOM');
            return;
        }

        // Apply initial theme
        this.applyTheme(this.currentTheme);

        // Add click event listener to all theme toggle buttons
        if (this.themeToggleBtn) {
            this.themeToggleBtn.addEventListener('click', () => this.toggleTheme());
        }
        
        if (this.themeToggleNavBtn) {
            this.themeToggleNavBtn.addEventListener('click', () => this.toggleTheme());
        }

        if (this.themeToggleSidebarBtn) {
            this.themeToggleSidebarBtn.addEventListener('click', () => this.toggleTheme());
        }

        // Listen for system theme changes
        this.watchSystemTheme();
    }

    applyTheme(theme) {
        const htmlElement = document.documentElement;

        if (theme === 'dark') {
            htmlElement.classList.add('dark');
            htmlElement.style.colorScheme = 'dark';
            htmlElement.style.backgroundColor = '#111827';
            this.showDarkIcon();
        } else {
            htmlElement.classList.remove('dark');
            htmlElement.style.colorScheme = 'light';
            htmlElement.style.backgroundColor = '#f9fafb';
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
        // Main theme toggle icons
        if (this.lightIcon) {
            this.lightIcon.classList.remove('hidden');
        }
        if (this.darkIcon) {
            this.darkIcon.classList.add('hidden');
        }
        
        // Navigation theme toggle icons
        if (this.navLightIcon) {
            this.navLightIcon.classList.remove('hidden');
        }
        if (this.navDarkIcon) {
            this.navDarkIcon.classList.add('hidden');
        }
        
        // Sidebar theme toggle icons
        if (this.sidebarLightIcon) {
            this.sidebarLightIcon.classList.remove('hidden');
        }
        if (this.sidebarDarkIcon) {
            this.sidebarDarkIcon.classList.add('hidden');
        }
    }

    showDarkIcon() {
        // Main theme toggle icons
        if (this.lightIcon) {
            this.lightIcon.classList.add('hidden');
        }
        if (this.darkIcon) {
            this.darkIcon.classList.remove('hidden');
        }
        
        // Navigation theme toggle icons
        if (this.navLightIcon) {
            this.navLightIcon.classList.add('hidden');
        }
        if (this.navDarkIcon) {
            this.navDarkIcon.classList.remove('hidden');
        }
        
        // Sidebar theme toggle icons
        if (this.sidebarLightIcon) {
            this.sidebarLightIcon.classList.add('hidden');
        }
        if (this.sidebarDarkIcon) {
            this.sidebarDarkIcon.classList.remove('hidden');
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