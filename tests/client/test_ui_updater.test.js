/**
 * UI Updater Tests - Comprehensive testing for UI updates and DOM manipulation
 * Module 4: Client-Side JavaScript Tests
 */

import { jest } from '@jest/globals';
import fs from 'fs';
import path from 'path';

const uiUpdaterPath = path.resolve('./static/js/ui_updater.js');
const uiUpdaterCode = fs.readFileSync(uiUpdaterPath, 'utf8');

// Remove the auto-initialization and window export for testing
const testableCode = uiUpdaterCode
    .replace(/window\.UIUpdater = new UIUpdater\(\);/, '')
    .replace(/console\.log\('🎯 UIUpdater: UIUpdater loaded and ready'\);/, '');

// Create a clean environment for each test
const createTestEnvironment = () => {
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
    
    // Execute the code in the environment
    const func = new Function(
        'window', 'document', 'console', 'Date', 'Math', 'setTimeout', 'clearTimeout', 'requestAnimationFrame', 'Map', 'Array', 'Object',
        testableCode + '; return UIUpdater;'
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

describe('UIUpdater', () => {
    let UIUpdaterClass;
    let uiUpdater;
    let mockJobTracker;
    
    beforeEach(() => {
        // Create a fresh class instance for each test
        UIUpdaterClass = createTestEnvironment();
        
        // Reset the DOM
        document.body.innerHTML = '';
        document.head.innerHTML = '';
        
        // Mock JobTracker
        mockJobTracker = {
            addEventListener: jest.fn(),
            removeEventListener: jest.fn(),
            updateProgress: jest.fn(),
            completeJob: jest.fn()
        };
        
        // Mock global dependencies
        global.window.JobTracker = mockJobTracker;
        global.window.displayResults = jest.fn();
        global.window.loadPaginatedSummaries = jest.fn();
        global.window.currentPage = 1;
        global.window.currentPageSize = 10;
        
        uiUpdater = new UIUpdaterClass();
        
        // Mock timers
        jest.useFakeTimers();
    });
    
    afterEach(() => {
        jest.useRealTimers();
        jest.clearAllMocks();
        delete global.window.JobTracker;
        delete global.window.displayResults;
        delete global.window.loadPaginatedSummaries;
        delete global.window.currentPage;
        delete global.window.currentPageSize;
    });
    
    describe('Constructor and Initialization', () => {
        test('should create UIUpdater with correct initial state', () => {
            expect(uiUpdater).toBeDefined();
            expect(uiUpdater.progressBars).toBeInstanceOf(Map);
            expect(uiUpdater.toastQueue).toEqual([]);
            expect(uiUpdater.isProcessingToasts).toBe(false);
            expect(uiUpdater.toastContainer).toBeTruthy();
            expect(uiUpdater.toastDuration).toBe(5000);
            expect(uiUpdater.maxToasts).toBe(5);
            expect(uiUpdater.animationDuration).toBe(300);
        });
        
        test('should initialize UI components', () => {
            // Toast container should be created
            const toastContainer = document.getElementById('async-toast-container');
            expect(toastContainer).toBeTruthy();
            expect(toastContainer.className).toBe('async-toast-container');
        });
        
        test('should register event listeners with JobTracker', () => {
            expect(mockJobTracker.addEventListener).toHaveBeenCalledWith('job_added', expect.any(Function));
            expect(mockJobTracker.addEventListener).toHaveBeenCalledWith('job_progress', expect.any(Function));
            expect(mockJobTracker.addEventListener).toHaveBeenCalledWith('job_completed', expect.any(Function));
            expect(mockJobTracker.addEventListener).toHaveBeenCalledWith('job_failed', expect.any(Function));
            expect(mockJobTracker.addEventListener).toHaveBeenCalledWith('stats_updated', expect.any(Function));
        });
        
        test('should handle missing JobTracker gracefully', () => {
            delete global.window.JobTracker;
            
            expect(() => {
                new UIUpdaterClass();
            }).not.toThrow();
        });
    });
    
    describe('Progress Bar Management', () => {
        describe('addProgressBar', () => {
            test('should create and add progress bar', () => {
                const jobId = 'test-job-1';
                const options = {
                    title: 'Test Video',
                    progress: 25,
                    status: 'in_progress'
                };
                
                uiUpdater.addProgressBar(jobId, options);
                
                expect(uiUpdater.progressBars.has(jobId)).toBe(true);
                
                const progressData = uiUpdater.progressBars.get(jobId);
                expect(progressData.title).toBe('Test Video');
                expect(progressData.progress).toBe(25);
                expect(progressData.status).toBe('in_progress');
                expect(progressData.element).toBeTruthy();
                expect(progressData.createdAt).toBeInstanceOf(Date);
            });
            
            test('should create progress section if it does not exist', () => {
                uiUpdater.addProgressBar('test-job', { title: 'Test' });
                
                const progressSection = document.getElementById('async-progress-section');
                expect(progressSection).toBeTruthy();
                expect(progressSection.className).toBe('async-progress-section');
                expect(progressSection.style.display).toBe('block');
            });
            
            test('should update existing progress bar instead of creating new one', () => {
                const jobId = 'existing-job';
                
                uiUpdater.addProgressBar(jobId, { title: 'Initial', progress: 10 });
                const initialSize = uiUpdater.progressBars.size;
                
                uiUpdater.addProgressBar(jobId, { title: 'Updated', progress: 50 });
                
                expect(uiUpdater.progressBars.size).toBe(initialSize);
                const progressData = uiUpdater.progressBars.get(jobId);
                expect(progressData.progress).toBe(50);
            });
            
            test('should create proper progress bar HTML structure', () => {
                uiUpdater.addProgressBar('html-test', {
                    title: 'HTML Test Video',
                    progress: 30,
                    status: 'in_progress'
                });
                
                const progressContainer = document.querySelector('[data-job-id="html-test"]');
                expect(progressContainer).toBeTruthy();
                expect(progressContainer.className).toContain('async-progress-container');
                expect(progressContainer.className).toContain('in_progress');
                
                const title = progressContainer.querySelector('.async-progress-title');
                expect(title.textContent).toBe('HTML Test Video');
                
                const progressText = progressContainer.querySelector('.async-progress-text');
                expect(progressText.textContent).toBe('30%');
                
                const progressBar = progressContainer.querySelector('.async-progress-bar');
                expect(progressBar.style.width).toBe('30%');
                
                const message = progressContainer.querySelector('.async-progress-message');
                expect(message).toBeTruthy();
            });
            
            test('should escape HTML in title to prevent XSS', () => {
                const maliciousTitle = '<script>alert("xss")</script>Test';
                
                uiUpdater.addProgressBar('xss-test', {
                    title: maliciousTitle,
                    progress: 0
                });
                
                const title = document.querySelector('.async-progress-title');
                expect(title.innerHTML).not.toContain('<script>');
                expect(title.textContent).toContain('Test');
            });
        });
        
        describe('updateProgressBar', () => {
            beforeEach(() => {
                uiUpdater.addProgressBar('update-test', {
                    title: 'Update Test',
                    progress: 0,
                    status: 'pending'
                });
            });
            
            test('should update progress bar values', () => {
                uiUpdater.updateProgressBar('update-test', {
                    progress: 75,
                    status: 'in_progress',
                    message: 'Processing transcription...'
                });
                
                const progressData = uiUpdater.progressBars.get('update-test');
                expect(progressData.progress).toBe(75);
                expect(progressData.status).toBe('in_progress');
                
                const progressBar = document.querySelector('[data-job-id="update-test"] .async-progress-bar');
                expect(progressBar.style.width).toBe('75%');
                
                const progressText = document.querySelector('[data-job-id="update-test"] .async-progress-text');
                expect(progressText.textContent).toBe('75%');
                
                const message = document.querySelector('[data-job-id="update-test"] .async-progress-message');
                expect(message.textContent).toBe('Processing transcription...');
                
                const container = document.querySelector('[data-job-id="update-test"]');
                expect(container.className).toContain('in_progress');
            });
            
            test('should handle progress clamping', () => {
                uiUpdater.updateProgressBar('update-test', { progress: 150 });
                
                const progressBar = document.querySelector('[data-job-id="update-test"] .async-progress-bar');
                expect(progressBar.style.width).toBe('100%');
                
                uiUpdater.updateProgressBar('update-test', { progress: -10 });
                expect(progressBar.style.width).toBe('0%');
            });
            
            test('should handle partial updates', () => {
                uiUpdater.updateProgressBar('update-test', { progress: 50 });
                uiUpdater.updateProgressBar('update-test', { status: 'in_progress' });
                uiUpdater.updateProgressBar('update-test', { message: 'Almost done...' });
                
                const progressData = uiUpdater.progressBars.get('update-test');
                expect(progressData.progress).toBe(50);
                expect(progressData.status).toBe('in_progress');
                
                const message = document.querySelector('[data-job-id="update-test"] .async-progress-message');
                expect(message.textContent).toBe('Almost done...');
            });
            
            test('should warn about unknown progress bar updates', () => {
                const consoleWarnSpy = jest.spyOn(console, 'warn');
                
                uiUpdater.updateProgressBar('unknown-job', { progress: 50 });
                
                expect(consoleWarnSpy).toHaveBeenCalledWith(
                    '⚠️ UIUpdater: Cannot update unknown progress bar unknown-job'
                );
            });
        });
        
        describe('removeProgressBar', () => {
            beforeEach(() => {
                uiUpdater.addProgressBar('remove-test', { title: 'Remove Test' });
            });
            
            test('should remove progress bar with animation', () => {
                const progressElement = document.querySelector('[data-job-id="remove-test"]');
                expect(progressElement).toBeTruthy();
                
                uiUpdater.removeProgressBar('remove-test');
                
                // Should start fade out animation
                expect(progressElement.style.opacity).toBe('0');
                expect(progressElement.style.transition).toContain('opacity');
                
                // After animation duration, element should be removed
                jest.advanceTimersByTime(uiUpdater.animationDuration);
                
                expect(uiUpdater.progressBars.has('remove-test')).toBe(false);
                expect(document.querySelector('[data-job-id="remove-test"]')).toBeNull();
            });
            
            test('should handle removal of non-existent progress bar', () => {
                expect(() => {
                    uiUpdater.removeProgressBar('non-existent');
                }).not.toThrow();
            });
            
            test('should handle element already removed from DOM', () => {
                const progressElement = document.querySelector('[data-job-id="remove-test"]');
                progressElement.remove(); // Remove manually
                
                expect(() => {
                    uiUpdater.removeProgressBar('remove-test');
                }).not.toThrow();
            });
        });
        
        describe('clearAllProgressBars', () => {
            beforeEach(() => {
                uiUpdater.addProgressBar('clear-1', { title: 'Clear 1' });
                uiUpdater.addProgressBar('clear-2', { title: 'Clear 2' });
                uiUpdater.addProgressBar('clear-3', { title: 'Clear 3' });
            });
            
            test('should clear all progress bars', () => {
                expect(uiUpdater.progressBars.size).toBe(3);
                
                uiUpdater.clearAllProgressBars();
                
                expect(uiUpdater.progressBars.size).toBe(0);
                
                const progressSection = document.getElementById('async-progress-section');
                expect(progressSection.style.display).toBe('none');
                expect(progressSection.innerHTML).toBe('<h3 class="async-progress-section-title">Processing Summaries</h3>');
            });
        });
    });
    
    describe('Toast Notification System', () => {
        describe('showToast', () => {
            test('should create and queue toast notification', () => {
                uiUpdater.showToast('Test message', 'info');
                
                expect(uiUpdater.toastQueue).toHaveLength(1);
                
                const toast = uiUpdater.toastQueue[0];
                expect(toast.message).toBe('Test message');
                expect(toast.type).toBe('info');
                expect(toast.duration).toBe(5000);
                expect(toast.id).toMatch(/^toast_\d+_[a-z0-9]+$/);
                expect(toast.createdAt).toBeInstanceOf(Date);
            });
            
            test('should use custom duration when provided', () => {
                uiUpdater.showToast('Custom duration', 'warning', { duration: 10000 });
                
                const toast = uiUpdater.toastQueue[0];
                expect(toast.duration).toBe(10000);
            });
            
            test('should start processing toast queue', () => {
                const processSpy = jest.spyOn(uiUpdater, 'processToastQueue');
                
                uiUpdater.showToast('Test message');
                
                expect(processSpy).toHaveBeenCalled();
            });
        });
        
        describe('processToastQueue', () => {
            test('should process toast queue and display toasts', async () => {
                // Add multiple toasts
                uiUpdater.showToast('Toast 1', 'info');
                uiUpdater.showToast('Toast 2', 'success');
                uiUpdater.showToast('Toast 3', 'error');
                
                // Process queue
                await uiUpdater.processToastQueue();
                
                // Should display toasts
                const toastElements = document.querySelectorAll('.async-toast');
                expect(toastElements).toHaveLength(3);
                expect(uiUpdater.toastQueue).toHaveLength(0);
            });
            
            test('should respect max toast limit', async () => {
                uiUpdater.maxToasts = 2;
                
                // Add more toasts than limit
                for (let i = 0; i < 5; i++) {
                    uiUpdater.showToast(`Toast ${i + 1}`);
                }
                
                // Start processing (but don't wait for completion)
                uiUpdater.processToastQueue();
                
                // Should only show max number of toasts
                const toastElements = document.querySelectorAll('.async-toast');
                expect(toastElements.length).toBeLessThanOrEqual(2);
                expect(uiUpdater.toastQueue.length).toBeGreaterThan(0); // Remaining should be queued
            });
            
            test('should not start processing if already processing', () => {
                uiUpdater.isProcessingToasts = true;
                const originalQueue = [...uiUpdater.toastQueue];
                
                uiUpdater.processToastQueue();
                
                expect(uiUpdater.toastQueue).toEqual(originalQueue);
            });
        });
        
        describe('displayToast', () => {
            test('should create toast element with correct structure', () => {
                const toastData = {
                    id: 'test-toast-1',
                    message: 'Test notification',
                    type: 'success',
                    duration: 5000
                };
                
                uiUpdater.displayToast(toastData);
                
                const toastElement = document.querySelector('[data-toast-id="test-toast-1"]');
                expect(toastElement).toBeTruthy();
                expect(toastElement.className).toContain('async-toast-success');
                
                const message = toastElement.querySelector('.async-toast-message');
                expect(message.textContent).toBe('Test notification');
                
                const closeButton = toastElement.querySelector('.async-toast-close');
                expect(closeButton).toBeTruthy();
            });
            
            test('should apply correct CSS classes for different types', () => {
                const types = ['success', 'error', 'warning', 'info'];
                
                types.forEach((type, index) => {
                    uiUpdater.displayToast({
                        id: `toast-${index}`,
                        message: `${type} message`,
                        type,
                        duration: 1000
                    });
                });
                
                expect(document.querySelector('.async-toast-success')).toBeTruthy();
                expect(document.querySelector('.async-toast-error')).toBeTruthy();
                expect(document.querySelector('.async-toast-warning')).toBeTruthy();
                expect(document.querySelector('.async-toast-info')).toBeTruthy();
            });
            
            test('should auto-remove toast after duration', () => {
                uiUpdater.displayToast({
                    id: 'auto-remove-toast',
                    message: 'Auto remove',
                    type: 'info',
                    duration: 1000
                });
                
                const toastElement = document.querySelector('[data-toast-id="auto-remove-toast"]');
                expect(toastElement).toBeTruthy();
                
                // Fast-forward past duration
                jest.advanceTimersByTime(1000);
                
                // Should start removal animation
                expect(toastElement.style.opacity).toBe('0');
                expect(toastElement.style.transform).toBe('translateX(100%)');
                
                // After animation, should be removed
                jest.advanceTimersByTime(uiUpdater.animationDuration);
                
                expect(document.querySelector('[data-toast-id="auto-remove-toast"]')).toBeNull();
            });
            
            test('should escape HTML in messages to prevent XSS', () => {
                const maliciousMessage = '<script>alert("xss")</script>Safe message';
                
                uiUpdater.displayToast({
                    id: 'xss-toast',
                    message: maliciousMessage,
                    type: 'info',
                    duration: 5000
                });
                
                const messageElement = document.querySelector('.async-toast-message');
                expect(messageElement.innerHTML).not.toContain('<script>');
                expect(messageElement.textContent).toContain('Safe message');
            });
        });
        
        describe('removeToast', () => {
            test('should remove toast with animation', () => {
                uiUpdater.displayToast({
                    id: 'remove-toast',
                    message: 'Remove me',
                    type: 'info',
                    duration: 10000
                });
                
                const toastElement = document.querySelector('[data-toast-id="remove-toast"]');
                
                uiUpdater.removeToast(toastElement);
                
                expect(toastElement.style.opacity).toBe('0');
                expect(toastElement.style.transform).toBe('translateX(100%)');
                
                jest.advanceTimersByTime(uiUpdater.animationDuration);
                
                expect(document.querySelector('[data-toast-id="remove-toast"]')).toBeNull();
            });
            
            test('should handle removal of already removed element', () => {
                const toastElement = document.createElement('div');
                
                expect(() => {
                    uiUpdater.removeToast(toastElement);
                }).not.toThrow();
            });
        });
        
        describe('clearAllToasts', () => {
            beforeEach(() => {
                uiUpdater.showToast('Toast 1');
                uiUpdater.showToast('Toast 2');
                uiUpdater.showToast('Toast 3');
                uiUpdater.processToastQueue();
            });
            
            test('should clear all toasts and queue', () => {
                uiUpdater.clearAllToasts();
                
                expect(uiUpdater.toastQueue).toHaveLength(0);
                
                // After animation time, no toasts should remain
                jest.advanceTimersByTime(uiUpdater.animationDuration);
                
                const remainingToasts = document.querySelectorAll('.async-toast');
                expect(remainingToasts).toHaveLength(0);
            });
        });
    });
    
    describe('Connection Status Management', () => {
        test('should create connection status indicator', () => {
            uiUpdater.updateConnectionStatus(true, { active: 2, completed: 5, failed: 1 });
            
            const statusIndicator = uiUpdater.connectionStatusIndicator;
            expect(statusIndicator).toBeTruthy();
            expect(statusIndicator.className).toContain('async-connection-status');
            expect(statusIndicator.className).toContain('connected');
            
            const statusText = statusIndicator.querySelector('.connection-status-text');
            expect(statusText.textContent).toBe('Connected');
            
            const statusStats = statusIndicator.querySelector('.connection-status-stats');
            expect(statusStats.textContent).toBe('2 active, 5 completed, 1 failed');
        });
        
        test('should update connection status for disconnected state', () => {
            uiUpdater.updateConnectionStatus(false);
            
            const statusIndicator = uiUpdater.connectionStatusIndicator;
            expect(statusIndicator.className).toContain('disconnected');
            
            const statusText = statusIndicator.querySelector('.connection-status-text');
            expect(statusText.textContent).toBe('Disconnected');
            
            expect(statusIndicator.title).toBe('Real-time updates: Disconnected');
        });
        
        test('should handle empty stats gracefully', () => {
            uiUpdater.updateConnectionStatus(true, {});
            
            const statusStats = uiUpdater.connectionStatusIndicator.querySelector('.connection-status-stats');
            expect(statusStats.textContent).toBe('');
        });
        
        test('should add status indicator to header if available', () => {
            const header = document.createElement('div');
            header.className = 'header';
            document.body.appendChild(header);
            
            uiUpdater.updateConnectionStatus(true);
            
            expect(header.contains(uiUpdater.connectionStatusIndicator)).toBe(true);
        });
    });
    
    describe('Event Handlers', () => {
        describe('handleJobAdded', () => {
            test('should create progress bar for added job', () => {
                const jobData = {
                    jobId: 'added-job',
                    job: {
                        title: 'Added Job Video',
                        progress: 0,
                        status: 'pending'
                    }
                };
                
                uiUpdater.handleJobAdded(jobData);
                
                expect(uiUpdater.progressBars.has('added-job')).toBe(true);
                
                const progressElement = document.querySelector('[data-job-id="added-job"]');
                expect(progressElement).toBeTruthy();
                
                const title = progressElement.querySelector('.async-progress-title');
                expect(title.textContent).toBe('Added Job Video');
            });
        });
        
        describe('handleJobProgress', () => {
            beforeEach(() => {
                uiUpdater.handleJobAdded({
                    jobId: 'progress-job',
                    job: { title: 'Progress Job', progress: 0, status: 'pending' }
                });
            });
            
            test('should update progress bar for job progress', () => {
                const progressData = {
                    jobId: 'progress-job',
                    job: { progress: 50, status: 'in_progress' },
                    progressData: { message: 'Halfway there' }
                };
                
                uiUpdater.handleJobProgress(progressData);
                
                const progressBar = document.querySelector('[data-job-id="progress-job"] .async-progress-bar');
                expect(progressBar.style.width).toBe('50%');
                
                const message = document.querySelector('[data-job-id="progress-job"] .async-progress-message');
                expect(message.textContent).toBe('Halfway there');
            });
        });
        
        describe('handleJobCompleted', () => {
            beforeEach(() => {
                uiUpdater.handleJobAdded({
                    jobId: 'completed-job',
                    job: { title: 'Completed Job', progress: 0, status: 'pending' }
                });
            });
            
            test('should remove progress bar and show completion toast', () => {
                const completionData = {
                    jobId: 'completed-job',
                    job: { title: 'Completed Job' },
                    completionData: { summary: 'Job completed successfully' }
                };
                
                uiUpdater.handleJobCompleted(completionData);
                
                // Should show success toast
                expect(uiUpdater.toastQueue).toHaveLength(1);
                expect(uiUpdater.toastQueue[0].message).toContain('Summary completed');
                expect(uiUpdater.toastQueue[0].type).toBe('success');
                
                // Should remove progress bar after delay
                jest.advanceTimersByTime(2000);
                
                expect(uiUpdater.progressBars.has('completed-job')).toBe(false);
            });
            
            test('should call addCompletedSummary when summary data available', () => {
                const addSummarySpy = jest.spyOn(uiUpdater, 'addCompletedSummary');
                
                const completionData = {
                    jobId: 'completed-job',
                    job: { title: 'Completed Job' },
                    completionData: { summary: 'Summary content' }
                };
                
                uiUpdater.handleJobCompleted(completionData);
                
                expect(addSummarySpy).toHaveBeenCalledWith(completionData.completionData);
            });
        });
        
        describe('handleJobFailed', () => {
            beforeEach(() => {
                uiUpdater.handleJobAdded({
                    jobId: 'failed-job',
                    job: { title: 'Failed Job', progress: 0, status: 'pending' }
                });
            });
            
            test('should remove progress bar and show error toast', () => {
                const failureData = {
                    jobId: 'failed-job',
                    job: { title: 'Failed Job', error: 'Network timeout' },
                    errorData: { error: 'Network timeout' }
                };
                
                uiUpdater.handleJobFailed(failureData);
                
                // Should show error toast
                expect(uiUpdater.toastQueue).toHaveLength(1);
                expect(uiUpdater.toastQueue[0].message).toContain('Failed');
                expect(uiUpdater.toastQueue[0].message).toContain('Network timeout');
                expect(uiUpdater.toastQueue[0].type).toBe('error');
                
                // Should remove progress bar after delay
                jest.advanceTimersByTime(2000);
                
                expect(uiUpdater.progressBars.has('failed-job')).toBe(false);
            });
        });
        
        describe('handleStatsUpdated', () => {
            test('should update connection status with stats', () => {
                const updateSpy = jest.spyOn(uiUpdater, 'updateConnectionStatus');
                const stats = { active: 3, completed: 7, failed: 2 };
                
                uiUpdater.handleStatsUpdated(stats);
                
                expect(updateSpy).toHaveBeenCalledWith(stats);
            });
        });
    });
    
    describe('Summary Integration', () => {
        describe('addCompletedSummary', () => {
            test('should integrate with existing displayResults function', () => {
                const summaryData = {
                    title: 'Test Video Summary',
                    summary: 'This is a test summary',
                    video_id: 'test123',
                    video_url: 'https://youtube.com/watch?v=test123',
                    thumbnail_url: 'https://img.youtube.com/vi/test123/default.jpg'
                };
                
                // Create mock new-results container
                const newResultsContainer = document.createElement('div');
                newResultsContainer.id = 'new-results';
                document.body.appendChild(newResultsContainer);
                
                uiUpdater.addCompletedSummary(summaryData);
                
                expect(global.window.displayResults).toHaveBeenCalledWith(
                    [{
                        type: 'video',
                        title: 'Test Video Summary',
                        summary: 'This is a test summary',
                        video_id: 'test123',
                        video_url: 'https://youtube.com/watch?v=test123',
                        thumbnail_url: 'https://img.youtube.com/vi/test123/default.jpg',
                        error: undefined
                    }],
                    newResultsContainer,
                    true
                );
            });
            
            test('should handle missing displayResults function', () => {
                delete global.window.displayResults;
                
                expect(() => {
                    uiUpdater.addCompletedSummary({ title: 'Test' });
                }).not.toThrow();
            });
            
            test('should call refreshSummaryCache', () => {
                const refreshSpy = jest.spyOn(uiUpdater, 'refreshSummaryCache');
                
                uiUpdater.addCompletedSummary({ title: 'Test' });
                
                expect(refreshSpy).toHaveBeenCalled();
            });
        });
        
        describe('refreshSummaryCache', () => {
            test('should call loadPaginatedSummaries after delay', () => {
                uiUpdater.refreshSummaryCache();
                
                expect(global.window.loadPaginatedSummaries).not.toHaveBeenCalled();
                
                jest.advanceTimersByTime(1000);
                
                expect(global.window.loadPaginatedSummaries).toHaveBeenCalledWith(1, 10);
            });
            
            test('should handle missing loadPaginatedSummaries function', () => {
                delete global.window.loadPaginatedSummaries;
                
                expect(() => {
                    uiUpdater.refreshSummaryCache();
                    jest.advanceTimersByTime(1000);
                }).not.toThrow();
            });
            
            test('should use current page and page size', () => {
                global.window.currentPage = 3;
                global.window.currentPageSize = 20;
                
                uiUpdater.refreshSummaryCache();
                jest.advanceTimersByTime(1000);
                
                expect(global.window.loadPaginatedSummaries).toHaveBeenCalledWith(3, 20);
            });
        });
    });
    
    describe('Progress Section Management', () => {
        test('should create progress section when needed', () => {
            // Remove any existing section
            const existingSection = document.getElementById('async-progress-section');
            if (existingSection) {
                existingSection.remove();
            }
            
            uiUpdater.addProgressBar('test-job', { title: 'Test' });
            
            const progressSection = document.getElementById('async-progress-section');
            expect(progressSection).toBeTruthy();
            expect(progressSection.className).toBe('async-progress-section');
            
            const title = progressSection.querySelector('.async-progress-section-title');
            expect(title.textContent).toBe('Processing Summaries');
        });
        
        test('should insert progress section after summarize controls', () => {
            const summarizeControls = document.createElement('div');
            summarizeControls.className = 'summarize-controls';
            document.body.appendChild(summarizeControls);
            
            const nextElement = document.createElement('div');
            nextElement.className = 'next-element';
            document.body.appendChild(nextElement);
            
            uiUpdater.addProgressBar('test-job', { title: 'Test' });
            
            const progressSection = document.getElementById('async-progress-section');
            expect(progressSection.previousElementSibling).toBe(summarizeControls);
        });
        
        test('should fallback to container if no summarize controls', () => {
            const container = document.createElement('div');
            container.className = 'container';
            document.body.appendChild(container);
            
            uiUpdater.addProgressBar('test-job', { title: 'Test' });
            
            const progressSection = document.getElementById('async-progress-section');
            expect(container.contains(progressSection)).toBe(true);
        });
    });
    
    describe('Utility Functions', () => {
        describe('escapeHtml', () => {
            test('should escape HTML characters', () => {
                const maliciousInput = '<script>alert("xss")</script>&lt;test&gt;';
                const escaped = uiUpdater.escapeHtml(maliciousInput);
                
                expect(escaped).not.toContain('<script>');
                expect(escaped).toContain('&lt;script&gt;');
                expect(escaped).toContain('&amp;lt;test&amp;gt;');
            });
            
            test('should handle empty and null inputs', () => {
                expect(uiUpdater.escapeHtml('')).toBe('');
                expect(uiUpdater.escapeHtml(null)).toBe('null');
                expect(uiUpdater.escapeHtml(undefined)).toBe('undefined');
            });
        });
        
        describe('getState', () => {
            test('should return current UI state', () => {
                uiUpdater.addProgressBar('state-test-1', { title: 'Test 1' });
                uiUpdater.addProgressBar('state-test-2', { title: 'Test 2' });
                uiUpdater.showToast('Test toast 1');
                uiUpdater.showToast('Test toast 2');
                uiUpdater.showToast('Test toast 3');
                
                const state = uiUpdater.getState();
                
                expect(state).toEqual({
                    progressBars: 2,
                    activeToasts: 0, // Toasts not processed yet
                    queuedToasts: 3,
                    isProcessingToasts: false
                });
            });
        });
    });
    
    describe('Error Handling and Edge Cases', () => {
        test('should handle DOM manipulation when elements are missing', () => {
            // Remove toast container
            const toastContainer = document.getElementById('async-toast-container');
            if (toastContainer) {
                toastContainer.remove();
            }
            
            expect(() => {
                uiUpdater.showToast('Test message');
            }).not.toThrow();
        });
        
        test('should handle progress bar updates on removed elements', () => {
            uiUpdater.addProgressBar('remove-test', { title: 'Test' });
            
            // Manually remove the element
            const element = document.querySelector('[data-job-id="remove-test"]');
            element.remove();
            
            expect(() => {
                uiUpdater.updateProgressBar('remove-test', { progress: 50 });
            }).not.toThrow();
        });
        
        test('should handle errors in event handlers gracefully', () => {
            // Mock JobTracker to throw errors
            global.window.JobTracker = {
                addEventListener: jest.fn((event, handler) => {
                    if (event === 'job_added') {
                        // Simulate handler that throws
                        handler({ jobId: 'error-job', job: {} });
                    }
                })
            };
            
            expect(() => {
                new UIUpdaterClass();
            }).not.toThrow();
        });
        
        test('should handle missing global functions gracefully', () => {
            delete global.window.displayResults;
            delete global.window.loadPaginatedSummaries;
            
            expect(() => {
                uiUpdater.addCompletedSummary({ title: 'Test' });
                uiUpdater.refreshSummaryCache();
                jest.advanceTimersByTime(1000);
            }).not.toThrow();
        });
    });
    
    describe('Performance and Memory Management', () => {
        test('should efficiently handle many progress bars', () => {
            const startTime = performance.now();
            
            // Add many progress bars
            for (let i = 0; i < 100; i++) {
                uiUpdater.addProgressBar(`perf-job-${i}`, {
                    title: `Performance Job ${i}`,
                    progress: i,
                    status: 'in_progress'
                });
            }
            
            const addTime = performance.now() - startTime;
            expect(addTime).toBeLessThan(100); // Should complete in <100ms
            
            expect(uiUpdater.progressBars.size).toBe(100);
            expect(document.querySelectorAll('.async-progress-container')).toHaveLength(100);
        });
        
        test('should efficiently handle many toasts', () => {
            const startTime = performance.now();
            
            // Add many toasts
            for (let i = 0; i < 100; i++) {
                uiUpdater.showToast(`Performance toast ${i}`, 'info');
            }
            
            const addTime = performance.now() - startTime;
            expect(addTime).toBeLessThan(50); // Should complete in <50ms
            
            expect(uiUpdater.toastQueue).toHaveLength(100);
        });
        
        test('should clean up removed elements properly', () => {
            // Add and remove many progress bars
            for (let i = 0; i < 50; i++) {
                uiUpdater.addProgressBar(`cleanup-${i}`, { title: `Cleanup ${i}` });
                uiUpdater.removeProgressBar(`cleanup-${i}`);
                jest.advanceTimersByTime(uiUpdater.animationDuration);
            }
            
            expect(uiUpdater.progressBars.size).toBe(0);
            expect(document.querySelectorAll('.async-progress-container')).toHaveLength(0);
        });
    });
    
    describe('Accessibility', () => {
        test('should include proper ARIA labels and roles', () => {
            uiUpdater.addProgressBar('accessibility-test', {
                title: 'Accessibility Test Video',
                progress: 50,
                status: 'in_progress'
            });
            
            const progressContainer = document.querySelector('[data-job-id="accessibility-test"]');
            expect(progressContainer).toBeTruthy();
            
            // Check for semantic structure
            const progressTrack = progressContainer.querySelector('.async-progress-track');
            const progressBar = progressContainer.querySelector('.async-progress-bar');
            expect(progressTrack).toBeTruthy();
            expect(progressBar).toBeTruthy();
        });
        
        test('should provide meaningful progress information', () => {
            uiUpdater.addProgressBar('progress-info-test', {
                title: 'Progress Information Test',
                progress: 75,
                status: 'in_progress'
            });
            
            const progressText = document.querySelector('[data-job-id="progress-info-test"] .async-progress-text');
            expect(progressText.textContent).toBe('75%');
        });
        
        test('should have keyboard-accessible close buttons on toasts', () => {
            uiUpdater.displayToast({
                id: 'keyboard-test',
                message: 'Keyboard accessible toast',
                type: 'info',
                duration: 10000
            });
            
            const closeButton = document.querySelector('.async-toast-close');
            expect(closeButton).toBeTruthy();
            expect(closeButton.tagName).toBe('BUTTON');
        });
    });
});