// settings: moved verbatim from the inline <script> in templates/settings.html.
// Loaded as a classic script at the end of <body>, so top-level declarations
// are globals (inline onclick handlers rely on that).

function togglePassword(fieldId) {
    const field = document.getElementById(fieldId);
    const button = field.parentElement.querySelector('.toggle-btn');

    if (field.type === 'password') {
        field.type = 'text';
        // Show "eye with slash" icon when password is visible
        button.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
                <line x1="1" y1="1" x2="23" y2="23"></line>
            </svg>
        `;
    } else {
        field.type = 'password';
        // Show regular eye icon when password is hidden
        button.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                <circle cx="12" cy="12" r="3"></circle>
            </svg>
        `;
    }
}

function showMessage(text, type) {
    const messageDiv = document.getElementById('message');
    messageDiv.textContent = text;
    messageDiv.className = `message ${type}`;
    messageDiv.style.display = 'block';

    // Auto-hide success messages after 5 seconds
    if (type === 'success') {
        setTimeout(() => {
            messageDiv.style.display = 'none';
        }, 5000);
    }
}

function setLoading(loading) {
    const submitBtn = document.querySelector('.save-btn');
    const loadingSpan = submitBtn.querySelector('.loading');

    if (loading) {
        submitBtn.disabled = true;
        loadingSpan.style.display = 'inline';
    } else {
        submitBtn.disabled = false;
        loadingSpan.style.display = 'none';
    }
}

document.getElementById('settings-form').addEventListener('submit', async function(e) {
    e.preventDefault();

    setLoading(true);

    const formData = new FormData(this);
    const settings = {};

    // Convert form data to object
    for (let [key, value] of formData.entries()) {
        settings[key] = value;
    }

    // Handle checkboxes (they won't be in formData if unchecked)
    const checkboxes = ['login_enabled', 'webshare_proxy_enabled', 'flask_debug'];
    checkboxes.forEach(checkbox => {
        if (!settings[checkbox]) {
            settings[checkbox] = 'false';
        } else {
            settings[checkbox] = 'true';
        }
    });

    try {
        const response = await fetch('/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(settings)
        });

        const result = await response.json();

        if (response.ok) {
            showMessage(result.message || 'Settings saved successfully!', 'success');
        } else {
            showMessage(result.error || 'Failed to save settings', 'error');
        }
    } catch (error) {
        console.error('Error saving settings:', error);
        showMessage('Connection error. Please try again.', 'error');
    } finally {
        setLoading(false);
    }
});

// Voice Selection and Preview Functionality
let currentlyPlayingAudio = null;
let isTestingAllVoices = false;

// Voice selection function
function selectVoice(voiceId) {
    // Clear all selections
    document.querySelectorAll('.voice-option').forEach((option, index) => {
        option.classList.remove('selected');
        option.setAttribute('aria-checked', 'false');
        option.setAttribute('tabindex', '-1');
    });

    // Clear all radio buttons
    document.querySelectorAll('input[name="tts_voice"]').forEach(radio => {
        radio.checked = false;
    });

    // Select the clicked voice
    const selectedOption = document.querySelector(`input[value="${voiceId}"]`).closest('.voice-option');
    selectedOption.classList.add('selected');
    selectedOption.setAttribute('aria-checked', 'true');
    selectedOption.setAttribute('tabindex', '0');

    // Check the radio button
    document.querySelector(`input[value="${voiceId}"]`).checked = true;

    // Announce selection to screen readers
    const voiceName = selectedOption.querySelector('.voice-name').textContent;
    announceToScreenReader(`Selected voice: ${voiceName}`);
}

// Function to announce messages to screen readers
function announceToScreenReader(message) {
    const statusElement = document.getElementById('voice-status');
    if (statusElement) {
        statusElement.textContent = message;
        // Clear after announcement
        setTimeout(() => {
            statusElement.textContent = '';
        }, 1000);
    }
}

