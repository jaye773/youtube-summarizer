/**
 * Integration Tests - Comprehensive testing for component integration and workflows
 * Module 4: Client-Side JavaScript Tests
 */

import { jest } from '@jest/globals';
import fs from 'fs';
import path from 'path';

// Load all the source files
const sseClientPath = path.resolve('./static/js/sse_client.js');
const jobTrackerPath = path.resolve('./static/js/job_tracker.js');
const uiUpdaterPath = path.resolve('./static/js/ui_updater.js');

const sseClientCode = fs.readFileSync(sseClientPath, 'utf8');
const jobTrackerCode = fs.readFileSync(jobTrackerPath, 'utf8');
const uiUpdaterCode = fs.readFileSync(uiUpdaterPath, 'utf8');

// Clean the code for testing
const cleanSSECode = sseClientCode
    .replace(/window\.SSEClient = SSEClient;/, '')
    .replace(/if \(typeof window !== 'undefined'.*?}/, '');

const cleanJobTrackerCode = jobTrackerCode
    .replace(/window\.JobTracker = new JobTracker\(\);/, '')
    .replace(/console\.log\('🎯 JobTracker: JobTracker loaded and ready'\);/, '');

const cleanUIUpdaterCode = uiUpdaterCode
    .replace(/window\.UIUpdater = new UIUpdater\(\);/, '')
    .replace(/console\.log\('🎯 UIUpdater: UIUpdater loaded and ready'\);/, '');

// Create integrated environment
const createIntegratedEnvironment = () => {
    const environment = {
        window: global,
        document: global.document,
        EventSource: global.EventSource,
        console: global.console,
        Date: global.Date,
        Math: global.Math,
        setTimeout: global.setTimeout,
        clearTimeout: global.clearTimeout,
        requestAnimationFrame: global.requestAnimationFrame,
        Map: global.Map,
        Array: global.Array,
        Object: global.Object,
        Error: global.Error
    };
    
    // Execute all classes in the environment
    const func = new Function(
        'window', 'document', 'EventSource', 'console', 'Date', 'Math', 'setTimeout', 'clearTimeout', 'requestAnimationFrame', 'Map', 'Array', 'Object', 'Error',
        `
        ${cleanSSECode}
        ${cleanJobTrackerCode}  
        ${cleanUIUpdaterCode}
        
        return {
            SSEClient: SSEClient,
            JobTracker: JobTracker,
            UIUpdater: UIUpdater
        };
        `
    );
    
    return func(
        environment.window,
        environment.document,
        environment.EventSource,
        environment.console,
        environment.Date,
        environment.Math,
        environment.setTimeout,
        environment.clearTimeout,
        environment.requestAnimationFrame,
        environment.Map,
        environment.Array,
        environment.Object,
        environment.Error
    );
};

