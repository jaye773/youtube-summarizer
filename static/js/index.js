// index: moved verbatim from the inline <script> in templates/index.html.
// Loaded as a classic script at the end of <body>, so top-level declarations
// are globals (inline onclick handlers rely on that).

// Escape text before interpolating into innerHTML to prevent XSS from
// user input, YouTube-supplied titles, and server error strings.
function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
}

const summarizeBtn = document.getElementById('summarize-btn');
const linksTextarea = document.getElementById('youtube-links');
const loader = document.getElementById('loader');

// Search elements
const searchInput = document.getElementById('search-input');
const searchBtn = document.getElementById('search-btn');
const clearSearchBtn = document.getElementById('clear-search-btn');
const searchResults = document.getElementById('search-results');

// Pagination elements
const paginationSection = document.getElementById('pagination-section');
const paginationInfoText = document.getElementById('pagination-info-text');
const pageSizeSelect = document.getElementById('page-size-select');
const prevPageBtn = document.getElementById('prev-page-btn');
const nextPageBtn = document.getElementById('next-page-btn');
const currentPageSpan = document.getElementById('current-page');
const totalPagesSpan = document.getElementById('total-pages');

// Pagination state
let currentPage = 1;
let currentPageSize = 10;
let totalSummaries = 0;
let totalPages = 0;

// --- SSE REAL-TIME NOTIFICATIONS ---
let eventSource = null;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;
const reconnectDelay = 1000; // Start with 1 second

function initializeSSE() {
    if (eventSource) {
        eventSource.close();
    }

    // Subscribe to summary completion and progress events
    const subscriptions = 'summary_complete,summary_progress,summary_result,summary_done,system';
    eventSource = new EventSource(`/events?subscribe=${subscriptions}`);

    eventSource.onopen = function(event) {
        console.log('SSE connection opened');
        reconnectAttempts = 0;
        showNotification('Connected to real-time updates', 'success');
    };

    eventSource.onmessage = function(event) {
        console.log('SSE message received:', event.data);
    };

    eventSource.addEventListener('connected', function(event) {
        const data = JSON.parse(event.data);
        console.log('SSE connection established:', data);
        updateConnectionStatus(true);
    });

    eventSource.addEventListener('summary_progress', function(event) {
        const data = JSON.parse(event.data);
        updateProgressIndicator(data);
    });

    eventSource.addEventListener('summary_complete', function(event) {
        const data = JSON.parse(event.data);
        handleSummaryComplete(data);
        showNotification(`Summary completed: ${data.title}`, 'success');
    });

    eventSource.addEventListener('summary_result', function(event) {
        handleSummaryResultEvent(JSON.parse(event.data));
    });

    eventSource.addEventListener('summary_done', function(event) {
        handleSummaryDoneEvent(JSON.parse(event.data));
    });

    eventSource.addEventListener('system', function(event) {
        const data = JSON.parse(event.data);
        showNotification(data.message || 'System notification', 'info');
    });

    eventSource.addEventListener('ping', function(event) {
        // Keep-alive ping, no action needed
        console.log('SSE keep-alive ping received');
    });

    eventSource.onerror = function(event) {
        console.error('SSE error:', event);
        updateConnectionStatus(false);

        if (eventSource.readyState === EventSource.CLOSED) {
            console.log('SSE connection closed, attempting to reconnect...');
            handleSSEReconnect();
        } else if (eventSource.readyState === EventSource.CONNECTING) {
            console.log('SSE reconnecting...');
        }
    };
}

function handleSSEReconnect() {
    if (reconnectAttempts >= maxReconnectAttempts) {
        console.log('Max reconnection attempts reached');
        showNotification('Real-time updates disconnected. Please refresh the page.', 'error');
        return;
    }

    reconnectAttempts++;
    const delay = Math.min(reconnectDelay * Math.pow(2, reconnectAttempts - 1), 30000);

    console.log(`Attempting to reconnect SSE (attempt ${reconnectAttempts}/${maxReconnectAttempts}) in ${delay}ms`);
    showNotification(`Reconnecting to real-time updates... (${reconnectAttempts}/${maxReconnectAttempts})`, 'warning');

    setTimeout(() => {
        initializeSSE();
    }, delay);
}

function updateConnectionStatus(connected) {
    // Use the existing connection status in async-status-container instead of creating new ones
    const connectionStatus = document.getElementById('connection-status');
    const statusDot = connectionStatus?.querySelector('.connection-status-dot');
    const statusText = connectionStatus?.querySelector('.status-text');

    if (connectionStatus && statusDot && statusText) {
        // Update container classes
        connectionStatus.className = connected ? 'async-connection-status connected' : 'async-connection-status disconnected';
        // Update dot classes  
        statusDot.className = connected ? 'connection-status-dot connected' : 'connection-status-dot disconnected';
        // Update text
        statusText.textContent = connected ? 'Connected' : 'Disconnected';
        // Update title
        connectionStatus.title = connected ? 'Real-time updates connected' : 'Real-time updates disconnected';
    }
}

