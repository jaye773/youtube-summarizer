#!/usr/bin/env python3
"""
Performance Tests for Dark Mode Theme Switching

This module provides comprehensive performance testing for the YouTube Summarizer
theme switching system, validating transition speeds, memory usage, CPU impact,
and animation smoothness.

Author: YouTube Summarizer Team
Version: 1.0.0
"""

import pytest
import time
import statistics
import json
import os
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass
from contextlib import contextmanager

# Try to import playwright for browser testing
try:
    from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = Any
    Browser = Any
    BrowserContext = Any


@dataclass
class PerformanceMetrics:
    """Container for performance measurement results."""
    operation: str
    duration_ms: float
    memory_before_mb: Optional[float]
    memory_after_mb: Optional[float]
    memory_delta_mb: Optional[float]
    cpu_intensive: bool
    fps_during_transition: Optional[float]
    layout_shifts: int
    paint_time_ms: Optional[float]
    additional_data: Dict[str, Any]


class ThemePerformanceTester:
    """Performance testing utility for theme operations."""

    def __init__(self, page: Page):
        """Initialize with Playwright page.

        Args:
            page: Playwright page object for testing
        """
        self.page = page
        self.metrics_history: List[PerformanceMetrics] = []

    def measure_theme_switch_performance(self, from_theme: str, to_theme: str) -> PerformanceMetrics:
        """Measure performance of theme switching.

        Args:
            from_theme: Starting theme ('light' or 'dark')
            to_theme: Target theme ('light' or 'dark')

        Returns:
            Performance metrics for the theme switch
        """
        # Set initial theme
        self.page.evaluate(f'() => localStorage.setItem("youtube-summarizer-theme", "{from_theme}")')
        self.page.reload()
        self.page.wait_for_timeout(1000)

        # Get baseline memory
        memory_before = self._get_memory_usage()

        # Start performance monitoring
        self.page.evaluate("""
            () => {
                window.performanceData = {
                    startTime: performance.now(),
                    layoutShifts: 0,
                    paintTime: null,
                    frameCount: 0,
                    animationFrames: []
                };

                // Monitor layout shifts
                if ('LayoutShiftObserver' in window) {
                    new LayoutShiftObserver((entries) => {
                        for (let entry of entries) {
                            window.performanceData.layoutShifts += entry.value;
                        }
                    }).observe({ entryTypes: ['layout-shift'] });
                }

                // Monitor paint timing
                if ('PerformancePaintTiming' in window) {
                    const observer = new PerformanceObserver((list) => {
                        for (let entry of list.getEntries()) {
                            if (entry.name === 'first-contentful-paint') {
                                window.performanceData.paintTime = entry.startTime;
                            }
                        }
                    });
                    observer.observe({ entryTypes: ['paint'] });
                }

                // Monitor animation frames for FPS calculation
                function countFrame() {
                    window.performanceData.frameCount++;
                    window.performanceData.animationFrames.push(performance.now());
                    requestAnimationFrame(countFrame);
                }
                requestAnimationFrame(countFrame);
            }
        """)

        # Perform theme switch
        switch_start = time.time()

        # Method 1: Direct localStorage change + reload
        self.page.evaluate(f'() => localStorage.setItem("youtube-summarizer-theme", "{to_theme}")')
        self.page.reload()
        self.page.wait_for_timeout(100)  # Allow for theme application

        switch_duration = (time.time() - switch_start) * 1000  # Convert to ms

        # Get performance data
        perf_data = self.page.evaluate("""
            () => {
                const data = window.performanceData || {};
                const endTime = performance.now();

                // Calculate FPS during transition
                const frames = data.animationFrames || [];
                const recentFrames = frames.filter(frame => frame > (endTime - 1000)); // Last 1 second
                const fps = recentFrames.length;

                return {
                    totalTime: endTime - (data.startTime || endTime),
                    layoutShifts: data.layoutShifts || 0,
                    paintTime: data.paintTime,
                    fps: fps,
                    frameCount: data.frameCount || 0
                };
            }
        """)

        # Get final memory
        memory_after = self._get_memory_usage()
        memory_delta = memory_after - memory_before if memory_before and memory_after else None

        # Create metrics object
        metrics = PerformanceMetrics(
            operation=f"Theme switch: {from_theme} → {to_theme}",
            duration_ms=switch_duration,
            memory_before_mb=memory_before,
            memory_after_mb=memory_after,
            memory_delta_mb=memory_delta,
            cpu_intensive=switch_duration > 100,  # Consider >100ms as CPU intensive
            fps_during_transition=perf_data.get('fps'),
            layout_shifts=perf_data.get('layoutShifts', 0),
            paint_time_ms=perf_data.get('paintTime'),
            additional_data={
                'total_transition_time': perf_data.get('totalTime'),
                'frame_count': perf_data.get('frameCount')
            }
        )

        self.metrics_history.append(metrics)
        return metrics

    def measure_css_variable_update_performance(self) -> PerformanceMetrics:
        """Measure performance of CSS variable updates.

        Returns:
            Performance metrics for CSS variable updates
        """
        memory_before = self._get_memory_usage()

        # Measure CSS variable update time
        update_time = self.page.evaluate("""
            () => {
                const startTime = performance.now();
                const root = document.documentElement;

                // Update multiple CSS variables rapidly
                const variables = [
                    '--bg-primary', '--bg-secondary', '--bg-tertiary',
                    '--text-primary', '--text-secondary', '--text-muted',
                    '--border-default', '--border-subtle', '--border-strong',
                    '--accent-primary', '--accent-hover'
                ];

                const darkColors = [
                    '#1a1a1a', '#2d2d2d', '#404040',
                    '#ffffff', '#e0e0e0', '#a0a0a0',
                    '#555555', '#333333', '#777777',
                    '#4a9eff', '#3a8eef'
                ];

                // Update all variables
                variables.forEach((variable, index) => {
                    root.style.setProperty(variable, darkColors[index] || '#ffffff');
                });

                // Force style recalculation
                getComputedStyle(root).getPropertyValue('--bg-primary');

                return performance.now() - startTime;
            }
        """)

        memory_after = self._get_memory_usage()
        memory_delta = memory_after - memory_before if memory_before and memory_after else None

        metrics = PerformanceMetrics(
            operation="CSS Variable Updates",
            duration_ms=update_time,
            memory_before_mb=memory_before,
            memory_after_mb=memory_after,
            memory_delta_mb=memory_delta,
            cpu_intensive=update_time > 50,
            fps_during_transition=None,
            layout_shifts=0,
            paint_time_ms=None,
            additional_data={'variables_updated': 10}
        )

        self.metrics_history.append(metrics)
        return metrics

    def measure_dom_reflow_performance(self) -> PerformanceMetrics:
        """Measure performance impact of theme-related DOM reflows.

        Returns:
            Performance metrics for DOM reflow operations
        """
        memory_before = self._get_memory_usage()

        # Create elements and measure reflow time
        reflow_data = self.page.evaluate("""
            () => {
                const startTime = performance.now();

                // Create multiple elements that will cause reflows
                const elements = [];
                for (let i = 0; i < 100; i++) {
                    const div = document.createElement('div');
                    div.className = 'test-element card';
                    div.style.padding = '10px';
                    div.style.margin = '5px';
                    div.innerHTML = `<h4>Test Card ${i}</h4><p>Content for testing theme performance</p>`;
                    elements.push(div);
                    document.body.appendChild(div);
                }

                // Force reflow by reading computed styles
                let totalHeight = 0;
                elements.forEach(el => {
                    totalHeight += el.offsetHeight; // This triggers reflow
                });

                const afterElementsTime = performance.now();

                // Now switch theme class on document root (triggers massive reflow)
                document.documentElement.classList.remove('theme-light', 'theme-dark');
                document.documentElement.classList.add('theme-dark');

                // Force another reflow
                elements.forEach(el => {
                    totalHeight += el.offsetHeight;
                });

                const afterThemeTime = performance.now();

                // Clean up
                elements.forEach(el => el.remove());

                return {
                    elementCreationTime: afterElementsTime - startTime,
                    themeApplicationTime: afterThemeTime - afterElementsTime,
                    totalTime: afterThemeTime - startTime,
                    elementsCreated: 100,
                    totalHeight: totalHeight
                };
            }
        """)

        memory_after = self._get_memory_usage()
        memory_delta = memory_after - memory_before if memory_before and memory_after else None

        metrics = PerformanceMetrics(
            operation="DOM Reflow with Theme Change",
            duration_ms=reflow_data['totalTime'],
            memory_before_mb=memory_before,
            memory_after_mb=memory_after,
            memory_delta_mb=memory_delta,
            cpu_intensive=reflow_data['totalTime'] > 100,
            fps_during_transition=None,
            layout_shifts=0,  # Would need layout shift observer
            paint_time_ms=None,
            additional_data={
                'element_creation_time': reflow_data['elementCreationTime'],
                'theme_application_time': reflow_data['themeApplicationTime'],
                'elements_created': reflow_data['elementsCreated']
            }
        )

        self.metrics_history.append(metrics)
        return metrics

    def stress_test_rapid_theme_switching(self, iterations: int = 10) -> List[PerformanceMetrics]:
        """Perform stress test with rapid theme switching.

        Args:
            iterations: Number of theme switches to perform

        Returns:
            List of performance metrics for each switch
        """
        results = []

        for i in range(iterations):
            from_theme = 'light' if i % 2 == 0 else 'dark'
            to_theme = 'dark' if i % 2 == 0 else 'light'

            metrics = self.measure_theme_switch_performance(from_theme, to_theme)
            results.append(metrics)

            # Brief pause between switches
            time.sleep(0.1)

        return results

    def measure_animation_smoothness(self, animation_duration_ms: int = 300) -> PerformanceMetrics:
        """Measure smoothness of theme transition animations.

        Args:
            animation_duration_ms: Expected animation duration in milliseconds

        Returns:
            Performance metrics for animation smoothness
        """
        memory_before = self._get_memory_usage()

        # Set up animation monitoring
        animation_data = self.page.evaluate(f"""
            () => {{
                const startTime = performance.now();
                const frames = [];
                let animationActive = true;

                // Monitor frame rate during animation
                function recordFrame() {{
                    if (animationActive) {{
                        frames.push(performance.now());
                        requestAnimationFrame(recordFrame);
                    }}
                }}
                requestAnimationFrame(recordFrame);

                // Create animated element
                const testEl = document.createElement('div');
                testEl.style.cssText = `
                    position: fixed;
                    top: 50px;
                    left: 50px;
                    width: 100px;
                    height: 100px;
                    background-color: var(--bg-primary);
                    transition: background-color {animation_duration_ms}ms ease;
                    border: 2px solid var(--border-default);
                `;
                document.body.appendChild(testEl);

                // Trigger theme change to start animation
                const currentTheme = document.documentElement.getAttribute('data-theme');
                const newTheme = currentTheme === 'light' ? 'dark' : 'light';
                document.documentElement.classList.remove('theme-' + currentTheme);
                document.documentElement.classList.add('theme-' + newTheme);
                document.documentElement.setAttribute('data-theme', newTheme);

                // Stop monitoring after animation should be complete
                setTimeout(() => {{
                    animationActive = false;
                    testEl.remove();

                    // Calculate frame statistics
                    const totalTime = frames[frames.length - 1] - frames[0];
                    const frameCount = frames.length;
                    const avgFps = (frameCount / totalTime) * 1000;

                    // Calculate frame time consistency
                    const frameTimes = frames.slice(1).map((time, i) => time - frames[i]);
                    const avgFrameTime = frameTimes.reduce((sum, time) => sum + time, 0) / frameTimes.length;
                    const frameTimeVariance = frameTimes.reduce((sum, time) => sum + Math.pow(time - avgFrameTime, 2), 0) / frameTimes.length;

                    window.animationResults = {{
                        totalTime: totalTime,
                        frameCount: frameCount,
                        avgFps: avgFps,
                        avgFrameTime: avgFrameTime,
                        frameTimeVariance: frameTimeVariance,
                        droppedFrames: frameCount < (totalTime / 16.67) * 0.9 // Less than 90% of 60fps
                    }};
                }}, {animation_duration_ms + 100});

                return {{ startTime: startTime }};
            }}
        """)

        # Wait for animation to complete
        self.page.wait_for_timeout(animation_duration_ms + 200)

        # Get animation results
        results = self.page.evaluate('() => window.animationResults || {}')

        memory_after = self._get_memory_usage()
        memory_delta = memory_after - memory_before if memory_before and memory_after else None

        metrics = PerformanceMetrics(
            operation="Theme Transition Animation",
            duration_ms=results.get('totalTime', 0),
            memory_before_mb=memory_before,
            memory_after_mb=memory_after,
            memory_delta_mb=memory_delta,
            cpu_intensive=results.get('avgFps', 60) < 45,  # Below 45fps is CPU intensive
            fps_during_transition=results.get('avgFps'),
            layout_shifts=0,
            paint_time_ms=None,
            additional_data={
                'frame_count': results.get('frameCount', 0),
                'avg_frame_time': results.get('avgFrameTime', 0),
                'frame_time_variance': results.get('frameTimeVariance', 0),
                'dropped_frames': results.get('droppedFrames', False)
            }
        )

        self.metrics_history.append(metrics)
        return metrics

    def _get_memory_usage(self) -> Optional[float]:
        """Get current JavaScript heap memory usage.

        Returns:
            Memory usage in MB, or None if not available
        """
        try:
            memory_bytes = self.page.evaluate("""
                () => {
                    if (performance.memory) {
                        return performance.memory.usedJSHeapSize;
                    }
                    return null;
                }
            """)
            return memory_bytes / (1024 * 1024) if memory_bytes else None
        except:
            return None

    def get_performance_summary(self) -> Dict[str, Any]:
        """Generate performance summary from all collected metrics.

        Returns:
            Dictionary containing performance summary statistics
        """
        if not self.metrics_history:
            return {'status': 'NO_METRICS_COLLECTED'}

        durations = [m.duration_ms for m in self.metrics_history]
        memory_deltas = [m.memory_delta_mb for m in self.metrics_history if m.memory_delta_mb is not None]
        fps_values = [m.fps_during_transition for m in self.metrics_history if m.fps_during_transition is not None]

        return {
            'total_operations': len(self.metrics_history),
            'duration_stats': {
                'min_ms': min(durations),
                'max_ms': max(durations),
                'avg_ms': statistics.mean(durations),
                'median_ms': statistics.median(durations),
                'std_dev_ms': statistics.stdev(durations) if len(durations) > 1 else 0
            },
            'memory_stats': {
                'measurements': len(memory_deltas),
                'avg_delta_mb': statistics.mean(memory_deltas) if memory_deltas else None,
                'max_delta_mb': max(memory_deltas) if memory_deltas else None,
                'total_memory_growth_mb': sum(memory_deltas) if memory_deltas else None
            },
            'fps_stats': {
                'measurements': len(fps_values),
                'avg_fps': statistics.mean(fps_values) if fps_values else None,
                'min_fps': min(fps_values) if fps_values else None
            },
            'performance_issues': {
                'slow_operations': len([m for m in self.metrics_history if m.duration_ms > 100]),
                'cpu_intensive_operations': len([m for m in self.metrics_history if m.cpu_intensive]),
                'layout_shifts_detected': sum([m.layout_shifts for m in self.metrics_history]),
                'low_fps_operations': len([m for m in self.metrics_history
                                         if m.fps_during_transition and m.fps_during_transition < 45])
            }
        }


