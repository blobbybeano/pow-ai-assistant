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

let sessionId = crypto.randomUUID();
let currentParams = null;
let activeUploads = [];

async function init() {
  try {
    const res = await fetch('/api/params');
    if (!res.ok) throw new Error('Unable to load parameters');
    currentParams = await res.json();
    populateParams(currentParams);
  } catch (err) {
    showToast(err.message, 'error');
  }
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
  const group = document.createElement('div');
  group.className = `message-group ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = role === 'customer' ? 'C' : 'AI';

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

  addMessageBubble('customer', messageInput.value.trim() || '📷 Photos sent', activeUploads);

  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('message', messageInput.value.trim());
  activeUploads.forEach((file) => formData.append('images[]', file, file.name));

  setFormDisabled(true);
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
    const aiText = data.ai?.text || 'No response';
    addMessageBubble('ai', aiText, data.images || []);
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    setFormDisabled(false);
    resetForm();
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

toggleParamsBtn.addEventListener('click', () => {
  paramsPanel.classList.toggle('active');
});

closeParamsBtn.addEventListener('click', () => {
  paramsPanel.classList.remove('active');
});

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
    limits: {
      max_image_size_mb: Number(limitImageSize.value),
    },
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
  if (event.key === 'Escape') closeLightbox();
});

function closeLightbox() {
  lightbox.classList.remove('active');
  lightbox.setAttribute('aria-hidden', 'true');
}

init();
