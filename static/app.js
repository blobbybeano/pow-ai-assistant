const personas = [
  {
    id: 'carla',
    name: 'Carla Mendes',
    shortName: 'Carla',
    label: 'Weekday Concierge',
    tone:
      'Polished weekday concierge who celebrates momentum and keeps projects on track.',
    accent: '#ec4899',
    gradient: 'linear-gradient(135deg, #fbcfe8, #f472b6)',
    avatar: '/static/images/carla.svg',
    prompts: [
      {
        pattern: /slack|channel|digest/i,
        reply:
          "I'll assemble a bright Monday-ready Slack digest with quick wins and next asks.",
      },
      {
        pattern: /report|dashboard|metrics/i,
        reply:
          'Let me tee up a crisp recap with bulletproof metrics and weekday follow-through.',
      },
      {
        pattern: /timeline|deadline|schedule/i,
        reply:
          'I will anchor the schedule, spotlight blockers, and confirm the weekday owners.',
      },
    ],
    fallbacks: [
      'Want me to summarize the goals and send a celebratory weekday handoff?',
      'I can package the customer wins with crisp next actions for the team.',
      'How about I draft a polished update so everyone starts tomorrow aligned?',
    ],
    kickoff:
      'Ready to capture the wins and keep our weekday momentum buzzing. Shall I draft the follow-up?',
  },
  {
    id: 'tom',
    name: 'Tom Alvarez',
    shortName: 'Tom',
    label: 'Weekend Strategist',
    tone:
      'Relaxed weekend strategist who keeps things light while planning the next push.',
    accent: '#38bdf8',
    gradient: 'linear-gradient(135deg, #bae6fd, #38bdf8)',
    avatar: '/static/images/tom.svg',
    prompts: [
      {
        pattern: /slack|channel|digest/i,
        reply:
          'I can prep a chill weekend Slack digest so Monday kicks off with zero guesswork.',
      },
      {
        pattern: /report|dashboard|metrics/i,
        reply:
          'Let me spin up a breezy snapshot of the metrics and flag what needs eyes on Monday.',
      },
      {
        pattern: /timeline|deadline|schedule/i,
        reply:
          "I'll map the timeline, call out the weekend nudges, and line us up for an easy restart.",
      },
    ],
    fallbacks: [
      'Happy to outline weekend priorities and keep the tone easy before we ramp back up.',
      'I can sketch the next moves so we coast into Monday with confidence.',
      'Want a relaxed recap with the few things worth nudging before the week begins?',
    ],
    kickoff:
      'Weekend check-in coming right up. Want me to line up the Monday game plan for everyone?',
  },
];