@pytest.fixture
def browser_page():
    """Create Playwright browser page for performance testing."""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        yield page

        browser.close()


@pytest.fixture
def perf_tester(browser_page):
    """Create theme performance tester."""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    return ThemePerformanceTester(browser_page)


class TestThemeSwitchingPerformance:
    """Test theme switching performance characteristics."""

    def test_light_to_dark_switch_performance(self, perf_tester):
        """Test performance of light to dark theme switching."""
        perf_tester.page.goto('http://localhost:5000')

        metrics = perf_tester.measure_theme_switch_performance('light', 'dark')

        # Theme switch should be fast (< 100ms is excellent, < 500ms acceptable)
        assert metrics.duration_ms < 500, \
            f"Light to dark switch too slow: {metrics.duration_ms:.2f}ms"

        # Should not cause significant memory growth
        if metrics.memory_delta_mb:
            assert metrics.memory_delta_mb < 10, \
                f"Excessive memory growth during theme switch: {metrics.memory_delta_mb:.2f}MB"

        # Should not cause layout shifts
        assert metrics.layout_shifts < 0.1, \
            f"Theme switch caused layout shifts: {metrics.layout_shifts}"

    def test_dark_to_light_switch_performance(self, perf_tester):
        """Test performance of dark to light theme switching."""
        perf_tester.page.goto('http://localhost:5000')

        metrics = perf_tester.measure_theme_switch_performance('dark', 'light')

        assert metrics.duration_ms < 500, \
            f"Dark to light switch too slow: {metrics.duration_ms:.2f}ms"

        if metrics.memory_delta_mb:
            assert metrics.memory_delta_mb < 10, \
                f"Excessive memory growth during theme switch: {metrics.memory_delta_mb:.2f}MB"

        assert metrics.layout_shifts < 0.1, \
            f"Theme switch caused layout shifts: {metrics.layout_shifts}"

    def test_css_variable_update_performance(self, perf_tester):
        """Test performance of CSS variable updates."""
        perf_tester.page.goto('http://localhost:5000')

        metrics = perf_tester.measure_css_variable_update_performance()

        # CSS variable updates should be very fast (< 50ms)
        assert metrics.duration_ms < 50, \
            f"CSS variable updates too slow: {metrics.duration_ms:.2f}ms"

        # Should not cause significant memory growth
        if metrics.memory_delta_mb:
            assert abs(metrics.memory_delta_mb) < 1, \
                f"CSS variable updates caused unexpected memory change: {metrics.memory_delta_mb:.2f}MB"

    def test_dom_reflow_performance(self, perf_tester):
        """Test performance impact of theme-related DOM reflows."""
        perf_tester.page.goto('http://localhost:5000')

        metrics = perf_tester.measure_dom_reflow_performance()

        # DOM reflow with many elements should complete reasonably quickly
        assert metrics.duration_ms < 1000, \
            f"DOM reflow with theme change too slow: {metrics.duration_ms:.2f}ms"

        # Theme application portion should be fast
        theme_time = metrics.additional_data.get('theme_application_time', 0)
        assert theme_time < 100, \
            f"Theme application during reflow too slow: {theme_time:.2f}ms"