function updateProgressIndicator(progressData) {
    let progressBar = document.getElementById('real-time-progress');

    if (!progressBar && progressData.status !== 'completed') {
        progressBar = createProgressBar();
    }

    if (!progressBar) return;

    const { status, message, progress, total, current_video, current_playlist } = progressData;

    if (status === 'completed') {
        // Hide progress bar after completion
        setTimeout(() => {
            if (progressBar && progressBar.parentNode) {
                progressBar.parentNode.removeChild(progressBar);
            }
        }, 3000);
        return;
    }

    // Update progress bar
    const progressBarFill = progressBar.querySelector('.real-time-progress-fill');
    const progressText = progressBar.querySelector('.real-time-progress-text');
    const progressDetails = progressBar.querySelector('.real-time-progress-details');

    if (total && total > 0) {
        const percentage = Math.min((progress / total) * 100, 100);
        progressBarFill.style.width = `${percentage}%`;
        progressText.textContent = `${progress}/${total} - ${message}`;
    } else {
        progressBarFill.style.width = '100%';
        progressBarFill.style.animationDuration = '2s';
        progressText.textContent = message;
    }

    // Update details
    if (current_video) {
        let details = `Processing: ${current_video.title}`;
        if (current_playlist) {
            details += ` (from ${current_playlist})`;
        }
        progressDetails.textContent = details;
    } else {
        progressDetails.textContent = '';
    }
}

function createProgressBar() {
    const progressContainer = document.createElement('div');
    progressContainer.id = 'real-time-progress';
    progressContainer.className = 'real-time-progress-container';
    progressContainer.innerHTML = `
        <div class="real-time-progress-bar">
            <div class="real-time-progress-fill"></div>
        </div>
        <div class="real-time-progress-text">Preparing...</div>
        <div class="real-time-progress-details"></div>
    `;

    const container = document.querySelector('.container');
    const summarizeControls = document.querySelector('.summarize-controls');
    container.insertBefore(progressContainer, summarizeControls.nextSibling);

    return progressContainer;
}

function handleSummaryComplete(data) {
    // Optionally refresh cached summaries or update UI
    console.log('Summary completed:', data);

    // If we're currently on the first page, refresh to show new summaries
    if (currentPage === 1) {
        setTimeout(() => {
            loadPaginatedSummaries(currentPage, currentPageSize);
        }, 1000);
    }
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;

    // Style the notification
    Object.assign(notification.style, {
        position: 'fixed',
        top: '20px',
        right: '20px',
        padding: '12px 20px',
        borderRadius: '6px',
        color: 'white',
        fontWeight: 'bold',
        zIndex: '10000',
        minWidth: '200px',
        maxWidth: '400px',
        wordWrap: 'break-word',
        opacity: '0',
        transition: 'opacity 0.3s ease-in-out'
    });

    // Set background color based on type
    const colors = {
        success: '#27ae60',
        error: '#e74c3c',
        warning: '#f39c12',
        info: '#3498db'
    };
    notification.style.backgroundColor = colors[type] || colors.info;

    document.body.appendChild(notification);

    // Fade in
    setTimeout(() => {
        notification.style.opacity = '1';
    }, 10);

    // Auto remove after 5 seconds
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 5000);
}

// Close SSE connection when page unloads
window.addEventListener('beforeunload', function() {
    if (eventSource) {
        eventSource.close();
    }
});

// --- UPDATED State Object ---
let currentAudioPlayer = {
    player: new Audio(),
    button: null,
    text: null,
    state: 'stopped',
    // References to the active progress bar elements
    progressContainer: null,
    progressFill: null,
    currentTimeEl: null,
    totalTimeEl: null
};

const player = currentAudioPlayer.player;

// --- NEW Event Listeners for Progress Bar ---
player.addEventListener('timeupdate', () => {
    if (!currentAudioPlayer.progressContainer || player.duration === 0) return;
    // Update the fill width
    const progressPercent = (player.currentTime / player.duration) * 100;
    currentAudioPlayer.progressFill.style.width = `${progressPercent}%`;
    // Update the current time display
    currentAudioPlayer.currentTimeEl.textContent = formatTime(player.currentTime);
});

player.addEventListener('loadedmetadata', () => {
    if (!currentAudioPlayer.totalTimeEl || player.duration === 0) return;
    // Set the total duration display
    currentAudioPlayer.totalTimeEl.textContent = formatTime(player.duration);
});

player.addEventListener('ended', () => {
    resetAudioPlayerUI();
});

