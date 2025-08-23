/**
 * Jest Test Setup - Client-side JavaScript Testing Configuration
 * Module 4: Client-Side JavaScript Tests
 */

import '@testing-library/jest-dom';

// Mock EventSource globally for all tests
global.EventSource = class MockEventSource {
    constructor(url, options = {}) {
        this.url = url;
        this.options = options;
        this.readyState = EventSource.CONNECTING;
        this.listeners = new Map();
        
        // Simulate async connection
        setTimeout(() => {
            this.readyState = EventSource.OPEN;
            this.dispatchEvent(new Event('open'));
        }, 0);
    }
    
    addEventListener(type, listener) {
        if (!this.listeners.has(type)) {
            this.listeners.set(type, []);
        }
        this.listeners.get(type).push(listener);
    }
    
    removeEventListener(type, listener) {
        if (this.listeners.has(type)) {
            const listeners = this.listeners.get(type);
            const index = listeners.indexOf(listener);
            if (index > -1) {
                listeners.splice(index, 1);
            }
        }
    }
    
    dispatchEvent(event) {
        const eventType = event.type;
        if (this.listeners.has(eventType)) {
            this.listeners.get(eventType).forEach(listener => {
                try {
                    listener(event);
                } catch (error) {
                    console.error('EventSource listener error:', error);
                }
            });
        }
    }
    
    close() {
        this.readyState = EventSource.CLOSED;
        this.dispatchEvent(new Event('close'));
    }
    
    // Simulate sending a message event
    _simulateMessage(data, eventType = 'message') {
        const event = new Event(eventType);
        event.data = typeof data === 'string' ? data : JSON.stringify(data);
        this.dispatchEvent(event);
    }
    
    // Simulate error
    _simulateError() {
        this.readyState = EventSource.CLOSED;
        this.dispatchEvent(new Event('error'));
    }
};

// EventSource constants
EventSource.CONNECTING = 0;
EventSource.OPEN = 1;
EventSource.CLOSED = 2;

// Mock localStorage
const localStorageMock = {
    store: new Map(),
    
    getItem(key) {
        return this.store.get(key) || null;
    },
    
    setItem(key, value) {
        this.store.set(key, String(value));
    },
    
    removeItem(key) {
        this.store.delete(key);
    },
    
    clear() {
        this.store.clear();
    },
    
    get length() {
        return this.store.size;
    },
    
    key(index) {
        return Array.from(this.store.keys())[index] || null;
    }
};

Object.defineProperty(window, 'localStorage', {
    value: localStorageMock,
    writable: true
});

// Mock fetch API
global.fetch = jest.fn(() =>
    Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
        text: () => Promise.resolve(''),
        status: 200,
        statusText: 'OK'
    })
);

// Mock console methods to reduce test noise (but keep them available for debugging)
const originalLog = console.log;
const originalWarn = console.warn;
const originalError = console.error;

// Only suppress console output in production test environment
if (process.env.NODE_ENV === 'test') {
    console.log = jest.fn();
    console.warn = jest.fn();
    console.error = jest.fn();
}

// Restore console methods for debugging if needed
global.restoreConsole = () => {
    console.log = originalLog;
    console.warn = originalWarn;
    console.error = originalError;
};

// Mock requestAnimationFrame and cancelAnimationFrame
global.requestAnimationFrame = jest.fn((callback) => {
    return setTimeout(callback, 16); // ~60fps
});

global.cancelAnimationFrame = jest.fn((id) => {
    clearTimeout(id);
});

// Mock window.performance for performance testing
global.performance = {
    now: jest.fn(() => Date.now()),
    mark: jest.fn(),
    measure: jest.fn(),
    getEntriesByName: jest.fn(() => []),
    getEntriesByType: jest.fn(() => [])
};

// Common DOM testing utilities
global.createMockElement = (tagName, attributes = {}) => {
    const element = document.createElement(tagName);
    Object.assign(element, attributes);
    return element;
};

global.dispatchCustomEvent = (element, eventName, data = {}) => {
    const event = new CustomEvent(eventName, { detail: data });
    element.dispatchEvent(event);
};

// Test timeout configuration
jest.setTimeout(10000); // 10 seconds for integration tests

// Clean up after each test
afterEach(() => {
    // Reset localStorage
    localStorageMock.clear();
    
    // Clear all mocks
    jest.clearAllMocks();
    
    // Reset fetch mock
    fetch.mockClear();
    
    // Clean up DOM
    document.body.innerHTML = '';
    document.head.innerHTML = '';
    
    // Clear any global instances that might be created during tests
    if (window.SSEClient) {
        delete window.SSEClient;
    }
    if (window.JobTracker) {
        delete window.JobTracker;
    }
    if (window.UIUpdater) {
        delete window.UIUpdater;
    }
});

// Utility function to wait for async operations
global.waitFor = (conditionFn, timeout = 5000, interval = 50) => {
    return new Promise((resolve, reject) => {
        const startTime = Date.now();
        
        const checkCondition = () => {
            if (conditionFn()) {
                resolve();
            } else if (Date.now() - startTime > timeout) {
                reject(new Error(`Timeout waiting for condition after ${timeout}ms`));
            } else {
                setTimeout(checkCondition, interval);
            }
        };
        
        checkCondition();
    });
};

// Utility to simulate network delays
global.delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));

console.log('🧪 Jest Setup: Client-side testing environment configured');