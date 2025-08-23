/**
 * SSE Client Tests - Comprehensive testing for Server-Sent Events client
 * Module 4: Client-Side JavaScript Tests
 */

import { jest } from '@jest/globals';

// Import the SSE client code (we'll load it as text and evaluate)
import fs from 'fs';
import path from 'path';

const sseClientPath = path.resolve('./static/js/sse_client.js');
const sseClientCode = fs.readFileSync(sseClientPath, 'utf8');

// Remove the auto-initialization and window export for testing
const testableCode = sseClientCode
    .replace(/window\.SSEClient = SSEClient;/, '')
    .replace(/if \(typeof window !== 'undefined'.*?}/, '');

// Create a clean environment for each test
const createTestEnvironment = () => {
    const environment = {
        window: global,
        document: global.document,
        EventSource: global.EventSource,
        console: global.console,
        Date: global.Date,
        Math: global.Math,
        setTimeout: global.setTimeout,
        clearTimeout: global.clearTimeout,
        requestAnimationFrame: global.requestAnimationFrame
    };
    
    // Execute the code in the environment
    const func = new Function('window', 'document', 'EventSource', 'console', 'Date', 'Math', 'setTimeout', 'clearTimeout', 'requestAnimationFrame', 
        testableCode + '; return SSEClient;');
    
    return func(
        environment.window,
        environment.document,
        environment.EventSource,
        environment.console,
        environment.Date,
        environment.Math,
        environment.setTimeout,
        environment.clearTimeout,
        environment.requestAnimationFrame
    );
};

