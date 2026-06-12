const chatLog = document.getElementById('chat-log');
const chatForm = document.getElementById('chat-form');
const messageInput = document.getElementById('message');
const fileInput = document.getElementById('image-input');
const previewStrip = document.getElementById('preview-strip');
const dropZone = document.getElementById('drop-zone');
const uploadInfo = document.getElementById('upload-info');
const toggleParamsBtn = document.getElementById('toggle-params');
const paramsPanel = document.getElementById('params-panel');
const closeParamsBtn = document.getElementById('close-params');
const saveParamsBtn = document.getElementById('save-params');
const toastContainer = document.getElementById('toast-container');
const lightbox = document.getElementById('lightbox');
const lightboxImage = document.getElementById('lightbox-image');
const lightboxClose = document.getElementById('lightbox-close');
const serviceSelect = document.getElementById('service-preset');
const serviceFocus = document.getElementById('service-focus');
const systemPrompt = document.getElementById('system-prompt');
const pricingBase = document.getElementById('pricing-base');
const pricingRate = document.getElementById('pricing-rate');
const pricingHeavy = document.getElementById('pricing-heavy');
const pricingOil = document.getElementById('pricing-oil');
const pricingAlgae = document.getElementById('pricing-algae');
const pricingAccess = document.getElementById('pricing-access');
const coverageMax = document.getElementById('coverage-max');
const coverageConfidence = document.getElementById('coverage-confidence');
const responseFormat = document.getElementById('response-format');
const limitImageSize = document.getElementById('limit-image-size');
const emptyState = document.getElementById('empty-state');
const summaryCard = document.getElementById('summary-card');
const summaryPrice = document.getElementById('summary-price');
const summaryService = document.getElementById('summary-service');
const summaryArea = document.getElementById('summary-area');
const summaryConfidence = document.getElementById('summary-confidence');
const summaryHighlights = document.getElementById('summary-highlights');
const summaryHelper = document.getElementById('summary-helper');
const openParamsSecondary = document.getElementById('open-params-secondary');
const paramsOverlay = document.getElementById('params-overlay');
const clearChatBtn = document.getElementById('clear-chat');

const tuneFileInput = document.getElementById('tune-file-input');
const tuneDropZone = document.getElementById('tune-drop-zone');
const tuneFileList = document.getElementById('tune-file-list');
const tuneUploadInfo = document.getElementById('tune-upload-info');
const tuneAnalyseBtn = document.getElementById('tune-analyse-btn');
const tuneAddMoreBtn = document.getElementById('tune-add-more-btn');
const tuneImportOnlyBtn = document.getElementById('tune-import-only-btn');
const tuneImportOnlyRow = document.getElementById('tune-import-only-row');
const tuneImportResult = document.getElementById('tune-import-result');
const tuneStepUpload = document.getElementById('tune-step-upload');
const tuneStepQa = document.getElementById('tune-step-qa');
const tuneStepProfile = document.getElementById('tune-step-profile');
const tuneAnalysisSummary = document.getElementById('tune-analysis-summary');
const tuneQaLog = document.getElementById('tune-qa-log');
const tuneQaAnswer = document.getElementById('tune-qa-answer');
const tuneQaSubmit = document.getElementById('tune-qa-submit');
const tuneDoneBtn = document.getElementById('tune-done-btn');
const tuneQaComplete = document.getElementById('tune-qa-complete');
const tuneQaInputArea = document.getElementById('tune-qa-input-area');
const tuneGenerateBtn = document.getElementById('tune-generate-btn');
const tuneToneProfile = document.getElementById('tune-tone-profile');
const tuneSystemPrompt = document.getElementById('tune-system-prompt');
const tuneApplyBtn = document.getElementById('tune-apply-btn');
const tuneRegenerateBtn = document.getElementById('tune-regenerate-btn');
const tuneApplyStatus = document.getElementById('tune-apply-status');
const simulateLog = document.getElementById('simulate-log');
const simulateMessage = document.getElementById('simulate-message');
const simulateBtn = document.getElementById('simulate-btn');
const examplesCount = document.getElementById('examples-count');
const examplesList = document.getElementById('examples-list');

let sessionId = crypto.randomUUID();
let currentParams = null;
let activeUploads = [];
let tuneFiles = [];
let tuneSessionId = null;
let currentUser = null;

// ── Auth & role-based tab visibility ──────────────────────────────────────
function isMobile() { return window.innerWidth <= 768; }

function applyTabVisibility(role) {
  const mobile = isMobile();
  document.querySelectorAll('.tab-btn').forEach(btn => {
    const access = btn.dataset.access || 'all';
    let visible = false;
    if (access === 'all') visible = true;
    else if (access === 'admin' && role === 'admin') visible = true;
    else if (access === 'admin-desktop' && role === 'admin' && !mobile) visible = true;
    btn.style.display = visible ? '' : 'none';
  });

  // If current active tab is now hidden, switch to first visible tab
  const activeBtn = document.querySelector('.tab-btn.active');
  if (activeBtn && activeBtn.style.display === 'none') {
    const firstVisible = document.querySelector('.tab-btn:not([style*="display: none"])');
    if (firstVisible) firstVisible.click();
  }
}

async function authInit() {
  try {
    const res = await fetch('/api/auth/me');
    if (res.status === 401) { window.location = '/login'; return; }
    if (!res.ok) return;
    currentUser = await res.json();

    const label = document.getElementById('header-user-label');
    if (label) label.textContent = currentUser.name || currentUser.email;

    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
      logoutBtn.style.display = '';
      logoutBtn.addEventListener('click', async () => {
        await fetch('/logout', { method: 'POST' });
        window.location = '/login';
      });
    }

    applyTabVisibility(currentUser.role);
    window.addEventListener('resize', () => applyTabVisibility(currentUser.role));

    // Load user management panel if admin
    if (currentUser.role === 'admin') usersInit();

    // Push notifications (all users)
    notifInit();
  } catch (_) {}
}

authInit();

const priceFormatter = new Intl.NumberFormat('en-GB', {
  style: 'currency',
  currency: 'GBP',
  maximumFractionDigits: 2,
});

// ── Burger menu toggle ────────────────────────────────
(function() {
  const burgerBtn = document.getElementById('app-burger-btn');
  const menu      = document.getElementById('app-menu');
  if (!burgerBtn || !menu) return;
  burgerBtn.addEventListener('click', () => {
    const open = !menu.hidden;
    menu.hidden = open;
    burgerBtn.classList.toggle('open', !open);
    burgerBtn.setAttribute('aria-expanded', String(!open));
  });
  // Close when clicking outside
  document.addEventListener('click', (e) => {
    if (!menu.hidden && !menu.contains(e.target) && !burgerBtn.contains(e.target)) {
      menu.hidden = true;
      burgerBtn.classList.remove('open');
      burgerBtn.setAttribute('aria-expanded', 'false');
    }
  });
})();

document.querySelectorAll('.tab-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    // Close burger menu when a tab is selected
    const menu = document.getElementById('app-menu');
    const burgerBtn = document.getElementById('app-burger-btn');
    if (menu) menu.hidden = true;
    if (burgerBtn) { burgerBtn.classList.remove('open'); burgerBtn.setAttribute('aria-expanded', 'false'); }
    const target = btn.dataset.tab;
    document.querySelectorAll('.tab-btn').forEach((b) => {
      b.classList.toggle('active', b.dataset.tab === target);
      b.setAttribute('aria-selected', b.dataset.tab === target);
    });
    document.querySelectorAll('.tab-content').forEach((el) => {
      el.classList.toggle('active', el.id === `tab-${target}`);
    });
    // Hide the app header when in the full-screen Messages view
    document.body.classList.toggle('tab-messages-active', target === 'messages');
    if (target === 'calendar') calInit();
    if (target === 'checkatrade') caInit();
    if (target !== 'messages') { waStopListPoll(); waDisconnectSSE(); }
  });
});

async function init() {
  try {
    const res = await fetch('/api/params');
    if (!res.ok) throw new Error('Unable to load parameters');
    currentParams = await res.json();
    populateParams(currentParams);
  } catch (err) {
    showToast(err.message, 'error');
  }
  updateQuoteSummary();
  loadExamples();
}

function populateParams(params) {
  systemPrompt.value = params.system_prompt || '';
  responseFormat.value = params.response_format || 'json';
  const presets = params.service_presets || {};
  serviceSelect.innerHTML = '';
  Object.entries(presets).forEach(([key, data]) => {
    const option = document.createElement('option');
    option.value = key;
    option.textContent = data.label || key;
    if (key === params.service_preset) option.selected = true;
    serviceSelect.appendChild(option);
  });
  updateServiceFocus();

  const pricing = params.pricing || {};
  pricingBase.value = pricing.base_callout ?? '';
  pricingRate.value = pricing.rate_per_m2 ?? '';
  const multipliers = pricing.multipliers || {};
  pricingHeavy.value = multipliers.heavy_soiling ?? '';
  pricingOil.value = multipliers.oil_stains ?? '';
  pricingAlgae.value = multipliers.algae_biocide ?? '';
  pricingAccess.value = multipliers.access_difficulty ?? '';

  const coverage = params.coverage_policy || {};
  coverageMax.value = coverage.max_additional_photo_requests ?? 1;
  coverageConfidence.value = coverage.confidence_threshold ?? 0.7;

  const limits = params.limits || {};
  limitImageSize.value = limits.max_image_size_mb ?? 8;
}

function updateServiceFocus() {
  const selected = serviceSelect.value;
  const focus = currentParams?.service_presets?.[selected]?.focus;
  serviceFocus.textContent = focus || '';
}

serviceSelect?.addEventListener('change', updateServiceFocus);

function addMessageBubble(role, text, images = []) {
  if (emptyState && !emptyState.classList.contains('hidden')) {
    emptyState.classList.add('hidden');
  }
  const group = document.createElement('div');
  group.className = `message-group ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = role === 'customer' ? 'You' : 'PW';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  const body = document.createElement('div');
  body.className = 'bubble-body';
  body.textContent = text;
  bubble.appendChild(body);

  if (images.length) {
    const gallery = document.createElement('div');
    gallery.className = 'bubble-gallery';
    images.forEach((img) => {
      const thumb = document.createElement('img');
      thumb.src = img.data_url;
      thumb.alt = img.name;
      thumb.addEventListener('click', () => openLightbox(img.data_url));
      gallery.appendChild(thumb);
    });
    bubble.appendChild(gallery);
  }

  const timestamp = document.createElement('span');
  timestamp.className = 'timestamp';
  timestamp.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  bubble.appendChild(timestamp);

  group.appendChild(avatar);
  group.appendChild(bubble);
  chatLog.appendChild(group);
  chatLog.scrollTop = chatLog.scrollHeight;
  return body;
}

function showTypingIndicator() {
  const group = document.createElement('div');
  group.className = 'message-group ai typing-indicator';
  group.id = 'typing-indicator';

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = 'PW';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';

  group.appendChild(avatar);
  group.appendChild(bubble);
  chatLog.appendChild(group);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function removeTypingIndicator() {
  document.getElementById('typing-indicator')?.remove();
}

function typewriterEffect(bodyEl, text) {
  bodyEl.textContent = '';
  const batchSize = text.length > 300 ? 3 : 1;
  const delay     = text.length > 300 ? 10 : 16;
  let i = 0;
  function step() {
    if (i >= text.length) return;
    bodyEl.textContent += text.slice(i, i + batchSize);
    i += batchSize;
    chatLog.scrollTop = chatLog.scrollHeight;
    setTimeout(step, delay);
  }
  step();
}

function handleFiles(files) {
  activeUploads = [];
  previewStrip.innerHTML = '';
  [...files].forEach((file) => {
    const allowed = ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'];
    if (!allowed.includes(file.type)) {
      showToast(`${file.name} is not a supported image type.`, 'error');
      return;
    }
    activeUploads.push(file);
    const reader = new FileReader();
    reader.onload = (event) => {
      const img = document.createElement('img');
      img.src = event.target.result;
      img.alt = file.name;
      img.addEventListener('click', () => openLightbox(event.target.result));
      previewStrip.appendChild(img);
    };
    reader.readAsDataURL(file);
  });
  uploadInfo.textContent = activeUploads.length ? `${activeUploads.length} file(s) ready` : '';
}

fileInput.addEventListener('change', (event) => handleFiles(event.target.files));

['dragenter', 'dragover'].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add('dragover');
  });
});

['dragleave', 'drop'].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove('dragover');
  });
});

dropZone.addEventListener('drop', (event) => {
  const dt = event.dataTransfer;
  if (!dt?.files?.length) return;
  fileInput.files = dt.files;
  handleFiles(dt.files);
});

messageInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

chatForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!messageInput.value.trim() && activeUploads.length === 0) {
    showToast('Add a message or at least one image.', 'error');
    return;
  }

  const submitBtn = chatForm.querySelector('button[type="submit"]');
  if (submitBtn.disabled) return;

  addMessageBubble('customer', messageInput.value.trim() || '📷 Photos sent', activeUploads);

  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('message', messageInput.value.trim());
  activeUploads.forEach((file) => formData.append('images[]', file, file.name));

  resetForm();
  submitBtn.disabled = true;
  showTypingIndicator();

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: 'Unable to send message' }));
      throw new Error(err.error || 'Unable to send message');
    }
    const data = await res.json();
    sessionId = data.session_id;
    removeTypingIndicator();
    const replyText = data.ai?.text || 'No response';
    const bodyEl = addMessageBubble('ai', '', data.images || []);
    typewriterEffect(bodyEl, replyText);
    updateQuoteSummary(data.ai);
  } catch (err) {
    removeTypingIndicator();
    showToast(err.message, 'error');
  } finally {
    submitBtn.disabled = false;
  }
});

function setFormDisabled(disabled) {
  messageInput.disabled = disabled;
  fileInput.disabled = disabled;
  chatForm.querySelector('button[type="submit"]').disabled = disabled;
  uploadInfo.textContent = disabled ? 'Sending…' : '';
}

function resetForm() {
  messageInput.value = '';
  fileInput.value = '';
  previewStrip.innerHTML = '';
  activeUploads = [];
  uploadInfo.textContent = '';
}

function updateQuoteSummary(aiPayload = null) {
  if (!summaryCard) return;
  if (!aiPayload || !aiPayload.json) {
    summaryCard.classList.add('empty');
    summaryPrice.textContent = '—';
    summaryService.textContent = '—';
    summaryArea.textContent = '—';
    summaryConfidence.textContent = '—';
    summaryHelper.textContent = 'Send a message to see the live quote overview.';
    if (summaryHighlights) {
      summaryHighlights.innerHTML = '';
      const li = document.createElement('li');
      li.textContent = 'No analysis yet.';
      summaryHighlights.appendChild(li);
    }
    return;
  }

  const result = aiPayload.json || {};
  summaryCard.classList.remove('empty');
  summaryHelper.textContent = 'Latest AI estimate';

  const price = typeof aiPayload.price_gbp === 'number' ? aiPayload.price_gbp : null;
  summaryPrice.textContent = price !== null ? priceFormatter.format(price) : '—';
  summaryService.textContent = result.service || '—';

  const area = result.area_estimate_m2;
  summaryArea.textContent = (typeof area === 'number' && !Number.isNaN(area)) ? `${Math.round(area)} m²` : '—';

  const confidence = result.confidence;
  summaryConfidence.textContent =
    (typeof confidence === 'number' && !Number.isNaN(confidence)) ? `${Math.round(confidence * 100)}%` : '—';

  if (summaryHighlights) {
    summaryHighlights.innerHTML = '';
    const highlights = [];
    if (result.summary) highlights.push(result.summary);
    const issues = result.condition?.issues || [];
    if (Array.isArray(issues) && issues.length) highlights.push(`Issues spotted: ${issues.join(', ')}`);
    const missing = result.missing_sections || [];
    if (Array.isArray(missing) && missing.length) highlights.push(`Missing coverage: ${missing.join(', ')}`);
    if (result.needs_more_photos && result.next_request) highlights.push(result.next_request);
    if (result.notes) highlights.push(result.notes);
    if (!highlights.length) highlights.push('No additional notes.');
    highlights.forEach((item) => {
      const li = document.createElement('li');
      li.textContent = item;
      summaryHighlights.appendChild(li);
    });
  }
}

function openParamsPanel() {
  if (!paramsPanel) return;
  paramsPanel.classList.add('active');
  paramsOverlay?.classList.add('active');
  paramsPanel.setAttribute('aria-hidden', 'false');
  paramsOverlay?.setAttribute('aria-hidden', 'false');
  document.body.classList.add('drawer-open');
}

function closeParamsPanel() {
  paramsPanel?.classList.remove('active');
  paramsOverlay?.classList.remove('active');
  paramsPanel?.setAttribute('aria-hidden', 'true');
  paramsOverlay?.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('drawer-open');
}

toggleParamsBtn?.addEventListener('click', openParamsPanel);
openParamsSecondary?.addEventListener('click', openParamsPanel);
closeParamsBtn?.addEventListener('click', closeParamsPanel);
paramsOverlay?.addEventListener('click', closeParamsPanel);

saveParamsBtn.addEventListener('click', async () => {
  const payload = {
    system_prompt: systemPrompt.value,
    service_preset: serviceSelect.value,
    response_format: responseFormat.value,
    pricing: {
      base_callout: Number(pricingBase.value),
      rate_per_m2: Number(pricingRate.value),
      multipliers: {
        heavy_soiling: Number(pricingHeavy.value),
        oil_stains: Number(pricingOil.value),
        algae_biocide: Number(pricingAlgae.value),
        access_difficulty: Number(pricingAccess.value),
      },
    },
    coverage_policy: {
      max_additional_photo_requests: Number(coverageMax.value),
      confidence_threshold: Number(coverageConfidence.value),
    },
    limits: { max_image_size_mb: Number(limitImageSize.value) },
  };
  try {
    const res = await fetch('/api/params', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('Unable to save parameters');
    const data = await res.json();
    currentParams = data.params;
    showToast('Parameters updated', 'success');
    closeParamsPanel();
  } catch (err) {
    showToast(err.message, 'error');
  }
});

function openLightbox(src) {
  lightboxImage.src = src;
  lightbox.setAttribute('aria-hidden', 'false');
  lightbox.classList.add('active');
}

lightboxClose.addEventListener('click', closeLightbox);
lightbox.addEventListener('click', (event) => {
  if (event.target === lightbox) closeLightbox();
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    closeLightbox();
    closeParamsPanel();
  }
});

function closeLightbox() {
  lightbox.classList.remove('active');
  lightbox.setAttribute('aria-hidden', 'true');
}

clearChatBtn?.addEventListener('click', () => {
  chatLog.querySelectorAll('.message-group').forEach((node) => node.remove());
  if (emptyState) emptyState.classList.remove('hidden');
  updateQuoteSummary();
  sessionId = crypto.randomUUID();
  resetForm();
});

tuneFileInput.addEventListener('change', (e) => addTuneFiles(e.target.files));
tuneAddMoreBtn.addEventListener('click', () => tuneFileInput.click());

['dragenter', 'dragover'].forEach((ev) => {
  tuneDropZone.addEventListener(ev, (e) => {
    e.preventDefault();
    tuneDropZone.classList.add('dragover');
  });
});
['dragleave', 'drop'].forEach((ev) => {
  tuneDropZone.addEventListener(ev, (e) => {
    e.preventDefault();
    tuneDropZone.classList.remove('dragover');
  });
});
tuneDropZone.addEventListener('drop', (e) => {
  const files = e.dataTransfer?.files;
  if (!files?.length) return;
  addTuneFiles(files);
});

function addTuneFiles(newFiles) {
  const existingNames = new Set(tuneFiles.map((f) => f.name));
  [...newFiles].forEach((file) => {
    if (!existingNames.has(file.name)) {
      tuneFiles.push(file);
      existingNames.add(file.name);
    }
  });
  renderTuneFileList();
  tuneFileInput.value = '';
}

function removeTuneFile(name) {
  tuneFiles = tuneFiles.filter((f) => f.name !== name);
  renderTuneFileList();
}

function renderTuneFileList() {
  tuneFileList.innerHTML = '';
  tuneFiles.forEach((file) => {
    const item = document.createElement('div');
    item.className = 'tune-file-item';

    const name = document.createElement('span');
    name.className = 'tune-file-name';
    name.textContent = file.name;

    const size = document.createElement('span');
    size.className = 'tune-file-size';
    size.textContent = formatBytes(file.size);

    const remove = document.createElement('button');
    remove.className = 'tune-file-remove';
    remove.textContent = '✕';
    remove.title = 'Remove file';
    remove.addEventListener('click', () => removeTuneFile(file.name));

    item.appendChild(name);
    item.appendChild(size);
    item.appendChild(remove);
    tuneFileList.appendChild(item);
  });
  const count = tuneFiles.length;
  tuneUploadInfo.textContent = count ? `${count} file${count !== 1 ? 's' : ''} ready to analyse` : '';
  tuneAddMoreBtn.classList.toggle('hidden', count === 0);
  if (tuneImportOnlyRow) tuneImportOnlyRow.classList.toggle('hidden', count === 0);
  if (tuneImportResult) tuneImportResult.classList.add('hidden');
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

tuneAnalyseBtn.addEventListener('click', async () => {
  if (!tuneFiles.length) {
    showToast('Please upload at least one conversation file.', 'error');
    return;
  }

  tuneAnalyseBtn.disabled = true;
  tuneAnalyseBtn.innerHTML = '<span class="spinner"></span> Analysing…';

  const formData = new FormData();
  tuneFiles.forEach((file) => formData.append('files[]', file, file.name));

  try {
    const res = await fetch('/api/tune/analyse', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Analysis failed');

    tuneSessionId = data.session_id;
    tuneAnalysisSummary.textContent = data.analysis_summary || '';
    tuneQaLog.innerHTML = '';

    const exBanner = document.getElementById('tune-examples-extracted-banner');
    if (exBanner) {
      if (data.examples_added > 0) {
        exBanner.textContent = `✓ Extracted ${data.examples_added} real conversation example${data.examples_added === 1 ? '' : 's'} — these will be used to match your replies to future customers.`;
        exBanner.classList.remove('hidden');
      } else {
        exBanner.classList.add('hidden');
      }
    }

    const updateBanner = document.getElementById('tune-update-banner');
    if (updateBanner) {
      updateBanner.classList.toggle('hidden', !data.is_update);
    }

    tuneStepUpload.classList.add('hidden');
    tuneStepQa.classList.remove('hidden');

    if (data.question) {
      addTuneQaBubble('question', data.question, data.question_number, data.total_questions);
    } else {
      showTuneQaComplete();
    }
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    tuneAnalyseBtn.disabled = false;
    tuneAnalyseBtn.textContent = 'Analyse conversations';
  }
});

if (tuneImportOnlyBtn) {
  tuneImportOnlyBtn.addEventListener('click', async () => {
    if (!tuneFiles.length) {
      showToast('Please upload at least one conversation file.', 'error');
      return;
    }
    tuneImportOnlyBtn.disabled = true;
    tuneImportOnlyBtn.innerHTML = '<span class="spinner"></span> Importing…';

    const formData = new FormData();
    tuneFiles.forEach((file) => formData.append('files[]', file, file.name));

    try {
      const res = await fetch('/api/tune/import-examples', { method: 'POST', body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Import failed');

      tuneImportResult.classList.remove('hidden');
      if (data.examples_added > 0) {
        tuneImportResult.className = 'tune-import-result tune-import-result--success';
        tuneImportResult.textContent = `Done — extracted ${data.examples_added} new conversation example${data.examples_added === 1 ? '' : 's'} (${data.total_examples} total in library). The AI will use these next time a customer messages.`;
      } else {
        tuneImportResult.className = 'tune-import-result tune-import-result--info';
        tuneImportResult.textContent = `No new examples found — the conversations may already be in the library, or the AI couldn't find clear customer→owner pairs in these files.`;
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      tuneImportOnlyBtn.disabled = false;
      tuneImportOnlyBtn.textContent = 'Import examples only (no questions)';
    }
  });
}

function addTuneQaBubble(type, text, num, total) {
  const bubble = document.createElement('div');
  bubble.className = `tune-qa-bubble ${type}`;
  if (type === 'question' && num && total) {
    const label = document.createElement('div');
    label.className = 'tune-qa-label';
    label.textContent = `Question ${num} of ${total}`;
    bubble.appendChild(label);
  }
  const body = document.createElement('div');
  body.textContent = text;
  bubble.appendChild(body);
  tuneQaLog.appendChild(bubble);
  tuneQaLog.scrollTop = tuneQaLog.scrollHeight;
}

tuneQaSubmit.addEventListener('click', submitTuneAnswer);
tuneQaAnswer.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    submitTuneAnswer();
  }
});

async function submitTuneAnswer() {
  const answer = tuneQaAnswer.value.trim();
  if (!answer) return;
  if (!tuneSessionId) {
    showToast('Session expired. Please re-upload your files.', 'error');
    return;
  }

  addTuneQaBubble('answer', answer);
  tuneQaAnswer.value = '';
  tuneQaSubmit.disabled = true;
  tuneDoneBtn.disabled = true;

  try {
    const res = await fetch('/api/tune/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: tuneSessionId, answer }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to submit answer');

    if (data.ready) {
      showTuneQaComplete();
    } else if (data.question) {
      addTuneQaBubble('question', data.question, data.question_number, data.total_questions);
    }
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    tuneQaSubmit.disabled = false;
    tuneDoneBtn.disabled = false;
  }
}

tuneDoneBtn.addEventListener('click', () => {
  showTuneQaComplete();
});

function showTuneQaComplete() {
  tuneQaInputArea.classList.add('hidden');
  tuneQaComplete.classList.remove('hidden');
}

tuneGenerateBtn.addEventListener('click', async () => {
  if (!tuneSessionId) {
    showToast('Session expired. Please re-upload your files.', 'error');
    return;
  }
  tuneGenerateBtn.disabled = true;
  tuneGenerateBtn.innerHTML = '<span class="spinner"></span> Generating…';

  try {
    const res = await fetch('/api/tune/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: tuneSessionId }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Generation failed');

    tuneToneProfile.value = data.tone_profile || '';
    tuneSystemPrompt.value = data.system_prompt || '';
    tuneApplyStatus.classList.add('hidden');

    tuneStepQa.classList.add('hidden');
    tuneStepProfile.classList.remove('hidden');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    tuneGenerateBtn.disabled = false;
    tuneGenerateBtn.textContent = 'Generate my profile';
  }
});

tuneRegenerateBtn.addEventListener('click', async () => {
  if (!tuneSessionId) {
    showToast('Session expired. Please re-upload your files.', 'error');
    return;
  }
  tuneRegenerateBtn.disabled = true;
  tuneRegenerateBtn.innerHTML = '<span class="spinner"></span> Regenerating…';

  try {
    const res = await fetch('/api/tune/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: tuneSessionId }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Generation failed');
    tuneToneProfile.value = data.tone_profile || '';
    tuneSystemPrompt.value = data.system_prompt || '';
    tuneApplyStatus.classList.add('hidden');
    showToast('Profile regenerated', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    tuneRegenerateBtn.disabled = false;
    tuneRegenerateBtn.textContent = 'Regenerate';
  }
});

tuneApplyBtn.addEventListener('click', async () => {
  const toneProfile = tuneToneProfile.value.trim();
  const sysPrompt = tuneSystemPrompt.value.trim();
  if (!toneProfile || !sysPrompt) {
    showToast('Both fields are required.', 'error');
    return;
  }
  tuneApplyBtn.disabled = true;
  tuneApplyBtn.innerHTML = '<span class="spinner"></span> Applying…';

  try {
    const res = await fetch('/api/tune/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: tuneSessionId, tone_profile: toneProfile, system_prompt: sysPrompt }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Apply failed');

    tuneApplyStatus.textContent = '✓ Profile applied — the estimator AI will now use your new style.';
    tuneApplyStatus.className = 'tune-apply-status';
    tuneApplyStatus.classList.remove('hidden');
    showToast('Profile applied successfully', 'success');
  } catch (err) {
    tuneApplyStatus.textContent = `Error: ${err.message}`;
    tuneApplyStatus.className = 'tune-apply-status error';
    tuneApplyStatus.classList.remove('hidden');
    showToast(err.message, 'error');
  } finally {
    tuneApplyBtn.disabled = false;
    tuneApplyBtn.textContent = 'Apply this profile';
  }
});

simulateBtn.addEventListener('click', sendSimulation);
simulateMessage.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendSimulation();
  }
});

async function sendSimulation() {
  const msg = simulateMessage.value.trim();
  if (!msg) return;
  simulateMessage.value = '';
  simulateBtn.disabled = true;
  simulateBtn.innerHTML = '<span class="spinner"></span>';

  addSimBubble('customer', msg);

  try {
    const res = await fetch('/api/tune/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Simulation failed');
    addSimBubble('ai', data.reply, msg);
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    simulateBtn.disabled = false;
    simulateBtn.textContent = 'Send';
  }
}

function addSimBubble(role, text, customerMsg = '') {
  const bubble = document.createElement('div');
  bubble.className = `simulate-bubble ${role}`;

  const body = document.createElement('div');
  body.textContent = text;
  bubble.appendChild(body);

  if (role === 'ai') {
    const feedback = document.createElement('div');
    feedback.className = 'sim-feedback';

    const thumbUp = document.createElement('button');
    thumbUp.className = 'sim-thumb';
    thumbUp.textContent = '👍';
    thumbUp.title = 'Good reply';
    thumbUp.addEventListener('click', () => {
      thumbUp.disabled = true;
      thumbDown.disabled = true;
    });

    const thumbDown = document.createElement('button');
    thumbDown.className = 'sim-thumb';
    thumbDown.textContent = '👎';
    thumbDown.title = 'Needs improvement';
    thumbDown.addEventListener('click', () => {
      thumbUp.disabled = true;
      thumbDown.disabled = true;
      showCorrectionForm(bubble, customerMsg);
    });

    feedback.appendChild(thumbUp);
    feedback.appendChild(thumbDown);
    bubble.appendChild(feedback);
  }

  simulateLog.appendChild(bubble);
  simulateLog.scrollTop = simulateLog.scrollHeight;
}

function showCorrectionForm(bubble, customerMsg) {
  const form = document.createElement('div');
  form.className = 'sim-correction-form';

  const label = document.createElement('div');
  label.className = 'sim-correction-label';
  label.textContent = 'What would you actually say?';

  const ta = document.createElement('textarea');
  ta.placeholder = 'Type your preferred reply…';

  const saveBtn = document.createElement('button');
  saveBtn.className = 'primary';
  saveBtn.textContent = 'Save correction';

  saveBtn.addEventListener('click', async () => {
    const ownerReply = ta.value.trim();
    if (!ownerReply) return;
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<span class="spinner"></span> Saving…';
    try {
      const [feedbackRes, patchRes] = await Promise.all([
        fetch('/api/tune/feedback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ customer_message: customerMsg, owner_reply: ownerReply }),
        }),
        fetch('/api/tune/patch-profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ customer_message: customerMsg, owner_reply: ownerReply }),
        }),
      ]);
      const feedbackData = await feedbackRes.json();
      if (!feedbackRes.ok) throw new Error(feedbackData.error || 'Failed to save');
      const patchData = patchRes.ok ? await patchRes.json() : { updated: false };
      const profileMsg = patchData.updated ? ' · Profile updated too.' : '';
      form.innerHTML = `<div class="sim-correction-saved">✓ Saved to example library${profileMsg}</div>`;
      updateExamplesCount(feedbackData.total_examples);
      loadExamples();
      showToast('Correction saved' + (patchData.updated ? ' and profile updated' : ''), 'success');
    } catch (err) {
      showToast(err.message, 'error');
      saveBtn.disabled = false;
      saveBtn.textContent = 'Save correction';
    }
  });

  form.appendChild(label);
  form.appendChild(ta);
  form.appendChild(saveBtn);
  bubble.appendChild(form);
}

async function loadExamples() {
  try {
    const res = await fetch('/api/tune/examples');
    const data = await res.json();
    const examples = data.examples || [];
    updateExamplesCount(examples.length);
    renderExamples(examples);
  } catch (_) {}
}

function updateExamplesCount(count) {
  examplesCount.textContent = `${count} saved`;
}

function renderExamples(examples) {
  examplesList.innerHTML = '';
  if (!examples.length) {
    const empty = document.createElement('div');
    empty.className = 'examples-empty';
    empty.textContent = 'No corrections yet. Use 👎 in the simulator to add your style.';
    examplesList.appendChild(empty);
    return;
  }
  [...examples].reverse().slice(0, 10).forEach((ex) => {
    const item = document.createElement('div');
    item.className = 'example-item';

    const custLabel = document.createElement('div');
    custLabel.className = 'ex-label';
    custLabel.textContent = 'Customer';
    const custText = document.createElement('div');
    custText.className = 'ex-text';
    custText.textContent = ex.customer;

    const ownerLabel = document.createElement('div');
    ownerLabel.className = 'ex-label ex-label--owner';
    ownerLabel.textContent = 'Your reply';
    const ownerText = document.createElement('div');
    ownerText.className = 'ex-text ex-text--owner';
    ownerText.textContent = ex.owner;

    item.appendChild(custLabel);
    item.appendChild(custText);
    item.appendChild(ownerLabel);
    item.appendChild(ownerText);
    examplesList.appendChild(item);
  });
}

const insightLog = document.getElementById('insight-log');
const insightMessage = document.getElementById('insight-message');
const insightBtn = document.getElementById('insight-btn');

insightBtn.addEventListener('click', sendInsight);
insightMessage.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendInsight();
  }
});

document.querySelectorAll('.insight-chip').forEach((chip) => {
  chip.addEventListener('click', () => {
    insightMessage.value = chip.dataset.q;
    sendInsight();
  });
});

async function sendInsight() {
  const msg = insightMessage.value.trim();
  if (!msg) return;
  insightMessage.value = '';
  insightBtn.disabled = true;
  insightBtn.innerHTML = '<span class="spinner"></span>';

  addInsightBubble('question', msg);

  try {
    const res = await fetch('/api/tune/insight', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: msg }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to get insight');
    addInsightBubble('answer', data.answer);
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    insightBtn.disabled = false;
    insightBtn.textContent = 'Ask';
  }
}

function addInsightBubble(type, text) {
  const bubble = document.createElement('div');
  bubble.className = `insight-bubble ${type}`;
  bubble.textContent = text;
  insightLog.appendChild(bubble);
  insightLog.scrollTop = insightLog.scrollHeight;
}

// ── Coach Me ────────────────────────────────────────────────────────────────

