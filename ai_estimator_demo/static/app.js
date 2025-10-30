const chatStream = document.getElementById('chat-stream');
const chatForm = document.getElementById('chat-form');
const messageField = document.getElementById('message');
const filePicker = document.getElementById('file-picker');
const attachmentPreview = document.getElementById('attachment-preview');
const toastContainer = document.getElementById('toast-container');
const lightbox = document.getElementById('lightbox');
const lightboxImg = document.getElementById('lightbox-image');
const lightboxClose = document.getElementById('lightbox-close');
const toggleParams = document.getElementById('toggle-params');
const paramsPanel = document.getElementById('params-panel');
const paramsForm = document.getElementById('params-form');
const closeParams = document.getElementById('close-params');

let sessionId = null;
let pendingFiles = [];
let currentParams = window.__INITIAL_PARAMS__ || {};
const servicePresets = window.__SERVICE_PRESETS__ || {};

function formatTimestamp(date = new Date()) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function createToast(message, type = 'success', timeout = 4000) {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('fade-out');
    setTimeout(() => toast.remove(), 350);
  }, timeout);
}

function clearAttachments() {
  pendingFiles.forEach(f => f.preview && URL.revokeObjectURL(f.preview));
  pendingFiles = [];
  attachmentPreview.innerHTML = '';
  filePicker.value = '';
}

function renderAttachmentPreview() {
  attachmentPreview.innerHTML = '';
  pendingFiles.forEach((file, index) => {
    if (!file.preview) {
      file.preview = URL.createObjectURL(file);
    }
    const chip = document.createElement('div');
    chip.className = 'attachment-chip';
    chip.innerHTML = `<span>${file.name}</span><button type="button" aria-label="Remove attachment">×</button>`;
    chip.querySelector('button').addEventListener('click', () => {
      URL.revokeObjectURL(file.preview);
      pendingFiles.splice(index, 1);
      renderAttachmentPreview();
    });
    attachmentPreview.appendChild(chip);
  });
}

function formatText(text = '') {
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  return escaped.replace(/\n/g, '<br>');
}

function appendMessage({ role, text, images = [], meta = {} }) {
  const row = document.createElement('div');
  row.className = `message-row ${role}`;

  const avatar = document.createElement('div');
  avatar.className = `avatar ${role}`;
  avatar.textContent = role === 'user' ? 'CU' : 'AI';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  if (text) {
    bubble.innerHTML = formatText(text);
  }

  if (images.length) {
    const grid = document.createElement('div');
    grid.className = 'image-grid';
    images.forEach(img => {
      const imageEl = document.createElement('img');
      imageEl.src = img.preview || img.url;
      imageEl.alt = img.name || 'attachment';
      imageEl.addEventListener('click', () => openLightbox(img.url || img.preview));
      grid.appendChild(imageEl);
    });
    bubble.appendChild(grid);
  }

  const metaLine = document.createElement('div');
  metaLine.className = 'message-meta';
  metaLine.innerHTML = `<span>${role === 'user' ? 'Customer' : 'PowWash AI'}</span><span>${formatTimestamp(meta.timestamp || new Date())}</span>`;
  bubble.appendChild(metaLine);

  if (role === 'ai' && meta.json) {
    const status = document.createElement('div');
    status.className = 'status-line';
    status.innerHTML = `Confidence: ${meta.json.confidence ?? 'n/a'} • Service: ${meta.json.service}`;
    bubble.appendChild(status);
  }

  row.appendChild(avatar);
  row.appendChild(bubble);
  chatStream.appendChild(row);
  chatStream.scrollTo({ top: chatStream.scrollHeight, behavior: 'smooth' });
}

function openLightbox(src) {
  lightboxImg.src = src;
  lightbox.hidden = false;
}

function closeLightbox() {
  lightbox.hidden = true;
  lightboxImg.src = '';
}

lightboxClose.addEventListener('click', closeLightbox);
lightbox.addEventListener('click', (event) => {
  if (event.target === lightbox) {
    closeLightbox();
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && !lightbox.hidden) {
    closeLightbox();
  }
});

function addFiles(fileList) {
  const maxSizeMb = currentParams.max_image_size_mb || 12;
  Array.from(fileList).forEach(file => {
    const sizeMb = file.size / (1024 * 1024);
    if (sizeMb > maxSizeMb) {
      createToast(`${file.name} exceeds ${maxSizeMb}MB limit`, 'error');
      return;
    }
    pendingFiles.push(file);
  });
  renderAttachmentPreview();
}

filePicker.addEventListener('change', (event) => {
  addFiles(event.target.files);
});

const chatPanel = document.querySelector('.chat-panel');
chatPanel.addEventListener('dragover', (event) => {
  event.preventDefault();
  chatPanel.classList.add('dragging');
});
chatPanel.addEventListener('dragleave', () => chatPanel.classList.remove('dragging'));
chatPanel.addEventListener('drop', (event) => {
  event.preventDefault();
  chatPanel.classList.remove('dragging');
  if (event.dataTransfer?.files?.length) {
    addFiles(event.dataTransfer.files);
  }
});

messageField.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

