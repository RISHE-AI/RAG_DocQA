/* ═══════════════════════════════════════════════════════════════════
   DocQA Studio — Modern Interactive Client Application
   ═══════════════════════════════════════════════════════════════════ */

// ─── Markdown Parser Configuration ───
if (typeof marked !== 'undefined') {
  marked.setOptions({
    breaks: true,
    gfm: true,
    highlight: function(code, lang) {
      if (typeof hljs !== 'undefined') {
        if (lang && hljs.getLanguage(lang)) {
          return hljs.highlight(code, { language: lang }).value;
        }
        return hljs.highlightAuto(code).value;
      }
      return code;
    }
  });
}

// ─── Application State ───
const state = {
  documentLoaded: false,
  activeDocument: null,
  availableModels: [],
  selectedModel: '',
  isProcessing: false,
  messages: [],
  activeCitationChunk: null
};

// ─── DOM References ───
const elements = {
  // Navigation
  modelPickerBtn: document.getElementById('modelPickerBtn'),
  modelDropdownMenu: document.getElementById('modelDropdownMenu'),
  currentModelLabel: document.getElementById('currentModelLabel'),
  modelList: document.getElementById('modelList'),
  groqStatusPill: document.getElementById('groqStatusPill'),
  faissStatusPill: document.getElementById('faissStatusPill'),
  exportChatBtn: document.getElementById('exportChatBtn'),
  clearChatBtn: document.getElementById('clearChatBtn'),
  sidebarToggleBtn: document.getElementById('sidebarToggleBtn'),
  appSidebar: document.getElementById('appSidebar'),

  // Sidebar Document Elements
  dropzone: document.getElementById('dropzone'),
  fileInput: document.getElementById('fileInput'),
  uploadProgressContainer: document.getElementById('uploadProgressContainer'),
  progressFill: document.getElementById('progressFill'),
  progressStage: document.getElementById('progressStage'),
  progressPercent: document.getElementById('progressPercent'),
  docStatusBadge: document.getElementById('docStatusBadge'),
  docMetaContainer: document.getElementById('docMetaContainer'),
  docCardActions: document.getElementById('docCardActions'),
  clearDocBtn: document.getElementById('clearDocBtn'),

  // Chat Elements
  messagesViewport: document.getElementById('messagesViewport'),
  welcomeHero: document.getElementById('welcomeHero'),
  chatStream: document.getElementById('chatStream'),
  scrollBottomBtn: document.getElementById('scrollBottomBtn'),
  chatForm: document.getElementById('chatForm'),
  questionInput: document.getElementById('questionInput'),
  sendBtn: document.getElementById('sendBtn'),
  attachBtn: document.getElementById('attachBtn'),
  inputDocNotice: document.getElementById('inputDocNotice'),

  // Citation Modal
  citationModal: document.getElementById('citationModal'),
  modalPageTitle: document.getElementById('modalPageTitle'),
  modalSimilarity: document.getElementById('modalSimilarity'),
  modalChunkText: document.getElementById('modalChunkText'),
  closeCitationModal: document.getElementById('closeCitationModal'),
  doneCitationBtn: document.getElementById('doneCitationBtn'),
  copyCitationBtn: document.getElementById('copyCitationBtn'),

  // Toast Container
  toastContainer: document.getElementById('toastContainer')
};

// ─── Initialize Application ───
document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  checkApplicationStatus();
});

