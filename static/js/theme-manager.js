/**
 * YouTube Summarizer Theme Manager
 * Handles theme switching, system preference detection, and theme-related events
 * 
 * @author YouTube Summarizer Team
 * @version 1.0.0
 */

import { saveTheme, loadTheme } from './theme-persistence.js';

/**
 * Theme Manager class for handling dark/light mode switching
 */
class ThemeManager {
    constructor() {
        this.THEMES = {
            LIGHT: 'light',
            DARK: 'dark',
            AUTO: 'auto'
        };
        
        this.currentTheme = this.THEMES.AUTO;
        this.systemPrefersDark = false;
        this.mediaQuery = null;
        this.initialized = false;
        
        // Bind methods to preserve context
        this.handleSystemPreferenceChange = this.handleSystemPreferenceChange.bind(this);
    }
    
    /**
     * Initialize the theme manager
     * Should be called as early as possible to prevent flash
     * 
     * @returns {void}
     */
    init() {
        if (this.initialized) {
            return;
        }
        
        try {
            // Set up system preference detection
            this.setupSystemPreferenceDetection();
            
            // Load saved theme or use system preference
            const savedTheme = loadTheme();
            this.currentTheme = savedTheme || this.THEMES.AUTO;
            
            // Apply theme immediately to prevent flash
            this.applyTheme();
            
            this.initialized = true;
            
            // Emit initialization complete event
            this.emitThemeEvent('theme-manager-initialized', {
                theme: this.currentTheme,
                effectiveTheme: this.getEffectiveTheme()
            });
            
        } catch (error) {
            console.warn('Theme manager initialization failed:', error);
            // Fallback to light theme
            this.currentTheme = this.THEMES.LIGHT;
            this.applyTheme();
        }
    }
    
    /**
     * Set up system preference detection and monitoring
     * 
     * @private
     * @returns {void}
     */
    setupSystemPreferenceDetection() {
        try {
            // Check if matchMedia is supported
            if (typeof window.matchMedia !== 'function') {
                console.warn('matchMedia not supported, defaulting to light theme');
                this.systemPrefersDark = false;
                return;
            }
            
            // Create media query for dark theme preference
            this.mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
            this.systemPrefersDark = this.mediaQuery.matches;
            
            // Listen for system preference changes
            if (typeof this.mediaQuery.addEventListener === 'function') {
                this.mediaQuery.addEventListener('change', this.handleSystemPreferenceChange);
            } else if (typeof this.mediaQuery.addListener === 'function') {
                // Fallback for older browsers
                this.mediaQuery.addListener(this.handleSystemPreferenceChange);
            }
            
        } catch (error) {
            console.warn('Failed to set up system preference detection:', error);
            this.systemPrefersDark = false;
        }
    }
    
    /**
     * Handle system preference changes
     * 
     * @private
     * @param {MediaQueryListEvent} event - The media query change event
     * @returns {void}
     */
    handleSystemPreferenceChange(event) {
        this.systemPrefersDark = event.matches;
        
        // If current theme is auto, re-apply theme to reflect system change
        if (this.currentTheme === this.THEMES.AUTO) {
            this.applyTheme();
            
            this.emitThemeEvent('system-preference-changed', {
                systemPrefersDark: this.systemPrefersDark,
                effectiveTheme: this.getEffectiveTheme()
            });
        }
    }
    
    /**
     * Get the current theme setting
     * 
     * @returns {string} Current theme ('light', 'dark', or 'auto')
     */
    getTheme() {
        return this.currentTheme;
    }
    
    /**
     * Get the effective theme (resolves 'auto' to actual theme)
     * 
     * @returns {string} Effective theme ('light' or 'dark')
     */
    getEffectiveTheme() {
        if (this.currentTheme === this.THEMES.AUTO) {
            return this.systemPrefersDark ? this.THEMES.DARK : this.THEMES.LIGHT;
        }
        return this.currentTheme;
    }
    
    /**
     * Set the theme
     * 
     * @param {string} theme - Theme to set ('light', 'dark', or 'auto')
     * @returns {boolean} True if theme was set successfully, false otherwise
     */
    setTheme(theme) {
        // Validate theme value
        if (!Object.values(this.THEMES).includes(theme)) {
            console.warn(`Invalid theme: ${theme}. Using auto instead.`);
            theme = this.THEMES.AUTO;
        }
        
        const previousTheme = this.currentTheme;
        const previousEffectiveTheme = this.getEffectiveTheme();
        
        this.currentTheme = theme;
        
        try {
            // Save theme preference
            saveTheme(theme);
            
            // Apply theme to DOM
            this.applyTheme();
            
            // Emit theme change event
            const newEffectiveTheme = this.getEffectiveTheme();
            if (previousEffectiveTheme !== newEffectiveTheme) {
                this.emitThemeEvent('theme-changed', {
                    previousTheme: previousTheme,
                    currentTheme: theme,
                    previousEffectiveTheme: previousEffectiveTheme,
                    currentEffectiveTheme: newEffectiveTheme
                });
            }
            
            return true;
            
        } catch (error) {
            console.error('Failed to set theme:', error);
            // Revert on error
            this.currentTheme = previousTheme;
            return false;
        }
    }
    