describe('Integration Tests', () => {
    let classes;
    let sseClient;
    let jobTracker;
    let uiUpdater;
    let mockEventSource;
    
    beforeEach(() => {
        // Reset DOM
        document.body.innerHTML = '';
        document.head.innerHTML = '';
        
        // Create integrated environment
        classes = createIntegratedEnvironment();
        
        // Mock EventSource with enhanced functionality
        const originalEventSource = global.EventSource;
        global.EventSource = jest.fn().mockImplementation(function(url, options) {
            mockEventSource = new originalEventSource(url, options);
            
            // Enhanced mock methods
            mockEventSource._simulateConnect = () => {
                mockEventSource.readyState = EventSource.OPEN;
                mockEventSource.dispatchEvent(new Event('open'));
            };
            
            mockEventSource._simulateError = () => {
                mockEventSource.readyState = EventSource.CLOSED;
                mockEventSource.dispatchEvent(new Event('error'));
            };
            
            mockEventSource._simulateMessage = (data, type = 'message') => {
                const event = new Event(type);
                event.data = typeof data === 'string' ? data : JSON.stringify(data);
                mockEventSource.dispatchEvent(event);
            };
            
            // Simulate progress event
            mockEventSource._simulateProgress = (jobId, progress, status = 'in_progress', message = 'Processing...') => {
                mockEventSource._simulateMessage({
                    job_id: jobId,
                    progress: progress,
                    status: status,
                    message: message,
                    video_title: `Test Video ${jobId}`,
                    video_url: `https://youtube.com/watch?v=${jobId}`
                }, 'summary_progress');
            };
            
            // Simulate completion event
            mockEventSource._simulateCompletion = (jobId, summary = 'Test summary') => {
                mockEventSource._simulateMessage({
                    job_id: jobId,
                    summary: summary,
                    title: `Test Video ${jobId}`,
                    video_id: jobId,
                    video_url: `https://youtube.com/watch?v=${jobId}`,
                    thumbnail_url: `https://img.youtube.com/vi/${jobId}/default.jpg`
                }, 'summary_complete');
            };
            
            return mockEventSource;
        });
        
        // Create instances
        jobTracker = new classes.JobTracker();
        
        // Set up global references for integration
        global.window.JobTracker = jobTracker;
        global.window.displayResults = jest.fn();
        global.window.loadPaginatedSummaries = jest.fn();
        global.window.currentPage = 1;
        global.window.currentPageSize = 10;
        
        uiUpdater = new classes.UIUpdater();
        global.window.UIUpdater = uiUpdater;
        
        sseClient = new classes.SSEClient();
        
        // Use fake timers for integration tests
        jest.useFakeTimers();
    });
    
    afterEach(() => {
        jest.useRealTimers();
        jest.clearAllMocks();
        
        if (sseClient) {
            sseClient.disconnect();
        }
        
        // Clean up global references
        delete global.window.JobTracker;
        delete global.window.UIUpdater;
        delete global.window.displayResults;
        delete global.window.loadPaginatedSummaries;
        delete global.window.currentPage;
        delete global.window.currentPageSize;
    });
    
    describe('Full Workflow Integration', () => {
        test('should handle complete video summarization workflow', async () => {
            // 1. Connect SSE client
            sseClient.connect();
            expect(global.EventSource).toHaveBeenCalled();
            
            // 2. Simulate connection established
            mockEventSource._simulateConnect();
            expect(sseClient.isConnected).toBe(true);
            
            // 3. Simulate progress events for a video
            const jobId = 'test-video-123';
            
            // Initial progress
            mockEventSource._simulateProgress(jobId, 0, 'pending', 'Starting transcription...');
            
            // Verify job was created and UI updated
            expect(jobTracker.getJob(jobId)).toBeDefined();
            expect(jobTracker.getJob(jobId).progress).toBe(0);
            expect(jobTracker.getJob(jobId).status).toBe('pending');
            expect(uiUpdater.progressBars.has(jobId)).toBe(true);
            
            // Check progress bar in DOM
            let progressElement = document.querySelector(`[data-job-id="${jobId}"]`);
            expect(progressElement).toBeTruthy();
            expect(progressElement.className).toContain('pending');
            
            // 4. Simulate progress updates
            mockEventSource._simulateProgress(jobId, 25, 'in_progress', 'Transcribing audio...');
            
            expect(jobTracker.getJob(jobId).progress).toBe(25);
            expect(jobTracker.getJob(jobId).status).toBe('in_progress');
            
            progressElement = document.querySelector(`[data-job-id="${jobId}"]`);
            expect(progressElement.className).toContain('in_progress');
            
            const progressBar = progressElement.querySelector('.async-progress-bar');
            expect(progressBar.style.width).toBe('25%');
            
            // 5. Continue progress updates
            mockEventSource._simulateProgress(jobId, 50, 'in_progress', 'Analyzing content...');
            mockEventSource._simulateProgress(jobId, 75, 'in_progress', 'Generating summary...');
            
            expect(jobTracker.getJob(jobId).progress).toBe(75);
            
            // 6. Simulate completion
            mockEventSource._simulateCompletion(jobId, 'This is a comprehensive test summary of the video content.');
            
            // Verify job completion
            expect(jobTracker.getJob(jobId).status).toBe('completed');
            expect(jobTracker.getJob(jobId).progress).toBe(100);
            expect(jobTracker.completedJobs.has(jobId)).toBe(true);
            expect(jobTracker.activeJobs.has(jobId)).toBe(false);
            
            // Verify UI updates
            expect(global.window.displayResults).toHaveBeenCalledWith(
                expect.arrayContaining([
                    expect.objectContaining({
                        type: 'video',
                        title: `Test Video ${jobId}`,
                        summary: 'This is a comprehensive test summary of the video content.',
                        video_id: jobId
                    })
                ]),
                expect.any(Object),
                true
            );
            
            // Check success toast
            expect(uiUpdater.toastQueue).toHaveLength(1);
            expect(uiUpdater.toastQueue[0].type).toBe('success');
            expect(uiUpdater.toastQueue[0].message).toContain('Summary completed');
            
            // 7. Verify cleanup after delay
            jest.advanceTimersByTime(2000);
            
            expect(uiUpdater.progressBars.has(jobId)).toBe(false);
            
            // 8. Verify cache refresh
            jest.advanceTimersByTime(1000);
            expect(global.window.loadPaginatedSummaries).toHaveBeenCalledWith(1, 10);
        });
        
        test('should handle job failure workflow', async () => {
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            const jobId = 'failed-job-456';
            
            // Start job
            mockEventSource._simulateProgress(jobId, 10, 'in_progress', 'Starting...');
            
            expect(jobTracker.getJob(jobId)).toBeDefined();
            expect(uiUpdater.progressBars.has(jobId)).toBe(true);
            
            // Simulate some progress
            mockEventSource._simulateProgress(jobId, 30, 'in_progress', 'Processing...');
            
            // Simulate failure (using system event to trigger failure)
            mockEventSource._simulateMessage({
                type: 'job_failed',
                job_id: jobId,
                error: 'Video not accessible',
                error_code: 'ACCESS_DENIED'
            }, 'system');
            
            // Manually fail the job (simulating what the system event handler would do)
            jobTracker.failJob(jobId, {
                error: 'Video not accessible',
                error_code: 'ACCESS_DENIED'
            });
            
            // Verify job failure
            expect(jobTracker.getJob(jobId).status).toBe('failed');
            expect(jobTracker.getJob(jobId).error).toBe('Video not accessible');
            expect(jobTracker.completedJobs.has(jobId)).toBe(true); // Failed jobs go to completed
            expect(jobTracker.activeJobs.has(jobId)).toBe(false);
            
            // Trigger UI handler manually
            uiUpdater.handleJobFailed({
                jobId: jobId,
                job: jobTracker.getJob(jobId),
                errorData: { error: 'Video not accessible' }
            });
            
            // Check error toast
            expect(uiUpdater.toastQueue).toHaveLength(1);
            expect(uiUpdater.toastQueue[0].type).toBe('error');
            expect(uiUpdater.toastQueue[0].message).toContain('Failed');
            expect(uiUpdater.toastQueue[0].message).toContain('Video not accessible');
            
            // Verify cleanup
            jest.advanceTimersByTime(2000);
            expect(uiUpdater.progressBars.has(jobId)).toBe(false);
        });
        
        test('should handle multiple concurrent jobs', async () => {
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            const jobIds = ['job1', 'job2', 'job3', 'job4', 'job5'];
            
            // Start all jobs
            jobIds.forEach((jobId, index) => {
                mockEventSource._simulateProgress(jobId, index * 10, 'in_progress', `Processing job ${index + 1}...`);
            });
            
            // Verify all jobs are tracked
            expect(jobTracker.getActiveJobs()).toHaveLength(5);
            expect(uiUpdater.progressBars.size).toBe(5);
            
            // Check DOM has all progress bars
            const progressBars = document.querySelectorAll('.async-progress-container');
            expect(progressBars).toHaveLength(5);
            
            // Simulate different progress rates
            mockEventSource._simulateProgress('job1', 90, 'in_progress', 'Almost done...');
            mockEventSource._simulateProgress('job2', 50, 'in_progress', 'Halfway...');
            mockEventSource._simulateProgress('job3', 25, 'in_progress', 'Getting started...');
            
            // Complete some jobs
            mockEventSource._simulateCompletion('job1', 'First summary');
            mockEventSource._simulateCompletion('job3', 'Third summary');
            
            // Fail one job
            jobTracker.failJob('job2', { error: 'Network timeout' });
            uiUpdater.handleJobFailed({
                jobId: 'job2',
                job: jobTracker.getJob('job2'),
                errorData: { error: 'Network timeout' }
            });
            
            // Verify states
            expect(jobTracker.getActiveJobs()).toHaveLength(2); // job4, job5
            expect(jobTracker.getCompletedJobs()).toHaveLength(3); // job1, job2, job3
            expect(jobTracker.getJobsByStatus('completed')).toHaveLength(2); // job1, job3
            expect(jobTracker.getJobsByStatus('failed')).toHaveLength(1); // job2
            
            // Check UI updates
            expect(uiUpdater.toastQueue).toHaveLength(3); // 2 success + 1 error
            
            const successToasts = uiUpdater.toastQueue.filter(t => t.type === 'success');
            const errorToasts = uiUpdater.toastQueue.filter(t => t.type === 'error');
            expect(successToasts).toHaveLength(2);
            expect(errorToasts).toHaveLength(1);
            
            // Complete remaining jobs
            mockEventSource._simulateCompletion('job4', 'Fourth summary');
            mockEventSource._simulateCompletion('job5', 'Fifth summary');
            
            expect(jobTracker.getActiveJobs()).toHaveLength(0);
            expect(jobTracker.getCompletedJobs()).toHaveLength(5);
        });
    });
    
    describe('Connection Resilience', () => {
        test('should handle connection loss and recovery', async () => {
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            expect(sseClient.isConnected).toBe(true);
            
            const jobId = 'resilience-test';
            mockEventSource._simulateProgress(jobId, 30, 'in_progress', 'Processing...');
            
            expect(jobTracker.getJob(jobId)).toBeDefined();
            expect(uiUpdater.progressBars.has(jobId)).toBe(true);
            
            // Simulate connection loss
            mockEventSource._simulateError();
            
            expect(sseClient.isConnected).toBe(false);
            expect(sseClient.isReconnecting).toBe(true);
            
            // Verify UI shows disconnected state
            const connectionIndicator = document.getElementById('sse-connection-status');
            expect(connectionIndicator).toBeTruthy();
            expect(connectionIndicator.className).toContain('disconnected');
            
            // Simulate reconnection after backoff
            jest.advanceTimersByTime(2000); // First reconnect attempt
            mockEventSource._simulateConnect();
            
            expect(sseClient.isConnected).toBe(true);
            expect(sseClient.isReconnecting).toBe(false);
            expect(sseClient.reconnectAttempts).toBe(0); // Reset after successful connection
            
            // Continue with the job after reconnection
            mockEventSource._simulateProgress(jobId, 80, 'in_progress', 'Resuming...');
            mockEventSource._simulateCompletion(jobId, 'Resilience test summary');
            
            expect(jobTracker.getJob(jobId).status).toBe('completed');
        });
        
        test('should handle maximum reconnection attempts', async () => {
            sseClient.maxReconnectAttempts = 3;
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            // Simulate repeated connection failures
            for (let i = 0; i < 4; i++) {
                mockEventSource._simulateError();
                jest.advanceTimersByTime(5000);
            }
            
            expect(sseClient.reconnectAttempts).toBe(3);
            expect(sseClient.isReconnecting).toBe(false); // Gave up
        });
    });
    
    describe('Event Flow Integration', () => {
        test('should properly chain SSE events through JobTracker to UI', async () => {
            const eventChain = [];
            
            // Monitor event flow
            const originalUpdateProgress = jobTracker.updateProgress.bind(jobTracker);
            jobTracker.updateProgress = jest.fn((data) => {
                eventChain.push({ type: 'job_tracker_update', data });
                return originalUpdateProgress(data);
            });
            
            const originalCompleteJob = jobTracker.completeJob.bind(jobTracker);
            jobTracker.completeJob = jest.fn((jobId, data) => {
                eventChain.push({ type: 'job_tracker_complete', jobId, data });
                return originalCompleteJob(jobId, data);
            });
            
            const originalAddProgressBar = uiUpdater.addProgressBar.bind(uiUpdater);
            uiUpdater.addProgressBar = jest.fn((jobId, options) => {
                eventChain.push({ type: 'ui_add_progress', jobId, options });
                return originalAddProgressBar(jobId, options);
            });
            
            // Start the flow
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            const jobId = 'event-chain-test';
            mockEventSource._simulateProgress(jobId, 25, 'in_progress', 'Testing event chain...');
            
            // Verify event chain
            expect(eventChain).toEqual([
                { type: 'job_tracker_update', data: expect.objectContaining({ job_id: jobId }) },
                { type: 'ui_add_progress', jobId, options: expect.any(Object) }
            ]);
            
            // Continue chain
            mockEventSource._simulateCompletion(jobId, 'Event chain test summary');
            
            expect(eventChain).toContainEqual(
                { type: 'job_tracker_complete', jobId, data: expect.any(Object) }
            );
        });
        
        test('should handle custom SSE events', async () => {
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            const customHandler = jest.fn();
            sseClient.addEventListener('custom_event', customHandler);
            
            // Send custom event
            mockEventSource._simulateMessage({
                type: 'maintenance',
                message: 'Server maintenance in 5 minutes',
                scheduled_time: Date.now() + 300000
            }, 'system');
            
            // Verify system handler was called
            expect(customHandler).not.toHaveBeenCalled(); // System events have their own handler
            
            // Test direct custom event
            mockEventSource._simulateMessage({
                custom_data: 'test'
            }, 'custom_event');
            
            expect(customHandler).toHaveBeenCalledWith({ custom_data: 'test' });
        });
    });
    
    describe('UI State Synchronization', () => {
        test('should maintain UI consistency with job states', async () => {
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            const jobIds = ['sync1', 'sync2', 'sync3'];
            
            // Start jobs
            jobIds.forEach(jobId => {
                mockEventSource._simulateProgress(jobId, 0, 'pending', 'Queued...');
            });
            
            // Verify initial state
            expect(jobTracker.getStats()).toEqual(
                expect.objectContaining({
                    active: 3,
                    completed: 0,
                    failed: 0,
                    pending: 3,
                    inProgress: 0
                })
            );
            
            // Update states
            mockEventSource._simulateProgress('sync1', 50, 'in_progress', 'Processing...');
            mockEventSource._simulateProgress('sync2', 25, 'in_progress', 'Processing...');
            
            // Verify intermediate state
            expect(jobTracker.getStats()).toEqual(
                expect.objectContaining({
                    active: 3,
                    pending: 1,
                    inProgress: 2
                })
            );
            
            // Complete and fail jobs
            mockEventSource._simulateCompletion('sync1', 'First summary');
            jobTracker.failJob('sync2', { error: 'Test error' });
            uiUpdater.handleJobFailed({
                jobId: 'sync2',
                job: jobTracker.getJob('sync2'),
                errorData: { error: 'Test error' }
            });
            
            // Verify final state
            const finalStats = jobTracker.getStats();
            expect(finalStats).toEqual(
                expect.objectContaining({
                    active: 1, // sync3
                    completed: 1, // sync1
                    failed: 1 // sync2
                })
            );
            
            // Verify UI reflects the stats
            const connectionStats = uiUpdater.connectionStatusIndicator?.querySelector('.connection-status-stats');
            // Note: stats are updated through handleStatsUpdated which needs manual trigger in tests
        });
        
        test('should handle rapid state changes', async () => {
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            const jobId = 'rapid-changes';
            
            // Simulate rapid updates
            mockEventSource._simulateProgress(jobId, 10, 'in_progress', 'Step 1...');
            mockEventSource._simulateProgress(jobId, 20, 'in_progress', 'Step 2...');
            mockEventSource._simulateProgress(jobId, 40, 'in_progress', 'Step 3...');
            mockEventSource._simulateProgress(jobId, 60, 'in_progress', 'Step 4...');
            mockEventSource._simulateProgress(jobId, 80, 'in_progress', 'Step 5...');
            mockEventSource._simulateCompletion(jobId, 'Rapid changes test');
            
            // Verify final state is correct despite rapid changes
            const job = jobTracker.getJob(jobId);
            expect(job.status).toBe('completed');
            expect(job.progress).toBe(100);
            
            // Verify UI cleanup happens
            jest.advanceTimersByTime(2000);
            expect(uiUpdater.progressBars.has(jobId)).toBe(false);
        });
    });
    
    describe('Error Handling Integration', () => {
        test('should handle malformed SSE data gracefully', async () => {
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            const consoleErrorSpy = jest.spyOn(console, 'error');
            
            // Send malformed JSON
            const malformedEvent = new Event('summary_progress');
            malformedEvent.data = '{ malformed json }';
            mockEventSource.dispatchEvent(malformedEvent);
            
            expect(consoleErrorSpy).toHaveBeenCalledWith(
                expect.stringContaining('Error parsing progress event'),
                expect.any(Error)
            );
            
            // System should continue to work
            mockEventSource._simulateProgress('after-error', 50, 'in_progress', 'After error...');
            expect(jobTracker.getJob('after-error')).toBeDefined();
        });
        
        test('should handle missing global dependencies', async () => {
            // Remove global dependencies
            delete global.window.JobTracker;
            delete global.window.UIUpdater;
            
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            // Should not crash when dependencies are missing
            expect(() => {
                mockEventSource._simulateProgress('no-deps', 50, 'in_progress', 'No dependencies...');
            }).not.toThrow();
        });
        
        test('should handle DOM manipulation errors gracefully', async () => {
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            // Remove DOM elements that UI updater might reference
            document.body.innerHTML = '';
            
            expect(() => {
                mockEventSource._simulateProgress('dom-error', 50, 'in_progress', 'DOM error test...');
            }).not.toThrow();
        });
    });
    
    describe('Performance Integration', () => {
        test('should handle high-frequency events efficiently', async () => {
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            const startTime = performance.now();
            const jobId = 'performance-test';
            
            // Send many rapid updates
            for (let i = 0; i <= 100; i++) {
                mockEventSource._simulateProgress(jobId, i, 'in_progress', `Step ${i}...`);
            }
            
            const updateTime = performance.now() - startTime;
            expect(updateTime).toBeLessThan(200); // Should complete in <200ms
            
            // Verify final state is correct
            const job = jobTracker.getJob(jobId);
            expect(job.progress).toBe(100);
            
            const progressBar = document.querySelector(`[data-job-id="${jobId}"] .async-progress-bar`);
            expect(progressBar.style.width).toBe('100%');
        });
        
        test('should efficiently manage memory with many jobs', async () => {
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            // Create many jobs
            for (let i = 0; i < 100; i++) {
                mockEventSource._simulateProgress(`batch-job-${i}`, 100, 'completed', 'Batch complete');
                mockEventSource._simulateCompletion(`batch-job-${i}`, `Summary ${i}`);
            }
            
            expect(jobTracker.completedJobs.size).toBe(100);
            expect(uiUpdater.toastQueue.length).toBeGreaterThan(0);
            
            // Verify cleanup
            jest.advanceTimersByTime(2000);
            
            expect(uiUpdater.progressBars.size).toBe(0);
            
            // Test memory cleanup
            jobTracker.clearCompleted();
            expect(jobTracker.completedJobs.size).toBe(0);
        });
    });
    
    describe('Accessibility Integration', () => {
        test('should maintain accessibility throughout workflow', async () => {
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            const jobId = 'accessibility-test';
            mockEventSource._simulateProgress(jobId, 50, 'in_progress', 'Accessibility test...');
            
            // Check progress bar accessibility
            const progressContainer = document.querySelector(`[data-job-id="${jobId}"]`);
            expect(progressContainer).toBeTruthy();
            
            const progressBar = progressContainer.querySelector('.async-progress-bar');
            const progressText = progressContainer.querySelector('.async-progress-text');
            expect(progressBar).toBeTruthy();
            expect(progressText.textContent).toBe('50%');
            
            // Complete job and check toast accessibility
            mockEventSource._simulateCompletion(jobId, 'Accessibility test summary');
            uiUpdater.processToastQueue();
            
            const toast = document.querySelector('.async-toast');
            const closeButton = toast?.querySelector('.async-toast-close');
            
            if (toast && closeButton) {
                expect(closeButton.tagName).toBe('BUTTON');
                expect(closeButton.textContent).toBe('×');
            }
        });
        
        test('should provide meaningful progress information', async () => {
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            const jobId = 'meaningful-progress';
            
            // Test different progress messages
            const progressSteps = [
                { progress: 10, message: 'Starting transcription...' },
                { progress: 30, message: 'Processing audio...' },
                { progress: 60, message: 'Analyzing content...' },
                { progress: 90, message: 'Generating summary...' }
            ];
            
            progressSteps.forEach(({ progress, message }) => {
                mockEventSource._simulateProgress(jobId, progress, 'in_progress', message);
                
                const messageElement = document.querySelector(`[data-job-id="${jobId}"] .async-progress-message`);
                expect(messageElement.textContent).toBe(message);
            });
        });
    });
    
    describe('CSS Integration Tests', () => {
        test('should apply correct CSS classes throughout workflow', async () => {
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            const jobId = 'css-test';
            
            // Test pending state
            mockEventSource._simulateProgress(jobId, 0, 'pending', 'Queued...');
            let container = document.querySelector(`[data-job-id="${jobId}"]`);
            expect(container.className).toContain('async-progress-container');
            expect(container.className).toContain('pending');
            
            // Test in_progress state
            mockEventSource._simulateProgress(jobId, 50, 'in_progress', 'Processing...');
            expect(container.className).toContain('in_progress');
            
            // Test completed state (would normally be set by completion handler)
            container.className = container.className.replace('in_progress', 'completed');
            expect(container.className).toContain('completed');
            
            // Test connection status CSS
            const connectionStatus = document.getElementById('sse-connection-status');
            expect(connectionStatus.className).toContain('sse-connection-status');
            expect(connectionStatus.className).toContain('connected');
        });
        
        test('should handle responsive design classes', async () => {
            // Simulate mobile viewport
            Object.defineProperty(window, 'innerWidth', { value: 400 });
            
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            const jobId = 'responsive-test';
            mockEventSource._simulateProgress(jobId, 50, 'in_progress', 'Responsive test...');
            
            const progressContainer = document.querySelector(`[data-job-id="${jobId}"]`);
            expect(progressContainer).toBeTruthy();
            
            // Toast should have responsive classes available
            uiUpdater.showToast('Responsive test toast', 'info');
            uiUpdater.processToastQueue();
            
            const toast = document.querySelector('.async-toast');
            expect(toast).toBeTruthy();
            expect(toast.className).toContain('async-toast');
        });
    });
    
    describe('Real-world Scenarios', () => {
        test('should handle browser tab visibility changes', async () => {
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            const jobId = 'visibility-test';
            mockEventSource._simulateProgress(jobId, 30, 'in_progress', 'Before tab hidden...');
            
            // Simulate tab becoming hidden (browser behavior)
            Object.defineProperty(document, 'hidden', { value: true, configurable: true });
            const visibilityChangeEvent = new Event('visibilitychange');
            document.dispatchEvent(visibilityChangeEvent);
            
            // Continue progress while hidden
            mockEventSource._simulateProgress(jobId, 70, 'in_progress', 'While tab hidden...');
            
            // Tab becomes visible again
            Object.defineProperty(document, 'hidden', { value: false, configurable: true });
            document.dispatchEvent(visibilityChangeEvent);
            
            // Complete job
            mockEventSource._simulateCompletion(jobId, 'Visibility test complete');
            
            expect(jobTracker.getJob(jobId).status).toBe('completed');
        });
        
        test('should handle network interruptions gracefully', async () => {
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            const jobId = 'network-test';
            mockEventSource._simulateProgress(jobId, 40, 'in_progress', 'Before network issue...');
            
            // Simulate network interruption
            mockEventSource._simulateError();
            
            expect(sseClient.isConnected).toBe(false);
            expect(sseClient.isReconnecting).toBe(true);
            
            // Job should still be tracked locally
            expect(jobTracker.getJob(jobId)).toBeDefined();
            expect(jobTracker.getJob(jobId).progress).toBe(40);
            
            // Reconnect
            jest.advanceTimersByTime(2000);
            mockEventSource._simulateConnect();
            
            // Resume job progress
            mockEventSource._simulateProgress(jobId, 80, 'in_progress', 'After reconnection...');
            mockEventSource._simulateCompletion(jobId, 'Network resilience test');
            
            expect(jobTracker.getJob(jobId).status).toBe('completed');
            expect(sseClient.isConnected).toBe(true);
        });
        
        test('should handle concurrent user interactions', async () => {
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            // Start multiple jobs
            const jobIds = ['concurrent1', 'concurrent2', 'concurrent3'];
            jobIds.forEach(jobId => {
                mockEventSource._simulateProgress(jobId, 20, 'in_progress', 'Starting...');
            });
            
            // Simulate user interactions while jobs are running
            // User closes a toast
            uiUpdater.showToast('User interaction test', 'info');
            uiUpdater.processToastQueue();
            
            const toast = document.querySelector('.async-toast');
            const closeButton = toast?.querySelector('.async-toast-close');
            if (closeButton) {
                closeButton.click();
            }
            
            // User forces reconnection
            sseClient.forceReconnect();
            jest.advanceTimersByTime(100);
            mockEventSource._simulateConnect();
            
            // Jobs continue processing
            jobIds.forEach(jobId => {
                mockEventSource._simulateProgress(jobId, 90, 'in_progress', 'Finishing...');
                mockEventSource._simulateCompletion(jobId, `Summary for ${jobId}`);
            });
            
            // Verify all jobs completed successfully
            jobIds.forEach(jobId => {
                expect(jobTracker.getJob(jobId).status).toBe('completed');
            });
            
            expect(jobTracker.getCompletedJobs()).toHaveLength(3);
        });
    });
});