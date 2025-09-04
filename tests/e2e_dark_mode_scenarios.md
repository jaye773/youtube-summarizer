# End-to-End Dark Mode Test Scenarios

## Overview

This document outlines comprehensive end-to-end test scenarios for the YouTube Summarizer dark mode functionality. These scenarios cover complete user journeys from first visit to advanced usage patterns.

## Test Environment Setup

### Prerequisites
- Flask application running on `http://localhost:5000`
- Theme manager JavaScript module loaded
- CSS variables properly configured
- Playwright browser automation (recommended)

### Test Data Requirements
- Valid YouTube URLs for testing
- Sample playlists for batch processing
- Mock SSE events for real-time testing

## Scenario Categories

### 1. First-Time Visitor Scenarios

#### 1.1 System Preference Detection - Light Mode User
**Objective**: Verify first-time visitors see appropriate theme based on system preference

**Preconditions**:
- User has never visited the application
- System is set to light mode (`prefers-color-scheme: light`)
- No localStorage data exists

**Test Steps**:
1. Navigate to `http://localhost:5000`
2. Verify page loads with light theme applied
3. Check that `data-theme="light"` attribute is set on `<html>`
4. Verify CSS variables show light theme colors
5. Confirm no localStorage theme preference exists

**Expected Results**:
- Page displays in light theme immediately
- No flash of unstyled content (FOUC)
- System preference is correctly detected
- Theme manager initializes successfully

**Acceptance Criteria**:
- Load time < 3 seconds
- No JavaScript console errors
- Smooth visual experience
- Correct CSS variable values applied

#### 1.2 System Preference Detection - Dark Mode User
**Objective**: Verify first-time visitors see appropriate theme based on system preference

**Preconditions**:
- User has never visited the application
- System is set to dark mode (`prefers-color-scheme: dark`)
- No localStorage data exists

**Test Steps**:
1. Navigate to `http://localhost:5000`
2. Verify page loads with dark theme applied
3. Check that `data-theme="dark"` attribute is set on `<html>`
4. Verify CSS variables show dark theme colors
5. Confirm no localStorage theme preference exists

**Expected Results**:
- Page displays in dark theme immediately
- No flash of unstyled content (FOUC)
- System preference is correctly detected
- Theme manager initializes successfully

**Acceptance Criteria**:
- Load time < 3 seconds
- No JavaScript console errors
- Smooth visual experience
- Correct CSS variable values applied

#### 1.3 System Preference Unavailable Fallback
**Objective**: Verify graceful fallback when system preference cannot be detected

**Preconditions**:
- `matchMedia` API is unavailable or returns no preference
- No localStorage theme preference

**Test Steps**:
1. Mock `matchMedia` to return false or be undefined
2. Navigate to application
3. Verify fallback to light theme
4. Check application remains functional

**Expected Results**:
- Light theme applied as fallback
- No JavaScript errors
- All functionality works normally

### 2. Returning User Scenarios

#### 2.1 Returning User with Saved Light Preference
**Objective**: Verify saved theme preferences are correctly restored

**Preconditions**:
- localStorage contains `youtube-summarizer-theme: "light"`
- System preference may be different

**Test Steps**:
1. Navigate to application
2. Verify light theme is applied regardless of system preference
3. Check theme toggle reflects current state
4. Test theme persistence across page refresh

**Expected Results**:
- Light theme applied immediately
- Saved preference overrides system preference
- Theme persists across browser refresh

#### 2.2 Returning User with Saved Dark Preference
**Objective**: Verify saved theme preferences are correctly restored

**Preconditions**:
- localStorage contains `youtube-summarizer-theme: "dark"`
- System preference may be different

**Test Steps**:
1. Navigate to application
2. Verify dark theme is applied regardless of system preference
3. Check theme toggle reflects current state
4. Test theme persistence across page refresh

**Expected Results**:
- Dark theme applied immediately
- Saved preference overrides system preference
- Theme persists across browser refresh

#### 2.3 Returning User with Auto Preference
**Objective**: Verify auto theme mode follows system changes

**Preconditions**:
- localStorage contains `youtube-summarizer-theme: "auto"`

**Test Steps**:
1. Set system to light mode
2. Navigate to application - verify light theme
3. Change system to dark mode (simulate system change)
4. Verify theme updates to dark automatically
5. Check that preference remains "auto"

**Expected Results**:
- Theme follows system preference changes
- Auto mode preserved in localStorage
- Smooth transitions between themes

### 3. Theme Switching During Active Session

#### 3.1 Manual Theme Toggle - Light to Dark
**Objective**: Verify smooth theme switching during active use

**Test Steps**:
1. Load application in light theme
2. Locate theme toggle button/control
3. Click to switch to dark theme
4. Verify immediate visual update
5. Check localStorage is updated
6. Confirm all UI elements update correctly

**Expected Results**:
- Instant theme change < 100ms
- Smooth visual transition
- All UI elements themed correctly
- localStorage preference saved

**Visual Checkpoints**:
- Header/navigation theming
- Main content areas
- Buttons and form elements
- Progress bars and status indicators
- Toast notifications

