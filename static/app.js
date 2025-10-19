const humanParticipants = [
  {
    id: 'mira',
    name: 'Mira Chen',
    role: 'Customer Success Lead',
    avatar: '',
    color: 'linear-gradient(135deg, #fcd34d, #f59e0b)',
  },
  {
    id: 'samir',
    name: 'Samir Patel',
    role: 'Solutions Engineer',
    avatar: '',
    color: 'linear-gradient(135deg, #34d399, #10b981)',
  },
  {
    id: 'jordan',
    name: 'Jordan Ellis',
    role: 'Product Marketing',
    avatar: '',
    color: 'linear-gradient(135deg, #a855f7, #6366f1)',
  },
];

const aiPersonas = [
  {
    id: 'carla',
    name: 'Carla Vega',
    shortName: 'Carla',
    role: 'Weekday AI Strategist',
    tone: 'Weekday strategist · Warm & proactive',
    color: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
    avatar: '/static/carla.svg',
    isAI: true,
    prompts: [
      {
        pattern: /slack|channel|digest/i,
        reply:
          'Carla here — I can package weekday highlights into a Slack digest with crisp follow-up prompts.',
      },
      {
        pattern: /report|dashboard|metrics/i,
        reply:
          'Carla here — I will map the reporting flow, keep dashboards fresh, and flag weekday anomalies early.',
      },
      {
        pattern: /timeline|deadline|schedule/i,
        reply:
          'Carla here — I will outline the delivery schedule, spotlight dependencies, and set weekday check-ins.',
      },
    ],
    fallbacks: [
      'Carla here — I can recap the goals, assign weekday owners, and prep the next best response.',
      'Carla here — happy to polish a weekday-ready reply that keeps momentum and clarifies next actions.',
      'Carla here — I’ll organise the updates, confirm commitments, and draft a warm weekday follow-up.',
    ],
  },
  {
    id: 'tom',
    name: 'Tom Alvarez',
    shortName: 'Tom',
    role: 'Weekend AI Concierge',
    tone: 'Weekend concierge · Relaxed & reliable',
    color: 'linear-gradient(135deg, #34d399, #10b981)',
    avatar: '/static/tom.svg',
    isAI: true,
    prompts: [
      {
        pattern: /slack|channel|digest/i,
        reply:
          'Tom here — I’ll spin up a light weekend digest for Slack so Monday starts with zero surprises.',
      },
      {
        pattern: /report|dashboard|metrics/i,
        reply:
          'Tom here — I can queue the metrics refresh, add context notes, and keep the weekend vibe calm.',
      },
      {
        pattern: /timeline|deadline|schedule/i,
        reply:
          'Tom here — I’ll map the timeline, note weekend blockers, and tee up a smooth Monday kickoff.',
      },
    ],
    fallbacks: [
      'Tom here — glad to draft a relaxed weekend reply that keeps the plan humming.',
      'Tom here — I can summarise the thread, point out easy wins, and leave Monday with a head start.',
      'Tom here — let me capture the asks and prep a weekend-friendly update with clear next moves.',
    ],
  },
];

const participants = [...humanParticipants, ...aiPersonas];

function getDefaultAIPersonaId() {
  const day = new Date().getDay();
  return day === 0 || day === 6 ? 'tom' : 'carla';
}

let activeParticipantId = humanParticipants[0].id;
let activeAIPersonaId = getDefaultAIPersonaId();
let autoRepliesEnabled = true;
let inboxAiEnabled = true;
const conversationSettings = new Map();
let pendingAI = null;
let typingMessageId = null;
let isPreviewEditing = false;

const messageList = document.querySelector('#messageList');
const participantList = document.querySelector('#participantList');
const personaSwitcher = document.querySelector('#aiPersonaSwitcher');
const activeName = document.querySelector('#activeName');
const activeRole = document.querySelector('#activeRole');
const messageInput = document.querySelector('#messageInput');
const sendButton = document.querySelector('#sendButton');
const inboxAiToggle = document.querySelector('#inboxAiToggle');
const autoToggle = document.querySelector('#autoToggle');
const aiPreview = document.querySelector('#aiPreview');
const previewTypingIndicator = document.querySelector('#previewTypingIndicator');
const previewDisplay = document.querySelector('#previewDisplay');
const previewEditor = document.querySelector('#previewEditor');
const aiPreviewName = document.querySelector('#aiPreviewName');
const aiPreviewTone = document.querySelector('#aiPreviewTone');
const aiPreviewAvatar = document.querySelector('#aiPreviewAvatar');
const editPreviewButton = document.querySelector('#editPreview');
const sendPreview = document.querySelector('#sendPreview');
const cancelPreview = document.querySelector('#cancelPreview');
const settingsButton = document.querySelector('#settingsButton');
const settingsOverlay = document.querySelector('#settingsOverlay');
const closeSettingsButton = document.querySelector('#closeSettings');
const settingsForm = document.querySelector('#settingsForm');