function resetAudioPlayerUI() {
    if (currentAudioPlayer.button) {
        currentAudioPlayer.button.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M3 10v4c0 .55.45 1 1 1h3l3.29 3.29c.63.63 1.71.18 1.71-.71V6.41c0-.89-1.08-1.34-1.71-.71L7 9H4c-.55 0-1 .45-1 1zm13.5 2c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 4.45v.2c0 .38.25.71.6.85C17.18 6.53 19 9.06 19 12s-1.82 5.47-4.4 6.5c-.36.14-.6.47-.6.85v.2c0 .63.63 1.07 1.21.85C18.6 19.11 21 15.84 21 12s-2.4-7.11-5.79-8.4c-.58-.23-1.21.22-1.21.85z"/></svg>';
    }
    if (currentAudioPlayer.progressContainer) {
        currentAudioPlayer.progressContainer.style.display = 'none';
        currentAudioPlayer.progressFill.style.width = '0%';
        currentAudioPlayer.currentTimeEl.textContent = '0:00';
    }
    currentAudioPlayer.state = 'stopped';
    currentAudioPlayer.button = null;
    currentAudioPlayer.text = null;
    currentAudioPlayer.progressContainer = null;
}

function formatTime(seconds) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
}

// --- Page Load and Main Button Logic (No major changes) ---
document.addEventListener('DOMContentLoaded', loadInitialSummaries);

// --- SEARCH FUNCTIONALITY ---
searchBtn.addEventListener('click', performSearch);
clearSearchBtn.addEventListener('click', clearSearch);
searchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        performSearch();
    }
});

// --- PAGINATION EVENT LISTENERS ---
pageSizeSelect.addEventListener('change', async (e) => {
    currentPageSize = parseInt(e.target.value, 10);
    currentPage = 1; // Reset to first page when changing page size
    await loadPaginatedSummaries(currentPage, currentPageSize);
});

prevPageBtn.addEventListener('click', async () => {
    if (currentPage > 1) {
        currentPage--;
        await loadPaginatedSummaries(currentPage, currentPageSize);
    }
});

nextPageBtn.addEventListener('click', async () => {
    if (currentPage < totalPages) {
        currentPage++;
        await loadPaginatedSummaries(currentPage, currentPageSize);
    }
});

// --- MODEL SELECTION FUNCTIONALITY ---
const modelSelect = document.getElementById('model-select');

// Load saved model preference
function loadModelPreference() {
    const savedModel = localStorage.getItem('selectedModel');
    if (savedModel && modelSelect.querySelector(`option[value="${savedModel}"]`)) {
        modelSelect.value = savedModel;
    } else if (modelSelect.children.length > 0) {
        // If saved model is not available, select the first available option
        const firstOption = modelSelect.querySelector('option:not(:disabled)');
        if (firstOption) {
            modelSelect.value = firstOption.value;
            localStorage.setItem('selectedModel', firstOption.value);
        }
    }
}

// Save model preference when changed
modelSelect.addEventListener('change', () => {
    localStorage.setItem('selectedModel', modelSelect.value);
});

// Populate model options and check availability
async function populateModelOptions() {
    try {
        const response = await fetch('/api_status');
        const status = await response.json();

        // Clear existing options
        modelSelect.innerHTML = '';

        // Model list and display names come from ai_models.AVAILABLE_MODELS via /api_status
        const providerLabels = { google: 'Google Gemini', openai: 'OpenAI' };
        const providerKeySet = {
            google: status.google_api_key_set,
            openai: status.openai_api_key_set
        };

        // Group models by provider
        const providers = {};

        (status.models || []).forEach(model => {
            // Only offer models whose provider has an API key
            if (!providerKeySet[model.provider]) return;

            const providerName = providerLabels[model.provider] || model.provider;
            if (!providers[providerName]) {
                providers[providerName] = [];
            }
            providers[providerName].push({
                key: model.key,
                name: model.display_name
            });
        });

        // Create optgroups and options
        Object.keys(providers).forEach(providerName => {
            const optgroup = document.createElement('optgroup');
            optgroup.label = providerName;

            providers[providerName].forEach(model => {
                const option = document.createElement('option');
                option.value = model.key;
                option.textContent = model.name;
                optgroup.appendChild(option);
            });

            modelSelect.appendChild(optgroup);
        });

        // Set default selection (server default if offered, otherwise first available)
        let defaultModel;
        if (status.default_model && modelSelect.querySelector(`option[value="${status.default_model}"]`)) {
            defaultModel = status.default_model;
        } else {
            defaultModel = modelSelect.querySelector('option')?.value;
        }

        if (defaultModel) {
            modelSelect.value = defaultModel;
        }

        // If no models are available, show a message
        if (modelSelect.children.length === 0) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'No AI models available - Please configure API keys';
            option.disabled = true;
            modelSelect.appendChild(option);
        }

    } catch (error) {
        console.warn('Could not populate model options:', error);
        // Fallback: add a basic option
        const option = document.createElement('option');
        option.value = '';  // empty: the server uses its default model
        option.textContent = 'Default model';
        modelSelect.appendChild(option);
    }
}

async function performSearch() {
    const query = searchInput.value.trim();
    if (!query) {
        alert('Please enter a search term.');
        return;
    }

    searchBtn.disabled = true;
    searchBtn.textContent = 'Searching...';

    try {
        const response = await fetch(`/search_summaries?q=${encodeURIComponent(query)}`);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Search failed');
        }

        const results = await response.json();
        displaySearchResults(results, query);
    } catch (error) {
        console.error('Search error:', error);
        alert(`Search failed: ${error.message}`);
    } finally {
        searchBtn.disabled = false;
        searchBtn.textContent = 'Search';
    }
}