// ─── Event Setup ───
function setupEventListeners() {
  // 1. File Upload Drag & Drop
  elements.dropzone.addEventListener('click', () => elements.fileInput.click());
  elements.attachBtn.addEventListener('click', () => elements.fileInput.click());
  elements.fileInput.addEventListener('change', handleFileSelect);

  elements.dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    elements.dropzone.classList.add('drag-active');
  });

  elements.dropzone.addEventListener('dragleave', () => {
    elements.dropzone.classList.remove('drag-active');
  });

  elements.dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    elements.dropzone.classList.remove('drag-active');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processSelectedFile(e.dataTransfer.files[0]);
    }
  });

  // Global window drag & drop prevention
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('drop', (e) => e.preventDefault());

  // 2. Chat Form & Auto-growing textarea
  elements.chatForm.addEventListener('submit', handleQuestionSubmit);
  elements.questionInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleQuestionSubmit(e);
    }
  });

  elements.questionInput.addEventListener('input', autoResizeTextarea);

  // 3. Model Picker Dropdown
  elements.modelPickerBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    elements.modelDropdownMenu.classList.toggle('show');
  });

  document.addEventListener('click', () => {
    elements.modelDropdownMenu.classList.remove('show');
  });

  elements.modelDropdownMenu.addEventListener('click', (e) => e.stopPropagation());

  // 4. Sidebar Toggle (Mobile / Desktop)
  elements.sidebarToggleBtn.addEventListener('click', () => {
    elements.appSidebar.classList.toggle('collapsed');
  });

  // 5. Document Management
  elements.clearDocBtn.addEventListener('click', clearDocumentDatabase);

  // 6. Chat Actions
  elements.clearChatBtn.addEventListener('click', clearConversation);
  elements.exportChatBtn.addEventListener('click', exportTranscript);

  // 7. Scroll to Bottom Button
  elements.messagesViewport.addEventListener('scroll', handleViewportScroll);
  elements.scrollBottomBtn.addEventListener('click', () => {
    elements.messagesViewport.scrollTo({ top: elements.messagesViewport.scrollHeight, behavior: 'smooth' });
  });

  // 8. Quick Prompt Chips
  document.querySelectorAll('.prompt-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const q = chip.dataset.question;
      if (!q) return;
      elements.questionInput.value = q;
      autoResizeTextarea();
      elements.questionInput.focus();
      if (state.documentLoaded && !state.isProcessing) {
        handleQuestionSubmit(new Event('submit'));
      } else if (!state.documentLoaded) {
        showToast('Please upload a document first before asking.', 'info');
      }
    });
  });

  // 9. Citation Modal Close
  elements.closeCitationModal.addEventListener('click', closeCitation);
  elements.doneCitationBtn.addEventListener('click', closeCitation);
  elements.citationModal.addEventListener('click', (e) => {
    if (e.target === elements.citationModal) closeCitation();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && elements.citationModal.classList.contains('show')) {
      closeCitation();
    }
  });

  elements.copyCitationBtn.addEventListener('click', () => {
    if (state.activeCitationChunk) {
      copyToClipboard(state.activeCitationChunk.text, elements.copyCitationBtn, 'Copied Excerpt');
    }
  });
}

// ─── Status & Telemetry Check ───
async function checkApplicationStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();

    if (data.success) {
      state.documentLoaded = data.loaded;
      state.activeDocument = data.document;
      state.availableModels = data.availableModels || [];
      state.selectedModel = data.activeModel || (state.availableModels[0] || 'openai/gpt-oss-120b');

      renderModelSelector();
      updateTelemetryBadges(data);
      updateDocumentCard(data.loaded ? data.document : null);
    }
  } catch (err) {
    console.warn('Status check warning:', err);
    updateTelemetryBadges({ groqConfigured: false });
  }
}

function updateTelemetryBadges(data) {
  // Groq status
  if (data.groqConfigured) {
    elements.groqStatusPill.className = 'telemetry-pill is-ready';
    elements.groqStatusPill.querySelector('.pill-text').textContent = 'Groq: Online';
  } else {
    elements.groqStatusPill.className = 'telemetry-pill is-warn';
    elements.groqStatusPill.querySelector('.pill-text').textContent = 'Groq: Key Missing';
  }

  // Vector status
  if (data.loaded) {
    elements.faissStatusPill.className = 'telemetry-pill is-ready';
    elements.faissStatusPill.querySelector('.pill-text').textContent = `FAISS: ${data.document.total_chunks || 0} Chunks`;
    elements.inputDocNotice.textContent = `${data.document.filename || 'Document'} loaded`;
    elements.inputDocNotice.style.color = '#fb923c';
  } else {
    elements.faissStatusPill.className = 'telemetry-pill';
    elements.faissStatusPill.querySelector('.pill-text').textContent = 'FAISS: 384-dim';
    elements.inputDocNotice.textContent = 'No document loaded';
    elements.inputDocNotice.style.color = 'var(--text-dim)';
  }
}