class TestAnimationPerformance:
    """Test theme transition animation performance."""

    def test_transition_animation_smoothness(self, perf_tester):
        """Test smoothness of theme transition animations."""
        perf_tester.page.goto('http://localhost:5000')

        metrics = perf_tester.measure_animation_smoothness(300)

        # Animation should maintain good frame rate (>45 FPS)
        if metrics.fps_during_transition:
            assert metrics.fps_during_transition >= 45, \
                f"Animation frame rate too low: {metrics.fps_during_transition:.1f} FPS"

        # Should not drop significant frames
        dropped_frames = metrics.additional_data.get('dropped_frames', False)
        assert not dropped_frames, "Animation dropped significant frames"

        # Frame time variance should be low (consistent frame times)
        frame_variance = metrics.additional_data.get('frame_time_variance', 0)
        assert frame_variance < 100, \
            f"Frame time too inconsistent: {frame_variance:.2f}ms² variance"

    def test_multiple_element_animation_performance(self, perf_tester):
        """Test performance when many elements animate simultaneously."""
        perf_tester.page.goto('http://localhost:5000')

        # Create multiple animated elements
        perf_tester.page.evaluate("""
            () => {
                for (let i = 0; i < 50; i++) {
                    const el = document.createElement('div');
                    el.className = 'animated-element';
                    el.style.cssText = `
                        position: absolute;
                        top: ${Math.random() * 500}px;
                        left: ${Math.random() * 500}px;
                        width: 20px;
                        height: 20px;
                        background-color: var(--accent-primary);
                        transition: background-color 0.3s ease;
                    `;
                    document.body.appendChild(el);
                }
            }
        """)

        metrics = perf_tester.measure_animation_smoothness(300)

        # Should maintain reasonable performance even with many elements
        if metrics.fps_during_transition:
            assert metrics.fps_during_transition >= 30, \
                f"Multi-element animation too slow: {metrics.fps_during_transition:.1f} FPS"

        # Clean up
        perf_tester.page.evaluate("""
            () => {
                document.querySelectorAll('.animated-element').forEach(el => el.remove());
            }
        """)