const coachToggle = document.getElementById('coach-toggle');
const coachChevron = document.getElementById('coach-chevron');
const coachBody = document.getElementById('coach-body');
const coachIdle = document.getElementById('coach-idle');
const coachStartBtn = document.getElementById('coach-start-btn');
const coachSession = document.getElementById('coach-session');
const coachQaLog = document.getElementById('coach-qa-log');
const coachInputArea = document.getElementById('coach-input-area');
const coachAnswer = document.getElementById('coach-answer');
const coachSubmitBtn = document.getElementById('coach-submit-btn');
const coachDoneBtn = document.getElementById('coach-done-btn');
const coachComplete = document.getElementById('coach-complete');

let coachSessionId = null;
let coachCurrentQuestion = '';

if (coachToggle) {
  coachToggle.addEventListener('click', () => {
    const expanded = coachToggle.getAttribute('aria-expanded') === 'true';
    coachToggle.setAttribute('aria-expanded', String(!expanded));
    coachBody.classList.toggle('hidden', expanded);
    coachChevron.textContent = expanded ? '▸' : '▾';
  });
}

if (coachStartBtn) {
  coachStartBtn.addEventListener('click', async () => {
    coachStartBtn.disabled = true;
    coachStartBtn.innerHTML = '<span class="spinner"></span> Starting…';
    try {
      const res = await fetch('/api/tune/coach-start', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Could not start coaching');
      coachSessionId = data.session_id;
      coachCurrentQuestion = data.question;
      coachIdle.classList.add('hidden');
      coachSession.classList.remove('hidden');
      addCoachBubble('question', data.question);
    } catch (err) {
      showToast(err.message, 'error');
      coachStartBtn.disabled = false;
      coachStartBtn.textContent = 'Start coaching session';
    }
  });
}

async function submitCoachAnswer() {
  const answer = coachAnswer.value.trim();
  if (!answer || !coachSessionId) return;
  coachAnswer.value = '';
  coachSubmitBtn.disabled = true;
  coachDoneBtn.disabled = true;
  addCoachBubble('answer', answer);

  try {
    const res = await fetch('/api/tune/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: coachSessionId, answer }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to submit');

    if (data.ready) {
      coachInputArea.classList.add('hidden');
      await completeCoachSession();
    } else if (data.question) {
      coachCurrentQuestion = data.question;
      addCoachBubble('question', data.question);
    }
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    coachSubmitBtn.disabled = false;
    coachDoneBtn.disabled = false;
  }
}

async function completeCoachSession() {
  coachInputArea.classList.add('hidden');
  coachComplete.classList.remove('hidden');
  coachComplete.textContent = 'Updating your profile…';
  try {
    const res = await fetch('/api/tune/coach-complete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: coachSessionId }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Profile update failed');
    coachComplete.textContent = '✓ Profile updated. Your answers have been merged in.';
    coachComplete.classList.add('success');
    coachSessionId = null;
    showToast('Profile updated from coaching session', 'success');
  } catch (err) {
    coachComplete.textContent = `Error: ${err.message}`;
    showToast(err.message, 'error');
  }
}

if (coachSubmitBtn) {
  coachSubmitBtn.addEventListener('click', submitCoachAnswer);
}
if (coachAnswer) {
  coachAnswer.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitCoachAnswer(); }
  });
}
if (coachDoneBtn) {
  coachDoneBtn.addEventListener('click', async () => {
    if (!coachSessionId) return;
    coachDoneBtn.disabled = true;
    coachSubmitBtn.disabled = true;
    await completeCoachSession();
  });
}

function addCoachBubble(type, text) {
  const bubble = document.createElement('div');
  bubble.className = `coach-bubble ${type}`;
  bubble.textContent = text;
  coachQaLog.appendChild(bubble);
  coachQaLog.scrollTop = coachQaLog.scrollHeight;
}

// ── Fine-tune panel ───────────────────────────────────────────────────────────

const ftExamplesCount = document.getElementById('ft-examples-count');
const ftModelBadge    = document.getElementById('ft-model-badge');
const ftIdle          = document.getElementById('ft-idle');
const ftRunning       = document.getElementById('ft-running');
const ftReady         = document.getElementById('ft-ready');
const ftActive        = document.getElementById('ft-active');
const ftError         = document.getElementById('ft-error');
const ftProgressLabel = document.getElementById('ft-progress-label');
const ftActiveId      = document.getElementById('ft-active-id');
const ftErrorMsg      = document.getElementById('ft-error-msg');
const ftTrainBtn      = document.getElementById('ft-train-btn');
const ftPollBtn       = document.getElementById('ft-poll-btn');
const ftActivateBtn   = document.getElementById('ft-activate-btn');
const ftRetrainBtn    = document.getElementById('ft-retrain-btn');
const ftDeactivateBtn = document.getElementById('ft-deactivate-btn');
const ftRetryBtn      = document.getElementById('ft-retry-btn');

const FT_STATUS_LABELS = {
  none: 'Idle',
  validating_files: 'Validating files…',
  queued: 'Queued…',
  running: 'Training…',
  succeeded: 'Complete',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

function ftShowSection(name) {
  [ftIdle, ftRunning, ftReady, ftActive, ftError].forEach(el => el && el.classList.add('hidden'));
  const map = { idle: ftIdle, running: ftRunning, ready: ftReady, active: ftActive, error: ftError };
  if (map[name]) map[name].classList.remove('hidden');
}

function ftApplyState(state) {
  if (!state) return;

  if (ftExamplesCount) ftExamplesCount.textContent = state.examples_count ?? '—';

  const isActive = state.active && state.model_id;
  if (ftModelBadge) {
    ftModelBadge.textContent = isActive ? 'Fine-tuned ✓' : 'Base model';
    ftModelBadge.classList.toggle('active', !!isActive);
  }
  if (ftActiveId) ftActiveId.textContent = state.model_id || '';

  if (isActive) {
    ftShowSection('active');
  } else if (state.status === 'succeeded' && state.model_id) {
    ftShowSection('ready');
  } else if (['validating_files', 'queued', 'running'].includes(state.status)) {
    ftShowSection('running');
    if (ftProgressLabel) ftProgressLabel.textContent = FT_STATUS_LABELS[state.status] || 'Training…';
    const ex = state.training_examples;
    if (ex && ftProgressLabel) ftProgressLabel.textContent += ` (${ex} examples)`;
  } else if (['failed', 'cancelled'].includes(state.status)) {
    ftShowSection('error');
    if (ftErrorMsg) ftErrorMsg.textContent = state.error || 'Training failed. Please try again.';
  } else {
    ftShowSection('idle');
  }
}

async function ftLoadStatus() {
  try {
    const res = await fetch('/api/tune/finetune-status');
    const data = await res.json();
    ftApplyState(data);
  } catch (e) { /* silent */ }
}

async function ftStartTraining() {
  if (ftTrainBtn) { ftTrainBtn.disabled = true; ftTrainBtn.innerHTML = '<span class="spinner"></span> Starting…'; }
  try {
    const res = await fetch('/api/tune/finetune-start', { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Could not start training');
    showToast(`Training started with ${data.examples} examples. Check back in 30–60 min.`);
    ftShowSection('running');
    if (ftProgressLabel) ftProgressLabel.textContent = `Training… (${data.examples} examples)`;
  } catch (err) {
    showToast(err.message, 'error');
    if (ftTrainBtn) { ftTrainBtn.disabled = false; ftTrainBtn.textContent = 'Train Now'; }
  }
}

async function ftPollStatus() {
  if (ftPollBtn) { ftPollBtn.disabled = true; ftPollBtn.innerHTML = '<span class="spinner"></span>'; }
  try {
    const res = await fetch('/api/tune/finetune-poll', { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Could not check status');
    ftApplyState(data);
    if (data.status === 'succeeded') {
      showToast('Training complete! Click "Activate" to start using your custom model.');
    } else {
      showToast(`Status: ${FT_STATUS_LABELS[data.status] || data.status}`);
    }
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    if (ftPollBtn) { ftPollBtn.disabled = false; ftPollBtn.textContent = 'Check status'; }
  }
}

async function ftActivateModel() {
  if (ftActivateBtn) { ftActivateBtn.disabled = true; ftActivateBtn.innerHTML = '<span class="spinner"></span>'; }
  try {
    const res = await fetch('/api/tune/finetune-activate', { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Could not activate model');
    showToast('Your fine-tuned model is now active. The Simulate panel will use it.');
    await ftLoadStatus();
  } catch (err) {
    showToast(err.message, 'error');
    if (ftActivateBtn) { ftActivateBtn.disabled = false; ftActivateBtn.textContent = 'Activate fine-tuned model'; }
  }
}

async function ftDeactivateModel() {
  try {
    const res = await fetch('/api/tune/finetune-deactivate', { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Could not deactivate');
    showToast('Switched back to base model.');
    await ftLoadStatus();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

if (ftTrainBtn)      ftTrainBtn.addEventListener('click', ftStartTraining);
if (ftPollBtn)       ftPollBtn.addEventListener('click', ftPollStatus);
if (ftActivateBtn)   ftActivateBtn.addEventListener('click', ftActivateModel);
if (ftDeactivateBtn) ftDeactivateBtn.addEventListener('click', ftDeactivateModel);
if (ftRetrainBtn)    ftRetrainBtn.addEventListener('click', () => { ftShowSection('idle'); if (ftTrainBtn) { ftTrainBtn.disabled = false; ftTrainBtn.textContent = 'Train Now'; } });
if (ftRetryBtn)      ftRetryBtn.addEventListener('click', () => { ftShowSection('idle'); if (ftTrainBtn) { ftTrainBtn.disabled = false; ftTrainBtn.textContent = 'Train Now'; } });

document.querySelector('[data-tab="tune"]')?.addEventListener('click', () => {
  ftLoadStatus();
  tuneAimLoad();
  tuneUserInstrLoad();
});

// ── Tune: General Aim ─────────────────────────────────────────────────────────
async function tuneAimLoad() {
  try {
    const d = await (await fetch('/api/tune/aim')).json();
    const el = document.getElementById('tune-aim-text');
    if (el) el.value = d.aim || '';
  } catch (_) {}
}

async function tuneAimSave() {
  const aim = (document.getElementById('tune-aim-text')?.value || '').trim();
  const statusEl = document.getElementById('tune-aim-status');
  try {
    await fetch('/api/tune/aim', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ aim }) });
    if (statusEl) { statusEl.textContent = 'Saved ✓'; statusEl.className = 'cal-save-status ok'; setTimeout(() => { statusEl.textContent = ''; }, 2500); }
  } catch (_) {
    if (statusEl) { statusEl.textContent = 'Error saving'; statusEl.className = 'cal-save-status err'; }
  }
}

document.getElementById('tune-aim-save-btn')?.addEventListener('click', tuneAimSave);

// ── Tune: Per-person Instructions ─────────────────────────────────────────────
let _tuneUsers = [];

async function tuneUserInstrLoad() {
  try {
    const d = await (await fetch('/api/tune/user-instructions')).json();
    _tuneUsers = d.users || [];
    tuneUserInstrRender();
  } catch (_) {}
}

function tuneUserInstrRender() {
  const list = document.getElementById('tune-userinstr-list');
  const actions = document.getElementById('tune-userinstr-actions');
  const addBtn = document.getElementById('tune-userinstr-add-btn');
  if (!list) return;
  list.innerHTML = '';
  _tuneUsers.forEach((u, i) => {
    const row = document.createElement('div');
    row.className = 'tune-userinstr-person';
    row.innerHTML = `
      <div class="tune-userinstr-person-header">
        <input class="tune-userinstr-name" type="text" placeholder="Person's name (e.g. Dan)" value="${(u.name || '').replace(/"/g, '&quot;')}" data-idx="${i}">
        <button class="tune-userinstr-remove ghost" data-idx="${i}" type="button">Remove</button>
      </div>
      <textarea class="tune-userinstr-text" rows="4" placeholder="e.g. This engineer covers the northern service area. Prefer jobs close to their configured home base at the start and end of the day." data-idx="${i}">${u.instructions || ''}</textarea>
    `;
    list.appendChild(row);
  });
  list.querySelectorAll('.tune-userinstr-name').forEach(el => el.addEventListener('input', e => { _tuneUsers[+e.target.dataset.idx].name = e.target.value; }));
  list.querySelectorAll('.tune-userinstr-text').forEach(el => el.addEventListener('input', e => { _tuneUsers[+e.target.dataset.idx].instructions = e.target.value; }));
  list.querySelectorAll('.tune-userinstr-remove').forEach(el => el.addEventListener('click', e => { _tuneUsers.splice(+e.target.dataset.idx, 1); tuneUserInstrRender(); }));
  if (addBtn) addBtn.style.display = _tuneUsers.length >= 2 ? 'none' : '';
  if (actions) actions.style.display = _tuneUsers.length > 0 ? '' : 'none';
}

document.getElementById('tune-userinstr-add-btn')?.addEventListener('click', () => {
  if (_tuneUsers.length >= 2) return;
  _tuneUsers.push({ name: '', instructions: '' });
  tuneUserInstrRender();
});

async function tuneUserInstrSave() {
  const statusEl = document.getElementById('tune-userinstr-status');
  try {
    await fetch('/api/tune/user-instructions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ users: _tuneUsers }) });
    if (statusEl) { statusEl.textContent = 'Saved ✓'; statusEl.className = 'cal-save-status ok'; setTimeout(() => { statusEl.textContent = ''; }, 2500); }
  } catch (_) {
    if (statusEl) { statusEl.textContent = 'Error saving'; statusEl.className = 'cal-save-status err'; }
  }
}

document.getElementById('tune-userinstr-save-btn')?.addEventListener('click', tuneUserInstrSave);

// ────────────────────────────────────────────────────────────────────────────

function showToast(message, variant = 'success') {
  const toast = document.createElement('div');
  toast.className = `toast ${variant}`;
  const icon = document.createElement('span');
  icon.className = 'toast-icon';
  icon.textContent = variant === 'error' ? '⚠️' : '✅';
  const text = document.createElement('span');
  text.textContent = message;
  toast.appendChild(icon);
  toast.appendChild(text);
  toastContainer.appendChild(toast);
  setTimeout(() => toast.classList.add('hide'), 3200);
  setTimeout(() => toast.remove(), 3600);
}

init();

// ─────────────────────────────────────────────────────────────────────────────
// KNOWLEDGE BASE TAB — Goal & Process section
// ─────────────────────────────────────────────────────────────────────────────

(function kbGoalInit() {
  const goalText      = document.getElementById('kb-goal-text');
  const goalProcess   = document.getElementById('kb-goal-process');
  const goalTriggers  = document.getElementById('kb-goal-escalation-triggers');
  const goalPhone     = document.getElementById('kb-goal-escalation-phone');
  const goalChannel   = document.getElementById('kb-goal-escalation-channel');
  const goalCalCheck  = document.getElementById('kb-goal-cal-check');
  const goalCalBook   = document.getElementById('kb-goal-cal-book');
  const goalSaveBtn   = document.getElementById('kb-goal-save');
  const goalStatus    = document.getElementById('kb-goal-status');

  async function load() {
    try {
      const data = await fetch('/api/kb/goal').then(r => r.json());
      if (goalText)     goalText.value    = data.goal || '';
      if (goalProcess)  goalProcess.value = data.process || '';
      if (goalTriggers) goalTriggers.value = data.escalationTriggers || '';
      if (goalPhone)    goalPhone.value   = data.escalationPhone || '';
      if (goalChannel)  goalChannel.value = data.escalationChannel || 'whatsapp';
      if (goalCalCheck) goalCalCheck.checked = data.calendarCheckEnabled !== false;
      if (goalCalBook)  goalCalBook.checked  = data.calendarBookEnabled  !== false;
    } catch (_) {}
  }

  async function save() {
    if (!goalSaveBtn) return;
    goalSaveBtn.disabled = true;
    if (goalStatus) goalStatus.textContent = 'Normalising & saving…';
    try {
      const res = await fetch('/api/kb/goal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal:                  goalText?.value.trim()     || '',
          process:               goalProcess?.value.trim()  || '',
          escalationTriggers:    goalTriggers?.value.trim() || '',
          escalationPhone:       goalPhone?.value.trim()    || '',
          escalationChannel:     goalChannel?.value         || 'whatsapp',
          calendarCheckEnabled:  goalCalCheck?.checked      ?? true,
          calendarBookEnabled:   goalCalBook?.checked        ?? true,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        // Reflect normalised values back into the textareas
        const cfg = data.config || {};
        if (goalText     && cfg.goal              !== undefined) goalText.value     = cfg.goal;
        if (goalProcess  && cfg.process           !== undefined) goalProcess.value  = cfg.process;
        if (goalTriggers && cfg.escalationTriggers !== undefined) goalTriggers.value = cfg.escalationTriggers;
        if (goalStatus) {
          goalStatus.textContent = '✓ Saved';
          setTimeout(() => { if (goalStatus) goalStatus.textContent = ''; }, 2500);
        }
        showToast('Goal settings normalised & saved', 'success');
        window.kbCrossCheck?.('goal',
          `Goal: ${cfg.goal || ''}\nProcess: ${cfg.process || ''}\nEscalation triggers: ${cfg.escalationTriggers || ''}`
        );
      } else {
        throw new Error(data.error || 'Save failed');
      }
    } catch (e) {
      if (goalStatus) goalStatus.textContent = '✗ ' + e.message;
      showToast('Could not save goal settings', 'error');
    } finally {
      if (goalSaveBtn) goalSaveBtn.disabled = false;
    }
  }

  const goalRefineInput  = document.getElementById('kb-goal-refine-input');
  const goalRefineBtn    = document.getElementById('kb-goal-refine-btn');
  const goalRefineStatus = document.getElementById('kb-goal-refine-status');

  async function refine() {
    const newInfo = goalRefineInput?.value.trim();
    if (!newInfo) { showToast('Describe what to add or change first.', 'error'); return; }

    if (goalRefineBtn) { goalRefineBtn.disabled = true; goalRefineBtn.textContent = 'Thinking…'; }
    if (goalRefineStatus) { goalRefineStatus.textContent = 'Refining…'; goalRefineStatus.className = 'kb-goal-refine-status kb-goal-refine-status--thinking'; }

    try {
      const res = await fetch('/api/kb/goal/refine', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal:               goalText?.value.trim()     || '',
          process:            goalProcess?.value.trim()  || '',
          escalationTriggers: goalTriggers?.value.trim() || '',
          newInfo,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        if (goalText     && data.goal              !== undefined) goalText.value     = data.goal;
        if (goalProcess  && data.process           !== undefined) goalProcess.value  = data.process;
        if (goalTriggers && data.escalationTriggers !== undefined) goalTriggers.value = data.escalationTriggers;
        if (goalRefineInput) goalRefineInput.value = '';
        if (goalRefineStatus) {
          goalRefineStatus.textContent = '✓ Updated';
          goalRefineStatus.className = 'kb-goal-refine-status kb-goal-refine-status--done';
          setTimeout(() => { if (goalRefineStatus) { goalRefineStatus.textContent = ''; goalRefineStatus.className = 'kb-goal-refine-status'; } }, 3000);
        }
        showToast('Goal & process refined by AI', 'success');
      } else {
        throw new Error(data.error || 'Refine failed');
      }
    } catch (e) {
      if (goalRefineStatus) { goalRefineStatus.textContent = '✗ ' + e.message; goalRefineStatus.className = 'kb-goal-refine-status kb-goal-refine-status--error'; }
      showToast('Refinement failed: ' + e.message, 'error');
    } finally {
      if (goalRefineBtn) {
        goalRefineBtn.disabled = false;
        goalRefineBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"/></svg> Refine with AI';
      }
    }
  }

  if (goalSaveBtn)    goalSaveBtn.addEventListener('click', save);
  if (goalRefineBtn)  goalRefineBtn.addEventListener('click', refine);
  load();
})();

// ─────────────────────────────────────────────────────────────────────────────
// AI ADVISOR MODAL
// ─────────────────────────────────────────────────────────────────────────────
(function () {
  const modal       = document.getElementById('kb-advisor-modal');
  const msgEl       = document.getElementById('kb-advisor-message');
  const threadEl    = document.getElementById('kb-advisor-thread');
  const applyBtn    = document.getElementById('kb-advisor-apply');
  const dismissBtn  = document.getElementById('kb-advisor-dismiss');
  const closeBtn    = document.getElementById('kb-advisor-close');
  const replyInput  = document.getElementById('kb-advisor-reply-input');
  const replySend   = document.getElementById('kb-advisor-reply-send');
  const replyStatus = document.getElementById('kb-advisor-reply-status');

  if (!modal) return;

  // State held for the current insight
  let _section     = '';
  let _updatedText = '';
  let _insight     = '';
  let _payload     = null;

  function _addBubble(text, type) {
    if (!threadEl) return null;
    const el = document.createElement('div');
    el.className = `kb-advisor-bubble kb-advisor-bubble--${type}`;
    el.textContent = text;
    threadEl.appendChild(el);
    threadEl.scrollTop = threadEl.scrollHeight;
    return el;
  }

  function show(data) {
    _insight = data.message || '';
    _payload = data.applyPayload || null;

    msgEl.textContent = _insight;

    if (_payload && data.applyLabel) {
      applyBtn.textContent = data.applyLabel;
      applyBtn.hidden = false;
    } else {
      applyBtn.hidden = true;
    }

    // Clear thread on fresh open
    if (threadEl) threadEl.innerHTML = '';
    replyInput.value = '';
    if (replyStatus) replyStatus.textContent = '';
    modal.hidden = false;
    // Re-trigger animation
    modal.style.animation = 'none';
    requestAnimationFrame(() => { modal.style.animation = ''; });
  }

  function hide() {
    modal.hidden = true;
    _payload = null;
    if (threadEl) threadEl.innerHTML = '';
  }

  async function applyFix(payload) {
    if (!payload) return;
    try {
      const res = await fetch(payload.endpoint, {
        method: payload.method || 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload.body),
      });
      const data = await res.json();
      if (res.ok && data.ok !== false) {
        showToast('Fix applied successfully', 'success');
        hide();
      } else {
        showToast('Could not apply fix: ' + (data.error || 'Unknown error'), 'error');
      }
    } catch (e) {
      showToast('Could not apply fix: ' + e.message, 'error');
    }
  }

  applyBtn?.addEventListener('click', () => applyFix(_payload));
  dismissBtn?.addEventListener('click', hide);
  closeBtn?.addEventListener('click', hide);

  replySend?.addEventListener('click', async () => {
    const msg = replyInput?.value.trim();
    if (!msg) return;
    replySend.disabled = true;
    replyInput.value = '';

    // Show user bubble immediately
    _addBubble(msg, 'user');

    // Show loading indicator
    const loadingEl = _addBubble('···', 'loading');

    try {
      const res = await fetch('/api/kb/cross-check/respond', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          section:        _section,
          updatedText:    _updatedText,
          currentInsight: _insight,
          userMessage:    msg,
        }),
      });
      const data = await res.json();

      // Replace loading bubble with AI reply
      if (loadingEl) loadingEl.remove();
      const replyText = data.message || (data.hasInsight ? '' : 'Got it — no changes needed.');
      if (replyText) _addBubble(replyText, 'ai');

      if (data.hasInsight) {
        // Update state so further replies have correct context
        _insight = data.message || _insight;
        _payload = data.applyPayload || null;
        if (_payload && data.applyLabel) {
          applyBtn.textContent = data.applyLabel;
          applyBtn.hidden = false;
        } else {
          applyBtn.hidden = true;
        }
        // Update the main message to match
        msgEl.textContent = _insight;
      } else {
        // Adviser is done — auto-close after user has read the reply
        setTimeout(hide, 2800);
      }
    } catch (e) {
      if (loadingEl) loadingEl.remove();
      _addBubble('Sorry, something went wrong. Try again.', 'ai');
    } finally {
      replySend.disabled = false;
    }
  });

  // Allow Enter (without Shift) to send
  replyInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      replySend?.click();
    }
  });

  /**
   * Call after any KB section save.
   * @param {string} section  'goal' | 'tone' | 'prices' | 'scenarios'
   * @param {string} updatedText  Plain-text summary of what was saved
   */
  window.kbCrossCheck = async function (section, updatedText) {
    _section     = section;
    _updatedText = updatedText;
    try {
      const res = await fetch('/api/kb/cross-check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ section, updatedText }),
      });
      const data = await res.json();
      if (data.hasInsight) show(data);
    } catch (_) { /* silent — cross-check is advisory only */ }
  };
})();

// ─────────────────────────────────────────────────────────────────────────────
// KNOWLEDGE BASE TAB
// ─────────────────────────────────────────────────────────────────────────────

const kbToneInput   = document.getElementById('kb-tone-input');
const kbToneSave    = document.getElementById('kb-tone-save');
const kbToneResult  = document.getElementById('kb-tone-result');
const kbTonePreview = document.getElementById('kb-tone-preview');

const kbServiceSel   = document.getElementById('kb-service-select');
const kbCustomWrap   = document.getElementById('kb-custom-wrap');
const kbCustomName   = document.getElementById('kb-custom-name');
const kbSubcatSection = document.getElementById('kb-subcat-section');
const kbSubcatName   = document.getElementById('kb-subcat-name');
const kbPricingTime  = document.getElementById('kb-pricing-time');
const kbCommonQ      = document.getElementById('kb-common-q');
const kbThingsKnow   = document.getElementById('kb-things-know');
const kbAiSave       = document.getElementById('kb-ai-save');
const kbPriceList    = document.getElementById('kb-price-list');

const kbChatLog     = document.getElementById('kb-chat-log');
const kbChatInput   = document.getElementById('kb-chat-input');
const kbChatSend    = document.getElementById('kb-chat-send');

let kbChatHistory   = [];
let kbPricesCache   = {};

// ── Helpers ────────────────────────────────────────────────────────────────

function kbSetBusy(btn, busy, label) {
  btn.disabled = busy;
  if (label) btn.textContent = busy ? label : btn.dataset.defaultLabel || btn.textContent;
}

function kbRenderPrices(prices) {
  kbPricesCache = prices || {};
  kbPriceList.innerHTML = '';

  const keys = Object.keys(kbPricesCache);
  if (!keys.length) {
    kbPriceList.innerHTML = '<p class="kb-price-empty">No services saved yet — add your first one above.</p>';
    return;
  }

  keys.forEach(key => {
    const info = kbPricesCache[key];
    const card = document.createElement('div');
    card.className = 'kb-price-card';

    card.innerHTML = `
      <div class="kb-price-card__head">
        <button class="kb-price-card__toggle" aria-expanded="false" aria-label="Toggle section">
          <span class="kb-price-card__chevron">▸</span>
          <span class="kb-price-card__title" data-service-key="${key}">${info.label || key}</span>
          <button class="kb-price-card__rename" data-key="${key}" title="Rename" aria-label="Rename service">✏</button>
        </button>
        <button class="kb-price-card__del" data-key="${key}" title="Remove service" aria-label="Remove service">✕</button>
      </div>
    `;

    const body = document.createElement('div');
    body.className = 'kb-price-card__body kb-price-card__body--collapsed';

    // ── Booking process section ───────────────────────────────────────
    const processSection = document.createElement('div');
    processSection.className = 'kb-service-process';
    const processLabel = document.createElement('div');
    processLabel.className = 'kb-service-process__label';
    processLabel.textContent = '🔄 Booking Process';
    const processText = document.createElement('div');
    processText.className = 'kb-service-process__text kb-service-process__text--editable';
    processText.dataset.serviceKey = key;
    processText.title = 'Click to edit';
    if (info.booking_process) {
      processText.textContent = info.booking_process;
    } else {
      processText.innerHTML = '<span class="kb-service-process__placeholder">Click to add the booking process for this service — e.g. what info to gather, any special steps before pricing or booking in…</span>';
    }
    processSection.appendChild(processLabel);
    processSection.appendChild(processText);
    body.appendChild(processSection);

    // Inline edit handler for booking process
    processText.addEventListener('click', function () {
      if (processText.classList.contains('kb-service-process__text--active')) return;
      processText.classList.add('kb-service-process__text--active');

      const originalContent = info.booking_process || '';
      const textarea = document.createElement('textarea');
      textarea.className = 'kb-service-process__textarea';
      textarea.value = originalContent;
      textarea.placeholder = 'Describe the steps specific to this service — from first message to confirmed booking…';

      const actions = document.createElement('div');
      actions.className = 'kb-service-process__actions';
      actions.innerHTML = `
        <button class="kb-btn kb-btn--primary kb-svc-save-btn">✨ Save &amp; refine</button>
        <button class="kb-btn kb-btn--ghost kb-svc-cancel-btn">Cancel</button>
      `;

      processText.innerHTML = '';
      processText.appendChild(textarea);
      processText.appendChild(actions);
      textarea.focus();

      function cancelEdit() {
        processText.classList.remove('kb-service-process__text--active');
        if (info.booking_process) {
          processText.textContent = info.booking_process;
        } else {
          processText.innerHTML = '<span class="kb-service-process__placeholder">Click to add the booking process for this service — e.g. what info to gather, any special steps before pricing or booking in…</span>';
        }
      }

      actions.querySelector('.kb-svc-cancel-btn').addEventListener('click', e => { e.stopPropagation(); cancelEdit(); });
      textarea.addEventListener('keydown', e => { if (e.key === 'Escape') { e.preventDefault(); cancelEdit(); } });

      actions.querySelector('.kb-svc-save-btn').addEventListener('click', async e => {
        e.stopPropagation();
        const newText = textarea.value.trim();
        const saveBtn = actions.querySelector('.kb-svc-save-btn');
        saveBtn.textContent = 'Refining…';
        saveBtn.disabled = true;

        let finalText = newText;
        try {
          const refRes  = await fetch('/api/kb/refine-text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: newText, context: 'booking process for ' + (info.label || key) }),
          });
          const refData = await refRes.json();
          if (refData.refined && refData.refined.trim()) finalText = refData.refined.trim();
        } catch (_) {}

        saveBtn.textContent = 'Saving…';
        try {
          await fetch(`/api/kb/prices/${encodeURIComponent(key)}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ booking_process: finalText }),
          });
          info.booking_process = finalText;
          processText.classList.remove('kb-service-process__text--active');
          if (finalText) {
            processText.textContent = finalText;
          } else {
            processText.innerHTML = '<span class="kb-service-process__placeholder">Click to add the booking process for this service…</span>';
          }
          showToast('Saved ✓', 'success');
        } catch (_) {
          showToast('Could not save.', 'error');
          cancelEdit();
        }
      });
    });

    // ── Service-level things to know section ─────────────────────────
    const ttkSection = document.createElement('div');
    ttkSection.className = 'kb-service-ttk';
    const ttkLabel = document.createElement('div');
    ttkLabel.className = 'kb-service-ttk__label';
    ttkLabel.textContent = '📋 Things to Know (all ' + (info.label || key) + ' jobs)';
    const ttkText = document.createElement('div');
    ttkText.className = 'kb-service-ttk__text kb-service-ttk__text--editable';
    ttkText.dataset.serviceKey = key;
    ttkText.title = 'Click to edit';
    if (info.things_to_know) {
      ttkText.textContent = info.things_to_know;
    } else {
      ttkText.innerHTML = '<span class="kb-service-ttk__placeholder">Click to add general notes that apply to all ' + (info.label || key) + ' jobs — sub-category notes will override these where they overlap…</span>';
    }
    ttkSection.appendChild(ttkLabel);
    ttkSection.appendChild(ttkText);
    body.appendChild(ttkSection);

    ttkText.addEventListener('click', function () {
      if (ttkText.classList.contains('kb-service-ttk__text--active')) return;
      ttkText.classList.add('kb-service-ttk__text--active');

      const originalContent = info.things_to_know || '';
      const textarea = document.createElement('textarea');
      textarea.className = 'kb-service-ttk__textarea';
      textarea.value = originalContent;
      textarea.placeholder = 'General things to know for all ' + (info.label || key) + ' jobs…';

      const actions = document.createElement('div');
      actions.className = 'kb-service-ttk__actions';
      actions.innerHTML = `
        <button class="kb-btn kb-btn--primary kb-ttk-save-btn">✨ Save &amp; refine</button>
        <button class="kb-btn kb-btn--ghost kb-ttk-cancel-btn">Cancel</button>
      `;

      ttkText.innerHTML = '';
      ttkText.appendChild(textarea);
      ttkText.appendChild(actions);
      textarea.focus();

      function cancelTtk() {
        ttkText.classList.remove('kb-service-ttk__text--active');
        if (info.things_to_know) {
          ttkText.textContent = info.things_to_know;
        } else {
          ttkText.innerHTML = '<span class="kb-service-ttk__placeholder">Click to add general notes that apply to all ' + (info.label || key) + ' jobs — sub-category notes will override these where they overlap…</span>';
        }
      }

      actions.querySelector('.kb-ttk-cancel-btn').addEventListener('click', e => { e.stopPropagation(); cancelTtk(); });
      textarea.addEventListener('keydown', e => { if (e.key === 'Escape') { e.preventDefault(); cancelTtk(); } });

      actions.querySelector('.kb-ttk-save-btn').addEventListener('click', async e => {
        e.stopPropagation();
        const newText = textarea.value.trim();
        const saveBtn = actions.querySelector('.kb-ttk-save-btn');
        saveBtn.textContent = 'Refining…';
        saveBtn.disabled = true;

        let finalText = newText;
        try {
          const refRes = await fetch('/api/kb/refine-text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: newText, context: 'general things to know for ' + (info.label || key) }),
          });
          const refData = await refRes.json();
          if (refData.refined && refData.refined.trim()) finalText = refData.refined.trim();
        } catch (_) {}

        saveBtn.textContent = 'Saving…';
        try {
          await fetch(`/api/kb/prices/${encodeURIComponent(key)}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ things_to_know: finalText }),
          });
          info.things_to_know = finalText;
          ttkText.classList.remove('kb-service-ttk__text--active');
          if (finalText) {
            ttkText.textContent = finalText;
          } else {
            ttkText.innerHTML = '<span class="kb-service-ttk__placeholder">Click to add general notes that apply to all ' + (info.label || key) + ' jobs — sub-category notes will override these where they overlap…</span>';
          }
          showToast('Saved ✓', 'success');
        } catch (_) {
          showToast('Could not save.', 'error');
          cancelTtk();
        }
      });
    });

    const subCats = info.sub_categories || {};
    const subKeys = Object.keys(subCats);

    if (subKeys.length) {
      subKeys.forEach(scKey => {
        const sc = subCats[scKey];
        const scCard = document.createElement('div');
        scCard.className = 'kb-subcat-card';

        let sections = '';
        if (sc.pricing_and_time) {
          sections += `<div class="kb-subcat-section">
            <div class="kb-subcat-section__label">💰 Pricing &amp; Time</div>
            <div class="kb-subcat-section__text kb-subcat-section__text--editable" data-field="pricing_and_time" data-service="${key}" data-subcat="${scKey}" title="Click to edit">${sc.pricing_and_time}</div>
          </div>`;
        }
        if (sc.common_questions) {
          sections += `<div class="kb-subcat-section">
            <div class="kb-subcat-section__label">❓ Common Questions</div>
            <div class="kb-subcat-section__text kb-subcat-section__text--editable" data-field="common_questions" data-service="${key}" data-subcat="${scKey}" title="Click to edit">${sc.common_questions}</div>
          </div>`;
        }
        if (sc.things_to_know) {
          sections += `<div class="kb-subcat-section">
            <div class="kb-subcat-section__label">📋 Things to Know</div>
            <div class="kb-subcat-section__text kb-subcat-section__text--editable" data-field="things_to_know" data-service="${key}" data-subcat="${scKey}" title="Click to edit">${sc.things_to_know}</div>
          </div>`;
        }

        scCard.innerHTML = `
          <div class="kb-subcat-card__head">
            <span class="kb-subcat-card__chevron">▸</span>
            <span class="kb-subcat-card__label">${sc.label || scKey}</span>
            <button class="kb-subcat-del" data-service="${key}" data-subcat="${scKey}" title="Remove sub-category">✕</button>
          </div>
          <div class="kb-subcat-card__body kb-subcat-card__body--collapsed">${sections}</div>
        `;

        scCard.querySelector('.kb-subcat-card__head').addEventListener('click', function (e) {
          if (e.target.closest('.kb-subcat-del')) return;
          const scBody = scCard.querySelector('.kb-subcat-card__body');
          const chev   = scCard.querySelector('.kb-subcat-card__chevron');
          const isOpen = !scBody.classList.contains('kb-subcat-card__body--collapsed');
          scBody.classList.toggle('kb-subcat-card__body--collapsed', isOpen);
          if (chev) chev.textContent = isOpen ? '▸' : '▾';
        });

        body.appendChild(scCard);
      });
    } else {
      // Legacy fallback for old-format entries
      const variants = info.variants || [];
      if (variants.length) {
        const sec = document.createElement('div');
        sec.innerHTML = `<div class="kb-price-section__label">Pricing</div>`;
        variants.forEach(v => {
          const pStr = v.price != null ? `£${v.price}${v.price_to ? '–£' + v.price_to : ''}` : 'TBC';
          sec.innerHTML += `<div class="kb-variant"><span class="kb-variant__name">${v.name || 'Standard'}</span><span class="kb-variant__price">${pStr}</span>${v.notes ? `<span class="kb-variant__note">${v.notes}</span>` : ''}</div>`;
        });
        body.appendChild(sec);
      } else if (info.price_from != null || info.notes) {
        const pStr = info.price_from != null ? `£${info.price_from}${info.price_to ? '–£' + info.price_to : ''}` : '';
        const sec = document.createElement('div');
        sec.innerHTML = `<div class="kb-price-section__label">${pStr ? 'Pricing' : 'Notes'}</div><div class="kb-variant">${pStr ? `<span class="kb-variant__price">${pStr}</span>` : ''}${info.notes ? `<span class="kb-variant__note">${info.notes}</span>` : ''}</div>`;
        body.appendChild(sec);
      }
    }

    card.appendChild(body);
    kbPriceList.appendChild(card);
  });

  // Accordion toggle
  kbPriceList.querySelectorAll('.kb-price-card__toggle').forEach(toggle => {
    toggle.addEventListener('click', () => {
      const card = toggle.closest('.kb-price-card');
      const body = card.querySelector('.kb-price-card__body');
      const chev = toggle.querySelector('.kb-price-card__chevron');
      const open = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', String(!open));
      if (body) body.classList.toggle('kb-price-card__body--collapsed', open);
      if (chev) chev.textContent = open ? '▸' : '▾';
    });
  });

  // Rename service headline
  kbPriceList.querySelectorAll('.kb-price-card__rename').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation(); // don't toggle accordion
      const serviceKey  = btn.dataset.key;
      const titleEl     = btn.closest('.kb-price-card__toggle').querySelector('.kb-price-card__title');
      if (!titleEl || titleEl.querySelector('input')) return; // already editing

      const originalLabel = titleEl.textContent.trim();
      const input = document.createElement('input');
      input.className = 'kb-price-card__rename-input';
      input.value = originalLabel;
      input.type  = 'text';

      titleEl.textContent = '';
      titleEl.appendChild(input);
      input.focus();
      input.select();

      async function saveLabel() {
        const newLabel = input.value.trim();
        titleEl.textContent = newLabel || originalLabel;
        if (!newLabel || newLabel === originalLabel) return;
        try {
          await fetch(`/api/kb/prices/${encodeURIComponent(serviceKey)}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ label: newLabel }),
          });
          showToast('Renamed ✓', 'success');
        } catch (_) {
          titleEl.textContent = originalLabel;
          showToast('Could not rename.', 'error');
        }
      }

      input.addEventListener('keydown', e => {
        if (e.key === 'Enter')  { e.preventDefault(); input.blur(); }
        if (e.key === 'Escape') { titleEl.textContent = originalLabel; }
      });
      input.addEventListener('blur', saveLabel);
    });
  });

  // Delete service — two-step confirmation
  kbPriceList.querySelectorAll('.kb-price-card__del').forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.dataset.confirming === 'true') {
        kbDeletePrice(btn.dataset.key);
        return;
      }
      btn.dataset.confirming = 'true';
      btn.textContent = 'Delete?';
      btn.classList.add('kb-price-card__del--confirm');
      const reset = () => {
        btn.dataset.confirming = '';
        btn.textContent = '✕';
        btn.classList.remove('kb-price-card__del--confirm');
        document.removeEventListener('click', outsideClick);
      };
      const outsideClick = e => { if (e.target !== btn) reset(); };
      setTimeout(() => document.addEventListener('click', outsideClick), 0);
      setTimeout(reset, 4000);
    });
  });

  // Delete sub-category
  kbPriceList.querySelectorAll('.kb-subcat-del').forEach(btn => {
    btn.addEventListener('click', () => {
      kbDeleteSubcat(btn.dataset.service, btn.dataset.subcat);
    });
  });

  // Inline edit — click any editable section text to edit it
  kbPriceList.querySelectorAll('.kb-subcat-section__text--editable').forEach(textEl => {
    textEl.addEventListener('click', function onTextClick() {
      if (textEl.classList.contains('kb-subcat-section__text--active')) return;
      textEl.classList.add('kb-subcat-section__text--active');

      const field        = textEl.dataset.field;
      const service      = textEl.dataset.service;
      const subcat       = textEl.dataset.subcat;
      const originalText = textEl.textContent.trim();

      const textarea = document.createElement('textarea');
      textarea.className = 'kb-subcat-edit-textarea';
      textarea.value = originalText;

      const actions = document.createElement('div');
      actions.className = 'kb-subcat-edit-actions';
      actions.innerHTML = `
        <button class="kb-btn kb-btn--primary kb-subcat-save-btn">✨ Save &amp; refine</button>
        <button class="kb-btn kb-btn--ghost kb-subcat-cancel-btn">Cancel</button>
      `;

      textEl.innerHTML = '';
      textEl.appendChild(textarea);
      textEl.appendChild(actions);
      textarea.focus();
      textarea.setSelectionRange(textarea.value.length, textarea.value.length);

      function cancel() {
        textEl.classList.remove('kb-subcat-section__text--active');
        textEl.innerHTML = originalText;
      }

      actions.querySelector('.kb-subcat-cancel-btn').addEventListener('click', e => {
        e.stopPropagation();
        cancel();
      });

      textarea.addEventListener('keydown', e => {
        if (e.key === 'Escape') { e.preventDefault(); cancel(); }
      });

      actions.querySelector('.kb-subcat-save-btn').addEventListener('click', async e => {
        e.stopPropagation();
        const newText = textarea.value.trim();
        if (!newText) return;

        const saveBtn = actions.querySelector('.kb-subcat-save-btn');
        saveBtn.textContent = 'Refining…';
        saveBtn.disabled = true;

        let finalText = newText;
        try {
          const refRes  = await fetch('/api/kb/refine-text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: newText, context: field.replace(/_/g, ' ') + ' for ' + subcat }),
          });
          const refData = await refRes.json();
          if (refData.refined && refData.refined.trim()) finalText = refData.refined.trim();
        } catch (_) {}

        try {
          await fetch(`/api/kb/prices/${encodeURIComponent(service)}/sub_categories/${encodeURIComponent(subcat)}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ [field]: finalText }),
          });
          textEl.classList.remove('kb-subcat-section__text--active');
          textEl.textContent = finalText;
          // Update data attribute so next click has the new text
          textEl.dataset.original = finalText;
          showToast('Saved ✓', 'success');
        } catch (_) {
          showToast('Could not save — try again.', 'error');
          cancel();
        }
      });
    });
  });
}