function renderModelSelector() {
  // Label
  const cleanName = state.selectedModel.split('/').pop();
  elements.currentModelLabel.textContent = cleanName;

  // List
  elements.modelList.innerHTML = '';
  state.availableModels.forEach(m => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `model-option-btn ${m === state.selectedModel ? 'active' : ''}`;
    
    const nameSpan = document.createElement('span');
    nameSpan.textContent = m;

    const checkSpan = document.createElement('span');
    checkSpan.textContent = m === state.selectedModel ? '✓' : '';

    btn.appendChild(nameSpan);
    btn.appendChild(checkSpan);

    btn.addEventListener('click', () => {
      state.selectedModel = m;
      elements.currentModelLabel.textContent = m.split('/').pop();
      elements.modelDropdownMenu.classList.remove('show');
      renderModelSelector();
      showToast(`Active model switched to ${m}`, 'info');
    });

    elements.modelList.appendChild(btn);
  });
}

function updateDocumentCard(meta) {
  if (meta && state.documentLoaded) {
    elements.docStatusBadge.textContent = 'Active';
    elements.docStatusBadge.className = 'badge-status loaded';

    const fileSizeStr = meta.file_size ? `${(meta.file_size / 1024).toFixed(1)} KB` : 'N/A';

    elements.docMetaContainer.innerHTML = `
      <div class="doc-name-banner" title="${escapeHtml(meta.filename)}">
        <span class="doc-file-icon">📄</span>
        <span class="doc-name-text">${escapeHtml(meta.filename)}</span>
      </div>
      <div class="doc-info-grid">
        <div class="meta-box">
          <span class="meta-title">Total Pages</span>
          <span class="meta-val">${meta.total_pages || 1}</span>
        </div>
        <div class="meta-box">
          <span class="meta-title">Chunks</span>
          <span class="meta-val">${meta.total_chunks || 0}</span>
        </div>
        <div class="meta-box">
          <span class="meta-title">File Size</span>
          <span class="meta-val">${fileSizeStr}</span>
        </div>
        <div class="meta-box">
          <span class="meta-title">Dimension</span>
          <span class="meta-val">384d</span>
        </div>
      </div>
    `;
    elements.docCardActions.style.display = 'block';
  } else {
    elements.docStatusBadge.textContent = 'Not Loaded';
    elements.docStatusBadge.className = 'badge-status';
    elements.docMetaContainer.innerHTML = `
      <div class="empty-doc-placeholder">
        <div class="placeholder-icon">📑</div>
        <p>No document loaded</p>
        <span>Upload a file above to start questioning</span>
      </div>
    `;
    elements.docCardActions.style.display = 'none';
  }
}

// ─── File Upload Logic ───
function handleFileSelect(e) {
  const files = e.target.files;
  if (!files || files.length === 0) return;
  processSelectedFile(files[0]);
  elements.fileInput.value = '';
}

