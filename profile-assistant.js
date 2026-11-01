(function() {
  /* =============================================
     KNOWLEDGE BASE — key-value profile data
  ============================================= */
  const KB = [
    {
      keys: ['current role','job','position','work','title','experience','career','data engineering experience','ai engineering experience','what do you do','who is'],
      answer: "Jabulani is an <strong>early-career Data &amp; AI Engineering professional</strong> currently developing through IBM internship experience. His direction is Data Engineering -> Analytics Systems -> AI Engineering -> Agentic Systems -> Enterprise AI.",
      section: '#experience',
      sectionLabel: 'View Experience'
    },
    {
      keys: ['ibm','company','employer','internship','organization'],
      answer: "At <strong>IBM South Africa</strong>, Jabulani has hands-on and client-engineering exposure across Python, SQL, ETL, FastAPI, Kafka, Confluent, PySpark, LLM apps, watsonx, MCP/tool calling, technical discovery, requirements and governance-aware solution engineering.",
      section: '#experience',
      sectionLabel: 'View IBM Experience'
    },
    {
      keys: ['skill','skills','technologies','tech stack','tools','what can','expertise','good at'],
      answer: "His strongest current capability areas are:<br>• <strong>Data:</strong> Python, SQL, ETL, Db2, PySpark, Kafka, validation and modelling<br>• <strong>Systems:</strong> FastAPI, REST, GraphQL, MCP servers, backend/database integration<br>• <strong>AI:</strong> LLM apps, prompt engineering, NL2SQL, tool calling, RAG concepts and AI evaluation<br>• <strong>Enterprise:</strong> requirements, discovery, architecture discussions, governance and stakeholder alignment.",
      section: '#skills',
      sectionLabel: 'View Skills'
    },
    {
      keys: ['project','projects','built','portfolio','case study','work done','achievements','systems'],
      answer: "Hero projects include <strong>Pulse360 AI Performance Analytics</strong>, <strong>SARB Regulatory 360 Risk View</strong>, <strong>Kafka Real-Time Tax/Risk Analytics</strong>, <strong>Fleet360 Logistics Data Modernisation</strong>, <strong>Credit Application AI Data Pipeline</strong> and a <strong>local MCP Server</strong>.",
      section: '#projects',
      sectionLabel: 'View Systems'
    },
    {
      keys: ['pulse360','performance','employee','pdf','csv'],
      answer: "<strong>Pulse360</strong> demonstrates the difference between LLM generation, structured system behavior and agentic decision-making. It combines performance-review interpretation, broader database analysis, MCP tool calling and output artifacts such as PDF reports and CSV development outputs.",
      section: '#projects',
      sectionLabel: 'View Pulse360'
    },
    {
      keys: ['sarb','regulatory','risk','ba410','ba700','iceberg'],
      answer: "<strong>SARB Regulatory 360</strong> is a regulatory analytics project involving BA410/BA700 data, risk-oriented data marts, PySpark transformations, Iceberg-style architecture, fraud/risk metrics, anomaly analytics and prompt-driven querying concepts.",
      section: '#projects',
      sectionLabel: 'View Regulatory 360'
    },
    {
      keys: ['kafka','confluent','streaming','fastapi','tax','risk analytics'],
      answer: "The real-time risk analytics platform pattern uses <strong>Kafka, Confluent Cloud, FastAPI, Streamlit, SQL, risk scoring and AI/LLM reasoning</strong> to simulate event-driven anomaly explanation and risk intelligence.",
      section: '#projects',
      sectionLabel: 'View Streaming Project'
    },
    {
      keys: ['fleet','fleet360','db2','3nf','csv','data modernisation'],
      answer: "<strong>Fleet360</strong> modernises about 10 years of fleet-maintenance data from 11 CSV sources into a normalized Db2 foundation using 3NF modelling, Python ETL, null detection, cleaning, imputation and mapping logic.",
      section: '#projects',
      sectionLabel: 'View Fleet360'
    },
    {
      keys: ['mcp','tool calling','mcp server','inspector','agent'],
      answer: "Jabulani built a local <strong>Model Context Protocol server</strong> with tool registration, request handling, custom tools, local testing and validation through MCP Inspector. This is the foundation for his next profile assistant agent.",
      section: '#projects',
      sectionLabel: 'View MCP Work'
    },
    {
      keys: ['rag','mongodb','vector','embeddings','voyage','openai','chatbot','assistant'],
      answer: "The next portfolio assistant roadmap is a RAG pipeline using <strong>MongoDB Atlas Vector Search</strong> with both <strong>Voyage AI</strong> and <strong>OpenAI embeddings</strong>. Free/self-hosted vector-store alternatives worth testing include Qdrant, Chroma, Weaviate and PostgreSQL with pgvector.",
      section: '#stack',
      sectionLabel: 'View Stack'
    },
    {
      keys: ['certification','certifications','badges','credential','certified','training','learning'],
      answer: "The portfolio now separates <strong>verified learning, training, exposure and certifications</strong>. DP-100, AZ-900, AI-300 and AZ-204 are treated as preparation/exposure unless a passing credential is supplied.",
      section: '#badges',
      sectionLabel: 'View Learning'
    },
    {
      keys: ['education','study','university','degree','school','qualifications','academic'],
      answer: "Jabulani's academic foundation is a <strong>Bachelor of Science in Information Technology</strong> from the University of the Free State, supported by student-assistant roles in physics labs, web/internet programming and computer hardware.",
      section: '#education',
      sectionLabel: 'View Education'
    },
    {
      keys: ['leadership','community','volunteer','mentor','teaching','communication'],
      answer: "Jabulani's leadership story includes service-learning supervision, computer-literacy training, student support and a communication priority: Situation -> Recommendation -> Reason -> Business Impact -> Next Step.",
      section: '#volunteer',
      sectionLabel: 'View Impact'
    },
    {
      keys: ['philosophy','approach','methodology','mindset','principle'],
      answer: "Jabulani's engineering philosophy: <em>Data-driven first. AI-enabled second.</em> Not every problem needs an agent; the best architecture is often deterministic workflows plus selective AI autonomy, with governance and evaluation around it.",
      section: '#about',
      sectionLabel: 'About Jabulani'
    },
    {
      keys: ['contact','email','linkedin','github','reach','hire','available','availability'],
      answer: "You can connect through the contact section. The current email shown is a placeholder from the source portfolio and should be replaced with Jabulani's preferred public email before publishing.",
      section: '#contact',
      sectionLabel: 'Go to Contact'
    }
  ];

  const RAG_API_BASE_URL = window.PORTFOLIO_API_BASE_URL || 'http://localhost:8765';
  const RAG_TOP_K = 3;
  const RAG_CHAT_MODEL = 'gpt-5.5';
  const RAG_HEALTH_TIMEOUT_MS = 5000;
  const RAG_REQUEST_TIMEOUT_MS = 180000;

  /* =============================================
     FUZZY MATCH — find best KB entry
  ============================================= */
  function findAnswer(input) {
    const q = input.toLowerCase().trim();
    let best = null, bestScore = 0;
    for (const entry of KB) {
      let score = 0;
      for (const kw of entry.keys) {
        if (q.includes(kw)) score += kw.length;
        else {
          const words = kw.split(' ');
          for (const w of words) {
            if (w.length > 3 && q.includes(w)) score += 1;
          }
        }
      }
      if (score > bestScore) { bestScore = score; best = entry; }
    }
    return bestScore > 0 ? best : null;
  }

  /* =============================================
     LOCAL STORAGE ANALYTICS
  ============================================= */
  const LS_KEY = 'jn_portfolio_analytics';

  function loadAnalytics() {
    try { return JSON.parse(localStorage.getItem(LS_KEY)) || { sessions: 0, totalQuestions: 0, visitors: 0, lastVisit: null, questions: {} }; }
    catch(e) { return { sessions: 0, totalQuestions: 0, visitors: 0, lastVisit: null, questions: {} }; }
  }

  function saveAnalytics(data) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(data)); } catch(e) {}
  }

  function recordSession() {
    const a = loadAnalytics();
    const today = new Date().toDateString();
    a.sessions++;
    a.lastVisit = new Date().toISOString();
    if (!localStorage.getItem('jn_visited_' + today)) {
      a.visitors++;
      try { localStorage.setItem('jn_visited_' + today, '1'); } catch(e) {}
    }
    saveAnalytics(a);
  }

  function recordQuestion(q) {
    const a = loadAnalytics();
    a.totalQuestions++;
    const key = q.toLowerCase().trim().slice(0, 60);
    a.questions[key] = (a.questions[key] || 0) + 1;
    saveAnalytics(a);
  }

  function renderAnalytics() {
    const a = loadAnalytics();
    document.getElementById('an-sessions').textContent = a.sessions;
    document.getElementById('an-questions').textContent = a.totalQuestions;
    document.getElementById('an-visitors').textContent = a.visitors;
    document.getElementById('an-last').textContent = a.lastVisit
      ? new Date(a.lastVisit).toLocaleDateString('en-ZA', { day:'numeric', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' })
      : '—';

    const topQ = Object.entries(a.questions)
      .sort((x,y) => y[1]-x[1])
      .slice(0, 5);

    const tqEl = document.getElementById('an-top-questions');
    if (topQ.length) {
      tqEl.innerHTML = '<div class="tq-label">Top Questions Asked</div>' +
        topQ.map(([q,c]) => `<div class="tq-item"><span>${q}</span><span class="tq-count">${c}×</span></div>`).join('');
    } else {
      tqEl.innerHTML = '<div class="tq-label" style="opacity:0.5">No questions yet</div>';
    }
  }

  /* =============================================
     CHAT ENGINE
  ============================================= */
  const panel     = document.getElementById('chat-panel');
  const shipBtn   = document.getElementById('ship-btn');
  const closeBtn  = document.getElementById('chat-close-btn');
  const messagesEl= document.getElementById('chat-messages');
  const inputEl   = document.getElementById('chat-input');
  const sendBtn   = document.getElementById('chat-send');
  const analyticsToggle = document.getElementById('analytics-toggle');
  const analyticsPanel  = document.getElementById('analytics-panel');
  const chatStatusEl = document.getElementById('chat-status');

  let isOpen = false;
  let greeted = false;
  let isSending = false;

  function ts() {
    return new Date().toLocaleTimeString('en-ZA', { hour:'2-digit', minute:'2-digit' });
  }

  function addMsg(text, role, section, sectionLabel, options = {}) {
    const div = document.createElement('div');
    div.className = 'msg ' + role;
    if (options.label) {
      const label = document.createElement('div');
      label.className = 'msg-label';
      label.textContent = options.label;
      div.appendChild(label);
    }
    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    if (options.allowHtml) bubble.innerHTML = text;
    else bubble.textContent = text;
    if (Array.isArray(options.citations) && options.citations.length) {
      const citations = document.createElement('details');
      citations.className = 'msg-citations';
      const title = document.createElement('summary');
      title.className = 'msg-citations-title';
      title.textContent = `EVIDENCE & SCORES (${options.citations.length})`;
      citations.appendChild(title);
      const citationList = document.createElement('div');
      citationList.className = 'msg-citation-list';
      options.citations.forEach(citation => {
        const item = document.createElement('div');
        item.className = 'msg-citation';
        const description = [
          citation.evidence_id ? `[${citation.evidence_id}]` : '',
          citation.title || citation.source_id || 'Source',
          citation.section || ''
        ].filter(Boolean).join(' · ');
        const source = document.createElement('div');
        source.textContent = description;
        item.appendChild(source);

        const scores = [];
        if (citation.chunk_id) scores.push(`Chunk ${citation.chunk_id}`);
        if (citation.vector_score != null && Number.isFinite(Number(citation.vector_score))) {
          scores.push(`Vector ${Number(citation.vector_score).toFixed(3)}`);
        }
        if (citation.rerank_score != null && Number.isFinite(Number(citation.rerank_score))) {
          scores.push(`Rerank ${Number(citation.rerank_score).toFixed(3)}`);
        }
        if (scores.length) {
          const scoreLine = document.createElement('div');
          scoreLine.className = 'msg-citation-scores';
          scoreLine.textContent = scores.join(' · ');
          item.appendChild(scoreLine);
        }
        citationList.appendChild(item);
      });
      citations.appendChild(citationList);
      bubble.appendChild(citations);
    }
    if (options.timings) {
      const timingParts = [];
      if (Number.isFinite(Number(options.timings.healthMs))) {
        timingParts.push(`Health ${Number(options.timings.healthMs).toFixed(0)} ms`);
      }
      if (Number.isFinite(Number(options.timings.askMs))) {
        timingParts.push(`API ${Number(options.timings.askMs).toFixed(0)} ms`);
      }
      const backend = options.timings.backend;
      if (backend) {
        if (Number.isFinite(Number(backend.embedding))) timingParts.push(`Embed ${Number(backend.embedding).toFixed(0)} ms`);
        if (Number.isFinite(Number(backend.retrieval))) timingParts.push(`Retrieve ${Number(backend.retrieval).toFixed(0)} ms`);
        if (Number.isFinite(Number(backend.rerank))) timingParts.push(`Rerank ${Number(backend.rerank).toFixed(0)} ms`);
        if (Number.isFinite(Number(backend.answer_generation))) timingParts.push(`Answer ${Number(backend.answer_generation).toFixed(0)} ms`);
      }
      if (timingParts.length) {
        const timings = document.createElement('div');
        timings.className = 'msg-timings';
        timings.textContent = timingParts.join(' · ');
        bubble.appendChild(timings);
      }
    }
    if (section && sectionLabel) {
      const link = document.createElement('a');
      link.className = 'sec-link';
      const sectionExists = document.querySelector(section);
      link.href = sectionExists ? section : `index.html${section}`;
      link.textContent = '→ ' + sectionLabel;
      link.addEventListener('click', () => {
        closeChat();
        if (sectionExists) {
          setTimeout(() => { document.querySelector(section)?.scrollIntoView({ behavior:'smooth' }); }, 300);
        }
      });
      bubble.appendChild(document.createElement('br'));
      bubble.appendChild(link);
    }
    const time = document.createElement('div');
    time.className = 'msg-time';
    time.textContent = ts();
    div.appendChild(bubble);
    div.appendChild(time);
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  async function checkRagHealth() {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), RAG_HEALTH_TIMEOUT_MS);
    const started = performance.now();
    try {
      const response = await fetch(`${RAG_API_BASE_URL}/api/status`, {
        method: 'GET',
        cache: 'no-store',
        signal: controller.signal
      });
      if (!response.ok) {
        throw new Error(`RAG status check failed (HTTP ${response.status}).`);
      }
      const payload = await response.json();
      if (!payload || typeof payload.mongo_ok !== 'boolean') {
        throw new Error('RAG status endpoint returned an unexpected response.');
      }
      if (!payload.mongo_ok) {
        throw new Error('RAG backend is reachable, but MongoDB is not connected.');
      }
      if (payload.config?.chat_model !== RAG_CHAT_MODEL) {
        throw new Error(
          `RAG is configured for ${payload.config?.chat_model || 'an unknown model'}; ${RAG_CHAT_MODEL} is required.`
        );
      }
      return { elapsedMs: performance.now() - started };
    } catch (error) {
      if (error.name === 'AbortError') {
        throw new Error(`RAG health check timed out after ${RAG_HEALTH_TIMEOUT_MS / 1000} seconds.`);
      }
      throw error;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  async function askRag(question) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), RAG_REQUEST_TIMEOUT_MS);
    const started = performance.now();
    try {
      const response = await fetch(`${RAG_API_BASE_URL}/api/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: question, top_k: RAG_TOP_K, min_score: 0.6 }),
        signal: controller.signal
      });
      let payload;
      try {
        payload = await response.json();
      } catch {
        throw new Error(`RAG API returned a non-JSON response (${response.status}).`);
      }
      if (!response.ok) {
        const detail = payload && typeof payload.error === 'string' ? `: ${payload.error}` : '';
        throw new Error(`RAG API request failed (${response.status})${detail}`);
      }
      if (!payload || typeof payload.answer !== 'string' || !payload.answer.trim()) {
        throw new Error('RAG API response did not contain an answer.');
      }
      if (payload.chat_model !== RAG_CHAT_MODEL) {
        throw new Error(
          `RAG answered with ${payload.chat_model || 'an unknown model'}; ${RAG_CHAT_MODEL} is required.`
        );
      }
      if (!Array.isArray(payload.citations) ||
          payload.citations.some(citation => !citation || typeof citation !== 'object' || Array.isArray(citation))) {
        throw new Error('RAG API response did not contain valid citations.');
      }
      return { ...payload, clientElapsedMs: performance.now() - started };
    } catch (error) {
      if (error.name === 'AbortError') {
        throw new Error(`RAG /api/ask timed out after ${RAG_REQUEST_TIMEOUT_MS / 1000} seconds.`);
      }
      throw error;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  function showTyping() {
    const d = document.createElement('div');
    d.className = 'msg bot';
    d.id = 'typing-indicator';
    d.innerHTML = '<div class="msg-bubble typing-indicator"><span></span><span></span><span></span></div>';
    messagesEl.appendChild(d);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function removeTyping() {
    document.getElementById('typing-indicator')?.remove();
  }

  async function processInput(text) {
    const question = text.trim();
    if (!question || isSending) return;
    isSending = true;
    inputEl.disabled = true;
    sendBtn.disabled = true;
    addMsg(question, 'user');
    recordQuestion(question);
    showTyping();

    const localMatch = findAnswer(question);
    let healthElapsedMs = null;
    let askStarted = null;
    try {
      chatStatusEl.dataset.state = 'loading';
      chatStatusEl.textContent = 'Checking RAG API health...';
      const health = await checkRagHealth();
      healthElapsedMs = health.elapsedMs;
      chatStatusEl.textContent = `API healthy (${healthElapsedMs.toFixed(0)} ms) — retrieving answer...`;
      askStarted = performance.now();
      const result = await askRag(question);
      const askElapsedMs = performance.now() - askStarted;
      removeTyping();
      const insufficient = result.insufficient_evidence === true;
      chatStatusEl.dataset.state = 'connected';
      const backendTimings = result.timings_ms;
      const timingSummary = backendTimings
        ? `embed ${backendTimings.embedding} ms · retrieve ${backendTimings.retrieval} ms · rerank ${backendTimings.rerank} ms · answer ${backendTimings.answer_generation} ms`
        : `ask ${askElapsedMs.toFixed(0)} ms`;
      chatStatusEl.textContent = `RAG API healthy · health ${healthElapsedMs.toFixed(0)} ms · ${timingSummary}`;
      addMsg(
        result.answer,
        'bot',
        localMatch?.section || '#contact',
        localMatch?.sectionLabel || 'Explore Portfolio',
        {
          label: insufficient ? 'RAG // INSUFFICIENT EVIDENCE' : 'RAG // GROUNDED ANSWER',
          citations: result.citations,
          timings: {
            healthMs: healthElapsedMs,
            askMs: askElapsedMs,
            backend: backendTimings
          }
        }
      );
    } catch (error) {
      removeTyping();
      chatStatusEl.dataset.state = 'error';
      const askElapsedMs = askStarted == null ? null : performance.now() - askStarted;
      const healthNote = healthElapsedMs == null ? 'Health check failed' : `Health ${healthElapsedMs.toFixed(0)} ms`;
      chatStatusEl.textContent = `RAG API error · ${healthNote}${askElapsedMs == null ? '' : ` · ask ${askElapsedMs.toFixed(0)} ms`}`;
      console.error('Lex RAG request failed; local fallback is disabled.', error);
      const errorMessage = error instanceof Error ? error.message : 'Unknown API error.';
      addMsg(
        `The RAG request failed: ${errorMessage}`,
        'bot',
        localMatch?.section || '#contact',
        localMatch?.sectionLabel || 'Contact Jabulani',
        { label: 'RAG // API ERROR' }
      );
    } finally {
      isSending = false;
      inputEl.disabled = false;
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }

  function openChat() {
    isOpen = true;
    panel.classList.add('open');
    shipBtn.style.filter = 'drop-shadow(0 0 24px rgba(0,245,255,1)) drop-shadow(0 0 48px rgba(123,47,255,0.6))';
    recordSession();
    if (!greeted) {
      greeted = true;
      setTimeout(() => {
        addMsg(
          "Hello! I'm <strong>Lex</strong>, Jabulani's profile agent. 👋<br>I can tell you about his experience, skills, projects, certifications, and more. What would you like to know?",
          'bot',
          undefined,
          undefined,
          { allowHtml: true }
        );
      }, 350);
    }
    setTimeout(() => inputEl.focus(), 400);
  }

  function closeChat() {
    isOpen = false;
    panel.classList.remove('open');
    shipBtn.style.filter = '';
  }

  shipBtn.addEventListener('click', () => isOpen ? closeChat() : openChat());
  closeBtn.addEventListener('click', closeChat);

  sendBtn.addEventListener('click', () => {
    void processInput(inputEl.value);
    inputEl.value = '';
  });

  inputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      e.preventDefault();
      void processInput(inputEl.value);
      inputEl.value = '';
    }
  });

  document.querySelectorAll('.sugg-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      void processInput(chip.dataset.q);
    });
  });

  analyticsToggle.addEventListener('click', () => {
    analyticsPanel.classList.toggle('open');
    if (analyticsPanel.classList.contains('open')) {
      renderAnalytics();
      analyticsToggle.textContent = 'HIDE ANALYTICS';
    } else {
      analyticsToggle.textContent = 'VIEW SESSION ANALYTICS';
    }
  });

  // Close on Escape
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && isOpen) closeChat();
  });
})();
