// Compagnon de révision, front Phase A, vanilla JS.
// Cf. ARCHITECTURE.md §8.3.

// Phase v15.6.5 : 30 s au lieu de 60 s pour la sensation "live" sur le
// solde DeepSeek qui peut baisser à chaque rewrite/stream. Cache backend
// 30 s sur le bloc engines (cf. _collect_engines_status), donc 1 hit
// API externe par 30 s en pratique.
const QUOTA_POLL_MS = 30_000;

const $ = (sel) => document.querySelector(sel);

// ============================================================ Tooltip global (Phase A.10.15)
// Système custom qui remplace les tooltips natifs ternes du browser
// pour TOUS les éléments avec `title=`. User : « rend le tooltip plus
// joli […] factorise le code pour pas le faire manuellement sur chaque
// truc mais que ça soit une classe qui s'applique à tous les cas (dont
// ceux que j'oublie ou les futurs qui arriveront) ».
//
// Mécanisme :
//   1. Hijack au load : pour chaque [title], copie dans data-tooltip,
//      retire le title natif, copie en aria-label pour les SR.
//   2. MutationObserver pour les éléments dynamiquement ajoutés.
//   3. Event delegation mouseover/mouseout sur document → affiche un
//      seul container global #global-tooltip positionné via
//      getBoundingClientRect (auto haut/bas selon la place).
//   4. Délai d'apparition 350ms pour ne pas être agressif.
//   5. Cache au scroll/wheel/click pour ne pas rester accroché.
(function _initGlobalTooltip() {
  if (window._globalTooltipInited) return;
  window._globalTooltipInited = true;

  const tip = document.createElement("div");
  tip.id = "global-tooltip";
  tip.hidden = true;
  // Insert au boot de DOMContentLoaded ; si body pas encore prêt,
  // on diffère.
  const attach = () => document.body.appendChild(tip);
  if (document.body) attach();
  else document.addEventListener("DOMContentLoaded", attach, { once: true });

  let showTimer = null;
  let hideTimer = null;
  let currentTarget = null;

  const positionTip = (el) => {
    // Mesure d'abord (tooltip déjà visible mais opacity:0 pour ne pas
    // se déclencher visuellement avant positionnement).
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
    // Clamp horizontal
    left = Math.max(4, Math.min(left, window.innerWidth - tipRect.width - 4));
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
    tip.classList.remove("gt-above", "gt-below");
    tip.classList.add(placement === "above" ? "gt-above" : "gt-below");
  };

  const show = (el, text) => {
    if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
    if (showTimer) { clearTimeout(showTimer); showTimer = null; }
    showTimer = setTimeout(() => {
      tip.textContent = text;
      tip.hidden = false;
      tip.classList.remove("gt-hide");
      // 1ère frame : positionne caché, puis show avec animation
      positionTip(el);
      // Re-position au prochain tick si le content a changé la taille
      requestAnimationFrame(() => {
        if (el === currentTarget) positionTip(el);
        tip.classList.add("gt-show");
      });
    }, 350);
  };

  const hide = () => {
    if (showTimer) { clearTimeout(showTimer); showTimer = null; }
    if (hideTimer) clearTimeout(hideTimer);
    tip.classList.remove("gt-show");
    tip.classList.add("gt-hide");
    hideTimer = setTimeout(() => {
      tip.hidden = true;
      currentTarget = null;
    }, 150);
  };

  const hijack = (el) => {
    if (!el || el.nodeType !== 1) return;
    if (el.dataset.tooltip !== undefined) return;
    const t = el.getAttribute("title");
    if (!t) return;
    el.dataset.tooltip = t;
    el.removeAttribute("title");
    // a11y : conserve l'info pour les screen readers (si pas déjà set)
    if (!el.hasAttribute("aria-label")) {
      el.setAttribute("aria-label", t);
    }
  };

  // Hijack initial
  const initialHijack = () => {
    document.querySelectorAll("[title]").forEach(hijack);
  };
  if (document.readyState !== "loading") initialHijack();
  else document.addEventListener("DOMContentLoaded", initialHijack, { once: true });

  // MutationObserver pour le DOM dynamique
  const mo = new MutationObserver((muts) => {
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
      childList: true, subtree: true,
      attributes: true, attributeFilter: ["title"],
    });
  };
  if (document.body) startObserver();
  else document.addEventListener("DOMContentLoaded", startObserver, { once: true });

  // Event delegation
  document.addEventListener("mouseover", (e) => {
    const el = e.target.closest("[data-tooltip]");
    if (!el || el === currentTarget) return;
    currentTarget = el;
    show(el, el.dataset.tooltip);
  });
  document.addEventListener("mouseout", (e) => {
    if (!currentTarget) return;
    const rel = e.relatedTarget;
    if (rel && currentTarget.contains(rel)) return;
    hide();
  });
  // Hide au scroll / wheel / click / keydown pour ne pas rester accroché
  // (sinon le tooltip "flotte" alors qu'on a quitté l'élément).
  const hideAggressive = () => { if (currentTarget) hide(); };
  document.addEventListener("scroll", hideAggressive, true);
  document.addEventListener("wheel", hideAggressive, { passive: true });
  document.addEventListener("click", hideAggressive);
  document.addEventListener("keydown", (e) => {
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
let activeMode = null;  // "colle" | "guidé"  (mode "lecture" supprimé Phase Z.8)
// Phase v15.7.4 : format colle courant (oral|photos|mixte). Reflète l'état
// backend (set_meta dans session_state). Mis à jour au start_session, au
// restore via /api/current_session, et à chaque bascule chip/slash.
let activeColleFormat = "mixte";
let currentEventSource = null;
let userRole = "owner";  // "owner" | "viewer", défini au boot via /api/role
let viewerPollHandle = null;  // setInterval handle pour polling /api/current_session
let currentClaudeTurn = null;
let currentClaudeRawText = "";  // accumulateur pour rendu markdown live
let mediaRecorder = null;
let recordedChunks = [];
let micStream = null;
let isRecording = false;

// ============================================================ Mode guidé (Phase A.7.2 v5)
// État : liste de slides + index courant. Initialisé après start_session
// si mode === "guidé" via /api/guided/init. Espace/← /→/🎯 naviguent.
// Chaque changement de slide envoie un meta-message à Claude qui décide
// d'intervenir ou non (mode adaptatif).

let guidedSlides = [];   // [{n, title, duration_min, png_url, oral_excerpt}]
let guidedIndex = -1;    // index 0-based dans guidedSlides
let guidedTitleGlobal = "";

// Garde-fous anti-cascade pour les transitions de slide auto. Le tuteur
// peut malgré le prompt §2.9 émettre <<<NEXT_SLIDE>>> en réponse au meta
// d'arrivée, ce qui crée une cascade. Deux barrières :
//   1. Cooldown temporel court (5s) entre transitions auto consécutives.
//   2. Flag binaire respondingToSlideMeta qui couvre TOUTE la durée du
//      stream déclenché par sendGuidedSlideMeta, ne dépend pas du temps,
//      reste actif tant que le tuteur stream sa réponse au meta. Si le
//      tuteur émet NEXT_SLIDE pendant ce stream, on ignore quoi qu'il
//      arrive (les markers d'arrivée n'enchaînent jamais une transition).
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
  // True si la dernière bulle Compagnon (claude) du dialogue se termine
  // par un point d'interrogation. Sert à bloquer les transitions auto
  // de slide quand le tuteur vient de poser une question, l'étudiant
  // doit avoir le temps de répondre.
  const claudeBubbles = dialogue.querySelectorAll(".turn.claude");
  if (!claudeBubbles.length) return false;
  const last = claudeBubbles[claudeBubbles.length - 1];
  let raw = last.dataset.rawText || last.textContent || "";
  // Strip balise NEXT_SLIDE finale éventuelle
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

// ============================================================ Markdown rendering (Phase A.7.2 v3)
// Petit renderer minimaliste pour les patterns courants des réponses Claude :
// **gras**, *italique*, `code inline`, listes - / 1. , paragraphes \n\n, sauts \n.
// Échappe le HTML d'abord pour éviter les injections (Claude peut produire
// du HTML non-trusté dans son texte). Pas de dépendance externe (pas de CDN).

function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Phase A.10.2 : helper qui retourne l'URL serveur pour une pièce
// jointe (photo de séance ou autre fichier). Route selon `storage` :
//   - "uploads" (défaut nouvelles A.10.2+) → /api/upload_file
//   - "cours" (legacy + backfill) → /api/cours_file
// Si `att.storage` est absent, fallback sur "cours" pour les sessions
// pré-A.10.2 dont les tray entries n'ont pas le champ.
function _attachmentSrcUrl(att) {
  if (!att || !att.rel_path) return "";
  const storage = att.storage || "cours";
  const endpoint = storage === "uploads" ? "/api/upload_file" : "/api/cours_file";
  return `${endpoint}?path=${encodeURIComponent(att.rel_path)}`;
}

// ============================================================ Markdown rendering (Phase A.10.16)
// Migration des 240+ lignes de regex hardcoded vers markdown-it (CDN).
// La biblio gère nativement CommonMark + GFM (tables, listes imbriquées,
// blockquotes + listes, fenced code, etc.), résiste aux entrées partielles
// du streaming SSE (un `**` non fermé devient littéral, pas d'exception)
// et a déjà testé tous les edge cases composés qu'on rencontrait à la
// main (notamment le bug A.10.15d : listes à puces dans blockquote).
//
// Hooks custom préservés :
//   - renderer image : route les paths vers /api/upload_file (préfixe
//     `_uploads/`), /api/cours_file (relatif COURS) ou URL externe directe ;
//     ajoute tooltip `_prettifyPhotoFilename` au hover ; onerror placeholder
//     visible ; wrap dans <span class="md-img-wrap" data-md=...> avec bouton
//     🗑 qui retire l'image du texte source du message.
//
// Le post-process des refs page (« page 3 du corrigé ») reste séparé dans
// `linkifyPageRefs(rootEl)` qui walk les text nodes du DOM rendu (cf.
// section « Page refs cliquables » plus bas). Math LaTeX `$...$` reste
// géré par KaTeX auto-render sur l'event SSE `done`.
//
// Lazy-init : `app.js` n'a pas `defer` mais le script markdown-it si, donc
// `window.markdownit` n'est pas garanti dispo au parse de ce fichier. On
// résout au premier appel à `renderMarkdown`, puis on cache l'instance.

let _md = null;

function _getMarkdownIt() {
  if (_md) return _md;
  if (typeof window.markdownit !== "function") return null;
  _md = window.markdownit({
    html: false,        // pas d'HTML brut en entrée (XSS-safe)
    linkify: false,     // pas d'auto-linkify : on a `linkifyPageRefs` qui fait mieux
    breaks: true,       // \n → <br> (alignement avec l'ancien renderMarkdown)
    typographer: false, // pas de smartquotes (« » FR déjà gérés à la source)
  });
  // Désactive les règles non utilisées qui consomment du temps de parse
  try {
    _md.disable(["reference", "abbr", "footnote", "deflist"]);
  } catch (_) { /* version markdown-it sans ces règles → no-op */ }
  // Override du renderer image (cf. Phase A.7.2 v4 + A.10.2 + A.10.15)
  _md.renderer.rules.image = function (tokens, idx, options, env, self) {
    const token = tokens[idx];
    const src = token.attrGet("src") || "";
    const alt = self.renderInlineAsText(token.children || [], options, env) || "";
    const isExternal = /^https?:\/\//i.test(src);
    // Normalise les backslashes Windows que Claude génère parfois
    // (ex: `PRG2\\CM\\scripts_oraux\\slide-7.png`) en forward-slashes
    // pour que /api/cours_file résolve correctement.
    const normSrc = src.replace(/\\/g, "/").trim();
    const safeAlt = alt.replace(/"/g, "&quot;");
    let safeSrc;
    if (isExternal) {
      safeSrc = normSrc.replace(/"/g, "&quot;");
    } else if (normSrc.startsWith("_uploads/")) {
      // Strip le préfixe pour passer le chemin relatif à UPLOADS_DIR
      const stripped = normSrc.slice("_uploads/".length);
      safeSrc = `/api/upload_file?path=${encodeURIComponent(stripped)}`;
    } else {
      safeSrc = `/api/cours_file?path=${encodeURIComponent(normSrc)}`;
    }
    // Tooltip joli au hover : pour les images OCR-renamed, ça donne
    // "Pseudo Code Leaf2 · 14/05 10:42".
    // Phase A.10.32 : on émet `data-tooltip` DIRECTEMENT (comme les boutons
    // d'action du chat), au lieu d'un `title=` que le système de tooltip
    // global devait hijacker. Le hijack par MutationObserver ne se déclenche
    // pas de façon fiable sur les `<img>` injectées en masse via innerHTML
    // (rerender de transcript / replay), d'où l'absence de tooltip au hover
    // dans le chat alors que la galerie (qui pose `title` via la propriété
    // JS `card.title=`, donc via une mutation d'attribut bien captée)
    // l'affichait. Émettre `data-tooltip` retire toute dépendance au hijack.
    let imgTitle = "";
    try {
      const filenameOnly = normSrc.split("/").pop() || "";
      const pretty = (typeof _prettifyPhotoFilename === "function")
        ? _prettifyPhotoFilename(filenameOnly) : filenameOnly;
      imgTitle = (pretty || alt).replace(/"/g, "&quot;");
    } catch (_) {
      imgTitle = safeAlt;
    }
    // Attribut conditionnel : pas de `data-tooltip=""` (sinon le hover
    // afficherait une bulle vide, `closest("[data-tooltip]")` matche la
    // simple présence de l'attribut).
    const tipAttr = imgTitle
      ? ` data-tooltip="${imgTitle}" aria-label="${imgTitle}"`
      : "";
    const dataPath = normSrc.replace(/"/g, "&quot;");
    // data-md = markdown source reconstitué, sert au bouton 🗑 pour retirer
    // pile cette image du texte du message (cf. dialogue click handler).
    const origMd = `![${alt}](${src})`;
    const dataMd = origMd.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
    return `<span class="md-img-wrap" data-md="${dataMd}">` +
      `<img src="${safeSrc}" alt="${safeAlt}"${tipAttr} class="md-img" data-src-path="${dataPath}" onerror="this.outerHTML='&lt;div class=&quot;md-img-broken&quot;&gt;⚠️ Image introuvable : &lt;code&gt;'+this.dataset.srcPath+'&lt;/code&gt;&lt;/div&gt;'">` +
      `<button type="button" class="md-img-del" data-tooltip="Retirer cette pièce jointe du message" aria-label="Retirer cette pièce jointe du message">🗑</button>` +
      `</span>`;
  };
  // Phase A.7.2 v8 : préserve la classe `md-table` sur les tables
  // (CSS existant). Override mince qui injecte la classe sur l'open
  // tag, sinon markdown-it produit `<table>` nu.
  _md.renderer.rules.table_open = function () {
    return '<table class="md-table">\n';
  };
  return _md;
}

// Phase A.10.28 : Gemini (engine gemini_api) émet souvent le titre d'une
// carte cahier EN PROSE juste avant la balise `<<<CAHIER>>>`, au lieu, OU EN
// PLUS, de l'attribut `titre="…"`. Trois formes observées (AN1 CCT) :
//   a) « Titre : **9. …** \n <<<CAHIER>>> »                  (balise nue)
//   b) « Titre : **8. …** \n <<<CAHIER titre="Méthode…">>> » (balise + attribut)
//   c) « **Racine carrée (méthode)** \n <<<CAHIER>>> »       (ligne full-bold)
// Conséquence : ligne « Titre : … » parasite dans le dialogue, et carte sans
// bandeau (a/c) ou avec un titre incohérent (b). Miroir du fix A.10.15b.
//
// Règle :
//  - Ligne « Titre : … » (mot-clé EXPLICITE) → titre AUTORITAIRE. Aspiré dans
//    titre=, que la balise soit nue OU déjà pourvue. Si un ancien titre=
//    existait (cas b), ce n'était pas le vrai titre : on le rapatrie en 1ère
//    ligne du corps pour ne rien perdre (« Méthode : … » = sous-ligne réelle).
//  - Ligne full-bold `**…**` (signal plus FAIBLE) → ne remplit QUE les balises
//    nues, jamais d'écrasement d'un titre= déjà présent.
// Une ligne d'amorce optionnelle (« Sous ce titre… », « Notez… ») entre le
// titre et la balise est tolérée et supprimée elle aussi.
function _hoistCahierTitles(text) {
  if (!text || text.indexOf("<<<CAHIER") === -1) return text;
  // Fin de ligne-titre → blancs → amorce optionnelle → blancs.
  const TAIL =
    "[ \\t]*\\n(?:[ \\t]*\\n)*" +
    "(?:[ \\t]*(?:Sous ce titre|Notez|Écriv|Inscriv|Recopiez)[^\\n]*\\n)?" +
    "(?:[ \\t]*\\n)*";
  const clean = (s) => s.trim().replace(/\s+/g, " ").replace(/"/g, "'");
  // a/b, variante mot-clé « Titre : … » : titre autoritaire, balise nue OU
  // déjà pourvue. L'attribut existant est rapatrié dans le corps.
  const reKeyword = new RegExp(
    "(^|\\n)[ \\t]*Titre[s]?[ \\t]*[:：\\-–—]?[ \\t]*" +
    "(?:\\*\\*[ \\t]*)?(.+?)(?:[ \\t]*\\*\\*)?" +
    TAIL + "<<<CAHIER([^>]*)>{1,3}",
    "g"
  );
  text = text.replace(reKeyword, (m, lead, rawTitle, attrs) => {
    const titre = clean(rawTitle);
    if (!titre || titre.length > 120) return m;  // garde-fou : pas un titre
    const old = ((attrs || "").match(/titre\s*=\s*"([^"]*)"/i) || [])[1];
    const body =
      old && old.trim() && old.trim().toLowerCase() !== titre.toLowerCase()
        ? "\n" + old.trim() + "\n"
        : "";
    return `${lead}<<<CAHIER titre="${titre}">>>${body}`;
  });
  // c, variante full-bold (signal faible) : ne remplit QUE les balises nues.
  const reBold = new RegExp(
    "(^|\\n)[ \\t]*\\*\\*[ \\t]*(.+?)[ \\t]*\\*\\*" + TAIL + "<<<CAHIER>{1,3}",
    "g"
  );
  text = text.replace(reBold, (m, lead, rawTitle) => {
    const titre = clean(rawTitle);
    if (!titre || titre.length > 120) return m;
    return `${lead}<<<CAHIER titre="${titre}">>>`;
  });
  return text;
}

// Phase A.10.28 : protège les spans mathématiques (`$…$`, `$$…$$`) de
// markdown-it AVANT le rendu. Sans ça, un `_indice_` ou un `*` à l'intérieur
// d'une formule est pris pour de l'emphase et corrompt le LaTeX, observé sur
// `\underbrace{…}_{\text{Bloc 1}} \times \underbrace{…}_{\text{Bloc 2}}` que
// markdown-it transformait en `<em>…</em>`. On remplace chaque span par un
// placeholder ASCII neutre, on rend le markdown, puis on réinjecte le LaTeX
// BRUT ; KaTeX le rend ensuite sur le DOM (event `done`). Régression
// introduite par la migration markdown-it A.10.16 : l'ancien renderMarkdown
// regex ne touchait jamais l'intérieur des `$`.
// Phase A.10.31 : balises couleur cahier (`{rouge}`, `{hl-jaune}`, fermetures
// `{/…}`). Sert à deux nettoyages : retrait à l'intérieur d'un `$…$` (cf.
// `_protectMathSpans`) et retrait des résidus orphelins (cf. `_renderCahierBlock`).
const _CAHIER_TAG_RE =
  /\{\/?(?:bleu|rouge|vert|noir|hl-jaune|hl-vert|hl-rose|hl-violet)\}/g;

// Phase A.12.5 : normalisation siunitx. KaTeX n'implémente PAS le package
// LaTeX `siunitx` : `\SI{20}{\kilo\hertz}`, `\per`, `\mega`… s'affichent en
// rouge littéral (commande inconnue), et un `\SI{…}` émis HORS `$…$` reste
// du texte brut. Le tuteur LLM y recourt malgré le prompt → on convertit
// au rendu : `\SI{X}{unités}` → `X <unités lisibles>`, prefixes/unités
// siunitx → leur symbole. Inside math : forme KaTeX (`\,\mathrm{…}`) ;
// hors math : texte plein.
const _SIUNITX_UNITS = {
  yotta: "Y", zetta: "Z", exa: "E", peta: "P", tera: "T", giga: "G",
  mega: "M", kilo: "k", hecto: "h", deca: "da", deci: "d", centi: "c",
  milli: "m", micro: "µ", nano: "n", pico: "p", femto: "f",
  hertz: "Hz", second: "s", minute: "min", hour: "h", metre: "m",
  meter: "m", gram: "g", kilogram: "kg", bit: "bit", byte: "B",
  watt: "W", volt: "V", ampere: "A", ohm: "Ω", farad: "F", henry: "H",
  joule: "J", newton: "N", pascal: "Pa", kelvin: "K", celsius: "°C",
  mole: "mol", candela: "cd", decibel: "dB", percent: "%", per: "/",
  bel: "B", radian: "rad", steradian: "sr", tesla: "T", weber: "Wb",
};
// Une commande de contrôle LaTeX complète : `\` + lettres, NON suivie d'une
// autre lettre (sinon `\percent` serait coupé en `\per`). Le remplacement se
// fait en UN seul passage par regex globale : sinon `\per\second` → on
// remplace `\second`→`s` d'abord → `\pers` → le `\` de `\per` est collé à un
// `s`, plus de frontière de mot → `\per` n'est plus reconnu (bug A.12.5).
const _SIUNITX_CMD_RE = /\\([a-zA-Z]+)(?![a-zA-Z])/g;
function _expandSiUnits(u) {
  const s = String(u || "").replace(_SIUNITX_CMD_RE, (m, name) =>
    Object.prototype.hasOwnProperty.call(_SIUNITX_UNITS, name)
      ? _SIUNITX_UNITS[name]
      : m
  );
  // Retire les accolades, les commandes inconnues résiduelles, les espaces.
  return s.replace(/[{}]/g, "").replace(/\\[a-zA-Z]+/g, "").replace(/\s+/g, "");
}
function _normalizeSiunitx(text, inMath) {
  if (!text || text.indexOf("\\") === -1) return text;
  let t = text;
  // \SI{valeur}{unités} et \qty{valeur}{unités}
  t = t.replace(
    /\\(?:SI|qty)\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g,
    (_m, val, unit) => {
      const u = _expandSiUnits(unit);
      const v = String(val).trim();
      return inMath ? `${v}\\,\\mathrm{${u}}` : `${v} ${u}`;
    }
  );
  // \si{unités} (unité seule) et \unit{unités}
  t = t.replace(/\\(?:si|unit)\s*\{([^{}]*)\}/g, (_m, unit) => {
    const u = _expandSiUnits(unit);
    return inMath ? `\\mathrm{${u}}` : u;
  });
  // \num{nombre}
  t = t.replace(/\\num\s*\{([^{}]*)\}/g, (_m, n) => String(n).trim());
  // Macros de préfixe/unité restées nues (hors \SI), un seul passage, et
  // seules les commandes connues sont remplacées (les vraies commandes
  // KaTeX `\geq`, `\cdot`, `\mathrm`, `\perp`… sont laissées intactes).
  t = t.replace(_SIUNITX_CMD_RE, (m, name) =>
    Object.prototype.hasOwnProperty.call(_SIUNITX_UNITS, name)
      ? _SIUNITX_UNITS[name]
      : m
  );
  return t;
}

function _protectMathSpans(text) {
  const spans = [];
  const staged = (text || "").replace(
    /\$\$[\s\S]+?\$\$|\$[^$\n]+?\$/g,
    (m) => {
      // Phase A.10.31 : un `{couleur}`/`{hl-…}` émis PAR LE TUTEUR À
      // L'INTÉRIEUR d'un `$…$` casse le rendu : les passes STYLOS le
      // convertiraient en `<span>`, scindant la formule en deux nœuds texte
      // → KaTeX ne peut plus apparier les `$` → `$` littéraux + formule
      // éclatée (observé : `$\sin^3(x) = {vert}…{/vert}$`). On retire ces
      // balises du LaTeX, la formule rend en noir (doctrine A.10.29 ;
      // colorer l'intérieur d'une formule n'a de toute façon pas de sens).
      const clean = m.replace(_CAHIER_TAG_RE, "");
      const i = spans.length;
      // Phase A.12.5 : convertit siunitx en forme KaTeX dans le span math.
      spans.push(_normalizeSiunitx(clean, true));
      return `ZZMATHPLACEHOLDER${i}ZZ`;
    }
  );
  // Phase A.12.5 : convertit les `\SI{…}` restés HORS `$…$` en texte plein.
  return { staged: _normalizeSiunitx(staged, false), spans };
}
function _restoreMathSpans(html, spans) {
  if (!spans || !spans.length) return html;
  return html.replace(
    /ZZMATHPLACEHOLDER(\d+)ZZ/g,
    (_m, i) => spans[parseInt(i, 10)] || ""
  );
}

// Phase A.12 : rendu d'une puce d'appel d'outil. La boucle d'outils du
// backend (claude_client) injecte un marqueur `<<<TOOLCALL>>>{json}<<<TOOLEND>>>`
// dans le flux entre le texte d'avant et d'après un Read/Grep/Glob. Le front
// le remplace par cette puce « 🔍 Lecture de X », l'étudiant voit le tuteur
// agir, comme dans Claude Code, au lieu d'un gros bloc de texte opaque.
function _renderToolCallChip(jsonStr) {
  let tool = "", label = "", ok = true;
  try {
    const d = JSON.parse(jsonStr);
    tool = d.tool || "";
    label = d.label || "";
    ok = d.ok !== false;
  } catch (_) {
    return "";
  }
  const ICONS = { Read: "📄", Grep: "🔎", Glob: "🗂️" };
  const VERBS = { Read: "Lecture de", Grep: "Recherche", Glob: "Liste" };
  const icon = ICONS[tool] || "🔧";
  const verb = VERBS[tool] || tool || "Outil";
  const cls = ok ? "tool-call-chip" : "tool-call-chip is-error";
  const fail = ok ? "" : ' <span class="tcc-fail">échec</span>';
  return (
    `<div class="${cls}">` +
    `<span class="tcc-dot"></span>` +
    `<span class="tcc-icon">${icon}</span>` +
    `<span class="tcc-text">${verb} <code>${escapeHtml(label)}</code>${fail}</span>` +
    `</div>`
  );
}

// Phase A.12.4 : bloc de questions à choix cliquables. Le tuteur émet
// <<<CHOICES>>>{"q","multi","options"}<<<END>>> ; le front affiche la
// question, des boutons d'options, et un champ libre « Autre », façon
// interface Claude.ai. La sélection est composée en message étudiant et
// envoyée (cf. listener délégué `_onChoicesClick`).
function _renderChoicesBlock(jsonStr) {
  let q = "", options = [], multi = false;
  try {
    const d = JSON.parse(jsonStr);
    q = String(d.q || d.question || "").trim();
    options = Array.isArray(d.options) ? d.options : [];
    multi = d.multi === true;
  } catch (_) {
    return "";
  }
  if (!options.length) return "";
  const optsHtml = options
    .map((o) => {
      const label = escapeHtml(String(o));
      return `<button type="button" class="choice-opt" data-val="${label}">${label}</button>`;
    })
    .join("");
  const hint = multi
    ? "Sélectionne une ou plusieurs réponses : ou bien écris la tienne."
    : "Choisis une réponse : ou bien écris la tienne.";
  return (
    `<div class="choices-block" data-multi="${multi ? "1" : "0"}">` +
    (q ? `<div class="choices-q">${escapeHtml(q)}</div>` : "") +
    `<div class="choices-hint">${hint}</div>` +
    `<div class="choices-opts">${optsHtml}</div>` +
    `<textarea class="choice-custom" rows="2" placeholder="✍️ Autre / précise ta réponse…"></textarea>` +
    `<button type="button" class="choice-send">Envoyer ma réponse →</button>` +
    `</div>`
  );
}

// Listener délégué : clics sur les options / le bouton Envoyer d'un bloc
// de choix. Délégué (sur document) pour survivre aux re-render de bulle.
function _onChoicesClick(e) {
  const opt = e.target.closest(".choice-opt");
  if (opt) {
    const block = opt.closest(".choices-block");
    if (!block || block.classList.contains("is-answered")) return;
    if (block.dataset.multi !== "1") {
      block.querySelectorAll(".choice-opt.selected").forEach((b) => {
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
  const picked = [...block.querySelectorAll(".choice-opt.selected")].map(
    (b) => (b.dataset.val || "").trim()
  );
  const customEl = block.querySelector(".choice-custom");
  const custom = customEl ? customEl.value.trim() : "";
  const parts = picked.filter(Boolean);
  if (custom) parts.push(custom);
  if (!parts.length) {
    if (customEl) customEl.focus();
    return;
  }
  block.classList.add("is-answered");
  block.querySelectorAll("button, textarea").forEach((el) => {
    el.disabled = true;
  });
  if (userInput) {
    userInput.value = parts.join("\n");
    try {
      userInput.dispatchEvent(new Event("input", { bubbles: true }));
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
      // Phase A.10.19 : extrait les blocs `<<<CAHIER titre="...">>>...<<<END>>>`
      // AVANT markdown-it (sinon les balises seraient escapées/écrasées).
      // Chaque bloc est remplacé par un placeholder `ZZCAHIERPLACEHOLDERNZZ`
      // unique. Le sentinel n'utilise QUE des lettres ASCII sans aucun caractère
      // spécial markdown (pas d'underscore : `___text___` serait parsé comme
      // bold+italic CommonMark → le placeholder serait mangé. Bug observé
      // 2026-05-15 sur la 1ère tentative avec `___CAHIER_N___`).
      // Après render, on rerend les blocs via `_renderCahierBlock` qui :
      //   1. md.render le contenu (markdown + KaTeX inline)
      //   2. remplace {bleu}…{/bleu} (4 stylos) par des spans colorés
      //   3. remplace {hl-jaune}…{/hl-jaune} (4 surligneurs) par <mark>
      //   4. tolère aussi ==texte== comme raccourci surligneur jaune
      // Phase A.12 : extrait les marqueurs d'appels d'outils
      // <<<TOOLCALL>>>{json}<<<TOOLEND>>> AVANT markdown-it. Rendus en puces
      // visuelles « 🔍 Lecture de X » par _renderToolCallChip. On retire
      // aussi un marqueur encore incomplet (close pas arrivé) pour ne pas
      // afficher le JSON brut le temps d'un chunk de streaming.
      // Phase A.12.4 : extrait aussi les blocs de questions à choix
      // <<<CHOICES>>>{json}<<<END>>> (boutons cliquables + champ libre).
      const choicesBlocks = [];
      const toolCallBlocks = [];
      const preStaged = text
        .replace(/<<<CHOICES>>>([\s\S]*?)<<<END>>>/g, (_m, json) => {
          const i = choicesBlocks.length;
          choicesBlocks.push(json);
          return `\n\nZZCHOICESPLACEHOLDER${i}ZZ\n\n`;
        })
        .replace(/<<<CHOICES>>>(?:(?!<<<END>>>)[\s\S])*$/, "")
        .replace(/<<<TOOLCALL>>>([\s\S]*?)<<<TOOLEND>>>/g, (_m, json) => {
          const i = toolCallBlocks.length;
          toolCallBlocks.push(json);
          return `\n\nZZTOOLCALLPLACEHOLDER${i}ZZ\n\n`;
        })
        .replace(/<<<TOOLCALL>>>(?:(?!<<<TOOLEND>>>)[\s\S])*$/, "");
      const cahierBlocks = [];
      // Phase A.10.28 : récupère les titres émis hors balise (tic Gemini)
      // avant l'extraction, puis on extrait les blocs normalement.
      const stagedCahier = _hoistCahierTitles(preStaged).replace(
        // Phase A.12.3 : tolérance : Gemini émet parfois `<<<CAHIER …">`
        // (1 seul `>`, comme une balise XML) au lieu de `">>>`. On accepte
        // 1 à 3 `>` pour ne pas casser le rendu de la carte cahier.
        /<<<CAHIER([^>]*)>{1,3}([\s\S]*?)<<<END>>>/g,
        (_m, attrs, body) => {
          const i = cahierBlocks.length;
          cahierBlocks.push({ attrs, body });
          return `\n\nZZCAHIERPLACEHOLDER${i}ZZ\n\n`;
        }
      );
      // Phase A.10.28 : protège le LaTeX (`$…$`, `$$…$$`) de markdown-it pour
      // qu'un `_indice_` interne ne soit pas mangé en `<em>`. Réinjecté brut
      // après le rendu, KaTeX le traite ensuite sur le DOM.
      const { staged, spans: mathSpans } = _protectMathSpans(stagedCahier);
      // Phase A.10.16 : collapse les `\n` cosmétiques que markdown-it
      // insère entre block tags. Voir commentaire historique pour le `why`.
      let html = md.render(staged).replace(/(<br\s*\/?>|>)\s*\n+\s*/g, "$1");
      html = _restoreMathSpans(html, mathSpans);
      // Phase A.10.19 : réintègre les cards cahier. Le placeholder a été
      // wrappé dans `<p>…</p>` par markdown-it (block isolé), on remplace
      // le paragraphe entier par le HTML de la card. Tolère whitespace
      // interne (markdown-it peut insérer un `\n` avant `</p>` qui survit
      // au post-process A.10.16 si pas précédé directement de `>`/`<br>`).
      html = html.replace(
        /<p>\s*ZZCAHIERPLACEHOLDER(\d+)ZZ\s*<\/p>/g,
        (_m, i) => _renderCahierBlock(cahierBlocks[parseInt(i, 10)])
      );
      // Phase A.10.19 hotfix 3 : fallback : si markdown-it a wrappé le
      // placeholder différemment (par ex. dans un `<br>` continu si
      // breaks:true le fait, ou ailleurs), on remplace aussi les
      // occurrences brutes restantes du sentinel pour éviter qu'il
      // affiche en clair à l'utilisateur.
      html = html.replace(
        /ZZCAHIERPLACEHOLDER(\d+)ZZ/g,
        (_m, i) => _renderCahierBlock(cahierBlocks[parseInt(i, 10)])
      );
      // Phase A.12 : réintègre les puces d'appels d'outils (Read/Grep/Glob).
      html = html.replace(
        /<p>\s*ZZTOOLCALLPLACEHOLDER(\d+)ZZ\s*<\/p>/g,
        (_m, i) => _renderToolCallChip(toolCallBlocks[parseInt(i, 10)])
      );
      html = html.replace(
        /ZZTOOLCALLPLACEHOLDER(\d+)ZZ/g,
        (_m, i) => _renderToolCallChip(toolCallBlocks[parseInt(i, 10)])
      );
      // Phase A.12.4 : réintègre les blocs de questions à choix.
      html = html.replace(
        /<p>\s*ZZCHOICESPLACEHOLDER(\d+)ZZ\s*<\/p>/g,
        (_m, i) => _renderChoicesBlock(choicesBlocks[parseInt(i, 10)])
      );
      html = html.replace(
        /ZZCHOICESPLACEHOLDER(\d+)ZZ/g,
        (_m, i) => _renderChoicesBlock(choicesBlocks[parseInt(i, 10)])
      );
      return html;
    } catch (e) {
      console.warn("markdown-it render error:", e);
    }
  }
  // Fallback minimaliste si markdown-it pas (encore) chargé. Garde un
  // rendu lisible sans crash.
  return `<p>${escapeHtml(text)}</p>`;
}

// Phase A.10.19 : rendu d'une card « cahier » de Découverte/Colle. Le tuteur
// émet `<<<CAHIER titre="...">>>...<<<END>>>` aux moments « notez ceci sur
// votre cahier ». Le contenu interne est du markdown + KaTeX + 4 stylos
// (bleu/rouge/vert/noir) + 4 surligneurs (jaune/vert/rose/violet) avec
// sémantique pédagogique fixée (cf. README §6.bis).
function _renderCahierBlock({ attrs, body }) {
  const titreMatch = (attrs || "").match(/titre\s*=\s*"([^"]*)"/i);
  const titre = titreMatch ? titreMatch[1].trim() : "";
  const md = _getMarkdownIt();
  let inner = (body || "").trim();
  // Phase A.10.32 : referme les `$` inline que le tuteur a oublié de
  // fermer. Observé en session : `$(\arccos u)' = {rouge}-\frac{…}{…}{/rouge}`
  // SANS `$` final. Conséquences en chaîne : `_protectMathSpans` exige les
  // deux `$` → la balise `{rouge}` n'est pas nettoyée → la passe STYLOS la
  // convertit en `<span>`, scindant la formule en deux nœuds texte → KaTeX
  // ne peut plus apparier les `$` (formule éclatée, `$` littéral affiché).
  // On referme donc, ligne par ligne, tout `$` inline impair, mais
  // seulement si le segment resté ouvert ressemble à du LaTeX (`\`, `{`,
  // `}`), jamais un `$` monétaire isolé.
  inner = inner
    .split("\n")
    .map((line) => {
      const dollars = (line.match(/\$/g) || []).length;
      if (dollars % 2 === 0) return line;
      const tail = line.slice(line.lastIndexOf("$") + 1);
      return /[\\{}]/.test(tail) ? `${line.replace(/\s+$/, "")}$` : line;
    })
    .join("\n");
  // Render le markdown interne en passant par markdown-it (héritage de
  // toutes les améliorations A.10.16+). Les balises {couleur} et {hl-X}
  // ne sont pas escapeHtml-ées (chars `{`, `}` ne sont pas spéciaux) ;
  // elles survivent au render et sont substituées ici sur la sortie HTML.
  // Phase A.10.28 : même protection LaTeX que renderMarkdown : un `$…$`
  // contenant un `_indice_` serait sinon corrompu en `<em>` dans la carte.
  const { staged: innerStaged, spans: innerMath } = _protectMathSpans(inner);
  let innerHtml = md
    ? _restoreMathSpans(
        md.render(innerStaged).replace(/(<br\s*\/?>|>)\s*\n+\s*/g, "$1"),
        innerMath,
      )
    : `<p>${escapeHtml(inner)}</p>`;
  // Phase A.10.20 : sur un cahier papier, le **gras**, l'_italique_ et
  // le `code inline` ne se transcrivent pas. Seuls couleurs + surligneurs
  // + lignes de texte ont du sens. On unwrap donc `<strong>`, `<em>`,
  // `<code>` inline pour ne laisser que le texte brut (la couleur reste
  // appliquée via les spans `cahier-c-*`). Les blocs `<pre>` (multi-ligne)
  // sont GARDÉS car un code à recopier sur cahier reste structuré.
  innerHtml = innerHtml
    .replace(/<strong>/g, "")
    .replace(/<\/strong>/g, "")
    .replace(/<em>/g, "")
    .replace(/<\/em>/g, "");
  // Phase A.10.20 → A.10.26 : `<code>` inline : auto-coloriage sémantique
  // intelligent. User : « tu penses que tuteur sera assez intelligent pour
  // choisir les bonnes couleurs ? je ne veux pas du scénario pas intelligible »
  // → on n'attend PAS de discipline du tuteur, on détecte à la volée :
  //
  //   - 🟢 Vert (= valeur / exemple) : si le contenu contient des `"..."`,
  //     `[...]`, `(...)`, `{...}`, OU si purement numérique. Ex : `"ATGC"`,
  //     `[A, T, G, C]`, `(us, vs)`, `42`.
  //   - 🔴 Rouge (= nom / concept) : tout le reste par défaut. Ex :
  //     `charToBase`, `BinTree`, `Maybe`, `List Base`, `String`.
  //
  // Le tuteur peut override avec `{vert}Just A{/vert}` ou `{rouge}foo{/rouge}`
  // pour les cas ambigus.
  innerHtml = innerHtml.replace(
    /<code>([\s\S]*?)<\/code>/g,
    (_m, content) => {
      const trimmed = content.trim();
      const isValue =
        /^[-+]?\d+(?:\.\d+)?$/.test(trimmed) ||           // nombre pur
        /["']/.test(trimmed) ||                            // contient guillemets
        /[\[\]{}]/.test(trimmed) ||                        // contient brackets
        /^\([^)]*\)$/.test(trimmed);                       // tuple (...)
      const cls = isValue ? "cahier-code-inline-value" : "cahier-code-inline";
      return `<span class="${cls}">${content}</span>`;
    },
  );
  // Phase A.10.20 : code blocks fenced en vert (= exemple écrit) avec
  // commentaires en rouge (= warning/insight). Détection patterns
  // multi-langages : `-- ...` Idris/Haskell, `# ...` Python/Shell,
  // `// ...` C/Java/JS. Le code lui-même hérite de `.cahier-body pre`
  // qui force la couleur verte (CSS). On wrap juste les lignes de
  // commentaire dans un span `.cahier-code-comment` rouge.
  innerHtml = innerHtml.replace(
    /(<pre[^>]*>[\s\S]*?<code[^>]*>)([\s\S]*?)(<\/code>[\s\S]*?<\/pre>)/g,
    (_m, openPart, codeContent, closePart) => {
      const lines = codeContent.split("\n");
      const colored = lines.map((line) => {
        if (/^\s*(--|#|\/\/)/.test(line)) {
          return `<span class="cahier-code-comment">${line}</span>`;
        }
        return line;
      }).join("\n");
      return openPart + colored + closePart;
    },
  );
  // 4 stylos, match non-greedy, multi-ligne via [\s\S]*?
  const STYLOS = ["bleu", "rouge", "vert", "noir"];
  for (const c of STYLOS) {
    const re = new RegExp(`\\{${c}\\}([\\s\\S]*?)\\{\\/${c}\\}`, "gi");
    innerHtml = innerHtml.replace(re, `<span class="cahier-c-${c}">$1</span>`);
  }
  // 4 surligneurs (jaune, vert, rose, violet), préfixe `hl-` pour
  // distinguer du stylo vert (qui partagerait sinon la même balise).
  const HIGHLIGHTS = ["jaune", "vert", "rose", "violet"];
  for (const h of HIGHLIGHTS) {
    const re = new RegExp(`\\{hl-${h}\\}([\\s\\S]*?)\\{\\/hl-${h}\\}`, "gi");
    innerHtml = innerHtml.replace(re, `<mark class="cahier-hl-${h}">$1</mark>`);
  }
  // Raccourci ==texte== → surligneur jaune par défaut (extension CommonMark
  // non-native ; le tuteur peut écrire `==important==` au lieu de
  // `{hl-jaune}important{/hl-jaune}` pour le cas le plus fréquent).
  innerHtml = innerHtml.replace(
    /==([^=\n]+)==/g,
    '<mark class="cahier-hl-jaune">$1</mark>'
  );
  // Phase A.10.31 : nettoyage des balises couleur ORPHELINES : si le tuteur
  // oublie de fermer un `{hl-jaune}` (ou ouvre/ferme en désordre), les passes
  // ci-dessus ne l'ont pas convertie en `<span>`/`<mark>` → on retire le
  // résidu pour qu'il ne s'affiche pas en clair (`{hl-jaune}` littéral
  // observé en session). Les balises bien appariées sont déjà consommées.
  innerHtml = innerHtml.replace(_CAHIER_TAG_RE, "");
  // Phase A.10.30 : sous-titres de carte en surligneur vert. Le surligneur
  // vert (`hl-vert`) ne servait à rien (doctrine historique : « titre de
  // fiche root », jamais émis). On le réaffecte aux SOUS-TITRES du corps,
  // détectés automatiquement (le tuteur n'a rien à baliser) :
  //  - lignes-label « Méthode : … », « Définition : … », « Théorème : … »…
  //  - titres markdown `##` / `###` (rendus `<hN>` par markdown-it).
  const _SOUS_TITRE_LABELS =
    "Méthode|Définition|Théorème|Propriété|Proposition|Lemme|Corollaire|" +
    "Règle|Notation|Rappel|Remarque|Astuce|Exemple|Démonstration|Preuve";
  innerHtml = innerHtml.replace(
    new RegExp(`<p>(\\s*(?:${_SOUS_TITRE_LABELS})s?\\s*:[\\s\\S]*?)</p>`, "gi"),
    '<p><mark class="cahier-hl-vert">$1</mark></p>',
  );
  innerHtml = innerHtml.replace(
    /<(h[1-6])((?:\s[^>]*)?)>([\s\S]*?)<\/\1>/gi,
    '<$1$2><mark class="cahier-hl-vert">$3</mark></$1>',
  );
  // Phase A.10.28 : le titre peut contenir du markdown résiduel que Gemini
  // glisse parfois (`*italique*`, `**gras**`, `` `code` ``). Cf. doctrine
  // A.10.20 : gras / italique n'ont pas de sens sur une feuille de cahier :
  // on strip les marqueurs, le texte reste. Le `$…$` est conservé tel quel :
  // KaTeX auto-render (renderMathIn) le rend, car il walke tout le bubble.
  // Phase A.12.6 : le titre de la carte = le titre de la fiche → TOUJOURS
  // violet. Avant (A.10.30), il passait au vert quand non numéroté ; mais en
  // pratique les titres de carte ne sont JAMAIS numérotés → le violet ne
  // servait jamais et le titre se confondait avec les sous-titres ## / ###
  // (verts). Désormais : violet = titre de carte, vert = sous-titres. Une
  // hiérarchie visuelle nette, et les deux surligneurs sont enfin utilisés.
  const titreClean = titre.replace(/\*+/g, "").replace(/`/g, "");
  const titreHtml = titre
    ? `<div class="cahier-titre">${escapeHtml(titreClean)}</div>`
    : "";
  return (
    `<div class="cahier-card">${titreHtml}` +
    `<div class="cahier-body">${innerHtml}</div></div>`
  );
}

// ============================================================ KaTeX render (Phase A.7.2 v4)
// On déclenche le rendu des formules LaTeX uniquement à la fin du stream
// (event `done`/`end`) pour éviter les flicker sur les `$\frac{` partiels
// qui ne sont pas encore fermés. KaTeX est chargé via CDN (cf. index.html).

// ============================================================ Page refs cliquables (Corrigé)
// Quand le tuteur écrit « page 3 du corrigé » ou « cf. page 5 du script »,
// on transforme la mention en lien cliquable qui ouvre l'onglet
// « Corrigés & script » et saute au bon document/page.
//
// Patterns couverts (case-insensitive) :
//   - page 3 du corrigé / pages 3-4 du corrigé (1ʳᵉ page seule)
//   - page 5 du script (imprimable)
//   - p. 7 du corrigé / p.7 du script
//   - à la page 2 du concat / de la correction / etc.

function linkifyPageRefs(rootEl) {
  if (!rootEl) return;
  if (typeof correctionsList === "undefined" || !correctionsList.length) return;
  // Phase Z.8.4 : regex étendue pour capturer optionnellement « de
  // l'exercice N » qui suit le kind. Permet de cibler le bon corrigé
  // quand il y en a plusieurs (1 par exo). Groupes :
  //   1: numéro de page
  //   2: kind (corrigé/script/énoncé/...)
  //   3: numéro d'exo (optionnel, ex "3" ou "3.5")
  const re = /\b(?:à\s+la\s+)?(?:p\.?|page)\s*(\d{1,3})\s+(?:du|de\s+l['’])\s*(corrig[ée]|script(?:\s+imprimable)?|correction|concat|énonc[ée]|enonc[ée])(?:\s+(?:de\s+)?(?:l['’])?(?:exercice|exo|ex)\.?\s*(\d+(?:\.\d+)?))?/giu;
  // Walk text nodes, éviter de toucher au HTML déjà rendu (KaTeX, code, etc.)
  const walker = document.createTreeWalker(rootEl, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const p = node.parentElement;
      if (!p) return NodeFilter.FILTER_REJECT;
      const tag = (p.tagName || "").toUpperCase();
      if (tag === "CODE" || tag === "PRE") return NodeFilter.FILTER_REJECT;
      if (p.closest && p.closest(".katex")) return NodeFilter.FILTER_REJECT;
      if (p.closest && p.closest(".corrige-pageref")) return NodeFilter.FILTER_REJECT;
      return re.test(node.nodeValue || "")
        ? NodeFilter.FILTER_ACCEPT
        : NodeFilter.FILTER_SKIP;
    },
  });
  const targets = [];
  let n;
  while ((n = walker.nextNode())) targets.push(n);
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
      const exoCaptured = m[3] || null;  // Phase Z.8.4
      let kind, kindHumanFr;
      if (kindRaw.startsWith("script")) {
        kind = "script"; kindHumanFr = "script imprimable";
      } else if (kindRaw.startsWith("énonc") || kindRaw.startsWith("enonc")) {
        kind = "enonce"; kindHumanFr = "énoncé";
      } else {
        kind = "correction"; kindHumanFr = "corrigé";
      }
      const a = document.createElement("a");
      a.href = "#";
      a.className = "corrige-pageref";
      a.dataset.page = String(pageN);
      a.dataset.kind = kind;
      if (exoCaptured) a.dataset.exo = exoCaptured;
      a.textContent = m[0];
      a.title = exoCaptured
        ? `Sauter à la page ${pageN} du ${kindHumanFr} de l'exercice ${exoCaptured}`
        : `Sauter à la page ${pageN} du ${kindHumanFr}`;
      a.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        jumpToCorrigePage(pageN, kind, exoCaptured ? { exo: exoCaptured } : {});
      });
      frag.appendChild(a);
      lastIdx = m.index + m[0].length;
    }
    const tail = text.slice(lastIdx);
    if (tail) frag.appendChild(document.createTextNode(tail));
    node.parentNode.replaceChild(frag, node);
  }
}

// Phase Z.8.4 : résolution d'index dans correctionsList avec ciblage
// optionnel par exo (string, ex "3") en plus du kind. Utilisé par :
//   - linkifyPageRefs (refs « page X du corrigé de l'ex 3 ») via regex étendue
//   - SHOW_DOC handler (payload du tuteur peut contenir `exo`)
//   - jumpToCorrigePage (navigation programmatique)
// Si `exoStr` non null et qu'un doc match (kind + exo), retourne son idx.
// Sinon fallback sur le 1ᵉʳ doc du kind. Si rien matche, retourne -1.
function _findDocIdx(kind, exoStr) {
  if (!correctionsList || !correctionsList.length) return -1;
  if (exoStr != null) {
    const exact = correctionsList.findIndex(
      c => (c.kind || "") === kind && String(c.exo || "") === String(exoStr),
    );
    if (exact >= 0) return exact;
    // Fallback : si l'exo demandé n'existe pas pour ce kind, on
    // prend le 1ᵉʳ du kind (avec un warning) plutôt que rater.
    console.warn(
      "_findDocIdx: pas de doc kind=%s exo=%s, fallback 1er du kind",
      kind, exoStr,
    );
  }
  return correctionsList.findIndex(c => (c.kind || "") === kind);
}

function jumpToCorrigePage(pageN, kind, opts = {}) {
  if (!correctionsList || !correctionsList.length) return;
  // Phase Z.8.4 : opts.idx prend la priorité (résolu par caller via
  // _findDocIdx si exo connu). opts.exo en fallback. Sinon, 1er du kind.
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
  // Active l'onglet « Corrigés & script » avant de sauter.
  const tab = document.querySelector('#sidebar-tabs .sb-tab[data-tab="corrige"]');
  if (tab && !tab.classList.contains("active")) tab.click();
  showCorrige(targetIdx, safePage - 1);
}

function renderMathIn(element) {
  if (!element) return;
  if (typeof renderMathInElement !== "function") {
    return;  // CDN pas encore chargée, skip silencieux
  }
  try {
    renderMathInElement(element, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$",  right: "$",  display: false },
        { left: "\\(", right: "\\)", display: false },
        { left: "\\[", right: "\\]", display: true },
      ],
      throwOnError: false,
      strict: "ignore",
    });
  } catch (err) {
    console.warn("KaTeX render a échoué :", err);
  }
}

// ============================================================ Toolbar de ton (Phase A.7.2 v4)
// Boutons sous chaque réponse Claude pour demander une reformulation
// avec un ton/format différent (sans modifier le prompt système). Chaque
// click envoie une meta-instruction à Claude qui re-stream une nouvelle
// réponse alignée sur la demande.

const TONE_PRESETS = [
  { emoji: "📝", label: "Plus concis",
    instr: "Reformule la dernière réponse en plus concis : 1-2 phrases max, garde l'essentiel." },
  { emoji: "➕", label: "Plus développé",
    instr: "Développe la dernière réponse : ajoute le contexte, les exemples, les nuances qui manquaient." },
  { emoji: "📖", label: "Avec exemple",
    instr: "Reprends la dernière réponse avec un exemple concret qui illustre le point." },
  { emoji: "🎯", label: "Plus simple",
    instr: "Reformule la dernière réponse de manière plus accessible, comme à quelqu'un qui découvre le sujet." },
  { emoji: "🔬", label: "Plus rigoureux",
    instr: "Reformule la dernière réponse de manière plus rigoureuse, avec les hypothèses et notations précises." },
  { emoji: "🔄", label: "Reformule",
    instr: "Reformule la dernière réponse autrement, en gardant le même niveau de détail." },
];

function appendToneToolbar(parentTurn) {
  const toolbar = document.createElement("div");
  toolbar.className = "tone-toolbar";
  // Phase Z.9.7 : les 6 reformulations sont groupées dans un popover
  // « 🎛 Modifier ▾ » (option 2 user-validée) pour épurer la barre.
  // Les 4 boutons de recherche (🔍/📚/🎬/🌐) restent en accès direct.
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
    a.addEventListener("click", async (e) => {
      e.stopPropagation();
      popover.hidden = true;
      // Désactive tous les boutons de la toolbar pour éviter double-click.
      // Phase v15.7.24 : re-enable après que sendMetaInstruction return
      // (= dès que le stream est lancé). Avant ce fix, les boutons sous
      // CETTE bulle restaient grisés à vie après une reformulation, alors
      // qu'on voulait bien pouvoir cliquer 🔍 Exo voisin / 🎬 Vidéo / etc.
      // après coup. Les nouvelles bulles ont leur propre toolbar fonc-
      // tionnelle (créée au finalizeClaudeTurn), c'est juste celle de la
      // bulle d'origine qui restait coincée.
      toolbar.querySelectorAll("button").forEach(b => b.disabled = true);
      try {
        await sendMetaInstruction(preset.instr, preset.label);
      } finally {
        toolbar.querySelectorAll("button").forEach(b => b.disabled = false);
      }
    });
    popover.appendChild(a);
  }
  modifyBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (popover.hidden) {
      // Ferme les autres popovers ouverts dans la page
      document.querySelectorAll(".tone-modify-popover:not([hidden])").forEach(p => {
        if (p !== popover) p.hidden = true;
      });
      popover.hidden = false;
      // Phase Z.9.8 : auto-flip drop-up ↔ drop-down selon l'espace dispo.
      // Le défaut est drop-up (popover au-dessus du bouton). Si la
      // bulle Compagnon est en haut du viewport (premier message), le
      // popover sortirait par le haut → on bascule en drop-down.
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
  // Phase Z.8.6 → A.10.23 → A.10.24 : boutons contextuels : prend la
  // question/réponse du tuteur affichée au-dessus comme description du
  // blocage et lance des recherches dans bulles isolées non vues par le
  // tuteur. Visible en colle, découverte ET guidé. (Workspace exclu :
  // pas de contexte COURS.) Raisonnement initial « guidé exclu car le
  // tuteur a accès FS » est faux pour 🎬 Vidéo / 🌐 Internet (le tuteur
  // n'a pas de tools web/youtube), et 📚 Cours reste utile pour bypass
  // le tuteur. User 2026-05-15 : « dans guidé y'a aussi les boutons
  // supplémentaires ? » → étendu à guidé.
  if (activeMode === "colle" || activeMode === "découverte" || activeMode === "guidé") {
    // Phase A.10.23 : fusion 🔍 Exo voisin + 📚 Passage CM en un seul
    // bouton « 📚 Cours » (1 mot) qui lance les 2 recherches en parallèle
    // dans tes cours : un exo voisin pour t'entraîner + le passage CM
    // qui définit le concept. User : « rassembler la logique en un pour
    // trouver à la fin les cm et les exo, libellé en 1 mot ».
    const coursBtn = document.createElement("button");
    coursBtn.className = "tone-btn tone-btn-cours";
    coursBtn.title = "Cherche dans tes cours : exo voisin pour t'entraîner + passage CM qui définit le concept (2 bulles séparées dans le dialogue)";
    coursBtn.textContent = "📚 Cours";
    coursBtn.addEventListener("click", () => {
      coursBtn.disabled = true;
      const claudeText = (parentTurn.dataset.rawText || parentTurn.textContent || "").trim();
      const lastStudent = _getLastStudentTextBefore(parentTurn);
      const desc = _buildContextualExoDescription(claudeText, lastStudent);
      // Lance les 2 en parallèle, ré-active dès que les 2 sont done.
      Promise.allSettled([
        performFindSimilarExo({ description: desc }),
        performFindCmPassage(desc),
      ]).finally(() => { coursBtn.disabled = false; });
    });
    toolbar.appendChild(coursBtn);
    // Phase Z.9 : 🎬 contextuel YouTube
    const ytBtn = document.createElement("button");
    ytBtn.className = "tone-btn tone-btn-yt";
    ytBtn.title = "Cherche une vidéo YouTube qui explique ce concept (chaînes éducatives FR)";
    ytBtn.textContent = "🎬 Vidéo";
    ytBtn.addEventListener("click", () => {
      ytBtn.disabled = true;
      const claudeText = (parentTurn.dataset.rawText || parentTurn.textContent || "").trim();
      const lastStudent = _getLastStudentTextBefore(parentTurn);
      const desc = _buildContextualExoDescription(claudeText, lastStudent);
      performFindYoutube(desc).finally(() => { ytBtn.disabled = false; });
    });
    toolbar.appendChild(ytBtn);
    // Phase Z.9.6 : 🌐 contextuel recherche internet
    const webBtn = document.createElement("button");
    webBtn.className = "tone-btn tone-btn-web";
    webBtn.title = "Cherche des ressources internet sur ce concept (sites éducatifs FR)";
    webBtn.textContent = "🌐 Internet";
    webBtn.addEventListener("click", () => {
      webBtn.disabled = true;
      const claudeText = (parentTurn.dataset.rawText || parentTurn.textContent || "").trim();
      const lastStudent = _getLastStudentTextBefore(parentTurn);
      const desc = _buildContextualExoDescription(claudeText, lastStudent);
      performWebSearchExo(desc).finally(() => { webBtn.disabled = false; });
    });
    toolbar.appendChild(webBtn);
  }
  parentTurn.appendChild(toolbar);
}

// Phase Z.8.6 : récupère le texte du dernier message student rendu
// AVANT la bulle claude `claudeTurn` passée. Utilisé pour enrichir la
// description envoyée à /api/find_similar_exo : la question du tuteur
// + ce que l'étudiant venait de dire = contexte plein du blocage.
function _getLastStudentTextBefore(claudeTurn) {
  if (!claudeTurn) return "";
  let prev = claudeTurn.previousElementSibling;
  // Skip les meta-chips, markers, autres bulles non-student
  while (prev) {
    if (prev.classList && prev.classList.contains("turn") && prev.classList.contains("student") && !prev.classList.contains("marker")) {
      return (prev.dataset.rawText || prev.textContent || "").trim();
    }
    prev = prev.previousElementSibling;
  }
  return "";
}

// Phase v15.7.20 : affiche le bloc OCR Gemini Flash sous la bulle
// student qui contenait la photo. Collapsible <details> pour ne pas
// encombrer le fil par défaut. Le user peut déplier pour vérifier que
// l'OCR Gemini correspond à ce qu'il a écrit, ou le contester si
// erroné. Markdown rendu (tableau, équations LaTeX).
function _appendOcrCollapsibleBlock(turnContainer, blk) {
  if (!turnContainer || !blk || !blk.ocr_markdown) return;
  const wrap = document.createElement("details");
  wrap.className = "ocr-collapsible";
  // Compact par défaut, ouvrable au clic. Si warnings ou completeness
  // < 80%, on l'ouvre par défaut pour attirer l'œil.
  const completeness = blk.completeness_pct;
  const warnings = blk.warnings || [];
  const shouldExpand = (
    warnings.length > 0
    || (typeof completeness === "number" && completeness < 80)
  );
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
  // Render Markdown (qui supporte les tableaux Markdown + LaTeX inline).
  body.innerHTML = renderMarkdown(blk.ocr_markdown);
  // Phase v15.7.20 : KaTeX pour les équations dans l'OCR (ex: $f(x) = x^2$).
  try { renderMathIn(body); } catch (_) {}
  wrap.appendChild(body);

  const hint = document.createElement("div");
  hint.className = "ocr-hint";
  hint.textContent = "Si cet OCR ne correspond pas à ce que tu as écrit, signale-le au Compagnon dans ton prochain message.";
  wrap.appendChild(hint);

  turnContainer.appendChild(wrap);
}


// Phase v15.7.12 : retire les markdowns d'images et les mentions de
// pièces jointes du texte d'une bulle. Sans ça, le `dataset.rawText`
// d'une bulle student qui contient une photo polluait la query passée
// aux recherches YouTube/Web/Exo voisin/CM (champs « Édite la query »
// se retrouvait pré-rempli avec `![photo.jpg](EN1/CC/.../photo.jpg)`
// au lieu du vrai contexte de la question).
function _stripAttachmentMarkdown(text) {
  if (!text) return "";
  return text
    // Markdown image : ![alt](url)
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    // Mention texte de pièce jointe injectée par le backend pour les non-images
    .replace(/\[Pièce jointe\s*:[^\]]*\]/g, "")
    // Espaces multiples + retours à la ligne en cascade laissés par le strip
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]+\n/g, "\n")
    .trim();
}

function _buildContextualExoDescription(claudeText, studentText) {
  // Borne pour ne pas envoyer un dump de plusieurs k tokens au backend.
  // 800 chars suffisent largement pour planter le contexte d'un blocage.
  const truncate = (s, n) => (s && s.length > n ? s.slice(0, n).trim() + "…" : (s || "").trim());
  // Phase v15.7.12 : nettoyage des markdowns d'images / pièces jointes
  // AVANT troncature. Sinon les premiers 800 chars d'une bulle qui
  // commence par une grosse photo seraient juste le markdown image.
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

// Phase Z.9.8 : positionne le popover au-dessus (drop-up) ou en
// dessous (drop-down) du bouton selon l'espace disponible. Évite
// que le popover sorte du viewport quand la bulle est en haut.
function _positionToneModifyPopover(btn, pop) {
  pop.classList.remove("drop-down");
  // offsetHeight n'est calculable qu'une fois rendu (hidden=false avant l'appel).
  const popHeight = pop.offsetHeight || 280;  // fallback estimation
  const btnRect = btn.getBoundingClientRect();
  // Si l'espace au-dessus du bouton est insuffisant pour le popover
  // + une marge de sécurité, on bascule en drop-down.
  if (btnRect.top < popHeight + 10) {
    pop.classList.add("drop-down");
  }
}

// Phase Z.9.7 : handler global qui ferme les popovers « 🎛 Modifier »
// quand on clique en dehors de leur wrap. Auto-removed quand plus
// aucun popover n'est ouvert (évite les listeners zombies).
function _onClickOutsideToneModify(ev) {
  let stillOpen = false;
  document.querySelectorAll(".tone-modify-popover:not([hidden])").forEach(p => {
    const wrap = p.parentElement;  // .tone-modify-wrap
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
  // Affiche un chip discret « 🎛️ Plus concis » au lieu d'une bulle student
  // pleine, pour ne pas polluer le dialogue.
  const chip = document.createElement("div");
  chip.className = "meta-chip";
  chip.textContent = `🎛️ ${label}`;
  dialogue.appendChild(chip);
  dialogue.scrollTop = dialogue.scrollHeight;
  try {
    const reading_state = (typeof getReadingStateForSend === "function")
      ? getReadingStateForSend() : null;
    const r = await fetch("/api/send_message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: instr, reading_state }),
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

// ============================================================ Quota poll

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
    const resetSpan = resetTxt
      ? `<span class="quota-reset" title="Réinit le ${formatResetAbsolute(resetIso)}">↻ ${resetTxt}</span>`
      : "";
    return `<div class="quota-row">` +
      `<div class="quota-row-head">${label} ${resetSpan}</div>` +
      `<span class="bar ${cls}"><span style="width:${Math.min(pct,100)}%"></span></span>` +
      `<span class="quota-pct">${pct.toFixed(0)} %</span>` +
      `</div>`;
  };
  const proMaxBlock = [
    `<div class="quota-section-title">🤖 Claude Pro Max (CLI subscription)</div>`,
    row("Session 5h", d.session_pct, d.session_resets_at),
    row("Hebdo 7j", d.weekly_pct, d.weekly_resets_at),
    row("Hebdo Sonnet", d.weekly_sonnet_pct, d.weekly_sonnet_resets_at),
    row("Overage", d.extra_pct, null),
  ].join("");
  const enginesBlock = renderEnginesStatus(d.engines);
  return proMaxBlock + enginesBlock;
}

// Phase v15.6.5 : bloc d'état des moteurs alternatifs (DeepSeek, Groq,
// Gemini, API Anthropic). Affiche la balance live pour DeepSeek (depuis
// /user/balance) et juste « clé présente + free tier RPM/RPD » pour les
// autres (pas d'endpoint balance public).
function renderEnginesStatus(engineData) {
  if (!engineData || !engineData.engines) return "";
  const e = engineData.engines;
  const blocks = [];

  // DeepSeek, barre de solde si key + balance
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
      const cls = !ok ? "err" : (total < 0.5 ? "warn" : "");
      const detail = (total != null)
        ? `${total.toFixed(2)} ${cur} restants` +
          ((granted || toppedUp) ? ` (gratuit ${(granted || 0).toFixed(2)} + rechargé ${(toppedUp || 0).toFixed(2)})` : "")
        : "Solde indisponible";
      // Pas de "max" connu à l'avance, on affiche juste le total avec couleur.
      // Barre représentative : pleine si > 1$, vide si 0$.
      const pctVisual = total != null ? Math.min(100, total * 20) : 0;  // 5$ = 100%
      blocks.push(engineRowWithBar("💎", "DeepSeek", detail, pctVisual, cls, ds.billing_url, !ok));
    }
  }

  // Groq, Gemini, API Anthropic, pas de balance, juste tier + limites
  const fixedTierEntries = [
    ["groq_api", e.groq_api, "⚡"],
    ["gemini_api", e.gemini_api, "✨"],
    ["api_anthropic", e.api_anthropic, "🧠"],
  ];
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
  return `<div class="quota-section-title quota-section-engines">🔌 Autres moteurs</div>` +
         blocks.join("");
}

function engineRow(icon, label, statusEmoji, detail, billingUrl) {
  const linkPart = billingUrl
    ? ` · <a href="${billingUrl}" target="_blank" rel="noopener" class="engine-billing-link">⚙</a>`
    : "";
  return `<div class="engine-row">` +
    `<span class="engine-icon">${icon}</span>` +
    `<span class="engine-label">${escapeHtml(label)}</span>` +
    `<span class="engine-status">${statusEmoji}</span>` +
    `<span class="engine-detail">${escapeHtml(detail)}${linkPart}</span>` +
    `</div>`;
}

function engineRowWithBar(icon, label, detail, pct, cls, billingUrl, broken) {
  const linkPart = billingUrl
    ? ` <a href="${billingUrl}" target="_blank" rel="noopener" class="engine-billing-link" title="Recharger / configurer">⚙</a>`
    : "";
  return `<div class="engine-row engine-row-bar">` +
    `<div class="engine-row-head">` +
      `<span class="engine-icon">${icon}</span>` +
      `<span class="engine-label">${escapeHtml(label)}</span>` +
      `<span class="engine-detail">${escapeHtml(detail)}${linkPart}</span>` +
    `</div>` +
    (broken
      ? `<div class="engine-broken-hint">Solde épuisé (clic ⚙ pour recharger)</div>`
      : `<span class="bar ${cls}"><span style="width:${Math.min(pct,100)}%"></span></span>`
    ) +
    `</div>`;
}

function formatResetCountdown(iso) {
  if (!iso) return null;
  const reset = new Date(iso).getTime();
  const now = Date.now();
  let diffSec = Math.round((reset - now) / 1000);
  if (diffSec <= 0) return "imminent";
  const days = Math.floor(diffSec / 86400); diffSec -= days * 86400;
  const hours = Math.floor(diffSec / 3600); diffSec -= hours * 3600;
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
      weekday: "short", day: "2-digit", month: "short",
      hour: "2-digit", minute: "2-digit",
    });
  } catch (_) { return iso; }
}

// Phase Z.8.2 : formatage discret du timestamp d'un message dans la
// barre role. Format adapté à la fraîcheur :
//   - aujourd'hui  → "14:23"
//   - hier         → "Hier 14:23"
//   - cette année  → "9 mai 14:23"
//   - autre année  → "9 mai 2025 14:23"
// Hover (title) : date+heure complète locale.
function formatTurnTimeShort(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    const hhmm = d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    if (sameDay) return hhmm;
    const yest = new Date(now);
    yest.setDate(yest.getDate() - 1);
    if (d.toDateString() === yest.toDateString()) return `Hier ${hhmm}`;
    const sameYear = d.getFullYear() === now.getFullYear();
    const datePart = d.toLocaleDateString("fr-FR", sameYear
      ? { day: "numeric", month: "short" }
      : { day: "numeric", month: "short", year: "numeric" });
    return `${datePart} ${hhmm}`;
  } catch (_) { return ""; }
}

function formatTurnTimeAbsolute(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString("fr-FR", {
      weekday: "long", day: "numeric", month: "long", year: "numeric",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch (_) { return iso; }
}

setInterval(refreshQuota, QUOTA_POLL_MS);
refreshQuota();

// ============================================================ Panneau Connexion mobile
// Affiche les URLs (LAN + Tailscale) pour ouvrir /mobile depuis le téléphone.
// Fetched une fois au boot, pas de polling, les IPs ne changent pas en
// cours de session (sauf changement de WiFi).

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

    // 1) WiFi LAN local (même réseau qu'à la maison)
    if (data.lan_ip) {
      rows.push(makeConnRow("WiFi local (même réseau)",
                            `http://${data.lan_ip}:${port}/`,
                            true));
    } else {
      rows.push(makeConnRow("WiFi local", "non détecté", false));
    }

    // 2) Tailscale tailnet (téléphone, autres machines avec client Tailscale)
    if (data.tailscale_ip) {
      rows.push(makeConnRow("Tailscale tailnet (téléphone, autres machines)",
                            `http://${data.tailscale_ip}:${port}/`,
                            true));
    } else {
      rows.push(makeConnRow("Tailscale tailnet", "non détecté", false));
    }

    // 3) Tailscale serve / Funnel, état live (public / tailnet / off)
    const fState = data.tailscale_funnel_state || "off";
    const fUrl = data.tailscale_funnel_live_url || data.tailscale_funnel || "";
    if (fState === "public") {
      rows.push(makeConnRow(
        "🌐 Tailscale Funnel : exposé sur Internet",
        fUrl || "(URL inconnue)",
        !!fUrl,
      ));
    } else if (fState === "tailnet") {
      rows.push(makeConnRow(
        "🔒 Tailscale serve : privé (tailnet uniquement)",
        fUrl || "(URL inconnue)",
        !!fUrl,
      ));
    } else if (data.tailscale_funnel) {
      // L'URL est dans le JSON mais Tailscale dit off → désync probable
      // (Compagnon vient de redémarrer mais Funnel n'a pas été relancé).
      rows.push(makeConnRow(
        "⚪ Tailscale Funnel : coupé (config présente mais inactive)",
        data.tailscale_funnel,
        false,
      ));
    } else {
      rows.push(makeConnRow(
        "⚪ Tailscale Funnel : non configuré",
        "voir _remote_access/SETUP_TAILSCALE_FUNNEL.md",
        false,
      ));
    }

    // 4) Cloudflare Tunnel (URL publique permanente sur ton domaine)
    if (data.cloudflare_tunnel) {
      rows.push(makeConnRow("Cloudflare Tunnel (public, ton domaine)",
                            data.cloudflare_tunnel,
                            true));
    } else {
      rows.push(makeConnRow(
        "Cloudflare Tunnel (public)",
        "non configuré, voir _remote_access/SETUP_CLOUDFLARE.md",
        false,
      ));
    }

    panel.innerHTML = "";
    // Banner auth (avant les rows) si Basic Auth activé
    if (data.basic_auth_enabled) {
      const banner = document.createElement("div");
      banner.className = "conn-auth-banner";
      banner.textContent =
        "🔐 Auth Basic activée : le navigateur demandera identifiant/mot " +
        "de passe sur les URLs publiques (Tailscale Funnel, Cloudflare Tunnel). " +
        "LAN et tailnet privé restent libres (skip 127.0.0.1/::1).";
      panel.appendChild(banner);
    }
    rows.forEach(rEl => panel.appendChild(rEl));
    // Footer : rappel sur /mobile pour le flow photo téléphone
    const hint = document.createElement("div");
    hint.className = "conn-hint";
    hint.innerHTML =
      "💡 Ajoute <code>/mobile</code> à n'importe quelle URL pour la page " +
      "spéciale photo téléphone (capture rapide qui injecte dans la session " +
      "active).";
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
    urlEl.addEventListener("click", (e) => {
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
    btn.type = "button"; btn.className = "conn-copy";
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
// Refresh périodique pour suivre les changements d'état Funnel quand
// on toggle depuis la GUI Tk (sinon l'utilisateur voit pas le changement
// jusqu'au prochain F5).
setInterval(refreshConnectionInfo, 30_000);

// ============================================================ Auto-advance opt-in (Phase v15)
// Single point de contrôle : bouton « 🤖 Activer auto-nav » dans la
// sidebar du panneau guidé. Au start, par défaut auto-advance est OFF
// (mode manuel le plus prévisible). L'étudiant peut activer à n'importe
// quel moment via ce bouton, qui injecte le message synthétique
// d'activation dans le _history du tuteur.

(function setupAutoAdvanceUI() {
  const remindBtn = document.getElementById("guided-remind-nav-btn");
  if (!remindBtn) return;

  remindBtn.addEventListener("click", async () => {
      remindBtn.disabled = true;
      const wasActivation = remindBtn.textContent.includes("Activer");
      remindBtn.textContent = wasActivation
        ? "⏳ Activation…"
        : "⏳ Rappel envoyé…";
      try {
        const r = await fetch("/api/auto_advance/remind", { method: "POST" });
        if (!r.ok) {
          const d = await r.json().catch(() => ({}));
          alert((wasActivation ? "Activation" : "Rappel") + " échoué : "
                + (d.error || r.status));
          showRemindNavBtnIfActive(!wasActivation);
          remindBtn.disabled = false;
          return;
        }
        remindBtn.textContent = wasActivation ? "✓ Activé" : "✓ Rappelé";
        // Bulle système visible dans la conv pour traçabilité.
        const sysMsg = wasActivation
          ? "🤖 Auto-navigation activée : le tuteur peut désormais faire avancer la slide lui-même via NEXT_SLIDE."
          : "🤖 Rappel auto-nav envoyé au tuteur.";
        appendTurn("system", sysMsg);
        // Après activation, on bascule en mode « auto_advance actif »
        // → label devient « Rappeler nav » au prochain reset.
        setTimeout(() => {
          showRemindNavBtnIfActive(true);  // l'auto-advance est ON désormais
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
  // Affiche le bouton « 🤖 Activer/Rappeler nav » dans le panneau guidé
  // dès qu'une session guidée est active. Le label change selon que
  // auto_advance était déjà coché au démarrage (« Rappeler ») ou pas
  // (« Activer »), dans les deux cas, click = POST /api/auto_advance/
  // remind qui set_meta auto_advance=True + injecte le rappel.
  const remindBtn = document.getElementById("guided-remind-nav-btn");
  if (!remindBtn) return;
  if (activeMode !== "guidé") {
    remindBtn.hidden = true;
    return;
  }
  remindBtn.hidden = false;
  remindBtn.textContent = autoAdvance
    ? "🤖 Rappeler nav au tuteur"
    : "🤖 Activer auto-nav";
  remindBtn.title = autoAdvance
    ? "Réinjecte le rappel auto-advance dans la conv (utile si le tuteur a oublié)."
    : "Active l'auto-advance pour la session courante (le tuteur fera avancer la slide lui-même).";
}

// ============================================================ Onglets sidebar (Phase A.7.2 v11)
// Refonte de la sidebar : grid 4-rows (slide guidée / onglets / contenu
// scrollable / footer terminer). Click sur un onglet → bascule le pane.

(function setupSidebarTabs() {
  const tabs = document.querySelectorAll("#sidebar-tabs .sb-tab");
  const panes = document.querySelectorAll("#sidebar-tab-content .sb-pane");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.tab;
      tabs.forEach(t => t.classList.toggle("active", t === tab));
      panes.forEach(p => p.classList.toggle("active", p.dataset.pane === target));
      // Phase v15.7.23 : refresh notes au switch sur l'onglet
      if (target === "notes" && typeof refreshSavedNotes === "function") {
        refreshSavedNotes();
      }
      // Phase A.9.1 : refresh galerie photos au switch sur l'onglet
      if (target === "photos" && typeof refreshSessionPhotos === "function") {
        refreshSessionPhotos();
      }
      // Phase A.10 : refresh consignes épinglées au switch
      if (target === "stickies" && typeof refreshStickies === "function") {
        refreshStickies();
      }
      // Phase A.10.13c : refresh sommaire dynamique au switch sur Docs
      if (target === "corrige" && typeof refreshDynamicOutline === "function") {
        refreshDynamicOutline();
      }
    });
  });
})();

// ============================================================ Form cascade (selects)
// 5 selects qui cascadent (matiere → type → num → [annee CC] → exo) +
// mode + bouton rescan. Source des options : /api/cours_options qui
// recycle les helpers list_* du cours_resolver (mêmes que la GUI Tk).
//
// Restauration : compagnon.py CLI passe matiere/type/num/exo via query
// params → on les applique au fur et à mesure que chaque cascade
// remplit son select. Si une valeur n'existe plus côté disque (ex :
// l'exo a été supprimé), elle est silencieusement ignorée et le user
// re-sélectionne.

const formMatiere = startForm.querySelector('[name="matiere"]');
const formType = startForm.querySelector('[name="type"]');
const formNum = startForm.querySelector('[name="num"]');
const formAnnee = startForm.querySelector('[name="annee"]');
const formExo = startForm.querySelector('[name="exo"]');
const formRescan = $("#form-rescan");

// Garde-fou anti-récursion lors des cascades programmatiques
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
  // Restaure la valeur précédente si elle existe encore
  if (prev && values.includes(prev)) {
    selectEl.value = prev;
  } else {
    selectEl.value = "";
  }
}

function _disableCascadeBelow(level) {
  // level ∈ {"matiere", "type", "num", "annee", "exo"}, désactive
  // tous les niveaux strictement après celui passé.
  const order = ["matiere", "type", "num", "annee", "exo"];
  const idx = order.indexOf(level);
  if (idx < 0) return;
  const tail = order.slice(idx + 1);
  for (const name of tail) {
    const el = startForm.querySelector(`[name="${name}"]`);
    if (!el) continue;
    el.disabled = true;
    el.innerHTML = `<option value="">${name === "annee" ? "—" : (name === "exo" ? "Exo…" : (name === "num" ? "N°…" : "Type…"))}</option>`;
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
  // Charge les types pour la matière courante. Reset tout en aval.
  cascadeMuted = true;
  try {
    const m = formMatiere.value;
    if (!m) {
      _disableCascadeBelow("matiere");
      return;
    }
    const data = await fetchCoursOptions({ matiere: m });
    if (!data) { _disableCascadeBelow("matiere"); return; }
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
    if (!m || !t) { _disableCascadeBelow("type"); return; }
    const data = await fetchCoursOptions({ matiere: m, type: t });
    if (!data) { _disableCascadeBelow("type"); return; }
    _setOptions(formNum, data.nums || [], "N°…");
    formNum.disabled = !(data.nums || []).length;
    // Annee : visible uniquement pour les CC, et seulement après un num
    formAnnee.hidden = (t !== "CC");
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
    if (!m || !t || !n) { _disableCascadeBelow("num"); return; }
    const data = await fetchCoursOptions({ matiere: m, type: t, num: n });
    if (!data) { _disableCascadeBelow("num"); return; }
    if (t === "CC") {
      _setOptions(formAnnee, data.annees || [], "—");
      formAnnee.hidden = false;
      formAnnee.disabled = !(data.annees || []).length;
      // Si plusieurs annees, on attend le choix utilisateur avant exos.
      // Si une seule, on auto-sélectionne et on poursuit.
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
      // Sinon on bloque exo en attendant l'annee
      formExo.disabled = true;
      formExo.innerHTML = '<option value="">Exo…</option>';
      return;
    }
    // Pas CC : exos directement
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
    const data = await fetchCoursOptions({ matiere: m, type: t, num: n, annee: a });
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

// ============================================================ Source DROIT (Phase S4 : Cartable)
// Sélecteur de source COURS ⇄ DROIT. En DROIT, on masque les combos COURS et
// on alimente trois combos droit (matière slug → type CM/TD → n°) depuis
// /api/droit_options. Pas d'exo ni de millésime. Le submit injecte
// source=droit + matiere/type/num (slug / CM|TD / n) dans le body.
const formSource = startForm.querySelector('[name="source"]');
const formDroitMatiere = startForm.querySelector('[name="droit_matiere"]');
const formDroitType = startForm.querySelector('[name="droit_type"]');
const formDroitNum = startForm.querySelector('[name="droit_num"]');

function isDroitSource() {
  return !!(formSource && formSource.value === "droit");
}

function applySourceMode() {
  const droit = isDroitSource();
  // Combos COURS : masqués + désactivés en droit (sinon `required` bloque le submit
  // et FormData enverrait des champs vides).
  for (const el of [formMatiere, formType, formNum, formAnnee, formExo]) {
    if (!el) continue;
    el.hidden = droit;
    if (droit) el.disabled = true;
  }
  // Combos DROIT : visibles + actifs en droit uniquement.
  for (const el of [formDroitMatiere, formDroitType, formDroitNum]) {
    if (!el) continue;
    el.hidden = !droit;
    el.disabled = !droit;
  }
  // L'ancrage corrigé et les checkboxes « Sans énoncé » / « Sujet libre » n'ont
  // pas de sens en droit (pas de corrigé officiel, contenu Cartable imposé).
  const caEl = startForm.querySelector('[name="corrige_anchor"]');
  if (caEl && droit) { caEl.hidden = true; caEl.disabled = true; }
  const igEl = startForm.querySelector('[name="ignore_enonce"]');
  const igLabel = igEl ? igEl.closest("label") : null;
  if (igLabel) igLabel.hidden = droit;
  const sjEl0 = startForm.querySelector('[name="sujet_libre_mode"]');
  const sjLabel = sjEl0 ? sjEl0.closest("label") : null;
  if (sjLabel) sjLabel.hidden = droit;
  if (droit && sjEl0 && sjEl0.checked) {
    sjEl0.checked = false;
    sjEl0.dispatchEvent(new Event("change", { bubbles: true }));
  }
  // En droit, charge les matières si le combo est encore vide.
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
  if (formDroitType) { formDroitType.disabled = true; formDroitType.innerHTML = '<option value="">Type…</option>'; }
  if (formDroitNum) { formDroitNum.disabled = true; formDroitNum.innerHTML = '<option value="">N°…</option>'; }
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
      if (formDroitType) { formDroitType.disabled = true; formDroitType.innerHTML = '<option value="">Type…</option>'; }
      if (formDroitNum) { formDroitNum.disabled = true; formDroitNum.innerHTML = '<option value="">N°…</option>'; }
      return;
    }
    const data = await fetchDroitOptions({ matiere: m });
    if (!data) return;
    _setOptions(formDroitType, data.types || [], "Type…");
    formDroitType.disabled = !(data.types || []).length;
    if (formDroitNum) { formDroitNum.disabled = true; formDroitNum.innerHTML = '<option value="">N°…</option>'; }
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
      if (formDroitNum) { formDroitNum.disabled = true; formDroitNum.innerHTML = '<option value="">N°…</option>'; }
      return;
    }
    const data = await fetchDroitOptions({ matiere: m, type: t });
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

// Wire change events
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

// Rescan button, reload tout depuis la racine. Conserve les valeurs
// actuelles et tente de les ré-appliquer si elles existent encore.
async function rescanFormOptions() {
  const current = {
    matiere: formMatiere.value,
    type: formType.value,
    num: formNum.value,
    annee: formAnnee.value,
    exo: formExo.value,
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

// Phase A.10.15 : sync les selects du form de démarrage à un contexte
// de session (typiquement celle qu'on vient de reprendre via
// /api/resume_session ou /api/current_session). Évite l'incohérence
// « je suis en AN1 dans la dialogue mais l'entête affiche encore PRG2 »
// signalée par l'user 2026-05-15. Cas spéciaux : sujet libre coche la
// checkbox dédiée + remplit le textarea ; workspace bypass (le folder
// picker est géré côté GUI Tk).
async function syncFormToSession(data) {
  if (!data || !startForm) return;
  // Phase S4 (Cartable) : restaure une session DROIT : bascule la source,
  // pré-remplit les combos droit, applique le mode. Pas de combos COURS.
  if (String(data.source || "").toLowerCase() === "droit") {
    if (formSource) { formSource.value = "droit"; applySourceMode(); }
    await cascadeDroitRoot({
      matiere: String(data.droit_matiere || data.matiere || ""),
      type: String(data.type || "").toUpperCase(),
      num: String(data.num || ""),
    });
    const modeElD = startForm.querySelector('[name="mode"]');
    if (modeElD && data.mode) modeElD.value = data.mode;
    return;
  }
  // Revenu sur une session non-droit : s'assurer que la source est COURS.
  if (formSource && formSource.value !== "cours") {
    formSource.value = "cours";
    applySourceMode();
  }
  const m = String(data.matiere || "").toUpperCase();
  const sjEl = startForm.querySelector('[name="sujet_libre_mode"]');
  if (m === "LIBRE") {
    if (sjEl && !sjEl.checked) {
      sjEl.checked = true;
      sjEl.dispatchEvent(new Event("change", { bubbles: true }));
    }
    const ta = document.querySelector("#start-form-sujet-libre-text");
    if (ta && data.sujet_libre) ta.value = data.sujet_libre;
    return;
  }
  if (m === "WORKSPACE") {
    // Pas de cascade COURS, la GUI Tk gère le folder picker.
    return;
  }
  // Décocher sujet libre si on revient d'une session libre vers une réelle.
  if (sjEl && sjEl.checked) {
    sjEl.checked = false;
    sjEl.dispatchEvent(new Event("change", { bubbles: true }));
  }
  const autoSelect = {
    matiere: m,
    type: String(data.type || "").toUpperCase(),
    num: String(data.num || ""),
    annee: String(data.annee || ""),
    exo: String(data.exo || ""),
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

// Boot : applique query params si présents (compagnon.py CLI)
(async function initFormOptions() {
  const params = new URLSearchParams(window.location.search);
  const auto = {
    matiere: params.get("matiere") || "",
    type: params.get("type") || "",
    num: params.get("num") || "",
    annee: params.get("annee") || "",
    exo: params.get("exo") || "",
  };
  const data = await fetchCoursOptions({});
  if (!data) return;
  _setOptions(formMatiere, data.matieres || [], "Matière…");
  if (auto.matiere && (data.matieres || []).includes(auto.matiere)) {
    formMatiere.value = auto.matiere;
    await cascadeFromMatiere(auto);
  }
  // Phase S4 (Cartable) : source=droit dans l'URL (passée par compagnon.py /
  // GUI Tk). On bascule en mode droit et on pré-remplit les combos droit
  // depuis matiere/type/num. Awaité AVANT l'autostart pour que le submit
  // trouve les valeurs en place.
  const sourceParam = (params.get("source") || "").toLowerCase();
  if (sourceParam === "droit" && formSource) {
    formSource.value = "droit";
    applySourceMode();
    await cascadeDroitRoot({
      matiere: params.get("matiere") || "",
      type: (params.get("type") || "").toUpperCase(),
      num: params.get("num") || "",
    });
  }
  // Mode (input non cascade), applique aussi si présent
  if (params.get("mode")) {
    const modeEl = startForm.querySelector('[name="mode"]');
    if (modeEl) modeEl.value = params.get("mode");
  }
  // Phase v15.7.7 : pré-remplit aussi le select Format colle si fourni
  // par l'URL (compagnon.py CLI / GUI Tk passent --colle-format → query
  // param). Sans ça, lancer en "photos" depuis la GUI Tk laissait le
  // select web sur "mixte" (incohérence visuelle).
  const cfParam = (params.get("colle_format") || "").toLowerCase();
  if (cfParam && ["oral", "photos", "mixte"].includes(cfParam)) {
    const cfEl = startForm.querySelector('[name="colle_format"]');
    if (cfEl) cfEl.value = cfParam;
  }
  // Phase v15.7.30 : idem corrige_anchor depuis l'URL.
  let caParam = (params.get("corrige_anchor") || "").toLowerCase();
  if (["sans_corrigé", "sans_corrige"].includes(caParam)) caParam = "aucun";
  if (caParam && ["strict", "consultatif", "aucun"].includes(caParam)) {
    const caEl = startForm.querySelector('[name="corrige_anchor"]');
    if (caEl) caEl.value = caParam;
  }
  // Phase A.10.13 (2026-05-14), la case 🎲 Sans énoncé est FORCÉE
  // décochée au boot, peu importe ce qui traîne dans l'URL ou dans
  // last_selection. C'est une option ponctuelle (« je veux faire CETTE
  // séance sans énoncé »), pas une préférence persistante. User : « au
  // redémarrage y'a sans énoncé qui se coche automatiquement faut
  // corriger ». Bug racine : update_last_selection(**kwargs) ne
  // supprime pas les clés non passées, donc une valeur True ancienne
  // restait dans le JSON et se propageait via URL → checkbox cochée.
  // Fix radical : ignore complètement la valeur passée, force False.
  {
    const ieEl = startForm.querySelector('[name="ignore_enonce"]');
    if (ieEl) ieEl.checked = false;
  }
  // Phase A.8.3 : sujet libre depuis l'URL. Si présent : auto-coche le mode
  // sujet libre + pré-remplit le textarea + désactive Guidé.
  const sujetLibreParam = params.get("sujet_libre") || "";
  if (sujetLibreParam.trim()) {
    const sjEl = startForm.querySelector('[name="sujet_libre_mode"]');
    if (sjEl) {
      sjEl.checked = true;
    }
    const ta = document.querySelector("#start-form-sujet-libre-text");
    if (ta) ta.value = sujetLibreParam;
    // Phase A.10.13a : params generate_invented_pdf retiré (mode supprimé).
    // Trigger toggle visibility une fois init complète (à la fin de
    // initFormOptions). On le fait ici de manière différée pour laisser
    // le reste du DOM se setup.
    setTimeout(() => _toggleSujetLibreZone(), 50);
  }
  // Phase A.9 : workspace_root depuis l'URL. Si présent, on le stocke dans
  // une variable module-globale qui sera injectée dans le body au submit
  // du form (pas de widget dédié dans le front web, la sélection se fait
  // côté GUI Tk, le front web hérite juste des params via URL).
  const wsRoot = (params.get("workspace_root") || "").trim();
  if (wsRoot) {
    window._pendingWorkspace = {
      workspace_root: wsRoot,
      workspace_focus_subdir: (params.get("workspace_focus_subdir") || "").trim(),
      workspace_excludes: (params.get("workspace_excludes") || "").trim(),
      // Phase A.10.13a : generate_invented_pdf retiré (mode supprimé).
    };
  }
  // Phase v15.7.7 : toggle de visibilité du select Format colle selon le
  // mode courant (cohérent avec la GUI Tk : masqué en guidé puisque le
  // backend ignore le paramètre dans ce mode). Init + listener change.
  // Phase v15.7.30 : même traitement pour le select Ancrage corrigé.
  const modeEl = startForm.querySelector('[name="mode"]');
  const cfEl = startForm.querySelector('[name="colle_format"]');
  const caEl = startForm.querySelector('[name="corrige_anchor"]');
  function _refreshColleFormatSelectVisibility() {
    // Phase A.8.2 : Format visible en colle ET découverte. Masqué en
    // guidé (le tuteur a déjà accès aux PDF via Read/Grep/Glob).
    const m = modeEl ? modeEl.value : "colle";
    const isVisible = m === "colle" || m === "découverte";
    if (cfEl) { cfEl.hidden = !isVisible; cfEl.disabled = !isVisible; }
    if (caEl) { caEl.hidden = !isVisible; caEl.disabled = !isVisible; }
  }
  if (modeEl) modeEl.addEventListener("change", _refreshColleFormatSelectVisibility);
  _refreshColleFormatSelectVisibility();

  // Phase A.8.3 : toggle Sujet libre. Quand coché : montre la zone
  // sujet-libre-zone, désactive les combos COURS, désactive option Guidé.
  const sjEl = startForm.querySelector('[name="sujet_libre_mode"]');
  if (sjEl) {
    sjEl.addEventListener("change", _toggleSujetLibreZone);
    _toggleSujetLibreZone();  // init silencieux
  }

  // Phase v15.7.36.2 : autostart : si l'URL contient `?autostart=1`,
  // submit le form automatiquement après le pré-remplissage des cascades
  // (la GUI Tk passe ce flag pour bypass le clic Lancer côté navigateur).
  // Le param est retiré de l'URL via history.replaceState pour qu'un
  // F5 ne re-déclenche pas l'autostart (un F5 doit re-utiliser
  // /api/current_session pour restore).
  if ((params.get("autostart") || "") === "1") {
    // Retire `autostart` de l'URL pour ne pas re-trigger au F5
    try {
      const cleanUrl = new URL(window.location.href);
      cleanUrl.searchParams.delete("autostart");
      history.replaceState({}, "", cleanUrl.toString());
    } catch (_) { /* IE / vieux Safari : pas critique */ }
    // Submit après un léger délai pour laisser le temps aux cascades
    // (cascadeFromMatiere notamment) de bien remplir les selects.
    // Délai légèrement augmenté pour les matières où le scan IA / scan
    // arbo prennent un peu de temps.
    setTimeout(() => {
      if (typeof restoreActiveSessionIfAny === "function" && activeSession) {
        // Déjà une session active (cas du restore Ctrl+F5 ou bascule) :
        // ne pas re-submit.
        return;
      }
      // Trigger le submit handler du form (qui détecte conflit / lance)
      try {
        startForm.dispatchEvent(new Event("submit", {cancelable: true, bubbles: true}));
      } catch (_) {
        // Fallback (vieux browser) : click sur le bouton submit
        const submitBtn = startForm.querySelector("button[type='submit']");
        if (submitBtn) submitBtn.click();
      }
    }, 350);
  }
})();

// ============================================================ Form toggle warnings (Phase A.10.13)
// Warnings inline qui apparaissent quand l'utilisateur coche une checkbox
// potentiellement déroutante (🎲 Sans énoncé, 💡 Sujet libre). User :
// « si par erreur l'user clique sur sans énoncé qu'un message d'erreur
// apparait pour le contextualiser afin qu'il ne se fasse pas surprendre ».
(function _wireFormToggleWarnings() {
  const wrapper = document.getElementById("form-toggle-warnings");
  const form = document.getElementById("start-form");
  if (!wrapper || !form) return;
  const refreshWrapper = () => {
    const anyShown = wrapper.querySelectorAll(
      ".form-toggle-warning:not([hidden])"
    ).length > 0;
    wrapper.hidden = !anyShown;
  };
  const wireOne = (name) => {
    const cb = form.querySelector(`[name="${name}"]`);
    const warn = wrapper.querySelector(`.form-toggle-warning[data-for="${name}"]`);
    if (!cb || !warn) return;
    const apply = () => {
      warn.hidden = !cb.checked;
      refreshWrapper();
    };
    cb.addEventListener("change", apply);
    apply();  // état initial cohérent au boot (si pré-cochée par URL)
  };
  wireOne("ignore_enonce");
  wireOne("sujet_libre_mode");
})();

// ============================================================ Auto-restore après Ctrl+F5
// Le backend Flask garde la session active in-memory tant que le process
// tourne. Au boot du front, on tente une restauration : si une session
// est active côté backend, on repopule le dialogue avec le transcript et
// on réactive les commandes (sans relancer le 1ʳᵉ stream, la session
// est déjà à jour, le tuteur attend un message).
async function restoreActiveSessionIfAny() {
  try {
    const r = await fetch("/api/current_session");
    if (!r.ok) return;
    const data = await r.json();
    if (!data.active) return;
    activeSession = data.session_id;
    activeMode = data.mode || "colle";
    // Phase v15.7.4 : restaure les chips de format colle.
    applyColleFormatChips(data.colle_format || "mixte");
    // Phase v15.7.30 : restaure les chips d'ancrage corrigé.
    applyCorrigeAnchorChips(data.corrige_anchor || "strict");
    // Phase A.10.15 : sync les selects du form de démarrage au contexte
    // restauré (cas F5 / restart bot).
    try { await syncFormToSession(data); } catch (_) { /* best-effort */ }
    // Phase v15.7.31 : restaure la phase débrief si applicable.
    const phase = data.phase || "active";
    inDebrief = (phase === "debrief");
    const phaseSuffix = inDebrief ? " [🎓 débrief]" : (phase === "closed" ? " [fermée]" : " [restauré]");
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
    // Phase A.9 (correctif) : pas de lock du form ici. Les selects de
    // SOURCE (matière/type/num/exo/année/mode) doivent rester actifs
    // pour permettre à l'user de préparer un futur Lancer (modal de
    // conflit). Seul `corrige_anchor` est inhibé via le no-op de
    // `setCorrigeAnchor` quand activeSession est set.
    if (activeMode === "guidé") {
      const startIdx = Number.isInteger(data.guided_index) ? data.guided_index : 0;
      initGuidedPanel(startIdx);
    }
    showRemindNavBtnIfActive(!!data.auto_advance);
    initCorrectionsPanel();
    // Phase A.8.4 : la carte récap n'est PLUS re-affichée au Ctrl+F5.
    // Bug observé 2026-05-12 session PSI TP_Shannon : la carte se ré-injectait
    // à la date du reload (10:37) au lieu du recap_at original (06:41), sans
    // marqueur de suppression, perdue dans le scroll. Le user accède au
    // récap via l'archive .md (Phase A.8.1) qui contient la section
    // dédiée. Statut « phase débrief » reste visible dans sessionInfo
    // (« [🎓 débrief] »).
  } catch (e) {
    console.warn("restoreActiveSessionIfAny a échoué :", e);
  }
}
restoreActiveSessionIfAny();

// ============================================================ Mode viewer (lecture seule, Phase v15.4)
// Quand l'utilisateur est connecté en tant que `viewer` (credentials
// `viewer_user`/`viewer_pass` dans _secrets/remote_access.json), on cache
// les contrôles d'écriture (form Lancer, input footer, action buttons,
// bouton fin de séance, mic/media) et on poll /api/current_session pour
// rafraîchir le transcript en lecture.

async function detectUserRole() {
  try {
    const r = await fetch("/api/role");
    if (!r.ok) return;
    const data = await r.json();
    userRole = (data && data.role) || "owner";
  } catch (_) { /* défaut owner */ }
  if (userRole === "viewer") applyViewerMode();
}

function applyViewerMode() {
  // Banner discret en haut du dialogue
  const banner = document.createElement("div");
  banner.id = "viewer-banner";
  banner.textContent =
    "🔒 Mode partagé (lecture seule) : vous voyez la session en direct, " +
    "vous ne pouvez pas modifier ni envoyer de message.";
  const main = document.getElementById("dialogue");
  if (main) main.insertBefore(banner, main.firstChild);

  // Cache la barre Démarrer
  if (startForm) startForm.style.display = "none";

  // Cache l'input footer (textarea, send, mic, media)
  const inputFooter = document.getElementById("dialogue-input");
  if (inputFooter) inputFooter.style.display = "none";

  // Cache le bouton Terminer la séance
  if (endBtn) endBtn.style.display = "none";

  // Cache le record-indicator (push-to-talk inutile)
  if (recordIndicator) recordIndicator.style.display = "none";

  // Phase v15.7.30.1 : les bandeaux chips ont été supprimés, et le form
  // (qui contient les selects colle_format / corrige_anchor) est déjà
  // caché par `startForm.style.display = "none"` ci-dessus en mode viewer.
  // Rien à désactiver de plus.

  // Cache l'engine switcher (les viewers ne décident pas du moteur)
  const engineWrap = document.getElementById("engine-switcher-wrap");
  if (engineWrap) engineWrap.style.display = "none";

  // CSS pour cacher les action buttons sur les bulles + suggestions edit
  // + nav guidé (le viewer ne pilote pas les slides, il suit ce que fait
  // le owner via le polling de guided_index).
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

  // Polling /api/current_session toutes les 5s pour voir le owner taper
  startViewerPolling();
}

async function viewerRefreshTranscript() {
  try {
    const r = await fetch("/api/current_session");
    if (!r.ok) return;
    const data = await r.json();
    if (!data.active) {
      if (dialogue.querySelector(".placeholder")) return;
      dialogue.innerHTML =
        '<p class="placeholder">Pas de session active actuellement. ' +
        'Le owner doit en démarrer une.</p>';
      return;
    }
    activeSession = data.session_id;
    activeMode = data.mode || "colle";
    // Phase v15.7.4 : synchronise les chips côté viewer (read-only :
    // les chips sont visibles mais inactifs, applyViewerMode les disable
    // après si role=viewer).
    applyColleFormatChips(data.colle_format || "mixte");
    // Phase v15.7.30 : idem chips ancrage corrigé.
    applyCorrigeAnchorChips(data.corrige_anchor || "strict");
    if (sessionInfo) {
      sessionInfo.textContent =
        `→ ${data.session_id} (engine: ${data.engine || "?"}) [viewer]`;
    }
    rerenderDialogueFromTranscript(data.transcript || []);
    if (activeMode === "guidé") {
      const startIdx = Number.isInteger(data.guided_index) ? data.guided_index : 0;
      if (!guidedSlides.length) {
        initGuidedPanel(startIdx);
      } else if (startIdx !== guidedIndex) {
        // Owner a changé de slide, synchronise visuellement (sans
        // déclencher le sendGuidedSlideMeta qui tenterait POST 403).
        showGuidedSlide(startIdx, /*announceToClaude=*/false);
      }
    }
    if (!correctionsList.length) initCorrectionsPanel();
  } catch (e) { /* silencieux, la prochaine itération réessaie */ }
}

function startViewerPolling() {
  if (viewerPollHandle !== null) return;
  viewerRefreshTranscript();  // immédiat
  viewerPollHandle = setInterval(viewerRefreshTranscript, 5000);
}

detectUserRole();

// ============================================================ Start session

startForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(startForm);
  const body = Object.fromEntries(fd.entries());
  // Phase S4 (Cartable) : source DROIT : matiere/type/num viennent des combos
  // droit. On les normalise dans le body pour le backend ET la logique de
  // conflit/scan disque (qui lit body.matiere/type/num/exo). Pas de corrigé
  // officiel → ancrage forcé `aucun`.
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
  // Phase A.9 : si workspace_root a été passé en URL params au boot,
  // injecte-le dans le body. Le backend short-circuit alors les combos
  // COURS et force mode=workspace + prompt PROMPT_SYSTEME_WORKSPACE.md.
  if (window._pendingWorkspace && window._pendingWorkspace.workspace_root) {
    body.workspace_root = window._pendingWorkspace.workspace_root;
    if (window._pendingWorkspace.workspace_focus_subdir) {
      body.workspace_focus_subdir = window._pendingWorkspace.workspace_focus_subdir;
    }
    if (window._pendingWorkspace.workspace_excludes) {
      body.workspace_excludes = window._pendingWorkspace.workspace_excludes;
    }
    // Phase A.10.13a : generate_invented_pdf retiré.
  }
  // Phase A.8.3 : si la checkbox 💡 Sujet libre est cochée, injecte le
  // texte du textarea dans le body. Le backend short-circuit alors les
  // combos matière/type/num/exo.
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
  // Phase Z.8.5 → A.9 → A.10.15 : si une session est ACTIVE **et** que
  // son contexte (matière/type/num/exo/année **+ mode/format/anchor**)
  // matche celui du body, afficher directement le modal de conflit (4
  // options : Reprendre / Conserver+nouvelle / Écraser / Annuler).
  //
  // Si le contexte diffère (ex. TP8→TP9 depuis l'entête, ou changement
  // d'ancrage strict→consultatif sur le même exo), on **fall-through**
  // vers `findExistingSession(body)` qui scanne le disque pour le vrai
  // target. Sinon le modal affichait l'ancienne session comme « existante
  // pour TP9 » alors que c'est en réalité un TP8, incohérent (cf.
  // friction user 2026-05-14). Le backend `/api/start_session` finalise
  // automatiquement la session active avant d'en démarrer une nouvelle.
  if (activeSession) {
    try {
      const r = await fetch("/api/current_session");
      if (r.ok) {
        const data = await r.json();
        if (data.active) {
          const norm = (v) => (v == null ? "" : String(v).trim());
          const reqMode   = norm(body.mode) || "colle";
          const reqFormat = norm(body.colle_format) || "mixte";
          const reqAnchor = norm(body.corrige_anchor) || "strict";
          const sMode   = norm(data.mode)          || "colle";
          const sFormat = norm(data.colle_format)  || "mixte";
          const sAnchor = norm(data.corrige_anchor) || "strict";
          const sameContext = (
            norm(data.matiere).toUpperCase() === norm(body.matiere).toUpperCase() &&
            norm(data.type).toUpperCase()    === norm(body.type).toUpperCase()    &&
            norm(data.num)                   === norm(body.num)                   &&
            norm(data.exo)                   === norm(body.exo)                   &&
            norm(data.annee)                 === norm(body.annee)                 &&
            sMode   === reqMode  &&
            sFormat === reqFormat &&
            sAnchor === reqAnchor
          );
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
              label: data.label,
            };
            showStartConflictModal(existing, body);
            return;
          }
        }
      }
    } catch (_) { /* fallthrough vers findExistingSession */ }
  }
  // Pas de session active, vérifie le disque pour un match avec le
  // contexte ciblé (cf. findExistingSession).
  const existing = await findExistingSession(body);
  if (existing) {
    showStartConflictModal(existing, body);
    return;
  }
  await doStartSession(body);
});

// Helper Phase Z.8.5 → A.10.15 : compare le contexte de la session
// active avec celui qu'on tente de lancer. Inclut mode/colle_format/
// corrige_anchor depuis Phase A.8.6 : le suffixe du session_id en
// dépend, donc deux contextes qui diffèrent sur ces axes sont des
// sessions distinctes (pas de risque d'écrasement).
async function _isCurrentSessionSameContext(body) {
  if (!activeSession) return false;
  try {
    const r = await fetch("/api/current_session");
    if (!r.ok) return false;
    const data = await r.json();
    if (!data.active) return false;
    const norm = (v) => (v == null ? "" : String(v).trim());
    const reqMode   = norm(body.mode) || "colle";
    const reqFormat = norm(body.colle_format) || "mixte";
    const reqAnchor = norm(body.corrige_anchor) || "strict";
    const sMode   = norm(data.mode)          || "colle";
    const sFormat = norm(data.colle_format)  || "mixte";
    const sAnchor = norm(data.corrige_anchor) || "strict";
    return (
      norm(data.matiere).toUpperCase() === norm(body.matiere).toUpperCase() &&
      norm(data.type).toUpperCase()    === norm(body.type).toUpperCase()    &&
      norm(data.num)                   === norm(body.num)                   &&
      norm(data.exo)                   === norm(body.exo)                   &&
      norm(data.annee)                 === norm(body.annee)                 &&
      sMode   === reqMode  &&
      sFormat === reqFormat &&
      sAnchor === reqAnchor
    );
  } catch (_) { return false; }
}

// Phase A.8.3 : toggle Sujet libre. Affiche/cache la zone textarea et
// désactive les contrôles COURS quand le mode sujet libre est actif.
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
    // L'option Guidé du select mode est désactivée en sujet libre
    const modeEl = startForm.querySelector('[name="mode"]');
    if (modeEl) {
      const guidedOpt = modeEl.querySelector('option[value="guidé"]');
      if (guidedOpt) guidedOpt.disabled = active;
      // Si on était sur Guidé, bascule sur Découverte
      if (active && modeEl.value === "guidé") {
        modeEl.value = "découverte";
        modeEl.dispatchEvent(new Event("change", {bubbles: true}));
      }
    }
  }
}

async function findExistingSession(body) {
  // Phase A.8.6 : le match doit aussi prendre en compte mode, colle_format
  // et corrige_anchor. Sinon démarrer « PSI TP_Shannon mode colle » alors
  // qu'une session « PSI TP_Shannon mode découverte » existe déjà
  // déclencherait le modal de conflit, alors qu'aucun écrasement n'est
  // en jeu (les session_id ont des suffixes différents).
  try {
    const r = await fetch("/api/sessions");
    if (!r.ok) return null;
    const data = await r.json();
    const list = Array.isArray(data.sessions) ? data.sessions : [];
    const norm = (v) => (v == null ? "" : String(v).trim());
    const reqMode   = norm(body.mode) || "colle";
    const reqFormat = norm(body.colle_format) || "mixte";
    const reqAnchor = norm(body.corrige_anchor) || "strict";
    // Phase A.12.3 : en mode workspace, matiere/type/num/exo sont
    // synthétisés côté backend (`WORKSPACE`/`DIR`/slug) et ABSENTS du body
    // du formulaire au submit. On matche donc sur `workspace_root` (le
    // dossier choisi), sinon le modal de conflit ne se déclenchait jamais
    // pour une nouvelle séance sur un workspace déjà ouvert.
    const _normWs = (p) =>
      norm(p).replace(/[\\/]+$/, "").replace(/\\/g, "/").toLowerCase();
    const reqWs = _normWs(body.workspace_root);
    const matches = list.filter(s => {
      if (reqWs) {
        // Workspace : un dossier = une conv. On matche sur le seul
        // workspace_root et on ignore mode/format/anchor (placeholders en
        // workspace), l'utilisateur veut « même dossier → propose ».
        return _normWs(s.workspace_root) === reqWs;
      }
      if (norm(s.matiere).toUpperCase() !== norm(body.matiere).toUpperCase()) return false;
      if (norm(s.type).toUpperCase()    !== norm(body.type).toUpperCase())    return false;
      if (norm(s.num)                   !== norm(body.num))                   return false;
      if (norm(s.exo)                   !== norm(body.exo))                   return false;
      if (norm(s.annee)                 !== norm(body.annee))                 return false;
      // Tolérance migration : si la session existante n'a pas le champ
      // (legacy avant Phase A.8.6), on considère qu'elle peut matcher
      // n'importe quel mode/format/anchor, l'utilisateur a sans doute
      // une seule version de cet exo en stock, autant la lui proposer.
      const sMode   = norm(s.mode);
      const sFormat = norm(s.colle_format);
      const sAnchor = norm(s.corrige_anchor);
      if (sMode   && sMode   !== reqMode)   return false;
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

// Phase A.9 (correctif) : tous les contrôles du form RESTENT actifs
// mid-session. L'utilisateur peut donc changer matière/type/num/exo/
// année/mode/sujet_libre/etc. mid-session pour préparer un futur clic
// Lancer (qui ouvrira le modal de conflit). Le seul cas vraiment
// « bizarre » mid-session était le chip `corrige_anchor` qui POSTait
// /api/set_corrige_anchor pour switcher en cours de séance, désactivé
// dans `setCorrigeAnchor` quand activeSession est set (la valeur du
// select reste éditable mais ne s'applique qu'au prochain Lancer).
// Cf. friction user 2026-05-13 : « le select matiere n'a pas a être
// grisé car en pleine session je veux décider de changer de matière …
// y'a que corrige_anchor où c'est bizarre que ce soit switchable ».

async function doStartSession(body) {
  try {
    const r = await fetch("/api/start_session", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    const data = await r.json();
    if (!r.ok) { alert("Erreur: " + (data.error || r.status)); return; }
    activeSession = data.session_id;
    activeMode = body.mode || "colle";
    // Phase v15.7.4 : synchronise les chips au démarrage (silencieux,
    // pas de marker visuel : c'est le format initial, pas une bascule).
    applyColleFormatChips(data.colle_format || body.colle_format || "mixte");
    // Phase v15.7.30 : idem chips ancrage corrigé au démarrage.
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
    // Phase A.9 (correctif) : pas de lock du form ici. Les selects de
    // SOURCE (matière/type/num/exo/année/mode) doivent rester actifs
    // pour permettre à l'user de préparer un futur Lancer (modal de
    // conflit). Seul `corrige_anchor` est inhibé via le no-op de
    // `setCorrigeAnchor` quand activeSession est set.
    if (activeMode === "guidé") {
      initGuidedPanel();  // fire-and-forget, ne bloque pas le 1ʳᵉ stream
    }
    showRemindNavBtnIfActive(!!data.auto_advance);
    initCorrectionsPanel();  // panneau « Corrigés » sidebar, tous modes
    // Le contexte initial est déjà append côté backend, on déclenche le 1er stream.
    streamResponse();
  } catch (e) { alert("Erreur réseau: " + e.message); }
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
    // fallback minimaliste si la modale n'est pas dans le DOM
    if (confirm("Une session existe déjà pour cet exercice. " +
                "OK = reprendre, Annuler = démarrer (efface l'ancienne).")) {
      resumeSession(existing.session_id);
    } else {
      fetch(`/api/sessions/${encodeURIComponent(existing.session_id)}`,
            { method: "DELETE" }).finally(() => doStartSession(body));
    }
    return;
  }
  const exo = body.exo && body.exo !== "full" ? `ex${body.exo}` : "exfull";
  const ctxLabel = `${body.matiere || "?"} ${body.type || "?"}${body.num || "?"} ${exo}` +
                   (body.annee ? ` ${body.annee}` : "");
  msg.textContent =
    `Une session pour ${ctxLabel} existe déjà. Tu peux la reprendre, ` +
    `en démarrer une nouvelle qui CONSERVE l'ancienne (recommandé, ` +
    `nouveau fichier suffixé _2/_3…), ou la SUPPRIMER pour repartir de zéro.`;
  const dateStr = (existing.last_alive || existing.started_at || "")
                    .slice(0, 16).replace("T", " ");
  const labelLine = existing.label ? `\n« ${existing.label} »` : "";
  meta.textContent =
    `${existing.session_id}${labelLine}\n` +
    `${existing.n_exchanges || 0} tour(s), mode ${existing.mode || "colle"}` +
    (existing.interrupted ? " (interrompue)" : "") + `\n` +
    `Dernière activité : ${dateStr || "(inconnue)"}`;
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
      // Phase A.9 : conserve l'ancienne, démarre une nouvelle suffixée
      // _2/_3/… via `force_new_session=true`. Le backend appelle
      // `_resolve_session_id(base, force_new_session=True)` qui scanne
      // _1.json, _2.json… et retourne le 1ᵉʳ libre.
      cleanup();
      await doStartSession({ ...body, force_new_session: true });
    };
  }
  overwriteBtn.onclick = async () => {
    // Phase A.8.5 hotfix : confirmation explicite avant DELETE destructif.
    // Bug observé 2026-05-12 : user a perdu une session de 55 messages en
    // cliquant par mégarde sur cette option (croyant qu'elle reprenait).
    // Un backup _trash/ est créé côté backend mais ne couvre pas tous les
    // cas (si plusieurs DELETE successifs > rotation FIFO 20).
    const n = existing.n_exchanges || 0;
    const lastAct = (existing.last_alive || existing.started_at || "")
                      .slice(0, 16).replace("T", " ");
    const confirmMsg =
      `⚠ Cela va SUPPRIMER la session existante :\n\n` +
      `   ${existing.session_id}\n` +
      `   ${n} tour(s), dernière activité ${lastAct}\n\n` +
      `Tape OUI pour confirmer (un backup sera quand même créé dans _sessions/_trash/).`;
    const answer = window.prompt(confirmMsg, "");
    if (!answer || answer.trim().toUpperCase() !== "OUI") {
      // Annulé, modale reste ouverte pour permettre à l'user de
      // changer d'avis et cliquer Reprendre.
      return;
    }
    cleanup();
    try {
      await fetch(`/api/sessions/${encodeURIComponent(existing.session_id)}`,
                  { method: "DELETE" });
    } catch (_) { /* continue tout de même */ }
    await doStartSession(body);
  };
  cancelBtn.onclick = () => cleanup();
}

// ============================================================ Send + stream

// Phase v15.7.21 : pendant un stream actif, le bouton Send devient
// ⏹ Annuler. Le click ouvre alors la modal d'annulation au lieu d'envoyer.
function _onSendClickRouter() {
  if (isStreamingActive()) {
    openCancelStreamModal();
  } else {
    sendUserMessage();
  }
}
sendBtn.addEventListener("click", _onSendClickRouter);
userInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); _onSendClickRouter(); }
});

// Auto-resize façon LLM SOTA : la hauteur s'adapte au contenu, capée par max-height CSS.
// Phase A.8.4 : auto-scroll vers le bas après resize pour que la dernière
// ligne reste visible quand le contenu dépasse max-height (200px CSS).
// Avant : en dictée vocale longue ou saisie clavier prolongée, le texte
// débordait silencieusement, le user devait scroller manuellement le
// textarea pour suivre la dictée en cours.
function autoResizeUserInput() {
  userInput.style.height = "auto";
  userInput.style.height = userInput.scrollHeight + "px";
  userInput.scrollTop = userInput.scrollHeight;
}
userInput.addEventListener("input", autoResizeUserInput);

// Détection répétitions anormales (hallucination Whisper). Retourne le motif
// répété s'il y a un groupe de 1-4 mots qui apparaît ≥5 fois consécutivement,
// sinon null.
function detectWhisperRepetition(text) {
  if (!text) return null;
  // 1-4 mots (lettres/apostrophes/chiffres), capturés, suivis de virgule/espace
  // optionnels, puis le même groupe répété ≥4 fois supplémentaires (= 5 total).
  const re = /\b([\wÀ-ÿ'’]+(?:[\s,]+[\wÀ-ÿ'’]+){0,3})(?:[\s,]+\1){4,}/i;
  const m = text.match(re);
  return m ? m[1].trim() : null;
}

function maybeFlagWhisperHallucination(text) {
  const motif = detectWhisperRepetition(text);
  if (!motif) {
    // Si un banner précédent traînait, on l'enlève
    const old = document.getElementById("whisper-hallu-banner");
    if (old) old.remove();
    return;
  }
  // Insère un banner discret au-dessus de #dialogue-input
  let banner = document.getElementById("whisper-hallu-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "whisper-hallu-banner";
    banner.className = "whisper-hallu";
    const footer = document.getElementById("dialogue-input");
    footer.parentNode.insertBefore(banner, footer);
  }
  const safe = motif.replace(/[<>&]/g, c => ({"<":"&lt;",">":"&gt;","&":"&amp;"}[c]));
  banner.innerHTML =
    `⚠️ Whisper a halluciné une répétition (« <code>${safe}</code> »). ` +
    `Vous voulez nettoyer le texte avant d'envoyer ? ` +
    `<button type="button" id="whisper-hallu-clean">Nettoyer</button> ` +
    `<button type="button" id="whisper-hallu-dismiss">Ignorer</button>`;
  document.getElementById("whisper-hallu-clean").addEventListener("click", () => {
    // Remplace toute occurrence répétée du motif par 1 seule occurrence
    const reGlob = new RegExp(
      `\\b(${motif.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})(?:[\\s,]+\\1){2,}`,
      "gi",
    );
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
  // Phase A.7.2 v15.5 : auto-stop du mic à l'envoi.
  // Si l'utilisateur clique Envoyer (ou Entrée) PENDANT un enregistrement,
  // on stoppe proprement la capture audio et on annule la transcription
  // Whisper. Le contenu courant de l'input (preview WebSpeech sur Chrome/
  // Edge, ou texte tapé) part tel quel, Claude/Gemini gère sans souci
  // les hésitations « euh/donc/voilà ». Pour finaliser Whisper avant envoi
  // (texte plus propre, ~5-15% moins de tokens), cliquer ⏹ d'abord.
  if (isRecording) {
    abortRecordingAndTranscribe();
  }
  const text = userInput.value.trim();
  // Phase v15.7.8 : autorise un envoi sans texte si au moins une pièce
  // jointe est dans le bandeau d'attachments (« j'ai juste envie
  // d'envoyer une photo » sans commenter). Le tray est mis à jour par
  // polling, donc fiable côté DOM sans nouveau fetch ici.
  const hasAttachments = !!(attachmentsTray && attachmentsTray.children.length > 0);
  if (!text && !hasAttachments) return;
  // Phase v15.7.4 : slash-command de bascule format colle (intercepté
  // côté front pour afficher tout de suite le marker, et ne pas créer
  // de bulle student vide). Le backend a la même garde en redondance
  // (cas API direct / mobile).
  const slashMatch = text ? SLASH_COLLE_FORMAT_RE.exec(text) : null;
  if (slashMatch) {
    let fmt = slashMatch[1].toLowerCase();
    if (fmt === "photo") fmt = "photos";
    userInput.value = "";
    autoResizeUserInput();
    setColleFormat(fmt);
    return;
  }
  // Phase v15.7.30 : slash-command de bascule ancrage corrigé.
  const slashAnchorMatch = text ? SLASH_CORRIGE_ANCHOR_RE.exec(text) : null;
  if (slashAnchorMatch) {
    const raw = slashAnchorMatch[1].toLowerCase().replace(/ /g, "_");
    userInput.value = "";
    autoResizeUserInput();
    setCorrigeAnchor(raw);
    return;
  }
  // Annule une transcription Whisper en vol, sinon son résultat retombe
  // dans le champ après que sendUserMessage l'ait vidé.
  cancelPendingTranscribe();
  // Phase v15.7.3 : annule un rewrite ✨ Améliorer encore en vol. Sans
  // ça, le rewrite revient ~1 s après l'envoi et écrase userInput avec
  // la version améliorée du message qu'on vient d'envoyer brut →
  // pollution / désynchro. Le finally de performRewrite() s'occupe de
  // remettre l'UI propre (bouton ✨, readOnly=false).
  if (rewriteInFlightAbort) {
    try { rewriteInFlightAbort.abort(); } catch (_) {}
    rewriteInFlightAbort = null;
  }
  userInput.value = "";
  autoResizeUserInput();
  // Construit le texte d'affichage qui inclut les markdowns d'images
  // (le backend va vider sa queue et l'injecter dans le transcript stocké
  //, on anticipe côté front pour que la bulle student rende les images
  // tout de suite au lieu d'afficher le markdown brut).
  let displayText = text;
  try {
    const r0 = await fetch("/api/pending_attachments");
    if (r0.ok) {
      const d0 = await r0.json();
      const atts = d0.attachments || [];
      if (atts.length > 0) {
        // Phase A.10.13.bug : préfixe `_uploads/` pour storage="uploads"
        // (cohérent avec le markdown backend dans api_send_message).
        // Sinon renderMarkdown route vers /api/cours_file qui 404
        // → "⚠ Image introuvable" pour toutes les photos uploadées
        // depuis A.10.2. Helper module-level depuis A.10.13.bug2.
        const lines = atts.map(a =>
          a.is_image
            ? `![${a.original_name || a.filename}](${_relWithStoragePrefix(a)})`
            : `[Pièce jointe : ${a.original_name || a.filename} (${_relWithStoragePrefix(a)})]`
        );
        // Phase v15.7.8 : si pas de texte (envoi photo seule), pas de
        // séparateur "\n\n" en tête (sinon la bulle student commencerait
        // par deux retours à la ligne avant l'image).
        displayText = text
          ? text + "\n\n" + lines.join("\n")
          : lines.join("\n");
      }
    }
  } catch (_) { /* fallback : pas d'images dans la bulle */ }
  const t = appendTurn("student", "");
  t.innerHTML = renderMarkdown(displayText);
  // Phase v15.7.20 : rendu LaTeX (KaTeX) appliqué AUSSI aux bulles
  // student. Avant : seules les bulles Compagnon avaient renderMathIn,
  // l'étudiant qui postait du `$f(x) = x^2$` voyait le markdown brut.
  renderMathIn(t);
  if (t.parentElement) t.parentElement.dataset.rawText = displayText;
  // Phase v15.7.9 : helper pour retirer la bulle posée en avance si le
  // fetch send_message échoue (sinon on a une bulle student orpheline,
  // pas dans le transcript backend → tentative de suppression utilisateur
  // tombe sur « index hors plage »).
  const _removeOrphanStudentBubble = () => {
    try {
      const container = t && t.parentElement;
      if (container && container.parentElement) {
        container.parentElement.removeChild(container);
      }
    } catch (_) { /* best-effort */ }
  };
  try {
    const reading_state = (typeof getReadingStateForSend === "function")
      ? getReadingStateForSend() : null;
    const r = await fetch("/api/send_message", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text, reading_state}),
    });
    if (!r.ok && r.status !== 202) {
      const data = await r.json().catch(() => ({}));
      _removeOrphanStudentBubble();  // Phase v15.7.9
      alert("Erreur send: " + (data.error || r.status));
      return;
    }
    // Phase v15.7.20 : récupère ocr_blocks depuis la response 202 et
    // injecte un bloc collapsible <details> sous la bulle student pour
    // que le user voie l'OCR Gemini Flash et puisse le contester.
    try {
      const data = await r.json().catch(() => ({}));
      const ocrBlocks = data.ocr_blocks || [];
      if (ocrBlocks.length > 0 && t && t.parentElement) {
        for (const blk of ocrBlocks) {
          _appendOcrCollapsibleBlock(t.parentElement, blk);
        }
      }
    } catch (_) { /* best-effort, l'envoi a marché */ }
    refreshAttachmentsTray();  // queue vidée côté backend → sync UI
    // Phase A.9.1 : refresh galerie photos après envoi (la queue qui vient
    // d'être vidée a été persistée dans session_photos côté backend).
    if (typeof refreshSessionPhotos === "function") {
      refreshSessionPhotos();
    }
    streamResponse();
  } catch (e) {
    _removeOrphanStudentBubble();  // Phase v15.7.9
    alert("Erreur réseau: " + e.message);
  }
}

// ============================================================ Thinking indicator (Phase A.7.2 v6.3)
// Bulle « 🤔 Compagnon réfléchit… 3.2s » affichée pendant l'attente entre
// le clic Lancer/Envoyer et le 1ᵉʳ chunk de réponse. Le timer s'incrémente
// toutes les 250 ms, supprimé dès le 1ᵉʳ event "text" (ou done/end/error).

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
    // Affichage adaptatif selon la durée :
    // - < 30 s : neutre, format classique
    // - 30-60 s : jaune + label « (anormalement long) »
    // - 60-120 s : orange + label « (très long, peut-être bloqué) »
    // - > 120 s : rouge + suggestion d'annuler
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

// ============================================================ Cropper config commune (Phase v15.7.24)
// Réutilisée par toutes les instances Cropper du Compagnon (modal
// re-crop attachment + modal preview avant upload). Le pattern dragMode
// est différent selon touch device :
// - Touch (mobile/tablette) : "move" → tap dans l'image déplace
//   l'image, NE casse PAS la zone de crop. Avant ce fix (v15.7.16
//   utilisait "crop" pour permettre de redessiner en glissant), un
//   tap accidentel sur les bords noirs ou hors handles redessinait
//   une mini-zone et l'utilisateur perdait sa sélection.
// - Souris (desktop) : "crop" → glisser sur l'image redessine la zone
//   librement (la souris est précise, pas de tap accidentel).
// + minCropBoxWidth/Height : empêche que la zone se réduise sous 50px,
//   filet de sécurité supplémentaire contre les zones rikiki accidentelles.
function _cropperOptionsCommon() {
  const isTouchDevice = (navigator.maxTouchPoints > 0) || ("ontouchstart" in window);
  return {
    viewMode: 1,
    autoCropArea: 1,
    background: false,
    responsive: true,
    checkOrientation: true,
    dragMode: isTouchDevice ? "move" : "crop",
    minCropBoxWidth: 50,
    minCropBoxHeight: 50,
  };
}

// ============================================================ Selection toolbar + Notes (Phase v15.7.23)
// Quand l'utilisateur sélectionne du texte dans une bulle (Compagnon ou
// student), un mini-popup apparaît juste au-dessus de la sélection avec
// 4 actions : 💾 Sauvegarder / 📋 Citer / 🤔 Expliquer / 📝 Copier.
//
// Sauvegarder → POST /api/saved_selections + onglet sidebar 🔖 Notes.
// Citer → insère `> texte\n` dans userInput.
// Expliquer → pré-remplit `Peux-tu m'expliquer : "texte"` (user valide).
// Copier → clipboard.writeText (l'utilisateur peut faire Ctrl+C aussi
//   mais avoir le bouton fait moins de friction au touch).
//
// Notes : persistées dans session_state.data["saved_selections"] côté
// backend. Click sur une note → scroll vers la bulle source via
// message_id + highlight bref jaune.

let _selectionToolbarEl = null;       // div flottant créé à la volée
let _selectionHideTimer = null;       // setTimeout pour masquer après inactivité
const _SELECTION_MIN_CHARS = 3;       // sélection trop courte = pas de toolbar

function _getSelectionInsideTurn() {
  // Retourne {text, range, bubbleEl, role, messageId} ou null si pas de
  // sélection valide dans une bulle .turn (claude ou student).
  const sel = window.getSelection && window.getSelection();
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return null;
  const text = sel.toString().trim();
  if (text.length < _SELECTION_MIN_CHARS) return null;
  // Range doit être inclus dans une bulle .turn (pas un contrôle d'UI)
  const range = sel.getRangeAt(0);
  let node = range.commonAncestorContainer;
  if (node.nodeType === Node.TEXT_NODE) node = node.parentElement;
  // Remonte jusqu'à trouver le .turn parent
  let bubble = node;
  while (bubble && bubble !== document.body) {
    if (bubble.classList && bubble.classList.contains("turn") &&
        (bubble.classList.contains("claude") || bubble.classList.contains("student"))) {
      break;
    }
    bubble = bubble.parentElement;
  }
  if (!bubble || bubble === document.body) return null;
  // Skip les bulles « system » et les sous-éléments comme .ocr-collapsible
  if (bubble.classList.contains("system")) return null;
  // Récupère role + message_id si dispo (data-id posé sur le .turn)
  const role = bubble.classList.contains("student") ? "student" : "claude";
  const messageId = bubble.dataset?.msgId || null;
  return { text, range, bubbleEl: bubble, role, messageId };
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
  tb.addEventListener("mousedown", (e) => e.preventDefault());  // évite de perdre la sélection
  tb.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    const act = btn.dataset.act;
    const info = _getSelectionInsideTurn();
    if (!info) return;
    if (act === "cahier-open-colors") {
      // Phase A.10.22 : unification : ouvre l'onglet Couleurs et garde
      // la sélection vivante. L'onglet a un mode « applique-à-sélection »
      // qui détecte la sélection courante et propose les swatches comme
      // boutons d'application.
      _openColorsTabForSelection(info);
      return;
    }
    _handleSelectionAction(act, info);
  });
  _selectionToolbarEl = tb;
  return tb;
}

// Phase A.10.20 : détecte si la sélection est DANS une `.cahier-card`.
// Active alors les boutons couleur dans la toolbar.
function _isSelectionInCahierCard(range) {
  let node = range.commonAncestorContainer;
  if (node.nodeType === Node.TEXT_NODE) node = node.parentElement;
  while (node && node !== document.body) {
    if (node.classList && node.classList.contains("cahier-card")) return true;
    node = node.parentElement;
  }
  return false;
}

// Phase A.10.20 : applique une couleur stylo / surligneur à la sélection
// courante. Edite le texte source du message (data-raw-text) en wrappant
// la 1ère occurrence du texte sélectionné dans `{tag}…{/tag}`. PATCH
// /api/messages/<index> avec `silent=true` pour skipper l'OCR refresh.
async function _applyCahierColor(info, tag) {
  const turn = info.bubbleEl;
  let rawText = turn.dataset.rawText || "";
  const selectedText = (info.text || "").trim();
  if (!selectedText) {
    alert("Sélection vide.");
    return;
  }
  // Trouve l'index transcript de cette bulle (mêmes critères que editTurn)
  const all = Array.from(dialogue.querySelectorAll(".turn.student, .turn.claude"));
  const index = all.indexOf(turn);
  if (index < 0) { alert("Bulle introuvable dans le transcript."); return; }
  // Construit le nouveau texte
  let newText;
  if (tag === "clear") {
    // Retire tout color/hl tag qui wrappe la sélection
    const allTags = ["bleu", "rouge", "vert", "noir",
      "hl-jaune", "hl-vert", "hl-rose", "hl-violet"];
    newText = rawText;
    let stripped = false;
    for (const t of allTags) {
      // Pattern : `{t}xxxSELECTEDxxx{/t}` → on retire les tags autour de la sélection
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
    // Find first occurrence dans le texte source, tolère whitespace différents
    const idx = rawText.indexOf(selectedText);
    if (idx < 0) {
      // Fallback : tolère espaces multiples / sauts de ligne
      const flexRe = new RegExp(selectedText
        .split(/\s+/)
        .map(t => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
        .join("\\s+"));
      const m = rawText.match(flexRe);
      if (!m) {
        alert("Sélection introuvable dans le texte source.\n\n" +
              "Essaie une sélection plus simple (pas à cheval sur plusieurs paragraphes).");
        return;
      }
      newText = rawText.slice(0, m.index) +
        `{${tag}}${m[0]}{/${tag}}` +
        rawText.slice(m.index + m[0].length);
    } else {
      newText = rawText.slice(0, idx) +
        `{${tag}}${selectedText}{/${tag}}` +
        rawText.slice(idx + selectedText.length);
    }
  }
  if (newText === rawText) {
    _hideSelectionToolbar();
    return;
  }
  // PATCH backend
  try {
    const r = await fetch(`/api/messages/${index}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: newText, silent: true }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      alert("Échec PATCH : " + (data.error || r.status));
      return;
    }
    // Update local : raw + render
    turn.dataset.rawText = newText;
    const textDiv = turn.querySelector(":scope > div:nth-child(2)");
    if (textDiv) textDiv.innerHTML = renderMarkdown(newText);
    // Re-applique linkifyPageRefs et KaTeX si applicable
    try { linkifyPageRefs(turn); } catch (_) {}
    if (window.renderMathInElement) {
      try { window.renderMathInElement(turn, _katexOptions || {}); } catch (_) {}
    }
    _hideSelectionToolbar();
    try { window.getSelection().removeAllRanges(); } catch (_) {}
  } catch (e) {
    alert("Erreur réseau : " + e.message);
  }
}

function _positionSelectionToolbar(range) {
  const tb = _ensureSelectionToolbar();
  const rect = range.getBoundingClientRect();
  // Au-dessus de la sélection si possible, sinon en dessous
  const tbHeight = 40;  // approximation
  const margin = 8;
  let top = rect.top + window.scrollY - tbHeight - margin;
  if (top < window.scrollY + 4) {
    top = rect.bottom + window.scrollY + margin;  // bascule en dessous
  }
  let left = rect.left + window.scrollX + (rect.width / 2);
  // Centré sur la sélection mais clamp aux bords du viewport
  tb.style.top = top + "px";
  tb.style.left = left + "px";
  tb.style.transform = "translateX(-50%)";
  // Phase A.10.22 : toggle bouton « 🎨 Colorier » selon que la sélection
  // est dans une `.cahier-card`. Ouvre l'onglet Couleurs unifié au clic.
  const colorOpenBtn = tb.querySelector('[data-act="cahier-open-colors"]');
  if (colorOpenBtn) {
    colorOpenBtn.hidden = !_isSelectionInCahierCard(range);
  }
  tb.hidden = false;
  // Auto-hide après 8s d'inactivité (utilisateur peut avoir cliqué ailleurs)
  if (_selectionHideTimer) clearTimeout(_selectionHideTimer);
  _selectionHideTimer = setTimeout(() => {
    if (tb) tb.hidden = true;
  }, 8000);
}

function _hideSelectionToolbar() {
  if (_selectionToolbarEl) _selectionToolbarEl.hidden = true;
  if (_selectionHideTimer) { clearTimeout(_selectionHideTimer); _selectionHideTimer = null; }
}

document.addEventListener("selectionchange", () => {
  const info = _getSelectionInsideTurn();
  if (info) {
    _positionSelectionToolbar(info.range);
  } else {
    _hideSelectionToolbar();
  }
});

// Phase v15.7.28 : nettoie le bruit KaTeX d'une sélection visuelle.
// Quand l'user sélectionne du texte qui contient des formules rendues
// par KaTeX, getSelection().toString() capture à la fois la couche
// MathML invisible (chars Unicode mathématiques type 𝑌, 𝑖, 𝐸…)
// ET la couche visuelle (Y, i, E…), séparées par des \n parasites
// entre les spans inline-block + ZWSP (​) intercalés.
//
// On retire ces 3 sources de bruit et on collapse les espaces multiples.
// Résultat : phrase lisible sans la mise en forme math (Y_i devient
// "Y i") mais propre, copiable, citable sans bouillie Unicode.
function _cleanupKatexSelection(text) {
  if (!text) return "";
  // Mathematical Alphanumeric Symbols (𝐴-𝟿) : tout le bloc U+1D400-U+1D7FF
  let out = text.replace(/[\u{1D400}-\u{1D7FF}]/gu, "");
  // Invisibles : ZWSP, ZWNJ, ZWJ, ZWNBSP, FUNCTION APPLICATION,
  // INVISIBLE TIMES, INVISIBLE SEPARATOR, INVISIBLE PLUS, etc.
  out = out.replace(/[​-‏⁠-⁯﻿]/g, "");
  // Collapse tous les whitespace (incluant \n) en simple espace
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
    // Phase v15.7.28 : cleanup KaTeX direct sur le text à sauvegarder.
    // Approche plus simple que v15.7.26 (rawText + 2 modes) : on
    // retire les chars Unicode mathématiques + ZWSP + collapse les
    // \n parasites. Lisible sans avoir à re-rendre le source markdown.
    const cleanedText = _cleanupKatexSelection(text);
    try {
      const r = await fetch("/api/saved_selections", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          text: cleanedText,
          message_id: info.messageId,
          role: info.role,
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        alert("Sauvegarde échouée : " + (data.error || r.status));
        return;
      }
      // Phase v15.7.26 : highlight persistant de la sélection dans la
      // bulle source via <mark class="saved-note-mark">. Best-effort :
      // surroundContents foire si la sélection traverse plusieurs nœuds
      // (ex: span KaTeX) → on swallow l'erreur, le user a quand même
      // sa note dans le panneau.
      try {
        const range = info.range;
        const mark = document.createElement("mark");
        mark.className = "saved-note-mark";
        mark.dataset.selId = data.id;
        range.surroundContents(mark);
        // Clear la sélection pour montrer le résultat clean
        try { window.getSelection().removeAllRanges(); } catch (_) {}
      } catch (e) {
        // Sélection traverse plusieurs éléments (KaTeX, listes) →
        // surroundContents lève DOMException. Pas grave : la note est
        // sauvegardée, juste sans highlight visuel persistant.
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
  // Toast bref en haut de l'écran
  const t = document.createElement("div");
  t.className = "selection-toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => { try { t.remove(); } catch (_) {} }, 1800);
}

// ============================================================ Notes pane

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
      notesListEl.innerHTML =
        '<div class="notes-empty">Pas de session active. Lance une séance pour sauvegarder des notes.</div>';
      return;
    }
    if (sels.length === 0) {
      notesListEl.innerHTML =
        '<div class="notes-empty">' +
        '<strong>Aucune note pour l\'instant.</strong><br><br>' +
        '<em>Sélectionne du texte dans une bulle (Compagnon ou toi-même) pour voir les options : ' +
        '<strong>💾 Sauvegarder</strong>, <strong>📋 Citer</strong>, ' +
        '<strong>🤔 Expliquer</strong>, <strong>📝 Copier</strong>.</em>' +
        '</div>';
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
      head.innerHTML = `<span class="note-role">${role}</span>` +
                       `<span class="note-ts" title="${ts}">${formatTurnTimeShort(ts)}</span>`;
      // Phase v15.7.28 : affichage simple. Les nouvelles notes arrivent
      // déjà nettoyées depuis la sauvegarde. Pour les anciennes notes
      // (sauvées en v15.7.23-v15.7.26 avec le junk KaTeX brut), on
      // ré-applique le cleanup au render (idempotent : sans effet sur
      // texte déjà propre). Évite une migration JSON.
      const body = document.createElement("div");
      body.className = "note-body";
      body.textContent = _cleanupKatexSelection(sel.text);

      const actions = document.createElement("div");
      actions.className = "note-actions";

      const goBtn = document.createElement("button");
      goBtn.type = "button"; goBtn.title = "Aller à la bulle source";
      goBtn.textContent = "↪ Voir";
      goBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        _scrollToBubble(sel.message_id);
      });
      const delBtn = document.createElement("button");
      delBtn.type = "button"; delBtn.title = "Supprimer cette note";
      delBtn.textContent = "🗑";
      delBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!confirm("Supprimer cette note ?")) return;
        try {
          await fetch("/api/saved_selections/" + encodeURIComponent(sel.id), {
            method: "DELETE",
          });
          // Phase v15.7.26 : retire aussi le highlight persistant de la
          // bulle source (mark[data-sel-id="..."]) si présent.
          if (dialogue) {
            const marks = dialogue.querySelectorAll(
              `mark.saved-note-mark[data-sel-id="${CSS.escape(sel.id)}"]`
            );
            marks.forEach(m => {
              const parent = m.parentNode;
              while (m.firstChild) parent.insertBefore(m.firstChild, m);
              parent.removeChild(m);
              parent.normalize();
            });
          }
          refreshSavedNotes();
        } catch (e2) { alert("Erreur : " + e2.message); }
      });
      actions.appendChild(goBtn);
      actions.appendChild(delBtn);
      item.appendChild(head);
      item.appendChild(body);
      item.appendChild(actions);
      // Click body → scroll vers bulle source
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
  bubble.scrollIntoView({ behavior: "smooth", block: "center" });
  bubble.classList.add("note-highlight");
  setTimeout(() => bubble.classList.remove("note-highlight"), 2500);
}

if (notesRefreshBtn) notesRefreshBtn.addEventListener("click", refreshSavedNotes);

// Phase A.10.13e : formate joliment un nom de fichier photo renommé via
// OCR Gemini (Phase A.10.13d). Pattern d'entrée :
//   YYYY-MM-DD_HHMM_<kind>_<slug>_vN.ext  (nouveau, renommé OCR)
//   cropped_<timestamp_ms>_v1.jpg          (legacy, avant rename)
//   photo_AN1_TD5_ex11_v1.jpg              (legacy COURS perso)
// Sortie : "Pseudo code · leaf2 function · 14/05 10:42" si parse OK,
// sinon retourne le filename brut (fallback).
function _prettifyPhotoFilename(filename) {
  if (!filename) return "";
  // Strip extension
  const base = filename.replace(/\.[a-z0-9]+$/i, "");
  // Pattern OCR-renamed : YYYY-MM-DD_HHMM_<kind>_<slug>_vN
  const m = base.match(/^(\d{4}-\d{2}-\d{2})_(\d{4})_([a-z0-9_]+?)_v(\d+)$/i);
  if (m) {
    const date = m[1];        // 2026-05-14
    const hhmm = m[2];        // 1042
    const kindSlug = m[3];    // pseudo_code_leaf2_function
    const version = parseInt(m[4], 10);
    // Heuristique : sépare kind (1-3 premiers mots avant underscore)
    // du slug du contenu. Comme on n'a pas de séparateur explicite,
    // on capitalise tout et on joint par espaces.
    const words = kindSlug.split("_").filter(w => w.length > 0);
    const pretty = words
      .map(w => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
    // Date au format FR : DD/MM HH:MM
    const [y, mo, d] = date.split("-");
    const hh = hhmm.slice(0, 2);
    const mm = hhmm.slice(2);
    const dateFr = `${d}/${mo} ${hh}:${mm}`;
    const vSuffix = version > 1 ? ` (v${version})` : "";
    return `${pretty} · ${dateFr}${vSuffix}`;
  }
  // Pattern legacy `cropped_<timestamp>_vN` : juste retire les underscores
  const m2 = base.match(/^cropped_(\d+)_v(\d+)$/);
  if (m2) {
    const ts = parseInt(m2[1], 10);
    if (!isNaN(ts) && ts > 1000000000000) {
      try {
        const d = new Date(ts);
        const dateFr = d.toLocaleString("fr-FR", {
          day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
        });
        return `Photo · ${dateFr}`;
      } catch (_) {}
    }
    return base;
  }
  // Fallback générique : underscores → espaces, capitalize 1er mot
  return base.replace(/_/g, " ").replace(/\bv\d+\b/, "").trim();
}

// ============================================================ Photos gallery (Phase A.9.1)
// Galerie auto des photos envoyées au tuteur pendant la séance. Chaque
// send_message qui embarquait des images alimente côté backend la liste
// `session_photos` du JSON de session ; le front la lit via /api/session_photos
// et affiche une grille de vignettes. Click = lightbox (réutilise le même
// composant que les slides guidées). 🗑 = retire l'entrée de la galerie
// (le fichier disque reste, comme pour `pending_attachments` DELETE).

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
      photosGridEl.innerHTML =
        '<div class="photos-empty">Pas de session active. Lance une séance pour archiver les photos.</div>';
      return;
    }
    if (photos.length === 0) {
      photosGridEl.innerHTML =
        '<div class="photos-empty">' +
        '<strong>Aucune photo pour l\'instant.</strong><br><br>' +
        '<em>Toutes les images envoyées au tuteur (📷 ou 📎) seront archivées ici ' +
        'automatiquement. Clique sur une vignette pour l\'aggrandir, ou sur 🗑 pour ' +
        'la retirer de la galerie.</em>' +
        '</div>';
      return;
    }
    photosGridEl.innerHTML = "";
    // Tri : plus récente en premier (renverse la liste qui est en ordre
    // chronologique d'envoi).
    const sorted = [...photos].reverse();
    for (const ph of sorted) {
      const card = document.createElement("div");
      card.className = "photo-card";
      card.dataset.photoId = ph.id || "";
      // Phase A.10.13e : title au hover : nom formaté joli depuis le
      // filename renommé OCR (YYYY-MM-DD_HHMM_kind_slug_vN.ext).
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
          textContent: "🗎 (fichier introuvable)",
        }));
      });
      imgWrap.appendChild(img);

      const meta = document.createElement("div");
      meta.className = "photo-meta";
      const tsShort = (typeof formatTurnTimeShort === "function")
        ? formatTurnTimeShort(ph.sent_at || "") : (ph.sent_at || "");
      const sizeKb = ph.size_bytes ? Math.round(ph.size_bytes / 1024) + " kB" : "";
      meta.innerHTML =
        `<span class="photo-ts" title="${ph.sent_at || ""}">${tsShort}</span>` +
        (sizeKb ? `<span class="photo-size">${sizeKb}</span>` : "");

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "photo-del-btn";
      delBtn.title = "Retirer de la galerie (le fichier disque est conservé)";
      delBtn.textContent = "🗑";
      delBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!confirm("Retirer cette photo de la galerie ?\n\n(Le fichier reste sous COURS/, seule l'entrée de tracking est supprimée.)")) {
          return;
        }
        try {
          const resp = await fetch("/api/session_photos/" + encodeURIComponent(ph.id), {
            method: "DELETE",
          });
          if (resp.ok || resp.status === 204) {
            refreshSessionPhotos();
          } else {
            const errData = await resp.json().catch(() => ({}));
            alert("Erreur : " + (errData.error || resp.status));
          }
        } catch (e2) { alert("Erreur réseau : " + e2.message); }
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

// ============================================================ Dynamic Outline (Phase A.10.13c)
// Sommaire de la séance auto-construit depuis les patterns structuraux
// des réponses du tuteur (## H2, **Exercice N**, etc.). Affiché dans le
// pane Docs au-dessus des PDFs officiels. Édition inline (double-click
// sur le titre), toggle on/off via 🗑/✓, click corps → scroll vers
// bulle source. Refresh après chaque réponse tuteur (hook SSE).

const outlineListEl = $("#outline-list");
const outlineRefreshBtn = $("#outline-refresh");

const _OUTLINE_KIND_ICONS = {
  section: "§",
  subsection: "§§",
  exercise: "✏",
  question: "?",
};

async function refreshDynamicOutline() {
  if (!outlineListEl) return;
  try {
    const r = await fetch("/api/dynamic_outline");
    if (!r.ok) return;
    const data = await r.json();
    const entries = data.outline || [];
    if (!data.active) {
      outlineListEl.innerHTML =
        '<div class="outline-empty">Pas de session active.</div>';
      return;
    }
    if (entries.length === 0) {
      outlineListEl.innerHTML =
        '<div class="outline-empty">Le tuteur n\'a pas encore introduit de section/question structurée. Ce sommaire s\'enrichit automatiquement au fil des réponses.</div>';
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
      titleEl.addEventListener("click", (e) => {
        if (e.target === titleEl && e.detail === 1) {
          // Single-click → scroll vers source
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
      toggleBtn.title = enabled
        ? "Désactiver (l'entrée reste mais grisée)"
        : "Réactiver";
      toggleBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        await _patchOutline(entry.id, { enabled: !enabled });
        refreshDynamicOutline();
      });

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.textContent = "🗑";
      delBtn.title = "Supprimer";
      delBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!confirm("Supprimer cette entrée du sommaire ?")) return;
        try {
          const resp = await fetch("/api/dynamic_outline/" + encodeURIComponent(entry.id), {
            method: "DELETE",
          });
          if (resp.ok || resp.status === 204) refreshDynamicOutline();
        } catch (e2) { alert("Erreur : " + e2.message); }
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
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
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
  const finish = async (commit) => {
    if (done) return;
    done = true;
    titleEl.contentEditable = "false";
    if (commit) {
      const newTitle = (titleEl.textContent || "").trim();
      if (newTitle && newTitle !== old) {
        const updated = await _patchOutline(entry.id, { title: newTitle });
        if (updated) {
          refreshDynamicOutline();
          return;
        }
      }
    }
    titleEl.textContent = old;
  };
  titleEl.addEventListener("blur", () => finish(true), { once: true });
  titleEl.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); finish(false); }
    else if (e.key === "Enter") { e.preventDefault(); finish(true); }
  });
}

if (outlineRefreshBtn) outlineRefreshBtn.addEventListener("click", refreshDynamicOutline);

// ============================================================ Stickies (Phase A.10)
// Mémoire persistante de séance, consignes épinglées que le tuteur doit
// respecter en priorité. Deux origines :
//   - kind="user"  : épinglée manuellement via chip 📌 sur une bulle student
//   - kind="tutor" : émise par le tuteur via <<<REMEMBER>>>{"text"}<<<END>>>
//                    sur demande explicite (« retiens que… »)
// Cap 200 chars/sticky, toggle on/off (désactive l'injection sans supprimer),
// édition inline au double-clic, import depuis une autre session.

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
      stickiesListEl.innerHTML =
        '<div class="stickies-empty">Pas de session active. Lance une séance pour épingler des consignes.</div>';
      return;
    }
    if (stickies.length === 0) {
      stickiesListEl.innerHTML =
        '<div class="stickies-empty">' +
        '<strong>Aucune consigne épinglée.</strong><br><br>' +
        '<em>Pour épingler une consigne : passe la souris sur une bulle à toi dans le fil et clique sur <strong>📌</strong>. ' +
        'Ou dis explicitement au tuteur : « <em>retiens que…</em> » : il émettra la balise lui-même.</em><br><br>' +
        '<em>Les consignes sont rappelées au tuteur à chaque tour pour qu\'il ne les oublie pas en cours de séance.</em>' +
        '</div>';
      return;
    }
    stickiesListEl.innerHTML = "";
    for (const sticky of stickies) {
      const card = document.createElement("div");
      const kind = sticky.kind === "tutor" ? "tutor" : "user";
      card.className = "sticky-card sticky-" + kind +
                       (sticky.enabled === false ? " sticky-disabled" : "");
      card.dataset.stickyId = sticky.id || "";

      const head = document.createElement("div");
      head.className = "sticky-head";
      const kindIcon = kind === "tutor" ? "🤖" : "📌";
      const kindLabel = kind === "tutor" ? "Tuteur" : "Toi";
      const ts = sticky.created_at || "";
      const tsShort = (typeof formatTurnTimeShort === "function")
        ? formatTurnTimeShort(ts) : ts;
      head.innerHTML =
        `<span class="sticky-kind" title="${kindLabel}">${kindIcon} ${kindLabel}</span>` +
        `<span class="sticky-ts" title="${ts}">${tsShort}</span>`;

      const body = document.createElement("div");
      body.className = "sticky-body";
      body.textContent = sticky.text || "";
      body.title = "Double-clic pour modifier";
      body.addEventListener("dblclick", () => _editStickyInline(sticky, body));

      const actions = document.createElement("div");
      actions.className = "sticky-actions";

      // Toggle on/off
      const toggleBtn = document.createElement("button");
      toggleBtn.type = "button";
      toggleBtn.className = "sticky-toggle";
      const enabled = sticky.enabled !== false;
      toggleBtn.textContent = enabled ? "✅ Active" : "⏸ Désactivée";
      toggleBtn.title = enabled
        ? "Désactiver (le tuteur ne sera plus rappelé de cette consigne, mais elle reste dans la liste)"
        : "Réactiver";
      toggleBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        await _patchSticky(sticky.id, { enabled: !enabled });
        refreshStickies();
      });

      // Source message link
      if (sticky.source_message_id) {
        const goBtn = document.createElement("button");
        goBtn.type = "button";
        goBtn.className = "sticky-goto";
        goBtn.textContent = "↪ Voir";
        goBtn.title = "Aller à la bulle source";
        goBtn.addEventListener("click", (e) => {
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
      delBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!confirm("Supprimer cette consigne ?")) return;
        try {
          const resp = await fetch("/api/stickies/" + encodeURIComponent(sticky.id), {
            method: "DELETE",
          });
          if (resp.ok || resp.status === 204) {
            refreshStickies();
          } else {
            const err = await resp.json().catch(() => ({}));
            alert("Erreur : " + (err.error || resp.status));
          }
        } catch (e2) { alert("Erreur réseau : " + e2.message); }
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
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
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
  const finish = async (commit) => {
    if (done) return;
    done = true;
    if (commit) {
      const newText = (input.value || "").trim();
      if (newText && newText !== oldText) {
        const updated = await _patchSticky(sticky.id, { text: newText });
        if (updated) {
          refreshStickies();
          return;
        }
      }
    }
    // revert
    refreshStickies();
  };
  input.addEventListener("blur", () => finish(true));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); finish(false); }
    else if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); finish(true); }
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
    finalText = prompt(
      "Le message fait " + cleanText.length + " chars (max 200). " +
      "Modifie/raccourcis la consigne avant de l'épingler :",
      cleanText.slice(0, 197) + "…",
    );
    if (!finalText) return;
    finalText = finalText.trim();
    if (!finalText) return;
  }
  try {
    const r = await fetch("/api/stickies", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: finalText,
        source_message_id: messageId || null,
        kind: "user",
      }),
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
    // Active l'onglet pour feedback visuel
    const tab = document.querySelector('#sidebar-tabs .sb-tab[data-tab="stickies"]');
    if (tab) tab.click();
  } catch (e) {
    alert("Erreur réseau : " + e.message);
  }
}

// Chip 📌 hover sur les bulles student (= `.turn.student` dans le DOM).
// Ne pas attacher sur les bulles "marker" qui sont des transitions techniques.
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
  chip.addEventListener("click", (e) => {
    e.stopPropagation();
    const msgId = turnEl.dataset.msgId || null;
    // dataset.rawText est set sur la `.turn.student` à chaque rerender,
    // sinon fallback sur le textContent du `<div>` inner (3ᵉ enfant après
    // role + content). Pas grave si on prend du markdown brut, l'utilisateur
    // peut éditer le prompt sticky avant validation côté _createStickyFromMessage.
    const rawText = turnEl.dataset.rawText
      || (turnEl.children[1]?.textContent || "");
    _createStickyFromMessage(msgId, rawText);
  });
  turnEl.appendChild(chip);
}

// Observe le DOM pour ajouter le chip sur les nouvelles bulles student.
(function setupStickyPinChipObserver() {
  if (!dialogue) return;
  // Initial scan (au cas où des bulles existent déjà au boot, ex: restore).
  dialogue.querySelectorAll(".turn.student").forEach(_maybeAttachPinChipToStudentTurn);
  const mo = new MutationObserver((mutations) => {
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
  mo.observe(dialogue, { childList: true, subtree: true });
})();

if (stickiesRefreshBtn) stickiesRefreshBtn.addEventListener("click", refreshStickies);

// ============================================================ Stickies, modal d'import
// Permet de copier les stickies d'une autre session vers la session active.
// Vue 1 : liste des sessions. Vue 2 : stickies de la session choisie avec
// checkboxes. Bouton final → POST /api/stickies/import_from/<id>.

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
      sImportSessionsList.innerHTML =
        '<div class="sim-empty">Erreur de chargement.</div>';
      return;
    }
    const data = await r.json();
    const sessions = data.sessions || [];
    // Filtre la session courante (on importe pas vers soi-même).
    const current = activeSession?.session_id || null;
    const candidates = sessions.filter(s =>
      s.session_id !== current && (s.stickies_count || 0) > 0,
    );
    if (candidates.length === 0) {
      sImportSessionsList.innerHTML =
        '<div class="sim-empty">' +
        'Aucune autre session avec des consignes épinglées.<br><br>' +
        '<em>Une session apparaît ici dès qu\'elle contient au moins ' +
        'une consigne (manuelle ou tuteur).</em>' +
        '</div>';
      return;
    }
    sImportSessionsList.innerHTML = "";
    for (const sess of candidates) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "sim-session-item";
      const label = sess.label || sess.session_id;
      const count = sess.stickies_count || 0;
      item.innerHTML =
        `<div class="sim-session-label">${label}</div>` +
        `<div class="sim-session-meta">${count} consigne${count > 1 ? "s" : ""}` +
        (sess.started_at ? ` · ${formatTurnTimeShort(sess.started_at)}` : "") +
        `</div>`;
      item.addEventListener("click", () => _showStickiesOfSession(sess));
      sImportSessionsList.appendChild(item);
    }
  } catch (e) {
    sImportSessionsList.innerHTML =
      `<div class="sim-empty">Erreur réseau : ${e.message}</div>`;
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
      sImportStickiesList.innerHTML =
        '<div class="sim-empty">Impossible de lire cette session.</div>';
      return;
    }
    const data = await r.json();
    const stickies = (data.stickies || []).filter(s => s.enabled !== false);
    if (stickies.length === 0) {
      sImportStickiesList.innerHTML =
        '<div class="sim-empty">Cette session n\'a aucune consigne active.</div>';
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
    sImportStickiesList.innerHTML =
      `<div class="sim-empty">Erreur : ${e.message}</div>`;
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
  cbs.forEach(cb => { cb.checked = anyUnchecked; });
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
    const r = await fetch(
      "/api/stickies/import_from/" + encodeURIComponent(_sImportCurrentSessionId),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sticky_ids: ids }),
      },
    );
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

// Escape pour fermer le modal
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && sImportModal && !sImportModal.hidden) {
    _closeStickiesImportModal();
  }
});

// ============================================================ Tips & Coach marks (Phase A.10.5)
// Onglet 🎓 Astuces : liste curated d'astuces avec bouton « Voir où » qui
// déclenche un effet visuel (spotlight) sur l'élément concerné. Pattern
// classique d'onboarding (Slack, Figma, Linear).

// _spotlight(target, opts), applique un effet jaune scintillant + scroll
// vers la cible. Si la cible est un onglet du rail, bascule aussi dessus.
//   target : Element | string (sélecteur CSS)
//   opts.activateTab : bool, si target est un .sb-tab, click() avant le pulse
//   opts.scrollIntoView : bool, scroll vers l'élément (default true)
//   opts.duration : ms, durée du highlight (default ~3000)
function _spotlight(target, opts = {}) {
  let el = target;
  if (typeof target === "string") {
    el = document.querySelector(target);
  }
  if (!el || !(el instanceof Element)) {
    console.warn("_spotlight : cible introuvable", target);
    return;
  }
  // Si la cible est un onglet, on l'active d'abord (pour basculer le pane)
  if (el.classList.contains("sb-tab") && opts.activateTab !== false) {
    try { el.click(); } catch (_) {}
  }
  if (opts.scrollIntoView !== false) {
    try { el.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (_) {}
  }
  // Classe distincte pour les tabs (animation interne) vs autres éléments
  const isTab = el.classList.contains("sb-tab");
  const cls = isTab ? "sb-tab-spotlight" : "spotlight-target";
  el.classList.add(cls);
  const duration = opts.duration || 3000;
  setTimeout(() => el.classList.remove(cls), duration);
}

// Pré-remplit le textarea utilisateur avec un draft + focus.
function _prefillTextarea(text) {
  const ta = document.getElementById("user-input");
  if (!ta) return;
  if (ta.disabled) {
    alert("Lance d'abord une séance pour pouvoir taper.");
    return;
  }
  ta.value = text;
  ta.focus();
  // Trigger input event pour que les listeners (autoresize, rewrite-btn enable, etc.) réagissent
  ta.dispatchEvent(new Event("input", { bubbles: true }));
  _spotlight("#send-btn", { scrollIntoView: false });
}

// Catalogue d'astuces. Chaque astuce a :
//   title  : titre court avec emoji
//   body   : description 1-2 phrases
//   action : { label, fn }, clic = exécute fn (typiquement _spotlight + extra)
const TIPS_CATALOG = [
  // ============================================================ Phase A.10.20 : réordonné
  // BASICS, actions quotidiennes les plus fréquentes en tête.
  {
    title: "🎙 Dicter ta réponse au micro",
    body: "Le bouton 🎤 à côté du textarea capture l'audio, le transcrit via Whisper large-v3 et insère le résultat. Si tu avais déjà tapé du texte, la transcription est appendée (pas remplacée).",
    action: { label: "▶ Voir le bouton 🎤", fn: () => _spotlight("#mic-btn") },
  },
  {
    title: "⌨ Maintenir Espace pour parler (push-to-talk)",
    body: "Quand le focus n'est PAS sur un input, maintenir [Espace] active l'enregistrement micro tant que la touche est appuyée. Lâche pour stopper et envoyer la transcription.",
    action: null,
  },
  {
    title: "📷 Prendre une photo depuis ton téléphone",
    body: "Le bouton 📷 ouvre la caméra sur mobile, ou flash l'onglet 🔗 Distant sur desktop (QR/URL Tailscale). La photo arrive dans le tray d'envoi du desktop automatiquement.",
    action: { label: "▶ Voir l'onglet Distant", fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="mobile"]') },
  },
  {
    title: "✏ Éditer un message > en écrire un nouveau pour recharger le contexte",
    body: [
      "Si le tuteur dérive ou tu veux reformuler ta question avec plus de contexte, préfère éditer le message d'origine (icône ✏ au hover sur ta bulle) plutôt que renvoyer un nouveau message.",
      "Bouton « 🔄 Recharger contexte » dans l'éditeur : modifie + supprime tout ce qui suit + regénère la réponse du tuteur.",
      "Avantages : pas de tokens gaspillés sur des tours obsolètes, le tuteur repart d'un état propre, et l'historique reste lisible.",
    ],
    action: null,
  },
  {
    title: "✨ Reformuler ton brouillon avant envoi",
    body: "Le bouton ✨ ouvre 4 actions : Reformuler / Plus concis / Développer / Corriger fautes. Utile pour transformer une dictée vocale brute en réponse propre. Fonctionne aussi en mode édition de bulle.",
    action: { label: "▶ Voir le bouton ✨", fn: () => _spotlight("#rewrite-btn") },
  },
  {
    title: "🛑 Annuler la réflexion en cours du tuteur",
    body: 'Pendant que le tuteur stream, le bouton Envoyer devient ⏹ Annuler. Click = modal 2 options : "Reprendre (garder mon message)" ou "Supprimer mon message" (annule + retire la dernière bulle).',
    action: null,
  },

  // ============================================================ Carte cahier (feature centrale Découverte)
  {
    title: "📒 Carte cahier : la doctrine couleurs",
    body: [
      "Le tuteur émet des cartes « cahier » visuelles aux moments « notez ceci sur votre cahier ». Disponible dans les 3 modes : systématique en Découverte, ponctuelle en Colle (après blocage prolongé, en débrief, sur demande), ponctuelle en Guidé (correction d'erreur du script, astuce mémorisable). Fond crème, lignes Seyès, marge stylo rouge.",
      "🔵 Bleu = prose courante (défaut, ~60% du texte).",
      "🔴 Rouge = concept ou résultat à retenir absolument.",
      "🟢 Vert = exemples concrets, valeurs, ET code à recopier (fond vert pâle).",
      "⚫ Noir = formules mathématiques. Tous les rendus LaTeX ($…$ et $$…$$) dans une carte passent automatiquement en noir, c'est le rôle dédié du stylo noir.",
      "🟣 Violet surligneur = titre de la carte cahier, appliqué automatiquement.",
      "🟢 Vert surligneur = sous-titres dans le corps (titres ## / ###, lignes « Méthode : » / « Définition : » / « Théorème : »…), appliqué automatiquement.",
      "🟡 Jaune surligneur = formule vitale à mémoriser par cœur.",
      "🩷 Rose surligneur = piège, erreur classique, « attention ».",
      "Code en blocs ``` ``` : tout en vert, commentaires (-- ... / # ... / // ...) automatiquement en rouge.",
      "Limites = guides, pas absolues : certains concepts justifient d'utiliser le rouge ou le vert plusieurs fois. Évite juste le sapin-de-Noël (tout coloré).",
    ],
    action: null,
  },
  {
    title: "🎨 Tout ce que tu peux faire avec les couleurs cahier",
    body: [
      "L'onglet 🎨 Couleurs centralise toute la gestion : 4 stylos + 4 surligneurs avec preview + picker hex + bouton ↺ Reset.",
      "Cas 1, REMAP GLOBAL (rétroactif, toutes cards) : clique sur l'input couleur à droite d'un rôle (ex: rouge → orange). Toutes les cards existantes et futures prennent INSTANTANÉMENT la nouvelle teinte. Persisté dans localStorage du navigateur. Mécanique : CSS variables, aucun message touché.",
      "Cas 2, APPLIQUER À UNE SÉLECTION : (a) sélectionne un mot dans une carte cahier crème, (b) clique le bouton « 🎨 Colorier » qui apparaît dans la mini-toolbar au-dessus, (c) l'onglet 🎨 Couleurs s'ouvre avec une bannière « 🎯 Sélection active : … » : clique alors le swatch (gros « Aa » coloré à gauche de chaque rôle) pour appliquer cette couleur au mot sélectionné. Édit persisté côté serveur (PATCH).",
      "Le bouton ⌫ « Retirer le coloriage de cette sélection » dans la bannière permet de défaire un coloriage existant autour de la sélection.",
    ],
    action: {
      label: "▶ Ouvrir l'onglet 🎨 Couleurs",
      fn: () => {
        const tab = document.querySelector('#sidebar-tabs .sb-tab[data-tab="colors"]');
        if (tab) tab.click();
      },
    },
  },

  // ============================================================ Session management
  {
    title: "💬 Reprendre une session interrompue",
    body: "L'onglet Historique liste toutes tes sessions persistées. Clic = soit reprendre (replay du transcript), soit ouvrir en lecture seule. Le bot peut reprendre une session vieille de plusieurs jours.",
    action: { label: "▶ Voir l'onglet Historique", fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="history"]') },
  },
  {
    title: "📊 Surveiller ton quota Pro Max",
    body: "L'onglet Quota affiche en temps réel ta consommation : session 5h, hebdo 7j Opus, hebdo Sonnet, overage. Cookie chiffré DPAPI, refresh toutes les 30s.",
    action: { label: "▶ Voir l'onglet Quota", fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="quota"]') },
  },
  {
    title: "📄 Exporter la séance en PDF + Markdown",
    body: "Le bouton 📄 Récap dans le footer de la sidebar génère à tout moment un ZIP avec ton transcript complet (PDF lisible + MD léger), incluant les consignes épinglées et le récap de séance si la phase débrief est engagée.",
    action: { label: "▶ Voir le bouton 📄 Récap", fn: () => _spotlight("#export-recap-btn") },
  },

  // ============================================================ Notes, consignes, photos, docs
  {
    title: "💾 Sauvegarder une phrase comme note (surligneur orange)",
    body: [
      "Sélectionne du texte dans n'importe quelle bulle (Compagnon ou toi-même, dans une cahier-card ou pas, n'importe où dans le dialogue).",
      "Un popup apparaît avec 4 actions : 💾 Sauvegarder, 📋 Citer, 🤔 Expliquer, 📝 Copier.",
      "Click 💾 → la sélection est enregistrée dans l'onglet 🔖 Notes ET marquée d'un surligneur 🟠 orange dans la bulle pour retrouver visuellement ce que t'as save (couleur distincte du jaune cahier pour éviter la confusion).",
      "La couleur du surligneur 💾 est configurable depuis l'onglet 🎨 Couleurs cahier (ligne « Surligneur 💾 Notes save »). Tu peux la changer pour n'importe quelle teinte qui te parle.",
    ],
    action: { label: "▶ Voir l'onglet Notes", fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="notes"]') },
  },
  {
    title: "📌 Épingler une consigne à respecter",
    body: "Le tuteur oublie parfois une consigne donnée il y a 30 tours. Passe la souris sur une de tes bulles → clique 📌 pour l'épingler. Rappelée au tuteur à CHAQUE tour suivant.",
    action: { label: "▶ Voir l'onglet Consignes", fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="stickies"]') },
  },
  {
    title: "🤖 Demander au tuteur de retenir lui-même",
    body: 'Si tu dis "retiens que je dois toujours écrire la signature avant la fonction", le tuteur émet la balise <<<REMEMBER>>> qui s\'ajoute aux consignes épinglées automatiquement.',
    action: { label: "▶ Pré-remplir un draft", fn: () => _prefillTextarea("Retiens que ") },
  },
  {
    title: "📋 Importer des consignes d'une autre session",
    body: "Dans l'onglet Consignes, le bouton 📋 Importer ouvre un modal 2 étapes : choisis la session source, coche les consignes à copier. Utile pour reprendre des règles établies dans une séance précédente.",
    action: { label: "▶ Ouvrir l'onglet Consignes", fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="stickies"]') },
  },
  {
    title: "📸 Revoir les photos envoyées",
    body: "Toutes les photos que tu as envoyées au tuteur pendant la séance sont archivées dans l'onglet Photos : vignettes cliquables (lightbox), tri anti-chrono, suppression individuelle.",
    action: { label: "▶ Voir l'onglet Photos", fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="photos"]') },
  },
  {
    title: "🏷 Photos auto-renommées par OCR",
    body: "Quand tu envoies une photo en mode colle/découverte format photos/mixte, le tuteur OCR via Gemini Flash 2.5 et renomme automatiquement le fichier en YYYY-MM-DD_HHMM_<type>_<slug>.ext. Survole une vignette pour voir le nom formaté.",
    action: { label: "▶ Voir l'onglet Photos", fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="photos"]') },
  },
  {
    title: "📚 Lire l'énoncé / corrigé / script pendant la séance",
    body: "L'onglet Docs montre le PDF rasterisé page par page. Quand tu navigues une page, le tuteur reçoit en préfixe « [Contexte lecture : page N/M] » pour qu'il sache ce que tu as sous les yeux.",
    action: { label: "▶ Voir l'onglet Docs", fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="corrige"]') },
  },

  // ============================================================ Mode switching
  {
    title: "🔀 Basculer le format de la séance",
    body: "Tape /oral, /photos ou /mixte dans le textarea pour changer le format en cours de séance. Le tuteur acquitte d'un fragment court et adapte sa posture (suggérer/exiger photo, ou s'en passer).",
    action: { label: "▶ Pré-remplir /mixte", fn: () => _prefillTextarea("/mixte") },
  },
  {
    title: "📘 Basculer l'ancrage corrigé",
    body: "Tape /strict (corrigé fait foi), /consultatif (corrigé visible mais discutable) ou /aucun (sans corrigé). Utile quand le corrigé officiel a une erreur et que le tuteur tourne en boucle dessus.",
    action: { label: "▶ Pré-remplir /consultatif", fn: () => _prefillTextarea("/consultatif") },
  },
  {
    title: "🎲 Mode « Sans énoncé » (avec prudence)",
    body: "Coche 🎲 dans le form de lancement → le tuteur ignore l'énoncé du disque et invente ses propres questions. Utile pour la révision globale d'un thème. Option PONCTUELLE par séance (décochée par défaut à chaque boot).",
    action: null,
  },
  {
    title: "💡 Mode « Sujet libre » (hors COURS/)",
    body: 'Coche 💡 et décris ton sujet (« apprendre Python ») → le tuteur s\'appuie uniquement sur ses connaissances LLM, sans matériel COURS. Mode guidé indisponible. Bandeau jaune au clic pour t\'avertir.',
    action: null,
  },

  // ============================================================ Troubleshooting (bottom)
  {
    title: "⚠ « 503 UNAVAILABLE » ou « high demand » : c'est du côté serveur",
    body: [
      "Quand un moteur (typiquement Gemini) renvoie 503 UNAVAILABLE / overloaded / high demand, c'est une surcharge temporaire côté Google. Pas un bug local.",
      "Deux options : (1) attendre 30s-2min, ces spikes sont courts ; (2) basculer sur un autre moteur via le sélecteur en haut (qui clignote en orange quand l'erreur tombe).",
      "Si ça se répète sur la journée : vérifier https://status.cloud.google.com/.",
    ],
    action: { label: "▶ Voir le sélecteur de moteur", fn: () => _spotlight("#engine-switcher") },
  },
  {
    title: "⚠ « 503 UNAVAILABLE » ou « high demand » : c'est du côté serveur",
    body:
      "Quand un moteur (typiquement Gemini) renvoie 503 UNAVAILABLE / overloaded / high demand, " +
      "c'est une surcharge temporaire côté Google (ou autre provider). Pas un bug local, le reload de " +
      "contexte n'y changera rien. Deux options : (1) attendre 30s-2min, ces spikes sont courts ; " +
      "(2) basculer sur un autre moteur via le sélecteur en haut (qui clignote en orange quand l'erreur " +
      "tombe). Si ça se répète sur la journée, vérifie https://status.cloud.google.com/.",
    action: {
      label: "▶ Voir le sélecteur de moteur",
      fn: () => _spotlight("#engine-switcher"),
    },
  },
  {
    title: "✏ Éditer un message > en écrire un nouveau pour recharger le contexte",
    body:
      "Si le tuteur dérive ou tu veux reformuler ta question avec plus de contexte, préfère " +
      "éditer le message d'origine (icône ✏ au hover sur ta bulle) plutôt que renvoyer un nouveau " +
      "message à la suite. Bouton « 🔄 Recharger contexte » dans l'éditeur : modifie + supprime " +
      "tout ce qui suit + regénère la réponse du tuteur. Avantages : pas de tokens gaspillés sur des " +
      "tours obsolètes, le tuteur repart d'un état propre, et l'historique reste lisible. " +
      "Empile-trop-de-messages-pour-corriger = saturation cognitive ET token cost.",
    action: null,
  },
  // ============================================================ Phase A.10.13f
  // Nouvelles features récentes (en haut, plus visibles).
  {
    title: "📄 Exporter la séance en PDF + Markdown",
    body: "Le bouton 📄 Récap dans le footer de la sidebar génère à tout moment un ZIP avec ton transcript complet (PDF lisible + MD léger), incluant les consignes épinglées et le récap de séance si la phase débrief est engagée. Pratique avant un examen, pour audit, ou pour le futur portfolio.",
    action: {
      label: "▶ Voir le bouton 📄 Récap",
      fn: () => _spotlight("#export-recap-btn"),
    },
  },
  {
    title: "🏷 Photos auto-renommées par OCR",
    body: "Quand tu envoies une photo en mode colle/découverte format photos/mixte, le tuteur OCR via Gemini Flash 2.5 et renomme automatiquement le fichier en YYYY-MM-DD_HHMM_<type>_<slug>.ext. Survole une vignette dans l'onglet 📸 Photos pour voir le nom formaté.",
    action: {
      label: "▶ Voir l'onglet Photos",
      fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="photos"]'),
    },
  },
  {
    title: "📌 Demander au tuteur de retenir une consigne",
    body: 'Dis "retiens que je dois toujours écrire la signature avant la fonction" → le tuteur émet la balise <<<REMEMBER>>> qui s\'ajoute aux consignes épinglées. Elle sera rappelée au tuteur à CHAQUE tour suivant (mémoire persistante de séance).',
    action: {
      label: "▶ Pré-remplir un draft",
      fn: () => _prefillTextarea("Retiens que "),
    },
  },
  {
    title: "🎲 Mode « Sans énoncé » (avec prudence)",
    body: "Coche 🎲 dans le form de lancement → le tuteur ignore l'énoncé du disque et invente ses propres questions. Utile pour la révision globale d'un thème. Un bandeau jaune apparaît quand tu coches pour te rappeler la conséquence. C'est une option PONCTUELLE par séance (décochée par défaut à chaque boot).",
    action: null,
  },
  {
    title: "💡 Mode « Sujet libre » (hors COURS/)",
    body: 'Coche 💡 et décris ton sujet (« apprendre Python ») → le tuteur s\'appuie uniquement sur ses connaissances LLM, sans matériel COURS. Mode guidé indisponible. Bandeau jaune au clic pour t\'avertir.',
    action: null,
  },
  // ============================================================ Existant (A.10.5)
  {
    title: "📷 Prendre une photo depuis ton téléphone",
    body: "Connecte ton téléphone via Tailscale ou un tunnel Cloudflare, ouvre l'URL générée dans l'onglet Distant, prends une photo : elle apparaît automatiquement dans le tray d'envoi du desktop.",
    action: {
      label: "▶ Voir l'onglet Distant",
      fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="mobile"]'),
    },
  },
  {
    title: "📌 Épingler une consigne à respecter",
    body: "Le tuteur oublie parfois une consigne donnée il y a 30 tours. Passe la souris sur une de tes bulles dans le fil → clique sur 📌 pour l'épingler. Elle sera rappelée au tuteur à CHAQUE tour suivant.",
    action: {
      label: "▶ Voir l'onglet Consignes",
      fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="stickies"]'),
    },
  },
  {
    title: "🤖 Demander au tuteur de retenir lui-même",
    body: 'Si tu dis "retiens que je dois toujours écrire la signature avant la fonction", le tuteur émet la balise <<<REMEMBER>>> qui s\'ajoute aux consignes épinglées automatiquement.',
    action: {
      label: "▶ Pré-remplir un draft",
      fn: () => _prefillTextarea("Retiens que "),
    },
  },
  {
    title: "💾 Sauvegarder une phrase comme note",
    body: "Sélectionne du texte dans n'importe quelle bulle (à toi ou au tuteur), un popup apparaît : 💾 Sauvegarder, 📋 Citer, 🤔 Expliquer, 📝 Copier. Les notes vivent dans l'onglet Notes.",
    action: {
      label: "▶ Voir l'onglet Notes",
      fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="notes"]'),
    },
  },
  {
    title: "📸 Revoir les photos envoyées",
    body: "Toutes les photos que tu as envoyées au tuteur pendant la séance sont archivées dans l'onglet Photos : vignettes cliquables (lightbox), tri anti-chrono, suppression individuelle.",
    action: {
      label: "▶ Voir l'onglet Photos",
      fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="photos"]'),
    },
  },
  {
    title: "✨ Reformuler ton brouillon avant envoi",
    body: "Le bouton ✨ à côté de 📎 ouvre un menu : Reformuler (plus clair), Plus concis, Développer, Corriger fautes. Utile pour transformer une dictée vocale brute en réponse propre.",
    action: {
      label: "▶ Voir le bouton ✨",
      fn: () => _spotlight("#rewrite-btn"),
    },
  },
  {
    title: "🎙 Dicter ta réponse au micro",
    body: "Le bouton 🎤 à côté du textarea capture l'audio, le transcrit via Whisper large-v3 et insère le résultat dans le textarea. Tu peux ensuite l'éditer ou le passer dans ✨ avant d'envoyer.",
    action: {
      label: "▶ Voir le bouton 🎤",
      fn: () => _spotlight("#mic-btn"),
    },
  },
  {
    title: "🔀 Basculer le format de la séance",
    body: "Tape /oral, /photos ou /mixte dans le textarea pour changer le format en cours de séance. Le tuteur acquitte d'un fragment court et adapte sa posture (suggérer/exiger photo, ou s'en passer).",
    action: {
      label: "▶ Pré-remplir /mixte",
      fn: () => _prefillTextarea("/mixte"),
    },
  },
  {
    title: "📘 Basculer l'ancrage corrigé",
    body: "Tape /strict (corrigé fait foi), /consultatif (corrigé visible mais discutable) ou /aucun (sans corrigé). Utile quand le corrigé officiel a une erreur et que le tuteur tourne en boucle dessus.",
    action: {
      label: "▶ Pré-remplir /consultatif",
      fn: () => _prefillTextarea("/consultatif"),
    },
  },
  {
    title: "📚 Lire l'énoncé / corrigé / script pendant la séance",
    body: "L'onglet Docs montre le PDF rasterisé page par page. Quand tu navigues une page, le tuteur reçoit en préfixe « [Contexte lecture : page N/M] » pour qu'il sache ce que tu as sous les yeux.",
    action: {
      label: "▶ Voir l'onglet Docs",
      fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="corrige"]'),
    },
  },
  {
    title: "💬 Reprendre une session interrompue",
    body: "L'onglet Historique liste toutes tes sessions persistées. Clic = soit reprendre (resume avec replay du transcript), soit ouvrir en lecture seule. Le bot peut reprendre une session vieille de plusieurs jours.",
    action: {
      label: "▶ Voir l'onglet Historique",
      fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="history"]'),
    },
  },
  {
    title: "📋 Importer des consignes d'une autre session",
    body: "Dans l'onglet Consignes, le bouton 📋 Importer ouvre un modal 2 étapes : choisis la session source, coche les consignes à copier. Utile pour reprendre des règles établies dans une séance précédente.",
    action: {
      label: "▶ Ouvrir l'onglet Consignes",
      fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="stickies"]'),
    },
  },
  {
    title: "📊 Surveiller ton quota Pro Max",
    body: "L'onglet Quota affiche en temps réel ta consommation : session 5h, hebdo 7j Opus, hebdo Sonnet, overage. Cookie chiffré DPAPI, refresh toutes les 30s.",
    action: {
      label: "▶ Voir l'onglet Quota",
      fn: () => _spotlight('#sidebar-tabs .sb-tab[data-tab="quota"]'),
    },
  },
  {
    title: "⌨ Maintenir Espace pour parler",
    body: "Quand le focus n'est pas sur un input, maintenir [Espace] active l'enregistrement micro tant que la touche est appuyée. Lâche pour stopper et envoyer la transcription.",
    action: null,
  },
  {
    title: "🛑 Annuler la réflexion en cours du tuteur",
    body: 'Pendant que le tuteur stream sa réponse, le bouton Envoyer devient ⏹ Annuler. Click = modal 2 options : "Reprendre (garder mon message)" ou "Supprimer mon message" (annule + retire la dernière bulle).',
    action: null,
  },
];

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
    // Phase A.10.20 : body supporte string (1 paragraphe) ou array de
    // strings (plusieurs paragraphes/lignes). Permet aux astuces denses
    // (ex: doctrine couleurs cahier) d'être lisibles au lieu d'un pavé
    // d'un seul bloc.
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
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        try { tip.action.fn(); } catch (err) {
          console.warn("tip action a planté :", err);
        }
      });
      card.appendChild(btn);
    }
    list.appendChild(card);
  }
}

// Render à l'init (le script charge en bas du body, DOMContentLoaded
// peut déjà être passé, d'où le branch sur readyState).
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    try { renderTipsList(); } catch (_) {}
    try { _loadCahierColorsFromStorage(); } catch (_) {}
    try { renderColorsPanel(); } catch (_) {}
  });
} else {
  try { renderTipsList(); } catch (_) {}
  try { _loadCahierColorsFromStorage(); } catch (_) {}
  try { renderColorsPanel(); } catch (_) {}
}

// ============================================================ Onglet 🎨 Couleurs (Phase A.10.21)
// Permet à l'utilisateur de remapper les couleurs cahier rétroactivement.
// Le changement passe par CSS variables (`document.documentElement.style.
// setProperty('--cahier-c-rouge', '#xxx')`), ce qui répercute INSTANTANÉMENT
// sur toutes les cartes existantes (passées et futures) sans toucher au
// texte des messages. Préférences persistées dans localStorage.

// Phase A.10.22 : unification : sélection vivante au moment où l'user
// clique « 🎨 Colorier » dans la sélection-toolbar. Stockée globalement
// pour que l'onglet Couleurs sache à quoi appliquer le swatch cliqué.
// Expire après 60s (sécurité, l'user peut être parti faire autre chose).
let _pendingColorSelection = null;
let _pendingColorSelectionExpiry = 0;

function _openColorsTabForSelection(info) {
  _pendingColorSelection = {
    text: info.text,
    bubbleEl: info.bubbleEl,
    messageId: info.messageId,
  };
  _pendingColorSelectionExpiry = Date.now() + 60_000;
  // Bascule l'onglet Couleurs
  const tab = document.querySelector('#sidebar-tabs .sb-tab[data-tab="colors"]');
  if (tab) tab.click();
  // Re-render le panel (pour afficher la banner « sélection détectée »)
  renderColorsPanel();
  _hideSelectionToolbar();
}

function _getPendingColorSelection() {
  if (!_pendingColorSelection) return null;
  if (Date.now() > _pendingColorSelectionExpiry) {
    _pendingColorSelection = null;
    return null;
  }
  // Vérifie que la bulle existe toujours dans le DOM
  if (!document.body.contains(_pendingColorSelection.bubbleEl)) {
    _pendingColorSelection = null;
    return null;
  }
  return _pendingColorSelection;
}

const _CAHIER_COLOR_DEFAULTS = {
  // Stylos : valeur hex directe
  "cahier-c-bleu":   { kind: "stylo", default: "#1d4ed8", label: "Stylo bleu (défaut prose)" },
  "cahier-c-rouge":  { kind: "stylo", default: "#b91c1c", label: "Stylo rouge (concept à retenir)" },
  "cahier-c-vert":   { kind: "stylo", default: "#15803d", label: "Stylo vert (exemples + code)" },
  "cahier-c-noir":   { kind: "stylo", default: "#111111", label: "Stylo noir (formules LaTeX / maths)" },
  // Surligneurs : triplet RGB stocké comme hex pour l'UI, converti en `r,g,b` pour CSS var
  "cahier-hl-jaune":  { kind: "hl", default: "#fde047", label: "Surligneur jaune (formule vitale)" },
  "cahier-hl-vert":   { kind: "hl", default: "#86efac", label: "Surligneur vert (sous-titres : titres ## / ###, lignes Méthode/Définition…)" },
  "cahier-hl-rose":   { kind: "hl", default: "#f9a8d4", label: "Surligneur rose (piège)" },
  "cahier-hl-violet": { kind: "hl", default: "#c4b5fd", label: "Surligneur violet (titre de la carte cahier)" },
  // Phase A.10.27 : surligneur des notes sauvegardées (💾 Save). Couleur
  // par défaut ORANGE (distinct du jaune cahier). Appliqué sur les bulles
  // via `mark.saved-note-mark` à n'importe quel endroit du dialogue
  // (pas seulement dans .cahier-card).
  "note-saved-hl":    { kind: "hl", default: "#fb923c", label: "Surligneur 💾 Notes save (n'importe où dans le dialogue)" },
};

const _CAHIER_COLORS_STORAGE_KEY = "compagnon_cahier_colors_v1";

function _hexToRgbTriplet(hex) {
  const m = hex.replace("#", "").match(/^([a-f0-9]{2})([a-f0-9]{2})([a-f0-9]{2})$/i);
  if (!m) return "0, 0, 0";
  return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)].join(", ");
}

function _setCahierCSSVar(name, hex) {
  // Phase A.10.21 : renommé depuis `_applyCahierColor` (collision avec le
  // helper sélection-toolbar de Phase A.10.20). Applique une couleur sur
  // la CSS variable correspondante. Stylos : valeur hex directe.
  // Surligneurs : triplet RGB pour rgba() avec alpha.
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
  } catch (_) { /* corrupt → ignore */ }
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
  // Lit les valeurs en cours (depuis CSS var calculée OU défaut)
  let stored = {};
  try {
    const raw = localStorage.getItem(_CAHIER_COLORS_STORAGE_KEY);
    if (raw) stored = JSON.parse(raw) || {};
  } catch (_) {}
  list.innerHTML = "";

  // Phase A.10.22 : bannière « sélection active » si l'user a cliqué
  // « 🎨 Colorier » dans la sélection-toolbar avant d'arriver ici.
  // Permet d'appliquer une couleur en cliquant sur un swatch.
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
    // Bouton ⌫ clear ponctuel : retire le coloriage autour de la sélection
    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "colors-selection-clear";
    clearBtn.textContent = "⌫ Retirer le coloriage de cette sélection";
    clearBtn.addEventListener("click", () => {
      _applyCahierColor({
        text: pending.text,
        bubbleEl: pending.bubbleEl,
        messageId: pending.messageId,
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
        // Le name est par ex "cahier-c-rouge" → tag = "rouge"
        // ou "cahier-hl-jaune" → tag = "hl-jaune"
        const tag = name.replace(/^cahier-/, "");
        _applyCahierColor({
          text: pending.text,
          bubbleEl: pending.bubbleEl,
          messageId: pending.messageId,
        }, tag);
        _pendingColorSelection = null;
        // Re-render pour cacher la bannière
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
      // Update sample preview
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
  // Reset button
  const resetBtn = document.getElementById("colors-reset-btn");
  if (resetBtn && !resetBtn.dataset.bound) {
    resetBtn.dataset.bound = "1";
    resetBtn.addEventListener("click", () => {
      if (!confirm("Reset toutes les couleurs cahier aux valeurs par défaut ?")) return;
      try { localStorage.removeItem(_CAHIER_COLORS_STORAGE_KEY); } catch (_) {}
      // Restore CSS vars to default
      for (const [name, meta] of Object.entries(_CAHIER_COLOR_DEFAULTS)) {
        _setCahierCSSVar(name, meta.default);
      }
      renderColorsPanel();
    });
  }
}

// ============================================================ Cancel stream (Phase v15.7.21)
// Bouton ⏹ qui apparaît à la place de Send pendant que le Compagnon
// stream sa réponse. Click → modal 2 options :
//   - Reprendre (garder mon message) : annule juste le stream LLM, le
//     message student reste dans le transcript. User peut renvoyer un
//     message ou reformuler.
//   - Supprimer mon message : annule + retire la dernière bulle student
//     du DOM ET du transcript backend. « Comme si je n'avais rien envoyé. »
//
// Note : le sub-process LLM (CLI / API) peut continuer à tourner en
// background quelques secondes après le cancel. On accepte le coût
// pour la simplicité (vs subprocess.kill() qui demanderait un check
// par moteur). L'important est que le user voie l'arrêt immédiatement
// côté UI.

function setStreamingUI(streaming) {
  if (!sendBtn) return;
  if (streaming) {
    sendBtn.dataset.originalText = sendBtn.textContent;
    sendBtn.textContent = "⏹ Annuler";
    sendBtn.classList.add("cancel-mode");
    sendBtn.title = "Annuler la réflexion du Compagnon";
    // Disable bouton media/photo/rewrite pendant le stream, pas de
    // sens d'attacher de nouveaux fichiers ou de reformuler tant que
    // le tuteur n'a pas fini.
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
  // action ∈ {"resume", "delete_last_user"}
  if (!isStreamingActive()) return;
  // Ferme le SSE côté client AVANT d'envoyer le POST, pas la peine de
  // continuer à écouter pendant que le serveur se prépare à raccrocher.
  try { currentEventSource.close(); } catch (_) {}
  currentEventSource = null;
  setStreamingUI(false);
  stopThinkingIndicator();
  // Si action = delete_last_user : retire aussi la dernière bulle
  // student du DOM. Le backend va de son côté retirer du transcript.
  if (action === "delete_last_user") {
    const studentBubbles = dialogue.querySelectorAll(".turn.student");
    if (studentBubbles.length > 0) {
      try {
        const last = studentBubbles[studentBubbles.length - 1];
        last.remove();
      } catch (_) {}
    }
  }
  // Retire la bulle Compagnon partielle dans tous les cas (elle n'aura
  // jamais de fin propre).
  if (currentClaudeTurn && currentClaudeTurn.parentElement) {
    try { currentClaudeTurn.parentElement.remove(); } catch (_) {}
  }
  currentClaudeTurn = null;
  currentClaudeRawText = "";
  // Notifie le backend (best-effort, ne bloque pas l'UI si fail)
  try {
    await fetch("/api/cancel_stream", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({action}),
    });
  } catch (e) {
    console.warn("cancel_stream POST échec :", e);
  }
}

function openCancelStreamModal() {
  // Modal simple en JS pur (pas besoin de HTML pré-existant, on crée
  // à la volée et on retire au close).
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
  const close = () => { try { modal.remove(); } catch (_) {} };
  modal.querySelector("#csm-resume").addEventListener("click", () => {
    cancelStream("resume");
    close();
  });
  modal.querySelector("#csm-delete").addEventListener("click", () => {
    cancelStream("delete_last_user");
    close();
  });
  modal.querySelector("#csm-back").addEventListener("click", close);
  // Click outside = back
  modal.addEventListener("click", (e) => {
    if (e.target === modal) close();
  });
}

function streamResponse() {
  if (currentEventSource) currentEventSource.close();
  currentClaudeTurn = appendTurn("claude", "");
  // Pendant le streaming, le message n'est pas encore dans le transcript
  // backend, on cache le bouton 🗑 via la classe is-streaming.
  if (currentClaudeTurn && currentClaudeTurn.parentElement) {
    currentClaudeTurn.parentElement.classList.add("is-streaming");
  }
  currentClaudeRawText = "";
  // Indicateur « réflexion en cours » avec timer (Phase A.7.2 v6.3).
  // Attente typique entre clic Lancer/Envoyer et 1ᵉʳ chunk de Claude :
  // 3-15 s selon engine et taille du contexte. Sans feedback, l'écran
  // reste vide → on dirait que c'est planté. Le indicator est attaché
  // à la bulle Claude vide et retiré dès le 1ᵉʳ chunk text.
  startThinkingIndicator(currentClaudeTurn);
  // Phase v15.7.21 : affiche le bouton ⏹ Annuler pendant le stream.
  setStreamingUI(true);
  const es = new EventSource("/api/stream_response");
  currentEventSource = es;
  es.addEventListener("text", (e) => {
    const chunk = JSON.parse(e.data);
    stopThinkingIndicator();
    // Accumule le raw text et re-rend en markdown à chaque chunk.
    // Coût : un re-render complet par chunk (~2-5 ms pour des réponses
    // ≤ 5 KB). Tradoff acceptable pour avoir le rendu markdown live
    // (gras, listes, code) au lieu du `**texte brut**` cassé.
    currentClaudeRawText += chunk;
    currentClaudeTurn.innerHTML = renderMarkdown(currentClaudeRawText);
    dialogue.scrollTop = dialogue.scrollHeight;
  });
  es.addEventListener("tts", (e) => {
    // Phase A : pas de TTS audio (Edge TTS / Piper en Phase B).
    // On marque la phrase TTS visuellement.
    const chunk = JSON.parse(e.data);
    const span = document.createElement("span");
    span.style.fontWeight = "600";
    span.textContent = chunk;
    currentClaudeTurn.appendChild(span);
  });
  es.addEventListener("suggested_edit", (e) => {
    // Phase A.7 lecture : Claude propose une correction d'un fichier perso.
    // On affiche un card avec le diff et un bouton Appliquer.
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
    setStreamingUI(false);  // Phase v15.7.21
    stopThinkingIndicator();
    finalizeClaudeTurn();
    respondingToSlideMeta = false;  // reset garde-fou anti-cascade
    finishSession();
  });
  // Phase v15.7.21 : server a confirmé l'annulation. Le SSE ferme,
  // on retire la bulle Compagnon partielle qui n'aura jamais de fin.
  es.addEventListener("cancelled", () => {
    es.close();
    currentEventSource = null;
    setStreamingUI(false);
    stopThinkingIndicator();
    if (currentClaudeTurn && currentClaudeTurn.parentElement) {
      try { currentClaudeTurn.parentElement.remove(); } catch (_) {}
    }
    currentClaudeTurn = null;
    currentClaudeRawText = "";
    respondingToSlideMeta = false;
  });
  es.addEventListener("final_text", (e) => {
    // Phase v15 : le backend a appliqué les filtres anti-dérive (role
    // hijacking, récitation, balise mal placée) et nous pousse le texte
    // filtré. On remplace la bulle qui a été streamée brute pour que
    // l'utilisateur ne voit pas le texte buggé à l'écran.
    let payload;
    try { payload = JSON.parse(e.data); } catch (_) { return; }
    const filteredText = (payload && payload.text) || "";
    const stats = (payload && payload.stats) || {};
    if (!currentClaudeTurn) return;
    currentClaudeRawText = filteredText;
    if (!filteredText.trim()) {
      // Filtré entièrement (le tuteur a dérivé d'emblée). On affiche un
      // marker discret au lieu d'une bulle vide.
      currentClaudeTurn.innerHTML =
        '<em style="color:var(--fg-dim);font-size:0.9em;">' +
        '⚠ Réponse filtrée (dérive détectée). Réessayez via 🔄 Recharger contexte.' +
        '</em>';
    } else {
      currentClaudeTurn.innerHTML = renderMarkdown(filteredText);
      if (currentClaudeTurn.parentElement) {
        currentClaudeTurn.parentElement.dataset.rawText = filteredText;
      }
    }
    console.info(
      "output_filters: réponse nettoyée, role=%d recited=%d misplaced_next_slide=%d",
      stats.role_hijacking_lines_removed || 0,
      stats.recited_paragraphs_removed || 0,
      stats.misplaced_next_slide_removed || 0,
    );
  });
  es.addEventListener("next_slide", () => {
    // Auto-advance piloté par le tuteur (mode guidé). Le tuteur a émis
    // <<<NEXT_SLIDE>>> en jugeant la slide acquise, on laisse 1.5 s à
    // l'étudiant pour lire la fin de la réponse, puis on avance.
    if (activeMode !== "guidé" || !guidedSlides.length) return;
    if (guidedIndex >= guidedSlides.length - 1) return;  // dernière slide
    if (slideTransitionLocked()) {
      console.warn("next_slide ignoré, cooldown actif (cascade évitée)");
      return;
    }
    if (lastClaudeBubbleHasPendingQuestion()) {
      // Garde-fou : si le tuteur vient de poser une question, on ne
      // doit pas avancer la slide automatiquement, l'étudiant doit
      // avoir le temps de répondre.
      console.warn("next_slide ignoré, question pendante du tuteur");
      appendTurn("system",
        "⚠ Transition auto bloquée : le tuteur a posé une question. " +
        "Réponds d'abord, puis tu pourras avancer (➡ ou tuteur).");
      return;
    }
    const idxAtEmit = guidedIndex;
    setTimeout(() => {
      if (guidedIndex !== idxAtEmit) return;
      if (slideTransitionLocked()) return;
      if (lastClaudeBubbleHasPendingQuestion()) return;  // double check
      gotoNextSlide("tuteur");
      markSlideTransition();
    }, 1500);
  });
  es.addEventListener("show_doc", (e) => {
    // Mode guidé : le tuteur prend le contrôle du panneau Docs pour
    // afficher une page précise (énoncé/corrigé/script). Payload :
    //   {kind: "enonce"|"correction"|"script", page: int, exo?: str}
    // Phase Z.8.4 : ajout du champ optionnel `exo` pour cibler le bon
    // corrigé quand il y en a plusieurs (1 par exercice). Avant ce fix,
    // SHOW_DOC ouvrait toujours le 1ᵉʳ corrigé matchant le kind, donc
    // « page 10 du corrigé ex 3 » ouvrait silencieusement le corrigé ex 1.
    if (!correctionsList.length) return;
    let payload;
    try { payload = JSON.parse(e.data); } catch (_) { return; }
    const kind = (payload && payload.kind) || "";
    const page = (payload && payload.page) || 1;
    const exoTarget = payload && payload.exo != null ? String(payload.exo) : null;
    const targetIdx = _findDocIdx(kind, exoTarget);
    if (targetIdx < 0) {
      console.warn("show_doc: aucun doc kind=%s exo=%s", kind, exoTarget);
      return;
    }
    setTimeout(() => {
      jumpToCorrigePage(page, kind, { idx: targetIdx });
      const item = correctionsList[targetIdx];
      const total = (item.pages || []).length;
      const safePage = Math.min(Math.max(1, page), Math.max(1, total));
      const kindLbl = _kindLabelFr(kind).toLowerCase();
      appendTurn(
        "system",
        `🤖 Le tuteur affiche la page ${safePage}/${total} ` +
        `du ${kindLbl} « ${item.label} ».`
      );
    }, 800);
  });
  es.addEventListener("goto_slide", (e) => {
    // Saut arbitraire piloté par le tuteur (mode guidé). Le tuteur a émis
    // <<<GOTO_SLIDE>>>{"n": N}<<<END>>> pour ramener l'étudiant à une slide
    // précédente (boucle arrière sur un concept loupé) ou avancer de
    // plusieurs slides d'un coup. Validé côté front : n doit être dans
    // [1, guidedSlides.length].
    if (activeMode !== "guidé" || !guidedSlides.length) return;
    let payload;
    try { payload = JSON.parse(e.data); } catch (_) { return; }
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
      showGuidedSlide(n - 1, /*announceToClaude=*/true, "tuteur");
      markSlideTransition();
    }, 1500);
  });
  // Phase A.10.13a : les listeners SSE `invented_pdf_started/ready/error`
  // ont été retirés (mode invented PDF supprimé).

  // Phase A.10 : le tuteur a émis <<<REMEMBER>>>{"text":"..."}<<<END>>>,
  // le backend a persisté + nous remonte la nouvelle sticky. Toast + refresh.
  es.addEventListener("sticky_added", (e) => {
    let sticky;
    try { sticky = JSON.parse(e.data); } catch (_) { return; }
    if (!sticky || !sticky.text) return;
    if (typeof _flashSelectionFeedback === "function") {
      const preview = sticky.text.length > 60
        ? sticky.text.slice(0, 57) + "…" : sticky.text;
      _flashSelectionFeedback("📌 Consigne ajoutée par le tuteur : « " + preview + " »");
    }
    if (typeof refreshStickies === "function") refreshStickies();
  });
  es.addEventListener("done", () => {
    es.close();
    currentEventSource = null;
    setStreamingUI(false);  // Phase v15.7.21
    stopThinkingIndicator();
    finalizeClaudeTurn();
    respondingToSlideMeta = false;  // reset garde-fou anti-cascade
    // Phase A.10.13c : refresh sommaire dynamique après chaque réponse
    // tuteur (l'extracteur backend a peut-être ajouté des entries).
    if (typeof refreshDynamicOutline === "function") {
      try { refreshDynamicOutline(); } catch (_) {}
    }
  });
  es.addEventListener("error", (e) => {
    let info = ""; let engineFromEvent = "";
    try {
      const parsed = e.data ? JSON.parse(e.data) : null;
      info = parsed ? (parsed.message || parsed.detail || "") : "";
      engineFromEvent = parsed ? (parsed.engine || "") : "";
    } catch (_) {}
    respondingToSlideMeta = false;  // reset garde-fou anti-cascade
    stopThinkingIndicator();
    // Phase v15.6.4 : si l'erreur ressemble à un problème de moteur
    // (solde / TPM / contexte), on formate en FR explicite avec une
    // suggestion d'action plutôt qu'un dump SDK brut.
    const looksLikeQuota = /402|413|insufficient|too.large|tokens per minute|context.length|rate.limit/i.test(info);
    // Phase A.10.18 : détecte aussi les indisponibilités upstream
    // (Gemini surcharge HTTP 503, model overloaded, etc.) qu'on n'arrange
    // pas côté code mais où basculer de moteur règle le problème
    // immédiatement. User : « 503 UNAVAILABLE. This model is currently
    // experiencing high demand ».
    const looksLikeUpstreamUnavailable = /\b50[234]\b|UNAVAILABLE|high.demand|overload|temporarily|service.unavailable/i.test(info);
    if (looksLikeQuota) {
      const fr = formatQuotaErrorFr(engineFromEvent || "?", info);
      const sysMsg = `${fr.title}\n\n${fr.cause}\n\n${fr.suggestion}\n\n` +
                     `Détail technique : ${(info || "").slice(0, 250)}`;
      appendTurn("system", sysMsg);
      flashEngineSwitcher();
    } else if (looksLikeUpstreamUnavailable) {
      const engine = engineFromEvent || "le moteur";
      const sysMsg =
        `⚠ ${engine} en surcharge temporaire : réponse refusée par le serveur upstream.\n\n` +
        `Solutions :\n` +
        ` 1. Réessaie dans 30s-2min (les spikes durent rarement plus).\n` +
        ` 2. Bascule sur un autre moteur via le sélecteur en haut (clignote en orange ↑).\n\n` +
        `Détail technique : ${(info || "").slice(0, 250)}`;
      appendTurn("system", sysMsg);
      flashEngineSwitcher();
    } else {
      appendTurn("system", "[Erreur stream] " + (info || "connexion perdue"));
    }
    es.close(); currentEventSource = null;
    setStreamingUI(false);  // Phase v15.7.21
  });
  es.addEventListener("quota_midflow", (e) => {
    // Phase A.7.2 v7.3 : le quota a sauté en plein flow. Le backend liste
    // les providers de fallback dispos (clés présentes dans l'env). On
    // affiche un card avec un bouton par provider, clic → POST
    // /api/switch_engine → relance streamResponse() (qui stream depuis
    // l'historique transféré, sans re-poster le user message).
    stopThinkingIndicator();
    es.close();
    currentEventSource = null;
    respondingToSlideMeta = false;  // reset garde-fou anti-cascade
    try {
      const payload = JSON.parse(e.data);
      renderQuotaMidflowCard(payload);
    } catch (err) {
      appendTurn("system", "[Erreur stream] quota épuisé (parse échoué).");
    }
  });
}

// ============================================================ Bascule à chaud (Phase A.7.2 v7.3)
// Card affiché quand le backend pousse un event `quota_midflow` : le
// quota du provider courant a sauté en plein flow. Le payload contient
// `available: [{engine, label}]` listant les providers dont la clé API
// est définie. Un clic sur un bouton POST `/api/switch_engine` puis
// re-déclenche le stream, l'historique est conservé côté backend, le
// retry arrive avec le user message déjà en place.

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
    noFallback.textContent =
      "Aucun provider de fallback détecté (pas de clé GEMINI_API_KEY / " +
      "DEEPSEEK_API_KEY / GROQ_API_KEY). Configure-en au moins une et " +
      "redémarre la séance (Stop puis Lancer dans la GUI Tk).";
    card.appendChild(noFallback);
  } else {
    const help = document.createElement("div");
    help.className = "qmf-help";
    help.textContent =
      "Bascule à chaud sans perdre l'historique. Choisis un provider :";
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
  // Désactive tous les boutons du card pour éviter le double-clic.
  card.querySelectorAll(".qmf-btn").forEach(b => b.disabled = true);
  const status = document.createElement("div");
  status.className = "qmf-status";
  status.textContent = `Bascule sur ${provider.label}…`;
  card.appendChild(status);
  try {
    const r = await fetch("/api/switch_engine", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ engine: provider.engine }),
    });
    const data = await r.json();
    if (!r.ok) {
      status.textContent = "✗ " + (data.error || `HTTP ${r.status}`);
      card.classList.add("qmf-error");
      // Réactive les boutons en cas d'échec pour permettre re-essai.
      card.querySelectorAll(".qmf-btn").forEach(b => b.disabled = false);
      return;
    }
    status.textContent =
      `✓ Basculé sur ${provider.label} (historique préservé : ${data.history_size} msgs). Reprise…`;
    card.classList.add("qmf-success");
    // Met à jour le badge sessionInfo.
    if (sessionInfo.textContent) {
      sessionInfo.textContent = sessionInfo.textContent.replace(
        /engine: [^)]+/, `engine: ${provider.engine}`
      );
    }
    // Relance le stream. Le backend a mis retry_pending=True donc le
    // GET /api/stream_response stream depuis l'historique sans rien
    // re-poster.
    streamResponse();
  } catch (err) {
    status.textContent = "✗ Erreur réseau : " + err.message;
    card.classList.add("qmf-error");
    card.querySelectorAll(".qmf-btn").forEach(b => b.disabled = false);
  }
}

// ============================================================ Suggestions d'édition (Phase A.7 lecture)

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
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ file, before, after }),
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
  // Appelé sur `done` / `end` : (1) rendu LaTeX final, (2) refs page
  // cliquables (corrigé/script), (3) ajout toolbar de ton sous la bulle.
  if (!currentClaudeTurn) return;
  renderMathIn(currentClaudeTurn);
  linkifyPageRefs(currentClaudeTurn);
  const turnContainer = currentClaudeTurn.parentElement;
  if (turnContainer) {
    // Le message est désormais persisté backend, boutons d'action utilisables.
    turnContainer.classList.remove("is-streaming");
    turnContainer.dataset.rawText = currentClaudeRawText;
    if (!turnContainer.querySelector(".tone-toolbar")) {
      appendToneToolbar(turnContainer);
    }
  }
}

// Phase A.9 : bulle système avec bouton « 📂 Ouvrir dans Docs » qui active
// l'onglet Docs et navigue vers le PDF dont on connaît le filename.
// Réutilisable pour tout event de création de doc (PDF d'énoncé inventé,
// futurs cas de génération). Si `filename` est null/vide, le bouton
// ouvre juste l'onglet Docs sans navigation spécifique.
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
    const tab = document.querySelector(
      '#sidebar-tabs .sb-tab[data-tab="corrige"]',
    );
    if (tab) tab.click();
    if (!filename) return;
    // Le panneau Docs est rechargé en arrière-plan ; on attend un court
    // moment pour que correctionsList contienne le nouveau PDF puis on
    // y navigue. Plusieurs tentatives au cas où la liste tarde à charger.
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
  // Markers de transition slide ([Mode guidé] L'étudiant/Le tuteur a…) →
  // rendu discret. Détecté côté front via le préfixe pour ne pas surcharger
  // le schéma backend. Sous-classe selon source pour distinguer visuellement
  // qui a déclenché la transition (cf. sendGuidedSlideMeta).
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
  // Phase Z.8.2 : timestamp discret à droite du label (formaté court :
  // HH:MM si aujourd'hui, "Hier HH:MM" sinon, "9 mai HH:MM" pour plus
  // ancien). Title hover = date complète absolue. Si opts.at non fourni
  // (live stream avant que le backend ait posé le msg), fallback sur
  // Date.now() côté client, sera remplacé au prochain rerender via
  // entry.at du transcript backend.
  const timeSpan = document.createElement("span");
  timeSpan.className = "turn-time";
  const atIso = opts.at || new Date().toISOString();
  timeSpan.dataset.atIso = atIso;
  timeSpan.textContent = formatTurnTimeShort(atIso);
  timeSpan.title = formatTurnTimeAbsolute(atIso);
  r.appendChild(timeSpan);
  // Flag « (modifié) » à côté du label si edited_at est passé en opt
  // (au boot via /api/current_session ou après un PATCH succès).
  const flag = document.createElement("span");
  flag.className = "turn-edited-flag";
  flag.textContent = "(modifié)";
  if (!opts.editedAt) flag.style.display = "none";
  else flag.title = `Modifié à ${formatTurnTimeAbsolute(opts.editedAt)}`;
  r.appendChild(flag);
  const t = document.createElement("div");
  t.textContent = text;
  div.appendChild(r); div.appendChild(t);
  // Bulles système (notifications backend, transitions bloquées, etc.) :
  // bouton 🗑 qui les masque LOCALEMENT (pas dans le transcript backend
  //, elles n'y sont pas). Pas de ✏ ni 🔊.
  if (role === "system") {
    div.dataset.localOnly = "1";
    const actions = document.createElement("div");
    actions.className = "turn-actions";
    const delBtn = document.createElement("button");
    delBtn.type = "button"; delBtn.className = "turn-del-btn";
    delBtn.title = "Masquer cette notification";
    delBtn.textContent = "🗑";
    delBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      div.remove();  // suppression purement DOM
    });
    actions.appendChild(delBtn);
    div.appendChild(actions);
    dialogue.appendChild(div);
    dialogue.scrollTop = dialogue.scrollHeight;
    return t;
  }
  // Markers de transition slide : un seul bouton 🗑 qui supprime + revient
  // à la slide précédente (cohérence visuelle ET d'état). Pas de ✏ ni 🔊
  // (ça n'a pas de sens d'éditer ou d'écouter un marker système).
  if (looksLikeMarker) {
    div.dataset.rawText = markerText;
    const actions = document.createElement("div");
    actions.className = "turn-actions";
    const delBtn = document.createElement("button");
    delBtn.type = "button"; delBtn.className = "turn-del-btn";
    delBtn.title = "Supprimer cette transition et revenir à la slide précédente";
    delBtn.textContent = "🗑";
    delBtn.addEventListener("click", (e) => {
      e.stopPropagation(); deleteTurn(div);
    });
    actions.appendChild(delBtn);
    div.appendChild(actions);
    dialogue.appendChild(div);
    dialogue.scrollTop = dialogue.scrollHeight;
    return t;
  }
  // Boutons d'action visibles au hover (pas sur les bulles « système »).
  if (role === "student" || role === "claude") {
    div.dataset.rawText = text;
    const actions = document.createElement("div");
    actions.className = "turn-actions";
    if (role === "claude") {
      // Bouton 🔊 « Écouter » : génère le TTS et affiche un mini-player
      // sous la bulle avec play/pause/scrub/speed/voice (Phase A.7.2 v14).
      const ttsBtn = document.createElement("button");
      ttsBtn.type = "button"; ttsBtn.className = "turn-tts-btn";
      ttsBtn.title = "Écouter cette réponse"; ttsBtn.textContent = "🔊";
      ttsBtn.addEventListener("click", (e) => {
        e.stopPropagation(); toggleTTSPlayer(div);
      });
      actions.appendChild(ttsBtn);
    }
    const copyBtn = document.createElement("button");
    copyBtn.type = "button"; copyBtn.className = "turn-copy-btn";
    copyBtn.title = "Copier le texte de ce message"; copyBtn.textContent = "📋";
    copyBtn.addEventListener("click", (e) => {
      e.stopPropagation(); copyTurnText(div, copyBtn);
    });
    const editBtn = document.createElement("button");
    editBtn.type = "button"; editBtn.className = "turn-edit-btn";
    editBtn.title = "Modifier ce message"; editBtn.textContent = "✏";
    editBtn.addEventListener("click", (e) => {
      e.stopPropagation(); editTurn(div);
    });
    const delBtn = document.createElement("button");
    delBtn.type = "button"; delBtn.className = "turn-del-btn";
    delBtn.title = "Supprimer ce message du contexte"; delBtn.textContent = "🗑";
    delBtn.addEventListener("click", (e) => {
      e.stopPropagation(); deleteTurn(div);
    });
    actions.appendChild(copyBtn); actions.appendChild(editBtn); actions.appendChild(delBtn);
    div.appendChild(actions);
    // Flèches < N/M > si ce message a plusieurs branches frères
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
  prev.type = "button"; prev.className = "turn-branch-prev";
  prev.textContent = "‹"; prev.title = "Branche précédente";
  prev.disabled = idx <= 1;
  prev.addEventListener("click", (e) => {
    e.stopPropagation();
    if (idx > 1) switchToBranch(ids[idx - 2]);
  });
  const counter = document.createElement("span");
  counter.className = "turn-branch-counter";
  counter.textContent = `${idx}/${count}`;
  const next = document.createElement("button");
  next.type = "button"; next.className = "turn-branch-next";
  next.textContent = "›"; next.title = "Branche suivante";
  next.disabled = idx >= count;
  next.addEventListener("click", (e) => {
    e.stopPropagation();
    if (idx < count) switchToBranch(ids[idx]);
  });
  nav.appendChild(prev); nav.appendChild(counter); nav.appendChild(next);
  turnEl.appendChild(nav);
}

async function switchToBranch(targetMsgId) {
  if (!targetMsgId) return;
  try {
    const r = await fetch(
      `/api/messages/${encodeURIComponent(targetMsgId)}/switch`,
      { method: "POST" },
    );
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      alert("Switch échoué : " + (data.error || r.status));
      return;
    }
    // Reload du dialogue avec le nouveau transcript
    rerenderDialogueFromTranscript(data.transcript || []);
  } catch (e) {
    alert("Erreur réseau pendant le switch : " + e.message);
  }
}

// Phase v15.7.30.1 : strip défensif du préfixe `[Contexte lecture actuelle
//, l'étudiant consulte la page X/Y du KIND « LABEL » (FILENAME)]` qui
// était persisté à tort dans le transcript jusqu'à v15.7.30. Régression
// au reload de session : le préfixe apparaissait brut en bulle student.
// Le backend v15.7.30.1 ne persiste plus ce préfixe (split LLM/transcript),
// mais on garde ce strip côté front pour rétrocompatibilité avec les
// vieilles sessions JSON qui ont déjà le préfixe en dur.
const _READING_PREFIX_RE =
  /^\[Contexte lecture actuelle, l'étudiant consulte[^\]]*\]\s*\n*/;

function _stripReadingPrefix(text) {
  if (!text) return text;
  return text.replace(_READING_PREFIX_RE, "");
}

// Phase A.9.2 : au F5/reload, le transcript persisté contient le bloc OCR
// concaténé au texte de la bulle student (l'OCR est stocké pour que le
// tuteur garde son contexte en cas de reprise). Sans cette extraction, le
// `renderMarkdown` à la replay convertit le bloc en `<p>` plats moches.
// Ce parseur miroir du backend (`app.py:1496-1511`) retire la section OCR
// du texte affiché et reconstruit les `<details>.ocr-collapsible` via le
// même helper `_appendOcrCollapsibleBlock` que le live render.
function _extractOcrBlocksFromText(text) {
  if (!text) return { cleanText: text || "", ocrBlocks: [] };
  // Header tel qu'écrit en backend (cf. app.py). On accepte un espacement
  // tolérant pour survivre à un éventuel post-traitement (strip trailing
  // newlines, etc.).
  const headerRe =
    /\n{1,2}\[OCR pré-traitée par Gemini Flash 2\.5, vérifie qu'elle correspond à ta lecture multimodale, sinon dis-le et signale la divergence à l'étudiant\]:/;
  const m = headerRe.exec(text);
  if (!m) return { cleanText: text, ocrBlocks: [] };
  const cleanText = text.slice(0, m.index).replace(/\s+$/, "");
  const ocrSection = text.slice(m.index + m[0].length);
  // Le séparateur entre blocs est exactement `\n\n--- OCR de l'image ---\n`.
  // split() avec regex globale → on perd le séparateur et on récupère un
  // tableau de blocs (le 1ᵉʳ élément est vide ou whitespace avant le 1ᵉʳ sép).
  const parts = ocrSection.split(/\n\n--- OCR de l'image ---\n/);
  const ocrBlocks = [];
  for (const part of parts) {
    if (!part || !part.trim()) continue;
    const lines = part.split("\n");
    let kind = "?";
    let completeness = null;
    let warnings = [];
    let bodyStartIdx = 0;
    // Parse les lignes header (Type détecté / Complétude / Warnings)
    // dans l'ordre attendu. Tolère un ordre permuté quand même.
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      let matched = false;
      const kMatch = /^Type détecté\s*:\s*(.+?)\s*$/.exec(line);
      if (kMatch) { kind = kMatch[1]; matched = true; }
      const cMatch = /^Complétude estimée\s*:\s*(\d+)\s*%\s*$/.exec(line);
      if (cMatch) { completeness = parseInt(cMatch[1], 10); matched = true; }
      const wMatch = /^Warnings\s*:\s*(.+?)\s*$/.exec(line);
      if (wMatch) {
        // Backend join via `, ` → on resplit pareil. Tolère ` · ` au cas où.
        warnings = wMatch[1].split(/\s*(?:,| · )\s*/).filter(w => w.length > 0);
        matched = true;
      }
      if (!matched) {
        // Première ligne non-header → début du body. La structure backend
        // garantit une ligne vide entre header et body, on la skippe.
        if (line.trim() === "") { bodyStartIdx = i + 1; continue; }
        bodyStartIdx = i;
        break;
      }
    }
    const ocr_markdown = lines.slice(bodyStartIdx).join("\n").trim();
    ocrBlocks.push({
      kind_detected: kind,
      completeness_pct: completeness,
      warnings,
      ocr_markdown,
    });
  }
  return { cleanText, ocrBlocks };
}

function rerenderDialogueFromTranscript(transcript) {
  dialogue.innerHTML = "";
  for (const entry of transcript) {
    const role = entry.role === "student" ? "student" : "claude";
    let cleanText = role === "student"
      ? _stripReadingPrefix(entry.text || "")
      : (entry.text || "");
    // Phase A.9.2 : extrait les blocs OCR de la bulle student pour les
    // re-rendre en `<details>` plutôt qu'en `<p>` brut. Pas d'extraction
    // côté Compagnon (le tuteur ne réémet jamais ce header verbatim).
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
      rawText: cleanText,
    });
    turn.innerHTML = renderMarkdown(cleanText);
    if (turn.parentElement) {
      turn.parentElement.dataset.rawText = cleanText;
    }
    // Phase v15.7.20 : rendu LaTeX appliqué à TOUS les rôles (student
    // pouvait poster du `$x^2$` qui restait en texte brut au re-render).
    renderMathIn(turn);
    // Phase A.9.2 : réinjecte les `<details>.ocr-collapsible` sous la bulle
    // student (en miroir du flow live post-`send_message`).
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

// Phase A.10.13.bug2 : helper module-level : préfixe `_uploads/` quand
// l'attachment est storage="uploads" (cohérent avec api_send_message
// backend qui injecte le même préfixe dans le markdown stocké). Sans ça,
// renderMarkdown route vers /api/cours_file qui 404 → "⚠ Image introuvable".
// Bug observé 2026-05-14 sur session AN1 CCT lors d'un upload mobile
// via Tailscale depuis le mode édition + reload contexte.
function _relWithStoragePrefix(a) {
  if (!a || !a.rel_path) return "";
  if (a.storage === "uploads") return `_uploads/${a.rel_path}`;
  return a.rel_path;
}

// Phase A.8.5 : variable globale pointant vers le textarea d'édition actif
// (s'il y en a un). Permet à uploadAttachmentFile / handlePasteEvent /
// refreshAttachmentsTray de rediriger les images vers ce textarea au lieu
// du tray pending_attachments habituel. Snapshot des att.id déjà présents
// à l'ouverture de l'édit pour ne capter que les nouveaux arrivants
// (typiquement upload mobile / paste).
let _activeEditTextarea = null;
let _editAttachmentSeenIds = new Set();

function _setActiveEditTextarea(ta) {
  _activeEditTextarea = ta;
  if (ta) {
    _editAttachmentSeenIds = new Set();
    // Snapshot async des ids déjà dans le tray à l'ouverture de l'édit.
    fetch("/api/pending_attachments").then(r => r.ok ? r.json() : null).then(d => {
      if (!d) return;
      for (const a of (d.attachments || [])) {
        if (a.id) _editAttachmentSeenIds.add(a.id);
      }
    }).catch(() => {});
  } else {
    _editAttachmentSeenIds = new Set();
  }
}

// Phase A.8.5 : insère un markdown image à la position curseur (ou fin)
// du textarea d'édition actif. Auto-resize après insertion.
// Phase A.10.13.bug2 : accepte un objet attachment (`{rel_path, storage,
// original_name}`) ou la signature legacy `(rel_path, original_name)`.
// Préfixe `_uploads/` automatique via `_relWithStoragePrefix` pour les
// attachments storage="uploads" (sans ça, /api/cours_file 404 → image
// introuvable). Le markdown stocké côté serveur applique le même préfixe.
function _insertImageMarkdownInEdit(attOrRelPath, original_name) {
  const ta = _activeEditTextarea;
  if (!ta) return;
  // Phase A.8.5 hotfix : sanity check : si le textarea n'est plus dans
  // le DOM (zone d'édition fermée sans cleanup, ex. après rerender),
  // libère la variable globale et retombe sur le flow normal.
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
  const pos = (typeof ta.selectionStart === "number") ? ta.selectionStart : ta.value.length;
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
  if (turnEl.querySelector(".turn-edit-area")) return;  // déjà en édition
  const all = Array.from(dialogue.querySelectorAll(".turn.student, .turn.claude"));
  const index = all.indexOf(turnEl);
  if (index < 0) return;
  const role = turnEl.classList.contains("student") ? "student" : "claude";
  const rawText = turnEl.dataset.rawText || "";
  // Cache le contenu rendu et les actions pendant l'édition
  const textDiv = turnEl.querySelector(":scope > div:nth-child(2)");
  const actions = turnEl.querySelector(".turn-actions");
  if (textDiv) textDiv.style.display = "none";
  if (actions) actions.style.display = "none";
  // Construit la zone d'édition
  const wrap = document.createElement("div");
  wrap.className = "turn-edit-area";
  const ta = document.createElement("textarea");
  ta.className = "turn-edit-textarea";
  ta.value = rawText;
  ta.rows = Math.min(20, Math.max(3, rawText.split("\n").length + 1));
  // Bouton 📎 « Joindre une image » dans l'éditeur, upload staged
  // (pas dans pending_attachments) et append le markdown au textarea.
  const attachBtn = document.createElement("button");
  attachBtn.type = "button"; attachBtn.className = "turn-edit-attach";
  attachBtn.textContent = "📎";
  attachBtn.title = "Joindre une image à ce message";
  const attachInput = document.createElement("input");
  attachInput.type = "file"; attachInput.accept = "image/*";
  attachInput.multiple = true; attachInput.style.display = "none";
  attachBtn.addEventListener("click", () => attachInput.click());
  attachInput.addEventListener("change", async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    e.target.value = "";
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f, f.name);
      fd.append("staged", "1");
      try {
        const r = await fetch("/api/upload_attachment", { method: "POST", body: fd });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) {
          alert(`Upload "${f.name}" échoué : ${data.error || r.status}`);
          continue;
        }
        // Phase A.10.13.bug2 : préfixe `_uploads/` pour storage="uploads"
        // (sinon /api/cours_file 404 → "⚠ Image introuvable" au reload).
        const relWithPrefix = _relWithStoragePrefix(data);
        const md = data.is_image
          ? `![${data.original_name || data.filename}](${relWithPrefix})`
          : `[Pièce jointe : ${data.original_name || data.filename} (${relWithPrefix})]`;
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
  saveBtn.type = "button"; saveBtn.className = "turn-edit-save";
  saveBtn.textContent = "Modifier";
  saveBtn.title = "Remplace ce message (l'ancien est perdu)";
  const branchBtn = document.createElement("button");
  branchBtn.type = "button"; branchBtn.className = "turn-edit-branch";
  branchBtn.textContent = "+ Branche";
  branchBtn.title = "Crée une nouvelle branche : l'ancien message reste accessible via les flèches";
  const reloadBtn = document.createElement("button");
  reloadBtn.type = "button"; reloadBtn.className = "turn-edit-reload";
  reloadBtn.textContent = "🔄 Recharger contexte";
  reloadBtn.title = "Modifie + supprime tout ce qui suit + regénère la réponse du tuteur";
  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button"; cancelBtn.className = "turn-edit-cancel";
  cancelBtn.textContent = "Annuler";
  ctrls.appendChild(attachBtn); ctrls.appendChild(attachInput);
  ctrls.appendChild(saveBtn); ctrls.appendChild(branchBtn);
  ctrls.appendChild(reloadBtn); ctrls.appendChild(cancelBtn);
  wrap.appendChild(ta); wrap.appendChild(ctrls);
  turnEl.appendChild(wrap);
  ta.focus();
  ta.setSelectionRange(ta.value.length, ta.value.length);
  // Phase A.8.5 : déclare ce textarea comme actif pour que paste / mobile
  // capture / drag-drop redirigent les images vers ici au lieu du tray.
  _setActiveEditTextarea(ta);
  // Phase A.10.17 : hook input event pour resync ✨ Rewrite (qui regarde
  // désormais `_getActiveTextarea()`). Sans ce listener, le bouton resterait
  // figé sur l'état au moment de l'entrée en édition.
  ta.addEventListener("input", refreshRewriteBtnState);
  refreshRewriteBtnState();

  const cleanup = () => {
    wrap.remove();
    if (textDiv) textDiv.style.display = "";
    if (actions) actions.style.display = "";
    // Phase A.8.5 : libère l'édition active à la fermeture.
    if (_activeEditTextarea === ta) _setActiveEditTextarea(null);
    // Phase A.10.17 : invalide la cible rewrite si elle pointait sur ce
    // textarea (qui n'existera plus). Cache aussi le banner d'undo
    // pendouillant (sinon clic Undo restaurerait sur userInput, étrange).
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
    // Phase A.10.17 : resync ✨ Rewrite après fermeture (la cible
    // redevient userInput, le bouton doit refléter ce contenu).
    refreshRewriteBtnState();
  };
  cancelBtn.addEventListener("click", cleanup);
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); cleanup(); }
    else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault(); saveBtn.click();
    }
  });
  const submit = async (asBranch) => {
    const newText = ta.value.trim();
    if (!newText) { alert("Le message ne peut pas être vide."); return; }
    if (newText === rawText.trim()) { cleanup(); return; }
    saveBtn.disabled = true; branchBtn.disabled = true; cancelBtn.disabled = true;
    (asBranch ? branchBtn : saveBtn).textContent = "…";
    try {
      const r = await fetch(`/api/messages/${index}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: newText, as_branch: asBranch }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        alert((asBranch ? "Branche" : "Édition") + " échouée : " + (data.error || r.status));
        saveBtn.disabled = false; branchBtn.disabled = false; cancelBtn.disabled = false;
        saveBtn.textContent = "Modifier"; branchBtn.textContent = "+ Branche";
        return;
      }
      if (asBranch || data.branched) {
        // Une nouvelle branche est créée → reload complet du dialogue
        // depuis le serveur pour récupérer les sibling_count à jour.
        try {
          const cs = await fetch("/api/current_session");
          const csd = await cs.json();
          if (csd.active && Array.isArray(csd.transcript)) {
            rerenderDialogueFromTranscript(csd.transcript);
            return;
          }
        } catch (_) { /* tomber dans le fallback ci-dessous */ }
      }
      // Édition in-place : update DOM local
      turnEl.dataset.rawText = newText;
      if (textDiv) {
        textDiv.innerHTML = renderMarkdown(newText);
        // Phase v15.7.20 : LaTeX appliqué student aussi (cf. rerender)
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
      saveBtn.disabled = false; branchBtn.disabled = false; cancelBtn.disabled = false;
      saveBtn.textContent = "Modifier"; branchBtn.textContent = "+ Branche";
    }
  };
  saveBtn.addEventListener("click", () => submit(false));
  branchBtn.addEventListener("click", () => submit(true));
  reloadBtn.addEventListener("click", async () => {
    const newText = ta.value.trim();
    if (!newText) { alert("Le message ne peut pas être vide."); return; }
    if (!confirm(
      "Modifier ce message et regénérer la réponse du tuteur ?\n\n" +
      "Tout ce qui vient APRÈS sera perdu (réponse claude actuelle + " +
      "messages suivants). Action irréversible."
    )) return;
    saveBtn.disabled = true; branchBtn.disabled = true;
    reloadBtn.disabled = true; cancelBtn.disabled = true;
    reloadBtn.textContent = "…";
    try {
      // 1. Sauve les modifications du textarea (PATCH in-place, pose
      //    edited_at + note système : le tuteur saura que c'est édité).
      if (newText !== rawText.trim()) {
        const pr = await fetch(`/api/messages/${index}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: newText, as_branch: false }),
        });
        if (!pr.ok) {
          const d = await pr.json().catch(() => ({}));
          alert("Sauvegarde échouée : " + (d.error || pr.status));
          throw new Error("save_failed");
        }
      }
      // 2. Tronque ce qui suit + réarme le stream
      const rr = await fetch(`/api/messages/${index}/regenerate`, {
        method: "POST",
      });
      const rd = await rr.json().catch(() => ({}));
      if (!rr.ok) {
        // Si index hors plage → mismatch DOM/backend (le transcript a
        // changé après bascule moteur, suppression marker, etc.). On
        // resynchronise depuis le backend et on demande au user de
        // re-cliquer Recharger sur la bonne bulle.
        if ((rd.error || "").startsWith("index hors plage")) {
          alert(
            "Désynchronisation détectée entre l'affichage et le backend " +
            "(probablement après bascule moteur ou suppression). Le " +
            "dialogue va être resynchronisé depuis le serveur. " +
            "réessaye ensuite Recharger contexte sur la bulle souhaitée.",
          );
          try {
            const cs = await fetch("/api/current_session");
            const csd = await cs.json();
            if (csd.active && Array.isArray(csd.transcript)) {
              rerenderDialogueFromTranscript(csd.transcript);
            }
          } catch (_) { /* fallback silencieux */ }
        } else {
          alert("Régénération échouée : " + (rd.error || rr.status));
        }
        throw new Error("regenerate_failed");
      }
      // 3. Reload UI avec le transcript tronqué
      // Phase A.8.5 hotfix : libère _activeEditTextarea AVANT le rerender
      // qui détruit le DOM de la zone d'édition. Sans ça, la variable
      // globale reste pointer sur le textarea orphelin → tous les
      // uploads suivants (paste, mobile, drag-drop) sont redirigés
      // vers cet élément détaché au lieu du textarea principal.
      if (_activeEditTextarea === ta) _setActiveEditTextarea(null);
      rerenderDialogueFromTranscript(rd.transcript || []);
      // 4. Lance le stream pour récupérer la nouvelle réponse claude
      streamResponse();
    } catch (e) {
      // Restore boutons sur erreur
      saveBtn.disabled = false; branchBtn.disabled = false;
      reloadBtn.disabled = false; cancelBtn.disabled = false;
      reloadBtn.textContent = "🔄 Recharger contexte";
    }
  });
}

async function copyTurnText(turnEl, btn) {
  if (!turnEl) return;
  const raw = turnEl.dataset.rawText
    || (turnEl.querySelector(":scope > div:nth-child(2)") || {}).textContent
    || "";
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
    // Fallback execCommand pour anciens navigateurs / contextes non-secure
    const ta = document.createElement("textarea");
    ta.value = raw;
    ta.style.position = "fixed"; ta.style.opacity = "0";
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
  const confirmMsg = isMarker
    ? "Supprimer cette transition et revenir à la slide précédente ?"
    : "Supprimer ce message du contexte ? Cette action est définitive.";
  if (!confirm(confirmMsg)) return;
  try {
    const r = await fetch(`/api/messages/${index}`, { method: "DELETE" });
    if (!r.ok && r.status !== 204) {
      const err = await r.json().catch(() => ({}));
      alert("Suppression échouée : " + (err.error || r.status));
      return;
    }
    // Le backend retourne 200 JSON {ok, was_marker, new_guided_index} si
    // c'était un marker, sinon 204 No Content. On parse seulement si JSON.
    let data = {};
    try { data = await r.json(); } catch (_) { /* 204 ou pas JSON */ }
    turnEl.remove();
    // Si marker supprimé → reculer le panneau guidé à la slide précédente
    if (data.was_marker
        && Number.isInteger(data.new_guided_index)
        && activeMode === "guidé"
        && guidedSlides.length) {
      showGuidedSlide(data.new_guided_index, /*announceToClaude=*/false);
    }
  } catch (e) {
    alert("Erreur réseau pendant la suppression : " + e.message);
  }
}

// ============================================================ Bouton micro toggle (Phase A.6.2 : révisé v15.6.2)
// Click → MediaRecorder.start() (visuel rouge pulsant). Re-click → annule
// le mic SANS attendre la transcription Whisper canonique : on garde la
// preview WebSpeech qui est déjà dans l'input, et on libère le stream.
//
// Pourquoi annuler plutôt que finaliser Whisper : finaliser via Whisper
// prend ~1-3 s d'attente que le user ne veut pas subir. Si la preview
// WebSpeech a des erreurs, le bouton ✨ Améliorer (popover 4 actions)
// les corrige proprement avant envoi, pas besoin du re-pass Whisper.
//
// Sémantique unifiée : Re-click 🎤 = Entrée pendant le mic = juste
// abort + envoi/garde du contenu courant. Aucune voie n'attend Whisper.

micBtn.addEventListener("click", async () => {
  if (!isRecording) {
    await startRecording();
  } else {
    abortRecordingAndTranscribe();
  }
});

// Variables pour le timer d'enregistrement (feedback live, Phase A.7.2 v2).
let recordStartTs = 0;
let recordTimerHandle = null;
// AbortController du fetch /api/transcribe en cours. Permet d'annuler la
// transcription quand l'utilisateur envoie ou ré-enregistre avant que
// Whisper finisse, sinon le résultat retombe dans le champ vide après
// coup et pollue l'enregistrement suivant.
let pendingTranscribeAbort = null;
// Texte tapé par l'utilisateur AVANT de cliquer 🎤, préservé pendant la
// preview WebSpeech (qui écrit dans la cible mic) et restauré au retour
// Whisper, avec la transcription canonique appended derrière.
let userInputBeforeRecording = "";
// Phase A.10.17 : textarea-cible du mic. Pointe vers `_activeEditTextarea`
// si une édition de bulle est en cours, sinon vers `userInput`. Verrouillé
// au démarrage de l'enregistrement (pour que la fermeture de l'édition
// pendant qu'on parle ne fasse pas perdre la transcription).
let _recordingTargetTextarea = null;
const userInputPlaceholderDefault =
  "Tape ta réponse, ou clique 🎤 pour la dicter…";

// Phase A.10.17 : helper unique pour les boutons de l'input footer (mic,
// ✨ rewrite, 📎, 📷). Quand une bulle est en édition (`_activeEditTextarea`
// set), les boutons opèrent sur ce textarea-là. Sinon, sur `userInput`.
// Le textarea media/photo upload routait déjà via `_activeEditTextarea`
// dans `uploadAttachmentFile`, on étend la cohérence aux 4 boutons.
function _getActiveTextarea() {
  if (_activeEditTextarea && document.body.contains(_activeEditTextarea)) {
    return _activeEditTextarea;
  }
  return userInput;
}

// Auto-resize d'un textarea quel qu'il soit (édition ou main). Le main a
// max-height CSS, l'édition a un cap à 400px géré inline (cf. editTurn).
function _autoResizeTextarea(ta) {
  if (!ta) return;
  if (ta === userInput) { autoResizeUserInput(); return; }
  try {
    ta.style.height = "auto";
    ta.style.height = Math.min(400, ta.scrollHeight) + "px";
  } catch (_) {}
}

// ============================================================ Live preview WebSpeech (Phase A.7.2 v6)
// Pendant que MediaRecorder enregistre pour Whisper (canonique, qualité),
// on lance EN PARALLÈLE l'API WebSpeech native du navigateur. Elle envoie
// l'audio au cloud Google (Chrome/Edge) en streaming et nous renvoie une
// transcription quasi-instantanée, pas top sur le vocab technique mais
// suffisante pour un feedback visuel pendant qu'on parle. Sur stop, le
// retour Whisper écrase la preview (texte canonique).
//
// Pas dispo dans Firefox (pas d'implémentation SpeechRecognition). Sur
// les navigateurs sans support, on passe simplement le live preview
// (l'utilisateur voit l'animation timer mais pas le texte).
//
// Privacy : Chrome/Edge envoient l'audio chez Google pour reconnaissance.
// Sur localhost c'est acceptable, mais à signaler dans la doc.

let liveRecognition = null;
let liveTranscriptFinal = "";  // partie déjà finalisée par WebSpeech

function setupLiveRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    return null;  // Firefox, Safari < 14.1 → pas de live preview
  }
  const rec = new SR();
  rec.continuous = true;       // ne s'arrête pas après 1 phrase
  rec.interimResults = true;   // on veut les résultats partiels (live)
  rec.lang = "fr-FR";
  rec.onresult = (e) => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const tr = e.results[i][0].transcript;
      if (e.results[i].isFinal) liveTranscriptFinal += tr + " ";
      else interim += tr;
    }
    // Feedback visuel : on met le texte dans la cible mic comme preview.
    // Sera écrasé par le retour Whisper (canonique) à la fin.
    // Phase A.10.17 : cible = `_recordingTargetTextarea` (édition de bulle
    // si active, sinon `userInput`).
    const ta = _recordingTargetTextarea || userInput;
    ta.value = (liveTranscriptFinal + interim).trim();
    _autoResizeTextarea(ta);
  };
  rec.onerror = (e) => {
    // "no-speech" et "aborted" sont normaux (silence prolongé / stop manuel)
    if (e.error && !["no-speech", "aborted"].includes(e.error)) {
      console.warn("WebSpeech erreur :", e.error);
    }
  };
  rec.onend = () => {
    // Sur certains browsers le service auto-stop après ~60 s. Si on
    // enregistre toujours, on relance.
    if (isRecording && liveRecognition) {
      try { rec.start(); } catch (_) { /* déjà running */ }
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
    // Phase Z.8.3 : neutralise TOUS les handlers AVANT d'arrêter, pour
    // qu'aucun event tardif (résultats partiels en cours de finalisation)
    // ne re-touche userInput.value après l'arrêt. Bug observé en envoi
    // direct (Entrée pendant le mic) : sans ça, un onresult tirait après
    // que sendUserMessage ait vidé l'input et venait y réécrire un
    // fragment final ("le reste de la phrase"). On utilise aussi .abort()
    // au lieu de .stop() pour couper net (stop laisse finaliser, abort
    // jette tout immédiatement).
    liveRecognition.onresult = null;
    liveRecognition.onend = null;
    liveRecognition.onerror = null;
    if (typeof liveRecognition.abort === "function") {
      liveRecognition.abort();
    } else {
      liveRecognition.stop();
    }
  } catch (_) { /* déjà stoppé */ }
  liveRecognition = null;
}

async function startRecording() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert("Le navigateur ne supporte pas getUserMedia. Utilise Chrome/Firefox récent.");
    return;
  }
  // Annule une transcription Whisper en vol d'un enregistrement précédent :
  // sinon son résultat tardif viendrait écraser le nouveau enregistrement.
  cancelPendingTranscribe();
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    alert("Permission micro refusée ou aucun micro détecté : " + e.message);
    return;
  }
  recordedChunks = [];
  // MIME prefer webm/opus (compact), fallback laissé au navigateur sinon
  let mime = "";
  for (const cand of ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"]) {
    if (MediaRecorder.isTypeSupported(cand)) { mime = cand; break; }
  }
  try {
    mediaRecorder = mime ? new MediaRecorder(micStream, { mimeType: mime }) : new MediaRecorder(micStream);
  } catch (e) {
    alert("MediaRecorder init échoué : " + e.message);
    releaseMicStream();
    return;
  }
  mediaRecorder.addEventListener("dataavailable", (e) => {
    if (e.data && e.data.size > 0) recordedChunks.push(e.data);
  });
  mediaRecorder.addEventListener("stop", onRecordingStopped);
  mediaRecorder.start();
  isRecording = true;
  micBtn.classList.add("recording");
  micBtn.textContent = "⏹";
  micBtn.title = "Cliquer pour annuler le mic (garde la preview dans l'input). Entrée envoie directement ce qui est dans l'input.";
  // Live preview WebSpeech (Phase A.7.2 v6) : Chrome/Edge uniquement.
  // Tu vois ce que tu dis pendant que tu parles ; au stop, Whisper
  // large-v3 écrase avec la version canonique haute qualité.
  // Phase A.10.17 : verrouille la cible mic au démarrage. Si l'utilisateur
  // ferme l'édition pendant qu'il parle, on continue d'écrire dans le bon
  // textarea (et on snap correctement à la fin). L'édition active = cible.
  _recordingTargetTextarea = _getActiveTextarea();
  userInputBeforeRecording = _recordingTargetTextarea.value;  // snapshot
  startLiveRecognition();
  // Feedback live (Phase A.7.2 v2) : placeholder + timer + indicator pulsé.
  _recordingTargetTextarea.value = "";  // reset pour preview WebSpeech propre
  _autoResizeTextarea(_recordingTargetTextarea);
  if (_recordingTargetTextarea === userInput) {
    userInput.placeholder = liveRecognition
      ? "🎤 Parlez… Entrée pour envoyer, ⏹ pour annuler le mic"
      : "🎤 Parlez… Entrée pour envoyer (input vide sans WebSpeech), ⏹ pour annuler";
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
  recordIndicator.textContent =
    `🎤 Enregistrement… ${m}:${s.toString().padStart(2, "0")}`;
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
  // Feedback live : passe en mode « transcription en cours » jusqu'au
  // retour de /api/transcribe (peut prendre quelques secondes).
  if (recordTimerHandle) {
    clearInterval(recordTimerHandle);
    recordTimerHandle = null;
  }
  userInput.placeholder = "⏳ Transcription en cours…";
  recordIndicator.textContent = "⏳ Transcription en cours… (Whisper large-v3)";
}

function releaseMicStream() {
  if (micStream) {
    micStream.getTracks().forEach((t) => t.stop());
    micStream = null;
  }
}

async function onRecordingStopped() {
  releaseMicStream();
  const blob = new Blob(recordedChunks, { type: mediaRecorder.mimeType || "audio/webm" });
  recordedChunks = [];
  const fd = new FormData();
  // Extension cohérente avec le mimetype pour aider ffmpeg côté backend
  let ext = "webm";
  if (mediaRecorder.mimeType && mediaRecorder.mimeType.includes("ogg")) ext = "ogg";
  fd.append("audio", blob, `recording.${ext}`);
  // AbortController : si l'utilisateur envoie ou ré-enregistre pendant que
  // Whisper transcrit, on aborte au lieu de laisser le résultat retomber
  // dans le champ après coup.
  pendingTranscribeAbort = new AbortController();
  const myAbort = pendingTranscribeAbort;
  try {
    const r = await fetch("/api/transcribe", {
      method: "POST", body: fd, signal: myAbort.signal,
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
    // Concatène la transcription Whisper canonique au texte qui était
    // tapé AVANT le clic 🎤. La preview WebSpeech qui occupait le textarea
    // pendant l'enregistrement est écrasée (Whisper > WebSpeech).
    //
    // Phase A.10.17 : réécriture après bug v15.7.24. L'ancien check
    // `userTouchedInput` comparait `currentInput.trim() !== snapshot.trim()`
    // pour détecter une modif manuelle pendant le record, mais WebSpeech
    // (qui ré-écrit la preview en continu) faisait toujours diverger
    // currentInput de snapshot → la logique perdait le snapshot. User :
    // « si y'a du texte déjà actif, faut que ça n'annule pas l'ancien ».
    //
    // Comportement définitif : **toujours** préserver le snapshot pre-mic
    // et appender la transcription Whisper derrière. Si l'utilisateur veut
    // repartir de zéro, il efface manuellement post-transcription.
    //
    // Cible = textarea verrouillée au démarrage du mic (édition de bulle
    // ou main input). Fallback userInput si la cible a été détruite
    // (édition fermée pendant l'enregistrement).
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
    // Détection hallucination Whisper : un même groupe de 1-4 mots répété
    // ≥5 fois consécutivement. Cas typique : long silence ou voix basse →
    // Whisper boucle sur « j'ai pas, j'ai pas, j'ai pas… ». On flag, on
    // n'efface pas (l'étudiant peut vouloir corriger lui-même).
    maybeFlagWhisperHallucination(text);
  } catch (e) {
    if (e.name === "AbortError") {
      // L'utilisateur a envoyé ou ré-enregistré, on ne fait rien.
      // Le UI est déjà reset par le code qui a déclenché l'abort.
      return;
    }
    alert("Erreur réseau pendant la transcription : " + e.message);
  } finally {
    if (pendingTranscribeAbort === myAbort) pendingTranscribeAbort = null;
    micBtn.classList.remove("transcribing");
    micBtn.textContent = "🎤";
    micBtn.title = "Cliquer pour démarrer / arrêter l'enregistrement vocal";
    // Feedback live : reset des placeholders/indicators au retour.
    userInput.placeholder = userInputPlaceholderDefault;
    recordIndicator.classList.remove("active");
    recordIndicator.textContent = "Maintenir [Espace] pour parler";
  }
}

// Annule une transcription Whisper en vol. Appelé quand l'utilisateur
// envoie un message ou relance un enregistrement avant que Whisper finisse.
// Reset aussi le snapshot userInputBeforeRecording pour ne pas mélanger.
function cancelPendingTranscribe() {
  if (!pendingTranscribeAbort) return;
  pendingTranscribeAbort.abort();
  pendingTranscribeAbort = null;
  userInputBeforeRecording = "";
}

// Phase A.7.2 v15.5 : abort propre quand l'utilisateur envoie un message
// PENDANT que le mic enregistre. Diffère de stopRecording() par deux points :
//   - on déclenche pas /api/transcribe (le listener "stop" est détaché) ;
//   - on restaure le préfixe tapé avant le clic 🎤 si l'utilisateur en
//     avait un, sinon on perdrait ce qu'il avait tapé en début de message.
// Le contenu courant de userInput (preview WebSpeech ou texte tapé) reste
// dans le champ et part dans la requête /api/send_message du caller.
function abortRecordingAndTranscribe() {
  if (mediaRecorder) {
    // Détache le handler avant le stop pour bypasser onRecordingStopped
    // qui poste à /api/transcribe, on n'en veut pas en mode envoi direct.
    mediaRecorder.removeEventListener("stop", onRecordingStopped);
    if (mediaRecorder.state !== "inactive") {
      try { mediaRecorder.stop(); } catch (_) { /* déjà stoppé */ }
    }
  }
  stopLiveRecognition();
  releaseMicStream();
  recordedChunks = [];
  isRecording = false;
  // Recolle le préfixe typé avant l'enregistrement (perdu pendant la preview).
  // Phase A.10.17 : utilise la cible verrouillée (édition de bulle ou main).
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
  // Reset UI mic identique à la fin propre de transcription.
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
  // Phase v15.6.3 : la preview WebSpeech remplit userInput.value
  // programmatiquement (pas via frappe clavier), donc l'event "input"
  // ne se déclenche pas pendant l'enregistrement. À l'abort, on
  // resync explicitement l'état du bouton ✨ : si l'input contient
  // ≥8 caractères de preview, le bouton doit s'activer.
  refreshRewriteBtnState();
}

// ============================================================ Quota error formatter FR (Phase v15.6.4)
// Parse le message d'erreur brut renvoyé par le backend (provenant des
// SDK OpenAI/Anthropic/Gemini) et retourne un message en français
// explicite avec une suggestion d'action. Centralisé ici pour être
// réutilisé par le rewrite ET le quota_midflow card du stream principal.

function formatQuotaErrorFr(engine, rawDetail) {
  const d = (rawDetail || "").toString().toLowerCase();
  const engineHuman = ({
    "deepseek_api": "DeepSeek",
    "groq_api":     "Groq",
    "gemini_api":   "Gemini",
    "api_anthropic": "API Anthropic",
    "cli_subscription": "Claude CLI (Pro Max)",
  })[engine] || engine;

  // 1. Solde insuffisant (DeepSeek 402, Anthropic credits)
  if (/402|insufficient.balance|insufficient_balance|payment.required|solde/i.test(d)) {
    return {
      title: `💳 ${engineHuman} n'a plus de solde sur ta clé API`,
      cause: "Cause : la clé API du moteur est à zéro crédit. " +
             "Le moteur ne peut pas répondre tant qu'elle n'est pas rechargée.",
      suggestion:
        "Solutions :\n" +
        "  1. Bascule sur un autre moteur (Claude CLI Pro Max = gratuit, " +
        "Groq/Gemini = free tier généreux).\n" +
        (engine === "deepseek_api"
          ? "  2. Recharge ta clé sur https://platform.deepseek.com/billing"
          : "  2. Vérifie ton plan sur la console du provider"),
    };
  }

  // 2. Request too large / TPM dépassé (Groq free tier 12k TPM, autres)
  // Match le motif "Limit X, Requested Y" pour extraire les chiffres.
  const tpmMatch = d.match(/limit\s+(\d+)[,\s]+requested\s+(\d+)/i);
  if (/413|request.too.large|tokens per minute|rate_limit_exceeded/i.test(d)) {
    let cause;
    if (tpmMatch) {
      const limit = parseInt(tpmMatch[1], 10);
      const requested = parseInt(tpmMatch[2], 10);
      cause = `Cause : ta requête fait ${requested.toLocaleString("fr-FR")} tokens, ` +
              `mais ${engineHuman} n'accepte que ${limit.toLocaleString("fr-FR")} tokens/minute ` +
              `sur ce niveau de service. Le contexte de la session (script + corrigés + ` +
              `transcript) est trop gros pour ce moteur.`;
    } else {
      cause = `Cause : la requête dépasse la limite TPM (tokens/minute) du free tier ${engineHuman}.`;
    }
    return {
      title: `📏 ${engineHuman} : requête trop grosse pour ce moteur`,
      cause: cause,
      suggestion:
        "Solutions :\n" +
        "  1. Bascule sur un moteur avec un contexte plus large : " +
        "Claude CLI (1M tokens, Pro Max), Gemini 2.5 Pro (1M tokens, free tier), " +
        "ou API Anthropic (200k tokens).\n" +
        "  2. Si tu tiens à ce moteur : passe en plan Dev Tier payant " +
        "(Groq → https://console.groq.com/settings/billing).",
    };
  }

  // 3. Context length exceeded (DeepSeek 64k, autres petits modèles)
  if (/context.length|context_length_exceeded|maximum.context/i.test(d)) {
    return {
      title: `📦 ${engineHuman} : contexte de session trop long`,
      cause: `Cause : la session a dépassé la fenêtre de contexte maximale de ce moteur ` +
             `(historique + script + corrigés cumulés).`,
      suggestion:
        "Solutions :\n" +
        "  1. Bascule sur Claude CLI ou Gemini 2.5 Pro (1M tokens chacun).\n" +
        "  2. Termine cette session et démarre un nouvel exo : l'historique repart à zéro.",
    };
  }

  // 4. Rate limit générique (RPM, RPD, etc.) sur free tier
  if (/rate.limit|too.many.requests|429/i.test(d)) {
    return {
      title: `⏱ ${engineHuman} : trop de requêtes (rate limit)`,
      cause: `Cause : tu as dépassé le quota de requêtes par minute ou par jour du free tier ${engineHuman}.`,
      suggestion:
        "Solutions :\n" +
        "  1. Attends 1-5 minutes et réessaie.\n" +
        "  2. Bascule sur un autre moteur en attendant.",
    };
  }

  // 5. Quota Anthropic / Pro Max épuisé
  if (/quota|usage.limit|claude.*max|anthropic/i.test(d)) {
    return {
      title: `🚫 ${engineHuman} : quota épuisé`,
      cause: `Cause : le quota Pro Max ou les crédits API Anthropic sont épuisés sur cette fenêtre.`,
      suggestion:
        "Solutions :\n" +
        "  1. Bascule sur Gemini ou Groq (free tier généreux) en attendant le reset.\n" +
        "  2. Le reset Pro Max est visible dans le panneau Quota à droite.",
    };
  }

  // Défaut : message générique
  return {
    title: `⚠ ${engineHuman} : indisponible pour cette requête`,
    cause: `Le moteur a refusé la requête. Voir le détail technique ci-dessous.`,
    suggestion: "Solution : bascule sur un autre moteur via le sélecteur en haut.",
  };
}

function flashEngineSwitcher() {
  // Scroll + flash visuel sur le sélecteur en haut pour attirer l'œil.
  const el = document.getElementById("engine-switcher");
  if (!el) return;
  try {
    el.scrollIntoView({behavior: "smooth", block: "center"});
  } catch (_) { /* IE / vieux Safari */ }
  // Animation : 3 pulses orange en 1.8s
  el.classList.remove("flash-attention");
  // force reflow pour que la ré-application de la classe relance l'anim
  void el.offsetWidth;
  el.classList.add("flash-attention");
  setTimeout(() => el.classList.remove("flash-attention"), 1900);
  // Focus pour que le user n'ait qu'à appuyer sur ↑/↓ pour changer
  setTimeout(() => { try { el.focus(); } catch (_) {} }, 200);
}

// ============================================================ Colle Format (Phase v15.7.4 → v15.7.30.1)
// Bascule à chaud du format d'interaction en mode colle :
//  - 🎙 Oral : pas de photo, le tuteur ne la mentionne jamais.
//  - 📸 Photos : le tuteur attend la photo sur les questions structurées
//    (table de vérité, schéma, équation posée…).
//  - 🔀 Mixte (défaut) : décision au cas par cas (cf. prompt COMPAGNON §1.6).
// Voies de bascule (Phase v15.7.30.1) :
//   1. Le `<select name="colle_format">` du form dialogue-header sert à la
//      fois au choix initial (transmis à /api/start_session) ET à la
//      bascule à chaud quand une session est active (`change` listener →
//      POST /api/set_colle_format).
//   2. Slash-commands /oral|/photos|/mixte (point final toléré pour la
//      dictée vocale).
// Phase v15.7.30.1 : les bandeaux chips ont été supprimés (redondants).

const COLLE_FORMAT_LABELS = {
  oral: "🎙 Oral",
  photos: "📸 Photos",
  mixte: "🔀 Mixte",
};
// Sync avec le regex Python _SLASH_COLLE_FORMAT_RE côté app.py, toute
// modif ici doit être reflétée là-bas (ou inversement).
const SLASH_COLLE_FORMAT_RE = /^\/(oral|photos?|mixte)\.?\s*$/i;
const colleFormatSelect = startForm.querySelector('[name="colle_format"]');
// Flag anti-boucle : suspend le `change` listener pendant la sync
// programmatique (applyColleFormatChips → set value → change fire → POST).
let _suspendColleFormatChange = false;

function applyColleFormatChips(fmt) {
  // v15.7.30.1 : sync la `value` du <select> au lieu de chips.
  // Tolérance : "photo" → "photos" (singulier accepté côté backend).
  let normalized = (fmt || "").toLowerCase();
  if (normalized === "photo") normalized = "photos";
  if (!["oral", "photos", "mixte"].includes(normalized)) normalized = "mixte";
  activeColleFormat = normalized;
  if (colleFormatSelect && colleFormatSelect.value !== normalized) {
    _suspendColleFormatChange = true;
    try { colleFormatSelect.value = normalized; }
    finally { _suspendColleFormatChange = false; }
  }
}

function appendFormatMarker(fmt) {
  // Marker visuel sobre dans le fil quand le format bascule en cours
  // de séance. Pas une bulle complète, juste un séparateur teinté.
  if (!dialogue) return;
  const label = COLLE_FORMAT_LABELS[fmt] || fmt;
  const marker = document.createElement("div");
  marker.className = "format-marker";
  marker.innerHTML = `🔀 Format → <strong>${label}</strong>`;
  dialogue.appendChild(marker);
  dialogue.scrollTop = dialogue.scrollHeight;
}

async function setColleFormat(fmt, opts = {}) {
  // POST /api/set_colle_format → bascule + marker système côté tuteur.
  // opts.skipMarker : ne pas afficher le marker visuel (utile au boot
  // initial où on synchronise sans avoir « bascule »).
  if (!activeSession) return;
  let normalized = (fmt || "").toLowerCase();
  if (normalized === "photo") normalized = "photos";
  if (!["oral", "photos", "mixte"].includes(normalized)) return;
  // Idempotent : si déjà actif, on n'envoie pas (évite spam de markers
  // au tuteur si le user re-clique le même chip).
  if (normalized === activeColleFormat && !opts.force) return;
  try {
    const r = await fetch("/api/set_colle_format", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({format: normalized}),
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

// v15.7.30.1 : wiring du <select> : `change` POST /api/set_colle_format
// quand une session est active. Avant session, le select sert juste à
// définir le choix initial transmis à /api/start_session (FormData).
if (colleFormatSelect) {
  colleFormatSelect.addEventListener("change", () => {
    if (_suspendColleFormatChange) return;
    if (!activeSession) return;
    setColleFormat(colleFormatSelect.value);
  });
}

// ============================================================ Corrige Anchor (Phase v15.7.30 → v15.7.30.1)
// Bascule à chaud du mode d'ancrage corrigé en mode colle :
//  - 📘 Strict : corrigé fait foi (règle inviolable du prompt v0.5).
//  - 📖 Consultatif : corrigé visible mais cité comme point de vue
//    parmi d'autres ; voies alternatives validées.
//  - 🚫 Sans corrigé : corrigé pas injecté dans le contexte du tuteur.
// Voies de bascule (Phase v15.7.30.1) :
//   1. Le `<select name="corrige_anchor">` du form sert au choix initial
//      ET à la bascule à chaud quand une session est active (`change`
//      listener → POST /api/set_corrige_anchor).
//   2. Slash-commands /strict /consultatif /sans_corrigé.
// Phase v15.7.30.1 : bandeau chips supprimé (redondant).

const CORRIGE_ANCHOR_LABELS = {
  strict: "📘 Strict",
  consultatif: "📖 Consultatif",
  aucun: "🚫 Sans corrigé",
};
// Sync avec le regex Python _SLASH_CORRIGE_ANCHOR_RE côté app.py.
const SLASH_CORRIGE_ANCHOR_RE =
  /^\/(strict|consultatif|aucun|sans[_ ]corrig[ée])\.?\s*$/i;
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
  // v15.7.30.1 : sync la `value` du <select>.
  const normalized = _normalizeCorrigeAnchor(anchor);
  activeCorrigeAnchor = normalized;
  if (corrigeAnchorSelect && corrigeAnchorSelect.value !== normalized) {
    _suspendCorrigeAnchorChange = true;
    try { corrigeAnchorSelect.value = normalized; }
    finally { _suspendCorrigeAnchorChange = false; }
  }
  // Phase A.9 (correctif) : le select reste TOUJOURS interactif. La
  // valeur peut être changée mid-session pour préparer un futur Lancer ;
  // c'est `setCorrigeAnchor` qui inhibe le POST mid-session (no-op si
  // activeSession). Le tooltip explique le comportement.
  if (corrigeAnchorSelect) {
    const sid = activeSession || "";
    const noAnchorContext = (activeMode === "workspace") || /_LIBRE_/.test(sid);
    if (noAnchorContext) {
      corrigeAnchorSelect.title =
        "Pas de corrigé officiel dans ce contexte (workspace / sujet libre), "
        + "valeur forcée à « aucun » par le backend.";
    } else if (activeSession) {
      corrigeAnchorSelect.title =
        "Changement mid-session inactif (pas de switch live). La nouvelle "
        + "valeur s'appliquera au prochain clic Lancer.";
    } else {
      corrigeAnchorSelect.title = "";
    }
    corrigeAnchorSelect.disabled = false;
  }
}

function appendAnchorMarker(anchor) {
  // Marker visuel sobre dans le fil quand l'ancrage bascule en cours
  // de séance. Teinte mauve pour distinguer du format-marker orange.
  if (!dialogue) return;
  const label = CORRIGE_ANCHOR_LABELS[anchor] || anchor;
  const marker = document.createElement("div");
  marker.className = "anchor-marker";
  marker.innerHTML = `📘 Ancrage → <strong>${label}</strong>`;
  dialogue.appendChild(marker);
  dialogue.scrollTop = dialogue.scrollHeight;
}

async function setCorrigeAnchor(anchor, opts = {}) {
  // Phase A.9 (correctif) : friction user 2026-05-13 : « y'a que
  // corrige_anchor où c'est bizarre que ce soit switchable en pleine
  // session ». Le POST live mid-session est désactivé ; la valeur du
  // select reste éditable et s'appliquera au prochain Lancer (via
  // body.corrige_anchor → /api/start_session avec force_new_session
  // si conflit). Si activeSession est set, no-op (le select garde
  // visuellement la nouvelle valeur, juste pas de marker ni de POST).
  if (activeSession) return;
  // Sans session active, le change listener n'a pas non plus de POST
  // à faire, la valeur est lue depuis la FormData au prochain submit.
}

// v15.7.30.1 : wiring du <select> ancrage : `change` POST /api/set_corrige_anchor
// quand une session est active.
if (corrigeAnchorSelect) {
  corrigeAnchorSelect.addEventListener("change", () => {
    if (_suspendCorrigeAnchorChange) return;
    if (!activeSession) return;
    setCorrigeAnchor(corrigeAnchorSelect.value);
  });
}

// ============================================================ Rewrite (Phase A.7.2 v15.5)
// Bouton ✨ entre 📎 et le textarea : ouvre un popover avec 4 actions
// (Reformuler / Concis / Développer / Corriger fautes). Click sur une
// action → POST /api/rewrite → remplace userInput + banner d'annulation.
//
// Pourquoi cette UX : aucun LLM grand public n'expose ce « rewrite avant
// envoi » en standard. Pratique quand on dicte au mic : la transcription
// brute Whisper / WebSpeech est pleine de hésitations qu'on aimerait
// nettoyer sans couper le flow d'écriture.

let lastRewriteOriginal = null;       // texte avant le dernier rewrite
let lastRewriteIntent = null;         // pour le wording du banner
let rewriteBannerHandle = null;       // setTimeout pour auto-dismiss
let rewriteInFlightAbort = null;      // AbortController du fetch rewrite
// Phase A.10.17 : textarea-cible du dernier rewrite (édition de bulle ou
// main). Mémorisé pour que `undoLastRewrite` opère sur le bon textarea
// même si l'édition s'est terminée entre-temps.
let _lastRewriteTargetTextarea = null;

const REWRITE_INTENT_LABELS = {
  reformulate: "Reformulé",
  concise:     "Resserré",
  expand:      "Développé",
  fix_typos:   "Fautes corrigées",
};

function refreshRewriteBtnState() {
  if (!rewriteBtn) return;
  // Activable seulement si session active (le textarea est enabled) ET
  // que la cible contient au moins quelques mots, pas la peine de
  // proposer un rewrite sur 2 caractères.
  // Phase A.10.17 : cible = textarea de l'édition de bulle si active,
  // sinon userInput. Permet à ✨ Améliorer de fonctionner en édition.
  const ta = _getActiveTextarea();
  const text = ta.value.trim();
  const sessionActive = !userInput.disabled;
  rewriteBtn.disabled = !sessionActive || text.length < 8;
}

// Phase v15.7.1 : récupère le texte brut de la dernière bulle Compagnon
// pour l'envoyer comme contexte d'ancrage au rewriter. Préfère
// `dataset.rawText` (le markdown source posé par le stream et persisté
// pour l'édition de bulle) ; fallback sur textContent si absent. Retourne
// "" si aucune bulle Compagnon dans le dialogue, ce qui fait basculer le
// backend en mode legacy (pas de bloc [Contexte] injecté).
function getLastTutorTurnText() {
  if (!dialogue) return "";
  const claudeBubbles = dialogue.querySelectorAll(".turn.claude");
  if (!claudeBubbles.length) return "";
  const last = claudeBubbles[claudeBubbles.length - 1];
  const raw = (last.dataset && last.dataset.rawText) || "";
  // Phase v15.7.12 : applique _stripAttachmentMarkdown pour retirer les
  // ![photo](path) qui pollueraient le contexte rewrite (cas où la bulle
  // tuteur cite ou inclut une photo, rare mais possible via SHOW_DOC etc).
  if (raw.trim()) return _stripAttachmentMarkdown(raw);
  // Fallback : textContent du div texte (2e enfant après l'en-tête rôle).
  const textDiv = last.querySelector(":scope > div:nth-child(2)");
  return _stripAttachmentMarkdown(((textDiv && textDiv.textContent) || ""));
}

// Phase Z.8.4 : bouton 💡 visible uniquement en mode colle (en guidé,
// le tuteur peut déjà fouiller COURS/ via Read/Grep/Glob naturellement).
// Activable dès qu'une session colle est active.
function refreshFindExoBtnState() {
  if (!findExoBtn) return;
  const sessionActive = !!activeSession;
  const showInColleOnly = activeMode === "colle";
  findExoBtn.hidden = !showInColleOnly;
  findExoBtn.disabled = !sessionActive || !showInColleOnly;
}

function openRewritePopover() {
  if (!rewritePopover || rewriteBtn?.disabled) return;
  // Toggle si déjà ouvert
  if (!rewritePopover.hidden) {
    closeRewritePopover();
    return;
  }
  // Affiche/cache le bouton "Annuler" selon qu'il y a un undo dispo
  if (rewriteUndoBtn) rewriteUndoBtn.hidden = (lastRewriteOriginal === null);
  rewritePopover.hidden = false;
  // Click outside → close. addEventListener once: true puis recreate à
  // chaque ouverture pour ne pas leaker.
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
  // Banner discret au-dessus de #dialogue-input avec lien d'annulation.
  // Auto-dismiss à 8 s (pas trop court pour un éventuel undo réfléchi,
  // pas trop long pour ne pas polluer la UI).
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
  // Phase A.10.17 : cible = textarea-source du rewrite (mémorisée par
  // performRewrite). Permet undo correct quand l'édition s'est terminée
  // entre le rewrite et le undo. Fallback userInput sinon.
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
  if (rewriteBannerHandle) { clearTimeout(rewriteBannerHandle); rewriteBannerHandle = null; }
  refreshRewriteBtnState();
}

async function performRewrite(intent) {
  closeRewritePopover();
  // Phase A.10.17 : cible = textarea de la bulle en édition si active,
  // sinon userInput. Mémorise la cible pour undoLastRewrite (qui doit
  // pouvoir restaurer même si l'édition s'est terminée entre-temps).
  const ta = _getActiveTextarea();
  const text = ta.value.trim();
  if (!text || text.length < 8) {
    alert("Pas assez de texte pour reformuler.");
    return;
  }
  // Phase v15.7.1 : capte la dernière bulle Compagnon comme contexte
  // d'ancrage pour le rewriter (résolution des pronoms « celle/il/ça »
  // et alignement du vocabulaire technique sur celui du tuteur). Le
  // backend cap à REWRITE_MAX_CONTEXT_CHARS et n'autorise PAS le
  // rewriter à toucher au fond du brouillon.
  const contextTutor = getLastTutorTurnText();
  // Annule un rewrite précédent encore en vol, sinon ses résultats
  // tardifs viendraient écraser un input qui aurait été modifié entre-temps.
  if (rewriteInFlightAbort) { try { rewriteInFlightAbort.abort(); } catch (_) {} }
  rewriteInFlightAbort = new AbortController();
  const myAbort = rewriteInFlightAbort;
  // UI feedback : bouton ✨ → ⏳ pulsé, textarea read-only pour éviter les
  // modifs concurrentes pendant que le serveur travaille.
  rewriteBtn.classList.add("busy");
  rewriteBtn.textContent = "⏳";
  rewriteBtn.disabled = true;
  ta.readOnly = true;
  try {
    const body = {text, intent};
    if (contextTutor) body.context_tutor = contextTutor;
    const r = await fetch("/api/rewrite", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
      signal: myAbort.signal,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const detail = data.detail || data.error || r.status;
      const failedEngine = data.engine || "?";
      if (r.status === 429) {
        // Phase v15.6.4 : moteur indisponible pour cette requête (solde
        // vide, TPM dépassé, contexte trop grand…). Pas d'auto-fallback
        // (l'utilisateur a choisi son moteur pour des raisons précises).
        // On propose explicitement de basculer via un confirm avec
        // message FR explicite + flash visuel sur le sélecteur.
        const fr = formatQuotaErrorFr(failedEngine, detail);
        const yes = window.confirm(
          fr.title + "\n\n" + fr.cause + "\n\n" + fr.suggestion + "\n\n" +
          "Détail technique : " + (detail || "").slice(0, 200) + "\n\n" +
          "Changer de moteur maintenant ?",
        );
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
  rewriteBtn.addEventListener("click", (ev) => {
    ev.stopPropagation();  // évite que le click outside listener se déclenche
    openRewritePopover();
  });
}
if (rewritePopover) {
  rewritePopover.querySelectorAll(".rewrite-action").forEach(btn => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const intent = btn.dataset.intent;
      if (intent) performRewrite(intent);
    });
  });
}
if (rewriteUndoBtn) {
  rewriteUndoBtn.addEventListener("click", (ev) => {
    ev.stopPropagation();
    closeRewritePopover();
    undoLastRewrite();
  });
}
// Écho input → état du bouton ✨ (activable selon longueur).
userInput.addEventListener("input", refreshRewriteBtnState);

// ============================================================ Find similar exo (Phase Z.8.4)
// Bouton 💡 visible en mode colle uniquement. Click → prompt léger
// pour décrire le blocage → POST /api/find_similar_exo (1 appel
// Claude jetable avec accès FS scopé COURS/{matiere}/, mode guidé,
// system prompt qui interdit le corrigé en cours). Résultat rendu
// dans une bulle système dédiée, la conv principale n'est PAS
// polluée (le tuteur de la colle ne voit pas l'exo trouvé).

let findExoInFlightAbort = null;

// Phase Z.9 : mémoire des exos voisins déjà proposés dans la session.
// Chaque entrée : {matiere, type, num, exo}. Reset à init session,
// passé au backend via `exclude` à chaque /api/find_similar_exo pour
// éviter les répétitions au re-clic 🔄.
let foundExoHistory = [];

// Phase Z.9 : mémoire des URLs déjà vues (web search + YouTube).
// Permet à l'utilisateur de cliquer "Autre vidéo" / "Autre ressource"
// sans retomber sur les mêmes liens. Passé au backend via exclude_urls.
let seenWebUrls = [];
let seenYoutubeUrls = [];

async function performFindSimilarExo(opts = {}) {
  // Phase Z.8.6 : opts.description (string) court-circuite le prompt manuel.
  // Phase Z.9 : opts.difficulty ("easier"|"harder"|"different") +
  // opts.exclude (liste de {matiere,type,num,exo}) passés au backend.
  let trimmed;
  if (opts.description != null) {
    trimmed = String(opts.description).trim();
    if (trimmed.length < 4) {
      alert("Contexte insuffisant pour la recherche.");
      return;
    }
  } else {
    if (!findExoBtn || findExoBtn.disabled) return;
    const description = window.prompt(
      "Décris brièvement sur quoi tu bloques (ex : « le calcul du bit de parité dans Hamming »). " +
      "Le compagnon va chercher un exo voisin dans tes cours pour t'entraîner.",
      "",
    );
    if (description == null) return;  // user a annulé
    trimmed = description.trim();
    if (trimmed.length < 4) {
      alert("Décris en quelques mots sur quoi tu bloques.");
      return;
    }
  }
  if (findExoInFlightAbort) { try { findExoInFlightAbort.abort(); } catch (_) {} }
  findExoInFlightAbort = new AbortController();
  const myAbort = findExoInFlightAbort;

  // Bulle "🔍 Recherche en cours..." qui sera remplacée par le résultat
  const searchLabel = opts.difficulty === "easier"
    ? "📉 Recherche d'un exo plus simple…"
    : opts.difficulty === "harder"
      ? "📈 Recherche d'un exo plus dur…"
      : opts.difficulty === "different"
        ? "🔄 Recherche d'un autre angle…"
        : "🔍 Recherche d'un exercice voisin dans tes cours…";
  const searchingBubble = appendTurn("system", searchLabel);
  const searchingTurn = searchingBubble && searchingBubble.parentElement;
  // Le bouton 🔍 footer peut être hidden (mode guidé) ou absent (DOM ?),
  // dans ce cas on saute le state visuel, la bulle "Recherche…" sert
  // d'indicateur. Idem si l'appel vient de la tone-toolbar (la
  // désactivation du bouton parent est gérée par son listener).
  if (findExoBtn) {
    findExoBtn.classList.add("busy");
    findExoBtn.textContent = "⏳";
    findExoBtn.disabled = true;
  }
  try {
    const r = await fetch("/api/find_similar_exo", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        description: trimmed,
        difficulty: opts.difficulty || null,
        exclude: foundExoHistory,
      }),
      signal: myAbort.signal,
    });
    const data = await r.json().catch(() => ({}));
    if (searchingTurn) searchingTurn.remove();
    if (!r.ok) {
      const detail = data.detail || data.error || r.status;
      if (r.status === 429) {
        const fr = (typeof formatQuotaErrorFr === "function")
          ? formatQuotaErrorFr(data.engine || "?", detail)
          : null;
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
      // Phase Z.9 : bulle "rien trouvé" avec bouton 🌐 vers web search.
      _renderEmptyExoBubble(data.reason || "Aucun exercice voisin trouvé dans tes cours.", trimmed);
      return;
    }
    // Phase Z.9 : mémorise l'exo trouvé pour éviter la répétition.
    if (data.exo) {
      foundExoHistory.push({
        matiere: data.exo.matiere || "",
        type: data.exo.type || "",
        num: data.exo.num || "",
        exo: data.exo.exo || "",
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

// Phase Z.8.8 : helper réutilisable pour générer un bouton qui ouvre
// un fichier de COURS/ dans un nouvel onglet via /api/cours_file. Sert
// à toutes les bulles système qui référencent un fichier (exo voisin,
// pointe-moi le CM, recherche internet avec PDF associé, etc.).
//
// @param {string} relPath, chemin relatif à COURS_ROOT, format POSIX
// @param {string} label  , texte du bouton (avec emoji recommandé)
// @param {string} title  , tooltip détaillée (peut être plus longue)
// @returns {HTMLAnchorElement}
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
  // Bulle système dédiée, plus riche que les notifications standard.
  // Contient label, why, énoncé, et un avertissement « le tuteur de
  // la colle ne le voit pas » pour rappeler que c'est isolé.
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
  labelDiv.textContent = `📚 ${safeLabelTxt}` +
    (safeMat ? `   ·   ${safeMat} ${safeType}${safeNum} ex ${safeExo}` : "");
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
  hint.textContent =
    "⚠ Le tuteur de la colle ne voit pas cet exo. Quand tu reviens, " +
    "dis-le-lui pour qu'il sache que tu as fait le détour.";
  wrapper.appendChild(hint);

  // Phase Z.8.8 : boutons inline dans la bulle pour ouvrir les fichiers
  // PDF référencés par l'exo voisin (énoncé + corrigés). Servent à
  // l'utilisateur de voir l'énoncé complet (avec schémas, équations
  // formatées) et le corrigé après avoir tenté l'exo. Helper réutilisé
  // par les futurs boutons (recherche internet, pointer le CM, etc.).
  const fileActions = document.createElement("div");
  fileActions.className = "found-exo-files";

  if (exo.enonce_pdf_path) {
    fileActions.appendChild(_makeOpenFileBtn(
      exo.enonce_pdf_path,
      "📄 Voir l'énoncé PDF",
      "Ouvre l'énoncé original (PDF complet avec schémas)",
    ));
  }
  const corrPaths = Array.isArray(exo.correction_pdf_paths) ? exo.correction_pdf_paths : [];
  if (corrPaths.length === 1) {
    fileActions.appendChild(_makeOpenFileBtn(
      corrPaths[0],
      "✅ Voir le corrigé PDF",
      "Ouvre le corrigé du prof, à n'utiliser qu'APRÈS avoir tenté l'exo voisin chez toi",
    ));
  } else if (corrPaths.length > 1) {
    // Plusieurs corrigés (1 par sous-question), un bouton par fichier
    corrPaths.forEach((p, i) => {
      fileActions.appendChild(_makeOpenFileBtn(
        p,
        `✅ Corrigé ${i + 1}`,
        `Ouvre ${p.split("/").pop()}`,
      ));
    });
  }
  if (fileActions.childElementCount > 0) {
    wrapper.appendChild(fileActions);
  }

  // Phase Z.9 : boutons "pas satisfait, autre chose ?" : variantes de
  // difficulté, autre angle, recherche internet, vidéo YouTube. Chacun
  // déclenche un nouvel appel et rend une nouvelle bulle.
  const altActions = document.createElement("div");
  altActions.className = "found-exo-alts";
  const altLabel = document.createElement("span");
  altLabel.className = "found-exo-alts-label";
  altLabel.textContent = "Pas satisfait ?";
  altActions.appendChild(altLabel);

  const desc = description || "(contexte précédent)";
  const mkAlt = (label, title, handler) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "found-exo-alt-btn";
    b.title = title; b.textContent = label;
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      b.disabled = true;
      handler().finally(() => { b.disabled = false; });
    });
    altActions.appendChild(b);
  };
  mkAlt("📉 Plus simple", "Trouve un exo voisin plus simple",
    () => performFindSimilarExo({ description: desc, difficulty: "easier" }));
  mkAlt("📈 Plus dur", "Trouve un exo voisin plus difficile",
    () => performFindSimilarExo({ description: desc, difficulty: "harder" }));
  mkAlt("🔄 Autre angle", "Trouve un exo voisin sous un autre angle",
    () => performFindSimilarExo({ description: desc, difficulty: "different" }));
  mkAlt("✏ Affiner", "Précise ta demande (texte libre) avant de relancer la recherche",
    () => _refineAndRelaunch(desc));
  mkAlt("🌐 Sur internet", "Cherche des ressources sur internet (sites éducatifs FR)",
    () => performWebSearchExo(desc));
  mkAlt("🎬 Vidéo YouTube", "Trouve une vidéo explicative sur YouTube",
    () => performFindYoutube(desc));
  wrapper.appendChild(altActions);

  // Action : copier l'énoncé dans le clipboard + masquer
  const actions = document.createElement("div");
  actions.className = "turn-actions";
  if (exo.enonce) {
    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "found-exo-copy";
    copyBtn.title = "Copier l'énoncé";
    copyBtn.textContent = "📋";
    copyBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      try {
        await navigator.clipboard.writeText(exo.enonce);
        copyBtn.textContent = "✓";
        setTimeout(() => { copyBtn.textContent = "📋"; }, 1500);
      } catch (_) { copyBtn.textContent = "✗"; }
    });
    actions.appendChild(copyBtn);
  }
  const delBtn = document.createElement("button");
  delBtn.type = "button"; delBtn.className = "turn-del-btn";
  delBtn.title = "Masquer";
  delBtn.textContent = "🗑";
  delBtn.addEventListener("click", (e) => {
    e.stopPropagation(); wrapper.remove();
  });
  actions.appendChild(delBtn);
  wrapper.appendChild(actions);

  dialogue.appendChild(wrapper);
  dialogue.scrollTop = dialogue.scrollHeight;
}

if (findExoBtn) {
  findExoBtn.addEventListener("click", (ev) => {
    ev.stopPropagation();
    performFindSimilarExo();
  });
}

// ============================================================ Web search / YouTube / CM passage (Phase Z.9)
// 3 nouvelles recherches isolées, mêmes patterns que find_similar_exo :
//   - performWebSearchExo(description) → /api/web_search_exo
//   - performFindYoutube(description) → /api/find_youtube_video
//   - performFindCmPassage(description) → /api/find_cm_passage

// Phase Z.9.2 : bouton "✏ Affiner" dans "Pas satisfait ?". Demande à
// l'utilisateur de préciser sa demande, l'ajoute en post-scriptum à la
// description contextuelle existante et relance la recherche d'exo voisin.
async function _refineAndRelaunch(baseDescription) {
  const refinement = window.prompt(
    "Précise ta demande pour la prochaine recherche d'exo voisin :\n" +
    "(ex: « plus axé table de vérité », « avec un cas industriel concret », " +
    "« sans calcul, juste raisonnement »)",
    "",
  );
  if (refinement == null) return;
  const trimmed = refinement.trim();
  if (trimmed.length < 4) {
    alert("Précision trop courte, abandon.");
    return;
  }
  const enriched =
    (baseDescription || "").trim() +
    "\n\nPRÉCISION DE L'ÉTUDIANT : " + trimmed;
  await performFindSimilarExo({ description: enriched });
}

// Phase Z.9.4 → Z.9.5 : bulle d'erreur avec query éditable + lien direct.
// L'utilisateur voit les mots-clés extraits, peut les modifier, puis
// clique pour ouvrir Google ou YouTube. L'algo natif est beaucoup plus
// fiable que les hallucinations LLM.
function _renderSearchFailedBubble(emoji, reason, description, target, refinedData = null) {
  const wrapper = document.createElement("div");
  wrapper.className = "turn system found-exo-bubble";
  if (target === "youtube") wrapper.classList.add("found-video-bubble");
  else if (target === "google") wrapper.classList.add("found-web-bubble");
  wrapper.dataset.localOnly = "1";
  _appendBubbleHeader(wrapper, `${emoji} Recherche infructueuse`);
  const reasonDiv = document.createElement("div");
  reasonDiv.className = "found-exo-why";
  reasonDiv.textContent = reason;
  wrapper.appendChild(reasonDiv);

  // Phase Z.9.5 : input éditable + bouton via helper factorisé.
  // Phase v15.7.14 : refinedData propagé pour pré-remplir avec la
  // query Gemini Flash + activer le marker ✨ et le bouton 🔄.
  _appendDirectSearchInput(wrapper, description, target === "youtube" ? "youtube" : "google", refinedData);
  _appendDelButton(wrapper);
  dialogue.appendChild(wrapper);
  dialogue.scrollTop = dialogue.scrollHeight;
}

// Phase Z.9.5 : helper réutilisable : ajoute à `wrapper` un bloc
// "Mots-clés à chercher : <input>" + bouton "Chercher sur Google/YouTube"
// qui ouvre la query éditée dans un nouvel onglet. Réutilisé par les
// bulles de résultats web/youtube ET par les bulles d'erreur.
function _appendDirectSearchInput(wrapper, description, target, refinedData = null) {
  // Phase v15.7.14 : Si refinedData est fourni (la query a déjà été
  // raffinée par Gemini Flash en amont via /api/refine_search_query),
  // on l'utilise directement et on ajoute un marker ✨ + bouton 🔄.
  // Sinon : pré-remplit avec heuristique JS (instantané) PUIS refine
  // async pour remplacer.
  const initialQuery = refinedData?.query || _extractSimpleSearchQuery(description);
  const queryDiv = document.createElement("div");
  queryDiv.className = "found-search-query";
  const queryLabel = document.createElement("label");
  queryLabel.innerHTML = "Pas ce que tu voulais ? Édite la query " +
    '<span class="refined-marker" title="Query reformulée par Gemini Flash" hidden>✨</span> : ';
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
  const baseUrl = target === "youtube"
    ? "https://www.youtube.com/results?search_query="
    : "https://www.google.com/search?q=";
  const btnLabel = target === "youtube"
    ? "🔍 Chercher sur YouTube"
    : "🔍 Chercher sur Google";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "found-exo-direct-search-btn";
  btn.textContent = btnLabel;
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    const q = (queryInput.value || "").trim();
    if (!q) { queryInput.focus(); return; }
    window.open(baseUrl + encodeURIComponent(q), "_blank", "noopener");
  });
  queryInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); btn.click(); }
  });
  queryDiv.appendChild(btn);

  // Phase v15.7.14 : bouton 🔄 Reformuler. État local : queries déjà
  // proposées (initiale + alts), à exclude au prochain refine pour
  // tourner les angles. Disabled pendant le call refine.
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
  reBtn.addEventListener("click", async (e) => {
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
        // Pas d'alt dispo, on pourrait alterner entre les alts initiales
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

  // Si pas de refinedData fourni (cas legacy : appelé hors d'un perform*),
  // lance un refine en background pour upgrader le pré-remplissage. Le
  // user voit l'heuristique en attendant (~1s), puis ça devient ✨.
  if (!refinedData) {
    (async () => {
      try {
        const fresh = await _refineSearchQuery(description, target, []);
        if (fresh && fresh.query && queryInput.value === initialQuery) {
          // Remplace seulement si l'user n'a pas déjà touché à l'input.
          queryInput.value = fresh.query;
          triedQueries.add(fresh.query);
          (fresh.alternatives || []).forEach(a => triedQueries.add(a));
          if (refinedMarker) refinedMarker.hidden = false;
        }
      } catch (_) { /* heuristique reste, pas d'alerte */ }
    })();
  } else if (refinedMarker) {
    refinedMarker.hidden = false;
  }
}

// Phase v15.7.14 : appelle /api/refine_search_query (Gemini Flash).
// Renvoie {query, alternatives} ou null si erreur.
async function _refineSearchQuery(description, target, exclude = []) {
  if (!description) return null;
  try {
    const r = await fetch("/api/refine_search_query", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ description, target, exclude }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      console.warn("refine_search_query a échoué :", data);
      return null;
    }
    return { query: data.query, alternatives: data.alternatives || [] };
  } catch (e) {
    console.warn("refine_search_query erreur réseau :", e);
    return null;
  }
}

// Phase Z.9.5 : extrait des mots-clés courts et concrets depuis une
// description structurée (qui contient des préambules type "Le tuteur
// vient de me dire :", "PRÉCISION DE L'ÉTUDIANT :", etc.). Retourne
// une query type "multiplexeur MUX21 fonction" plutôt que la phrase
// complète bruitée. L'utilisateur peut éditer après.
function _extractSimpleSearchQuery(description) {
  if (!description) return "";
  let text = String(description);
  // Phase v15.7.12 : strip markdown images / pièces jointes
  text = _stripAttachmentMarkdown(text);

  // Phase v15.7.13 : extrait la portion TUTEUR uniquement. Le bloc
  // student (« Ma dernière intervention était : … ») est inutile pour
  // une query courte (souvent conversationnel type « Là c'est mieux ? »)
  // et POLLUE la query : seul le tuteur a le vocabulaire technique
  // (COMP, S[1:0], MUX21, table de vérité, etc.). On split sur les
  // marqueurs et on garde uniquement le bloc tuteur.
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
  // Retire les blocs de fin (Je bloque, PRÉCISION, trouve-moi)
  tutorPart = tutorPart.replace(/Je bloque pour répondre[\s\S]*$/i, "");
  tutorPart = tutorPart.replace(/PRÉCISION DE L'ÉTUDIANT\s*:[\s\S]*$/i, "");
  tutorPart = tutorPart.replace(/trouve-moi\s+dans\s+mes\s+cours[\s\S]*$/i, "");
  // Normalise espaces. Si le marker tuteur était absent (texte raw),
  // fallback sur le texte original sans les blocs de préambule globaux.
  let workText = tutorPart.replace(/\s+/g, " ").trim();
  if (!workText) {
    workText = text
      .replace(/Le tuteur vient de me (?:dire|demander)\s*\/?\s*(?:demander)?\s*:/gi, "")
      .replace(/Ma dernière intervention était\s*:/gi, "")
      .replace(/Je bloque pour répondre[\s\S]*$/i, "")
      .replace(/PRÉCISION DE L'ÉTUDIANT\s*:[\s\S]*$/i, "")
      .replace(/trouve-moi\s+dans\s+mes\s+cours[\s\S]*$/i, "")
      .replace(/\s+/g, " ").trim();
  }
  if (!workText) return "";

  // Découpe en phrases.
  const sentences = workText.split(/(?<=[.?!])\s+/)
    .map(s => s.trim().replace(/^[-*•·]\s*/, ""))
    .filter(s => s.length >= 8);
  let pick = "";
  if (sentences.length === 0) {
    pick = workText;
  } else {
    // Phase v15.7.13 : heuristique « densité technique » : préfère les
    // phrases qui contiennent du jargon (notation [N:M] ou [N], mots en
    // MAJUSCULES de longueur >= 2 type COMP/MUX/SEL, identifiants type
    // MUX21 ou A2). Ces phrases sont la VRAIE question du tuteur ;
    // les phrases neutres (« Correct. », « Établissez la table sur
    // papier et envoyez la photo. ») sont du remplissage moins utile
    // pour une recherche externe.
    const techRegex = /\[[0-9]+(?::[0-9]+)?\]|\b[A-Z]{2,}\b|\b[A-Z][a-z]*[0-9]+\b/g;
    const scored = sentences.map(s => {
      const matches = s.match(techRegex) || [];
      return { s, score: matches.length, len: s.length };
    });
    const techPhrases = scored.filter(x => x.score > 0 && x.len <= 220);
    if (techPhrases.length > 0) {
      // Préfère la dernière phrase technique (souvent la plus récente
      // dans le tour, donc la question active).
      pick = techPhrases[techPhrases.length - 1].s;
    } else {
      const candidates = scored.filter(x => x.len <= 200);
      pick = candidates.length > 0
        ? candidates[candidates.length - 1].s
        : sentences[sentences.length - 1];
    }
  }
  // Phase v15.7.13 : strip du préfixe « Question N.N : » qui prend de
  // la place sans aider la recherche.
  pick = pick.replace(/^Question\s+\d+(?:[.,]\d+)?\s*:\s*/i, "");
  // Nettoie ponctuation finale et limite à 100 chars (relevé de 80 à 100
  // pour laisser passer les phrases techniques moyennes type « analysez
  // le composant COMP pour déterminer S[1:0] en fonction de A[2:0] »).
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
    b.type = "button"; b.className = "found-exo-alt-btn";
    b.title = title; b.textContent = label;
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      b.disabled = true;
      handler().finally(() => { b.disabled = false; });
    });
    altActions.appendChild(b);
  };
  mkAlt("🌐 Sur internet", "Cherche des ressources externes",
    () => performWebSearchExo(description));
  mkAlt("🎬 Vidéo YouTube", "Trouve une vidéo explicative",
    () => performFindYoutube(description));
  mkAlt("📚 Passage du CM", "Pointe-moi le passage du cours sur ce concept",
    () => performFindCmPassage(description));
  wrapper.appendChild(altActions);
  dialogue.appendChild(wrapper);
  dialogue.scrollTop = dialogue.scrollHeight;
}

async function performWebSearchExo(description, opts = {}) {
  if (!description || description.length < 4) {
    alert("Description manquante pour la recherche internet.");
    return;
  }
  // Phase Z.9.4 : opts.forceEngine ("api_anthropic" | "gemini_api")
  // pour le bouton « Réessayer sur Claude API ».
  const labelExtra = opts.forceEngine === "api_anthropic" ? " (Claude API)" : "";
  // Phase v15.7.14 : refine la query AVANT de lancer la recherche.
  // ~1-2s de latence, mais le LLM principal reçoit ensuite des mots-clés
  // techniques au lieu de bricoler depuis la description verbeuse.
  const refiningBubble = appendTurn("system", `✨ Reformulation de la query…`);
  const refiningTurn = refiningBubble && refiningBubble.parentElement;
  const refinedData = await _refineSearchQuery(description, "web", []);
  if (refiningTurn) refiningTurn.remove();
  const searchingBubble = appendTurn("system", `🌐 Recherche sur internet${labelExtra}…`);
  const searchingTurn = searchingBubble && searchingBubble.parentElement;
  try {
    const r = await fetch("/api/web_search_exo", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        description,
        exclude_urls: seenWebUrls,
        force_engine: opts.forceEngine || undefined,
        refined_query: refinedData?.query || undefined,  // Phase v15.7.14
      }),
    });
    const data = await r.json().catch(() => ({}));
    if (searchingTurn) searchingTurn.remove();
    if (!r.ok) {
      _handleSearchError(r.status, data, description);
      return;
    }
    if (!data.found || !(data.results || []).length) {
      const reason = data.reason || "Aucune ressource pertinente trouvée.";
      // Phase Z.9.4 : bulle d'erreur enrichie avec lien Google direct.
      _renderSearchFailedBubble("🌐", reason, description, "google", refinedData);
      return;
    }
    (data.results || []).forEach(r2 => { if (r2.url) seenWebUrls.push(r2.url); });
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
  // Phase v15.7.14 : refine via Gemini Flash en amont (~1-2s).
  const refiningBubble = appendTurn("system", "✨ Reformulation de la query…");
  const refiningTurn = refiningBubble && refiningBubble.parentElement;
  const refinedData = await _refineSearchQuery(description, "youtube", []);
  if (refiningTurn) refiningTurn.remove();
  const searchingBubble = appendTurn("system", "🎬 Recherche d'une vidéo YouTube…");
  const searchingTurn = searchingBubble && searchingBubble.parentElement;
  try {
    const r = await fetch("/api/find_youtube_video", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        description,
        exclude_urls: seenYoutubeUrls,
        refined_query: refinedData?.query || undefined,  // Phase v15.7.14
      }),
    });
    const data = await r.json().catch(() => ({}));
    if (searchingTurn) searchingTurn.remove();
    if (!r.ok) {
      _handleSearchError(r.status, data, description);
      return;
    }
    if (!data.found || !(data.results || []).length) {
      const reason = data.reason || "Aucune vidéo pertinente trouvée.";
      // Phase Z.9.4 : bulle d'erreur enrichie avec lien YouTube direct.
      _renderSearchFailedBubble("🎬", reason, description, "youtube", refinedData);
      return;
    }
    (data.results || []).forEach(v => { if (v.url) seenYoutubeUrls.push(v.url); });
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
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ description }),
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
    const ok = window.confirm(
      "🌐 La recherche internet nécessite Claude API ou Gemini.\n\n" +
      "Moteur courant : " + (data.engine || "?") + "\n\n" +
      "Bascule maintenant ? (le sélecteur en haut va clignoter)",
    );
    if (ok && typeof flashEngineSwitcher === "function") {
      flashEngineSwitcher();
    }
    return;
  }
  if (status === 429) {
    const fr = (typeof formatQuotaErrorFr === "function")
      ? formatQuotaErrorFr(data.engine || "?", detail) : null;
    if (fr) alert(fr.title + "\n\n" + fr.cause + "\n\n" + fr.suggestion);
    else alert("Quota épuisé : " + detail);
    return;
  }
  alert("Recherche échouée : " + detail);
}

// ============================================================ Bulles de résultat (Phase Z.9)

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
  delBtn.type = "button"; delBtn.className = "turn-del-btn";
  delBtn.title = "Masquer"; delBtn.textContent = "🗑";
  delBtn.addEventListener("click", (e) => {
    e.stopPropagation(); wrapper.remove();
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
    link.target = "_blank"; link.rel = "noopener";
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
  // Phase Z.9.5 : input éditable + bouton "Chercher sur Google" pour
  // fallback manuel. L'utilisateur peut toujours se rabattre sur l'algo
  // natif Google si les liens proposés ne lui plaisent pas.
  // Phase v15.7.14 : refinedData propagé pour pré-remplir avec query Gemini.
  _appendDirectSearchInput(wrapper, description, "google", refinedData);
  // Bouton "Autre ressource"
  const altActions = document.createElement("div");
  altActions.className = "found-exo-alts";
  const altBtn = document.createElement("button");
  altBtn.type = "button"; altBtn.className = "found-exo-alt-btn";
  altBtn.textContent = "🌐 Autre ressource";
  altBtn.title = "Cherche d'autres ressources internet (différentes de celles déjà vues)";
  altBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    altBtn.disabled = true;
    performWebSearchExo(description).finally(() => { altBtn.disabled = false; });
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
    link.href = v.url || "#"; link.target = "_blank"; link.rel = "noopener";
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
  // Phase Z.9.5 : input éditable + bouton "Chercher sur YouTube" pour
  // fallback manuel quand les vidéos proposées ne plaisent pas (ou sont
  // mortes). Algo natif YouTube > hallucination LLM.
  // Phase v15.7.14 : refinedData propagé pour pré-remplir avec query Gemini.
  _appendDirectSearchInput(wrapper, description, "youtube", refinedData);
  // Bouton "Autre vidéo"
  const altActions = document.createElement("div");
  altActions.className = "found-exo-alts";
  const altBtn = document.createElement("button");
  altBtn.type = "button"; altBtn.className = "found-exo-alt-btn";
  altBtn.textContent = "🎬 Autre vidéo";
  altBtn.title = "Trouve une autre vidéo (différente de celles déjà vues)";
  altBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    altBtn.disabled = true;
    performFindYoutube(description).finally(() => { altBtn.disabled = false; });
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
    fileActions.appendChild(_makeOpenFileBtn(
      passage.pdf_path,
      "📄 Ouvrir le PDF",
      "Ouvre le poly du CM dans un nouvel onglet",
    ));
    wrapper.appendChild(fileActions);
  }
  _appendDelButton(wrapper);
  dialogue.appendChild(wrapper);
  dialogue.scrollTop = dialogue.scrollHeight;
}

// ============================================================ Pièces jointes (Phase A.7.2 v10)
// Trois sources convergent vers la même file d'attente backend
// (pending_attachments) : bouton 📎, paste clipboard (Ctrl+V), drag&drop.
// Le bandeau au-dessus du champ d'input affiche les thumbnails et permet
// de retirer une pièce avant l'envoi. Au clic Envoyer, les paths sont
// injectés dans le texte (markdown pour images, mention texte pour PDF).
// Une mini-app mobile (page /mobile) pousse aussi dans cette queue depuis
// le téléphone, vu en quasi-temps-réel grâce au polling 2s.

const attachmentsTray = $("#attachments-tray");

async function uploadAttachmentFile(file) {
  if (!file) return null;
  // Phase v15.7.22 : pré-preview Cropper auto pour les images, alignement
  // UX Clipboard_Relay v0.1.5. PDF/Excel/audio/vidéo/etc → upload direct
  // comme avant. L'utilisateur peut recadrer, pivoter, ou cliquer
  // « Envoyer tel quel » s'il ne veut pas modifier l'image.
  if (file.type && file.type.startsWith("image/")) {
    const previewResult = await _openImagePreviewBeforeUpload(file);
    if (previewResult === null) {
      // L'utilisateur a annulé. On n'upload rien.
      return null;
    }
    file = previewResult;  // soit cropped, soit l'original (Envoyer tel quel)
  }
  const fd = new FormData();
  fd.append("file", file, file.name || "attachment.bin");
  // Phase A.8.5 : si édition active, on upload en mode staged et on
  // insère le markdown directement dans le textarea (pas dans le tray).
  // Permet de coller / drag-drop / choisir un fichier pour enrichir un
  // message en cours d'édition sans polluer le tray ni avoir à fermer
  // l'édition pour envoyer un nouveau message.
  // Phase A.8.5 hotfix : sanity check : si _activeEditTextarea pointe
  // vers un élément orphelin (zone détruite par rerender sans cleanup),
  // on reset à null avant de décider du flow.
  if (_activeEditTextarea && !document.body.contains(_activeEditTextarea)) {
    _setActiveEditTextarea(null);
  }
  const isEditMode = _activeEditTextarea !== null;
  if (isEditMode) fd.append("staged", "1");
  try {
    const r = await fetch("/api/upload_attachment", { method: "POST", body: fd });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      alert(`Upload "${file.name}" échoué : ${data.error || r.status}`);
      return null;
    }
    if (isEditMode && data.is_image) {
      _insertImageMarkdownInEdit(data);
      _flashSelectionFeedback("📷 Image ajoutée à l'édition");
    } else if (isEditMode && !data.is_image) {
      // Non-image en édition : on insère la mention texte.
      // Phase A.10.13.bug2 : préfixe `_uploads/` pour storage="uploads".
      const relWithPrefix = _relWithStoragePrefix(data);
      const md = `[Pièce jointe : ${data.original_name || data.filename} (${relWithPrefix})]`;
      const ta = _activeEditTextarea;
      const sep = ta.value && !ta.value.endsWith("\n\n") ? "\n\n" : "";
      ta.value += sep + md;
      _flashSelectionFeedback("📎 Pièce jointe ajoutée à l'édition");
    } else {
      refreshAttachmentsTray();  // sync immédiate (avant le poll)
    }
    return data;
  } catch (e) {
    alert(`Erreur réseau upload "${file.name}" : ${e.message}`);
    return null;
  }
}

// ============================================================ Preview Cropper avant upload (Phase v15.7.22)
// Pattern emprunté à Clipboard_Relay v0.1.5 : quand une image arrive
// par n'importe quel canal (📎 / paste / drag-drop / 📷 mobile via
// /mobile), on ouvre une modal AVEC Cropper pré-actif (sans clic sur
// un icône) pour permettre crop + rotation + reset, OU bouton « Envoyer
// tel quel » si la photo est déjà clean, OU Annuler.
//
// Modal distincte de #crop-modal (qui sert au re-crop d'un attachment
// DÉJÀ uploadé via le bouton ✂ du tray, Phase v15.7.10).

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
  return new Promise((resolve) => {
    if (!cropPreviewModal || !cropPreviewImg) {
      // Modal pas dans le DOM (vieux index.html ?) → upload direct.
      resolve(file);
      return;
    }
    if (typeof Cropper === "undefined") {
      console.warn("Cropper.js non chargé, upload direct sans preview.");
      resolve(file);
      return;
    }
    cropPreviewResolve = resolve;
    cropPreviewModal._originalFile = file;  // pour "Envoyer tel quel"
    const reader = new FileReader();
    reader.onload = (e) => {
      cropPreviewImg.src = e.target.result;
      cropPreviewModal.hidden = false;
      cropPreviewImg.onload = () => {
        if (cropPreviewInstance) {
          try { cropPreviewInstance.destroy(); } catch (_) {}
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
    try { cropPreviewInstance.destroy(); } catch (_) {}
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
  // Envoie le file original sans modif
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
      maxWidth: 2000, maxHeight: 2000,
      imageSmoothingEnabled: true, imageSmoothingQuality: "high",
    });
    if (!canvas) { alert("Aucune zone à recadrer."); return; }
    const blob = await new Promise(r => canvas.toBlob(r, "image/jpeg", 0.92));
    if (!blob) { alert("Échec export canvas."); return; }
    const fname = "cropped_" + Date.now() + ".jpg";
    const cropped = new File([blob], fname, { type: "image/jpeg" });
    _closeCropPreviewModal(cropped);
  } catch (e) {
    alert("Erreur cropper : " + e.message);
  } finally {
    cropPreviewApply.disabled = false;
    cropPreviewApply.textContent = orig;
  }
});
// Échap pour annuler
document.addEventListener("keydown", (e) => {
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
    // Phase A.8.5 : si édition active, intercepte les NOUVEAUX attachments
    // (id pas dans _editAttachmentSeenIds, snapshot pris à l'ouverture
    // de l'édit). Cas typique : user prend une photo via /mobile pendant
    // qu'il édite un message → la photo doit aller dans le textarea édité,
    // pas dans le tray habituel. DELETE backend pour éviter doublon.
    // Phase A.8.5 hotfix : sanity check : si textarea orphelin (zone
    // détruite par rerender), reset _activeEditTextarea avant de décider.
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
          // Non-image : on insère la mention texte aussi.
          // Phase A.10.13.bug2 : préfixe `_uploads/` pour storage="uploads".
          const relWithPrefix = _relWithStoragePrefix(att);
          const md = `[Pièce jointe : ${att.original_name || att.filename} (${relWithPrefix})]`;
          const ta = _activeEditTextarea;
          const sep = ta.value && !ta.value.endsWith("\n\n") ? "\n\n" : "";
          ta.value += sep + md;
          redirected.push(att);
        }
      }
      // DELETE async les attachments redirigés pour qu'ils ne restent
      // pas dans le tray + soient consommés. Best-effort, on ignore les
      // échecs (le prochain tick re-tentera).
      for (const att of redirected) {
        try {
          await fetch(`/api/pending_attachments/${att.id}`, { method: "DELETE" });
        } catch (_) {}
      }
      if (redirected.length > 0) {
        _flashSelectionFeedback(
          redirected.length === 1
            ? "📷 Photo insérée dans l'édition"
            : `📷 ${redirected.length} pièces insérées dans l'édition`,
        );
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
        img.src = imgSrc; img.alt = "";
        img.style.cssText = "width:100%;height:100%;object-fit:cover;border-radius:3px;cursor:zoom-in;";
        img.title = "Cliquer pour agrandir";
        img.addEventListener("click", (e) => {
          e.stopPropagation();
          openLightbox(imgSrc);
        });
        thumb.appendChild(img);
      } else {
        // Icône selon extension
        const ext = (att.filename || "").split(".").pop().toLowerCase();
        const icon = ({
          pdf: "📕", doc: "📄", docx: "📄",
          xls: "📊", xlsx: "📊", csv: "📊",
          ppt: "📽", pptx: "📽",
          txt: "📝", md: "📝", json: "🧾",
        })[ext] || "📎";
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
      // Phase v15.7.10 : bouton ✂ Rogner pour les images uniquement
      // (PDF/Excel/etc. n'ont pas de sens à cropper).
      if (att.is_image) {
        const crop = document.createElement("button");
        crop.className = "att-crop"; crop.type = "button";
        crop.textContent = "✂"; crop.title = "Rogner cette photo";
        crop.addEventListener("click", () => openCropModal(att));
        item.appendChild(thumb);
        item.appendChild(info);
        item.appendChild(crop);
      } else {
        item.appendChild(thumb);
        item.appendChild(info);
      }
      const del = document.createElement("button");
      del.className = "att-del"; del.type = "button";
      del.textContent = "🗑"; del.title = "Retirer cette pièce jointe";
      del.addEventListener("click", async () => {
        try {
          await fetch(`/api/pending_attachments/${encodeURIComponent(att.id)}`,
                      { method: "DELETE" });
          refreshAttachmentsTray();
        } catch (e) { alert("Erreur : " + e.message); }
      });
      item.appendChild(del);
      attachmentsTray.appendChild(item);
    }
  } catch (e) {
    /* polling silencieux */
  }
}

function formatAttSize(bytes) {
  if (!bytes) return "0";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " kB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

// Bouton 📎 : ouvre le file picker, accepte tous types
if (mediaBtn) {
  mediaBtn.addEventListener("click", () => {
    if (mediaInput) mediaInput.click();
  });
}

if (mediaInput) {
  mediaInput.addEventListener("change", async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    for (const f of files) await uploadAttachmentFile(f);
    mediaInput.value = "";
    userInput.focus();
  });
}

// ============================================================ Bouton 📷 Photo (Phase v15.7.10)
// Workflow distinct du 📎 (fichier générique) :
//  - Sur mobile (touch + viewport étroit) → input file capture="environment"
//    (caméra arrière native du téléphone). UX standard mobile.
//  - Sur desktop → bascule sur l'onglet « 🔗 Distant » et le scintille,
//    pour pointer le QR/URL Tailscale Funnel. Pas de webcam desktop : en
//    révision papier, le cahier n'est pas devant le laptop.

const photoBtn = $("#photo-btn");
const photoInput = $("#photo-input");

function isMobileDeviceForPhoto() {
  // Touch capability + viewport étroit. Pourquoi ces deux : juste le
  // touch coche les laptops Windows tactiles (pas le bon comportement,
  // ils ont une vraie webcam et un grand écran). Juste le viewport coche
  // un desktop maximisé. La conjonction = vrai mobile/tablette.
  const hasTouch = (navigator.maxTouchPoints > 0) || ('ontouchstart' in window);
  return hasTouch && window.innerWidth < 900;
}

function flashRemoteTab() {
  // Bascule sur l'onglet « 🔗 Distant » + 3 pulses oranges sur la pane
  // pour pointer le QR/URL d'accès distant. Pattern emprunté à
  // flashEngineSwitcher (Phase v15.6.4).
  const tab = document.querySelector('#sidebar-tabs .sb-tab[data-tab="mobile"]');
  if (tab) tab.click();  // simule click → bascule la pane
  const pane = document.querySelector('#sidebar-tab-content .sb-pane[data-pane="mobile"]');
  if (!pane) return;
  try {
    pane.scrollIntoView({behavior: "smooth", block: "center"});
  } catch (_) {}
  pane.classList.remove("flash-attention");
  void pane.offsetWidth;  // reflow forcé pour relancer l'animation
  pane.classList.add("flash-attention");
  setTimeout(() => pane.classList.remove("flash-attention"), 1900);
}

function openPhotoFlow() {
  if (isMobileDeviceForPhoto()) {
    // Mobile : déclenche l'input file avec capture="environment".
    // Le navigateur Android/iOS ouvre l'app caméra système.
    if (photoInput) photoInput.click();
  } else {
    // Desktop : bascule sur l'onglet Distant + flash. Hint visuel
    // au-dessus du tray pour expliciter pourquoi on a switché.
    flashRemoteTab();
    showPhotoDesktopHint();
  }
}

let _photoHintTimer = null;
function showPhotoDesktopHint() {
  // Petite bannière temporaire au-dessus du tray pour expliquer la
  // bascule (sinon le user pourrait penser que le bouton n'a rien fait).
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
  photoInput.addEventListener("change", async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    for (const f of files) await uploadAttachmentFile(f);
    photoInput.value = "";
    userInput.focus();
  });
}

// ============================================================ Modal crop (Phase v15.7.10)
// Cropper.js sur la photo de l'attachment cliqué via ✂ dans le tray.
// Output : POST /api/pending_attachments/<id>/replace avec le canvas
// cropped en blob → backend update l'entry (rel_path, filename, size,
// mime, cropped:true) → tray rafraîchi au prochain poll.

let cropperInstance = null;
let cropTargetAttId = null;

const cropModal = $("#crop-modal");
const cropImg = $("#crop-img");
const cropClose = $("#crop-close");
const cropCancel = $("#crop-cancel");
const cropReset = $("#crop-reset");
const cropApply = $("#crop-apply");
// Phase v15.7.16 : rotation 90° dans les 2 sens
const cropRotateLeft = $("#crop-rotate-left");
const cropRotateRight = $("#crop-rotate-right");

function openCropModal(att) {
  if (!cropModal || !cropImg) return;
  if (typeof Cropper === "undefined") {
    alert("Cropper.js non chargé. Recharge la page.");
    return;
  }
  cropTargetAttId = att.id;
  // Phase A.10.2 : route selon att.storage ("uploads" / "cours").
  cropImg.src = `${_attachmentSrcUrl(att)}&t=${Date.now()}`;
  cropImg.alt = att.original_name || att.filename || "Photo";
  cropModal.hidden = false;
  // Init Cropper après que l'image soit chargée (sinon il calcule mal
  // les dimensions du canvas).
  cropImg.onload = () => {
    if (cropperInstance) {
      try { cropperInstance.destroy(); } catch (_) {}
      cropperInstance = null;
    }
    cropperInstance = new Cropper(cropImg, _cropperOptionsCommon());
  };
}

function closeCropModal() {
  if (!cropModal) return;
  cropModal.hidden = true;
  if (cropperInstance) {
    try { cropperInstance.destroy(); } catch (_) {}
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
  const attId = cropTargetAttId;  // capture (closeCropModal va reset)
  // Extrait le canvas cropped. maxWidth/maxHeight pour éviter les images
  // gigantesques (les téléphones modernes prennent en 4032×3024 = 12 MP).
  // Cap raisonnable pour le tuteur multimodal : 2000px sur le plus grand
  // côté est largement suffisant pour lire une table de vérité.
  let canvas;
  try {
    canvas = cropperInstance.getCroppedCanvas({
      maxWidth: 2000, maxHeight: 2000,
      imageSmoothingEnabled: true, imageSmoothingQuality: "high",
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
  // canvas → blob (JPEG 0.92 par défaut, bon ratio qualité/poids)
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
    const r = await fetch(
      `/api/pending_attachments/${encodeURIComponent(attId)}/replace`,
      { method: "POST", body: fd },
    );
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
// Phase v15.7.16 : rotation 90° dans les 2 sens (photos prises de travers
// avec EXIF faux : téléphone tenu en biais, capteur pas calibré à temps).
if (cropRotateLeft) cropRotateLeft.addEventListener("click", () => {
  if (cropperInstance) cropperInstance.rotate(-90);
});
if (cropRotateRight) cropRotateRight.addEventListener("click", () => {
  if (cropperInstance) cropperInstance.rotate(90);
});
// Échap pour fermer
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && cropModal && !cropModal.hidden) {
    closeCropModal();
  }
});

// Paste clipboard (Ctrl+V dans le textarea ou n'importe où sur la page) :
// capture les images du clipboard. Pour les fichiers binaires (PDF/Excel),
// le presse-papier ne contient en général pas le fichier brut → drag&drop.
async function handlePasteEvent(e) {
  if (!activeSession) return;
  const clipData = e.clipboardData;
  if (!clipData) return;

  // Phase v15.7.29 : handler plus robuste pour les paste d'image
  // clipboard. 3 sources possibles :
  //  (A) clipboardData.items[i].kind === "file", Chrome/Firefox récents
  //  (B) clipboardData.items[i].type starts with "image/" même si
  //       kind n'est pas "file", certaines apps Windows
  //  (C) clipboardData.files, fallback browser-spec
  const files = [];
  const seen = new Set();  // dédup par taille+type (les 3 voies se chevauchent)
  const _push = (f) => {
    if (!f) return;
    const key = `${f.size}|${f.type}`;
    if (seen.has(key)) return;
    seen.add(key);
    files.push(f);
  };
  for (const it of (clipData.items || [])) {
    const isImageType = it.type && it.type.startsWith("image/");
    if (it.kind === "file" || isImageType) {
      _push(it.getAsFile());
    }
  }
  for (const f of (clipData.files || [])) {
    _push(f);
  }

  if (files.length === 0) return;
  e.preventDefault();

  // Phase v15.7.29 : image collée depuis le clipboard Windows
  // (Snipping Tool, Print Screen) arrive souvent sans name (file.name
  // === "" ou "image.png"). Stamp un nom unique pour l'upload + tri.
  const stamped = files.map((f) => {
    const hasGoodName = f.name && f.name !== "" && f.name !== "image.png";
    if (hasGoodName) return f;
    const ext = (f.type && f.type.split("/")[1]) || "bin";
    const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    return new File([f], `paste-${ts}.${ext}`, { type: f.type });
  });

  // Toast feedback : confirme visuellement que le paste a été capté.
  // Utile si le user en doute ("ça marche pas") avant que le Cropper ouvre.
  const isImg = stamped.some(f => f.type && f.type.startsWith("image/"));
  if (isImg) _flashSelectionFeedback("📷 Image collée : chargement…");

  for (const f of stamped) {
    await uploadAttachmentFile(f);
  }

  // Phase v15.7.29 : scroll auto vers le tray d'attachments en bas de
  // page. Sans ça l'user (qui regarde le chat plus haut) voit le toast
  // mais pas la thumbnail apparaître → impression que ça n'a pas marché.
  // Best-effort : si tray vide après upload (image rejetée), on ne
  // scroll pas pour rien.
  try {
    if (attachmentsTray && attachmentsTray.children.length > 0) {
      attachmentsTray.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  } catch (_) {}
}
document.addEventListener("paste", handlePasteEvent);

// Drag & drop sur toute la fenêtre
let dragDepth = 0;
document.addEventListener("dragenter", (e) => {
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
document.addEventListener("dragover", (e) => {
  if (!activeSession) return;
  if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files")) {
    e.preventDefault();
  }
});
document.addEventListener("drop", async (e) => {
  if (!activeSession) return;
  if (!e.dataTransfer || !e.dataTransfer.files || e.dataTransfer.files.length === 0) return;
  e.preventDefault();
  dragDepth = 0;
  document.body.classList.remove("drop-active");
  for (const f of Array.from(e.dataTransfer.files)) {
    await uploadAttachmentFile(f);
  }
});

// Polling 2s sur la queue serveur (sync avec photos venant du téléphone)
setInterval(refreshAttachmentsTray, 2000);
refreshAttachmentsTray();

// ============================================================ Mode guidé, init + navigation

async function initGuidedPanel(startIndex = 0, overrides = null) {
  try {
    // Phase v15.7.35 : overrides {script_path, slides_path} passés en
    // query params permettent à la modal de fallback de pointer vers
    // des fichiers spécifiques (file picker manuel ou résultat scan IA).
    const params = new URLSearchParams();
    if (overrides && overrides.script_path) params.set("script_path", overrides.script_path);
    if (overrides && overrides.slides_path) params.set("slides_path", overrides.slides_path);
    const url = "/api/guided/init" + (params.toString() ? "?" + params : "");
    const r = await fetch(url);
    // Robustesse : si l'endpoint n'existe pas (backend antérieur à
    // Phase A.7.2 v5), Flask renvoie une 404 HTML, `r.json()` jetterait
    // un SyntaxError peu parlant. On détecte le content-type et on
    // donne un message d'erreur utile (« redémarre le backend »).
    const ct = r.headers.get("content-type") || "";
    if (!ct.includes("application/json")) {
      appendTurn("system",
        `Mode guidé : endpoint /api/guided/init absent (HTTP ${r.status}). ` +
        `Redémarre le backend Compagnon, l'app.py qui tourne est antérieur ` +
        `à Phase A.7.2 v5. Repli en mode lecture libre.`);
      return;
    }
    const data = await r.json();
    if (!r.ok) {
      // Phase v15.7.35 : si le backend signale guided_fallback_required,
      // on ouvre une modal qui propose : Parcourir / IA scan / Repli colle.
      if (data.guided_fallback_required) {
        openGuidedFallbackModal(data, startIndex);
        return;
      }
      appendTurn("system",
        `Mode guidé indisponible : ${data.error || r.status}. Repli en mode lecture libre.`);
      return;
    }
    guidedSlides = data.slides || [];
    guidedTitleGlobal = data.titre_global || "";
    if (!guidedSlides.length) {
      appendTurn("system", "Mode guidé : aucune slide trouvée.");
      return;
    }
    // Incohérence SCRIPT.md ↔ slides_*.pdf détectée côté backend ?
    // Affiche un banner avec la commande de régen, conformément à la
    // règle: SCRIPT.md = source de vérité, slides_*.pdf doit en découler
    // via run_script_oral.py.
    if (data.inconsistency) {
      renderInconsistencyBanner(data.inconsistency);
    }
    // Phase v15.7.36 : mode guidé « lite » (script .txt sans headers
    // SLIDE N). Le tuteur a quand même reçu le texte complet via
    // SCRIPT ORAL PERSO ; les slides sont synthétiques (1 par page PDF).
    // Affiche un message système discret avec le pourquoi + bouton CC.
    if (data.lite) {
      renderGuidedLiteNotice(data.lite_reason || "Mode lite actif.");
    }
    guidedPanel.hidden = false;
    // startIndex permet de restaurer la slide au F5 (auto-restore via
    // /api/current_session). 0 par défaut au démarrage normal.
    const safeStart = Math.min(Math.max(0, startIndex), guidedSlides.length - 1);
    guidedIndex = safeStart;
    showGuidedSlide(safeStart, /*announceToClaude=*/false);
    // 1ʳᵉ slide : on l'annonce dans le dialogue (le tuteur a déjà reçu le
    // contexte initial via le prompt, il décide s'il enchaîne ou attend).
  } catch (e) {
    appendTurn("system", "Mode guidé : erreur réseau (" + e.message + ").");
  }
}

function showGuidedSlide(i, announceToClaude, source = "user") {
  if (i < 0 || i >= guidedSlides.length) return;
  guidedIndex = i;
  // Persiste l'index dans la session JSON pour permettre la restauration
  // après Ctrl+F5. Fire-and-forget, pas critique si le call échoue.
  if (activeSession) {
    fetch("/api/state/guided_index", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index: i }),
    }).catch(() => {});
  }
  const slide = guidedSlides[i];
  guidedCounter.textContent = `${i + 1} / ${guidedSlides.length}`;
  guidedTitle.textContent = slide.title || `(slide ${slide.n})`;
  guidedDuration.textContent = slide.duration_min
    ? `Durée cible : ${slide.duration_min} min`
    : "";
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
  // Marker de transition slide : visible dans la conv (style .turn.marker
  // + .marker-user ou .marker-tutor selon source) et injecté comme bulle
  // student dans le transcript pour que le tuteur ait aussi le contexte.
  // source : "user" (clic flèche/jump manuel) ou "tuteur" (NEXT_SLIDE/
  // GOTO_SLIDE émis par claude). Le format diffère pour que le tuteur
  // sache qui a déclenché la transition.
  const verb = source === "tuteur"
    ? "Le tuteur a fait avancer à"
    : "L'étudiant est passé à";
  const instr =
    `[Mode guidé] ${verb} la slide ${slide.n}/${guidedSlides.length}` +
    (slide.title ? ` : « ${slide.title} »` : "") + ".";
  const t = appendTurn("student", "", { rawText: instr });
  t.innerHTML = renderMarkdown(instr);
  if (t.parentElement) t.parentElement.dataset.rawText = instr;
  // Active le flag : pendant TOUT le stream de la réponse à ce meta,
  // les NEXT_SLIDE/GOTO_SLIDE éventuels du tuteur seront ignorés
  // (cf. slideTransitionLocked). Reset par le handler done/end de
  // streamResponse.
  respondingToSlideMeta = true;
  fetch("/api/send_message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: instr }),
  }).then(r => {
    if (r.ok || r.status === 202) streamResponse();
    else respondingToSlideMeta = false;
  }).catch(e => {
    console.warn("guidé meta send a échoué :", e);
    respondingToSlideMeta = false;
  });
}

function gotoNextSlide(source = "user") {
  if (activeMode !== "guidé" || !guidedSlides.length) return;
  if (guidedIndex < guidedSlides.length - 1) {
    showGuidedSlide(guidedIndex + 1, /*announceToClaude=*/true, source);
  }
}
function gotoPrevSlide(source = "user") {
  if (activeMode !== "guidé" || !guidedSlides.length) return;
  if (guidedIndex > 0) {
    showGuidedSlide(guidedIndex - 1, /*announceToClaude=*/true, source);
  }
}
function jumpToSlide() {
  if (activeMode !== "guidé" || !guidedSlides.length) return;
  const ans = window.prompt(
    `Aller à la slide n° (1 - ${guidedSlides.length}) :`,
    String(guidedIndex + 1));
  if (!ans) return;
  const n = parseInt(ans, 10);
  if (Number.isFinite(n) && n >= 1 && n <= guidedSlides.length) {
    showGuidedSlide(n - 1, /*announceToClaude=*/true, "user");
  }
}

if (guidedNext) guidedNext.addEventListener("click", gotoNextSlide);
if (guidedPrev) guidedPrev.addEventListener("click", gotoPrevSlide);
if (guidedJump) guidedJump.addEventListener("click", jumpToSlide);

// Lightbox : clic sur la slide → ouvre l'image en plein écran (Phase A.7.2 v6.4).
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

// Délégation d'event sur les images du dialogue : click → lightbox,
// click sur le 🗑 → retire la pièce jointe du message (uniquement sur
// les bulles student, celles du tuteur ne sont pas censées être éditées
// pour ce cas, le bouton n'apparaît pas via CSS).
dialogue.addEventListener("click", (e) => {
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
  // Décode le data-md (qui était HTML-escapé dans le rendu)
  const decodedMd = mdLine
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&");
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
      headers: { "Content-Type": "application/json" },
      // silent=true → pas de note système « édité » ni de flag (modifié) :
      // c'est juste un nettoyage de pièce jointe, pas une vraie modif de contenu.
      body: JSON.stringify({ text: newText, silent: true }),
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
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && lightbox && !lightbox.hidden) {
    e.preventDefault();
    closeLightbox();
  }
});

function renderInconsistencyBanner(inc) {
  // Banner persistant dans le dialogue qui annonce la divergence
  // SCRIPT/PDF + bouton « Copier la commande de régen ». La règle est
  // claire (CLAUDE.md §3 + ARCHITECTURE.md §11) : SCRIPT.md = source
  // de vérité, le PDF doit être recompilé. On ne lance pas la commande
  // depuis le browser (besoin de MiKTeX, dossiers, droits), on aide
  // l'utilisateur à la copier-coller dans son terminal.
  const card = document.createElement("div");
  card.className = "turn inconsistency-card";

  const role = document.createElement("div");
  role.className = "role";
  role.textContent = "⚠️ Incohérence SCRIPT ↔ slides PDF";
  card.appendChild(role);

  const msg = document.createElement("div");
  msg.className = "inc-message";
  msg.textContent = inc.message ||
    `SCRIPT (${inc.nb_slides_script} slides) ≠ PDF (${inc.nb_pages_pdf} pages).`;
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
      setTimeout(() => { copyBtn.textContent = "📋 Copier la commande"; }, 2000);
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

// ============================================================ End session (Phase v15.7.31 : débrief)
// Comportement v0.6 (avant) : clic Terminer / <<<END_SESSION>>> →
// finishSession() qui POST /api/end_session et nuke tout.
// Comportement v0.7 (v15.7.31) : workflow en 2 temps :
//   1. clic Terminer → triggerSessionRecap() → POST /api/session_recap
//      → carte récap (résumé + concepts + suggestions) injectée dans le
//      fil, session reste ACTIVE en phase débrief.
//   2. user peut continuer à poser des Q&R, refaire des mini-exos, etc.
//      Pour vraiment fermer : bouton dédié dans la carte →
//      closeSessionFinal() → POST /api/session_close.
//
// inDebrief tracke localement la phase pour gérer le 2ᵉ clic Terminer
// (qui ne re-déclenche pas le récap, juste affiche un hint).
let inDebrief = false;

endBtn.addEventListener("click", () => {
  if (!activeSession) return;
  if (inDebrief) {
    // 2ᵉ clic en phase débrief : pointer vers le bouton « 🚪 Fermer
    // définitivement » de la carte récap. Pas de re-trigger récap.
    appendTurn("system",
      "Session déjà en phase débrief. Pour fermer définitivement, " +
      "utilisez le bouton « 🚪 Fermer définitivement » de la carte récap.");
    return;
  }
  triggerSessionRecap();
});

// Phase A.10.13b : Bouton 📄 Récap : exporte la session active en ZIP
// (PDF + MD) téléchargeable. Disponible à tout moment (pas seulement
// à la fin). User : « à la limite à la fin ça peut sortir un pdf
// récapitatif voire un bouton quelque part pour sortir un pdf
// recapitulatif de la section à chaque fois qu'on le veut ».
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
      // Extract filename depuis Content-Disposition si présent, sinon fallback
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
      // Re-enable seulement si session toujours active
      exportRecapBtn.disabled = !activeSession;
    }
  });
}

async function triggerSessionRecap() {
  if (!activeSession) return;
  if (isRecording) abortRecordingAndTranscribe();
  if (currentEventSource) { currentEventSource.close(); currentEventSource = null; }
  // Bulle d'attente, Gemini Flash met 3-8s sur transcript long
  const waitBubble = appendTurn("system",
    "🎓 Génération du récap de séance (audit Gemini Flash sur le transcript), patience 3-8 s…");
  try {
    const r = await fetch("/api/session_recap", { method: "POST" });
    const data = await r.json();
    if (waitBubble && waitBubble.parentElement) {
      waitBubble.parentElement.remove();
    }
    if (!r.ok) {
      appendTurn("system",
        "⚠ Récap échoué : " + (data.error || r.status) + ". Tu peux fermer la séance " +
        "via le bouton Terminer (qui fera un end_session brut).");
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
  // Phase A.8.4 : bouton ✕ de fermeture/suppression de la carte récap.
  // La carte étant localOnly (pas dans le transcript backend), elle est
  // simplement retirée du DOM au clic. Le user peut toujours accéder
  // au récap via l'archive .md (section dédiée).
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

  // Résumé
  if (recap.summary) {
    const sumDiv = document.createElement("div");
    sumDiv.className = "recap-summary";
    sumDiv.innerHTML = renderMarkdown(recap.summary);
    wrapper.appendChild(sumDiv);
  }

  // Concepts couverts, chaque concept est cliquable pour un mini-exo ciblé.
  const concepts = Array.isArray(recap.concepts_covered) ? recap.concepts_covered : [];
  if (concepts.length) {
    const div = document.createElement("div");
    div.className = "recap-section recap-concepts";
    div.innerHTML = "<h4>📚 Concepts couverts</h4>" +
      `<p class="recap-hint">Clique 🎯 sur un concept pour un mini-exo ciblé dessus.</p>`;
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

  // Exercices traités
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

  // Suggestions
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

  // Phase A.11.1 : Boutons d'avancement. Plutôt que de pousser à fermer
  // la séance, on propose des suites concrètes. Tout fonctionne en phase
  // débrief (la session reste active), cf. /api/recap_action.
  const nextSteps = document.createElement("div");
  nextSteps.className = "recap-section recap-next-steps";
  nextSteps.innerHTML = "<h4>🚀 Pour aller plus loin</h4>" +
    `<p class="recap-hint">La séance reste ouverte : choisis une suite, ` +
    `ou ferme définitivement quand tu as fini.</p>`;
  const nsRow = document.createElement("div");
  nsRow.className = "recap-next-steps-row";
  const NEXT_STEP_BTNS = [
    ["bloc_lecon", "📄 Bloc complet de la leçon",
     "Le tuteur compile toutes les fiches/leçons de la séance en un seul bloc."],
    ["bloc_exos", "📄 Bloc complet des exos",
     "Le tuteur regroupe tous les exos traités + leur correction rédigée."],
    ["serie_exos", "📝 Série d'exos d'entraînement",
     "Le tuteur génère de nouveaux exos (énoncés seuls) sur les concepts du jour."],
  ];
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
  colleBtn.title = "Pré-arme une nouvelle séance en mode colle " +
    "(auto-interrogation) sur la même matière.";
  colleBtn.addEventListener("click", switchToColleMode);
  nsRow.appendChild(colleBtn);
  nextSteps.appendChild(nsRow);
  wrapper.appendChild(nextSteps);

  // Actions
  const actions = document.createElement("div");
  actions.className = "recap-actions";

  const continueBtn = document.createElement("button");
  continueBtn.type = "button";
  continueBtn.className = "recap-action-btn recap-continue-btn";
  continueBtn.innerHTML = "💬 Continuer en débrief";
  continueBtn.title = "Pose des questions libres au tuteur en posture détaillée. " +
    "La séance reste ouverte.";
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
  closeBtn.title = "Finalise la session (ended_at, duration_seconds). " +
    "Plus possible de continuer après.";
  closeBtn.addEventListener("click", closeSessionFinal);
  actions.appendChild(closeBtn);

  wrapper.appendChild(actions);

  if (dialogue.querySelector(".placeholder")) dialogue.innerHTML = "";
  dialogue.appendChild(wrapper);
  dialogue.scrollTop = dialogue.scrollHeight;
}

async function triggerMiniExo(concept) {
  if (!activeSession) return;
  if (currentEventSource) { currentEventSource.close(); currentEventSource = null; }
  try {
    const r = await fetch("/api/mini_exo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ concept: concept }),
    });
    if (!r.ok) {
      const data = await r.json().catch(() => ({}));
      alert("Mini-exo échoué : " + (data.error || r.status));
      return;
    }
    // Note visuelle pour situer le mini-exo
    appendTurn("system", `🎯 Mini-exo demandé : ${concept}`);
    // Stream la réponse du tuteur. /api/mini_exo a set retry_pending=True,
    // donc /api/stream_response démarre sans pending_user_text à fournir.
    streamResponse();
  } catch (e) {
    alert("Erreur réseau mini-exo : " + e.message);
  }
}

// Phase A.11.1 : Boutons d'avancement de la carte récap. Même mécanique
// que triggerMiniExo : POST qui injecte une requête dans l'historique du
// tuteur + arme retry_pending, puis on streame la réponse. La séance reste
// ouverte (phase débrief).
async function triggerRecapAction(kind) {
  if (!activeSession) {
    appendTurn("system",
      "⚠ Séance déjà fermée : relance une séance pour continuer.");
    return;
  }
  if (currentEventSource) { currentEventSource.close(); currentEventSource = null; }
  const labels = {
    bloc_lecon: "📄 Bloc complet de la leçon",
    bloc_exos: "📄 Bloc complet des exos",
    serie_exos: "📝 Série d'exos d'entraînement",
  };
  try {
    const r = await fetch("/api/recap_action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: kind }),
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

// Phase A.11.1 : Pré-arme le formulaire pour relancer une séance en mode
// colle sur la même matière (progression Découverte → Guidé → Colle).
function switchToColleMode() {
  const modeEl = startForm && startForm.querySelector('[name="mode"]');
  if (modeEl) {
    modeEl.value = "colle";
    modeEl.dispatchEvent(new Event("change", { bubbles: true }));
  }
  appendTurn("system",
    "🎯 Mode colle pré-sélectionné dans le formulaire. Ferme cette séance " +
    "(🚪) si besoin, puis clique « Démarrer » pour t'auto-interroger sur la " +
    "même matière, sans guidage.");
  const startBtn = startForm && startForm.querySelector('button[type="submit"]');
  if (startBtn) startBtn.scrollIntoView({ behavior: "smooth", block: "center" });
}

// Phase A.11.1 : Après fermeture définitive, on ne laisse pas un écran
// mort : une carte propose de rebondir (mode colle, nouvelle séance).
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
  hint.textContent = "La séance est archivée. Choisis une suite pour " +
    "continuer à progresser :";
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
    if (startBtn) startBtn.scrollIntoView({ behavior: "smooth", block: "center" });
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
  if (currentEventSource) { currentEventSource.close(); currentEventSource = null; }
  try {
    const r = await fetch("/api/session_close", { method: "POST" });
    const data = await r.json();
    if (r.ok) {
      appendTurn("system",
        `🚪 Séance archivée. Durée totale : ${data.duration_seconds}s.`);
    }
  } catch (e) { /* silencieux */ }
  _cleanupAfterSessionClose();
  // Phase A.11.1 : pas d'écran mort après fermeture : on propose la suite.
  renderPostCloseCard();
}

// Fallback : ancien chemin /api/end_session pour fermeture brutale sans
// récap (cas d'erreur ou stop de secours). Pas utilisé en flow normal.
async function finishSession(autoFromEnd = true) {
  if (!activeSession) return;
  // Phase v15.7.31 : par défaut, déclenche le récap au lieu de fermer brutalement.
  // Garde le chemin direct uniquement si appelé avec `autoFromEnd === "force_close"`
  // (cas d'erreur où on n'a pas envie d'attendre Gemini).
  if (autoFromEnd !== "force_close" && !inDebrief) {
    return triggerSessionRecap();
  }
  if (isRecording) abortRecordingAndTranscribe();
  if (currentEventSource) { currentEventSource.close(); currentEventSource = null; }
  try {
    const r = await fetch("/api/end_session", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({interrupted: false}),
    });
    const data = await r.json();
    if (r.ok) {
      appendTurn("system",
        `Séance terminée. Durée: ${data.duration_seconds}s.`);
    }
  } catch (e) { /* silencieux */ }
  _cleanupAfterSessionClose();
}

function _cleanupAfterSessionClose() {
  activeSession = null;
  activeMode = null;
  inDebrief = false;
  // Phase v15.7.30.1 : reset format colle / ancrage au défaut.
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
  if (findExoBtn) { findExoBtn.disabled = true; findExoBtn.hidden = true; }
  closeRewritePopover();
  // Phase A.9 (correctif) : pas de unlock à faire ici : le form n'a
  // jamais été lockée. Restauration explicite seulement du bouton
  // submit (re-enable au cas où un code parallèle l'aurait désactivé).
  const submitBtn = startForm.querySelector('button[type="submit"]');
  if (submitBtn) submitBtn.disabled = false;
  sessionInfo.textContent = "";
}

// ============================================================ Push-to-talk indicator (visuel uniquement)
// Le hook ESPACE est côté Python (listener.py), ici on visualise juste si le
// backend nous indique le passage en mode recording. Phase A : pas de canal
// dédié, donc on laisse statique. À brancher en Phase B si besoin.

document.addEventListener("keydown", (e) => {
  // Skip si focus dans un champ de saisie (textarea, input, contenteditable,
  // select). On laisse le comportement natif (navigation curseur, etc.).
  const ae = document.activeElement;
  if (ae) {
    const tag = (ae.tagName || "").toUpperCase();
    if (tag === "TEXTAREA" || tag === "INPUT" || tag === "SELECT" || ae.isContentEditable) {
      return;
    }
  }
  // En mode guidé : Espace / → / ← naviguent entre slides, sauf si l'onglet
  // « Corrigés & script » est actif, auquel cas la nav corrigé prend la main
  // (cohérence visuelle : la flèche actionne ce qui est sous les yeux).
  if (activeMode === "guidé" && guidedSlides.length) {
    const corrigeActiveAndLoaded =
      typeof corrigeTabIsActive === "function"
      && corrigeTabIsActive() && correctionsList.length;
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
  // Hors mode guidé (ou guidé + tab corrigé actif) : ←/→ navigue dans le
  // panneau Corrigé quand il est ouvert et a des documents.
  if (
    typeof corrigeTabIsActive === "function"
    && corrigeTabIsActive() && correctionsList.length
  ) {
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
document.addEventListener("keyup", (e) => {
  if (e.code === "Space") {
    recordIndicator.classList.remove("active");
  }
});

// ============================================================ TTS Player (Phase A.7.2 v14)
// Mini-player audio attaché à chaque bulle Compagnon. Click 🔊 → fetch
// /api/tts/synthesize → audio HTML5 dont la durée + scrubbing + speed
// sont nativement gérés par le navigateur. Voix par défaut Denise (FR),
// changeable via le sélecteur. Mémorise vitesse/voix dans localStorage.

const TTS_VOICES = [
  { id: "fr-FR-DeniseNeural",   label: "Denise" },
  { id: "fr-FR-HenriNeural",    label: "Henri" },
  { id: "fr-FR-AlainNeural",    label: "Alain" },
  { id: "fr-FR-BrigitteNeural", label: "Brigitte" },
];
const TTS_SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];

function getTTSPref(key, fallback) {
  try { return localStorage.getItem("tts_" + key) || fallback; }
  catch (_) { return fallback; }
}
function setTTSPref(key, value) {
  try { localStorage.setItem("tts_" + key, String(value)); } catch (_) {}
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
    // Si déjà ouvert : toggle play/pause si même bulle
    const audio = existing.querySelector("audio");
    if (audio) {
      if (audio.paused) audio.play(); else audio.pause();
    }
    return;
  }
  const rawText = turnEl.dataset.rawText || "";
  if (!rawText.trim()) {
    alert("Rien à lire dans cette bulle.");
    return;
  }
  // Strip markdown / KaTeX delimiters pour la voix (gros effet UX,
  // sinon le TTS prononce « dollar f de x dollar » au lieu de la formule).
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
  playBtn.type = "button"; playBtn.className = "tts-play";
  playBtn.title = "Play / Pause"; playBtn.textContent = "▶";
  const timeline = document.createElement("input");
  timeline.type = "range"; timeline.className = "tts-timeline";
  timeline.min = "0"; timeline.max = "100"; timeline.value = "0"; timeline.step = "0.1";
  timeline.disabled = true;
  const timeLabel = document.createElement("span");
  timeLabel.className = "tts-time"; timeLabel.textContent = "0:00 / —";
  const speedSel = document.createElement("select");
  speedSel.className = "tts-speed"; speedSel.title = "Vitesse";
  for (const sp of TTS_SPEEDS) {
    const opt = document.createElement("option");
    opt.value = String(sp); opt.textContent = `${sp}×`;
    speedSel.appendChild(opt);
  }
  speedSel.value = getTTSPref("speed", "1");
  audio.playbackRate = parseFloat(speedSel.value) || 1;
  const voiceSel = document.createElement("select");
  voiceSel.className = "tts-voice"; voiceSel.title = "Voix";
  for (const v of TTS_VOICES) {
    const opt = document.createElement("option");
    opt.value = v.id; opt.textContent = v.label;
    voiceSel.appendChild(opt);
  }
  voiceSel.value = getTTSPref("voice", "fr-FR-DeniseNeural");
  const closeBtn = document.createElement("button");
  closeBtn.type = "button"; closeBtn.className = "tts-close";
  closeBtn.title = "Fermer le lecteur"; closeBtn.textContent = "✕";
  closeBtn.addEventListener("click", () => {
    audio.pause(); audio.src = ""; wrap.remove();
  });
  const status = document.createElement("span");
  status.className = "tts-status"; status.textContent = "⏳ Synthèse…";

  wrap.appendChild(playBtn);
  wrap.appendChild(timeline);
  wrap.appendChild(timeLabel);
  wrap.appendChild(speedSel);
  wrap.appendChild(voiceSel);
  wrap.appendChild(status);
  wrap.appendChild(closeBtn);
  wrap.appendChild(audio);

  // Wiring contrôles
  playBtn.addEventListener("click", () => {
    if (audio.paused) audio.play(); else audio.pause();
  });
  audio.addEventListener("play",  () => { playBtn.textContent = "⏸"; });
  audio.addEventListener("pause", () => { playBtn.textContent = "▶"; });
  audio.addEventListener("ended", () => { playBtn.textContent = "▶"; timeline.value = "0"; });
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

  // Fetch initial TTS + auto-play dès qu'il est prêt (single-click UX)
  fetchTTSInto(audio, text, voiceSel.value, status, wrap, /*autoplay=*/true);
  return wrap;
}

async function fetchTTSInto(audio, text, voice, statusEl, wrap, autoplay = false) {
  try {
    const r = await fetch("/api/tts/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice }),
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
      // Le click utilisateur sur 🔊 a propagé l'autorisation d'autoplay
      // au browser, donc audio.play() devrait passer sans warning.
      audio.play().catch((err) => {
        console.warn("autoplay refusé :", err);
      });
    }
  } catch (e) {
    statusEl.textContent = "✗ Réseau : " + e.message;
  }
}

// ============================================================ Sélecteur de moteur (Phase A.7.2 v9)
// Bouton dans le header pour basculer le moteur à chaud (CLI / API / Gemini /
// DeepSeek / Groq selon clés présentes). POST /api/switch_engine ; persisté
// dans _secrets/engine_pref.json donc cohérent avec la GUI Tkinter.

const engineSwitcher = $("#engine-switcher");

const ENGINE_LABELS = {
  cli_subscription: "CLI Claude (subscription)",
  anthropic_api: "API Anthropic",
  gemini_api: "Gemini",
  deepseek_api: "DeepSeek",
  groq_api: "Groq",
};

async function refreshEngineSwitcher() {
  if (!engineSwitcher) return;
  try {
    const r = await fetch("/api/engine");
    if (!r.ok) return;
    const data = await r.json();
    const current = data.current;
    const available = Array.isArray(data.available) ? data.available : [];
    // Construit les options : current + available (dédup), labels lisibles
    const seen = new Set();
    const items = [];
    if (current) {
      items.push({ engine: current, label: ENGINE_LABELS[current] || current });
      seen.add(current);
    }
    for (const a of available) {
      if (seen.has(a.engine)) continue;
      items.push({ engine: a.engine, label: a.label || ENGINE_LABELS[a.engine] || a.engine });
      seen.add(a.engine);
    }
    engineSwitcher.innerHTML = items.map(it =>
      `<option value="${it.engine}"${it.engine === current ? " selected" : ""}>${it.label}</option>`
    ).join("");
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
      // Si pas de session active : juste persiste la pref (engine_pref.json)
      // via /api/switch_engine_pref. Si session active : bascule à chaud.
      const path = activeSession ? "/api/switch_engine" : "/api/switch_engine_pref";
      const r = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ engine: target }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        alert("Bascule moteur échouée : " + (data.error || r.status));
        // Revert le select à l'engine courant côté backend
        await refreshEngineSwitcher();
      } else {
        // Met à jour le sessionInfo si présent
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
// Refresh aussi après chaque start de session (le backend peut avoir changé de pref)
const _origRefreshAfterStart = refreshEngineSwitcher;
// noop: déjà appelé au boot ; le refresh au start est implicite dans le radio

// ============================================================ Panneau Historique (Phase A.7.2 v9)
// Liste les sessions persistées dans _sessions/, click pour reprise (replay
// si récente, résumé sinon), hover → 🗑 supprimer / ✏️ renommer inline.

const historyList = $("#history-list");
const historyRefresh = $("#history-refresh");

function fmtSessionLabel(s) {
  if (s.label) return s.label;
  // Fallback: "MAT TYPN exX" + date
  const exo = s.exo && s.exo !== "full" ? `ex${s.exo}` : "exfull";
  const annee = s.annee ? ` ${s.annee}` : "";
  return `${s.matiere || "?"} ${s.type || "?"}${s.num || "?"} ${exo}${annee}`;
}

function fmtSessionDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString("fr-FR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch (_) { return iso.slice(0, 16); }
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
      // Phase A.8.6 : affiche aussi format colle + ancrage corrigé pour
      // distinguer visuellement les variations d'un même exo. Les anciens
      // fichiers sans ces champs continuent d'afficher uniquement le mode.
      const chips = [mode];
      if (s.colle_format) chips.push(s.colle_format);
      if (s.corrige_anchor) chips.push(s.corrige_anchor);
      const meta = [
        fmtSessionDate(s.last_alive || s.started_at),
        `${s.n_exchanges || 0} tour${(s.n_exchanges || 0) > 1 ? "s" : ""}`,
        chips.join(" · "),
      ].filter(Boolean).join(" · ");
      item.innerHTML = `
        <div class="h-title">${escapeHtml(fmtSessionLabel(s))}</div>
        <div class="h-meta">${meta} ${flagInterrupted}</div>
        <div class="h-actions">
          <button class="h-action-btn h-rename" type="button" title="Renommer">✏️</button>
          <button class="h-action-btn h-del" type="button" title="Supprimer">🗑️</button>
        </div>
      `;
      // Click sur le titre / meta → reprise
      item.addEventListener("click", (e) => {
        if (e.target.closest(".h-actions")) return;
        if (item.querySelector(".h-rename-input")) return;  // en cours de rename
        resumeSession(s.session_id);
      });
      // Rename
      item.querySelector(".h-rename").addEventListener("click", (e) => {
        e.stopPropagation();
        startRenameSession(item, s);
      });
      // Delete
      item.querySelector(".h-del").addEventListener("click", async (e) => {
        e.stopPropagation();
        if (s.session_id === activeSession) {
          alert("Impossible de supprimer la session active. Termine-la d'abord.");
          return;
        }
        if (!confirm(`Supprimer la session « ${fmtSessionLabel(s)} » ?`)) return;
        const dr = await fetch(`/api/sessions/${encodeURIComponent(s.session_id)}`, {
          method: "DELETE",
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
  const commit = async (save) => {
    const newLabel = input.value.trim();
    if (!save) {
      refreshHistoryList();
      return;
    }
    const body = { label: newLabel || null };
    const r = await fetch(`/api/sessions/${encodeURIComponent(s.session_id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      alert("Renommage échoué : " + (err.error || r.status));
    }
    refreshHistoryList();
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); commit(true); }
    else if (e.key === "Escape") { e.preventDefault(); commit(false); }
  });
  input.addEventListener("blur", () => commit(true));
}

async function resumeSession(sid) {
  if (!sid) return;
  // Phase A.8.5 hotfix : pas de short-circuit si déjà active.
  // Avant : `if (sid === activeSession) return;` empêchait l'action quand
  // l'user clique « Reprendre la session existante » depuis le modal
  // conflict pour une session déjà chargée par restoreActiveSessionIfAny
  // au boot. Le clic ne déclenchait rien → impression que le bouton est
  // mort. Fix : on relance toujours le resume_session backend (qui va
  // re-régénérer l'archive .md A.8.5, re-rasterizer les docs, re-injecter
  // le contexte initial). Coût : ~1-3s. Bénéfice : action prévisible.
  // Indique au user que ça travaille (peut prendre 5-10s si génération résumé)
  if (sessionInfo) sessionInfo.textContent = `⏳ Reprise de ${sid}…`;
  try {
    const r = await fetch("/api/resume_session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sid }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      alert("Reprise échouée : " + (data.error || r.status));
      if (sessionInfo) sessionInfo.textContent = "";
      return;
    }
    activeSession = data.session_id;
    activeMode = data.mode || "colle";
    // Phase v15.7.4 : restaure les chips de format colle.
    applyColleFormatChips(data.colle_format || "mixte");
    // Phase v15.7.30 : restaure les chips d'ancrage corrigé.
    applyCorrigeAnchorChips(data.corrige_anchor || "strict");
    // Phase A.10.15 : sync les selects du form de démarrage au contexte
    // de la session reprise (cf. friction user 2026-05-15 : changer de
    // session via 💬 Historique laissait les selects pointant l'ancien
    // contexte).
    try { await syncFormToSession(data); } catch (_) { /* best-effort */ }
    sessionInfo.textContent =
      `→ ${data.session_id} (engine: ${data.engine}) ` +
      `[${data.summary_used ? "résumé" : "replay"}]`;
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
    // Phase A.9 (correctif) : pas de lock du form ici. Les selects de
    // SOURCE (matière/type/num/exo/année/mode) doivent rester actifs
    // pour permettre à l'user de préparer un futur Lancer (modal de
    // conflit). Seul `corrige_anchor` est inhibé via le no-op de
    // `setCorrigeAnchor` quand activeSession est set.
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

// ============================================================ Panneau Corrigés & script (sidebar tab)
// Disponible dans tous les modes. Affiche page-par-page les corrigés
// officiels + le script imprimable (rasterisés via /api/corrections/init).
// Picker pour switcher entre documents quand il y en a plusieurs.
//
// Tracking : juste-avant-stream (et non sur chaque nav). Le front maintient
// `currentReadingState` ; à chaque envoi de message, le body /api/send_message
// inclut ce state. Le backend prefixe une ligne `[Contexte lecture actuelle : ...]`
// au text. Aucun spam d'historique sur les navigations de page.

const correctionsList = [];
let corrigeIdx = 0;
let corrigePageIdx = 0;
let currentReadingState = null;  // {kind, label, filename, page, total} ou null
// Mémoire de la dernière page consultée par document, clé = filename (stable
// même si l'ordre change entre deux init). Évite le reset à page 1 quand
// l'utilisateur switche corrigé→script→corrigé via le picker.
const corrigePageMemory = new Map();
// Marker de position dans le dialogue (Phase A.7.2 v15.7).
// Quand l'étudiant tourne les pages du panneau Docs, on pose un marker
// cliquable dans le stream après une pause de navigation (debounce).
// Click sur le marker = retour à cette position. Sert de repère temporel
// "qu'est-ce que je regardais quand j'ai posé telle question".
let docMarkerTimeoutHandle = null;
let lastDocMarkerKey = null;        // "idx:pageIdx" du dernier marker posé
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
  // Reset l'état du marker de position : nouvelle session = nouveaux markers,
  // l'ancienne dédup ne tient plus.
  if (docMarkerTimeoutHandle) {
    clearTimeout(docMarkerTimeoutHandle);
    docMarkerTimeoutHandle = null;
  }
  lastDocMarkerKey = null;
  // Phase Z.9 : reset des mémoires de recherche
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
    showCorrige(0, 0, /*notify=*/false);
    // Phase Z.8.1 : re-linkify les refs page dans les bulles claude
    // déjà rendues. À la reprise via restoreActiveSessionIfAny ou
    // resumeSession, rerenderDialogueFromTranscript est appelée AVANT
    // que /api/corrections/init n'ait répondu, donc linkifyPageRefs()
    // bail (correctionsList vide) et les liens ne sont pas rendus.
    // On rattrape ici une fois la liste peuplée.
    document.querySelectorAll('#dialogue-stream .turn.claude').forEach(turn => {
      linkifyPageRefs(turn);
    });
  } catch (e) {
    setCorrigePlaceholder(`Erreur réseau : ${e.message}`);
  }
}

function setCorrigePlaceholder(txt) {
  if (corrigeImg) { corrigeImg.hidden = true; corrigeImg.src = ""; }
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
  // Phase v15.7.36.9 : si le label commence déjà par un descripteur
  // explicite (« Annale », « Aide-mémoire », « Exos », « Toutes les… »,
  // « Script »), skip le préfixe kindLbl pour éviter le doublon type
  // « Corrigé : Annale Q&A : CC2 ». Sinon, format historique
  // « Corrigé : Exercice 3 » conservé pour les cas canoniques (où le
  // label seul `Exercice 3` ne suffit pas à dire que c'est un corrigé).
  const _SELF_DESC_RE = /^(Annale|Aide-mémoire|Exos|Toutes|Script)\b/i;
  correctionsList.forEach((c, i) => {
    const opt = document.createElement("option");
    opt.value = String(i);
    const totalP = (c.pages || []).length;
    const kindLbl = _kindLabelFr(c.kind);
    const labelStr = String(c.label || "");
    const skipPrefix = _SELF_DESC_RE.test(labelStr);
    opt.textContent = skipPrefix
      ? `${labelStr} : ${totalP} page${totalP > 1 ? "s" : ""}`
      : `${kindLbl} : ${labelStr} : ${totalP} page${totalP > 1 ? "s" : ""}`;
    corrigePicker.appendChild(opt);
  });
  // Affiche le picker dès qu'on a plus d'un document (corrigé(s) + script).
  corrigePicker.hidden = correctionsList.length < 2;
}

function showCorrige(idx, pageIdx, notify = true) {
  if (!correctionsList.length) return;
  if (idx < 0 || idx >= correctionsList.length) return;
  // Mémorise la page courante du doc qu'on quitte (si on quitte vraiment).
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
  // Phase A.7.2 v15.7 : si pageIdx n'est pas spécifié explicitement
  // (null/undefined), restaure la dernière page consultée pour ce doc.
  // Permet au picker (et autres callers qui veulent juste « ouvrir le
  // doc X là où je l'avais laissé ») de NE PAS pré-resolver eux-mêmes.
  // Source unique de vérité pour la restauration de page = ce bloc.
  let resolvedPageIdx = pageIdx;
  if (resolvedPageIdx === null || resolvedPageIdx === undefined) {
    const memKey = item.filename || `idx:${idx}`;
    resolvedPageIdx = corrigePageMemory.has(memKey)
      ? corrigePageMemory.get(memKey)
      : 0;
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
    corrigePrev.disabled = (corrigeIdx === 0 && corrigePageIdx === 0);
  }
  if (corrigeNext) {
    const isLastItem = (corrigeIdx === correctionsList.length - 1);
    corrigeNext.disabled = isLastItem && (corrigePageIdx === pages.length - 1);
  }
  if (corrigeJump) corrigeJump.disabled = pages.length < 2;

  // Mémorise l'état lecture pour injection juste-avant-stream sur le
  // prochain user message. Pas de POST silencieux à chaque nav, on
  // annote le message envoyé naturellement.
  currentReadingState = {
    kind: item.kind || "document",
    label: item.label || "",
    filename: item.filename || "",
    page: corrigePageIdx + 1,
    total: pages.length,
  };
  // Phase A.7.2 v15.7 : marker de position dans le dialogue (debouncé).
  // Pose un repère cliquable après 1.5 s sans nouvelle nav pour permettre
  // de retrouver "qu'est-ce que je regardais à ce moment". Skip si
  // notify=false (init du panneau, click sur un marker passé, refs
  // cliquables qui font déjà mention dans le texte).
  if (notify) maybeAppendDocPositionMarker(idx, corrigePageIdx);
}

function maybeAppendDocPositionMarker(idx, pageIdx) {
  // Debounce : on attend DOC_MARKER_DEBOUNCE_MS sans nouvelle nav avant
  // de poser le marker. Sinon on flood le dialogue à chaque pression de
  // flèche pendant un parcours rapide. Cancel le timer en cours si on
  // re-navigue avant la pose.
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
  // Dédup : si le dernier marker pointe déjà sur la même position, on
  // skip. Évite les doublons quand le user revient en arrière à la même
  // page après une navigation aller-retour.
  if (key === lastDocMarkerKey) return;
  lastDocMarkerKey = key;
  const total = (item.pages || []).length;
  const kindLbl = _kindLabelFr(item.kind || "").toLowerCase();
  const safeLabel = (item.label || "").replace(
    /[<>&]/g, c => ({"<": "&lt;", ">": "&gt;", "&": "&amp;"}[c]),
  );
  const safeFile = (item.filename || "").replace(
    /[<>&]/g, c => ({"<": "&lt;", ">": "&gt;", "&": "&amp;"}[c]),
  );
  const marker = document.createElement("div");
  marker.className = "doc-marker";
  marker.dataset.docIdx = String(idx);
  marker.dataset.docPage = String(pageIdx);
  marker.title = `Cliquer pour ré-afficher cette page (${safeFile || kindLbl})`;
  marker.innerHTML =
    `<span class="doc-marker-icon">📄</span>` +
    `<span class="doc-marker-text">Page <strong>${pageIdx + 1}/${total}</strong> du ${kindLbl}` +
    (safeLabel ? ` <em>« ${safeLabel} »</em>` : ``) +
    `</span>` +
    `<span class="doc-marker-hint">↩ retour</span>`;
  marker.addEventListener("click", () => {
    // Active l'onglet Docs s'il ne l'est pas (l'utilisateur peut être
    // revenu à Quota/Historique entre-temps).
    const tab = document.querySelector('#sidebar-tabs .sb-tab[data-tab="corrige"]');
    if (tab && !tab.classList.contains("active")) tab.click();
    // notify=false : pas de re-pose de marker, c'est juste un retour.
    showCorrige(idx, pageIdx, /*notify=*/false);
  });
  dialogue.appendChild(marker);
  dialogue.scrollTop = dialogue.scrollHeight;
}

function getReadingStateForSend() {
  // Renvoie le state si l'onglet « Corrigés & script » est actif (donc
  // l'étudiant est probablement en train de lire), sinon null.
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
  const ans = window.prompt(
    `Aller à la page n° (1 - ${cur.pages.length}) :`,
    String(corrigePageIdx + 1));
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
    // pageIdx omis volontairement : showCorrige consulte corrigePageMemory
    // et restaure la dernière page lue de ce doc (Phase v15.7). Switcher
    // de l'énoncé au script ramène donc à la page 5 du script si c'est là
    // qu'on l'avait laissé, pas à la page 1.
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

// ============================================================ Phase v15.7.35 : Modal fallback mode guidé
// Affichée quand /api/guided/init renvoie guided_fallback_required.
// 3 options : Parcourir manuellement (file picker), Chercher avec IA
// (Gemini Flash scan persisté), Repli en mode colle.

let guidedFallbackState = {
  folderPath: "",         // Dossier de départ pour le picker
  startIndex: 0,          // Index slide à restaurer après init OK
  scriptPath: "",         // Fichier script choisi par l'user
  slidesPath: "",         // Fichier slides choisi par l'user
  pickerMode: "script",   // "script" ou "slides", quel fichier on attend
  cwd: "",                // Dossier courant du picker
};

function openGuidedFallbackModal(data, startIndex) {
  // Phase v15.7.36.1 : `missing_only` indique quel fichier doit être re-choisi
  // ("script" ou "slides"). L'autre fichier (`data.script_path` ou
  // `data.slides_path`) est pré-rempli dans le state pour que l'user n'ait à
  // parcourir QUE le manquant. Permet de ne pas reclasser un fichier déjà OK.
  const missingOnly = data.missing_only || "";  // "script" | "slides" | ""
  const initialScript = (missingOnly === "slides" && data.script_path) ? data.script_path : "";
  const initialSlides = (missingOnly === "script" && data.slides_path) ? data.slides_path : "";
  guidedFallbackState = {
    folderPath: data.folder_path || `${data.matiere}/${data.type_code}`,
    startIndex,
    scriptPath: initialScript,
    slidesPath: initialSlides,
    pickerMode: missingOnly === "slides" ? "slides" : "script",
    cwd: data.folder_path || `${data.matiere}/${data.type_code}`,
    missingOnly,
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
    gfbRunAiScan(/*force=*/false);
  });
  document.getElementById("gfb-colle").addEventListener("click", () => {
    closeGuidedFallbackModal();
    appendTurn("system",
      "Mode guidé désactivé : repli en mode colle libre. " +
      "Tu peux poser tes questions au tuteur normalement.");
  });
  document.getElementById("gfb-cancel").addEventListener("click", closeGuidedFallbackModal);
  document.getElementById("gfb-launch").addEventListener("click", gfbLaunchGuided);

  // Phase v15.7.36.4 : auto-lance le scan IA dès l'ouverture de la
  // modal. Le matching direct par thème (passé via `num` de session)
  // est quasi-instantané et déterministe. Si match → affichage
  // simplifié « ✅ Trouvé » + ▶ Lancer en 1 clic. Si pas de match,
  // Gemini Flash prend ~3s, affichage avec partial actions.
  // L'user peut toujours cliquer 🔍 Parcourir manuellement pour
  // bypass complètement.
  document.getElementById("gfb-ai-result").hidden = false;
  gfbRunAiScan(/*force=*/false);
}

function closeGuidedFallbackModal() {
  const m = document.getElementById("guided-fallback-modal");
  if (m) m.remove();
}

function escapeHtmlSafe(s) {
  return String(s || "").replace(/[<>&"]/g,
    c => ({"<":"&lt;",">":"&gt;","&":"&amp;",'"':"&quot;"}[c]));
}

async function gfbLoadFolder(pathRel) {
  const listEl = document.getElementById("gfb-picker-list");
  const cwdEl = document.getElementById("gfb-picker-cwd");
  const targetEl = document.getElementById("gfb-picker-target");
  if (!listEl || !cwdEl || !targetEl) return;

  targetEl.textContent = guidedFallbackState.pickerMode === "script"
    ? "🎯 Choisis le SCRIPT (texte oral) :"
    : "🎯 Choisis les SLIDES (PDF visuel) :";
  listEl.innerHTML = "<div class='gfb-loading'>Chargement…</div>";

  try {
    const r = await fetch("/api/browse_folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: pathRel }),
    });
    const data = await r.json();
    if (!r.ok) {
      listEl.innerHTML = `<div class='gfb-error'>Erreur : ${escapeHtmlSafe(data.error || "")}</div>`;
      return;
    }
    guidedFallbackState.cwd = data.cwd || "";
    cwdEl.textContent = `📁 ${data.cwd || "<racine COURS>"}`;
    listEl.innerHTML = "";

    // Bouton « remonter » si on n'est pas à la racine
    if (data.parent_path !== null && data.parent_path !== undefined) {
      const upBtn = document.createElement("button");
      upBtn.type = "button";
      upBtn.className = "gfb-entry gfb-entry-up";
      upBtn.innerHTML = "⬆ .. (remonter)";
      upBtn.addEventListener("click", () => gfbLoadFolder(data.parent_path));
      listEl.appendChild(upBtn);
    }

    for (const entry of (data.entries || [])) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "gfb-entry " + (entry.is_dir ? "gfb-entry-dir" : "gfb-entry-file");
      const icon = entry.is_dir ? "📁"
        : (entry.kind === "slides_pdf" ? "🖼"
          : entry.kind === "script_md" || entry.kind === "script_txt" ? "📝"
          : entry.kind === "script_imprimable" ? "🖨"
          : entry.kind === "annale" ? "📑"
          : entry.kind === "aide_memoire" ? "📋"
          : entry.suffix === ".pdf" ? "📄"
          : "📄");
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
  // Si on a maintenant les 2 → enable Lancer ; sinon, continue le picker
  if (!guidedFallbackState.scriptPath || !guidedFallbackState.slidesPath) {
    gfbLoadFolder(guidedFallbackState.cwd);
  }
}

function gfbRenderSelections() {
  const sel = document.getElementById("gfb-selections");
  if (!sel) return;
  const s = guidedFallbackState;
  // Phase v15.7.35.1 : chaque sélection a 2 actions :
  //   ✎ Modifier : force le pickerMode sur ce slot ET recharge le picker
  //                dans le dossier du fichier actuel (pour parcourir un
  //                remplaçant à côté). Cible : un seul fichier mal proposé
  //                par l'IA sans avoir à reclasser l'autre.
  //   ✕ Clear   : vide le path, force le pickerMode sur ce slot. Le
  //                picker se recharge dans le dossier de départ.
  // Mise en évidence visuelle du slot ACTUELLEMENT cible via classe
  // `gfb-sel-active` (l'user voit où va atterrir son prochain clic).
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
      // « Modifier » : bascule le picker sur ce slot et recharge
      // dans le dossier du fichier actuel (pour parcourir un voisin).
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
  // Phase v15.7.36.4 : passe le `num` de session comme `theme` au
  // backend pour activer le matching direct par suffix (plus fiable
  // que Gemini Flash sur le matching de thème).
  let themeHint = "";
  try {
    const r0 = await fetch("/api/current_session");
    if (r0.ok) {
      const d0 = await r0.json();
      if (d0 && d0.active && d0.num && d0.num !== "full") {
        themeHint = d0.num;
      }
    }
  } catch (_) { /* fail-soft */ }

  resultEl.innerHTML = themeHint
    ? `<div class='gfb-loading'>🎯 Recherche directe par thème <code>${escapeHtmlSafe(themeHint)}</code>…</div>`
    : "<div class='gfb-loading'>🤖 Gemini Flash scanne le dossier… (~3-5 s)</div>";
  try {
    const r = await fetch("/api/scan_with_ai", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        folder_path: guidedFallbackState.folderPath,
        force_refresh: !!force,
        theme: themeHint,
      }),
    });
    const data = await r.json();
    if (!r.ok) {
      resultEl.innerHTML = `<div class='gfb-error'>Erreur : ${escapeHtmlSafe(data.error || "")}</div>`;
      return;
    }
    // Phase v15.7.36.4 : UX simplifiée selon la méthode :
    //   - `direct_suffix_match` : panneau minimal « ✅ Trouvé par thème »
    //     avec 1 bouton ▶ et lien discret « modifier ».
    //   - Gemini : panneau complet avec confiance + reasoning + actions
    //     partial (garder 1 sur 2).
    const isDirect = data.method === "direct_suffix_match";
    const cachedTag = data.cached ? " <span class='gfb-cached'>(cache)</span>" : "";
    const confColor = data.confidence_0_100 >= 70 ? "high"
      : data.confidence_0_100 >= 40 ? "med" : "low";
    const headerLabel = isDirect ? "✅ Trouvé directement par thème" : "🤖 Suggestion IA";
    const headerExtra = isDirect ? "" :
      `<span class="gfb-conf gfb-conf-${confColor}">Confiance : ${data.confidence_0_100}/100</span>`;

    let actionsHtml = `
      <div class="gfb-ai-actions">
        <button type="button" class="gfb-ai-accept" id="gfb-ai-accept"
          ${(data.script_oral_path && data.slides_pdf_path) ? "" : "disabled"}>
          ▶ Lancer avec ces fichiers
        </button>
        <button type="button" class="gfb-ai-modify" id="gfb-ai-modify">
          ✎ Modifier (parcourir manuellement)
        </button>
      </div>
    `;
    // En cas de match direct fiable : pas de boutons partial, l'user
    // peut juste lancer ou modifier. Évite la surcharge cognitive.
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
    // Phase v15.7.36.4 : UX simplifiée : ▶ Lancer direct depuis le
    // panneau IA, sans passer par le picker intermédiaire. Le user
    // valide en 1 clic si l'IA a trouvé juste.
    const acceptBtn = document.getElementById("gfb-ai-accept");
    if (acceptBtn) acceptBtn.addEventListener("click", () => {
      guidedFallbackState.scriptPath = data.script_oral_path || "";
      guidedFallbackState.slidesPath = data.slides_pdf_path || "";
      if (!guidedFallbackState.scriptPath || !guidedFallbackState.slidesPath) {
        alert("Manque script ou slides, clique ✎ Modifier pour parcourir.");
        return;
      }
      // Lance direct, ferme la modal.
      gfbLaunchGuided();
    });
    const modifyBtn = document.getElementById("gfb-ai-modify");
    if (modifyBtn) modifyBtn.addEventListener("click", () => {
      // Modifier = pré-remplit les choix IA mais ouvre le picker pour
      // que l'user puisse cliquer ✎ Modifier sur le slot à corriger.
      guidedFallbackState.scriptPath = data.script_oral_path || "";
      guidedFallbackState.slidesPath = data.slides_pdf_path || "";
      guidedFallbackState.pickerMode = "slides";
      resultEl.hidden = true;
      document.getElementById("gfb-picker").hidden = false;
      gfbRenderSelections();
      gfbLoadFolder(_seedFolderFrom(guidedFallbackState.scriptPath
        || guidedFallbackState.slidesPath));
    });
    const refreshBtn = document.getElementById("gfb-ai-refresh");
    if (refreshBtn) refreshBtn.addEventListener("click", () => gfbRunAiScan(true));
    // Phase v15.7.36.1 : garder slides IA + parcourir uniquement script
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
    // ... garder script IA + parcourir uniquement slides
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
  appendTurn("system",
    `🎯 Mode guidé : lancement avec script <code>${escapeHtmlSafe(s.scriptPath)}</code> ` +
    `et slides <code>${escapeHtmlSafe(s.slidesPath)}</code>.`);
  // Relance initGuidedPanel avec overrides
  initGuidedPanel(s.startIndex, {
    script_path: s.scriptPath,
    slides_path: s.slidesPath,
  });
}

// ============================================================ Phase v15.7.36 : Mode guidé lite + prompt CC
// Notice quand le mode lite est actif : signale à l'user que le script
// est continu (pas découpé par SLIDE N), avec un bouton « 📝 Prompt
// Claude Code » qui ouvre une modal proposant un prompt clé-en-main
// pour régénérer un SCRIPT.md Feynman propre via une session Claude Code
// séparée (qui peut elle aussi auditer les autres dossiers PSI).

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
  // Récupère le contexte session courante pour formater le prompt
  let ctx = null;
  try {
    const r = await fetch("/api/current_session");
    if (r.ok) ctx = await r.json();
  } catch (_) { /* silencieux */ }
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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind }),
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
        setTimeout(() => { btn.textContent = "📋 Copier dans le presse-papier"; }, 2000);
      }
    } catch (_) {
      ta.select();
      document.execCommand("copy");
    }
  });
  document.getElementById("cc-prompt-close").addEventListener("click", () => modal.remove());
}
