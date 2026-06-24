const QUOTA_POLL_MS = 30_000;
const $ = sel => document.querySelector(sel);
(function _initGlobalTooltip() {
  if (window._globalTooltipInited) return;
  window._globalTooltipInited = true;
  const tip = document.createElement("div");
  tip.id = "global-tooltip";
  tip.hidden = true;
  const attach = () => document.body.appendChild(tip);
  if (document.body) attach();else document.addEventListener("DOMContentLoaded", attach, {
    once: true
  });
  let showTimer = null;
  let hideTimer = null;
  let currentTarget = null;
  const positionTip = el => {
    const rect = el.getBoundingClientRect();
    const tipRect = tip.getBoundingClientRect();
    const margin = 6;
    let left = rect.left + rect.width / 2 - tipRect.width / 2;
    let top = rect.top - tipRect.height - margin;
    let placement = "above";
    if (top < 4) {
      top = rect.bottom + margin;
      placement = "below";
    }
    left = Math.max(4, Math.min(left, window.innerWidth - tipRect.width - 4));
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
    tip.classList.remove("gt-above", "gt-below");
    tip.classList.add(placement === "above" ? "gt-above" : "gt-below");
  };
  const show = (el, text) => {
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
    if (showTimer) {
      clearTimeout(showTimer);
      showTimer = null;
    }
    showTimer = setTimeout(() => {
      tip.textContent = text;
      tip.hidden = false;
      tip.classList.remove("gt-hide");
      positionTip(el);
      requestAnimationFrame(() => {
        if (el === currentTarget) positionTip(el);
        tip.classList.add("gt-show");
      });
    }, 350);
  };
  const hide = () => {
    if (showTimer) {
      clearTimeout(showTimer);
      showTimer = null;
    }
    if (hideTimer) clearTimeout(hideTimer);
    tip.classList.remove("gt-show");
    tip.classList.add("gt-hide");
    hideTimer = setTimeout(() => {
      tip.hidden = true;
      currentTarget = null;
    }, 150);
  };
  const hijack = el => {
    if (!el || el.nodeType !== 1) return;
    if (el.dataset.tooltip !== undefined) return;
    const t = el.getAttribute("title");
    if (!t) return;
    el.dataset.tooltip = t;
    el.removeAttribute("title");
    if (!el.hasAttribute("aria-label")) {
      el.setAttribute("aria-label", t);
    }
  };
  const initialHijack = () => {
    document.querySelectorAll("[title]").forEach(hijack);
  };
  if (document.readyState !== "loading") initialHijack();else document.addEventListener("DOMContentLoaded", initialHijack, {
    once: true
  });
  const mo = new MutationObserver(muts => {
    for (const mut of muts) {
      if (mut.type === "attributes" && mut.attributeName === "title") {
        hijack(mut.target);
        continue;
      }
      for (const node of mut.addedNodes) {
        if (!node || node.nodeType !== 1) continue;
        if (node.hasAttribute && node.hasAttribute("title")) hijack(node);
        if (node.querySelectorAll) {
          node.querySelectorAll("[title]").forEach(hijack);
        }
      }
    }
  });
  const startObserver = () => {
    mo.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["title"]
    });
  };
  if (document.body) startObserver();else document.addEventListener("DOMContentLoaded", startObserver, {
    once: true
  });
  document.addEventListener("mouseover", e => {
    const el = e.target.closest("[data-tooltip]");
    if (!el || el === currentTarget) return;
    currentTarget = el;
    show(el, el.dataset.tooltip);
  });
  document.addEventListener("mouseout", e => {
    if (!currentTarget) return;
    const rel = e.relatedTarget;
    if (rel && currentTarget.contains(rel)) return;
    hide();
  });
  const hideAggressive = () => {
    if (currentTarget) hide();
  };
  document.addEventListener("scroll", hideAggressive, true);
  document.addEventListener("wheel", hideAggressive, {
    passive: true
  });
  document.addEventListener("click", hideAggressive);
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") hideAggressive();
  });
})();
const dialogue = $("#dialogue-stream");
const userInput = $("#user-input");
const sendBtn = $("#send-btn");
const endBtn = $("#end-session");
const exportRecapBtn = $("#export-recap-btn");
const startForm = $("#start-form");
const sessionInfo = $("#session-info");
const quotaContent = $("#quota-content");
const recordIndicator = $("#record-indicator");
const micBtn = $("#mic-btn");
const mediaBtn = $("#media-btn");
const mediaInput = $("#media-input");
const rewriteBtn = $("#rewrite-btn");
const rewritePopover = $("#rewrite-popover");
const rewriteUndoBtn = $("#rewrite-undo");
const findExoBtn = $("#find-exo-btn");
let activeSession = null;
let activeMode = null;
let activeColleFormat = "mixte";
let currentEventSource = null;
let userRole = "owner";
let viewerPollHandle = null;
let currentClaudeTurn = null;
let currentClaudeRawText = "";
let mediaRecorder = null;
let recordedChunks = [];
let micStream = null;
let isRecording = false;
let guidedSlides = [];
let guidedIndex = -1;
let guidedTitleGlobal = "";
const SLIDE_TRANSITION_COOLDOWN_MS = 5000;
let lastSlideTransitionTs = 0;
let respondingToSlideMeta = false;
function slideTransitionLocked() {
  if (respondingToSlideMeta) return true;
  return Date.now() - lastSlideTransitionTs < SLIDE_TRANSITION_COOLDOWN_MS;
}
function markSlideTransition() {
  lastSlideTransitionTs = Date.now();
}
function lastClaudeBubbleHasPendingQuestion() {
  const claudeBubbles = dialogue.querySelectorAll(".turn.claude");
  if (!claudeBubbles.length) return false;
  const last = claudeBubbles[claudeBubbles.length - 1];
  let raw = last.dataset.rawText || last.textContent || "";
  raw = raw.replace(/<<<NEXT_SLIDE>>>/g, "").trim();
  if (!raw) return false;
  return raw.endsWith("?");
}
const guidedPanel = $("#guided-panel");
const guidedCounter = $("#guided-counter");
const guidedImg = $("#guided-slide-img");
const guidedPlaceholder = $("#guided-slide-placeholder");
const guidedTitle = $("#guided-slide-title");
const guidedDuration = $("#guided-slide-duration");
const guidedPrev = $("#guided-prev");
const guidedNext = $("#guided-next");
const guidedJump = $("#guided-jump");
function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function _attachmentSrcUrl(att) {
  if (!att || !att.rel_path) return "";
  const storage = att.storage || "cours";
  const endpoint = storage === "uploads" ? "/api/upload_file" : "/api/cours_file";
  return `${endpoint}?path=${encodeURIComponent(att.rel_path)}`;
}
let _md = null;
function _getMarkdownIt() {
  if (_md) return _md;
  if (typeof window.markdownit !== "function") return null;
  _md = window.markdownit({
    html: false,
    linkify: false,
    breaks: true,
    typographer: false
  });
  try {
    _md.disable(["reference", "abbr", "footnote", "deflist"]);
  } catch (_) {}
  _md.renderer.rules.image = function (tokens, idx, options, env, self) {
    const token = tokens[idx];
    const src = token.attrGet("src") || "";
    const alt = self.renderInlineAsText(token.children || [], options, env) || "";
    const isExternal = /^https?:\/\//i.test(src);
    const normSrc = src.replace(/\\/g, "/").trim();
    const safeAlt = alt.replace(/"/g, "&quot;");
    let safeSrc;
    if (isExternal) {
      safeSrc = normSrc.replace(/"/g, "&quot;");
    } else if (normSrc.startsWith("_uploads/")) {
      const stripped = normSrc.slice("_uploads/".length);
      safeSrc = `/api/upload_file?path=${encodeURIComponent(stripped)}`;
    } else {
      safeSrc = `/api/cours_file?path=${encodeURIComponent(normSrc)}`;
    }
    let imgTitle = "";
    try {
      const filenameOnly = normSrc.split("/").pop() || "";
      const pretty = typeof _prettifyPhotoFilename === "function" ? _prettifyPhotoFilename(filenameOnly) : filenameOnly;
      imgTitle = (pretty || alt).replace(/"/g, "&quot;");
    } catch (_) {
      imgTitle = safeAlt;
    }
    const tipAttr = imgTitle ? ` data-tooltip="${imgTitle}" aria-label="${imgTitle}"` : "";
    const dataPath = normSrc.replace(/"/g, "&quot;");
    const origMd = `![${alt}](${src})`;
    const dataMd = origMd.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
    return `<span class="md-img-wrap" data-md="${dataMd}">` + `<img src="${safeSrc}" alt="${safeAlt}"${tipAttr} class="md-img" data-src-path="${dataPath}" onerror="this.outerHTML='&lt;div class=&quot;md-img-broken&quot;&gt;⚠️ Image introuvable : &lt;code&gt;'+this.dataset.srcPath+'&lt;/code&gt;&lt;/div&gt;'">` + `<button type="button" class="md-img-del" data-tooltip="Retirer cette pièce jointe du message" aria-label="Retirer cette pièce jointe du message">🗑</button>` + `</span>`;
  };
  _md.renderer.rules.table_open = function () {
    return '<table class="md-table">\n';
  };
  return _md;
}
function _hoistCahierTitles(text) {
  if (!text || text.indexOf("<<<CAHIER") === -1) return text;
  const TAIL = "[ \\t]*\\n(?:[ \\t]*\\n)*" + "(?:[ \\t]*(?:Sous ce titre|Notez|Écriv|Inscriv|Recopiez)[^\\n]*\\n)?" + "(?:[ \\t]*\\n)*";
  const clean = s => s.trim().replace(/\s+/g, " ").replace(/"/g, "'");
  const reKeyword = new RegExp("(^|\\n)[ \\t]*Titre[s]?[ \\t]*[:：\\-–—]?[ \\t]*" + "(?:\\*\\*[ \\t]*)?(.+?)(?:[ \\t]*\\*\\*)?" + TAIL + "<<<CAHIER([^>]*)>{1,3}", "g");
  text = text.replace(reKeyword, (m, lead, rawTitle, attrs) => {
    const titre = clean(rawTitle);
    if (!titre || titre.length > 120) return m;
    const old = ((attrs || "").match(/titre\s*=\s*"([^"]*)"/i) || [])[1];
    const body = old && old.trim() && old.trim().toLowerCase() !== titre.toLowerCase() ? "\n" + old.trim() + "\n" : "";
    return `${lead}<<<CAHIER titre="${titre}">>>${body}`;
  });
  const reBold = new RegExp("(^|\\n)[ \\t]*\\*\\*[ \\t]*(.+?)[ \\t]*\\*\\*" + TAIL + "<<<CAHIER>{1,3}", "g");
  text = text.replace(reBold, (m, lead, rawTitle) => {
    const titre = clean(rawTitle);
    if (!titre || titre.length > 120) return m;
    return `${lead}<<<CAHIER titre="${titre}">>>`;
  });
  return text;
}
const _CAHIER_TAG_RE = /\{\/?(?:bleu|rouge|vert|noir|hl-jaune|hl-vert|hl-rose|hl-violet)\}/g;
const _SIUNITX_UNITS = {
  yotta: "Y",
  zetta: "Z",
  exa: "E",
  peta: "P",
  tera: "T",
  giga: "G",
  mega: "M",
  kilo: "k",
  hecto: "h",
  deca: "da",
  deci: "d",
  centi: "c",
  milli: "m",
  micro: "µ",
  nano: "n",
  pico: "p",
  femto: "f",
  hertz: "Hz",
  second: "s",
  minute: "min",
  hour: "h",
  metre: "m",
  meter: "m",
  gram: "g",
  kilogram: "kg",
  bit: "bit",
  byte: "B",
  watt: "W",
  volt: "V",
  ampere: "A",
  ohm: "Ω",
  farad: "F",
  henry: "H",
  joule: "J",
  newton: "N",
  pascal: "Pa",
  kelvin: "K",
  celsius: "°C",
  mole: "mol",
  candela: "cd",
  decibel: "dB",
  percent: "%",
  per: "/",
  bel: "B",
  radian: "rad",
  steradian: "sr",
  tesla: "T",
  weber: "Wb"
};
const _SIUNITX_CMD_RE = /\\([a-zA-Z]+)(?![a-zA-Z])/g;
function _expandSiUnits(u) {
  const s = String(u || "").replace(_SIUNITX_CMD_RE, (m, name) => Object.prototype.hasOwnProperty.call(_SIUNITX_UNITS, name) ? _SIUNITX_UNITS[name] : m);
  return s.replace(/[{}]/g, "").replace(/\\[a-zA-Z]+/g, "").replace(/\s+/g, "");
}
function _normalizeSiunitx(text, inMath) {
  if (!text || text.indexOf("\\") === -1) return text;
  let t = text;
  t = t.replace(/\\(?:SI|qty)\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, (_m, val, unit) => {
    const u = _expandSiUnits(unit);
    const v = String(val).trim();
    return inMath ? `${v}\\,\\mathrm{${u}}` : `${v} ${u}`;
  });
  t = t.replace(/\\(?:si|unit)\s*\{([^{}]*)\}/g, (_m, unit) => {
    const u = _expandSiUnits(unit);
    return inMath ? `\\mathrm{${u}}` : u;
  });
  t = t.replace(/\\num\s*\{([^{}]*)\}/g, (_m, n) => String(n).trim());
  t = t.replace(_SIUNITX_CMD_RE, (m, name) => Object.prototype.hasOwnProperty.call(_SIUNITX_UNITS, name) ? _SIUNITX_UNITS[name] : m);
  return t;
}
function _protectMathSpans(text) {
  const spans = [];
  const staged = (text || "").replace(/\$\$[\s\S]+?\$\$|\$[^$\n]+?\$/g, m => {
    const clean = m.replace(_CAHIER_TAG_RE, "");
    const i = spans.length;
    spans.push(_normalizeSiunitx(clean, true));
    return `ZZMATHPLACEHOLDER${i}ZZ`;
  });
  return {
    staged: _normalizeSiunitx(staged, false),
    spans
  };
}
function _restoreMathSpans(html, spans) {
  if (!spans || !spans.length) return html;
  return html.replace(/ZZMATHPLACEHOLDER(\d+)ZZ/g, (_m, i) => spans[parseInt(i, 10)] || "");
}
function _renderToolCallChip(jsonStr) {
  let tool = "",
    label = "",
    ok = true;
  try {
    const d = JSON.parse(jsonStr);
    tool = d.tool || "";
    label = d.label || "";
    ok = d.ok !== false;
  } catch (_) {
    return "";
  }
  const ICONS = {
    Read: "📄",
    Grep: "🔎",
    Glob: "🗂️"
  };
  const VERBS = {
    Read: "Lecture de",
    Grep: "Recherche",
    Glob: "Liste"
  };
  const icon = ICONS[tool] || "🔧";
  const verb = VERBS[tool] || tool || "Outil";
  const cls = ok ? "tool-call-chip" : "tool-call-chip is-error";
  const fail = ok ? "" : ' <span class="tcc-fail">échec</span>';
  return `<div class="${cls}">` + `<span class="tcc-dot"></span>` + `<span class="tcc-icon">${icon}</span>` + `<span class="tcc-text">${verb} <code>${escapeHtml(label)}</code>${fail}</span>` + `</div>`;
}
function _renderChoicesBlock(jsonStr) {
  let q = "",
    options = [],
    multi = false;
  try {
    const d = JSON.parse(jsonStr);
    q = String(d.q || d.question || "").trim();
    options = Array.isArray(d.options) ? d.options : [];
    multi = d.multi === true;
  } catch (_) {
    return "";
  }
  if (!options.length) return "";
  const optsHtml = options.map(o => {
    const label = escapeHtml(String(o));
    return `<button type="button" class="choice-opt" data-val="${label}">${label}</button>`;
  }).join("");
  const hint = multi ? "Sélectionne une ou plusieurs réponses : ou bien écris la tienne." : "Choisis une réponse : ou bien écris la tienne.";
  return `<div class="choices-block" data-multi="${multi ? "1" : "0"}">` + (q ? `<div class="choices-q">${escapeHtml(q)}</div>` : "") + `<div class="choices-hint">${hint}</div>` + `<div class="choices-opts">${optsHtml}</div>` + `<textarea class="choice-custom" rows="2" placeholder="✍️ Autre / précise ta réponse…"></textarea>` + `<button type="button" class="choice-send">Envoyer ma réponse →</button>` + `</div>`;
}
function _onChoicesClick(e) {
  const opt = e.target.closest(".choice-opt");
  if (opt) {
    const block = opt.closest(".choices-block");
    if (!block || block.classList.contains("is-answered")) return;
    if (block.dataset.multi !== "1") {
      block.querySelectorAll(".choice-opt.selected").forEach(b => {
        if (b !== opt) b.classList.remove("selected");
      });
    }
    opt.classList.toggle("selected");
    return;
  }
  const send = e.target.closest(".choice-send");
  if (!send) return;
  const block = send.closest(".choices-block");
  if (!block || block.classList.contains("is-answered")) return;
  const picked = [...block.querySelectorAll(".choice-opt.selected")].map(b => (b.dataset.val || "").trim());
  const customEl = block.querySelector(".choice-custom");
  const custom = customEl ? customEl.value.trim() : "";
  const parts = picked.filter(Boolean);
  if (custom) parts.push(custom);
  if (!parts.length) {
    if (customEl) customEl.focus();
    return;
  }
  block.classList.add("is-answered");
  block.querySelectorAll("button, textarea").forEach(el => {
    el.disabled = true;
  });
  if (userInput) {
    userInput.value = parts.join("\n");
    try {
      userInput.dispatchEvent(new Event("input", {
        bubbles: true
      }));
    } catch (_) {}
  }
  if (sendBtn) sendBtn.click();
}
document.addEventListener("click", _onChoicesClick);
function renderMarkdown(text) {
  if (!text) return "";
  const md = _getMarkdownIt();
  if (md) {
    try {
      const choicesBlocks = [];
      const toolCallBlocks = [];
      const preStaged = text.replace(/<<<CHOICES>>>([\s\S]*?)<<<END>>>/g, (_m, json) => {
        const i = choicesBlocks.length;
        choicesBlocks.push(json);
        return `\n\nZZCHOICESPLACEHOLDER${i}ZZ\n\n`;
      }).replace(/<<<CHOICES>>>(?:(?!<<<END>>>)[\s\S])*$/, "").replace(/<<<TOOLCALL>>>([\s\S]*?)<<<TOOLEND>>>/g, (_m, json) => {
        const i = toolCallBlocks.length;
        toolCallBlocks.push(json);
        return `\n\nZZTOOLCALLPLACEHOLDER${i}ZZ\n\n`;
      }).replace(/<<<TOOLCALL>>>(?:(?!<<<TOOLEND>>>)[\s\S])*$/, "");
      const cahierBlocks = [];
      const stagedCahier = _hoistCahierTitles(preStaged).replace(/<<<CAHIER([^>]*)>{1,3}([\s\S]*?)<<<END>>>/g, (_m, attrs, body) => {
        const i = cahierBlocks.length;
        cahierBlocks.push({
          attrs,
          body
        });
        return `\n\nZZCAHIERPLACEHOLDER${i}ZZ\n\n`;
      });
      const {
        staged,
        spans: mathSpans
      } = _protectMathSpans(stagedCahier);
      let html = md.render(staged).replace(/(<br\s*\/?>|>)\s*\n+\s*/g, "$1");
      html = _restoreMathSpans(html, mathSpans);
      html = html.replace(/<p>\s*ZZCAHIERPLACEHOLDER(\d+)ZZ\s*<\/p>/g, (_m, i) => _renderCahierBlock(cahierBlocks[parseInt(i, 10)]));
      html = html.replace(/ZZCAHIERPLACEHOLDER(\d+)ZZ/g, (_m, i) => _renderCahierBlock(cahierBlocks[parseInt(i, 10)]));
      html = html.replace(/<p>\s*ZZTOOLCALLPLACEHOLDER(\d+)ZZ\s*<\/p>/g, (_m, i) => _renderToolCallChip(toolCallBlocks[parseInt(i, 10)]));
      html = html.replace(/ZZTOOLCALLPLACEHOLDER(\d+)ZZ/g, (_m, i) => _renderToolCallChip(toolCallBlocks[parseInt(i, 10)]));
      html = html.replace(/<p>\s*ZZCHOICESPLACEHOLDER(\d+)ZZ\s*<\/p>/g, (_m, i) => _renderChoicesBlock(choicesBlocks[parseInt(i, 10)]));
      html = html.replace(/ZZCHOICESPLACEHOLDER(\d+)ZZ/g, (_m, i) => _renderChoicesBlock(choicesBlocks[parseInt(i, 10)]));
      return html;
    } catch (e) {
      console.warn("markdown-it render error:", e);
    }
  }
  return `<p>${escapeHtml(text)}</p>`;
}
function _renderCahierBlock({
  attrs,
  body
}) {
  const titreMatch = (attrs || "").match(/titre\s*=\s*"([^"]*)"/i);
  const titre = titreMatch ? titreMatch[1].trim() : "";
  const md = _getMarkdownIt();
  let inner = (body || "").trim();
  inner = inner.split("\n").map(line => {
    const dollars = (line.match(/\$/g) || []).length;
    if (dollars % 2 === 0) return line;
    const tail = line.slice(line.lastIndexOf("$") + 1);
    return /[\\{}]/.test(tail) ? `${line.replace(/\s+$/, "")}$` : line;
  }).join("\n");
  const {
    staged: innerStaged,
    spans: innerMath
  } = _protectMathSpans(inner);
  let innerHtml = md ? _restoreMathSpans(md.render(innerStaged).replace(/(<br\s*\/?>|>)\s*\n+\s*/g, "$1"), innerMath) : `<p>${escapeHtml(inner)}</p>`;
  innerHtml = innerHtml.replace(/<strong>/g, "").replace(/<\/strong>/g, "").replace(/<em>/g, "").replace(/<\/em>/g, "");
  innerHtml = innerHtml.replace(/<code>([\s\S]*?)<\/code>/g, (_m, content) => {
    const trimmed = content.trim();
    const isValue = /^[-+]?\d+(?:\.\d+)?$/.test(trimmed) || /["']/.test(trimmed) || /[\[\]{}]/.test(trimmed) || /^\([^)]*\)$/.test(trimmed);
    const cls = isValue ? "cahier-code-inline-value" : "cahier-code-inline";
    return `<span class="${cls}">${content}</span>`;
  });
  innerHtml = innerHtml.replace(/(<pre[^>]*>[\s\S]*?<code[^>]*>)([\s\S]*?)(<\/code>[\s\S]*?<\/pre>)/g, (_m, openPart, codeContent, closePart) => {
    const lines = codeContent.split("\n");
    const colored = lines.map(line => {
      if (/^\s*(--|#|\/\/)/.test(line)) {
        return `<span class="cahier-code-comment">${line}</span>`;
      }
      return line;
    }).join("\n");
    return openPart + colored + closePart;
  });
  const STYLOS = ["bleu", "rouge", "vert", "noir"];
  for (const c of STYLOS) {
    const re = new RegExp(`\\{${c}\\}([\\s\\S]*?)\\{\\/${c}\\}`, "gi");
    innerHtml = innerHtml.replace(re, `<span class="cahier-c-${c}">$1</span>`);
  }
  const HIGHLIGHTS = ["jaune", "vert", "rose", "violet"];
  for (const h of HIGHLIGHTS) {
    const re = new RegExp(`\\{hl-${h}\\}([\\s\\S]*?)\\{\\/hl-${h}\\}`, "gi");
    innerHtml = innerHtml.replace(re, `<mark class="cahier-hl-${h}">$1</mark>`);
  }
  innerHtml = innerHtml.replace(/==([^=\n]+)==/g, '<mark class="cahier-hl-jaune">$1</mark>');
  innerHtml = innerHtml.replace(_CAHIER_TAG_RE, "");
  const _SOUS_TITRE_LABELS = "Méthode|Définition|Théorème|Propriété|Proposition|Lemme|Corollaire|" + "Règle|Notation|Rappel|Remarque|Astuce|Exemple|Démonstration|Preuve";
  innerHtml = innerHtml.replace(new RegExp(`<p>(\\s*(?:${_SOUS_TITRE_LABELS})s?\\s*:[\\s\\S]*?)</p>`, "gi"), '<p><mark class="cahier-hl-vert">$1</mark></p>');
  innerHtml = innerHtml.replace(/<(h[1-6])((?:\s[^>]*)?)>([\s\S]*?)<\/\1>/gi, '<$1$2><mark class="cahier-hl-vert">$3</mark></$1>');
  const titreClean = titre.replace(/\*+/g, "").replace(/`/g, "");
  const titreHtml = titre ? `<div class="cahier-titre">${escapeHtml(titreClean)}</div>` : "";
  return `<div class="cahier-card">${titreHtml}` + `<div class="cahier-body">${innerHtml}</div></div>`;
}
function linkifyPageRefs(rootEl) {
  if (!rootEl) return;
  if (typeof correctionsList === "undefined" || !correctionsList.length) return;
  const re = /\b(?:à\s+la\s+)?(?:p\.?|page)\s*(\d{1,3})\s+(?:du|de\s+l['’])\s*(corrig[ée]|script(?:\s+imprimable)?|correction|concat|énonc[ée]|enonc[ée])(?:\s+(?:de\s+)?(?:l['’])?(?:exercice|exo|ex)\.?\s*(\d+(?:\.\d+)?))?/giu;
  const walker = document.createTreeWalker(rootEl, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const p = node.parentElement;
      if (!p) return NodeFilter.FILTER_REJECT;
      const tag = (p.tagName || "").toUpperCase();
      if (tag === "CODE" || tag === "PRE") return NodeFilter.FILTER_REJECT;
      if (p.closest && p.closest(".katex")) return NodeFilter.FILTER_REJECT;
      if (p.closest && p.closest(".corrige-pageref")) return NodeFilter.FILTER_REJECT;
      return re.test(node.nodeValue || "") ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
    }
  });
  const targets = [];
  let n;
  while (n = walker.nextNode()) targets.push(n);
  for (const node of targets) {
    const text = node.nodeValue || "";
    re.lastIndex = 0;
    const frag = document.createDocumentFragment();
    let lastIdx = 0;
    let m;
    while ((m = re.exec(text)) !== null) {
      const before = text.slice(lastIdx, m.index);
      if (before) frag.appendChild(document.createTextNode(before));
      const pageN = parseInt(m[1], 10);
      const kindRaw = m[2].toLowerCase();
      const exoCaptured = m[3] || null;
      let kind, kindHumanFr;
      if (kindRaw.startsWith("script")) {
        kind = "script";
        kindHumanFr = "script imprimable";
      } else if (kindRaw.startsWith("énonc") || kindRaw.startsWith("enonc")) {
        kind = "enonce";
        kindHumanFr = "énoncé";
      } else {
        kind = "correction";
        kindHumanFr = "corrigé";
      }
      const a = document.createElement("a");
      a.href = "#";
      a.className = "corrige-pageref";
      a.dataset.page = String(pageN);
      a.dataset.kind = kind;
      if (exoCaptured) a.dataset.exo = exoCaptured;
      a.textContent = m[0];
      a.title = exoCaptured ? `Sauter à la page ${pageN} du ${kindHumanFr} de l'exercice ${exoCaptured}` : `Sauter à la page ${pageN} du ${kindHumanFr}`;
      a.addEventListener("click", ev => {
        ev.preventDefault();
        ev.stopPropagation();
        jumpToCorrigePage(pageN, kind, exoCaptured ? {
          exo: exoCaptured
        } : {});
      });
      frag.appendChild(a);
      lastIdx = m.index + m[0].length;
    }
    const tail = text.slice(lastIdx);
    if (tail) frag.appendChild(document.createTextNode(tail));
    node.parentNode.replaceChild(frag, node);
  }
}
function _findDocIdx(kind, exoStr) {
  if (!correctionsList || !correctionsList.length) return -1;
  if (exoStr != null) {
    const exact = correctionsList.findIndex(c => (c.kind || "") === kind && String(c.exo || "") === String(exoStr));
    if (exact >= 0) return exact;
    console.warn("_findDocIdx: pas de doc kind=%s exo=%s, fallback 1er du kind", kind, exoStr);
  }
  return correctionsList.findIndex(c => (c.kind || "") === kind);
}
function jumpToCorrigePage(pageN, kind, opts = {}) {
  if (!correctionsList || !correctionsList.length) return;
  let targetIdx = -1;
  if (Number.isInteger(opts.idx) && opts.idx >= 0 && opts.idx < correctionsList.length) {
    targetIdx = opts.idx;
  } else if (opts.exo != null) {
    targetIdx = _findDocIdx(kind, opts.exo);
  } else {
    targetIdx = correctionsList.findIndex(c => (c.kind || "") === kind);
  }
  if (targetIdx < 0) targetIdx = corrigeIdx;
  const item = correctionsList[targetIdx];
  if (!item) return;
  const total = (item.pages || []).length;
  const safePage = Math.min(Math.max(1, pageN), Math.max(1, total));
  const tab = document.querySelector('#sidebar-tabs .sb-tab[data-tab="corrige"]');
  if (tab && !tab.classList.contains("active")) tab.click();
  showCorrige(targetIdx, safePage - 1);
}
function renderMathIn(element) {
  if (!element) return;
  if (typeof renderMathInElement !== "function") {
    return;
  }
  try {
    renderMathInElement(element, {
      delimiters: [{
        left: "$$",
        right: "$$",
        display: true
      }, {
        left: "$",
        right: "$",
        display: false
      }, {
        left: "\\(",
        right: "\\)",
        display: false
      }, {
        left: "\\[",
        right: "\\]",
        display: true
      }],
      throwOnError: false,
      strict: "ignore"
    });
  } catch (err) {
    console.warn("KaTeX render a échoué :", err);
  }
}
const TONE_PRESETS = [{
  emoji: "📝",
  label: "Plus concis",
  instr: "Reformule la dernière réponse en plus concis : 1-2 phrases max, garde l'essentiel."
}, {
  emoji: "➕",
  label: "Plus développé",
  instr: "Développe la dernière réponse : ajoute le contexte, les exemples, les nuances qui manquaient."
}, {
  emoji: "📖",
  label: "Avec exemple",
  instr: "Reprends la dernière réponse avec un exemple concret qui illustre le point."
}, {
  emoji: "🎯",
  label: "Plus simple",
  instr: "Reformule la dernière réponse de manière plus accessible, comme à quelqu'un qui découvre le sujet."
}, {
  emoji: "🔬",
  label: "Plus rigoureux",
  instr: "Reformule la dernière réponse de manière plus rigoureuse, avec les hypothèses et notations précises."
}, {
  emoji: "🔄",
  label: "Reformule",
  instr: "Reformule la dernière réponse autrement, en gardant le même niveau de détail."
}];
function appendToneToolbar(parentTurn) {
  const toolbar = document.createElement("div");
  toolbar.className = "tone-toolbar";
  const modifyWrap = document.createElement("div");
  modifyWrap.className = "tone-modify-wrap";
  const modifyBtn = document.createElement("button");
  modifyBtn.type = "button";
  modifyBtn.className = "tone-btn tone-btn-modify";
  modifyBtn.textContent = "🎛 Modifier ▾";
  modifyBtn.title = "Reformuler la dernière réponse du tuteur (concis, développé, exemple, plus simple, plus rigoureux, autre)";
  const popover = document.createElement("div");
  popover.className = "tone-modify-popover";
  popover.hidden = true;
  popover.setAttribute("role", "menu");
  for (const preset of TONE_PRESETS) {
    const a = document.createElement("button");
    a.type = "button";
    a.className = "tone-modify-action";
    const iconSpan = document.createElement("span");
    iconSpan.className = "tone-modify-icon";
    iconSpan.textContent = preset.emoji;
    const labelSpan = document.createElement("span");
    labelSpan.className = "tone-modify-label";
    labelSpan.textContent = preset.label;
    const hintSpan = document.createElement("span");
    hintSpan.className = "tone-modify-hint";
    hintSpan.textContent = preset.instr;
    a.appendChild(iconSpan);
    a.appendChild(labelSpan);
    a.appendChild(hintSpan);
    a.addEventListener("click", async e => {
      e.stopPropagation();
      popover.hidden = true;
      toolbar.querySelectorAll("button").forEach(b => b.disabled = true);
      try {
        await sendMetaInstruction(preset.instr, preset.label);
      } finally {
        toolbar.querySelectorAll("button").forEach(b => b.disabled = false);
      }
    });
    popover.appendChild(a);
  }
  modifyBtn.addEventListener("click", e => {
    e.stopPropagation();
    if (popover.hidden) {
      document.querySelectorAll(".tone-modify-popover:not([hidden])").forEach(p => {
        if (p !== popover) p.hidden = true;
      });
      popover.hidden = false;
      _positionToneModifyPopover(modifyBtn, popover);
      document.addEventListener("click", _onClickOutsideToneModify);
    } else {
      popover.hidden = true;
      document.removeEventListener("click", _onClickOutsideToneModify);
    }
  });
  modifyWrap.appendChild(modifyBtn);
  modifyWrap.appendChild(popover);
  toolbar.appendChild(modifyWrap);
  if (activeMode === "colle" || activeMode === "découverte" || activeMode === "guidé") {
    const coursBtn = document.createElement("button");
    coursBtn.className = "tone-btn tone-btn-cours";
    coursBtn.title = "Cherche dans tes cours : exo voisin pour t'entraîner + passage CM qui définit le concept (2 bulles séparées dans le dialogue)";
    coursBtn.textContent = "📚 Cours";
    coursBtn.addEventListener("click", () => {
      coursBtn.disabled = true;
      const claudeText = (parentTurn.dataset.rawText || parentTurn.textContent || "").trim();
      const lastStudent = _getLastStudentTextBefore(parentTurn);
      const desc = _buildContextualExoDescription(claudeText, lastStudent);
      Promise.allSettled([performFindSimilarExo({
        description: desc
      }), performFindCmPassage(desc)]).finally(() => {
        coursBtn.disabled = false;
      });
    });
    toolbar.appendChild(coursBtn);
    const ytBtn = document.createElement("button");
    ytBtn.className = "tone-btn tone-btn-yt";
    ytBtn.title = "Cherche une vidéo YouTube qui explique ce concept (chaînes éducatives FR)";
    ytBtn.textContent = "🎬 Vidéo";
    ytBtn.addEventListener("click", () => {
      ytBtn.disabled = true;
      const claudeText = (parentTurn.dataset.rawText || parentTurn.textContent || "").trim();
      const lastStudent = _getLastStudentTextBefore(parentTurn);
      const desc = _buildContextualExoDescription(claudeText, lastStudent);
      performFindYoutube(desc).finally(() => {
        ytBtn.disabled = false;
      });
    });
    toolbar.appendChild(ytBtn);
    const webBtn = document.createElement("button");
    webBtn.className = "tone-btn tone-btn-web";
    webBtn.title = "Cherche des ressources internet sur ce concept (sites éducatifs FR)";
    webBtn.textContent = "🌐 Internet";
    webBtn.addEventListener("click", () => {
      webBtn.disabled = true;
      const claudeText = (parentTurn.dataset.rawText || parentTurn.textContent || "").trim();
      const lastStudent = _getLastStudentTextBefore(parentTurn);
      const desc = _buildContextualExoDescription(claudeText, lastStudent);
      performWebSearchExo(desc).finally(() => {
        webBtn.disabled = false;
      });
    });
    toolbar.appendChild(webBtn);
  }
  parentTurn.appendChild(toolbar);
}
function _getLastStudentTextBefore(claudeTurn) {
  if (!claudeTurn) return "";
  let prev = claudeTurn.previousElementSibling;
  while (prev) {
    if (prev.classList && prev.classList.contains("turn") && prev.classList.contains("student") && !prev.classList.contains("marker")) {
      return (prev.dataset.rawText || prev.textContent || "").trim();
    }
    prev = prev.previousElementSibling;
  }
  return "";
}
function _appendOcrCollapsibleBlock(turnContainer, blk) {
  if (!turnContainer || !blk || !blk.ocr_markdown) return;
  const wrap = document.createElement("details");
  wrap.className = "ocr-collapsible";
  const completeness = blk.completeness_pct;
  const warnings = blk.warnings || [];
  const shouldExpand = warnings.length > 0 || typeof completeness === "number" && completeness < 80;
  if (shouldExpand) wrap.setAttribute("open", "open");
  const summary = document.createElement("summary");
  const kindLabel = blk.kind_detected || "?";
  let summaryText = `🔍 OCR pré-vérifié par Gemini Flash · ${kindLabel}`;
  if (typeof completeness === "number") {
    summaryText += ` · complétude ${completeness}%`;
  }
  if (warnings.length > 0) {
    summaryText += ` · ⚠ ${warnings.length} warning${warnings.length > 1 ? "s" : ""}`;
  }
  summary.textContent = summaryText;
  wrap.appendChild(summary);
  if (warnings.length > 0) {
    const warnEl = document.createElement("div");
    warnEl.className = "ocr-warnings";
    warnEl.textContent = "⚠ " + warnings.join(" · ");
    wrap.appendChild(warnEl);
  }
  const body = document.createElement("div");
  body.className = "ocr-body";
  body.innerHTML = renderMarkdown(blk.ocr_markdown);
  try {
    renderMathIn(body);
  } catch (_) {}
  wrap.appendChild(body);
  const hint = document.createElement("div");
  hint.className = "ocr-hint";
  hint.textContent = "Si cet OCR ne correspond pas à ce que tu as écrit, signale-le au Compagnon dans ton prochain message.";
  wrap.appendChild(hint);
  turnContainer.appendChild(wrap);
}
function _stripAttachmentMarkdown(text) {
  if (!text) return "";
  return text.replace(/!\[[^\]]*\]\([^)]*\)/g, "").replace(/\[Pièce jointe\s*:[^\]]*\]/g, "").replace(/\n{3,}/g, "\n\n").replace(/[ \t]+\n/g, "\n").trim();
}
function _buildContextualExoDescription(claudeText, studentText) {
  const truncate = (s, n) => s && s.length > n ? s.slice(0, n).trim() + "…" : (s || "").trim();
  const claudeClean = _stripAttachmentMarkdown(claudeText);
  const studentClean = _stripAttachmentMarkdown(studentText);
  const claudeQ = truncate(claudeClean, 800);
  const studentQ = truncate(studentClean, 400);
  let desc = "Le tuteur vient de me dire / demander :\n\n" + claudeQ;
  if (studentQ) {
    desc += "\n\nMa dernière intervention était :\n\n" + studentQ;
  }
  desc += "\n\nJe bloque pour répondre, trouve-moi dans mes cours un exercice voisin du même type pour m'entraîner avant de revenir à celui-ci.";
  return desc;
}
function _positionToneModifyPopover(btn, pop) {
  pop.classList.remove("drop-down");
  const popHeight = pop.offsetHeight || 280;
  const btnRect = btn.getBoundingClientRect();
  if (btnRect.top < popHeight + 10) {
    pop.classList.add("drop-down");
  }
}
function _onClickOutsideToneModify(ev) {
  let stillOpen = false;
  document.querySelectorAll(".tone-modify-popover:not([hidden])").forEach(p => {
    const wrap = p.parentElement;
    if (wrap && !wrap.contains(ev.target)) {
      p.hidden = true;
    } else {
      stillOpen = true;
    }
  });
  if (!stillOpen) {
    document.removeEventListener("click", _onClickOutsideToneModify);
  }
}
async function sendMetaInstruction(instr, label) {
  const chip = document.createElement("div");
  chip.className = "meta-chip";
  chip.textContent = `🎛️ ${label}`;
  dialogue.appendChild(chip);
  dialogue.scrollTop = dialogue.scrollHeight;
  try {
    const reading_state = typeof getReadingStateForSend === "function" ? getReadingStateForSend() : null;
    const r = await fetch("/api/send_message", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        text: instr,
        reading_state
      })
    });
    const data = await r.json();
    if (!r.ok) {
      alert("Erreur meta: " + (data.error || r.status));
      return;
    }
    streamResponse();
  } catch (e) {
    alert("Erreur réseau (meta): " + e.message);
  }
}
async function refreshQuota() {
  try {
    const r = await fetch("/api/quota");
    const data = await r.json();
    quotaContent.innerHTML = renderQuota(data);
  } catch (e) {
    quotaContent.textContent = "(quota indisponible)";
  }
}
function renderQuota(d) {
  if (d.error) return `<div>(${d.error})</div>`;
  const row = (label, pct, resetIso) => {
    if (pct == null) return "";
    const cls = pct >= 90 ? "err" : pct >= 70 ? "warn" : "";
    const resetTxt = formatResetCountdown(resetIso);
    const resetSpan = resetTxt ? `<span class="quota-reset" title="Réinit le ${formatResetAbsolute(resetIso)}">↻ ${resetTxt}</span>` : "";
    return `<div class="quota-row">` + `<div class="quota-row-head">${label} ${resetSpan}</div>` + `<span class="bar ${cls}"><span style="width:${Math.min(pct, 100)}%"></span></span>` + `<span class="quota-pct">${pct.toFixed(0)} %</span>` + `</div>`;
  };
  const proMaxBlock = [`<div class="quota-section-title">🤖 Claude Pro Max (CLI subscription)</div>`, row("Session 5h", d.session_pct, d.session_resets_at), row("Hebdo 7j", d.weekly_pct, d.weekly_resets_at), row("Hebdo Sonnet", d.weekly_sonnet_pct, d.weekly_sonnet_resets_at), row("Overage", d.extra_pct, null)].join("");
  const enginesBlock = renderEnginesStatus(d.engines);
  return proMaxBlock + enginesBlock;
}
function renderEnginesStatus(engineData) {
  if (!engineData || !engineData.engines) return "";
  const e = engineData.engines;
  const blocks = [];
  const ds = e.deepseek_api;
  if (ds) {
    if (!ds.key_present) {
      blocks.push(engineRow("💎", "DeepSeek", "—", "Pas de clé API configurée", null));
    } else if (ds.error) {
      blocks.push(engineRow("💎", "DeepSeek", "❌", `Erreur : ${ds.error}`, ds.billing_url));
    } else {
      const total = ds.total_balance;
      const granted = ds.granted_balance;
      const toppedUp = ds.topped_up_balance;
      const cur = ds.currency || "USD";
      const ok = ds.is_available && total != null && total > 0;
      const cls = !ok ? "err" : total < 0.5 ? "warn" : "";
      const detail = total != null ? `${total.toFixed(2)} ${cur} restants` + (granted || toppedUp ? ` (gratuit ${(granted || 0).toFixed(2)} + rechargé ${(toppedUp || 0).toFixed(2)})` : "") : "Solde indisponible";
      const pctVisual = total != null ? Math.min(100, total * 20) : 0;
      blocks.push(engineRowWithBar("💎", "DeepSeek", detail, pctVisual, cls, ds.billing_url, !ok));
    }
  }
  const fixedTierEntries = [["groq_api", e.groq_api, "⚡"], ["gemini_api", e.gemini_api, "✨"], ["api_anthropic", e.api_anthropic, "🧠"]];
  for (const [_id, info, icon] of fixedTierEntries) {
    if (!info) continue;
    if (!info.key_present) {
      blocks.push(engineRow(icon, info.label || _id, "—", "Pas de clé API configurée", info.billing_url));
      continue;
    }
    const limits = [];
    if (info.rpm) limits.push(`${info.rpm} RPM`);
    if (info.tpm) limits.push(`${info.tpm.toLocaleString("fr-FR")} TPM`);
    if (info.rpd) limits.push(`${info.rpd.toLocaleString("fr-FR")} RPD`);
    const detail = (info.tier_label || "") + (limits.length ? " · " + limits.join(" · ") : "");
    blocks.push(engineRow(icon, info.label || _id, "✓", detail, info.billing_url));
  }
  if (!blocks.length) return "";
  return `<div class="quota-section-title quota-section-engines">🔌 Autres moteurs</div>` + blocks.join("");
}
function engineRow(icon, label, statusEmoji, detail, billingUrl) {
  const linkPart = billingUrl ? ` · <a href="${billingUrl}" target="_blank" rel="noopener" class="engine-billing-link">⚙</a>` : "";
  return `<div class="engine-row">` + `<span class="engine-icon">${icon}</span>` + `<span class="engine-label">${escapeHtml(label)}</span>` + `<span class="engine-status">${statusEmoji}</span>` + `<span class="engine-detail">${escapeHtml(detail)}${linkPart}</span>` + `</div>`;
}
function engineRowWithBar(icon, label, detail, pct, cls, billingUrl, broken) {
  const linkPart = billingUrl ? ` <a href="${billingUrl}" target="_blank" rel="noopener" class="engine-billing-link" title="Recharger / configurer">⚙</a>` : "";
  return `<div class="engine-row engine-row-bar">` + `<div class="engine-row-head">` + `<span class="engine-icon">${icon}</span>` + `<span class="engine-label">${escapeHtml(label)}</span>` + `<span class="engine-detail">${escapeHtml(detail)}${linkPart}</span>` + `</div>` + (broken ? `<div class="engine-broken-hint">Solde épuisé (clic ⚙ pour recharger)</div>` : `<span class="bar ${cls}"><span style="width:${Math.min(pct, 100)}%"></span></span>`) + `</div>`;
}
function formatResetCountdown(iso) {
  if (!iso) return null;
  const reset = new Date(iso).getTime();
  const now = Date.now();
  let diffSec = Math.round((reset - now) / 1000);
  if (diffSec <= 0) return "imminent";
  const days = Math.floor(diffSec / 86400);
  diffSec -= days * 86400;
  const hours = Math.floor(diffSec / 3600);
  diffSec -= hours * 3600;
  const mins = Math.floor(diffSec / 60);
  if (days > 0) return `${days}j ${hours}h`;
  if (hours > 0) return `${hours}h${String(mins).padStart(2, "0")}`;
  return `${mins} min`;
}
function formatResetAbsolute(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString("fr-FR", {
      weekday: "short",
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit"
    });
  } catch (_) {
    return iso;
  }
}
function formatTurnTimeShort(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    const hhmm = d.toLocaleTimeString("fr-FR", {
      hour: "2-digit",
      minute: "2-digit"
    });
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    if (sameDay) return hhmm;
    const yest = new Date(now);
    yest.setDate(yest.getDate() - 1);
    if (d.toDateString() === yest.toDateString()) return `Hier ${hhmm}`;
    const sameYear = d.getFullYear() === now.getFullYear();
    const datePart = d.toLocaleDateString("fr-FR", sameYear ? {
      day: "numeric",
      month: "short"
    } : {
      day: "numeric",
      month: "short",
      year: "numeric"
    });
    return `${datePart} ${hhmm}`;
  } catch (_) {
    return "";
  }
}
function formatTurnTimeAbsolute(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString("fr-FR", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    });
  } catch (_) {
    return iso;
  }
}
setInterval(refreshQuota, QUOTA_POLL_MS);
refreshQuota();
async function refreshConnectionInfo() {
  const panel = $("#connection-content");
  if (!panel) return;
  try {
    const r = await fetch("/api/connection_info");
    if (!r.ok) {
      panel.innerHTML = `<div class="conn-row unavailable"><span class="conn-label">Erreur ${r.status}</span></div>`;
      return;
    }
    const data = await r.json();
    const port = data.port || 5680;
    const rows = [];
    if (data.lan_ip) {
      rows.push(makeConnRow("WiFi local (même réseau)", `http://${data.lan_ip}:${port}/`, true));
    } else {
      rows.push(makeConnRow("WiFi local", "non détecté", false));
    }
    if (data.tailscale_ip) {
      rows.push(makeConnRow("Tailscale tailnet (téléphone, autres machines)", `http://${data.tailscale_ip}:${port}/`, true));
    } else {
      rows.push(makeConnRow("Tailscale tailnet", "non détecté", false));
    }
    const fState = data.tailscale_funnel_state || "off";
    const fUrl = data.tailscale_funnel_live_url || data.tailscale_funnel || "";
    if (fState === "public") {
      rows.push(makeConnRow("🌐 Tailscale Funnel : exposé sur Internet", fUrl || "(URL inconnue)", !!fUrl));
    } else if (fState === "tailnet") {
      rows.push(makeConnRow("🔒 Tailscale serve : privé (tailnet uniquement)", fUrl || "(URL inconnue)", !!fUrl));
    } else if (data.tailscale_funnel) {
      rows.push(makeConnRow("⚪ Tailscale Funnel : coupé (config présente mais inactive)", data.tailscale_funnel, false));
    } else {
      rows.push(makeConnRow("⚪ Tailscale Funnel : non configuré", "voir _remote_access/SETUP_TAILSCALE_FUNNEL.md", false));
    }
    if (data.cloudflare_tunnel) {
      rows.push(makeConnRow("Cloudflare Tunnel (public, ton domaine)", data.cloudflare_tunnel, true));
    } else {
      rows.push(makeConnRow("Cloudflare Tunnel (public)", "non configuré, voir _remote_access/SETUP_CLOUDFLARE.md", false));
    }
    panel.innerHTML = "";
    if (data.basic_auth_enabled) {
      const banner = document.createElement("div");
      banner.className = "conn-auth-banner";
      banner.textContent = "🔐 Auth Basic activée : le navigateur demandera identifiant/mot " + "de passe sur les URLs publiques (Tailscale Funnel, Cloudflare Tunnel). " + "LAN et tailnet privé restent libres (skip 127.0.0.1/::1).";
      panel.appendChild(banner);
    }
    rows.forEach(rEl => panel.appendChild(rEl));
    const hint = document.createElement("div");
    hint.className = "conn-hint";
    hint.innerHTML = "💡 Ajoute <code>/mobile</code> à n'importe quelle URL pour la page " + "spéciale photo téléphone (capture rapide qui injecte dans la session " + "active).";
    panel.appendChild(hint);
  } catch (e) {
    panel.innerHTML = `<div class="conn-row unavailable"><span class="conn-label">Hors-ligne : ${e.message}</span></div>`;
  }
}
function makeConnRow(label, urlOrText, isClickable) {
  const row = document.createElement("div");
  row.className = "conn-row" + (isClickable ? "" : " unavailable");
  const labelEl = document.createElement("div");
  labelEl.className = "conn-label";
  labelEl.textContent = label;
  row.appendChild(labelEl);
  const urlEl = document.createElement("div");
  urlEl.className = "conn-url";
  urlEl.textContent = urlOrText;
  if (isClickable) {
    urlEl.title = "Cliquer pour ouvrir / Ctrl+clic pour copier";
    urlEl.addEventListener("click", e => {
      if (e.ctrlKey || e.metaKey) {
        navigator.clipboard.writeText(urlOrText).catch(() => {});
        return;
      }
      window.open(urlOrText, "_blank", "noopener");
    });
  }
  row.appendChild(urlEl);
  if (isClickable) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "conn-copy";
    btn.textContent = "📋 Copier l'URL";
    btn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(urlOrText);
        btn.textContent = "✓ Copié";
        btn.classList.add("copied");
        setTimeout(() => {
          btn.textContent = "📋 Copier l'URL";
          btn.classList.remove("copied");
        }, 1500);
      } catch (_) {
        btn.textContent = "Échec";
      }
    });
    row.appendChild(btn);
  }
  return row;
}
refreshConnectionInfo();
setInterval(refreshConnectionInfo, 30_000);
(function setupAutoAdvanceUI() {
  const remindBtn = document.getElementById("guided-remind-nav-btn");
  if (!remindBtn) return;
  remindBtn.addEventListener("click", async () => {
    remindBtn.disabled = true;
    const wasActivation = remindBtn.textContent.includes("Activer");
    remindBtn.textContent = wasActivation ? "⏳ Activation…" : "⏳ Rappel envoyé…";
    try {
      const r = await fetch("/api/auto_advance/remind", {
        method: "POST"
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        alert((wasActivation ? "Activation" : "Rappel") + " échoué : " + (d.error || r.status));
        showRemindNavBtnIfActive(!wasActivation);
        remindBtn.disabled = false;
        return;
      }
      remindBtn.textContent = wasActivation ? "✓ Activé" : "✓ Rappelé";
      const sysMsg = wasActivation ? "🤖 Auto-navigation activée : le tuteur peut désormais faire avancer la slide lui-même via NEXT_SLIDE." : "🤖 Rappel auto-nav envoyé au tuteur.";
      appendTurn("system", sysMsg);
      setTimeout(() => {
        showRemindNavBtnIfActive(true);
        remindBtn.disabled = false;
      }, 1500);
    } catch (e) {
      alert("Erreur réseau : " + e.message);
      showRemindNavBtnIfActive(!wasActivation);
      remindBtn.disabled = false;
    }
  });
})();
function showRemindNavBtnIfActive(autoAdvance) {
  const remindBtn = document.getElementById("guided-remind-nav-btn");
  if (!remindBtn) return;
  if (activeMode !== "guidé") {
    remindBtn.hidden = true;
    return;
  }
  remindBtn.hidden = false;
  remindBtn.textContent = autoAdvance ? "🤖 Rappeler nav au tuteur" : "🤖 Activer auto-nav";
  remindBtn.title = autoAdvance ? "Réinjecte le rappel auto-advance dans la conv (utile si le tuteur a oublié)." : "Active l'auto-advance pour la session courante (le tuteur fera avancer la slide lui-même).";
}
(function setupSidebarTabs() {
  const tabs = document.querySelectorAll("#sidebar-tabs .sb-tab");
  const panes = document.querySelectorAll("#sidebar-tab-content .sb-pane");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.tab;
      tabs.forEach(t => t.classList.toggle("active", t === tab));
      panes.forEach(p => p.classList.toggle("active", p.dataset.pane === target));
      if (target === "notes" && typeof refreshSavedNotes === "function") {
        refreshSavedNotes();
      }
      if (target === "photos" && typeof refreshSessionPhotos === "function") {
        refreshSessionPhotos();
      }
      if (target === "stickies" && typeof refreshStickies === "function") {
        refreshStickies();
      }
      if (target === "corrige" && typeof refreshDynamicOutline === "function") {
        refreshDynamicOutline();
      }
    });
  });
})();
const formMatiere = startForm.querySelector('[name="matiere"]');
const formType = startForm.querySelector('[name="type"]');
const formNum = startForm.querySelector('[name="num"]');
const formAnnee = startForm.querySelector('[name="annee"]');
const formExo = startForm.querySelector('[name="exo"]');
const formRescan = $("#form-rescan");
let cascadeMuted = false;
function _setOptions(selectEl, values, placeholder) {
  if (!selectEl) return;
  const prev = selectEl.value;
  selectEl.innerHTML = "";
  const ph = document.createElement("option");
  ph.value = "";
  ph.textContent = placeholder;
  selectEl.appendChild(ph);
  for (const v of values) {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    selectEl.appendChild(opt);
  }
  if (prev && values.includes(prev)) {
    selectEl.value = prev;
  } else {
    selectEl.value = "";
  }
}
function _disableCascadeBelow(level) {
  const order = ["matiere", "type", "num", "annee", "exo"];
  const idx = order.indexOf(level);
  if (idx < 0) return;
  const tail = order.slice(idx + 1);
  for (const name of tail) {
    const el = startForm.querySelector(`[name="${name}"]`);
    if (!el) continue;
    el.disabled = true;
    el.innerHTML = `<option value="">${name === "annee" ? "—" : name === "exo" ? "Exo…" : name === "num" ? "N°…" : "Type…"}</option>`;
    el.value = "";
  }
}
async function fetchCoursOptions(filters) {
  const qs = new URLSearchParams(filters).toString();
  try {
    const r = await fetch(`/api/cours_options?${qs}`);
    if (!r.ok) return null;
    return await r.json();
  } catch (e) {
    console.warn("cours_options fetch failed:", e);
    return null;
  }
}
async function cascadeFromMatiere(autoSelect = {}) {
  cascadeMuted = true;
  try {
    const m = formMatiere.value;
    if (!m) {
      _disableCascadeBelow("matiere");
      return;
    }
    const data = await fetchCoursOptions({
      matiere: m
    });
    if (!data) {
      _disableCascadeBelow("matiere");
      return;
    }
    _setOptions(formType, data.types || [], "Type…");
    formType.disabled = !(data.types || []).length;
    _disableCascadeBelow("type");
    if (autoSelect.type && (data.types || []).includes(autoSelect.type)) {
      formType.value = autoSelect.type;
      await cascadeFromType(autoSelect);
    }
  } finally {
    cascadeMuted = false;
  }
}
async function cascadeFromType(autoSelect = {}) {
  cascadeMuted = true;
  try {
    const m = formMatiere.value;
    const t = formType.value;
    if (!m || !t) {
      _disableCascadeBelow("type");
      return;
    }
    const data = await fetchCoursOptions({
      matiere: m,
      type: t
    });
    if (!data) {
      _disableCascadeBelow("type");
      return;
    }
    _setOptions(formNum, data.nums || [], "N°…");
    formNum.disabled = !(data.nums || []).length;
    formAnnee.hidden = t !== "CC";
    formAnnee.disabled = true;
    formAnnee.innerHTML = '<option value="">—</option>';
    formAnnee.value = "";
    formExo.disabled = true;
    formExo.innerHTML = '<option value="">Exo…</option>';
    formExo.value = "";
    if (autoSelect.num && (data.nums || []).includes(autoSelect.num)) {
      formNum.value = autoSelect.num;
      await cascadeFromNum(autoSelect);
    }
  } finally {
    cascadeMuted = false;
  }
}
async function cascadeFromNum(autoSelect = {}) {
  cascadeMuted = true;
  try {
    const m = formMatiere.value;
    const t = formType.value;
    const n = formNum.value;
    if (!m || !t || !n) {
      _disableCascadeBelow("num");
      return;
    }
    const data = await fetchCoursOptions({
      matiere: m,
      type: t,
      num: n
    });
    if (!data) {
      _disableCascadeBelow("num");
      return;
    }
    if (t === "CC") {
      _setOptions(formAnnee, data.annees || [], "—");
      formAnnee.hidden = false;
      formAnnee.disabled = !(data.annees || []).length;
      if ((data.annees || []).length === 1) {
        formAnnee.value = data.annees[0];
        await cascadeFromAnnee(autoSelect);
        return;
      }
      if (autoSelect.annee && (data.annees || []).includes(autoSelect.annee)) {
        formAnnee.value = autoSelect.annee;
        await cascadeFromAnnee(autoSelect);
        return;
      }
      formExo.disabled = true;
      formExo.innerHTML = '<option value="">Exo…</option>';
      return;
    }
    _setOptions(formExo, data.exos || [], "Exo…");
    formExo.disabled = !(data.exos || []).length;
    if (autoSelect.exo && (data.exos || []).includes(autoSelect.exo)) {
      formExo.value = autoSelect.exo;
    }
  } finally {
    cascadeMuted = false;
  }
}
async function cascadeFromAnnee(autoSelect = {}) {
  cascadeMuted = true;
  try {
    const m = formMatiere.value;
    const t = formType.value;
    const n = formNum.value;
    const a = formAnnee.value;
    if (!m || !t || !n) return;
    const data = await fetchCoursOptions({
      matiere: m,
      type: t,
      num: n,
      annee: a
    });
    if (!data) return;
    _setOptions(formExo, data.exos || [], "Exo…");
    formExo.disabled = !(data.exos || []).length;
    if (autoSelect.exo && (data.exos || []).includes(autoSelect.exo)) {
      formExo.value = autoSelect.exo;
    }
  } finally {
    cascadeMuted = false;
  }
}
const formSource = startForm.querySelector('[name="source"]');
const formDroitMatiere = startForm.querySelector('[name="droit_matiere"]');
const formDroitType = startForm.querySelector('[name="droit_type"]');
const formDroitNum = startForm.querySelector('[name="droit_num"]');
function isDroitSource() {
  return !!(formSource && formSource.value === "droit");
}
function applySourceMode() {
  const droit = isDroitSource();
  for (const el of [formMatiere, formType, formNum, formAnnee, formExo]) {
    if (!el) continue;
    el.hidden = droit;
    if (droit) el.disabled = true;
  }
  for (const el of [formDroitMatiere, formDroitType, formDroitNum]) {
    if (!el) continue;
    el.hidden = !droit;
    el.disabled = !droit;
  }
  const caEl = startForm.querySelector('[name="corrige_anchor"]');
  if (caEl && droit) {
    caEl.hidden = true;
    caEl.disabled = true;
  }
  const igEl = startForm.querySelector('[name="ignore_enonce"]');
  const igLabel = igEl ? igEl.closest("label") : null;
  if (igLabel) igLabel.hidden = droit;
  const sjEl0 = startForm.querySelector('[name="sujet_libre_mode"]');
  const sjLabel = sjEl0 ? sjEl0.closest("label") : null;
  if (sjLabel) sjLabel.hidden = droit;
  if (droit && sjEl0 && sjEl0.checked) {
    sjEl0.checked = false;
    sjEl0.dispatchEvent(new Event("change", {
      bubbles: true
    }));
  }
  if (droit && formDroitMatiere && formDroitMatiere.options.length <= 1) {
    cascadeDroitRoot();
  }
}
async function fetchDroitOptions(filters) {
  const qs = new URLSearchParams(filters).toString();
  try {
    const r = await fetch(`/api/droit_options?${qs}`);
    if (!r.ok) return null;
    return await r.json();
  } catch (e) {
    console.warn("droit_options fetch failed:", e);
    return null;
  }
}
async function cascadeDroitRoot(autoSelect = {}) {
  const data = await fetchDroitOptions({});
  if (!data || !formDroitMatiere) return;
  _setOptions(formDroitMatiere, data.matieres || [], "Matière…");
  formDroitMatiere.disabled = false;
  if (formDroitType) {
    formDroitType.disabled = true;
    formDroitType.innerHTML = '<option value="">Type…</option>';
  }
  if (formDroitNum) {
    formDroitNum.disabled = true;
    formDroitNum.innerHTML = '<option value="">N°…</option>';
  }
  if (autoSelect.matiere && (data.matieres || []).includes(autoSelect.matiere)) {
    formDroitMatiere.value = autoSelect.matiere;
    await cascadeDroitFromMatiere(autoSelect);
  }
}
async function cascadeDroitFromMatiere(autoSelect = {}) {
  cascadeMuted = true;
  try {
    const m = formDroitMatiere ? formDroitMatiere.value : "";
    if (!m) {
      if (formDroitType) {
        formDroitType.disabled = true;
        formDroitType.innerHTML = '<option value="">Type…</option>';
      }
      if (formDroitNum) {
        formDroitNum.disabled = true;
        formDroitNum.innerHTML = '<option value="">N°…</option>';
      }
      return;
    }
    const data = await fetchDroitOptions({
      matiere: m
    });
    if (!data) return;
    _setOptions(formDroitType, data.types || [], "Type…");
    formDroitType.disabled = !(data.types || []).length;
    if (formDroitNum) {
      formDroitNum.disabled = true;
      formDroitNum.innerHTML = '<option value="">N°…</option>';
    }
    if (autoSelect.type && (data.types || []).includes(autoSelect.type)) {
      formDroitType.value = autoSelect.type;
      await cascadeDroitFromType(autoSelect);
    }
  } finally {
    cascadeMuted = false;
  }
}
async function cascadeDroitFromType(autoSelect = {}) {
  cascadeMuted = true;
  try {
    const m = formDroitMatiere ? formDroitMatiere.value : "";
    const t = formDroitType ? formDroitType.value : "";
    if (!m || !t) {
      if (formDroitNum) {
        formDroitNum.disabled = true;
        formDroitNum.innerHTML = '<option value="">N°…</option>';
      }
      return;
    }
    const data = await fetchDroitOptions({
      matiere: m,
      type: t
    });
    if (!data) return;
    _setOptions(formDroitNum, data.nums || [], "N°…");
    formDroitNum.disabled = !(data.nums || []).length;
    if (autoSelect.num && (data.nums || []).includes(autoSelect.num)) {
      formDroitNum.value = autoSelect.num;
    }
  } finally {
    cascadeMuted = false;
  }
}
if (formSource) formSource.addEventListener("change", applySourceMode);
if (formDroitMatiere) formDroitMatiere.addEventListener("change", () => {
  if (!cascadeMuted) cascadeDroitFromMatiere();
});
if (formDroitType) formDroitType.addEventListener("change", () => {
  if (!cascadeMuted) cascadeDroitFromType();
});
if (formMatiere) formMatiere.addEventListener("change", () => {
  if (!cascadeMuted) cascadeFromMatiere();
});
if (formType) formType.addEventListener("change", () => {
  if (!cascadeMuted) cascadeFromType();
});
if (formNum) formNum.addEventListener("change", () => {
  if (!cascadeMuted) cascadeFromNum();
});
if (formAnnee) formAnnee.addEventListener("change", () => {
  if (!cascadeMuted) cascadeFromAnnee();
});
async function rescanFormOptions() {
  const current = {
    matiere: formMatiere.value,
    type: formType.value,
    num: formNum.value,
    annee: formAnnee.value,
    exo: formExo.value
  };
  const data = await fetchCoursOptions({});
  if (!data) return;
  _setOptions(formMatiere, data.matieres || [], "Matière…");
  if (current.matiere && (data.matieres || []).includes(current.matiere)) {
    formMatiere.value = current.matiere;
    await cascadeFromMatiere(current);
  } else {
    _disableCascadeBelow("matiere");
  }
}
if (formRescan) formRescan.addEventListener("click", rescanFormOptions);
async function syncFormToSession(data) {
  if (!data || !startForm) return;
  if (String(data.source || "").toLowerCase() === "droit") {
    if (formSource) {
      formSource.value = "droit";
      applySourceMode();
    }
    await cascadeDroitRoot({
      matiere: String(data.droit_matiere || data.matiere || ""),
      type: String(data.type || "").toUpperCase(),
      num: String(data.num || "")
    });
    const modeElD = startForm.querySelector('[name="mode"]');
    if (modeElD && data.mode) modeElD.value = data.mode;
    return;
  }
  if (formSource && formSource.value !== "cours") {
    formSource.value = "cours";
    applySourceMode();
  }
  const m = String(data.matiere || "").toUpperCase();
  const sjEl = startForm.querySelector('[name="sujet_libre_mode"]');
  if (m === "LIBRE") {
    if (sjEl && !sjEl.checked) {
      sjEl.checked = true;
      sjEl.dispatchEvent(new Event("change", {
        bubbles: true
      }));
    }
    const ta = document.querySelector("#start-form-sujet-libre-text");
    if (ta && data.sujet_libre) ta.value = data.sujet_libre;
    return;
  }
  if (m === "WORKSPACE") {
    return;
  }
  if (sjEl && sjEl.checked) {
    sjEl.checked = false;
    sjEl.dispatchEvent(new Event("change", {
      bubbles: true
    }));
  }
  const autoSelect = {
    matiere: m,
    type: String(data.type || "").toUpperCase(),
    num: String(data.num || ""),
    annee: String(data.annee || ""),
    exo: String(data.exo || "")
  };
  if (autoSelect.matiere && formMatiere) {
    const options = Array.from(formMatiere.options || []).map(o => o.value);
    if (options.includes(autoSelect.matiere)) {
      formMatiere.value = autoSelect.matiere;
      await cascadeFromMatiere(autoSelect);
    }
  }
  const modeEl = startForm.querySelector('[name="mode"]');
  if (modeEl && data.mode) modeEl.value = data.mode;
  const cfEl = startForm.querySelector('[name="colle_format"]');
  if (cfEl && data.colle_format) cfEl.value = data.colle_format;
  const caEl = startForm.querySelector('[name="corrige_anchor"]');
  if (caEl && data.corrige_anchor) caEl.value = data.corrige_anchor;
}
(async function initFormOptions() {
  const params = new URLSearchParams(window.location.search);
  const auto = {
    matiere: params.get("matiere") || "",
    type: params.get("type") || "",
    num: params.get("num") || "",
    annee: params.get("annee") || "",
    exo: params.get("exo") || ""
  };
  const data = await fetchCoursOptions({});
  if (!data) return;
  _setOptions(formMatiere, data.matieres || [], "Matière…");
  if (auto.matiere && (data.matieres || []).includes(auto.matiere)) {
    formMatiere.value = auto.matiere;
    await cascadeFromMatiere(auto);
  }
  const sourceParam = (params.get("source") || "").toLowerCase();
  if (sourceParam === "droit" && formSource) {
    formSource.value = "droit";
    applySourceMode();
    await cascadeDroitRoot({
      matiere: params.get("matiere") || "",
      type: (params.get("type") || "").toUpperCase(),
      num: params.get("num") || ""
    });
  }
  if (params.get("mode")) {
    const modeEl = startForm.querySelector('[name="mode"]');
    if (modeEl) modeEl.value = params.get("mode");
  }
  const cfParam = (params.get("colle_format") || "").toLowerCase();
  if (cfParam && ["oral", "photos", "mixte"].includes(cfParam)) {
    const cfEl = startForm.querySelector('[name="colle_format"]');
    if (cfEl) cfEl.value = cfParam;
  }
  let caParam = (params.get("corrige_anchor") || "").toLowerCase();
  if (["sans_corrigé", "sans_corrige"].includes(caParam)) caParam = "aucun";
  if (caParam && ["strict", "consultatif", "aucun"].includes(caParam)) {
    const caEl = startForm.querySelector('[name="corrige_anchor"]');
    if (caEl) caEl.value = caParam;
  }
  {
    const ieEl = startForm.querySelector('[name="ignore_enonce"]');
    if (ieEl) ieEl.checked = false;
  }
  const sujetLibreParam = params.get("sujet_libre") || "";
  if (sujetLibreParam.trim()) {
    const sjEl = startForm.querySelector('[name="sujet_libre_mode"]');
    if (sjEl) {
      sjEl.checked = true;
    }
    const ta = document.querySelector("#start-form-sujet-libre-text");
    if (ta) ta.value = sujetLibreParam;
    setTimeout(() => _toggleSujetLibreZone(), 50);
  }
  const wsRoot = (params.get("workspace_root") || "").trim();
  if (wsRoot) {
    window._pendingWorkspace = {
      workspace_root: wsRoot,
      workspace_focus_subdir: (params.get("workspace_focus_subdir") || "").trim(),
      workspace_excludes: (params.get("workspace_excludes") || "").trim()
    };
  }
  const modeEl = startForm.querySelector('[name="mode"]');
  const cfEl = startForm.querySelector('[name="colle_format"]');
  const caEl = startForm.querySelector('[name="corrige_anchor"]');
  function _refreshColleFormatSelectVisibility() {
    const m = modeEl ? modeEl.value : "colle";
    const isVisible = m === "colle" || m === "découverte";
    if (cfEl) {
      cfEl.hidden = !isVisible;
      cfEl.disabled = !isVisible;
    }
    if (caEl) {
      caEl.hidden = !isVisible;
      caEl.disabled = !isVisible;
    }
  }
  if (modeEl) modeEl.addEventListener("change", _refreshColleFormatSelectVisibility);
  _refreshColleFormatSelectVisibility();
  const sjEl = startForm.querySelector('[name="sujet_libre_mode"]');
  if (sjEl) {
    sjEl.addEventListener("change", _toggleSujetLibreZone);
    _toggleSujetLibreZone();
  }
  if ((params.get("autostart") || "") === "1") {
    try {
      const cleanUrl = new URL(window.location.href);
      cleanUrl.searchParams.delete("autostart");
      history.replaceState({}, "", cleanUrl.toString());
    } catch (_) {}
    setTimeout(() => {
      if (typeof restoreActiveSessionIfAny === "function" && activeSession) {
        return;
      }
      try {
        startForm.dispatchEvent(new Event("submit", {
          cancelable: true,
          bubbles: true
        }));
      } catch (_) {
        const submitBtn = startForm.querySelector("button[type='submit']");
        if (submitBtn) submitBtn.click();
      }
    }, 350);
  }
})();
(function _wireFormToggleWarnings() {
  const wrapper = document.getElementById("form-toggle-warnings");
  const form = document.getElementById("start-form");
  if (!wrapper || !form) return;
  const refreshWrapper = () => {
    const anyShown = wrapper.querySelectorAll(".form-toggle-warning:not([hidden])").length > 0;
    wrapper.hidden = !anyShown;
  };
  const wireOne = name => {
    const cb = form.querySelector(`[name="${name}"]`);
    const warn = wrapper.querySelector(`.form-toggle-warning[data-for="${name}"]`);
    if (!cb || !warn) return;
    const apply = () => {
      warn.hidden = !cb.checked;
      refreshWrapper();
    };
    cb.addEventListener("change", apply);
    apply();
  };
  wireOne("ignore_enonce");
  wireOne("sujet_libre_mode");
})();
async function restoreActiveSessionIfAny() {
  try {
    const r = await fetch("/api/current_session");
    if (!r.ok) return;
    const data = await r.json();
    if (!data.active) return;
    activeSession = data.session_id;
    activeMode = data.mode || "colle";
    applyColleFormatChips(data.colle_format || "mixte");
    applyCorrigeAnchorChips(data.corrige_anchor || "strict");
    try {
      await syncFormToSession(data);
    } catch (_) {}
    const phase = data.phase || "active";
    inDebrief = phase === "debrief";
    const phaseSuffix = inDebrief ? " [🎓 débrief]" : phase === "closed" ? " [fermée]" : " [restauré]";
    sessionInfo.textContent = `→ ${data.session_id} (engine: ${data.engine || "?"})${phaseSuffix}`;
    rerenderDialogueFromTranscript(data.transcript || []);
    userInput.disabled = false;
    sendBtn.disabled = false;
    endBtn.disabled = false;
    if (exportRecapBtn) exportRecapBtn.disabled = false;
    micBtn.disabled = false;
    if (mediaBtn) mediaBtn.disabled = false;
    if (photoBtn) photoBtn.disabled = false;
    refreshRewriteBtnState();
    refreshFindExoBtnState();
    if (activeMode === "guidé") {
      const startIdx = Number.isInteger(data.guided_index) ? data.guided_index : 0;
      initGuidedPanel(startIdx);
    }
    showRemindNavBtnIfActive(!!data.auto_advance);
    initCorrectionsPanel();
  } catch (e) {
    console.warn("restoreActiveSessionIfAny a échoué :", e);
  }
}
restoreActiveSessionIfAny();
async function detectUserRole() {
  try {
    const r = await fetch("/api/role");
    if (!r.ok) return;
    const data = await r.json();
    userRole = data && data.role || "owner";
  } catch (_) {}
  if (userRole === "viewer") applyViewerMode();
}
function applyViewerMode() {
  const banner = document.createElement("div");
  banner.id = "viewer-banner";
  banner.textContent = "🔒 Mode partagé (lecture seule) : vous voyez la session en direct, " + "vous ne pouvez pas modifier ni envoyer de message.";
  const main = document.getElementById("dialogue");
  if (main) main.insertBefore(banner, main.firstChild);
  if (startForm) startForm.style.display = "none";
  const inputFooter = document.getElementById("dialogue-input");
  if (inputFooter) inputFooter.style.display = "none";
  if (endBtn) endBtn.style.display = "none";
  if (recordIndicator) recordIndicator.style.display = "none";
  const engineWrap = document.getElementById("engine-switcher-wrap");
  if (engineWrap) engineWrap.style.display = "none";
  const style = document.createElement("style");
  style.textContent = `
    .turn-actions, .tone-toolbar,
    .turn-edit-area, .turn-branch-nav,
    .suggested-edit .se-actions,
    #attachments-tray,
    #guided-nav,
    #guided-remind-nav-btn,
    #corrige-nav,
    #corrige-picker { display: none !important; }
    #viewer-banner {
      background: rgba(255, 200, 50, 0.12);
      border-bottom: 1px solid rgba(255, 200, 50, 0.40);
      color: var(--fg, #e6e6e6);
      padding: 8px 14px;
      font-size: 12px; line-height: 1.4;
    }
  `;
  document.head.appendChild(style);
  startViewerPolling();
}
async function viewerRefreshTranscript() {
  try {
    const r = await fetch("/api/current_session");
    if (!r.ok) return;
    const data = await r.json();
    if (!data.active) {
      if (dialogue.querySelector(".placeholder")) return;
      dialogue.innerHTML = '<p class="placeholder">Pas de session active actuellement. ' + 'Le owner doit en démarrer une.</p>';
      return;
    }
    activeSession = data.session_id;
    activeMode = data.mode || "colle";
    applyColleFormatChips(data.colle_format || "mixte");
    applyCorrigeAnchorChips(data.corrige_anchor || "strict");
    if (sessionInfo) {
      sessionInfo.textContent = `→ ${data.session_id} (engine: ${data.engine || "?"}) [viewer]`;
    }
    rerenderDialogueFromTranscript(data.transcript || []);
    if (activeMode === "guidé") {
      const startIdx = Number.isInteger(data.guided_index) ? data.guided_index : 0;
      if (!guidedSlides.length) {
        initGuidedPanel(startIdx);
      } else if (startIdx !== guidedIndex) {
        showGuidedSlide(startIdx, false);
      }
    }
    if (!correctionsList.length) initCorrectionsPanel();
  } catch (e) {}
}
function startViewerPolling() {
  if (viewerPollHandle !== null) return;
  viewerRefreshTranscript();
  viewerPollHandle = setInterval(viewerRefreshTranscript, 5000);
}
detectUserRole();
startForm.addEventListener("submit", async e => {
  e.preventDefault();
  const fd = new FormData(startForm);
  const body = Object.fromEntries(fd.entries());
  if (formSource && formSource.value === "droit") {
    body.source = "droit";
    body.matiere = (body.droit_matiere || "").trim();
    body.type = (body.droit_type || "").trim();
    body.num = (body.droit_num || "").trim();
    body.exo = "full";
    body.corrige_anchor = "aucun";
    if (!body.matiere || !body.type || !body.num) {
      alert("Choisis la matière, le type (CM/TD) et la séance de droit avant de lancer.");
      return;
    }
  }
  if (window._pendingWorkspace && window._pendingWorkspace.workspace_root) {
    body.workspace_root = window._pendingWorkspace.workspace_root;
    if (window._pendingWorkspace.workspace_focus_subdir) {
      body.workspace_focus_subdir = window._pendingWorkspace.workspace_focus_subdir;
    }
    if (window._pendingWorkspace.workspace_excludes) {
      body.workspace_excludes = window._pendingWorkspace.workspace_excludes;
    }
  }
  const sjEl = startForm.querySelector('[name="sujet_libre_mode"]');
  if (sjEl && sjEl.checked) {
    const ta = document.querySelector("#start-form-sujet-libre-text");
    const sujetText = (ta ? ta.value : "").trim();
    if (!sujetText) {
      alert("Décris ton sujet en 1-3 phrases avant de lancer.");
      return;
    }
    body.sujet_libre = sujetText;
  }
  if (activeSession) {
    try {
      const r = await fetch("/api/current_session");
      if (r.ok) {
        const data = await r.json();
        if (data.active) {
          const norm = v => v == null ? "" : String(v).trim();
          const reqMode = norm(body.mode) || "colle";
          const reqFormat = norm(body.colle_format) || "mixte";
          const reqAnchor = norm(body.corrige_anchor) || "strict";
          const sMode = norm(data.mode) || "colle";
          const sFormat = norm(data.colle_format) || "mixte";
          const sAnchor = norm(data.corrige_anchor) || "strict";
          const sameContext = norm(data.matiere).toUpperCase() === norm(body.matiere).toUpperCase() && norm(data.type).toUpperCase() === norm(body.type).toUpperCase() && norm(data.num) === norm(body.num) && norm(data.exo) === norm(body.exo) && norm(data.annee) === norm(body.annee) && sMode === reqMode && sFormat === reqFormat && sAnchor === reqAnchor;
          if (sameContext) {
            const transcript = data.transcript || [];
            const existing = {
              session_id: data.session_id,
              matiere: data.matiere,
              type: data.type,
              num: data.num,
              exo: data.exo,
              annee: data.annee,
              mode: data.mode,
              colle_format: data.colle_format,
              corrige_anchor: data.corrige_anchor,
              n_exchanges: transcript.length,
              last_alive: data.last_alive || data.started_at || "",
              started_at: data.started_at || "",
              interrupted: !!data.interrupted,
              label: data.label
            };
            showStartConflictModal(existing, body);
            return;
          }
        }
      }
    } catch (_) {}
  }
  const existing = await findExistingSession(body);
  if (existing) {
    showStartConflictModal(existing, body);
    return;
  }
  await doStartSession(body);
});
async function _isCurrentSessionSameContext(body) {
  if (!activeSession) return false;
  try {
    const r = await fetch("/api/current_session");
    if (!r.ok) return false;
    const data = await r.json();
    if (!data.active) return false;
    const norm = v => v == null ? "" : String(v).trim();
    const reqMode = norm(body.mode) || "colle";
    const reqFormat = norm(body.colle_format) || "mixte";
    const reqAnchor = norm(body.corrige_anchor) || "strict";
    const sMode = norm(data.mode) || "colle";
    const sFormat = norm(data.colle_format) || "mixte";
    const sAnchor = norm(data.corrige_anchor) || "strict";
    return norm(data.matiere).toUpperCase() === norm(body.matiere).toUpperCase() && norm(data.type).toUpperCase() === norm(body.type).toUpperCase() && norm(data.num) === norm(body.num) && norm(data.exo) === norm(body.exo) && norm(data.annee) === norm(body.annee) && sMode === reqMode && sFormat === reqFormat && sAnchor === reqAnchor;
  } catch (_) {
    return false;
  }
}
function _toggleSujetLibreZone() {
  const sjEl = document.querySelector('[name="sujet_libre_mode"]');
  if (!sjEl) return;
  const active = sjEl.checked;
  const zone = document.querySelector("#sujet-libre-zone");
  if (zone) zone.hidden = !active;
  const startForm = document.querySelector("#start-form");
  if (startForm) {
    for (const name of ["matiere", "type", "num", "annee", "exo"]) {
      const el = startForm.querySelector(`[name="${name}"]`);
      if (el) el.disabled = active;
    }
    const modeEl = startForm.querySelector('[name="mode"]');
    if (modeEl) {
      const guidedOpt = modeEl.querySelector('option[value="guidé"]');
      if (guidedOpt) guidedOpt.disabled = active;
      if (active && modeEl.value === "guidé") {
        modeEl.value = "découverte";
        modeEl.dispatchEvent(new Event("change", {
          bubbles: true
        }));
      }
    }
  }
}
async function findExistingSession(body) {
  try {
    const r = await fetch("/api/sessions");
    if (!r.ok) return null;
    const data = await r.json();
    const list = Array.isArray(data.sessions) ? data.sessions : [];
    const norm = v => v == null ? "" : String(v).trim();
    const reqMode = norm(body.mode) || "colle";
    const reqFormat = norm(body.colle_format) || "mixte";
    const reqAnchor = norm(body.corrige_anchor) || "strict";
    const _normWs = p => norm(p).replace(/[\\/]+$/, "").replace(/\\/g, "/").toLowerCase();
    const reqWs = _normWs(body.workspace_root);
    const matches = list.filter(s => {
      if (reqWs) {
        return _normWs(s.workspace_root) === reqWs;
      }
      if (norm(s.matiere).toUpperCase() !== norm(body.matiere).toUpperCase()) return false;
      if (norm(s.type).toUpperCase() !== norm(body.type).toUpperCase()) return false;
      if (norm(s.num) !== norm(body.num)) return false;
      if (norm(s.exo) !== norm(body.exo)) return false;
      if (norm(s.annee) !== norm(body.annee)) return false;
      const sMode = norm(s.mode);
      const sFormat = norm(s.colle_format);
      const sAnchor = norm(s.corrige_anchor);
      if (sMode && sMode !== reqMode) return false;
      if (sFormat && sFormat !== reqFormat) return false;
      if (sAnchor && sAnchor !== reqAnchor) return false;
      return true;
    });
    if (!matches.length) return null;
    matches.sort((a, b) => {
      const ta = new Date(a.last_alive || a.started_at || 0).getTime();
      const tb = new Date(b.last_alive || b.started_at || 0).getTime();
      return tb - ta;
    });
    return matches[0];
  } catch (_) {
    return null;
  }
}
async function doStartSession(body) {
  try {
    const r = await fetch("/api/start_session", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body)
    });
    const data = await r.json();
    if (!r.ok) {
      alert("Erreur: " + (data.error || r.status));
      return;
    }
    activeSession = data.session_id;
    activeMode = body.mode || "colle";
    applyColleFormatChips(data.colle_format || body.colle_format || "mixte");
    applyCorrigeAnchorChips(data.corrige_anchor || body.corrige_anchor || "strict");
    sessionInfo.textContent = `→ ${data.session_id} (engine: ${data.engine})`;
    dialogue.innerHTML = "";
    userInput.disabled = false;
    sendBtn.disabled = false;
    endBtn.disabled = false;
    if (exportRecapBtn) exportRecapBtn.disabled = false;
    micBtn.disabled = false;
    if (mediaBtn) mediaBtn.disabled = false;
    if (photoBtn) photoBtn.disabled = false;
    refreshRewriteBtnState();
    refreshFindExoBtnState();
    if (activeMode === "guidé") {
      initGuidedPanel();
    }
    showRemindNavBtnIfActive(!!data.auto_advance);
    initCorrectionsPanel();
    streamResponse();
  } catch (e) {
    alert("Erreur réseau: " + e.message);
  }
}
function showStartConflictModal(existing, body) {
  const modal = $("#start-conflict-modal");
  const msg = $("#scm-msg");
  const meta = $("#scm-meta");
  const resumeBtn = $("#scm-resume-btn");
  const keepOldBtn = $("#scm-keep-old-btn");
  const overwriteBtn = $("#scm-overwrite-btn");
  const cancelBtn = $("#scm-cancel-btn");
  if (!modal || !msg || !meta) {
    if (confirm("Une session existe déjà pour cet exercice. " + "OK = reprendre, Annuler = démarrer (efface l'ancienne).")) {
      resumeSession(existing.session_id);
    } else {
      fetch(`/api/sessions/${encodeURIComponent(existing.session_id)}`, {
        method: "DELETE"
      }).finally(() => doStartSession(body));
    }
    return;
  }
  const exo = body.exo && body.exo !== "full" ? `ex${body.exo}` : "exfull";
  const ctxLabel = `${body.matiere || "?"} ${body.type || "?"}${body.num || "?"} ${exo}` + (body.annee ? ` ${body.annee}` : "");
  msg.textContent = `Une session pour ${ctxLabel} existe déjà. Tu peux la reprendre, ` + `en démarrer une nouvelle qui CONSERVE l'ancienne (recommandé, ` + `nouveau fichier suffixé _2/_3…), ou la SUPPRIMER pour repartir de zéro.`;
  const dateStr = (existing.last_alive || existing.started_at || "").slice(0, 16).replace("T", " ");
  const labelLine = existing.label ? `\n« ${existing.label} »` : "";
  meta.textContent = `${existing.session_id}${labelLine}\n` + `${existing.n_exchanges || 0} tour(s), mode ${existing.mode || "colle"}` + (existing.interrupted ? " (interrompue)" : "") + `\n` + `Dernière activité : ${dateStr || "(inconnue)"}`;
  modal.hidden = false;
  const cleanup = () => {
    modal.hidden = true;
    resumeBtn.onclick = null;
    if (keepOldBtn) keepOldBtn.onclick = null;
    overwriteBtn.onclick = null;
    cancelBtn.onclick = null;
  };
  resumeBtn.onclick = async () => {
    cleanup();
    await resumeSession(existing.session_id);
  };
  if (keepOldBtn) {
    keepOldBtn.onclick = async () => {
      cleanup();
      await doStartSession({
        ...body,
        force_new_session: true
      });
    };
  }
  overwriteBtn.onclick = async () => {
    const n = existing.n_exchanges || 0;
    const lastAct = (existing.last_alive || existing.started_at || "").slice(0, 16).replace("T", " ");
    const confirmMsg = `⚠ Cela va SUPPRIMER la session existante :\n\n` + `   ${existing.session_id}\n` + `   ${n} tour(s), dernière activité ${lastAct}\n\n` + `Tape OUI pour confirmer (un backup sera quand même créé dans _sessions/_trash/).`;
    const answer = window.prompt(confirmMsg, "");
    if (!answer || answer.trim().toUpperCase() !== "OUI") {
      return;
    }
    cleanup();
    try {
      await fetch(`/api/sessions/${encodeURIComponent(existing.session_id)}`, {
        method: "DELETE"
      });
    } catch (_) {}
    await doStartSession(body);
  };
  cancelBtn.onclick = () => cleanup();
}
function _onSendClickRouter() {
  if (isStreamingActive()) {
    openCancelStreamModal();
  } else {
    sendUserMessage();
  }
}
sendBtn.addEventListener("click", _onSendClickRouter);
userInput.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    _onSendClickRouter();
  }
});
function autoResizeUserInput() {
  userInput.style.height = "auto";
  userInput.style.height = userInput.scrollHeight + "px";
  userInput.scrollTop = userInput.scrollHeight;
}
userInput.addEventListener("input", autoResizeUserInput);
function detectWhisperRepetition(text) {
  if (!text) return null;
  const re = /\b([\wÀ-ÿ'’]+(?:[\s,]+[\wÀ-ÿ'’]+){0,3})(?:[\s,]+\1){4,}/i;
  const m = text.match(re);
  return m ? m[1].trim() : null;
}
function maybeFlagWhisperHallucination(text) {
  const motif = detectWhisperRepetition(text);
  if (!motif) {
    const old = document.getElementById("whisper-hallu-banner");
    if (old) old.remove();
    return;
  }
  let banner = document.getElementById("whisper-hallu-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "whisper-hallu-banner";
    banner.className = "whisper-hallu";
    const footer = document.getElementById("dialogue-input");
    footer.parentNode.insertBefore(banner, footer);
  }
  const safe = motif.replace(/[<>&]/g, c => ({
    "<": "&lt;",
    ">": "&gt;",
    "&": "&amp;"
  })[c]);
  banner.innerHTML = `⚠️ Whisper a halluciné une répétition (« <code>${safe}</code> »). ` + `Vous voulez nettoyer le texte avant d'envoyer ? ` + `<button type="button" id="whisper-hallu-clean">Nettoyer</button> ` + `<button type="button" id="whisper-hallu-dismiss">Ignorer</button>`;
  document.getElementById("whisper-hallu-clean").addEventListener("click", () => {
    const reGlob = new RegExp(`\\b(${motif.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})(?:[\\s,]+\\1){2,}`, "gi");
    userInput.value = userInput.value.replace(reGlob, "$1");
    autoResizeUserInput();
    banner.remove();
    userInput.focus();
  });
  document.getElementById("whisper-hallu-dismiss").addEventListener("click", () => {
    banner.remove();
    userInput.focus();
  });
}
async function sendUserMessage() {
  if (isRecording) {
    abortRecordingAndTranscribe();
  }
  const text = userInput.value.trim();
  const hasAttachments = !!(attachmentsTray && attachmentsTray.children.length > 0);
  if (!text && !hasAttachments) return;
  const slashMatch = text ? SLASH_COLLE_FORMAT_RE.exec(text) : null;
  if (slashMatch) {
    let fmt = slashMatch[1].toLowerCase();
    if (fmt === "photo") fmt = "photos";
    userInput.value = "";
    autoResizeUserInput();
    setColleFormat(fmt);
    return;
  }
  const slashAnchorMatch = text ? SLASH_CORRIGE_ANCHOR_RE.exec(text) : null;
  if (slashAnchorMatch) {
    const raw = slashAnchorMatch[1].toLowerCase().replace(/ /g, "_");
    userInput.value = "";
    autoResizeUserInput();
    setCorrigeAnchor(raw);
    return;
  }
  cancelPendingTranscribe();
  if (rewriteInFlightAbort) {
    try {
      rewriteInFlightAbort.abort();
    } catch (_) {}
    rewriteInFlightAbort = null;
  }
  userInput.value = "";
  autoResizeUserInput();
  let displayText = text;
  try {
    const r0 = await fetch("/api/pending_attachments");
    if (r0.ok) {
      const d0 = await r0.json();
      const atts = d0.attachments || [];
      if (atts.length > 0) {
        const lines = atts.map(a => a.is_image ? `![${a.original_name || a.filename}](${_relWithStoragePrefix(a)})` : `[Pièce jointe : ${a.original_name || a.filename} (${_relWithStoragePrefix(a)})]`);
        displayText = text ? text + "\n\n" + lines.join("\n") : lines.join("\n");
      }
    }
  } catch (_) {}
  const t = appendTurn("student", "");
  t.innerHTML = renderMarkdown(displayText);
  renderMathIn(t);
  if (t.parentElement) t.parentElement.dataset.rawText = displayText;
  const _removeOrphanStudentBubble = () => {
    try {
      const container = t && t.parentElement;
      if (container && container.parentElement) {
        container.parentElement.removeChild(container);
      }
    } catch (_) {}
  };
  try {
    const reading_state = typeof getReadingStateForSend === "function" ? getReadingStateForSend() : null;
    const r = await fetch("/api/send_message", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        text,
        reading_state
      })
    });
    if (!r.ok && r.status !== 202) {
      const data = await r.json().catch(() => ({}));
      _removeOrphanStudentBubble();
      alert("Erreur send: " + (data.error || r.status));
      return;
    }
    try {
      const data = await r.json().catch(() => ({}));
      const ocrBlocks = data.ocr_blocks || [];
      if (ocrBlocks.length > 0 && t && t.parentElement) {
        for (const blk of ocrBlocks) {
          _appendOcrCollapsibleBlock(t.parentElement, blk);
        }
      }
    } catch (_) {}
    refreshAttachmentsTray();
    if (typeof refreshSessionPhotos === "function") {
      refreshSessionPhotos();
    }
    streamResponse();
  } catch (e) {
    _removeOrphanStudentBubble();
    alert("Erreur réseau: " + e.message);
  }
}
let thinkingHandle = null;
let thinkingStartTs = 0;
let thinkingNode = null;
function startThinkingIndicator(parentTurn) {
  stopThinkingIndicator();
  if (!parentTurn) return;
  const node = document.createElement("div");
  node.className = "thinking-indicator";
  node.textContent = "🤔 Compagnon réfléchit… 0.0 s";
  parentTurn.appendChild(node);
  thinkingNode = node;
  thinkingStartTs = Date.now();
  const tick = () => {
    if (!thinkingNode) return;
    const elapsed = (Date.now() - thinkingStartTs) / 1000;
    let label, cls;
    if (elapsed < 30) {
      label = `🤔 Compagnon réfléchit… ${elapsed.toFixed(1)} s`;
      cls = "";
    } else if (elapsed < 60) {
      label = `🤔 Compagnon réfléchit… ${elapsed.toFixed(0)} s, anormalement long`;
      cls = "warn";
    } else if (elapsed < 120) {
      label = `⏳ ${elapsed.toFixed(0)} s, très long, peut-être bloqué (latence Claude ?)`;
      cls = "err";
    } else {
      const m = Math.floor(elapsed / 60);
      const s = Math.floor(elapsed % 60);
      label = `🛑 ${m} min ${s} s, probablement bloqué. Vérifie la console / Stop+Lancer.`;
      cls = "err pulse";
    }
    thinkingNode.textContent = label;
    thinkingNode.className = "thinking-indicator " + cls;
  };
  thinkingHandle = setInterval(tick, 250);
}
function stopThinkingIndicator() {
  if (thinkingHandle !== null) {
    clearInterval(thinkingHandle);
    thinkingHandle = null;
  }
  if (thinkingNode && thinkingNode.parentNode) {
    thinkingNode.parentNode.removeChild(thinkingNode);
  }
  thinkingNode = null;
}
function _cropperOptionsCommon() {
  const isTouchDevice = navigator.maxTouchPoints > 0 || "ontouchstart" in window;
  return {
    viewMode: 1,
    autoCropArea: 1,
    background: false,
    responsive: true,
    checkOrientation: true,
    dragMode: isTouchDevice ? "move" : "crop",
    minCropBoxWidth: 50,
    minCropBoxHeight: 50
  };
}
let _selectionToolbarEl = null;
let _selectionHideTimer = null;
const _SELECTION_MIN_CHARS = 3;
function _getSelectionInsideTurn() {
  const sel = window.getSelection && window.getSelection();
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return null;
  const text = sel.toString().trim();
  if (text.length < _SELECTION_MIN_CHARS) return null;
  const range = sel.getRangeAt(0);
  let node = range.commonAncestorContainer;
  if (node.nodeType === Node.TEXT_NODE) node = node.parentElement;
  let bubble = node;
  while (bubble && bubble !== document.body) {
    if (bubble.classList && bubble.classList.contains("turn") && (bubble.classList.contains("claude") || bubble.classList.contains("student"))) {
      break;
    }
    bubble = bubble.parentElement;
  }
  if (!bubble || bubble === document.body) return null;
  if (bubble.classList.contains("system")) return null;
  const role = bubble.classList.contains("student") ? "student" : "claude";
  const messageId = bubble.dataset?.msgId || null;
  return {
    text,
    range,
    bubbleEl: bubble,
    role,
    messageId
  };
}
function _ensureSelectionToolbar() {
  if (_selectionToolbarEl) return _selectionToolbarEl;
  const tb = document.createElement("div");
  tb.id = "selection-toolbar";
  tb.hidden = true;
  tb.innerHTML = `
    <button type="button" data-act="save" title="Sauvegarder dans 🔖 Notes">💾 Save</button>
    <button type="button" data-act="quote" title="Citer dans ma réponse">📋 Citer</button>
    <button type="button" data-act="explain" title="Demander une explication au tuteur">🤔 Explique</button>
    <button type="button" data-act="copy" title="Copier dans le presse-papier">📝 Copier</button>
    <button type="button" data-act="cahier-open-colors" title="Colorier la sélection (ouvre l'onglet 🎨 Couleurs)" class="cahier-toolbar-open" hidden>🎨 Colorier</button>
  `;
  document.body.appendChild(tb);
  tb.addEventListener("mousedown", e => e.preventDefault());
  tb.addEventListener("click", e => {
    const btn = e.target.closest("button");
    if (!btn) return;
    const act = btn.dataset.act;
    const info = _getSelectionInsideTurn();
    if (!info) return;
    if (act === "cahier-open-colors") {
      _openColorsTabForSelection(info);
      return;
    }
    _handleSelectionAction(act, info);
  });
  _selectionToolbarEl = tb;
  return tb;
}
function _isSelectionInCahierCard(range) {
  let node = range.commonAncestorContainer;
  if (node.nodeType === Node.TEXT_NODE) node = node.parentElement;
  while (node && node !== document.body) {
    if (node.classList && node.classList.contains("cahier-card")) return true;
    node = node.parentElement;
  }
  return false;
}
async function _applyCahierColor(info, tag) {
  const turn = info.bubbleEl;
  let rawText = turn.dataset.rawText || "";
  const selectedText = (info.text || "").trim();
  if (!selectedText) {
    alert("Sélection vide.");
    return;
  }
  const all = Array.from(dialogue.querySelectorAll(".turn.student, .turn.claude"));
  const index = all.indexOf(turn);
  if (index < 0) {
    alert("Bulle introuvable dans le transcript.");
    return;
  }
  let newText;
  if (tag === "clear") {
    const allTags = ["bleu", "rouge", "vert", "noir", "hl-jaune", "hl-vert", "hl-rose", "hl-violet"];
    newText = rawText;
    let stripped = false;
    for (const t of allTags) {
      const escSel = selectedText.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const re = new RegExp(`\\{${t}\\}(\\s*${escSel}\\s*)\\{/${t}\\}`);
      const m = newText.match(re);
      if (m) {
        newText = newText.replace(re, "$1");
        stripped = true;
        break;
      }
    }
    if (!stripped) {
      alert("Aucun coloriage trouvé autour de cette sélection.");
      return;
    }
  } else {
    const idx = rawText.indexOf(selectedText);
    if (idx < 0) {
      const flexRe = new RegExp(selectedText.split(/\s+/).map(t => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\s+"));
      const m = rawText.match(flexRe);
      if (!m) {
        alert("Sélection introuvable dans le texte source.\n\n" + "Essaie une sélection plus simple (pas à cheval sur plusieurs paragraphes).");
        return;
      }
      newText = rawText.slice(0, m.index) + `{${tag}}${m[0]}{/${tag}}` + rawText.slice(m.index + m[0].length);
    } else {
      newText = rawText.slice(0, idx) + `{${tag}}${selectedText}{/${tag}}` + rawText.slice(idx + selectedText.length);
    }
  }
  if (newText === rawText) {
    _hideSelectionToolbar();
    return;
  }
  try {
    const r = await fetch(`/api/messages/${index}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        text: newText,
        silent: true
      })
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      alert("Échec PATCH : " + (data.error || r.status));
      return;
    }
    turn.dataset.rawText = newText;
    const textDiv = turn.querySelector(":scope > div:nth-child(2)");
    if (textDiv) textDiv.innerHTML = renderMarkdown(newText);
    try {
      linkifyPageRefs(turn);
    } catch (_) {}
    if (window.renderMathInElement) {
      try {
        window.renderMathInElement(turn, _katexOptions || {});
      } catch (_) {}
    }
    _hideSelectionToolbar();
    try {
      window.getSelection().removeAllRanges();
    } catch (_) {}
  } catch (e) {
    alert("Erreur réseau : " + e.message);
  }
}
function _positionSelectionToolbar(range) {
  const tb = _ensureSelectionToolbar();
  const rect = range.getBoundingClientRect();
  const tbHeight = 40;
  const margin = 8;
  let top = rect.top + window.scrollY - tbHeight - margin;
  if (top < window.scrollY + 4) {
    top = rect.bottom + window.scrollY + margin;
  }
  let left = rect.left + window.scrollX + rect.width / 2;
  tb.style.top = top + "px";
  tb.style.left = left + "px";
  tb.style.transform = "translateX(-50%)";
  const colorOpenBtn = tb.querySelector('[data-act="cahier-open-colors"]');
  if (colorOpenBtn) {
    colorOpenBtn.hidden = !_isSelectionInCahierCard(range);
  }
  tb.hidden = false;
  if (_selectionHideTimer) clearTimeout(_selectionHideTimer);
  _selectionHideTimer = setTimeout(() => {
    if (tb) tb.hidden = true;
  }, 8000);
}
function _hideSelectionToolbar() {
  if (_selectionToolbarEl) _selectionToolbarEl.hidden = true;
  if (_selectionHideTimer) {
    clearTimeout(_selectionHideTimer);
    _selectionHideTimer = null;
  }
}
document.addEventListener("selectionchange", () => {
  const info = _getSelectionInsideTurn();
  if (info) {
    _positionSelectionToolbar(info.range);
  } else {
    _hideSelectionToolbar();
  }
});
function _cleanupKatexSelection(text) {
  if (!text) return "";
  let out = text.replace(/[\u{1D400}-\u{1D7FF}]/gu, "");
  out = out.replace(/[​-‏⁠-⁯﻿]/g, "");
  out = out.replace(/\s+/g, " ");
  return out.trim();
}
async function _handleSelectionAction(action, info) {
  const text = info.text;
  if (action === "copy") {
    try {
      await navigator.clipboard.writeText(text);
      _flashSelectionFeedback("✓ Copié");
    } catch (_) {
      alert("Copie échouée : fais Ctrl+C manuellement.");
    }
    return;
  }
  if (action === "quote") {
    if (!userInput) return;
    const quoted = text.split("\n").map(l => "> " + l).join("\n");
    const sep = userInput.value && !userInput.value.endsWith("\n") ? "\n\n" : "";
    userInput.value += sep + quoted + "\n\n";
    autoResizeUserInput();
    userInput.focus();
    userInput.setSelectionRange(userInput.value.length, userInput.value.length);
    _hideSelectionToolbar();
    return;
  }
  if (action === "explain") {
    if (!userInput) return;
    const cleanText = text.replace(/\s+/g, " ").trim();
    const prompt = `Peux-tu m'expliquer : "${cleanText}"`;
    const sep = userInput.value && !userInput.value.endsWith("\n") ? "\n\n" : "";
    userInput.value += sep + prompt;
    autoResizeUserInput();
    userInput.focus();
    userInput.setSelectionRange(userInput.value.length, userInput.value.length);
    _hideSelectionToolbar();
    return;
  }
  if (action === "save") {
    const cleanedText = _cleanupKatexSelection(text);
    try {
      const r = await fetch("/api/saved_selections", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          text: cleanedText,
          message_id: info.messageId,
          role: info.role
        })
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        alert("Sauvegarde échouée : " + (data.error || r.status));
        return;
      }
      try {
        const range = info.range;
        const mark = document.createElement("mark");
        mark.className = "saved-note-mark";
        mark.dataset.selId = data.id;
        range.surroundContents(mark);
        try {
          window.getSelection().removeAllRanges();
        } catch (_) {}
      } catch (e) {
        console.debug("Highlight persistant impossible :", e.message);
      }
      _flashSelectionFeedback("✓ Sauvegardé dans 🔖 Notes");
      refreshSavedNotes();
      _hideSelectionToolbar();
    } catch (e) {
      alert("Erreur réseau : " + e.message);
    }
  }
}
function _flashSelectionFeedback(msg) {
  const t = document.createElement("div");
  t.className = "selection-toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => {
    try {
      t.remove();
    } catch (_) {}
  }, 1800);
}
const notesListEl = $("#notes-list");
const notesRefreshBtn = $("#notes-refresh");
async function refreshSavedNotes() {
  if (!notesListEl) return;
  try {
    const r = await fetch("/api/saved_selections");
    if (!r.ok) return;
    const data = await r.json();
    const sels = data.selections || [];
    if (!data.active) {
      notesListEl.innerHTML = '<div class="notes-empty">Pas de session active. Lance une séance pour sauvegarder des notes.</div>';
      return;
    }
    if (sels.length === 0) {
      notesListEl.innerHTML = '<div class="notes-empty">' + '<strong>Aucune note pour l\'instant.</strong><br><br>' + '<em>Sélectionne du texte dans une bulle (Compagnon ou toi-même) pour voir les options : ' + '<strong>💾 Sauvegarder</strong>, <strong>📋 Citer</strong>, ' + '<strong>🤔 Expliquer</strong>, <strong>📝 Copier</strong>.</em>' + '</div>';
      return;
    }
    notesListEl.innerHTML = "";
    for (const sel of sels) {
      const item = document.createElement("div");
      item.className = "note-item note-" + (sel.role || "claude");
      const role = sel.role === "student" ? "Toi" : "Compagnon";
      const ts = sel.captured_at || "";
      const head = document.createElement("div");
      head.className = "note-head";
      head.innerHTML = `<span class="note-role">${role}</span>` + `<span class="note-ts" title="${ts}">${formatTurnTimeShort(ts)}</span>`;
      const body = document.createElement("div");
      body.className = "note-body";
      body.textContent = _cleanupKatexSelection(sel.text);
      const actions = document.createElement("div");
      actions.className = "note-actions";
      const goBtn = document.createElement("button");
      goBtn.type = "button";
      goBtn.title = "Aller à la bulle source";
      goBtn.textContent = "↪ Voir";
      goBtn.addEventListener("click", e => {
        e.stopPropagation();
        _scrollToBubble(sel.message_id);
      });
      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.title = "Supprimer cette note";
      delBtn.textContent = "🗑";
      delBtn.addEventListener("click", async e => {
        e.stopPropagation();
        if (!confirm("Supprimer cette note ?")) return;
        try {
          await fetch("/api/saved_selections/" + encodeURIComponent(sel.id), {
            method: "DELETE"
          });
          if (dialogue) {
            const marks = dialogue.querySelectorAll(`mark.saved-note-mark[data-sel-id="${CSS.escape(sel.id)}"]`);
            marks.forEach(m => {
              const parent = m.parentNode;
              while (m.firstChild) parent.insertBefore(m.firstChild, m);
              parent.removeChild(m);
              parent.normalize();
            });
          }
          refreshSavedNotes();
        } catch (e2) {
          alert("Erreur : " + e2.message);
        }
      });
      actions.appendChild(goBtn);
      actions.appendChild(delBtn);
      item.appendChild(head);
      item.appendChild(body);
      item.appendChild(actions);
      body.addEventListener("click", () => _scrollToBubble(sel.message_id));
      notesListEl.appendChild(item);
    }
  } catch (e) {
    console.warn("refreshSavedNotes :", e);
  }
}
function _scrollToBubble(messageId) {
  if (!messageId) return;
  const bubble = dialogue && dialogue.querySelector(`.turn[data-msg-id="${CSS.escape(messageId)}"]`);
  if (!bubble) {
    alert("Bulle source introuvable (peut-être supprimée ou hors transcript courant).");
    return;
  }
  bubble.scrollIntoView({
    behavior: "smooth",
    block: "center"
  });
  bubble.classList.add("note-highlight");
  setTimeout(() => bubble.classList.remove("note-highlight"), 2500);
}
if (notesRefreshBtn) notesRefreshBtn.addEventListener("click", refreshSavedNotes);
function _prettifyPhotoFilename(filename) {
  if (!filename) return "";
  const base = filename.replace(/\.[a-z0-9]+$/i, "");
  const m = base.match(/^(\d{4}-\d{2}-\d{2})_(\d{4})_([a-z0-9_]+?)_v(\d+)$/i);
  if (m) {
    const date = m[1];
    const hhmm = m[2];
    const kindSlug = m[3];
    const version = parseInt(m[4], 10);
    const words = kindSlug.split("_").filter(w => w.length > 0);
    const pretty = words.map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
    const [y, mo, d] = date.split("-");
    const hh = hhmm.slice(0, 2);
    const mm = hhmm.slice(2);
    const dateFr = `${d}/${mo} ${hh}:${mm}`;
    const vSuffix = version > 1 ? ` (v${version})` : "";
    return `${pretty} · ${dateFr}${vSuffix}`;
  }
  const m2 = base.match(/^cropped_(\d+)_v(\d+)$/);
  if (m2) {
    const ts = parseInt(m2[1], 10);
    if (!isNaN(ts) && ts > 1000000000000) {
      try {
        const d = new Date(ts);
        const dateFr = d.toLocaleString("fr-FR", {
          day: "2-digit",
          month: "2-digit",
          hour: "2-digit",
          minute: "2-digit"
        });
        return `Photo · ${dateFr}`;
      } catch (_) {}
    }
    return base;
  }
  return base.replace(/_/g, " ").replace(/\bv\d+\b/, "").trim();
}
const photosGridEl = $("#photos-grid");
const photosRefreshBtn = $("#photos-refresh");
async function refreshSessionPhotos() {
  if (!photosGridEl) return;
  try {
    const r = await fetch("/api/session_photos");
    if (!r.ok) return;
    const data = await r.json();
    const photos = data.photos || [];
    if (!data.active) {
      photosGridEl.innerHTML = '<div class="photos-empty">Pas de session active. Lance une séance pour archiver les photos.</div>';
      return;
    }
    if (photos.length === 0) {
      photosGridEl.innerHTML = '<div class="photos-empty">' + '<strong>Aucune photo pour l\'instant.</strong><br><br>' + '<em>Toutes les images envoyées au tuteur (📷 ou 📎) seront archivées ici ' + 'automatiquement. Clique sur une vignette pour l\'aggrandir, ou sur 🗑 pour ' + 'la retirer de la galerie.</em>' + '</div>';
      return;
    }
    photosGridEl.innerHTML = "";
    const sorted = [...photos].reverse();
    for (const ph of sorted) {
      const card = document.createElement("div");
      card.className = "photo-card";
      card.dataset.photoId = ph.id || "";
      card.title = _prettifyPhotoFilename(ph.filename || ph.rel_path || "");
      const imgWrap = document.createElement("div");
      imgWrap.className = "photo-thumb-wrap";
      const img = document.createElement("img");
      img.className = "photo-thumb";
      img.alt = ph.original_name || ph.filename || "Photo";
      img.loading = "lazy";
      img.src = _attachmentSrcUrl(ph);
      img.addEventListener("click", () => {
        if (typeof openLightbox === "function") openLightbox(img.src);
      });
      img.addEventListener("error", () => {
        img.replaceWith(Object.assign(document.createElement("div"), {
          className: "photo-broken",
          textContent: "🗎 (fichier introuvable)"
        }));
      });
      imgWrap.appendChild(img);
      const meta = document.createElement("div");
      meta.className = "photo-meta";
      const tsShort = typeof formatTurnTimeShort === "function" ? formatTurnTimeShort(ph.sent_at || "") : ph.sent_at || "";
      const sizeKb = ph.size_bytes ? Math.round(ph.size_bytes / 1024) + " kB" : "";
      meta.innerHTML = `<span class="photo-ts" title="${ph.sent_at || ""}">${tsShort}</span>` + (sizeKb ? `<span class="photo-size">${sizeKb}</span>` : "");
      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "photo-del-btn";
      delBtn.title = "Retirer de la galerie (le fichier disque est conservé)";
      delBtn.textContent = "🗑";
      delBtn.addEventListener("click", async e => {
        e.stopPropagation();
        if (!confirm("Retirer cette photo de la galerie ?\n\n(Le fichier reste sous COURS/, seule l'entrée de tracking est supprimée.)")) {
          return;
        }
        try {
          const resp = await fetch("/api/session_photos/" + encodeURIComponent(ph.id), {
            method: "DELETE"
          });
          if (resp.ok || resp.status === 204) {
            refreshSessionPhotos();
          } else {
            const errData = await resp.json().catch(() => ({}));
            alert("Erreur : " + (errData.error || resp.status));
          }
        } catch (e2) {
          alert("Erreur réseau : " + e2.message);
        }
      });
      card.appendChild(imgWrap);
      card.appendChild(meta);
      card.appendChild(delBtn);
      photosGridEl.appendChild(card);
    }
  } catch (e) {
    console.warn("refreshSessionPhotos :", e);
  }
}
if (photosRefreshBtn) photosRefreshBtn.addEventListener("click", refreshSessionPhotos);
const outlineListEl = $("#outline-list");
const outlineRefreshBtn = $("#outline-refresh");
const _OUTLINE_KIND_ICONS = {
  section: "§",
  subsection: "§§",
  exercise: "✏",
  question: "?"
};
async function refreshDynamicOutline() {
  if (!outlineListEl) return;
  try {
    const r = await fetch("/api/dynamic_outline");
    if (!r.ok) return;
    const data = await r.json();
    const entries = data.outline || [];
    if (!data.active) {
      outlineListEl.innerHTML = '<div class="outline-empty">Pas de session active.</div>';
      return;
    }
    if (entries.length === 0) {
      outlineListEl.innerHTML = '<div class="outline-empty">Le tuteur n\'a pas encore introduit de section/question structurée. Ce sommaire s\'enrichit automatiquement au fil des réponses.</div>';
      return;
    }
    outlineListEl.innerHTML = "";
    for (const entry of entries) {
      const item = document.createElement("div");
      item.className = "outline-item";
      if (entry.enabled === false) item.classList.add("outline-disabled");
      item.dataset.kind = entry.kind || "section";
      item.dataset.outlineId = entry.id || "";
      const kindEl = document.createElement("span");
      kindEl.className = "outline-item-kind";
      kindEl.textContent = _OUTLINE_KIND_ICONS[entry.kind] || "•";
      const titleEl = document.createElement("span");
      titleEl.className = "outline-item-title";
      titleEl.textContent = entry.title || "";
      titleEl.title = entry.snippet || "Double-clic pour modifier · Click pour aller à la source";
      titleEl.addEventListener("click", e => {
        if (e.target === titleEl && e.detail === 1) {
          setTimeout(() => {
            if (!titleEl.isContentEditable) {
              _scrollToBubble(entry.source_message_id);
            }
          }, 200);
        }
      });
      titleEl.addEventListener("dblclick", () => _editOutlineInline(entry, titleEl));
      const actions = document.createElement("div");
      actions.className = "outline-item-actions";
      const toggleBtn = document.createElement("button");
      toggleBtn.type = "button";
      const enabled = entry.enabled !== false;
      toggleBtn.textContent = enabled ? "✓" : "⏸";
      toggleBtn.title = enabled ? "Désactiver (l'entrée reste mais grisée)" : "Réactiver";
      toggleBtn.addEventListener("click", async e => {
        e.stopPropagation();
        await _patchOutline(entry.id, {
          enabled: !enabled
        });
        refreshDynamicOutline();
      });
      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.textContent = "🗑";
      delBtn.title = "Supprimer";
      delBtn.addEventListener("click", async e => {
        e.stopPropagation();
        if (!confirm("Supprimer cette entrée du sommaire ?")) return;
        try {
          const resp = await fetch("/api/dynamic_outline/" + encodeURIComponent(entry.id), {
            method: "DELETE"
          });
          if (resp.ok || resp.status === 204) refreshDynamicOutline();
        } catch (e2) {
          alert("Erreur : " + e2.message);
        }
      });
      actions.appendChild(toggleBtn);
      actions.appendChild(delBtn);
      item.appendChild(kindEl);
      item.appendChild(titleEl);
      item.appendChild(actions);
      outlineListEl.appendChild(item);
    }
  } catch (e) {
    console.warn("refreshDynamicOutline :", e);
  }
}
async function _patchOutline(id, patch) {
  try {
    const r = await fetch("/api/dynamic_outline/" + encodeURIComponent(id), {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(patch)
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      alert("Erreur : " + (err.error || r.status));
      return null;
    }
    return await r.json();
  } catch (e) {
    alert("Erreur réseau : " + e.message);
    return null;
  }
}
function _editOutlineInline(entry, titleEl) {
  const old = entry.title || "";
  titleEl.contentEditable = "true";
  titleEl.focus();
  const range = document.createRange();
  range.selectNodeContents(titleEl);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  let done = false;
  const finish = async commit => {
    if (done) return;
    done = true;
    titleEl.contentEditable = "false";
    if (commit) {
      const newTitle = (titleEl.textContent || "").trim();
      if (newTitle && newTitle !== old) {
        const updated = await _patchOutline(entry.id, {
          title: newTitle
        });
        if (updated) {
          refreshDynamicOutline();
          return;
        }
      }
    }
    titleEl.textContent = old;
  };
  titleEl.addEventListener("blur", () => finish(true), {
    once: true
  });
  titleEl.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      e.preventDefault();
      finish(false);
    } else if (e.key === "Enter") {
      e.preventDefault();
      finish(true);
    }
  });
}
if (outlineRefreshBtn) outlineRefreshBtn.addEventListener("click", refreshDynamicOutline);
const stickiesListEl = $("#stickies-list");
const stickiesRefreshBtn = $("#stickies-refresh");
const stickiesImportBtn = $("#stickies-import");
async function refreshStickies() {
  if (!stickiesListEl) return;
  try {
    const r = await fetch("/api/stickies");
    if (!r.ok) return;
    const data = await r.json();
    const stickies = data.stickies || [];
    if (!data.active) {
      stickiesListEl.innerHTML = '<div class="stickies-empty">Pas de session active. Lance une séance pour épingler des consignes.</div>';
      return;
    }
    if (stickies.length === 0) {
      stickiesListEl.innerHTML = '<div class="stickies-empty">' + '<strong>Aucune consigne épinglée.</strong><br><br>' + '<em>Pour épingler une consigne : passe la souris sur une bulle à toi dans le fil et clique sur <strong>📌</strong>. ' + 'Ou dis explicitement au tuteur : « <em>retiens que…</em> » : il émettra la balise lui-même.</em><br><br>' + '<em>Les consignes sont rappelées au tuteur à chaque tour pour qu\'il ne les oublie pas en cours de séance.</em>' + '</div>';
      return;
    }
    stickiesListEl.innerHTML = "";
    for (const sticky of stickies) {
      const card = document.createElement("div");
      const kind = sticky.kind === "tutor" ? "tutor" : "user";
      card.className = "sticky-card sticky-" + kind + (sticky.enabled === false ? " sticky-disabled" : "");
      card.dataset.stickyId = sticky.id || "";
      const head = document.createElement("div");
      head.className = "sticky-head";
      const kindIcon = kind === "tutor" ? "🤖" : "📌";
      const kindLabel = kind === "tutor" ? "Tuteur" : "Toi";
      const ts = sticky.created_at || "";
      const tsShort = typeof formatTurnTimeShort === "function" ? formatTurnTimeShort(ts) : ts;
      head.innerHTML = `<span class="sticky-kind" title="${kindLabel}">${kindIcon} ${kindLabel}</span>` + `<span class="sticky-ts" title="${ts}">${tsShort}</span>`;
      const body = document.createElement("div");
      body.className = "sticky-body";
      body.textContent = sticky.text || "";
      body.title = "Double-clic pour modifier";
      body.addEventListener("dblclick", () => _editStickyInline(sticky, body));
      const actions = document.createElement("div");
      actions.className = "sticky-actions";
      const toggleBtn = document.createElement("button");
      toggleBtn.type = "button";
      toggleBtn.className = "sticky-toggle";
      const enabled = sticky.enabled !== false;
      toggleBtn.textContent = enabled ? "✅ Active" : "⏸ Désactivée";
      toggleBtn.title = enabled ? "Désactiver (le tuteur ne sera plus rappelé de cette consigne, mais elle reste dans la liste)" : "Réactiver";
      toggleBtn.addEventListener("click", async e => {
        e.stopPropagation();
        await _patchSticky(sticky.id, {
          enabled: !enabled
        });
        refreshStickies();
      });
      if (sticky.source_message_id) {
        const goBtn = document.createElement("button");
        goBtn.type = "button";
        goBtn.className = "sticky-goto";
        goBtn.textContent = "↪ Voir";
        goBtn.title = "Aller à la bulle source";
        goBtn.addEventListener("click", e => {
          e.stopPropagation();
          _scrollToBubble(sticky.source_message_id);
        });
        actions.appendChild(goBtn);
      }
      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "sticky-del";
      delBtn.textContent = "🗑";
      delBtn.title = "Supprimer cette consigne";
      delBtn.addEventListener("click", async e => {
        e.stopPropagation();
        if (!confirm("Supprimer cette consigne ?")) return;
        try {
          const resp = await fetch("/api/stickies/" + encodeURIComponent(sticky.id), {
            method: "DELETE"
          });
          if (resp.ok || resp.status === 204) {
            refreshStickies();
          } else {
            const err = await resp.json().catch(() => ({}));
            alert("Erreur : " + (err.error || resp.status));
          }
        } catch (e2) {
          alert("Erreur réseau : " + e2.message);
        }
      });
      actions.appendChild(toggleBtn);
      actions.appendChild(delBtn);
      card.appendChild(head);
      card.appendChild(body);
      card.appendChild(actions);
      stickiesListEl.appendChild(card);
    }
  } catch (e) {
    console.warn("refreshStickies :", e);
  }
}
async function _patchSticky(id, patch) {
  try {
    const r = await fetch("/api/stickies/" + encodeURIComponent(id), {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(patch)
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      alert("Erreur : " + (err.error || r.status));
      return null;
    }
    return await r.json();
  } catch (e) {
    alert("Erreur réseau : " + e.message);
    return null;
  }
}
function _editStickyInline(sticky, bodyEl) {
  const oldText = sticky.text || "";
  const input = document.createElement("textarea");
  input.className = "sticky-edit-input";
  input.value = oldText;
  input.rows = 2;
  input.maxLength = 200;
  bodyEl.replaceWith(input);
  input.focus();
  input.setSelectionRange(0, input.value.length);
  let done = false;
  const finish = async commit => {
    if (done) return;
    done = true;
    if (commit) {
      const newText = (input.value || "").trim();
      if (newText && newText !== oldText) {
        const updated = await _patchSticky(sticky.id, {
          text: newText
        });
        if (updated) {
          refreshStickies();
          return;
        }
      }
    }
    refreshStickies();
  };
  input.addEventListener("blur", () => finish(true));
  input.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      e.preventDefault();
      finish(false);
    } else if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      finish(true);
    }
  });
}
async function _createStickyFromMessage(messageId, text) {
  const cleanText = (text || "").trim();
  if (!cleanText) {
    alert("Bulle vide, rien à épingler.");
    return;
  }
  let finalText = cleanText;
  if (cleanText.length > 200) {
    finalText = prompt("Le message fait " + cleanText.length + " chars (max 200). " + "Modifie/raccourcis la consigne avant de l'épingler :", cleanText.slice(0, 197) + "…");
    if (!finalText) return;
    finalText = finalText.trim();
    if (!finalText) return;
  }
  try {
    const r = await fetch("/api/stickies", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        text: finalText,
        source_message_id: messageId || null,
        kind: "user"
      })
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      alert("Erreur : " + (err.error || r.status));
      return;
    }
    if (typeof _flashSelectionFeedback === "function") {
      _flashSelectionFeedback("📌 Consigne épinglée");
    }
    refreshStickies();
    const tab = document.querySelector('#sidebar-tabs .sb-tab[data-tab="stickies"]');
    if (tab) tab.click();
  } catch (e) {
    alert("Erreur réseau : " + e.message);
  }
}
function _maybeAttachPinChipToStudentTurn(turnEl) {
  if (!turnEl) return;
  if (!turnEl.classList.contains("turn") || !turnEl.classList.contains("student")) return;
  if (turnEl.classList.contains("marker")) return;
  if (turnEl.querySelector(":scope > .sticky-pin-chip")) return;
  const chip = document.createElement("button");
  chip.type = "button";
  chip.className = "sticky-pin-chip";
  chip.textContent = "📌";
  chip.title = "Épingler ce message comme consigne pour le tuteur";
  chip.addEventListener("click", e => {
    e.stopPropagation();
    const msgId = turnEl.dataset.msgId || null;
    const rawText = turnEl.dataset.rawText || turnEl.children[1]?.textContent || "";
    _createStickyFromMessage(msgId, rawText);
  });
  turnEl.appendChild(chip);
}
(function setupStickyPinChipObserver() {
  if (!dialogue) return;
  dialogue.querySelectorAll(".turn.student").forEach(_maybeAttachPinChipToStudentTurn);
  const mo = new MutationObserver(mutations => {
    for (const m of mutations) {
      for (const node of m.addedNodes) {
        if (node.nodeType !== 1) continue;
        if (node.classList?.contains("turn") && node.classList.contains("student")) {
          _maybeAttachPinChipToStudentTurn(node);
        }
        node.querySelectorAll?.(".turn.student").forEach(_maybeAttachPinChipToStudentTurn);
      }
    }
  });
  mo.observe(dialogue, {
    childList: true,
    subtree: true
  });
})();
if (stickiesRefreshBtn) stickiesRefreshBtn.addEventListener("click", refreshStickies);
const sImportModal = $("#stickies-import-modal");
const sImportClose = $("#sim-close");
const sImportCancel = $("#sim-cancel");
const sImportStep1 = $("#sim-step1");
const sImportStep2 = $("#sim-step2");
const sImportSessionsList = $("#sim-sessions-list");
const sImportStickiesList = $("#sim-stickies-list");
const sImportBack = $("#sim-back-step1");
const sImportLabel = $("#sim-step2-label");
const sImportToggleAll = $("#sim-toggle-all");
const sImportApply = $("#sim-import");
let _sImportCurrentSessionId = null;
function _openStickiesImportModal() {
  if (!sImportModal) return;
  sImportModal.hidden = false;
  sImportStep1.hidden = false;
  sImportStep2.hidden = true;
  _sImportCurrentSessionId = null;
  _loadSessionsForImport();
}
function _closeStickiesImportModal() {
  if (!sImportModal) return;
  sImportModal.hidden = true;
}
async function _loadSessionsForImport() {
  sImportSessionsList.innerHTML = '<div class="sim-empty">Chargement…</div>';
  try {
    const r = await fetch("/api/sessions");
    if (!r.ok) {
      sImportSessionsList.innerHTML = '<div class="sim-empty">Erreur de chargement.</div>';
      return;
    }
    const data = await r.json();
    const sessions = data.sessions || [];
    const current = activeSession?.session_id || null;
    const candidates = sessions.filter(s => s.session_id !== current && (s.stickies_count || 0) > 0);
    if (candidates.length === 0) {
      sImportSessionsList.innerHTML = '<div class="sim-empty">' + 'Aucune autre session avec des consignes épinglées.<br><br>' + '<em>Une session apparaît ici dès qu\'elle contient au moins ' + 'une consigne (manuelle ou tuteur).</em>' + '</div>';
      return;
    }
    sImportSessionsList.innerHTML = "";
    for (const sess of candidates) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "sim-session-item";
      const label = sess.label || sess.session_id;
      const count = sess.stickies_count || 0;
      item.innerHTML = `<div class="sim-session-label">${label}</div>` + `<div class="sim-session-meta">${count} consigne${count > 1 ? "s" : ""}` + (sess.started_at ? ` · ${formatTurnTimeShort(sess.started_at)}` : "") + `</div>`;
      item.addEventListener("click", () => _showStickiesOfSession(sess));
      sImportSessionsList.appendChild(item);
    }
  } catch (e) {
    sImportSessionsList.innerHTML = `<div class="sim-empty">Erreur réseau : ${e.message}</div>`;
  }
}
async function _showStickiesOfSession(sess) {
  _sImportCurrentSessionId = sess.session_id;
  sImportStep1.hidden = true;
  sImportStep2.hidden = false;
  sImportLabel.textContent = sess.label || sess.session_id;
  sImportStickiesList.innerHTML = '<div class="sim-empty">Chargement…</div>';
  try {
    const r = await fetch("/api/sessions/" + encodeURIComponent(sess.session_id));
    if (!r.ok) {
      sImportStickiesList.innerHTML = '<div class="sim-empty">Impossible de lire cette session.</div>';
      return;
    }
    const data = await r.json();
    const stickies = (data.stickies || []).filter(s => s.enabled !== false);
    if (stickies.length === 0) {
      sImportStickiesList.innerHTML = '<div class="sim-empty">Cette session n\'a aucune consigne active.</div>';
      return;
    }
    sImportStickiesList.innerHTML = "";
    for (const sticky of stickies) {
      const row = document.createElement("label");
      row.className = "sim-sticky-row sim-sticky-" + (sticky.kind || "user");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.value = sticky.id;
      cb.checked = true;
      const kindIcon = sticky.kind === "tutor" ? "🤖" : "📌";
      const span = document.createElement("span");
      span.className = "sim-sticky-text";
      span.textContent = kindIcon + " " + (sticky.text || "");
      row.appendChild(cb);
      row.appendChild(span);
      sImportStickiesList.appendChild(row);
    }
  } catch (e) {
    sImportStickiesList.innerHTML = `<div class="sim-empty">Erreur : ${e.message}</div>`;
  }
}
if (stickiesImportBtn) stickiesImportBtn.addEventListener("click", _openStickiesImportModal);
if (sImportClose) sImportClose.addEventListener("click", _closeStickiesImportModal);
if (sImportCancel) sImportCancel.addEventListener("click", _closeStickiesImportModal);
if (sImportBack) sImportBack.addEventListener("click", () => {
  sImportStep1.hidden = false;
  sImportStep2.hidden = true;
});
if (sImportToggleAll) sImportToggleAll.addEventListener("click", () => {
  const cbs = sImportStickiesList.querySelectorAll('input[type=checkbox]');
  const anyUnchecked = Array.from(cbs).some(cb => !cb.checked);
  cbs.forEach(cb => {
    cb.checked = anyUnchecked;
  });
});
if (sImportApply) sImportApply.addEventListener("click", async () => {
  if (!_sImportCurrentSessionId) return;
  const cbs = sImportStickiesList.querySelectorAll('input[type=checkbox]:checked');
  const ids = Array.from(cbs).map(cb => cb.value);
  if (ids.length === 0) {
    alert("Sélectionne au moins une consigne à importer.");
    return;
  }
  try {
    const r = await fetch("/api/stickies/import_from/" + encodeURIComponent(_sImportCurrentSessionId), {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        sticky_ids: ids
      })
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      alert("Erreur : " + (err.error || r.status));
      return;
    }
    const data = await r.json();
    if (typeof _flashSelectionFeedback === "function") {
      _flashSelectionFeedback(`📋 ${data.imported_count} consigne(s) importée(s)`);
    }
    _closeStickiesImportModal();
    refreshStickies();
  } catch (e) {
    alert("Erreur réseau : " + e.message);
  }
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && sImportModal && !sImportModal.hidden) {
    _closeStickiesImportModal();
  }
});
function _spotlight(target, opts = {}) {
  let el = target;
  if (typeof target === "string") {
    el = document.querySelector(target);
  }
  if (!el || !(el instanceof Element)) {
    console.warn("_spotlight : cible introuvable", target);
    return;
  }
  if (el.classList.contains("sb-tab") && opts.activateTab !== false) {
    try {
      el.click();
    } catch (_) {}
  }
  if (opts.scrollIntoView !== false) {
    try {
      el.scrollIntoView({
        behavior: "smooth",
        block: "center"
      });
    } catch (_) {}
  }
  const isTab = el.classList.contains("sb-tab");
  const cls = isTab ? "sb-tab-spotlight" : "spotlight-target";
  el.classList.add(cls);
  const duration = opts.duration || 3000;
  setTimeout(() => el.classList.remove(cls), duration);
}
function _prefillTextarea(text) {
  const ta = document.getElementById("user-input");
  if (!ta) return;
  if (ta.disabled) {
    alert("Lance d'abord une séance pour pouvoir taper.");
    return;
  }
  ta.value = text;
  ta.focus();
  ta.dispatchEvent(new Event("input", {
    bubbles: true
  }));
  _spotlight("#send-btn", {
    scrollIntoView: false
  });
}
const TIPS_CATALOG = [{
  title: "🎙 Dicter ta réponse au micro",
  body: "Le bouton 🎤 à côté du textarea capture l'audio, le transcrit via Whisper large-v3 et insère le résultat. Si tu avais déjà tapé du texte, la transcription est appendée (pas remplacée).",
  action: {
    label: "▶ Voir le bouton 🎤",
    fn: () => _spotlight("#mic-btn")
  }
}, {
  title: "⌨ Maintenir Espace pour parler (push-to-talk)",
  body: "Quand le focus n'est PAS sur un input, maintenir [Espace] active l'enregistrement micro tant que la touche est appuyée. Lâche pour stopper et envoyer la transcription.",
  action: null
}, {
  title: "📷 Prendre une photo depuis ton téléphone",
  body: "Le bouton 📷 ouvre la caméra sur mobile, ou flash l'onglet 🔗 Distant sur desktop (QR/URL Tailscale). La photo arrive dans le tray d'envoi du desktop automatiquement.",
  action: {
    label: "▶ Voir l'onglet Distant",
    fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="mobile"]')
  }
}, {
  title: "✏ Éditer un message > en écrire un nouveau pour recharger le contexte",
  body: ["Si le tuteur dérive ou tu veux reformuler ta question avec plus de contexte, préfère éditer le message d'origine (icône ✏ au hover sur ta bulle) plutôt que renvoyer un nouveau message.", "Bouton « 🔄 Recharger contexte » dans l'éditeur : modifie + supprime tout ce qui suit + regénère la réponse du tuteur.", "Avantages : pas de tokens gaspillés sur des tours obsolètes, le tuteur repart d'un état propre, et l'historique reste lisible."],
  action: null
}, {
  title: "✨ Reformuler ton brouillon avant envoi",
  body: "Le bouton ✨ ouvre 4 actions : Reformuler / Plus concis / Développer / Corriger fautes. Utile pour transformer une dictée vocale brute en réponse propre. Fonctionne aussi en mode édition de bulle.",
  action: {
    label: "▶ Voir le bouton ✨",
    fn: () => _spotlight("#rewrite-btn")
  }
}, {
  title: "🛑 Annuler la réflexion en cours du tuteur",
  body: 'Pendant que le tuteur stream, le bouton Envoyer devient ⏹ Annuler. Click = modal 2 options : "Reprendre (garder mon message)" ou "Supprimer mon message" (annule + retire la dernière bulle).',
  action: null
}, {
  title: "📒 Carte cahier : la doctrine couleurs",
  body: ["Le tuteur émet des cartes « cahier » visuelles aux moments « notez ceci sur votre cahier ». Disponible dans les 3 modes : systématique en Découverte, ponctuelle en Colle (après blocage prolongé, en débrief, sur demande), ponctuelle en Guidé (correction d'erreur du script, astuce mémorisable). Fond crème, lignes Seyès, marge stylo rouge.", "🔵 Bleu = prose courante (défaut, ~60% du texte).", "🔴 Rouge = concept ou résultat à retenir absolument.", "🟢 Vert = exemples concrets, valeurs, ET code à recopier (fond vert pâle).", "⚫ Noir = formules mathématiques. Tous les rendus LaTeX ($…$ et $$…$$) dans une carte passent automatiquement en noir, c'est le rôle dédié du stylo noir.", "🟣 Violet surligneur = titre de la carte cahier, appliqué automatiquement.", "🟢 Vert surligneur = sous-titres dans le corps (titres ## / ###, lignes « Méthode : » / « Définition : » / « Théorème : »…), appliqué automatiquement.", "🟡 Jaune surligneur = formule vitale à mémoriser par cœur.", "🩷 Rose surligneur = piège, erreur classique, « attention ».", "Code en blocs ``` ``` : tout en vert, commentaires (-- ... / # ... / // ...) automatiquement en rouge.", "Limites = guides, pas absolues : certains concepts justifient d'utiliser le rouge ou le vert plusieurs fois. Évite juste le sapin-de-Noël (tout coloré)."],
  action: null
}, {
  title: "🎨 Tout ce que tu peux faire avec les couleurs cahier",
  body: ["L'onglet 🎨 Couleurs centralise toute la gestion : 4 stylos + 4 surligneurs avec preview + picker hex + bouton ↺ Reset.", "Cas 1, REMAP GLOBAL (rétroactif, toutes cards) : clique sur l'input couleur à droite d'un rôle (ex: rouge → orange). Toutes les cards existantes et futures prennent INSTANTANÉMENT la nouvelle teinte. Persisté dans localStorage du navigateur. Mécanique : CSS variables, aucun message touché.", "Cas 2, APPLIQUER À UNE SÉLECTION : (a) sélectionne un mot dans une carte cahier crème, (b) clique le bouton « 🎨 Colorier » qui apparaît dans la mini-toolbar au-dessus, (c) l'onglet 🎨 Couleurs s'ouvre avec une bannière « 🎯 Sélection active : … » : clique alors le swatch (gros « Aa » coloré à gauche de chaque rôle) pour appliquer cette couleur au mot sélectionné. Édit persisté côté serveur (PATCH).", "Le bouton ⌫ « Retirer le coloriage de cette sélection » dans la bannière permet de défaire un coloriage existant autour de la sélection."],
  action: {
    label: "▶ Ouvrir l'onglet 🎨 Couleurs",
    fn: () => {
      const tab = document.querySelector('#sidebar-tabs .sb-tab[data-tab="colors"]');
      if (tab) tab.click();
    }
  }
}, {
  title: "💬 Reprendre une session interrompue",
  body: "L'onglet Historique liste toutes tes sessions persistées. Clic = soit reprendre (replay du transcript), soit ouvrir en lecture seule. Le bot peut reprendre une session vieille de plusieurs jours.",
  action: {
    label: "▶ Voir l'onglet Historique",
    fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="history"]')
  }
}, {
  title: "📊 Surveiller ton quota Pro Max",
  body: "L'onglet Quota affiche en temps réel ta consommation : session 5h, hebdo 7j Opus, hebdo Sonnet, overage. Cookie chiffré DPAPI, refresh toutes les 30s.",
  action: {
    label: "▶ Voir l'onglet Quota",
    fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="quota"]')
  }
}, {
  title: "📄 Exporter la séance en PDF + Markdown",
  body: "Le bouton 📄 Récap dans le footer de la sidebar génère à tout moment un ZIP avec ton transcript complet (PDF lisible + MD léger), incluant les consignes épinglées et le récap de séance si la phase débrief est engagée.",
  action: {
    label: "▶ Voir le bouton 📄 Récap",
    fn: () => _spotlight("#export-recap-btn")
  }
}, {
  title: "💾 Sauvegarder une phrase comme note (surligneur orange)",
  body: ["Sélectionne du texte dans n'importe quelle bulle (Compagnon ou toi-même, dans une cahier-card ou pas, n'importe où dans le dialogue).", "Un popup apparaît avec 4 actions : 💾 Sauvegarder, 📋 Citer, 🤔 Expliquer, 📝 Copier.", "Click 💾 → la sélection est enregistrée dans l'onglet 🔖 Notes ET marquée d'un surligneur 🟠 orange dans la bulle pour retrouver visuellement ce que t'as save (couleur distincte du jaune cahier pour éviter la confusion).", "La couleur du surligneur 💾 est configurable depuis l'onglet 🎨 Couleurs cahier (ligne « Surligneur 💾 Notes save »). Tu peux la changer pour n'importe quelle teinte qui te parle."],
  action: {
    label: "▶ Voir l'onglet Notes",
    fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="notes"]')
  }
}, {
  title: "📌 Épingler une consigne à respecter",
  body: "Le tuteur oublie parfois une consigne donnée il y a 30 tours. Passe la souris sur une de tes bulles → clique 📌 pour l'épingler. Rappelée au tuteur à CHAQUE tour suivant.",
  action: {
    label: "▶ Voir l'onglet Consignes",
    fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="stickies"]')
  }
}, {
  title: "🤖 Demander au tuteur de retenir lui-même",
  body: 'Si tu dis "retiens que je dois toujours écrire la signature avant la fonction", le tuteur émet la balise <<<REMEMBER>>> qui s\'ajoute aux consignes épinglées automatiquement.',
  action: {
    label: "▶ Pré-remplir un draft",
    fn: () => _prefillTextarea("Retiens que ")
  }
}, {
  title: "📋 Importer des consignes d'une autre session",
  body: "Dans l'onglet Consignes, le bouton 📋 Importer ouvre un modal 2 étapes : choisis la session source, coche les consignes à copier. Utile pour reprendre des règles établies dans une séance précédente.",
  action: {
    label: "▶ Ouvrir l'onglet Consignes",
    fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="stickies"]')
  }
}, {
  title: "📸 Revoir les photos envoyées",
  body: "Toutes les photos que tu as envoyées au tuteur pendant la séance sont archivées dans l'onglet Photos : vignettes cliquables (lightbox), tri anti-chrono, suppression individuelle.",
  action: {
    label: "▶ Voir l'onglet Photos",
    fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="photos"]')
  }
}, {
  title: "🏷 Photos auto-renommées par OCR",
  body: "Quand tu envoies une photo en mode colle/découverte format photos/mixte, le tuteur OCR via Gemini Flash 2.5 et renomme automatiquement le fichier en YYYY-MM-DD_HHMM_<type>_<slug>.ext. Survole une vignette pour voir le nom formaté.",
  action: {
    label: "▶ Voir l'onglet Photos",
    fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="photos"]')
  }
}, {
  title: "📚 Lire l'énoncé / corrigé / script pendant la séance",
  body: "L'onglet Docs montre le PDF rasterisé page par page. Quand tu navigues une page, le tuteur reçoit en préfixe « [Contexte lecture : page N/M] » pour qu'il sache ce que tu as sous les yeux.",
  action: {
    label: "▶ Voir l'onglet Docs",
    fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="corrige"]')
  }
}, {
  title: "🔀 Basculer le format de la séance",
  body: "Tape /oral, /photos ou /mixte dans le textarea pour changer le format en cours de séance. Le tuteur acquitte d'un fragment court et adapte sa posture (suggérer/exiger photo, ou s'en passer).",
  action: {
    label: "▶ Pré-remplir /mixte",
    fn: () => _prefillTextarea("/mixte")
  }
}, {
  title: "📘 Basculer l'ancrage corrigé",
  body: "Tape /strict (corrigé fait foi), /consultatif (corrigé visible mais discutable) ou /aucun (sans corrigé). Utile quand le corrigé officiel a une erreur et que le tuteur tourne en boucle dessus.",
  action: {
    label: "▶ Pré-remplir /consultatif",
    fn: () => _prefillTextarea("/consultatif")
  }
}, {
  title: "🎲 Mode « Sans énoncé » (avec prudence)",
  body: "Coche 🎲 dans le form de lancement → le tuteur ignore l'énoncé du disque et invente ses propres questions. Utile pour la révision globale d'un thème. Option PONCTUELLE par séance (décochée par défaut à chaque boot).",
  action: null
}, {
  title: "💡 Mode « Sujet libre » (hors COURS/)",
  body: 'Coche 💡 et décris ton sujet (« apprendre Python ») → le tuteur s\'appuie uniquement sur ses connaissances LLM, sans matériel COURS. Mode guidé indisponible. Bandeau jaune au clic pour t\'avertir.',
  action: null
}, {
  title: "⚠ « 503 UNAVAILABLE » ou « high demand » : c'est du côté serveur",
  body: ["Quand un moteur (typiquement Gemini) renvoie 503 UNAVAILABLE / overloaded / high demand, c'est une surcharge temporaire côté Google. Pas un bug local.", "Deux options : (1) attendre 30s-2min, ces spikes sont courts ; (2) basculer sur un autre moteur via le sélecteur en haut (qui clignote en orange quand l'erreur tombe).", "Si ça se répète sur la journée : vérifier https://status.cloud.google.com/."],
  action: {
    label: "▶ Voir le sélecteur de moteur",
    fn: () => _spotlight("#engine-switcher")
  }
}, {
  title: "⚠ « 503 UNAVAILABLE » ou « high demand » : c'est du côté serveur",
  body: "Quand un moteur (typiquement Gemini) renvoie 503 UNAVAILABLE / overloaded / high demand, " + "c'est une surcharge temporaire côté Google (ou autre provider). Pas un bug local, le reload de " + "contexte n'y changera rien. Deux options : (1) attendre 30s-2min, ces spikes sont courts ; " + "(2) basculer sur un autre moteur via le sélecteur en haut (qui clignote en orange quand l'erreur " + "tombe). Si ça se répète sur la journée, vérifie https://status.cloud.google.com/.",
  action: {
    label: "▶ Voir le sélecteur de moteur",
    fn: () => _spotlight("#engine-switcher")
  }
}, {
  title: "✏ Éditer un message > en écrire un nouveau pour recharger le contexte",
  body: "Si le tuteur dérive ou tu veux reformuler ta question avec plus de contexte, préfère " + "éditer le message d'origine (icône ✏ au hover sur ta bulle) plutôt que renvoyer un nouveau " + "message à la suite. Bouton « 🔄 Recharger contexte » dans l'éditeur : modifie + supprime " + "tout ce qui suit + regénère la réponse du tuteur. Avantages : pas de tokens gaspillés sur des " + "tours obsolètes, le tuteur repart d'un état propre, et l'historique reste lisible. " + "Empile-trop-de-messages-pour-corriger = saturation cognitive ET token cost.",
  action: null
}, {
  title: "📄 Exporter la séance en PDF + Markdown",
  body: "Le bouton 📄 Récap dans le footer de la sidebar génère à tout moment un ZIP avec ton transcript complet (PDF lisible + MD léger), incluant les consignes épinglées et le récap de séance si la phase débrief est engagée. Pratique avant un examen, pour audit, ou pour le futur portfolio.",
  action: {
    label: "▶ Voir le bouton 📄 Récap",
    fn: () => _spotlight("#export-recap-btn")
  }
}, {
  title: "🏷 Photos auto-renommées par OCR",
  body: "Quand tu envoies une photo en mode colle/découverte format photos/mixte, le tuteur OCR via Gemini Flash 2.5 et renomme automatiquement le fichier en YYYY-MM-DD_HHMM_<type>_<slug>.ext. Survole une vignette dans l'onglet 📸 Photos pour voir le nom formaté.",
  action: {
    label: "▶ Voir l'onglet Photos",
    fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="photos"]')
  }
}, {
  title: "📌 Demander au tuteur de retenir une consigne",
  body: 'Dis "retiens que je dois toujours écrire la signature avant la fonction" → le tuteur émet la balise <<<REMEMBER>>> qui s\'ajoute aux consignes épinglées. Elle sera rappelée au tuteur à CHAQUE tour suivant (mémoire persistante de séance).',
  action: {
    label: "▶ Pré-remplir un draft",
    fn: () => _prefillTextarea("Retiens que ")
  }
}, {
  title: "🎲 Mode « Sans énoncé » (avec prudence)",
  body: "Coche 🎲 dans le form de lancement → le tuteur ignore l'énoncé du disque et invente ses propres questions. Utile pour la révision globale d'un thème. Un bandeau jaune apparaît quand tu coches pour te rappeler la conséquence. C'est une option PONCTUELLE par séance (décochée par défaut à chaque boot).",
  action: null
}, {
  title: "💡 Mode « Sujet libre » (hors COURS/)",
  body: 'Coche 💡 et décris ton sujet (« apprendre Python ») → le tuteur s\'appuie uniquement sur ses connaissances LLM, sans matériel COURS. Mode guidé indisponible. Bandeau jaune au clic pour t\'avertir.',
  action: null
}, {
  title: "📷 Prendre une photo depuis ton téléphone",
  body: "Connecte ton téléphone via Tailscale ou un tunnel Cloudflare, ouvre l'URL générée dans l'onglet Distant, prends une photo : elle apparaît automatiquement dans le tray d'envoi du desktop.",
  action: {
    label: "▶ Voir l'onglet Distant",
    fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="mobile"]')
  }
}, {
  title: "📌 Épingler une consigne à respecter",
  body: "Le tuteur oublie parfois une consigne donnée il y a 30 tours. Passe la souris sur une de tes bulles dans le fil → clique sur 📌 pour l'épingler. Elle sera rappelée au tuteur à CHAQUE tour suivant.",
  action: {
    label: "▶ Voir l'onglet Consignes",
    fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="stickies"]')
  }
}, {
  title: "🤖 Demander au tuteur de retenir lui-même",
  body: 'Si tu dis "retiens que je dois toujours écrire la signature avant la fonction", le tuteur émet la balise <<<REMEMBER>>> qui s\'ajoute aux consignes épinglées automatiquement.',
  action: {
    label: "▶ Pré-remplir un draft",
    fn: () => _prefillTextarea("Retiens que ")
  }
}, {
  title: "💾 Sauvegarder une phrase comme note",
  body: "Sélectionne du texte dans n'importe quelle bulle (à toi ou au tuteur), un popup apparaît : 💾 Sauvegarder, 📋 Citer, 🤔 Expliquer, 📝 Copier. Les notes vivent dans l'onglet Notes.",
  action: {
    label: "▶ Voir l'onglet Notes",
    fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="notes"]')
  }
}, {
  title: "📸 Revoir les photos envoyées",
  body: "Toutes les photos que tu as envoyées au tuteur pendant la séance sont archivées dans l'onglet Photos : vignettes cliquables (lightbox), tri anti-chrono, suppression individuelle.",
  action: {
    label: "▶ Voir l'onglet Photos",
    fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="photos"]')
  }
}, {
  title: "✨ Reformuler ton brouillon avant envoi",
  body: "Le bouton ✨ à côté de 📎 ouvre un menu : Reformuler (plus clair), Plus concis, Développer, Corriger fautes. Utile pour transformer une dictée vocale brute en réponse propre.",
  action: {
    label: "▶ Voir le bouton ✨",
    fn: () => _spotlight("#rewrite-btn")
  }
}, {
  title: "🎙 Dicter ta réponse au micro",
  body: "Le bouton 🎤 à côté du textarea capture l'audio, le transcrit via Whisper large-v3 et insère le résultat dans le textarea. Tu peux ensuite l'éditer ou le passer dans ✨ avant d'envoyer.",
  action: {
    label: "▶ Voir le bouton 🎤",
    fn: () => _spotlight("#mic-btn")
  }
}, {
  title: "🔀 Basculer le format de la séance",
  body: "Tape /oral, /photos ou /mixte dans le textarea pour changer le format en cours de séance. Le tuteur acquitte d'un fragment court et adapte sa posture (suggérer/exiger photo, ou s'en passer).",
  action: {
    label: "▶ Pré-remplir /mixte",
    fn: () => _prefillTextarea("/mixte")
  }
}, {
  title: "📘 Basculer l'ancrage corrigé",
  body: "Tape /strict (corrigé fait foi), /consultatif (corrigé visible mais discutable) ou /aucun (sans corrigé). Utile quand le corrigé officiel a une erreur et que le tuteur tourne en boucle dessus.",
  action: {
    label: "▶ Pré-remplir /consultatif",
    fn: () => _prefillTextarea("/consultatif")
  }
}, {
  title: "📚 Lire l'énoncé / corrigé / script pendant la séance",
  body: "L'onglet Docs montre le PDF rasterisé page par page. Quand tu navigues une page, le tuteur reçoit en préfixe « [Contexte lecture : page N/M] » pour qu'il sache ce que tu as sous les yeux.",
  action: {
    label: "▶ Voir l'onglet Docs",
    fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="corrige"]')
  }
}, {
  title: "💬 Reprendre une session interrompue",
  body: "L'onglet Historique liste toutes tes sessions persistées. Clic = soit reprendre (resume avec replay du transcript), soit ouvrir en lecture seule. Le bot peut reprendre une session vieille de plusieurs jours.",
  action: {
    label: "▶ Voir l'onglet Historique",
    fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="history"]')
  }
}, {
  title: "📋 Importer des consignes d'une autre session",
  body: "Dans l'onglet Consignes, le bouton 📋 Importer ouvre un modal 2 étapes : choisis la session source, coche les consignes à copier. Utile pour reprendre des règles établies dans une séance précédente.",
  action: {
    label: "▶ Ouvrir l'onglet Consignes",
    fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="stickies"]')
  }
}, {
  title: "📊 Surveiller ton quota Pro Max",
  body: "L'onglet Quota affiche en temps réel ta consommation : session 5h, hebdo 7j Opus, hebdo Sonnet, overage. Cookie chiffré DPAPI, refresh toutes les 30s.",
  action: {
    label: "▶ Voir l'onglet Quota",
    fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="quota"]')
  }
}, {
  title: "⌨ Maintenir Espace pour parler",
  body: "Quand le focus n'est pas sur un input, maintenir [Espace] active l'enregistrement micro tant que la touche est appuyée. Lâche pour stopper et envoyer la transcription.",
  action: null
}, {
  title: "🛑 Annuler la réflexion en cours du tuteur",
  body: 'Pendant que le tuteur stream sa réponse, le bouton Envoyer devient ⏹ Annuler. Click = modal 2 options : "Reprendre (garder mon message)" ou "Supprimer mon message" (annule + retire la dernière bulle).',
  action: null
}];
function renderTipsList() {
  const list = document.getElementById("tips-list");
  if (!list) return;
  list.innerHTML = "";
  for (const tip of TIPS_CATALOG) {
    const card = document.createElement("div");
    card.className = "tip-card";
    const title = document.createElement("div");
    title.className = "tip-title";
    title.textContent = tip.title;
    card.appendChild(title);
    const body = document.createElement("div");
    body.className = "tip-body";
    const paragraphs = Array.isArray(tip.body) ? tip.body : [tip.body];
    for (const para of paragraphs) {
      const p = document.createElement("div");
      p.className = "tip-body-para";
      p.textContent = para;
      body.appendChild(p);
    }
    card.appendChild(body);
    if (tip.action) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "tip-action";
      btn.textContent = tip.action.label;
      btn.addEventListener("click", e => {
        e.stopPropagation();
        try {
          tip.action.fn();
        } catch (err) {
          console.warn("tip action a planté :", err);
        }
      });
      card.appendChild(btn);
    }
    list.appendChild(card);
  }
}
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    try {
      renderTipsList();
    } catch (_) {}
    try {
      _loadCahierColorsFromStorage();
    } catch (_) {}
    try {
      renderColorsPanel();
    } catch (_) {}
  });
} else {
  try {
    renderTipsList();
  } catch (_) {}
  try {
    _loadCahierColorsFromStorage();
  } catch (_) {}
  try {
    renderColorsPanel();
  } catch (_) {}
}
let _pendingColorSelection = null;
let _pendingColorSelectionExpiry = 0;
function _openColorsTabForSelection(info) {
  _pendingColorSelection = {
    text: info.text,
    bubbleEl: info.bubbleEl,
    messageId: info.messageId
  };
  _pendingColorSelectionExpiry = Date.now() + 60_000;
  const tab = document.querySelector('#sidebar-tabs .sb-tab[data-tab="colors"]');
  if (tab) tab.click();
  renderColorsPanel();
  _hideSelectionToolbar();
}
function _getPendingColorSelection() {
  if (!_pendingColorSelection) return null;
  if (Date.now() > _pendingColorSelectionExpiry) {
    _pendingColorSelection = null;
    return null;
  }
  if (!document.body.contains(_pendingColorSelection.bubbleEl)) {
    _pendingColorSelection = null;
    return null;
  }
  return _pendingColorSelection;
}
const _CAHIER_COLOR_DEFAULTS = {
  "cahier-c-bleu": {
    kind: "stylo",
    default: "#1d4ed8",
    label: "Stylo bleu (défaut prose)"
  },
  "cahier-c-rouge": {
    kind: "stylo",
    default: "#b91c1c",
    label: "Stylo rouge (concept à retenir)"
  },
  "cahier-c-vert": {
    kind: "stylo",
    default: "#15803d",
    label: "Stylo vert (exemples + code)"
  },
  "cahier-c-noir": {
    kind: "stylo",
    default: "#111111",
    label: "Stylo noir (formules LaTeX / maths)"
  },
  "cahier-hl-jaune": {
    kind: "hl",
    default: "#fde047",
    label: "Surligneur jaune (formule vitale)"
  },
  "cahier-hl-vert": {
    kind: "hl",
    default: "#86efac",
    label: "Surligneur vert (sous-titres : titres ## / ###, lignes Méthode/Définition…)"
  },
  "cahier-hl-rose": {
    kind: "hl",
    default: "#f9a8d4",
    label: "Surligneur rose (piège)"
  },
  "cahier-hl-violet": {
    kind: "hl",
    default: "#c4b5fd",
    label: "Surligneur violet (titre de la carte cahier)"
  },
  "note-saved-hl": {
    kind: "hl",
    default: "#fb923c",
    label: "Surligneur 💾 Notes save (n'importe où dans le dialogue)"
  }
};
const _CAHIER_COLORS_STORAGE_KEY = "compagnon_cahier_colors_v1";
function _hexToRgbTriplet(hex) {
  const m = hex.replace("#", "").match(/^([a-f0-9]{2})([a-f0-9]{2})([a-f0-9]{2})$/i);
  if (!m) return "0, 0, 0";
  return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)].join(", ");
}
function _setCahierCSSVar(name, hex) {
  const meta = _CAHIER_COLOR_DEFAULTS[name];
  if (!meta) return;
  const cssVar = `--${name}`;
  if (meta.kind === "stylo") {
    document.documentElement.style.setProperty(cssVar, hex);
  } else {
    document.documentElement.style.setProperty(cssVar, _hexToRgbTriplet(hex));
  }
}
function _saveCahierColorsToStorage() {
  const state = {};
  for (const name of Object.keys(_CAHIER_COLOR_DEFAULTS)) {
    const input = document.querySelector(`#colors-list input[data-name="${name}"]`);
    if (input) state[name] = input.value;
  }
  try {
    localStorage.setItem(_CAHIER_COLORS_STORAGE_KEY, JSON.stringify(state));
  } catch (e) {
    console.warn("localStorage write failed:", e);
  }
}
function _loadCahierColorsFromStorage() {
  let stored = null;
  try {
    const raw = localStorage.getItem(_CAHIER_COLORS_STORAGE_KEY);
    if (raw) stored = JSON.parse(raw);
  } catch (_) {}
  if (!stored || typeof stored !== "object") return;
  for (const [name, hex] of Object.entries(stored)) {
    if (_CAHIER_COLOR_DEFAULTS[name] && typeof hex === "string") {
      _setCahierCSSVar(name, hex);
    }
  }
}
function renderColorsPanel() {
  const list = document.getElementById("colors-list");
  if (!list) return;
  let stored = {};
  try {
    const raw = localStorage.getItem(_CAHIER_COLORS_STORAGE_KEY);
    if (raw) stored = JSON.parse(raw) || {};
  } catch (_) {}
  list.innerHTML = "";
  const pending = _getPendingColorSelection();
  if (pending) {
    const banner = document.createElement("div");
    banner.className = "colors-selection-banner";
    const txt = document.createElement("div");
    txt.className = "colors-selection-banner-txt";
    const preview = (pending.text || "").slice(0, 50);
    txt.innerHTML = `🎯 Sélection active : <em>« ${preview}${pending.text.length > 50 ? "…" : ""} »</em><br>Clique un swatch ci-dessous pour appliquer cette couleur à la sélection (édit du message). Ou clique l'input hex pour remapper globalement.`;
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "colors-selection-cancel";
    cancel.textContent = "✕ Annuler la sélection";
    cancel.addEventListener("click", () => {
      _pendingColorSelection = null;
      renderColorsPanel();
    });
    banner.appendChild(txt);
    banner.appendChild(cancel);
    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "colors-selection-clear";
    clearBtn.textContent = "⌫ Retirer le coloriage de cette sélection";
    clearBtn.addEventListener("click", () => {
      _applyCahierColor({
        text: pending.text,
        bubbleEl: pending.bubbleEl,
        messageId: pending.messageId
      }, "clear");
      _pendingColorSelection = null;
      renderColorsPanel();
    });
    banner.appendChild(clearBtn);
    list.appendChild(banner);
  }
  for (const [name, meta] of Object.entries(_CAHIER_COLOR_DEFAULTS)) {
    const row = document.createElement("div");
    row.className = "colors-row";
    if (pending) row.classList.add("colors-row-selectable");
    const current = stored[name] || meta.default;
    const sample = document.createElement("button");
    sample.type = "button";
    sample.className = "colors-row-sample";
    if (meta.kind === "stylo") {
      sample.style.color = current;
      sample.style.background = "#fefef2";
      sample.textContent = "Aa";
    } else {
      sample.style.background = `rgba(${_hexToRgbTriplet(current)}, 0.55)`;
      sample.style.color = "#1a1a1a";
      sample.textContent = "Aa";
    }
    if (pending) {
      sample.title = "Click pour appliquer cette couleur à la sélection";
      sample.classList.add("colors-row-sample-active");
      sample.addEventListener("click", () => {
        const tag = name.replace(/^cahier-/, "");
        _applyCahierColor({
          text: pending.text,
          bubbleEl: pending.bubbleEl,
          messageId: pending.messageId
        }, tag);
        _pendingColorSelection = null;
        setTimeout(() => renderColorsPanel(), 100);
      });
    } else {
      sample.title = "Aperçu : sélectionne du texte dans une carte cahier pour appliquer";
      sample.style.cursor = "default";
    }
    const label = document.createElement("span");
    label.className = "colors-row-label";
    label.textContent = meta.label;
    const input = document.createElement("input");
    input.type = "color";
    input.value = current;
    input.dataset.name = name;
    input.title = "Remapper globalement (rétroactif, toutes cards)";
    input.addEventListener("input", () => {
      _setCahierCSSVar(name, input.value);
      if (meta.kind === "stylo") {
        sample.style.color = input.value;
      } else {
        sample.style.background = `rgba(${_hexToRgbTriplet(input.value)}, 0.55)`;
      }
      _saveCahierColorsToStorage();
    });
    row.appendChild(sample);
    row.appendChild(label);
    row.appendChild(input);
    list.appendChild(row);
  }
  const resetBtn = document.getElementById("colors-reset-btn");
  if (resetBtn && !resetBtn.dataset.bound) {
    resetBtn.dataset.bound = "1";
    resetBtn.addEventListener("click", () => {
      if (!confirm("Reset toutes les couleurs cahier aux valeurs par défaut ?")) return;
      try {
        localStorage.removeItem(_CAHIER_COLORS_STORAGE_KEY);
      } catch (_) {}
      for (const [name, meta] of Object.entries(_CAHIER_COLOR_DEFAULTS)) {
        _setCahierCSSVar(name, meta.default);
      }
      renderColorsPanel();
    });
  }
}
function setStreamingUI(streaming) {
  if (!sendBtn) return;
  if (streaming) {
    sendBtn.dataset.originalText = sendBtn.textContent;
    sendBtn.textContent = "⏹ Annuler";
    sendBtn.classList.add("cancel-mode");
    sendBtn.title = "Annuler la réflexion du Compagnon";
    if (mediaBtn) mediaBtn.disabled = true;
    if (photoBtn) photoBtn.disabled = true;
    if (rewriteBtn) rewriteBtn.disabled = true;
  } else {
    if (sendBtn.dataset.originalText) {
      sendBtn.textContent = sendBtn.dataset.originalText;
      delete sendBtn.dataset.originalText;
    } else {
      sendBtn.textContent = "Envoyer";
    }
    sendBtn.classList.remove("cancel-mode");
    sendBtn.title = "";
    if (mediaBtn && activeSession) mediaBtn.disabled = false;
    if (photoBtn && activeSession) photoBtn.disabled = false;
    refreshRewriteBtnState();
  }
}
function isStreamingActive() {
  return currentEventSource !== null;
}
async function cancelStream(action) {
  if (!isStreamingActive()) return;
  try {
    currentEventSource.close();
  } catch (_) {}
  currentEventSource = null;
  setStreamingUI(false);
  stopThinkingIndicator();
  if (action === "delete_last_user") {
    const studentBubbles = dialogue.querySelectorAll(".turn.student");
    if (studentBubbles.length > 0) {
      try {
        const last = studentBubbles[studentBubbles.length - 1];
        last.remove();
      } catch (_) {}
    }
  }
  if (currentClaudeTurn && currentClaudeTurn.parentElement) {
    try {
      currentClaudeTurn.parentElement.remove();
    } catch (_) {}
  }
  currentClaudeTurn = null;
  currentClaudeRawText = "";
  try {
    await fetch("/api/cancel_stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        action
      })
    });
  } catch (e) {
    console.warn("cancel_stream POST échec :", e);
  }
}
function openCancelStreamModal() {
  const modal = document.createElement("div");
  modal.id = "cancel-stream-modal";
  modal.className = "modal-overlay";
  modal.innerHTML = `
    <div class="modal-card">
      <h3>⏹ Annuler la réflexion ?</h3>
      <p>Le Compagnon est en train de réfléchir. Tu peux interrompre
      maintenant et choisir quoi faire de ton message :</p>
      <div class="modal-actions">
        <button type="button" class="modal-btn-secondary" id="csm-resume">
          ↩ Reprendre (garder mon message)
        </button>
        <button type="button" class="modal-btn-danger" id="csm-delete">
          🗑 Supprimer mon message
        </button>
        <button type="button" class="modal-btn-cancel" id="csm-back">
          ← Retour (continuer la réflexion)
        </button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  const close = () => {
    try {
      modal.remove();
    } catch (_) {}
  };
  modal.querySelector("#csm-resume").addEventListener("click", () => {
    cancelStream("resume");
    close();
  });
  modal.querySelector("#csm-delete").addEventListener("click", () => {
    cancelStream("delete_last_user");
    close();
  });
  modal.querySelector("#csm-back").addEventListener("click", close);
  modal.addEventListener("click", e => {
    if (e.target === modal) close();
  });
}
function streamResponse() {
  if (currentEventSource) currentEventSource.close();
  currentClaudeTurn = appendTurn("claude", "");
  if (currentClaudeTurn && currentClaudeTurn.parentElement) {
    currentClaudeTurn.parentElement.classList.add("is-streaming");
  }
  currentClaudeRawText = "";
  startThinkingIndicator(currentClaudeTurn);
  setStreamingUI(true);
  const es = new EventSource("/api/stream_response");
  currentEventSource = es;
  es.addEventListener("text", e => {
    const chunk = JSON.parse(e.data);
    stopThinkingIndicator();
    currentClaudeRawText += chunk;
    currentClaudeTurn.innerHTML = renderMarkdown(currentClaudeRawText);
    dialogue.scrollTop = dialogue.scrollHeight;
  });
  es.addEventListener("tts", e => {
    const chunk = JSON.parse(e.data);
    const span = document.createElement("span");
    span.style.fontWeight = "600";
    span.textContent = chunk;
    currentClaudeTurn.appendChild(span);
  });
  es.addEventListener("suggested_edit", e => {
    try {
      const payload = JSON.parse(e.data);
      renderSuggestedEdit(payload);
    } catch (err) {
      console.error("suggested_edit parse error:", err);
    }
  });
  es.addEventListener("end", () => {
    es.close();
    currentEventSource = null;
    setStreamingUI(false);
    stopThinkingIndicator();
    finalizeClaudeTurn();
    respondingToSlideMeta = false;
    finishSession();
  });
  es.addEventListener("cancelled", () => {
    es.close();
    currentEventSource = null;
    setStreamingUI(false);
    stopThinkingIndicator();
    if (currentClaudeTurn && currentClaudeTurn.parentElement) {
      try {
        currentClaudeTurn.parentElement.remove();
      } catch (_) {}
    }
    currentClaudeTurn = null;
    currentClaudeRawText = "";
    respondingToSlideMeta = false;
  });
  es.addEventListener("final_text", e => {
    let payload;
    try {
      payload = JSON.parse(e.data);
    } catch (_) {
      return;
    }
    const filteredText = payload && payload.text || "";
    const stats = payload && payload.stats || {};
    if (!currentClaudeTurn) return;
    currentClaudeRawText = filteredText;
    if (!filteredText.trim()) {
      currentClaudeTurn.innerHTML = '<em style="color:var(--fg-dim);font-size:0.9em;">' + '⚠ Réponse filtrée (dérive détectée). Réessayez via 🔄 Recharger contexte.' + '</em>';
    } else {
      currentClaudeTurn.innerHTML = renderMarkdown(filteredText);
      if (currentClaudeTurn.parentElement) {
        currentClaudeTurn.parentElement.dataset.rawText = filteredText;
      }
    }
    console.info("output_filters: réponse nettoyée, role=%d recited=%d misplaced_next_slide=%d", stats.role_hijacking_lines_removed || 0, stats.recited_paragraphs_removed || 0, stats.misplaced_next_slide_removed || 0);
  });
  es.addEventListener("next_slide", () => {
    if (activeMode !== "guidé" || !guidedSlides.length) return;
    if (guidedIndex >= guidedSlides.length - 1) return;
    if (slideTransitionLocked()) {
      console.warn("next_slide ignoré, cooldown actif (cascade évitée)");
      return;
    }
    if (lastClaudeBubbleHasPendingQuestion()) {
      console.warn("next_slide ignoré, question pendante du tuteur");
      appendTurn("system", "⚠ Transition auto bloquée : le tuteur a posé une question. " + "Réponds d'abord, puis tu pourras avancer (➡ ou tuteur).");
      return;
    }
    const idxAtEmit = guidedIndex;
    setTimeout(() => {
      if (guidedIndex !== idxAtEmit) return;
      if (slideTransitionLocked()) return;
      if (lastClaudeBubbleHasPendingQuestion()) return;
      gotoNextSlide("tuteur");
      markSlideTransition();
    }, 1500);
  });
  es.addEventListener("show_doc", e => {
    if (!correctionsList.length) return;
    let payload;
    try {
      payload = JSON.parse(e.data);
    } catch (_) {
      return;
    }
    const kind = payload && payload.kind || "";
    const page = payload && payload.page || 1;
    const exoTarget = payload && payload.exo != null ? String(payload.exo) : null;
    const targetIdx = _findDocIdx(kind, exoTarget);
    if (targetIdx < 0) {
      console.warn("show_doc: aucun doc kind=%s exo=%s", kind, exoTarget);
      return;
    }
    setTimeout(() => {
      jumpToCorrigePage(page, kind, {
        idx: targetIdx
      });
      const item = correctionsList[targetIdx];
      const total = (item.pages || []).length;
      const safePage = Math.min(Math.max(1, page), Math.max(1, total));
      const kindLbl = _kindLabelFr(kind).toLowerCase();
      appendTurn("system", `🤖 Le tuteur affiche la page ${safePage}/${total} ` + `du ${kindLbl} « ${item.label} ».`);
    }, 800);
  });
  es.addEventListener("goto_slide", e => {
    if (activeMode !== "guidé" || !guidedSlides.length) return;
    let payload;
    try {
      payload = JSON.parse(e.data);
    } catch (_) {
      return;
    }
    const n = payload && payload.n;
    if (!Number.isInteger(n) || n < 1 || n > guidedSlides.length) {
      console.warn("goto_slide n hors plage:", n, "/", guidedSlides.length);
      return;
    }
    if (n - 1 === guidedIndex) return;
    if (slideTransitionLocked()) {
      console.warn("goto_slide ignoré, cooldown actif (cascade évitée)");
      return;
    }
    const idxAtEmit = guidedIndex;
    setTimeout(() => {
      if (guidedIndex !== idxAtEmit) return;
      if (slideTransitionLocked()) return;
      showGuidedSlide(n - 1, true, "tuteur");
      markSlideTransition();
    }, 1500);
  });
  es.addEventListener("sticky_added", e => {
    let sticky;
    try {
      sticky = JSON.parse(e.data);
    } catch (_) {
      return;
    }
    if (!sticky || !sticky.text) return;
    if (typeof _flashSelectionFeedback === "function") {
      const preview = sticky.text.length > 60 ? sticky.text.slice(0, 57) + "…" : sticky.text;
      _flashSelectionFeedback("📌 Consigne ajoutée par le tuteur : « " + preview + " »");
    }
    if (typeof refreshStickies === "function") refreshStickies();
  });
  es.addEventListener("done", () => {
    es.close();
    currentEventSource = null;
    setStreamingUI(false);
    stopThinkingIndicator();
    finalizeClaudeTurn();
    respondingToSlideMeta = false;
    if (typeof refreshDynamicOutline === "function") {
      try {
        refreshDynamicOutline();
      } catch (_) {}
    }
  });
  es.addEventListener("error", e => {
    let info = "";
    let engineFromEvent = "";
    try {
      const parsed = e.data ? JSON.parse(e.data) : null;
      info = parsed ? parsed.message || parsed.detail || "" : "";
      engineFromEvent = parsed ? parsed.engine || "" : "";
    } catch (_) {}
    respondingToSlideMeta = false;
    stopThinkingIndicator();
    const looksLikeQuota = /402|413|insufficient|too.large|tokens per minute|context.length|rate.limit/i.test(info);
    const looksLikeUpstreamUnavailable = /\b50[234]\b|UNAVAILABLE|high.demand|overload|temporarily|service.unavailable/i.test(info);
    if (looksLikeQuota) {
      const fr = formatQuotaErrorFr(engineFromEvent || "?", info);
      const sysMsg = `${fr.title}\n\n${fr.cause}\n\n${fr.suggestion}\n\n` + `Détail technique : ${(info || "").slice(0, 250)}`;
      appendTurn("system", sysMsg);
      flashEngineSwitcher();
    } else if (looksLikeUpstreamUnavailable) {
      const engine = engineFromEvent || "le moteur";
      const sysMsg = `⚠ ${engine} en surcharge temporaire : réponse refusée par le serveur upstream.\n\n` + `Solutions :\n` + ` 1. Réessaie dans 30s-2min (les spikes durent rarement plus).\n` + ` 2. Bascule sur un autre moteur via le sélecteur en haut (clignote en orange ↑).\n\n` + `Détail technique : ${(info || "").slice(0, 250)}`;
      appendTurn("system", sysMsg);
      flashEngineSwitcher();
    } else {
      appendTurn("system", "[Erreur stream] " + (info || "connexion perdue"));
    }
    es.close();
    currentEventSource = null;
    setStreamingUI(false);
  });
  es.addEventListener("quota_midflow", e => {
    stopThinkingIndicator();
    es.close();
    currentEventSource = null;
    respondingToSlideMeta = false;
    try {
      const payload = JSON.parse(e.data);
      renderQuotaMidflowCard(payload);
    } catch (err) {
      appendTurn("system", "[Erreur stream] quota épuisé (parse échoué).");
    }
  });
}
function renderQuotaMidflowCard(payload) {
  const message = payload.message || "Quota épuisé.";
  const available = Array.isArray(payload.available) ? payload.available : [];
  const card = document.createElement("div");
  card.className = "turn quota-midflow-card";
  const role = document.createElement("div");
  role.className = "role";
  role.textContent = "⚠️ Quota épuisé en cours de séance";
  card.appendChild(role);
  const msg = document.createElement("div");
  msg.className = "qmf-message";
  msg.textContent = message;
  card.appendChild(msg);
  if (available.length === 0) {
    const noFallback = document.createElement("div");
    noFallback.className = "qmf-nofallback";
    noFallback.textContent = "Aucun provider de fallback détecté (pas de clé GEMINI_API_KEY / " + "DEEPSEEK_API_KEY / GROQ_API_KEY). Configure-en au moins une et " + "redémarre la séance (Stop puis Lancer dans la GUI Tk).";
    card.appendChild(noFallback);
  } else {
    const help = document.createElement("div");
    help.className = "qmf-help";
    help.textContent = "Bascule à chaud sans perdre l'historique. Choisis un provider :";
    card.appendChild(help);
    const btnRow = document.createElement("div");
    btnRow.className = "qmf-buttons";
    for (const prov of available) {
      const btn = document.createElement("button");
      btn.className = "qmf-btn";
      btn.textContent = `→ ${prov.label}`;
      btn.dataset.engine = prov.engine;
      btn.addEventListener("click", () => switchEngineAndRetry(prov, card));
      btnRow.appendChild(btn);
    }
    card.appendChild(btnRow);
  }
  if (dialogue.querySelector(".placeholder")) dialogue.innerHTML = "";
  dialogue.appendChild(card);
  dialogue.scrollTop = dialogue.scrollHeight;
}
async function switchEngineAndRetry(provider, card) {
  card.querySelectorAll(".qmf-btn").forEach(b => b.disabled = true);
  const status = document.createElement("div");
  status.className = "qmf-status";
  status.textContent = `Bascule sur ${provider.label}…`;
  card.appendChild(status);
  try {
    const r = await fetch("/api/switch_engine", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        engine: provider.engine
      })
    });
    const data = await r.json();
    if (!r.ok) {
      status.textContent = "✗ " + (data.error || `HTTP ${r.status}`);
      card.classList.add("qmf-error");
      card.querySelectorAll(".qmf-btn").forEach(b => b.disabled = false);
      return;
    }
    status.textContent = `✓ Basculé sur ${provider.label} (historique préservé : ${data.history_size} msgs). Reprise…`;
    card.classList.add("qmf-success");
    if (sessionInfo.textContent) {
      sessionInfo.textContent = sessionInfo.textContent.replace(/engine: [^)]+/, `engine: ${provider.engine}`);
    }
    streamResponse();
  } catch (err) {
    status.textContent = "✗ Erreur réseau : " + err.message;
    card.classList.add("qmf-error");
    card.querySelectorAll(".qmf-btn").forEach(b => b.disabled = false);
  }
}
function renderSuggestedEdit(payload) {
  const file = payload.file || "(fichier inconnu)";
  const before = payload.before || "";
  const after = payload.after || "";
  const reason = payload.reason || "";
  const card = document.createElement("div");
  card.className = "turn suggested-edit";
  const role = document.createElement("div");
  role.className = "role";
  role.textContent = "✏ Suggestion de correction";
  card.appendChild(role);
  const fileLabel = document.createElement("div");
  fileLabel.className = "se-file";
  fileLabel.textContent = file;
  card.appendChild(fileLabel);
  if (reason) {
    const why = document.createElement("div");
    why.className = "se-reason";
    why.textContent = reason;
    card.appendChild(why);
  }
  const diff = document.createElement("div");
  diff.className = "se-diff";
  const beforeBlock = document.createElement("div");
  beforeBlock.className = "se-before";
  beforeBlock.textContent = before;
  const afterBlock = document.createElement("div");
  afterBlock.className = "se-after";
  afterBlock.textContent = after;
  diff.appendChild(beforeBlock);
  diff.appendChild(afterBlock);
  card.appendChild(diff);
  const actions = document.createElement("div");
  actions.className = "se-actions";
  const applyBtn = document.createElement("button");
  applyBtn.textContent = "✓ Appliquer";
  applyBtn.className = "se-apply";
  const rejectBtn = document.createElement("button");
  rejectBtn.textContent = "✗ Rejeter";
  rejectBtn.className = "se-reject";
  actions.appendChild(applyBtn);
  actions.appendChild(rejectBtn);
  card.appendChild(actions);
  const status = document.createElement("div");
  status.className = "se-status";
  card.appendChild(status);
  applyBtn.addEventListener("click", async () => {
    applyBtn.disabled = true;
    rejectBtn.disabled = true;
    status.textContent = "Application…";
    try {
      const r = await fetch("/api/apply_edit", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          file,
          before,
          after
        })
      });
      const data = await r.json();
      if (r.ok) {
        status.textContent = `✓ Appliqué (${data.delta_chars >= 0 ? "+" : ""}${data.delta_chars} car., backup ${data.backup})`;
        card.classList.add("applied");
      } else {
        status.textContent = "✗ " + (data.error || `HTTP ${r.status}`);
        applyBtn.disabled = false;
        rejectBtn.disabled = false;
        card.classList.add("apply-error");
      }
    } catch (err) {
      status.textContent = "✗ Erreur réseau : " + err.message;
      applyBtn.disabled = false;
      rejectBtn.disabled = false;
    }
  });
  rejectBtn.addEventListener("click", () => {
    applyBtn.disabled = true;
    rejectBtn.disabled = true;
    status.textContent = "Rejeté";
    card.classList.add("rejected");
  });
  if (dialogue.querySelector(".placeholder")) dialogue.innerHTML = "";
  dialogue.appendChild(card);
  dialogue.scrollTop = dialogue.scrollHeight;
}
function finalizeClaudeTurn() {
  if (!currentClaudeTurn) return;
  renderMathIn(currentClaudeTurn);
  linkifyPageRefs(currentClaudeTurn);
  const turnContainer = currentClaudeTurn.parentElement;
  if (turnContainer) {
    turnContainer.classList.remove("is-streaming");
    turnContainer.dataset.rawText = currentClaudeRawText;
    if (!turnContainer.querySelector(".tone-toolbar")) {
      appendToneToolbar(turnContainer);
    }
  }
}
function appendCreatedDocNotice(text, filename) {
  const t = appendTurn("system", text);
  if (!t) return;
  const bubble = t.parentElement;
  if (!bubble) return;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "doc-link-btn";
  btn.textContent = "📂 Ouvrir dans Docs";
  btn.addEventListener("click", () => {
    const tab = document.querySelector('#sidebar-tabs .sb-tab[data-tab="corrige"]');
    if (tab) tab.click();
    if (!filename) return;
    let attempts = 0;
    const tryShow = () => {
      attempts += 1;
      if (typeof correctionsList === "undefined") return;
      const idx = correctionsList.findIndex(c => c.filename === filename);
      if (idx >= 0) {
        showCorrige(idx, 0);
      } else if (attempts < 10) {
        setTimeout(tryShow, 200);
      }
    };
    setTimeout(tryShow, 250);
  });
  bubble.appendChild(btn);
  return t;
}
function appendTurn(role, text, opts = {}) {
  if (dialogue.querySelector(".placeholder")) dialogue.innerHTML = "";
  const div = document.createElement("div");
  div.className = "turn " + role;
  const markerText = opts.rawText || text || "";
  const looksLikeMarker = role === "student" && markerText.startsWith("[Mode guidé]");
  if (looksLikeMarker) {
    div.classList.add("marker");
    if (markerText.includes("Le tuteur")) {
      div.classList.add("marker-tutor");
    } else {
      div.classList.add("marker-user");
    }
  }
  if (opts.id) div.dataset.msgId = opts.id;
  const r = document.createElement("div");
  r.className = "role";
  r.textContent = role === "student" ? "Toi" : role === "claude" ? "Compagnon" : "Système";
  const timeSpan = document.createElement("span");
  timeSpan.className = "turn-time";
  const atIso = opts.at || new Date().toISOString();
  timeSpan.dataset.atIso = atIso;
  timeSpan.textContent = formatTurnTimeShort(atIso);
  timeSpan.title = formatTurnTimeAbsolute(atIso);
  r.appendChild(timeSpan);
  const flag = document.createElement("span");
  flag.className = "turn-edited-flag";
  flag.textContent = "(modifié)";
  if (!opts.editedAt) flag.style.display = "none";else flag.title = `Modifié à ${formatTurnTimeAbsolute(opts.editedAt)}`;
  r.appendChild(flag);
  const t = document.createElement("div");
  t.textContent = text;
  div.appendChild(r);
  div.appendChild(t);
  if (role === "system") {
    div.dataset.localOnly = "1";
    const actions = document.createElement("div");
    actions.className = "turn-actions";
    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "turn-del-btn";
    delBtn.title = "Masquer cette notification";
    delBtn.textContent = "🗑";
    delBtn.addEventListener("click", e => {
      e.stopPropagation();
      div.remove();
    });
    actions.appendChild(delBtn);
    div.appendChild(actions);
    dialogue.appendChild(div);
    dialogue.scrollTop = dialogue.scrollHeight;
    return t;
  }
  if (looksLikeMarker) {
    div.dataset.rawText = markerText;
    const actions = document.createElement("div");
    actions.className = "turn-actions";
    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "turn-del-btn";
    delBtn.title = "Supprimer cette transition et revenir à la slide précédente";
    delBtn.textContent = "🗑";
    delBtn.addEventListener("click", e => {
      e.stopPropagation();
      deleteTurn(div);
    });
    actions.appendChild(delBtn);
    div.appendChild(actions);
    dialogue.appendChild(div);
    dialogue.scrollTop = dialogue.scrollHeight;
    return t;
  }
  if (role === "student" || role === "claude") {
    div.dataset.rawText = text;
    const actions = document.createElement("div");
    actions.className = "turn-actions";
    if (role === "claude") {
      const ttsBtn = document.createElement("button");
      ttsBtn.type = "button";
      ttsBtn.className = "turn-tts-btn";
      ttsBtn.title = "Écouter cette réponse";
      ttsBtn.textContent = "🔊";
      ttsBtn.addEventListener("click", e => {
        e.stopPropagation();
        toggleTTSPlayer(div);
      });
      actions.appendChild(ttsBtn);
    }
    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "turn-copy-btn";
    copyBtn.title = "Copier le texte de ce message";
    copyBtn.textContent = "📋";
    copyBtn.addEventListener("click", e => {
      e.stopPropagation();
      copyTurnText(div, copyBtn);
    });
    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "turn-edit-btn";
    editBtn.title = "Modifier ce message";
    editBtn.textContent = "✏";
    editBtn.addEventListener("click", e => {
      e.stopPropagation();
      editTurn(div);
    });
    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "turn-del-btn";
    delBtn.title = "Supprimer ce message du contexte";
    delBtn.textContent = "🗑";
    delBtn.addEventListener("click", e => {
      e.stopPropagation();
      deleteTurn(div);
    });
    actions.appendChild(copyBtn);
    actions.appendChild(editBtn);
    actions.appendChild(delBtn);
    div.appendChild(actions);
    if (opts.siblingCount > 1) {
      attachBranchNav(div, opts);
    }
  }
  dialogue.appendChild(div);
  dialogue.scrollTop = dialogue.scrollHeight;
  return t;
}
function attachBranchNav(turnEl, opts) {
  const nav = document.createElement("div");
  nav.className = "turn-branch-nav";
  const idx = (opts.siblingIndex || 0) + 1;
  const count = opts.siblingCount;
  const ids = opts.siblingIds || [];
  const prev = document.createElement("button");
  prev.type = "button";
  prev.className = "turn-branch-prev";
  prev.textContent = "‹";
  prev.title = "Branche précédente";
  prev.disabled = idx <= 1;
  prev.addEventListener("click", e => {
    e.stopPropagation();
    if (idx > 1) switchToBranch(ids[idx - 2]);
  });
  const counter = document.createElement("span");
  counter.className = "turn-branch-counter";
  counter.textContent = `${idx}/${count}`;
  const next = document.createElement("button");
  next.type = "button";
  next.className = "turn-branch-next";
  next.textContent = "›";
  next.title = "Branche suivante";
  next.disabled = idx >= count;
  next.addEventListener("click", e => {
    e.stopPropagation();
    if (idx < count) switchToBranch(ids[idx]);
  });
  nav.appendChild(prev);
  nav.appendChild(counter);
  nav.appendChild(next);
  turnEl.appendChild(nav);
}
async function switchToBranch(targetMsgId) {
  if (!targetMsgId) return;
  try {
    const r = await fetch(`/api/messages/${encodeURIComponent(targetMsgId)}/switch`, {
      method: "POST"
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      alert("Switch échoué : " + (data.error || r.status));
      return;
    }
    rerenderDialogueFromTranscript(data.transcript || []);
  } catch (e) {
    alert("Erreur réseau pendant le switch : " + e.message);
  }
}
const _READING_PREFIX_RE = /^\[Contexte lecture actuelle, l'étudiant consulte[^\]]*\]\s*\n*/;
function _stripReadingPrefix(text) {
  if (!text) return text;
  return text.replace(_READING_PREFIX_RE, "");
}
function _extractOcrBlocksFromText(text) {
  if (!text) return {
    cleanText: text || "",
    ocrBlocks: []
  };
  const headerRe = /\n{1,2}\[OCR pré-traitée par Gemini Flash 2\.5, vérifie qu'elle correspond à ta lecture multimodale, sinon dis-le et signale la divergence à l'étudiant\]:/;
  const m = headerRe.exec(text);
  if (!m) return {
    cleanText: text,
    ocrBlocks: []
  };
  const cleanText = text.slice(0, m.index).replace(/\s+$/, "");
  const ocrSection = text.slice(m.index + m[0].length);
  const parts = ocrSection.split(/\n\n--- OCR de l'image ---\n/);
  const ocrBlocks = [];
  for (const part of parts) {
    if (!part || !part.trim()) continue;
    const lines = part.split("\n");
    let kind = "?";
    let completeness = null;
    let warnings = [];
    let bodyStartIdx = 0;
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      let matched = false;
      const kMatch = /^Type détecté\s*:\s*(.+?)\s*$/.exec(line);
      if (kMatch) {
        kind = kMatch[1];
        matched = true;
      }
      const cMatch = /^Complétude estimée\s*:\s*(\d+)\s*%\s*$/.exec(line);
      if (cMatch) {
        completeness = parseInt(cMatch[1], 10);
        matched = true;
      }
      const wMatch = /^Warnings\s*:\s*(.+?)\s*$/.exec(line);
      if (wMatch) {
        warnings = wMatch[1].split(/\s*(?:,| · )\s*/).filter(w => w.length > 0);
        matched = true;
      }
      if (!matched) {
        if (line.trim() === "") {
          bodyStartIdx = i + 1;
          continue;
        }
        bodyStartIdx = i;
        break;
      }
    }
    const ocr_markdown = lines.slice(bodyStartIdx).join("\n").trim();
    ocrBlocks.push({
      kind_detected: kind,
      completeness_pct: completeness,
      warnings,
      ocr_markdown
    });
  }
  return {
    cleanText,
    ocrBlocks
  };
}
function rerenderDialogueFromTranscript(transcript) {
  dialogue.innerHTML = "";
  for (const entry of transcript) {
    const role = entry.role === "student" ? "student" : "claude";
    let cleanText = role === "student" ? _stripReadingPrefix(entry.text || "") : entry.text || "";
    let ocrBlocksFromTranscript = [];
    if (role === "student") {
      const ext = _extractOcrBlocksFromText(cleanText);
      cleanText = ext.cleanText;
      ocrBlocksFromTranscript = ext.ocrBlocks;
    }
    const turn = appendTurn(role, "", {
      id: entry.id,
      at: entry.at,
      editedAt: entry.edited_at,
      siblingCount: entry.sibling_count,
      siblingIndex: entry.sibling_index,
      siblingIds: entry.sibling_ids,
      rawText: cleanText
    });
    turn.innerHTML = renderMarkdown(cleanText);
    if (turn.parentElement) {
      turn.parentElement.dataset.rawText = cleanText;
    }
    renderMathIn(turn);
    if (role === "student" && ocrBlocksFromTranscript.length > 0) {
      const turnContainer = turn.parentElement;
      if (turnContainer) {
        for (const blk of ocrBlocksFromTranscript) {
          _appendOcrCollapsibleBlock(turnContainer, blk);
        }
      }
    }
    if (role === "claude") {
      linkifyPageRefs(turn);
      const turnContainer = turn.parentElement;
      if (turnContainer && !turnContainer.querySelector(".tone-toolbar")) {
        appendToneToolbar(turnContainer);
      }
    }
  }
}
function _relWithStoragePrefix(a) {
  if (!a || !a.rel_path) return "";
  if (a.storage === "uploads") return `_uploads/${a.rel_path}`;
  return a.rel_path;
}
let _activeEditTextarea = null;
let _editAttachmentSeenIds = new Set();
function _setActiveEditTextarea(ta) {
  _activeEditTextarea = ta;
  if (ta) {
    _editAttachmentSeenIds = new Set();
    fetch("/api/pending_attachments").then(r => r.ok ? r.json() : null).then(d => {
      if (!d) return;
      for (const a of d.attachments || []) {
        if (a.id) _editAttachmentSeenIds.add(a.id);
      }
    }).catch(() => {});
  } else {
    _editAttachmentSeenIds = new Set();
  }
}
function _insertImageMarkdownInEdit(attOrRelPath, original_name) {
  const ta = _activeEditTextarea;
  if (!ta) return;
  if (!document.body.contains(ta)) {
    _setActiveEditTextarea(null);
    return;
  }
  let rel_path;
  let alt;
  if (typeof attOrRelPath === "object" && attOrRelPath !== null) {
    rel_path = _relWithStoragePrefix(attOrRelPath);
    alt = attOrRelPath.original_name || attOrRelPath.filename || original_name || "image";
  } else {
    rel_path = attOrRelPath;
    alt = original_name || "image";
  }
  const md = `![${alt}](${rel_path})`;
  const pos = typeof ta.selectionStart === "number" ? ta.selectionStart : ta.value.length;
  const before = ta.value.slice(0, pos);
  const after = ta.value.slice(pos);
  const sepBefore = before && !before.endsWith("\n") ? "\n\n" : "";
  const sepAfter = after && !after.startsWith("\n") ? "\n\n" : "";
  ta.value = before + sepBefore + md + sepAfter + after;
  try {
    ta.style.height = "auto";
    ta.style.height = Math.min(400, ta.scrollHeight) + "px";
  } catch (_) {}
  const newPos = before.length + sepBefore.length + md.length;
  try {
    ta.focus();
    ta.setSelectionRange(newPos, newPos);
  } catch (_) {}
}
async function editTurn(turnEl) {
  if (!turnEl || !turnEl.parentElement) return;
  if (turnEl.querySelector(".turn-edit-area")) return;
  const all = Array.from(dialogue.querySelectorAll(".turn.student, .turn.claude"));
  const index = all.indexOf(turnEl);
  if (index < 0) return;
  const role = turnEl.classList.contains("student") ? "student" : "claude";
  const rawText = turnEl.dataset.rawText || "";
  const textDiv = turnEl.querySelector(":scope > div:nth-child(2)");
  const actions = turnEl.querySelector(".turn-actions");
  if (textDiv) textDiv.style.display = "none";
  if (actions) actions.style.display = "none";
  const wrap = document.createElement("div");
  wrap.className = "turn-edit-area";
  const ta = document.createElement("textarea");
  ta.className = "turn-edit-textarea";
  ta.value = rawText;
  ta.rows = Math.min(20, Math.max(3, rawText.split("\n").length + 1));
  const attachBtn = document.createElement("button");
  attachBtn.type = "button";
  attachBtn.className = "turn-edit-attach";
  attachBtn.textContent = "📎";
  attachBtn.title = "Joindre une image à ce message";
  const attachInput = document.createElement("input");
  attachInput.type = "file";
  attachInput.accept = "image/*";
  attachInput.multiple = true;
  attachInput.style.display = "none";
  attachBtn.addEventListener("click", () => attachInput.click());
  attachInput.addEventListener("change", async e => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    e.target.value = "";
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f, f.name);
      fd.append("staged", "1");
      try {
        const r = await fetch("/api/upload_attachment", {
          method: "POST",
          body: fd
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) {
          alert(`Upload "${f.name}" échoué : ${data.error || r.status}`);
          continue;
        }
        const relWithPrefix = _relWithStoragePrefix(data);
        const md = data.is_image ? `![${data.original_name || data.filename}](${relWithPrefix})` : `[Pièce jointe : ${data.original_name || data.filename} (${relWithPrefix})]`;
        const sep = ta.value && !ta.value.endsWith("\n\n") ? "\n\n" : "";
        ta.value += sep + md;
        ta.style.height = "auto";
        ta.style.height = Math.min(400, ta.scrollHeight) + "px";
      } catch (err) {
        alert("Erreur réseau upload : " + err.message);
      }
    }
  });
  const ctrls = document.createElement("div");
  ctrls.className = "turn-edit-ctrls";
  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "turn-edit-save";
  saveBtn.textContent = "Modifier";
  saveBtn.title = "Remplace ce message (l'ancien est perdu)";
  const branchBtn = document.createElement("button");
  branchBtn.type = "button";
  branchBtn.className = "turn-edit-branch";
  branchBtn.textContent = "+ Branche";
  branchBtn.title = "Crée une nouvelle branche : l'ancien message reste accessible via les flèches";
  const reloadBtn = document.createElement("button");
  reloadBtn.type = "button";
  reloadBtn.className = "turn-edit-reload";
  reloadBtn.textContent = "🔄 Recharger contexte";
  reloadBtn.title = "Modifie + supprime tout ce qui suit + regénère la réponse du tuteur";
  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "turn-edit-cancel";
  cancelBtn.textContent = "Annuler";
  ctrls.appendChild(attachBtn);
  ctrls.appendChild(attachInput);
  ctrls.appendChild(saveBtn);
  ctrls.appendChild(branchBtn);
  ctrls.appendChild(reloadBtn);
  ctrls.appendChild(cancelBtn);
  wrap.appendChild(ta);
  wrap.appendChild(ctrls);
  turnEl.appendChild(wrap);
  ta.focus();
  ta.setSelectionRange(ta.value.length, ta.value.length);
  _setActiveEditTextarea(ta);
  ta.addEventListener("input", refreshRewriteBtnState);
  refreshRewriteBtnState();
  const cleanup = () => {
    wrap.remove();
    if (textDiv) textDiv.style.display = "";
    if (actions) actions.style.display = "";
    if (_activeEditTextarea === ta) _setActiveEditTextarea(null);
    if (_lastRewriteTargetTextarea === ta) {
      _lastRewriteTargetTextarea = null;
      lastRewriteOriginal = null;
      lastRewriteIntent = null;
      const banner = document.getElementById("rewrite-banner");
      if (banner) banner.remove();
      if (rewriteBannerHandle) {
        clearTimeout(rewriteBannerHandle);
        rewriteBannerHandle = null;
      }
    }
    refreshRewriteBtnState();
  };
  cancelBtn.addEventListener("click", cleanup);
  ta.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      e.preventDefault();
      cleanup();
    } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      saveBtn.click();
    }
  });
  const submit = async asBranch => {
    const newText = ta.value.trim();
    if (!newText) {
      alert("Le message ne peut pas être vide.");
      return;
    }
    if (newText === rawText.trim()) {
      cleanup();
      return;
    }
    saveBtn.disabled = true;
    branchBtn.disabled = true;
    cancelBtn.disabled = true;
    (asBranch ? branchBtn : saveBtn).textContent = "…";
    try {
      const r = await fetch(`/api/messages/${index}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          text: newText,
          as_branch: asBranch
        })
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        alert((asBranch ? "Branche" : "Édition") + " échouée : " + (data.error || r.status));
        saveBtn.disabled = false;
        branchBtn.disabled = false;
        cancelBtn.disabled = false;
        saveBtn.textContent = "Modifier";
        branchBtn.textContent = "+ Branche";
        return;
      }
      if (asBranch || data.branched) {
        try {
          const cs = await fetch("/api/current_session");
          const csd = await cs.json();
          if (csd.active && Array.isArray(csd.transcript)) {
            rerenderDialogueFromTranscript(csd.transcript);
            return;
          }
        } catch (_) {}
      }
      turnEl.dataset.rawText = newText;
      if (textDiv) {
        textDiv.innerHTML = renderMarkdown(newText);
        renderMathIn(textDiv);
      }
      const flag = turnEl.querySelector(".turn-edited-flag");
      if (flag) {
        flag.style.display = "";
        flag.title = `Modifié à ${data.edited_at || "à l'instant"}`;
      }
      cleanup();
    } catch (e) {
      alert("Erreur réseau pendant l'édition : " + e.message);
      saveBtn.disabled = false;
      branchBtn.disabled = false;
      cancelBtn.disabled = false;
      saveBtn.textContent = "Modifier";
      branchBtn.textContent = "+ Branche";
    }
  };
  saveBtn.addEventListener("click", () => submit(false));
  branchBtn.addEventListener("click", () => submit(true));
  reloadBtn.addEventListener("click", async () => {
    const newText = ta.value.trim();
    if (!newText) {
      alert("Le message ne peut pas être vide.");
      return;
    }
    if (!confirm("Modifier ce message et regénérer la réponse du tuteur ?\n\n" + "Tout ce qui vient APRÈS sera perdu (réponse claude actuelle + " + "messages suivants). Action irréversible.")) return;
    saveBtn.disabled = true;
    branchBtn.disabled = true;
    reloadBtn.disabled = true;
    cancelBtn.disabled = true;
    reloadBtn.textContent = "…";
    try {
      if (newText !== rawText.trim()) {
        const pr = await fetch(`/api/messages/${index}`, {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            text: newText,
            as_branch: false
          })
        });
        if (!pr.ok) {
          const d = await pr.json().catch(() => ({}));
          alert("Sauvegarde échouée : " + (d.error || pr.status));
          throw new Error("save_failed");
        }
      }
      const rr = await fetch(`/api/messages/${index}/regenerate`, {
        method: "POST"
      });
      const rd = await rr.json().catch(() => ({}));
      if (!rr.ok) {
        if ((rd.error || "").startsWith("index hors plage")) {
          alert("Désynchronisation détectée entre l'affichage et le backend " + "(probablement après bascule moteur ou suppression). Le " + "dialogue va être resynchronisé depuis le serveur. " + "réessaye ensuite Recharger contexte sur la bulle souhaitée.");
          try {
            const cs = await fetch("/api/current_session");
            const csd = await cs.json();
            if (csd.active && Array.isArray(csd.transcript)) {
              rerenderDialogueFromTranscript(csd.transcript);
            }
          } catch (_) {}
        } else {
          alert("Régénération échouée : " + (rd.error || rr.status));
        }
        throw new Error("regenerate_failed");
      }
      if (_activeEditTextarea === ta) _setActiveEditTextarea(null);
      rerenderDialogueFromTranscript(rd.transcript || []);
      streamResponse();
    } catch (e) {
      saveBtn.disabled = false;
      branchBtn.disabled = false;
      reloadBtn.disabled = false;
      cancelBtn.disabled = false;
      reloadBtn.textContent = "🔄 Recharger contexte";
    }
  });
}
async function copyTurnText(turnEl, btn) {
  if (!turnEl) return;
  const raw = turnEl.dataset.rawText || (turnEl.querySelector(":scope > div:nth-child(2)") || {}).textContent || "";
  if (!raw) return;
  const flash = (txt, cls) => {
    if (!btn) return;
    const orig = btn.textContent;
    btn.textContent = txt;
    btn.classList.add(cls);
    setTimeout(() => {
      btn.textContent = orig;
      btn.classList.remove(cls);
    }, 1200);
  };
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(raw);
      flash("✓", "copied");
      return;
    }
    const ta = document.createElement("textarea");
    ta.value = raw;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    flash(ok ? "✓" : "✗", ok ? "copied" : "copy-err");
  } catch (e) {
    console.warn("copy failed:", e);
    flash("✗", "copy-err");
  }
}
async function deleteTurn(turnEl) {
  if (!turnEl || !turnEl.parentElement) return;
  const all = Array.from(dialogue.querySelectorAll(".turn.student, .turn.claude"));
  const index = all.indexOf(turnEl);
  if (index < 0) return;
  const isMarker = turnEl.classList.contains("marker");
  const confirmMsg = isMarker ? "Supprimer cette transition et revenir à la slide précédente ?" : "Supprimer ce message du contexte ? Cette action est définitive.";
  if (!confirm(confirmMsg)) return;
  try {
    const r = await fetch(`/api/messages/${index}`, {
      method: "DELETE"
    });
    if (!r.ok && r.status !== 204) {
      const err = await r.json().catch(() => ({}));
      alert("Suppression échouée : " + (err.error || r.status));
      return;
    }
    let data = {};
    try {
      data = await r.json();
    } catch (_) {}
    turnEl.remove();
    if (data.was_marker && Number.isInteger(data.new_guided_index) && activeMode === "guidé" && guidedSlides.length) {
      showGuidedSlide(data.new_guided_index, false);
    }
  } catch (e) {
    alert("Erreur réseau pendant la suppression : " + e.message);
  }
}
micBtn.addEventListener("click", async () => {
  if (!isRecording) {
    await startRecording();
  } else {
    abortRecordingAndTranscribe();
  }
});
let recordStartTs = 0;
let recordTimerHandle = null;
let pendingTranscribeAbort = null;
let userInputBeforeRecording = "";
let _recordingTargetTextarea = null;
const userInputPlaceholderDefault = "Tape ta réponse, ou clique 🎤 pour la dicter…";
function _getActiveTextarea() {
  if (_activeEditTextarea && document.body.contains(_activeEditTextarea)) {
    return _activeEditTextarea;
  }
  return userInput;
}
function _autoResizeTextarea(ta) {
  if (!ta) return;
  if (ta === userInput) {
    autoResizeUserInput();
    return;
  }
  try {
    ta.style.height = "auto";
    ta.style.height = Math.min(400, ta.scrollHeight) + "px";
  } catch (_) {}
}
let liveRecognition = null;
let liveTranscriptFinal = "";
function setupLiveRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    return null;
  }
  const rec = new SR();
  rec.continuous = true;
  rec.interimResults = true;
  rec.lang = "fr-FR";
  rec.onresult = e => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const tr = e.results[i][0].transcript;
      if (e.results[i].isFinal) liveTranscriptFinal += tr + " ";else interim += tr;
    }
    const ta = _recordingTargetTextarea || userInput;
    ta.value = (liveTranscriptFinal + interim).trim();
    _autoResizeTextarea(ta);
  };
  rec.onerror = e => {
    if (e.error && !["no-speech", "aborted"].includes(e.error)) {
      console.warn("WebSpeech erreur :", e.error);
    }
  };
  rec.onend = () => {
    if (isRecording && liveRecognition) {
      try {
        rec.start();
      } catch (_) {}
    }
  };
  return rec;
}
function startLiveRecognition() {
  liveTranscriptFinal = "";
  liveRecognition = setupLiveRecognition();
  if (!liveRecognition) return;
  try {
    liveRecognition.start();
  } catch (e) {
    console.warn("WebSpeech start a échoué :", e);
    liveRecognition = null;
  }
}
function stopLiveRecognition() {
  if (!liveRecognition) return;
  try {
    liveRecognition.onresult = null;
    liveRecognition.onend = null;
    liveRecognition.onerror = null;
    if (typeof liveRecognition.abort === "function") {
      liveRecognition.abort();
    } else {
      liveRecognition.stop();
    }
  } catch (_) {}
  liveRecognition = null;
}
async function startRecording() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert("Le navigateur ne supporte pas getUserMedia. Utilise Chrome/Firefox récent.");
    return;
  }
  cancelPendingTranscribe();
  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: true
    });
  } catch (e) {
    alert("Permission micro refusée ou aucun micro détecté : " + e.message);
    return;
  }
  recordedChunks = [];
  let mime = "";
  for (const cand of ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"]) {
    if (MediaRecorder.isTypeSupported(cand)) {
      mime = cand;
      break;
    }
  }
  try {
    mediaRecorder = mime ? new MediaRecorder(micStream, {
      mimeType: mime
    }) : new MediaRecorder(micStream);
  } catch (e) {
    alert("MediaRecorder init échoué : " + e.message);
    releaseMicStream();
    return;
  }
  mediaRecorder.addEventListener("dataavailable", e => {
    if (e.data && e.data.size > 0) recordedChunks.push(e.data);
  });
  mediaRecorder.addEventListener("stop", onRecordingStopped);
  mediaRecorder.start();
  isRecording = true;
  micBtn.classList.add("recording");
  micBtn.textContent = "⏹";
  micBtn.title = "Cliquer pour annuler le mic (garde la preview dans l'input). Entrée envoie directement ce qui est dans l'input.";
  _recordingTargetTextarea = _getActiveTextarea();
  userInputBeforeRecording = _recordingTargetTextarea.value;
  startLiveRecognition();
  _recordingTargetTextarea.value = "";
  _autoResizeTextarea(_recordingTargetTextarea);
  if (_recordingTargetTextarea === userInput) {
    userInput.placeholder = liveRecognition ? "🎤 Parlez… Entrée pour envoyer, ⏹ pour annuler le mic" : "🎤 Parlez… Entrée pour envoyer (input vide sans WebSpeech), ⏹ pour annuler";
  }
  recordIndicator.classList.add("active");
  recordStartTs = Date.now();
  updateRecordIndicator();
  recordTimerHandle = setInterval(updateRecordIndicator, 250);
}
function updateRecordIndicator() {
  const elapsed = Math.floor((Date.now() - recordStartTs) / 1000);
  const m = Math.floor(elapsed / 60);
  const s = elapsed % 60;
  recordIndicator.textContent = `🎤 Enregistrement… ${m}:${s.toString().padStart(2, "0")}`;
}
function stopRecording() {
  if (!mediaRecorder || mediaRecorder.state === "inactive") return;
  mediaRecorder.stop();
  stopLiveRecognition();
  isRecording = false;
  micBtn.classList.remove("recording");
  micBtn.classList.add("transcribing");
  micBtn.textContent = "⏳";
  micBtn.title = "Transcription en cours…";
  if (recordTimerHandle) {
    clearInterval(recordTimerHandle);
    recordTimerHandle = null;
  }
  userInput.placeholder = "⏳ Transcription en cours…";
  recordIndicator.textContent = "⏳ Transcription en cours… (Whisper large-v3)";
}
function releaseMicStream() {
  if (micStream) {
    micStream.getTracks().forEach(t => t.stop());
    micStream = null;
  }
}
async function onRecordingStopped() {
  releaseMicStream();
  const blob = new Blob(recordedChunks, {
    type: mediaRecorder.mimeType || "audio/webm"
  });
  recordedChunks = [];
  const fd = new FormData();
  let ext = "webm";
  if (mediaRecorder.mimeType && mediaRecorder.mimeType.includes("ogg")) ext = "ogg";
  fd.append("audio", blob, `recording.${ext}`);
  pendingTranscribeAbort = new AbortController();
  const myAbort = pendingTranscribeAbort;
  try {
    const r = await fetch("/api/transcribe", {
      method: "POST",
      body: fd,
      signal: myAbort.signal
    });
    const data = await r.json();
    if (!r.ok) {
      alert("Transcription échouée : " + (data.detail || data.error || r.status));
      return;
    }
    const text = (data.text || "").trim();
    if (!text) {
      alert("Transcription vide (silence ou audio trop court).");
      return;
    }
    let target = _recordingTargetTextarea;
    if (!target || !document.body.contains(target)) target = userInput;
    const prev = (userInputBeforeRecording || "").trim();
    target.value = prev ? `${prev} ${text}` : text;
    userInputBeforeRecording = "";
    _recordingTargetTextarea = null;
    _autoResizeTextarea(target);
    refreshRewriteBtnState();
    refreshFindExoBtnState();
    target.focus();
    target.setSelectionRange(target.value.length, target.value.length);
    maybeFlagWhisperHallucination(text);
  } catch (e) {
    if (e.name === "AbortError") {
      return;
    }
    alert("Erreur réseau pendant la transcription : " + e.message);
  } finally {
    if (pendingTranscribeAbort === myAbort) pendingTranscribeAbort = null;
    micBtn.classList.remove("transcribing");
    micBtn.textContent = "🎤";
    micBtn.title = "Cliquer pour démarrer / arrêter l'enregistrement vocal";
    userInput.placeholder = userInputPlaceholderDefault;
    recordIndicator.classList.remove("active");
    recordIndicator.textContent = "Maintenir [Espace] pour parler";
  }
}
function cancelPendingTranscribe() {
  if (!pendingTranscribeAbort) return;
  pendingTranscribeAbort.abort();
  pendingTranscribeAbort = null;
  userInputBeforeRecording = "";
}
function abortRecordingAndTranscribe() {
  if (mediaRecorder) {
    mediaRecorder.removeEventListener("stop", onRecordingStopped);
    if (mediaRecorder.state !== "inactive") {
      try {
        mediaRecorder.stop();
      } catch (_) {}
    }
  }
  stopLiveRecognition();
  releaseMicStream();
  recordedChunks = [];
  isRecording = false;
  let target = _recordingTargetTextarea;
  if (!target || !document.body.contains(target)) target = userInput;
  const preview = target.value.trim();
  const prefix = (userInputBeforeRecording || "").trim();
  if (prefix) {
    target.value = preview ? `${prefix} ${preview}` : prefix;
    _autoResizeTextarea(target);
  }
  userInputBeforeRecording = "";
  _recordingTargetTextarea = null;
  pendingTranscribeAbort = null;
  micBtn.classList.remove("recording", "transcribing");
  micBtn.textContent = "🎤";
  micBtn.title = "Cliquer pour démarrer / arrêter l'enregistrement vocal";
  if (recordTimerHandle) {
    clearInterval(recordTimerHandle);
    recordTimerHandle = null;
  }
  recordIndicator.classList.remove("active");
  recordIndicator.textContent = "Maintenir [Espace] pour parler";
  userInput.placeholder = userInputPlaceholderDefault;
  refreshRewriteBtnState();
}
function formatQuotaErrorFr(engine, rawDetail) {
  const d = (rawDetail || "").toString().toLowerCase();
  const engineHuman = {
    "deepseek_api": "DeepSeek",
    "groq_api": "Groq",
    "gemini_api": "Gemini",
    "api_anthropic": "API Anthropic",
    "cli_subscription": "Claude CLI (Pro Max)"
  }[engine] || engine;
  if (/402|insufficient.balance|insufficient_balance|payment.required|solde/i.test(d)) {
    return {
      title: `💳 ${engineHuman} n'a plus de solde sur ta clé API`,
      cause: "Cause : la clé API du moteur est à zéro crédit. " + "Le moteur ne peut pas répondre tant qu'elle n'est pas rechargée.",
      suggestion: "Solutions :\n" + "  1. Bascule sur un autre moteur (Claude CLI Pro Max = gratuit, " + "Groq/Gemini = free tier généreux).\n" + (engine === "deepseek_api" ? "  2. Recharge ta clé sur https://platform.deepseek.com/billing" : "  2. Vérifie ton plan sur la console du provider")
    };
  }
  const tpmMatch = d.match(/limit\s+(\d+)[,\s]+requested\s+(\d+)/i);
  if (/413|request.too.large|tokens per minute|rate_limit_exceeded/i.test(d)) {
    let cause;
    if (tpmMatch) {
      const limit = parseInt(tpmMatch[1], 10);
      const requested = parseInt(tpmMatch[2], 10);
      cause = `Cause : ta requête fait ${requested.toLocaleString("fr-FR")} tokens, ` + `mais ${engineHuman} n'accepte que ${limit.toLocaleString("fr-FR")} tokens/minute ` + `sur ce niveau de service. Le contexte de la session (script + corrigés + ` + `transcript) est trop gros pour ce moteur.`;
    } else {
      cause = `Cause : la requête dépasse la limite TPM (tokens/minute) du free tier ${engineHuman}.`;
    }
    return {
      title: `📏 ${engineHuman} : requête trop grosse pour ce moteur`,
      cause: cause,
      suggestion: "Solutions :\n" + "  1. Bascule sur un moteur avec un contexte plus large : " + "Claude CLI (1M tokens, Pro Max), Gemini 2.5 Pro (1M tokens, free tier), " + "ou API Anthropic (200k tokens).\n" + "  2. Si tu tiens à ce moteur : passe en plan Dev Tier payant " + "(Groq → https://console.groq.com/settings/billing)."
    };
  }
  if (/context.length|context_length_exceeded|maximum.context/i.test(d)) {
    return {
      title: `📦 ${engineHuman} : contexte de session trop long`,
      cause: `Cause : la session a dépassé la fenêtre de contexte maximale de ce moteur ` + `(historique + script + corrigés cumulés).`,
      suggestion: "Solutions :\n" + "  1. Bascule sur Claude CLI ou Gemini 2.5 Pro (1M tokens chacun).\n" + "  2. Termine cette session et démarre un nouvel exo : l'historique repart à zéro."
    };
  }
  if (/rate.limit|too.many.requests|429/i.test(d)) {
    return {
      title: `⏱ ${engineHuman} : trop de requêtes (rate limit)`,
      cause: `Cause : tu as dépassé le quota de requêtes par minute ou par jour du free tier ${engineHuman}.`,
      suggestion: "Solutions :\n" + "  1. Attends 1-5 minutes et réessaie.\n" + "  2. Bascule sur un autre moteur en attendant."
    };
  }
  if (/quota|usage.limit|claude.*max|anthropic/i.test(d)) {
    return {
      title: `🚫 ${engineHuman} : quota épuisé`,
      cause: `Cause : le quota Pro Max ou les crédits API Anthropic sont épuisés sur cette fenêtre.`,
      suggestion: "Solutions :\n" + "  1. Bascule sur Gemini ou Groq (free tier généreux) en attendant le reset.\n" + "  2. Le reset Pro Max est visible dans le panneau Quota à droite."
    };
  }
  return {
    title: `⚠ ${engineHuman} : indisponible pour cette requête`,
    cause: `Le moteur a refusé la requête. Voir le détail technique ci-dessous.`,
    suggestion: "Solution : bascule sur un autre moteur via le sélecteur en haut."
  };
}
function flashEngineSwitcher() {
  const el = document.getElementById("engine-switcher");
  if (!el) return;
  try {
    el.scrollIntoView({
      behavior: "smooth",
      block: "center"
    });
  } catch (_) {}
  el.classList.remove("flash-attention");
  void el.offsetWidth;
  el.classList.add("flash-attention");
  setTimeout(() => el.classList.remove("flash-attention"), 1900);
  setTimeout(() => {
    try {
      el.focus();
    } catch (_) {}
  }, 200);
}
const COLLE_FORMAT_LABELS = {
  oral: "🎙 Oral",
  photos: "📸 Photos",
  mixte: "🔀 Mixte"
};
const SLASH_COLLE_FORMAT_RE = /^\/(oral|photos?|mixte)\.?\s*$/i;
const colleFormatSelect = startForm.querySelector('[name="colle_format"]');
let _suspendColleFormatChange = false;
function applyColleFormatChips(fmt) {
  let normalized = (fmt || "").toLowerCase();
  if (normalized === "photo") normalized = "photos";
  if (!["oral", "photos", "mixte"].includes(normalized)) normalized = "mixte";
  activeColleFormat = normalized;
  if (colleFormatSelect && colleFormatSelect.value !== normalized) {
    _suspendColleFormatChange = true;
    try {
      colleFormatSelect.value = normalized;
    } finally {
      _suspendColleFormatChange = false;
    }
  }
}
function appendFormatMarker(fmt) {
  if (!dialogue) return;
  const label = COLLE_FORMAT_LABELS[fmt] || fmt;
  const marker = document.createElement("div");
  marker.className = "format-marker";
  marker.innerHTML = `🔀 Format → <strong>${label}</strong>`;
  dialogue.appendChild(marker);
  dialogue.scrollTop = dialogue.scrollHeight;
}
async function setColleFormat(fmt, opts = {}) {
  if (!activeSession) return;
  let normalized = (fmt || "").toLowerCase();
  if (normalized === "photo") normalized = "photos";
  if (!["oral", "photos", "mixte"].includes(normalized)) return;
  if (normalized === activeColleFormat && !opts.force) return;
  try {
    const r = await fetch("/api/set_colle_format", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        format: normalized
      })
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      alert("Bascule format échouée : " + (data.error || r.status));
      return;
    }
    applyColleFormatChips(data.colle_format);
    if (!opts.skipMarker) appendFormatMarker(data.colle_format);
  } catch (e) {
    alert("Erreur réseau bascule format : " + e.message);
  }
}
if (colleFormatSelect) {
  colleFormatSelect.addEventListener("change", () => {
    if (_suspendColleFormatChange) return;
    if (!activeSession) return;
    setColleFormat(colleFormatSelect.value);
  });
}
const CORRIGE_ANCHOR_LABELS = {
  strict: "📘 Strict",
  consultatif: "📖 Consultatif",
  aucun: "🚫 Sans corrigé"
};
const SLASH_CORRIGE_ANCHOR_RE = /^\/(strict|consultatif|aucun|sans[_ ]corrig[ée])\.?\s*$/i;
const corrigeAnchorSelect = startForm.querySelector('[name="corrige_anchor"]');
let _suspendCorrigeAnchorChange = false;
let activeCorrigeAnchor = "strict";
function _normalizeCorrigeAnchor(raw) {
  let v = (raw || "").toLowerCase().trim();
  if (["sans_corrigé", "sans_corrige", "sans corrigé", "sans corrige"].includes(v)) {
    v = "aucun";
  }
  return ["strict", "consultatif", "aucun"].includes(v) ? v : "strict";
}
function applyCorrigeAnchorChips(anchor) {
  const normalized = _normalizeCorrigeAnchor(anchor);
  activeCorrigeAnchor = normalized;
  if (corrigeAnchorSelect && corrigeAnchorSelect.value !== normalized) {
    _suspendCorrigeAnchorChange = true;
    try {
      corrigeAnchorSelect.value = normalized;
    } finally {
      _suspendCorrigeAnchorChange = false;
    }
  }
  if (corrigeAnchorSelect) {
    const sid = activeSession || "";
    const noAnchorContext = activeMode === "workspace" || /_LIBRE_/.test(sid);
    if (noAnchorContext) {
      corrigeAnchorSelect.title = "Pas de corrigé officiel dans ce contexte (workspace / sujet libre), " + "valeur forcée à « aucun » par le backend.";
    } else if (activeSession) {
      corrigeAnchorSelect.title = "Changement mid-session inactif (pas de switch live). La nouvelle " + "valeur s'appliquera au prochain clic Lancer.";
    } else {
      corrigeAnchorSelect.title = "";
    }
    corrigeAnchorSelect.disabled = false;
  }
}
function appendAnchorMarker(anchor) {
  if (!dialogue) return;
  const label = CORRIGE_ANCHOR_LABELS[anchor] || anchor;
  const marker = document.createElement("div");
  marker.className = "anchor-marker";
  marker.innerHTML = `📘 Ancrage → <strong>${label}</strong>`;
  dialogue.appendChild(marker);
  dialogue.scrollTop = dialogue.scrollHeight;
}
async function setCorrigeAnchor(anchor, opts = {}) {
  if (activeSession) return;
}
if (corrigeAnchorSelect) {
  corrigeAnchorSelect.addEventListener("change", () => {
    if (_suspendCorrigeAnchorChange) return;
    if (!activeSession) return;
    setCorrigeAnchor(corrigeAnchorSelect.value);
  });
}
let lastRewriteOriginal = null;
let lastRewriteIntent = null;
let rewriteBannerHandle = null;
let rewriteInFlightAbort = null;
let _lastRewriteTargetTextarea = null;
const REWRITE_INTENT_LABELS = {
  reformulate: "Reformulé",
  concise: "Resserré",
  expand: "Développé",
  fix_typos: "Fautes corrigées"
};
function refreshRewriteBtnState() {
  if (!rewriteBtn) return;
  const ta = _getActiveTextarea();
  const text = ta.value.trim();
  const sessionActive = !userInput.disabled;
  rewriteBtn.disabled = !sessionActive || text.length < 8;
}
function getLastTutorTurnText() {
  if (!dialogue) return "";
  const claudeBubbles = dialogue.querySelectorAll(".turn.claude");
  if (!claudeBubbles.length) return "";
  const last = claudeBubbles[claudeBubbles.length - 1];
  const raw = last.dataset && last.dataset.rawText || "";
  if (raw.trim()) return _stripAttachmentMarkdown(raw);
  const textDiv = last.querySelector(":scope > div:nth-child(2)");
  return _stripAttachmentMarkdown(textDiv && textDiv.textContent || "");
}
function refreshFindExoBtnState() {
  if (!findExoBtn) return;
  const sessionActive = !!activeSession;
  const showInColleOnly = activeMode === "colle";
  findExoBtn.hidden = !showInColleOnly;
  findExoBtn.disabled = !sessionActive || !showInColleOnly;
}
function openRewritePopover() {
  if (!rewritePopover || rewriteBtn?.disabled) return;
  if (!rewritePopover.hidden) {
    closeRewritePopover();
    return;
  }
  if (rewriteUndoBtn) rewriteUndoBtn.hidden = lastRewriteOriginal === null;
  rewritePopover.hidden = false;
  setTimeout(() => {
    document.addEventListener("click", _onClickOutsideRewritePopover);
  }, 0);
}
function closeRewritePopover() {
  if (!rewritePopover) return;
  rewritePopover.hidden = true;
  document.removeEventListener("click", _onClickOutsideRewritePopover);
}
function _onClickOutsideRewritePopover(ev) {
  if (!rewritePopover || rewritePopover.hidden) return;
  if (rewritePopover.contains(ev.target) || rewriteBtn?.contains(ev.target)) return;
  closeRewritePopover();
}
function showRewriteBanner(intent) {
  let banner = document.getElementById("rewrite-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "rewrite-banner";
    const footer = document.getElementById("dialogue-input");
    footer.parentNode.insertBefore(banner, footer);
  }
  const label = REWRITE_INTENT_LABELS[intent] || "Réécrit";
  banner.innerHTML = "";
  const span = document.createElement("span");
  span.textContent = `✨ ${label}, un test ?`;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = "↩ Annuler";
  btn.addEventListener("click", undoLastRewrite);
  banner.appendChild(span);
  banner.appendChild(btn);
  if (rewriteBannerHandle) clearTimeout(rewriteBannerHandle);
  rewriteBannerHandle = setTimeout(() => {
    if (banner) banner.remove();
    rewriteBannerHandle = null;
  }, 8000);
}
function undoLastRewrite() {
  if (lastRewriteOriginal === null) return;
  let ta = _lastRewriteTargetTextarea;
  if (!ta || !document.body.contains(ta)) ta = userInput;
  ta.value = lastRewriteOriginal;
  _autoResizeTextarea(ta);
  ta.focus();
  ta.setSelectionRange(ta.value.length, ta.value.length);
  lastRewriteOriginal = null;
  lastRewriteIntent = null;
  _lastRewriteTargetTextarea = null;
  const banner = document.getElementById("rewrite-banner");
  if (banner) banner.remove();
  if (rewriteBannerHandle) {
    clearTimeout(rewriteBannerHandle);
    rewriteBannerHandle = null;
  }
  refreshRewriteBtnState();
}
async function performRewrite(intent) {
  closeRewritePopover();
  const ta = _getActiveTextarea();
  const text = ta.value.trim();
  if (!text || text.length < 8) {
    alert("Pas assez de texte pour reformuler.");
    return;
  }
  const contextTutor = getLastTutorTurnText();
  if (rewriteInFlightAbort) {
    try {
      rewriteInFlightAbort.abort();
    } catch (_) {}
  }
  rewriteInFlightAbort = new AbortController();
  const myAbort = rewriteInFlightAbort;
  rewriteBtn.classList.add("busy");
  rewriteBtn.textContent = "⏳";
  rewriteBtn.disabled = true;
  ta.readOnly = true;
  try {
    const body = {
      text,
      intent
    };
    if (contextTutor) body.context_tutor = contextTutor;
    const r = await fetch("/api/rewrite", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body),
      signal: myAbort.signal
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const detail = data.detail || data.error || r.status;
      const failedEngine = data.engine || "?";
      if (r.status === 429) {
        const fr = formatQuotaErrorFr(failedEngine, detail);
        const yes = window.confirm(fr.title + "\n\n" + fr.cause + "\n\n" + fr.suggestion + "\n\n" + "Détail technique : " + (detail || "").slice(0, 200) + "\n\n" + "Changer de moteur maintenant ?");
        if (yes) flashEngineSwitcher();
      } else {
        alert(`Rewrite échoué (moteur : ${failedEngine}) : ${detail}`);
      }
      return;
    }
    const rewritten = (data.rewritten || "").trim();
    if (!rewritten) {
      alert("Le rewrite a renvoyé un texte vide : réessaie ou modifie ton brouillon.");
      return;
    }
    lastRewriteOriginal = text;
    lastRewriteIntent = intent;
    _lastRewriteTargetTextarea = ta;
    ta.value = rewritten;
    _autoResizeTextarea(ta);
    ta.focus();
    ta.setSelectionRange(ta.value.length, ta.value.length);
    showRewriteBanner(intent);
  } catch (e) {
    if (e.name !== "AbortError") {
      alert("Erreur réseau pendant le rewrite : " + e.message);
    }
  } finally {
    if (rewriteInFlightAbort === myAbort) rewriteInFlightAbort = null;
    rewriteBtn.classList.remove("busy");
    rewriteBtn.textContent = "✨";
    ta.readOnly = false;
    refreshRewriteBtnState();
    refreshFindExoBtnState();
  }
}
if (rewriteBtn) {
  rewriteBtn.addEventListener("click", ev => {
    ev.stopPropagation();
    openRewritePopover();
  });
}
if (rewritePopover) {
  rewritePopover.querySelectorAll(".rewrite-action").forEach(btn => {
    btn.addEventListener("click", ev => {
      ev.stopPropagation();
      const intent = btn.dataset.intent;
      if (intent) performRewrite(intent);
    });
  });
}
if (rewriteUndoBtn) {
  rewriteUndoBtn.addEventListener("click", ev => {
    ev.stopPropagation();
    closeRewritePopover();
    undoLastRewrite();
  });
}
userInput.addEventListener("input", refreshRewriteBtnState);
let findExoInFlightAbort = null;
let foundExoHistory = [];
let seenWebUrls = [];
let seenYoutubeUrls = [];
async function performFindSimilarExo(opts = {}) {
  let trimmed;
  if (opts.description != null) {
    trimmed = String(opts.description).trim();
    if (trimmed.length < 4) {
      alert("Contexte insuffisant pour la recherche.");
      return;
    }
  } else {
    if (!findExoBtn || findExoBtn.disabled) return;
    const description = window.prompt("Décris brièvement sur quoi tu bloques (ex : « le calcul du bit de parité dans Hamming »). " + "Le compagnon va chercher un exo voisin dans tes cours pour t'entraîner.", "");
    if (description == null) return;
    trimmed = description.trim();
    if (trimmed.length < 4) {
      alert("Décris en quelques mots sur quoi tu bloques.");
      return;
    }
  }
  if (findExoInFlightAbort) {
    try {
      findExoInFlightAbort.abort();
    } catch (_) {}
  }
  findExoInFlightAbort = new AbortController();
  const myAbort = findExoInFlightAbort;
  const searchLabel = opts.difficulty === "easier" ? "📉 Recherche d'un exo plus simple…" : opts.difficulty === "harder" ? "📈 Recherche d'un exo plus dur…" : opts.difficulty === "different" ? "🔄 Recherche d'un autre angle…" : "🔍 Recherche d'un exercice voisin dans tes cours…";
  const searchingBubble = appendTurn("system", searchLabel);
  const searchingTurn = searchingBubble && searchingBubble.parentElement;
  if (findExoBtn) {
    findExoBtn.classList.add("busy");
    findExoBtn.textContent = "⏳";
    findExoBtn.disabled = true;
  }
  try {
    const r = await fetch("/api/find_similar_exo", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        description: trimmed,
        difficulty: opts.difficulty || null,
        exclude: foundExoHistory
      }),
      signal: myAbort.signal
    });
    const data = await r.json().catch(() => ({}));
    if (searchingTurn) searchingTurn.remove();
    if (!r.ok) {
      const detail = data.detail || data.error || r.status;
      if (r.status === 429) {
        const fr = typeof formatQuotaErrorFr === "function" ? formatQuotaErrorFr(data.engine || "?", detail) : null;
        if (fr) {
          alert(fr.title + "\n\n" + fr.cause + "\n\n" + fr.suggestion);
        } else {
          alert("Quota épuisé : " + detail);
        }
      } else {
        alert("Recherche échouée : " + detail);
      }
      return;
    }
    if (!data.found) {
      _renderEmptyExoBubble(data.reason || "Aucun exercice voisin trouvé dans tes cours.", trimmed);
      return;
    }
    if (data.exo) {
      foundExoHistory.push({
        matiere: data.exo.matiere || "",
        type: data.exo.type || "",
        num: data.exo.num || "",
        exo: data.exo.exo || ""
      });
    }
    renderFoundExoBubble(data.exo, trimmed);
  } catch (e) {
    if (searchingTurn) searchingTurn.remove();
    if (e.name !== "AbortError") {
      alert("Erreur réseau : " + e.message);
    }
  } finally {
    if (findExoInFlightAbort === myAbort) findExoInFlightAbort = null;
    if (findExoBtn) {
      findExoBtn.classList.remove("busy");
      findExoBtn.textContent = "🔍";
    }
    refreshFindExoBtnState();
  }
}
function _makeOpenFileBtn(relPath, label, title) {
  const a = document.createElement("a");
  a.className = "found-exo-open-file";
  a.href = `/api/cours_file?path=${encodeURIComponent(relPath)}`;
  a.target = "_blank";
  a.rel = "noopener";
  a.title = title || `Ouvrir ${relPath}`;
  a.textContent = label;
  return a;
}
function renderFoundExoBubble(exo, description) {
  const wrapper = document.createElement("div");
  wrapper.className = "turn system found-exo-bubble";
  wrapper.dataset.localOnly = "1";
  const role = document.createElement("div");
  role.className = "role";
  role.textContent = "💡 Exercice voisin (hors session)";
  const ts = document.createElement("span");
  ts.className = "turn-time";
  const nowIso = new Date().toISOString();
  ts.dataset.atIso = nowIso;
  ts.textContent = formatTurnTimeShort(nowIso);
  ts.title = formatTurnTimeAbsolute(nowIso);
  role.appendChild(ts);
  wrapper.appendChild(role);
  const labelDiv = document.createElement("div");
  labelDiv.className = "found-exo-label";
  const safeMat = (exo.matiere || "").toString().replace(/[<>&]/g, "");
  const safeType = (exo.type || "").toString().replace(/[<>&]/g, "");
  const safeNum = (exo.num || "").toString().replace(/[<>&]/g, "");
  const safeExo = (exo.exo || "").toString().replace(/[<>&]/g, "");
  const safeLabelTxt = (exo.label || "Exercice voisin").toString().replace(/[<>&]/g, "");
  labelDiv.textContent = `📚 ${safeLabelTxt}` + (safeMat ? `   ·   ${safeMat} ${safeType}${safeNum} ex ${safeExo}` : "");
  wrapper.appendChild(labelDiv);
  if (exo.why) {
    const whyDiv = document.createElement("div");
    whyDiv.className = "found-exo-why";
    whyDiv.innerHTML = renderMarkdown("**Pourquoi cet exo ?** " + exo.why);
    wrapper.appendChild(whyDiv);
  }
  if (exo.enonce) {
    const enonceDiv = document.createElement("div");
    enonceDiv.className = "found-exo-enonce";
    enonceDiv.innerHTML = renderMarkdown(exo.enonce);
    wrapper.appendChild(enonceDiv);
  }
  const hint = document.createElement("div");
  hint.className = "found-exo-hint";
  hint.textContent = "⚠ Le tuteur de la colle ne voit pas cet exo. Quand tu reviens, " + "dis-le-lui pour qu'il sache que tu as fait le détour.";
  wrapper.appendChild(hint);
  const fileActions = document.createElement("div");
  fileActions.className = "found-exo-files";
  if (exo.enonce_pdf_path) {
    fileActions.appendChild(_makeOpenFileBtn(exo.enonce_pdf_path, "📄 Voir l'énoncé PDF", "Ouvre l'énoncé original (PDF complet avec schémas)"));
  }
  const corrPaths = Array.isArray(exo.correction_pdf_paths) ? exo.correction_pdf_paths : [];
  if (corrPaths.length === 1) {
    fileActions.appendChild(_makeOpenFileBtn(corrPaths[0], "✅ Voir le corrigé PDF", "Ouvre le corrigé du prof, à n'utiliser qu'APRÈS avoir tenté l'exo voisin chez toi"));
  } else if (corrPaths.length > 1) {
    corrPaths.forEach((p, i) => {
      fileActions.appendChild(_makeOpenFileBtn(p, `✅ Corrigé ${i + 1}`, `Ouvre ${p.split("/").pop()}`));
    });
  }
  if (fileActions.childElementCount > 0) {
    wrapper.appendChild(fileActions);
  }
  const altActions = document.createElement("div");
  altActions.className = "found-exo-alts";
  const altLabel = document.createElement("span");
  altLabel.className = "found-exo-alts-label";
  altLabel.textContent = "Pas satisfait ?";
  altActions.appendChild(altLabel);
  const desc = description || "(contexte précédent)";
  const mkAlt = (label, title, handler) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "found-exo-alt-btn";
    b.title = title;
    b.textContent = label;
    b.addEventListener("click", e => {
      e.stopPropagation();
      b.disabled = true;
      handler().finally(() => {
        b.disabled = false;
      });
    });
    altActions.appendChild(b);
  };
  mkAlt("📉 Plus simple", "Trouve un exo voisin plus simple", () => performFindSimilarExo({
    description: desc,
    difficulty: "easier"
  }));
  mkAlt("📈 Plus dur", "Trouve un exo voisin plus difficile", () => performFindSimilarExo({
    description: desc,
    difficulty: "harder"
  }));
  mkAlt("🔄 Autre angle", "Trouve un exo voisin sous un autre angle", () => performFindSimilarExo({
    description: desc,
    difficulty: "different"
  }));
  mkAlt("✏ Affiner", "Précise ta demande (texte libre) avant de relancer la recherche", () => _refineAndRelaunch(desc));
  mkAlt("🌐 Sur internet", "Cherche des ressources sur internet (sites éducatifs FR)", () => performWebSearchExo(desc));
  mkAlt("🎬 Vidéo YouTube", "Trouve une vidéo explicative sur YouTube", () => performFindYoutube(desc));
  wrapper.appendChild(altActions);
  const actions = document.createElement("div");
  actions.className = "turn-actions";
  if (exo.enonce) {
    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "found-exo-copy";
    copyBtn.title = "Copier l'énoncé";
    copyBtn.textContent = "📋";
    copyBtn.addEventListener("click", async e => {
      e.stopPropagation();
      try {
        await navigator.clipboard.writeText(exo.enonce);
        copyBtn.textContent = "✓";
        setTimeout(() => {
          copyBtn.textContent = "📋";
        }, 1500);
      } catch (_) {
        copyBtn.textContent = "✗";
      }
    });
    actions.appendChild(copyBtn);
  }
  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "turn-del-btn";
  delBtn.title = "Masquer";
  delBtn.textContent = "🗑";
  delBtn.addEventListener("click", e => {
    e.stopPropagation();
    wrapper.remove();
  });
  actions.appendChild(delBtn);
  wrapper.appendChild(actions);
  dialogue.appendChild(wrapper);
  dialogue.scrollTop = dialogue.scrollHeight;
}
if (findExoBtn) {
  findExoBtn.addEventListener("click", ev => {
    ev.stopPropagation();
    performFindSimilarExo();
  });
}
async function _refineAndRelaunch(baseDescription) {
  const refinement = window.prompt("Précise ta demande pour la prochaine recherche d'exo voisin :\n" + "(ex: « plus axé table de vérité », « avec un cas industriel concret », " + "« sans calcul, juste raisonnement »)", "");
  if (refinement == null) return;
  const trimmed = refinement.trim();
  if (trimmed.length < 4) {
    alert("Précision trop courte, abandon.");
    return;
  }
  const enriched = (baseDescription || "").trim() + "\n\nPRÉCISION DE L'ÉTUDIANT : " + trimmed;
  await performFindSimilarExo({
    description: enriched
  });
}
function _renderSearchFailedBubble(emoji, reason, description, target, refinedData = null) {
  const wrapper = document.createElement("div");
  wrapper.className = "turn system found-exo-bubble";
  if (target === "youtube") wrapper.classList.add("found-video-bubble");else if (target === "google") wrapper.classList.add("found-web-bubble");
  wrapper.dataset.localOnly = "1";
  _appendBubbleHeader(wrapper, `${emoji} Recherche infructueuse`);
  const reasonDiv = document.createElement("div");
  reasonDiv.className = "found-exo-why";
  reasonDiv.textContent = reason;
  wrapper.appendChild(reasonDiv);
  _appendDirectSearchInput(wrapper, description, target === "youtube" ? "youtube" : "google", refinedData);
  _appendDelButton(wrapper);
  dialogue.appendChild(wrapper);
  dialogue.scrollTop = dialogue.scrollHeight;
}
function _appendDirectSearchInput(wrapper, description, target, refinedData = null) {
  const initialQuery = refinedData?.query || _extractSimpleSearchQuery(description);
  const queryDiv = document.createElement("div");
  queryDiv.className = "found-search-query";
  const queryLabel = document.createElement("label");
  queryLabel.innerHTML = "Pas ce que tu voulais ? Édite la query " + '<span class="refined-marker" title="Query reformulée par Gemini Flash" hidden>✨</span> : ';
  const refinedMarker = queryLabel.querySelector(".refined-marker");
  const inputId = "search-query-" + Math.random().toString(36).slice(2, 9);
  queryLabel.htmlFor = inputId;
  const queryInput = document.createElement("input");
  queryInput.type = "text";
  queryInput.id = inputId;
  queryInput.className = "found-search-input";
  queryInput.value = initialQuery;
  queryInput.placeholder = "ex : multiplexeur MUX21";
  queryDiv.appendChild(queryLabel);
  queryDiv.appendChild(queryInput);
  const baseUrl = target === "youtube" ? "https://www.youtube.com/results?search_query=" : "https://www.google.com/search?q=";
  const btnLabel = target === "youtube" ? "🔍 Chercher sur YouTube" : "🔍 Chercher sur Google";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "found-exo-direct-search-btn";
  btn.textContent = btnLabel;
  btn.addEventListener("click", e => {
    e.stopPropagation();
    const q = (queryInput.value || "").trim();
    if (!q) {
      queryInput.focus();
      return;
    }
    window.open(baseUrl + encodeURIComponent(q), "_blank", "noopener");
  });
  queryInput.addEventListener("keydown", e => {
    if (e.key === "Enter") {
      e.preventDefault();
      btn.click();
    }
  });
  queryDiv.appendChild(btn);
  const triedQueries = new Set();
  if (refinedData?.query) {
    triedQueries.add(refinedData.query);
    (refinedData.alternatives || []).forEach(a => triedQueries.add(a));
  }
  const reBtn = document.createElement("button");
  reBtn.type = "button";
  reBtn.className = "found-exo-reformulate-btn";
  reBtn.textContent = "🔄";
  reBtn.title = "Reformuler la query (Gemini Flash propose un autre angle)";
  reBtn.addEventListener("click", async e => {
    e.stopPropagation();
    triedQueries.add((queryInput.value || "").trim());
    reBtn.disabled = true;
    reBtn.textContent = "⏳";
    try {
      const fresh = await _refineSearchQuery(description, target, Array.from(triedQueries));
      if (fresh && fresh.query) {
        queryInput.value = fresh.query;
        triedQueries.add(fresh.query);
        (fresh.alternatives || []).forEach(a => triedQueries.add(a));
        if (refinedMarker) refinedMarker.hidden = false;
      } else {
        const alts = (refinedData?.alternatives || []).filter(a => !triedQueries.has(a));
        if (alts.length > 0) {
          queryInput.value = alts[0];
          triedQueries.add(alts[0]);
        } else {
          alert("Plus d'alternatives à proposer. Édite manuellement ?");
        }
      }
    } catch (err) {
      alert("Erreur reformulation : " + err.message);
    } finally {
      reBtn.disabled = false;
      reBtn.textContent = "🔄";
    }
  });
  queryDiv.appendChild(reBtn);
  wrapper.appendChild(queryDiv);
  if (!refinedData) {
    (async () => {
      try {
        const fresh = await _refineSearchQuery(description, target, []);
        if (fresh && fresh.query && queryInput.value === initialQuery) {
          queryInput.value = fresh.query;
          triedQueries.add(fresh.query);
          (fresh.alternatives || []).forEach(a => triedQueries.add(a));
          if (refinedMarker) refinedMarker.hidden = false;
        }
      } catch (_) {}
    })();
  } else if (refinedMarker) {
    refinedMarker.hidden = false;
  }
}
async function _refineSearchQuery(description, target, exclude = []) {
  if (!description) return null;
  try {
    const r = await fetch("/api/refine_search_query", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        description,
        target,
        exclude
      })
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      console.warn("refine_search_query a échoué :", data);
      return null;
    }
    return {
      query: data.query,
      alternatives: data.alternatives || []
    };
  } catch (e) {
    console.warn("refine_search_query erreur réseau :", e);
    return null;
  }
}
function _extractSimpleSearchQuery(description) {
  if (!description) return "";
  let text = String(description);
  text = _stripAttachmentMarkdown(text);
  const tutorMarker = /Le tuteur vient de me (?:dire|demander)\s*\/?\s*(?:demander)?\s*:/i;
  const studentMarker = /Ma dernière intervention était\s*:/i;
  let tutorPart = text;
  const tutorIdx = text.search(tutorMarker);
  if (tutorIdx !== -1) {
    tutorPart = text.slice(tutorIdx).replace(tutorMarker, "");
  }
  const studentIdx = tutorPart.search(studentMarker);
  if (studentIdx !== -1) {
    tutorPart = tutorPart.slice(0, studentIdx);
  }
  tutorPart = tutorPart.replace(/Je bloque pour répondre[\s\S]*$/i, "");
  tutorPart = tutorPart.replace(/PRÉCISION DE L'ÉTUDIANT\s*:[\s\S]*$/i, "");
  tutorPart = tutorPart.replace(/trouve-moi\s+dans\s+mes\s+cours[\s\S]*$/i, "");
  let workText = tutorPart.replace(/\s+/g, " ").trim();
  if (!workText) {
    workText = text.replace(/Le tuteur vient de me (?:dire|demander)\s*\/?\s*(?:demander)?\s*:/gi, "").replace(/Ma dernière intervention était\s*:/gi, "").replace(/Je bloque pour répondre[\s\S]*$/i, "").replace(/PRÉCISION DE L'ÉTUDIANT\s*:[\s\S]*$/i, "").replace(/trouve-moi\s+dans\s+mes\s+cours[\s\S]*$/i, "").replace(/\s+/g, " ").trim();
  }
  if (!workText) return "";
  const sentences = workText.split(/(?<=[.?!])\s+/).map(s => s.trim().replace(/^[-*•·]\s*/, "")).filter(s => s.length >= 8);
  let pick = "";
  if (sentences.length === 0) {
    pick = workText;
  } else {
    const techRegex = /\[[0-9]+(?::[0-9]+)?\]|\b[A-Z]{2,}\b|\b[A-Z][a-z]*[0-9]+\b/g;
    const scored = sentences.map(s => {
      const matches = s.match(techRegex) || [];
      return {
        s,
        score: matches.length,
        len: s.length
      };
    });
    const techPhrases = scored.filter(x => x.score > 0 && x.len <= 220);
    if (techPhrases.length > 0) {
      pick = techPhrases[techPhrases.length - 1].s;
    } else {
      const candidates = scored.filter(x => x.len <= 200);
      pick = candidates.length > 0 ? candidates[candidates.length - 1].s : sentences[sentences.length - 1];
    }
  }
  pick = pick.replace(/^Question\s+\d+(?:[.,]\d+)?\s*:\s*/i, "");
  pick = pick.replace(/[.?!]+\s*$/, "").trim();
  if (pick.length > 100) {
    pick = pick.slice(0, 100).replace(/\s+\S*$/, "");
  }
  return pick;
}
function _renderEmptyExoBubble(reasonText, description) {
  const wrapper = document.createElement("div");
  wrapper.className = "turn system found-exo-bubble found-exo-empty";
  wrapper.dataset.localOnly = "1";
  const role = document.createElement("div");
  role.className = "role";
  role.textContent = "🔍 Aucun exo voisin trouvé";
  const ts = document.createElement("span");
  ts.className = "turn-time";
  const nowIso = new Date().toISOString();
  ts.textContent = formatTurnTimeShort(nowIso);
  ts.title = formatTurnTimeAbsolute(nowIso);
  role.appendChild(ts);
  wrapper.appendChild(role);
  const reasonDiv = document.createElement("div");
  reasonDiv.className = "found-exo-why";
  reasonDiv.textContent = reasonText;
  wrapper.appendChild(reasonDiv);
  const altActions = document.createElement("div");
  altActions.className = "found-exo-alts";
  const altLabel = document.createElement("span");
  altLabel.className = "found-exo-alts-label";
  altLabel.textContent = "Essayer autrement :";
  altActions.appendChild(altLabel);
  const mkAlt = (label, title, handler) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "found-exo-alt-btn";
    b.title = title;
    b.textContent = label;
    b.addEventListener("click", e => {
      e.stopPropagation();
      b.disabled = true;
      handler().finally(() => {
        b.disabled = false;
      });
    });
    altActions.appendChild(b);
  };
  mkAlt("🌐 Sur internet", "Cherche des ressources externes", () => performWebSearchExo(description));
  mkAlt("🎬 Vidéo YouTube", "Trouve une vidéo explicative", () => performFindYoutube(description));
  mkAlt("📚 Passage du CM", "Pointe-moi le passage du cours sur ce concept", () => performFindCmPassage(description));
  wrapper.appendChild(altActions);
  dialogue.appendChild(wrapper);
  dialogue.scrollTop = dialogue.scrollHeight;
}
async function performWebSearchExo(description, opts = {}) {
  if (!description || description.length < 4) {
    alert("Description manquante pour la recherche internet.");
    return;
  }
  const labelExtra = opts.forceEngine === "api_anthropic" ? " (Claude API)" : "";
  const refiningBubble = appendTurn("system", `✨ Reformulation de la query…`);
  const refiningTurn = refiningBubble && refiningBubble.parentElement;
  const refinedData = await _refineSearchQuery(description, "web", []);
  if (refiningTurn) refiningTurn.remove();
  const searchingBubble = appendTurn("system", `🌐 Recherche sur internet${labelExtra}…`);
  const searchingTurn = searchingBubble && searchingBubble.parentElement;
  try {
    const r = await fetch("/api/web_search_exo", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        description,
        exclude_urls: seenWebUrls,
        force_engine: opts.forceEngine || undefined,
        refined_query: refinedData?.query || undefined
      })
    });
    const data = await r.json().catch(() => ({}));
    if (searchingTurn) searchingTurn.remove();
    if (!r.ok) {
      _handleSearchError(r.status, data, description);
      return;
    }
    if (!data.found || !(data.results || []).length) {
      const reason = data.reason || "Aucune ressource pertinente trouvée.";
      _renderSearchFailedBubble("🌐", reason, description, "google", refinedData);
      return;
    }
    (data.results || []).forEach(r2 => {
      if (r2.url) seenWebUrls.push(r2.url);
    });
    _renderWebResultsBubble(data.results, description, data.dead_urls_filtered || 0, refinedData);
  } catch (e) {
    if (searchingTurn) searchingTurn.remove();
    alert("Erreur réseau : " + e.message);
  }
}
async function performFindYoutube(description) {
  if (!description || description.length < 4) {
    alert("Description manquante pour la recherche vidéo.");
    return;
  }
  const refiningBubble = appendTurn("system", "✨ Reformulation de la query…");
  const refiningTurn = refiningBubble && refiningBubble.parentElement;
  const refinedData = await _refineSearchQuery(description, "youtube", []);
  if (refiningTurn) refiningTurn.remove();
  const searchingBubble = appendTurn("system", "🎬 Recherche d'une vidéo YouTube…");
  const searchingTurn = searchingBubble && searchingBubble.parentElement;
  try {
    const r = await fetch("/api/find_youtube_video", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        description,
        exclude_urls: seenYoutubeUrls,
        refined_query: refinedData?.query || undefined
      })
    });
    const data = await r.json().catch(() => ({}));
    if (searchingTurn) searchingTurn.remove();
    if (!r.ok) {
      _handleSearchError(r.status, data, description);
      return;
    }
    if (!data.found || !(data.results || []).length) {
      const reason = data.reason || "Aucune vidéo pertinente trouvée.";
      _renderSearchFailedBubble("🎬", reason, description, "youtube", refinedData);
      return;
    }
    (data.results || []).forEach(v => {
      if (v.url) seenYoutubeUrls.push(v.url);
    });
    _renderYoutubeResultsBubble(data.results, description, data.dead_urls_filtered || 0, refinedData);
  } catch (e) {
    if (searchingTurn) searchingTurn.remove();
    alert("Erreur réseau : " + e.message);
  }
}
async function performFindCmPassage(description) {
  if (!description || description.length < 4) {
    alert("Description manquante.");
    return;
  }
  const searchingBubble = appendTurn("system", "📚 Recherche du passage de CM…");
  const searchingTurn = searchingBubble && searchingBubble.parentElement;
  try {
    const r = await fetch("/api/find_cm_passage", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        description
      })
    });
    const data = await r.json().catch(() => ({}));
    if (searchingTurn) searchingTurn.remove();
    if (!r.ok) {
      const detail = data.detail || data.error || r.status;
      alert("Recherche CM échouée : " + detail);
      return;
    }
    if (!data.found || !data.passage) {
      appendTurn("system", `📚 ${data.reason || "Aucun passage de CM identifié pour ce concept."}`);
      return;
    }
    _renderCmPassageBubble(data.passage, description);
  } catch (e) {
    if (searchingTurn) searchingTurn.remove();
    alert("Erreur réseau : " + e.message);
  }
}
function _handleSearchError(status, data, description) {
  const detail = data.detail || data.error || status;
  if (status === 400 && data.error === "engine_unsupported") {
    const ok = window.confirm("🌐 La recherche internet nécessite Claude API ou Gemini.\n\n" + "Moteur courant : " + (data.engine || "?") + "\n\n" + "Bascule maintenant ? (le sélecteur en haut va clignoter)");
    if (ok && typeof flashEngineSwitcher === "function") {
      flashEngineSwitcher();
    }
    return;
  }
  if (status === 429) {
    const fr = typeof formatQuotaErrorFr === "function" ? formatQuotaErrorFr(data.engine || "?", detail) : null;
    if (fr) alert(fr.title + "\n\n" + fr.cause + "\n\n" + fr.suggestion);else alert("Quota épuisé : " + detail);
    return;
  }
  alert("Recherche échouée : " + detail);
}
function _appendBubbleHeader(wrapper, title) {
  const role = document.createElement("div");
  role.className = "role";
  role.textContent = title;
  const ts = document.createElement("span");
  ts.className = "turn-time";
  const nowIso = new Date().toISOString();
  ts.textContent = formatTurnTimeShort(nowIso);
  ts.title = formatTurnTimeAbsolute(nowIso);
  role.appendChild(ts);
  wrapper.appendChild(role);
}
function _appendDelButton(wrapper) {
  const actions = document.createElement("div");
  actions.className = "turn-actions";
  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "turn-del-btn";
  delBtn.title = "Masquer";
  delBtn.textContent = "🗑";
  delBtn.addEventListener("click", e => {
    e.stopPropagation();
    wrapper.remove();
  });
  actions.appendChild(delBtn);
  wrapper.appendChild(actions);
}
function _renderWebResultsBubble(results, description, deadCount, refinedData = null) {
  const wrapper = document.createElement("div");
  wrapper.className = "turn system found-exo-bubble found-web-bubble";
  wrapper.dataset.localOnly = "1";
  _appendBubbleHeader(wrapper, "🌐 Ressources internet (hors session)");
  if (deadCount && deadCount > 0) {
    const warn = document.createElement("div");
    warn.className = "found-exo-why";
    warn.style.color = "rgba(255, 167, 38, 0.95)";
    warn.textContent = `⚠ ${deadCount} lien(s) supprimé(s) car morts (probable hallucination du modèle).`;
    wrapper.appendChild(warn);
  }
  const list = document.createElement("div");
  list.className = "found-web-list";
  for (const r of results) {
    const item = document.createElement("div");
    item.className = "found-web-item";
    const link = document.createElement("a");
    link.href = r.url || "#";
    link.target = "_blank";
    link.rel = "noopener";
    link.className = "found-web-link";
    link.textContent = r.title || r.url || "Sans titre";
    item.appendChild(link);
    if (r.source) {
      const src = document.createElement("span");
      src.className = "found-web-source";
      src.textContent = " · " + r.source;
      item.appendChild(src);
    }
    if (r.kind) {
      const kind = document.createElement("span");
      kind.className = "found-web-kind";
      kind.textContent = " [" + r.kind + "]";
      item.appendChild(kind);
    }
    if (r.why) {
      const why = document.createElement("div");
      why.className = "found-web-why";
      why.textContent = r.why;
      item.appendChild(why);
    }
    list.appendChild(item);
  }
  wrapper.appendChild(list);
  _appendDirectSearchInput(wrapper, description, "google", refinedData);
  const altActions = document.createElement("div");
  altActions.className = "found-exo-alts";
  const altBtn = document.createElement("button");
  altBtn.type = "button";
  altBtn.className = "found-exo-alt-btn";
  altBtn.textContent = "🌐 Autre ressource";
  altBtn.title = "Cherche d'autres ressources internet (différentes de celles déjà vues)";
  altBtn.addEventListener("click", e => {
    e.stopPropagation();
    altBtn.disabled = true;
    performWebSearchExo(description).finally(() => {
      altBtn.disabled = false;
    });
  });
  altActions.appendChild(altBtn);
  wrapper.appendChild(altActions);
  _appendDelButton(wrapper);
  dialogue.appendChild(wrapper);
  dialogue.scrollTop = dialogue.scrollHeight;
}
function _renderYoutubeResultsBubble(results, description, deadCount, refinedData = null) {
  const wrapper = document.createElement("div");
  wrapper.className = "turn system found-exo-bubble found-video-bubble";
  wrapper.dataset.localOnly = "1";
  _appendBubbleHeader(wrapper, "🎬 Vidéo YouTube (hors session)");
  if (deadCount && deadCount > 0) {
    const warn = document.createElement("div");
    warn.className = "found-exo-why";
    warn.style.color = "rgba(255, 167, 38, 0.95)";
    warn.textContent = `⚠ ${deadCount} vidéo(s) supprimée(s) car URL morte (probable hallucination du modèle).`;
    wrapper.appendChild(warn);
  }
  const list = document.createElement("div");
  list.className = "found-web-list";
  for (const v of results) {
    const item = document.createElement("div");
    item.className = "found-web-item";
    const link = document.createElement("a");
    link.href = v.url || "#";
    link.target = "_blank";
    link.rel = "noopener";
    link.className = "found-web-link";
    link.textContent = v.title || v.url || "Sans titre";
    item.appendChild(link);
    if (v.channel) {
      const ch = document.createElement("span");
      ch.className = "found-web-source";
      ch.textContent = " · " + v.channel;
      item.appendChild(ch);
    }
    if (v.why) {
      const why = document.createElement("div");
      why.className = "found-web-why";
      why.textContent = v.why;
      item.appendChild(why);
    }
    list.appendChild(item);
  }
  wrapper.appendChild(list);
  _appendDirectSearchInput(wrapper, description, "youtube", refinedData);
  const altActions = document.createElement("div");
  altActions.className = "found-exo-alts";
  const altBtn = document.createElement("button");
  altBtn.type = "button";
  altBtn.className = "found-exo-alt-btn";
  altBtn.textContent = "🎬 Autre vidéo";
  altBtn.title = "Trouve une autre vidéo (différente de celles déjà vues)";
  altBtn.addEventListener("click", e => {
    e.stopPropagation();
    altBtn.disabled = true;
    performFindYoutube(description).finally(() => {
      altBtn.disabled = false;
    });
  });
  altActions.appendChild(altBtn);
  wrapper.appendChild(altActions);
  _appendDelButton(wrapper);
  dialogue.appendChild(wrapper);
  dialogue.scrollTop = dialogue.scrollHeight;
}
function _renderCmPassageBubble(passage, description) {
  const wrapper = document.createElement("div");
  wrapper.className = "turn system found-exo-bubble found-cm-bubble";
  wrapper.dataset.localOnly = "1";
  _appendBubbleHeader(wrapper, "📚 Passage du cours (hors session)");
  const labelDiv = document.createElement("div");
  labelDiv.className = "found-exo-label";
  let label = passage.label || passage.filename || "Passage CM";
  if (passage.page != null) label += `   ·   Page ${passage.page}`;
  labelDiv.textContent = "📖 " + label;
  wrapper.appendChild(labelDiv);
  if (passage.why) {
    const whyDiv = document.createElement("div");
    whyDiv.className = "found-exo-why";
    whyDiv.innerHTML = renderMarkdown("**Pourquoi ce passage ?** " + passage.why);
    wrapper.appendChild(whyDiv);
  }
  if (passage.extract) {
    const extractDiv = document.createElement("div");
    extractDiv.className = "found-exo-enonce";
    extractDiv.innerHTML = renderMarkdown(passage.extract);
    wrapper.appendChild(extractDiv);
  }
  if (passage.pdf_path) {
    const fileActions = document.createElement("div");
    fileActions.className = "found-exo-files";
    fileActions.appendChild(_makeOpenFileBtn(passage.pdf_path, "📄 Ouvrir le PDF", "Ouvre le poly du CM dans un nouvel onglet"));
    wrapper.appendChild(fileActions);
  }
  _appendDelButton(wrapper);
  dialogue.appendChild(wrapper);
  dialogue.scrollTop = dialogue.scrollHeight;
}
const attachmentsTray = $("#attachments-tray");
async function uploadAttachmentFile(file) {
  if (!file) return null;
  if (file.type && file.type.startsWith("image/")) {
    const previewResult = await _openImagePreviewBeforeUpload(file);
    if (previewResult === null) {
      return null;
    }
    file = previewResult;
  }
  const fd = new FormData();
  fd.append("file", file, file.name || "attachment.bin");
  if (_activeEditTextarea && !document.body.contains(_activeEditTextarea)) {
    _setActiveEditTextarea(null);
  }
  const isEditMode = _activeEditTextarea !== null;
  if (isEditMode) fd.append("staged", "1");
  try {
    const r = await fetch("/api/upload_attachment", {
      method: "POST",
      body: fd
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      alert(`Upload "${file.name}" échoué : ${data.error || r.status}`);
      return null;
    }
    if (isEditMode && data.is_image) {
      _insertImageMarkdownInEdit(data);
      _flashSelectionFeedback("📷 Image ajoutée à l'édition");
    } else if (isEditMode && !data.is_image) {
      const relWithPrefix = _relWithStoragePrefix(data);
      const md = `[Pièce jointe : ${data.original_name || data.filename} (${relWithPrefix})]`;
      const ta = _activeEditTextarea;
      const sep = ta.value && !ta.value.endsWith("\n\n") ? "\n\n" : "";
      ta.value += sep + md;
      _flashSelectionFeedback("📎 Pièce jointe ajoutée à l'édition");
    } else {
      refreshAttachmentsTray();
    }
    return data;
  } catch (e) {
    alert(`Erreur réseau upload "${file.name}" : ${e.message}`);
    return null;
  }
}
let cropPreviewInstance = null;
let cropPreviewResolve = null;
const cropPreviewModal = $("#crop-preview-modal");
const cropPreviewImg = $("#crop-preview-img");
const cropPreviewClose = $("#crop-preview-close");
const cropPreviewCancel = $("#crop-preview-cancel");
const cropPreviewRotateLeft = $("#crop-preview-rotate-left");
const cropPreviewRotateRight = $("#crop-preview-rotate-right");
const cropPreviewReset = $("#crop-preview-reset");
const cropPreviewSkip = $("#crop-preview-skip");
const cropPreviewApply = $("#crop-preview-apply");
function _openImagePreviewBeforeUpload(file) {
  return new Promise(resolve => {
    if (!cropPreviewModal || !cropPreviewImg) {
      resolve(file);
      return;
    }
    if (typeof Cropper === "undefined") {
      console.warn("Cropper.js non chargé, upload direct sans preview.");
      resolve(file);
      return;
    }
    cropPreviewResolve = resolve;
    cropPreviewModal._originalFile = file;
    const reader = new FileReader();
    reader.onload = e => {
      cropPreviewImg.src = e.target.result;
      cropPreviewModal.hidden = false;
      cropPreviewImg.onload = () => {
        if (cropPreviewInstance) {
          try {
            cropPreviewInstance.destroy();
          } catch (_) {}
          cropPreviewInstance = null;
        }
        cropPreviewInstance = new Cropper(cropPreviewImg, _cropperOptionsCommon());
      };
    };
    reader.readAsDataURL(file);
  });
}
function _closeCropPreviewModal(result) {
  if (!cropPreviewModal) return;
  cropPreviewModal.hidden = true;
  if (cropPreviewInstance) {
    try {
      cropPreviewInstance.destroy();
    } catch (_) {}
    cropPreviewInstance = null;
  }
  if (cropPreviewImg) {
    cropPreviewImg.src = "";
    cropPreviewImg.onload = null;
  }
  delete cropPreviewModal._originalFile;
  if (cropPreviewResolve) {
    const r = cropPreviewResolve;
    cropPreviewResolve = null;
    r(result);
  }
}
if (cropPreviewClose) cropPreviewClose.addEventListener("click", () => _closeCropPreviewModal(null));
if (cropPreviewCancel) cropPreviewCancel.addEventListener("click", () => _closeCropPreviewModal(null));
if (cropPreviewRotateLeft) cropPreviewRotateLeft.addEventListener("click", () => {
  if (cropPreviewInstance) cropPreviewInstance.rotate(-90);
});
if (cropPreviewRotateRight) cropPreviewRotateRight.addEventListener("click", () => {
  if (cropPreviewInstance) cropPreviewInstance.rotate(90);
});
if (cropPreviewReset) cropPreviewReset.addEventListener("click", () => {
  if (cropPreviewInstance) cropPreviewInstance.reset();
});
if (cropPreviewSkip) cropPreviewSkip.addEventListener("click", () => {
  const file = cropPreviewModal._originalFile;
  _closeCropPreviewModal(file || null);
});
if (cropPreviewApply) cropPreviewApply.addEventListener("click", async () => {
  if (!cropPreviewInstance) return;
  cropPreviewApply.disabled = true;
  const orig = cropPreviewApply.textContent;
  cropPreviewApply.textContent = "⏳…";
  try {
    const canvas = cropPreviewInstance.getCroppedCanvas({
      maxWidth: 2000,
      maxHeight: 2000,
      imageSmoothingEnabled: true,
      imageSmoothingQuality: "high"
    });
    if (!canvas) {
      alert("Aucune zone à recadrer.");
      return;
    }
    const blob = await new Promise(r => canvas.toBlob(r, "image/jpeg", 0.92));
    if (!blob) {
      alert("Échec export canvas.");
      return;
    }
    const fname = "cropped_" + Date.now() + ".jpg";
    const cropped = new File([blob], fname, {
      type: "image/jpeg"
    });
    _closeCropPreviewModal(cropped);
  } catch (e) {
    alert("Erreur cropper : " + e.message);
  } finally {
    cropPreviewApply.disabled = false;
    cropPreviewApply.textContent = orig;
  }
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && cropPreviewModal && !cropPreviewModal.hidden) {
    _closeCropPreviewModal(null);
  }
});
async function refreshAttachmentsTray() {
  if (!attachmentsTray) return;
  try {
    const r = await fetch("/api/pending_attachments");
    if (!r.ok) return;
    const data = await r.json();
    let atts = data.attachments || [];
    if (_activeEditTextarea && !document.body.contains(_activeEditTextarea)) {
      _setActiveEditTextarea(null);
    }
    if (_activeEditTextarea) {
      const redirected = [];
      const kept = [];
      for (const att of atts) {
        if (!att.id || _editAttachmentSeenIds.has(att.id)) {
          kept.push(att);
          continue;
        }
        _editAttachmentSeenIds.add(att.id);
        if (att.is_image) {
          _insertImageMarkdownInEdit(att);
          redirected.push(att);
        } else {
          const relWithPrefix = _relWithStoragePrefix(att);
          const md = `[Pièce jointe : ${att.original_name || att.filename} (${relWithPrefix})]`;
          const ta = _activeEditTextarea;
          const sep = ta.value && !ta.value.endsWith("\n\n") ? "\n\n" : "";
          ta.value += sep + md;
          redirected.push(att);
        }
      }
      for (const att of redirected) {
        try {
          await fetch(`/api/pending_attachments/${att.id}`, {
            method: "DELETE"
          });
        } catch (_) {}
      }
      if (redirected.length > 0) {
        _flashSelectionFeedback(redirected.length === 1 ? "📷 Photo insérée dans l'édition" : `📷 ${redirected.length} pièces insérées dans l'édition`);
      }
      atts = kept;
    }
    if (atts.length === 0) {
      attachmentsTray.innerHTML = "";
      attachmentsTray.hidden = true;
      return;
    }
    attachmentsTray.hidden = false;
    attachmentsTray.innerHTML = "";
    for (const att of atts) {
      const item = document.createElement("div");
      item.className = "att-item";
      const thumb = document.createElement("div");
      thumb.className = "att-thumb";
      if (att.is_image) {
        const imgSrc = _attachmentSrcUrl(att);
        const img = document.createElement("img");
        img.src = imgSrc;
        img.alt = "";
        img.style.cssText = "width:100%;height:100%;object-fit:cover;border-radius:3px;cursor:zoom-in;";
        img.title = "Cliquer pour agrandir";
        img.addEventListener("click", e => {
          e.stopPropagation();
          openLightbox(imgSrc);
        });
        thumb.appendChild(img);
      } else {
        const ext = (att.filename || "").split(".").pop().toLowerCase();
        const icon = {
          pdf: "📕",
          doc: "📄",
          docx: "📄",
          xls: "📊",
          xlsx: "📊",
          csv: "📊",
          ppt: "📽",
          pptx: "📽",
          txt: "📝",
          md: "📝",
          json: "🧾"
        }[ext] || "📎";
        thumb.textContent = icon;
      }
      const info = document.createElement("div");
      info.className = "att-info";
      const nameEl = document.createElement("div");
      nameEl.className = "att-name";
      nameEl.textContent = att.original_name || att.filename;
      nameEl.title = att.rel_path;
      info.appendChild(nameEl);
      const sizeEl = document.createElement("div");
      sizeEl.className = "att-size";
      sizeEl.textContent = formatAttSize(att.size_bytes);
      info.appendChild(sizeEl);
      if (att.is_image) {
        const crop = document.createElement("button");
        crop.className = "att-crop";
        crop.type = "button";
        crop.textContent = "✂";
        crop.title = "Rogner cette photo";
        crop.addEventListener("click", () => openCropModal(att));
        item.appendChild(thumb);
        item.appendChild(info);
        item.appendChild(crop);
      } else {
        item.appendChild(thumb);
        item.appendChild(info);
      }
      const del = document.createElement("button");
      del.className = "att-del";
      del.type = "button";
      del.textContent = "🗑";
      del.title = "Retirer cette pièce jointe";
      del.addEventListener("click", async () => {
        try {
          await fetch(`/api/pending_attachments/${encodeURIComponent(att.id)}`, {
            method: "DELETE"
          });
          refreshAttachmentsTray();
        } catch (e) {
          alert("Erreur : " + e.message);
        }
      });
      item.appendChild(del);
      attachmentsTray.appendChild(item);
    }
  } catch (e) {}
}
function formatAttSize(bytes) {
  if (!bytes) return "0";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " kB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}
if (mediaBtn) {
  mediaBtn.addEventListener("click", () => {
    if (mediaInput) mediaInput.click();
  });
}
if (mediaInput) {
  mediaInput.addEventListener("change", async e => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    for (const f of files) await uploadAttachmentFile(f);
    mediaInput.value = "";
    userInput.focus();
  });
}
const photoBtn = $("#photo-btn");
const photoInput = $("#photo-input");
function isMobileDeviceForPhoto() {
  const hasTouch = navigator.maxTouchPoints > 0 || 'ontouchstart' in window;
  return hasTouch && window.innerWidth < 900;
}
function flashRemoteTab() {
  const tab = document.querySelector('#sidebar-tabs .sb-tab[data-tab="mobile"]');
  if (tab) tab.click();
  const pane = document.querySelector('#sidebar-tab-content .sb-pane[data-pane="mobile"]');
  if (!pane) return;
  try {
    pane.scrollIntoView({
      behavior: "smooth",
      block: "center"
    });
  } catch (_) {}
  pane.classList.remove("flash-attention");
  void pane.offsetWidth;
  pane.classList.add("flash-attention");
  setTimeout(() => pane.classList.remove("flash-attention"), 1900);
}
function openPhotoFlow() {
  if (isMobileDeviceForPhoto()) {
    if (photoInput) photoInput.click();
  } else {
    flashRemoteTab();
    showPhotoDesktopHint();
  }
}
let _photoHintTimer = null;
function showPhotoDesktopHint() {
  const tray = $("#attachments-tray");
  if (!tray) return;
  let hint = document.getElementById("photo-desktop-hint");
  if (!hint) {
    hint = document.createElement("div");
    hint.id = "photo-desktop-hint";
    hint.className = "photo-desktop-hint";
    tray.parentElement && tray.parentElement.insertBefore(hint, tray);
  }
  hint.textContent = "📱 Scanne le QR ou ouvre l'URL Tailscale sur ton téléphone pour prendre une photo (page /mobile).";
  hint.hidden = false;
  if (_photoHintTimer) clearTimeout(_photoHintTimer);
  _photoHintTimer = setTimeout(() => {
    hint.hidden = true;
    _photoHintTimer = null;
  }, 7000);
}
if (photoBtn) {
  photoBtn.addEventListener("click", openPhotoFlow);
}
if (photoInput) {
  photoInput.addEventListener("change", async e => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    for (const f of files) await uploadAttachmentFile(f);
    photoInput.value = "";
    userInput.focus();
  });
}
let cropperInstance = null;
let cropTargetAttId = null;
const cropModal = $("#crop-modal");
const cropImg = $("#crop-img");
const cropClose = $("#crop-close");
const cropCancel = $("#crop-cancel");
const cropReset = $("#crop-reset");
const cropApply = $("#crop-apply");
const cropRotateLeft = $("#crop-rotate-left");
const cropRotateRight = $("#crop-rotate-right");
function openCropModal(att) {
  if (!cropModal || !cropImg) return;
  if (typeof Cropper === "undefined") {
    alert("Cropper.js non chargé. Recharge la page.");
    return;
  }
  cropTargetAttId = att.id;
  cropImg.src = `${_attachmentSrcUrl(att)}&t=${Date.now()}`;
  cropImg.alt = att.original_name || att.filename || "Photo";
  cropModal.hidden = false;
  cropImg.onload = () => {
    if (cropperInstance) {
      try {
        cropperInstance.destroy();
      } catch (_) {}
      cropperInstance = null;
    }
    cropperInstance = new Cropper(cropImg, _cropperOptionsCommon());
  };
}
function closeCropModal() {
  if (!cropModal) return;
  cropModal.hidden = true;
  if (cropperInstance) {
    try {
      cropperInstance.destroy();
    } catch (_) {}
    cropperInstance = null;
  }
  cropTargetAttId = null;
  if (cropImg) {
    cropImg.src = "";
    cropImg.onload = null;
  }
}
async function applyCrop() {
  if (!cropperInstance || !cropTargetAttId) return;
  const attId = cropTargetAttId;
  let canvas;
  try {
    canvas = cropperInstance.getCroppedCanvas({
      maxWidth: 2000,
      maxHeight: 2000,
      imageSmoothingEnabled: true,
      imageSmoothingQuality: "high"
    });
  } catch (e) {
    alert("Erreur Cropper : " + e.message);
    return;
  }
  if (!canvas) {
    alert("Aucune zone à recadrer.");
    return;
  }
  cropApply.disabled = true;
  cropApply.textContent = "⏳ Envoi…";
  const blob = await new Promise(resolve => {
    canvas.toBlob(resolve, "image/jpeg", 0.92);
  });
  if (!blob) {
    alert("Échec de l'export du canvas.");
    cropApply.disabled = false;
    cropApply.textContent = "✂ Recadrer & remplacer";
    return;
  }
  const fd = new FormData();
  fd.append("file", blob, `cropped_${Date.now()}.jpg`);
  try {
    const r = await fetch(`/api/pending_attachments/${encodeURIComponent(attId)}/replace`, {
      method: "POST",
      body: fd
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      alert("Recadrage échoué : " + (data.error || r.status));
      return;
    }
    refreshAttachmentsTray();
    closeCropModal();
  } catch (e) {
    alert("Erreur réseau crop : " + e.message);
  } finally {
    cropApply.disabled = false;
    cropApply.textContent = "✂ Recadrer & remplacer";
  }
}
if (cropClose) cropClose.addEventListener("click", closeCropModal);
if (cropCancel) cropCancel.addEventListener("click", closeCropModal);
if (cropReset) cropReset.addEventListener("click", () => {
  if (cropperInstance) cropperInstance.reset();
});
if (cropApply) cropApply.addEventListener("click", applyCrop);
if (cropRotateLeft) cropRotateLeft.addEventListener("click", () => {
  if (cropperInstance) cropperInstance.rotate(-90);
});
if (cropRotateRight) cropRotateRight.addEventListener("click", () => {
  if (cropperInstance) cropperInstance.rotate(90);
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && cropModal && !cropModal.hidden) {
    closeCropModal();
  }
});
async function handlePasteEvent(e) {
  if (!activeSession) return;
  const clipData = e.clipboardData;
  if (!clipData) return;
  const files = [];
  const seen = new Set();
  const _push = f => {
    if (!f) return;
    const key = `${f.size}|${f.type}`;
    if (seen.has(key)) return;
    seen.add(key);
    files.push(f);
  };
  for (const it of clipData.items || []) {
    const isImageType = it.type && it.type.startsWith("image/");
    if (it.kind === "file" || isImageType) {
      _push(it.getAsFile());
    }
  }
  for (const f of clipData.files || []) {
    _push(f);
  }
  if (files.length === 0) return;
  e.preventDefault();
  const stamped = files.map(f => {
    const hasGoodName = f.name && f.name !== "" && f.name !== "image.png";
    if (hasGoodName) return f;
    const ext = f.type && f.type.split("/")[1] || "bin";
    const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    return new File([f], `paste-${ts}.${ext}`, {
      type: f.type
    });
  });
  const isImg = stamped.some(f => f.type && f.type.startsWith("image/"));
  if (isImg) _flashSelectionFeedback("📷 Image collée : chargement…");
  for (const f of stamped) {
    await uploadAttachmentFile(f);
  }
  try {
    if (attachmentsTray && attachmentsTray.children.length > 0) {
      attachmentsTray.scrollIntoView({
        behavior: "smooth",
        block: "center"
      });
    }
  } catch (_) {}
}
document.addEventListener("paste", handlePasteEvent);
let dragDepth = 0;
document.addEventListener("dragenter", e => {
  if (!activeSession) return;
  if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files")) {
    dragDepth++;
    document.body.classList.add("drop-active");
  }
});
document.addEventListener("dragleave", () => {
  if (dragDepth > 0) dragDepth--;
  if (dragDepth === 0) document.body.classList.remove("drop-active");
});
document.addEventListener("dragover", e => {
  if (!activeSession) return;
  if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files")) {
    e.preventDefault();
  }
});
document.addEventListener("drop", async e => {
  if (!activeSession) return;
  if (!e.dataTransfer || !e.dataTransfer.files || e.dataTransfer.files.length === 0) return;
  e.preventDefault();
  dragDepth = 0;
  document.body.classList.remove("drop-active");
  for (const f of Array.from(e.dataTransfer.files)) {
    await uploadAttachmentFile(f);
  }
});
setInterval(refreshAttachmentsTray, 2000);
refreshAttachmentsTray();
async function initGuidedPanel(startIndex = 0, overrides = null) {
  try {
    const params = new URLSearchParams();
    if (overrides && overrides.script_path) params.set("script_path", overrides.script_path);
    if (overrides && overrides.slides_path) params.set("slides_path", overrides.slides_path);
    const url = "/api/guided/init" + (params.toString() ? "?" + params : "");
    const r = await fetch(url);
    const ct = r.headers.get("content-type") || "";
    if (!ct.includes("application/json")) {
      appendTurn("system", `Mode guidé : endpoint /api/guided/init absent (HTTP ${r.status}). ` + `Redémarre le backend Compagnon, l'app.py qui tourne est antérieur ` + `à Phase A.7.2 v5. Repli en mode lecture libre.`);
      return;
    }
    const data = await r.json();
    if (!r.ok) {
      if (data.guided_fallback_required) {
        openGuidedFallbackModal(data, startIndex);
        return;
      }
      appendTurn("system", `Mode guidé indisponible : ${data.error || r.status}. Repli en mode lecture libre.`);
      return;
    }
    guidedSlides = data.slides || [];
    guidedTitleGlobal = data.titre_global || "";
    if (!guidedSlides.length) {
      appendTurn("system", "Mode guidé : aucune slide trouvée.");
      return;
    }
    if (data.inconsistency) {
      renderInconsistencyBanner(data.inconsistency);
    }
    if (data.lite) {
      renderGuidedLiteNotice(data.lite_reason || "Mode lite actif.");
    }
    guidedPanel.hidden = false;
    const safeStart = Math.min(Math.max(0, startIndex), guidedSlides.length - 1);
    guidedIndex = safeStart;
    showGuidedSlide(safeStart, false);
  } catch (e) {
    appendTurn("system", "Mode guidé : erreur réseau (" + e.message + ").");
  }
}
function showGuidedSlide(i, announceToClaude, source = "user") {
  if (i < 0 || i >= guidedSlides.length) return;
  guidedIndex = i;
  if (activeSession) {
    fetch("/api/state/guided_index", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        index: i
      })
    }).catch(() => {});
  }
  const slide = guidedSlides[i];
  guidedCounter.textContent = `${i + 1} / ${guidedSlides.length}`;
  guidedTitle.textContent = slide.title || `(slide ${slide.n})`;
  guidedDuration.textContent = slide.duration_min ? `Durée cible : ${slide.duration_min} min` : "";
  if (slide.png_url) {
    guidedImg.src = slide.png_url;
    guidedImg.hidden = false;
    guidedPlaceholder.hidden = true;
  } else {
    guidedImg.hidden = true;
    guidedPlaceholder.hidden = false;
    guidedPlaceholder.textContent = "(pas d'image rasterizée)";
  }
  guidedPrev.disabled = i === 0;
  guidedNext.disabled = i === guidedSlides.length - 1;
  if (announceToClaude && activeSession) {
    sendGuidedSlideMeta(slide, source);
  }
}
function sendGuidedSlideMeta(slide, source) {
  const verb = source === "tuteur" ? "Le tuteur a fait avancer à" : "L'étudiant est passé à";
  const instr = `[Mode guidé] ${verb} la slide ${slide.n}/${guidedSlides.length}` + (slide.title ? ` : « ${slide.title} »` : "") + ".";
  const t = appendTurn("student", "", {
    rawText: instr
  });
  t.innerHTML = renderMarkdown(instr);
  if (t.parentElement) t.parentElement.dataset.rawText = instr;
  respondingToSlideMeta = true;
  fetch("/api/send_message", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      text: instr
    })
  }).then(r => {
    if (r.ok || r.status === 202) streamResponse();else respondingToSlideMeta = false;
  }).catch(e => {
    console.warn("guidé meta send a échoué :", e);
    respondingToSlideMeta = false;
  });
}
function gotoNextSlide(source = "user") {
  if (activeMode !== "guidé" || !guidedSlides.length) return;
  if (guidedIndex < guidedSlides.length - 1) {
    showGuidedSlide(guidedIndex + 1, true, source);
  }
}
function gotoPrevSlide(source = "user") {
  if (activeMode !== "guidé" || !guidedSlides.length) return;
  if (guidedIndex > 0) {
    showGuidedSlide(guidedIndex - 1, true, source);
  }
}
function jumpToSlide() {
  if (activeMode !== "guidé" || !guidedSlides.length) return;
  const ans = window.prompt(`Aller à la slide n° (1 - ${guidedSlides.length}) :`, String(guidedIndex + 1));
  if (!ans) return;
  const n = parseInt(ans, 10);
  if (Number.isFinite(n) && n >= 1 && n <= guidedSlides.length) {
    showGuidedSlide(n - 1, true, "user");
  }
}
if (guidedNext) guidedNext.addEventListener("click", gotoNextSlide);
if (guidedPrev) guidedPrev.addEventListener("click", gotoPrevSlide);
if (guidedJump) guidedJump.addEventListener("click", jumpToSlide);
const lightbox = $("#lightbox");
const lightboxImg = $("#lightbox-img");
function openLightbox(src) {
  if (!lightbox || !lightboxImg || !src) return;
  lightboxImg.src = src;
  lightbox.hidden = false;
}
function closeLightbox() {
  if (!lightbox) return;
  lightbox.hidden = true;
  if (lightboxImg) lightboxImg.src = "";
}
if (guidedImg) {
  guidedImg.addEventListener("click", () => {
    if (guidedImg.src) openLightbox(guidedImg.src);
  });
}
if (lightbox) {
  lightbox.addEventListener("click", closeLightbox);
}
dialogue.addEventListener("click", e => {
  const del = e.target.closest(".md-img-del");
  if (del) {
    e.preventDefault();
    e.stopPropagation();
    const turnEl = del.closest(".turn.student");
    if (!turnEl) return;
    const wrap = del.closest(".md-img-wrap");
    if (!wrap) return;
    const md = wrap.dataset.md || "";
    handleRemoveAttachmentFromMessage(turnEl, md);
    return;
  }
  const img = e.target.closest(".md-img");
  if (img && img.src) {
    openLightbox(img.src);
  }
});
async function handleRemoveAttachmentFromMessage(turnEl, mdLine) {
  if (!mdLine) return;
  if (!confirm("Retirer cette pièce jointe du message ?")) return;
  const all = Array.from(dialogue.querySelectorAll(".turn.student, .turn.claude"));
  const index = all.indexOf(turnEl);
  if (index < 0) return;
  const rawText = turnEl.dataset.rawText || "";
  const decodedMd = mdLine.replace(/&quot;/g, '"').replace(/&amp;/g, "&");
  let newText = rawText.replace(decodedMd, "");
  newText = newText.replace(/\n{3,}/g, "\n\n").trim();
  if (!newText) {
    if (confirm("Le message ne contient plus rien d'autre. Supprimer entièrement le message ?")) {
      deleteTurn(turnEl);
    }
    return;
  }
  try {
    const r = await fetch(`/api/messages/${index}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        text: newText,
        silent: true
      })
    });
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      alert("Suppression échouée : " + (d.error || r.status));
      return;
    }
    turnEl.dataset.rawText = newText;
    const textDiv = turnEl.querySelector(":scope > div:nth-child(2)");
    if (textDiv) {
      textDiv.innerHTML = renderMarkdown(newText);
      renderMathIn(textDiv);
    }
  } catch (e) {
    alert("Erreur réseau : " + e.message);
  }
}
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && lightbox && !lightbox.hidden) {
    e.preventDefault();
    closeLightbox();
  }
});
function renderInconsistencyBanner(inc) {
  const card = document.createElement("div");
  card.className = "turn inconsistency-card";
  const role = document.createElement("div");
  role.className = "role";
  role.textContent = "⚠️ Incohérence SCRIPT ↔ slides PDF";
  card.appendChild(role);
  const msg = document.createElement("div");
  msg.className = "inc-message";
  msg.textContent = inc.message || `SCRIPT (${inc.nb_slides_script} slides) ≠ PDF (${inc.nb_pages_pdf} pages).`;
  card.appendChild(msg);
  const cmd = document.createElement("pre");
  cmd.className = "inc-cmd";
  cmd.textContent = inc.regen_command;
  card.appendChild(cmd);
  const actions = document.createElement("div");
  actions.className = "inc-actions";
  const copyBtn = document.createElement("button");
  copyBtn.className = "inc-copy";
  copyBtn.textContent = "📋 Copier la commande";
  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(inc.regen_command);
      copyBtn.textContent = "✓ Copié";
      setTimeout(() => {
        copyBtn.textContent = "📋 Copier la commande";
      }, 2000);
    } catch (e) {
      copyBtn.textContent = "✗ " + e.message;
    }
  });
  actions.appendChild(copyBtn);
  card.appendChild(actions);
  if (dialogue.querySelector(".placeholder")) dialogue.innerHTML = "";
  dialogue.appendChild(card);
  dialogue.scrollTop = dialogue.scrollHeight;
}
let inDebrief = false;
endBtn.addEventListener("click", () => {
  if (!activeSession) return;
  if (inDebrief) {
    appendTurn("system", "Session déjà en phase débrief. Pour fermer définitivement, " + "utilisez le bouton « 🚪 Fermer définitivement » de la carte récap.");
    return;
  }
  triggerSessionRecap();
});
if (exportRecapBtn) {
  exportRecapBtn.addEventListener("click", async () => {
    if (exportRecapBtn.disabled) return;
    const originalText = exportRecapBtn.textContent;
    exportRecapBtn.disabled = true;
    exportRecapBtn.textContent = "⏳ Génération…";
    try {
      const r = await fetch("/api/export_recap");
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        alert("Erreur export : " + (err.error || r.status));
        return;
      }
      const blob = await r.blob();
      let filename = "recap.zip";
      const cd = r.headers.get("Content-Disposition") || "";
      const m = cd.match(/filename="([^"]+)"/);
      if (m) filename = m[1];
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      alert("Erreur réseau export récap : " + e.message);
    } finally {
      exportRecapBtn.textContent = originalText;
      exportRecapBtn.disabled = !activeSession;
    }
  });
}
async function triggerSessionRecap() {
  if (!activeSession) return;
  if (isRecording) abortRecordingAndTranscribe();
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }
  const waitBubble = appendTurn("system", "🎓 Génération du récap de séance (audit Gemini Flash sur le transcript), patience 3-8 s…");
  try {
    const r = await fetch("/api/session_recap", {
      method: "POST"
    });
    const data = await r.json();
    if (waitBubble && waitBubble.parentElement) {
      waitBubble.parentElement.remove();
    }
    if (!r.ok) {
      appendTurn("system", "⚠ Récap échoué : " + (data.error || r.status) + ". Tu peux fermer la séance " + "via le bouton Terminer (qui fera un end_session brut).");
      return;
    }
    inDebrief = true;
    if (sessionInfo) {
      const cur = sessionInfo.textContent || "";
      if (!cur.includes("[débrief]")) {
        sessionInfo.textContent = cur + " [🎓 débrief]";
      }
    }
    renderSessionRecapCard(data.recap || {});
  } catch (e) {
    if (waitBubble && waitBubble.parentElement) waitBubble.parentElement.remove();
    appendTurn("system", "⚠ Erreur réseau récap : " + e.message);
  }
}
function renderSessionRecapCard(recap) {
  const wrapper = document.createElement("div");
  wrapper.className = "turn system session-recap-card";
  wrapper.dataset.localOnly = "1";
  const role = document.createElement("div");
  role.className = "role";
  role.textContent = "🎓 Récap de séance";
  const ts = document.createElement("span");
  ts.className = "turn-time";
  const nowIso = new Date().toISOString();
  ts.dataset.atIso = nowIso;
  ts.textContent = formatTurnTimeShort(nowIso);
  ts.title = formatTurnTimeAbsolute(nowIso);
  role.appendChild(ts);
  const recapCloseBtn = document.createElement("button");
  recapCloseBtn.type = "button";
  recapCloseBtn.className = "session-recap-close";
  recapCloseBtn.title = "Fermer la carte récap";
  recapCloseBtn.textContent = "✕";
  recapCloseBtn.addEventListener("click", () => {
    wrapper.remove();
  });
  role.appendChild(recapCloseBtn);
  wrapper.appendChild(role);
  if (recap.summary) {
    const sumDiv = document.createElement("div");
    sumDiv.className = "recap-summary";
    sumDiv.innerHTML = renderMarkdown(recap.summary);
    wrapper.appendChild(sumDiv);
  }
  const concepts = Array.isArray(recap.concepts_covered) ? recap.concepts_covered : [];
  if (concepts.length) {
    const div = document.createElement("div");
    div.className = "recap-section recap-concepts";
    div.innerHTML = "<h4>📚 Concepts couverts</h4>" + `<p class="recap-hint">Clique 🎯 sur un concept pour un mini-exo ciblé dessus.</p>`;
    const ul = document.createElement("ul");
    concepts.forEach(c => {
      const li = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = String(c);
      li.appendChild(label);
      const miniBtn = document.createElement("button");
      miniBtn.type = "button";
      miniBtn.className = "wp-mini-exo-btn";
      miniBtn.innerHTML = "🎯";
      miniBtn.title = "Mini-exo ciblé : le tuteur produit un exo court (3-5 questions) sur ce concept";
      miniBtn.addEventListener("click", () => triggerMiniExo(String(c)));
      li.appendChild(miniBtn);
      ul.appendChild(li);
    });
    div.appendChild(ul);
    wrapper.appendChild(div);
  }
  const exos = Array.isArray(recap.exercises_handled) ? recap.exercises_handled : [];
  if (exos.length) {
    const div = document.createElement("div");
    div.className = "recap-section recap-exos";
    div.innerHTML = "<h4>📝 Exercices traités</h4>";
    const ul = document.createElement("ul");
    exos.forEach(e => {
      const li = document.createElement("li");
      li.textContent = String(e);
      ul.appendChild(li);
    });
    div.appendChild(ul);
    wrapper.appendChild(div);
  }
  const sugg = Array.isArray(recap.suggestions) ? recap.suggestions : [];
  if (sugg.length) {
    const div = document.createElement("div");
    div.className = "recap-section recap-suggestions";
    div.innerHTML = "<h4>💡 Suggestions de révision</h4>";
    const ul = document.createElement("ul");
    sugg.forEach(s => {
      const li = document.createElement("li");
      li.textContent = String(s);
      ul.appendChild(li);
    });
    div.appendChild(ul);
    wrapper.appendChild(div);
  }
  const nextSteps = document.createElement("div");
  nextSteps.className = "recap-section recap-next-steps";
  nextSteps.innerHTML = "<h4>🚀 Pour aller plus loin</h4>" + `<p class="recap-hint">La séance reste ouverte : choisis une suite, ` + `ou ferme définitivement quand tu as fini.</p>`;
  const nsRow = document.createElement("div");
  nsRow.className = "recap-next-steps-row";
  const NEXT_STEP_BTNS = [["bloc_lecon", "📄 Bloc complet de la leçon", "Le tuteur compile toutes les fiches/leçons de la séance en un seul bloc."], ["bloc_exos", "📄 Bloc complet des exos", "Le tuteur regroupe tous les exos traités + leur correction rédigée."], ["serie_exos", "📝 Série d'exos d'entraînement", "Le tuteur génère de nouveaux exos (énoncés seuls) sur les concepts du jour."]];
  NEXT_STEP_BTNS.forEach(([kind, label, title]) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "recap-action-btn recap-nextstep-btn";
    b.textContent = label;
    b.title = title;
    b.addEventListener("click", () => triggerRecapAction(kind));
    nsRow.appendChild(b);
  });
  const colleBtn = document.createElement("button");
  colleBtn.type = "button";
  colleBtn.className = "recap-action-btn recap-nextstep-btn";
  colleBtn.textContent = "🎯 Passer en mode colle";
  colleBtn.title = "Pré-arme une nouvelle séance en mode colle " + "(auto-interrogation) sur la même matière.";
  colleBtn.addEventListener("click", switchToColleMode);
  nsRow.appendChild(colleBtn);
  nextSteps.appendChild(nsRow);
  wrapper.appendChild(nextSteps);
  const actions = document.createElement("div");
  actions.className = "recap-actions";
  const continueBtn = document.createElement("button");
  continueBtn.type = "button";
  continueBtn.className = "recap-action-btn recap-continue-btn";
  continueBtn.innerHTML = "💬 Continuer en débrief";
  continueBtn.title = "Pose des questions libres au tuteur en posture détaillée. " + "La séance reste ouverte.";
  continueBtn.addEventListener("click", () => {
    if (userInput) {
      userInput.focus();
      userInput.placeholder = "Pose ta question de débrief…";
    }
  });
  actions.appendChild(continueBtn);
  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "recap-action-btn recap-close-btn";
  closeBtn.innerHTML = "🚪 Fermer définitivement";
  closeBtn.title = "Finalise la session (ended_at, duration_seconds). " + "Plus possible de continuer après.";
  closeBtn.addEventListener("click", closeSessionFinal);
  actions.appendChild(closeBtn);
  wrapper.appendChild(actions);
  if (dialogue.querySelector(".placeholder")) dialogue.innerHTML = "";
  dialogue.appendChild(wrapper);
  dialogue.scrollTop = dialogue.scrollHeight;
}
async function triggerMiniExo(concept) {
  if (!activeSession) return;
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }
  try {
    const r = await fetch("/api/mini_exo", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        concept: concept
      })
    });
    if (!r.ok) {
      const data = await r.json().catch(() => ({}));
      alert("Mini-exo échoué : " + (data.error || r.status));
      return;
    }
    appendTurn("system", `🎯 Mini-exo demandé : ${concept}`);
    streamResponse();
  } catch (e) {
    alert("Erreur réseau mini-exo : " + e.message);
  }
}
async function triggerRecapAction(kind) {
  if (!activeSession) {
    appendTurn("system", "⚠ Séance déjà fermée : relance une séance pour continuer.");
    return;
  }
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }
  const labels = {
    bloc_lecon: "📄 Bloc complet de la leçon",
    bloc_exos: "📄 Bloc complet des exos",
    serie_exos: "📝 Série d'exos d'entraînement"
  };
  try {
    const r = await fetch("/api/recap_action", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        action: kind
      })
    });
    if (!r.ok) {
      const data = await r.json().catch(() => ({}));
      alert("Action échouée : " + (data.error || r.status));
      return;
    }
    appendTurn("system", `${labels[kind] || kind} : demandé au tuteur…`);
    streamResponse();
  } catch (e) {
    alert("Erreur réseau : " + e.message);
  }
}
function switchToColleMode() {
  const modeEl = startForm && startForm.querySelector('[name="mode"]');
  if (modeEl) {
    modeEl.value = "colle";
    modeEl.dispatchEvent(new Event("change", {
      bubbles: true
    }));
  }
  appendTurn("system", "🎯 Mode colle pré-sélectionné dans le formulaire. Ferme cette séance " + "(🚪) si besoin, puis clique « Démarrer » pour t'auto-interroger sur la " + "même matière, sans guidage.");
  const startBtn = startForm && startForm.querySelector('button[type="submit"]');
  if (startBtn) startBtn.scrollIntoView({
    behavior: "smooth",
    block: "center"
  });
}
function renderPostCloseCard() {
  const card = document.createElement("div");
  card.className = "turn system session-recap-card";
  card.dataset.localOnly = "1";
  const role = document.createElement("div");
  role.className = "role";
  role.textContent = "✅ Séance terminée. Et maintenant ?";
  card.appendChild(role);
  const hint = document.createElement("p");
  hint.className = "recap-hint";
  hint.textContent = "La séance est archivée. Choisis une suite pour " + "continuer à progresser :";
  card.appendChild(hint);
  const row = document.createElement("div");
  row.className = "recap-next-steps-row";
  const colleB = document.createElement("button");
  colleB.type = "button";
  colleB.className = "recap-action-btn recap-nextstep-btn";
  colleB.textContent = "🎯 M'interroger en mode colle";
  colleB.addEventListener("click", switchToColleMode);
  row.appendChild(colleB);
  const newB = document.createElement("button");
  newB.type = "button";
  newB.className = "recap-action-btn recap-nextstep-btn";
  newB.textContent = "🔁 Nouvelle séance";
  newB.addEventListener("click", () => {
    const startBtn = startForm && startForm.querySelector('button[type="submit"]');
    if (startBtn) startBtn.scrollIntoView({
      behavior: "smooth",
      block: "center"
    });
  });
  row.appendChild(newB);
  card.appendChild(row);
  if (dialogue.querySelector(".placeholder")) dialogue.innerHTML = "";
  dialogue.appendChild(card);
  dialogue.scrollTop = dialogue.scrollHeight;
}
async function closeSessionFinal() {
  if (!activeSession) return;
  if (isRecording) abortRecordingAndTranscribe();
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }
  try {
    const r = await fetch("/api/session_close", {
      method: "POST"
    });
    const data = await r.json();
    if (r.ok) {
      appendTurn("system", `🚪 Séance archivée. Durée totale : ${data.duration_seconds}s.`);
    }
  } catch (e) {}
  _cleanupAfterSessionClose();
  renderPostCloseCard();
}
async function finishSession(autoFromEnd = true) {
  if (!activeSession) return;
  if (autoFromEnd !== "force_close" && !inDebrief) {
    return triggerSessionRecap();
  }
  if (isRecording) abortRecordingAndTranscribe();
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }
  try {
    const r = await fetch("/api/end_session", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        interrupted: false
      })
    });
    const data = await r.json();
    if (r.ok) {
      appendTurn("system", `Séance terminée. Durée: ${data.duration_seconds}s.`);
    }
  } catch (e) {}
  _cleanupAfterSessionClose();
}
function _cleanupAfterSessionClose() {
  activeSession = null;
  activeMode = null;
  inDebrief = false;
  activeColleFormat = "mixte";
  activeCorrigeAnchor = "strict";
  guidedSlides = [];
  guidedIndex = -1;
  guidedPanel.hidden = true;
  userInput.disabled = true;
  sendBtn.disabled = true;
  endBtn.disabled = true;
  if (exportRecapBtn) exportRecapBtn.disabled = true;
  micBtn.disabled = true;
  if (mediaBtn) mediaBtn.disabled = true;
  if (photoBtn) photoBtn.disabled = true;
  if (rewriteBtn) rewriteBtn.disabled = true;
  if (findExoBtn) {
    findExoBtn.disabled = true;
    findExoBtn.hidden = true;
  }
  closeRewritePopover();
  const submitBtn = startForm.querySelector('button[type="submit"]');
  if (submitBtn) submitBtn.disabled = false;
  sessionInfo.textContent = "";
}
document.addEventListener("keydown", e => {
  const ae = document.activeElement;
  if (ae) {
    const tag = (ae.tagName || "").toUpperCase();
    if (tag === "TEXTAREA" || tag === "INPUT" || tag === "SELECT" || ae.isContentEditable) {
      return;
    }
  }
  if (activeMode === "guidé" && guidedSlides.length) {
    const corrigeActiveAndLoaded = typeof corrigeTabIsActive === "function" && corrigeTabIsActive() && correctionsList.length;
    if (!corrigeActiveAndLoaded) {
      if (e.code === "Space" || e.code === "ArrowRight") {
        e.preventDefault();
        gotoNextSlide();
        return;
      }
      if (e.code === "ArrowLeft") {
        e.preventDefault();
        gotoPrevSlide();
        return;
      }
    }
  }
  if (typeof corrigeTabIsActive === "function" && corrigeTabIsActive() && correctionsList.length) {
    if (e.code === "ArrowRight") {
      e.preventDefault();
      corrigeNextPage();
      return;
    }
    if (e.code === "ArrowLeft") {
      e.preventDefault();
      corrigePrevPage();
      return;
    }
  }
  if (e.code === "Space") {
    recordIndicator.classList.add("active");
  }
});
document.addEventListener("keyup", e => {
  if (e.code === "Space") {
    recordIndicator.classList.remove("active");
  }
});
const TTS_VOICES = [{
  id: "fr-FR-DeniseNeural",
  label: "Denise"
}, {
  id: "fr-FR-HenriNeural",
  label: "Henri"
}, {
  id: "fr-FR-AlainNeural",
  label: "Alain"
}, {
  id: "fr-FR-BrigitteNeural",
  label: "Brigitte"
}];
const TTS_SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];
function getTTSPref(key, fallback) {
  try {
    return localStorage.getItem("tts_" + key) || fallback;
  } catch (_) {
    return fallback;
  }
}
function setTTSPref(key, value) {
  try {
    localStorage.setItem("tts_" + key, String(value));
  } catch (_) {}
}
function fmtTime(s) {
  if (!Number.isFinite(s) || s < 0) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}
async function toggleTTSPlayer(turnEl) {
  const existing = turnEl.querySelector(":scope > .tts-player");
  if (existing) {
    const audio = existing.querySelector("audio");
    if (audio) {
      if (audio.paused) audio.play();else audio.pause();
    }
    return;
  }
  const rawText = turnEl.dataset.rawText || "";
  if (!rawText.trim()) {
    alert("Rien à lire dans cette bulle.");
    return;
  }
  const cleanText = stripMarkdownForTTS(rawText);
  if (!cleanText.trim()) {
    alert("Rien à lire après nettoyage du markdown.");
    return;
  }
  const player = renderTTSPlayer(turnEl, cleanText);
  turnEl.appendChild(player);
}
function stripMarkdownForTTS(text) {
  let t = text;
  t = t.replace(/```[\s\S]*?```/g, " (bloc de code) ");
  t = t.replace(/!\[[^\]]*\]\([^)]+\)/g, " (image) ");
  t = t.replace(/\[Pièce jointe[^\]]*\]/gi, " (pièce jointe) ");
  t = t.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
  t = t.replace(/\$\$[\s\S]*?\$\$/g, " (formule) ");
  t = t.replace(/\$[^$\n]+\$/g, " (formule inline) ");
  t = t.replace(/`([^`]+)`/g, "$1");
  t = t.replace(/\*\*([^*]+)\*\*/g, "$1");
  t = t.replace(/\*([^*]+)\*/g, "$1");
  t = t.replace(/^#+\s+/gm, "");
  t = t.replace(/<<<[A-Z_]+>>>[\s\S]*?<<<END>>>/g, "");
  t = t.replace(/<<<[A-Z_]+>>>/g, "");
  t = t.replace(/[—–]/g, ", ");
  return t.trim();
}
function renderTTSPlayer(turnEl, text) {
  const wrap = document.createElement("div");
  wrap.className = "tts-player tts-loading";
  const audio = document.createElement("audio");
  audio.preload = "auto";
  const playBtn = document.createElement("button");
  playBtn.type = "button";
  playBtn.className = "tts-play";
  playBtn.title = "Play / Pause";
  playBtn.textContent = "▶";
  const timeline = document.createElement("input");
  timeline.type = "range";
  timeline.className = "tts-timeline";
  timeline.min = "0";
  timeline.max = "100";
  timeline.value = "0";
  timeline.step = "0.1";
  timeline.disabled = true;
  const timeLabel = document.createElement("span");
  timeLabel.className = "tts-time";
  timeLabel.textContent = "0:00 / —";
  const speedSel = document.createElement("select");
  speedSel.className = "tts-speed";
  speedSel.title = "Vitesse";
  for (const sp of TTS_SPEEDS) {
    const opt = document.createElement("option");
    opt.value = String(sp);
    opt.textContent = `${sp}×`;
    speedSel.appendChild(opt);
  }
  speedSel.value = getTTSPref("speed", "1");
  audio.playbackRate = parseFloat(speedSel.value) || 1;
  const voiceSel = document.createElement("select");
  voiceSel.className = "tts-voice";
  voiceSel.title = "Voix";
  for (const v of TTS_VOICES) {
    const opt = document.createElement("option");
    opt.value = v.id;
    opt.textContent = v.label;
    voiceSel.appendChild(opt);
  }
  voiceSel.value = getTTSPref("voice", "fr-FR-DeniseNeural");
  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "tts-close";
  closeBtn.title = "Fermer le lecteur";
  closeBtn.textContent = "✕";
  closeBtn.addEventListener("click", () => {
    audio.pause();
    audio.src = "";
    wrap.remove();
  });
  const status = document.createElement("span");
  status.className = "tts-status";
  status.textContent = "⏳ Synthèse…";
  wrap.appendChild(playBtn);
  wrap.appendChild(timeline);
  wrap.appendChild(timeLabel);
  wrap.appendChild(speedSel);
  wrap.appendChild(voiceSel);
  wrap.appendChild(status);
  wrap.appendChild(closeBtn);
  wrap.appendChild(audio);
  playBtn.addEventListener("click", () => {
    if (audio.paused) audio.play();else audio.pause();
  });
  audio.addEventListener("play", () => {
    playBtn.textContent = "⏸";
  });
  audio.addEventListener("pause", () => {
    playBtn.textContent = "▶";
  });
  audio.addEventListener("ended", () => {
    playBtn.textContent = "▶";
    timeline.value = "0";
  });
  audio.addEventListener("loadedmetadata", () => {
    if (Number.isFinite(audio.duration)) {
      timeline.max = String(audio.duration);
      timeline.disabled = false;
    }
  });
  audio.addEventListener("timeupdate", () => {
    timeline.value = String(audio.currentTime);
    const total = Number.isFinite(audio.duration) ? fmtTime(audio.duration) : "—";
    timeLabel.textContent = `${fmtTime(audio.currentTime)} / ${total}`;
  });
  timeline.addEventListener("input", () => {
    const v = parseFloat(timeline.value);
    if (Number.isFinite(v)) audio.currentTime = v;
  });
  speedSel.addEventListener("change", () => {
    const sp = parseFloat(speedSel.value) || 1;
    audio.playbackRate = sp;
    setTTSPref("speed", sp);
  });
  voiceSel.addEventListener("change", async () => {
    setTTSPref("voice", voiceSel.value);
    const wasPlaying = !audio.paused;
    audio.pause();
    wrap.classList.add("tts-loading");
    status.textContent = "⏳ Re-synthèse…";
    await fetchTTSInto(audio, text, voiceSel.value, status, wrap);
    if (wasPlaying) audio.play().catch(() => {});
  });
  fetchTTSInto(audio, text, voiceSel.value, status, wrap, true);
  return wrap;
}
async function fetchTTSInto(audio, text, voice, statusEl, wrap, autoplay = false) {
  try {
    const r = await fetch("/api/tts/synthesize", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        text,
        voice
      })
    });
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      statusEl.textContent = "✗ " + (d.error || `HTTP ${r.status}`);
      return;
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    if (audio.src) URL.revokeObjectURL(audio.src);
    audio.src = url;
    statusEl.textContent = "";
    wrap.classList.remove("tts-loading");
    if (autoplay) {
      audio.play().catch(err => {
        console.warn("autoplay refusé :", err);
      });
    }
  } catch (e) {
    statusEl.textContent = "✗ Réseau : " + e.message;
  }
}
const engineSwitcher = $("#engine-switcher");
const ENGINE_LABELS = {
  cli_subscription: "CLI Claude (subscription)",
  anthropic_api: "API Anthropic",
  gemini_api: "Gemini",
  deepseek_api: "DeepSeek",
  groq_api: "Groq"
};
async function refreshEngineSwitcher() {
  if (!engineSwitcher) return;
  try {
    const r = await fetch("/api/engine");
    if (!r.ok) return;
    const data = await r.json();
    const current = data.current;
    const available = Array.isArray(data.available) ? data.available : [];
    const seen = new Set();
    const items = [];
    if (current) {
      items.push({
        engine: current,
        label: ENGINE_LABELS[current] || current
      });
      seen.add(current);
    }
    for (const a of available) {
      if (seen.has(a.engine)) continue;
      items.push({
        engine: a.engine,
        label: a.label || ENGINE_LABELS[a.engine] || a.engine
      });
      seen.add(a.engine);
    }
    engineSwitcher.innerHTML = items.map(it => `<option value="${it.engine}"${it.engine === current ? " selected" : ""}>${it.label}</option>`).join("");
    engineSwitcher.disabled = false;
  } catch (e) {
    console.warn("refreshEngineSwitcher a échoué :", e);
  }
}
if (engineSwitcher) {
  engineSwitcher.addEventListener("change", async () => {
    const target = engineSwitcher.value;
    if (!target) return;
    engineSwitcher.disabled = true;
    try {
      const path = activeSession ? "/api/switch_engine" : "/api/switch_engine_pref";
      const r = await fetch(path, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          engine: target
        })
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        alert("Bascule moteur échouée : " + (data.error || r.status));
        await refreshEngineSwitcher();
      } else {
        if (sessionInfo && activeSession) {
          sessionInfo.textContent = `→ ${activeSession} (engine: ${target})`;
        }
      }
    } catch (e) {
      alert("Erreur réseau bascule moteur : " + e.message);
    } finally {
      engineSwitcher.disabled = false;
    }
  });
}
refreshEngineSwitcher();
const _origRefreshAfterStart = refreshEngineSwitcher;
const historyList = $("#history-list");
const historyRefresh = $("#history-refresh");
function fmtSessionLabel(s) {
  if (s.label) return s.label;
  const exo = s.exo && s.exo !== "full" ? `ex${s.exo}` : "exfull";
  const annee = s.annee ? ` ${s.annee}` : "";
  return `${s.matiere || "?"} ${s.type || "?"}${s.num || "?"} ${exo}${annee}`;
}
function fmtSessionDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString("fr-FR", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit"
    });
  } catch (_) {
    return iso.slice(0, 16);
  }
}
async function refreshHistoryList() {
  if (!historyList) return;
  try {
    const r = await fetch("/api/sessions");
    if (!r.ok) {
      historyList.innerHTML = `<div class="history-empty">Erreur : ${r.status}</div>`;
      return;
    }
    const data = await r.json();
    const sessions = Array.isArray(data.sessions) ? data.sessions : [];
    if (!sessions.length) {
      historyList.innerHTML = `<div class="history-empty">Pas encore de sessions.</div>`;
      return;
    }
    historyList.innerHTML = "";
    for (const s of sessions) {
      const item = document.createElement("div");
      item.className = "history-item";
      if (activeSession && s.session_id === activeSession) item.classList.add("is-active");
      item.dataset.sid = s.session_id;
      const mode = s.mode || "colle";
      const flagInterrupted = s.interrupted ? `<span class="h-flag">⚠ interrompue</span>` : "";
      const chips = [mode];
      if (s.colle_format) chips.push(s.colle_format);
      if (s.corrige_anchor) chips.push(s.corrige_anchor);
      const meta = [fmtSessionDate(s.last_alive || s.started_at), `${s.n_exchanges || 0} tour${(s.n_exchanges || 0) > 1 ? "s" : ""}`, chips.join(" · ")].filter(Boolean).join(" · ");
      item.innerHTML = `
        <div class="h-title">${escapeHtml(fmtSessionLabel(s))}</div>
        <div class="h-meta">${meta} ${flagInterrupted}</div>
        <div class="h-actions">
          <button class="h-action-btn h-rename" type="button" title="Renommer">✏️</button>
          <button class="h-action-btn h-del" type="button" title="Supprimer">🗑️</button>
        </div>
      `;
      item.addEventListener("click", e => {
        if (e.target.closest(".h-actions")) return;
        if (item.querySelector(".h-rename-input")) return;
        resumeSession(s.session_id);
      });
      item.querySelector(".h-rename").addEventListener("click", e => {
        e.stopPropagation();
        startRenameSession(item, s);
      });
      item.querySelector(".h-del").addEventListener("click", async e => {
        e.stopPropagation();
        if (s.session_id === activeSession) {
          alert("Impossible de supprimer la session active. Termine-la d'abord.");
          return;
        }
        if (!confirm(`Supprimer la session « ${fmtSessionLabel(s)} » ?`)) return;
        const dr = await fetch(`/api/sessions/${encodeURIComponent(s.session_id)}`, {
          method: "DELETE"
        });
        if (!dr.ok && dr.status !== 204) {
          const err = await dr.json().catch(() => ({}));
          alert("Suppression échouée : " + (err.error || dr.status));
          return;
        }
        refreshHistoryList();
      });
      historyList.appendChild(item);
    }
  } catch (e) {
    historyList.innerHTML = `<div class="history-empty">Erreur réseau : ${e.message}</div>`;
  }
}
function startRenameSession(item, s) {
  const titleDiv = item.querySelector(".h-title");
  const current = s.label || fmtSessionLabel(s);
  const input = document.createElement("input");
  input.type = "text";
  input.className = "h-rename-input";
  input.value = current;
  input.maxLength = 120;
  titleDiv.replaceWith(input);
  input.focus();
  input.select();
  const commit = async save => {
    const newLabel = input.value.trim();
    if (!save) {
      refreshHistoryList();
      return;
    }
    const body = {
      label: newLabel || null
    };
    const r = await fetch(`/api/sessions/${encodeURIComponent(s.session_id)}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body)
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      alert("Renommage échoué : " + (err.error || r.status));
    }
    refreshHistoryList();
  };
  input.addEventListener("keydown", e => {
    if (e.key === "Enter") {
      e.preventDefault();
      commit(true);
    } else if (e.key === "Escape") {
      e.preventDefault();
      commit(false);
    }
  });
  input.addEventListener("blur", () => commit(true));
}
async function resumeSession(sid) {
  if (!sid) return;
  if (sessionInfo) sessionInfo.textContent = `⏳ Reprise de ${sid}…`;
  try {
    const r = await fetch("/api/resume_session", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        session_id: sid
      })
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      alert("Reprise échouée : " + (data.error || r.status));
      if (sessionInfo) sessionInfo.textContent = "";
      return;
    }
    activeSession = data.session_id;
    activeMode = data.mode || "colle";
    applyColleFormatChips(data.colle_format || "mixte");
    applyCorrigeAnchorChips(data.corrige_anchor || "strict");
    try {
      await syncFormToSession(data);
    } catch (_) {}
    sessionInfo.textContent = `→ ${data.session_id} (engine: ${data.engine}) ` + `[${data.summary_used ? "résumé" : "replay"}]`;
    rerenderDialogueFromTranscript(data.transcript || []);
    userInput.disabled = false;
    sendBtn.disabled = false;
    endBtn.disabled = false;
    if (exportRecapBtn) exportRecapBtn.disabled = false;
    micBtn.disabled = false;
    if (mediaBtn) mediaBtn.disabled = false;
    if (photoBtn) photoBtn.disabled = false;
    refreshRewriteBtnState();
    refreshFindExoBtnState();
    if (activeMode === "guidé") {
      const startIdx = Number.isInteger(data.guided_index) ? data.guided_index : 0;
      initGuidedPanel(startIdx);
    }
    showRemindNavBtnIfActive(!!data.auto_advance);
    initCorrectionsPanel();
    refreshHistoryList();
  } catch (e) {
    alert("Erreur réseau pendant la reprise : " + e.message);
    if (sessionInfo) sessionInfo.textContent = "";
  }
}
if (historyRefresh) historyRefresh.addEventListener("click", refreshHistoryList);
refreshHistoryList();
const correctionsList = [];
let corrigeIdx = 0;
let corrigePageIdx = 0;
let currentReadingState = null;
const corrigePageMemory = new Map();
let docMarkerTimeoutHandle = null;
let lastDocMarkerKey = null;
const DOC_MARKER_DEBOUNCE_MS = 1500;
const corrigePicker = $("#corrige-picker");
const corrigeImg = $("#corrige-page-img");
const corrigePlaceholder = $("#corrige-placeholder");
const corrigeCounter = $("#corrige-counter");
const corrigePdfName = $("#corrige-pdf-name");
const corrigePrev = $("#corrige-prev");
const corrigeNext = $("#corrige-next");
const corrigeJump = $("#corrige-jump");
function corrigeTabIsActive() {
  const tab = document.querySelector('#sidebar-tabs .sb-tab[data-tab="corrige"]');
  return !!(tab && tab.classList.contains("active"));
}
function _kindLabelFr(kind) {
  if (kind === "enonce") return "Énoncé";
  if (kind === "enonce_invente") return "Énoncé (généré)";
  if (kind === "script") return "Script";
  if (kind === "slides") return "Slides";
  if (kind === "correction") return "Corrigé";
  return "Document";
}
async function initCorrectionsPanel() {
  correctionsList.length = 0;
  corrigeIdx = 0;
  corrigePageIdx = 0;
  currentReadingState = null;
  corrigePageMemory.clear();
  if (docMarkerTimeoutHandle) {
    clearTimeout(docMarkerTimeoutHandle);
    docMarkerTimeoutHandle = null;
  }
  lastDocMarkerKey = null;
  foundExoHistory = [];
  seenWebUrls = [];
  seenYoutubeUrls = [];
  if (!activeSession) {
    setCorrigePlaceholder("Aucune session active.");
    return;
  }
  setCorrigePlaceholder("Chargement…");
  try {
    const r = await fetch("/api/corrections/init");
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      setCorrigePlaceholder(`Indisponible : ${d.error || r.status}`);
      return;
    }
    const data = await r.json();
    const items = Array.isArray(data.corrections) ? data.corrections : [];
    if (!items.length) {
      setCorrigePlaceholder("Aucun document (énoncé, corrigé, script) trouvé pour cet exercice.");
      return;
    }
    for (const it of items) correctionsList.push(it);
    populateCorrigePicker();
    showCorrige(0, 0, false);
    document.querySelectorAll('#dialogue-stream .turn.claude').forEach(turn => {
      linkifyPageRefs(turn);
    });
  } catch (e) {
    setCorrigePlaceholder(`Erreur réseau : ${e.message}`);
  }
}
function setCorrigePlaceholder(txt) {
  if (corrigeImg) {
    corrigeImg.hidden = true;
    corrigeImg.src = "";
  }
  if (corrigePlaceholder) {
    corrigePlaceholder.hidden = false;
    corrigePlaceholder.textContent = txt;
  }
  if (corrigeCounter) corrigeCounter.textContent = "— / —";
  if (corrigePdfName) corrigePdfName.textContent = "";
  if (corrigePicker) {
    corrigePicker.hidden = true;
    corrigePicker.innerHTML = "";
  }
  if (corrigePrev) corrigePrev.disabled = true;
  if (corrigeNext) corrigeNext.disabled = true;
  if (corrigeJump) corrigeJump.disabled = true;
}
function populateCorrigePicker() {
  if (!corrigePicker) return;
  corrigePicker.innerHTML = "";
  const _SELF_DESC_RE = /^(Annale|Aide-mémoire|Exos|Toutes|Script)\b/i;
  correctionsList.forEach((c, i) => {
    const opt = document.createElement("option");
    opt.value = String(i);
    const totalP = (c.pages || []).length;
    const kindLbl = _kindLabelFr(c.kind);
    const labelStr = String(c.label || "");
    const skipPrefix = _SELF_DESC_RE.test(labelStr);
    opt.textContent = skipPrefix ? `${labelStr} : ${totalP} page${totalP > 1 ? "s" : ""}` : `${kindLbl} : ${labelStr} : ${totalP} page${totalP > 1 ? "s" : ""}`;
    corrigePicker.appendChild(opt);
  });
  corrigePicker.hidden = correctionsList.length < 2;
}
function showCorrige(idx, pageIdx, notify = true) {
  if (!correctionsList.length) return;
  if (idx < 0 || idx >= correctionsList.length) return;
  if (correctionsList[corrigeIdx]) {
    const prevKey = correctionsList[corrigeIdx].filename || `idx:${corrigeIdx}`;
    corrigePageMemory.set(prevKey, corrigePageIdx);
  }
  corrigeIdx = idx;
  const item = correctionsList[idx];
  const pages = item.pages || [];
  if (!pages.length) {
    setCorrigePlaceholder(`Pas de page rasterizée pour ${item.label}.`);
    return;
  }
  let resolvedPageIdx = pageIdx;
  if (resolvedPageIdx === null || resolvedPageIdx === undefined) {
    const memKey = item.filename || `idx:${idx}`;
    resolvedPageIdx = corrigePageMemory.has(memKey) ? corrigePageMemory.get(memKey) : 0;
  }
  corrigePageIdx = Math.min(Math.max(0, resolvedPageIdx), pages.length - 1);
  const page = pages[corrigePageIdx];
  if (corrigePicker) corrigePicker.value = String(idx);
  if (corrigeImg && page.png_url) {
    corrigeImg.src = page.png_url;
    corrigeImg.hidden = false;
    if (corrigePlaceholder) corrigePlaceholder.hidden = true;
  } else {
    if (corrigeImg) corrigeImg.hidden = true;
    if (corrigePlaceholder) {
      corrigePlaceholder.hidden = false;
      corrigePlaceholder.textContent = "(pas d'image rasterizée)";
    }
  }
  if (corrigeCounter) {
    corrigeCounter.textContent = `${corrigePageIdx + 1} / ${pages.length}`;
  }
  if (corrigePdfName) corrigePdfName.textContent = item.filename || "";
  if (corrigePrev) {
    corrigePrev.disabled = corrigeIdx === 0 && corrigePageIdx === 0;
  }
  if (corrigeNext) {
    const isLastItem = corrigeIdx === correctionsList.length - 1;
    corrigeNext.disabled = isLastItem && corrigePageIdx === pages.length - 1;
  }
  if (corrigeJump) corrigeJump.disabled = pages.length < 2;
  currentReadingState = {
    kind: item.kind || "document",
    label: item.label || "",
    filename: item.filename || "",
    page: corrigePageIdx + 1,
    total: pages.length
  };
  if (notify) maybeAppendDocPositionMarker(idx, corrigePageIdx);
}
function maybeAppendDocPositionMarker(idx, pageIdx) {
  if (docMarkerTimeoutHandle) clearTimeout(docMarkerTimeoutHandle);
  docMarkerTimeoutHandle = setTimeout(() => {
    docMarkerTimeoutHandle = null;
    appendDocPositionMarker(idx, pageIdx);
  }, DOC_MARKER_DEBOUNCE_MS);
}
function appendDocPositionMarker(idx, pageIdx) {
  const item = correctionsList[idx];
  if (!item) return;
  const key = `${idx}:${pageIdx}`;
  if (key === lastDocMarkerKey) return;
  lastDocMarkerKey = key;
  const total = (item.pages || []).length;
  const kindLbl = _kindLabelFr(item.kind || "").toLowerCase();
  const safeLabel = (item.label || "").replace(/[<>&]/g, c => ({
    "<": "&lt;",
    ">": "&gt;",
    "&": "&amp;"
  })[c]);
  const safeFile = (item.filename || "").replace(/[<>&]/g, c => ({
    "<": "&lt;",
    ">": "&gt;",
    "&": "&amp;"
  })[c]);
  const marker = document.createElement("div");
  marker.className = "doc-marker";
  marker.dataset.docIdx = String(idx);
  marker.dataset.docPage = String(pageIdx);
  marker.title = `Cliquer pour ré-afficher cette page (${safeFile || kindLbl})`;
  marker.innerHTML = `<span class="doc-marker-icon">📄</span>` + `<span class="doc-marker-text">Page <strong>${pageIdx + 1}/${total}</strong> du ${kindLbl}` + (safeLabel ? ` <em>« ${safeLabel} »</em>` : ``) + `</span>` + `<span class="doc-marker-hint">↩ retour</span>`;
  marker.addEventListener("click", () => {
    const tab = document.querySelector('#sidebar-tabs .sb-tab[data-tab="corrige"]');
    if (tab && !tab.classList.contains("active")) tab.click();
    showCorrige(idx, pageIdx, false);
  });
  dialogue.appendChild(marker);
  dialogue.scrollTop = dialogue.scrollHeight;
}
function getReadingStateForSend() {
  if (!corrigeTabIsActive()) return null;
  if (!currentReadingState) return null;
  return currentReadingState;
}
function corrigeNextPage() {
  if (!correctionsList.length) return;
  const cur = correctionsList[corrigeIdx];
  if (!cur) return;
  const pages = cur.pages || [];
  if (corrigePageIdx < pages.length - 1) {
    showCorrige(corrigeIdx, corrigePageIdx + 1);
  } else if (corrigeIdx < correctionsList.length - 1) {
    showCorrige(corrigeIdx + 1, 0);
  }
}
function corrigePrevPage() {
  if (!correctionsList.length) return;
  if (corrigePageIdx > 0) {
    showCorrige(corrigeIdx, corrigePageIdx - 1);
  } else if (corrigeIdx > 0) {
    const prev = correctionsList[corrigeIdx - 1];
    const last = prev && prev.pages ? Math.max(0, prev.pages.length - 1) : 0;
    showCorrige(corrigeIdx - 1, last);
  }
}
function corrigeJumpPage() {
  if (!correctionsList.length) return;
  const cur = correctionsList[corrigeIdx];
  if (!cur || !cur.pages || cur.pages.length < 2) return;
  const ans = window.prompt(`Aller à la page n° (1 - ${cur.pages.length}) :`, String(corrigePageIdx + 1));
  if (!ans) return;
  const n = parseInt(ans, 10);
  if (Number.isFinite(n) && n >= 1 && n <= cur.pages.length) {
    showCorrige(corrigeIdx, n - 1);
  }
}
if (corrigePicker) {
  corrigePicker.addEventListener("change", () => {
    const idx = parseInt(corrigePicker.value, 10);
    if (!Number.isFinite(idx)) return;
    showCorrige(idx);
  });
}
if (corrigePrev) corrigePrev.addEventListener("click", corrigePrevPage);
if (corrigeNext) corrigeNext.addEventListener("click", corrigeNextPage);
if (corrigeJump) corrigeJump.addEventListener("click", corrigeJumpPage);
if (corrigeImg) {
  corrigeImg.addEventListener("click", () => {
    if (corrigeImg.src) openLightbox(corrigeImg.src);
  });
}
let guidedFallbackState = {
  folderPath: "",
  startIndex: 0,
  scriptPath: "",
  slidesPath: "",
  pickerMode: "script",
  cwd: ""
};
function openGuidedFallbackModal(data, startIndex) {
  const missingOnly = data.missing_only || "";
  const initialScript = missingOnly === "slides" && data.script_path ? data.script_path : "";
  const initialSlides = missingOnly === "script" && data.slides_path ? data.slides_path : "";
  guidedFallbackState = {
    folderPath: data.folder_path || `${data.matiere}/${data.type_code}`,
    startIndex,
    scriptPath: initialScript,
    slidesPath: initialSlides,
    pickerMode: missingOnly === "slides" ? "slides" : "script",
    cwd: data.folder_path || `${data.matiere}/${data.type_code}`,
    missingOnly
  };
  const existing = document.getElementById("guided-fallback-modal");
  if (existing) existing.remove();
  const modal = document.createElement("div");
  modal.id = "guided-fallback-modal";
  modal.className = "modal-overlay";
  modal.innerHTML = `
    <div class="modal-card guided-fallback-card">
      <h3>📂 Mode guidé : matériau introuvable</h3>
      <p class="gfb-detail">${escapeHtmlSafe(data.detail || data.error || "")}</p>
      <p class="gfb-hint">Trois options pour continuer :</p>
      <div class="gfb-actions" id="gfb-main-actions">
        <button type="button" class="gfb-action-btn" id="gfb-browse">
          🔍 Parcourir manuellement
          <span class="gfb-hint-small">Choisis script + slides dans l'arbo COURS</span>
        </button>
        <button type="button" class="gfb-action-btn" id="gfb-ai-scan">
          🤖 Chercher avec IA
          <span class="gfb-hint-small">Gemini Flash propose les fichiers (~3-5 s, persisté)</span>
        </button>
        <button type="button" class="gfb-action-btn gfb-fallback-btn" id="gfb-colle">
          ↩ Repli en mode colle
          <span class="gfb-hint-small">Session continue sans navigation slide-par-slide</span>
        </button>
      </div>
      <div class="gfb-picker" id="gfb-picker" hidden>
        <div class="gfb-picker-header">
          <span class="gfb-picker-target" id="gfb-picker-target"></span>
          <span class="gfb-picker-cwd" id="gfb-picker-cwd"></span>
        </div>
        <div class="gfb-picker-list" id="gfb-picker-list"></div>
        <div class="gfb-selections" id="gfb-selections"></div>
      </div>
      <div class="gfb-ai-result" id="gfb-ai-result" hidden></div>
      <div class="gfb-bottom-actions">
        <button type="button" class="gfb-cancel-btn" id="gfb-cancel">Annuler</button>
        <button type="button" class="gfb-launch-btn" id="gfb-launch" disabled>
          ▶ Lancer le mode guidé
        </button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  document.getElementById("gfb-browse").addEventListener("click", () => {
    document.getElementById("gfb-main-actions").hidden = true;
    document.getElementById("gfb-picker").hidden = false;
    gfbLoadFolder(guidedFallbackState.folderPath);
  });
  document.getElementById("gfb-ai-scan").addEventListener("click", () => {
    document.getElementById("gfb-main-actions").hidden = true;
    document.getElementById("gfb-ai-result").hidden = false;
    gfbRunAiScan(false);
  });
  document.getElementById("gfb-colle").addEventListener("click", () => {
    closeGuidedFallbackModal();
    appendTurn("system", "Mode guidé désactivé : repli en mode colle libre. " + "Tu peux poser tes questions au tuteur normalement.");
  });
  document.getElementById("gfb-cancel").addEventListener("click", closeGuidedFallbackModal);
  document.getElementById("gfb-launch").addEventListener("click", gfbLaunchGuided);
  document.getElementById("gfb-ai-result").hidden = false;
  gfbRunAiScan(false);
}
function closeGuidedFallbackModal() {
  const m = document.getElementById("guided-fallback-modal");
  if (m) m.remove();
}
function escapeHtmlSafe(s) {
  return String(s || "").replace(/[<>&"]/g, c => ({
    "<": "&lt;",
    ">": "&gt;",
    "&": "&amp;",
    '"': "&quot;"
  })[c]);
}
async function gfbLoadFolder(pathRel) {
  const listEl = document.getElementById("gfb-picker-list");
  const cwdEl = document.getElementById("gfb-picker-cwd");
  const targetEl = document.getElementById("gfb-picker-target");
  if (!listEl || !cwdEl || !targetEl) return;
  targetEl.textContent = guidedFallbackState.pickerMode === "script" ? "🎯 Choisis le SCRIPT (texte oral) :" : "🎯 Choisis les SLIDES (PDF visuel) :";
  listEl.innerHTML = "<div class='gfb-loading'>Chargement…</div>";
  try {
    const r = await fetch("/api/browse_folder", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        path: pathRel
      })
    });
    const data = await r.json();
    if (!r.ok) {
      listEl.innerHTML = `<div class='gfb-error'>Erreur : ${escapeHtmlSafe(data.error || "")}</div>`;
      return;
    }
    guidedFallbackState.cwd = data.cwd || "";
    cwdEl.textContent = `📁 ${data.cwd || "<racine COURS>"}`;
    listEl.innerHTML = "";
    if (data.parent_path !== null && data.parent_path !== undefined) {
      const upBtn = document.createElement("button");
      upBtn.type = "button";
      upBtn.className = "gfb-entry gfb-entry-up";
      upBtn.innerHTML = "⬆ .. (remonter)";
      upBtn.addEventListener("click", () => gfbLoadFolder(data.parent_path));
      listEl.appendChild(upBtn);
    }
    for (const entry of data.entries || []) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "gfb-entry " + (entry.is_dir ? "gfb-entry-dir" : "gfb-entry-file");
      const icon = entry.is_dir ? "📁" : entry.kind === "slides_pdf" ? "🖼" : entry.kind === "script_md" || entry.kind === "script_txt" ? "📝" : entry.kind === "script_imprimable" ? "🖨" : entry.kind === "annale" ? "📑" : entry.kind === "aide_memoire" ? "📋" : entry.suffix === ".pdf" ? "📄" : "📄";
      const sizeStr = entry.size != null ? ` (${Math.round(entry.size / 1024)} KB)` : "";
      btn.innerHTML = `${icon} ${escapeHtmlSafe(entry.name)}<span class="gfb-entry-kind">${escapeHtmlSafe(entry.kind || "")}${sizeStr}</span>`;
      if (entry.is_dir) {
        btn.addEventListener("click", () => gfbLoadFolder(entry.path_rel));
      } else {
        btn.addEventListener("click", () => gfbSelectFile(entry));
      }
      listEl.appendChild(btn);
    }
    if (!(data.entries || []).length) {
      listEl.innerHTML += "<div class='gfb-empty'>Dossier vide</div>";
    }
  } catch (e) {
    listEl.innerHTML = `<div class='gfb-error'>Erreur réseau : ${escapeHtmlSafe(e.message)}</div>`;
  }
}
function gfbSelectFile(entry) {
  if (guidedFallbackState.pickerMode === "script") {
    guidedFallbackState.scriptPath = entry.path_rel;
    guidedFallbackState.pickerMode = "slides";
  } else {
    guidedFallbackState.slidesPath = entry.path_rel;
  }
  gfbRenderSelections();
  if (!guidedFallbackState.scriptPath || !guidedFallbackState.slidesPath) {
    gfbLoadFolder(guidedFallbackState.cwd);
  }
}
function gfbRenderSelections() {
  const sel = document.getElementById("gfb-selections");
  if (!sel) return;
  const s = guidedFallbackState;
  const isScriptActive = s.pickerMode === "script";
  sel.innerHTML = `
    <div class="gfb-selection-row ${isScriptActive ? 'gfb-sel-active' : ''}">
      <span class="gfb-sel-label">📝 Script ${isScriptActive ? '<span class="gfb-sel-target-marker">← cible du picker</span>' : ''} :</span>
      <span class="gfb-sel-value">${escapeHtmlSafe(s.scriptPath || "(non choisi)")}</span>
      ${s.scriptPath ? '<button type="button" class="gfb-sel-edit" data-edit="script" title="Modifier ce fichier (recharge le picker)">✎</button>' : ""}
      ${s.scriptPath ? '<button type="button" class="gfb-sel-clear" data-clear="script" title="Effacer ce choix">✕</button>' : ""}
    </div>
    <div class="gfb-selection-row ${!isScriptActive ? 'gfb-sel-active' : ''}">
      <span class="gfb-sel-label">🖼 Slides ${!isScriptActive ? '<span class="gfb-sel-target-marker">← cible du picker</span>' : ''} :</span>
      <span class="gfb-sel-value">${escapeHtmlSafe(s.slidesPath || "(non choisi)")}</span>
      ${s.slidesPath ? '<button type="button" class="gfb-sel-edit" data-edit="slides" title="Modifier ce fichier (recharge le picker)">✎</button>' : ""}
      ${s.slidesPath ? '<button type="button" class="gfb-sel-clear" data-clear="slides" title="Effacer ce choix">✕</button>' : ""}
    </div>
  `;
  function _folderOf(pathRel) {
    if (!pathRel) return s.folderPath;
    const idx = pathRel.lastIndexOf("/");
    return idx >= 0 ? pathRel.substring(0, idx) : "";
  }
  sel.querySelectorAll(".gfb-sel-clear").forEach(b => {
    b.addEventListener("click", () => {
      if (b.dataset.clear === "script") {
        s.scriptPath = "";
        s.pickerMode = "script";
      } else {
        s.slidesPath = "";
        s.pickerMode = "slides";
      }
      gfbRenderSelections();
      gfbLoadFolder(s.cwd || s.folderPath);
    });
  });
  sel.querySelectorAll(".gfb-sel-edit").forEach(b => {
    b.addEventListener("click", () => {
      const current = b.dataset.edit === "script" ? s.scriptPath : s.slidesPath;
      const startFolder = _folderOf(current);
      if (b.dataset.edit === "script") {
        s.pickerMode = "script";
      } else {
        s.pickerMode = "slides";
      }
      gfbRenderSelections();
      gfbLoadFolder(startFolder);
    });
  });
  gfbUpdateLaunchBtn();
}
function gfbUpdateLaunchBtn() {
  const btn = document.getElementById("gfb-launch");
  if (!btn) return;
  btn.disabled = !(guidedFallbackState.scriptPath && guidedFallbackState.slidesPath);
}
async function gfbRunAiScan(force) {
  const resultEl = document.getElementById("gfb-ai-result");
  if (!resultEl) return;
  let themeHint = "";
  try {
    const r0 = await fetch("/api/current_session");
    if (r0.ok) {
      const d0 = await r0.json();
      if (d0 && d0.active && d0.num && d0.num !== "full") {
        themeHint = d0.num;
      }
    }
  } catch (_) {}
  resultEl.innerHTML = themeHint ? `<div class='gfb-loading'>🎯 Recherche directe par thème <code>${escapeHtmlSafe(themeHint)}</code>…</div>` : "<div class='gfb-loading'>🤖 Gemini Flash scanne le dossier… (~3-5 s)</div>";
  try {
    const r = await fetch("/api/scan_with_ai", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        folder_path: guidedFallbackState.folderPath,
        force_refresh: !!force,
        theme: themeHint
      })
    });
    const data = await r.json();
    if (!r.ok) {
      resultEl.innerHTML = `<div class='gfb-error'>Erreur : ${escapeHtmlSafe(data.error || "")}</div>`;
      return;
    }
    const isDirect = data.method === "direct_suffix_match";
    const cachedTag = data.cached ? " <span class='gfb-cached'>(cache)</span>" : "";
    const confColor = data.confidence_0_100 >= 70 ? "high" : data.confidence_0_100 >= 40 ? "med" : "low";
    const headerLabel = isDirect ? "✅ Trouvé directement par thème" : "🤖 Suggestion IA";
    const headerExtra = isDirect ? "" : `<span class="gfb-conf gfb-conf-${confColor}">Confiance : ${data.confidence_0_100}/100</span>`;
    let actionsHtml = `
      <div class="gfb-ai-actions">
        <button type="button" class="gfb-ai-accept" id="gfb-ai-accept"
          ${data.script_oral_path && data.slides_pdf_path ? "" : "disabled"}>
          ▶ Lancer avec ces fichiers
        </button>
        <button type="button" class="gfb-ai-modify" id="gfb-ai-modify">
          ✎ Modifier (parcourir manuellement)
        </button>
      </div>
    `;
    if (!isDirect) {
      actionsHtml += `
        <div class="gfb-ai-partial-actions" id="gfb-ai-partial-actions">
          <span class="gfb-ai-partial-hint">
            ⚠ Seulement 1 fichier correct ? Accepte le bon et parcours juste l'autre :
          </span>
          <button type="button" class="gfb-ai-partial-btn" id="gfb-ai-keep-slides"
            ${data.slides_pdf_path ? "" : "disabled"}>
            ✓ Garder slides + 🔍 re-parcourir script
          </button>
          <button type="button" class="gfb-ai-partial-btn" id="gfb-ai-keep-script"
            ${data.script_oral_path ? "" : "disabled"}>
            ✓ Garder script + 🔍 re-parcourir slides
          </button>
          <button type="button" class="gfb-ai-refresh" id="gfb-ai-refresh">
            🔄 Relancer (force LLM, ignore cache)
          </button>
        </div>
      `;
    }
    resultEl.innerHTML = `
      <div class="gfb-ai-header">
        ${headerLabel}${cachedTag}
        ${headerExtra}
      </div>
      <div class="gfb-ai-reasoning">${escapeHtmlSafe(data.reasoning || "")}</div>
      <div class="gfb-ai-fields">
        <div class="gfb-ai-field">
          <span class="gfb-ai-label">📝 Script :</span>
          <span class="gfb-ai-path">${escapeHtmlSafe(data.script_oral_path || "(non trouvé)")}</span>
        </div>
        <div class="gfb-ai-field">
          <span class="gfb-ai-label">🖼 Slides :</span>
          <span class="gfb-ai-path">${escapeHtmlSafe(data.slides_pdf_path || "(non trouvé)")}</span>
        </div>
      </div>
      ${actionsHtml}
    `;
    function _seedFolderFrom(pathRel) {
      if (!pathRel) return guidedFallbackState.folderPath;
      const idx = pathRel.lastIndexOf("/");
      return idx >= 0 ? pathRel.substring(0, idx) : guidedFallbackState.folderPath;
    }
    const acceptBtn = document.getElementById("gfb-ai-accept");
    if (acceptBtn) acceptBtn.addEventListener("click", () => {
      guidedFallbackState.scriptPath = data.script_oral_path || "";
      guidedFallbackState.slidesPath = data.slides_pdf_path || "";
      if (!guidedFallbackState.scriptPath || !guidedFallbackState.slidesPath) {
        alert("Manque script ou slides, clique ✎ Modifier pour parcourir.");
        return;
      }
      gfbLaunchGuided();
    });
    const modifyBtn = document.getElementById("gfb-ai-modify");
    if (modifyBtn) modifyBtn.addEventListener("click", () => {
      guidedFallbackState.scriptPath = data.script_oral_path || "";
      guidedFallbackState.slidesPath = data.slides_pdf_path || "";
      guidedFallbackState.pickerMode = "slides";
      resultEl.hidden = true;
      document.getElementById("gfb-picker").hidden = false;
      gfbRenderSelections();
      gfbLoadFolder(_seedFolderFrom(guidedFallbackState.scriptPath || guidedFallbackState.slidesPath));
    });
    const refreshBtn = document.getElementById("gfb-ai-refresh");
    if (refreshBtn) refreshBtn.addEventListener("click", () => gfbRunAiScan(true));
    const keepSlidesBtn = document.getElementById("gfb-ai-keep-slides");
    if (keepSlidesBtn) keepSlidesBtn.addEventListener("click", () => {
      guidedFallbackState.slidesPath = data.slides_pdf_path || "";
      guidedFallbackState.scriptPath = "";
      guidedFallbackState.pickerMode = "script";
      resultEl.hidden = true;
      document.getElementById("gfb-picker").hidden = false;
      gfbRenderSelections();
      gfbLoadFolder(_seedFolderFrom(guidedFallbackState.slidesPath));
    });
    const keepScriptBtn = document.getElementById("gfb-ai-keep-script");
    if (keepScriptBtn) keepScriptBtn.addEventListener("click", () => {
      guidedFallbackState.scriptPath = data.script_oral_path || "";
      guidedFallbackState.slidesPath = "";
      guidedFallbackState.pickerMode = "slides";
      resultEl.hidden = true;
      document.getElementById("gfb-picker").hidden = false;
      gfbRenderSelections();
      gfbLoadFolder(_seedFolderFrom(guidedFallbackState.scriptPath));
    });
  } catch (e) {
    resultEl.innerHTML = `<div class='gfb-error'>Erreur réseau : ${escapeHtmlSafe(e.message)}</div>`;
  }
}
async function gfbLaunchGuided() {
  const s = guidedFallbackState;
  if (!s.scriptPath || !s.slidesPath) return;
  closeGuidedFallbackModal();
  appendTurn("system", `🎯 Mode guidé : lancement avec script <code>${escapeHtmlSafe(s.scriptPath)}</code> ` + `et slides <code>${escapeHtmlSafe(s.slidesPath)}</code>.`);
  initGuidedPanel(s.startIndex, {
    script_path: s.scriptPath,
    slides_path: s.slidesPath
  });
}
function renderGuidedLiteNotice(reason) {
  if (!dialogue) return;
  const wrapper = document.createElement("div");
  wrapper.className = "turn system guided-lite-notice";
  wrapper.dataset.localOnly = "1";
  const safeReason = escapeHtmlSafe(reason);
  wrapper.innerHTML = `
    <div class="role">ℹ Mode guidé : lite</div>
    <div class="guided-lite-body">${safeReason}</div>
    <div class="guided-lite-actions">
      <button type="button" class="guided-lite-cc-btn" id="guided-lite-cc-btn">
        📝 Régénérer proprement via Claude Code
      </button>
    </div>
  `;
  if (dialogue.querySelector(".placeholder")) dialogue.innerHTML = "";
  dialogue.appendChild(wrapper);
  dialogue.scrollTop = dialogue.scrollHeight;
  const btn = wrapper.querySelector("#guided-lite-cc-btn");
  if (btn) btn.addEventListener("click", openClaudeCodePromptModal);
}
async function openClaudeCodePromptModal(defaultKind = "regen_script_md") {
  let ctx = null;
  try {
    const r = await fetch("/api/current_session");
    if (r.ok) ctx = await r.json();
  } catch (_) {}
  if (!ctx || !ctx.active) {
    alert("Pas de session active : impossible de générer un prompt.");
    return;
  }
  const existing = document.getElementById("cc-prompt-modal");
  if (existing) existing.remove();
  const modal = document.createElement("div");
  modal.id = "cc-prompt-modal";
  modal.className = "modal-overlay";
  modal.innerHTML = `
    <div class="modal-card cc-prompt-card">
      <h3>📝 Prompt Claude Code</h3>
      <p class="cc-prompt-hint">
        Copie le prompt et colle-le dans une nouvelle session
        <code>claude</code> (CLI ou web) à la racine de
        <code>COURS/</code>. La session pourra éditer fichiers,
        relancer pipelines, auditer.
      </p>
      <div class="cc-prompt-kind-selector">
        <label class="cc-kind-label">
          <input type="radio" name="cc-kind" value="regen_script_md" ${defaultKind === "regen_script_md" ? "checked" : ""}>
          🔧 Régénérer SCRIPT.md Feynman (session courante)
        </label>
        <label class="cc-kind-label">
          <input type="radio" name="cc-kind" value="audit_matiere_cc" ${defaultKind === "audit_matiere_cc" ? "checked" : ""}>
          🔍 Auditer toute la matière (script/slides orphelins)
        </label>
      </div>
      <textarea class="cc-prompt-textarea" readonly placeholder="Chargement…"></textarea>
      <div class="cc-prompt-actions">
        <button type="button" class="cc-prompt-copy" id="cc-prompt-copy">📋 Copier dans le presse-papier</button>
        <button type="button" class="cc-prompt-close" id="cc-prompt-close">Fermer</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  const ta = modal.querySelector(".cc-prompt-textarea");
  async function _loadPrompt(kind) {
    ta.value = "Chargement…";
    try {
      const r = await fetch("/api/claude_code_prompt", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          kind
        })
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        ta.value = "Erreur : " + (d.error || r.status);
        return;
      }
      const data = await r.json();
      ta.value = data.prompt || "";
    } catch (e) {
      ta.value = "Erreur réseau : " + e.message;
    }
  }
  _loadPrompt(defaultKind);
  modal.querySelectorAll('input[name="cc-kind"]').forEach(input => {
    input.addEventListener("change", () => _loadPrompt(input.value));
  });
  document.getElementById("cc-prompt-copy").addEventListener("click", async () => {
    if (!ta) return;
    try {
      await navigator.clipboard.writeText(ta.value);
      const btn = document.getElementById("cc-prompt-copy");
      if (btn) {
        btn.textContent = "✓ Copié !";
        setTimeout(() => {
          btn.textContent = "📋 Copier dans le presse-papier";
        }, 2000);
      }
    } catch (_) {
      ta.select();
      document.execCommand("copy");
    }
  });
  document.getElementById("cc-prompt-close").addEventListener("click", () => modal.remove());
}