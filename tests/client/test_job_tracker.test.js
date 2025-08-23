/**
 * Job Tracker Tests - Comprehensive testing for job state management and progress tracking
 * Module 4: Client-Side JavaScript Tests
 */

import { jest } from '@jest/globals';
import fs from 'fs';
import path from 'path';

const jobTrackerPath = path.resolve('./static/js/job_tracker.js');
const jobTrackerCode = fs.readFileSync(jobTrackerPath, 'utf8');

// Remove the auto-initialization and window export for testing
const testableCode = jobTrackerCode
    .replace(/window\.JobTracker = new JobTracker\(\);/, '')
    .replace(/console\.log\('🎯 JobTracker: JobTracker loaded and ready'\);/, '');

// Create a clean environment for each test
const createTestEnvironment = () => {
    const environment = {
        console: global.console,
        Date: global.Date,
        Map: global.Map,
        Array: global.Array,
        Object: global.Object,
        Error: global.Error
    };
    
    // Execute the code in the environment
    const func = new Function('console', 'Date', 'Map', 'Array', 'Object', 'Error',
        testableCode + '; return JobTracker;');
    
    return func(
        environment.console,
        environment.Date,
        environment.Map,
        environment.Array,
        environment.Object,
        environment.Error
    );
};

describe('JobTracker', () => {
    let JobTrackerClass;
    let jobTracker;
    
    beforeEach(() => {
        // Create a fresh class instance for each test
        JobTrackerClass = createTestEnvironment();
        jobTracker = new JobTrackerClass();
        
        // Mock Date.now for consistent timestamps
        const mockDate = new Date('2023-12-01T12:00:00Z');
        jest.spyOn(global, 'Date').mockImplementation(() => mockDate);
        Date.now = jest.fn(() => mockDate.getTime());
    });
    
    afterEach(() => {
        jest.clearAllMocks();
        Date.mockRestore?.();
    });
    
    describe('Constructor and Initialization', () => {
        test('should create JobTracker with correct initial state', () => {
            expect(jobTracker).toBeDefined();
            expect(jobTracker.activeJobs).toBeInstanceOf(Map);
            expect(jobTracker.completedJobs).toBeInstanceOf(Map);
            expect(jobTracker.jobHistory).toEqual([]);
            expect(jobTracker.maxHistorySize).toBe(100);
            expect(jobTracker.eventHandlers).toBeInstanceOf(Map);
            expect(jobTracker.activeJobs.size).toBe(0);
            expect(jobTracker.completedJobs.size).toBe(0);
        });
        
        test('should bind methods correctly', () => {
            expect(typeof jobTracker.addJob).toBe('function');
            expect(typeof jobTracker.updateProgress).toBe('function');
            expect(typeof jobTracker.completeJob).toBe('function');
            expect(typeof jobTracker.failJob).toBe('function');
            expect(typeof jobTracker.removeJob).toBe('function');
        });
    });
    
    describe('Job Management', () => {
        describe('addJob', () => {
            test('should add a new job with default values', () => {
                const jobId = 'test-job-1';
                const job = jobTracker.addJob(jobId);
                
                expect(job).toEqual({
                    jobId,
                    status: 'pending',
                    progress: 0,
                    createdAt: expect.any(Date),
                    updatedAt: expect.any(Date)
                });
                
                expect(jobTracker.activeJobs.has(jobId)).toBe(true);
                expect(jobTracker.activeJobs.get(jobId)).toBe(job);
            });
            
            test('should add a new job with custom data', () => {
                const jobId = 'test-job-2';
                const jobData = {
                    title: 'Test Video',
                    type: 'video',
                    url: 'https://youtube.com/watch?v=test',
                    priority: 'high'
                };
                
                const job = jobTracker.addJob(jobId, jobData);
                
                expect(job).toEqual({
                    jobId,
                    status: 'pending',
                    progress: 0,
                    createdAt: expect.any(Date),
                    updatedAt: expect.any(Date),
                    ...jobData
                });
            });
            
            test('should trigger job_added event', () => {
                const eventHandler = jest.fn();
                jobTracker.addEventListener('job_added', eventHandler);
                
                const jobId = 'test-job-3';
                const job = jobTracker.addJob(jobId);
                
                expect(eventHandler).toHaveBeenCalledWith({
                    jobId,
                    job
                });
            });
            
            test('should trigger stats_updated event', () => {
                const statsHandler = jest.fn();
                jobTracker.addEventListener('stats_updated', statsHandler);
                
                jobTracker.addJob('test-job');
                
                expect(statsHandler).toHaveBeenCalledWith({
                    active: 1,
                    completed: 0,
                    failed: 0,
                    total: 1,
                    inProgress: 0,
                    pending: 1,
                    historySize: 0
                });
            });
        });
        
        describe('updateProgress', () => {
            beforeEach(() => {
                jobTracker.addJob('test-job', { title: 'Test Video' });
            });
            
            test('should update existing job progress', () => {
                const progressData = {
                    job_id: 'test-job',
                    progress: 50,
                    status: 'in_progress',
                    message: 'Processing video...',
                    step: 'transcription'
                };
                
                jobTracker.updateProgress(progressData);
                
                const job = jobTracker.getJob('test-job');
                expect(job.progress).toBe(50);
                expect(job.status).toBe('in_progress');
                expect(job.message).toBe('Processing video...');
                expect(job.step).toBe('transcription');
                expect(job.updatedAt).toEqual(expect.any(Date));
            });
            
            test('should create job if it does not exist (server-initiated)', () => {
                const progressData = {
                    job_id: 'new-server-job',
                    progress: 25,
                    status: 'in_progress',
                    video_title: 'Server Video',
                    video_url: 'https://youtube.com/watch?v=server'
                };
                
                jobTracker.updateProgress(progressData);
                
                const job = jobTracker.getJob('new-server-job');
                expect(job).toBeDefined();
                expect(job.title).toBe('Server Video');
                expect(job.url).toBe('https://youtube.com/watch?v=server');
                expect(job.progress).toBe(25);
                expect(job.status).toBe('in_progress');
            });
            
            test('should handle progress data without job_id', () => {
                const consoleWarnSpy = jest.spyOn(console, 'warn');
                const progressData = {
                    progress: 50,
                    status: 'in_progress'
                };
                
                jobTracker.updateProgress(progressData);
                
                expect(consoleWarnSpy).toHaveBeenCalledWith(
                    '⚠️ JobTracker: Progress update missing job_id:',
                    progressData
                );
            });
            
            test('should trigger job_progress event', () => {
                const progressHandler = jest.fn();
                jobTracker.addEventListener('job_progress', progressHandler);
                
                const progressData = {
                    job_id: 'test-job',
                    progress: 75
                };
                
                jobTracker.updateProgress(progressData);
                
                expect(progressHandler).toHaveBeenCalledWith({
                    jobId: 'test-job',
                    job: expect.any(Object),
                    progressData
                });
            });
            
            test('should preserve existing job data when updating', () => {
                const job = jobTracker.getJob('test-job');
                job.customField = 'custom value';
                
                jobTracker.updateProgress({
                    job_id: 'test-job',
                    progress: 30
                });
                
                const updatedJob = jobTracker.getJob('test-job');
                expect(updatedJob.customField).toBe('custom value');
                expect(updatedJob.progress).toBe(30);
            });
        });
        
        describe('completeJob', () => {
            beforeEach(() => {
                jobTracker.addJob('test-job', { title: 'Test Video' });
            });
            
            test('should complete a job successfully', () => {
                const completionData = {
                    summary: 'Video summary',
                    video_id: 'test123',
                    duration: 300
                };
                
                const job = jobTracker.completeJob('test-job', completionData);
                
                expect(job.status).toBe('completed');
                expect(job.progress).toBe(100);
                expect(job.completedAt).toEqual(expect.any(Date));
                expect(job.updatedAt).toEqual(expect.any(Date));
                expect(job.summary).toBe('Video summary');
                expect(job.video_id).toBe('test123');
                expect(job.duration).toBe(300);
                
                // Should be moved to completed jobs
                expect(jobTracker.activeJobs.has('test-job')).toBe(false);
                expect(jobTracker.completedJobs.has('test-job')).toBe(true);
            });
            
            test('should add completed job to history', () => {
                jobTracker.completeJob('test-job');
                
                expect(jobTracker.jobHistory).toHaveLength(1);
                expect(jobTracker.jobHistory[0]).toEqual(
                    expect.objectContaining({
                        jobId: 'test-job',
                        status: 'completed',
                        historyAddedAt: expect.any(Date)
                    })
                );
            });
            
            test('should handle completion of unknown job', () => {
                const consoleWarnSpy = jest.spyOn(console, 'warn');
                
                const result = jobTracker.completeJob('unknown-job');
                
                expect(result).toBeUndefined();
                expect(consoleWarnSpy).toHaveBeenCalledWith(
                    '⚠️ JobTracker: Cannot complete unknown job unknown-job'
                );
            });
            
            test('should trigger job_completed event', () => {
                const completedHandler = jest.fn();
                jobTracker.addEventListener('job_completed', completedHandler);
                
                const completionData = { result: 'success' };
                jobTracker.completeJob('test-job', completionData);
                
                expect(completedHandler).toHaveBeenCalledWith({
                    jobId: 'test-job',
                    job: expect.any(Object),
                    completionData
                });
            });
        });
        
        describe('failJob', () => {
            beforeEach(() => {
                jobTracker.addJob('test-job', { title: 'Test Video' });
            });
            
            test('should fail a job with error data', () => {
                const errorData = {
                    error: 'Network timeout',
                    errorCode: 'TIMEOUT',
                    retryable: true
                };
                
                const job = jobTracker.failJob('test-job', errorData);
                
                expect(job.status).toBe('failed');
                expect(job.failedAt).toEqual(expect.any(Date));
                expect(job.updatedAt).toEqual(expect.any(Date));
                expect(job.error).toBe('Network timeout');
                expect(job.errorCode).toBe('TIMEOUT');
                expect(job.retryable).toBe(true);
                
                // Should be moved to completed jobs (failed jobs are "completed")
                expect(jobTracker.activeJobs.has('test-job')).toBe(false);
                expect(jobTracker.completedJobs.has('test-job')).toBe(true);
            });
            
            test('should handle error data with message field', () => {
                const errorData = {
                    message: 'Video not found'
                };
                
                const job = jobTracker.failJob('test-job', errorData);
                expect(job.error).toBe('Video not found');
            });
            
            test('should use default error message for empty error data', () => {
                const job = jobTracker.failJob('test-job');
                expect(job.error).toBe('Unknown error');
            });
            
            test('should add failed job to history', () => {
                jobTracker.failJob('test-job', { error: 'Test error' });
                
                expect(jobTracker.jobHistory).toHaveLength(1);
                expect(jobTracker.jobHistory[0]).toEqual(
                    expect.objectContaining({
                        jobId: 'test-job',
                        status: 'failed',
                        error: 'Test error',
                        historyAddedAt: expect.any(Date)
                    })
                );
            });
            
            test('should trigger job_failed event', () => {
                const failedHandler = jest.fn();
                jobTracker.addEventListener('job_failed', failedHandler);
                
                const errorData = { error: 'Test failure' };
                jobTracker.failJob('test-job', errorData);
                
                expect(failedHandler).toHaveBeenCalledWith({
                    jobId: 'test-job',
                    job: expect.any(Object),
                    errorData
                });
            });
            
            test('should handle failure of unknown job', () => {
                const consoleWarnSpy = jest.spyOn(console, 'warn');
                
                const result = jobTracker.failJob('unknown-job');
                
                expect(result).toBeUndefined();
                expect(consoleWarnSpy).toHaveBeenCalledWith(
                    '⚠️ JobTracker: Cannot fail unknown job unknown-job'
                );
            });
        });
        
        describe('removeJob', () => {
            test('should remove active job', () => {
                jobTracker.addJob('active-job');
                
                const result = jobTracker.removeJob('active-job');
                
                expect(result).toBe(true);
                expect(jobTracker.activeJobs.has('active-job')).toBe(false);
            });
            
            test('should remove completed job', () => {
                jobTracker.addJob('completed-job');
                jobTracker.completeJob('completed-job');
                
                const result = jobTracker.removeJob('completed-job');
                
                expect(result).toBe(true);
                expect(jobTracker.completedJobs.has('completed-job')).toBe(false);
            });
            
            test('should return false for non-existent job', () => {
                const result = jobTracker.removeJob('non-existent');
                expect(result).toBe(false);
            });
            
            test('should trigger job_removed event', () => {
                const removedHandler = jest.fn();
                jobTracker.addEventListener('job_removed', removedHandler);
                
                jobTracker.addJob('test-job');
                jobTracker.removeJob('test-job');
                
                expect(removedHandler).toHaveBeenCalledWith({
                    jobId: 'test-job'
                });
            });
        });
    });
    
    describe('Job Querying', () => {
        beforeEach(() => {
            // Set up test jobs
            jobTracker.addJob('active-1', { title: 'Active 1', status: 'pending' });
            jobTracker.addJob('active-2', { title: 'Active 2', status: 'in_progress' });
            jobTracker.addJob('active-3', { title: 'Active 3', status: 'pending' });
            jobTracker.completeJob('active-1');
            jobTracker.failJob('active-2', { error: 'Test error' });
        });
        
        test('should get job by ID', () => {
            const job = jobTracker.getJob('active-3');
            expect(job).toBeDefined();
            expect(job.title).toBe('Active 3');
            
            const completedJob = jobTracker.getJob('active-1');
            expect(completedJob).toBeDefined();
            expect(completedJob.status).toBe('completed');
        });
        
        test('should return null for non-existent job', () => {
            const job = jobTracker.getJob('non-existent');
            expect(job).toBeNull();
        });
        
        test('should get all active jobs', () => {
            const activeJobs = jobTracker.getActiveJobs();
            expect(activeJobs).toHaveLength(1);
            expect(activeJobs[0].jobId).toBe('active-3');
        });
        
        test('should get all completed jobs', () => {
            const completedJobs = jobTracker.getCompletedJobs();
            expect(completedJobs).toHaveLength(2);
            
            const jobIds = completedJobs.map(job => job.jobId).sort();
            expect(jobIds).toEqual(['active-1', 'active-2']);
        });
        
        test('should get jobs by status', () => {
            const failedJobs = jobTracker.getJobsByStatus('failed');
            expect(failedJobs).toHaveLength(1);
            expect(failedJobs[0].jobId).toBe('active-2');
            
            const completedJobs = jobTracker.getJobsByStatus('completed');
            expect(completedJobs).toHaveLength(1);
            expect(completedJobs[0].jobId).toBe('active-1');
            
            const pendingJobs = jobTracker.getJobsByStatus('pending');
            expect(pendingJobs).toHaveLength(1);
            expect(pendingJobs[0].jobId).toBe('active-3');
        });
    });
    
    describe('Job Cleanup', () => {
        beforeEach(() => {
            // Set up test jobs
            for (let i = 1; i <= 5; i++) {
                jobTracker.addJob(`job-${i}`, { title: `Job ${i}` });
                if (i <= 3) {
                    jobTracker.completeJob(`job-${i}`);
                }
            }
        });
        
        test('should clear completed jobs', () => {
            const clearedHandler = jest.fn();
            jobTracker.addEventListener('jobs_cleared', clearedHandler);
            
            jobTracker.clearCompleted();
            
            expect(jobTracker.completedJobs.size).toBe(0);
            expect(jobTracker.activeJobs.size).toBe(2); // Should keep active jobs
            
            expect(clearedHandler).toHaveBeenCalledWith({
                count: 3,
                type: 'completed'
            });
        });
        
        test('should clear all jobs', () => {
            const clearedHandler = jest.fn();
            jobTracker.addEventListener('jobs_cleared', clearedHandler);
            
            jobTracker.clearAll();
            
            expect(jobTracker.activeJobs.size).toBe(0);
            expect(jobTracker.completedJobs.size).toBe(0);
            expect(jobTracker.jobHistory).toEqual([]);
            
            expect(clearedHandler).toHaveBeenCalledWith({
                count: 5,
                type: 'all',
                activeCount: 2,
                completedCount: 3
            });
        });
    });
    
    describe('Statistics', () => {
        beforeEach(() => {
            // Create diverse job set
            jobTracker.addJob('pending-1', { status: 'pending' });
            jobTracker.addJob('pending-2', { status: 'pending' });
            jobTracker.addJob('progress-1', { status: 'in_progress' });
            jobTracker.addJob('progress-2', { status: 'in_progress' });
            jobTracker.completeJob('pending-1');
            jobTracker.failJob('pending-2', { error: 'Test error' });
        });
        
        test('should calculate correct statistics', () => {
            const stats = jobTracker.getStats();
            
            expect(stats).toEqual({
                active: 2, // progress-1, progress-2
                completed: 1, // pending-1 (successfully completed)
                failed: 1, // pending-2 (failed)
                total: 4, // all jobs
                inProgress: 2, // progress-1, progress-2
                pending: 0, // none remaining pending
                historySize: 2 // pending-1, pending-2 added to history
            });
        });
        
        test('should trigger stats_updated event when jobs change', () => {
            const statsHandler = jest.fn();
            jobTracker.addEventListener('stats_updated', statsHandler);
            
            jobTracker.addJob('new-job');
            
            expect(statsHandler).toHaveBeenCalledWith(
                expect.objectContaining({
                    active: 3,
                    total: 5
                })
            );
        });
    });
    
    describe('Job History', () => {
        test('should maintain job history with correct order', () => {
            const jobs = [];
            for (let i = 1; i <= 5; i++) {
                jobTracker.addJob(`job-${i}`);
                jobs.push(`job-${i}`);
            }
            
            // Complete jobs in different order
            jobTracker.completeJob('job-3');
            jobTracker.completeJob('job-1');
            jobTracker.failJob('job-5', { error: 'Test' });
            
            const history = jobTracker.getHistory();
            expect(history).toHaveLength(3);
            
            // Should be in reverse chronological order (most recent first)
            expect(history[0].jobId).toBe('job-5');
            expect(history[1].jobId).toBe('job-1');
            expect(history[2].jobId).toBe('job-3');
        });
        
        test('should limit history size', () => {
            jobTracker.maxHistorySize = 3;
            
            // Complete more jobs than history limit
            for (let i = 1; i <= 5; i++) {
                jobTracker.addJob(`job-${i}`);
                jobTracker.completeJob(`job-${i}`);
            }
            
            const history = jobTracker.getHistory();
            expect(history).toHaveLength(3);
            
            // Should keep most recent
            expect(history[0].jobId).toBe('job-5');
            expect(history[1].jobId).toBe('job-4');
            expect(history[2].jobId).toBe('job-3');
        });
        
        test('should respect history limit parameter', () => {
            // Add many jobs to history
            for (let i = 1; i <= 10; i++) {
                jobTracker.addJob(`job-${i}`);
                jobTracker.completeJob(`job-${i}`);
            }
            
            const limitedHistory = jobTracker.getHistory(3);
            expect(limitedHistory).toHaveLength(3);
            
            const fullHistory = jobTracker.getHistory(20);
            expect(fullHistory).toHaveLength(10);
        });
        
        test('should add historyAddedAt timestamp', () => {
            jobTracker.addJob('test-job');
            jobTracker.completeJob('test-job');
            
            const history = jobTracker.getHistory();
            expect(history[0].historyAddedAt).toEqual(expect.any(Date));
        });
    });
    
    describe('Event System', () => {
        test('should add and trigger event handlers', () => {
            const handler = jest.fn();
            jobTracker.addEventListener('custom_event', handler);
            
            jobTracker.triggerHandler('custom_event', { test: 'data' });
            
            expect(handler).toHaveBeenCalledWith({ test: 'data' });
        });
        
        test('should support multiple handlers for same event', () => {
            const handler1 = jest.fn();
            const handler2 = jest.fn();
            
            jobTracker.addEventListener('test_event', handler1);
            jobTracker.addEventListener('test_event', handler2);
            
            jobTracker.triggerHandler('test_event', { data: 'test' });
            
            expect(handler1).toHaveBeenCalledWith({ data: 'test' });
            expect(handler2).toHaveBeenCalledWith({ data: 'test' });
        });
        
        test('should remove event handlers', () => {
            const handler = jest.fn();
            jobTracker.addEventListener('test_event', handler);
            jobTracker.removeEventListener('test_event', handler);
            
            jobTracker.triggerHandler('test_event', { data: 'test' });
            
            expect(handler).not.toHaveBeenCalled();
        });
        
        test('should handle errors in event handlers gracefully', () => {
            const errorHandler = jest.fn(() => {
                throw new Error('Handler error');
            });
            const workingHandler = jest.fn();
            
            jobTracker.addEventListener('test_event', errorHandler);
            jobTracker.addEventListener('test_event', workingHandler);
            
            expect(() => {
                jobTracker.triggerHandler('test_event', { data: 'test' });
            }).not.toThrow();
            
            expect(workingHandler).toHaveBeenCalledWith({ data: 'test' });
        });
    });
    
    describe('Data Import/Export', () => {
        beforeEach(() => {
            // Set up test data
            jobTracker.addJob('active-1', { title: 'Active Job' });
            jobTracker.addJob('completed-1', { title: 'Completed Job' });
            jobTracker.completeJob('completed-1');
        });
        
        test('should export job data correctly', () => {
            const exportData = jobTracker.exportData();
            
            expect(exportData).toEqual({
                activeJobs: [['active-1', expect.any(Object)]],
                completedJobs: [['completed-1', expect.any(Object)]],
                jobHistory: [expect.any(Object)],
                stats: expect.any(Object),
                timestamp: expect.any(String)
            });
            
            expect(exportData.stats.active).toBe(1);
            expect(exportData.stats.completed).toBe(1);
            expect(exportData.jobHistory).toHaveLength(1);
        });
        
        test('should import job data successfully', () => {
            const exportData = jobTracker.exportData();
            
            // Clear current data
            jobTracker.clearAll();
            expect(jobTracker.activeJobs.size).toBe(0);
            expect(jobTracker.completedJobs.size).toBe(0);
            
            // Import data
            jobTracker.importData(exportData);
            
            expect(jobTracker.activeJobs.size).toBe(1);
            expect(jobTracker.completedJobs.size).toBe(1);
            expect(jobTracker.jobHistory).toHaveLength(1);
            expect(jobTracker.getJob('active-1')).toBeDefined();
            expect(jobTracker.getJob('completed-1')).toBeDefined();
        });
        
        test('should handle partial import data', () => {
            const partialData = {
                activeJobs: [['imported-job', { jobId: 'imported-job', title: 'Imported' }]]
            };
            
            jobTracker.importData(partialData);
            
            expect(jobTracker.getJob('imported-job')).toBeDefined();
            expect(jobTracker.getJob('imported-job').title).toBe('Imported');
        });
        
        test('should handle import errors gracefully', () => {
            const consoleErrorSpy = jest.spyOn(console, 'error');
            const invalidData = {
                activeJobs: 'invalid data'
            };
            
            expect(() => {
                jobTracker.importData(invalidData);
            }).not.toThrow();
            
            expect(consoleErrorSpy).toHaveBeenCalledWith(
                '❌ JobTracker: Failed to import data:',
                expect.any(Error)
            );
        });
    });
    
    describe('Edge Cases and Error Handling', () => {
        test('should handle concurrent job operations', () => {
            const jobId = 'concurrent-job';
            
            // Simulate concurrent operations
            jobTracker.addJob(jobId);
            jobTracker.updateProgress({ job_id: jobId, progress: 50 });
            jobTracker.updateProgress({ job_id: jobId, progress: 75 });
            jobTracker.completeJob(jobId);
            
            const job = jobTracker.getJob(jobId);
            expect(job.status).toBe('completed');
            expect(job.progress).toBe(100);
        });
        
        test('should handle invalid progress data gracefully', () => {
            jobTracker.addJob('test-job');
            
            // Test with various invalid data
            jobTracker.updateProgress({ job_id: 'test-job', progress: null });
            jobTracker.updateProgress({ job_id: 'test-job', status: '' });
            jobTracker.updateProgress({ job_id: 'test-job', message: null });
            
            const job = jobTracker.getJob('test-job');
            expect(job).toBeDefined(); // Should not break
        });
        
        test('should handle job operations on non-string IDs', () => {
            const numericId = 123;
            const objectId = { id: 'object-id' };
            
            // Should work with non-string IDs
            jobTracker.addJob(numericId);
            jobTracker.addJob(objectId);
            
            expect(jobTracker.getJob(numericId)).toBeDefined();
            expect(jobTracker.getJob(objectId)).toBeDefined();
        });
        
        test('should maintain data consistency during rapid operations', () => {
            const jobIds = [];
            
            // Rapidly add many jobs
            for (let i = 0; i < 100; i++) {
                const jobId = `rapid-job-${i}`;
                jobIds.push(jobId);
                jobTracker.addJob(jobId);
            }
            
            // Randomly complete/fail some jobs
            for (let i = 0; i < 50; i++) {
                const jobId = jobIds[i];
                if (i % 2 === 0) {
                    jobTracker.completeJob(jobId);
                } else {
                    jobTracker.failJob(jobId, { error: 'Test error' });
                }
            }
            
            const stats = jobTracker.getStats();
            expect(stats.active).toBe(50);
            expect(stats.completed).toBe(25);
            expect(stats.failed).toBe(25);
            expect(stats.total).toBe(100);
            expect(stats.historySize).toBe(50);
        });
    });
    
    describe('Memory Management', () => {
        test('should properly clean up references when removing jobs', () => {
            const jobId = 'memory-test-job';
            jobTracker.addJob(jobId, { largeData: new Array(1000).fill('test') });
            
            expect(jobTracker.getJob(jobId)).toBeDefined();
            
            jobTracker.removeJob(jobId);
            
            expect(jobTracker.getJob(jobId)).toBeNull();
            expect(jobTracker.activeJobs.has(jobId)).toBe(false);
            expect(jobTracker.completedJobs.has(jobId)).toBe(false);
        });
        
        test('should handle history size limits correctly', () => {
            const originalHistorySize = jobTracker.maxHistorySize;
            jobTracker.maxHistorySize = 5;
            
            // Add more jobs than history limit
            for (let i = 1; i <= 10; i++) {
                jobTracker.addJob(`history-job-${i}`);
                jobTracker.completeJob(`history-job-${i}`);
            }
            
            expect(jobTracker.jobHistory.length).toBe(5);
            
            // Restore original history size
            jobTracker.maxHistorySize = originalHistorySize;
        });
    });
    
    describe('Performance', () => {
        test('should handle large numbers of jobs efficiently', () => {
            const startTime = performance.now();
            
            // Add 1000 jobs
            for (let i = 0; i < 1000; i++) {
                jobTracker.addJob(`perf-job-${i}`, { title: `Performance Job ${i}` });
            }
            
            const addTime = performance.now() - startTime;
            expect(addTime).toBeLessThan(100); // Should complete in <100ms
            
            // Query operations should also be fast
            const queryStart = performance.now();
            const allJobs = jobTracker.getActiveJobs();
            const queryTime = performance.now() - queryStart;
            
            expect(allJobs.length).toBe(1000);
            expect(queryTime).toBeLessThan(50); // Query should be <50ms
        });
        
        test('should efficiently manage event handlers', () => {
            const handlers = [];
            
            // Add many event handlers
            for (let i = 0; i < 100; i++) {
                const handler = jest.fn();
                handlers.push(handler);
                jobTracker.addEventListener('perf_test', handler);
            }
            
            const startTime = performance.now();
            jobTracker.triggerHandler('perf_test', { data: 'test' });
            const triggerTime = performance.now() - startTime;
            
            expect(triggerTime).toBeLessThan(50); // Should complete in <50ms
            handlers.forEach(handler => {
                expect(handler).toHaveBeenCalledWith({ data: 'test' });
            });
        });
    });
});