const initialAIPersonaId = activeAIPersonaId;

const messages = [
  {
    id: crypto.randomUUID(),
    senderId: 'mira',
    text: 'Morning crew! Customer is ecstatic about yesterday\'s walkthrough.',
    timestamp: new Date().setHours(9, 12),
  },
  {
    id: crypto.randomUUID(),
    senderId: 'samir',
    text: 'Love it. They asked if we can wire the metrics digest straight into Slack.',
    timestamp: new Date().setHours(9, 14),
  },
  {
    id: crypto.randomUUID(),
    senderId: initialAIPersonaId,
    text: 'I can draft the automation proposal. Want me to highlight weekly trend callouts?',
    timestamp: new Date().setHours(9, 15),
  },
  {
    id: crypto.randomUUID(),
    senderId: 'jordan',
    text: 'Yes please! Also underline the part where reporting quality improves without extra lift.',
    timestamp: new Date().setHours(9, 16),
  },
];

ensureConversationSettings(activeParticipantId);

function formatTime(value) {
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value));
}

function getInitials(name) {
  return name
    .split(' ')
    .map((chunk) => chunk[0] ?? '')
    .join('')
    .slice(0, 2)
    .toUpperCase();
}

function renderParticipants() {
  participantList.innerHTML = '';

  humanParticipants.forEach((participant) => {
    const button = document.createElement('button');
    button.className = 'participant';
    button.type = 'button';
    button.dataset.id = participant.id;

    if (participant.id === activeParticipantId) {
      button.classList.add('is-active');
    }

    let avatar;
    if (participant.avatar) {
      avatar = document.createElement('img');
      avatar.className = 'participant__avatar-image';
      avatar.src = participant.avatar;
      avatar.alt = `${participant.name} avatar`;
    } else {
      avatar = document.createElement('div');
      avatar.className = 'participant__avatar';
      if (participant.color) {
        avatar.style.backgroundImage = participant.color;
      }
      avatar.textContent = getInitials(participant.name);
    }

    const meta = document.createElement('div');
    meta.className = 'participant__meta';

    const name = document.createElement('span');
    name.className = 'participant__name';
    name.textContent = participant.name;

    const role = document.createElement('span');
    role.className = 'participant__role';
    role.textContent = participant.role;

    meta.append(name, role);
    button.append(avatar, meta);
    participantList.append(button);
  });
}

function participantFor(id) {
  return participants.find((participant) => participant.id === id);
}

function ensureConversationSettings(participantId) {
  if (!participantId) {
    return { autoReplies: inboxAiEnabled };
  }
  if (!conversationSettings.has(participantId)) {
    conversationSettings.set(participantId, {
      autoReplies: inboxAiEnabled,
    });
  }
  return conversationSettings.get(participantId);
}

function aiPersonaFor(id) {
  return aiPersonas.find((persona) => persona.id === id);
}

function getActiveAIPersona() {
  return aiPersonaFor(activeAIPersonaId) ?? aiPersonas[0];
}

function renderActiveParticipant() {
  const participant = participantFor(activeParticipantId);
  if (!participant) {
    return;
  }

  activeName.textContent = participant.name;
  activeRole.textContent = participant.role;
  messageInput.placeholder = `Write as ${participant.name}`;
}

function renderPersonaSwitcher() {
  if (!personaSwitcher) {
    return;
  }

  personaSwitcher.innerHTML = '';

  const label = document.createElement('span');
  label.className = 'persona-switcher__label';
  label.textContent = 'AI persona';

  const options = document.createElement('div');
  options.className = 'persona-switcher__options';

  aiPersonas.forEach((persona) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.id = persona.id;
    button.className = 'persona-switcher__option';
    if (persona.id === activeAIPersonaId) {
      button.classList.add('is-active');
    }

    const avatar = document.createElement('img');
    avatar.className = 'persona-switcher__avatar';
    avatar.src = persona.avatar;
    avatar.alt = persona.name;

    const labelText = document.createElement('span');
    labelText.textContent = persona.shortName ?? persona.name;

    button.append(avatar, labelText);
    options.append(button);
  });

  personaSwitcher.append(label, options);
}