class TestStressTestPerformance:
    """Test performance under stress conditions."""

    def test_rapid_theme_switching_performance(self, perf_tester):
        """Test performance under rapid theme switching."""
        perf_tester.page.goto('http://localhost:5000')

        metrics_list = perf_tester.stress_test_rapid_theme_switching(10)

        # All switches should complete reasonably quickly
        for metrics in metrics_list:
            assert metrics.duration_ms < 1000, \
                f"Rapid theme switch too slow: {metrics.duration_ms:.2f}ms"

        # Performance should not degrade significantly over time
        durations = [m.duration_ms for m in metrics_list]
        first_half_avg = statistics.mean(durations[:5])
        second_half_avg = statistics.mean(durations[5:])

        # Second half should not be more than 50% slower than first half
        assert second_half_avg <= first_half_avg * 1.5, \
            f"Performance degraded over time: {first_half_avg:.2f}ms → {second_half_avg:.2f}ms"

    def test_memory_stability_under_stress(self, perf_tester):
        """Test memory usage stability under repeated theme switches."""
        perf_tester.page.goto('http://localhost:5000')

        # Perform many theme switches
        metrics_list = perf_tester.stress_test_rapid_theme_switching(20)

        # Calculate total memory growth
        memory_deltas = [m.memory_delta_mb for m in metrics_list if m.memory_delta_mb is not None]

        if memory_deltas:
            total_memory_growth = sum(memory_deltas)

            # Total memory growth should be minimal (< 20MB after 20 switches)
            assert total_memory_growth < 20, \
                f"Excessive memory growth under stress: {total_memory_growth:.2f}MB"

            # Average memory growth per switch should be minimal
            avg_memory_per_switch = total_memory_growth / len(memory_deltas)
            assert avg_memory_per_switch < 1, \
                f"Average memory growth per switch too high: {avg_memory_per_switch:.2f}MB"

    def test_cpu_usage_during_theme_operations(self, perf_tester):
        """Test CPU usage characteristics during theme operations."""
        perf_tester.page.goto('http://localhost:5000')

        # Perform various theme operations
        metrics_list = []

        # Regular theme switches
        metrics_list.extend(perf_tester.stress_test_rapid_theme_switching(5))

        # CSS variable updates
        for _ in range(3):
            metrics_list.append(perf_tester.measure_css_variable_update_performance())

        # DOM reflow operations
        for _ in range(2):
            metrics_list.append(perf_tester.measure_dom_reflow_performance())

        # Check for CPU-intensive operations
        cpu_intensive_ops = [m for m in metrics_list if m.cpu_intensive]
        cpu_intensive_percentage = len(cpu_intensive_ops) / len(metrics_list) * 100

        # No more than 30% of operations should be CPU-intensive
        assert cpu_intensive_percentage <= 30, \
            f"Too many CPU-intensive operations: {cpu_intensive_percentage:.1f}%"


