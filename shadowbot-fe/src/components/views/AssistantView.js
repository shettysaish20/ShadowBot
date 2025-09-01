import { html, css, LitElement } from '../../assets/lit-core-2.7.4.min.js';
import { configure as agentConfigure, runJob as agentRunJob, cancelJob as agentCancelJob, subscribe as agentSubscribe, getSnapshot as agentGetSnapshot } from '../../utils/agentStream.js';
// Deprecated: no longer fetching full report via history endpoint; relying solely on WS report.final payload

export class AssistantView extends LitElement {
    static styles = css`
        :host {
            height: 100%;
            display: flex;
            flex-direction: column;
        }

        * {
            font-family: 'Inter', sans-serif;
            cursor: default;
        }

        .response-container {
            height: calc(100% - 60px);
            overflow-y: auto;
            border-radius: 10px;
            font-size: var(--response-font-size, 18px);
            line-height: 1.6;
            background: var(--main-content-background);
            padding: 16px;
            scroll-behavior: smooth;
            user-select: text;
            cursor: text;
        }

        /* Allow text selection for all content within the response container */
        .response-container * {
            user-select: text;
            cursor: text;
        }

        /* Restore default cursor for interactive elements */
        .response-container a {
            cursor: pointer;
        }

        /* Animated word-by-word reveal */
        .response-container [data-word] {
            opacity: 0;
            filter: blur(10px);
            display: inline-block;
            transition: opacity 0.5s, filter 0.5s;
        }
        .response-container [data-word].visible {
            opacity: 1;
            filter: blur(0px);
        }

        /* Markdown styling */
        .response-container h1,
        .response-container h2,
        .response-container h3,
        .response-container h4,
        .response-container h5,
        .response-container h6 {
            margin: 1.2em 0 0.6em 0;
            color: var(--text-color);
            font-weight: 600;
        }

        .response-container h1 {
            font-size: 1.8em;
        }
        .response-container h2 {
            font-size: 1.5em;
        }
        .response-container h3 {
            font-size: 1.3em;
        }
        .response-container h4 {
            font-size: 1.1em;
        }
        .response-container h5 {
            font-size: 1em;
        }
        .response-container h6 {
            font-size: 0.9em;
        }

        .response-container p {
            margin: 0.8em 0;
            color: var(--text-color);
        }

        .response-container ul,
        .response-container ol {
            margin: 0.8em 0;
            padding-left: 2em;
            color: var(--text-color);
        }

        .response-container li {
            margin: 0.4em 0;
        }

        .response-container blockquote {
            margin: 1em 0;
            padding: 0.5em 1em;
            border-left: 4px solid var(--focus-border-color);
            background: rgba(0, 122, 255, 0.1);
            font-style: italic;
        }

        .response-container code {
            background: rgba(255, 255, 255, 0.1);
            padding: 0.2em 0.4em;
            border-radius: 3px;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 0.85em;
        }

        .response-container pre {
            background: var(--input-background);
            border: 1px solid var(--button-border);
            border-radius: 6px;
            padding: 1em;
            overflow-x: auto;
            margin: 1em 0;
        }

        .response-container pre code {
            background: none;
            padding: 0;
            border-radius: 0;
        }

        .response-container a {
            color: var(--link-color);
            text-decoration: none;
        }

        .response-container a:hover {
            text-decoration: underline;
        }

        .response-container strong,
        .response-container b {
            font-weight: 600;
            color: var(--text-color);
        }

        .response-container em,
        .response-container i {
            font-style: italic;
        }

        .response-container hr {
            border: none;
            border-top: 1px solid var(--border-color);
            margin: 2em 0;
        }

        .response-container table {
            border-collapse: collapse;
            width: 100%;
            margin: 1em 0;
        }

        .response-container th,
        .response-container td {
            border: 1px solid var(--border-color);
            padding: 0.5em;
            text-align: left;
        }

        .response-container th {
            background: var(--input-background);
            font-weight: 600;
        }

        .response-container::-webkit-scrollbar {
            width: 8px;
        }

        .response-container::-webkit-scrollbar-track {
            background: var(--scrollbar-track);
            border-radius: 4px;
        }

        .response-container::-webkit-scrollbar-thumb {
            background: var(--scrollbar-thumb);
            border-radius: 4px;
        }

        .response-container::-webkit-scrollbar-thumb:hover {
            background: var(--scrollbar-thumb-hover);
        }

        .text-input-container {
            display: flex;
            gap: 10px;
            margin-top: 10px;
            align-items: center;
        }

        .text-input-container input {
            flex: 1;
            background: var(--input-background);
            color: var(--text-color);
            border: 1px solid var(--button-border);
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 14px;
        }

        .text-input-container input:focus {
            outline: none;
            border-color: var(--focus-border-color);
            box-shadow: 0 0 0 3px var(--focus-box-shadow);
            background: var(--input-focus-background);
        }

        .text-input-container input::placeholder {
            color: var(--placeholder-color);
        }

        .text-input-container button {
            background: transparent;
            color: var(--start-button-background);
            border: none;
            padding: 0;
            border-radius: 100px;
        }

        .text-input-container button:hover {
            background: var(--text-input-button-hover);
        }

        .nav-button {
            background: transparent;
            color: white;
            border: none;
            padding: 4px;
            border-radius: 50%;
            font-size: 12px;
            display: flex;
            align-items: center;
            width: 36px;
            height: 36px;
            justify-content: center;
        }

        .nav-button:hover {
            background: rgba(255, 255, 255, 0.1);
        }

        .nav-button:disabled {
            opacity: 0.3;
        }

        .nav-button svg {
            stroke: white !important;
        }

        .response-counter {
            font-size: 12px;
            color: var(--description-color);
            white-space: nowrap;
            min-width: 60px;
            text-align: center;
        }

        .save-button {
            background: transparent;
            color: var(--start-button-background);
            border: none;
            padding: 4px;
            border-radius: 50%;
            font-size: 12px;
            display: flex;
            align-items: center;
            width: 36px;
            height: 36px;
            justify-content: center;
            cursor: pointer;
        }

        .save-button:hover {
            background: rgba(255, 255, 255, 0.1);
        }

        .save-button.saved {
            color: #4caf50;
        }

        .save-button svg {
            stroke: currentColor !important;
        }
    `;