function applyAutoToggleState() {
  const settings = ensureConversationSettings(activeParticipantId);
  const storedPreference = settings?.autoReplies ?? inboxAiEnabled;
  autoRepliesEnabled = inboxAiEnabled ? storedPreference : false;

  if (autoToggle) {
    if (!inboxAiEnabled) {
      autoToggle.checked = false;
      autoToggle.disabled = true;
    } else {
      autoToggle.disabled = false;
      autoToggle.checked = autoRepliesEnabled;
    }
  }
}

function updateInboxAiToggle() {
  if (!inboxAiToggle) {
    return;
  }

  inboxAiToggle.classList.toggle('is-off', !inboxAiEnabled);
  inboxAiToggle.setAttribute('aria-pressed', String(inboxAiEnabled));
  const status = inboxAiToggle.querySelector('.ai-inbox-toggle__status');
  if (status) {
    status.textContent = `Inbox AI: ${inboxAiEnabled ? 'On' : 'Off'}`;
  }
}

function setInboxAiEnabled(enabled) {
  if (inboxAiEnabled === enabled) {
    return;
  }
  inboxAiEnabled = enabled;
  updateInboxAiToggle();
  applyAutoToggleState();

  if (!inboxAiEnabled) {
    cancelAIResponse();
  }
}

function updateAIPreviewPersona(persona) {
  if (!persona) {
    return;
  }
  if (aiPreviewName) {
    aiPreviewName.textContent = persona.name;
  }
  if (aiPreviewTone) {
    aiPreviewTone.textContent = persona.tone;
  }
  if (aiPreviewAvatar) {
    aiPreviewAvatar.src = persona.avatar;
    aiPreviewAvatar.alt = persona.name;
  }
}

function resetPreview() {
  if (aiPreview) {
    aiPreview.classList.add('hidden');
  }
  if (previewTypingIndicator) {
    previewTypingIndicator.style.display = 'inline-flex';
  }
  if (previewEditor) {
    previewEditor.value = '';
    previewEditor.disabled = true;
    previewEditor.classList.add('ai-preview__editor-hidden');
  }
  if (previewDisplay) {
    previewDisplay.textContent = '';
    previewDisplay.classList.remove('is-hidden');
  }
  if (editPreviewButton) {
    editPreviewButton.disabled = true;
    editPreviewButton.textContent = 'Edit';
  }
  if (sendPreview) {
    sendPreview.disabled = true;
  }
  isPreviewEditing = false;
}

function setPreviewEditing(editing) {
  const hasText = Boolean(
    (previewEditor?.value ?? '').trim() || (previewDisplay?.textContent ?? '').trim()
  );
  const effectiveEditing = editing && hasText;
  isPreviewEditing = effectiveEditing;

  if (aiPreview) {
    aiPreview.classList.toggle('is-editing', effectiveEditing);
  }

  if (previewDisplay) {
    const shouldHide = effectiveEditing || !hasText;
    previewDisplay.classList.toggle('is-hidden', shouldHide);
  }

  if (previewEditor) {
    previewEditor.disabled = !effectiveEditing;
    previewEditor.classList.toggle('ai-preview__editor-hidden', !effectiveEditing);
    if (effectiveEditing) {
      previewEditor.focus();
      const length = previewEditor.value.length;
      previewEditor.setSelectionRange(length, length);
    }
  }

  if (editPreviewButton) {
    editPreviewButton.textContent = effectiveEditing ? 'Done editing' : 'Edit';
  }
}

function addTypingIndicator(persona) {
  const source = persona ?? getActiveAIPersona();
  if (!source) {
    return;
  }

  removeTypingIndicator();

  typingMessageId = crypto.randomUUID();
  messages.push({
    id: typingMessageId,
    senderId: source.id,
    isTyping: true,
    timestamp: Date.now(),
  });
}

function removeTypingIndicator() {
  if (!typingMessageId) {
    return;
  }

  const index = messages.findIndex((message) => message.id === typingMessageId);
  if (index >= 0) {
    messages.splice(index, 1);
  }
  typingMessageId = null;
}