function displaySearchResults(results, query) {
    searchResults.innerHTML = '';

    if (results.length === 0) {
        searchResults.innerHTML = `<p style="text-align: center; color: #7f8c8d; margin: 20px 0;">No summaries found for "${escapeHtml(query)}"</p>`;
        return;
    }

    const headerEl = document.createElement('h3');
    headerEl.textContent = `Search Results for "${query}" (${results.length} found)`;
    headerEl.style.margin = '0 0 15px 0';
    headerEl.style.color = '#2c3e50';
    searchResults.appendChild(headerEl);

    results.forEach(result => {
        const card = createResultCard(result.title, result.summary, result.error, result.thumbnail_url, result.video_id);
        searchResults.appendChild(card);
    });
}

function clearSearch() {
    searchInput.value = '';
    searchResults.innerHTML = '';
}

// --- PAGINATION FUNCTIONALITY ---
function loadPaginationState() {
    const savedPage = localStorage.getItem('summaries_current_page');
    const savedPageSize = localStorage.getItem('summaries_page_size');

    if (savedPage) currentPage = parseInt(savedPage, 10) || 1;
    if (savedPageSize) currentPageSize = parseInt(savedPageSize, 10) || 10;

    pageSizeSelect.value = currentPageSize.toString();
}

function savePaginationState() {
    localStorage.setItem('summaries_current_page', currentPage.toString());
    localStorage.setItem('summaries_page_size', currentPageSize.toString());
}

function updatePaginationUI(paginationData) {
    totalSummaries = paginationData.total;
    totalPages = paginationData.total_pages;
    currentPage = paginationData.page;

    // Update pagination info
    const startItem = totalSummaries === 0 ? 0 : (currentPage - 1) * currentPageSize + 1;
    const endItem = Math.min(currentPage * currentPageSize, totalSummaries);
    paginationInfoText.textContent = `Showing ${startItem}-${endItem} of ${totalSummaries} summaries`;

    // Update page info
    currentPageSpan.textContent = currentPage;
    totalPagesSpan.textContent = totalPages;

    // Update button states
    prevPageBtn.disabled = currentPage <= 1;
    nextPageBtn.disabled = currentPage >= totalPages;

    // Show/hide pagination section
    paginationSection.style.display = totalSummaries > 0 ? 'block' : 'none';
}

async function loadPaginatedSummaries(page = currentPage, pageSize = currentPageSize, preserveNewResults = true) {
    loader.innerHTML = '<p>Loading summaries...</p>';
    loader.classList.add('active');
    const initialResultsContainer = document.getElementById('initial-results');
    initialResultsContainer.innerHTML = '';

    // Preserve new results section by default
    const newResultsContainer = document.getElementById('new-results');
    if (!preserveNewResults && newResultsContainer.children.length > 0) {
        // Clear new results only if explicitly requested
        newResultsContainer.innerHTML = '';
    }

    try {
        const response = await fetch(`/get_cached_summaries?page=${page}&per_page=${pageSize}`);
        if (!response.ok) throw new Error('Could not fetch cached summaries.');
        const data = await response.json();

        if (data.summaries && data.summaries.length > 0) {
            initialResultsContainer.innerHTML = '<h2>Previously Summarized</h2>';
            displayResults(data.summaries, initialResultsContainer, false);
        }

        updatePaginationUI(data);
        currentPage = data.page;
        savePaginationState();

    } catch (error) {
        console.error("Error loading paginated summaries:", error);
        paginationSection.style.display = 'none';
    } finally {
        loader.classList.remove('active');
        loader.innerHTML = '<p>Working my magic... this may take a while for large playlists. 🪄</p>';
    }
}

async function loadInitialSummaries() {
    loadPaginationState();
    await populateModelOptions();
    loadModelPreference();
    // Load previously summarized videos, preserve new summaries section
    await loadPaginatedSummaries(currentPage, currentPageSize, true);

    // Initialize SSE connection for real-time updates
    initializeSSE();
}

// --- BACKGROUND SUMMARY REQUESTS ---
// POST /summarize/start queues the work and returns a request_id at once.
// Results arrive as `summary_result` SSE events (each with a per-request `seq`)
// and a final `summary_done` event; GET /summarize/<id> is the fallback and the
// end-of-request reconcile. Older servers without /summarize/start get the
// synchronous POST /summarize.
const SUMMARY_POLL_FAST_MS = 3000;   // SSE not connected
const SUMMARY_POLL_SLOW_MS = 15000;  // SSE connected: occasional safety reconcile
const MAX_PENDING_SUMMARY_EVENTS = 500;

let activeSummary = null;
let summaryStartInFlight = false;
const pendingSummaryEvents = [];

