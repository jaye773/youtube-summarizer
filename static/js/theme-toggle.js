/**
 * YouTube Summarizer Theme Toggle Component
 * Toggle button component for switching between light and dark themes
 * 
 * @author YouTube Summarizer Team
 * @version 1.0.0
 */

import themeManager from './theme-manager.js';

/**
 * Theme Toggle Component class
 * Manages the theme toggle button and its interactions
 */
class ThemeToggle {
    constructor() {
        this.button = null;
        this.iconContainer = null;
        this.sunIcon = null;
        this.moonIcon = null;
        this.initialized = false;
        
        // Configuration
        this.config = {
            buttonId: 'theme-toggle-btn',
            iconContainerId: 'theme-toggle-icon',
            animationDuration: 300,
            rotationDegrees: 180,
            scaleEffect: 1.1
        };
        
        // Bind methods to preserve context
        this.handleClick = this.handleClick.bind(this);
        this.handleKeydown = this.handleKeydown.bind(this);
        this.handleThemeChange = this.handleThemeChange.bind(this);
        this.handleSystemPreferenceChange = this.handleSystemPreferenceChange.bind(this);
    }
    
    /**
     * Initialize the theme toggle component
     * 
     * @returns {Promise<boolean>} True if initialization successful
     */
    async init() {
        if (this.initialized) {
            console.warn('Theme toggle already initialized');
            return true;
        }
        
        try {
            // Wait for theme manager to be ready
            if (!themeManager.initialized) {
                await this.waitForThemeManager();
            }
            
            // Create toggle button element
            this.createToggleButton();
            
            // Set up event listeners
            this.setupEventListeners();
            
            // Update initial state
            this.updateButtonState();
            
            this.initialized = true;
            
            // Emit initialization complete event
            this.emitToggleEvent('theme-toggle-initialized', {
                buttonId: this.config.buttonId,
                currentTheme: themeManager.getTheme(),
                effectiveTheme: themeManager.getEffectiveTheme()
            });
            
            console.log('✅ Theme toggle component initialized');
            return true;
            
        } catch (error) {
            console.error('Failed to initialize theme toggle:', error);
            return false;
        }
    }
    
    /**
     * Wait for theme manager to be initialized
     * 
     * @private
     * @returns {Promise<void>}
     */
    waitForThemeManager() {
        return new Promise((resolve) => {
            if (themeManager.initialized) {
                resolve();
                return;
            }
            
            const checkInterval = setInterval(() => {
                if (themeManager.initialized) {
                    clearInterval(checkInterval);
                    resolve();
                }
            }, 10);
            
            // Timeout after 5 seconds
            setTimeout(() => {
                clearInterval(checkInterval);
                resolve();
            }, 5000);
        });
    }
    
    /**
     * Create the theme toggle button element
     * 
     * @private
     * @returns {void}
     */
    createToggleButton() {
        // Find the settings button to position next to it
        const settingsBtn = document.querySelector('.settings-btn');
        if (!settingsBtn) {
            throw new Error('Settings button not found - cannot position theme toggle');
        }
        
        // Create the toggle button
        this.button = document.createElement('button');
        this.button.id = this.config.buttonId;
        this.button.className = 'theme-toggle-btn';
        this.button.type = 'button';
        this.button.setAttribute('aria-label', 'Toggle theme');
        this.button.setAttribute('aria-pressed', 'false');
        this.button.setAttribute('title', 'Toggle between light and dark theme');
        
        // Create icon container
        this.iconContainer = document.createElement('div');
        this.iconContainer.id = this.config.iconContainerId;
        this.iconContainer.className = 'theme-toggle-icon';
        this.iconContainer.setAttribute('aria-hidden', 'true');
        
        // Load and insert SVG icons
        this.loadIcons();
        
        // Append icon to button
        this.button.appendChild(this.iconContainer);
        
        // Insert button before settings button
        settingsBtn.parentNode.insertBefore(this.button, settingsBtn);
    }
    
    /**
     * Load and create SVG icons
     * 
     * @private
     * @returns {void}
     */
    loadIcons() {
        // Create sun icon (light mode)
        this.sunIcon = this.createSunIcon();
        this.sunIcon.classList.add('theme-icon', 'sun-icon');
        
        // Create moon icon (dark mode)
        this.moonIcon = this.createMoonIcon();
        this.moonIcon.classList.add('theme-icon', 'moon-icon');
        
        // Add both icons to container
        this.iconContainer.appendChild(this.sunIcon);
        this.iconContainer.appendChild(this.moonIcon);
    }
    