function setActiveAIPersona(id) {
  const persona = aiPersonaFor(id);
  if (!persona || activeAIPersonaId === id) {
    return;
  }

  const triggerText = pendingAI?.triggerText;
  const shouldReschedule = Boolean(pendingAI) && Boolean(triggerText) && autoRepliesEnabled;

  if (pendingAI) {
    cancelAIResponse();
  }

  activeAIPersonaId = id;
  renderPersonaSwitcher();
  updateAIPreviewPersona(persona);

  if (shouldReschedule && triggerText) {
    scheduleAIResponse(triggerText);
  }

  renderMessages();
}

function renderMessages() {
  messageList.innerHTML = '';

  messages
    .sort((a, b) => a.timestamp - b.timestamp)
    .forEach((message) => {
      const participant = participantFor(message.senderId);
      const item = document.createElement('article');
      const outbound = message.senderId === activeParticipantId;
      item.className = 'message';
      item.classList.add(outbound ? 'is-outbound' : 'is-inbound');

      if (message.isTyping) {
        item.classList.add('is-typing');
      }

      if (participant?.isAI && !message.isTyping) {
        item.classList.add('is-ai');
        const personaHeader = document.createElement('div');
        personaHeader.className = 'message__persona';

        const avatar = document.createElement('img');
        avatar.className = 'message__persona-avatar';
        avatar.src = participant.avatar ?? aiPersonas[0].avatar;
        avatar.alt = participant?.name ?? 'AI assistant';

        const meta = document.createElement('div');
        meta.className = 'message__persona-meta';

        const name = document.createElement('span');
        name.className = 'message__persona-name';
        name.textContent = participant?.name ?? 'Pow AI';

        meta.append(name);

        if (participant?.tone) {
          const tone = document.createElement('span');
          tone.className = 'message__persona-tone';
          tone.textContent = participant.tone;
          meta.append(tone);
        }

        personaHeader.append(avatar, meta);
        item.append(personaHeader);
      } else if (!message.isTyping) {
        const author = document.createElement('span');
        author.className = 'message__author';
        author.textContent = participant?.name ?? 'Unknown';
        item.append(author);
      }

      const bubble = document.createElement('div');
      bubble.className = 'message__bubble';
      if (message.isTyping) {
        bubble.classList.add('message__bubble--typing');
        bubble.innerHTML = '<span></span><span></span><span></span>';
      } else {
        bubble.textContent = message.text;
        bubble.style.backgroundImage = 'none';
        bubble.style.backgroundColor = outbound
          ? 'var(--bubble-outbound)'
          : 'var(--bubble-inbound)';
      }

      const timestamp = document.createElement('span');
      timestamp.className = 'message__time';
      timestamp.textContent = message.isTyping
        ? ''
        : formatTime(message.timestamp);

      item.append(bubble, timestamp);
      messageList.append(item);
    });

  messageList.scrollTop = messageList.scrollHeight;
}

function setActiveParticipant(id) {
  if (activeParticipantId === id) {
    return;
  }

  activeParticipantId = id;
  ensureConversationSettings(activeParticipantId);
  applyAutoToggleState();
  renderParticipants();
  renderActiveParticipant();
  renderMessages();
  cancelAIResponse();
}

function cancelAIResponse() {
  const hadPending = Boolean(pendingAI) || Boolean(typingMessageId);

  if (pendingAI) {
    clearTimeout(pendingAI.timer);
    clearTimeout(pendingAI.previewTimer);
    pendingAI = null;
  }

  removeTypingIndicator();
  resetPreview();
  updateAIPreviewPersona(getActiveAIPersona());

  if (hadPending) {
    renderMessages();
  }
}

function showAIPreview(content) {
  if (!aiPreview) {
    return;
  }

  aiPreview.classList.remove('hidden');
  updateAIPreviewPersona(getActiveAIPersona());

  const hasContent = Boolean(content);

  if (previewTypingIndicator) {
    previewTypingIndicator.style.display = hasContent ? 'none' : 'inline-flex';
  }

  if (previewDisplay) {
    previewDisplay.textContent = content ?? '';
  }

  if (previewEditor) {
    previewEditor.value = content ?? '';
  }

  if (sendPreview) {
    sendPreview.disabled = !hasContent;
  }

  if (editPreviewButton) {
    editPreviewButton.disabled = !hasContent;
  }

  if (!hasContent) {
    setPreviewEditing(false);
    return;
  }

  setPreviewEditing(isPreviewEditing);
}