function kbAddChatBubble(role, text) {
  const wrap = document.createElement('div');
  wrap.className = `kb-bubble kb-bubble--${role}`;
  const span = document.createElement('span');
  span.className = 'kb-bubble__text';
  span.textContent = text;
  wrap.appendChild(span);
  kbChatLog.appendChild(wrap);
  kbChatLog.scrollTop = kbChatLog.scrollHeight;
  return wrap;
}

function kbAddActionBubble(text) {
  const wrap = document.createElement('div');
  wrap.className = 'kb-bubble kb-bubble--action';
  const span = document.createElement('span');
  span.className = 'kb-bubble__text';
  span.textContent = text;
  wrap.appendChild(span);
  kbChatLog.appendChild(wrap);
  kbChatLog.scrollTop = kbChatLog.scrollHeight;
}

// ── Load on tab open ───────────────────────────────────────────────────────

async function kbLoad() {
  try {
    const res  = await fetch('/api/kb/status');
    const data = await res.json();
    if (data.tone) {
      kbTonePreview.textContent = data.tone;
      kbToneResult.classList.remove('hidden');
    }
    kbRenderPrices(data.prices);
  } catch (err) {
    console.warn('KB load failed', err);
  }
}

// ── Tone ──────────────────────────────────────────────────────────────────

if (kbToneSave) {
  kbToneSave.dataset.defaultLabel = kbToneSave.textContent;
  kbToneSave.addEventListener('click', async () => {
    const raw = kbToneInput?.value.trim();
    if (!raw) { showToast('Please describe your tone first.', 'error'); return; }
    kbSetBusy(kbToneSave, true, 'Formatting…');
    try {
      const res  = await fetch('/api/kb/tone', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to save tone.');
      kbTonePreview.textContent = data.tone;
      kbToneResult.classList.remove('hidden');
      kbToneInput.value = '';
      showToast('Tone rules saved!');
      window.kbCrossCheck?.('tone', data.tone || '');
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      kbSetBusy(kbToneSave, false, 'Save & Format with AI');
    }
  });
}

// ── Prices ────────────────────────────────────────────────────────────────

function kbGetServiceKey() {
  const sel = kbServiceSel?.value;
  if (!sel) return null;
  if (sel === 'custom') {
    const name = kbCustomName?.value.trim();
    if (!name) return null;
    return name.toLowerCase().replace(/[^a-z0-9]+/g, '_');
  }
  return sel;
}

function kbGetServiceLabel() {
  const sel = kbServiceSel?.value;
  if (sel === 'custom') return kbCustomName?.value.trim() || 'Custom';
  return kbServiceSel?.options[kbServiceSel.selectedIndex]?.text || sel;
}

if (kbServiceSel) {
  kbServiceSel.addEventListener('change', () => {
    const sel = kbServiceSel.value;
    kbCustomWrap?.classList.toggle('hidden', sel !== 'custom');
    kbSubcatSection?.classList.toggle('hidden', !sel);
  });
}

async function kbDeletePrice(key) {
  try {
    const res  = await fetch(`/api/kb/prices/${encodeURIComponent(key)}`, { method: 'DELETE' });
    const data = await res.json();
    kbRenderPrices(data);
    showToast('Service removed.');
  } catch (err) {
    showToast('Could not remove service.', 'error');
  }
}

async function kbDeleteSubcat(serviceKey, subcatKey) {
  try {
    const res  = await fetch(`/api/kb/prices/${encodeURIComponent(serviceKey)}/sub_categories/${encodeURIComponent(subcatKey)}`, { method: 'DELETE' });
    const data = await res.json();
    kbRenderPrices(data);
    showToast('Sub-category removed.');
  } catch (err) {
    showToast('Could not remove sub-category.', 'error');
  }
}

if (kbAiSave) {
  kbAiSave.dataset.defaultLabel = kbAiSave.textContent;
  kbAiSave.addEventListener('click', async () => {
    const sel = kbServiceSel?.value;
    if (!sel) { showToast('Please select a service.', 'error'); return; }
    const subcatLabel = kbSubcatName?.value.trim();
    if (!subcatLabel) { showToast('Please enter a sub-category name.', 'error'); return; }
    if (sel === 'custom' && !kbCustomName?.value.trim()) {
      showToast('Please enter a service name.', 'error'); return;
    }
    const serviceKey   = kbGetServiceKey();
    const serviceLabel = kbGetServiceLabel();
    kbSetBusy(kbAiSave, true, 'Saving…');
    try {
      const res = await fetch('/api/kb/prices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          service: serviceKey,
          label: serviceLabel,
          sub_category_label: subcatLabel,
          pricing_and_time: kbPricingTime?.value.trim() || '',
          common_questions: kbCommonQ?.value.trim() || '',
          things_to_know: kbThingsKnow?.value.trim() || '',
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to save.');
      kbRenderPrices(data);
      if (kbSubcatName) kbSubcatName.value = '';
      if (kbPricingTime) kbPricingTime.value = '';
      if (kbCommonQ) kbCommonQ.value = '';
      if (kbThingsKnow) kbThingsKnow.value = '';
      showToast('Sub-category saved!');
      window.kbCrossCheck?.('prices', `Service: ${serviceLabel} / ${subcatLabel}`);
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      kbSetBusy(kbAiSave, false, 'Save Sub-category');
    }
  });
}

// ── Chat ──────────────────────────────────────────────────────────────────

async function kbSendChat() {
  const msg = kbChatInput?.value.trim();
  if (!msg) return;
  kbChatInput.value = '';

  kbAddChatBubble('user', msg);
  kbChatHistory.push({ role: 'user', content: msg });

  const thinkingBubble = kbAddChatBubble('ai', '…');

  if (kbChatSend) kbChatSend.disabled = true;

  try {
    const res  = await fetch('/api/kb/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, history: kbChatHistory.slice(-12) }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Chat failed.');

    thinkingBubble.querySelector('.kb-bubble__text').textContent = data.reply;
    kbChatHistory.push({ role: 'assistant', content: data.reply });

    if (data.action) {
      const { type, prices, tone, scenarios } = data.action;
      if (type === 'prices_updated' && prices) {
        kbRenderPrices(prices);
        kbAddActionBubble('✓ Price guide updated successfully.');
      } else if (type === 'tone_updated' && tone) {
        kbTonePreview.textContent = tone;
        kbToneResult.classList.remove('hidden');
        kbAddActionBubble('✓ Tone rules updated successfully.');
      } else if (type === 'scenario_updated' && scenarios) {
        scenRender(scenarios);
        kbAddActionBubble('✓ Diagnostic scenario saved successfully.');
      }
    }
  } catch (err) {
    thinkingBubble.querySelector('.kb-bubble__text').textContent = `Error: ${err.message}`;
  } finally {
    if (kbChatSend) kbChatSend.disabled = false;
    kbChatLog.scrollTop = kbChatLog.scrollHeight;
  }
}

if (kbChatSend) kbChatSend.addEventListener('click', kbSendChat);
if (kbChatInput) {
  kbChatInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); kbSendChat(); }
  });
}

document.querySelector('[data-tab="kb"]')?.addEventListener('click', kbLoad);

// ── Diagnostic Scenarios ──────────────────────────────────────────────────

const scenService  = document.getElementById('scen-service');
const scenCategory = document.getElementById('scen-category');
const scenContent  = document.getElementById('scen-content');
const scenAdd      = document.getElementById('scen-add');
const scenList     = document.getElementById('scen-list');

const CATEGORY_ORDER = [
  'fault_diagnosis', 'common_issues', 'what_to_expect',
  'pricing_concerns', 'after_care', 'access_safety', 'seasonal', 'general_advice'
];

function scenRender(scenarios) {
  if (!scenList) return;
  if (!scenarios || !scenarios.length) {
    scenList.innerHTML = '<p class="scen-empty">No scenarios added yet. Add your first one above.</p>';
    return;
  }

  // Group by service_label → category_label
  const grouped = {};
  for (const s of scenarios) {
    const svc = s.service_label || s.service || 'General';
    const cat = s.category_label || s.category || 'General';
    if (!grouped[svc]) grouped[svc] = {};
    if (!grouped[svc][cat]) grouped[svc][cat] = [];
    grouped[svc][cat].push(s);
  }

  let html = '';
  for (const [svcLabel, cats] of Object.entries(grouped)) {
    html += `<div class="scen-service-group">
      <div class="scen-service-title">${svcLabel}</div>`;
    for (const [catLabel, items] of Object.entries(cats)) {
      html += `<div class="scen-cat-group">
        <div class="scen-cat-label">${catLabel}</div>
        <ul class="scen-bullets">`;
      for (const item of items) {
        html += `<li class="scen-bullet">
          <span class="scen-bullet__text">${item.content}</span>
          <button class="scen-del" data-id="${item.id}" title="Remove">×</button>
        </li>`;
      }
      html += `</ul></div>`;
    }
    html += `</div>`;
  }
  scenList.innerHTML = html;

  scenList.querySelectorAll('.scen-del').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.id;
      try {
        const res  = await fetch(`/api/kb/scenarios/${id}`, { method: 'DELETE' });
        const data = await res.json();
        scenRender(data);
        showToast('Scenario removed.');
      } catch {
        showToast('Could not remove scenario.', 'error');
      }
    });
  });
}

async function scenLoad() {
  try {
    const res  = await fetch('/api/kb/scenarios');
    const data = await res.json();
    scenRender(data);
  } catch {
    // silently ignore on tab load
  }
}

