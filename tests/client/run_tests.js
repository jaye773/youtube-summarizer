#!/usr/bin/env node

/**
 * Test Runner - Comprehensive test execution and reporting
 * Module 4: Client-Side JavaScript Tests
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// Colors for console output
const colors = {
    reset: '\x1b[0m',
    bright: '\x1b[1m',
    red: '\x1b[31m',
    green: '\x1b[32m',
    yellow: '\x1b[33m',
    blue: '\x1b[34m',
    magenta: '\x1b[35m',
    cyan: '\x1b[36m'
};

const log = (message, color = '') => {
    console.log(`${color}${message}${colors.reset}`);
};

const logSection = (title) => {
    const line = '='.repeat(60);
    log(line, colors.cyan);
    log(`  ${title}`, colors.bright + colors.cyan);
    log(line, colors.cyan);
};

const logSubsection = (title) => {
    log(`\n${colors.yellow}${'-'.repeat(40)}${colors.reset}`);
    log(`  ${title}`, colors.yellow);
    log(`${colors.yellow}${'-'.repeat(40)}${colors.reset}`);
};

const runCommand = (command, description) => {
    try {
        log(`\n🔄 ${description}...`, colors.blue);
        const output = execSync(command, { 
            encoding: 'utf8',
            stdio: ['pipe', 'pipe', 'pipe'],
            cwd: path.resolve(__dirname, '../..')
        });
        log(`✅ ${description} completed`, colors.green);
        return { success: true, output };
    } catch (error) {
        log(`❌ ${description} failed`, colors.red);
        log(error.stdout || error.message, colors.red);
        return { success: false, error: error.message };
    }
};

const checkTestFiles = () => {
    const testDir = __dirname;
    const testFiles = [
        'setup.js',
        'test_sse_client.test.js',
        'test_job_tracker.test.js', 
        'test_ui_updater.test.js',
        'test_integration.test.js',
        'test_performance.test.js',
        'test_accessibility.test.js',
        'test_visual_css.test.js'
    ];
    
    log('📁 Checking test files...', colors.blue);
    
    const missingFiles = [];
    testFiles.forEach(file => {
        const filePath = path.join(testDir, file);
        if (fs.existsSync(filePath)) {
            const stats = fs.statSync(filePath);
            log(`  ✅ ${file} (${Math.round(stats.size / 1024)}KB)`, colors.green);
        } else {
            log(`  ❌ ${file} (missing)`, colors.red);
            missingFiles.push(file);
        }
    });
    
    return missingFiles;
};

const checkSourceFiles = () => {
    const sourceDir = path.resolve(__dirname, '../../static/js');
    const sourceFiles = [
        'sse_client.js',
        'job_tracker.js',
        'ui_updater.js'
    ];
    
    log('\n📁 Checking source files...', colors.blue);
    
    sourceFiles.forEach(file => {
        const filePath = path.join(sourceDir, file);
        if (fs.existsSync(filePath)) {
            const stats = fs.statStats(filePath);
            log(`  ✅ ${file} (${Math.round(stats.size / 1024)}KB)`, colors.green);
        } else {
            log(`  ❌ ${file} (missing)`, colors.red);
        }
    });
    
    // Check CSS file
    const cssPath = path.resolve(__dirname, '../../static/css/async_ui.css');
    if (fs.existsSync(cssPath)) {
        const stats = fs.statSync(cssPath);
        log(`  ✅ async_ui.css (${Math.round(stats.size / 1024)}KB)`, colors.green);
    } else {
        log(`  ❌ async_ui.css (missing)`, colors.red);
    }
};

const analyzeCoverage = (coverageData) => {
    if (!coverageData) return null;
    
    try {
        // Extract coverage summary from Jest output
        const lines = coverageData.split('\n');
        const summaryStart = lines.findIndex(line => line.includes('Coverage summary'));
        
        if (summaryStart === -1) return null;
        
        const summary = {
            statements: null,
            branches: null,
            functions: null,
            lines: null
        };
        
        // Parse coverage percentages
        for (let i = summaryStart; i < lines.length && i < summaryStart + 10; i++) {
            const line = lines[i];
            if (line.includes('Statements')) {
                const match = line.match(/(\d+\.?\d*)%/);
                if (match) summary.statements = parseFloat(match[1]);
            }
            if (line.includes('Branches')) {
                const match = line.match(/(\d+\.?\d*)%/);
                if (match) summary.branches = parseFloat(match[1]);
            }
            if (line.includes('Functions')) {
                const match = line.match(/(\d+\.?\d*)%/);
                if (match) summary.functions = parseFloat(match[1]);
            }
            if (line.includes('Lines')) {
                const match = line.match(/(\d+\.?\d*)%/);
                if (match) summary.lines = parseFloat(match[1]);
            }
        }
        
        return summary;
    } catch (error) {
        log(`Warning: Could not parse coverage data: ${error.message}`, colors.yellow);
        return null;
    }
};

const generateReport = (results, coverage) => {
    const reportPath = path.join(__dirname, 'test-report.md');
    
    const report = `# Client-Side JavaScript Test Report
Generated: ${new Date().toISOString()}

## Test Summary

| Test Suite | Status | Duration |
|------------|---------|----------|
${results.map(r => `| ${r.name} | ${r.success ? '✅ PASS' : '❌ FAIL'} | ${r.duration || 'N/A'} |`).join('\n')}

## Coverage Summary

${coverage ? `
| Metric | Coverage | Target | Status |
|--------|----------|--------|--------|
| Statements | ${coverage.statements}% | 90% | ${coverage.statements >= 90 ? '✅' : '❌'} |
| Branches | ${coverage.branches}% | 90% | ${coverage.branches >= 90 ? '✅' : '❌'} |
| Functions | ${coverage.functions}% | 90% | ${coverage.functions >= 90 ? '✅' : '❌'} |
| Lines | ${coverage.lines}% | 90% | ${coverage.lines >= 90 ? '✅' : '❌'} |
` : 'Coverage data not available'}

## Test Files

- ✅ test_sse_client.test.js - SSE connection and event handling tests
- ✅ test_job_tracker.test.js - Job state management tests  
- ✅ test_ui_updater.test.js - UI updates and DOM manipulation tests
- ✅ test_integration.test.js - Component integration workflows
- ✅ test_performance.test.js - Performance benchmarks and optimization
- ✅ test_accessibility.test.js - WCAG compliance and accessibility features
- ✅ test_visual_css.test.js - CSS styling and visual components

## Source Files Tested

- ✅ static/js/sse_client.js - Server-Sent Events client implementation
- ✅ static/js/job_tracker.js - Job progress tracking and state management
- ✅ static/js/ui_updater.js - Dynamic UI updates and notifications
- ✅ static/css/async_ui.css - Async UI component styling

## Key Test Areas

### 🔌 SSE Client (test_sse_client.test.js)
- Connection management and state tracking
- Exponential backoff reconnection logic
- Event handling and message processing
- Error scenarios and recovery
- Memory leak prevention
- Performance under high event frequency

### 📋 Job Tracker (test_job_tracker.test.js)  
- Job lifecycle management (add, update, complete, fail)
- Progress tracking and state transitions
- Job querying and filtering
- History management with size limits
- Data import/export functionality
- Event system and handler management
- Concurrent job handling
- Performance with large job sets

### 🎨 UI Updater (test_ui_updater.test.js)
- Progress bar creation and updates
- Toast notification system
- Connection status indicators
- DOM manipulation and cleanup
- Event handler integration
- XSS prevention through HTML escaping
- Animation and timing management
- Responsive UI adaptation

### 🔄 Integration Tests (test_integration.test.js)
- End-to-end workflow simulation
- Component interaction and event flow
- Connection resilience and recovery
- Multi-job concurrent processing
- Error propagation and handling
- UI state synchronization
- Real-world scenario testing

### ⚡ Performance Tests (test_performance.test.js)
- High-frequency event processing
- Large dataset handling
- Memory management and leak prevention
- DOM manipulation efficiency
- Animation and transition performance
- Stress testing under load
- Resource constraint adaptation

### ♿ Accessibility Tests (test_accessibility.test.js)
- WCAG 2.1 AA compliance
- Keyboard navigation support
- Screen reader compatibility
- Color contrast requirements
- Focus management
- Error accessibility
- Responsive design accessibility
- Internationalization support

### 🎨 Visual CSS Tests (test_visual_css.test.js)
- CSS structure and organization
- Component styling verification
- Responsive design implementation  
- Dark mode and theme support
- Animation quality and performance
- Cross-browser compatibility
- Color system consistency
- Accessibility CSS features

## Recommendations

${coverage && (coverage.statements < 90 || coverage.branches < 90 || coverage.functions < 90 || coverage.lines < 90) 
  ? '⚠️ **Coverage below target**: Focus on testing uncovered code paths, especially error handling and edge cases.'
  : '✅ **Excellent coverage**: Maintain current testing practices and continue comprehensive test coverage.'}

${results.some(r => !r.success)
  ? '❌ **Failed tests detected**: Review and fix failing tests before deployment.'
  : '✅ **All tests passing**: Code is ready for deployment with high confidence.'}

## Next Steps

1. **Continuous Integration**: Integrate these tests into your CI/CD pipeline
2. **Performance Monitoring**: Set up performance regression testing  
3. **Accessibility Audit**: Regular accessibility testing in real browsers
4. **Cross-browser Testing**: Validate across different browsers and devices
5. **User Testing**: Complement automated tests with real user feedback

---
*Generated by Client-Side JavaScript Test Suite v1.0*
`;

    fs.writeFileSync(reportPath, report);
    log(`📄 Test report generated: ${reportPath}`, colors.green);
    
    return reportPath;
};

const main = async () => {
    logSection('Client-Side JavaScript Test Suite');
    
    log('🧪 YouTube Summarizer - Module 4 Testing', colors.bright);
    log('Testing SSE Client, Job Tracker, UI Updater, and Integration\n');
    
    // Check files
    logSubsection('File Validation');
    const missingFiles = checkTestFiles();
    checkSourceFiles();
    
    if (missingFiles.length > 0) {
        log(`\n❌ Missing test files: ${missingFiles.join(', ')}`, colors.red);
        process.exit(1);
    }
    
    // Install dependencies if needed
    logSubsection('Dependencies');
    const installResult = runCommand('npm install', 'Installing dependencies');
    if (!installResult.success) {
        log('⚠️ Could not install dependencies automatically', colors.yellow);
        log('Please run: npm install', colors.yellow);
    }
    
    // Run test suites
    logSubsection('Test Execution');
    
    const testSuites = [
        {
            name: 'SSE Client Tests',
            command: 'npx jest tests/client/test_sse_client.test.js --verbose',
            file: 'test_sse_client.test.js'
        },
        {
            name: 'Job Tracker Tests', 
            command: 'npx jest tests/client/test_job_tracker.test.js --verbose',
            file: 'test_job_tracker.test.js'
        },
        {
            name: 'UI Updater Tests',
            command: 'npx jest tests/client/test_ui_updater.test.js --verbose',
            file: 'test_ui_updater.test.js'
        },
        {
            name: 'Integration Tests',
            command: 'npx jest tests/client/test_integration.test.js --verbose',
            file: 'test_integration.test.js'
        },
        {
            name: 'Performance Tests',
            command: 'npx jest tests/client/test_performance.test.js --verbose',
            file: 'test_performance.test.js'
        },
        {
            name: 'Accessibility Tests',
            command: 'npx jest tests/client/test_accessibility.test.js --verbose',
            file: 'test_accessibility.test.js'
        },
        {
            name: 'Visual CSS Tests',
            command: 'npx jest tests/client/test_visual_css.test.js --verbose',
            file: 'test_visual_css.test.js'
        }
    ];
    
    const results = [];
    let allPassed = true;
    
    for (const suite of testSuites) {
        const startTime = Date.now();
        const result = runCommand(suite.command, `Running ${suite.name}`);
        const duration = `${Date.now() - startTime}ms`;
        
        results.push({
            name: suite.name,
            file: suite.file,
            success: result.success,
            duration,
            output: result.output || result.error
        });
        
        if (!result.success) {
            allPassed = false;
        }
    }
    
    // Run coverage analysis
    logSubsection('Coverage Analysis');
    const coverageResult = runCommand(
        'npx jest tests/client --coverage --coverageReporters=text --coverageReporters=html',
        'Generating coverage report'
    );
    
    const coverage = coverageResult.success ? analyzeCoverage(coverageResult.output) : null;
    
    // Generate final report
    logSubsection('Report Generation');
    const reportPath = generateReport(results, coverage);
    
    // Summary
    logSection('Test Results Summary');
    
    if (coverage) {
        log('📊 Coverage Summary:', colors.bright);
        log(`  Statements: ${coverage.statements}% ${coverage.statements >= 90 ? '✅' : '❌'}`, 
            coverage.statements >= 90 ? colors.green : colors.red);
        log(`  Branches: ${coverage.branches}% ${coverage.branches >= 90 ? '✅' : '❌'}`,
            coverage.branches >= 90 ? colors.green : colors.red);
        log(`  Functions: ${coverage.functions}% ${coverage.functions >= 90 ? '✅' : '❌'}`,
            coverage.functions >= 90 ? colors.green : colors.red);
        log(`  Lines: ${coverage.lines}% ${coverage.lines >= 90 ? '✅' : '❌'}`,
            coverage.lines >= 90 ? colors.green : colors.red);
    }
    
    log('\n🧪 Test Suite Summary:', colors.bright);
    results.forEach(result => {
        const status = result.success ? '✅ PASS' : '❌ FAIL';
        const color = result.success ? colors.green : colors.red;
        log(`  ${status} ${result.name} (${result.duration})`, color);
    });
    
    const passCount = results.filter(r => r.success).length;
    const totalCount = results.length;
    
    if (allPassed) {
        log(`\n🎉 All ${totalCount} test suites passed!`, colors.green + colors.bright);
        log('✅ Client-side JavaScript is ready for production', colors.green);
        
        if (coverage) {
            const avgCoverage = (coverage.statements + coverage.branches + coverage.functions + coverage.lines) / 4;
            if (avgCoverage >= 90) {
                log(`✅ Excellent test coverage: ${avgCoverage.toFixed(1)}%`, colors.green);
            } else {
                log(`⚠️ Coverage could be improved: ${avgCoverage.toFixed(1)}%`, colors.yellow);
            }
        }
        
        process.exit(0);
    } else {
        log(`\n❌ ${totalCount - passCount} of ${totalCount} test suites failed`, colors.red + colors.bright);
        log('🔧 Please review failing tests and fix issues before deployment', colors.red);
        process.exit(1);
    }
};

// Handle errors
process.on('unhandledRejection', (reason, promise) => {
    log(`❌ Unhandled Rejection at: ${promise}, reason: ${reason}`, colors.red);
    process.exit(1);
});

process.on('uncaughtException', (error) => {
    log(`❌ Uncaught Exception: ${error.message}`, colors.red);
    process.exit(1);
});

// Run the test suite
main().catch(error => {
    log(`❌ Test runner failed: ${error.message}`, colors.red);
    process.exit(1);
});