// Voice preview function
async function previewVoice(event, voiceId) {
    event.stopPropagation(); // Prevent the voice selection when clicking preview

    const button = event.target;
    const originalText = button.innerHTML;

    // Check if this button is currently playing - if so, stop it
    if (button.classList.contains('playing')) {
        if (currentlyPlayingAudio) {
            currentlyPlayingAudio.pause();
            currentlyPlayingAudio = null;
        }
        button.innerHTML = '▶️ Preview';
        button.classList.remove('playing');
        button.disabled = false;
        button.setAttribute('aria-label', `Preview ${voiceId} voice`);
        announceToScreenReader('Voice preview stopped');
        return;
    }

    // Stop any other currently playing audio
    if (currentlyPlayingAudio) {
        currentlyPlayingAudio.pause();
        currentlyPlayingAudio = null;
        // Reset all preview buttons
        document.querySelectorAll('.preview-btn').forEach(btn => {
            btn.classList.remove('playing');
            if (btn.innerHTML.includes('Stop')) {
                btn.innerHTML = '▶️ Preview';
            }
        });
    }

    try {
        // Set loading state
        button.innerHTML = '<span class="audio-loading"></span> Loading...';
        button.disabled = true;
        button.setAttribute('aria-label', 'Loading voice preview');
        announceToScreenReader('Loading voice preview');

        // Get sample text
        const sampleText = document.getElementById('sampleText').value || 
            'Welcome to the YouTube Summarizer! This is how your chosen voice will sound when reading video summaries.';

        // Make request to preview endpoint with timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 15000); // 15 second timeout

        const response = await fetch('/preview-voice', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                voice_id: voiceId,
                text: sampleText
            }),
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
            throw new Error(`Preview failed: ${response.status}`);
        }

        // Get the audio blob
        const audioBlob = await response.blob();
        const audioUrl = URL.createObjectURL(audioBlob);

        // Create and play audio
        const audio = new Audio(audioUrl);
        currentlyPlayingAudio = audio;

        // Set playing state
        button.innerHTML = '⏹️ Stop';
        button.classList.add('playing');
        button.disabled = false;
        button.setAttribute('aria-label', 'Stop voice preview');
        announceToScreenReader('Voice preview playing. Click to stop.');

        // Handle audio end
        audio.addEventListener('ended', () => {
            button.innerHTML = '▶️ Preview';
            button.classList.remove('playing');
            button.setAttribute('aria-label', `Preview ${voiceId} voice`);
            currentlyPlayingAudio = null;
            URL.revokeObjectURL(audioUrl);
            announceToScreenReader('Voice preview finished');
        });

        // Handle audio errors
        audio.addEventListener('error', () => {
            button.innerHTML = '▶️ Preview';
            button.classList.remove('playing');
            button.disabled = false;
            button.setAttribute('aria-label', `Preview ${voiceId} voice`);
            currentlyPlayingAudio = null;
            URL.revokeObjectURL(audioUrl);
            announceToScreenReader('Voice preview failed');
        });

        audio.play();

    } catch (error) {
        console.error('Voice preview error:', error);
        button.innerHTML = '▶️ Preview';
        button.disabled = false;
        button.classList.remove('playing');
        button.setAttribute('aria-label', `Preview ${voiceId} voice`);
        currentlyPlayingAudio = null;
        const errorMsg = 'Failed to preview voice. Please check your Google API key and internet connection, then try again.';
        showMessage(errorMsg, 'error');
        announceToScreenReader(errorMsg);
    }
}