#### 3.2 Manual Theme Toggle - Dark to Light
**Objective**: Verify smooth theme switching from dark theme

**Test Steps**:
1. Load application in dark theme
2. Click theme toggle
3. Verify switch to light theme
4. Check visual consistency
5. Verify localStorage update

**Expected Results**:
- Clean transition to light theme
- No visual artifacts
- All components properly themed

#### 3.3 Rapid Theme Switching Stress Test
**Objective**: Verify system stability under rapid theme changes

**Test Steps**:
1. Load application
2. Rapidly click theme toggle 10 times
3. Verify final state is consistent
4. Check for any visual glitches
5. Confirm localStorage reflects final state

**Expected Results**:
- System remains stable
- Final theme state is correct
- No memory leaks or errors
- Performance remains acceptable

### 4. Cross-Page Theme Consistency

#### 4.1 Navigation Between Pages
**Objective**: Verify theme consistency across different application pages

**Test Steps**:
1. Set dark theme on main page
2. Navigate to settings page (if available)
3. Verify dark theme is maintained
4. Navigate back to main page
5. Confirm theme consistency

**Expected Results**:
- Theme maintained across all pages
- No theme reset during navigation
- Consistent visual experience

#### 4.2 Form Submission Theme Persistence
**Objective**: Verify theme persists through form submissions

**Test Steps**:
1. Set dark theme
2. Submit YouTube URL for summarization
3. Verify theme maintained during processing
4. Check theme consistency on results page
5. Navigate back and verify theme

**Expected Results**:
- Theme never changes during form flow
- Processing states respect theme
- Results display in correct theme

### 5. Dynamic Content Theme Integration

#### 5.1 Real-Time Updates with SSE
**Objective**: Verify SSE updates respect current theme

**Test Steps**:
1. Set dark theme
2. Start a summarization job
3. Monitor real-time progress updates
4. Verify progress bars use dark theme colors
5. Check status messages are themed correctly

**Expected Results**:
- All dynamic content matches theme
- Progress indicators themed correctly
- Status messages readable in current theme

#### 5.2 Toast Notifications Theming
**Objective**: Verify toast notifications respect theme

**Test Steps**:
1. Set light theme
2. Trigger various toast notifications:
   - Success message
   - Error message  
   - Warning message
   - Info message
3. Switch to dark theme
4. Trigger same notifications
5. Verify appropriate theming

**Expected Results**:
- Toasts themed for current mode
- Proper contrast ratios maintained
- Icons and text clearly visible

#### 5.3 Dynamically Added Cards
**Objective**: Verify new content cards inherit theme

**Test Steps**:
1. Set dark theme
2. Add new video to batch processing
3. Verify new card appears in dark theme
4. Switch to light theme
5. Add another video
6. Confirm new card uses light theme

**Expected Results**:
- New cards inherit current theme
- No styling inconsistencies
- Smooth integration with existing content

### 6. Performance and Accessibility Scenarios

#### 6.1 Theme Switch Performance
**Objective**: Measure and verify theme switching performance

**Test Steps**:
1. Load application with performance monitoring
2. Record baseline performance metrics
3. Switch themes multiple times
4. Measure transition times
5. Monitor memory usage

**Performance Targets**:
- Theme switch < 100ms
- No memory leaks
- Smooth 60fps transitions
- CPU usage remains reasonable

#### 6.2 Keyboard Navigation with Themes
**Objective**: Verify keyboard accessibility across themes

**Test Steps**:
1. Load application in light theme
2. Navigate using only keyboard (Tab, Enter, Space)
3. Verify focus indicators are visible
4. Switch to dark theme using keyboard
5. Continue keyboard navigation
6. Verify focus remains visible in dark theme

**Expected Results**:
- Focus indicators visible in both themes
- Keyboard navigation fully functional
- No accessibility regressions

#### 6.3 Screen Reader Compatibility
**Objective**: Verify theme changes don't break screen reader functionality

**Test Steps**:
1. Enable screen reader (if available)
2. Navigate application with screen reader
3. Switch themes
4. Verify screen reader continues to work
5. Check for any accessibility announcements

**Expected Results**:
- Screen reader functionality unaffected
- No spurious announcements from theme changes
- Content remains accessible

### 7. Edge Cases and Error Scenarios

#### 7.1 LocalStorage Quota Exceeded
**Objective**: Test behavior when localStorage is full

**Test Steps**:
1. Fill localStorage to quota limit
2. Attempt to save theme preference
3. Verify graceful handling of storage failure
4. Check that application remains functional

**Expected Results**:
- Application continues to work
- Theme changes still work (in-memory)
- No JavaScript errors or crashes

#### 7.2 Corrupted Theme Data
**Objective**: Test handling of invalid localStorage data

**Test Steps**:
1. Set localStorage theme to invalid value: `"invalid-theme"`
2. Reload application
3. Verify fallback to system preference or default
4. Check that theme system recovers

**Expected Results**:
- Invalid data ignored
- Clean fallback to valid theme
- No JavaScript errors

#### 7.3 CSS Loading Failure
**Objective**: Test behavior when theme CSS fails to load