class TestRealWorldPerformance:
    """Test performance in realistic usage scenarios."""

    def test_theme_switch_with_content_loaded(self, perf_tester):
        """Test theme switching performance with realistic content."""
        perf_tester.page.goto('http://localhost:5000')

        # Add realistic content to the page
        perf_tester.page.evaluate("""
            () => {
                // Simulate loaded video cards
                const container = document.createElement('div');
                container.className = 'video-container';

                for (let i = 0; i < 10; i++) {
                    const card = document.createElement('div');
                    card.className = 'card video-card';
                    card.innerHTML = `
                        <div class="card-header">
                            <h3>Video Title ${i + 1}</h3>
                            <span class="duration">5:${String(i * 3 + 23).padStart(2, '0')}</span>
                        </div>
                        <div class="card-body">
                            <p>Video description with multiple lines of text that could be quite long...</p>
                            <div class="progress-bar">
                                <div class="progress-fill" style="width: ${Math.random() * 100}%;"></div>
                            </div>
                            <div class="video-meta">
                                <span class="views">1.${Math.floor(Math.random() * 9)}M views</span>
                                <span class="date">2 days ago</span>
                            </div>
                        </div>
                        <div class="card-footer">
                            <button class="btn-primary">Play Audio</button>
                            <button class="btn-secondary">Download</button>
                        </div>
                    `;
                    container.appendChild(card);
                }

                document.body.appendChild(container);
            }
        """)

        # Now test theme switching performance
        metrics = perf_tester.measure_theme_switch_performance('light', 'dark')

        # Performance should still be acceptable with content
        assert metrics.duration_ms < 750, \
            f"Theme switch with content too slow: {metrics.duration_ms:.2f}ms"

        assert metrics.layout_shifts < 0.2, \
            f"Theme switch with content caused layout shifts: {metrics.layout_shifts}"

    def test_theme_switch_during_active_sse(self, perf_tester):
        """Test theme switching while SSE events are being processed."""
        perf_tester.page.goto('http://localhost:5000')

        # Simulate active SSE processing
        perf_tester.page.evaluate("""
            () => {
                // Simulate incoming SSE events
                window.sseSimulation = setInterval(() => {
                    const event = new CustomEvent('sse-message', {
                        detail: {
                            type: 'progress',
                            data: {
                                job_id: 'test-job',
                                progress: Math.random() * 100,
                                status: 'Processing...'
                            }
                        }
                    });
                    document.dispatchEvent(event);

                    // Update UI elements
                    const progressBars = document.querySelectorAll('.progress-fill');
                    progressBars.forEach(bar => {
                        bar.style.width = Math.random() * 100 + '%';
                    });
                }, 100);
            }
        """)

        # Wait a bit for SSE simulation to start
        perf_tester.page.wait_for_timeout(200)

        # Test theme switching during active SSE
        metrics = perf_tester.measure_theme_switch_performance('dark', 'light')

        # Clean up SSE simulation
        perf_tester.page.evaluate('() => clearInterval(window.sseSimulation)')

        # Performance should not be severely impacted by SSE activity
        assert metrics.duration_ms < 1000, \
            f"Theme switch during SSE too slow: {metrics.duration_ms:.2f}ms"