// Test all voices function
async function testAllVoices() {
    if (isTestingAllVoices) {
        return; // Prevent multiple simultaneous tests
    }

    isTestingAllVoices = true;
    const testAllBtn = document.getElementById('testAllBtn');
    const testProgress = document.getElementById('testProgress');
    const testProgressBar = document.getElementById('testProgressBar');
    const originalText = testAllBtn.innerHTML;

    try {
        testAllBtn.innerHTML = '<span class="audio-loading"></span> Testing voices...';
        testAllBtn.disabled = true;
        testProgress.style.display = 'block';
        announceToScreenReader('Starting voice testing for all available voices');

        const voiceOptions = document.querySelectorAll('.voice-option');
        const sampleText = document.getElementById('sampleText').value || 
            'This is a sample of how this voice sounds.';

        for (let i = 0; i < voiceOptions.length; i++) {
            const option = voiceOptions[i];
            const voiceId = option.querySelector('input[name="tts_voice"]').value;
            const voiceName = option.querySelector('.voice-name').textContent;

            // Update progress
            const progress = ((i + 1) / voiceOptions.length) * 100;
            testProgressBar.style.width = `${progress}%`;
            testProgressBar.setAttribute('aria-valuenow', progress.toString());

            testAllBtn.innerHTML = `<span class="audio-loading"></span> Testing ${voiceName}... (${i + 1}/${voiceOptions.length})`;
            announceToScreenReader(`Testing voice ${i + 1} of ${voiceOptions.length}: ${voiceName}`);

            // Highlight current voice being tested
            option.style.transform = 'scale(1.02)';
            option.style.transition = 'transform 0.3s ease';

            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout for batch testing

                const response = await fetch('/preview-voice', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        voice_id: voiceId,
                        text: `${voiceName}: ${sampleText}`
                    }),
                    signal: controller.signal
                });

                clearTimeout(timeoutId);

                if (response.ok) {
                    const audioBlob = await response.blob();
                    const audioUrl = URL.createObjectURL(audioBlob);
                    const audio = new Audio(audioUrl);

                    // Play and wait for completion
                    await new Promise((resolve, reject) => {
                        audio.addEventListener('ended', resolve);
                        audio.addEventListener('error', reject);
                        audio.play().catch(reject);
                    });

                    URL.revokeObjectURL(audioUrl);
                }
            } catch (error) {
                console.warn(`Failed to test voice ${voiceId}:`, error);
            }

            // Reset highlight
            option.style.transform = '';

            // Brief pause between voices
            await new Promise(resolve => setTimeout(resolve, 500));
        }

        showMessage('Voice testing completed! Choose your preferred voice and save settings.', 'success');
        announceToScreenReader('Voice testing completed. All voices have been tested successfully.');

    } catch (error) {
        console.error('Test all voices error:', error);
        const errorMsg = 'Failed to test voices. Please check your Google API key and internet connection, then try again.';
        showMessage(errorMsg, 'error');
        announceToScreenReader(errorMsg);
    } finally {
        testAllBtn.innerHTML = originalText;
        testAllBtn.disabled = false;
        testProgress.style.display = 'none';
        testProgressBar.style.width = '0%';
        testProgressBar.setAttribute('aria-valuenow', '0');
        isTestingAllVoices = false;
    }
}

// Keyboard navigation support
document.addEventListener('DOMContentLoaded', function() {
    const voiceOptions = document.querySelectorAll('.voice-option[role="radio"]');

    voiceOptions.forEach((option, index) => {
        option.addEventListener('keydown', function(e) {
            switch(e.key) {
                case 'Enter':
                case ' ':
                    e.preventDefault();
                    const voiceId = option.querySelector('input[name="tts_voice"]').value;
                    selectVoice(voiceId);
                    break;
                case 'ArrowDown':
                case 'ArrowRight':
                    e.preventDefault();
                    const nextIndex = (index + 1) % voiceOptions.length;
                    voiceOptions[nextIndex].focus();
                    break;
                case 'ArrowUp':
                case 'ArrowLeft':
                    e.preventDefault();
                    const prevIndex = (index - 1 + voiceOptions.length) % voiceOptions.length;
                    voiceOptions[prevIndex].focus();
                    break;
            }
        });
    });

    // Set initial focus management
    const selectedVoice = document.querySelector('.voice-option.selected');
    if (selectedVoice) {
        selectedVoice.setAttribute('tabindex', '0');
        voiceOptions.forEach(option => {
            if (option !== selectedVoice) {
                option.setAttribute('tabindex', '-1');
            }
        });
    } else {
        // If no voice is selected, make the first one focusable
        voiceOptions[0]?.setAttribute('tabindex', '0');
        voiceOptions.forEach((option, index) => {
            if (index > 0) {
                option.setAttribute('tabindex', '-1');
            }
        });
    }
});

// Handle voice option click events
document.addEventListener('click', function(e) {
    if (e.target.closest('.voice-option') && !e.target.closest('.preview-btn')) {
        const option = e.target.closest('.voice-option');
        const voiceId = option.querySelector('input[name="tts_voice"]').value;
        selectVoice(voiceId);
    }
});