if (scenAdd) {
  scenAdd.dataset.defaultLabel = scenAdd.textContent;
  scenAdd.addEventListener('click', async () => {
    const service = scenService?.value;
    if (!service) { showToast('Please pick a service.', 'error'); return; }
    const content = scenContent?.value.trim();
    if (!content) { showToast('Please enter the scenario knowledge.', 'error'); return; }

    const serviceOpt  = scenService.options[scenService.selectedIndex];
    const categoryOpt = scenCategory.options[scenCategory.selectedIndex];

    kbSetBusy(scenAdd, true, 'Structuring with AI…');
    try {
      const res  = await fetch('/api/kb/scenarios', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          service:        service,
          service_label:  serviceOpt?.dataset.label || serviceOpt?.text || service,
          category:       scenCategory?.value,
          category_label: categoryOpt?.dataset.label || categoryOpt?.text || scenCategory?.value,
          content,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to save scenario.');
      scenRender(data);
      const _scenSvc = scenService?.options[scenService.selectedIndex]?.text || '';
      const _scenCat = scenCategory?.options[scenCategory.selectedIndex]?.text || '';
      const _scenTxt = content;
      scenContent.value = '';
      showToast('Scenario added!');
      window.kbCrossCheck?.('scenarios', `Service: ${_scenSvc}\nCategory: ${_scenCat}\nContent: ${_scenTxt}`);
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      kbSetBusy(scenAdd, false, scenAdd.dataset.defaultLabel);
    }
  });
}

scenLoad();


// ═══════════════════════════════════════════════════════
// MESSAGES TAB — WhatsApp dark workspace
// ═══════════════════════════════════════════════════════

// ── Demo / fallback data ─────────────────────────────────
function waMakeDemoData() {
  const now = Date.now();
  const ago = m => new Date(now - m * 60000).toISOString();
  const soon = m => new Date(now + m * 60000).toISOString();
  return [
    {
      id: '+447700900123', phoneNumber: '+44 7700 900123', displayName: 'Ava Thompson',
      aiEnabled: true, unreadCount: 2, assignedResponderId: 'demo-agent',
      messages: [
        { id: 'ava-1', text: 'Hi, can you quote for a driveway clean in Putney?', author: 'customer', direction: 'inbound', status: 'sent', sentAt: ago(42), timestamp: ago(42) },
        { id: 'ava-2', text: 'Of course. Roughly how large is the driveway, and is there outside water access?', author: 'ai', direction: 'outbound', status: 'sent', sentAt: ago(40), timestamp: ago(40) },
        { id: 'ava-3', text: 'Two cars plus a small front path. There is an outside tap.', author: 'customer', direction: 'inbound', status: 'sent', sentAt: ago(23), timestamp: ago(23) },
        { id: 'ava-4', text: 'Thanks Ava. That sounds straightforward. We can clean the driveway and path this week — send the postcode and I will confirm the exact slot.', author: 'ai', direction: 'outbound', status: 'scheduled', timestamp: ago(2), scheduledSendAt: soon(3) },
      ],
    },
    {
      id: '+447700900456', phoneNumber: '+44 7700 900456', displayName: 'Mason Reed',
      aiEnabled: true, unreadCount: 1, assignedResponderId: 'demo-agent',
      messages: [
        { id: 'mason-1', text: 'Do you clean sandstone patios? Mine has gone green after winter.', author: 'customer', direction: 'inbound', status: 'sent', sentAt: ago(78), timestamp: ago(78) },
      ],
    },
    {
      id: '+447700900789', phoneNumber: '+44 7700 900789', displayName: 'Nadia Patel',
      aiEnabled: false, unreadCount: 0, assignedResponderId: 'demo-agent',
      messages: [
        { id: 'nadia-1', text: 'Can we book the same window cleaner as last month?', author: 'customer', direction: 'inbound', status: 'sent', sentAt: ago(184), timestamp: ago(184) },
        { id: 'nadia-2', text: 'Yes, I have reserved Tuesday morning for you. I will send the confirmation shortly.', author: 'agent', direction: 'outbound', status: 'sent', sentAt: ago(171), timestamp: ago(171) },
      ],
    },
  ];
}

// ── State ────────────────────────────────────────────────
let waConversations  = [];
let waQuoteRequests  = [];
let waCoverageAlerts = [];
let waAttentionAlerts = [];
let waBookingsData   = { bookings: [], weekCount: 0, todayCount: 0, unseenCount: 0, engineerStats: [], lastSeen: null };
let waSelectedId    = null;
let waSelectedConvo = null;
let waCurrentView   = 'overview';
let waIsDemoMode    = true;
let waCountdownTimer = null;
let waPollTimer     = null;
let waListPollTimer  = null;
let waSSE            = null;
let waBusy          = false;

// ── Helpers ──────────────────────────────────────────────
function waInitials(name = 'PW') {
  const p = name.trim().split(/\s+/);
  return ((p[0]?.[0] || 'P') + (p[1]?.[0] || p[0]?.[1] || 'W')).toUpperCase().slice(0, 2);
}

function waFmtTime(msg) {
  if (!msg) return '';
  const d = new Date(msg.sentAt || msg.scheduledSendAt || msg.timestamp);
  if (isNaN(d)) return '';
  return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(d);
}

function waStatusLabel(msg) {
  if (msg.status === 'scheduled') {
    if (!msg.scheduledSendAt) return 'Scheduled to send soon';
    const secs = Math.max(0, Math.floor((new Date(msg.scheduledSendAt).getTime() - Date.now()) / 1000));
    const m = Math.floor(secs / 60);
    const s = String(secs % 60).padStart(2, '0');
    return `Sending in ${m}:${s}`;
  }
  if (msg.status === 'cancelled') return msg.error || 'Cancelled';
  if (msg.status === 'failed')    return msg.error || 'Failed to send';
  if (msg.status === 'drafting')  return 'Drafting…';
  if (msg.status === 'sending')   return 'Sending…';
  return msg.status;
}

function waDeliveryTick(msg) {
  if (msg.direction !== 'outbound') return '';
  if (['drafting','scheduled','cancelled','failed'].includes(msg.status)) return '';
  const s = msg.status;
  if (s === 'queued' || s === 'sending') {
    return `<span class="wa-tick wa-tick--clock" title="Sending">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
    </span>`;
  }
  if (s === 'sent') {
    return `<span class="wa-tick wa-tick--sent" title="Sent">
      <svg width="14" height="10" viewBox="0 0 14 10" fill="none"><path d="M1 5L5 9L13 1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </span>`;
  }
  if (s === 'delivered') {
    return `<span class="wa-tick wa-tick--delivered" title="Delivered">
      <svg width="18" height="10" viewBox="0 0 18 10" fill="none">
        <path d="M1 5L5 9L13 1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M5 5L9 9L17 1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </span>`;
  }
  if (s === 'read') {
    return `<span class="wa-tick wa-tick--read" title="Read">
      <svg width="18" height="10" viewBox="0 0 18 10" fill="none">
        <path d="M1 5L5 9L13 1" stroke="#53bdeb" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M5 5L9 9L17 1" stroke="#53bdeb" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </span>`;
  }
  return '';
}

function waPendingMsg(convo) {
  if (!convo) return null;
  return [...convo.messages].reverse().find(m => m.author === 'ai' && ['scheduled','drafting','sending'].includes(m.status)) || null;
}

function waPendingConvos(list) {
  return list.filter(c => {
    const lm = c.lastMessage || c.messages?.[c.messages.length - 1];
    return lm?.author === 'ai' && ['scheduled','drafting','sending'].includes(lm.status);
  });
}

// ── API calls (with demo fallback) ───────────────────────
async function waApiGet(path) {
  const r = await fetch('/api/messages' + path);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function waApiPost(path, body) {
  const r = await fetch('/api/messages' + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function waApiFetch(path, opts = {}) {
  const r = await fetch('/api' + path, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function waLoadConversations() {
  try {
    const data = await waApiGet('/conversations');
    const list = data.conversations || data || [];
    // Ensure lastMessage populated from messages array
    waConversations = list.map(c => {
      if (!c.lastMessage && c.messages?.length) c.lastMessage = c.messages[c.messages.length - 1];
      return c;
    });
    waIsDemoMode = false;
  } catch (_) {
    waConversations = waMakeDemoData().map(c => {
      c.lastMessage = c.messages[c.messages.length - 1]; return c;
    });
    waIsDemoMode = true;
  }
  _waUpdateAiActivityBanner();
}

// Global top-bar flashing light: lit whenever the AI is drafting/scheduling/sending
// a reply in ANY conversation, so operators always know the AI is relaying their
// quote answers to the customer — even from the overview or quotes screen.
function _waUpdateAiActivityBanner() {
  const el = document.getElementById('wa-ai-activity-banner');
  if (!el) return;
  let pending = 0;
  for (const c of (waConversations || [])) {
    // Scan all messages, not just lastMessage — a customer can double-text after
    // the AI draft is queued, pushing the pending AI reply out of last position.
    const msgs = c.messages && c.messages.length
      ? c.messages
      : (c.lastMessage ? [c.lastMessage] : []);
    const hasPending = msgs.some(m => m && m.author === 'ai'
      && ['scheduled','drafting','sending'].includes(m.status));
    if (hasPending) pending++;
  }
  if (pending > 0) {
    el.style.display = '';
    const t = el.querySelector('.wa-ai-activity-banner__text');
    if (t) t.textContent = pending === 1 ? 'AI is replying…' : `AI is replying · ${pending} chats`;
    if (!el._wired) {
      el._wired = true;
      el.addEventListener('click', () => { waShowView('conversations'); waRenderConvoList(); });
    }
  } else {
    el.style.display = 'none';
  }
}

async function waLoadQuoteRequests() {
  if (waIsDemoMode) return;
  try {
    waQuoteRequests = await waApiFetch('/quote-requests');
  } catch (_) {
    waQuoteRequests = [];
  }
}

async function waLoadBookings() {
  if (waIsDemoMode) return;
  try {
    waBookingsData = await waApiFetch('/bookings');
  } catch (_) {
    waBookingsData = { bookings: [], weekCount: 0, todayCount: 0, unseenCount: 0, engineerStats: [], lastSeen: null };
  }
}

async function waLoadCoverageAlerts() {
  if (waIsDemoMode) return;
  try {
    waCoverageAlerts = await waApiFetch('/scheduling/coverage-alerts');
  } catch (_) {
    waCoverageAlerts = [];
  }
}

async function waDismissCoverageAlert(id) {
  try {
    await waApiFetch(`/scheduling/coverage-alerts/${id}/dismiss`, { method: 'POST' });
  } catch (_) {}
  await waLoadCoverageAlerts();
  waRenderOverview();
}

async function waLoadAttentionAlerts() {
  if (waIsDemoMode) return;
  try {
    waAttentionAlerts = await waApiFetch('/attention-alerts');
  } catch (_) {
    waAttentionAlerts = [];
  }
}

async function waDismissAttentionAlert(id) {
  try {
    await waApiFetch(`/attention-alerts/${id}/dismiss`, { method: 'POST' });
  } catch (_) {}
  await waLoadAttentionAlerts();
  waRenderOverview();
}

async function waLoadConversation(id) {
  if (waIsDemoMode) {
    return waConversations.find(c => c.id === id) || null;
  }
  try {
    return await waApiGet('/conversations/' + encodeURIComponent(id));
  } catch (_) {
    return waConversations.find(c => c.id === id) || null;
  }
}

// ── Navigation ───────────────────────────────────────────
function waShowView(name) {
  waCurrentView = name;
  const views = ['overview', 'conversations', 'chat', 'settings', 'quotes', 'bookings'];
  views.forEach(v => {
    const el = document.getElementById('wa-view-' + v);
    if (el) el.classList.toggle('wa-hidden', v !== name);
  });
  const nav = document.getElementById('wa-bottom-nav');
  const title = document.getElementById('wa-title');
  if (name === 'chat') {
    if (nav) nav.style.display = 'none';
    if (title) title.textContent = 'Conversation';
    waStartCountdown();
    waStartPoll();
  } else {
    if (nav) nav.style.display = '';
    if (title) title.textContent = 'PowWash Workspace';
    waStopCountdown();
    waStopPoll();
    // Update active nav tab
    document.querySelectorAll('.wa-nav-item').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.waview === name);
    });
  }
  // Scroll to top of new view
  const viewEl = document.getElementById('wa-view-' + name);
  if (viewEl) viewEl.scrollTop = 0;
}

// ── Render: Overview ─────────────────────────────────────
let waSystemErrors = [];

async function waCheckSystemStatus() {
  try {
    const s = await waApiGet('/calendar/status');
    const errs = [];
    if (!s.connected) {
      const msg = s.hasCredentials
        ? 'Google Calendar disconnected — go to Settings > Calendar to reconnect.'
        : 'Google Calendar not set up — go to Settings > Calendar to add credentials.';
      errs.push({ key: 'calendar', label: 'Calendar not connected', detail: msg, tab: 'calendar' });
    }
    waSystemErrors = errs;
  } catch (_) {
    waSystemErrors = [];
  }
  waRenderOverview();
}

// ── Notifications panel (attention alerts — needs human response) ─────────
function waRenderNotifications() {
  const el = document.getElementById('wa-overview-notifications');
  if (!el) return;
  const attnAlerts = (waAttentionAlerts || []).filter(a => a.status === 'pending');
  if (!attnAlerts.length) { el.innerHTML = ''; return; }
  el.innerHTML = `
    <div class="wa-notif-panel">
      <div class="wa-notif-panel__header">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
        <span>Notifications</span>
        <span class="wa-notif-count">${attnAlerts.length}</span>
      </div>
      ${attnAlerts.map(a => `
        <div class="wa-notif-item" data-attn-conv="${_schedEsc(a.conversationId || '')}">
          <div class="wa-notif-item__body">
            <strong>${_schedEsc(a.displayName || 'A customer')} needs a human reply</strong>
            <span>${_schedEsc(a.reason || 'The AI handed this conversation over — please reply manually.')}</span>
          </div>
          <div class="wa-notif-item__actions">
            <button class="wa-notif-open-btn" data-attn-conv="${_schedEsc(a.conversationId || '')}">Open chat</button>
            <button class="wa-notif-dismiss-btn" data-attn-id="${_schedEsc(a.id)}">Dismiss</button>
          </div>
        </div>`).join('')}
    </div>`;
  el.querySelectorAll('.wa-notif-open-btn').forEach(btn => {
    btn.addEventListener('click', () => waOpenConversation(btn.dataset.attnConv));
  });
  el.querySelectorAll('.wa-notif-dismiss-btn').forEach(btn => {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      waDismissAttentionAlert(btn.dataset.attnId);
    });
  });
}

function waRenderOverview() {
  const pending = waPendingConvos(waConversations);
  const unread  = waConversations.reduce((t, c) => t + (c.unreadCount || 0), 0);

  // Conversations metric: show unread when > 0, total otherwise
  document.getElementById('wa-metric-convos-val').textContent = unread > 0 ? unread : waConversations.length;
  const convosLabel = document.querySelector('#wa-metric-convos .wa-metric-label');
  if (convosLabel) convosLabel.textContent = unread > 0 ? 'Unread' : 'Conversations';
  document.getElementById('wa-metric-convos')?.classList.toggle('has-unread', unread > 0);

  // Conversations nav badge
  const convBadge = document.getElementById('wa-nav-convos-badge');
  if (convBadge) { convBadge.textContent = unread; convBadge.style.display = unread > 0 ? 'flex' : 'none'; }

  // Notifications panel (attention alerts)
  waRenderNotifications();

  // System error banners
  const errBannerEl = document.getElementById('wa-overview-errors');
  if (errBannerEl) {
    errBannerEl.innerHTML = waSystemErrors.map(e => `
      <div class="wa-error-banner" data-err-tab="${e.tab || ''}">
        <svg class="wa-error-banner__icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        <div class="wa-error-banner__body">
          <strong>⚠ Error — ${e.label}</strong>
          <span>${e.detail}</span>
        </div>
        <svg class="wa-error-banner__chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
      </div>`).join('');
    errBannerEl.querySelectorAll('.wa-error-banner[data-err-tab]').forEach(el => {
      const tab = el.dataset.errTab;
      if (tab) el.addEventListener('click', () => {
        document.querySelector(`[data-tab="${tab}"]`)?.click();
      });
    });

    // Coverage-gap alerts — the AI has gone SILENT because the only engineers
    // covering a requested area are unticked or have no calendar linked.
    const covAlerts = (waCoverageAlerts || []).filter(a => a.status === 'pending');
    if (covAlerts.length) {
      errBannerEl.innerHTML += covAlerts.map(a => `
        <div class="wa-error-banner wa-coverage-banner" data-cov-conv="${_schedEsc(a.conversationId || '')}">
          <svg class="wa-error-banner__icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          <div class="wa-error-banner__body">
            <strong>⚠ Coverage gap — AI is paused for ${_schedEsc(a.displayName || 'a customer')}</strong>
            <span>No bookable engineer for ${a.postcode ? `<code>${_schedEsc(a.postcode)}</code>` : 'this area'}${a.service ? ` · ${_schedEsc(a.service)}` : ''}. ${a.blockedEngineers ? `Only ${_schedEsc(a.blockedEngineers)} cover it, but they're unticked or have no calendar.` : ''} The customer has had no reply — assign a calendar / tick an engineer, or reply manually.</span>
          </div>
          <button class="wa-coverage-dismiss" data-cov-id="${_schedEsc(a.id)}" title="Dismiss">Dismiss</button>
        </div>`).join('');
      errBannerEl.querySelectorAll('.wa-coverage-banner').forEach(el => {
        const convId = el.dataset.covConv;
        el.addEventListener('click', (ev) => {
          if (ev.target.classList.contains('wa-coverage-dismiss')) return;
          if (convId) waOpenConversation(convId);
        });
      });
      errBannerEl.querySelectorAll('.wa-coverage-dismiss').forEach(btn => {
        btn.addEventListener('click', (ev) => {
          ev.stopPropagation();
          waDismissCoverageAlert(btn.dataset.covId);
        });
      });
    }

  }

  const banner = document.getElementById('wa-overview-pending');
  banner.innerHTML = pending.length ? waRenderPendingBanner(pending[0]) : '';
  if (pending.length) {
    banner.querySelector('.wa-pending-banner')?.addEventListener('click', () => {
      waOpenConversation(pending[0].id);
    });
  }

  // Quote requests banner + nav badge
  const pendingQuotes = (waQuoteRequests || []).filter(q => q.status === 'pending');
  const n = pendingQuotes.length;

  const quoteBanner = document.getElementById('wa-overview-quotes');
  if (quoteBanner) {
    if (n > 0) {
      quoteBanner.innerHTML = `<button class="wa-quote-banner" id="wa-btn-open-quotes">
        <span class="wa-quote-banner__icon">🔧</span>
        <div class="wa-quote-banner__body">
          <strong>${n} custom quote request${n > 1 ? 's' : ''} waiting</strong>
          <span>Tap to review and give advice — AI will reply to the customer</span>
        </div>
        <svg class="wa-quote-banner__chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
      </button>`;
      quoteBanner.querySelector('#wa-btn-open-quotes')?.addEventListener('click', () => {
        waShowView('quotes');
        waRenderQuotesView();
      });
    } else {
      quoteBanner.innerHTML = '';
    }
  }

  // Update Quotes tab badge
  const badge = document.getElementById('wa-nav-quotes-badge');
  if (badge) {
    if (n > 0) {
      badge.textContent = n;
      badge.style.display = 'flex';
    } else {
      badge.style.display = 'none';
    }
  }

  // Update Quotes metric card
  const quotesCard = document.getElementById('wa-metric-quotes');
  if (quotesCard) {
    document.getElementById('wa-metric-quotes-val').textContent = n;
    quotesCard.classList.toggle('has-unread', n > 0);
    quotesCard.onclick = () => { waShowView('quotes'); waRenderQuotesView(); };
  }

  // Update Bookings metric card — flashes GOLD per-user until clicked.
  const bookingsCard = document.getElementById('wa-metric-bookings');
  if (bookingsCard) {
    const bd = waBookingsData || {};
    const valEl = document.getElementById('wa-metric-bookings-val');
    if (valEl) valEl.textContent = bd.weekCount || 0;
    const todayEl = document.getElementById('wa-metric-bookings-today');
    const unseen = bd.unseenCount || 0;
    if (todayEl) {
      if (unseen > 0) {
        todayEl.textContent = `${bd.todayCount || 0} today`;
        todayEl.style.display = '';
      } else {
        todayEl.textContent = '';
        todayEl.style.display = 'none';
      }
    }
    bookingsCard.classList.toggle('wa-booking-alert', unseen > 0);
    bookingsCard.onclick = () => {
      waMarkBookingsSeen();
      waShowView('bookings'); waRenderBookingsView();
    };
  }
}

async function waMarkBookingsSeen() {
  if (waIsDemoMode) return;
  try {
    const res = await waApiFetch('/bookings/mark-seen', { method: 'POST' });
    if (res && res.lastSeen) {
      waBookingsData.lastSeen = res.lastSeen;
      waBookingsData.unseenCount = 0;
    }
    waRenderOverview();
  } catch (_) {}
}

function _waBookingDateLabel(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
  } catch (_) { return iso; }
}

function _waBookingMadeAgo(iso) {
  if (!iso) return '';
  const s = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (s < 60)     return 'just now';
  if (s < 3600)   return `${Math.floor(s/60)}m ago`;
  if (s < 86400)  return `${Math.floor(s/3600)}h ago`;
  return `${Math.floor(s/86400)}d ago`;
}

function waRenderBookingsView() {
  const e = _schedEsc;
  const bd = waBookingsData || {};
  const rows = bd.bookings || [];
  const sub = document.getElementById('wa-bookings-subtitle');
  if (sub) {
    sub.textContent = rows.length
      ? `${bd.weekCount || 0} booked this past week · ${bd.total || rows.length} total`
      : 'No bookings logged yet';
  }

  // Engineer / quote-attribution stats
  const statsEl = document.getElementById('wa-bookings-stats');
  if (statsEl) {
    const stats = bd.engineerStats || [];
    statsEl.innerHTML = stats.length
      ? `<div class="wa-booking-stats">
          <p class="wa-booking-stats__title">Who priced the jobs</p>
          <div class="wa-booking-stats__row">
            ${stats.map(s => `<span class="wa-booking-chip"><strong>${e(String(s.count))}</strong> ${e(s.name)}</span>`).join('')}
          </div>
         </div>`
      : '';
  }

  const listEl = document.getElementById('wa-bookings-list');
  if (!listEl) return;
  if (!rows.length) {
    listEl.innerHTML = '<p class="wa-empty-state">Bookings made by the AI will appear here.</p>';
    return;
  }
  const lastSeenDt = bd.lastSeen ? new Date(bd.lastSeen) : null;
  listEl.innerHTML = rows.map(r => {
    const services = (r.services || []).map(e).join(', ') || '—';
    const price = Array.isArray(r.price) ? r.price.map(e).join(', ') : e(String(r.price || ''));
    const isNew = lastSeenDt ? (new Date(r.createdAt) > lastSeenDt) : true;
    const aiTag = r.isAI ? '<span class="wa-booking-tag wa-booking-tag--ai">AI</span>' : '';
    return `<div class="wa-booking-item${isNew ? ' is-new' : ''}">
      <div class="wa-booking-item__head">
        <strong>${e(r.postcode || '')} · ${e(r.customerName || 'Customer')}</strong>
        ${aiTag}
      </div>
      <div class="wa-booking-item__meta">
        <span>📅 ${e(_waBookingDateLabel(r.jobDate))}${r.startTime ? ' · ' + e(r.startTime) : ''}</span>
        ${r.engineerName ? `<span>👷 ${e(r.engineerName)}</span>` : ''}
        ${price ? `<span>💷 ${price}</span>` : ''}
      </div>
      <div class="wa-booking-item__svc">${services}</div>
      <div class="wa-booking-item__foot">
        <span>Priced by <strong>${e(r.quotedBy || 'AI')}</strong></span>
        <span>Booked ${e(_waBookingMadeAgo(r.createdAt))}</span>
      </div>
    </div>`;
  }).join('');
}

function waRenderPendingBanner(convo) {
  const lm = convo.lastMessage;
  const secs = lm?.scheduledSendAt
    ? Math.max(0, Math.floor((new Date(lm.scheduledSendAt) - Date.now()) / 1000))
    : null;
  const timeLabel = secs !== null ? ` in <strong>${secs}s</strong>` : '';
  return `<div class="wa-pending-banner" data-cid="${convo.id}">
    <svg class="wa-pending-banner__icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
    <div class="wa-pending-banner__body">
      <strong>${convo.displayName}</strong>
      <span>AI sending${timeLabel} — tap to review</span>
    </div>
    <svg class="wa-pending-banner__chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
  </div>`;
}

// ── Render: Quotes view ───────────────────────────────────
let _waQuotesTickTimer = null;

function _waQuoteElapsedStr(createdAt) {
  const s = Math.floor((Date.now() - new Date(createdAt)) / 1000);
  if (s < 60)   return `${s}s`;
  if (s < 3600) return `${Math.floor(s/60)}m ${s % 60}s`;
  return `${Math.floor(s/3600)}h ${Math.floor((s % 3600)/60)}m`;
}

function _waTickQuoteTimers() {
  document.querySelectorAll('.wa-quote-elapsed[data-created]').forEach(el => {
    el.textContent = _waQuoteElapsedStr(el.dataset.created);
  });
}

function waRenderQuotesView() {
  const listEl = document.getElementById('wa-quotes-list');
  const sub    = document.getElementById('wa-quotes-subtitle');
  if (!listEl) return;

  // Stop any previous tick timer
  if (_waQuotesTickTimer) { clearInterval(_waQuotesTickTimer); _waQuotesTickTimer = null; }

  const all     = waQuoteRequests || [];
  const pending = all.filter(q => q.status === 'pending');
  const answered = all.filter(q => q.status === 'answered');

  if (sub) sub.textContent = pending.length
    ? `${pending.length} pending · ${answered.length} answered`
    : 'No pending quote requests';

  if (!all.length) {
    listEl.innerHTML = '<p class="wa-empty-state">No quote requests yet. When the AI can\'t quote from the price guide, a request will appear here.</p>';
    return;
  }

  const esc = s => (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  const ago = t => {
    const s = Math.floor((Date.now() - new Date(t)) / 1000);
    if (s < 60) return 'just now';
    if (s < 3600) return `${Math.floor(s/60)}m ago`;
    if (s < 86400) return `${Math.floor(s/3600)}h ago`;
    return `${Math.floor(s/86400)}d ago`;
  };

  listEl.innerHTML = all.map(qr => {
    const isAnswered = qr.status === 'answered';
    const imgs = (qr.images || []).map(img =>
      `<img src="data:${img.contentType};base64,${img.data}" alt="Customer photo">`
    ).join('');
    const elapsedHtml = !isAnswered
      ? `<span class="wa-quote-elapsed-wrap">
           <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
           <span class="wa-quote-elapsed" data-created="${esc(qr.createdAt)}">${_waQuoteElapsedStr(qr.createdAt)}</span>
         </span>`
      : '';

    return `<div class="wa-quote-item${isAnswered ? ' answered' : ''}" data-qid="${esc(qr.id)}">
      <div class="wa-quote-header">
        <div class="wa-avatar" style="width:36px;height:36px;font-size:13px">${esc(qr.displayName || '?').slice(0,2).toUpperCase()}</div>
        <div class="wa-quote-meta">
          <strong>${esc(qr.displayName || qr.conversationId)}</strong>
          <span>${ago(qr.createdAt)}${qr.postcode ? ` · 📍 ${esc(qr.postcode)}` : ''}${elapsedHtml}</span>
        </div>
        <span class="wa-quote-status-pill${isAnswered ? ' answered' : ''}">${isAnswered ? 'Answered' : 'Pending'}</span>
      </div>
      <p class="wa-quote-description">${esc(qr.description)}</p>
      ${imgs ? `<div class="wa-quote-images">${imgs}</div>` : ''}
      <div class="wa-quote-original">
        <p class="wa-quote-label">Customer said</p>
        <p>${esc(qr.customerMessage)}</p>
      </div>
      ${isAnswered
        ? `<div class="wa-quote-original" style="margin-top:8px">
            <p class="wa-quote-label">Your advice</p>
            <p>${esc(qr.humanAdvice)}</p>
           </div>`
        : `<div class="wa-quote-advice-section">
            <p class="wa-quote-label">Your advice <span style="font-weight:400;text-transform:none;letter-spacing:0;font-size:11px;color:#4a5a66">— talk as if briefing a colleague; the AI will write the reply</span></p>
            <textarea class="wa-quote-advice-input" placeholder="e.g. Quote £180 for the driveway clean, £120 for the patio — total £300. That includes jet wash and weed treatment." data-qid="${esc(qr.id)}"></textarea>
            <div class="wa-quote-actions">
              <button class="wa-primary-btn wa-quote-submit" data-qid="${esc(qr.id)}">Send to AI →</button>
              <button class="wa-quote-reply-now" data-cid="${esc(qr.conversationId)}" data-qid="${esc(qr.id)}" title="Skip the queue — go reply to the customer directly">Reply now</button>
              <button class="wa-quote-dismiss" data-qid="${esc(qr.id)}">Dismiss</button>
            </div>
           </div>`
      }
    </div>`;
  }).join('');

  // Start live tick for elapsed timers (pending cards only)
  if (pending.length) {
    _waQuotesTickTimer = setInterval(_waTickQuoteTimers, 1000);
  }

  // Wire up submit buttons
  listEl.querySelectorAll('.wa-quote-submit').forEach(btn => {
    btn.addEventListener('click', async () => {
      const qid     = btn.dataset.qid;
      const item    = listEl.querySelector(`.wa-quote-item[data-qid="${qid}"]`);
      const textarea = item?.querySelector('.wa-quote-advice-input');
      const advice  = textarea?.value.trim();
      if (!advice) { textarea?.focus(); return; }
      btn.disabled = true;
      btn.textContent = 'Sending…';
      try {
        await waApiFetch(`/quote-requests/${encodeURIComponent(qid)}/answer`, { method: 'POST', body: { advice } });
        await waLoadQuoteRequests();
        waRenderQuotesView();
        waRenderOverview();
        waUpdateHeaderQuoteAlert();
      } catch (err) {
        btn.disabled = false;
        btn.textContent = 'Send to AI →';
        alert('Error: ' + (err.message || 'Could not send advice'));
      }
    });
  });

  // Wire up "Reply now" buttons — jump straight to the conversation chat
  listEl.querySelectorAll('.wa-quote-reply-now').forEach(btn => {
    btn.addEventListener('click', () => {
      const cid = btn.dataset.cid;
      if (cid) waOpenConversation(cid);
    });
  });

  // Wire up dismiss buttons
  listEl.querySelectorAll('.wa-quote-dismiss').forEach(btn => {
    btn.addEventListener('click', async () => {
      const qid = btn.dataset.qid;
      try {
        await waApiFetch(`/quote-requests/${encodeURIComponent(qid)}`, { method: 'DELETE' });
        await waLoadQuoteRequests();
        waRenderQuotesView();
        waRenderOverview();
        waUpdateHeaderQuoteAlert();
      } catch (_) {}
    });
  });
}

// ── Render: Conversation list ─────────────────────────────
function waRenderConvoList() {
  const sub = document.getElementById('wa-convos-subtitle');
  if (sub) sub.textContent = `${waConversations.length} conversation${waConversations.length !== 1 ? 's' : ''}`;

  const pending = waPendingConvos(waConversations);
  const bannerEl = document.getElementById('wa-list-pending-banners');
  bannerEl.innerHTML = pending.map(c => waRenderPendingBanner(c)).join('');
  bannerEl.querySelectorAll('.wa-pending-banner').forEach((el, i) => {
    el.addEventListener('click', () => waOpenConversation(pending[i].id));
  });

  const listEl = document.getElementById('wa-conversation-list');
  // Search filter
  const q = (document.getElementById('wa-search-input')?.value || '').toLowerCase().trim();
  const filteredConvos = q ? waConversations.filter(c => {
    const name = (c.displayName || '').toLowerCase();
    const phone = (c.phoneNumber || c.id || '').toLowerCase();
    const msg = ((c.lastMessage?.text) || '').toLowerCase();
    return name.includes(q) || phone.includes(q) || msg.includes(q);
  }) : waConversations;

  if (!filteredConvos.length) {
    listEl.innerHTML = q
      ? `<p class="wa-empty-state">No results for "<strong>${q}</strong>".</p>`
      : '<p class="wa-empty-state">No conversations yet.</p>';
    return;
  }
  listEl.innerHTML = filteredConvos.map(c => {
    const lm = c.lastMessage || c.messages?.[c.messages.length - 1];
    const inits = waInitials(c.displayName);
    const dotCls = c.aiEnabled ? 'on' : 'off';
    const aiLabel = c.aiEnabled ? 'AI active' : 'Manual only';
    const hasUnread = (c.unreadCount || 0) > 0;
    const badge = hasUnread ? `<span class="wa-unread-badge">${c.unreadCount}</span>` : '';
    const excerpt = lm ? (lm.text.length > 50 ? lm.text.slice(0, 50) + '…' : lm.text) : 'No messages yet';
    const time = waFmtTime(lm);
    const hasPending = lm?.author === 'ai' && ['scheduled','drafting','sending'].includes(lm?.status);
    const pillSecs = hasPending && lm?.scheduledSendAt
      ? Math.max(0, Math.floor((new Date(lm.scheduledSendAt) - Date.now()) / 1000))
      : null;
    const pillLabel = pillSecs !== null ? `⏱ ${pillSecs}s` : '⏱ AI';
    const pendingPill = hasPending ? `<span class="wa-ai-pending-pill" id="wa-pill-${c.id}">${pillLabel}</span>` : '';
    const rowCls = hasUnread ? 'wa-conversation-row has-unread' : 'wa-conversation-row';
    // Show phone number as secondary line when it differs from the display name
    const phone = c.phoneNumber || c.id || '';
    const showPhone = phone && c.displayName && c.displayName !== phone;
    const phoneLine = showPhone ? `<span class="wa-conv-phone">${phone}</span>` : '';
    return `<div class="wa-conv-row-wrap" data-cid="${c.id}">
      <button class="${rowCls}" data-cid="${c.id}">
        <div class="wa-avatar">${inits}</div>
        <div class="wa-conversation-copy">
          <h3>${c.displayName}</h3>
          ${phoneLine}
          <p>${excerpt}</p>
          <div class="wa-conversation-meta">
            <span class="wa-status-dot ${dotCls}"></span>
            <span>${aiLabel}</span>
          </div>
        </div>
        <div class="wa-row-right">
          <span class="wa-row-time">${time}</span>
          ${pendingPill}${badge}
        </div>
        <svg class="wa-row-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
        <button class="wa-hover-delete-btn" data-cid="${c.id}" title="Delete conversation" tabindex="-1">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
        </button>
      </button>
      <button class="wa-swipe-delete-btn" data-cid="${c.id}" title="Delete conversation">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
        Delete
      </button>
    </div>`;
  }).join('');

  // ── Tap to open ──────────────────────────────────────────
  listEl.querySelectorAll('.wa-conversation-row').forEach(btn => {
    btn.addEventListener('click', () => {
      const wrap = btn.closest('.wa-conv-row-wrap');
      if (wrap && wrap.classList.contains('is-swiped')) {
        // First tap closes the swipe; doesn't open the conversation
        _closeAllSwipes();
        return;
      }
      waOpenConversation(btn.dataset.cid);
    });
  });

  // ── Delete action (tap on revealed red panel) ─────────────
  async function _doDeleteConvo(cid) {
    const convo = waConversations.find(c => c.id === cid);
    const name  = convo?.displayName || cid;
    if (!confirm(`Delete conversation with ${name}?\n\nThis cannot be undone.`)) {
      _closeAllSwipes();
      return;
    }
    if (!waIsDemoMode) {
      try {
        await fetch('/api/messages/conversations/' + encodeURIComponent(cid), { method: 'DELETE' });
      } catch (_) {}
    }
    waConversations = waConversations.filter(c => c.id !== cid);
    if (waSelectedId === cid) {
      waSelectedId = null;
      waSelectedConvo = null;
      waShowView('conversations');
    }
    waRenderConvoList();
  }

  listEl.querySelectorAll('.wa-swipe-delete-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      _doDeleteConvo(btn.dataset.cid);
    });
  });

  listEl.querySelectorAll('.wa-hover-delete-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      _doDeleteConvo(btn.dataset.cid);
    });
  });

  // ── Swipe-to-delete (touch devices) ──────────────────────
  const DELETE_W = 80;
  const THRESHOLD = 50;

  function _closeAllSwipes(except) {
    listEl.querySelectorAll('.wa-conv-row-wrap').forEach(w => {
      if (w === except) return;
      w.classList.remove('is-swiped');
      const r = w.querySelector('.wa-conversation-row');
      if (r) { r.style.transition = ''; r.style.transform = ''; }
    });
  }

  listEl.querySelectorAll('.wa-conv-row-wrap').forEach(wrap => {
    const row = wrap.querySelector('.wa-conversation-row');
    let startX = 0, startY = 0, tracking = false, isHoriz = false;

    wrap.addEventListener('touchstart', e => {
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
      tracking = true;
      isHoriz = false;
      row.style.transition = 'none';
    }, { passive: true });

    wrap.addEventListener('touchmove', e => {
      if (!tracking) return;
      const dx = e.touches[0].clientX - startX;
      const dy = e.touches[0].clientY - startY;
      if (!isHoriz && Math.abs(dy) > Math.abs(dx) + 5) { tracking = false; return; }
      if (Math.abs(dx) > 5) isHoriz = true;
      if (!isHoriz) return;
      const base = wrap.classList.contains('is-swiped') ? -DELETE_W : 0;
      const tx = Math.min(0, Math.max(-DELETE_W, base + dx));
      row.style.transform = `translateX(${tx}px)`;
    }, { passive: true });

    wrap.addEventListener('touchend', e => {
      if (!tracking || !isHoriz) return;
      tracking = false;
      const dx = e.changedTouches[0].clientX - startX;
      row.style.transition = '';
      if (wrap.classList.contains('is-swiped')) {
        if (dx > 20) { wrap.classList.remove('is-swiped'); row.style.transform = ''; }
        else { row.style.transform = `translateX(-${DELETE_W}px)`; }
      } else {
        if (dx < -THRESHOLD) {
          _closeAllSwipes(wrap);
          wrap.classList.add('is-swiped');
          row.style.transform = `translateX(-${DELETE_W}px)`;
        } else {
          row.style.transform = '';
        }
      }
    }, { passive: true });
  });

  // Close any open swipe when tapping outside the list
  if (listEl._swipeTapOutside) document.removeEventListener('touchstart', listEl._swipeTapOutside);
  listEl._swipeTapOutside = e => { if (!e.target.closest('#wa-conversation-list')) _closeAllSwipes(); };
  document.addEventListener('touchstart', listEl._swipeTapOutside, { passive: true });
}

// ── Open a conversation ───────────────────────────────────
async function waOpenConversation(id) {
  waSelectedId = id;
  waShowView('chat');
  const headerEl = document.getElementById('wa-chat-header');
  headerEl.innerHTML = '<span class="wa-empty-state" style="padding:14px">Loading…</span>';
  document.getElementById('wa-message-list').innerHTML = '';
  document.getElementById('wa-draft-btn-wrap').innerHTML = '';

  const convo = await waLoadConversation(id);
  waSelectedConvo = convo;
  if (!convo) {
    headerEl.innerHTML = '<p class="wa-error-state">Failed to load conversation.</p>';
    return;
  }
  waRenderChat(convo);
  if (convo.error) {
    const msgList = document.getElementById('wa-message-list');
    const notice = document.createElement('div');
    notice.className = 'wa-system-notice wa-error-notice';
    notice.textContent = '⚠ ' + convo.error;
    msgList.prepend(notice);
  }
}

// ── Render: Chat detail ───────────────────────────────────
function waRenderChat(convo) {
  if (!convo) return;
  const pending = waPendingMsg(convo);

  // Header
  const headerEl = document.getElementById('wa-chat-header');
  const trackCls = convo.aiEnabled ? 'wa-toggle-track on' : 'wa-toggle-track';
  headerEl.innerHTML = `
    <button class="wa-back-btn" id="wa-back-btn" style="flex-shrink:0">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
    </button>
    <div class="wa-chat-title" style="flex:1;min-width:0;overflow:hidden">
      <h2 style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${convo.displayName}</h2>
    </div>
    <button class="wa-quote-flash" id="wa-chat-quote-alert" title="Custom quote requests waiting — tap to review" style="${_waPendingQuoteCount() > 0 ? '' : 'display:none'}">
      <span class="wa-quote-flash__dot"></span>
      <span class="wa-quote-flash__count">${_waPendingQuoteCount()}</span>
    </button>
    <label class="wa-ai-switch" title="Toggle AI auto-reply" style="flex-shrink:0;gap:6px">
      <input type="checkbox" id="wa-ai-toggle" ${convo.aiEnabled ? 'checked' : ''}>
      <div class="${trackCls}" id="wa-toggle-track"><div class="wa-toggle-thumb"></div></div>
    </label>`;

  document.getElementById('wa-back-btn').addEventListener('click', () => {
    waShowView('conversations');
    waRenderConvoList();
  });
  document.getElementById('wa-chat-quote-alert')?.addEventListener('click', () => {
    waShowView('quotes');
    waRenderQuotesView();
  });
  document.getElementById('wa-ai-toggle').addEventListener('change', async (e) => {
    const enabled = e.target.checked;
    document.getElementById('wa-toggle-track').className = enabled ? 'wa-toggle-track on' : 'wa-toggle-track';
    if (!waIsDemoMode) {
      try {
        await waApiPost('/conversations/' + encodeURIComponent(waSelectedId) + '/toggle-ai', { enabled });
      } catch (_) {}
    }
    if (waSelectedConvo) waSelectedConvo.aiEnabled = enabled;
    waRenderDraftBtn(waSelectedConvo);
  });

  // Messages
  waRenderMessages(convo);

  // AI countdown bar
  waUpdateCountdownBar();

  // Draft button
  waRenderDraftBtn(convo);

  // Composer
  const composerInput = document.getElementById('wa-composer-input');
  const sendBtn = document.getElementById('wa-send-btn');
  composerInput.value = '';
  waUpdateSendBtn();
  composerInput.oninput = waUpdateSendBtn;
  document.getElementById('wa-composer').onsubmit = async (e) => {
    e.preventDefault();
    const text = composerInput.value.trim();
    if (!text || waBusy) return;
    await waDoSend(text);
  };
}

function waUpdateSendBtn() {
  const input = document.getElementById('wa-composer-input');
  const btn   = document.getElementById('wa-send-btn');
  if (btn && input) btn.disabled = !input.value.trim() || waBusy;
}

function waRenderDraftBtn(convo) {
  const wrap = document.getElementById('wa-draft-btn-wrap');
  if (!convo || convo.aiEnabled) { wrap.innerHTML = ''; return; }
  wrap.innerHTML = `<button class="wa-draft-btn" id="wa-gen-draft-btn">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
    Generate AI draft
  </button>`;
  document.getElementById('wa-gen-draft-btn').addEventListener('click', async () => {
    const btn = document.getElementById('wa-gen-draft-btn');
    if (waBusy) return;
    waBusy = true;
    btn.disabled = true;
    btn.textContent = 'Drafting…';
    try {
      let draft = '';
      if (!waIsDemoMode) {
        const res = await waApiPost('/conversations/' + encodeURIComponent(waSelectedId) + '/draft', {});
        draft = res.draft || '';
      } else {
        // Demo mode — call real AI with the last customer message
        const lastCustomerMsg = (waSelectedConvo?.messages || []).slice().reverse()
          .find(m => m.direction === 'inbound' || m.author === 'customer');
        const msgText = lastCustomerMsg?.text || 'I would like a quote for exterior cleaning.';
        try {
          const res = await fetch('/api/messages/ai-draft-direct', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: msgText }),
          });
          const data = await res.json();
          draft = data.draft || '';
        } catch (_) {
          draft = '(AI unavailable — check API key)';
        }
      }
      document.getElementById('wa-composer-input').value = draft;
      waUpdateSendBtn();
    } catch (_) {}
    waBusy = false;
    waRenderDraftBtn(waSelectedConvo);
  });
}

function waRenderMessages(convo) {
  const listEl = document.getElementById('wa-message-list');
  if (!convo.messages?.length) {
    listEl.innerHTML = '<p class="wa-empty-state">No messages yet.</p>';
    return;
  }
  const pending = waPendingMsg(convo);
  // Filter out cancelled messages so they don't show as duplicates
  const visibleMessages = (convo.messages || []).filter(m => m.status !== 'cancelled');
  listEl.innerHTML = '<div class="wa-day-divider">Today</div>' +
    visibleMessages.map(msg => {
      const inbound = msg.direction === 'inbound';
      const isPending = pending?.id === msg.id;
      const classes = ['wa-bubble', inbound ? 'inbound' : 'outbound', isPending ? 'pending' : '', msg.status === 'cancelled' ? 'cancelled' : ''].filter(Boolean).join(' ');
      const authorIcon = msg.author === 'ai'
        ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/><circle cx="12" cy="16" r="1" fill="currentColor"/></svg>`
        : `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>`;
      const authorLabel = msg.author === 'ai' ? 'AI' : msg.author === 'agent' ? 'Agent' : msg.author === 'system' ? 'System' : 'Customer';
      const showStatusLabel = !['sent','delivered','read','queued','sending'].includes(msg.status) && msg.status !== 'sent';
      const statusHtml = showStatusLabel
        ? `<div class="wa-bubble-status"><span>${waStatusLabel(msg)}</span></div>` : '';
      const tick = waDeliveryTick(msg);
      const editHtml = isPending
        ? `<div class="wa-pending-actions">
            <button class="wa-send-now-btn" data-msgid="${msg.id}" data-text="${(msg.text||'').replace(/"/g,'&quot;')}">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
              Send now
            </button>
            <button class="wa-edit-btn" data-msgid="${msg.id}">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              Edit
            </button>
            <button class="wa-cancel-draft-btn" data-msgid="${msg.id}">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              Cancel
            </button>
          </div>` : '';
      const atts = msg.attachments || [];
      const mediaHtml = atts.map(att => {
        const src = `data:${att.contentType};base64,${att.data}`;
        if ((att.contentType || '').startsWith('video/')) {
          return `<video class="wa-media-thumb" src="${src}" controls playsinline></video>`;
        }
        return `<img class="wa-media-thumb" src="${src}" alt="Photo" onclick="this.requestFullscreen&&this.requestFullscreen()" />`;
      }).join('');
      const bodyText = (msg.text === '[Media]' && atts.length) ? '' : `<p>${msg.text}</p>`;
      return `<div class="wa-message-row ${inbound ? 'left' : 'right'}">
        <div class="${classes}">
          ${bodyText}
          ${mediaHtml}
          <div class="wa-bubble-meta">${authorIcon}<span>${authorLabel}</span><span>${waFmtTime(msg)}</span>${tick}</div>
          ${statusHtml}
          ${editHtml}
        </div>
      </div>`;
    }).join('');

  // Bind "Send now" buttons
  listEl.querySelectorAll('.wa-send-now-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (waBusy) return;
      waBusy = true;
      btn.disabled = true;
      btn.textContent = 'Sending…';
      const msgText = waSelectedConvo?.messages?.find(m => m.id === btn.dataset.msgid)?.text || btn.dataset.text || '';
      try {
        if (!waIsDemoMode) {
          await waApiPost('/conversations/' + encodeURIComponent(waSelectedId) + '/send', { text: msgText, author: 'ai' });
        } else {
          if (waSelectedConvo) {
            waSelectedConvo.messages.forEach(m => { if (m.status === 'scheduled') m.status = 'cancelled'; });
            waSelectedConvo.messages.push({
              id: 'ai-sent-' + Date.now(), text: msgText, author: 'ai', direction: 'outbound',
              status: 'sent', sentAt: new Date().toISOString(), timestamp: new Date().toISOString(),
            });
          }
        }
        await waRefreshChat();
      } catch (_) {}
      waBusy = false;
    });
  });

  // Bind "Cancel draft" buttons
  listEl.querySelectorAll('.wa-cancel-draft-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (waBusy) return;
      waBusy = true;
      try {
        if (!waIsDemoMode) {
          await waApiPost('/conversations/' + encodeURIComponent(waSelectedId) + '/cancel-draft', {});
        } else {
          if (waSelectedConvo) waSelectedConvo.messages.forEach(m => { if (m.status === 'scheduled') m.status = 'cancelled'; });
        }
        await waRefreshChat();
      } catch (_) {}
      waBusy = false;
    });
  });

  // Bind "Edit" buttons
  listEl.querySelectorAll('.wa-edit-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (waBusy) return;
      const mid = btn.dataset.msgid;
      const msgText = waSelectedConvo?.messages?.find(m => m.id === mid)?.text || '';
      if (!waIsDemoMode) {
        try {
          waBusy = true;
          await waApiPost('/conversations/' + encodeURIComponent(waSelectedId) + '/messages/' + encodeURIComponent(mid) + '/cancel', {});
          waBusy = false;
        } catch (_) { waBusy = false; }
      } else {
        const m = waSelectedConvo?.messages?.find(x => x.id === mid);
        if (m) m.status = 'cancelled';
      }
      const composerInput = document.getElementById('wa-composer-input');
      if (composerInput) { composerInput.value = msgText; waUpdateSendBtn(); composerInput.focus(); }
      await waRefreshChat();
    });
  });

  // Scroll to bottom
  listEl.scrollTop = listEl.scrollHeight;
}

// ── Send message ─────────────────────────────────────────
async function waDoSend(text) {
  if (waBusy) return;
  waBusy = true;
  waUpdateSendBtn();
  const composerInput = document.getElementById('wa-composer-input');
  composerInput.value = '';
  try {
    if (!waIsDemoMode) {
      await waApiPost('/conversations/' + encodeURIComponent(waSelectedId) + '/send', { text });
    } else {
      // Demo: append message locally
      if (waSelectedConvo) {
        // Cancel any pending
        waSelectedConvo.messages.forEach(m => { if (m.status === 'scheduled') m.status = 'cancelled'; });
        waSelectedConvo.messages.push({
          id: 'agent-' + Date.now(), text, author: 'agent', direction: 'outbound',
          status: 'sent', sentAt: new Date().toISOString(), timestamp: new Date().toISOString(),
        });
      }
    }
    await waRefreshChat();
  } catch (err) {
    composerInput.value = text;
  }
  waBusy = false;
  waUpdateSendBtn();
}

// ── Refresh chat ─────────────────────────────────────────
async function waRefreshChat() {
  if (!waSelectedId) return;
  await waLoadConversations();
  // Keep quote requests fresh while in a chat so the header flashing light
  // reflects answers/dismissals made elsewhere (no SSE event for resolution).
  await waLoadQuoteRequests();
  waUpdateHeaderQuoteAlert();
  const convo = await waLoadConversation(waSelectedId);
  waSelectedConvo = convo;
  if (convo) waRenderMessages(convo);
}