**Test Steps**:
1. Block theme CSS file from loading
2. Load application
3. Verify fallback styling works
4. Test theme switching with missing CSS

**Expected Results**:
- Basic styling still functional
- No JavaScript errors
- Graceful degradation

### 8. Browser Compatibility Scenarios

#### 8.1 Chrome/Chromium Testing
**Test Environment**: Latest Chrome/Chromium

**Test Steps**:
1. Run all core scenarios in Chrome
2. Test CSS Grid/Flexbox with themes
3. Verify CSS custom properties work
4. Test localStorage functionality

#### 8.2 Firefox Testing
**Test Environment**: Latest Firefox

**Test Steps**:
1. Run all core scenarios in Firefox
2. Test CSS variable inheritance
3. Verify matchMedia API works correctly
4. Test localStorage implementation

#### 8.3 Safari Testing (if available)
**Test Environment**: Latest Safari

**Test Steps**:
1. Run core scenarios in Safari
2. Test webkit-specific CSS properties
3. Verify event handling works correctly
4. Test mobile Safari if possible

#### 8.4 Mobile Browser Testing
**Test Environment**: Mobile browsers

**Test Steps**:
1. Test responsive design with themes
2. Verify touch interactions with theme toggle
3. Test viewport meta tag with theme colors
4. Verify mobile-specific CSS works

### 9. Integration with Existing Features

#### 9.1 YouTube Video Processing with Themes
**Objective**: Verify themes work with core YouTube functionality

**Test Steps**:
1. Set dark theme
2. Submit YouTube URL for processing
3. Verify all processing UI elements themed correctly:
   - Loading spinners
   - Progress bars
   - Status messages
   - Results display
4. Test with different video types

#### 9.2 Playlist Processing with Themes
**Objective**: Verify theme consistency during playlist processing

**Test Steps**:
1. Start playlist processing in light theme
2. Switch to dark theme during processing
3. Verify all active progress indicators update
4. Check completed items display correctly
5. Verify new items added respect current theme

#### 9.3 Audio Player with Themes
**Objective**: Test audio player controls with themes

**Test Steps**:
1. Generate summary with audio enabled
2. Test audio controls in light theme
3. Switch to dark theme
4. Verify audio controls remain functional and visible
5. Test volume controls and progress indicators

## Test Execution Guidelines

### Automated Testing
- Use Playwright for browser automation
- Run scenarios across multiple browsers
- Include performance measurements
- Generate detailed test reports

### Manual Testing Checklist
- [ ] Visual consistency check
- [ ] Contrast ratio verification
- [ ] Keyboard navigation test
- [ ] Touch interaction test (mobile)
- [ ] Screen reader compatibility
- [ ] Performance monitoring

### Continuous Integration
- Run core scenarios on every PR
- Run full suite on main branch
- Include browser compatibility matrix
- Monitor performance regressions

## Success Criteria

### Functional Requirements
- ✅ Theme detection works correctly
- ✅ Theme switching is smooth and fast
- ✅ Theme persistence works across sessions
- ✅ All UI components respect theme
- ✅ Dynamic content inherits theme

### Performance Requirements
- ✅ Theme switch < 100ms
- ✅ No FOUC (Flash of Unstyled Content)
- ✅ Memory usage stable
- ✅ No layout shifts

### Accessibility Requirements
- ✅ WCAG AA contrast ratios met
- ✅ Keyboard navigation works
- ✅ Focus indicators visible
- ✅ Screen reader compatible

### Browser Compatibility
- ✅ Chrome/Chromium: Full support
- ✅ Firefox: Full support  
- ✅ Safari: Core functionality
- ✅ Mobile browsers: Responsive design

## Troubleshooting Common Issues

### Theme Not Switching
1. Check for JavaScript errors in console
2. Verify theme-manager.js is loaded
3. Check CSS variables are defined
4. Ensure theme toggle button is connected

### FOUC (Flash of Unstyled Content)
1. Verify critical CSS is inlined or loads early
2. Check theme initialization timing
3. Ensure localStorage read happens early
4. Verify CSS variables have fallbacks

### LocalStorage Issues
1. Check browser privacy settings
2. Verify localStorage quota not exceeded
3. Test incognito/private browsing mode
4. Implement fallback for localStorage failures

### Performance Issues
1. Check for CSS animation conflicts
2. Monitor JavaScript execution time
3. Verify CSS variable performance
4. Test on slower devices/connections

## Reporting and Documentation

### Test Results Format
```json
{
  "scenario": "First-time visitor - system dark mode",
  "status": "PASS",
  "duration": "2.3s",
  "browser": "Chrome 91",
  "assertions": {
    "theme_applied": true,
    "no_fouc": true,
    "performance": "98ms",
    "accessibility": "AA compliant"
  }
}
```

### Issue Template
```markdown
## Issue Description
Brief description of the theme-related issue

## Steps to Reproduce
1. Step one
2. Step two
3. Step three

## Expected Behavior
What should happen

## Actual Behavior
What actually happens

## Environment
- Browser: Chrome 91
- OS: macOS 12
- Screen size: 1920x1080
- Theme: Dark mode

## Additional Context
Screenshots, console errors, etc.
```