    static properties = {
        responses: { type: Array },
        currentResponseIndex: { type: Number },
        selectedProfile: { type: String },
        onSendText: { type: Function },
        shouldAnimateResponse: { type: Boolean },
        savedResponses: { type: Array },
    };

    constructor() {
        super();
        this.responses = [];
        this.currentResponseIndex = -1;
        this.selectedProfile = 'interview';
        this.onSendText = () => { };
        this._lastAnimatedWordCount = 0;
        // Load saved responses from localStorage
        try {
            this.savedResponses = JSON.parse(localStorage.getItem('savedResponses') || '[]');
        } catch (e) {
            this.savedResponses = [];
        }
        this._agentUnsub = null;
        this._agentState = { job: null, steps: {}, report: null, connected: false };
    // Deprecated full-report fetch state removed
        this._lastSnippetApplied = null;
    }

    getProfileNames() {
        return {
            interview: 'Job Interview',
            sales: 'Sales Call',
            meeting: 'Business Meeting',
            presentation: 'Presentation',
            negotiation: 'Negotiation',
            exam: 'Exam Assistant',
        };
    }

    getCurrentResponse() {
        const profileNames = this.getProfileNames();
        return this.responses.length > 0 && this.currentResponseIndex >= 0
            ? this.responses[this.currentResponseIndex]
            : `Hey, Im listening to your ${profileNames[this.selectedProfile] || 'session'}?`;
    }

    renderMarkdown(content) {
        // Check if marked is available
        if (typeof window !== 'undefined' && window.marked) {
            try {
                // Configure marked for better security and formatting
                window.marked.setOptions({
                    breaks: true,
                    gfm: true,
                    sanitize: false, // We trust the AI responses
                });
                let rendered = window.marked.parse(content);
                rendered = this.wrapWordsInSpans(rendered);
                return rendered;
            } catch (error) {
                console.warn('Error parsing markdown:', error);
                return content; // Fallback to plain text
            }
        }
        console.log('Marked not available, using plain text');
        return content; // Fallback if marked is not available
    }