// ── Countdown timer ──────────────────────────────────────
function waUpdateCountdownBar() {
  // Countdown bar removed — timer is displayed inside the message bubble.
  // This is kept as a no-op so existing call sites don't error.
}

function waStartCountdown() {
  waStopCountdown();
  waUpdateCountdownBar();
  waCountdownTimer = setInterval(async () => {
    if (!waSelectedConvo) return;
    const pending = waPendingMsg(waSelectedConvo);
    if (!pending) { waStopCountdown(); waUpdateCountdownBar(); return; }

    // Re-render status label in bubble
    const statusEls = document.querySelectorAll('#wa-message-list .wa-bubble.pending .wa-bubble-status span');
    statusEls.forEach(el => { el.textContent = waStatusLabel(pending); });

    // Tick the pending pill in the conversation list (if visible)
    if (waSelectedId) {
      const pill = document.getElementById('wa-pill-' + waSelectedId);
      if (pill && pending.scheduledSendAt) {
        const secs = Math.max(0, Math.floor((new Date(pending.scheduledSendAt).getTime() - Date.now()) / 1000));
        pill.textContent = '⏱ ' + secs + 's';
      }
    }

    // Auto-send when countdown hits 0
    if (pending.scheduledSendAt) {
      const secs = Math.floor((new Date(pending.scheduledSendAt).getTime() - Date.now()) / 1000);
      if (secs <= 0 && !waBusy) {
        waStopCountdown();
        if (!waIsDemoMode) {
          await waRefreshChat();
        } else {
          if (waSelectedConvo) {
            waSelectedConvo.messages.forEach(m => { if (m.status === 'scheduled') m.status = 'sent'; });
          }
          await waRefreshChat();
        }
      }
    }
  }, 1000);
}
function waStopCountdown() {
  if (waCountdownTimer) { clearInterval(waCountdownTimer); waCountdownTimer = null; }
}

// ── Polling ──────────────────────────────────────────────
function waStartPoll() {
  waStopPoll();
  waPollTimer = setInterval(async () => {
    if (waCurrentView !== 'chat' || !waSelectedId) return;
    await waRefreshChat();
  }, 6000);
}
function waStopPoll() {
  if (waPollTimer) { clearInterval(waPollTimer); waPollTimer = null; }
}

function waStartListPoll() {
  waStopListPoll();
  // Always poll every 5s — SSE is unreliable on multi-instance hosting
  waListPollTimer = setInterval(async () => {
    if (waIsDemoMode || waCurrentView === 'chat') return;
    await waLoadConversations();
    // Refresh bookings too so the gold new-booking alert still fires when SSE
    // drops on multi-instance hosting.
    await waLoadBookings();
    if (waCurrentView === 'overview')      waRenderOverview();
    if (waCurrentView === 'conversations') waRenderConvoList();
    if (waCurrentView === 'bookings')      waRenderBookingsView();
  }, 5000);
}
function waStopListPoll() {
  if (waListPollTimer) { clearInterval(waListPollTimer); waListPollTimer = null; }
}

// ── Activity toasts + header quote alert ─────────────────
function _waPendingQuoteCount() {
  return (waQuoteRequests || []).filter(q => q.status === 'pending').length;
}

// Keep the flashing quote light in the chat header in sync with pending quotes
// so an operator deep in a conversation always sees one waiting.
function waUpdateHeaderQuoteAlert() {
  const el = document.getElementById('wa-chat-quote-alert');
  if (!el) return;
  const n = _waPendingQuoteCount();
  if (n > 0) {
    el.style.display = '';
    const countEl = el.querySelector('.wa-quote-flash__count');
    if (countEl) countEl.textContent = n;
  } else {
    el.style.display = 'none';
  }
}

let _waToastTimer = null;
function waShowToast({ icon = '💬', text = '', kind = '', onClick = null, duration = 4500 } = {}) {
  const stack = document.getElementById('wa-toast-stack');
  if (!stack) return;
  stack.innerHTML = '';                       // minimal — one toast at a time
  if (_waToastTimer) { clearTimeout(_waToastTimer); _waToastTimer = null; }

  const toast = document.createElement('div');
  toast.className = 'wa-toast' + (kind === 'ai' ? ' wa-toast--ai' : '');
  const dots = kind === 'ai'
    ? '<span class="wa-toast__dots"><span></span><span></span><span></span></span>'
    : '';
  toast.innerHTML = `<span class="wa-toast__icon">${icon}</span>` +
                    `<span class="wa-toast__text">${text}</span>${dots}`;
  if (onClick) {
    toast.addEventListener('click', () => { _waDismissToast(toast); onClick(); });
  }
  stack.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('show'));
  _waToastTimer = setTimeout(() => _waDismissToast(toast), duration);
}
function _waDismissToast(toast) {
  if (!toast) return;
  toast.classList.remove('show');
  setTimeout(() => toast.remove(), 250);
}

// Surface a lightweight toast when a customer messages or the AI starts replying,
// unless the operator is already looking at that conversation.
function waNotifyActivity(conversationId) {
  if (waCurrentView === 'chat' && waSelectedId === conversationId) return;
  const convo = waConversations.find(c => c.id === conversationId);
  if (!convo) return;
  const lm = convo.lastMessage || convo.messages?.[convo.messages.length - 1];
  if (!lm) return;
  const name = convo.displayName || 'Customer';
  const isAiPending = lm.author === 'ai' && ['scheduled','drafting','sending'].includes(lm.status);
  if (lm.direction === 'inbound') {
    waShowToast({ icon: '💬', text: `New message from ${name}`,
      onClick: () => waOpenConversation(conversationId) });
  } else if (isAiPending) {
    waShowToast({ icon: '🤖', kind: 'ai', text: `AI is replying to ${name}`,
      onClick: () => waOpenConversation(conversationId) });
  }
}

function waConnectSSE() {
  if (waSSE && waSSE.readyState !== 2) return; // already open or connecting
  waSSE = new EventSource('/api/messages/stream');
  waSSE.addEventListener('new_message', async (e) => {
    if (waIsDemoMode) return;
    const data = JSON.parse(e.data);
    await waLoadConversations();
    // Always update overview metrics so gold pulse stays in sync regardless of current view
    waRenderOverview();
    if (waCurrentView === 'conversations') waRenderConvoList();
    if (waCurrentView === 'chat' && waSelectedId === data.conversationId) {
      await waRefreshChat();
    }
    waNotifyActivity(data.conversationId);
  });
  waSSE.addEventListener('new_quote_request', async () => {
    if (waIsDemoMode) return;
    await waLoadQuoteRequests();
    if (waCurrentView === 'overview') waRenderOverview();
    if (waCurrentView === 'quotes')   waRenderQuotesView();
    waUpdateHeaderQuoteAlert();
    if (_waPendingQuoteCount() > 0 && waCurrentView !== 'quotes') {
      waShowToast({ icon: '🔧', text: 'New custom quote request — tap to review',
        onClick: () => { waShowView('quotes'); waRenderQuotesView(); } });
    }
  });
  waSSE.addEventListener('new_booking', async () => {
    if (waIsDemoMode) return;
    await waLoadBookings();
    if (waCurrentView === 'overview') waRenderOverview();
    if (waCurrentView === 'bookings') waRenderBookingsView();
    if ((waBookingsData.unseenCount || 0) > 0 && waCurrentView !== 'bookings') {
      waShowToast({ icon: '🟡', text: 'New booking added — tap to view',
        onClick: () => { waMarkBookingsSeen(); waShowView('bookings'); waRenderBookingsView(); } });
    }
  });
  waSSE.addEventListener('new_coverage_alert', async (e) => {
    if (waIsDemoMode) return;
    await waLoadCoverageAlerts();
    waRenderOverview();
    let disp = 'a customer';
    try { disp = (JSON.parse(e.data).displayName) || disp; } catch (_) {}
    if (waCurrentView !== 'overview') {
      waShowToast({ icon: '⚠️', text: `Coverage gap — AI paused for ${disp}`,
        onClick: () => { waShowView('overview'); waRenderOverview(); } });
    }
  });
  waSSE.addEventListener('new_attention_alert', async (e) => {
    if (waIsDemoMode) return;
    await waLoadAttentionAlerts();
    waRenderOverview();
    let disp = 'a customer';
    try { disp = (JSON.parse(e.data).displayName) || disp; } catch (_) {}
    if (waCurrentView !== 'overview') {
      waShowToast({ icon: '🔔', text: `Needs attention — AI paused for ${disp}`,
        onClick: () => { waShowView('overview'); waRenderOverview(); } });
    }
  });
  waSSE.onerror = () => {
    waSSE?.close();
    waSSE = null;
    // Reconnect after 5s
    setTimeout(() => { if (!waIsDemoMode) waConnectSSE(); }, 5000);
  };
}
function waDisconnectSSE() {
  if (waSSE) { waSSE.close(); waSSE = null; }
}

// ── Settings screen ──────────────────────────────────────
async function waRenderSettings() {
  const wrap = document.getElementById('wa-settings-content');
  wrap.innerHTML = '<p class="wa-empty-state">Loading…</p>';
  let settings = null;
  try {
    if (!waIsDemoMode) settings = await waApiGet('/settings');
  } catch (_) {}
  if (!settings) {
    settings = {
      twilio: { accountSid: 'AC-demo', messagingServiceSid: 'MG-demo', whatsappFrom: 'whatsapp:+447700900000', sandboxMode: true, authTokenConfigured: true },
      openAi: { organizationId: '', baseUrl: '', apiKeyConfigured: true },
    };
  }

  // Detect push support & current permission
  const isPwa     = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  const hasPush   = ('serviceWorker' in navigator) && ('PushManager' in window);
  const perm      = hasPush ? Notification.permission : 'unavailable';
  const permLabel = perm === 'granted' ? '🔔 On' : perm === 'denied' ? '🚫 Blocked' : perm === 'unavailable' ? '— unavailable' : '🔕 Off';
  const permColor = perm === 'granted' ? '#25D366' : perm === 'denied' ? '#ef4444' : '#8696a0';

  const iosHint = !hasPush ? `
    <div class="wa-notif-ios-tip">
      <strong>📱 iPhone — one-time setup needed</strong><br>
      Push notifications require the app to be saved to your Home Screen. In Safari tap
      <strong>Share → Add to Home Screen</strong>, then open PowWash from that icon and come back here.
      ${!isPwa ? '<br><em style="color:#ffc857">You appear to be in Safari — please use your Home Screen icon.</em>' : ''}
    </div>` : '';

  const enableRow = !hasPush ? '' : perm === 'denied' ? '' : perm === 'granted' ? `
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:6px">
      <button class="wa-notif-enable-btn" id="wa-notif-enable-btn" style="background:#1a6b3a">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
        Re-register subscription
      </button>
      <button class="wa-primary-btn" id="wa-notif-test-btn" style="background:#2563eb">
        Send test notification
      </button>
    </div>` : `
    <button class="wa-notif-enable-btn" id="wa-notif-enable-btn">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
      Enable notifications
    </button>`;

  const blockedNote = (hasPush && perm === 'denied') ? `
    <p class="wa-notif-blocked-msg">Notifications blocked. Go to iPhone Settings → Notifications → PowWash to re-enable.</p>` : '';

  // Load saved prefs
  let prefs = {};
  try {
    const r = await fetch('/api/notifications/prefs');
    if (r.ok) prefs = await r.json();
  } catch (_) {}
  const chk = t => prefs[t]?.enabled !== false ? 'checked' : '';

  wrap.innerHTML = `
    <!-- ── Notifications ── -->
    <div class="wa-settings-panel">
      <div class="wa-panel-header">
        <div class="wa-panel-header-left">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
          <h3>Notifications</h3>
        </div>
        <span class="wa-notif-status-pill" style="color:${permColor};border-color:${permColor};">${permLabel}</span>
      </div>
      ${iosHint}${enableRow}${blockedNote}
      <div id="wa-notif-save-msg" style="margin:6px 0 2px;font-size:13px;min-height:18px;"></div>
      <div class="wa-notif-toggle-list" style="margin-top:8px">
        <label class="wa-notif-row">
          <span class="wa-notif-row-info"><strong>New customer message</strong><small>When someone WhatsApps you</small></span>
          <input type="checkbox" class="wa-notif-chk" data-type="customer_message" ${chk('customer_message')}>
        </label>
        <label class="wa-notif-row">
          <span class="wa-notif-row-info"><strong>Human input needed</strong><small>When AI can't handle a reply</small></span>
          <input type="checkbox" class="wa-notif-chk" data-type="human_input" ${chk('human_input')}>
        </label>
        <label class="wa-notif-row">
          <span class="wa-notif-row-info"><strong>Booking confirmed</strong><small>When a job is added to calendar</small></span>
          <input type="checkbox" class="wa-notif-chk" data-type="booking_complete" ${chk('booking_complete')}>
        </label>
      </div>
      <button class="wa-primary-btn" id="wa-notif-save-btn" style="margin-top:10px">Save notification preferences</button>
    </div>

    <!-- ── Twilio ── -->
    <div class="wa-settings-panel" style="margin-top:12px">
      <div class="wa-panel-header">
        <div class="wa-panel-header-left">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
          <h3>Twilio WhatsApp</h3>
        </div>
      </div>
      <div class="wa-settings-grid">
        <div class="wa-field"><span>Account SID</span><input type="text" value="${settings.twilio?.accountSid || ''}" placeholder="ACxxxx" /></div>
        <div class="wa-field"><span>Auth Token</span><input type="password" value="" placeholder="${settings.twilio?.authTokenConfigured ? 'Configured' : 'Paste token'}" /></div>
        <div class="wa-field"><span>Messaging Service SID</span><input type="text" value="${settings.twilio?.messagingServiceSid || ''}" placeholder="MGxxxx" /></div>
        <div class="wa-field"><span>WhatsApp sender</span><input type="text" value="${settings.twilio?.whatsappFrom || ''}" placeholder="whatsapp:+1415…" /></div>
        <label class="wa-check-row"><input type="checkbox" ${settings.twilio?.sandboxMode ? 'checked' : ''}> Sandbox / test mode</label>
      </div>
    </div>

    <!-- ── OpenAI ── -->
    <div class="wa-settings-panel" style="margin-top:12px">
      <div class="wa-panel-header">
        <div class="wa-panel-header-left">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
          <h3>OpenAI</h3>
        </div>
      </div>
      <div class="wa-settings-grid">
        <div class="wa-field"><span>API Key</span><input type="password" value="" placeholder="${settings.openAi?.apiKeyConfigured ? 'Configured' : 'Paste key'}" /></div>
        <div class="wa-field"><span>Organization ID</span><input type="text" value="${settings.openAi?.organizationId || ''}" placeholder="org-…" /></div>
        <div class="wa-field" style="grid-column:span 2"><span>Base URL</span><input type="text" value="${settings.openAi?.baseUrl || ''}" placeholder="https://api.openai.com/v1" /></div>
      </div>
    </div>

    <div id="wa-settings-notice"></div>
    <button class="wa-primary-btn" id="wa-settings-save" style="margin-top:4px">Save integration settings</button>`;

  // Helper: show step status in the save-msg div AND in the button label
  function _notifStep(msg, color) {
    const el = document.getElementById('wa-notif-save-msg');
    if (el) {
      el.innerHTML = `<span style="color:${color||'#8696a0'};font-size:13px;font-weight:500">${msg}</span>`;
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  // Core subscribe flow (shared by Enable + Re-register buttons)
  async function _doSubscribe(skipPermRequest) {
    const btn = document.getElementById('wa-notif-enable-btn');
    const origLabel = btn ? btn.innerHTML : '';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span style="opacity:.7">⏳ Working…</span>';
    }
    try {
      // Step 1 — permission
      if (!skipPermRequest) {
        _notifStep('Asking for permission — look for a system prompt…', '#8696a0');
        const result = await Notification.requestPermission();
        if (result === 'denied') {
          _notifStep('❌ Blocked — go to iPhone Settings → Notifications → PowWash to re-enable.', '#ef4444');
          if (btn) { btn.disabled = false; btn.innerHTML = origLabel; }
          return;
        }
        if (result !== 'granted') {
          _notifStep('❌ Permission not granted. Tap the button again and accept the prompt.', '#ef4444');
          if (btn) { btn.disabled = false; btn.innerHTML = origLabel; }
          return;
        }
        _notifStep('✔ Permission granted — connecting…', '#25D366');
      }
      // Step 2 — service worker
      _notifStep('Connecting service worker…', '#8696a0');
      const swReady = await Promise.race([
        navigator.serviceWorker.ready,
        new Promise((_, rej) => setTimeout(() => rej(new Error('Service worker did not activate within 15s — close all PowWash tabs and try again')), 15000)),
      ]);
      if (!swReady.pushManager) throw new Error('PushManager not available — open PowWash from your Home Screen icon (not Safari)');
      // Step 3 — subscribe with APNs / FCM
      _notifStep('Registering with push service…', '#8696a0');
      const vapidRes = await fetch('/api/push/vapid-public-key');
      if (!vapidRes.ok) throw new Error('Could not fetch VAPID key (' + vapidRes.status + ')');
      const { publicKey } = await vapidRes.json();
      if (!publicKey) throw new Error('Server returned empty VAPID key — contact support');
      // Force a fresh subscription (unsubscribe first if exists)
      let existing = await swReady.pushManager.getSubscription();
      if (existing) await existing.unsubscribe();
      const sub = await swReady.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });
      // Step 4 — save to server
      _notifStep('Saving subscription to server…', '#8696a0');
      const subPayload = sub.toJSON();
      const subRes = await fetch('/api/push/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(subPayload),
      });
      if (!subRes.ok) {
        const errBody = await subRes.json().catch(() => ({}));
        throw new Error('Server error (' + subRes.status + '): ' + (errBody.error || 'unknown'));
      }
      _notifStep('✅ Notifications are active! Use "Send test" to confirm.', '#25D366');
      await waRenderSettings();
    } catch (e) {
      console.error('[push] subscribe failed:', e);
      _notifStep('❌ ' + (e.message || String(e)), '#ef4444');
      if (btn) { btn.disabled = false; btn.innerHTML = origLabel; }
    }
  }

  document.getElementById('wa-notif-enable-btn')?.addEventListener('click', () => {
    const isReregister = Notification.permission === 'granted';
    _doSubscribe(isReregister);
  });

  // Test push button
  document.getElementById('wa-notif-test-btn')?.addEventListener('click', async () => {
    const btn = document.getElementById('wa-notif-test-btn');
    if (!btn || btn.disabled) return;

    // Countdown so you can lock the screen before it fires
    const DELAY = 20;
    btn.disabled = true;
    _notifStep('🔒 Lock your screen — sending in ' + DELAY + 's…', '#8696a0');
    let remaining = DELAY;
    await new Promise(resolve => {
      const iv = setInterval(() => {
        remaining--;
        if (remaining <= 0) { clearInterval(iv); resolve(); return; }
        btn.textContent = 'Sending in ' + remaining + 's…';
        _notifStep('🔒 Lock your screen — sending in ' + remaining + 's…', '#8696a0');
      }, 1000);
    });

    btn.textContent = 'Sending…';
    _notifStep('📤 Sending notification…', '#8696a0');
    try {
      const r = await fetch('/api/push/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ type: 'customer_message' }) });
      const rb = await r.json().catch(() => ({}));
      if (r.ok) {
        _notifStep('✅ Test sent — it should appear on your lock screen!', '#25D366');
      } else {
        _notifStep('❌ ' + (rb.error || 'Server error ' + r.status), '#ef4444');
      }
    } catch (e) {
      _notifStep('❌ ' + e.message, '#ef4444');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Send test notification'; }
    }
  });

  // Save notification prefs
  document.getElementById('wa-notif-save-btn')?.addEventListener('click', async () => {
    const newPrefs = {};
    wrap.querySelectorAll('.wa-notif-chk').forEach(c => {
      newPrefs[c.dataset.type] = { enabled: c.checked, tone: prefs[c.dataset.type]?.tone || c.dataset.type };
    });
    try {
      await fetch('/api/notifications/prefs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(newPrefs) });
      prefs = newPrefs;
    } catch (_) {}
    const msg = document.getElementById('wa-notif-save-msg');
    if (msg) { msg.innerHTML = '<span style="color:#25D366">✓ Saved</span>'; setTimeout(() => { msg.innerHTML = ''; }, 2500); }
  });

  // Save integration settings (no-op UI feedback)
  document.getElementById('wa-settings-save').addEventListener('click', () => {
    const notice = document.getElementById('wa-settings-notice');
    notice.innerHTML = `<div class="wa-notice" style="margin-top:8px">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
      Settings saved.
    </div>`;
    setTimeout(() => { if (notice) notice.innerHTML = ''; }, 3000);
  });
}

// ── Initialise ───────────────────────────────────────────
let waInitDone = false;
async function waInit() {
  if (waInitDone) return;
  waInitDone = true;

  // Wire up bottom nav
  document.querySelectorAll('.wa-nav-item').forEach(btn => {
    btn.addEventListener('click', () => {
      const view = btn.dataset.waview;
      waShowView(view);
      if (view === 'overview')      { waLoadCoverageAlerts().then(waRenderOverview); waLoadAttentionAlerts().then(waRenderOverview); waRenderOverview(); }
      if (view === 'conversations') waRenderConvoList();
      if (view === 'settings')      waRenderSettings();
      if (view === 'quotes') {
        waLoadQuoteRequests().then(() => waRenderQuotesView());
      }
    });
  });

  // Wire overview buttons
  document.getElementById('wa-btn-open-chats')?.addEventListener('click', () => {
    waShowView('conversations'); waRenderConvoList();
  });
  document.getElementById('wa-btn-open-settings')?.addEventListener('click', () => {
    waShowView('settings'); waRenderSettings();
  });
  document.getElementById('wa-metric-convos')?.addEventListener('click', () => {
    waShowView('conversations'); waRenderConvoList();
  });
  document.getElementById('wa-metric-status')?.addEventListener('click', () => {
    waShowView('settings'); waRenderSettings();
  });

  // Conversations list back button → overview
  document.getElementById('wa-convos-back-btn')?.addEventListener('click', () => {
    waShowView('overview'); waRenderOverview();
  });

  // New conversation button
  document.getElementById('wa-new-convo-btn')?.addEventListener('click', waOpenOutboundModal);

  // Search bar — re-render list on input
  document.getElementById('wa-search-input')?.addEventListener('input', () => waRenderConvoList());

  // Refresh button on conversation list
  document.getElementById('wa-refresh-btn')?.addEventListener('click', async () => {
    document.getElementById('wa-conversation-list').innerHTML = '<p class="wa-empty-state">Refreshing…</p>';
    await waLoadConversations();
    waRenderConvoList();
  });

  // Quotes back button → overview
  document.getElementById('wa-quotes-back-btn')?.addEventListener('click', () => {
    waShowView('overview'); waRenderOverview();
  });

  // Bookings back button → overview
  document.getElementById('wa-bookings-back-btn')?.addEventListener('click', () => {
    waShowView('overview'); waRenderOverview();
  });

  // Load data then render overview
  await waLoadConversations();
  await waLoadQuoteRequests();
  await waLoadBookings();
  await waLoadCoverageAlerts();
  await waLoadAttentionAlerts();
  waRenderOverview();
  waShowView('overview');
  // Check system status in background — updates the error banners
  waCheckSystemStatus();
}

// Trigger init when Messages tab is clicked — registers handlers once, then connects SSE
document.querySelector('[data-tab="messages"]')?.addEventListener('click', async () => {
  await waInit(); // registers handlers once (guarded by waInitDone)
  waConnectSSE(); // open SSE connection for instant push
  waStartListPoll(); // 12s fallback if SSE drops
  if (!waIsDemoMode && waCurrentView !== 'chat') {
    await waLoadConversations();
    if (waCurrentView === 'overview')      waRenderOverview();
    if (waCurrentView === 'conversations') waRenderConvoList();
  }
});

// ═══════════════════════════════════════════════════════
// OUTBOUND TEMPLATE PICKER
// ═══════════════════════════════════════════════════════

async function waOpenOutboundModal() {
  const overlay = document.getElementById('wa-outbound-overlay');
  if (!overlay) return;
  // Reset state
  document.getElementById('wa-outbound-phone').value = '';
  document.getElementById('wa-outbound-preview').value = '';
  document.getElementById('wa-outbound-error').style.display = 'none';
  document.getElementById('wa-outbound-send').disabled = false;
  document.getElementById('wa-outbound-send').textContent = 'Send';
  // Default channel to whatsapp
  const radios = document.querySelectorAll('input[name="wa-outbound-channel"]');
  radios.forEach(r => { r.checked = r.value === 'whatsapp'; });

  overlay.classList.remove('stg-hidden');

  // Load templates into select
  const sel       = document.getElementById('wa-outbound-template');
  const varsDiv   = document.getElementById('wa-outbound-vars');
  const previewEl = document.getElementById('wa-outbound-preview');
  const nosidHint = document.getElementById('wa-outbound-nosid-hint');
  sel.innerHTML = '<option value="">— choose a template —</option>';
  let _outboundTemplates = [];
  try {
    const data = await fetch('/api/settings/templates').then(r => r.json());
    _outboundTemplates = data.templates || [];
    _outboundTemplates.forEach((t, i) => {
      const opt = document.createElement('option');
      opt.value = String(i);
      opt.textContent = t.name || (t.body || '').slice(0, 60) + '…';
      sel.appendChild(opt);
    });
    sel._outboundTemplates = _outboundTemplates;
  } catch (_) {
    sel.innerHTML += '<option disabled>Could not load templates</option>';
  }

  function waRebuildPreview(tmpl, inputs) {
    let body = tmpl.body || '';
    const vm = tmpl.varMap || {};
    Object.entries(vm).forEach(([pos, key]) => {
      const val = inputs[key] || '';
      body = body.replace(new RegExp('\\{\\{' + pos + '\\}\\}', 'g'), val || `{{${key}}}`);
    });
    previewEl.value = body;
  }

  function waShowVarFields(tmpl) {
    varsDiv.innerHTML = '';
    varsDiv.style.display = 'none';
    nosidHint.style.display = 'none';
    if (!tmpl) { previewEl.value = ''; return; }
    if (!tmpl.sid) nosidHint.style.display = 'block';
    const vm = tmpl.varMap || {};
    const keys = Object.values(vm);
    if (!keys.length) { previewEl.value = tmpl.body || ''; return; }
    varsDiv.style.display = 'flex';
    const inputs = {};
    keys.forEach(key => {
      const label = document.createElement('label');
      label.className = 'stg-field-label';
      label.style.display = 'block';
      label.textContent = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      const inp = document.createElement('input');
      inp.className = 'stg-input';
      inp.type = 'text';
      inp.placeholder = key.replace(/_/g, ' ');
      inp.style.cssText = 'width:100%;box-sizing:border-box;margin-top:4px';
      inp.oninput = () => { inputs[key] = inp.value; waRebuildPreview(tmpl, inputs); };
      inputs[key] = '';
      label.appendChild(inp);
      varsDiv.appendChild(label);
    });
    waRebuildPreview(tmpl, inputs);
  }

  // Wire template select → variable fields + preview
  sel.onchange = () => {
    const tmpl = _outboundTemplates[parseInt(sel.value)];
    waShowVarFields(tmpl || null);
  };

  // Wire close buttons
  document.getElementById('wa-outbound-close').onclick = waCloseOutboundModal;
  document.getElementById('wa-outbound-cancel').onclick = waCloseOutboundModal;
  overlay.onclick = (e) => { if (e.target === overlay) waCloseOutboundModal(); };

  // Wire send
  document.getElementById('wa-outbound-send').onclick = waSendOutbound;
}

function waCloseOutboundModal() {
  document.getElementById('wa-outbound-overlay')?.classList.add('stg-hidden');
}

async function waSendOutbound() {
  const phone   = (document.getElementById('wa-outbound-phone').value || '').trim();
  const message = (document.getElementById('wa-outbound-preview').value || '').trim();
  const channel = document.querySelector('input[name="wa-outbound-channel"]:checked')?.value || 'whatsapp';
  const errEl   = document.getElementById('wa-outbound-error');
  const sendBtn = document.getElementById('wa-outbound-send');

  errEl.style.display = 'none';

  if (!phone) { errEl.textContent = 'Enter a phone number.'; errEl.style.display = 'block'; return; }
  if (!phone.startsWith('+')) { errEl.textContent = 'Use E.164 format, e.g. +447700900000'; errEl.style.display = 'block'; return; }
  if (!message) { errEl.textContent = 'Choose a template or type a message.'; errEl.style.display = 'block'; return; }

  // Collect content_sid + content_variables from selected template
  const sel = document.getElementById('wa-outbound-template');
  const _tmplData = sel._outboundTemplates || window._waOutboundTemplates || [];
  const tmpl = _tmplData[parseInt(sel.value)];
  let content_sid = tmpl?.sid || null;
  let content_variables = null;
  if (content_sid && tmpl?.varMap) {
    content_variables = {};
    const vm = tmpl.varMap;
    const varsDiv = document.getElementById('wa-outbound-vars');
    const inputs = varsDiv ? [...varsDiv.querySelectorAll('input')] : [];
    Object.entries(vm).forEach(([pos, key], i) => {
      content_variables[pos] = (inputs[i]?.value || '').trim();
    });
  }

  sendBtn.disabled = true;
  sendBtn.textContent = 'Sending…';

  try {
    const payload = { phone, message, channel };
    if (content_sid) { payload.content_sid = content_sid; payload.content_variables = content_variables; }
    const res = await fetch('/api/messages/outbound', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.error) {
      errEl.textContent = data.error;
      errEl.style.display = 'block';
      sendBtn.disabled = false;
      sendBtn.textContent = 'Send';
      return;
    }
    // Success — close modal, refresh list, open the conversation
    waCloseOutboundModal();
    await waLoadConversations();
    waRenderConvoList();
    if (data.conversationId) {
      waOpenConversation(data.conversationId);
    } else {
      waShowView('conversations');
    }
  } catch (err) {
    errEl.textContent = 'Network error — please try again.';
    errEl.style.display = 'block';
    sendBtn.disabled = false;
    sendBtn.textContent = 'Send';
  }
}

// ═══════════════════════════════════════════════════════
// CUSTOMER SIMULATOR — split-panel preview
// ═══════════════════════════════════════════════════════

let simHistory       = [];      // [{role:"customer"|"ai", text}]
let simBusy          = false;
let simCountdownTimer = null;
const SIM_COUNTDOWN  = 120;     // seconds before auto-send (2 minutes)

function simEl(id) { return document.getElementById(id); }
function simEsc(t) { return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// ── Customer side ──────────────────────────────────────

function simScrollBottom() {
  const el = simEl('wa-sim-messages');
  if (el) el.scrollTop = el.scrollHeight;
}

function simUpdateSend() {
  const btn = simEl('wa-sim-send');
  const inp = simEl('wa-sim-input');
  if (btn && inp) btn.disabled = simBusy || !inp.value.trim();
}

function simAddBubble(role, text) {
  const msgs = simEl('wa-sim-messages');
  if (!msgs) return;
  msgs.querySelector('.wa-sim-welcome')?.remove();
  const div = document.createElement('div');
  div.className = `wa-sim-row ${role}`;
  div.innerHTML = `<div class="wa-sim-bubble ${role}"><p>${simEsc(text).replace(/\n/g,'<br>')}</p></div>`;
  msgs.appendChild(div);
  simScrollBottom();
}

function simShowCustomerTyping() {
  const msgs = simEl('wa-sim-messages');
  if (!msgs || simEl('wa-sim-ctyping')) return;
  const el = document.createElement('div');
  el.className = 'wa-sim-row ai'; el.id = 'wa-sim-ctyping';
  el.innerHTML = `<div class="wa-sim-typing"><span></span><span></span><span></span></div>`;
  msgs.appendChild(el);
  simScrollBottom();
}
function simHideCustomerTyping() { simEl('wa-sim-ctyping')?.remove(); }

function simShowError(msg) {
  const msgs = simEl('wa-sim-messages');
  if (!msgs) return;
  const el = document.createElement('div');
  el.className = 'wa-sim-error'; el.textContent = msg;
  msgs.appendChild(el);
  simScrollBottom();
}

// ── App / operator side ────────────────────────────────

function simScrollAppBottom() {
  const el = simEl('wa-sim-app-thread');
  if (el) el.scrollTop = el.scrollHeight;
}

function simSetAppStatus(text) {
  const el = simEl('wa-sim-app-status');
  if (el) el.textContent = text;
}

function simAddAppMsg(role, text) {
  const thread = simEl('wa-sim-app-thread');
  if (!thread) return;
  simEl('wa-sim-app-empty')?.remove();
  const label = role === 'customer' ? '📥 Incoming from customer' : '✅ Sent by AI';
  const div = document.createElement('div');
  div.className = 'wa-sim-app-row';
  div.innerHTML = `<div class="wa-sim-app-row-label">${label}</div>
    <div class="wa-sim-app-bubble${role==='ai'?' sent':''}">${simEsc(text).replace(/\n/g,'<br>')}</div>`;
  thread.appendChild(div);
  simScrollAppBottom();
}

function simShowGenerating(on) {
  simEl('wa-sim-generating')?.classList.toggle('active', on);
}

// ── Countdown / pending card ───────────────────────────

function simCancelCountdown() {
  if (simCountdownTimer) { clearInterval(simCountdownTimer); simCountdownTimer = null; }
}

function simHidePending() {
  simEl('wa-sim-pending')?.classList.remove('active');
  simCancelCountdown();
}

function simShowPending(draftText) {
  const card = simEl('wa-sim-pending');
  const ta   = simEl('wa-sim-draft-text');
  const cd   = simEl('wa-sim-countdown');
  const prog = simEl('wa-sim-progress');
  if (!card || !ta) return;
  ta.value = draftText;
  if (cd)   cd.textContent = SIM_COUNTDOWN;
  if (prog) prog.style.width = '100%';
  card.classList.add('active');

  simCancelCountdown();
  let secs = SIM_COUNTDOWN;
  simCountdownTimer = setInterval(() => {
    secs--;
    if (cd)   cd.textContent = secs;
    if (prog) prog.style.width = ((secs / SIM_COUNTDOWN) * 100) + '%';
    if (secs <= 0) {
      simCancelCountdown();
      const final = simEl('wa-sim-draft-text')?.value?.trim() || draftText;
      simCommitReply(final);
    }
  }, 1000);
}

function simCommitReply(text) {
  simHidePending();
  simHideCustomerTyping();
  simAddBubble('ai', text);
  simAddAppMsg('ai', text);
  simHistory.push({ role: 'ai', text });
  simSetAppStatus('Reply sent — waiting for next message');
  simBusy = false;
  simUpdateSend();
  simEl('wa-sim-input')?.focus();
}

function simShowBookingBadge(booking, errorMsg) {
  const msgs = simEl('wa-sim-messages');
  if (!msgs) return;
  const div = document.createElement('div');
  div.className = 'wa-sim-booking-badge' + (errorMsg ? ' error' : '');
  if (errorMsg) {
    div.innerHTML = `<span>⚠️ Booking attempt failed — ${simEsc(errorMsg)}</span>`;
  } else {
    const d = booking?.details || {};
    const link = booking?.htmlLink
      ? `<a href="${booking.htmlLink}" target="_blank" rel="noopener">View in Calendar →</a>`
      : '';
    div.innerHTML = `<span>📅 Booking created — ${simEsc(d.date || '')} ${simEsc(d.startTime || '')} · ${simEsc(d.customerName || 'Customer')} · ${simEsc(d.service || '')}</span>${link}`;
  }
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

// ── Main send ──────────────────────────────────────────

async function simSend() {
  const inp = simEl('wa-sim-input');
  if (!inp) return;
  const text = inp.value.trim();
  if (!text || simBusy) return;

  inp.value = '';
  simBusy = true;
  simUpdateSend();
  simHidePending();

  simAddBubble('customer', text);
  simAddAppMsg('customer', text);
  simSetAppStatus('AI generating reply…');
  simShowGenerating(true);
  simShowCustomerTyping();

  try {
    const res  = await fetch('/api/messages/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: simHistory }),
    });
    const data = await res.json();
    simHideCustomerTyping();
    simShowGenerating(false);

    if (!res.ok || data.error) {
      simShowError(data.error || 'AI reply failed — check your API key.');
      simSetAppStatus('Error');
      simBusy = false;
      simUpdateSend();
    } else {
      simHistory.push({ role: 'customer', text });
      simCommitReply(data.reply || '');
      if (data.booked && data.booking?.ok) {
        simShowBookingBadge(data.booking);
      } else if (data.booked === false && data.booking?.error) {
        simShowBookingBadge(null, data.booking.error);
      }
    }
  } catch (err) {
    simHideCustomerTyping();
    simShowGenerating(false);
    simShowError('Network error: ' + err.message);
    simSetAppStatus('Error');
    simBusy = false;
    simUpdateSend();
  }
}

// ── Open / close / reset ───────────────────────────────

function simOpen() {
  simEl('wa-simulator')?.classList.remove('wa-sim-closed');
  simEl('wa-sim-toggle')?.classList.add('open');
  simEl('wa-sim-input')?.focus();
  if (window.innerWidth <= 640) document.body.classList.add('sim-open');
}
function simClose() {
  simEl('wa-simulator')?.classList.add('wa-sim-closed');
  simEl('wa-sim-toggle')?.classList.remove('open');
  simCancelCountdown();
  document.body.classList.remove('sim-open');
}
function simReset() {
  simHistory = []; simBusy = false;
  simCancelCountdown(); simHidePending(); simShowGenerating(false);
  const msgs = simEl('wa-sim-messages');
  if (msgs) msgs.innerHTML = `<div class="wa-sim-welcome">
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
    <p>Type a customer enquiry to begin.<br>Try <em style="color:#00a884">"how much for a driveway clean?"</em></p>
  </div>`;
  const thread = simEl('wa-sim-app-thread');
  if (thread) thread.innerHTML = `<div class="wa-sim-app-empty" id="wa-sim-app-empty">
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
    <p>Operator view — incoming messages<br>and AI drafts appear here.</p>
  </div>`;
  simSetAppStatus('Waiting for messages');
  const inp = simEl('wa-sim-input');
  if (inp) inp.value = '';
  simUpdateSend();
}

// ── Init ───────────────────────────────────────────────

let simInitDone = false;
function simInitHandlers() {
  if (simInitDone) return;
  simInitDone = true;
  simEl('wa-sim-toggle')?.addEventListener('click', () => {
    simEl('wa-simulator')?.classList.contains('wa-sim-closed') ? simOpen() : simClose();
  });
  simEl('wa-sim-close')?.addEventListener('click', simClose);
  simEl('wa-sim-reset')?.addEventListener('click', simReset);
  simEl('wa-sim-input')?.addEventListener('input', simUpdateSend);
  simEl('wa-sim-input')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); simSend(); }
  });
  simEl('wa-sim-composer')?.addEventListener('submit', (e) => { e.preventDefault(); simSend(); });
  simEl('wa-sim-send-now')?.addEventListener('click', () => {
    const text = simEl('wa-sim-draft-text')?.value?.trim();
    if (text) simCommitReply(text);
  });
}