async function processSelectedFile(file) {
  const ext = file.name.split('.').pop().toLowerCase();
  if (!['pdf', 'txt', 'md'].includes(ext)) {
    showToast('Unsupported format! Please upload PDF, TXT, or MD.', 'error');
    return;
  }

  if (file.size > 100 * 1024 * 1024) {
    showToast('File size exceeds the 100MB limit.', 'error');
    return;
  }

  // Show animated progress UI
  elements.uploadProgressContainer.classList.add('show');
  updateProgress(20, 'Uploading document to server…');

  const formData = new FormData();
  formData.append('file', file);

  try {
    updateProgress(50, 'Extracting text and structure…');

    // Simulate progressive processing stage
    const timer = setTimeout(() => {
      updateProgress(80, 'Encoding 384-dim FAISS embeddings…');
    }, 1500);

    const response = await fetch('/api/upload', {
      method: 'POST',
      body: formData
    });

    clearTimeout(timer);
    const data = await response.json();

    if (data.success) {
      updateProgress(100, 'Vector indexing complete!');
      setTimeout(() => {
        elements.uploadProgressContainer.classList.remove('show');
        elements.progressFill.style.width = '0%';
      }, 1200);

      state.documentLoaded = true;
      state.activeDocument = data.metadata;

      updateDocumentCard(data.metadata);
      checkApplicationStatus();

      // Hide welcome hero on successful upload
      elements.welcomeHero.style.display = 'none';
      showToast(`Successfully indexed "${file.name}"!`, 'success');

      // Provide automated greeting if chat is empty
      if (elements.chatStream.children.length === 0) {
        addAssistantMessage({
          answer: `**Document Ready!** I have parsed and indexed **${data.metadata.filename}** (${data.metadata.total_pages} pages, ${data.metadata.total_chunks} semantic chunks).\n\nYou can ask any question about this document, or click one of the **Quick Prompts** in the sidebar.`,
          sources: [1],
          chunks: [],
          model: state.selectedModel,
          metrics: { total_ms: 12 }
        });
      }
    } else {
      elements.uploadProgressContainer.classList.remove('show');
      showToast(data.message || 'File processing failed.', 'error');
    }
  } catch (err) {
    elements.uploadProgressContainer.classList.remove('show');
    showToast(`Upload error: ${err.message}`, 'error');
  }
}

function updateProgress(pct, stage) {
  elements.progressFill.style.width = `${pct}%`;
  elements.progressPercent.textContent = `${pct}%`;
  elements.progressStage.textContent = stage;
}

// ─── Question Answering Workflow ───
async function handleQuestionSubmit(e) {
  if (e && e.preventDefault) e.preventDefault();

  const question = elements.questionInput.value.trim();
  if (!question || state.isProcessing) return;

  if (!state.documentLoaded) {
    showToast('Please upload a document before asking questions.', 'error');
    elements.dropzone.classList.add('drag-active');
    setTimeout(() => elements.dropzone.classList.remove('drag-active'), 1000);
    return;
  }

  // Clear input & reset height
  elements.questionInput.value = '';
  autoResizeTextarea();

  // Hide welcome hero
  elements.welcomeHero.style.display = 'none';

  // Render user message
  addUserMessage(question);

  // Set processing state
  state.isProcessing = true;
  elements.sendBtn.disabled = true;
  showTypingIndicator();
  scrollToBottom();

  const startTime = performance.now();

  try {
    const response = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: question,
        model: state.selectedModel
      })
    });

    const data = await response.json();
    removeTypingIndicator();

    if (data.success) {
      addAssistantMessage(data);
    } else {
      addErrorMessage(data.message || 'Failed to synthesize answer.');
    }
  } catch (err) {
    removeTypingIndicator();
    addErrorMessage(`Connection error: ${err.message}`);
  } finally {
    state.isProcessing = false;
    elements.sendBtn.disabled = false;
    elements.questionInput.focus();
    scrollToBottom();
  }
}

// ─── Message Rendering ───
function addUserMessage(text) {
  const row = document.createElement('div');
  row.className = 'message-row user';

  const wrapper = document.createElement('div');
  wrapper.className = 'msg-content-wrapper';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.textContent = text;

  wrapper.appendChild(bubble);

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = '👤';

  row.appendChild(wrapper);
  row.appendChild(avatar);

  elements.chatStream.appendChild(row);
  state.messages.push({ role: 'user', content: text, timestamp: new Date() });
}