async function readJsonResponse(response) {
    // Check if the response is JSON before trying to parse it
    const contentType = response.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
        // If not JSON, it's likely an HTML error page
        const text = await response.text();
        console.error('Server returned non-JSON response:', text);
        throw new Error('Server error: Expected JSON response but received HTML. Please check if the server is running correctly.');
    }
    return response.json();
}

async function summarizeSynchronously(urls, model) {
    const response = await fetch('/summarize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls: urls, model: model }),
    });
    const data = await readJsonResponse(response);
    if (!response.ok) throw new Error(data.error || 'An unknown server error occurred.');
    const newResultsContainer = document.getElementById('new-results');
    displayResults(data, newResultsContainer, true, true);
}

function isSSEConnected() {
    return !!eventSource && eventSource.readyState === EventSource.OPEN;
}

function handleSummaryResultEvent(data) {
    if (activeSummary && data.request_id === activeSummary.requestId) {
        acceptSummaryItem(activeSummary, data);
    } else if (summaryStartInFlight && pendingSummaryEvents.length < MAX_PENDING_SUMMARY_EVENTS) {
        // Arrived before /summarize/start answered with the request_id
        pendingSummaryEvents.push({ type: 'result', data });
    }
}

function handleSummaryDoneEvent(data) {
    if (activeSummary && data.request_id === activeSummary.requestId) {
        reconcileSummary(activeSummary);
    } else if (summaryStartInFlight && pendingSummaryEvents.length < MAX_PENDING_SUMMARY_EVENTS) {
        pendingSummaryEvents.push({ type: 'done', data });
    }
}

// Resolves when the request finishes; rejects if it failed or was lost.
function trackSummaryRequest(requestId) {
    return new Promise((resolve, reject) => {
        const newResultsContainer = document.getElementById('new-results');
        const heading = ensureNewSummariesHeading(newResultsContainer);
        const group = document.createElement('div');
        group.className = 'summary-request-results';
        group.dataset.requestId = requestId;
        heading.after(group);

        const tracker = {
            requestId, group, resolve, reject,
            nextSeq: 0,
            buffered: new Map(),
            playlists: {},
            finished: false,
            polling: false,
            timer: null,
        };
        activeSummary = tracker;
        summaryStartInFlight = false;

        const pending = pendingSummaryEvents.splice(0);
        let sawDone = false;
        pending.forEach(evt => {
            if (evt.data.request_id !== requestId) return;
            if (evt.type === 'result') acceptSummaryItem(tracker, evt.data);
            else sawDone = true;
        });

        if (sawDone) reconcileSummary(tracker);
        else scheduleSummaryPoll(tracker);
    });
}

function scheduleSummaryPoll(tracker) {
    if (tracker.finished) return;
    clearTimeout(tracker.timer);
    const delay = isSSEConnected() ? SUMMARY_POLL_SLOW_MS : SUMMARY_POLL_FAST_MS;
    tracker.timer = setTimeout(() => reconcileSummary(tracker), delay);
}

// Fetch the request state, render anything missed, and finish if it is done.
async function reconcileSummary(tracker) {
    if (tracker.finished || tracker.polling) return;
    tracker.polling = true;
    try {
        const response = await fetch(`/summarize/${encodeURIComponent(tracker.requestId)}`);
        if (response.status === 404) {
            finishSummary(tracker, new Error('The summary request is no longer available (the server may have restarted).'));
            return;
        }
        const state = await readJsonResponse(response);
        if (!response.ok) throw new Error(state.error || `Status check failed (${response.status})`);
        (state.items || []).forEach(item => acceptSummaryItem(tracker, item));
        if (state.done) {
            finishSummary(tracker, state.status === 'failed' ? new Error(state.error || 'Summarization failed.') : null);
            return;
        }
    } catch (error) {
        // Transient network problem: keep going, the next poll retries
        console.warn('Could not fetch summary status:', error);
    } finally {
        tracker.polling = false;
    }
    scheduleSummaryPoll(tracker);
}

function finishSummary(tracker, error) {
    if (tracker.finished) return;
    tracker.finished = true;
    clearTimeout(tracker.timer);
    if (activeSummary === tracker) activeSummary = null;
    if (!tracker.group.children.length) tracker.group.remove();
    if (error) tracker.reject(error);
    else tracker.resolve();
}

// Render items strictly in `seq` order; a gap (missed SSE event) triggers a status fetch.
function acceptSummaryItem(tracker, payload) {
    if (typeof payload.seq !== 'number' || payload.seq < tracker.nextSeq) return;
    tracker.buffered.set(payload.seq, payload);
    while (tracker.buffered.has(tracker.nextSeq)) {
        renderSummaryItem(tracker, tracker.buffered.get(tracker.nextSeq));
        tracker.buffered.delete(tracker.nextSeq);
        tracker.nextSeq++;
    }
    if (tracker.buffered.size > 0 && !tracker.finished) {
        reconcileSummary(tracker);
    }
}