// Init simulator the first time the Messages tab is clicked
document.querySelector('[data-tab="messages"]')?.addEventListener('click', simInitHandlers);

// ═══════════════════════════════════════════════════════════════
// SETTINGS TAB  (stg-* prefix)
// ═══════════════════════════════════════════════════════════════

let stgInitDone = false;
let stgTemplates = [];

// ── Push notification & audio helpers ─────────────────────────────────────
function urlBase64ToUint8Array(base64) {
  const pad = '='.repeat((4 - base64.length % 4) % 4);
  const b64 = (base64 + pad).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(b64);
  return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
}

const _audioCtx = new (window.AudioContext || window.webkitAudioContext)();

const TONE_DEFS = {
  customer: [[880, 0.08, 0.5], [1100, 0.22, 0.4]],
  human:    [[1100, 0.10, 0.6], [0, 0.05, 0], [1100, 0.10, 0.6]],
  booking:  [[523, 0.10, 0.45], [659, 0.10, 0.5], [784, 0.10, 0.55], [1047, 0.25, 0.6]],
};

function playTone(toneName) {
  try {
    const ctx  = _audioCtx;
    const segs = TONE_DEFS[toneName] || TONE_DEFS.customer;
    let when   = ctx.currentTime + 0.02;
    for (const [freq, dur, vol] of segs) {
      if (!freq) { when += dur; continue; }
      const osc  = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type      = 'sine';
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0, when);
      gain.gain.linearRampToValueAtTime(vol, when + 0.015);
      gain.gain.linearRampToValueAtTime(0,   when + dur);
      osc.connect(gain); gain.connect(ctx.destination);
      osc.start(when); osc.stop(when + dur + 0.01);
      when += dur;
    }
  } catch (_) {}
}

let _pushSubscription = null;

let _notifInitDone = false;
async function notifInit() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    // On iOS non-PWA or old browsers: show the iOS guidance tip always
    const permRow = document.getElementById('notif-permission-row');
    if (permRow) permRow.style.display = 'block';
    return;
  }

  const badge    = document.getElementById('notif-permission-badge');
  const permRow  = document.getElementById('notif-permission-row');
  const enableBtn = document.getElementById('notif-enable-btn');

  async function getOrCreateSubscription() {
    const reg     = await navigator.serviceWorker.ready;
    const vapidRes = await fetch('/api/push/vapid-public-key');
    const { publicKey } = await vapidRes.json();
    let sub = await reg.pushManager.getSubscription();
    if (!sub) {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });
    }
    await fetch('/api/push/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sub.toJSON()),
    });
    _pushSubscription = sub;
    return sub;
  }

  async function checkPermission() {
    const perm = Notification.permission;
    if (perm === 'granted') {
      if (badge) { badge.textContent = 'On'; badge.className = 'stg-badge stg-badge-on'; }
      if (permRow) permRow.style.display = 'none';
      await getOrCreateSubscription().catch(() => {});
    } else if (perm === 'denied') {
      if (badge) { badge.textContent = 'Blocked'; badge.className = 'stg-badge stg-badge-off'; }
      if (permRow) permRow.style.display = 'none';
    } else {
      if (badge) { badge.textContent = 'Off'; badge.className = 'stg-badge stg-badge-off'; }
      if (permRow) permRow.style.display = 'block';
    }
  }

  if (enableBtn && !_notifInitDone) {
    enableBtn.addEventListener('click', async () => {
      const result = await Notification.requestPermission();
      if (result === 'granted') {
        await getOrCreateSubscription().catch(() => {});
      }
      checkPermission();
    });
  }
  _notifInitDone = true;

  checkPermission();

  // Load saved prefs and apply to toggles
  const prefsRes = await fetch('/api/notifications/prefs');
  if (prefsRes.ok) {
    const prefs = await prefsRes.json();
    ['customer_message', 'human_input', 'booking_complete'].forEach(type => {
      const p    = prefs[type] || {};
      const tog  = document.querySelector(`.notif-toggle[data-type="${type}"]`);
      const sel  = document.querySelector(`.notif-tone-sel[data-type="${type}"]`);
      if (tog && p.enabled !== undefined) tog.checked = p.enabled;
      if (sel && p.tone) sel.value = p.tone;
    });
  }

  async function savePrefs() {
    const prefs = {};
    ['customer_message', 'human_input', 'booking_complete'].forEach(type => {
      const tog = document.querySelector(`.notif-toggle[data-type="${type}"]`);
      const sel = document.querySelector(`.notif-tone-sel[data-type="${type}"]`);
      prefs[type] = {
        enabled: tog ? tog.checked : true,
        tone:    sel ? sel.value : type === 'human_input' ? 'human' : type === 'booking_complete' ? 'booking' : 'customer',
      };
    });
    await fetch('/api/notifications/prefs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(prefs),
    });
  }

  document.querySelectorAll('.notif-toggle').forEach(tog => {
    tog.addEventListener('change', savePrefs);
  });
  document.querySelectorAll('.notif-tone-sel').forEach(sel => {
    sel.addEventListener('change', savePrefs);
  });

  // Test buttons — play tone locally and send push
  document.querySelectorAll('.notif-test-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const type = btn.dataset.type;
      const sel  = document.querySelector(`.notif-tone-sel[data-type="${type}"]`);
      const tone = sel ? sel.value : 'customer';
      playTone(tone);
      // Also fire a push so you hear it when the app is closed too
      await fetch('/api/push/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type }),
      });
      btn.textContent = '✓';
      setTimeout(() => { btn.textContent = 'Test'; }, 1500);
    });
  });

  // Play tone when push message received while app is open
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('message', e => {
      if (e.data && e.data.tone) playTone(e.data.tone);
    });
  }
}

async function usersInit() {
  const card = document.getElementById('stg-users-card');
  if (card) card.style.display = '';

  async function renderUsers() {
    const listEl = document.getElementById('stg-users-list');
    if (!listEl) return;
    const res = await fetch('/api/auth/users');
    if (!res.ok) return;
    const users = await res.json();
    listEl.innerHTML = users.map(u => `
      <div style="display:flex;align-items:center;justify-content:space-between;padding:0.45rem 0;border-bottom:1px solid var(--border);">
        <div>
          <span style="font-weight:600;font-size:0.88rem;">${u.name || u.email}</span>
          ${u.name ? `<span style="font-size:0.78rem;color:#64748b;margin-left:0.4rem;">${u.email}</span>` : ''}
          <span style="display:inline-block;margin-left:0.5rem;font-size:0.72rem;font-weight:600;padding:1px 7px;border-radius:20px;background:${u.role==='admin'?'#dbeafe':'#f1f5f9'};color:${u.role==='admin'?'#1d4ed8':'#475569'}">${u.role}</span>
        </div>
        ${u.email !== currentUser?.email ? `<button class="secondary" style="font-size:0.78rem;padding:3px 10px;" onclick="userDelete('${u.email}')">Remove</button>` : '<span style="font-size:0.78rem;color:#94a3b8;">(you)</span>'}
      </div>`).join('');
  }

  window.userDelete = async (email) => {
    if (!confirm(`Remove ${email}?`)) return;
    await fetch(`/api/auth/users/${encodeURIComponent(email)}`, { method: 'DELETE' });
    renderUsers();
  };

  const addBtn = document.getElementById('new-user-add-btn');
  const statusEl = document.getElementById('new-user-status');
  if (addBtn) {
    addBtn.addEventListener('click', async () => {
      const name  = document.getElementById('new-user-name').value.trim();
      const email = document.getElementById('new-user-email').value.trim();
      const pwd   = document.getElementById('new-user-password').value.trim();
      const role  = document.getElementById('new-user-role').value;
      if (!email || !pwd) { statusEl.textContent = 'Email and password are required.'; return; }
      addBtn.disabled = true;
      const res = await fetch('/api/auth/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password: pwd, role }),
      });
      const data = await res.json();
      if (res.ok) {
        statusEl.textContent = `✓ ${email} added.`;
        document.getElementById('new-user-name').value = '';
        document.getElementById('new-user-email').value = '';
        document.getElementById('new-user-password').value = '';
        renderUsers();
      } else {
        statusEl.textContent = data.error || 'Could not add user.';
      }
      addBtn.disabled = false;
    });
  }

  renderUsers();
}

async function stgInit() {
  if (!stgInitDone) {
    stgInitDone = true;
    document.getElementById('stg-twilio-save').addEventListener('click', stgSaveTwilio);
    document.getElementById('stg-twilio-test').addEventListener('click', stgTestTwilio);
    document.getElementById('stg-send-test-btn').addEventListener('click', stgSendTestMessage);
    document.getElementById('stg-add-template').addEventListener('click', stgAddTemplate);
    stgSetupWebhookSection();
    document.getElementById('stg-templates-save').addEventListener('click', stgSaveTemplates);
    document.getElementById('stg-sandbox-mode').addEventListener('change', function () {
      document.getElementById('stg-sandbox-info').classList.toggle('stg-hidden', !this.checked);
    });
    // Messages bottom nav → Settings shortcut
    document.getElementById('wa-nav-goto-settings')?.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(el => { el.classList.remove('active'); el.setAttribute('aria-hidden', 'true'); });
      const settingsBtn = document.querySelector('[data-tab="settings"]');
      const settingsTab = document.getElementById('tab-settings');
      if (settingsBtn) settingsBtn.classList.add('active');
      if (settingsTab) { settingsTab.classList.add('active'); settingsTab.removeAttribute('aria-hidden'); }
      stgInit();
    });
  }
  await Promise.all([stgLoadTwilio(), stgLoadTemplates()]);
}

// ── Checkatrade Lead Intake ──────────────────────────────────────────────────
let caInitDone = false;
let waTemplatesCache = [];
function escapeHtml(s) {
  return (s == null ? '' : String(s))
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function caInit() {
  const card = document.getElementById('stg-checkatrade-card');
  const scraperCard = document.getElementById('stg-scraper-card');
  const isAdmin = (typeof currentUser !== 'undefined' && currentUser && currentUser.role === 'admin');
  if (card) card.style.display = isAdmin ? '' : 'none';
  if (scraperCard) scraperCard.style.display = isAdmin ? '' : 'none';
  if (!isAdmin) return;
  if (!caInitDone) {
    caInitDone = true;
    document.getElementById('ca-save')?.addEventListener('click', caSaveSettings);
    document.getElementById('ca-preview')?.addEventListener('click', () => caRunTest(true));
    document.getElementById('ca-send-test')?.addEventListener('click', () => caRunTest(false));
    document.getElementById('ca-gmail-save')?.addEventListener('click', caSaveGmailCreds);
    document.getElementById('ca-login-test')?.addEventListener('click', () => caTestOneInbox('login'));
    document.getElementById('ca-enquiry-test')?.addEventListener('click', () => caTestOneInbox('enquiry'));
    document.getElementById('ca-run-test')?.addEventListener('click', caRunScraperTest);
    caMountScraper();
  }
  caLoadSettings();
  caLoadGmailCreds();
}

async function caLoadGmailCreds() {
  try {
    const d = await fetch('/api/checkatrade/scraper-credentials').then(r => r.json());
    if (d.loginEmail) document.getElementById('ca-login-email').value = d.loginEmail;
    if (d.enquiryEmail) document.getElementById('ca-enquiry-email').value = d.enquiryEmail;
    const badge = document.getElementById('ca-gmail-badge');
    if (badge) {
      const ok = d.hasLoginPassword && d.hasEnquiryPassword;
      badge.textContent = ok ? '✓ Credentials saved' : '⚠ Credentials needed';
      badge.style.color = ok ? '#15803d' : '#b45309';
    }
  } catch(_) {}
}

async function caSaveGmailCreds() {
  const btn = document.getElementById('ca-gmail-save');
  if (!btn) return;
  btn.disabled = true;
  const orig = btn.textContent;
  btn.textContent = 'Saving…';
  try {
    const res = await fetch('/api/checkatrade/scraper-credentials', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        loginEmail:           (document.getElementById('ca-login-email')?.value || '').trim(),
        loginEmailPassword:   document.getElementById('ca-login-pass')?.value || '',
        enquiryEmail:         (document.getElementById('ca-enquiry-email')?.value || '').trim(),
        enquiryEmailPassword: document.getElementById('ca-enquiry-pass')?.value || '',
      }),
    });
    if (res.ok) {
      showToast('Gmail credentials saved!');
      document.getElementById('ca-login-pass').value = '';
      document.getElementById('ca-enquiry-pass').value = '';
      await caLoadGmailCreds();
    } else {
      showToast('Could not save — is the scraper running?', true);
    }
  } catch(_) { showToast('Could not reach the scraper.', true); }
  btn.disabled = false;
  btn.textContent = orig;
}

async function caTestOneInbox(which) {
  const isLogin = which === 'login';
  const btnId    = isLogin ? 'ca-login-test'        : 'ca-enquiry-test';
  const resultId = isLogin ? 'ca-login-test-result'  : 'ca-enquiry-test-result';
  const emailId  = isLogin ? 'ca-login-email'        : 'ca-enquiry-email';
  const passId   = isLogin ? 'ca-login-pass'         : 'ca-enquiry-pass';

  const btn    = document.getElementById(btnId);
  const result = document.getElementById(resultId);
  if (!btn) return;

  btn.disabled = true;
  const orig = btn.textContent;
  btn.textContent = '…';
  if (result) { result.textContent = 'Connecting…'; result.style.color = '#6b7280'; }

  const body = { which };
  const emailVal = document.getElementById(emailId)?.value.trim();
  const passVal  = document.getElementById(passId)?.value;
  if (emailVal) body[isLogin ? 'loginEmail'    : 'enquiryEmail']    = emailVal;
  if (passVal)  body[isLogin ? 'loginEmailPassword' : 'enquiryEmailPassword'] = passVal;

  try {
    const res = await fetch('/api/checkatrade/test-scraper-credentials', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const d = await res.json();
    const r = isLogin ? d.login : d.enquiry;
    if (d.error || !r) {
      if (result) { result.textContent = '✗ ' + (d.error || 'No response'); result.style.color = '#dc2626'; }
    } else if (r.ok) {
      if (result) { result.textContent = '✓ Connected'; result.style.color = '#15803d'; }
    } else {
      const msg = r.error || 'Failed';
      const short = msg.length > 60 ? msg.slice(0, 57) + '…' : msg;
      if (result) { result.textContent = '✗ ' + short; result.style.color = '#dc2626'; result.title = msg; }
    }
  } catch(_) {
    if (result) { result.textContent = '✗ Scraper unreachable'; result.style.color = '#dc2626'; }
  }
  btn.disabled = false;
  btn.textContent = orig;
}

async function caRunScraperTest() {
  const btn = document.getElementById('ca-run-test');
  const status = document.getElementById('ca-run-test-status');
  const results = document.getElementById('ca-run-test-results');
  if (!btn) return;
  btn.disabled = true;
  btn.textContent = 'Running\u2026 (~1\u20132 min)';
  if (status) { status.textContent = 'Starting\u2026'; status.style.color = '#6b7280'; }
  if (results) results.innerHTML = '';

  let r;
  try {
    r = await fetch('/api/checkatrade/run-test', { method: 'POST' });
  } catch (e) {
    if (status) { status.textContent = 'Network error: ' + (e.message || e); status.style.color = '#dc2626'; }
    btn.disabled = false; btn.textContent = '\u25b6 Test Checkatrade scraper'; return;
  }
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    if (status) { status.textContent = d.error || 'Could not start test'; status.style.color = '#dc2626'; }
    btn.disabled = false; btn.textContent = '\u25b6 Test Checkatrade scraper'; return;
  }

  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = '', curEvent = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split('\n'); buf = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('event: ')) { curEvent = line.slice(7).trim(); }
        else if (line.startsWith('data: ')) {
          try {
            const d = JSON.parse(line.slice(6));
            if (curEvent === 'teststart' && d.msg && status) { status.textContent = d.msg; status.style.color = '#6b7280'; }
            else if (curEvent === 'status' && status) { status.textContent = typeof d === 'string' ? d : JSON.stringify(d); status.style.color = '#6b7280'; }
            else if (curEvent === 'testresult' && results) {
              const l = d.lead, e = d.enquiry || {};
              const card = document.createElement('div');
              card.style.cssText = 'border:1px solid #e3e8f0;border-radius:10px;padding:12px;margin-bottom:10px;background:#fafbfd;font-size:13px';
              const badge = l ? '<span style="color:#03543f;font-weight:600">\u2713 Matched</span>' : '<span style="color:#9b1c1c;font-weight:600">\u2717 No match</span>';
              card.innerHTML = '<div style="display:flex;justify-content:space-between"><strong>Email ' + ((d.index ?? 0) + 1) + ' of ' + (d.total ?? '?') + '</strong>' + badge + '</div>' +
                '<div style="color:#636e85;margin-top:4px">' + (e.subject || '') + (e.postcode ? ' \u00b7 ' + e.postcode : '') + '</div>' +
                (l ? '<div style="margin-top:6px"><b>' + (l.customerName || '\u2014') + '</b> \u00b7 ' + (l.phone || '') + ' \u00b7 ' + (l.email || '') + '<br>' + (l.jobTitle || '') + '</div>' : '');
              results.appendChild(card);
            }
            else if (curEvent === 'testdone') {
              if (d.error) { if (status) { status.textContent = d.error; status.style.color = '#dc2626'; } }
              else { if (status) { status.textContent = 'Done \u2014 ' + d.matched + '/' + d.total + ' matched'; status.style.color = '#15803d'; } }
            }
          } catch (_) {}
          curEvent = '';
        }
      }
    }
  } catch (e) {
    if (status) { status.textContent = 'Connection lost: ' + (e.message || e); status.style.color = '#dc2626'; }
  }
  btn.disabled = false; btn.textContent = '\u25b6 Test Checkatrade scraper';
}

function caMountScraper() {
  const frame = document.getElementById('ca-scraper-frame');
  const openLink = document.getElementById('ca-scraper-open');
  const fallback = document.getElementById('ca-scraper-fallback');
  if (!frame) return;
  const override = (typeof window !== 'undefined' && window.CHECKATRADE_SCRAPER_URL) ? String(window.CHECKATRADE_SCRAPER_URL) : '';
  const base = (override || (location.protocol + '//' + location.hostname + ':8080')).replace(/\/+$/, '');
  const url = base + '/api/checkatrade';
  if (openLink) openLink.href = url;
  if (!frame.src) frame.src = url;
  if (fallback) {
    fallback.innerHTML = 'If the control screen doesn\'t load, open it directly: <a href="' + url + '" target="_blank" rel="noopener">' + url + '</a>';
    fallback.style.display = '';
  }
}

function caPopulateTemplates(selectedSid) {
  const sel = document.getElementById('ca-default-template');
  const tpls = (waTemplatesCache || []);
  if (sel) {
    sel.innerHTML = '<option value="">— none —</option>' +
      tpls.map(t => `<option value="${escapeHtml(t.sid || '')}">${escapeHtml(t.name || t.sid || '')}</option>`).join('');
    if (selectedSid) sel.value = selectedSid;
  }
  const pool = document.getElementById('ca-template-pool');
  if (pool) {
    const sendable = tpls.filter(t => {
      const st = (t.twilioStatus || '').trim().toLowerCase();
      return st === '' || st === 'approved';
    });
    if (!sendable.length) {
      pool.innerHTML = '<span style="color:#b45309">No approved templates yet — add one under Settings → Approved Message Templates and it will appear here automatically.</span>';
    } else {
      pool.innerHTML = sendable.map(t => {
        const st = (t.twilioStatus || '').trim().toLowerCase();
        const ok = st === 'approved';
        const badge = ok
          ? '<span style="color:#15803d">✓ approved</span>'
          : '<span style="color:#9ca3af">legacy</span>';
        return `<div>• ${escapeHtml(t.name || t.sid || 'Untitled')} — ${badge}</div>`;
      }).join('');
    }
  }
}

async function caLoadSettings() {
  try {
    if (!waTemplatesCache || !waTemplatesCache.length) {
      try {
        const td = await fetch('/api/settings/templates').then(r => r.json());
        waTemplatesCache = td.templates || [];
      } catch (_) {}
    }
    const s = await fetch('/api/checkatrade/settings').then(r => r.json());
    document.getElementById('ca-active').checked = !!s.active;
    document.getElementById('ca-aimatch').checked = s.aiMatch !== false;
    document.getElementById('ca-automatch').checked = s.autoMatch !== false;
    caPopulateTemplates(s.defaultTemplateSid || '');
    const url = document.getElementById('ca-webhook-url');
    if (url) url.textContent = s.webhookUrl || '—';
    document.getElementById('ca-token-note').style.display = s.tokenRequired ? '' : 'none';
    caUpdateBadge(!!s.active);
  } catch (_) {}
}

function caUpdateBadge(active) {
  const b = document.getElementById('ca-status-badge');
  if (!b) return;
  b.textContent = active ? 'Active' : 'Off';
  b.className = active ? 'stg-badge stg-badge-on' : 'stg-badge stg-badge-off';
}

async function caSaveSettings() {
  const btn = document.getElementById('ca-save');
  btn.disabled = true; const orig = btn.textContent; btn.textContent = 'Saving…';
  try {
    const payload = {
      active: document.getElementById('ca-active').checked,
      aiMatch: document.getElementById('ca-aimatch').checked,
      autoMatch: document.getElementById('ca-automatch').checked,
      defaultTemplateSid: document.getElementById('ca-default-template').value,
    };
    const res = await fetch('/api/checkatrade/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.ok) { showToast('Checkatrade settings saved.'); caUpdateBadge(payload.active); }
    else showToast('Could not save settings.', true);
  } catch (_) { showToast('Could not save settings.', true); }
  finally { btn.disabled = false; btn.textContent = orig; }
}

async function caRunTest(dryRun) {
  const btnId = dryRun ? 'ca-preview' : 'ca-send-test';
  const btn = document.getElementById(btnId);
  btn.disabled = true; const orig = btn.textContent;
  btn.textContent = dryRun ? 'Previewing…' : 'Sending…';
  const box = document.getElementById('ca-test-result');
  try {
    const payload = {
      dryRun: dryRun,
      force: !dryRun,
      customerName: document.getElementById('ca-test-name').value.trim(),
      phone:        document.getElementById('ca-test-phone').value.trim(),
      email:        document.getElementById('ca-test-email').value.trim(),
      postcode:     document.getElementById('ca-test-postcode').value.trim(),
      jobTitle:     document.getElementById('ca-test-jobtitle').value.trim(),
      profile:      document.getElementById('ca-test-profile').value.trim(),
      jobDescription: document.getElementById('ca-test-desc').value.trim(),
    };
    const res = await fetch('/api/checkatrade/test', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    caRenderTestResult(data, dryRun);
    box.classList.remove('stg-hidden');
  } catch (e) {
    box.innerHTML = `<div class="stg-info-box" style="border-color:#fecaca;background:#fef2f2"><div>Request failed: ${escapeHtml(String(e))}</div></div>`;
    box.classList.remove('stg-hidden');
  } finally { btn.disabled = false; btn.textContent = orig; }
}

function caMatchLabel(match) {
  if (!match || !match.method) return '';
  const labels = {
    ai: '🤖 chosen by AI',
    keyword: '🔤 keyword match',
    default: '↩ default template',
    fallback: '↩ first available',
  };
  const label = labels[match.method] || match.method;
  const reason = match.reason ? ` — ${escapeHtml(match.reason)}` : '';
  return ` <span style="color:#6b7280;font-weight:400;font-size:12px">(${label}${reason})</span>`;
}

function caRenderTestResult(data, dryRun) {
  const box = document.getElementById('ca-test-result');
  const r = data.route || {};
  const tpl = r.template;
  const vars = r.contentVariables || {};
  const varRows = Object.keys(vars).length
    ? Object.entries(vars).map(([k, v]) => `<tr><td style="padding:2px 10px 2px 0;color:#6b7280">{{${escapeHtml(k)}}}</td><td>${escapeHtml(v || '(empty)')}</td></tr>`).join('')
    : '<tr><td colspan="2" style="color:#9ca3af">No variables</td></tr>';

  let banner = '';
  if (data.error) {
    banner = `<div style="color:#b91c1c;font-weight:600;margin-bottom:8px">⚠ ${escapeHtml(data.error)}</div>`;
  } else if (data.warning) {
    banner = `<div style="color:#b45309;font-weight:600;margin-bottom:8px">⚠ ${escapeHtml(data.warning)}</div>`;
  } else if (data.skipped) {
    banner = `<div style="color:#b45309;font-weight:600;margin-bottom:8px">Intake is off — ${escapeHtml(data.reason || 'lead ignored')}.</div>`;
  } else if (dryRun) {
    banner = `<div style="color:#15803d;font-weight:600;margin-bottom:8px">✓ Route preview — nothing was sent.</div>`;
  } else if (data.ok) {
    banner = `<div style="color:#15803d;font-weight:600;margin-bottom:8px">✓ Test message sent${data.sid ? ' (' + escapeHtml(data.sid) + ')' : ''}.</div>`;
  } else {
    banner = `<div style="color:#b91c1c;font-weight:600;margin-bottom:8px">Send failed${data.error ? ': ' + escapeHtml(data.error) : ''}.</div>`;
  }

  box.innerHTML = `
    <div class="stg-info-box" style="display:block;background:#f8fafc;border-color:#e2e8f0">
      ${banner}
      <div style="font-size:13px;line-height:1.7">
        <div><strong>Conversation:</strong> ${escapeHtml(r.displayName || '—')} ${r.conversationId ? '· ' + escapeHtml(r.conversationId) : ''}</div>
        <div><strong>Template chosen:</strong> ${tpl ? escapeHtml(tpl.name || tpl.sid) : '<span style="color:#b45309">none matched</span>'}${caMatchLabel(r.match)}</div>
        <table style="margin:6px 0"><tbody>${varRows}</tbody></table>
        <div style="margin-top:8px"><strong>Message that will be sent:</strong></div>
        <pre style="white-space:pre-wrap;background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:10px;margin:6px 0;font-family:inherit;font-size:13px">${escapeHtml(r.renderedMessage || '(no template)')}</pre>
        <details style="margin-top:6px"><summary style="cursor:pointer;color:#6b7280">AI context seeded for this customer</summary><pre style="white-space:pre-wrap;background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:10px;margin:6px 0;font-family:inherit;font-size:12px">${escapeHtml(r.leadContext || '')}</pre></details>
      </div>
    </div>`;
}

async function stgLoadTwilio() {
  try {
    const s = await fetch('/api/settings/twilio').then(r => r.json());
    document.getElementById('stg-account-sid').value = s.accountSid || '';
    document.getElementById('stg-auth-token').placeholder =
      s.authTokenSet ? '••••••••••••••••••••• (saved)' : 'Paste auth token…';
    document.getElementById('stg-whatsapp-from').value = s.whatsappFrom || '';
    document.getElementById('stg-messaging-sid').value = s.messagingServiceSid || '';
    document.getElementById('stg-sender-name').value = s.senderName || '';
    const sbBox = document.getElementById('stg-sandbox-mode');
    sbBox.checked = !!s.sandboxMode;
    document.getElementById('stg-sandbox-keyword').value = s.sandboxKeyword || '';
    document.getElementById('stg-sandbox-info').classList.toggle('stg-hidden', !sbBox.checked);
    stgUpdateBadge(s.accountSid && s.authTokenSet);
  } catch (_) {}
}

function stgUpdateBadge(connected) {
  const badge = document.getElementById('stg-twilio-badge');
  if (!badge) return;
  badge.textContent = connected ? 'Configured' : 'Not configured';
  badge.className   = connected ? 'stg-badge stg-badge-on' : 'stg-badge stg-badge-off';
}

async function stgSaveTwilio() {
  const btn = document.getElementById('stg-twilio-save');
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    const payload = {
      accountSid:        document.getElementById('stg-account-sid').value.trim(),
      authToken:         document.getElementById('stg-auth-token').value.trim(),
      whatsappFrom:      document.getElementById('stg-whatsapp-from').value.trim(),
      messagingServiceSid: document.getElementById('stg-messaging-sid').value.trim(),
      sandboxMode:       document.getElementById('stg-sandbox-mode').checked,
      sandboxKeyword:    document.getElementById('stg-sandbox-keyword').value.trim(),
      senderName:        document.getElementById('stg-sender-name').value.trim(),
    };
    const res = await fetch('/api/settings/twilio', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      showToast('Twilio settings saved.');
      document.getElementById('stg-auth-token').value = '';
      await stgLoadTwilio();
    } else { showToast('Failed to save settings.', 'error'); }
  } catch (e) { showToast('Error: ' + e.message, 'error'); }
  finally {
    btn.disabled = false;
    btn.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> Save';
  }
}

async function stgTestTwilio() {
  const btn    = document.getElementById('stg-twilio-test');
  const result = document.getElementById('stg-test-result');
  btn.disabled = true; btn.textContent = 'Testing…';
  result.className   = 'stg-test-result stg-test-testing';
  result.textContent = 'Connecting to Twilio…';
  result.classList.remove('stg-hidden');

  // Save any unsaved credentials first
  const sid   = document.getElementById('stg-account-sid').value.trim();
  const token = document.getElementById('stg-auth-token').value.trim();
  if (sid || token) await stgSaveTwilio();

  try {
    const res  = await fetch('/api/settings/twilio/test', { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      result.className = 'stg-test-result stg-test-ok';
      result.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> Connected — <strong>${data.name}</strong> (${data.status})`;
      stgUpdateBadge(true);
    } else {
      result.className = 'stg-test-result stg-test-error';
      result.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> ${data.error}`;
    }
  } catch (e) {
    result.className   = 'stg-test-result stg-test-error';
    result.textContent = 'Test failed: ' + e.message;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg> Test connection';
  }
}

async function stgLoadTemplates() {
  try {
    const data = await fetch('/api/settings/templates').then(r => r.json());
    stgTemplates = data.templates || [];
  } catch (_) { stgTemplates = []; }
  stgRenderTemplates();
}

function stgEsc(str) {
  return (str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function stgStatusBadge(status) {
  if (!status) return '';
  const map = {
    approved:       ['stg-badge-approved', '✓ Approved'],
    pending:          ['stg-badge-pending', '⏳ Pending review'],
    pending_deletion: ['stg-badge-pending', '⏳ Pending deletion'],
    received:         ['stg-badge-pending', '⏳ Submitted — awaiting review'],
    submitted:        ['stg-badge-pending', '⏳ Submitted — awaiting review'],
    in_review:        ['stg-badge-pending', '⏳ In review'],
    rejected:       ['stg-badge-rejected', '✗ Rejected'],
    approval_failed:['stg-badge-rejected', '✗ Submit failed'],
  };
  const [cls, label] = map[status] || ['stg-badge-pending', status];
  return `<span class="stg-status-badge ${cls}">${label}</span>`;
}

function stgRenderTemplates() {
  const list = document.getElementById('stg-templates-list');
  if (!list) return;
  if (stgTemplates.length === 0) {
    list.innerHTML = '<p class="stg-empty-state">No templates yet. Click "Add template" to create your first one.</p>';
    return;
  }
  list.innerHTML = stgTemplates.map((t, i) => {
    const hasSid    = !!(t.sid || '').trim();
    const isApproved = t.twilioStatus === 'approved';
    const isPending  = ['pending','pending_deletion','received','submitted','in_review'].includes(t.twilioStatus);
    return `
    <div class="stg-template-item" data-index="${i}">
      <div class="stg-template-header">
        <input class="stg-template-name" type="text" placeholder="Template name (e.g. Initial follow-up)" value="${stgEsc(t.name)}">
        <button class="stg-template-remove" data-index="${i}" title="Remove template">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
        </button>
      </div>
      <textarea class="stg-template-body" rows="4" placeholder="Hi {{customer_name}}, thanks for reaching out to PowWash! We'll be in touch shortly.">${stgEsc(t.body)}</textarea>
      <div class="stg-template-actions-row">
        <div class="stg-template-hint">
          Use <code>{{variable_name}}</code> for placeholders.
        </div>
        <div class="stg-template-twilio-row">
          <label class="stg-cat-label" title="UTILITY: quotes, follow-ups, booking confirmations&#10;MARKETING: promotions, offers&#10;AUTHENTICATION: OTP codes">Category:
            <select class="stg-template-category">
              <option value="UTILITY"${(t.category||'UTILITY')==='UTILITY'?' selected':''}>Utility</option>
              <option value="MARKETING"${(t.category||'')==='MARKETING'?' selected':''}>Marketing</option>
              <option value="AUTHENTICATION"${(t.category||'')==='AUTHENTICATION'?' selected':''}>Authentication</option>
            </select>
          </label>
          ${hasSid ? `<span class="stg-template-sid-display" title="Content SID">${stgEsc((t.sid||'').slice(0,24))}…</span>` : ''}
          ${stgStatusBadge(t.twilioStatus)}
          ${!isApproved ? `<button class="stg-submit-twilio-btn" data-index="${i}">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
            ${hasSid ? 'Resubmit' : 'Submit to Twilio'}
          </button>` : ''}
          ${(hasSid && isPending) ? `<button class="stg-check-status-btn" data-index="${i}" data-sid="${stgEsc(t.sid)}">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            Check status
          </button>` : ''}
        </div>
      </div>
      <div class="stg-twilio-result" id="stg-twilio-result-${i}" style="display:none"></div>
    </div>`;
  }).join('');

  list.querySelectorAll('.stg-template-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      stgCollectTemplates();
      stgTemplates.splice(parseInt(btn.dataset.index), 1);
      stgRenderTemplates();
    });
  });

  list.querySelectorAll('.stg-submit-twilio-btn').forEach(btn => {
    btn.addEventListener('click', () => stgSubmitToTwilio(parseInt(btn.dataset.index)));
  });

  list.querySelectorAll('.stg-check-status-btn').forEach(btn => {
    btn.addEventListener('click', () => stgCheckTwilioStatus(parseInt(btn.dataset.index), btn.dataset.sid));
  });
}

async function stgSubmitToTwilio(index) {
  stgCollectTemplates();
  const t = stgTemplates[index];
  if (!t) return;
  if (!t.name) { showToast('Give this template a name before submitting.', 'error'); return; }
  if (!t.body) { showToast('Template body is empty.', 'error'); return; }

  const btn    = document.querySelector(`.stg-submit-twilio-btn[data-index="${index}"]`);
  const result = document.getElementById(`stg-twilio-result-${index}`);
  if (btn) { btn.disabled = true; btn.textContent = 'Submitting…'; }
  if (result) { result.style.display = 'block'; result.className = 'stg-twilio-result stg-twilio-info'; result.textContent = 'Sending to Twilio Content API…'; }

  try {
    const res  = await fetch('/api/templates/submit-twilio', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template_name: t.name, category: t.category || 'UTILITY' }),
    });
    const data = await res.json();
    if (data.ok) {
      stgTemplates[index].sid          = data.sid;
      stgTemplates[index].twilioStatus = data.status;
      if (data.var_map) stgTemplates[index].varMap = data.var_map;
      if (result) {
        result.className = 'stg-twilio-result stg-twilio-success';
        result.innerHTML = `✓ Submitted — SID: <code>${data.sid}</code> · Status: <strong>${data.status}</strong>${data.approval_error ? `<br><small style="color:#b45309">Approval note: ${data.approval_error}</small>` : ''}`;
      }
      showToast('Template submitted to Twilio for WhatsApp approval', 'success');
      setTimeout(stgRenderTemplates, 1200);
    } else {
      throw new Error(data.error || 'Submit failed');
    }
  } catch (e) {
    if (result) { result.className = 'stg-twilio-result stg-twilio-error'; result.textContent = '✗ ' + e.message; }
    showToast('Submission failed: ' + e.message, 'error');
    if (btn) { btn.disabled = false; btn.textContent = 'Submit to Twilio'; }
  }
}