    wrapWordsInSpans(html) {
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        const tagsToSkip = ['PRE'];

        function wrap(node) {
            if (node.nodeType === Node.TEXT_NODE && node.textContent.trim() && !tagsToSkip.includes(node.parentNode.tagName)) {
                const words = node.textContent.split(/(\s+)/);
                const frag = document.createDocumentFragment();
                words.forEach(word => {
                    if (word.trim()) {
                        const span = document.createElement('span');
                        span.setAttribute('data-word', '');
                        span.textContent = word;
                        frag.appendChild(span);
                    } else {
                        frag.appendChild(document.createTextNode(word));
                    }
                });
                node.parentNode.replaceChild(frag, node);
            } else if (node.nodeType === Node.ELEMENT_NODE && !tagsToSkip.includes(node.tagName)) {
                Array.from(node.childNodes).forEach(wrap);
            }
        }
        Array.from(doc.body.childNodes).forEach(wrap);
        return doc.body.innerHTML;
    }

    getResponseCounter() {
        return this.responses.length > 0 ? `${this.currentResponseIndex + 1}/${this.responses.length}` : '';
    }

    navigateToPreviousResponse() {
        if (this.currentResponseIndex > 0) {
            this.currentResponseIndex--;
            this.dispatchEvent(
                new CustomEvent('response-index-changed', {
                    detail: { index: this.currentResponseIndex },
                })
            );
            this.requestUpdate();
        }
    }

    navigateToNextResponse() {
        if (this.currentResponseIndex < this.responses.length - 1) {
            this.currentResponseIndex++;
            this.dispatchEvent(
                new CustomEvent('response-index-changed', {
                    detail: { index: this.currentResponseIndex },
                })
            );
            this.requestUpdate();
        }
    }

    scrollResponseUp() {
        const container = this.shadowRoot.querySelector('.response-container');
        if (container) {
            const scrollAmount = container.clientHeight * 0.3; // Scroll 30% of container height
            container.scrollTop = Math.max(0, container.scrollTop - scrollAmount);
        }
    }

    scrollResponseDown() {
        const container = this.shadowRoot.querySelector('.response-container');
        if (container) {
            const scrollAmount = container.clientHeight * 0.3; // Scroll 30% of container height
            container.scrollTop = Math.min(container.scrollHeight - container.clientHeight, container.scrollTop + scrollAmount);
        }
    }

    loadFontSize() {
        const fontSize = localStorage.getItem('fontSize');
        if (fontSize !== null) {
            const fontSizeValue = parseInt(fontSize, 10) || 20;
            const root = document.documentElement;
            root.style.setProperty('--response-font-size', `${fontSizeValue}px`);
        }
    }

    connectedCallback() {
        super.connectedCallback();

        // Load and apply font size
        this.loadFontSize();

        // Set up IPC listeners for keyboard shortcuts
        if (window.require) {
            const { ipcRenderer } = window.require('electron');

            this.handlePreviousResponse = () => {
                console.log('Received navigate-previous-response message');
                this.navigateToPreviousResponse();
            };

            this.handleNextResponse = () => {
                console.log('Received navigate-next-response message');
                this.navigateToNextResponse();
            };

            this.handleScrollUp = () => {
                console.log('Received scroll-response-up message');
                this.scrollResponseUp();
            };

            this.handleScrollDown = () => {
                console.log('Received scroll-response-down message');
                this.scrollResponseDown();
            };

            ipcRenderer.on('navigate-previous-response', this.handlePreviousResponse);
            ipcRenderer.on('navigate-next-response', this.handleNextResponse);
            ipcRenderer.on('scroll-response-up', this.handleScrollUp);
            ipcRenderer.on('scroll-response-down', this.handleScrollDown);
        }

        // Start agent stream (fire-and-forget)
        agentConfigure({}).catch(e => console.warn('Agent configure failed', e));
        this._agentUnsub = agentSubscribe(async st => {
            this._agentState = st;
            // No longer performing follow-up fetch; report.final payload is authoritative
            this.requestUpdate();
        });
    }

