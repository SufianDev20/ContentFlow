function resetGenerateButton() {
    const generateBtn = document.getElementById('generate-btn');
    if (generateBtn) {
        generateBtn.disabled = false;
        generateBtn.setAttribute('aria-busy', 'false');
        generateBtn.textContent = 'Generate Content';
    }
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
            clearFormError();
            const urlInput = document.getElementById('url-input');
            const url = urlInput ? urlInput.value.trim() : '';

            if (!url) {
                showFormError('Enter a URL first.');
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
                showFormError(result?.error || 'Could not fetch that URL. Try pasting the text directly.');
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
            clearFormError();

            const content = contentInput ? contentInput.value.trim() : '';
            if (!content) {
                showFormError('Paste some content first.');
                return;
            }

            const formats = Array.from(document.querySelectorAll('input[type=checkbox]:checked')).map((cb) => cb.value);
            if (formats.length === 0) {
                showFormError('Select at least one format.');
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

            resetGenerateButton();
            if (!result || result.error) {
                showFormError(result?.error || 'Generation failed. Try again.');
                return;
            }
            if (result.outputs.length === 0) {
                showFormError('No outputs generated.');
                return;
            }
            const container = document.getElementById('outputs-container');
            container.innerHTML = '';
            result.outputs.forEach((output) => container.appendChild(renderOutputCard(output)));
        });
    }
});