async function stgCheckTwilioStatus(index, sid) {
  const btn    = document.querySelector(`.stg-check-status-btn[data-index="${index}"]`);
  const result = document.getElementById(`stg-twilio-result-${index}`);
  if (btn) { btn.disabled = true; btn.textContent = 'Checking…'; }
  if (result) { result.style.display = 'block'; result.className = 'stg-twilio-result stg-twilio-info'; result.textContent = 'Checking approval status…'; }

  try {
    const res  = await fetch('/api/templates/check-status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sid }),
    });
    const data = await res.json();
    if (data.ok) {
      stgTemplates[index].twilioStatus = data.status;
      if (result) {
        const isApproved = data.status === 'approved';
        result.className = `stg-twilio-result ${isApproved ? 'stg-twilio-success' : 'stg-twilio-info'}`;
        result.textContent = `Status: ${data.status}`;
      }
      showToast(`Approval status: ${data.status}`, data.status === 'approved' ? 'success' : 'info');
      setTimeout(stgRenderTemplates, 800);
    } else {
      throw new Error(data.error || 'Check failed');
    }
  } catch (e) {
    if (result) { result.className = 'stg-twilio-result stg-twilio-error'; result.textContent = '✗ ' + e.message; }
    if (btn) { btn.disabled = false; btn.textContent = 'Check status'; }
  }
}

function stgCollectTemplates() {
  const items = document.querySelectorAll('.stg-template-item');
  stgTemplates = Array.from(items).map(item => {
    const idx = parseInt(item.dataset.index);
    const prev = stgTemplates[idx] || {};
    return {
      name:         item.querySelector('.stg-template-name')?.value.trim()     || '',
      body:         item.querySelector('.stg-template-body')?.value.trim()     || '',
      category:     item.querySelector('.stg-template-category')?.value        || 'UTILITY',
      sid:          prev.sid          || '',
      twilioStatus: prev.twilioStatus || '',
      varMap:       prev.varMap       || {},
    };
  });
}

function stgAddTemplate() {
  stgCollectTemplates();
  stgTemplates.push({ name: '', body: '', category: 'UTILITY', sid: '' });
  stgRenderTemplates();
  const items = document.querySelectorAll('.stg-template-item');
  if (items.length) items[items.length - 1].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  items[items.length - 1]?.querySelector('.stg-template-name')?.focus();
}

async function stgSaveTemplates() {
  stgCollectTemplates();
  const btn = document.getElementById('stg-templates-save');
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    const res = await fetch('/api/settings/templates', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ templates: stgTemplates }),
    });
    if (res.ok) { showToast(`${stgTemplates.length} template${stgTemplates.length !== 1 ? 's' : ''} saved.`); }
    else { showToast('Failed to save templates.', 'error'); }
  } catch (e) { showToast('Error: ' + e.message, 'error'); }
  finally {
    btn.disabled = false;
    btn.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> Save templates';
  }
}

// Trigger init when Settings tab is clicked
document.querySelector('[data-tab="settings"]')?.addEventListener('click', () => { stgInit(); notifInit(); });

async function stgSendTestMessage() {
  const btn    = document.getElementById('stg-send-test-btn');
  const result = document.getElementById('stg-send-test-result');
  const to     = document.getElementById('stg-test-to').value.trim();
  const body   = document.getElementById('stg-test-body').value.trim();

  if (!to)   { stgShowSendResult('error', 'Enter a recipient number first.'); return; }
  if (!to.startsWith('+')) {
    stgShowSendResult('error',
      'Number must start with a <strong>+</strong> and include the country code — e.g. <strong>+44</strong>7565708252 for a UK number, not 07565708252.');
    return;
  }
  if (!body) { stgShowSendResult('error', 'Enter a message to send.'); return; }

  btn.disabled = true; btn.textContent = 'Sending…';
  stgShowSendResult('testing', 'Sending via Twilio…');

  try {
    const res  = await fetch('/api/settings/twilio/send-test', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ to, body }),
    });
    const data = await res.json();
    if (data.ok) {
      stgShowSendResult('ok',
        `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>` +
        ` Message sent — SID <code style="font-size:11px;background:rgba(0,0,0,0.06);padding:1px 5px;border-radius:3px">${data.sid}</code>, status: <strong>${data.status}</strong>`);
    } else {
      stgShowSendResult('error',
        `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> ` +
        data.error);
    }
  } catch (e) {
    stgShowSendResult('error', 'Request failed: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg> Send';
  }
}

function stgShowSendResult(type, html) {
  const el = document.getElementById('stg-send-test-result');
  el.className = `stg-test-result stg-test-${type}`;
  el.innerHTML = html;
  el.classList.remove('stg-hidden');
}

// ═══════════════════════════════════════════════════════════════
// WEBHOOK & LIVE INBOX
// ═══════════════════════════════════════════════════════════════

async function stgTestWebhook() {
  const btn    = document.getElementById('stg-webhook-test-btn');
  const result = document.getElementById('stg-webhook-test-result');
  btn.disabled = true;
  btn.textContent = 'Testing…';
  result.className   = 'stg-test-result stg-test-testing';
  result.textContent = 'Sending test request…';
  result.classList.remove('stg-hidden');
  try {
    const res  = await fetch('/api/settings/webhook/test', { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      result.className = 'stg-test-result stg-test-ok';
      result.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> Webhook is reachable — test message received successfully.`;
    } else {
      result.className = 'stg-test-result stg-test-error';
      result.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> ${data.error}`;
    }
  } catch (e) {
    result.className   = 'stg-test-result stg-test-error';
    result.textContent = 'Test failed: ' + e.message;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/><path d="M19.1 4.9C23 8.8 23 15.2 19.1 19.1"/></svg> Test webhook`;
  }
}

let stgInboxTimer = null;
let stgInboxLastCount = 0;

function stgSetupWebhookSection() {
  const base = window.location.origin;
  const waUrl  = base + '/webhook/whatsapp';
  const smsUrl = base + '/webhook/sms';

  const urlEl = document.getElementById('stg-webhook-url');
  if (urlEl) urlEl.textContent = waUrl;
  const smsEl = document.getElementById('stg-sms-webhook-url');
  if (smsEl) smsEl.textContent = smsUrl;

  function makeCopyHandler(btnId, url, codeId) {
    document.getElementById(btnId)?.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(url);
        const btn = document.getElementById(btnId);
        const orig = btn.innerHTML;
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.innerHTML = orig; }, 1800);
      } catch (_) {
        const range = document.createRange();
        range.selectNode(document.getElementById(codeId));
        window.getSelection().removeAllRanges();
        window.getSelection().addRange(range);
      }
    });
  }
  makeCopyHandler('stg-copy-webhook',     waUrl,  'stg-webhook-url');
  makeCopyHandler('stg-copy-sms-webhook', smsUrl, 'stg-sms-webhook-url');

  document.getElementById('stg-webhook-test-btn')?.addEventListener('click', stgTestWebhook);
  document.getElementById('stg-open-inbox')?.addEventListener('click', stgOpenInbox);
  document.getElementById('stg-inbox-close')?.addEventListener('click', stgCloseInbox);
  document.getElementById('stg-inbox-clear')?.addEventListener('click', stgClearInbox);

  // Close on backdrop click
  document.getElementById('stg-inbox-overlay')?.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) stgCloseInbox();
  });
}

function stgOpenInbox() {
  document.getElementById('stg-inbox-overlay').classList.remove('stg-hidden');
  document.getElementById('stg-inbox-dot').classList.add('stg-live');
  stgInboxLastCount = 0;
  stgPollInbox();
  stgInboxTimer = setInterval(stgPollInbox, 3000);
}

function stgCloseInbox() {
  document.getElementById('stg-inbox-overlay').classList.add('stg-hidden');
  document.getElementById('stg-inbox-dot').classList.remove('stg-live');
  if (stgInboxTimer) { clearInterval(stgInboxTimer); stgInboxTimer = null; }
}

async function stgClearInbox() {
  try {
    await fetch('/api/webhook/messages', { method: 'DELETE' });
    stgInboxLastCount = 0;
    stgRenderInbox([]);
  } catch (_) {}
}

async function stgPollInbox() {
  const statusEl = document.getElementById('stg-inbox-status');
  const pulseEl  = document.getElementById('stg-inbox-pulse');
  try {
    const data = await fetch('/api/webhook/messages').then(r => r.json());
    const msgs = data.messages || [];
    pulseEl.classList.add('live');
    statusEl.textContent = msgs.length === 0
      ? 'listening — no messages yet'
      : `${msgs.length} message${msgs.length !== 1 ? 's' : ''}`;
    const isNew = msgs.length > stgInboxLastCount;
    stgInboxLastCount = msgs.length;
    stgRenderInbox(msgs, isNew);
  } catch (_) {
    pulseEl.classList.remove('live');
    statusEl.textContent = 'connection error';
  }
}

function stgRenderInbox(msgs, highlightFirst = false) {
  const list  = document.getElementById('stg-inbox-list');
  const empty = document.getElementById('stg-inbox-empty');
  if (msgs.length === 0) {
    list.innerHTML  = '';
    empty.style.display = 'flex';
    return;
  }
  empty.style.display = 'none';
  list.innerHTML = msgs.map((m, i) => {
    const dt      = new Date(m.timestamp * 1000);
    const time    = dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const date    = dt.toLocaleDateString([], { month: 'short', day: 'numeric' });
    const from    = (m.from || '').replace('whatsapp:', '');
    const isNew   = highlightFirst && i === 0;
    const channel = m.channel || ((m.from || '').startsWith('whatsapp:') ? 'whatsapp' : 'sms');
    const badge   = channel === 'whatsapp'
      ? `<span class="stg-inbox-badge stg-inbox-badge-wa">WhatsApp</span>`
      : `<span class="stg-inbox-badge stg-inbox-badge-sms">SMS</span>`;
    return `
      <div class="stg-inbox-msg${isNew ? ' stg-inbox-new' : ''}">
        <div class="stg-inbox-msg-meta">
          ${badge}
          <span class="stg-inbox-msg-from">${from || 'unknown'}</span>
          <span class="stg-inbox-msg-time">${date} ${time}</span>
        </div>
        <div class="stg-inbox-msg-body">${stgEsc(m.body || '(no text)')}</div>
        ${m.numMedia > 0 ? `<div class="stg-inbox-msg-media">📎 ${m.numMedia} media attachment${m.numMedia > 1 ? 's' : ''}</div>` : ''}
      </div>`;
  }).join('');
}


// ═══════════════════════════════════════════════════════════
//  CALENDAR TAB  (cal* functions)
// ═══════════════════════════════════════════════════════════

let _calInitDone = false;

async function calInit() {
  if (_calInitDone) { await calCheckStatus(); return; }
  _calInitDone = true;

  // Set today as default slot-finder date
  const slotDate = document.getElementById('cal-slot-date');
  if (slotDate && !slotDate.value) slotDate.value = new Date().toISOString().slice(0, 10);

  // Wire buttons
  document.getElementById('cal-connect-btn')?.addEventListener('click', calStartOAuth);
  document.getElementById('cal-recheck-btn')?.addEventListener('click', calCheckStatus);
  document.getElementById('cal-test-btn')?.addEventListener('click', calTestConnection);
  document.getElementById('cal-disconnect-btn')?.addEventListener('click', calDisconnect);
  document.getElementById('cal-use-calendar-btn')?.addEventListener('click', calUseCalendar);
  // cal-save-btn-instance buttons use onclick="calSaveSettings()" directly
  document.getElementById('cal-find-slots-btn')?.addEventListener('click', calFindSlots);
  document.getElementById('cal-save-creds-btn')?.addEventListener('click', calSaveCredentials);

  await calLoadCredentialStatus();
  await calCheckStatus();
  await schedInit();
  holdsLoad();
}

async function calCheckStatus() {
  const badge  = document.getElementById('cal-status-badge');
  const errDiv = document.getElementById('cal-connect-error');
  if (badge) { badge.className = 'cal-badge cal-badge-warn'; badge.textContent = 'Checking…'; }

  try {
    const data = await fetch('/api/calendar/status').then(r => r.json());
    calApplyStatus(data);
    if (data.config) calPopulateForm(data.config);
    if (data.connected) calLoadCalendars(data.config?.calendarId);
  } catch (e) {
    if (badge) { badge.className = 'cal-badge cal-badge-off'; badge.textContent = 'Error'; }
    if (errDiv) { errDiv.textContent = String(e); errDiv.style.display = ''; }
  }
}

function calApplyStatus(data) {
  const badge        = document.getElementById('cal-status-badge');
  const hint         = document.getElementById('cal-connect-hint');
  const errDiv       = document.getElementById('cal-connect-error');
  const pickerRow    = document.getElementById('cal-picker-row');
  const connectBtn   = document.getElementById('cal-connect-btn');
  const disconnectBtn= document.getElementById('cal-disconnect-btn');

  const testBtn = document.getElementById('cal-test-btn');
  if (data.connected) {
    if (badge)  { badge.className = 'cal-badge cal-badge-on'; badge.textContent = 'Connected'; }
    if (hint)   hint.textContent = `Connected to "${data.calendarSummary || data.calendarId}". You can change which calendar to use below.`;
    if (errDiv) errDiv.style.display = 'none';
    if (pickerRow) pickerRow.style.display = 'flex';
    if (connectBtn) connectBtn.style.display = 'none';
    if (disconnectBtn) disconnectBtn.style.display = '';
    if (testBtn) testBtn.style.display = '';
  } else {
    if (badge)  { badge.className = 'cal-badge cal-badge-off'; badge.textContent = 'Not connected'; }
    if (hint)   hint.textContent = 'Click "Connect Google Calendar" — a Google sign-in window will open. Approve access and you\'re done.';
    if (pickerRow) pickerRow.style.display = 'none';
    if (connectBtn) connectBtn.style.display = '';
    if (disconnectBtn) disconnectBtn.style.display = 'none';
    if (data.reason && errDiv) {
      errDiv.textContent = '⚠ ' + data.reason;
      errDiv.style.display = '';
    }
  }
}

async function calLoadCredentialStatus() {
  try {
    const data = await fetch('/api/calendar/credentials').then(r => r.json());
    const badge    = document.getElementById('cal-creds-badge');
    const uriEl    = document.getElementById('cal-redirect-uri-display');
    const cidInput = document.getElementById('cal-client-id-input');
    const copyBtn  = document.getElementById('cal-copy-uri-btn');

    // Always derive the redirect URI from the current page origin — server-side
    // host detection is unreliable behind Replit's reverse proxy.
    const uri = window.location.origin + '/api/calendar/oauth/callback';
    if (uriEl) uriEl.textContent = uri;

    // Wire copy button
    if (copyBtn) {
      copyBtn.onclick = async () => {
        try {
          await navigator.clipboard.writeText(uri);
          copyBtn.classList.add('copied');
          copyBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> Copied!';
          setTimeout(() => {
            copyBtn.classList.remove('copied');
            copyBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy';
          }, 2500);
        } catch (_) {
          // Fallback: select the text
          if (uriEl) {
            const range = document.createRange();
            range.selectNodeContents(uriEl);
            window.getSelection()?.removeAllRanges();
            window.getSelection()?.addRange(range);
          }
        }
      };
    }

    if (data.hasCredentials) {
      if (badge) { badge.className = 'cal-badge cal-badge-on'; badge.textContent = 'Saved'; }
      if (cidInput && data.clientIdMasked) cidInput.placeholder = data.clientIdMasked + ' (already saved)';
    } else {
      if (badge) { badge.className = 'cal-badge cal-badge-off'; badge.textContent = 'Not set'; }
    }
  } catch (_) {}
}

async function calSaveCredentials() {
  const btn      = document.getElementById('cal-save-creds-btn');
  const status   = document.getElementById('cal-creds-status');
  const cidInput = document.getElementById('cal-client-id-input');
  const secInput = document.getElementById('cal-client-secret-input');
  const cid = (cidInput?.value || '').trim();
  const sec = (secInput?.value || '').trim();
  if (!cid || !sec) {
    if (status) { status.textContent = 'Both fields are required.'; status.style.color = '#dc2626'; }
    return;
  }
  if (btn) btn.disabled = true;
  if (status) { status.textContent = 'Saving…'; status.style.color = '#6b7280'; }
  try {
    const res = await fetch('/api/calendar/credentials', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clientId: cid, clientSecret: sec }),
    });
    const data = await res.json();
    if (data.ok) {
      if (status) { status.textContent = '✓ Saved'; status.style.color = '#15803d'; }
      if (secInput) secInput.value = '';
      await calLoadCredentialStatus();
      // Re-check calendar status now that credentials are available
      await calCheckStatus();
    } else {
      if (status) { status.textContent = data.error || 'Save failed'; status.style.color = '#dc2626'; }
    }
  } catch (e) {
    if (status) { status.textContent = String(e); status.style.color = '#dc2626'; }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function calTestConnection() {
  const btn    = document.getElementById('cal-test-btn');
  const result = document.getElementById('cal-test-result');
  if (btn) btn.disabled = true;
  if (result) { result.style.display = 'none'; result.className = 'cal-test-result'; }
  try {
    const data = await fetch('/api/calendar/status').then(r => r.json());
    if (result) {
      result.style.display = '';
      if (data.connected) {
        result.className = 'cal-test-result cal-test-ok';
        result.innerHTML =
          `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>` +
          ` Connected to <strong>${data.calendarSummary || data.calendarId}</strong> — calendar access is working.`;
      } else {
        result.className = 'cal-test-result cal-test-fail';
        result.innerHTML =
          `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>` +
          ` Test failed: ${data.reason || 'Unknown error'}`;
      }
    }
  } catch (e) {
    if (result) {
      result.style.display = '';
      result.className = 'cal-test-result cal-test-fail';
      result.textContent = 'Test failed: ' + String(e);
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function calDisconnect() {
  if (!confirm('Disconnect Google Calendar? You can reconnect at any time.')) return;
  try {
    await fetch('/api/calendar/disconnect', { method: 'POST' });
    showToast('Google Calendar disconnected', 'info');
    const result = document.getElementById('cal-test-result');
    if (result) result.style.display = 'none';
    await calCheckStatus();
  } catch (_) {}
}

function calPopulateForm(cfg) {
  const set = (id, val) => { const el = document.getElementById(id); if (el && val !== undefined) el.value = val; };
  const wh = cfg.workingHours || {};
  set('cal-start-time',   wh.start || '08:00');
  set('cal-end-time',     wh.end   || '17:30');
  set('cal-travel-buffer', cfg.travelBufferMinutes ?? 60);
  // stored as minutes, displayed as hours
  const holdMins = cfg.holdTimeoutMinutes ?? 60;
  set('cal-hold-timeout', Math.round((holdMins / 60) * 2) / 2); // round to nearest 0.5

  const fmt = cfg.eventFormat || {};
  set('cal-title-tmpl',   fmt.titleTemplate       || '');
  set('cal-desc-tmpl',    fmt.descriptionTemplate || '');
  set('cal-color-select', fmt.colorId             || '2');

  // Working days checkboxes
  const days = wh.days || [1,2,3,4,5];
  document.querySelectorAll('.cal-day-cb').forEach(cb => {
    cb.checked = days.includes(Number(cb.value));
  });
}

async function calLoadCalendars(currentCalId) {
  const sel = document.getElementById('cal-calendar-select');
  if (!sel) return;
  sel.innerHTML = '<option value="">Loading…</option>';
  try {
    const data = await fetch('/api/calendar/calendars').then(r => r.json());
    const cals = data.calendars || [];
    sel.innerHTML = cals.map(c =>
      `<option value="${calEsc(c.id)}" ${c.id === currentCalId ? 'selected' : ''}>
        ${calEsc(c.summary)}${c.primary ? ' (primary)' : ''}
      </option>`
    ).join('') || '<option value="">No calendars found</option>';
  } catch (e) {
    sel.innerHTML = '<option value="">Could not load calendars</option>';
  }
}

async function calUseCalendar() {
  const sel = document.getElementById('cal-calendar-select');
  const calId = sel?.value;
  if (!calId) return;
  const btn = document.getElementById('cal-use-calendar-btn');
  if (btn) btn.disabled = true;
  try {
    await fetch('/api/calendar/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ calendarId: calId }),
    });
    showToast('Calendar updated', 'success');
    await calCheckStatus();
  } catch (e) {
    showToast('Could not update calendar', 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

function calStartOAuth() {
  const btn    = document.getElementById('cal-connect-btn');
  const errDiv = document.getElementById('cal-connect-error');
  if (btn) btn.disabled = true;
  if (errDiv) errDiv.style.display = 'none';

  // Open the app's own Google OAuth flow in a popup window
  const w = 520, h = 640;
  const left = Math.max(0, (screen.width  - w) / 2);
  const top  = Math.max(0, (screen.height - h) / 2);
  // Pass the redirect URI derived from the browser origin — the server cannot
  // reliably determine the public domain behind Replit's reverse proxy.
  const oauthRedirectUri = encodeURIComponent(window.location.origin + '/api/calendar/oauth/callback');
  const popup = window.open(
    '/api/calendar/oauth/start?redirect_uri=' + oauthRedirectUri,
    'google_calendar_oauth',
    `width=${w},height=${h},left=${left},top=${top},resizable=yes,scrollbars=yes`
  );

  if (!popup) {
    if (errDiv) {
      errDiv.textContent = 'Popup blocked — please allow popups for this site and try again.';
      errDiv.style.display = '';
    }
    if (btn) btn.disabled = false;
    return;
  }

  // Listen for the callback page to post a message back
  function onMessage(evt) {
    if (!evt.data || evt.data.calendarOAuth === undefined) return;
    window.removeEventListener('message', onMessage);
    clearInterval(pollClosed);

    if (evt.data.calendarOAuth === 'success') {
      calCheckStatus().then(() => showToast('Google Calendar connected!', 'success'));
    } else {
      const reason = evt.data.reason || 'OAuth failed';
      if (errDiv) { errDiv.textContent = reason; errDiv.style.display = ''; }
    }
    if (btn) btn.disabled = false;
  }
  window.addEventListener('message', onMessage);

  // Fallback: if the popup is closed without posting a message
  const pollClosed = setInterval(() => {
    if (popup.closed) {
      clearInterval(pollClosed);
      window.removeEventListener('message', onMessage);
      if (btn) btn.disabled = false;
      // Re-check in case it succeeded but message was missed
      calCheckStatus();
    }
  }, 800);
}

async function calSaveSettings() {
  const btns     = document.querySelectorAll('.cal-save-btn-instance');
  const statuses = document.querySelectorAll('.cal-save-status-all');
  btns.forEach(b => b.disabled = true);
  statuses.forEach(s => { s.textContent = 'Saving…'; s.className = 'cal-save-status-all cal-save-status'; });

  const days = Array.from(document.querySelectorAll('.cal-day-cb'))
    .filter(cb => cb.checked).map(cb => Number(cb.value));

  // hold timeout is displayed in hours, stored in minutes
  const holdHours = Number(document.getElementById('cal-hold-timeout')?.value || 1);

  const payload = {
    workingHours: {
      start: document.getElementById('cal-start-time')?.value  || '08:00',
      end:   document.getElementById('cal-end-time')?.value    || '17:30',
      days,
    },
    travelBufferMinutes: Number(document.getElementById('cal-travel-buffer')?.value || 60),
    holdTimeoutMinutes:  Math.round(holdHours * 60),
    eventFormat: {
      titleTemplate:       document.getElementById('cal-title-tmpl')?.value   || '',
      descriptionTemplate: document.getElementById('cal-desc-tmpl')?.value    || '',
      colorId:             document.getElementById('cal-color-select')?.value || '2',
    },
  };

  try {
    const res  = await fetch('/api/calendar/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.ok) {
      statuses.forEach(s => { s.textContent = '✓ Saved'; s.className = 'cal-save-status-all cal-save-status ok'; setTimeout(() => { s.textContent = ''; }, 2500); });
      showToast('Calendar settings saved', 'success');
    } else {
      throw new Error(data.error || 'Save failed');
    }
  } catch (e) {
    statuses.forEach(s => { s.textContent = '✗ ' + e.message; s.className = 'cal-save-status-all cal-save-status err'; });
    showToast('Could not save settings', 'error');
  } finally {
    btns.forEach(b => b.disabled = false);
  }
}

// ── Active Holds ──────────────────────────────────────────────────────────────

async function holdsLoad() {
  const body = document.getElementById('cal-holds-body');
  const btn  = document.getElementById('holds-refresh-btn');
  if (btn)  btn.disabled = true;
  if (body) body.innerHTML = '<p class="cal-hint" style="margin:12px 0 0">Loading…</p>';

  try {
    const data = await fetch('/api/calendar/holds').then(r => r.json());
    if (!data.ok) throw new Error(data.error || 'Could not load holds');

    const mins  = data.timeoutMinutes || 60;
    const label = document.getElementById('holds-timeout-label');
    if (label) {
      label.textContent = mins >= 60
        ? `${mins / 60} hour${mins / 60 !== 1 ? 's' : ''}`
        : `${mins} minutes`;
    }
    holdsRender(data.holds || []);
  } catch (e) {
    if (body) body.innerHTML = `<p class="cal-hint" style="color:#dc2626;margin:12px 0 0">${holdsEsc(e.message)}</p>`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

function holdsRender(holds) {
  const body = document.getElementById('cal-holds-body');
  if (!body) return;

  if (!holds.length) {
    body.innerHTML = '<p class="cal-hint" style="margin:12px 0 0">No active holds — all clear.</p>';
    return;
  }

  const rows = holds.map(h => {
    const slotLabel  = _holdsFormatSlot(h.start, h.end);
    const ageLabel   = _holdsFormatAge(h.ageMinutes);
    const untilLabel = _holdsFormatUntil(h.hoursUntil);
    const isOverdue  = h.status === 'overdue';
    const isUrgent   = h.status === 'urgent';

    const badge = isOverdue
      ? `<span class="holds-badge holds-badge-overdue">Overdue</span>`
      : isUrgent
        ? `<span class="holds-badge holds-badge-urgent">Next day</span>`
        : `<span class="holds-badge holds-badge-active">Awaiting</span>`;

    const warning = isOverdue
      ? `<div class="holds-warning">No response for ${ageLabel} — safe to offer this slot to other customers.</div>`
      : '';

    const eId  = holdsEsc(h.eventId);
    const eCal = holdsEsc(h.calendarId || '');

    return `<div class="holds-row${isOverdue ? ' holds-row-overdue' : isUrgent ? ' holds-row-urgent' : ''}">
      <div class="holds-row-main">
        <div class="holds-info">
          <div class="holds-title">${holdsEsc(h.title)}</div>
          <div class="holds-meta">
            <span class="holds-slot-label">${holdsEsc(slotLabel)}</span>
            <span class="holds-dot">·</span>
            <span>${holdsEsc(untilLabel)}</span>
            <span class="holds-dot">·</span>
            <span class="holds-age">Held ${holdsEsc(ageLabel)}</span>
          </div>
        </div>
        <div class="holds-right">
          ${badge}
          <div class="holds-actions">
            <button class="cal-btn-primary holds-btn-sm" onclick="holdsConfirm('${eId}','${eCal}')">Confirm</button>
            <button class="cal-btn-ghost holds-btn-sm" onclick="holdsRelease('${eId}','${eCal}')">Release</button>
          </div>
        </div>
      </div>
      ${warning}
    </div>`;
  }).join('');

  body.innerHTML = `<div class="holds-list">${rows}</div>`;
}

function _holdsFormatSlot(start, end) {
  if (!start) return 'Unknown slot';
  try {
    const s  = new Date(start);
    const e  = end ? new Date(end) : null;
    const d  = s.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
    const st = s.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
    const et = e ? e.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : '';
    return `${d} · ${st}${et ? ' – ' + et : ''}`;
  } catch { return start; }
}

function _holdsFormatAge(mins) {
  if (mins === null || mins === undefined) return 'just now';
  if (mins < 1)  return 'just now';
  if (mins < 60) return `${Math.round(mins)}m`;
  const h = Math.floor(mins / 60), m = Math.round(mins % 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

function _holdsFormatUntil(hours) {
  if (hours === null || hours === undefined) return '';
  if (hours < 0)  return 'Slot passed';
  if (hours < 1)  return `In ${Math.round(hours * 60)}m`;
  if (hours < 24) return `In ${Math.round(hours)}h`;
  const d = Math.floor(hours / 24);
  return `In ${d} day${d !== 1 ? 's' : ''}`;
}

function holdsEsc(str) {
  return String(str ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/'/g, '&#39;');
}

async function holdsConfirm(eventId, calendarId) {
  if (!confirm('Mark this hold as a confirmed booking?')) return;
  try {
    const res  = await fetch(`/api/calendar/hold/${encodeURIComponent(eventId)}`, {
      method: 'PUT', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ calendarId }),
    });
    const data = await res.json();
    if (data.ok) { showToast('Booking confirmed ✓', 'success'); holdsLoad(); }
    else throw new Error(data.error || 'Confirm failed');
  } catch (e) { showToast('Could not confirm: ' + e.message, 'error'); }
}

async function holdsRelease(eventId, calendarId) {
  if (!confirm('Release this hold? The slot will be freed for other customers.')) return;
  try {
    const url  = `/api/calendar/hold/${encodeURIComponent(eventId)}?calendarId=${encodeURIComponent(calendarId || '')}`;
    const res  = await fetch(url, { method: 'DELETE' });
    const data = await res.json();
    if (data.ok) { showToast('Hold released', 'info'); holdsLoad(); }
    else throw new Error(data.error || 'Release failed');
  } catch (e) { showToast('Could not release: ' + e.message, 'error'); }
}

async function calFindSlots() {
  const btn      = document.getElementById('cal-find-slots-btn');
  const result   = document.getElementById('cal-slots-result');
  const date     = document.getElementById('cal-slot-date')?.value;
  const duration = document.getElementById('cal-slot-duration')?.value || 120;

  if (!date) { if (result) result.innerHTML = '<p class="cal-slots-error">Please pick a date first.</p>'; return; }

  if (btn) btn.disabled = true;
  if (result) result.innerHTML = '<p class="cal-slots-empty">Finding slots…</p>';

  try {
    const res  = await fetch(`/api/calendar/slots?date=${encodeURIComponent(date)}&duration=${duration}`);
    const data = await res.json();

    if (data.error) throw new Error(data.error);

    const slots = data.slots || [];
    if (!slots.length) {
      result.innerHTML = '<p class="cal-slots-empty">No free slots found for that day. Try a different date or reduce the job duration.</p>';
      return;
    }
    result.innerHTML = `
      <p style="font-size:12px;color:#6b7280;margin:0 0 8px">${slots.length} slot${slots.length !== 1 ? 's' : ''} available on ${date} for a ${duration}-min job</p>
      <div class="cal-slots-grid">
        ${slots.map(s => `
          <div class="cal-slot-chip" title="${s.start}">
            ${calEsc(s.startLabel)} – ${calEsc(s.endLabel)}
            <small>${duration} min</small>
          </div>
        `).join('')}
      </div>`;
  } catch (e) {
    if (result) result.innerHTML = `<p class="cal-slots-error">⚠ ${calEsc(String(e))}</p>`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

function calEsc(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ─────────────────────────────────────────────────────────────────────────────
// OPERATOR CONTACTS
// ─────────────────────────────────────────────────────────────────────────────
(function () {
  const opList  = document.getElementById('op-list');
  const opName  = document.getElementById('op-name');
  const opPhone = document.getElementById('op-phone');
  const opRole  = document.getElementById('op-role');
  const opAdd   = document.getElementById('op-add-btn');

  if (!opList) return;

  function render(ops) {
    if (!ops || !ops.length) {
      opList.innerHTML = '<p class="kb-op-empty">No operators saved yet — add one above.</p>';
      return;
    }
    opList.innerHTML = ops.map(op => `
      <div class="kb-op-item ${op.active ? '' : 'kb-op-item--inactive'}" data-id="${op.id}">
        <label class="kb-op-toggle" title="${op.active ? 'Active — click to deactivate' : 'Inactive — click to activate'}">
          <input type="checkbox" class="op-toggle" data-id="${op.id}" ${op.active ? 'checked' : ''} />
          <span class="kb-op-toggle-track"><span class="kb-op-toggle-thumb"></span></span>
        </label>
        <div class="kb-op-info">
          <span class="kb-op-name">${op.name}</span>${op.role ? ` <span class="kb-op-role">(${op.role})</span>` : ''}
          <div class="kb-op-phone">${op.phone}</div>
        </div>
        <button class="kb-op-delete" data-id="${op.id}" title="Remove">✕</button>
      </div>
    `).join('');

    opList.querySelectorAll('.op-toggle').forEach(cb => {
      cb.addEventListener('change', async function () {
        await fetch(`/api/operators/${this.dataset.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ active: this.checked }),
        });
        load();
      });
    });

    opList.querySelectorAll('.kb-op-delete').forEach(btn => {
      btn.addEventListener('click', async function () {
        if (!confirm(`Remove this operator?`)) return;
        const res = await fetch(`/api/operators/${this.dataset.id}`, { method: 'DELETE' });
        const d   = await res.json();
        render(d.operators || []);
        showToast('Operator removed');
      });
    });
  }

  async function load() {
    try {
      const ops = await fetch('/api/operators').then(r => r.json());
      render(ops);
    } catch (_) {}
  }

  opAdd?.addEventListener('click', async () => {
    const name  = opName?.value.trim();
    const phone = opPhone?.value.trim();
    const role  = opRole?.value.trim() || '';
    if (!name || !phone) { showToast('Name and phone number are required', 'error'); return; }
    opAdd.disabled = true;
    try {
      const res = await fetch('/api/operators', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, phone, role }),
      });
      const data = await res.json();
      if (data.ok) {
        if (opName)  opName.value  = '';
        if (opPhone) opPhone.value = '';
        if (opRole)  opRole.value  = '';
        render(data.operators);
        showToast(`${name} added as operator`);
      } else {
        showToast(data.error || 'Failed to add operator', 'error');
      }
    } catch (e) {
      showToast('Failed to add operator: ' + e.message, 'error');
    } finally {
      opAdd.disabled = false;
    }
  });

  load();
})();