    _sanitizeSnippet(html) {
        if (!html || typeof html !== 'string') return '';
        // Basic safety: strip script/style tags just in case
        return html.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
            .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');
    }

    // Removed _fetchReportOnce and _scheduleReportFetch (deprecated full report endpoint)

    disconnectedCallback() {
        super.disconnectedCallback();

        // Clean up IPC listeners
        if (window.require) {
            const { ipcRenderer } = window.require('electron');
            if (this.handlePreviousResponse) {
                ipcRenderer.removeListener('navigate-previous-response', this.handlePreviousResponse);
            }
            if (this.handleNextResponse) {
                ipcRenderer.removeListener('navigate-next-response', this.handleNextResponse);
            }
            if (this.handleScrollUp) {
                ipcRenderer.removeListener('scroll-response-up', this.handleScrollUp);
            }
            if (this.handleScrollDown) {
                ipcRenderer.removeListener('scroll-response-down', this.handleScrollDown);
            }
        }

        if (this._agentUnsub) { try { this._agentUnsub(); } catch (_) { } this._agentUnsub = null; }
    }

    async handleSendText() {
        const textInput = this.shadowRoot.querySelector('#textInput');
        if (textInput && textInput.value.trim()) {
            const message = textInput.value.trim();
            textInput.value = '';
            try {
                await agentRunJob(message, [], this.selectedProfile);
            } catch (e) {
                console.error('runJob error', e);
            }
        }
    }

