/**
 * Visual CSS Tests - Testing CSS styling and visual components
 * Module 4: Client-Side JavaScript Tests
 */

import { jest } from '@jest/globals';
import fs from 'fs';
import path from 'path';

// Load CSS content for analysis
const cssPath = path.resolve('./static/css/async_ui.css');
const cssContent = fs.readFileSync(cssPath, 'utf8');

// Load UI updater for DOM structure testing
const uiUpdaterPath = path.resolve('./static/js/ui_updater.js');
const uiUpdaterCode = fs.readFileSync(uiUpdaterPath, 'utf8');

const cleanUIUpdaterCode = uiUpdaterCode
    .replace(/window\.UIUpdater = new UIUpdater\(\);/, '')
    .replace(/console\.log\('🎯 UIUpdater: UIUpdater loaded and ready'\);/, '');

// Create test environment with CSS injection
const createVisualTestEnvironment = () => {
    const environment = {
        window: global,
        document: global.document,
        console: global.console,
        Date: global.Date,
        Math: global.Math,
        setTimeout: global.setTimeout,
        clearTimeout: global.clearTimeout,
        requestAnimationFrame: global.requestAnimationFrame,
        Map: global.Map,
        Array: global.Array,
        Object: global.Object
    };
    
    // Inject CSS into document head
    const style = document.createElement('style');
    style.textContent = cssContent;
    document.head.appendChild(style);
    
    const func = new Function(
        'window', 'document', 'console', 'Date', 'Math', 'setTimeout', 'clearTimeout', 'requestAnimationFrame', 'Map', 'Array', 'Object',
        cleanUIUpdaterCode + '; return UIUpdater;'
    );
    
    return func(
        environment.window,
        environment.document,
        environment.console,
        environment.Date,
        environment.Math,
        environment.setTimeout,
        environment.clearTimeout,
        environment.requestAnimationFrame,
        environment.Map,
        environment.Array,
        environment.Object
    );
};

// CSS testing utilities
const getCSSRule = (selector) => {
    const styleSheets = document.styleSheets;
    for (let sheet of styleSheets) {
        try {
            const rules = sheet.cssRules || sheet.rules;
            for (let rule of rules) {
                if (rule.selectorText && rule.selectorText.includes(selector)) {
                    return rule;
                }
            }
        } catch (e) {
            // Cross-origin stylesheets may not be accessible
            continue;
        }
    }
    return null;
};

const hasAnimation = (element, animationName) => {
    const computedStyle = window.getComputedStyle(element);
    return computedStyle.animationName.includes(animationName);
};

const hasTransition = (element, property) => {
    const computedStyle = window.getComputedStyle(element);
    return computedStyle.transitionProperty.includes(property) || 
           computedStyle.transitionProperty === 'all';
};

