/**
 * Performance Tests - Testing performance characteristics and optimization
 * Module 4: Client-Side JavaScript Tests
 */

import { jest } from '@jest/globals';
import fs from 'fs';
import path from 'path';

// Load source files
const sseClientPath = path.resolve('./static/js/sse_client.js');
const jobTrackerPath = path.resolve('./static/js/job_tracker.js');
const uiUpdaterPath = path.resolve('./static/js/ui_updater.js');

const sseClientCode = fs.readFileSync(sseClientPath, 'utf8');
const jobTrackerCode = fs.readFileSync(jobTrackerPath, 'utf8');
const uiUpdaterCode = fs.readFileSync(uiUpdaterPath, 'utf8');

// Clean code for testing
const cleanSSECode = sseClientCode
    .replace(/window\.SSEClient = SSEClient;/, '')
    .replace(/if \(typeof window !== 'undefined'.*?}/, '');

const cleanJobTrackerCode = jobTrackerCode
    .replace(/window\.JobTracker = new JobTracker\(\);/, '')
    .replace(/console\.log\('🎯 JobTracker: JobTracker loaded and ready'\);/, '');

const cleanUIUpdaterCode = uiUpdaterCode
    .replace(/window\.UIUpdater = new UIUpdater\(\);/, '')
    .replace(/console\.log\('🎯 UIUpdater: UIUpdater loaded and ready'\);/, '');