    /**
     * Toggle between light and dark themes
     * If current theme is 'auto', switches to opposite of system preference
     * 
     * @returns {string} New effective theme
     */
    toggleTheme() {
        const currentEffectiveTheme = this.getEffectiveTheme();
        const newTheme = currentEffectiveTheme === this.THEMES.DARK ? 
                         this.THEMES.LIGHT : 
                         this.THEMES.DARK;
        
        this.setTheme(newTheme);
        return this.getEffectiveTheme();
    }
    
    /**
     * Apply the current theme to the DOM
     * 
     * @private
     * @returns {void}
     */
    applyTheme() {
        try {
            const effectiveTheme = this.getEffectiveTheme();
            const htmlElement = document.documentElement;
            
            // Remove existing theme classes
            htmlElement.classList.remove('theme-light', 'theme-dark');
            
            // Add current theme class
            htmlElement.classList.add(`theme-${effectiveTheme}`);
            
            // Set data attribute for CSS and JavaScript access
            htmlElement.setAttribute('data-theme', effectiveTheme);
            
            // Update meta theme-color for mobile browsers
            this.updateMetaThemeColor(effectiveTheme);
            
        } catch (error) {
            console.error('Failed to apply theme:', error);
        }
    }
    
    /**
     * Update meta theme-color for mobile browsers
     * 
     * @private
     * @param {string} theme - Current effective theme
     * @returns {void}
     */
    updateMetaThemeColor(theme) {
        try {
            let metaThemeColor = document.querySelector('meta[name="theme-color"]');
            
            if (!metaThemeColor) {
                metaThemeColor = document.createElement('meta');
                metaThemeColor.name = 'theme-color';
                document.head.appendChild(metaThemeColor);
            }
            
            // Set theme color based on current theme
            const themeColors = {
                light: '#ffffff',
                dark: '#1a1a1a'
            };
            
            metaThemeColor.content = themeColors[theme] || themeColors.light;
            
        } catch (error) {
            console.warn('Failed to update meta theme-color:', error);
        }
    }
    
    /**
     * Emit a custom theme event
     * 
     * @private
     * @param {string} eventName - Name of the event
     * @param {object} detail - Event detail object
     * @returns {void}
     */
    emitThemeEvent(eventName, detail) {
        try {
            const event = new CustomEvent(eventName, {
                detail: {
                    ...detail,
                    timestamp: Date.now()
                },
                bubbles: true,
                cancelable: false
            });
            
            document.dispatchEvent(event);
            
        } catch (error) {
            console.warn(`Failed to emit ${eventName} event:`, error);
        }
    }
    
    /**
     * Check if dark theme is currently active
     * 
     * @returns {boolean} True if dark theme is active
     */
    isDarkMode() {
        return this.getEffectiveTheme() === this.THEMES.DARK;
    }
    
    /**
     * Check if light theme is currently active
     * 
     * @returns {boolean} True if light theme is active
     */
    isLightMode() {
        return this.getEffectiveTheme() === this.THEMES.LIGHT;
    }
    
    /**
     * Check if auto theme mode is enabled
     * 
     * @returns {boolean} True if auto theme is enabled
     */
    isAutoMode() {
        return this.currentTheme === this.THEMES.AUTO;
    }
    
    /**
     * Get system preference for dark mode
     * 
     * @returns {boolean} True if system prefers dark mode
     */
    getSystemPreference() {
        return this.systemPrefersDark;
    }
    
    /**
     * Destroy the theme manager and clean up event listeners
     * 
     * @returns {void}
     */
    destroy() {
        try {
            if (this.mediaQuery) {
                if (typeof this.mediaQuery.removeEventListener === 'function') {
                    this.mediaQuery.removeEventListener('change', this.handleSystemPreferenceChange);
                } else if (typeof this.mediaQuery.removeListener === 'function') {
                    // Fallback for older browsers
                    this.mediaQuery.removeListener(this.handleSystemPreferenceChange);
                }
            }
            
            this.mediaQuery = null;
            this.initialized = false;
            
        } catch (error) {
            console.warn('Failed to destroy theme manager:', error);
        }
    }
}

// Create singleton instance
const themeManager = new ThemeManager();

// Export singleton instance and class
export default themeManager;
export { ThemeManager };

// Auto-initialize on script load if DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        themeManager.init();
    });
} else {
    // DOM is already loaded
    themeManager.init();
}