    handleTextKeydown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this.handleSendText();
        }
    }

    scrollToBottom() {
        setTimeout(() => {
            const container = this.shadowRoot.querySelector('.response-container');
            if (container) {
                container.scrollTop = container.scrollHeight;
            }
        }, 0);
    }

    saveCurrentResponse() {
        const currentResponse = this.getCurrentResponse();
        if (currentResponse && !this.isResponseSaved()) {
            this.savedResponses = [
                ...this.savedResponses,
                {
                    response: currentResponse,
                    timestamp: new Date().toISOString(),
                    profile: this.selectedProfile,
                },
            ];
            // Save to localStorage for persistence
            localStorage.setItem('savedResponses', JSON.stringify(this.savedResponses));
            this.requestUpdate();
        }
    }

    isResponseSaved() {
        const currentResponse = this.getCurrentResponse();
        return this.savedResponses.some(saved => saved.response === currentResponse);
    }

    firstUpdated() { super.firstUpdated(); }
    updated(changedProperties) {
        super.updated(changedProperties);
        // Apply snippet HTML when present
        const report = this._agentState.report;
        if (report && report.snippet && report.snippet !== this._lastSnippetApplied) {
            const cont = this.shadowRoot && this.shadowRoot.querySelector('#finalReportSnippet');
            if (cont) {
                cont.innerHTML = this._sanitizeSnippet(report.snippet);
                this._lastSnippetApplied = report.snippet;
            }
        }
    // Full report iframe logic removed
    }

    // Add small header bar to show running job and profile
    render() {
        const snapshot = agentGetSnapshot();
        const currentJobProfile = snapshot?.job?.profile || this.selectedProfile;
        const currentResponse = this.getCurrentResponse();
        const responseCounter = this.getResponseCounter();
        const isSaved = this.isResponseSaved();
        const job = this._agentState.job || {};
        const report = this._agentState.report;
        const running = job.state === 'running';
        const terminal = ['completed', 'failed', 'timeout', 'canceled'].includes(job.state);
        const status = this._agentState.connectionStatus || (this._agentState.connected ? 'connected' : 'idle');
        const reconnectInfo = (status === 'reconnecting') ? ` (retry ${this._agentState.reconnectAttempts})` : '';
        const statusColors = { connected: '#2ecc71', connecting: '#f1c40f', reconnecting: '#e67e22', stalled: '#e67e22', error: '#e74c3c', closed: '#95a5a6', idle: '#7f8c8d' };
        const color = statusColors[status] || '#7f8c8d';
        return html`
            <div style="position:absolute;top:6px;right:8px;font-size:11px;display:flex;align-items:center;gap:6px;z-index:10;">
            <span style="display:inline-flex;align-items:center;gap:4px;padding:2px 6px;border:1px solid ${color};border-radius:12px;color:${color};background:rgba(255,255,255,0.05);">
                <span style="width:8px;height:8px;border-ra dius:50%;background:${color};"></span>
                WS ${status}${reconnectInfo}
            </span>
            ${status === 'error' || status === 'closed' ? html`<button style="background:transparent;border:1px solid ${color};color:${color};border-radius:10px;padding:2px 6px;font-size:10px;cursor:pointer;" @click=${() => window.shadowAgent && window.shadowAgent.forceReconnect()}>Retry</button>` : ''}
            </div>
            <div style="padding:4px 8px;font-size:12px;color:var(--description-color);display:flex;gap:12px;align-items:center;">
                <span>Profile: <strong>${currentJobProfile}</strong></span>
                ${snapshot.job && snapshot.job.state === 'running' ? html`<span>Running job ...</span>` : ''}
            </div>
            <div class="response-container" id="responseContainer">
                ${running ? html`<div style="font-size:12px;color:var(--description-color);margin-bottom:8px;">Running job... ${job.completed_steps || 0}/${job.total_steps || 0} (${Math.round((job.progress_ratio || 0) * 100)}%)</div>` : ''}
                ${job.state && !running ? html`<div style="font-size:12px;color:var(--description-color);margin-bottom:8px;">Job state: ${job.state}</div>` : ''}
                                                ${report ? html`<div class="final-report"><h4>Final Report</h4>
                                                    <div id="finalReportSnippet" style="font-size:12px;line-height:1.4;white-space:normal;"></div>
                                                </div>`: ''}
                <!-- Response rendering temporarily disabled to avoid DOM conflicts -->
            </div>
            <div class="text-input-container">
                <button class="nav-button" @click=${this.navigateToPreviousResponse} ?disabled=${this.currentResponseIndex <= 0}>
                    <?xml version="1.0" encoding="UTF-8"?><svg
                        width="24px"
                        height="24px"
                        stroke-width="1.7"
                        viewBox="0 0 24 24"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                        color="#ffffff"
                    >
                        <path d="M15 6L9 12L15 18" stroke="#ffffff" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"></path>
                    </svg>
                </button>

                ${this.responses.length > 0 ? html` <span class="response-counter">${responseCounter}</span> ` : ''}

                <button
                    class="save-button ${isSaved ? 'saved' : ''}"
                    @click=${this.saveCurrentResponse}
                    title="${isSaved ? 'Response saved' : 'Save this response'}"
                >
                    <?xml version="1.0" encoding="UTF-8"?><svg
                        width="24px"
                        height="24px"
                        stroke-width="1.7"
                        viewBox="0 0 24 24"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                    >
                        <path
                            d="M5 20V5C5 3.89543 5.89543 3 7 3H16.1716C16.702 3 17.2107 3.21071 17.5858 3.58579L19.4142 5.41421C19.7893 5.78929 20 6.29799 20 6.82843V20C20 21.1046 19.1046 22 18 22H7C5.89543 22 5 21 5 20Z"
                            stroke="currentColor"
                            stroke-width="1.7"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                        ></path>
                        <path d="M15 22V13H9V22" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"></path>
                        <path d="M9 3V8H15" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"></path>
                    </svg>
                </button>

                <input type="text" id="textInput" placeholder="Type a message to the AI..." @keydown=${this.handleTextKeydown} />

                <button class="nav-button" @click=${this.navigateToNextResponse} ?disabled=${this.currentResponseIndex >= this.responses.length - 1}>
                    <?xml version="1.0" encoding="UTF-8"?><svg
                        width="24px"
                        height="24px"
                        stroke-width="1.7"
                        viewBox="0 0 24 24"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                        color="#ffffff"
                    >
                        <path d="M9 6L15 12L9 18" stroke="#ffffff" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"></path>
                    </svg>
                </button>
            </div>
        `;
    }
}

customElements.define('assistant-view', AssistantView);
