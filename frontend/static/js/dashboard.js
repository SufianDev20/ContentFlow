let currentJobId = null;
let progressInterval = null;


function pollJobProgress(jobId) {
    if (progressInterval) {
        clearInterval(progressInterval);
    }

    currentJobId = jobId;
    progressInterval = setInterval(async () => {
        const status = await apiFetch(`/jobs/${jobId}/status/`);
        if (!status || status.error) {
            clearInterval(progressInterval);
            return;
        }

        updateProgressUI(status);

        if (status.status === 'complete' || status.status === 'failed') {
            clearInterval(progressInterval);
            if (status.status === 'complete') {
                const jobDetails = await apiFetch(`/jobs/${jobId}/`);
                if (jobDetails && !jobDetails.error) {
                    const container = document.getElementById('outputs-container');
                    if (container) {
                        container.innerHTML = '';
                        const outputs = Array.isArray(jobDetails.outputs) ? jobDetails.outputs : [];
                        if (outputs.length === 0) {
                            showError('No outputs generated.');
                            return;
                        }
                        outputs.forEach((output) => container.appendChild(renderOutputCard(output)));
                    }
                }
            }
            resetGenerateButton();
        }
    }, 2000);
}

function updateProgressUI(status) {
    const progressBar = document.getElementById('generation-progress');
    const progressText = document.getElementById('progress-text');
    const statusBadge = document.getElementById('status-badge');

    if (progressBar) {
        progressBar.style.width = `${status.progress}%`;
        progressBar.setAttribute('aria-valuenow', status.progress);
    }

    if (progressText) {
        progressText.textContent = `${status.progress}% - ${status.completed_outputs}/${status.total_formats} formats completed`;
    }

    if (statusBadge) {
        statusBadge.textContent = status.status;
        statusBadge.className = 'badge';
        if (status.status === 'processing') {
            statusBadge.classList.add('badge-processing');
        } else if (status.status === 'complete') {
            statusBadge.classList.add('badge-complete');
        } else if (status.status === 'failed') {
            statusBadge.classList.add('badge-failed');
        }
    }
}

function showProgressUI() {
    const progressContainer = document.getElementById('progress-container');
    if (progressContainer) {
        progressContainer.classList.remove('hidden');
    }
}

function hideProgressUI() {
    const progressContainer = document.getElementById('progress-container');
    if (progressContainer) {
        progressContainer.classList.add('hidden');
    }
}

function resetGenerateButton() {
    const generateBtn = document.getElementById('generate-btn');
    if (generateBtn) {
        generateBtn.disabled = false;
        generateBtn.setAttribute('aria-busy', 'false');
        generateBtn.textContent = 'Generate Content';
    }
}

function showError(message) {
    const el = document.getElementById('form-error');
    if (!el) return;
    el.textContent = message;
    el.classList.add('visible');
}

function clearError() {
    const el = document.getElementById('form-error');
    if (!el) return;
    el.textContent = '';
    el.classList.remove('visible');
}

// ---- Tabs ----
function switchToTextTab() {
    const tabText = document.getElementById('tab-text');
    const tabUrl = document.getElementById('tab-url');
    const panelText = document.getElementById('panel-text');
    const panelUrl = document.getElementById('panel-url');

    if (tabText && tabUrl && panelText && panelUrl) {
        tabText.classList.add('active');
        tabUrl.classList.remove('active');
        panelText.classList.remove('hidden');
        panelUrl.classList.add('hidden');
    }
}

