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
  {
    id: 'pow',
    name: 'Pow AI',
    role: 'AI Auto-Responder',
    color: 'linear-gradient(135deg, #5b5fef, #3730a3)',
    isAI: true,
  },
];

const humanParticipants = participants.filter((p) => !p.isAI);

let activeParticipantId = humanParticipants[0].id;
let autoRepliesEnabled = true;
let pendingAI = null;

const messageList = document.querySelector('#messageList');
const participantList = document.querySelector('#participantList');
const activeName = document.querySelector('#activeName');
const activeRole = document.querySelector('#activeRole');
const messageInput = document.querySelector('#messageInput');
const sendButton = document.querySelector('#sendButton');
const autoToggle = document.querySelector('#autoToggle');
const aiPreview = document.querySelector('#aiPreview');
const typingIndicator = document.querySelector('#typingIndicator');
const previewText = document.querySelector('#previewText');
const sendPreview = document.querySelector('#sendPreview');
const cancelPreview = document.querySelector('#cancelPreview');

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
    senderId: 'pow',
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

function renderActiveParticipant() {
  const participant = participantFor(activeParticipantId);
  if (!participant) {
    return;
  }

  activeName.textContent = participant.name;
  activeRole.textContent = participant.role;
  messageInput.placeholder = `Write as ${participant.name}`;
}

function bubbleBackground(participant) {
  if (participant.isAI) {
    return 'linear-gradient(135deg, #5b5fef, #3730a3)';
  }
  return participant.color;
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

      const author = document.createElement('span');
      author.className = 'message__author';
      author.textContent = participant?.name ?? 'Unknown';

      const bubble = document.createElement('div');
      bubble.className = 'message__bubble';
      bubble.textContent = message.text;
      bubble.style.backgroundImage = outbound
        ? bubbleBackground(participant)
        : undefined;

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
  aiPreview.classList.remove('hidden');
  if (content) {
    typingIndicator.style.display = 'none';
    previewText.textContent = content;
  } else {
    typingIndicator.style.display = 'flex';
    previewText.textContent = '';
  }
}

function generateAIResponse(text) {
  const prompts = [
    {
      pattern: /slack|channel|digest/i,
      reply:
        'I can package the highlights into a twice-weekly digest for Slack with quick action items.',
    },
    {
      pattern: /report|dashboard|metrics/i,
      reply:
        'Let me propose a metrics automation that keeps the dashboard fresh and flags anomalies for follow-up.',
    },
    {
      pattern: /timeline|deadline|schedule/i,
      reply:
        'I will chart a delivery timeline with milestones and surface blockers early so we can keep momentum.',
    },
  ];

  const suggestion = prompts.find((prompt) => prompt.pattern.test(text));
  if (suggestion) {
    return suggestion.reply;
  }

  const fallbacks = [
    'Want me to summarise the customer goals and tee up the next best action?',
    'I can capture the commitments from this thread and prep a polished response.',
    'Happy to outline the automation flow and highlight how it reduces manual effort.',
  ];

  return fallbacks[Math.floor(Math.random() * fallbacks.length)];
}

function scheduleAIResponse(triggerText) {
  cancelAIResponse();
  if (!autoRepliesEnabled) {
    return;
  }

  showAIPreview();

  pendingAI = {
    text: generateAIResponse(triggerText),
    timer: null,
    previewTimer: null,
  };

  pendingAI.timer = setTimeout(() => {
    typingIndicator.style.display = 'flex';
    pendingAI.previewTimer = setTimeout(() => {
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

  messages.push({
    id: crypto.randomUUID(),
    senderId: 'pow',
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
renderMessages();