function generateAIResponse(text, persona) {
  const prompts = persona?.prompts ?? [];

  const suggestion = prompts.find((prompt) => prompt.pattern.test(text));
  if (suggestion) {
    return suggestion.reply;
  }

  const fallbacks = persona?.fallbacks?.length
    ? persona.fallbacks
    : [
        'Want me to summarise the customer goals and tee up the next best action?',
        'I can capture the commitments from this thread and prep a polished response.',
        'Happy to outline the automation flow and highlight how it reduces manual effort.',
      ];

  return fallbacks[Math.floor(Math.random() * fallbacks.length)];
}

function scheduleAIResponse(triggerText) {
  cancelAIResponse();
  if (!autoRepliesEnabled || !inboxAiEnabled) {
    return;
  }

  const persona = getActiveAIPersona();
  if (!persona) {
    return;
  }

  updateAIPreviewPersona(persona);
  showAIPreview();
  addTypingIndicator(persona);
  renderMessages();

  pendingAI = {
    text: generateAIResponse(triggerText, persona),
    personaId: persona.id,
    triggerText,
    timer: null,
    previewTimer: null,
  };

  pendingAI.timer = setTimeout(() => {
    if (!pendingAI) {
      return;
    }

    if (previewTypingIndicator) {
      previewTypingIndicator.style.display = 'inline-flex';
    }

    pendingAI.previewTimer = setTimeout(() => {
      if (!pendingAI) {
        return;
      }
      showAIPreview(pendingAI.text);
    }, 700);
  }, 400);
}

function sendMessage() {
  const text = messageInput.value.trim();
  if (!text) {
    return;
  }

  messages.push({
    id: crypto.randomUUID(),
    senderId: activeParticipantId,
    text,
    timestamp: Date.now(),
  });

  messageInput.value = '';
  renderMessages();
  scheduleAIResponse(text);
}

function commitPendingAI() {
  if (!pendingAI) {
    return;
  }

  clearTimeout(pendingAI.timer);
  clearTimeout(pendingAI.previewTimer);

  const personaId = pendingAI.personaId ?? getActiveAIPersona().id;
  const editedText = previewEditor ? previewEditor.value.trim() : '';
  const textToSend = editedText || pendingAI.text;
  if (!textToSend) {
    return;
  }

  messages.push({
    id: crypto.randomUUID(),
    senderId: personaId,
    text: textToSend,
    timestamp: Date.now(),
  });

  pendingAI = null;
  removeTypingIndicator();
  resetPreview();
  updateAIPreviewPersona(getActiveAIPersona());
  renderMessages();
}

function createSettingsField(labelText, name, value, placeholder = '') {
  const field = document.createElement('label');
  field.className = 'settings-form__field';
  field.htmlFor = name;

  const labelSpan = document.createElement('span');
  labelSpan.textContent = labelText;

  const input = document.createElement('input');
  input.type = 'text';
  input.id = name;
  input.name = name;
  input.value = value ?? '';
  if (placeholder) {
    input.placeholder = placeholder;
  }

  field.append(labelSpan, input);
  return field;
}

function renderSettingsForm() {
  if (!settingsForm) {
    return;
  }

  settingsForm.innerHTML = '';

  humanParticipants.forEach((participant) => {
    const section = document.createElement('section');
    section.className = 'settings-form__section';

    const header = document.createElement('div');
    header.className = 'settings-form__header';

    const avatar = document.createElement('div');
    avatar.className = 'settings-form__avatar';
    if (participant.avatar) {
      const img = document.createElement('img');
      img.className = 'participant__avatar-image';
      img.src = participant.avatar;
      img.alt = `${participant.name} avatar`;
      avatar.append(img);
    } else {
      avatar.textContent = getInitials(participant.name);
    }

    const headerMeta = document.createElement('div');
    headerMeta.className = 'settings-form__header-meta';
    const title = document.createElement('strong');
    title.textContent = participant.name;
    const role = document.createElement('span');
    role.textContent = participant.role;
    headerMeta.append(title, role);

    header.append(avatar, headerMeta);
    section.append(header);

    section.append(
      createSettingsField('Display name', `${participant.id}-name`, participant.name)
    );
    section.append(
      createSettingsField('Role', `${participant.id}-role`, participant.role)
    );
    section.append(
      createSettingsField(
        'Profile image URL',
        `${participant.id}-avatar`,
        participant.avatar ?? '',
        'https://example.com/avatar.png'
      )
    );

    settingsForm.append(section);
  });

  const actions = document.createElement('div');
  actions.className = 'settings-form__actions';

  const cancel = document.createElement('button');
  cancel.type = 'button';
  cancel.className = 'btn';
  cancel.textContent = 'Cancel';
  cancel.addEventListener('click', () => {
    closeSettings();
  });

  const submit = document.createElement('button');
  submit.type = 'submit';
  submit.className = 'btn btn--primary';
  submit.textContent = 'Save changes';

  actions.append(cancel, submit);
  settingsForm.append(actions);
}