function addAssistantMessage(data) {
  const row = document.createElement('div');
  row.className = 'message-row assistant';

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.innerHTML = `
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M12 2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2 2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/>
      <rect x="4" y="8" width="16" height="12" rx="2"/>
      <circle cx="9" cy="13" r="1"/>
      <circle cx="15" cy="13" r="1"/>
    </svg>
  `;

  const wrapper = document.createElement('div');
  wrapper.className = 'msg-content-wrapper';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';

  // 1. Markdown Content
  const markdownContainer = document.createElement('div');
  markdownContainer.className = 'msg-markdown';
  if (typeof marked !== 'undefined') {
    markdownContainer.innerHTML = marked.parse(data.answer || '');
  } else {
    markdownContainer.textContent = data.answer || '';
  }

  // Inject copy button onto code snippets
  markdownContainer.querySelectorAll('pre').forEach(pre => {
    const code = pre.querySelector('code');
    const copyCodeBtn = document.createElement('button');
    copyCodeBtn.type = 'button';
    copyCodeBtn.className = 'action-btn';
    copyCodeBtn.style.cssText = 'position: absolute; top: 6px; right: 6px; font-size: 0.7rem;';
    copyCodeBtn.innerHTML = '📋 Copy';
    pre.style.position = 'relative';
    copyCodeBtn.addEventListener('click', () => {
      copyToClipboard(code ? code.innerText : pre.innerText, copyCodeBtn, 'Copied');
    });
    pre.appendChild(copyCodeBtn);
  });

  bubble.appendChild(markdownContainer);

  // 2. Source Citation Badges
  if (data.sources && data.sources.length > 0) {
    const citationsBar = document.createElement('div');
    citationsBar.className = 'citations-bar';

    const label = document.createElement('span');
    label.className = 'citation-header-label';
    label.innerHTML = '<span>📚 Verified Sources:</span>';
    citationsBar.appendChild(label);

    data.sources.forEach(page => {
      const pill = document.createElement('button');
      pill.type = 'button';
      pill.className = 'citation-pill';
      pill.innerHTML = `<span>Page ${page}</span> <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>`;

      // Find matching chunk if available
      const matchingChunk = (data.chunks || []).find(c => (c.pages || []).includes(page)) || (data.chunks && data.chunks[0]);

      pill.addEventListener('click', () => {
        openCitation(page, matchingChunk);
      });

      citationsBar.appendChild(pill);
    });

    bubble.appendChild(citationsBar);
  }

  // 3. Telemetry & Chunk Inspector Accordion
  if (data.chunks && data.chunks.length > 0) {
    const accordion = document.createElement('div');
    accordion.className = 'inspector-accordion';

    const toggleBtn = document.createElement('button');
    toggleBtn.type = 'button';
    toggleBtn.className = 'inspector-toggle';
    const retMs = data.metrics ? `${data.metrics.retrieval_ms}ms` : '<20ms';
    toggleBtn.innerHTML = `
      <span>🔍 Retrieval Inspector (${data.chunks.length} chunks • ${retMs})</span>
      <span class="acc-arrow">▼</span>
    `;

    const panel = document.createElement('div');
    panel.className = 'inspector-panel';

    // Metrics summary
    const statsRow = document.createElement('div');
    statsRow.className = 'telemetry-stats-row';
    statsRow.innerHTML = `
      <div class="telemetry-stat-item">Model: <span>${escapeHtml(data.model || state.selectedModel)}</span></div>
      <div class="telemetry-stat-item">Retrieval: <span>${retMs}</span></div>
      <div class="telemetry-stat-item">Total Latency: <span>${data.metrics ? `${data.metrics.total_ms}ms` : 'N/A'}</span></div>
    `;
    panel.appendChild(statsRow);

    // Chunks List
    const chunksList = document.createElement('div');
    chunksList.className = 'chunks-preview-list';

    data.chunks.forEach((chunk, i) => {
      const box = document.createElement('div');
      box.className = 'chunk-preview-box';
      const pgStr = (chunk.pages || [1]).join(', ');
      box.innerHTML = `
        <div class="chunk-box-header">
          <span>Chunk #${chunk.id || (i + 1)} (Page ${pgStr})</span>
          <strong>${chunk.similarity_pct || '90'}% Match</strong>
        </div>
        <div class="chunk-box-snippet">${escapeHtml(chunk.preview || chunk.text.slice(0, 150) + '…')}</div>
      `;
      box.style.cursor = 'pointer';
      box.addEventListener('click', () => openCitation(chunk.pages[0], chunk));
      chunksList.appendChild(box);
    });

    panel.appendChild(chunksList);

    toggleBtn.addEventListener('click', () => {
      panel.classList.toggle('open');
      toggleBtn.querySelector('.acc-arrow').textContent = panel.classList.contains('open') ? '▲' : '▼';
    });

    accordion.appendChild(toggleBtn);
    accordion.appendChild(panel);
    bubble.appendChild(accordion);
  }

  // 4. Action Toolbar
  const actionBar = document.createElement('div');
  actionBar.className = 'msg-action-bar';

  const copyBtn = document.createElement('button');
  copyBtn.type = 'button';
  copyBtn.className = 'action-btn';
  copyBtn.innerHTML = '📋 Copy Answer';
  copyBtn.addEventListener('click', () => {
    copyToClipboard(data.answer, copyBtn, '✓ Copied');
  });

  const downloadBtn = document.createElement('button');
  downloadBtn.type = 'button';
  downloadBtn.className = 'action-btn';
  downloadBtn.innerHTML = '📥 Download .md';
  downloadBtn.addEventListener('click', () => {
    downloadTextFile('answer.md', data.answer);
  });

  const helpfulBtn = document.createElement('button');
  helpfulBtn.type = 'button';
  helpfulBtn.className = 'action-btn';
  helpfulBtn.innerHTML = '👍 Helpful';
  helpfulBtn.addEventListener('click', () => {
    helpfulBtn.classList.toggle('active');
    showToast('Feedback noted. Thank you!', 'info');
  });

  actionBar.appendChild(copyBtn);
  actionBar.appendChild(downloadBtn);
  actionBar.appendChild(helpfulBtn);

  wrapper.appendChild(bubble);
  wrapper.appendChild(actionBar);

  row.appendChild(avatar);
  row.appendChild(wrapper);

  elements.chatStream.appendChild(row);
  state.messages.push({
    role: 'assistant',
    content: data.answer,
    sources: data.sources || [],
    model: data.model || state.selectedModel,
    timestamp: new Date()
  });
}