function renderSummaryItem(tracker, payload) {
    const { kind, item, index } = payload;
    if (!tracker.group.isConnected) {
        // "Clear" / "Move to Previous" emptied New Summaries mid-request; start a fresh group
        tracker.group.innerHTML = '';
        tracker.playlists = {};
        ensureNewSummariesHeading(document.getElementById('new-results')).after(tracker.group);
    }
    if (kind === 'playlist') {
        tracker.playlists[index] = createPlaylistContainer(item.title, tracker.group);
    } else if (kind === 'playlist_video') {
        let playlistContainer = tracker.playlists[index];
        if (!playlistContainer) {
            playlistContainer = createPlaylistContainer(payload.playlist_title, tracker.group);
            tracker.playlists[index] = playlistContainer;
        }
        appendVideoCard(item, playlistContainer);
    } else if (item.type === 'playlist') {
        const playlistContainer = createPlaylistContainer(item.title, tracker.group);
        if (item.error) {
            playlistContainer.innerHTML += `<div class="result-card error-card"><p>Error processing playlist: ${escapeHtml(item.error)}</p></div>`;
        }
        (item.summaries || []).forEach(video => appendVideoCard(video, playlistContainer));
    } else if (item.type === 'video') {
        appendVideoCard(item, tracker.group);
    } else if (item.type === 'error') {
        tracker.group.appendChild(createResultCard(item.url, null, item.error, null, null, null));
    }
}

function createPlaylistContainer(title, parent) {
    const playlistContainer = document.createElement('div');
    playlistContainer.className = 'playlist-container';
    playlistContainer.innerHTML = `<h2>Playlist: ${escapeHtml(title)}</h2>`;
    parent.appendChild(playlistContainer);
    return playlistContainer;
}

function appendVideoCard(video, parent) {
    // A re-summarized video replaces its earlier card in New Summaries
    if (video.video_id) {
        const newResultsContainer = document.getElementById('new-results');
        const existing = newResultsContainer.querySelector(`.result-card[data-video-id="${CSS.escape(video.video_id)}"]`);
        if (existing) existing.remove();
    }
    parent.appendChild(createResultCard(video.title, video.summary, video.error, video.thumbnail_url, video.video_id, video.video_url));
}

summarizeBtn.addEventListener('click', async () => {
    if (currentAudioPlayer.state !== 'stopped') {
        player.pause();
        resetAudioPlayerUI();
    }
    const urls = linksTextarea.value.split('\n').filter(url => url.trim() !== '');
    if (urls.length === 0) {
        alert('Please paste at least one YouTube link.');
        return;
    }
    summarizeBtn.disabled = true;
    summarizeBtn.textContent = 'Processing...';
    loader.classList.add('active');
    try {
        const selectedModel = document.getElementById('model-select').value;
        summaryStartInFlight = true;
        pendingSummaryEvents.length = 0;
        const response = await fetch('/summarize/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                urls: urls,
                model: selectedModel
            }),
        });

        if (response.status === 404) {
            // Older server without background requests
            summaryStartInFlight = false;
            pendingSummaryEvents.length = 0;
            await summarizeSynchronously(urls, selectedModel);
        } else {
            const data = await readJsonResponse(response);
            // 429 (rate limited / too many requests) and 400s carry a message in `error`
            if (!response.ok) throw new Error(data.error || data.message || 'An unknown server error occurred.');
            await trackSummaryRequest(data.request_id);
        }
        linksTextarea.value = '';

        // Refresh pagination to show updated summaries
        await loadPaginatedSummaries(currentPage, currentPageSize);
    } catch (error) {
        summaryStartInFlight = false;
        pendingSummaryEvents.length = 0;
        console.error('Error during summarization:', error);
        alert(`An Error Occurred: ${error.message}`);
    } finally {
        summarizeBtn.disabled = false;
        summarizeBtn.textContent = 'Summarize Links';
        loader.classList.remove('active');
    }
});

