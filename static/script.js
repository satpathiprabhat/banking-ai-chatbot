document.addEventListener("DOMContentLoaded", function () {

  // 1) Check for token on page load — if not found, redirect to login
  const token = localStorage.getItem('token');
  if (!token) {
    window.location = '/static/login.html';
    return;
  }

  const sendBtn = document.getElementById('send-btn');
  const userInput = document.getElementById('user-input');
  let chatHistory = [];

  sendBtn.addEventListener('click', sendMessage);

  // Multi-line input: send on Ctrl+Enter
  userInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      sendMessage();
      e.preventDefault();
    }
  });

  const profileBtn = document.getElementById('profile-btn');
const dropdown = document.getElementById('dropdown-menu');
const themeBtn = document.getElementById('theme-toggle');

// Set initial theme label
const initTheme = document.body.getAttribute('data-theme') || 'light';
themeBtn.textContent = initTheme === 'light' ? '🌙 Dark Mode' : '☀️ Light Mode';

// Profile menu toggle
profileBtn.addEventListener('click', () => {
  dropdown.classList.toggle('hidden');
});

// Theme toggle (now inside dropdown)
themeBtn.addEventListener('click', () => {
  const current = document.body.getAttribute('data-theme') || 'light';
  if (current === 'light') {
    document.body.setAttribute('data-theme', 'dark');
    themeBtn.textContent = '☀️ Light Mode';
  } else {
    document.body.setAttribute('data-theme', 'light');
    themeBtn.textContent = '🌙 Dark Mode';
  }
});

// Logout
document.getElementById('logout-btn').addEventListener('click', () => {
  localStorage.removeItem('token');
  window.location.href = '/static/login.html';
});

// Close dropdown if clicked outside
document.addEventListener('click', (event) => {
  if (!profileBtn.contains(event.target) && !dropdown.contains(event.target)) {
    dropdown.classList.add('hidden');
  }
});


  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // Format assistant text into bullet style with bold label
  function formatAssistantText(text) {
    const lines = text.split('\n');
    let html = '';
    lines.forEach(line => {
      const trimmed = line.trim();

      // * Bullets
      if (trimmed.startsWith('*')) {
        let cleanLine = trimmed.replace(/^\*\s*/, '').replace(/\*\*/g, '');
        const parts = cleanLine.split(':');
        const title = escapeHtml(parts[0].trim());
        const rest = escapeHtml(parts.slice(1).join(':').trim());
        html += `<p>&bull; <strong>${title}</strong>${rest ? ': ' + rest : ''}</p>`;
      }
      // Numbered list
      else if (/^\d+\./.test(trimmed)) {
        let cleanLine = trimmed.replace(/^\d+\.\s*/, '').replace(/\*\*/g, '');
        const parts = cleanLine.split(':');
        const title = escapeHtml(parts[0].trim());
        const rest = escapeHtml(parts.slice(1).join(':').trim());
        html += `<p>&bull; <strong>${title}</strong>${rest ? ': ' + rest : ''}</p>`;
      }
      else {
        html += `<p>${escapeHtml(trimmed.replace(/\*\*/g, ''))}</p>`;
      }
    });
    return html;
  }

  async function sendMessage() {
    const text = userInput.value.trim();
    if (!text) return;

    sendBtn.disabled = true;   // disable to avoid double submit
    appendMessage('user', text);
    userInput.value = '';

    const typingId = appendTypingIndicator();

    // Greeting fallback
    const lower = text.toLowerCase();
    if (["hi", "hello", "hey"].includes(lower)) {
      const msg = "Hello! How can I assist you with your banking needs today?";
      updateMessage(typingId, msg);
      chatHistory.push({ role: "assistant", content: msg });
      sendBtn.disabled = false;
      return;
    }

    try {
      const res = await fetch('/assist/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          session_id: "sess-001",
          customer_id: "cust-001",
          query: text,
          history: chatHistory.slice(0, -1)  // exclude current user msg; backend receives it via req.query
        })
      });
      
      const data = await res.json();

      // Friendly fallback if any technical/error-like text
      if (
        !data.message ||
        data.message.startsWith('[Error') ||
        data.message.toLowerCase().includes('quota') ||
        data.message.toLowerCase().includes('technical') ||
        data.message.toLowerCase().includes('429')
      ) {
        data.message = "Sorry, I'm currently facing technical difficulties. Please try again later.";
      }

      await new Promise(resolve => setTimeout(resolve, 800));
      updateMessage(typingId, data.message || '[No response]');
      chatHistory.push({ role: "assistant", content: data.message || '[No response]' });

    } catch (err) {
      await new Promise(resolve => setTimeout(resolve, 800));
      updateMessage(typingId, "Sorry, I'm currently facing technical difficulties.");
      chatHistory.push({ role: "assistant", content: "Error communicating." });
    }

    sendBtn.disabled = false;
  }

  function appendMessage(role, text, temp = false) {
    const chatWindow = document.getElementById('chat-window');
    const div = document.createElement('div');
    div.classList.add('message');
    div.classList.add(role === 'user' ? 'user-message' : 'assistant-message');

    const now = new Date();
    const time = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const safeText = role === 'user' ? escapeHtml(text) : text;
    div.innerHTML = `<span class="text">${safeText}</span>
                     <span class="timestamp">${time}</span>`;

    chatWindow.appendChild(div);
    chatHistory.push({ role: role, content: text });
    scrollToBottom();

    if (temp) {
      const id = Date.now() + Math.random();
      div.dataset.id = id;
      return id;
    }
  }

  function appendTypingIndicator() {
    const chatWindow = document.getElementById('chat-window');
    const div = document.createElement('div');
    div.classList.add('message', 'assistant-message', 'typing-indicator');
    div.innerHTML = `
      <span class="dot"></span>
      <span class="dot"></span>
      <span class="dot"></span>
    `;
    chatWindow.appendChild(div);
    scrollToBottom();
    const id = Date.now() + Math.random();
    div.dataset.id = id;
    return id;
  }

  function updateMessage(id, finalText) {
    const div = document.querySelector(`[data-id="${id}"]`);
    if (div) {
      div.classList.remove('typing-indicator');
      div.classList.add('assistant-message');
      const styled = formatAssistantText(finalText);
      const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      div.innerHTML = `<span class="text">${styled}</span>
                       <span class="timestamp">${time}</span>`;
      scrollToBottom();
    }
  }

  function scrollToBottom() {
    const chatWindow = document.getElementById('chat-window');
    setTimeout(() => {
      chatWindow.scrollTop = chatWindow.scrollHeight;
    }, 0);
  }

});