function addErrorMessage(errorText) {
  const row = document.createElement('div');
  row.className = 'message-row error';

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = '⚠️';

  const wrapper = document.createElement('div');
  wrapper.className = 'msg-content-wrapper';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.innerHTML = `<strong>Error:</strong> ${escapeHtml(errorText)}`;

  wrapper.appendChild(bubble);
  row.appendChild(avatar);
  row.appendChild(wrapper);

  elements.chatStream.appendChild(row);
}

// ─── Typing Indicator ───
function showTypingIndicator() {
  const row = document.createElement('div');
  row.className = 'message-row assistant';
  row.id = 'typingIndicatorRow';

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = '🤖';

  const wrapper = document.createElement('div');
  wrapper.className = 'msg-content-wrapper';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble typing-box';
  bubble.innerHTML = `
    <div class="typing-dots">
      <span></span>
      <span></span>
      <span></span>
    </div>
    <span class="typing-status-text">Searching semantic vectors & synthesizing response…</span>
  `;

  wrapper.appendChild(bubble);
  row.appendChild(avatar);
  row.appendChild(wrapper);

  elements.chatStream.appendChild(row);
}

function removeTypingIndicator() {
  const row = document.getElementById('typingIndicatorRow');
  if (row) row.remove();
}

// ─── Citation Excerpt Modal ───
function openCitation(page, chunk) {
  state.activeCitationChunk = chunk;
  elements.modalPageTitle.textContent = `Source Citation — Page ${page}`;
  
  if (chunk && chunk.similarity_pct) {
    elements.modalSimilarity.textContent = `Match Relevance: ${chunk.similarity_pct}%`;
  } else {
    elements.modalSimilarity.textContent = 'Direct Source Excerpt';
  }

  elements.modalChunkText.textContent = chunk ? chunk.text : `No raw text excerpt available for Page ${page}.`;
  elements.citationModal.classList.add('show');
}