async function sendMessage(event) {
  event.preventDefault();
  const text = messageField.value.trim();
  if (!text && pendingFiles.length === 0) {
    createToast('Please type a message or attach at least one image.', 'error');
    return;
  }

  const now = new Date();
  const previewImages = pendingFiles.map(file => ({ preview: file.preview || URL.createObjectURL(file), name: file.name }));
  appendMessage({ role: 'user', text, images: previewImages, meta: { timestamp: now } });

  const formData = new FormData();
  formData.append('message', text);
  if (sessionId) {
    formData.append('session_id', sessionId);
  }
  pendingFiles.forEach(file => {
    formData.append('images[]', file, file.name);
  });

  setSendingState(true);

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      body: formData
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      createToast(data.error || 'Something went wrong while contacting the estimator.', 'error');
      setSendingState(false);
      return;
    }
    const data = await response.json();
    sessionId = data.session_id || sessionId;
    const aiMeta = {
      timestamp: new Date(),
      json: data.ai?.json,
      format: currentParams.response_format,
    };
    let aiText = data.ai?.text || 'No response received.';
    const aiImages = (data.images || []).map(img => ({ url: img.url, name: img.name }));
    appendMessage({ role: 'ai', text: aiText, images: aiImages, meta: aiMeta });
    if (data.ai?.json) {
      const details = document.createElement('pre');
      details.className = 'json-dump';
      details.textContent = JSON.stringify(data.ai.json, null, 2);
      chatStream.lastElementChild.querySelector('.bubble').appendChild(details);
    }
  } catch (error) {
    console.error(error);
    createToast('Network error. Please try again.', 'error');
  } finally {
    setSendingState(false);
    messageField.value = '';
    clearAttachments();
  }
}

function setSendingState(isSending) {
  const sendBtn = chatForm.querySelector('.send-btn');
  if (isSending) {
    sendBtn.disabled = true;
    sendBtn.textContent = 'Sending…';
  } else {
    sendBtn.disabled = false;
    sendBtn.textContent = 'Send';
  }
}

chatForm.addEventListener('submit', sendMessage);

function populateParamsForm(params) {
  paramsForm.querySelector('#system-prompt').value = params.system_prompt || '';
  paramsForm.querySelector('#service-preset').value = params.service_preset || 'driveway';
  paramsForm.querySelector('#response-format').value = params.response_format || 'json+explanation';
  paramsForm.querySelector('#base-callout').value = params.pricing?.base_callout ?? '';
  paramsForm.querySelector('#rate-per-m2').value = params.pricing?.rate_per_m2 ?? '';
  paramsForm.querySelector('#mult-heavy').value = params.pricing?.multipliers?.heavy_soiling ?? '';
  paramsForm.querySelector('#mult-oil').value = params.pricing?.multipliers?.oil_stains ?? '';
  paramsForm.querySelector('#mult-algae').value = params.pricing?.multipliers?.algae_biocide ?? '';
  paramsForm.querySelector('#mult-access').value = params.pricing?.multipliers?.access_difficulty ?? '';
  paramsForm.querySelector('#max-photo-requests').value = params.coverage_policy?.max_additional_photo_requests ?? '';
  paramsForm.querySelector('#confidence-threshold').value = params.coverage_policy?.confidence_threshold ?? '';
  paramsForm.querySelector('#max-image-size').value = params.max_image_size_mb ?? '';
}

populateParamsForm(currentParams);

async function handleParamsSubmit(event) {
  event.preventDefault();
  const payload = {
    system_prompt: paramsForm.querySelector('#system-prompt').value,
    service_preset: paramsForm.querySelector('#service-preset').value,
    response_format: paramsForm.querySelector('#response-format').value,
    pricing: {
      base_callout: parseFloat(paramsForm.querySelector('#base-callout').value || '0'),
      rate_per_m2: parseFloat(paramsForm.querySelector('#rate-per-m2').value || '0'),
      multipliers: {
        heavy_soiling: parseFloat(paramsForm.querySelector('#mult-heavy').value || '1'),
        oil_stains: parseFloat(paramsForm.querySelector('#mult-oil').value || '1'),
        algae_biocide: parseFloat(paramsForm.querySelector('#mult-algae').value || '1'),
        access_difficulty: parseFloat(paramsForm.querySelector('#mult-access').value || '1'),
      }
    },
    coverage_policy: {
      max_additional_photo_requests: parseInt(paramsForm.querySelector('#max-photo-requests').value || '1', 10),
      confidence_threshold: parseFloat(paramsForm.querySelector('#confidence-threshold').value || '0.7')
    },
    max_image_size_mb: parseFloat(paramsForm.querySelector('#max-image-size').value || '12')
  };

  try {
    const response = await fetch('/api/params', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!response.ok) {
      createToast('Failed to update parameters.', 'error');
      return;
    }
    const data = await response.json();
    currentParams = data.params;
    createToast('Parameters updated.', 'success');
  } catch (error) {
    console.error(error);
    createToast('Network error while updating parameters.', 'error');
  }
}

paramsForm.addEventListener('submit', handleParamsSubmit);

toggleParams.addEventListener('click', () => {
  const expanded = toggleParams.getAttribute('aria-expanded') === 'true';
  toggleParams.setAttribute('aria-expanded', String(!expanded));
  paramsPanel.classList.toggle('open', !expanded);
});

closeParams.addEventListener('click', () => {
  paramsPanel.classList.remove('open');
  toggleParams.setAttribute('aria-expanded', 'false');
});

window.addEventListener('resize', () => {
  if (window.innerWidth > 1100) {
    paramsPanel.classList.remove('open');
    toggleParams.setAttribute('aria-expanded', 'false');
  }
});

(async function hydrateParams() {
  try {
    const response = await fetch('/api/params');
    if (!response.ok) return;
    const data = await response.json();
    currentParams = data;
    populateParamsForm(currentParams);
  } catch (error) {
    console.warn('Unable to fetch params on load', error);
  }
})();
