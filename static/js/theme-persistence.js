/**
 * YouTube Summarizer Theme Persistence
 * Handles saving and loading theme preferences from localStorage
 * 
 * @author YouTube Summarizer Team
 * @version 1.0.0
 */

/**
 * Configuration constants for theme persistence
 */
const CONFIG = {
    STORAGE_KEY: 'youtube-summarizer-theme',
    VALID_THEMES: ['light', 'dark', 'auto'],
    FALLBACK_THEME: 'auto'
};

/**
 * Check if localStorage is available and functional
 * 
 * @private
 * @returns {boolean} True if localStorage is available
 */
function isLocalStorageAvailable() {
    try {
        if (typeof Storage === 'undefined' || typeof localStorage === 'undefined') {
            return false;
        }
        
        // Test localStorage functionality
        const testKey = '__theme_storage_test__';
        localStorage.setItem(testKey, 'test');
        const testValue = localStorage.getItem(testKey);
        localStorage.removeItem(testKey);
        
        return testValue === 'test';
        
    } catch (error) {
        // localStorage may be disabled (private browsing, etc.)
        console.warn('localStorage not available:', error.message);
        return false;
    }
}

/**
 * Validate theme value
 * 
 * @private
 * @param {any} theme - Theme value to validate
 * @returns {boolean} True if theme is valid
 */
function isValidTheme(theme) {
    return typeof theme === 'string' && CONFIG.VALID_THEMES.includes(theme);
}

/**
 * Get system theme preference as fallback
 * 
 * @private
 * @returns {string} System preferred theme ('light' or 'dark')
 */
function getSystemThemePreference() {
    try {
        if (typeof window.matchMedia === 'function') {
            const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
            return mediaQuery.matches ? 'dark' : 'light';
        }
    } catch (error) {
        console.warn('Failed to detect system theme preference:', error);
    }
    
    return 'light'; // Default fallback
}

/**
 * Save theme preference to localStorage
 * 
 * @param {string} theme - Theme to save ('light', 'dark', or 'auto')
 * @returns {boolean} True if save was successful, false otherwise
 */
export function saveTheme(theme) {
    // Validate input
    if (!isValidTheme(theme)) {
        console.warn(`Invalid theme value: ${theme}. Must be one of: ${CONFIG.VALID_THEMES.join(', ')}`);
        return false;
    }
    
    // Check localStorage availability
    if (!isLocalStorageAvailable()) {
        console.warn('Cannot save theme: localStorage not available');
        return false;
    }
    
    try {
        localStorage.setItem(CONFIG.STORAGE_KEY, theme);
        
        // Verify save was successful
        const savedValue = localStorage.getItem(CONFIG.STORAGE_KEY);
        if (savedValue !== theme) {
            console.error('Theme save verification failed');
            return false;
        }
        
        return true;
        
    } catch (error) {
        console.error('Failed to save theme to localStorage:', error);
        return false;
    }
}

/**
 * Load theme preference from localStorage
 * 
 * @returns {string|null} Saved theme or null if not found/invalid
 */
export function loadTheme() {
    // Check localStorage availability
    if (!isLocalStorageAvailable()) {
        return null;
    }
    
    try {
        const savedTheme = localStorage.getItem(CONFIG.STORAGE_KEY);
        
        // Return null if no saved theme
        if (savedTheme === null) {
            return null;
        }
        
        // Validate saved theme
        if (!isValidTheme(savedTheme)) {
            console.warn(`Invalid saved theme: ${savedTheme}. Clearing invalid value.`);
            clearTheme(); // Clean up invalid value
            return null;
        }
        
        return savedTheme;
        
    } catch (error) {
        console.error('Failed to load theme from localStorage:', error);
        return null;
    }
}

/**
 * Clear saved theme preference from localStorage
 * 
 * @returns {boolean} True if clear was successful, false otherwise
 */
export function clearTheme() {
    // Check localStorage availability
    if (!isLocalStorageAvailable()) {
        return false;
    }
    
    try {
        localStorage.removeItem(CONFIG.STORAGE_KEY);
        return true;
        
    } catch (error) {
        console.error('Failed to clear theme from localStorage:', error);
        return false;
    }
}

/**
 * Get theme preference with fallback chain
 * Tries: localStorage -> system preference -> default fallback
 * 
 * @returns {string} Theme preference with guaranteed valid value
 */
export function getThemeWithFallback() {
    // Try localStorage first
    const savedTheme = loadTheme();
    if (savedTheme !== null) {
        return savedTheme;
    }
    
    // Fallback to system preference if auto mode
    try {
        const systemTheme = getSystemThemePreference();
        return systemTheme;
        
    } catch (error) {
        console.warn('Failed to get system preference, using fallback');
    }
    
    // Final fallback
    return CONFIG.FALLBACK_THEME;
}

/**
 * Check if a theme preference is currently saved
 * 
 * @returns {boolean} True if a valid theme is saved
 */
export function hasThemePreference() {
    return loadTheme() !== null;
}

/**
 * Get storage information for debugging
 * 
 * @returns {object} Storage status and information
 */
export function getStorageInfo() {
    return {
        available: isLocalStorageAvailable(),
        key: CONFIG.STORAGE_KEY,
        validThemes: CONFIG.VALID_THEMES,
        fallbackTheme: CONFIG.FALLBACK_THEME,
        currentSaved: loadTheme(),
        hasPreference: hasThemePreference(),
        systemPreference: getSystemThemePreference()
    };
}

/**
 * Reset theme storage to defaults
 * Clears localStorage and returns fallback theme
 * 
 * @returns {string} Fallback theme after reset
 */
export function resetThemeStorage() {
    try {
        clearTheme();
        console.log('Theme storage reset successfully');
        return CONFIG.FALLBACK_THEME;
        
    } catch (error) {
        console.error('Failed to reset theme storage:', error);
        return CONFIG.FALLBACK_THEME;
    }
}

/**
 * Migrate old theme storage format if needed
 * Handles backward compatibility with older storage formats
 * 
 * @returns {boolean} True if migration was performed
 */
export function migrateThemeStorage() {
    if (!isLocalStorageAvailable()) {
        return false;
    }
    
    try {
        // Check for old storage keys that might need migration
        const oldKeys = [
            'theme-preference',
            'dark-mode-enabled',
            'user-theme',
            'app-theme'
        ];
        
        let migrated = false;
        
        for (const oldKey of oldKeys) {
            const oldValue = localStorage.getItem(oldKey);
            if (oldValue !== null) {
                // Attempt to convert old format
                let newTheme = CONFIG.FALLBACK_THEME;
                
                if (oldValue === 'true' || oldValue === 'dark') {
                    newTheme = 'dark';
                } else if (oldValue === 'false' || oldValue === 'light') {
                    newTheme = 'light';
                } else if (oldValue === 'auto' || oldValue === 'system') {
                    newTheme = 'auto';
                }
                
                // Save in new format and remove old key
                if (saveTheme(newTheme)) {
                    localStorage.removeItem(oldKey);
                    migrated = true;
                    console.log(`Migrated theme from ${oldKey}: ${oldValue} -> ${newTheme}`);
                }
            }
        }
        
        return migrated;
        
    } catch (error) {
        console.error('Failed to migrate theme storage:', error);
        return false;
    }
}

// Auto-run migration on module load
try {
    migrateThemeStorage();
} catch (error) {
    console.warn('Theme migration check failed:', error);
}

/**
 * Export configuration for external access
 */
export const THEME_CONFIG = {
    ...CONFIG,
    isLocalStorageAvailable
};