    /**
     * Create sun SVG icon
     * 
     * @private
     * @returns {SVGElement} Sun icon element
     */
    createSunIcon() {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('fill', 'none');
        svg.setAttribute('stroke', 'currentColor');
        svg.setAttribute('stroke-width', '2');
        svg.setAttribute('stroke-linecap', 'round');
        svg.setAttribute('stroke-linejoin', 'round');
        
        svg.innerHTML = `
            <circle cx="12" cy="12" r="5"/>
            <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
        `;
        
        return svg;
    }
    
    /**
     * Create moon SVG icon
     * 
     * @private
     * @returns {SVGElement} Moon icon element
     */
    createMoonIcon() {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('fill', 'none');
        svg.setAttribute('stroke', 'currentColor');
        svg.setAttribute('stroke-width', '2');
        svg.setAttribute('stroke-linecap', 'round');
        svg.setAttribute('stroke-linejoin', 'round');
        
        svg.innerHTML = `
            <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>
        `;
        
        return svg;
    }
    
    /**
     * Set up event listeners
     * 
     * @private
     * @returns {void}
     */
    setupEventListeners() {
        if (!this.button) return;
        
        // Button click event
        this.button.addEventListener('click', this.handleClick);
        
        // Keyboard support
        this.button.addEventListener('keydown', this.handleKeydown);
        
        // Theme change events from theme manager
        document.addEventListener('theme-changed', this.handleThemeChange);
        document.addEventListener('system-preference-changed', this.handleSystemPreferenceChange);
        
        // Focus and hover effects
        this.button.addEventListener('focus', this.handleFocus.bind(this));
        this.button.addEventListener('blur', this.handleBlur.bind(this));
    }
    
    /**
     * Handle button click
     * 
     * @private
     * @param {Event} event - Click event
     * @returns {void}
     */
    handleClick(event) {
        event.preventDefault();
        
        // Prevent double clicks during animation
        if (this.button.classList.contains('animating')) {
            return;
        }
        
        try {
            // Toggle theme
            const newTheme = themeManager.toggleTheme();
            
            // Play toggle animation
            this.playToggleAnimation();
            
            // Update ARIA pressed state
            this.updateAriaPressed();
            
            // Emit toggle event
            this.emitToggleEvent('theme-toggle-clicked', {
                newTheme: newTheme,
                previousTheme: themeManager.getTheme()
            });
            
        } catch (error) {
            console.error('Error toggling theme:', error);
        }
    }
    
