/* ==========================================================================
   Personal AI Chat Web App - frontend logic (vanilla JS, no framework)

   There is no API key anywhere in this file. The browser only ever talks to
   our own FastAPI backend, which holds the key server-side.

   Sections:
     1. state + helpers        6. voice input (speech to text)
     2. markdown rendering     7. voice output (text to speech)
     3. message rendering      8. long-term memory panel
     4. conversations          9. input UX / sidebar / theme
     5. file attachments      10. boot
   ========================================================================== */

(() => {
  "use strict";

  // ============================================================ 1. state
  const state = {
    conversationId: null,   // null = a brand new, unsaved chat
    conversations: [],
    documents: [],
    sending: false,
    streaming: true,        // falls back to /api/chat if streaming fails
    speaking: false,
    listening: false,
    uploadInfo: { max_mb: 10, extensions: [] },
  };

  const settings = {
    speak: localStorage.getItem("voiceSpeak") === "1",
    autoSend: localStorage.getItem("voiceAutoSend") === "1",
  };

  const $ = (id) => document.getElementById(id);
  const el = {
    sidebar: $("sidebar"), overlay: $("overlay"), chatList: $("chatList"),
    chat: $("chat"), welcome: $("welcome"), input: $("input"), send: $("btnSend"),
    newChat: $("btnNewChat"), menu: $("btnMenu"), closeSidebar: $("btnCloseSidebar"),
    theme: $("btnTheme"), themeTop: $("btnThemeTop"), themeIcon: $("themeIcon"),
    themeLabel: $("themeLabel"), headerTitle: $("headerTitle"),
    charCount: $("charCount"), modelBadge: $("modelBadge"), toast: $("toast"),
    hint: $("hint"),
    // attachments
    attach: $("btnAttach"), fileInput: $("fileInput"), attachments: $("attachments"),
    // voice
    mic: $("btnMic"), speaker: $("btnSpeaker"),
    optSpeak: $("optSpeak"), optAutoSend: $("optAutoSend"),
    voiceNote: $("voiceSupportNote"),
    // memory
    memoryBtn: $("btnMemory"), memoryModal: $("memoryModal"),
    memoryList: $("memoryList"), memoryInput: $("memoryInput"),
    memoryCount: $("memoryCount"), addMemory: $("btnAddMemory"),
    clearMemory: $("btnClearMemory"), closeMemory: $("btnCloseMemory"),
    doneMemory: $("btnDoneMemory"),
  };

  const MAX_CHARS = parseInt(el.input.getAttribute("maxlength"), 10) || 10000;

  function toast(message, ms = 2200) {
    el.toast.textContent = message;
    el.toast.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { el.toast.hidden = true; }, ms);
  }

  async function api(path, options = {}) {
    const opts = { ...options };
    if (!(opts.body instanceof FormData)) {
      opts.headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
    }
    const res = await fetch(path, opts);
    let data = null;
    try { data = await res.json(); } catch (_) { /* empty body */ }
    if (res.status === 401) {
      // Session expired or password set: go and sign in.
      window.location.href = "/login";
      throw new Error("Please sign in.");
    }
    if (!res.ok) {
      throw new Error((data && data.detail) || "Request failed. Please try again.");
    }
    return data;
  }

  // ---------------------------------------------------------- action cards
  /** A completed action, e.g. "Opened YouTube". */
  function addActionCard(detail, result) {
    const card = document.createElement("div");
    card.className = "action-card done";
    card.innerHTML =
      '<div class="action-head"><span class="action-icon">⚡</span>' +
      `<span class="action-title"></span></div>`;
    card.querySelector(".action-title").textContent = detail;

    if (result) {
      const body = document.createElement("pre");
      body.className = "action-result";
      body.textContent = result.length > 1200 ? result.slice(0, 1200) + "…" : result;
      card.append(body);
    }
    el.chat.append(card);
    showWelcome(false);
    scrollToBottom(true);
  }

  /** A risky action waiting for the user to allow it. */
  function addConfirmCard(token, detail) {
    const card = document.createElement("div");
    card.className = "action-card confirm";

    const head = document.createElement("div");
    head.className = "action-head";
    head.innerHTML = '<span class="action-icon">⚠️</span>';
    const title = document.createElement("span");
    title.className = "action-title";
    title.textContent = detail;
    head.append(title);

    const note = document.createElement("div");
    note.className = "action-note";
    note.textContent = "Nova needs your permission before doing this.";

    const buttons = document.createElement("div");
    buttons.className = "action-buttons";

    const yes = document.createElement("button");
    yes.className = "btn-primary";
    yes.textContent = "Confirm";

    const no = document.createElement("button");
    no.className = "btn-danger";
    no.textContent = "Cancel";

    const finish = (text, cls) => {
      buttons.remove();
      note.textContent = text;
      card.classList.remove("confirm");
      card.classList.add(cls);
    };

    yes.addEventListener("click", async () => {
      yes.disabled = true; no.disabled = true;
      yes.textContent = "Working...";
      try {
        const out = await api("/api/actions/confirm", {
          method: "POST",
          body: JSON.stringify({ token }),
        });
        finish(out.result || "Done.", "done");
        speak(out.result || "Done.");
      } catch (err) {
        finish(err.message, "failed");
      }
    });

    no.addEventListener("click", async () => {
      yes.disabled = true; no.disabled = true;
      try {
        await api("/api/actions/cancel", {
          method: "POST",
          body: JSON.stringify({ token }),
        });
      } catch (_) { /* nothing to undo */ }
      finish("Cancelled — I did not do it.", "failed");
    });

    buttons.append(yes, no);
    card.append(head, note, buttons);
    el.chat.append(card);
    showWelcome(false);
    scrollToBottom(true);
  }

  function scrollToBottom(force = false) {
    const nearBottom =
      el.chat.scrollHeight - el.chat.scrollTop - el.chat.clientHeight < 160;
    if (force || nearBottom) el.chat.scrollTop = el.chat.scrollHeight;
  }

  function formatBytes(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
    return `${(n / 1024 / 1024).toFixed(1)} MB`;
  }

  // ============================================================ 2. markdown
  if (window.marked) {
    marked.setOptions({ breaks: true, gfm: true, headerIds: false, mangle: false });
  }

  function renderMarkdown(target, text) {
    const raw = window.marked ? marked.parse(text || "") : escapeHtml(text || "");
    target.innerHTML = window.DOMPurify
      ? DOMPurify.sanitize(raw, { USE_PROFILES: { html: true } })
      : raw;
    enhanceCodeBlocks(target);
  }

  function escapeHtml(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  function enhanceCodeBlocks(scope) {
    scope.querySelectorAll("pre > code").forEach((code) => {
      const pre = code.parentElement;
      if (pre.parentElement && pre.parentElement.classList.contains("code-block")) return;

      const langClass = [...code.classList].find((c) => c.startsWith("language-"));
      const lang = langClass ? langClass.replace("language-", "") : "code";

      const block = document.createElement("div");
      block.className = "code-block";
      const head = document.createElement("div");
      head.className = "code-head";
      const label = document.createElement("span");
      label.textContent = lang;
      const copy = document.createElement("button");
      copy.className = "copy-btn";
      copy.textContent = "📋 Copy";
      copy.addEventListener("click", () => copyText(code.textContent, copy));
      head.append(label, copy);

      pre.replaceWith(block);
      block.append(head, pre);

      if (window.hljs) {
        try { hljs.highlightElement(code); } catch (_) { /* ignore */ }
      }
    });
  }

  async function copyText(text, button) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
      }
      const original = button.textContent;
      button.textContent = "✅ Copied!";
      setTimeout(() => { button.textContent = original; }, 1400);
    } catch (_) {
      toast("Could not copy to clipboard.");
    }
  }

  // ============================================================ 3. rendering
  function showWelcome(show) {
    el.welcome.hidden = !show;
    el.chat.hidden = show;
  }

  function addMessage(role, content, { markdown = role === "assistant" } = {}) {
    const wrap = document.createElement("div");
    wrap.className = `msg ${role}`;

    const roleEl = document.createElement("div");
    roleEl.className = "msg-role";
    roleEl.textContent = role === "user" ? "You" : role === "error" ? "Error" : "AI";

    const body = document.createElement("div");
    body.className = "msg-body";
    if (markdown) renderMarkdown(body, content);
    else body.textContent = content;

    wrap.append(roleEl, body);

    if (role === "assistant") {
      body.dataset.raw = content;
      const actions = document.createElement("div");
      actions.className = "msg-actions";

      const copy = document.createElement("button");
      copy.className = "copy-btn";
      copy.textContent = "📋 Copy";
      copy.addEventListener("click", () => copyText(body.dataset.raw || content, copy));

      const say = document.createElement("button");
      say.className = "copy-btn";
      say.textContent = "🔊 Read";
      say.addEventListener("click", () => speak(body.dataset.raw || content, true));

      actions.append(copy);
      if (window.speechSynthesis) actions.append(say);
      wrap.append(actions);
    }

    el.chat.append(wrap);
    showWelcome(false);
    scrollToBottom(true);
    return { wrap, body };
  }

  function addThinking() {
    const wrap = document.createElement("div");
    wrap.className = "msg assistant";
    wrap.innerHTML =
      '<div class="msg-role">AI</div>' +
      '<div class="msg-body"><span class="dots"><i></i><i></i><i></i></span></div>';
    el.chat.append(wrap);
    showWelcome(false);
    scrollToBottom(true);
    return { wrap, body: wrap.querySelector(".msg-body") };
  }

  function renderSidebar() {
    el.chatList.innerHTML = "";
    if (!state.conversations.length) {
      el.chatList.innerHTML = '<div class="empty-hint">No chats yet.</div>';
      return;
    }
    state.conversations.forEach((c) => {
      const item = document.createElement("div");
      item.className = "chat-item" + (c.id === state.conversationId ? " active" : "");
      item.dataset.id = c.id;

      const title = document.createElement("div");
      title.className = "chat-item-title";
      title.textContent = c.title || "New Chat";
      title.title = c.title || "New Chat";

      const del = document.createElement("button");
      del.className = "chat-item-del";
      del.textContent = "🗑";
      del.title = "Delete chat";
      del.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteConversation(c.id, c.title);
      });

      item.append(title, del);
      item.addEventListener("click", () => openConversation(c.id));
      el.chatList.append(item);
    });
  }

  // ============================================================ 4. conversations
  async function loadConversations() {
    try {
      state.conversations = await api("/api/conversations");
      renderSidebar();
    } catch (err) {
      console.error(err);
      toast("Could not load your chats.");
    }
  }

  async function openConversation(id) {
    try {
      const data = await api(`/api/conversations/${id}`);
      state.conversationId = data.id;
      el.headerTitle.textContent = data.title || "New Chat";
      el.chat.innerHTML = "";

      if (!data.messages.length) showWelcome(true);
      else {
        data.messages.forEach((m) => addMessage(m.role, m.content));
        showWelcome(false);
      }
      renderSidebar();
      await loadDocuments();
      closeSidebar();
      el.input.focus();
    } catch (err) {
      toast(err.message);
      await loadConversations();
    }
  }

  function newChat() {
    // Nothing is written to the database until the first message or upload.
    state.conversationId = null;
    state.documents = [];
    renderAttachments();
    el.chat.innerHTML = "";
    el.headerTitle.textContent = document.title;
    showWelcome(true);
    renderSidebar();
    closeSidebar();
    el.input.focus();
  }

  async function deleteConversation(id, title) {
    if (!confirm(`Delete "${title || "this chat"}"? This cannot be undone.`)) return;
    try {
      await api(`/api/conversations/${id}`, { method: "DELETE" });
      const wasActive = state.conversationId === id;
      await loadConversations();
      if (wasActive) {
        if (state.conversations.length) await openConversation(state.conversations[0].id);
        else newChat();
      }
      toast("Chat deleted.");
    } catch (err) {
      toast(err.message);
    }
  }

  /** Make sure a conversation row exists (needed before attaching a file). */
  async function ensureConversation() {
    if (state.conversationId !== null) return state.conversationId;
    const created = await api("/api/conversations", {
      method: "POST",
      body: JSON.stringify({ title: "New Chat" }),
    });
    state.conversationId = created.id;
    await loadConversations();
    return state.conversationId;
  }

  // ============================================================ 5. attachments
  function renderAttachments() {
    el.attachments.innerHTML = "";
    if (!state.documents.length) {
      el.attachments.hidden = true;
      return;
    }
    el.attachments.hidden = false;
    state.documents.forEach((doc) => {
      const chip = document.createElement("div");
      chip.className = "chip";

      const name = document.createElement("span");
      name.className = "chip-name";
      name.textContent = `📄 ${doc.filename}`;
      name.title = `${formatBytes(doc.size_bytes)} · ${doc.text_chars} characters extracted`;

      const remove = document.createElement("button");
      remove.className = "chip-x";
      remove.textContent = "✕";
      remove.title = "Remove this file";
      remove.addEventListener("click", () => removeDocument(doc.id));

      chip.append(name, remove);
      el.attachments.append(chip);
    });
  }

  async function loadDocuments() {
    if (state.conversationId === null) {
      state.documents = [];
      renderAttachments();
      return;
    }
    try {
      state.documents = await api(
        `/api/conversations/${state.conversationId}/documents`
      );
    } catch (_) {
      state.documents = [];
    }
    renderAttachments();
  }

  async function removeDocument(id) {
    try {
      await api(`/api/documents/${id}`, { method: "DELETE" });
      state.documents = state.documents.filter((d) => d.id !== id);
      renderAttachments();
      toast("File removed.");
    } catch (err) {
      toast(err.message);
    }
  }

  async function uploadFile(file) {
    if (!file) return;
    const limit = state.uploadInfo.max_mb * 1024 * 1024;
    if (file.size > limit) {
      toast(`That file is too big. The limit is ${state.uploadInfo.max_mb} MB.`);
      return;
    }

    el.attach.classList.add("busy");
    el.attach.textContent = "⏳";
    try {
      const conversationId = await ensureConversation();
      const form = new FormData();
      form.append("file", file);
      form.append("conversation_id", conversationId);

      const doc = await api("/api/upload", { method: "POST", body: form });
      state.documents.unshift(doc);
      renderAttachments();
      toast(`Attached ${doc.filename} — ${doc.text_chars.toLocaleString()} characters read.`);
      if (!el.input.value.trim()) {
        el.input.value = `Summarise ${doc.filename} for me.`;
        autosize();
        updateCharCount();
        el.send.disabled = false;
      }
    } catch (err) {
      toast(err.message, 5000);
    } finally {
      el.attach.classList.remove("busy");
      el.attach.textContent = "📎";
      el.fileInput.value = "";
    }
  }

  el.attach.addEventListener("click", () => el.fileInput.click());
  el.fileInput.addEventListener("change", (e) => uploadFile(e.target.files[0]));

  // Drag and drop anywhere on the chat area.
  ["dragover", "drop"].forEach((type) => {
    document.addEventListener(type, (e) => {
      e.preventDefault();
      if (type === "drop" && e.dataTransfer.files.length) {
        uploadFile(e.dataTransfer.files[0]);
      }
    });
  });

  // ============================================================ 6. voice input
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let voiceBaseText = "";

  function setupRecognition() {
    if (!SpeechRecognition) return null;
    const rec = new SpeechRecognition();
    rec.lang = navigator.language || "en-US";
    rec.interimResults = true;
    rec.continuous = false;
    rec.maxAlternatives = 1;

    rec.onstart = () => {
      state.listening = true;
      el.mic.classList.add("listening");
      el.mic.textContent = "⏹";
      el.hint.textContent = "Listening… speak now";
    };

    rec.onresult = (event) => {
      let transcript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      el.input.value = (voiceBaseText + " " + transcript).trim();
      autosize();
      updateCharCount();
      el.send.disabled = !el.input.value.trim();
    };

    rec.onerror = (event) => {
      const map = {
        "not-allowed": "Microphone access was blocked. Allow it in your browser settings.",
        "service-not-allowed": "Microphone needs a secure connection (https) or localhost.",
        "no-speech": "I didn't hear anything. Try again.",
        "audio-capture": "No microphone was found.",
        network: "Speech recognition needs an internet connection.",
      };
      toast(map[event.error] || `Voice input failed (${event.error}).`, 4000);
    };

    rec.onend = () => {
      state.listening = false;
      el.mic.classList.remove("listening");
      el.mic.textContent = "🎤";
      el.hint.textContent = "Enter to send · Shift + Enter for a new line";
      if (settings.autoSend && el.input.value.trim() && !state.sending) {
        sendMessage();
      }
    };
    return rec;
  }

  function toggleListening() {
    if (!SpeechRecognition) {
      toast("Voice input needs Chrome, Edge, or Safari.", 4000);
      return;
    }
    if (!recognition) recognition = setupRecognition();
    if (state.listening) {
      recognition.stop();
      return;
    }
    stopSpeaking();                 // don't listen to ourselves
    voiceBaseText = el.input.value.trim();
    try {
      recognition.start();
    } catch (_) {
      /* start() throws if already running - ignore */
    }
  }

  el.mic.addEventListener("click", toggleListening);

  // ============================================================ 7. voice output
  /** Turn markdown into something worth listening to. */
  function speechText(markdown) {
    let text = markdown || "";
    text = text.replace(/```[\s\S]*?```/g, " (code block omitted) ");
    text = text.replace(/`([^`]+)`/g, "$1");
    text = text.replace(/!\[[^\]]*\]\([^)]*\)/g, " ");
    text = text.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");
    text = text.replace(/^\s{0,3}#{1,6}\s*/gm, "");
    text = text.replace(/(\*\*|__|\*|_|~~|>)/g, "");
    text = text.replace(/^\s*[-+*]\s+/gm, "");
    text = text.replace(/\|/g, " ");
    text = text.replace(/\s{2,}/g, " ").trim();
    return text.slice(0, 4000);   // keep utterances sane
  }

  function stopSpeaking() {
    if (window.speechSynthesis && state.speaking) {
      window.speechSynthesis.cancel();
      state.speaking = false;
      updateSpeakerButton();
    }
  }

  function speak(markdown, force = false) {
    if (!window.speechSynthesis) {
      if (force) toast("This browser cannot speak text.");
      return;
    }
    if (!force && !settings.speak) return;

    const text = speechText(markdown);
    if (!text) return;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = navigator.language || "en-US";
    utterance.rate = 1.02;

    const preferred = window.speechSynthesis
      .getVoices()
      .find((v) => v.lang && v.lang.startsWith(utterance.lang.slice(0, 2)));
    if (preferred) utterance.voice = preferred;

    utterance.onstart = () => { state.speaking = true; updateSpeakerButton(); };
    utterance.onend = () => { state.speaking = false; updateSpeakerButton(); };
    utterance.onerror = () => { state.speaking = false; updateSpeakerButton(); };

    window.speechSynthesis.speak(utterance);
  }

  function updateSpeakerButton() {
    if (state.speaking) {
      el.speaker.textContent = "⏹";
      el.speaker.title = "Stop speaking";
      el.speaker.classList.add("active");
      return;
    }
    el.speaker.textContent = settings.speak ? "🔊" : "🔈";
    el.speaker.classList.toggle("active", settings.speak);
    el.speaker.title = settings.speak
      ? "Spoken replies are ON - click to turn off"
      : "Spoken replies are OFF - click to turn on";
  }

  el.speaker.addEventListener("click", () => {
    if (state.speaking) { stopSpeaking(); return; }
    settings.speak = !settings.speak;
    localStorage.setItem("voiceSpeak", settings.speak ? "1" : "0");
    el.optSpeak.checked = settings.speak;
    updateSpeakerButton();
    toast(settings.speak ? "I'll read my replies aloud." : "Spoken replies off.");
  });

  // ============================================================ 8. memory panel
  async function refreshMemoryCount() {
    try {
      const data = await api("/api/memory");
      el.memoryCount.textContent = data.count;
      el.memoryCount.classList.toggle("zero", data.count === 0);
      return data;
    } catch (_) {
      return null;
    }
  }

  function renderMemoryList(data) {
    el.memoryList.innerHTML = "";
    if (!data || !data.facts.length) {
      el.memoryList.innerHTML =
        '<div class="empty-hint">Nothing yet. Tell me something like ' +
        '"my name is Sam" or "remember that I prefer short answers".</div>';
      return;
    }
    data.facts.forEach((fact) => {
      const row = document.createElement("div");
      row.className = "memory-item";

      const text = document.createElement("div");
      text.className = "memory-text";
      text.textContent = fact.content;

      const badge = document.createElement("span");
      badge.className = "badge " + (fact.source === "manual" ? "manual" : "auto");
      badge.textContent = fact.source === "manual" ? "you added" : "learned";

      const del = document.createElement("button");
      del.className = "chip-x";
      del.textContent = "✕";
      del.title = "Forget this";
      del.addEventListener("click", async () => {
        try {
          await api(`/api/memory/${fact.id}`, { method: "DELETE" });
          await openMemory();
        } catch (err) { toast(err.message); }
      });

      row.append(text, badge, del);
      el.memoryList.append(row);
    });
  }

  async function openMemory() {
    const data = await refreshMemoryCount();
    renderMemoryList(data);
    el.memoryModal.hidden = false;
    closeSidebar();
  }

  async function addMemoryFact() {
    const content = el.memoryInput.value.trim();
    if (content.length < 3) { toast("Write a little more first."); return; }
    try {
      await api("/api/memory", { method: "POST", body: JSON.stringify({ content }) });
      el.memoryInput.value = "";
      await openMemory();
      toast("Got it — I'll remember that.");
    } catch (err) {
      toast(err.message);
    }
  }

  el.memoryBtn.addEventListener("click", openMemory);
  el.addMemory.addEventListener("click", addMemoryFact);
  el.memoryInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); addMemoryFact(); }
  });
  el.closeMemory.addEventListener("click", () => { el.memoryModal.hidden = true; });
  el.doneMemory.addEventListener("click", () => { el.memoryModal.hidden = true; });
  el.memoryModal.addEventListener("click", (e) => {
    if (e.target === el.memoryModal) el.memoryModal.hidden = true;
  });
  el.clearMemory.addEventListener("click", async () => {
    if (!confirm("Forget everything you know about me? This cannot be undone.")) return;
    try {
      await api("/api/memory", { method: "DELETE" });
      await openMemory();
      toast("Memory cleared.");
    } catch (err) { toast(err.message); }
  });

  el.optSpeak.addEventListener("change", () => {
    settings.speak = el.optSpeak.checked;
    localStorage.setItem("voiceSpeak", settings.speak ? "1" : "0");
    updateSpeakerButton();
  });
  el.optAutoSend.addEventListener("change", () => {
    settings.autoSend = el.optAutoSend.checked;
    localStorage.setItem("voiceAutoSend", settings.autoSend ? "1" : "0");
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") el.memoryModal.hidden = true;
  });

  // ============================================================ 9. sending
  function setSending(on) {
    state.sending = on;
    el.send.disabled = on || !el.input.value.trim();
    el.input.disabled = on;
    el.attach.disabled = on;
    if (!on) el.input.focus();
  }

  async function sendMessage() {
    const text = el.input.value.trim();
    if (!text || state.sending) return;
    if (text.length > MAX_CHARS) {
      toast(`Message is too long (max ${MAX_CHARS} characters).`);
      return;
    }

    stopSpeaking();
    addMessage("user", text, { markdown: false });
    el.input.value = "";
    autosize();
    updateCharCount();
    setSending(true);

    const placeholder = addThinking();

    try {
      if (state.streaming) await streamReply(text, placeholder);
      else await plainReply(text, placeholder);
    } catch (err) {
      console.error(err);
      placeholder.wrap.remove();
      addMessage("error", err.message || "Sorry, something went wrong. Please try again.",
                 { markdown: false });
    } finally {
      setSending(false);
      await loadConversations();
      // Facts are extracted in the background, so give it a moment.
      setTimeout(refreshMemoryCount, 1500);
    }
  }

  async function plainReply(text, placeholder) {
    const data = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ conversation_id: state.conversationId, message: text }),
    });
    state.conversationId = data.conversation_id;
    el.headerTitle.textContent = data.title;
    placeholder.wrap.remove();
    (data.actions || []).forEach((a) => addActionCard(a.detail, a.result));
    if (data.message && data.message.trim()) addMessage("assistant", data.message);
    (data.pending || []).forEach((p) => addConfirmCard(p.token, p.detail));
    speak(data.message);
  }

  async function streamReply(text, placeholder) {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: state.conversationId, message: text }),
    });

    if (!res.ok || !res.body) {
      let detail = "";
      try { detail = (await res.json()).detail; } catch (_) { /* ignore */ }
      if (res.status === 400 || res.status === 404) throw new Error(detail || "Request rejected.");
      state.streaming = false;
      return plainReply(text, placeholder);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let answer = "";
    let failed = null;
    let body = null;

    const startBody = () => {
      if (!body) { placeholder.body.innerHTML = ""; body = placeholder.body; }
      return body;
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const frames = buffer.split("\n\n");
      buffer = frames.pop();

      for (const frame of frames) {
        let event = "message";
        let dataLine = "";
        frame.split("\n").forEach((line) => {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLine += line.slice(5).trim();
        });
        if (!dataLine) continue;

        let payload;
        try { payload = JSON.parse(dataLine); } catch (_) { continue; }

        if (event === "start") {
          state.conversationId = payload.conversation_id;
          if (payload.title) el.headerTitle.textContent = payload.title;
        } else if (event === "token") {
          answer += payload.text || "";
          const target = startBody();
          renderMarkdown(target, answer);
          target.insertAdjacentHTML("beforeend", '<span class="cursor">&nbsp;</span>');
          scrollToBottom();
        } else if (event === "tool") {
          // Nova performed an action. Show it, and start a fresh bubble after.
          if (answer.trim()) {
            placeholder.wrap.remove();
            addMessage("assistant", answer);
            answer = "";
            body = null;
          } else {
            placeholder.wrap.remove();
          }
          addActionCard(payload.detail, payload.result);
          placeholder = addThinking();
        } else if (event === "confirm") {
          if (answer.trim()) {
            placeholder.wrap.remove();
            addMessage("assistant", answer);
            answer = "";
            body = null;
          } else {
            placeholder.wrap.remove();
          }
          addConfirmCard(payload.token, payload.detail);
          placeholder = addThinking();
        } else if (event === "error") {
          failed = payload.detail || "Sorry, something went wrong. Please try again.";
        } else if (event === "done") {
          if (payload.title) el.headerTitle.textContent = payload.title;
        }
      }
    }

    placeholder.wrap.remove();

    if (answer.trim()) {
      addMessage("assistant", answer);
      speak(answer);
    }
    if (failed) addMessage("error", failed, { markdown: false });
    if (!answer.trim() && !failed) {
      addMessage("error", "The AI returned an empty response. Please try again.",
                 { markdown: false });
    }
  }

  // ============================================================ 9b. input UX
  function autosize() {
    el.input.style.height = "auto";
    el.input.style.height = Math.min(el.input.scrollHeight, 180) + "px";
  }

  function updateCharCount() {
    const n = el.input.value.length;
    el.charCount.textContent = `${n} / ${MAX_CHARS}`;
    el.charCount.style.color = n > MAX_CHARS * 0.9 ? "var(--danger)" : "";
  }

  el.input.addEventListener("input", () => {
    autosize();
    updateCharCount();
    el.send.disabled = state.sending || !el.input.value.trim();
  });

  el.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      sendMessage();
    }
  });

  el.send.addEventListener("click", sendMessage);

  document.querySelectorAll(".suggestion").forEach((btn) => {
    btn.addEventListener("click", () => {
      el.input.value = btn.dataset.prompt || "";
      autosize();
      updateCharCount();
      el.send.disabled = !el.input.value.trim();
      el.input.focus();
      // Put the cursor at the end, handy for the "remember my name is ..." prompt.
      el.input.setSelectionRange(el.input.value.length, el.input.value.length);
    });
  });

  // sidebar
  function openSidebar() {
    el.sidebar.classList.add("open");
    el.overlay.hidden = false;
  }
  function closeSidebar() {
    el.sidebar.classList.remove("open");
    el.overlay.hidden = true;
  }
  el.menu.addEventListener("click", openSidebar);
  el.closeSidebar.addEventListener("click", closeSidebar);
  el.overlay.addEventListener("click", closeSidebar);
  el.newChat.addEventListener("click", newChat);

  // theme
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);

    const goingLight = theme === "dark";
    el.themeIcon.textContent = goingLight ? "☀️" : "🌙";
    el.themeLabel.textContent = goingLight ? "Light mode" : "Dark mode";

    const dark = $("hljsDark");
    const light = $("hljsLight");
    if (dark && light) {
      dark.disabled = theme !== "dark";
      light.disabled = theme === "dark";
    }
  }
  function toggleTheme() {
    const current = document.documentElement.getAttribute("data-theme");
    applyTheme(current === "dark" ? "light" : "dark");
  }
  el.theme.addEventListener("click", toggleTheme);
  el.themeTop.addEventListener("click", toggleTheme);

  // ============================================================ 10. boot
  // Registering a service worker is what lets you "install" Nova as a real
  // app (own icon, own window, no address bar). It caches nothing.
  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    if (!window.isSecureContext) return;      // needs https or localhost
    navigator.serviceWorker.register("/static/sw.js").catch((err) => {
      console.warn("Service worker registration skipped:", err.message);
    });
  }

  async function init() {
    applyTheme(localStorage.getItem("theme") || "dark");
    registerServiceWorker();
    autosize();
    updateCharCount();

    // voice UI state
    el.optSpeak.checked = settings.speak;
    el.optAutoSend.checked = settings.autoSend;
    updateSpeakerButton();
    if (!SpeechRecognition) {
      el.mic.classList.add("unsupported");
      el.mic.title = "Voice input needs Chrome, Edge, or Safari";
    }
    const notes = [];
    notes.push(SpeechRecognition
      ? "Voice input is available in this browser."
      : "Voice input is not supported here — try Chrome, Edge, or Safari.");
    if (!window.isSecureContext && location.hostname !== "localhost"
        && location.hostname !== "127.0.0.1") {
      notes.push("The microphone needs https:// (or localhost) to work.");
    }
    el.voiceNote.textContent = notes.join(" ");

    try {
      const [health, uploadInfo] = await Promise.all([
        api("/api/health"),
        api("/api/upload/info").catch(() => null),
      ]);
      el.modelBadge.textContent = health.offline_mock ? "⚠ offline mock mode" : health.model;
      if (!health.api_key_configured && !health.offline_mock) {
        toast("No API key configured on the server. Check your .env file.", 5000);
      }
      if (uploadInfo) {
        state.uploadInfo = uploadInfo;
        if (uploadInfo.enabled === false) {
          // Server is running without python-multipart: hide the attach button
          // rather than letting the user click something that cannot work.
          el.attach.hidden = true;
          console.warn(uploadInfo.reason || "File upload is unavailable.");
        } else {
          el.fileInput.setAttribute("accept", uploadInfo.extensions.join(","));
          el.attach.title =
            `Attach a file (${uploadInfo.extensions.join(" ")}) — max ${uploadInfo.max_mb} MB`;
        }
      }
    } catch (_) {
      el.modelBadge.textContent = "server unreachable";
    }

    await refreshMemoryCount();
    await loadConversations();
    if (state.conversations.length) await openConversation(state.conversations[0].id);
    else newChat();
  }

  init();
})();
