const humanParticipants = [
  {
    id: 'mira',
    name: 'Mira Chen',
    role: 'Customer Success Lead',
    color: 'linear-gradient(135deg, #fcd34d, #f59e0b)',
  },
  {
    id: 'samir',
    name: 'Samir Patel',
    role: 'Solutions Engineer',
    color: 'linear-gradient(135deg, #34d399, #10b981)',
  },
  {
    id: 'jordan',
    name: 'Jordan Ellis',
    role: 'Product Marketing',
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
let previousAutoRepliesEnabled = autoRepliesEnabled;
let aiEnabled = true;
let pendingAI = null;
let typingMessageId = null;

const messageList = document.querySelector('#messageList');
const participantList = document.querySelector('#participantList');
const personaSwitcher = document.querySelector('#aiPersonaSwitcher');
const activeName = document.querySelector('#activeName');
const activeRole = document.querySelector('#activeRole');
const messageInput = document.querySelector('#messageInput');
const sendButton = document.querySelector('#sendButton');
const globalAiToggle = document.querySelector('#globalAiToggle');
const autoToggle = document.querySelector('#autoToggle');
const aiPreview = document.querySelector('#aiPreview');
const openPreviewButton = document.querySelector('#openPreview');
const previewPanel = document.querySelector('#aiPreviewPanel');
const previewTypingIndicator = document.querySelector('#previewTypingIndicator');
const previewEditor = document.querySelector('#previewEditor');
const aiPreviewName = document.querySelector('#aiPreviewName');
const aiPreviewTone = document.querySelector('#aiPreviewTone');
const aiPreviewAvatar = document.querySelector('#aiPreviewAvatar');
const sendPreview = document.querySelector('#sendPreview');
const cancelPreview = document.querySelector('#cancelPreview');
const closePreviewButton = document.querySelector('#closePreview');

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

function formatTime(value) {
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value));
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

    const avatar = document.createElement('div');
    avatar.className = 'participant__avatar';
    avatar.style.backgroundImage = participant.color;
    avatar.textContent = participant.name
      .split(' ')
      .map((chunk) => chunk[0])
      .join('')
      .slice(0, 2)
      .toUpperCase();

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

function bubbleBackground(participant) {
  if (!participant) {
    return 'linear-gradient(135deg, #5b5fef, #3730a3)';
  }
  return participant.color ?? 'linear-gradient(135deg, #5b5fef, #3730a3)';
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

function openPreviewPanel() {
  if (!previewPanel || !openPreviewButton || openPreviewButton.disabled) {
    return;
  }

  previewPanel.classList.remove('hidden');
  if (previewEditor && !previewEditor.disabled) {
    previewEditor.focus();
  }
}

function closePreviewPanel() {
  if (!previewPanel) {
    return;
  }

  previewPanel.classList.add('hidden');
}

function resetPreview() {
  if (aiPreview) {
    aiPreview.classList.add('hidden');
  }
  if (openPreviewButton) {
    openPreviewButton.disabled = true;
  }
  if (previewPanel) {
    previewPanel.classList.add('hidden');
  }
  if (previewTypingIndicator) {
    previewTypingIndicator.style.display = 'inline-flex';
  }
  if (previewEditor) {
    previewEditor.value = '';
    previewEditor.placeholder = '';
    previewEditor.disabled = true;
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
        bubble.style.backgroundImage = outbound
          ? bubbleBackground(participant)
          : undefined;
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

  if (openPreviewButton) {
    openPreviewButton.disabled = !content;
  }

  if (previewTypingIndicator) {
    previewTypingIndicator.style.display = content ? 'none' : 'inline-flex';
  }

  if (previewEditor) {
    if (content) {
      previewEditor.disabled = false;
      previewEditor.placeholder = '';
      previewEditor.value = content;
    } else {
      previewEditor.disabled = true;
      previewEditor.placeholder = 'Generating reply…';
      previewEditor.value = '';
    }
  }

  if (!content) {
    closePreviewPanel();
  }
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
  if (!autoRepliesEnabled || !aiEnabled) {
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
  const editedText =
    previewEditor && !previewEditor.disabled
      ? previewEditor.value.trim()
      : '';
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

autoToggle.addEventListener('change', (event) => {
  autoRepliesEnabled = event.target.checked;
  previousAutoRepliesEnabled = autoRepliesEnabled;
  if (!autoRepliesEnabled) {
    cancelAIResponse();
  }
});

sendButton.addEventListener('click', sendMessage);

messageInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

sendPreview.addEventListener('click', () => {
  commitPendingAI();
});

cancelPreview.addEventListener('click', () => {
  cancelAIResponse();
});

if (openPreviewButton) {
  openPreviewButton.addEventListener('click', openPreviewPanel);
  openPreviewButton.disabled = true;
}

if (closePreviewButton) {
  closePreviewButton.addEventListener('click', () => {
    closePreviewPanel();
  });
}

if (previewEditor) {
  previewEditor.disabled = true;
  previewEditor.addEventListener('input', () => {
    if (pendingAI && !previewEditor.disabled) {
      pendingAI.text = previewEditor.value;
    }
  });
}

if (globalAiToggle) {
  aiEnabled = globalAiToggle.checked;
  if (autoToggle) {
    if (!aiEnabled) {
      previousAutoRepliesEnabled = autoRepliesEnabled;
      autoRepliesEnabled = false;
      autoToggle.checked = false;
      autoToggle.disabled = true;
    }
  }

  globalAiToggle.addEventListener('change', (event) => {
    aiEnabled = event.target.checked;
    if (autoToggle) {
      if (!aiEnabled) {
        previousAutoRepliesEnabled = autoRepliesEnabled;
        autoRepliesEnabled = false;
        autoToggle.checked = false;
        autoToggle.disabled = true;
        cancelAIResponse();
      } else {
        autoToggle.disabled = false;
        autoRepliesEnabled = previousAutoRepliesEnabled ?? true;
        autoToggle.checked = autoRepliesEnabled;
        previousAutoRepliesEnabled = autoRepliesEnabled;
      }
    } else if (!aiEnabled) {
      cancelAIResponse();
    }
  });
}

renderParticipants();
renderActiveParticipant();
renderMessages();
renderPersonaSwitcher();
updateAIPreviewPersona(getActiveAIPersona());
