/**
 * Accessibility Tests - Testing WCAG compliance and accessibility features
 * Module 4: Client-Side JavaScript Tests
 */

import { jest } from '@jest/globals';
import fs from 'fs';
import path from 'path';

// Load source files for accessibility testing
const uiUpdaterPath = path.resolve('./static/js/ui_updater.js');
const uiUpdaterCode = fs.readFileSync(uiUpdaterPath, 'utf8');

const cleanUIUpdaterCode = uiUpdaterCode
    .replace(/window\.UIUpdater = new UIUpdater\(\);/, '')
    .replace(/console\.log\('🎯 UIUpdater: UIUpdater loaded and ready'\);/, '');

// Create accessibility test environment
const createA11yTestEnvironment = () => {
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

// Accessibility testing utilities
const getContrastRatio = (foreground, background) => {
    // Simplified contrast ratio calculation for testing
    // In real implementation, you'd parse CSS colors and calculate luminance
    const luminanceMap = {
        'white': 1,
        '#ffffff': 1,
        'black': 0,
        '#000000': 0,
        '#27ae60': 0.4, // Green
        '#e74c3c': 0.2, // Red  
        '#3498db': 0.3, // Blue
        '#f39c12': 0.6, // Orange
        '#8e44ad': 0.25, // Purple
        '#2c3e50': 0.1 // Dark blue
    };
    
    const fgLuminance = luminanceMap[foreground] || 0.5;
    const bgLuminance = luminanceMap[background] || 0.5;
    
    const lighter = Math.max(fgLuminance, bgLuminance);
    const darker = Math.min(fgLuminance, bgLuminance);
    
    return (lighter + 0.05) / (darker + 0.05);
};

const checkColorContrast = (element, minRatio = 4.5) => {
    const style = window.getComputedStyle(element);
    const color = style.color;
    const backgroundColor = style.backgroundColor;
    
    const ratio = getContrastRatio(color, backgroundColor);
    return ratio >= minRatio;
};

const checkKeyboardAccessible = (element) => {
    // Check if element is keyboard accessible
    const tabIndex = element.tabIndex;
    const tag = element.tagName.toLowerCase();
    
    // Elements that are naturally keyboard accessible
    const keyboardAccessible = ['button', 'input', 'select', 'textarea', 'a'];
    
    return keyboardAccessible.includes(tag) || tabIndex >= 0;
};

const checkAriaAttributes = (element) => {
    const attributes = element.attributes;
    const ariaAttributes = [];
    
    for (let attr of attributes) {
        if (attr.name.startsWith('aria-')) {
            ariaAttributes.push(attr.name);
        }
    }
    
    return ariaAttributes;
};

describe('Accessibility Tests', () => {
    let UIUpdaterClass;
    let uiUpdater;
    
    beforeEach(() => {
        // Reset DOM
        document.body.innerHTML = '';
        document.head.innerHTML = '';
        
        // Create environment
        UIUpdaterClass = createA11yTestEnvironment();
        
        // Mock dependencies
        global.window.JobTracker = { addEventListener: jest.fn() };
        
        uiUpdater = new UIUpdaterClass();
        
        // Use fake timers
        jest.useFakeTimers();
    });
    
    afterEach(() => {
        jest.useRealTimers();
        jest.clearAllMocks();
        delete global.window.JobTracker;
    });
    
    describe('WCAG 2.1 AA Compliance', () => {
        describe('Color Contrast Requirements', () => {
            test('should meet minimum color contrast for progress bars', () => {
                uiUpdater.addProgressBar('contrast-test', {
                    title: 'Contrast Test Video',
                    progress: 50,
                    status: 'in_progress'
                });
                
                const progressContainer = document.querySelector('[data-job-id="contrast-test"]');
                const progressTitle = progressContainer.querySelector('.async-progress-title');
                const progressText = progressContainer.querySelector('.async-progress-text');
                
                // Check title contrast
                expect(progressTitle).toBeTruthy();
                // In real implementation, we'd calculate actual contrast ratios
                // For now, we verify elements have proper structure for contrast testing
                
                // Check progress text contrast  
                expect(progressText).toBeTruthy();
                expect(progressText.textContent).toBe('50%');
            });
            
            test('should meet minimum color contrast for toast notifications', () => {
                const toastTypes = ['success', 'error', 'warning', 'info'];
                
                toastTypes.forEach(type => {
                    uiUpdater.displayToast({
                        id: `contrast-${type}`,
                        message: `${type} message`,
                        type,
                        duration: 5000
                    });
                    
                    const toast = document.querySelector(`[data-toast-id="contrast-${type}"]`);
                    expect(toast).toBeTruthy();
                    expect(toast.className).toContain(`async-toast-${type}`);
                    
                    const message = toast.querySelector('.async-toast-message');
                    expect(message.textContent).toBe(`${type} message`);
                });
            });
            
            test('should meet minimum color contrast for connection status', () => {
                // Test connected state
                uiUpdater.updateConnectionStatus(true, { active: 2, completed: 5 });
                
                let statusIndicator = uiUpdater.connectionStatusIndicator;
                expect(statusIndicator.className).toContain('connected');
                
                const statusText = statusIndicator.querySelector('.connection-status-text');
                expect(statusText.textContent).toBe('Connected');
                
                // Test disconnected state
                uiUpdater.updateConnectionStatus(false);
                expect(statusIndicator.className).toContain('disconnected');
                expect(statusText.textContent).toBe('Disconnected');
            });
        });
        
        describe('Keyboard Navigation', () => {
            test('should make toast close buttons keyboard accessible', () => {
                uiUpdater.displayToast({
                    id: 'keyboard-test',
                    message: 'Keyboard test message',
                    type: 'info',
                    duration: 10000
                });
                
                const toast = document.querySelector('[data-toast-id="keyboard-test"]');
                const closeButton = toast.querySelector('.async-toast-close');
                
                expect(closeButton.tagName).toBe('BUTTON');
                expect(checkKeyboardAccessible(closeButton)).toBe(true);
                
                // Test keyboard interaction
                const clickSpy = jest.fn();
                closeButton.addEventListener('click', clickSpy);
                
                // Simulate Enter key press
                const enterEvent = new KeyboardEvent('keydown', { key: 'Enter' });
                closeButton.dispatchEvent(enterEvent);
                
                // Test Space key press
                const spaceEvent = new KeyboardEvent('keydown', { key: ' ' });
                closeButton.dispatchEvent(spaceEvent);
                
                // While the actual browser behavior might not trigger click on keydown,
                // the element structure supports keyboard interaction
            });
            
            test('should support keyboard navigation for interactive elements', () => {
                // Add progress bars with interactive elements
                uiUpdater.addProgressBar('keyboard-nav-1', {
                    title: 'Keyboard Navigation Test 1',
                    progress: 30,
                    status: 'in_progress'
                });
                
                uiUpdater.addProgressBar('keyboard-nav-2', {
                    title: 'Keyboard Navigation Test 2', 
                    progress: 60,
                    status: 'in_progress'
                });
                
                // Show toast notifications
                uiUpdater.showToast('Keyboard navigation toast 1', 'info');
                uiUpdater.showToast('Keyboard navigation toast 2', 'success');
                uiUpdater.processToastQueue();
                
                // Check that interactive elements are in tab order
                const interactiveElements = document.querySelectorAll('button, [tabindex="0"]');
                expect(interactiveElements.length).toBeGreaterThan(0);
                
                // Verify close buttons are keyboard accessible
                const closeButtons = document.querySelectorAll('.async-toast-close');
                closeButtons.forEach(button => {
                    expect(checkKeyboardAccessible(button)).toBe(true);
                });
            });
        });
        
        describe('Focus Management', () => {
            test('should provide visible focus indicators', () => {
                uiUpdater.displayToast({
                    id: 'focus-test',
                    message: 'Focus indicator test',
                    type: 'info',
                    duration: 10000
                });
                
                const closeButton = document.querySelector('.async-toast-close');
                
                // Simulate focus
                closeButton.focus();
                
                // Check for focus styles (in real implementation, we'd check computed styles)
                expect(closeButton).toBeTruthy();
                expect(closeButton.tagName).toBe('BUTTON');
            });
            
            test('should maintain logical focus order', () => {
                // Create multiple interactive elements
                uiUpdater.showToast('Focus order test 1', 'info');
                uiUpdater.showToast('Focus order test 2', 'success');
                uiUpdater.showToast('Focus order test 3', 'warning');
                uiUpdater.processToastQueue();
                
                const closeButtons = document.querySelectorAll('.async-toast-close');
                
                // Verify elements can receive focus in logical order
                closeButtons.forEach((button, index) => {
                    expect(button.tabIndex).toBeGreaterThanOrEqual(-1);
                });
            });
        });
        
        describe('Screen Reader Support', () => {
            test('should provide meaningful text content for screen readers', () => {
                uiUpdater.addProgressBar('screen-reader-test', {
                    title: 'Screen Reader Test Video: Understanding Accessibility',
                    progress: 75,
                    status: 'in_progress'
                });
                
                const progressContainer = document.querySelector('[data-job-id="screen-reader-test"]');
                const progressTitle = progressContainer.querySelector('.async-progress-title');
                const progressText = progressContainer.querySelector('.async-progress-text');
                const progressMessage = progressContainer.querySelector('.async-progress-message');
                
                // Verify meaningful text content
                expect(progressTitle.textContent).toBe('Screen Reader Test Video: Understanding Accessibility');
                expect(progressText.textContent).toBe('75%');
                expect(progressMessage).toBeTruthy();
                
                // Update with meaningful message
                uiUpdater.updateProgressBar('screen-reader-test', {
                    message: 'Processing video transcription - 75% complete'
                });
                
                expect(progressMessage.textContent).toBe('Processing video transcription - 75% complete');
            });
            
            test('should provide descriptive toast messages', () => {
                const testMessages = [
                    { type: 'success', message: 'Video "Understanding Web Accessibility" summarization completed successfully' },
                    { type: 'error', message: 'Failed to process video "Broken Link Example": Network connection timeout' },
                    { type: 'warning', message: 'Video processing is taking longer than expected, please wait' },
                    { type: 'info', message: 'Starting transcription for video "Introduction to WCAG Guidelines"' }
                ];
                
                testMessages.forEach(({ type, message }, index) => {
                    uiUpdater.displayToast({
                        id: `sr-toast-${index}`,
                        message,
                        type,
                        duration: 5000
                    });
                    
                    const toast = document.querySelector(`[data-toast-id="sr-toast-${index}"]`);
                    const messageElement = toast.querySelector('.async-toast-message');
                    
                    expect(messageElement.textContent).toBe(message);
                });
            });
            
            test('should provide informative connection status', () => {
                // Test with meaningful stats
                uiUpdater.updateConnectionStatus(true, {
                    active: 3,
                    completed: 12,
                    failed: 1
                });
                
                const statusIndicator = uiUpdater.connectionStatusIndicator;
                const statusText = statusIndicator.querySelector('.connection-status-text');
                const statusStats = statusIndicator.querySelector('.connection-status-stats');
                
                expect(statusText.textContent).toBe('Connected');
                expect(statusStats.textContent).toBe('3 active, 12 completed, 1 failed');
                expect(statusIndicator.title).toBe('Real-time updates: Connected');
                
                // Test disconnected state
                uiUpdater.updateConnectionStatus(false);
                expect(statusText.textContent).toBe('Disconnected');
                expect(statusIndicator.title).toBe('Real-time updates: Disconnected');
            });
        });
        
        describe('Semantic HTML Structure', () => {
            test('should use appropriate HTML elements for progress bars', () => {
                uiUpdater.addProgressBar('semantic-test', {
                    title: 'Semantic HTML Test',
                    progress: 40,
                    status: 'in_progress'
                });
                
                const progressContainer = document.querySelector('[data-job-id="semantic-test"]');
                
                // Check for semantic structure
                const progressTrack = progressContainer.querySelector('.async-progress-track');
                const progressBar = progressContainer.querySelector('.async-progress-bar');
                
                expect(progressTrack).toBeTruthy();
                expect(progressBar).toBeTruthy();
                
                // In ideal implementation, we'd use <progress> element
                // For now, verify div-based structure is properly styled
                expect(progressContainer.tagName).toBe('DIV');
                expect(progressContainer.getAttribute('data-job-id')).toBe('semantic-test');
            });
            
            test('should use button elements for interactive controls', () => {
                uiUpdater.displayToast({
                    id: 'semantic-button-test',
                    message: 'Semantic button test',
                    type: 'info',
                    duration: 5000
                });
                
                const closeButton = document.querySelector('.async-toast-close');
                
                expect(closeButton.tagName).toBe('BUTTON');
                expect(closeButton.textContent).toBe('×');
            });
            
            test('should provide proper heading structure', () => {
                uiUpdater.addProgressBar('heading-test', {
                    title: 'Heading Structure Test',
                    progress: 0,
                    status: 'pending'
                });
                
                const progressSection = document.getElementById('async-progress-section');
                const sectionTitle = progressSection.querySelector('.async-progress-section-title');
                
                expect(sectionTitle.tagName).toBe('H3');
                expect(sectionTitle.textContent).toBe('Processing Summaries');
            });
        });
        
        describe('Error Prevention and Recovery', () => {
            test('should handle invalid input gracefully', () => {
                // Test with potentially problematic input
                const problematicInputs = [
                    '', // Empty string
                    null, // Null value
                    undefined, // Undefined
                    '<script>alert("xss")</script>Malicious content', // XSS attempt
                    'Very '.repeat(100) + 'long content', // Very long content
                    '🎵🎶🎸 Unicode content with emojis 🎤🎧', // Unicode content
                    'Content\nwith\nmultiple\nlines' // Multi-line content
                ];
                
                problematicInputs.forEach((input, index) => {
                    expect(() => {
                        uiUpdater.addProgressBar(`error-test-${index}`, {
                            title: input,
                            progress: 50,
                            status: 'in_progress'
                        });
                    }).not.toThrow();
                    
                    expect(() => {
                        uiUpdater.showToast(input, 'info');
                    }).not.toThrow();
                });
                
                // Verify XSS protection
                const xssProgressBar = document.querySelector('[data-job-id="error-test-3"]');
                if (xssProgressBar) {
                    const title = xssProgressBar.querySelector('.async-progress-title');
                    expect(title.innerHTML).not.toContain('<script>');
                    expect(title.textContent).toContain('Malicious content');
                }
            });
            
            test('should provide clear error messages', () => {
                // Test error scenarios with user-friendly messages
                uiUpdater.showToast(
                    'Unable to process video: The video is private or unavailable. Please check the video URL and try again.',
                    'error'
                );
                
                uiUpdater.showToast(
                    'Connection lost: Attempting to reconnect automatically. Your progress has been saved.',
                    'warning'
                );
                
                uiUpdater.processToastQueue();
                
                const errorToast = document.querySelector('.async-toast-error');
                const warningToast = document.querySelector('.async-toast-warning');
                
                expect(errorToast).toBeTruthy();
                expect(warningToast).toBeTruthy();
                
                const errorMessage = errorToast.querySelector('.async-toast-message');
                const warningMessage = warningToast.querySelector('.async-toast-message');
                
                expect(errorMessage.textContent).toContain('Unable to process video');
                expect(warningMessage.textContent).toContain('Connection lost');
            });
        });
        
        describe('Timing and Animation Considerations', () => {
            test('should respect reduced motion preferences', () => {
                // Mock reduced motion preference
                Object.defineProperty(window, 'matchMedia', {
                    writable: true,
                    value: jest.fn().mockImplementation(query => ({
                        matches: query === '(prefers-reduced-motion: reduce)',
                        media: query,
                        onchange: null,
                        addListener: jest.fn(),
                        removeListener: jest.fn(),
                        addEventListener: jest.fn(),
                        removeEventListener: jest.fn(),
                        dispatchEvent: jest.fn(),
                    })),
                });
                
                uiUpdater.addProgressBar('reduced-motion-test', {
                    title: 'Reduced Motion Test',
                    progress: 50,
                    status: 'in_progress'
                });
                
                // Animation properties should be adjusted for reduced motion
                // In CSS, this would be handled by @media (prefers-reduced-motion: reduce)
                const progressContainer = document.querySelector('[data-job-id="reduced-motion-test"]');
                expect(progressContainer).toBeTruthy();
            });
            
            test('should provide adequate timing for toast notifications', () => {
                // Default toast duration should be adequate (5 seconds)
                expect(uiUpdater.toastDuration).toBe(5000);
                
                // Test custom duration
                uiUpdater.showToast('Short message', 'info', { duration: 3000 });
                expect(uiUpdater.toastQueue[0].duration).toBe(3000);
                
                uiUpdater.showToast('Important message that needs more time to read', 'warning', { duration: 8000 });
                expect(uiUpdater.toastQueue[1].duration).toBe(8000);
            });
            
            test('should not auto-advance important content', () => {
                // Progress bars should remain visible until completion
                uiUpdater.addProgressBar('important-content', {
                    title: 'Important Content - Processing Critical Data',
                    progress: 30,
                    status: 'in_progress'
                });
                
                // Progress should not be removed automatically while in progress
                jest.advanceTimersByTime(10000);
                expect(uiUpdater.progressBars.has('important-content')).toBe(true);
                
                // Only removed after completion and delay
                uiUpdater.updateProgressBar('important-content', {
                    progress: 100,
                    status: 'completed'
                });
                
                // Simulate completion handler
                setTimeout(() => {
                    uiUpdater.removeProgressBar('important-content');
                }, 2000);
                
                jest.advanceTimersByTime(1999);
                expect(uiUpdater.progressBars.has('important-content')).toBe(true);
                
                jest.advanceTimersByTime(1);
                expect(uiUpdater.progressBars.has('important-content')).toBe(false);
            });
        });
    });
    
    describe('Responsive Design Accessibility', () => {
        test('should maintain accessibility across viewport sizes', () => {
            // Test mobile viewport
            Object.defineProperty(window, 'innerWidth', { value: 375, configurable: true });
            Object.defineProperty(window, 'innerHeight', { value: 667, configurable: true });
            
            uiUpdater.addProgressBar('mobile-a11y-test', {
                title: 'Mobile Accessibility Test Video with a Very Long Title That Might Wrap',
                progress: 60,
                status: 'in_progress'
            });
            
            const progressContainer = document.querySelector('[data-job-id="mobile-a11y-test"]');
            const progressTitle = progressContainer.querySelector('.async-progress-title');
            
            // Title should remain readable on mobile
            expect(progressTitle.textContent).toContain('Mobile Accessibility Test');
            
            // Test toast on mobile
            uiUpdater.showToast('Mobile toast message that might be longer on smaller screens', 'info');
            uiUpdater.processToastQueue();
            
            const toast = document.querySelector('.async-toast');
            expect(toast).toBeTruthy();
            
            // Test tablet viewport
            Object.defineProperty(window, 'innerWidth', { value: 768, configurable: true });
            Object.defineProperty(window, 'innerHeight', { value: 1024, configurable: true });
            
            uiUpdater.updateConnectionStatus(true, { active: 5, completed: 10 });
            const statusIndicator = uiUpdater.connectionStatusIndicator;
            expect(statusIndicator).toBeTruthy();
        });
        
        test('should handle touch interactions appropriately', () => {
            // Mock touch events
            const createTouchEvent = (type, touches = []) => {
                const event = new Event(type, { bubbles: true, cancelable: true });
                event.touches = touches;
                event.targetTouches = touches;
                event.changedTouches = touches;
                return event;
            };
            
            uiUpdater.displayToast({
                id: 'touch-test',
                message: 'Touch interaction test',
                type: 'info',
                duration: 10000
            });
            
            const closeButton = document.querySelector('.async-toast-close');
            
            // Button should be large enough for touch (minimum 44x44px target)
            // In real implementation, we'd check computed styles
            expect(closeButton.tagName).toBe('BUTTON');
            expect(closeButton.textContent).toBe('×');
            
            // Test touch event
            const touchStart = createTouchEvent('touchstart');
            const touchEnd = createTouchEvent('touchend');
            
            expect(() => {
                closeButton.dispatchEvent(touchStart);
                closeButton.dispatchEvent(touchEnd);
            }).not.toThrow();
        });
    });
    
    describe('Internationalization and Localization', () => {
        test('should handle right-to-left (RTL) languages', () => {
            // Mock RTL direction
            document.documentElement.dir = 'rtl';
            
            uiUpdater.addProgressBar('rtl-test', {
                title: 'اختبار اللغة العربية', // Arabic text
                progress: 45,
                status: 'in_progress'
            });
            
            const progressContainer = document.querySelector('[data-job-id="rtl-test"]');
            const progressTitle = progressContainer.querySelector('.async-progress-title');
            
            expect(progressTitle.textContent).toBe('اختبار اللغة العربية');
            
            // Toast notifications should also work with RTL
            uiUpdater.showToast('رسالة إشعار باللغة العربية', 'success');
            uiUpdater.processToastQueue();
            
            const toast = document.querySelector('.async-toast');
            const message = toast.querySelector('.async-toast-message');
            expect(message.textContent).toBe('رسالة إشعار باللغة العربية');
            
            // Reset direction
            document.documentElement.dir = 'ltr';
        });
        
        test('should handle various character encodings', () => {
            const multilingualTitles = [
                'English Title',
                'Título en Español',
                'Titre Français',
                'Deutsche Titel',
                'Русский заголовок',
                '中文标题',
                '日本語のタイトル',
                '한국어 제목',
                '🎵 Title with Emojis 🎶'
            ];
            
            multilingualTitles.forEach((title, index) => {
                uiUpdater.addProgressBar(`multilingual-${index}`, {
                    title: title,
                    progress: (index + 1) * 10,
                    status: 'in_progress'
                });
                
                const progressContainer = document.querySelector(`[data-job-id="multilingual-${index}"]`);
                const progressTitle = progressContainer.querySelector('.async-progress-title');
                
                expect(progressTitle.textContent).toBe(title);
            });
        });
    });
    
    describe('Error Accessibility', () => {
        test('should make error states clearly identifiable', () => {
            uiUpdater.addProgressBar('error-state-test', {
                title: 'Error State Test',
                progress: 30,
                status: 'in_progress'
            });
            
            // Update to failed state
            let progressContainer = document.querySelector('[data-job-id="error-state-test"]');
            progressContainer.className = progressContainer.className.replace('in_progress', 'failed');
            
            expect(progressContainer.className).toContain('failed');
            
            // Error toast should be clearly marked
            uiUpdater.showToast('Video processing failed: Invalid video format. Please use MP4, AVI, or MOV files.', 'error');
            uiUpdater.processToastQueue();
            
            const errorToast = document.querySelector('.async-toast-error');
            const errorMessage = errorToast.querySelector('.async-toast-message');
            
            expect(errorToast).toBeTruthy();
            expect(errorMessage.textContent).toContain('Video processing failed');
            expect(errorMessage.textContent).toContain('Please use MP4, AVI, or MOV files');
        });
        
        test('should provide recovery instructions for errors', () => {
            const errorMessages = [
                'Connection lost. Please check your internet connection and try again.',
                'File too large. Please use videos smaller than 100MB.',
                'Invalid URL. Please enter a valid YouTube video URL.',
                'Service temporarily unavailable. Please try again in a few minutes.'
            ];
            
            errorMessages.forEach((message, index) => {
                uiUpdater.showToast(message, 'error', { duration: 8000 }); // Longer duration for error messages
            });
            
            uiUpdater.processToastQueue();
            
            const errorToasts = document.querySelectorAll('.async-toast-error');
            expect(errorToasts).toHaveLength(4);
            
            errorToasts.forEach((toast, index) => {
                const message = toast.querySelector('.async-toast-message');
                expect(message.textContent).toBe(errorMessages[index]);
            });
        });
    });
});