// --- UPDATED Audio Handling Logic ---
async function handleSpeakClick(button, textToSpeak) {
    const isSameAudio = (currentAudioPlayer.button === button && currentAudioPlayer.text === textToSpeak);
    if (isSameAudio && currentAudioPlayer.state === 'playing') {
        player.pause();
        currentAudioPlayer.state = 'paused';
        button.textContent = '▶️';
        return;
    }
    if (isSameAudio && currentAudioPlayer.state === 'paused') {
        await player.play();
        currentAudioPlayer.state = 'playing';
        button.textContent = '⏹️';
        return;
    }

    // Stop and reset any previously active audio
    if (currentAudioPlayer.state !== 'stopped') {
        player.pause();
        resetAudioPlayerUI();
    }

    // Set up the new player state
    currentAudioPlayer.button = button;
    currentAudioPlayer.text = textToSpeak;
    currentAudioPlayer.state = 'loading';
    button.textContent = '⏳';
    button.disabled = true;

    // Find and set up the progress bar elements for the *new* card
    const card = button.closest('.result-card');
    currentAudioPlayer.progressContainer = card.querySelector('.progress-container');
    currentAudioPlayer.progressFill = card.querySelector('.progress-fill');
    currentAudioPlayer.currentTimeEl = card.querySelector('.current-time');
    currentAudioPlayer.totalTimeEl = card.querySelector('.total-time');
    currentAudioPlayer.progressContainer.style.display = 'flex'; // Show the progress bar

    try {
        const response = await fetch('/speak', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: textToSpeak }),
        });
        if (!response.ok) {
            if (response.status === 429) {
                const data = await response.json().catch(() => ({}));
                const err = new Error(data.error || 'Too many requests. Please wait a moment and try again.');
                err.userMessage = err.message;
                throw err;
            }
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('text/html')) {
                throw new Error('Server returned an error page. The server might be experiencing issues.');
            }
            throw new Error('Failed to generate audio from server.');
        }
        const audioBlob = await response.blob();
        player.src = URL.createObjectURL(audioBlob);
        await player.play();
        currentAudioPlayer.state = 'playing';
        button.textContent = '⏹️';
    } catch (error) {
        console.error('Error fetching speech:', error);
        alert(error.userMessage || 'Sorry, could not generate speech for this summary.');
        resetAudioPlayerUI();
    } finally {
        button.disabled = false;
    }
}

// --- Clear New Summaries ---
function clearNewSummaries() {
    const newResultsContainer = document.getElementById('new-results');
    if (confirm('Are you sure you want to clear all new summaries from view? They will still be available in Previously Summarized.')) {
        newResultsContainer.innerHTML = '';
    }
}

// --- Move New Summaries to Previously Summarized ---
function moveNewToPrevious() {
    const newResultsContainer = document.getElementById('new-results');
    const initialResultsContainer = document.getElementById('initial-results');

    // Get all cards from new results (excluding the heading)
    const newCards = Array.from(newResultsContainer.querySelectorAll('.result-card'));

    if (newCards.length === 0) {
        alert('No new summaries to move.');
        return;
    }

    // Make sure the Previously Summarized heading exists
    if (!initialResultsContainer.querySelector('h2')) {
        const heading = document.createElement('h2');
        heading.textContent = 'Previously Summarized';
        initialResultsContainer.prepend(heading);
    }

    // Move cards to the top of previously summarized (after heading)
    const heading = initialResultsContainer.querySelector('h2');
    newCards.reverse().forEach(card => {
        heading.after(card);
    });

    // Clear the new results container
    newResultsContainer.innerHTML = '';
}

// --- Delete Summary Handler ---
async function handleDeleteClick(button, videoId, card) {
    if (!confirm('Are you sure you want to delete this summary? This action cannot be undone.')) {
        return;
    }

    // Disable the button and show loading state
    button.disabled = true;
    const originalText = button.textContent;
    button.textContent = '⏳';

    try {
        const response = await fetch('/delete_summary', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ video_id: videoId }),
        });

        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            throw new Error('Server returned an error page. The server might be experiencing issues.');
        }

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to delete summary');
        }

        // Remove the card from the DOM with a fade effect
        card.style.transition = 'opacity 0.3s ease-out';
        card.style.opacity = '0';
        setTimeout(async () => {
            if (card.parentNode) {
                card.parentNode.removeChild(card);
            }
            // Refresh pagination after deletion
            await loadPaginatedSummaries(currentPage, currentPageSize);
        }, 300);

        console.log('Summary deleted successfully:', data.message);

    } catch (error) {
        console.error('Error deleting summary:', error);
        alert(`Failed to delete summary: ${error.message}`);
        // Restore button state on error
        button.textContent = originalText;
        button.disabled = false;
    }
}

// --- HTML Creation and Display Logic ---
function ensureNewSummariesHeading(container) {
    // Check if heading already exists
    let heading = container.querySelector('.new-summaries-heading');
    if (!heading) {
        heading = document.createElement('h2');
        heading.className = 'new-summaries-heading';
        heading.innerHTML = `
            <span>New Summaries</span>
            <div style="display: flex; gap: 10px;">
                <button class="clear-new-btn" onclick="moveNewToPrevious()" title="Move to Previously Summarized">Move to Previous</button>
                <button class="clear-new-btn" onclick="clearNewSummaries()" title="Clear from view">Clear</button>
            </div>
        `;
        container.appendChild(heading);
    }
    return heading;
}

function displayResults(data, container, prepend = false, isNewSummary = false) {
    if (data.length === 0) return;

    // Add heading for new summaries if this is the first item
    if (isNewSummary && container.id === 'new-results') {
        ensureNewSummariesHeading(container);
    }
    data.forEach(item => {
        if (item.type === 'playlist') {
            const playlistContainer = document.createElement('div');
            playlistContainer.className = 'playlist-container';
            playlistContainer.innerHTML = `<h2>Playlist: ${escapeHtml(item.title)}</h2>`;
            if (item.error) {
                playlistContainer.innerHTML += `<div class="result-card error-card"><p>Error processing playlist: ${escapeHtml(item.error)}</p></div>`;
            }
            if (item.summaries) {
                item.summaries.forEach(video => addOrUpdateCard(video, playlistContainer, prepend));
            }
            if (prepend) container.prepend(playlistContainer);
            else container.appendChild(playlistContainer);
        } else if (item.type === 'video') {
            addOrUpdateCard(item, container, prepend);
        } else if (item.type === 'error') {
            const errorCard = createResultCard(item.url, null, item.error, null, null, null);
            if (prepend) container.prepend(errorCard);
            else container.appendChild(errorCard);
        }
    });
}