    /**
     * Handle keyboard events
     * 
     * @private
     * @param {KeyboardEvent} event - Keyboard event
     * @returns {void}
     */
    handleKeydown(event) {
        // Support Enter and Space keys
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            this.handleClick(event);
        }
    }
    
    /**
     * Handle theme change events
     * 
     * @private
     * @param {CustomEvent} event - Theme change event
     * @returns {void}
     */
    handleThemeChange(event) {
        this.updateButtonState();
        this.updateAriaLabel(event.detail.currentEffectiveTheme);
    }
    
    /**
     * Handle system preference changes
     * 
     * @private
     * @param {CustomEvent} event - System preference change event
     * @returns {void}
     */
    handleSystemPreferenceChange(event) {
        // Only update if we're in auto mode
        if (themeManager.isAutoMode()) {
            this.updateButtonState();
            this.updateAriaLabel(event.detail.effectiveTheme);
        }
    }
    
    /**
     * Handle focus events
     * 
     * @private
     * @returns {void}
     */
    handleFocus() {
        this.button.classList.add('focused');
    }
    
    /**
     * Handle blur events
     * 
     * @private
     * @returns {void}
     */
    handleBlur() {
        this.button.classList.remove('focused');
    }
    
    /**
     * Update button state based on current theme
     * 
     * @private
     * @returns {void}
     */
    updateButtonState() {
        if (!this.button || !this.iconContainer) return;
        
        const effectiveTheme = themeManager.getEffectiveTheme();
        const isDarkMode = effectiveTheme === 'dark';
        
        // Update button class
        this.button.className = `theme-toggle-btn ${effectiveTheme}-mode`;
        
        // Update icon container class
        this.iconContainer.className = `theme-toggle-icon ${effectiveTheme}-mode`;
        
        // Show/hide appropriate icons
        if (this.sunIcon && this.moonIcon) {
            this.sunIcon.style.opacity = isDarkMode ? '0' : '1';
            this.moonIcon.style.opacity = isDarkMode ? '1' : '0';
        }
        
        // Update ARIA states
        this.updateAriaPressed();
        this.updateAriaLabel(effectiveTheme);
    }
    
    /**
     * Update ARIA pressed state
     * 
     * @private
     * @returns {void}
     */
    updateAriaPressed() {
        if (!this.button) return;
        
        const isDarkMode = themeManager.getEffectiveTheme() === 'dark';
        this.button.setAttribute('aria-pressed', isDarkMode ? 'true' : 'false');
    }
    
    /**
     * Update ARIA label based on current theme
     * 
     * @private
     * @param {string} currentTheme - Current effective theme
     * @returns {void}
     */
    updateAriaLabel(currentTheme) {
        if (!this.button) return;
        
        const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
        const label = `Switch to ${nextTheme} theme (currently ${currentTheme})`;
        
        this.button.setAttribute('aria-label', label);
        this.button.setAttribute('title', label);
    }
    
    /**
     * Play toggle animation
     * 
     * @private
     * @returns {void}
     */
    playToggleAnimation() {
        if (!this.iconContainer) return;
        
        // Prevent multiple animations
        if (this.button.classList.contains('animating')) {
            return;
        }
        
        this.button.classList.add('animating');
        
        // Apply animation classes
        this.iconContainer.classList.add('rotating');
        
        // Remove animation classes after animation completes
        setTimeout(() => {
            if (this.button && this.iconContainer) {
                this.button.classList.remove('animating');
                this.iconContainer.classList.remove('rotating');
            }
        }, this.config.animationDuration);
    }
    
    /**
     * Emit a custom toggle event
     * 
     * @private
     * @param {string} eventName - Name of the event
     * @param {object} detail - Event detail object
     * @returns {void}
     */
    emitToggleEvent(eventName, detail) {
        try {
            const event = new CustomEvent(eventName, {
                detail: {
                    ...detail,
                    toggleId: this.config.buttonId,
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
     * Show the toggle button (for programmatic control)
     * 
     * @returns {void}
     */
    show() {
        if (this.button) {
            this.button.style.display = '';
            this.button.removeAttribute('hidden');
        }
    }
    
    /**
     * Hide the toggle button (for programmatic control)
     * 
     * @returns {void}
     */
    hide() {
        if (this.button) {
            this.button.style.display = 'none';
            this.button.setAttribute('hidden', '');
        }
    }
    
    /**
     * Get current toggle button element
     * 
     * @returns {HTMLElement|null} Button element or null if not initialized
     */
    getButton() {
        return this.button;
    }
    
    /**
     * Check if component is initialized
     * 
     * @returns {boolean} True if initialized
     */
    isInitialized() {
        return this.initialized;
    }
    
    /**
     * Destroy the theme toggle component
     * 
     * @returns {void}
     */
    destroy() {
        try {
            // Remove event listeners
            if (this.button) {
                this.button.removeEventListener('click', this.handleClick);
                this.button.removeEventListener('keydown', this.handleKeydown);
                this.button.removeEventListener('focus', this.handleFocus);
                this.button.removeEventListener('blur', this.handleBlur);
            }
            
            document.removeEventListener('theme-changed', this.handleThemeChange);
            document.removeEventListener('system-preference-changed', this.handleSystemPreferenceChange);
            
            // Remove button from DOM
            if (this.button && this.button.parentNode) {
                this.button.parentNode.removeChild(this.button);
            }
            
            // Clear references
            this.button = null;
            this.iconContainer = null;
            this.sunIcon = null;
            this.moonIcon = null;
            this.initialized = false;
            
        } catch (error) {
            console.warn('Failed to destroy theme toggle:', error);
        }
    }
}

// Create singleton instance
const themeToggle = new ThemeToggle();

// Export singleton instance and class
export default themeToggle;
export { ThemeToggle };

// Auto-initialize when DOM is ready and script is loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        // Add small delay to ensure theme manager is ready
        setTimeout(() => {
            themeToggle.init();
        }, 100);
    });
} else {
    // DOM is already loaded
    setTimeout(() => {
        themeToggle.init();
    }, 100);
}

// Hide button if JavaScript is disabled (progressive enhancement)
// This is handled by CSS with .no-js class on html element
if (document.documentElement.classList.contains('no-js')) {
    document.documentElement.classList.remove('no-js');
}

// Ensure button is visible when JavaScript is enabled
document.documentElement.classList.add('js-enabled');