// ─────────────────────────────────────────────────────────────────────────────
// ENGINEERS & SMART SCHEDULING
// ─────────────────────────────────────────────────────────────────────────────

async function schedInit() {
  document.getElementById('sched-add-eng-btn')?.addEventListener('click', () => schedShowEngForm(null));
  document.getElementById('sched-save-eng-btn')?.addEventListener('click', schedSaveEngineer);
  document.getElementById('sched-cancel-eng-btn')?.addEventListener('click', schedHideEngForm);
  document.getElementById('sched-save-rules-btn')?.addEventListener('click', schedSaveRules);
  document.getElementById('sched-agent-save-btn')?.addEventListener('click', schedAgentSaveInstructions);
  document.getElementById('sched-agent-maps-save-btn')?.addEventListener('click', schedAgentSaveMapsKey);
  document.getElementById('sched-agent-test-btn')?.addEventListener('click', schedAgentTest);
  await Promise.all([schedLoadEngineers(), schedLoadRules(), schedAgentLoad()]);
}

// ── AI Scheduling Agent ──────────────────────────────────────────────────────

async function schedAgentLoad() {
  try {
    const [cfg, maps] = await Promise.all([
      fetch('/api/scheduling/agent-config').then(r => r.json()),
      fetch('/api/scheduling/maps-config').then(r => r.json()),
    ]);
    schedAgentShowKnowledge(cfg.instructions || '');
    schedAgentUpdateMapsBadge(maps);
  } catch (_) {}
}

function schedAgentShowKnowledge(text, highlightNewLines) {
  const display = document.getElementById('sched-knowledge-display');
  const pre     = document.getElementById('sched-knowledge-text');
  const editBox = document.getElementById('sched-agent-instructions');
  if (editBox) editBox.value = text || '';
  if (display) display.style.display = '';
  const directEdit = document.getElementById('sched-agent-direct-edit');
  if (directEdit) directEdit.style.display = 'none';

  if (!pre) return;
  // Store raw text for edit mode
  pre.dataset.rawText = text || '';

  const rawText = text || '';
  if (!rawText.trim()) {
    pre.innerHTML = '<span style="color:#9ca3af">(No knowledge saved yet — add something below.)</span>';
    return;
  }

  // Build expandable sections from ## headings
  const newLines  = new Set(highlightNewLines || []);
  const lines     = rawText.split('\n');
  let html        = '';
  let inSection   = false;
  let sectionBody = '';
  let sectionIdx  = 0;

  function flushSection(heading, body, idx) {
    const id  = `sched-ks-${idx}`;
    const hHl = newLines.has(heading.trim()) ? ' sched-line-new' : '';
    // Check if any body line is highlighted
    const bodyLines = body.split('\n');
    const bodyHtml  = bodyLines.map(l => {
      const hl = newLines.has(l.trim()) ? ' sched-line-new' : '';
      return `<span class="sched-kl${hl}">${escHtml(l)}</span>`;
    }).join('\n');
    return (
      `<div class="sched-ksection">` +
        `<button class="sched-ksection-hdr${hHl}" data-target="${id}" aria-expanded="true" type="button">` +
          `<svg class="sched-ksection-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>` +
          escHtml(heading.replace(/^#{1,3}\s*/, '').replace(/\*\*/g, '')) +
        `</button>` +
        `<div class="sched-ksection-body" id="${id}"><pre class="sched-ksection-pre">${bodyHtml}</pre></div>` +
      `</div>`
    );
  }

  let currentHeading = '';
  lines.forEach(line => {
    if (/^#{1,3} /.test(line)) {
      if (inSection) {
        html += flushSection(currentHeading, sectionBody.replace(/^\n+/, '').replace(/\n+$/, ''), sectionIdx++);
        sectionBody = '';
      }
      currentHeading = line;
      inSection      = true;
    } else if (inSection) {
      sectionBody += '\n' + line;
    } else {
      // Pre-section preamble
      const hl = newLines.has(line.trim()) ? ' sched-line-new' : '';
      html += `<span class="sched-kl${hl}">${escHtml(line)}</span>\n`;
    }
  });
  if (inSection) html += flushSection(currentHeading, sectionBody.replace(/^\n+/, '').replace(/\n+$/, ''), sectionIdx++);

  pre.innerHTML = html;

  // Wire up toggle clicks
  pre.querySelectorAll('.sched-ksection-hdr').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = document.getElementById(btn.dataset.target);
      const open   = btn.getAttribute('aria-expanded') === 'true';
      btn.setAttribute('aria-expanded', open ? 'false' : 'true');
      btn.classList.toggle('sched-ksection-hdr--collapsed', open);
      if (target) target.style.display = open ? 'none' : '';
    });
  });

  // Remove highlight after 6 seconds
  if (newLines.size) {
    setTimeout(() => {
      pre.querySelectorAll('.sched-line-new').forEach(el => el.classList.remove('sched-line-new'));
    }, 6000);
  }
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Direct edit toggle
document.getElementById('sched-agent-edit-btn')?.addEventListener('click', () => {
  const display    = document.getElementById('sched-knowledge-display');
  const directEdit = document.getElementById('sched-agent-direct-edit');
  if (display)    display.style.display    = 'none';
  if (directEdit) directEdit.style.display = '';
  const editBox = document.getElementById('sched-agent-instructions');
  if (editBox) editBox.focus();
});

document.getElementById('sched-agent-cancel-edit-btn')?.addEventListener('click', () => {
  const pre = document.getElementById('sched-knowledge-text');
  schedAgentShowKnowledge(pre?.dataset?.rawText || '');
});

// Refine with AI
async function schedAgentRefine() {
  const input    = document.getElementById('sched-agent-refine-input');
  const btn      = document.getElementById('sched-agent-refine-btn');
  const statusEl = document.getElementById('sched-agent-refine-status');
  const newInfo  = (input?.value || '').trim();
  if (!newInfo) { if (input) input.focus(); return; }
  if (btn) btn.disabled = true;
  if (statusEl) { statusEl.textContent = 'Thinking…'; statusEl.className = 'cal-save-status'; statusEl.style.color = '#6b7280'; }
  try {
    const res  = await fetch('/api/scheduling/agent-config/refine', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ newInfo }),
    });
    const data = await res.json();
    if (data.ok) {
      // Diff old vs new to find changed/added lines for highlight
      const oldPre  = document.getElementById('sched-knowledge-text');
      const oldText = (oldPre?.dataset?.rawText || '');
      const oldSet  = new Set(oldText.split('\n').map(l => l.trim()).filter(Boolean));
      const newLines = data.instructions.split('\n')
        .map(l => l.trim()).filter(l => l && !oldSet.has(l));
      schedAgentShowKnowledge(data.instructions, newLines);
      if (input) input.value = '';
      if (statusEl) { statusEl.textContent = 'Updated ✓'; statusEl.style.color = '#16a34a'; setTimeout(() => { if (statusEl) statusEl.textContent = ''; }, 3000); }
    } else {
      if (statusEl) { statusEl.textContent = data.error || 'Error'; statusEl.style.color = '#dc2626'; }
    }
  } catch (e) {
    if (statusEl) { statusEl.textContent = 'Failed'; statusEl.style.color = '#dc2626'; }
  } finally {
    if (btn) btn.disabled = false;
  }
}

document.getElementById('sched-agent-refine-btn')?.addEventListener('click', schedAgentRefine);

function schedAgentUpdateMapsBadge(maps) {
  const badge   = document.getElementById('sched-agent-maps-badge');
  const keyInput = document.getElementById('sched-agent-maps-key');
  if (!badge) return;
  const hasKey = maps?.hasKey || maps?.status?.connected;
  if (hasKey) {
    badge.textContent = 'Maps API key saved ✓';
    badge.className   = 'cal-badge cal-badge-on';
    if (keyInput) {
      keyInput.value = '';
      keyInput.placeholder = 'Key saved — paste a new one here to replace it';
    }
  } else {
    badge.textContent = 'No Maps API — estimates only';
    badge.className   = 'cal-badge cal-badge-off';
    if (keyInput) keyInput.placeholder = 'AIza…';
  }
}

async function schedAgentSaveInstructions() {
  const btn    = document.getElementById('sched-agent-save-btn');
  const status = document.getElementById('sched-agent-save-status');
  const instr  = document.getElementById('sched-agent-instructions')?.value || '';
  if (btn) btn.disabled = true;
  if (status) { status.textContent = 'Saving…'; status.style.color = '#6b7280'; }
  try {
    const res = await fetch('/api/scheduling/agent-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instructions: instr }),
    });
    const data = await res.json();
    if (data.ok) {
      if (status) { status.textContent = 'Saved ✓'; status.style.color = '#16a34a'; }
    } else {
      if (status) { status.textContent = data.error || 'Error'; status.style.color = '#dc2626'; }
    }
  } catch (e) {
    if (status) { status.textContent = 'Save failed'; status.style.color = '#dc2626'; }
  } finally {
    if (btn) btn.disabled = false;
    setTimeout(() => { if (status) status.textContent = ''; }, 3000);
  }
}

async function schedAgentSaveMapsKey() {
  const btn    = document.getElementById('sched-agent-maps-save-btn');
  const status = document.getElementById('sched-agent-maps-status');
  const key    = document.getElementById('sched-agent-maps-key')?.value?.trim() || '';
  if (btn) btn.disabled = true;
  if (status) { status.textContent = 'Saving…'; status.style.color = '#6b7280'; }
  try {
    const res  = await fetch('/api/scheduling/maps-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ apiKey: key }),
    });
    const data = await res.json();
    if (data.ok) {
      schedAgentUpdateMapsBadge(data);
      const msg = data.status?.connected ? 'Connected ✓' : 'Saved (key not yet verified)';
      if (status) { status.textContent = msg; status.style.color = data.status?.connected ? '#16a34a' : '#f59e0b'; }
      const keyEl = document.getElementById('sched-agent-maps-key');
      if (keyEl) keyEl.value = '';
    } else {
      if (status) { status.textContent = data.error || 'Error'; status.style.color = '#dc2626'; }
    }
  } catch (e) {
    if (status) { status.textContent = 'Save failed'; status.style.color = '#dc2626'; }
  } finally {
    if (btn) btn.disabled = false;
    setTimeout(() => { if (status) status.textContent = ''; }, 4000);
  }
}

async function schedAgentTest() {
  const btn      = document.getElementById('sched-agent-test-btn');
  const resultEl = document.getElementById('sched-agent-result');
  const bodyEl   = document.getElementById('sched-agent-result-body');
  const postcode = document.getElementById('sched-agent-test-postcode')?.value?.trim();
  const service  = document.getElementById('sched-agent-test-service')?.value?.trim() || 'cleaning job';
  const duration = parseInt(document.getElementById('sched-agent-test-duration')?.value) || 120;
  const notes    = document.getElementById('sched-agent-test-notes')?.value?.trim() || '';

  if (!postcode) { showToast('Enter a job postcode first', 'error'); return; }

  if (btn) { btn.disabled = true; btn.textContent = 'Thinking…'; }
  if (resultEl) resultEl.style.display = 'none';

  try {
    const res  = await fetch('/api/scheduling/agent-recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ postcode, service, durationMins: duration, customerNotes: notes }),
    });
    const data = await res.json();

    if (!data.ok || data.error) {
      if (bodyEl) bodyEl.innerHTML = `<p style="color:#dc2626">Error: ${data.error || 'Unknown error'}</p>`;
    } else {
      if (bodyEl) bodyEl.innerHTML = schedAgentRenderResult(data);
    }
    if (resultEl) resultEl.style.display = 'block';
  } catch (e) {
    if (bodyEl) bodyEl.innerHTML = `<p style="color:#dc2626">Request failed: ${e.message}</p>`;
    if (resultEl) resultEl.style.display = 'block';
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Ask the agent'; }
  }
}

function schedAgentRenderResult(data) {
  const recs = data.recommendations || [];
  const sourceTag = data.mapsSource === 'google_maps'
    ? '<span style="color:#16a34a;font-size:11px">● Google Maps</span>'
    : '<span style="color:#f59e0b;font-size:11px">● Estimated distances</span>';

  let html = `<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
    <strong style="font-size:13px">Agent recommendations</strong>${sourceTag}
  </div>`;

  if (recs.length === 0) {
    html += '<p style="color:#6b7280;font-size:13px">No slot recommendations returned. Try connecting Google Calendar so the agent has availability data.</p>';
  }

  // Store recs globally so book buttons can access them
  window._schedAgentLastRecs = recs;

  recs.forEach((r, i) => {
    const confidenceColor = r.confidence === 'high' ? '#16a34a' : r.confidence === 'medium' ? '#f59e0b' : '#9ca3af';
    const hasSlot = r.rawSlot && r.rawSlot.start && r.rawSlot.end;
    const bookBtn = hasSlot
      ? `<button
           onclick="schedAgentTestBook(${i})"
           style="margin-top:10px;font-size:12px;padding:5px 12px;border:1px solid #7c3aed;border-radius:6px;background:#fff;color:#7c3aed;cursor:pointer;font-weight:600"
           id="sched-book-btn-${i}">
           Book this slot
         </button>`
      : '';
    html += `
    <div style="background:#f8f9fb;border:1px solid #e5e7eb;border-radius:8px;padding:14px;margin-bottom:10px">
      <div style="display:flex;align-items:flex-start;gap:10px">
        <span style="background:#7c3aed;color:#fff;border-radius:50%;width:22px;height:22px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0">${r.rank || i+1}</span>
        <div style="flex:1">
          <div style="font-weight:600;font-size:13px;margin-bottom:2px">${r.date || '—'} &nbsp;${r.timeSlot || ''}</div>
          <div style="font-size:12px;color:#374151;margin-bottom:4px">${r.engineer || ''}</div>
          ${r.travelNote ? `<div style="font-size:12px;color:#6b7280;margin-bottom:6px">🗺 ${r.travelNote}</div>` : ''}
          <div style="font-size:12px;color:#374151;line-height:1.5">${r.reasoning || ''}</div>
          ${r.caveat ? `<div style="font-size:11px;color:#f59e0b;margin-top:6px">⚠ ${r.caveat}</div>` : ''}
          ${bookBtn}
          <span id="sched-book-status-${i}" style="font-size:12px;margin-left:8px"></span>
        </div>
        <span style="font-size:11px;color:${confidenceColor};white-space:nowrap">${r.confidence || ''}</span>
      </div>
    </div>`;
  });

  if (data.agentReasoning) {
    html += `<details style="margin-top:8px">
      <summary style="font-size:12px;color:#6b7280;cursor:pointer">Agent reasoning (full)</summary>
      <p style="font-size:12px;color:#374151;margin-top:8px;line-height:1.6;white-space:pre-wrap">${data.agentReasoning}</p>
    </details>`;
  }

  if (data.caveat) {
    html += `<p style="font-size:11px;color:#f59e0b;margin-top:8px;border-top:1px solid #e5e7eb;padding-top:8px">⚠ ${data.caveat}</p>`;
  }

  return html;
}

// ── Scheduling assistant chat ────────────────────────────────────────────────
let schedAsstHistory = [];

document.getElementById('sched-asst-toggle')?.addEventListener('click', () => {
  const panel   = document.getElementById('sched-asst-panel');
  const chevron = document.getElementById('sched-asst-chevron');
  const open    = panel?.style.display !== 'none';
  if (panel)   panel.style.display   = open ? 'none' : '';
  if (chevron) chevron.style.transform = open ? '' : 'rotate(180deg)';
});

async function schedAsstSend() {
  const input  = document.getElementById('sched-asst-input');
  const btn    = document.getElementById('sched-asst-send');
  const log    = document.getElementById('sched-asst-log');
  const msg    = (input?.value || '').trim();
  if (!msg || !log) return;
  input.value = '';

  // User bubble
  const userWrap = document.createElement('div');
  userWrap.className = 'kb-bubble kb-bubble--user';
  const userSpan = document.createElement('span');
  userSpan.className = 'kb-bubble__text';
  userSpan.textContent = msg;
  userWrap.appendChild(userSpan);
  log.appendChild(userWrap);

  // Thinking bubble
  const aiWrap = document.createElement('div');
  aiWrap.className = 'kb-bubble kb-bubble--ai';
  const aiSpan = document.createElement('span');
  aiSpan.className = 'kb-bubble__text';
  aiSpan.textContent = '…';
  aiWrap.appendChild(aiSpan);
  log.appendChild(aiWrap);
  log.scrollTop = log.scrollHeight;

  schedAsstHistory.push({ role: 'user', content: msg });
  if (btn) btn.disabled = true;

  try {
    const res  = await fetch('/api/scheduling/assistant', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, history: schedAsstHistory.slice(-10) }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Request failed');
    aiSpan.textContent = data.reply;
    schedAsstHistory.push({ role: 'assistant', content: data.reply });
  } catch (err) {
    aiSpan.textContent = `Error: ${err.message}`;
  } finally {
    if (btn) btn.disabled = false;
    log.scrollTop = log.scrollHeight;
  }
}

document.getElementById('sched-asst-send')?.addEventListener('click', schedAsstSend);
document.getElementById('sched-asst-input')?.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); schedAsstSend(); }
});

async function schedAgentTestBook(recIndex) {
  const recs     = window._schedAgentLastRecs || [];
  const rec      = recs[recIndex];
  if (!rec || !rec.rawSlot) return;

  const btn      = document.getElementById(`sched-book-btn-${recIndex}`);
  const statusEl = document.getElementById(`sched-book-status-${recIndex}`);
  const customer = document.getElementById('sched-agent-test-customer')?.value?.trim() || 'Test Customer';
  const postcode = document.getElementById('sched-agent-test-postcode')?.value?.trim() || '';
  const service  = document.getElementById('sched-agent-test-service')?.value?.trim() || 'Cleaning';

  if (btn) btn.disabled = true;
  if (statusEl) { statusEl.textContent = 'Booking…'; statusEl.style.color = '#6b7280'; }

  try {
    const res  = await fetch('/api/calendar/hold', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jobSpec: {
          customerName: customer,
          service:      service,
          address:      postcode,
          postcode:     postcode,
          notes:        `Test booking via scheduling agent — ${rec.engineer}`,
        },
        slot: rec.rawSlot,
      }),
    });
    const data = await res.json();
    if (data.ok || data.eventId) {
      if (btn) { btn.textContent = 'Booked ✓'; btn.style.background = '#f0fdf4'; btn.style.color = '#16a34a'; btn.style.borderColor = '#16a34a'; }
      const linkHtml = data.eventHtmlLink
        ? ` <a href="${data.eventHtmlLink}" target="_blank" rel="noopener" style="color:#7c3aed;text-decoration:underline">Open in Google Calendar →</a>`
        : '';
      if (statusEl) { statusEl.innerHTML = `<span style="color:#16a34a">✓ Hold created!</span>${linkHtml}`; }
      showToast(`Hold created in Google Calendar — ${rec.date} ${rec.timeSlot}`, 'success');
    } else {
      throw new Error(data.error || 'Booking failed');
    }
  } catch (e) {
    if (statusEl) { statusEl.textContent = '✗ ' + e.message; statusEl.style.color = '#dc2626'; }
    if (btn) btn.disabled = false;
  }
}

async function schedLoadEngineers() {
  try {
    const [engData, calData] = await Promise.all([
      fetch('/api/scheduling/engineers').then(r => r.json()),
      fetch('/api/calendar/calendars').then(r => r.json()).catch(() => ({ calendars: [] })),
    ]);
    schedRenderEngineers(engData.engineers || [], calData.calendars || []);
  } catch (e) {
    const el = document.getElementById('sched-eng-list');
    if (el) el.innerHTML = '<p class="cal-hint" style="color:#dc2626">Could not load engineers.</p>';
  }
}

function schedRenderEngineers(engineers, cals) {
  cals = cals || [];
  const el = document.getElementById('sched-eng-list');
  if (!el) return;
  if (!engineers.length) {
    el.innerHTML = '<p class="cal-hint">No engineers configured yet. Add your first engineer below.</p>';
    return;
  }
  const regionLabel = { north: 'North', south: 'South', both: 'Both' };
  el.innerHTML = `
    <table class="sched-eng-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Home postcode</th>
          <th>Region</th>
          <th>Priority</th>
          <th>Fill ahead</th>
          <th>Calendar</th>
          <th>Status</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        ${engineers.map(eng => {
          const hasCal = !!(eng.calendarId && String(eng.calendarId).trim());
          const engIdEsc = _schedEsc(eng.id);
          let calOpts;
          if (cals.length) {
            const missingOpt = hasCal && !cals.some(c => c.id === eng.calendarId)
              ? `<option value="${_schedEsc(eng.calendarId)}" selected>${_schedEsc(eng.calendarId)} (inaccessible)</option>`
              : '';
            calOpts = `<select class="sched-eng-cal-select" onchange="schedChangeEngCalendar('${engIdEsc}', this.value)">
                <option value="" ${!hasCal ? 'selected' : ''}>— None (won&rsquo;t be booked) —</option>
                ${cals.map(c => `<option value="${_schedEsc(c.id)}" ${c.id === eng.calendarId ? 'selected' : ''}>${_schedEsc(c.summary)}${c.primary ? ' ★' : ''}</option>`).join('')}
                ${missingOpt}
              </select>`;
          } else {
            calOpts = hasCal
              ? `<span class="sched-cal-id-text" title="${_schedEsc(eng.calendarId)}">${_schedEsc(eng.calendarId)}</span>`
              : `<span class="sched-missing">Not connected</span>`;
          }
          return `
          <tr class="${eng.active && hasCal ? '' : 'sched-eng-row-muted'}">
            <td class="sched-eng-name-cell">${_schedEsc(eng.name)}</td>
            <td>${eng.homePostcode ? `<code class="cal-code-pill">${_schedEsc(eng.homePostcode)}</code>` : '<span class="sched-missing">Not set</span>'}</td>
            <td>${regionLabel[eng.region] || eng.region}</td>
            <td><span class="sched-priority-badge">P${eng.priority}</span></td>
            <td>${eng.fillAheadDays > 0 ? `${eng.fillAheadDays}d` : '—'}</td>
            <td class="sched-eng-cal-cell">${calOpts}</td>
            <td>
              <label class="sched-active-toggle" title="${eng.active ? 'AI can book this engineer' : 'AI will NOT book this engineer'}">
                <input type="checkbox" ${eng.active ? 'checked' : ''} onchange="schedToggleEngActive('${engIdEsc}', this.checked)">
                <span>${eng.active ? 'Active' : 'Off'}</span>
              </label>
            </td>
            <td class="sched-eng-actions">
              <button class="cal-btn-ghost sched-edit-btn" onclick="schedShowEngForm(${_schedEsc(JSON.stringify(JSON.stringify(eng)))})">Edit</button>
              <button class="cal-btn-ghost sched-delete-btn" onclick="schedDeleteEngineer('${engIdEsc}')">Delete</button>
            </td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>`;
}

function _schedEsc(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function schedShowEngForm(engJson) {
  const form  = document.getElementById('sched-eng-form');
  const title = document.getElementById('sched-eng-form-title');
  if (!form) return;
  const eng = engJson ? JSON.parse(engJson) : null;
  document.getElementById('sched-eng-id').value        = eng?.id || '';
  document.getElementById('sched-eng-name').value      = eng?.name || '';
  document.getElementById('sched-eng-postcode').value  = eng?.homePostcode || '';
  document.getElementById('sched-eng-region').value    = eng?.region || 'south';
  document.getElementById('sched-eng-priority').value  = eng?.priority ?? 1;
  document.getElementById('sched-eng-fillahead').value = eng?.fillAheadDays ?? 0;
  schedLoadEngCalendars(eng?.calendarId || '');
  document.getElementById('sched-eng-notes').value     = eng?.notes || '';
  document.getElementById('sched-eng-active').checked  = eng?.active !== false;
  if (title) title.textContent = eng ? `Edit — ${eng.name}` : 'Add engineer';
  document.getElementById('sched-eng-status').textContent = '';
  form.style.display = '';
  form.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function schedHideEngForm() {
  const form = document.getElementById('sched-eng-form');
  if (form) form.style.display = 'none';
}

async function schedLoadEngCalendars(selectedId) {
  const sel = document.getElementById('sched-eng-calid');
  if (!sel) return;
  sel.innerHTML = '<option value="">Loading calendars…</option>';
  try {
    const data = await fetch('/api/calendar/calendars').then(r => r.json());
    const cals = data.calendars || [];
    let opts = `<option value="" ${!selectedId ? 'selected' : ''}>— No calendar (AI won't book) —</option>`;
    opts += cals.map(c =>
      `<option value="${_schedEsc(c.id)}" ${c.id === selectedId ? 'selected' : ''}>${_schedEsc(c.summary)}${c.primary ? ' (primary)' : ''}</option>`
    ).join('');
    // If the saved calendar is no longer listed (e.g. access lost), keep it visible.
    if (selectedId && !cals.some(c => c.id === selectedId)) {
      opts += `<option value="${_schedEsc(selectedId)}" selected>${_schedEsc(selectedId)} (not accessible)</option>`;
    }
    sel.innerHTML = opts;
  } catch (e) {
    sel.innerHTML = `<option value="">— No calendar (AI won't book) —</option>` +
      (selectedId ? `<option value="${_schedEsc(selectedId)}" selected>${_schedEsc(selectedId)}</option>` : '');
  }
}

async function schedSaveEngineer() {
  const btn    = document.getElementById('sched-save-eng-btn');
  const status = document.getElementById('sched-eng-status');
  const id     = document.getElementById('sched-eng-id').value.trim();
  const payload = {
    name:          document.getElementById('sched-eng-name').value.trim(),
    homePostcode:  document.getElementById('sched-eng-postcode').value.trim().toUpperCase(),
    region:        document.getElementById('sched-eng-region').value,
    priority:      parseInt(document.getElementById('sched-eng-priority').value) || 1,
    fillAheadDays: parseInt(document.getElementById('sched-eng-fillahead').value) || 0,
    calendarId:    document.getElementById('sched-eng-calid').value.trim(),
    notes:         document.getElementById('sched-eng-notes').value.trim(),
    active:        document.getElementById('sched-eng-active').checked,
  };
  if (!payload.name) {
    if (status) { status.textContent = 'Name is required.'; status.style.color = '#dc2626'; }
    return;
  }
  if (btn) btn.disabled = true;
  if (status) { status.textContent = 'Saving…'; status.style.color = '#6b7280'; }
  try {
    const url    = id ? `/api/scheduling/engineers/${id}` : '/api/scheduling/engineers';
    const method = id ? 'PUT' : 'POST';
    const res    = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Save failed');
    schedHideEngForm();
    await schedLoadEngineers();
    showToast('Engineer saved', 'success');
  } catch (e) {
    if (status) { status.textContent = e.message; status.style.color = '#dc2626'; }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function schedDeleteEngineer(id) {
  if (!confirm('Remove this engineer?')) return;
  try {
    await fetch(`/api/scheduling/engineers/${id}`, { method: 'DELETE' });
    await schedLoadEngineers();
    showToast('Engineer removed', 'info');
  } catch (e) {
    showToast('Could not remove engineer', 'error');
  }
}

async function schedToggleEngActive(id, active) {
  try {
    await fetch(`/api/scheduling/engineers/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active: !!active }),
    });
    showToast(active ? 'Engineer enabled for AI booking' : 'Engineer disabled — AI won\'t book them', 'info');
  } catch (e) {
    showToast('Could not update engineer', 'error');
  }
  await schedLoadEngineers();
}

async function schedChangeEngCalendar(id, calendarId) {
  try {
    const res = await fetch(`/api/scheduling/engineers/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ calendarId }),
    });
    if (!res.ok) throw new Error('Save failed');
    showToast(calendarId ? 'Calendar assigned' : 'Calendar removed', 'success');
  } catch (e) {
    showToast('Could not update calendar', 'error');
  }
  await schedLoadEngineers();
}

async function schedLoadRules() {
  try {
    const data = await fetch('/api/scheduling/rules').then(r => r.json());
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
    set('sched-fill-ahead',        data.fillAheadDays          ?? 5);
    set('sched-london-km',         data.londonMaxGroupingKm    ?? 20);
    set('sched-london-urgent-km',  data.londonUrgentGroupingKm ?? 35);
    set('sched-group-km',          data.northMaxGroupingKm     ?? 60);
    set('sched-north-urgent-km',   data.northUrgentGroupingKm  ?? 90);
    const notes = document.getElementById('sched-rules-notes');
    if (notes) notes.value = data.notes ?? '';
  } catch (_) {}
}

async function schedSaveRules() {
  const btn    = document.getElementById('sched-save-rules-btn');
  const status = document.getElementById('sched-rules-status');
  const intVal = (id, def) => parseInt(document.getElementById(id)?.value) || def;
  const payload = {
    fillAheadDays:           intVal('sched-fill-ahead',       5),
    londonMaxGroupingKm:     intVal('sched-london-km',        20),
    londonUrgentGroupingKm:  intVal('sched-london-urgent-km', 35),
    northMaxGroupingKm:      intVal('sched-group-km',         60),
    northUrgentGroupingKm:   intVal('sched-north-urgent-km',  90),
    notes:                   document.getElementById('sched-rules-notes')?.value || '',
    homeReturnBonus: true,
  };
  if (btn) btn.disabled = true;
  if (status) { status.textContent = 'Saving…'; status.style.color = '#6b7280'; }
  try {
    const res  = await fetch('/api/scheduling/rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Save failed');
    if (status) { status.textContent = '✓ Saved'; status.style.color = '#16a34a'; setTimeout(() => { status.textContent = ''; }, 3000); }
    showToast('Scheduling rules saved', 'success');
  } catch (e) {
    if (status) { status.textContent = e.message; status.style.color = '#dc2626'; }
  } finally {
    if (btn) btn.disabled = false;
  }
}