// Performance testing utilities
const createPerformanceTestEnvironment = () => {
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

// Performance measurement utilities
const measurePerformance = (fn, label) => {
    const start = performance.now();
    const result = fn();
    const end = performance.now();
    const duration = end - start;
    
    // Log performance for debugging
    if (process.env.NODE_ENV !== 'test') {
        console.log(`${label}: ${duration.toFixed(3)}ms`);
    }
    
    return { result, duration };
};

const measureAsyncPerformance = async (fn, label) => {
    const start = performance.now();
    const result = await fn();
    const end = performance.now();
    const duration = end - start;
    
    if (process.env.NODE_ENV !== 'test') {
        console.log(`${label}: ${duration.toFixed(3)}ms`);
    }
    
    return { result, duration };
};

describe('Performance Tests', () => {
    let classes;
    let mockEventSource;
    
    beforeEach(() => {
        // Reset DOM
        document.body.innerHTML = '';
        document.head.innerHTML = '';
        
        // Create performance test environment
        classes = createPerformanceTestEnvironment();
        
        // Enhanced EventSource mock for performance testing
        const originalEventSource = global.EventSource;
        global.EventSource = jest.fn().mockImplementation(function(url, options) {
            mockEventSource = new originalEventSource(url, options);
            
            mockEventSource._simulateConnect = () => {
                mockEventSource.readyState = EventSource.OPEN;
                mockEventSource.dispatchEvent(new Event('open'));
            };
            
            mockEventSource._simulateMessage = (data, type = 'message') => {
                const event = new Event(type);
                event.data = typeof data === 'string' ? data : JSON.stringify(data);
                mockEventSource.dispatchEvent(event);
            };
            
            mockEventSource._simulateManyMessages = (count, delay = 0) => {
                for (let i = 0; i < count; i++) {
                    setTimeout(() => {
                        mockEventSource._simulateMessage({
                            job_id: `perf-job-${i}`,
                            progress: Math.min(100, (i / count) * 100),
                            status: i === count - 1 ? 'completed' : 'in_progress',
                            message: `Processing ${i + 1}/${count}`
                        }, 'summary_progress');
                    }, delay * i);
                }
            };
            
            return mockEventSource;
        });
        
        jest.useFakeTimers();
    });
    
    afterEach(() => {
        jest.useRealTimers();
        jest.clearAllMocks();
    });
    
    describe('SSEClient Performance', () => {
        test('should handle rapid event processing efficiently', () => {
            const sseClient = new classes.SSEClient();
            
            const { duration } = measurePerformance(() => {
                sseClient.connect();
                mockEventSource._simulateConnect();
                
                // Simulate 1000 rapid events
                for (let i = 0; i < 1000; i++) {
                    mockEventSource._simulateMessage({
                        job_id: `rapid-${i}`,
                        progress: i % 100,
                        message: `Rapid event ${i}`
                    }, 'summary_progress');
                }
            }, 'Rapid SSE event processing');
            
            expect(duration).toBeLessThan(200); // Should complete in <200ms
            expect(sseClient.isConnected).toBe(true);
        });
        
        test('should handle connection state changes efficiently', () => {
            const sseClient = new classes.SSEClient();
            
            const { duration } = measurePerformance(() => {
                // Simulate rapid connection state changes
                for (let i = 0; i < 100; i++) {
                    sseClient.connect();
                    mockEventSource._simulateConnect();
                    sseClient.disconnect();
                }
            }, 'Rapid connection state changes');
            
            expect(duration).toBeLessThan(100); // Should complete in <100ms
        });
        
        test('should efficiently manage event handlers', () => {
            const sseClient = new classes.SSEClient();
            const handlers = [];
            
            const { duration } = measurePerformance(() => {
                // Add many event handlers
                for (let i = 0; i < 500; i++) {
                    const handler = jest.fn();
                    handlers.push(handler);
                    sseClient.addEventListener('test_event', handler);
                }
                
                // Trigger event
                sseClient.triggerHandler('test_event', { data: 'test' });
            }, 'Event handler management');
            
            expect(duration).toBeLessThan(50); // Should complete in <50ms
            
            // Verify all handlers were called
            handlers.forEach(handler => {
                expect(handler).toHaveBeenCalledWith({ data: 'test' });
            });
        });
        
        test('should handle reconnection logic efficiently', () => {
            const sseClient = new classes.SSEClient();
            sseClient.maxReconnectAttempts = 20;
            
            const { duration } = measurePerformance(() => {
                sseClient.connect();
                
                // Simulate multiple rapid failures and reconnections
                for (let i = 0; i < 10; i++) {
                    mockEventSource._simulateConnect();
                    mockEventSource._simulateError();
                    jest.advanceTimersByTime(100);
                }
            }, 'Reconnection logic');
            
            expect(duration).toBeLessThan(100); // Should complete in <100ms
        });
    });
    
    describe('JobTracker Performance', () => {
        test('should handle large numbers of jobs efficiently', () => {
            const jobTracker = new classes.JobTracker();
            
            const { duration } = measurePerformance(() => {
                // Add 1000 jobs
                for (let i = 0; i < 1000; i++) {
                    jobTracker.addJob(`perf-job-${i}`, {
                        title: `Performance Job ${i}`,
                        type: 'video',
                        url: `https://youtube.com/watch?v=perf${i}`
                    });
                }
            }, 'Adding 1000 jobs');
            
            expect(duration).toBeLessThan(100); // Should complete in <100ms
            expect(jobTracker.activeJobs.size).toBe(1000);
        });
        
        test('should efficiently process progress updates', () => {
            const jobTracker = new classes.JobTracker();
            
            // Pre-populate with jobs
            for (let i = 0; i < 100; i++) {
                jobTracker.addJob(`update-job-${i}`, { title: `Update Job ${i}` });
            }
            
            const { duration } = measurePerformance(() => {
                // Update all jobs multiple times
                for (let round = 0; round < 10; round++) {
                    for (let i = 0; i < 100; i++) {
                        jobTracker.updateProgress({
                            job_id: `update-job-${i}`,
                            progress: (round + 1) * 10,
                            status: round === 9 ? 'completed' : 'in_progress',
                            message: `Round ${round + 1}`
                        });
                    }
                }
            }, 'Processing 1000 progress updates');
            
            expect(duration).toBeLessThan(150); // Should complete in <150ms
        });
        
        test('should handle job queries efficiently', () => {
            const jobTracker = new classes.JobTracker();
            
            // Create diverse job set
            for (let i = 0; i < 500; i++) {
                jobTracker.addJob(`query-job-${i}`, { title: `Query Job ${i}` });
                if (i % 2 === 0) {
                    jobTracker.completeJob(`query-job-${i}`);
                } else if (i % 3 === 0) {
                    jobTracker.failJob(`query-job-${i}`, { error: 'Test error' });
                }
            }
            
            const { duration } = measurePerformance(() => {
                // Perform many queries
                for (let i = 0; i < 100; i++) {
                    jobTracker.getActiveJobs();
                    jobTracker.getCompletedJobs();
                    jobTracker.getJobsByStatus('completed');
                    jobTracker.getJobsByStatus('failed');
                    jobTracker.getStats();
                }
            }, 'Job queries');
            
            expect(duration).toBeLessThan(50); // Should complete in <50ms
        });
        
        test('should manage job history efficiently', () => {
            const jobTracker = new classes.JobTracker();
            jobTracker.maxHistorySize = 1000;
            
            const { duration } = measurePerformance(() => {
                // Add and complete many jobs to build history
                for (let i = 0; i < 1500; i++) {
                    jobTracker.addJob(`history-job-${i}`, { title: `History Job ${i}` });
                    jobTracker.completeJob(`history-job-${i}`, { result: `Result ${i}` });
                }
            }, 'Building job history');
            
            expect(duration).toBeLessThan(200); // Should complete in <200ms
            expect(jobTracker.jobHistory.length).toBe(1000); // Should respect max size
            
            // Test history retrieval
            const { duration: retrievalDuration } = measurePerformance(() => {
                for (let i = 0; i < 100; i++) {
                    jobTracker.getHistory(50);
                }
            }, 'History retrieval');
            
            expect(retrievalDuration).toBeLessThan(20);
        });
        
        test('should handle data import/export efficiently', () => {
            const jobTracker = new classes.JobTracker();
            
            // Create test data
            for (let i = 0; i < 100; i++) {
                jobTracker.addJob(`export-job-${i}`, { title: `Export Job ${i}` });
                if (i < 50) {
                    jobTracker.completeJob(`export-job-${i}`);
                }
            }
            
            let exportData;
            const { duration: exportDuration } = measurePerformance(() => {
                exportData = jobTracker.exportData();
            }, 'Data export');
            
            expect(exportDuration).toBeLessThan(50);
            
            // Test import
            const newJobTracker = new classes.JobTracker();
            const { duration: importDuration } = measurePerformance(() => {
                newJobTracker.importData(exportData);
            }, 'Data import');
            
            expect(importDuration).toBeLessThan(50);
            expect(newJobTracker.activeJobs.size).toBe(50);
            expect(newJobTracker.completedJobs.size).toBe(50);
        });
    });
    
    describe('UIUpdater Performance', () => {
        test('should handle many progress bars efficiently', () => {
            global.window.JobTracker = { addEventListener: jest.fn() };
            const uiUpdater = new classes.UIUpdater();
            
            const { duration } = measurePerformance(() => {
                // Add 100 progress bars
                for (let i = 0; i < 100; i++) {
                    uiUpdater.addProgressBar(`ui-perf-${i}`, {
                        title: `UI Performance Job ${i}`,
                        progress: i % 100,
                        status: 'in_progress'
                    });
                }
            }, 'Adding 100 progress bars');
            
            expect(duration).toBeLessThan(200); // Should complete in <200ms
            expect(uiUpdater.progressBars.size).toBe(100);
            expect(document.querySelectorAll('.async-progress-container')).toHaveLength(100);
        });
        
        test('should update progress bars efficiently', () => {
            global.window.JobTracker = { addEventListener: jest.fn() };
            const uiUpdater = new classes.UIUpdater();
            
            // Pre-create progress bars
            for (let i = 0; i < 50; i++) {
                uiUpdater.addProgressBar(`update-perf-${i}`, {
                    title: `Update Performance ${i}`,
                    progress: 0,
                    status: 'pending'
                });
            }
            
            const { duration } = measurePerformance(() => {
                // Update all progress bars multiple times
                for (let round = 0; round < 20; round++) {
                    for (let i = 0; i < 50; i++) {
                        uiUpdater.updateProgressBar(`update-perf-${i}`, {
                            progress: (round / 19) * 100,
                            status: round === 19 ? 'completed' : 'in_progress',
                            message: `Round ${round + 1}/20`
                        });
                    }
                }
            }, 'Updating progress bars');
            
            expect(duration).toBeLessThan(300); // Should complete in <300ms
        });
        
        test('should handle toast notifications efficiently', async () => {
            global.window.JobTracker = { addEventListener: jest.fn() };
            const uiUpdater = new classes.UIUpdater();
            uiUpdater.maxToasts = 50; // Allow many toasts for performance testing
            
            const { duration } = await measureAsyncPerformance(async () => {
                // Add many toasts
                for (let i = 0; i < 200; i++) {
                    uiUpdater.showToast(`Performance toast ${i}`, 'info', { duration: 1000 });
                }
                
                // Process them
                await uiUpdater.processToastQueue();
            }, 'Toast notification processing');
            
            expect(duration).toBeLessThan(500); // Should complete in <500ms
            expect(uiUpdater.toastQueue.length).toBeLessThanOrEqual(200);
        });
        
        test('should handle DOM manipulation efficiently', () => {
            global.window.JobTracker = { addEventListener: jest.fn() };
            const uiUpdater = new classes.UIUpdater();
            
            const { duration } = measurePerformance(() => {
                // Rapidly add and remove progress bars
                for (let i = 0; i < 50; i++) {
                    uiUpdater.addProgressBar(`dom-perf-${i}`, {
                        title: `DOM Performance ${i}`,
                        progress: 50,
                        status: 'in_progress'
                    });
                }
                
                for (let i = 0; i < 50; i++) {
                    uiUpdater.removeProgressBar(`dom-perf-${i}`);
                }
                
                // Advance timers to complete animations
                jest.advanceTimersByTime(uiUpdater.animationDuration);
            }, 'DOM manipulation');
            
            expect(duration).toBeLessThan(100); // Should complete in <100ms
            expect(uiUpdater.progressBars.size).toBe(0);
        });
        
        test('should efficiently escape HTML in messages', () => {
            global.window.JobTracker = { addEventListener: jest.fn() };
            const uiUpdater = new classes.UIUpdater();
            
            const maliciousStrings = [];
            for (let i = 0; i < 1000; i++) {
                maliciousStrings.push(`<script>alert('${i}')</script>Test message ${i}`);
            }
            
            const { duration } = measurePerformance(() => {
                maliciousStrings.forEach((str, index) => {
                    const escaped = uiUpdater.escapeHtml(str);
                    expect(escaped).not.toContain('<script>');
                    expect(escaped).toContain(`Test message ${index}`);
                });
            }, 'HTML escaping');
            
            expect(duration).toBeLessThan(100); // Should complete in <100ms
        });
    });
    
    describe('Memory Management Performance', () => {
        test('should not leak memory with rapid object creation/destruction', () => {
            const initialMemoryUsage = process.memoryUsage();
            
            // Create and destroy many instances
            for (let i = 0; i < 100; i++) {
                const sseClient = new classes.SSEClient();
                const jobTracker = new classes.JobTracker();
                
                global.window.JobTracker = jobTracker;
                const uiUpdater = new classes.UIUpdater();
                
                // Simulate usage
                sseClient.connect();
                mockEventSource._simulateConnect();
                
                for (let j = 0; j < 10; j++) {
                    jobTracker.addJob(`mem-job-${i}-${j}`, { title: `Memory Job ${i}-${j}` });
                    uiUpdater.addProgressBar(`mem-job-${i}-${j}`, {
                        title: `Memory Job ${i}-${j}`,
                        progress: j * 10,
                        status: 'in_progress'
                    });
                }
                
                // Cleanup
                sseClient.disconnect();
                jobTracker.clearAll();
                uiUpdater.clearAllProgressBars();
                uiUpdater.clearAllToasts();
                
                delete global.window.JobTracker;
            }
            
            const finalMemoryUsage = process.memoryUsage();
            
            // Memory usage shouldn't grow significantly
            const heapGrowth = finalMemoryUsage.heapUsed - initialMemoryUsage.heapUsed;
            expect(heapGrowth).toBeLessThan(50 * 1024 * 1024); // Less than 50MB growth
        });
        
        test('should efficiently clean up event listeners', () => {
            const sseClient = new classes.SSEClient();
            const initialHandlers = new Map();
            
            // Add many handlers
            for (let i = 0; i < 1000; i++) {
                const handler = jest.fn();
                initialHandlers.set(`handler-${i}`, handler);
                sseClient.addEventListener('test_event', handler);
            }
            
            const { duration: addDuration } = measurePerformance(() => {
                // Add more handlers
                for (let i = 1000; i < 2000; i++) {
                    const handler = jest.fn();
                    sseClient.addEventListener('test_event', handler);
                }
            }, 'Adding 1000 more event handlers');
            
            expect(addDuration).toBeLessThan(50);
            
            const { duration: removeDuration } = measurePerformance(() => {
                // Remove initial handlers
                for (const [key, handler] of initialHandlers) {
                    sseClient.removeEventListener('test_event', handler);
                }
            }, 'Removing 1000 event handlers');
            
            expect(removeDuration).toBeLessThan(100);
            
            // Verify correct number of handlers remain
            sseClient.triggerHandler('test_event', { data: 'test' });
            const remainingHandlers = sseClient.eventHandlers.get('test_event');
            expect(remainingHandlers.length).toBe(1000);
        });
    });
    
    describe('Integration Performance', () => {
        test('should handle end-to-end workflow efficiently', () => {
            const sseClient = new classes.SSEClient();
            const jobTracker = new classes.JobTracker();
            
            global.window.JobTracker = jobTracker;
            global.window.displayResults = jest.fn();
            const uiUpdater = new classes.UIUpdater();
            global.window.UIUpdater = uiUpdater;
            
            const { duration } = measurePerformance(() => {
                sseClient.connect();
                mockEventSource._simulateConnect();
                
                // Simulate 20 concurrent job workflows
                for (let i = 0; i < 20; i++) {
                    const jobId = `workflow-${i}`;
                    
                    // Progress through workflow
                    mockEventSource._simulateMessage({
                        job_id: jobId,
                        progress: 25,
                        status: 'in_progress',
                        message: 'Processing...',
                        video_title: `Workflow Video ${i}`
                    }, 'summary_progress');
                    
                    mockEventSource._simulateMessage({
                        job_id: jobId,
                        progress: 75,
                        status: 'in_progress',
                        message: 'Finalizing...'
                    }, 'summary_progress');
                    
                    mockEventSource._simulateMessage({
                        job_id: jobId,
                        summary: `Summary for workflow ${i}`,
                        title: `Workflow Video ${i}`,
                        video_id: jobId
                    }, 'summary_complete');
                }
            }, 'End-to-end workflow for 20 jobs');
            
            expect(duration).toBeLessThan(500); // Should complete in <500ms
            expect(jobTracker.getCompletedJobs()).toHaveLength(20);
            expect(global.window.displayResults).toHaveBeenCalledTimes(20);
            
            delete global.window.JobTracker;
            delete global.window.UIUpdater;
            delete global.window.displayResults;
        });
        
        test('should maintain performance under stress conditions', () => {
            const sseClient = new classes.SSEClient();
            const jobTracker = new classes.JobTracker();
            
            global.window.JobTracker = jobTracker;
            const uiUpdater = new classes.UIUpdater();
            global.window.UIUpdater = uiUpdater;
            
            const { duration } = measurePerformance(() => {
                sseClient.connect();
                mockEventSource._simulateConnect();
                
                // Simulate stress conditions
                for (let i = 0; i < 100; i++) {
                    // Rapid progress updates
                    for (let j = 0; j <= 100; j += 10) {
                        mockEventSource._simulateMessage({
                            job_id: `stress-${i}`,
                            progress: j,
                            status: j === 100 ? 'completed' : 'in_progress',
                            message: `Step ${j}%`
                        }, 'summary_progress');
                    }
                    
                    if (i === 100) {
                        mockEventSource._simulateMessage({
                            job_id: `stress-${i}`,
                            summary: `Stress test summary ${i}`,
                            title: `Stress Video ${i}`
                        }, 'summary_complete');
                    }
                }
                
                // Simulate connection issues
                for (let i = 0; i < 5; i++) {
                    mockEventSource._simulateError();
                    jest.advanceTimersByTime(100);
                    mockEventSource._simulateConnect();
                }
            }, 'Stress test with 100 rapid jobs + connection issues');
            
            expect(duration).toBeLessThan(1000); // Should complete in <1s
            
            delete global.window.JobTracker;
            delete global.window.UIUpdater;
        });
    });
    
    describe('Real-world Performance Scenarios', () => {
        test('should handle browser resource constraints efficiently', () => {
            // Simulate limited browser resources
            const originalRaf = global.requestAnimationFrame;
            let rafDelay = 32; // Simulate 30fps instead of 60fps
            
            global.requestAnimationFrame = jest.fn((callback) => {
                return setTimeout(callback, rafDelay);
            });
            
            global.window.JobTracker = { addEventListener: jest.fn() };
            const uiUpdater = new classes.UIUpdater();
            
            const { duration } = measurePerformance(() => {
                // Add many elements that require animation
                for (let i = 0; i < 50; i++) {
                    uiUpdater.addProgressBar(`resource-${i}`, {
                        title: `Resource Test ${i}`,
                        progress: 0,
                        status: 'pending'
                    });
                    
                    uiUpdater.showToast(`Resource toast ${i}`, 'info');
                }
                
                // Update them all
                for (let i = 0; i < 50; i++) {
                    uiUpdater.updateProgressBar(`resource-${i}`, {
                        progress: 100,
                        status: 'completed'
                    });
                }
                
                uiUpdater.processToastQueue();
                jest.advanceTimersByTime(1000);
            }, 'Resource-constrained environment');
            
            expect(duration).toBeLessThan(800); // Should adapt to constraints
            
            // Restore
            global.requestAnimationFrame = originalRaf;
            delete global.window.JobTracker;
        });
        
        test('should handle large DOM trees efficiently', () => {
            // Create a complex DOM structure
            const container = document.createElement('div');
            for (let i = 0; i < 1000; i++) {
                const element = document.createElement('div');
                element.textContent = `Element ${i}`;
                container.appendChild(element);
            }
            document.body.appendChild(container);
            
            global.window.JobTracker = { addEventListener: jest.fn() };
            const uiUpdater = new classes.UIUpdater();
            
            const { duration } = measurePerformance(() => {
                // Perform DOM operations in complex tree
                for (let i = 0; i < 20; i++) {
                    uiUpdater.addProgressBar(`dom-complex-${i}`, {
                        title: `Complex DOM ${i}`,
                        progress: 50,
                        status: 'in_progress'
                    });
                }
                
                // Update connection status (involves DOM queries)
                for (let i = 0; i < 10; i++) {
                    uiUpdater.updateConnectionStatus(i % 2 === 0, {
                        active: i,
                        completed: i * 2,
                        failed: i
                    });
                }
            }, 'Operations in complex DOM');
            
            expect(duration).toBeLessThan(200);
            
            delete global.window.JobTracker;
        });
    });
});