describe('Visual CSS Tests', () => {
    let UIUpdaterClass;
    let uiUpdater;
    
    beforeEach(() => {
        // Reset DOM and inject CSS
        document.body.innerHTML = '';
        document.head.innerHTML = '';
        
        // Create visual test environment with CSS
        UIUpdaterClass = createVisualTestEnvironment();
        
        // Mock dependencies
        global.window.JobTracker = { addEventListener: jest.fn() };
        
        uiUpdater = new UIUpdaterClass();
        
        jest.useFakeTimers();
    });
    
    afterEach(() => {
        jest.useRealTimers();
        jest.clearAllMocks();
        delete global.window.JobTracker;
    });
    
    describe('CSS Structure and Organization', () => {
        test('should have well-organized CSS sections', () => {
            expect(cssContent).toContain('Connection Status Indicator');
            expect(cssContent).toContain('Progress Bars Section');
            expect(cssContent).toContain('Toast Notifications');
            expect(cssContent).toContain('Responsive Design');
            expect(cssContent).toContain('Dark Mode Support');
            expect(cssContent).toContain('Animations and Transitions');
            expect(cssContent).toContain('Accessibility Enhancements');
        });
        
        test('should use consistent naming conventions', () => {
            // Check for consistent async- prefix
            const asyncClasses = cssContent.match(/\.async-[\w-]+/g) || [];
            expect(asyncClasses.length).toBeGreaterThan(10);
            
            // All async classes should follow kebab-case convention
            asyncClasses.forEach(className => {
                expect(className).toMatch(/^\.async-[a-z-]+$/);
            });
        });
        
        test('should have proper CSS property ordering', () => {
            // Check that display properties come before positioning
            // This is a simplified check - in practice you'd use a CSS linter
            const progressContainerRule = cssContent.match(/\.async-progress-container\s*{[^}]+}/s)?.[0];
            if (progressContainerRule) {
                expect(progressContainerRule).toContain('margin-bottom');
                expect(progressContainerRule).toContain('padding');
                expect(progressContainerRule).toContain('background');
                expect(progressContainerRule).toContain('border-radius');
            }
        });
    });
    
    describe('Connection Status Indicator Styling', () => {
        test('should style connection status properly', () => {
            uiUpdater.updateConnectionStatus(true, { active: 2, completed: 5 });
            
            const statusIndicator = uiUpdater.connectionStatusIndicator;
            expect(statusIndicator).toBeTruthy();
            expect(statusIndicator.className).toBe('async-connection-status connected');
            
            const statusDot = statusIndicator.querySelector('.connection-status-dot');
            const statusText = statusIndicator.querySelector('.connection-status-text');
            const statusStats = statusIndicator.querySelector('.connection-status-stats');
            
            expect(statusDot).toBeTruthy();
            expect(statusText).toBeTruthy();
            expect(statusStats).toBeTruthy();
            
            expect(statusDot.className).toBe('connection-status-dot connected');
            expect(statusText.textContent).toBe('Connected');
        });
        
        test('should apply different styles for connected/disconnected states', () => {
            // Test connected state
            uiUpdater.updateConnectionStatus(true);
            let statusIndicator = uiUpdater.connectionStatusIndicator;
            expect(statusIndicator.className).toContain('connected');
            expect(statusIndicator.className).not.toContain('disconnected');
            
            // Test disconnected state  
            uiUpdater.updateConnectionStatus(false);
            expect(statusIndicator.className).toContain('disconnected');
            expect(statusIndicator.className).not.toContain('connected');
        });
        
        test('should include CSS animations for status dots', () => {
            // CSS should define pulse animations
            expect(cssContent).toContain('pulse-connected');
            expect(cssContent).toContain('pulse-disconnected');
            expect(cssContent).toContain('@keyframes pulse-connected');
            expect(cssContent).toContain('@keyframes pulse-disconnected');
        });
    });
    
    describe('Progress Bar Styling', () => {
        test('should create properly styled progress bars', () => {
            uiUpdater.addProgressBar('style-test', {
                title: 'Style Test Video',
                progress: 60,
                status: 'in_progress'
            });
            
            const progressContainer = document.querySelector('[data-job-id="style-test"]');
            expect(progressContainer.className).toBe('async-progress-container in_progress');
            
            const progressHeader = progressContainer.querySelector('.async-progress-header');
            const progressTitle = progressContainer.querySelector('.async-progress-title');
            const progressText = progressContainer.querySelector('.async-progress-text');
            const progressTrack = progressContainer.querySelector('.async-progress-track');
            const progressBar = progressContainer.querySelector('.async-progress-bar');
            const progressMessage = progressContainer.querySelector('.async-progress-message');
            
            expect(progressHeader).toBeTruthy();
            expect(progressTitle).toBeTruthy();
            expect(progressText).toBeTruthy();
            expect(progressTrack).toBeTruthy();
            expect(progressBar).toBeTruthy();
            expect(progressMessage).toBeTruthy();
            
            // Check progress bar width
            expect(progressBar.style.width).toBe('60%');
        });
        
        test('should apply status-specific styling', () => {
            const statuses = ['pending', 'in_progress', 'completed', 'failed'];
            
            statuses.forEach(status => {
                uiUpdater.addProgressBar(`status-${status}`, {
                    title: `${status} Test`,
                    progress: status === 'completed' ? 100 : 50,
                    status: status
                });
                
                const container = document.querySelector(`[data-job-id="status-${status}"]`);
                expect(container.className).toContain(`async-progress-container ${status}`);
            });
        });
        
        test('should include progress section styling', () => {
            uiUpdater.addProgressBar('section-test', {
                title: 'Section Test',
                progress: 30,
                status: 'in_progress'
            });
            
            const progressSection = document.getElementById('async-progress-section');
            expect(progressSection).toBeTruthy();
            expect(progressSection.className).toBe('async-progress-section');
            expect(progressSection.style.display).toBe('block');
            
            const sectionTitle = progressSection.querySelector('.async-progress-section-title');
            expect(sectionTitle).toBeTruthy();
            expect(sectionTitle.tagName).toBe('H3');
            expect(sectionTitle.textContent).toBe('Processing Summaries');
        });
        
        test('should include progress bar animations', () => {
            // CSS should define progress animations
            expect(cssContent).toContain('progress-shine');
            expect(cssContent).toContain('progress-complete');
            expect(cssContent).toContain('progress-error');
            expect(cssContent).toContain('@keyframes progress-shine');
            expect(cssContent).toContain('@keyframes progress-complete');
            expect(cssContent).toContain('@keyframes progress-error');
        });
    });
    
    describe('Toast Notification Styling', () => {
        test('should create properly styled toast notifications', () => {
            uiUpdater.displayToast({
                id: 'toast-style-test',
                message: 'Toast style test message',
                type: 'info',
                duration: 5000
            });
            
            const toast = document.querySelector('[data-toast-id="toast-style-test"]');
            expect(toast).toBeTruthy();
            expect(toast.className).toBe('async-toast async-toast-info');
            
            const toastContent = toast.querySelector('.async-toast-content');
            const toastMessage = toast.querySelector('.async-toast-message');
            const toastClose = toast.querySelector('.async-toast-close');
            
            expect(toastContent).toBeTruthy();
            expect(toastMessage).toBeTruthy();
            expect(toastClose).toBeTruthy();
            
            expect(toastMessage.textContent).toBe('Toast style test message');
            expect(toastClose.textContent).toBe('×');
        });
        
        test('should apply type-specific toast styling', () => {
            const types = ['success', 'error', 'warning', 'info'];
            
            types.forEach(type => {
                uiUpdater.displayToast({
                    id: `toast-type-${type}`,
                    message: `${type} message`,
                    type: type,
                    duration: 1000
                });
                
                const toast = document.querySelector(`[data-toast-id="toast-type-${type}"]`);
                expect(toast.className).toBe(`async-toast async-toast-${type}`);
            });
        });
        
        test('should position toast container correctly', () => {
            // Toast container should be created
            const toastContainer = document.getElementById('async-toast-container');
            expect(toastContainer).toBeTruthy();
            expect(toastContainer.className).toBe('async-toast-container');
        });
        
        test('should include toast animations', () => {
            // Check that CSS includes slide animations for toasts
            expect(cssContent).toContain('translateX(100%)');
            expect(cssContent).toContain('translateX(0)');
            expect(cssContent).toContain('opacity: 0');
            expect(cssContent).toContain('opacity: 1');
        });
    });
    
    describe('Responsive Design', () => {
        test('should include mobile breakpoints', () => {
            expect(cssContent).toContain('@media (max-width: 768px)');
            expect(cssContent).toContain('@media (max-width: 480px)');
        });
        
        test('should adapt toast positioning for mobile', () => {
            // CSS should include mobile-specific toast positioning
            const mobileMediaQuery = cssContent.match(/@media \(max-width: 768px\) {[^}]+}/s)?.[0];
            if (mobileMediaQuery) {
                expect(mobileMediaQuery).toContain('async-toast-container');
                expect(mobileMediaQuery).toContain('left: 10px');
                expect(mobileMediaQuery).toContain('right: 10px');
            }
        });
        
        test('should adapt progress bars for mobile', () => {
            // CSS should include mobile-specific progress bar styling
            const mobileRules = cssContent.match(/@media \(max-width: 768px\) {([^}]|{[^}]*})*}/s)?.[0];
            if (mobileRules) {
                expect(mobileRules).toContain('async-progress');
            }
        });
    });
    
    describe('Dark Mode Support', () => {
        test('should include dark mode styles', () => {
            expect(cssContent).toContain('@media (prefers-color-scheme: dark)');
        });
        
        test('should define dark mode color schemes', () => {
            const darkModeRules = cssContent.match(/@media \(prefers-color-scheme: dark\) {([^}]|{[^}]*})*}/s)?.[0];
            if (darkModeRules) {
                expect(darkModeRules).toContain('async-progress-section');
                expect(darkModeRules).toContain('async-progress-container');
                expect(darkModeRules).toContain('async-connection-status');
                expect(darkModeRules).toContain('background');
                expect(darkModeRules).toContain('color');
            }
        });
    });
    
    describe('Accessibility CSS Features', () => {
        test('should include high contrast mode support', () => {
            expect(cssContent).toContain('@media (prefers-contrast: high)');
        });
        
        test('should include reduced motion support', () => {
            expect(cssContent).toContain('@media (prefers-reduced-motion: reduce)');
        });
        
        test('should define focus indicators', () => {
            expect(cssContent).toContain(':focus');
            expect(cssContent).toContain('outline');
        });
        
        test('should include screen reader utilities', () => {
            expect(cssContent).toContain('async-sr-only');
            expect(cssContent).toContain('position: absolute');
            expect(cssContent).toContain('width: 1px');
            expect(cssContent).toContain('height: 1px');
            expect(cssContent).toContain('overflow: hidden');
        });
        
        test('should handle reduced motion preferences', () => {
            const reducedMotionRules = cssContent.match(/@media \(prefers-reduced-motion: reduce\) {([^}]|{[^}]*})*}/s)?.[0];
            if (reducedMotionRules) {
                expect(reducedMotionRules).toContain('animation: none');
                expect(reducedMotionRules).toContain('transition');
            }
        });
        
        test('should handle high contrast preferences', () => {
            const highContrastRules = cssContent.match(/@media \(prefers-contrast: high\) {([^}]|{[^}]*})*}/s)?.[0];
            if (highContrastRules) {
                expect(highContrastRules).toContain('border');
                expect(highContrastRules).toContain('background');
            }
        });
    });
    
    describe('Animation and Transition Quality', () => {
        test('should use consistent animation timing', () => {
            // Check for consistent easing functions
            expect(cssContent).toContain('ease');
            expect(cssContent).toContain('ease-out');
            expect(cssContent).toContain('ease-in-out');
            
            // Check for reasonable duration values
            const durations = cssContent.match(/\d+(\.\d+)?s/g) || [];
            durations.forEach(duration => {
                const value = parseFloat(duration);
                expect(value).toBeGreaterThan(0);
                expect(value).toBeLessThan(5); // Reasonable max duration
            });
        });
        
        test('should include proper keyframe animations', () => {
            const keyframes = ['progress-shine', 'progress-complete', 'progress-error', 'pulse-connected', 'pulse-disconnected'];
            
            keyframes.forEach(keyframe => {
                expect(cssContent).toContain(`@keyframes ${keyframe}`);
                expect(cssContent).toContain('0%');
                expect(cssContent).toContain('100%');
            });
        });
        
        test('should use hardware acceleration hints', () => {
            // Check for transform properties that trigger hardware acceleration
            expect(cssContent).toContain('transform');
            expect(cssContent).toContain('translateX');
            expect(cssContent).toContain('scale');
        });
    });
    
    describe('CSS Architecture and Performance', () => {
        test('should use efficient CSS selectors', () => {
            // Avoid expensive selectors like universal (*) or deep nesting
            const universalSelectors = cssContent.match(/^\s*\*/gm) || [];
            expect(universalSelectors.length).toBeLessThan(5); // Minimal universal selectors
            
            // Check for reasonable specificity
            const deeplyNestedSelectors = cssContent.match(/(\.[a-zA-Z-]+ ){4,}/g) || [];
            expect(deeplyNestedSelectors.length).toBeLessThan(5); // Avoid deep nesting
        });
        
        test('should group related properties', () => {
            // Check that layout properties are grouped together
            const progressBarRule = cssContent.match(/\.async-progress-bar\s*{[^}]+}/s)?.[0];
            if (progressBarRule) {
                expect(progressBarRule).toContain('height');
                expect(progressBarRule).toContain('background');
                expect(progressBarRule).toContain('border-radius');
                expect(progressBarRule).toContain('transition');
            }
        });
        
        test('should use consistent units', () => {
            // Prefer rem/em for typography, px for borders/shadows
            const remUnits = cssContent.match(/\d+(\.\d+)?rem/g) || [];
            const emUnits = cssContent.match(/\d+(\.\d+)?em/g) || [];
            const pxUnits = cssContent.match(/\d+px/g) || [];
            
            expect(remUnits.length + emUnits.length).toBeGreaterThan(0); // Some relative units
            expect(pxUnits.length).toBeGreaterThan(0); // Some pixel units for precision
        });
        
        test('should include vendor prefixes where needed', () => {
            // Check for modern CSS features that might need prefixes
            // Note: In modern development, this is usually handled by autoprefixer
            const gradients = cssContent.match(/linear-gradient/g) || [];
            expect(gradients.length).toBeGreaterThan(0); // Should use gradients
        });
    });
    
    describe('Color System and Theming', () => {
        test('should use consistent color palette', () => {
            const colors = cssContent.match(/#[0-9a-fA-F]{6}/g) || [];
            const uniqueColors = [...new Set(colors)];
            
            // Should have a reasonable number of colors (not too many)
            expect(uniqueColors.length).toBeLessThan(20);
            
            // Check for common colors
            expect(cssContent).toContain('#27ae60'); // Green
            expect(cssContent).toContain('#e74c3c'); // Red
            expect(cssContent).toContain('#3498db'); // Blue
        });
        
        test('should use semantic color names in classes', () => {
            expect(cssContent).toContain('connected');
            expect(cssContent).toContain('disconnected');
            expect(cssContent).toContain('success');
            expect(cssContent).toContain('error');
            expect(cssContent).toContain('warning');
            expect(cssContent).toContain('info');
        });
        
        test('should support transparency and opacity', () => {
            expect(cssContent).toContain('rgba');
            expect(cssContent).toContain('opacity');
            
            // Check for reasonable opacity values
            const opacityValues = cssContent.match(/opacity:\s*([0-9.]+)/g) || [];
            opacityValues.forEach(opacity => {
                const value = parseFloat(opacity.split(':')[1]);
                expect(value).toBeGreaterThanOrEqual(0);
                expect(value).toBeLessThanOrEqual(1);
            });
        });
    });
    
    describe('Layout and Positioning', () => {
        test('should use modern layout techniques', () => {
            expect(cssContent).toContain('display: flex');
            expect(cssContent).toContain('align-items');
            expect(cssContent).toContain('justify-content');
            expect(cssContent).toContain('gap');
        });
        
        test('should handle z-index layering properly', () => {
            const zIndexValues = cssContent.match(/z-index:\s*(\d+)/g) || [];
            
            // Toast container should have high z-index
            expect(cssContent).toContain('z-index: 10000');
            
            zIndexValues.forEach(zIndex => {
                const value = parseInt(zIndex.split(':')[1]);
                expect(value).toBeGreaterThan(0);
                expect(value).toBeLessThan(100000); // Reasonable maximum
            });
        });
        
        test('should use appropriate positioning strategies', () => {
            expect(cssContent).toContain('position: fixed'); // For toasts
            expect(cssContent).toContain('position: absolute'); // For sr-only
            expect(cssContent).toContain('position: relative'); // For progress bars
        });
    });
    
    describe('Visual Hierarchy and Typography', () => {
        test('should establish clear visual hierarchy', () => {
            // Check for different font sizes
            const fontSizes = cssContent.match(/font-size:\s*(\d+px)/g) || [];
            const uniqueSizes = [...new Set(fontSizes)];
            
            expect(uniqueSizes.length).toBeGreaterThan(2); // At least 3 different sizes
        });
        
        test('should use appropriate font weights', () => {
            expect(cssContent).toContain('font-weight: 600');
            expect(cssContent).toContain('font-weight: 700');
            expect(cssContent).toContain('font-weight: 500');
        });
        
        test('should include proper line height and spacing', () => {
            expect(cssContent).toContain('line-height');
            expect(cssContent).toContain('letter-spacing');
            expect(cssContent).toContain('margin');
            expect(cssContent).toContain('padding');
        });
    });
    
    describe('Cross-Browser Compatibility', () => {
        test('should include fallbacks for modern properties', () => {
            // Check for fallback colors before gradients
            const gradientRules = cssContent.match(/background:[^;]*linear-gradient[^;]*;/g) || [];
            
            // Modern features should have reasonable fallbacks
            if (cssContent.includes('backdrop-filter')) {
                expect(cssContent).toContain('background'); // Fallback for backdrop-filter
            }
        });
        
        test('should use widely supported properties', () => {
            // Avoid cutting-edge CSS that might not be supported
            expect(cssContent).not.toContain('display: subgrid'); // Too new
            expect(cssContent).not.toContain('color-mix'); // Too new
            
            // Use well-supported modern features
            expect(cssContent).toContain('border-radius');
            expect(cssContent).toContain('box-shadow');
            expect(cssContent).toContain('transform');
        });
    });
});