function openSettings() {
  if (!settingsOverlay || !settingsForm) {
    return;
  }

  renderSettingsForm();
  settingsOverlay.classList.add('is-open');
  settingsOverlay.setAttribute('aria-hidden', 'false');
  if (settingsButton) {
    settingsButton.setAttribute('aria-expanded', 'true');
  }
  const firstInput = settingsForm.querySelector('input');
  firstInput?.focus();
}

function closeSettings() {
  if (!settingsOverlay) {
    return;
  }

  settingsOverlay.classList.remove('is-open');
  settingsOverlay.setAttribute('aria-hidden', 'true');
  if (settingsButton) {
    settingsButton.setAttribute('aria-expanded', 'false');
    settingsButton.focus();
  }
}

function handleSettingsSubmit(event) {
  event.preventDefault();
  if (!settingsForm) {
    return;
  }

  const formData = new FormData(settingsForm);

  humanParticipants.forEach((participant) => {
    const name = (formData.get(`${participant.id}-name`) ?? '').toString().trim();
    const role = (formData.get(`${participant.id}-role`) ?? '').toString().trim();
    const avatar = (formData.get(`${participant.id}-avatar`) ?? '').toString().trim();

    if (name) {
      participant.name = name;
    }
    if (role) {
      participant.role = role;
    }
    participant.avatar = avatar || '';
  });

  renderParticipants();
  renderActiveParticipant();
  renderMessages();
  closeSettings();
}

participantList.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-id]');
  if (!button) {
    return;
  }
  setActiveParticipant(button.dataset.id);
});

if (personaSwitcher) {
  personaSwitcher.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-id]');
    if (!button) {
      return;
    }
    setActiveAIPersona(button.dataset.id);
  });
}

if (autoToggle) {
  autoToggle.addEventListener('change', (event) => {
    autoRepliesEnabled = event.target.checked;
    const settings = ensureConversationSettings(activeParticipantId);
    settings.autoReplies = autoRepliesEnabled;
    if (!autoRepliesEnabled) {
      cancelAIResponse();
    }
  });
}

sendButton.addEventListener('click', sendMessage);

messageInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

if (sendPreview) {
  sendPreview.disabled = true;
  sendPreview.addEventListener('click', () => {
    commitPendingAI();
  });
}

if (cancelPreview) {
  cancelPreview.addEventListener('click', () => {
    cancelAIResponse();
  });
}

if (editPreviewButton) {
  editPreviewButton.disabled = true;
  editPreviewButton.addEventListener('click', () => {
    setPreviewEditing(!isPreviewEditing);
  });
}

if (previewEditor) {
  previewEditor.disabled = true;
  previewEditor.classList.add('ai-preview__editor-hidden');
  previewEditor.addEventListener('input', () => {
    if (pendingAI && !previewEditor.disabled) {
      pendingAI.text = previewEditor.value;
    }
    if (previewDisplay) {
      previewDisplay.textContent = previewEditor.value;
    }
    if (sendPreview) {
      sendPreview.disabled = !previewEditor.value.trim();
    }
  });
}

if (inboxAiToggle) {
  updateInboxAiToggle();
  inboxAiToggle.addEventListener('click', () => {
    setInboxAiEnabled(!inboxAiEnabled);
  });
}

if (settingsOverlay) {
  settingsOverlay.setAttribute('aria-hidden', 'true');
}

if (settingsForm) {
  settingsForm.addEventListener('submit', handleSettingsSubmit);
}

if (settingsButton) {
  settingsButton.addEventListener('click', () => {
    openSettings();
  });
}

if (closeSettingsButton) {
  closeSettingsButton.addEventListener('click', () => {
    closeSettings();
  });
}

if (settingsOverlay) {
  settingsOverlay.addEventListener('click', (event) => {
    if (event.target === settingsOverlay) {
      closeSettings();
    }
  });
}

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && settingsOverlay?.classList.contains('is-open')) {
    closeSettings();
  }
});

applyAutoToggleState();
updateInboxAiToggle();

renderParticipants();
renderActiveParticipant();
renderMessages();
renderPersonaSwitcher();
updateAIPreviewPersona(getActiveAIPersona());