def test_comprehensive_performance_suite(perf_tester):
    """Run comprehensive performance test suite and generate report."""

    # Run all performance tests
    basic_tests = TestThemeSwitchingPerformance()
    basic_tests.test_light_to_dark_switch_performance(perf_tester)
    basic_tests.test_dark_to_light_switch_performance(perf_tester)
    basic_tests.test_css_variable_update_performance(perf_tester)
    basic_tests.test_dom_reflow_performance(perf_tester)

    animation_tests = TestAnimationPerformance()
    animation_tests.test_transition_animation_smoothness(perf_tester)
    animation_tests.test_multiple_element_animation_performance(perf_tester)

    stress_tests = TestStressTestPerformance()
    stress_tests.test_rapid_theme_switching_performance(perf_tester)
    stress_tests.test_memory_stability_under_stress(perf_tester)
    stress_tests.test_cpu_usage_during_theme_operations(perf_tester)

    real_world_tests = TestRealWorldPerformance()
    real_world_tests.test_theme_switch_with_content_loaded(perf_tester)
    real_world_tests.test_theme_switch_during_active_sse(perf_tester)

    # Generate comprehensive report
    summary = perf_tester.get_performance_summary()

    # Save detailed performance report
    report_file = Path(__file__).parent / 'theme_performance_report.json'
    with open(report_file, 'w') as f:
        json.dump({
            'summary': summary,
            'detailed_metrics': [
                {
                    'operation': m.operation,
                    'duration_ms': m.duration_ms,
                    'memory_before_mb': m.memory_before_mb,
                    'memory_after_mb': m.memory_after_mb,
                    'memory_delta_mb': m.memory_delta_mb,
                    'cpu_intensive': m.cpu_intensive,
                    'fps_during_transition': m.fps_during_transition,
                    'layout_shifts': m.layout_shifts,
                    'paint_time_ms': m.paint_time_ms,
                    'additional_data': m.additional_data
                }
                for m in perf_tester.metrics_history
            ]
        }, f, indent=2)

    print(f"\nTheme Performance Report:")
    print(f"  Total Operations: {summary['total_operations']}")
    print(f"  Average Duration: {summary['duration_stats']['avg_ms']:.2f}ms")
    print(f"  Slowest Operation: {summary['duration_stats']['max_ms']:.2f}ms")

    if summary['memory_stats']['avg_delta_mb'] is not None:
        print(f"  Average Memory Growth: {summary['memory_stats']['avg_delta_mb']:.2f}MB")

    if summary['fps_stats']['avg_fps'] is not None:
        print(f"  Average FPS: {summary['fps_stats']['avg_fps']:.1f}")

    print(f"  Performance Issues:")
    print(f"    Slow Operations: {summary['performance_issues']['slow_operations']}")
    print(f"    CPU Intensive: {summary['performance_issues']['cpu_intensive_operations']}")
    print(f"    Layout Shifts: {summary['performance_issues']['layout_shifts_detected']}")
    print(f"  Detailed report saved to: {report_file}")

    # Assert overall performance is acceptable
    avg_duration = summary['duration_stats']['avg_ms']
    assert avg_duration < 200, f"Average operation duration too high: {avg_duration:.2f}ms"

    slow_ops_percentage = (summary['performance_issues']['slow_operations'] / summary['total_operations']) * 100
    assert slow_ops_percentage <= 20, f"Too many slow operations: {slow_ops_percentage:.1f}%"


if __name__ == '__main__':
    """Run performance tests when executed directly."""
    import subprocess
    import sys

    # Install browsers if Playwright is available
    if PLAYWRIGHT_AVAILABLE:
        try:
            subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'],
                         check=False, capture_output=True)
        except Exception:
            pass

    # Run the tests
    exit_code = pytest.main([
        __file__,
        '-v',
        '--tb=short',
        '-s',  # Don't capture output for progress visibility
    ])

    sys.exit(exit_code)