const participants = [
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

const humanParticipants = [...participants];

function getDefaultPersonaId() {
  const day = new Date().getDay();
  return day === 0 || day === 6 ? 'tom' : 'carla';
}

let activeParticipantId = humanParticipants[0].id;
let activePersonaId = getDefaultPersonaId();
let autoRepliesEnabled = true;
let pendingAI = null;

const messageList = document.querySelector('#messageList');
const participantList = document.querySelector('#participantList');
const activeName = document.querySelector('#activeName');
const activeRole = document.querySelector('#activeRole');
const messageInput = document.querySelector('#messageInput');
const sendButton = document.querySelector('#sendButton');
const autoToggle = document.querySelector('#autoToggle');
const autoToggleLabel = document.querySelector('.toggle__label');
const personaSwitch = document.querySelector('#personaSwitch');
const aiPreview = document.querySelector('#aiPreview');
const aiPreviewBubble = document.querySelector('.ai-preview__bubble');
const typingIndicator = document.querySelector('#typingIndicator');
const previewText = document.querySelector('#previewText');
const previewAvatar = document.querySelector('#previewAvatar');
const previewPersonaName = document.querySelector('#previewPersonaName');
const previewPersonaTone = document.querySelector('#previewPersonaTone');
const sendPreview = document.querySelector('#sendPreview');
const cancelPreview = document.querySelector('#cancelPreview');

function personaFor(id) {
  return personas.find((persona) => persona.id === id);
}

function getActivePersona() {
  return personaFor(activePersonaId) ?? personas[0];
}

function hexToRgba(hex, alpha) {
  if (!hex) {
    return hex;
  }

  const normalized = hex.replace('#', '');
  if (normalized.length !== 6) {
    return hex;
  }

  const value = parseInt(normalized, 16);
  const r = (value >> 16) & 255;
  const g = (value >> 8) & 255;
  const b = value & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

const initialPersona = getActivePersona();

const messages = [
  {
    id: crypto.randomUUID(),
    senderId: 'mira',
    text: "Morning crew! Customer is ecstatic about yesterday's walkthrough.",
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
    senderId: 'ai',
    personaId: initialPersona.id,
    text: initialPersona.kickoff,
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
  return humanParticipants.find((participant) => participant.id === id);
}

function renderActiveParticipant() {
  const participant = participantFor(activeParticipantId);
  if (!participant) {
    return;
  }

  activeName.textContent = participant.name;
  activeRole.textContent = participant.role;
  messageInput.placeholder = `Write as ${participant.name}`;
  updateAutoToggleLabel();
}

function bubbleBackground(participant) {
  return participant.color;
}

function renderPersonaSwitch() {
  if (!personaSwitch) {
    return;
  }

  personaSwitch.innerHTML = '';

  personas.forEach((persona) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'persona-switch__option';
    button.dataset.personaId = persona.id;

    if (persona.id === activePersonaId) {
      button.classList.add('is-active');
    }

    button.style.setProperty('--persona-accent', persona.accent);

    const avatar = document.createElement('img');
    avatar.src = persona.avatar;
    avatar.alt = `${persona.name} avatar`;

    const meta = document.createElement('div');
    meta.className = 'persona-switch__meta';

    const name = document.createElement('span');
    name.className = 'persona-switch__name';
    name.textContent = persona.shortName;

    const description = document.createElement('span');
    description.className = 'persona-switch__description';
    description.textContent = persona.label;

    meta.append(name, description);
    button.append(avatar, meta);
    personaSwitch.append(button);
  });
}

function updateAutoToggleLabel() {
  if (!autoToggleLabel) {
    return;
  }

  const persona = getActivePersona();
  autoToggleLabel.textContent = `Auto ${persona.shortName} replies`;
}

function updatePreviewPersona(persona = pendingAI
  ? personaFor(pendingAI.personaId)
  : getActivePersona()) {
  if (!persona) {
    return;
  }

  if (previewAvatar) {
    previewAvatar.src = persona.avatar;
    previewAvatar.alt = `${persona.name} avatar`;
  }

  if (previewPersonaName) {
    previewPersonaName.textContent = `${persona.name} · ${persona.label}`;
  }

  if (previewPersonaTone) {
    previewPersonaTone.textContent = persona.tone;
  }

  aiPreview?.style.setProperty('--ai-accent', persona.accent);
  if (aiPreviewBubble) {
    aiPreviewBubble.style.background = hexToRgba(persona.accent, 0.12);
  }
}

function renderMessages() {
  messageList.innerHTML = '';

  messages
    .sort((a, b) => a.timestamp - b.timestamp)
    .forEach((message) => {
      const isAI = message.senderId === 'ai';
      const participant = isAI
        ? null
        : participantFor(message.senderId);
      const persona = isAI ? personaFor(message.personaId) ?? getActivePersona() : null;

      const item = document.createElement('article');
      const outbound = message.senderId === activeParticipantId;
      item.className = 'message';
      item.classList.add(outbound ? 'is-outbound' : 'is-inbound');

      if (isAI) {
        item.classList.add('is-ai');
        if (persona?.accent) {
          item.style.setProperty('--message-accent', persona.accent);
        }
      }

      const author = document.createElement('span');
      author.className = 'message__author';
      if (isAI) {
        author.textContent = persona
          ? `${persona.name} · ${persona.label}`
          : 'Pow AI';
        if (persona?.accent) {
          author.style.color = persona.accent;
        }
      } else {
        author.textContent = participant?.name ?? 'Unknown';
      }

      const bubble = document.createElement('div');
      bubble.className = 'message__bubble';
      bubble.textContent = message.text;

      if (outbound && participant) {
        bubble.style.backgroundImage = bubbleBackground(participant);
      } else if (isAI && persona) {
        bubble.style.background = hexToRgba(persona.accent, 0.12);
        bubble.style.borderLeft = `4px solid ${persona.accent}`;
        bubble.style.color = '#1f2937';
      }

      const timestamp = document.createElement('span');
      timestamp.className = 'message__time';
      timestamp.textContent = formatTime(message.timestamp);

      item.append(author, bubble, timestamp);
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
  if (!pendingAI) {
    aiPreview.classList.add('hidden');
    typingIndicator.style.display = 'flex';
    previewText.textContent = '';
    return;
  }

  clearTimeout(pendingAI.timer);
  clearTimeout(pendingAI.previewTimer);
  pendingAI = null;
  aiPreview.classList.add('hidden');
  typingIndicator.style.display = 'flex';
  previewText.textContent = '';
}

function showAIPreview(content) {
  updatePreviewPersona();
  aiPreview.classList.remove('hidden');
  if (content) {
    typingIndicator.style.display = 'none';
    previewText.textContent = content;
  } else {
    typingIndicator.style.display = 'flex';
    previewText.textContent = '';
  }
}

function generateAIResponse(text, persona) {
  const prompts = persona?.prompts ?? [];
  const suggestion = prompts.find((prompt) => prompt.pattern.test(text));
  if (suggestion) {
    return suggestion.reply;
  }

  const fallbacks = persona?.fallbacks ?? [];
  if (fallbacks.length > 0) {
    return fallbacks[Math.floor(Math.random() * fallbacks.length)];
  }

  const defaultFallbacks = [
    'Want me to summarise the customer goals and tee up the next best action?',
    'I can capture the commitments from this thread and prep a polished response.',
    'Happy to outline the automation flow and highlight how it reduces manual effort.',
  ];

  return defaultFallbacks[Math.floor(Math.random() * defaultFallbacks.length)];
}

function scheduleAIResponse(triggerText) {
  cancelAIResponse();
  if (!autoRepliesEnabled) {
    return;
  }

  const persona = getActivePersona();

  pendingAI = {
    personaId: persona.id,
    triggerText,
    text: generateAIResponse(triggerText, persona),
    timer: null,
    previewTimer: null,
  };

  showAIPreview();

  pendingAI.timer = setTimeout(() => {
    typingIndicator.style.display = 'flex';
    pendingAI.previewTimer = setTimeout(() => {
      showAIPreview(pendingAI.text);
    }, 700);
  }, 400);
}

function setActivePersona(id) {
  if (activePersonaId === id) {
    return;
  }

  activePersonaId = id;
  renderPersonaSwitch();
  updateAutoToggleLabel();

  if (pendingAI) {
    const persona = getActivePersona();
    pendingAI.personaId = persona.id;
    pendingAI.text = generateAIResponse(pendingAI.triggerText, persona);
    updatePreviewPersona(persona);
    if (typingIndicator.style.display === 'none') {
      previewText.textContent = pendingAI.text;
    }
  } else {
    updatePreviewPersona();
  }
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

  messages.push({
    id: crypto.randomUUID(),
    senderId: 'ai',
    personaId: pendingAI.personaId,
    text: pendingAI.text,
    timestamp: Date.now(),
  });

  cancelAIResponse();
  renderMessages();
}

participantList.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-id]');
  if (!button) {
    return;
  }
  setActiveParticipant(button.dataset.id);
});

if (personaSwitch) {
  personaSwitch.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-persona-id]');
    if (!button) {
      return;
    }
    setActivePersona(button.dataset.personaId);
  });
}

autoToggle.addEventListener('change', (event) => {
  autoRepliesEnabled = event.target.checked;
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

renderParticipants();
renderActiveParticipant();
renderPersonaSwitch();
renderMessages();
updatePreviewPersona();