describe('SSEClient', () => {
    let SSEClientClass;
    let sseClient;
    let mockEventSource;
    
    beforeEach(() => {
        // Create a fresh class instance for each test
        SSEClientClass = createTestEnvironment();
        
        // Reset the DOM
        document.body.innerHTML = '';
        
        // Track EventSource instances
        const originalEventSource = global.EventSource;
        global.EventSource = jest.fn().mockImplementation(function(url, options) {
            mockEventSource = new originalEventSource(url, options);
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
            return mockEventSource;
        });
        
        sseClient = new SSEClientClass();
    });
    
    afterEach(() => {
        if (sseClient && typeof sseClient.disconnect === 'function') {
            sseClient.disconnect();
        }
        jest.clearAllMocks();
    });
    
    describe('Constructor and Initialization', () => {
        test('should create SSEClient with default configuration', () => {
            expect(sseClient).toBeDefined();
            expect(sseClient.endpoint).toBe('/events');
            expect(sseClient.reconnectDelay).toBe(1000);
            expect(sseClient.maxReconnectDelay).toBe(30000);
            expect(sseClient.maxReconnectAttempts).toBe(10);
            expect(sseClient.isConnected).toBe(false);
            expect(sseClient.isReconnecting).toBe(false);
            expect(sseClient.eventHandlers).toBeInstanceOf(Map);
            expect(sseClient.connectionId).toMatch(/^sse_\d+_[a-z0-9]+$/);
        });
        
        test('should create SSEClient with custom endpoint', () => {
            const customClient = new SSEClientClass('/custom-events');
            expect(customClient.endpoint).toBe('/custom-events');
        });
        
        test('should generate unique connection IDs', () => {
            const client1 = new SSEClientClass();
            const client2 = new SSEClientClass();
            expect(client1.connectionId).not.toBe(client2.connectionId);
            expect(client1.connectionId).toMatch(/^sse_\d+_[a-z0-9]+$/);
            expect(client2.connectionId).toMatch(/^sse_\d+_[a-z0-9]+$/);
        });
    });
    
    describe('Connection Management', () => {
        test('should connect and set up EventSource', async () => {
            sseClient.connect();
            
            expect(global.EventSource).toHaveBeenCalledWith('/events?client_id=' + sseClient.connectionId);
            expect(sseClient.eventSource).toBe(mockEventSource);
            expect(mockEventSource.addEventListener).toHaveBeenCalled();
        });
        
        test('should not create multiple connections when already connected', () => {
            sseClient.connect();
            mockEventSource.readyState = EventSource.OPEN;
            sseClient.isConnected = true;
            
            sseClient.connect();
            expect(global.EventSource).toHaveBeenCalledTimes(1);
        });
        
        test('should not connect when already reconnecting', () => {
            sseClient.isReconnecting = true;
            sseClient.connect();
            
            expect(global.EventSource).not.toHaveBeenCalled();
        });
        
        test('should handle connection open event', async () => {
            const connectionOpenHandler = jest.fn();
            sseClient.addEventListener('connection_open', connectionOpenHandler);
            
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            expect(sseClient.isConnected).toBe(true);
            expect(sseClient.isReconnecting).toBe(false);
            expect(sseClient.reconnectAttempts).toBe(0);
            expect(sseClient.reconnectDelay).toBe(1000);
            expect(connectionOpenHandler).toHaveBeenCalledWith({
                connectionId: sseClient.connectionId,
                timestamp: expect.any(Number)
            });
        });
        
        test('should create connection status indicator on open', () => {
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            const statusIndicator = document.getElementById('sse-connection-status');
            expect(statusIndicator).toBeTruthy();
            expect(statusIndicator.className).toContain('connected');
        });
    });
    
    describe('Disconnection and Cleanup', () => {
        test('should disconnect properly', () => {
            sseClient.connect();
            const disconnectHandler = jest.fn();
            sseClient.addEventListener('connection_closed', disconnectHandler);
            
            sseClient.disconnect();
            
            expect(sseClient.eventSource).toBeNull();
            expect(sseClient.isConnected).toBe(false);
            expect(sseClient.isReconnecting).toBe(false);
            expect(disconnectHandler).toHaveBeenCalledWith({
                timestamp: expect.any(Number)
            });
        });
        
        test('should clean up event listeners on disconnect', () => {
            sseClient.connect();
            const removeEventListenerSpy = jest.spyOn(mockEventSource, 'removeEventListener');
            
            sseClient.disconnect();
            
            expect(removeEventListenerSpy).toHaveBeenCalledWith('open', sseClient.handleOpen);
            expect(removeEventListenerSpy).toHaveBeenCalledWith('error', sseClient.handleError);
            expect(removeEventListenerSpy).toHaveBeenCalledWith('message', sseClient.handleMessage);
        });
        
        test('should update connection status on disconnect', () => {
            sseClient.connect();
            mockEventSource._simulateConnect();
            
            sseClient.disconnect();
            
            const statusIndicator = document.getElementById('sse-connection-status');
            expect(statusIndicator.className).toContain('disconnected');
        });
    });
    
    describe('Reconnection Logic with Exponential Backoff', () => {
        beforeEach(() => {
            jest.useFakeTimers();
        });
        
        afterEach(() => {
            jest.useRealTimers();
        });
        
        test('should handle connection error and initiate reconnection', () => {
            const reconnectingSpy = jest.fn();
            sseClient.addEventListener('reconnecting', reconnectingSpy);
            
            sseClient.connect();
            mockEventSource._simulateError();
            
            expect(sseClient.isConnected).toBe(false);
            expect(sseClient.reconnectAttempts).toBe(1);
            expect(sseClient.isReconnecting).toBe(true);
            expect(reconnectingSpy).toHaveBeenCalledWith({
                attempt: 1,
                delay: expect.any(Number),
                maxAttempts: 10
            });
        });
        
        test('should implement exponential backoff for reconnection', () => {
            sseClient.connect();
            
            // First reconnection attempt
            mockEventSource._simulateError();
            expect(sseClient.reconnectAttempts).toBe(1);
            
            // Advance timer for first reconnect
            jest.advanceTimersByTime(2000); // 1s * 2^(1-1) = 1s, but we use setTimeout with 2s
            
            // Second reconnection attempt (after first fails)
            if (mockEventSource) {
                mockEventSource._simulateError();
            }
            expect(sseClient.reconnectAttempts).toBe(2);
            
            // Third attempt should have longer delay
            jest.advanceTimersByTime(4000); // 1s * 2^(2-1) = 2s
            
            if (mockEventSource) {
                mockEventSource._simulateError();
            }
            expect(sseClient.reconnectAttempts).toBe(3);
        });
        
        test('should respect maximum reconnection attempts', () => {
            const connectionFailedSpy = jest.fn();
            sseClient.addEventListener('connection_failed', connectionFailedSpy);
            sseClient.maxReconnectAttempts = 3;
            
            sseClient.connect();
            
            // Simulate multiple failures
            for (let i = 0; i < 4; i++) {
                mockEventSource._simulateError();
                jest.advanceTimersByTime(5000);
            }
            
            expect(connectionFailedSpy).toHaveBeenCalledWith({
                attempts: 3,
                maxAttempts: 3
            });
        });
        
        test('should cap reconnection delay at maximum', () => {
            const reconnectingSpy = jest.fn();
            sseClient.addEventListener('reconnecting', reconnectingSpy);
            sseClient.maxReconnectDelay = 5000; // Set lower max for testing
            
            sseClient.connect();
            
            // Simulate many failures to trigger max delay
            sseClient.reconnectAttempts = 10; // High number to trigger max delay
            mockEventSource._simulateError();
            
            expect(reconnectingSpy).toHaveBeenCalledWith(
                expect.objectContaining({
                    delay: 5000 // Should be capped at maxReconnectDelay
                })
            );
        });
        
        test('should reset reconnection state on successful connection', () => {
            sseClient.connect();
            mockEventSource._simulateError();
            expect(sseClient.reconnectAttempts).toBe(1);
            
            // Simulate successful reconnection
            jest.advanceTimersByTime(2000);
            if (mockEventSource) {
                mockEventSource._simulateConnect();
            }
            
            expect(sseClient.isConnected).toBe(true);
            expect(sseClient.isReconnecting).toBe(false);
            expect(sseClient.reconnectAttempts).toBe(0);
            expect(sseClient.reconnectDelay).toBe(1000); // Reset to initial value
        });
    });
    
    describe('Event Handling', () => {
        test('should handle custom event handlers', () => {
            const customHandler = jest.fn();
            sseClient.addEventListener('custom_event', customHandler);
            
            sseClient.triggerHandler('custom_event', { test: 'data' });
            
            expect(customHandler).toHaveBeenCalledWith({ test: 'data' });
        });
        
        test('should handle multiple handlers for same event', () => {
            const handler1 = jest.fn();
            const handler2 = jest.fn();
            
            sseClient.addEventListener('test_event', handler1);
            sseClient.addEventListener('test_event', handler2);
            
            sseClient.triggerHandler('test_event', { data: 'test' });
            
            expect(handler1).toHaveBeenCalledWith({ data: 'test' });
            expect(handler2).toHaveBeenCalledWith({ data: 'test' });
        });
        
        test('should remove event handlers', () => {
            const handler = jest.fn();
            sseClient.addEventListener('test_event', handler);
            sseClient.removeEventListener('test_event', handler);
            
            sseClient.triggerHandler('test_event', { data: 'test' });
            
            expect(handler).not.toHaveBeenCalled();
        });
        
        test('should handle errors in event handlers gracefully', () => {
            const errorHandler = jest.fn(() => {
                throw new Error('Handler error');
            });
            const workingHandler = jest.fn();
            
            sseClient.addEventListener('test_event', errorHandler);
            sseClient.addEventListener('test_event', workingHandler);
            
            // Should not throw and should call working handler
            expect(() => {
                sseClient.triggerHandler('test_event', { data: 'test' });
            }).not.toThrow();
            
            expect(workingHandler).toHaveBeenCalled();
        });
    });
    
    describe('Message Processing', () => {
        beforeEach(() => {
            // Mock global dependencies
            global.window = global;
            global.window.JobTracker = {
                updateProgress: jest.fn(),
                completeJob: jest.fn()
            };
            global.window.UIUpdater = {
                addCompletedSummary: jest.fn()
            };
        });
        
        test('should handle summary_progress events', () => {
            const progressData = {
                job_id: 'test-job',
                progress: 50,
                message: 'Processing...'
            };
            
            const progressHandler = jest.fn();
            sseClient.addEventListener('summary_progress', progressHandler);
            sseClient.connect();
            
            mockEventSource._simulateMessage(progressData, 'summary_progress');
            
            expect(global.window.JobTracker.updateProgress).toHaveBeenCalledWith(progressData);
            expect(progressHandler).toHaveBeenCalledWith(progressData);
        });
        
        test('should handle summary_complete events', () => {
            const completionData = {
                job_id: 'test-job',
                summary: 'Test summary',
                video_id: 'test-video'
            };
            
            const completeHandler = jest.fn();
            sseClient.addEventListener('summary_complete', completeHandler);
            sseClient.connect();
            
            mockEventSource._simulateMessage(completionData, 'summary_complete');
            
            expect(global.window.UIUpdater.addCompletedSummary).toHaveBeenCalledWith(completionData);
            expect(global.window.JobTracker.completeJob).toHaveBeenCalledWith('test-job', completionData);
            expect(completeHandler).toHaveBeenCalledWith(completionData);
        });
        
        test('should handle system events', () => {
            const systemData = { type: 'notification', message: 'System update' };
            const systemHandler = jest.fn();
            
            sseClient.addEventListener('system', systemHandler);
            sseClient.connect();
            
            mockEventSource._simulateMessage(systemData, 'system');
            
            expect(systemHandler).toHaveBeenCalledWith(systemData);
        });
        
        test('should handle connected events', () => {
            const connectedData = { client_id: 'test-client', server_time: Date.now() };
            const connectedHandler = jest.fn();
            
            sseClient.addEventListener('connected', connectedHandler);
            sseClient.connect();
            
            mockEventSource._simulateMessage(connectedData, 'connected');
            
            expect(connectedHandler).toHaveBeenCalledWith(connectedData);
        });
        
        test('should handle ping events', () => {
            const pingHandler = jest.fn();
            sseClient.addEventListener('ping', pingHandler);
            sseClient.connect();
            
            mockEventSource._simulateMessage('', 'ping');
            
            expect(pingHandler).toHaveBeenCalledWith({ timestamp: expect.any(Number) });
        });
        
        test('should handle malformed JSON gracefully', () => {
            const errorSpy = jest.spyOn(console, 'error');
            sseClient.connect();
            
            // Simulate malformed JSON
            const event = new Event('summary_progress');
            event.data = '{ invalid json }';
            mockEventSource.dispatchEvent(event);
            
            expect(errorSpy).toHaveBeenCalledWith(
                expect.stringContaining('Error parsing progress event:'),
                expect.any(Error)
            );
        });
        
        test('should handle generic messages', () => {
            const messageHandler = jest.fn();
            sseClient.addEventListener('message', messageHandler);
            sseClient.connect();
            
            // Test JSON message
            mockEventSource._simulateMessage({ test: 'data' }, 'message');
            expect(messageHandler).toHaveBeenCalledWith({ test: 'data' });
            
            messageHandler.mockClear();
            
            // Test plain text message
            mockEventSource._simulateMessage('plain text', 'message');
            expect(messageHandler).toHaveBeenCalledWith('plain text');
        });
    });
    
    describe('Force Reconnection', () => {
        beforeEach(() => {
            jest.useFakeTimers();
        });
        
        afterEach(() => {
            jest.useRealTimers();
        });
        
        test('should force reconnection and reset attempts', () => {
            sseClient.reconnectAttempts = 5;
            sseClient.connect();
            
            sseClient.forceReconnect();
            
            expect(sseClient.reconnectAttempts).toBe(0);
            expect(sseClient.eventSource).toBeNull();
            
            // Should reconnect after timeout
            jest.advanceTimersByTime(100);
            expect(global.EventSource).toHaveBeenCalledTimes(2); // Initial + force reconnect
        });
    });
    
    describe('Connection State', () => {
        test('should provide accurate connection state', () => {
            const initialState = sseClient.getConnectionState();
            
            expect(initialState).toEqual({
                isConnected: false,
                isReconnecting: false,
                reconnectAttempts: 0,
                connectionId: sseClient.connectionId,
                readyState: undefined,
                endpoint: '/events'
            });
            
            sseClient.connect();
            const connectedState = sseClient.getConnectionState();
            
            expect(connectedState.readyState).toBe(EventSource.CONNECTING);
            expect(connectedState.endpoint).toBe('/events');
        });
    });
    
    describe('Browser Support Check', () => {
        test('should check EventSource support', () => {
            expect(SSEClientClass.isSupported()).toBe(true);
            
            const originalEventSource = global.EventSource;
            delete global.EventSource;
            
            expect(SSEClientClass.isSupported()).toBe(false);
            
            global.EventSource = originalEventSource;
        });
    });
    
    describe('Error Scenarios', () => {
        test('should handle EventSource creation failure', () => {
            global.EventSource = jest.fn(() => {
                throw new Error('EventSource creation failed');
            });
            
            sseClient.connect();
            
            // Should handle the error gracefully and attempt reconnection
            expect(sseClient.isConnected).toBe(false);
        });
        
        test('should handle missing global dependencies', () => {
            delete global.window.JobTracker;
            delete global.window.UIUpdater;
            
            sseClient.connect();
            
            // Should not crash when dependencies are missing
            expect(() => {
                mockEventSource._simulateMessage({ job_id: 'test' }, 'summary_progress');
            }).not.toThrow();
        });
        
        test('should handle DOM manipulation when elements are missing', () => {
            sseClient.connect();
            
            // Remove any existing status indicator
            const existingIndicator = document.getElementById('sse-connection-status');
            if (existingIndicator) {
                existingIndicator.remove();
            }
            
            // Should create new indicator without errors
            expect(() => {
                sseClient.updateConnectionStatus(true);
            }).not.toThrow();
            
            const newIndicator = document.getElementById('sse-connection-status');
            expect(newIndicator).toBeTruthy();
        });
    });
    
    describe('Memory Leak Prevention', () => {
        test('should clean up event listeners properly', () => {
            const handler = jest.fn();
            sseClient.addEventListener('test_event', handler);
            
            // Simulate multiple connections and disconnections
            for (let i = 0; i < 5; i++) {
                sseClient.connect();
                sseClient.disconnect();
            }
            
            // Handler should still be registered
            sseClient.triggerHandler('test_event', {});
            expect(handler).toHaveBeenCalledTimes(1);
        });
        
        test('should handle rapid connect/disconnect cycles', () => {
            for (let i = 0; i < 10; i++) {
                sseClient.connect();
                sseClient.disconnect();
            }
            
            // Should be in clean state
            expect(sseClient.eventSource).toBeNull();
            expect(sseClient.isConnected).toBe(false);
            expect(sseClient.isReconnecting).toBe(false);
        });
    });
    
    describe('Performance', () => {
        test('should handle high-frequency events efficiently', () => {
            const handler = jest.fn();
            sseClient.addEventListener('test_event', handler);
            
            const startTime = performance.now();
            
            // Simulate 1000 rapid events
            for (let i = 0; i < 1000; i++) {
                sseClient.triggerHandler('test_event', { index: i });
            }
            
            const endTime = performance.now();
            const duration = endTime - startTime;
            
            expect(handler).toHaveBeenCalledTimes(1000);
            expect(duration).toBeLessThan(100); // Should complete in <100ms
        });
        
        test('should efficiently manage event handler collections', () => {
            // Add many handlers
            const handlers = [];
            for (let i = 0; i < 100; i++) {
                const handler = jest.fn();
                handlers.push(handler);
                sseClient.addEventListener('test_event', handler);
            }
            
            // Remove half
            for (let i = 0; i < 50; i++) {
                sseClient.removeEventListener('test_event', handlers[i]);
            }
            
            // Trigger event
            sseClient.triggerHandler('test_event', {});
            
            // Check that only remaining handlers were called
            for (let i = 0; i < 50; i++) {
                expect(handlers[i]).not.toHaveBeenCalled();
            }
            for (let i = 50; i < 100; i++) {
                expect(handlers[i]).toHaveBeenCalledTimes(1);
            }
        });
    });
});