function addOrUpdateCard(video, container, prepend) {
    // Only remove existing card if it's in the same container
    // This allows new summaries to stay separate from previously summarized
    const existingCard = container.querySelector(`.result-card[data-video-id='${video.video_id}']`);
    if (existingCard) existingCard.remove();

    const card = createResultCard(video.title, video.summary, video.error, video.thumbnail_url, video.video_id, video.video_url);

    // If adding to new results, make sure heading is at the top
    if (container.id === 'new-results') {
        const heading = container.querySelector('.new-summaries-heading');
        if (heading && prepend) {
            // Insert after the heading
            heading.after(card);
        } else if (prepend) {
            container.prepend(card);
        } else {
            container.appendChild(card);
        }
    } else {
        if (prepend) container.prepend(card);
        else container.appendChild(card);
    }
}

// --- UPDATED to create progress bar elements ---
function createResultCard(title, summary, error, thumbnail_url, videoId, videoUrl) {
    const card = document.createElement('div');
    card.className = 'result-card';
    if (videoId) card.dataset.videoId = videoId;

    if (thumbnail_url) {
        const img = document.createElement('img');
        img.src = thumbnail_url;
        img.className = 'thumbnail';
        img.alt = `Thumbnail for ${title}`;
        card.appendChild(img);
    }

    const summaryContent = document.createElement('div');
    summaryContent.className = 'summary-content';
    const headerDiv = document.createElement('div');
    headerDiv.className = 'card-header';
    const titleEl = document.createElement('h3');
    if (videoUrl) {
        const titleLink = document.createElement('a');
        titleLink.href = videoUrl;
        titleLink.target = '_blank';
        titleLink.rel = 'noopener noreferrer';
        titleLink.textContent = title;
        titleEl.appendChild(titleLink);
    } else {
        titleEl.textContent = title;
    }
    headerDiv.appendChild(titleEl);

    summaryContent.appendChild(headerDiv);

    if (error) {
        card.classList.add('error-card');
        summaryContent.innerHTML += `<p>${escapeHtml(error)}</p>`;
    } else if (summary) {
        const speakBtn = document.createElement('button');
        speakBtn.className = 'icon-btn speak-btn';
        speakBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M3 10v4c0 .55.45 1 1 1h3l3.29 3.29c.63.63 1.71.18 1.71-.71V6.41c0-.89-1.08-1.34-1.71-.71L7 9H4c-.55 0-1 .45-1 1zm13.5 2c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 4.45v.2c0 .38.25.71.6.85C17.18 6.53 19 9.06 19 12s-1.82 5.47-4.4 6.5c-.36.14-.6.47-.6.85v.2c0 .63.63 1.07 1.21.85C18.6 19.11 21 15.84 21 12s-2.4-7.11-5.79-8.4c-.58-.23-1.21.22-1.21.85z"/></svg>';
        speakBtn.title = 'Read summary aloud';
        speakBtn.onclick = () => handleSpeakClick(speakBtn, summary);
        headerDiv.appendChild(speakBtn);

        // Add delete button if we have a video ID
        if (videoId) {
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'icon-btn trash-btn';
            deleteBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>';
            deleteBtn.title = 'Delete this summary';
            deleteBtn.onclick = () => handleDeleteClick(deleteBtn, videoId, card);
            headerDiv.appendChild(deleteBtn);
        }

        // Create progress bar elements
        const progressContainer = document.createElement('div');
        progressContainer.className = 'progress-container';
        progressContainer.innerHTML = `
            <span class="time-display current-time">0:00</span>
            <div class="progress-track">
                <div class="progress-fill"></div>
            </div>
            <span class="time-display total-time">0:00</span>`;

        const summaryPre = document.createElement('pre');
        summaryPre.textContent = summary;

        summaryContent.appendChild(progressContainer);
        summaryContent.appendChild(summaryPre);

        // Add seek functionality
        const progressTrack = progressContainer.querySelector('.progress-track');
        progressTrack.addEventListener('click', (e) => {
            // Only allow seeking on the currently active audio player
            if (currentAudioPlayer.progressContainer !== progressContainer) return;

            const trackWidth = progressTrack.offsetWidth;
            const clickX = e.offsetX;
            const duration = player.duration;
            if (duration > 0) {
                player.currentTime = (clickX / trackWidth) * duration;
            }
        });
    }

    card.appendChild(summaryContent);
    return card;
}