function closeCitation() {
  elements.citationModal.classList.remove('show');
  state.activeCitationChunk = null;
}

// ─── Clear Database & Conversations ───
async function clearDocumentDatabase() {
  if (!confirm('Are you sure you want to clear the active document and its FAISS vector database?')) {
    return;
  }

  try {
    const res = await fetch('/api/clear', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      state.documentLoaded = false;
      state.activeDocument = null;
      elements.chatStream.innerHTML = '';
      elements.welcomeHero.style.display = 'flex';
      updateDocumentCard(null);
      checkApplicationStatus();
      showToast('Document database cleared successfully.', 'info');
    }
  } catch (err) {
    showToast(`Clear error: ${err.message}`, 'error');
  }
}

function clearConversation() {
  if (elements.chatStream.children.length === 0) return;
  if (!confirm('Clear all conversation messages?')) return;

  elements.chatStream.innerHTML = '';
  state.messages = [];
  if (!state.documentLoaded) {
    elements.welcomeHero.style.display = 'flex';
  }
  showToast('Chat history cleared.', 'info');
}

// ─── Export Transcript ───
function exportTranscript() {
  if (state.messages.length === 0) {
    showToast('No conversation history to export.', 'info');
    return;
  }

  let transcript = `# DocQA Studio — Conversation Transcript\n`;
  transcript += `**Document:** ${state.activeDocument ? state.activeDocument.filename : 'None'}\n`;
  transcript += `**Export Date:** ${new Date().toLocaleString()}\n`;
  transcript += `**Model:** ${state.selectedModel}\n\n---\n\n`;

  state.messages.forEach((msg, i) => {
    const roleLabel = msg.role === 'user' ? '### 👤 User' : '### 🤖 Assistant';
    transcript += `${roleLabel}\n${msg.content}\n\n`;
    if (msg.sources && msg.sources.length > 0) {
      transcript += `*Sources cited: Pages ${msg.sources.join(', ')}*\n\n`;
    }
    transcript += `---\n\n`;
  });

  downloadTextFile('DocQA_Transcript.md', transcript);
  showToast('Transcript exported successfully!', 'success');
}

// ─── Helper Utilities ───
function autoResizeTextarea() {
  elements.questionInput.style.height = 'auto';
  elements.questionInput.style.height = `${Math.min(elements.questionInput.scrollHeight, 140)}px`;
}

function handleViewportScroll() {
  const fromBottom = elements.messagesViewport.scrollHeight - elements.messagesViewport.scrollTop - elements.messagesViewport.clientHeight;
  if (fromBottom > 150) {
    elements.scrollBottomBtn.classList.add('show');
  } else {
    elements.scrollBottomBtn.classList.remove('show');
  }
}

function scrollToBottom() {
  elements.messagesViewport.scrollTo({
    top: elements.messagesViewport.scrollHeight,
    behavior: 'smooth'
  });
}

function copyToClipboard(text, btnElement, successLabel = 'Copied') {
  navigator.clipboard.writeText(text).then(() => {
    if (btnElement) {
      const origText = btnElement.innerHTML;
      btnElement.innerHTML = `✓ ${successLabel}`;
      setTimeout(() => btnElement.innerHTML = origText, 2000);
    }
  }).catch(() => {
    showToast('Clipboard permission denied.', 'error');
  });
}

function downloadTextFile(filename, text) {
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const icon = type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ';
  toast.innerHTML = `<span style="font-weight:700;">${icon}</span> <span>${escapeHtml(message)}</span>`;

  elements.toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