function switchToUrlTab() {
    const tabText = document.getElementById('tab-text');
    const tabUrl = document.getElementById('tab-url');
    const panelText = document.getElementById('panel-text');
    const panelUrl = document.getElementById('panel-url');

    if (tabText && tabUrl && panelText && panelUrl) {
        tabUrl.classList.add('active');
        tabText.classList.remove('active');
        panelUrl.classList.remove('hidden');
        panelText.classList.add('hidden');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const tabText = document.getElementById('tab-text');
    const tabUrl = document.getElementById('tab-url');
    const fetchUrlBtn = document.getElementById('fetch-url-btn');
    const generateBtn = document.getElementById('generate-btn');
    const contentInput = document.getElementById('content-input');

    if (tabText) tabText.addEventListener('click', switchToTextTab);
    if (tabUrl) tabUrl.addEventListener('click', switchToUrlTab);

    function updateCharCount() {
        const charCount = document.getElementById('char-count');
        if (charCount && contentInput) {
            const currentLength = contentInput.value.length;
            const maxAttr = contentInput.maxLength;
            const maxLength = (maxAttr && maxAttr > 0) ? maxAttr : 50000;

            charCount.textContent = `${currentLength.toLocaleString()} / ${maxLength.toLocaleString()} characters`;

            if (currentLength > maxLength * 0.9) {
                charCount.classList.add('text-primary');
            } else {
                charCount.classList.remove('text-primary');
            }
        }
    }

    function validateContent() {
        const validationMessage = document.getElementById('validation-message');
        if (!validationMessage || !contentInput) return;

        const content = contentInput.value.trim();
        if (content.length === 0) {
            validationMessage.textContent = '';
        } else if (content.length < 50) {
            validationMessage.textContent = 'Content is too short for best results';
            validationMessage.classList.add('text-primary');
        } else if (content.length < 200) {
            validationMessage.textContent = 'Short content - consider adding more detail';
            validationMessage.classList.remove('text-primary');
        } else {
            validationMessage.textContent = '✓ Good content length';
            validationMessage.classList.remove('text-primary');
            validationMessage.classList.add('text-success');
        }
    }

    if (contentInput) {
        const savedContent = localStorage.getItem('contentflow_draft');
        if (savedContent) {
            contentInput.value = savedContent;
            updateCharCount();
            validateContent();
        }

        contentInput.addEventListener('input', () => {
            localStorage.setItem('contentflow_draft', contentInput.value);
            updateCharCount();
            validateContent();
        });
    }

    if (fetchUrlBtn) {
        fetchUrlBtn.addEventListener('click', async () => {
            clearError();
            const urlInput = document.getElementById('url-input');
            const url = urlInput ? urlInput.value.trim() : '';

            if (!url) {
                showError('Enter a URL first.');
                return;
            }

            fetchUrlBtn.disabled = true;
            fetchUrlBtn.textContent = 'Fetching…';

            const result = await apiFetch('/scrape/', {
                method: 'POST',
                body: JSON.stringify({ url })
            });

            fetchUrlBtn.disabled = false;
            fetchUrlBtn.textContent = 'Fetch content';

            if (!result || result.error) {
                showError(result?.error || 'Could not fetch that URL. Try pasting the text directly.');
                return;
            }

            const text = typeof result === 'string' ? result : (result.text ?? '');
            if (contentInput) {
                contentInput.value = text;
                localStorage.setItem('contentflow_draft', text);
                updateCharCount();
                validateContent();
            }
            switchToTextTab();
        });
    }

    if (generateBtn) {
        generateBtn.addEventListener('click', async () => {
            clearError();

            const content = contentInput ? contentInput.value.trim() : '';
            if (!content) {
                showError('Paste some content first.');
                return;
            }

            const formats = Array.from(document.querySelectorAll('input[type=checkbox]:checked')).map((cb) => cb.value);
            if (formats.length === 0) {
                showError('Select at least one format.');
                return;
            }

            const modelSelect = document.getElementById('model-select');
            const model = modelSelect ? modelSelect.value : '';

            generateBtn.disabled = true;
            generateBtn.setAttribute('aria-busy', 'true');
            generateBtn.textContent = 'Generating…';

            const result = await apiFetch('/jobs/', {
                method: 'POST',
                body: JSON.stringify({ content, formats, model })
            });

            if (!result || result.error) {
                showError(result?.error || 'Generation failed. Try again.');
                resetGenerateButton();
                return;
            }

            if (result.id) {
                showProgressUI();
                pollJobProgress(result.id);
            }
        });
    }
});

// ---- Helper Render Functions ----
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function renderRatingWidget(outputId, currentRating) {
    let stars = '';
    for (let i = 1; i <= 5; i++) {
        const filled = currentRating && i <= currentRating ? 'filled' : '';
        stars += `<span class="star ${filled}" data-output-id="${outputId}" data-value="${i}" role="button" aria-label="Rate ${i} of 5"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6L12 17.3 6.1 20.6l1.3-6.6L2.5 9.4l6.6-.8z"/></svg></span>`;
    }
    return `<div class="rating-widget">${stars}</div>`;
}

function renderOutputCard(output) {
    const card = document.createElement('div');
    card.className = 'output-card';

    const formatDisplay = output.format ? output.format.replace('_', ' ') : 'Output';
    const textContent = output.text || '';

    const qualityScore = output.quality_score ?? 0;
    const latencyMs = output.latency_ms ?? 0;
    const tokensPerSec = output.tokens_per_second ?? 0;

    card.innerHTML = `
    <div class="output-card-header">
      <span class="output-card-format">${formatDisplay}</span>
      <button class="copy-btn" data-text="${escapeHtml(textContent)}">Copy</button>
    </div>
    <p class="output-card-body">${escapeHtml(textContent)}</p>
    <div class="output-metrics-display">
      <div class="output-metric-item">
        <span class="output-metric-label">Quality</span>
        <span class="output-metric-value">${(qualityScore / 10).toFixed(1)}</span>
      </div>
      <div class="output-metric-item">
        <span class="output-metric-label">Latency</span>
        <span class="output-metric-value">${latencyMs}ms</span>
      </div>
      <div class="output-metric-item">
        <span class="output-metric-label">Speed</span>
        <span class="output-metric-value">${tokensPerSec} t/s</span>
      </div>
    </div>
    ${renderRatingWidget(output.id, output.user_rating)}
  `;

    const copyBtn = card.querySelector('.copy-btn');
    if (copyBtn) {
        copyBtn.addEventListener('click', (e) => {
            navigator.clipboard.writeText(e.target.dataset.text);
            e.target.textContent = 'Copied!';
            setTimeout(() => { e.target.textContent = 'Copy'; }, 1500);
        });
    }

    return card;
}

// Global Rating Event Listener
document.addEventListener('click', async (e) => {
    if (!e.target.classList.contains('star')) return;
    const outputId = e.target.dataset.outputId;
    const rating = parseInt(e.target.dataset.value, 10);

    await apiFetch(`/outputs/${outputId}/rate/`, {
        method: 'PATCH',
        body: JSON.stringify({ user_rating: rating })
    });

    const widget = e.target.closest('.rating-widget');
    if (widget) {
        widget.querySelectorAll('.star').forEach((star) => {
            const value = parseInt(star.dataset.value, 10);
            star.classList.toggle('filled', value <= rating);
        });
    }
});