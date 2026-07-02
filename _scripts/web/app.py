"""
app.py : front Flask du compagnon de révision.

Sert l'UI (index.html), expose une API JSON pour démarrer/terminer une
session, envoyer un message user, streamer la réponse Claude en SSE et
exposer le snapshot de quota.

L'état de la session vit en mémoire process : singleton sous lock car
Flask tourne en threaded mode. À redémarrer si bug, pas de persistance
au-delà du JSON de session écrit par ``SessionState`` (et restauré via
``find_resumable``).

Cf. ARCHITECTURE.md §8.
"""

import hmac
import json
import logging
import os
import queue
import re
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from flask import Flask, Response, g, jsonify, render_template, request, send_file, send_from_directory, stream_with_context

from claude_client import (
    DEFAULT_MODEL,
    MODE_COLLE,
    MODE_DECOUVERTE,
    MODE_GUIDE,
    MODE_WORKSPACE,
    ClaudeClient,
    ClaudeClientError,
    ClaudeQuotaExhaustedError,
)
from config import (
    CARTABLE_ROOT,
    COURS_ROOT,
    DEFAULT_ENGINE,
    ENGINE_PREF_PATH,
    PROMPT_SYSTEME_DECOUVERTE_PATH,
    PROMPT_SYSTEME_GUIDE_PATH,
    PROMPT_SYSTEME_PATH,
    PROMPT_SYSTEME_WORKSPACE_PATH,
    REMOTE_ACCESS_PATH,
    SCHEMA_VERSION_ENGINE_PREF,
    SESSIONS_DIR,
    TTS_CACHE_DIR,
    UPLOADS_DIR,
)
from cours_resolver import (
    find_enonce_pdf,
    find_free_poly,
    find_perso_script_imprimable,
    find_perso_script_md,
    find_perso_script_oral,
    find_perso_slides_pdf,
    find_perso_tache,
    list_annees_for_cc,
    list_exos_for_num,
    list_matieres,
    list_nums_for_type,
    list_types_for_matiere,
    resolve_corrections,
)
# Phase S4 (Cartable) : arbo DROIT. Importé comme module (et non via
# `from droit_resolver import ...`) pour ne PAS masquer les list_matieres /
# list_types_for_matiere / list_nums_for_type homonymes de cours_resolver.
import droit_resolver
from parser import ParserEvent, ParserEventType
from prompt_builder import PromptBuilder, SessionContext
from quota_check import get_usage_snapshot
from script_parser import parse_script
from session_state import SessionState
from slides_rasterize import rasterize_correction, rasterize_if_needed

logger = logging.getLogger(__name__)

# ============================================================ Flask app

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

app = Flask(
    __name__,
    template_folder=str(TEMPLATES_DIR),
    static_folder=str(STATIC_DIR),
)

# Phase v15.7.27 : cache-bust dynamique sur les assets statiques.
# Le user a vécu une note v15.7.26 sauvegardée sans `raw_text` parce que
# le browser cachait l'ancien app.js. Ici on expose `static_v(filename)`
# au template qui retourne `?v=<mtime>` : le browser revalide
# uniquement quand le fichier change réellement, pas de bump manuel.
@app.context_processor
def _inject_static_v():
    def static_v(filename: str) -> str:
        try:
            p = STATIC_DIR / filename
            return f"?v={int(p.stat().st_mtime)}"
        except Exception:
            return ""
    return {"static_v": static_v}


DEFAULT_PORT = 5680


# ============================================================ État de session (singleton)

class CompanionSession:
    """Container des objets vivants d'une séance."""

    def __init__(
        self,
        session_state: SessionState,
        client: ClaudeClient,
        prompt_builder: PromptBuilder,
    ):
        self.session_state = session_state
        self.client = client
        self.prompt_builder = prompt_builder
        self.event_queue: queue.Queue = queue.Queue()
        self.streaming_thread: Optional[threading.Thread] = None
        self.pending_user_text: Optional[str] = None
        # Phase v15.7.30.1 : ligne de contexte de lecture séparée du
        # `pending_user_text`. Ajoutée au prompt LLM mais PAS persistée
        # dans le transcript (sinon elle apparaît brute en bulle student
        # au rerender / reprise de session (bug observé v15.7.30).
        self.pending_reading_line: Optional[str] = None
        # Phase A.7.2 : flag « 1ʳᵉ stream attendue après start_session ».
        # Le contexte initial est déjà appended côté backend ; le frontend
        # appelle /api/stream_response juste après le start, sans
        # /api/send_message intermédiaire (le contexte EST le 1ʳᵉ message).
        # `/api/stream_response` doit donc accepter un pending_user_text
        # vide UNE FOIS pour streamer la réponse au contexte initial.
        self.initial_stream_pending: bool = True
        # Phase A.7.2 v7.3 : flag « retry stream après switch engine à chaud ».
        # Quand `/api/switch_engine` remplace `client` après un quota épuisé,
        # le user message est déjà dans l'historique transféré : le prochain
        # /api/stream_response doit juste relancer le stream sans toucher
        # au pending_user_text (consommé) ni à initial_stream_pending.
        self.retry_pending: bool = False
        # File d'attente des pièces jointes (photos téléphone, drag-drop,
        # paste clipboard, bouton 📎). Vidée au prochain send_message qui
        # injecte les attachements dans le texte (markdown pour images,
        # mention texte pour PDF/Excel/autres). Cf. /api/upload_attachment.
        self.pending_attachments: list[dict] = []
        self.lock = threading.Lock()
        # Phase v15.7.21 : flag set par POST /api/cancel_stream pour
        # interrompre gracieusement le SSE en cours. Checké à chaque
        # write côté /api/stream_response. Reset au démarrage de chaque
        # nouveau stream (cf. la même méthode).
        self.cancel_requested: bool = False
        # Phase A.8.4 : flag « le dernier user message contenait-il une
        # image ? ». Mis à jour au moment de consume pending_user_text dans
        # /api/stream_response. Utilisé par output_filters au post-stream
        # pour retirer un éventuel bloc OCR halluciné par le tuteur.
        self.last_user_had_image: bool = False


_state: Optional[CompanionSession] = None
_state_lock = threading.Lock()


# ============================================================ Accès distant : auth + URLs publiques (Phase A.7.2 v15.2)
# Permet d'exposer Compagnon à l'extérieur (Tailscale Funnel ou Cloudflare
# Tunnel) tout en gardant la sécurité raisonnable. Config dans
# `_secrets/remote_access.json` (cf. config.py REMOTE_ACCESS_PATH) :
#
#   {
#     "schema_version": 1,
#     "basic_auth": {"enabled": true, "user": "...", "pass": "..."},
#     "public_urls": {
#       "cloudflare_tunnel": "https://compagnon.gaylord.fr",
#       "tailscale_funnel": "https://compagnon-tailxxxx.ts.net"
#     }
#   }
#
# Si `basic_auth.enabled=true` : Flask exige Authorization: Basic ... sur
# chaque requête (sauf clients localhost 127.0.0.1/::1 : la GUI Tk locale
# n'est pas gênée). Comparaison constant-time via hmac.compare_digest pour
# éviter les attaques timing.
#
# Si le fichier est absent ou `enabled=false` → pas d'auth, comportement
# legacy. À NE PAS oublier d'activer si on bind sur un IP publique
# (Tailscale Funnel notamment, qui expose en clair sur Internet).

def _load_remote_access_cfg() -> Optional[dict]:
    """Lit ``_secrets/remote_access.json``. Retourne None si absent / illisible."""
    if not REMOTE_ACCESS_PATH.exists():
        return None
    try:
        with REMOTE_ACCESS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("remote_access.json illisible : %s", e)
        return None


_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}

# ============================================================ Rate limit + lockout (Phase v15.3)
# In-memory, par IP. Pas persistant : un restart Flask remet à zéro, mais
# l'attaquant a perdu son temps de toute façon.
#
# Seuil : 10 échecs en 5 min → lockout 15 min. Calibré pour ne pas gêner
# l'humain qui mistype son password (10 tries c'est beaucoup) mais bloquer
# net un bot qui tape sa wordlist.

_AUTH_FAIL_WINDOW_SEC = 300       # 5 min window pour compter les échecs
_AUTH_FAIL_THRESHOLD = 10         # nb max d'échecs dans la window avant lockout
_AUTH_LOCKOUT_SEC = 900           # 15 min de lockout après seuil atteint

_auth_failures: dict[str, list[float]] = {}  # ip → liste de timestamps d'échec
_auth_lockouts: dict[str, float] = {}        # ip → unlock_at_ts
_auth_state_lock = threading.Lock()


def _record_auth_failure(ip: str) -> None:
    """Enregistre un échec d'auth pour une IP. Déclenche un lockout si
    le seuil est atteint dans la window."""
    import time
    now = time.time()
    with _auth_state_lock:
        bucket = _auth_failures.setdefault(ip, [])
        # Purge les échecs hors window
        cutoff = now - _AUTH_FAIL_WINDOW_SEC
        bucket[:] = [t for t in bucket if t >= cutoff]
        bucket.append(now)
        if len(bucket) >= _AUTH_FAIL_THRESHOLD:
            _auth_lockouts[ip] = now + _AUTH_LOCKOUT_SEC
            logger.warning(
                "Auth lockout: IP %s a atteint %d echecs en %ds, locked %ds",
                ip, _AUTH_FAIL_THRESHOLD, _AUTH_FAIL_WINDOW_SEC,
                _AUTH_LOCKOUT_SEC,
            )
            bucket.clear()


def _check_lockout(ip: str) -> Optional[float]:
    """Retourne le nombre de secondes restantes de lockout, ou None si
    non locked. Auto-purge un lockout expiré."""
    import time
    now = time.time()
    with _auth_state_lock:
        unlock_at = _auth_lockouts.get(ip)
        if unlock_at is None:
            return None
        if now >= unlock_at:
            del _auth_lockouts[ip]
            return None
        return unlock_at - now


def _reset_auth_state(ip: str) -> None:
    """Reset les compteurs après un succès d'auth : l'humain ne doit pas
    accumuler d'échecs entre 2 sessions normales."""
    with _auth_state_lock:
        _auth_failures.pop(ip, None)
        _auth_lockouts.pop(ip, None)


def _check_credentials(auth_obj, basic_cfg) -> Optional[str]:
    """Compare les credentials Basic Auth fournis aux 2 paires possibles
    (owner, viewer) dans ``basic_cfg``. Retourne le rôle (``"owner"`` ou
    ``"viewer"``) ou None si match aucun.

    Comparaison constant-time via ``hmac.compare_digest``.
    """
    if auth_obj is None:
        return None
    user = str(auth_obj.username or "")
    password = str(auth_obj.password or "")

    owner_user = str(basic_cfg.get("user") or "")
    owner_pass = str(basic_cfg.get("pass") or "")
    if owner_user and owner_pass:
        if (hmac.compare_digest(user, owner_user)
                and hmac.compare_digest(password, owner_pass)):
            return "owner"

    viewer_user = str(basic_cfg.get("viewer_user") or "")
    viewer_pass = str(basic_cfg.get("viewer_pass") or "")
    if viewer_user and viewer_pass:
        if (hmac.compare_digest(user, viewer_user)
                and hmac.compare_digest(password, viewer_pass)):
            return "viewer"

    return None


# Whitelist GET pour les viewers. Tout endpoint GET hors de cette liste,
# et tout endpoint non-GET (POST/PATCH/DELETE/etc.) est bloqué pour les
# viewers (lecture seule = pas de mutation, pas de consommation quota).
_VIEWER_GET_ALLOW = {
    "/", "/mobile", "/robots.txt", "/favicon.ico",
    "/api/role",
    "/api/quota", "/api/connection_info",
    "/api/current_session", "/api/sessions",
    "/api/cours_options", "/api/cours_file",
    "/api/upload_file",  # Phase A.10.2 : uploads servis depuis _uploads/
    "/api/corrections/init", "/api/guided/init",
    "/api/pending_attachments",
    "/api/session_photos",  # Phase A.9.1 : galerie photos de la session active
    "/api/stickies",  # Phase A.10 : consignes épinglées de la session active
    "/api/dynamic_outline",  # Phase A.10.13c : sommaire dynamique de la session
    "/api/engines",  # affichage du moteur courant
}
_VIEWER_GET_ALLOW_PREFIX = (
    "/static/",
    # Détail d'une session par id, GET only (DELETE/PATCH déjà filtrés
    # par le check de méthode).
    "/api/sessions/",
)


def _viewer_can_access(method: str, path: str) -> bool:
    if method != "GET":
        return False
    if path in _VIEWER_GET_ALLOW:
        return True
    if any(path.startswith(p) for p in _VIEWER_GET_ALLOW_PREFIX):
        return True
    return False


@app.before_request
def _enforce_basic_auth():
    """Vérifie HTTP Basic Auth + détermine le rôle (owner/viewer). Stocke
    le rôle dans ``flask.g.role`` pour usage par les routes.

    - Skip pour 127.0.0.1/::1 (trafic local : GUI Tk, F5 navigateur même
      machine) : rôle = owner par défaut.
    - Si auth désactivée dans la config : rôle = owner.
    - Si auth activée : essaie owner puis viewer creds, sinon 401.
    - Lockout 15 min après 10 échecs en 5 min (par IP).
    - **Si rôle = viewer** : tout endpoint hors whitelist GET → 403.
    """
    g.role = "owner"  # défaut, écrasé si l'auth donne un autre rôle
    cfg = _load_remote_access_cfg()
    if not cfg:
        return None
    basic = cfg.get("basic_auth") or {}
    if not basic.get("enabled"):
        return None
    # Skip pour requêtes vraiment locales (GUI Tk lance localhost:5680).
    remote = (request.remote_addr or "").lower()
    if remote in _LOCAL_HOSTS:
        return None
    # Lockout actif ? → 429 immédiat sans même tester l'auth.
    locked_remaining = _check_lockout(remote)
    if locked_remaining is not None:
        retry = max(1, int(locked_remaining))
        return Response(
            f"Trop de tentatives échouées. Réessayez dans {retry} s.",
            429,
            {"Retry-After": str(retry)},
        )
    expected_user = str(basic.get("user") or "")
    expected_pass = str(basic.get("pass") or "")
    if not expected_user or not expected_pass:
        return Response("Auth misconfigured", 503)
    auth = request.authorization
    if auth is None:
        # Pas d'enregistrement de failure ici : un client peut faire un GET
        # sans header Authorization la 1ʳᵉ fois (popup browser). On compte
        # uniquement les vrais essais (auth fournie mais incorrecte).
        return Response(
            "Auth required",
            401,
            {"WWW-Authenticate": 'Basic realm="Compagnon de revision"'},
        )
    role = _check_credentials(auth, basic)
    if role is None:
        _record_auth_failure(remote)
        return Response(
            "Auth invalid",
            401,
            {"WWW-Authenticate": 'Basic realm="Compagnon de revision"'},
        )
    # Succès : reset les compteurs.
    _reset_auth_state(remote)
    g.role = role
    # Mode lecture seule : refuse tout endpoint qui mute / consomme quota.
    if role == "viewer" and not _viewer_can_access(request.method, request.path):
        return jsonify({
            "error": "lecture seule : endpoint non autorisé pour les viewers",
            "role": "viewer",
            "method": request.method,
            "path": request.path,
        }), 403
    return None


@app.route("/api/role", methods=["GET"])
def api_role():
    """Retourne le rôle de l'utilisateur connecté (``owner``/``viewer``).
    Permet au front de cacher les contrôles d'écriture pour les viewers."""
    return jsonify({
        "role": getattr(g, "role", "owner"),
    })


# ============================================================ Whisper lazy-load (Phase A.6.2)
# Le bouton micro du navigateur POST son blob audio à /api/transcribe.
# On charge le modèle large-v3 à la première requête, ~5-10 s + ~3 Go VRAM.
# Singleton thread-safe : le 2e click est instantané.

_transcriber = None
_transcriber_lock = threading.Lock()


def _get_transcriber():
    global _transcriber
    if _transcriber is None:
        with _transcriber_lock:
            if _transcriber is None:
                from transcribe_stream import WhisperTranscriber
                logger.info("Lazy-load Whisper large-v3 (premiere requete /api/transcribe)...")
                _transcriber = WhisperTranscriber()
    return _transcriber


# ============================================================ Endpoints

@app.route("/")
def index():
    """Sert la page principale."""
    if not (TEMPLATES_DIR / "index.html").exists():
        return ("index.html absent (sera codé en §14).", 404)
    # Phase v15.7.27 : render_template (pas send_from_directory) pour
    # interpréter les balises Jinja {{ static_v(...) }} qui posent le
    # cache-bust ?v=<mtime> sur app.js et style.css. Avant : balises
    # littérales dans le HTML → 404 → CSS et JS perdus.
    return render_template("index.html")


@app.route("/robots.txt", methods=["GET"])
def robots_txt():
    """Bloque l'indexation par les moteurs bien élevés (Google, Bing, etc.).
    Ne stoppe pas les bots de scraping ciblé, mais filtre les drive-by.
    Cf. _remote_access/README.md et CHANGELOG Phase v15.3."""
    return Response(
        "User-agent: *\nDisallow: /\n",
        mimetype="text/plain",
    )


@app.route("/mobile")
def page_mobile():
    """Sert la page mobile : capture de photos depuis le téléphone vers
    la session active. Bookmark à mettre sur l'écran d'accueil du téléphone
    (URL : http://<PC-tailscale-ip>:5680/mobile).
    """
    if not (TEMPLATES_DIR / "mobile.html").exists():
        return ("mobile.html absent.", 404)
    return send_from_directory(str(TEMPLATES_DIR), "mobile.html")


@app.route("/api/connection_info", methods=["GET"])
def api_connection_info():
    """Retourne les voies de connexion possibles à Compagnon (Phase v15.2).

    Trois canaux possibles :
      1. **LAN local** (WiFi maison / Ethernet) : IP via socket trick.
      2. **Tailscale tailnet** : IP `100.X.Y.Z` via `tailscale ip -4`.
      3. **URL publiques persistantes** (Tailscale Funnel, Cloudflare Tunnel)
         lues depuis ``_secrets/remote_access.json`` si l'utilisateur a
         configuré ces tunnels.

    Affiché dans le panneau « 🔗 Distant » de la sidebar avec liens
    cliquables/copiables. ``basic_auth_enabled`` permet au front de prévenir
    qu'une auth sera demandée au navigateur sur les liens publics.
    """
    import os as _os
    import socket
    import subprocess

    # Double protection contre le flash console quand Flask tourne sous
    # pythonw.exe (GUI subsystem) et lance tailscale.exe (Go console) :
    # CREATE_NO_WINDOW seul ne suffit pas, il faut aussi STARTUPINFO+SW_HIDE.
    # Endpoint pollé toutes les 30s par le front → flashs visibles sinon.
    _silent_kwargs: dict = {}
    if _os.name == "nt":
        _si = subprocess.STARTUPINFO()
        _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        _si.wShowWindow = subprocess.SW_HIDE
        _silent_kwargs = {
            "creationflags": subprocess.CREATE_NO_WINDOW,
            "startupinfo": _si,
        }

    lan_ip = None
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
    except OSError:
        pass
    finally:
        s.close()

    tailscale_ip = None
    try:
        r = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True, text=True, timeout=3,
            **_silent_kwargs,
        )
        if r.returncode == 0:
            ips = [line.strip() for line in r.stdout.splitlines() if line.strip()]
            tailscale_ip = ips[0] if ips else None
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    cfg = _load_remote_access_cfg() or {}
    public_urls = cfg.get("public_urls") or {}
    cloudflare_tunnel = (public_urls.get("cloudflare_tunnel") or "").strip() or None
    tailscale_funnel = (public_urls.get("tailscale_funnel") or "").strip() or None
    basic = cfg.get("basic_auth") or {}
    basic_auth_enabled = bool(basic.get("enabled"))
    viewer_enabled = bool(basic.get("viewer_user") and basic.get("viewer_pass"))

    # État live du Funnel (public / tailnet only / off) via query Tailscale.
    # Permet au panneau « 🔗 Distant » d'afficher la réalité, pas juste les
    # URLs configurées dans le JSON.
    funnel_state = "off"
    funnel_live_url: Optional[str] = None
    try:
        r = subprocess.run(
            ["tailscale", "funnel", "status"],
            capture_output=True, text=True, timeout=3,
            **_silent_kwargs,
        )
        if r.returncode == 0:
            txt = r.stdout or ""
            if "(Funnel on)" in txt:
                funnel_state = "public"
            elif "(tailnet only)" in txt:
                funnel_state = "tailnet"
            elif "No serve config" in txt:
                funnel_state = "off"
            for line in txt.splitlines():
                line = line.strip()
                if line.startswith("https://") and "ts.net" in line:
                    funnel_live_url = line.split()[0]
                    break
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    return jsonify({
        "lan_ip": lan_ip,
        "tailscale_ip": tailscale_ip,
        "cloudflare_tunnel": cloudflare_tunnel,
        "tailscale_funnel": tailscale_funnel,
        "tailscale_funnel_live_url": funnel_live_url,
        "tailscale_funnel_state": funnel_state,
        "basic_auth_enabled": basic_auth_enabled,
        "viewer_enabled": viewer_enabled,
        "port": DEFAULT_PORT,
        "hostname": socket.gethostname(),
    })


@app.route("/api/cours_options", methods=["GET"])
def api_cours_options():
    """Renvoie les options disponibles pour les selects cascading du form.

    Query params (tous optionnels) :
      - ``matiere`` : filtre les types disponibles
      - ``type`` : combiné à matiere, filtre les nums
      - ``num`` : combiné à matiere+type, filtre exos et années (CC)
      - ``annee`` : pour les CC nestés (filtre les exos par millésime)

    Retourne **tout** ce qui est dérivable du contexte donné : le front
    n'a qu'à câbler les sous-éléments du payload aux selects appropriés.
    Implémentation calquée sur ``gui.py._cascade_from_*`` (Phase A.6.1).
    """
    matiere = (request.args.get("matiere") or "").strip().upper()
    type_code = (request.args.get("type") or "").strip().upper()
    num = (request.args.get("num") or "").strip()
    annee = (request.args.get("annee") or "").strip() or None

    out = {
        "matieres": list_matieres(COURS_ROOT),
        "types": [],
        "nums": [],
        "annees": [],
        "exos": [],
    }
    if matiere:
        try:
            out["types"] = list_types_for_matiere(COURS_ROOT, matiere)
        except Exception:  # noqa: BLE001
            logger.exception("list_types_for_matiere a leve")
    if matiere and type_code:
        try:
            out["nums"] = list_nums_for_type(COURS_ROOT, matiere, type_code)
        except Exception:  # noqa: BLE001
            logger.exception("list_nums_for_type a leve")
    if matiere and type_code == "CC" and num:
        try:
            out["annees"] = list_annees_for_cc(COURS_ROOT, matiere, num)
        except Exception:  # noqa: BLE001
            logger.exception("list_annees_for_cc a leve")
    if matiere and type_code and num:
        try:
            out["exos"] = list_exos_for_num(
                COURS_ROOT, matiere, type_code, num, annee
            )
        except Exception:  # noqa: BLE001
            logger.exception("list_exos_for_num a leve")
    return jsonify(out)


@app.route("/api/droit_options", methods=["GET"])
def api_droit_options():
    """Phase S4 (Cartable) : options des selects cascading pour la source DROIT.

    Pendant simple de ``/api/cours_options`` mais pour l'arbo DROIT (markdown,
    produite par Cartable). Cascade à 3 niveaux seulement : matière (slug) →
    type (CM|TD) → num. Pas d'exo ni de millésime.

    Query params (tous optionnels) :
      - ``matiere`` : slug de la matière (filtre les types)
      - ``type`` : combiné à matiere, filtre les nums (CM|TD)
    """
    slug = (request.args.get("matiere") or "").strip()
    type_code = (request.args.get("type") or "").strip().upper()
    out = {
        "matieres": droit_resolver.list_matieres(CARTABLE_ROOT),
        "types": [],
        "nums": [],
    }
    if slug:
        try:
            out["types"] = droit_resolver.list_types_for_matiere(CARTABLE_ROOT, slug)
        except Exception:  # noqa: BLE001
            logger.exception("droit_resolver.list_types_for_matiere a leve")
    if slug and type_code:
        try:
            out["nums"] = droit_resolver.list_nums_for_type(
                CARTABLE_ROOT, slug, type_code
            )
        except Exception:  # noqa: BLE001
            logger.exception("droit_resolver.list_nums_for_type a leve")
    return jsonify(out)


# ============================================================ TTS (Phase A.7.2 v14)
# Edge TTS via la lib edge-tts (API gratuite Microsoft Read Aloud, sans clé).
# 4 voix françaises de qualité Neural. Cache MP3 sur SHA1(voice + text)
# pour éviter de regénérer la même phrase. Le front utilise un <audio>
# HTML5 avec controls custom (play/pause/scrub/speed).

_TTS_VOICES_FR = [
    {"id": "fr-FR-DeniseNeural",   "label": "Denise (femme, neutre)"},
    {"id": "fr-FR-HenriNeural",    "label": "Henri (homme, posé)"},
    {"id": "fr-FR-AlainNeural",    "label": "Alain (homme, mature)"},
    {"id": "fr-FR-BrigitteNeural", "label": "Brigitte (femme, dynamique)"},
]
_TTS_DEFAULT_VOICE = "fr-FR-DeniseNeural"
_TTS_MAX_CHARS = 8000  # ~5-6 minutes audio à voix normale


@app.route("/api/tts/voices", methods=["GET"])
def api_tts_voices():
    """Liste des voix françaises proposées au front (sélecteur du player)."""
    return jsonify({
        "voices": _TTS_VOICES_FR,
        "default": _TTS_DEFAULT_VOICE,
    })


@app.route("/api/tts/synthesize", methods=["POST"])
def api_tts_synthesize():
    """Synthétise du texte en MP3 via Edge TTS. Body : {text, voice?}.
    Cache disque sur sha1(voice + text) pour éviter de regénérer."""
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    voice = (body.get("voice") or _TTS_DEFAULT_VOICE).strip()
    if not text:
        return jsonify({"error": "text vide"}), 400
    if len(text) > _TTS_MAX_CHARS:
        return jsonify({
            "error": f"text trop long ({len(text)} chars, max {_TTS_MAX_CHARS})",
        }), 400
    if voice not in {v["id"] for v in _TTS_VOICES_FR}:
        return jsonify({"error": f"voix inconnue : {voice}"}), 400

    import asyncio
    import hashlib

    cache_key = hashlib.sha1(f"{voice}::{text}".encode("utf-8")).hexdigest()
    TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = TTS_CACHE_DIR / f"{cache_key}.mp3"
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return send_file(str(cache_path), mimetype="audio/mpeg",
                         conditional=True)

    try:
        import edge_tts
    except ImportError:
        return jsonify({"error": "edge-tts non installé (pip install edge-tts)"}), 500

    async def _synthesize() -> bytes:
        communicate = edge_tts.Communicate(text, voice)
        chunks = []
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                chunks.append(chunk["data"])
        return b"".join(chunks)

    try:
        audio_bytes = asyncio.run(_synthesize())
    except Exception as e:  # noqa: BLE001
        logger.exception("TTS edge-tts a leve")
        return jsonify({"error": f"synthèse échouée : {type(e).__name__}: {e}"}), 500

    if not audio_bytes:
        return jsonify({"error": "TTS retourné vide"}), 500

    # Persiste le cache (atomic via .tmp + retry OneDrive, Phase Z.8.7)
    from utils import _replace_with_retry
    tmp_path = cache_path.with_suffix(".mp3.tmp")
    tmp_path.write_bytes(audio_bytes)
    _replace_with_retry(tmp_path, cache_path)
    logger.info("TTS cached : %s (%d bytes, voice=%s)",
                cache_path.name, len(audio_bytes), voice)

    return Response(audio_bytes, mimetype="audio/mpeg", headers={
        "Content-Length": str(len(audio_bytes)),
        "Cache-Control": "public, max-age=31536000",
    })


@app.route("/api/quota", methods=["GET"])
def api_quota():
    """Snapshot quota Pro Max + état des autres moteurs (Phase v15.6.5).

    Retourne d'abord le snapshot Pro Max (compatible avec le front
    historique : `session_pct`, `weekly_pct`, etc.) puis ajoute un
    bloc `engines` avec, pour chaque moteur configuré, son état :
    - DeepSeek : solde restant en USD (via `GET /user/balance`).
    - Groq / Gemini / API Anthropic : pas d'endpoint balance public,
      on retourne juste `key_present` + les limites connues du free
      tier (RPM/RPD/TPM hardcodées d'après la doc des providers).

    Cache 30 s sur le bloc engines pour ne pas spammer les APIs
    externes au polling 30 s du frontend.
    """
    snapshot = get_usage_snapshot()
    snapshot["engines"] = _collect_engines_status()
    return jsonify(snapshot)


# ============================================================ Engines status (Phase v15.6.5)
# Cache 30 s sur le résultat de _collect_engines_status : DeepSeek
# rate-limite parfois /user/balance, et le frontend poll toutes les 30 s.

_engines_status_cache: dict = {}
_engines_status_cache_ts: float = 0.0
_ENGINES_CACHE_TTL_S = 30.0


def _collect_engines_status() -> dict:
    """Retourne {<engine_id>: {...}, "fetched_at": iso}. Tolérant aux
    échecs : si une API ne répond pas, on retourne `error` pour ce
    moteur précis et on continue les autres.
    """
    import time
    global _engines_status_cache, _engines_status_cache_ts
    now = time.time()
    if _engines_status_cache and (now - _engines_status_cache_ts) < _ENGINES_CACHE_TTL_S:
        return _engines_status_cache

    result: dict = {}

    # DeepSeek : endpoint balance officiel.
    if os.environ.get("DEEPSEEK_API_KEY"):
        result["deepseek_api"] = _fetch_deepseek_balance()
    else:
        result["deepseek_api"] = {"key_present": False, "label": "DeepSeek"}

    # Moteurs sans endpoint balance : on retourne juste l'état clé +
    # les limites connues du tier gratuit (utile pour matcher contre
    # la taille de la requête courante quand l'utilisateur réfléchit
    # à quel moteur basculer).
    free_tier_limits = {
        "groq_api": {
            "label": "Groq (Llama 3.3 70B)",
            "tier_label": "Free Tier",
            "rpm": 30, "rpd": 14400, "tpm": 12000,
            "billing_url": "https://console.groq.com/settings/billing",
            "key_env": "GROQ_API_KEY",
        },
        "gemini_api": {
            "label": "Gemini 2.5 Pro",
            "tier_label": "Free Tier",
            "rpm": 60, "rpd": 1500,
            "billing_url": "https://aistudio.google.com/app/apikey",
            "key_env": "GEMINI_API_KEY",
        },
        "api_anthropic": {
            "label": "API Anthropic",
            "tier_label": "Pay-as-you-go",
            "billing_url": "https://console.anthropic.com/settings/billing",
            "key_env": "ANTHROPIC_API_KEY",
        },
    }
    for engine_id, info in free_tier_limits.items():
        key_env = info.pop("key_env", None)
        result[engine_id] = {
            "key_present": bool(os.environ.get(key_env)) if key_env else False,
            **info,
        }

    out = {
        "engines": result,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
    }
    _engines_status_cache = out
    _engines_status_cache_ts = now
    return out


def _fetch_deepseek_balance() -> dict:
    """Appelle GET https://api.deepseek.com/user/balance avec la clé.

    Réponse documentée :
        {
          "is_available": bool,
          "balance_infos": [
            {"currency": "USD",
             "total_balance": "8.13",
             "granted_balance": "5.00",
             "topped_up_balance": "3.13"}
          ]
        }
    """
    import json as _json
    import urllib.error
    import urllib.request
    base = {"key_present": True, "label": "DeepSeek"}
    try:
        req = urllib.request.Request(
            "https://api.deepseek.com/user/balance",
            headers={
                "Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}",
                "Accept": "application/json",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = _json.loads(resp.read().decode("utf-8"))
        infos = payload.get("balance_infos") or []
        first = infos[0] if infos else {}
        return {
            **base,
            "is_available": bool(payload.get("is_available")),
            "currency": first.get("currency", "USD"),
            "total_balance": _safe_float(first.get("total_balance")),
            "granted_balance": _safe_float(first.get("granted_balance")),
            "topped_up_balance": _safe_float(first.get("topped_up_balance")),
            "billing_url": "https://platform.deepseek.com/billing",
        }
    except urllib.error.HTTPError as e:
        # 401 = clé invalide ; autres = erreur transitoire
        return {**base, "error": f"HTTP {e.code}", "billing_url": "https://platform.deepseek.com/billing"}
    except Exception as e:
        return {**base, "error": str(e)[:200]}


def _safe_float(v):
    """Convertit en float (DeepSeek renvoie les balances en string)."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@app.route("/api/start_session", methods=["POST"])
def api_start_session():
    """Démarre une session. Body JSON : matiere, type, num, exo, +chemins, +mode.

    Phase A.8.3 : accepte aussi un body avec ``sujet_libre`` (string non vide)
    pour démarrer une séance hors COURS/. Dans ce cas, matiere/type/num/exo
    sont remplis par des valeurs sentinelles côté _build_session_context.
    """
    global _state
    body = request.get_json(silent=True) or {}

    # Phase A.9 : détection workspace avant validation des champs requis.
    # En workspace, matiere/type/num/exo sont synthétisés côté backend, et
    # le mode est forcé à `workspace` quoi que dise le radio Mode.
    workspace_root_raw = (body.get("workspace_root") or "").strip()
    is_workspace = bool(workspace_root_raw)
    if is_workspace:
        ws_path = Path(workspace_root_raw)
        if not ws_path.is_absolute() or not ws_path.is_dir():
            return jsonify({
                "error": f"workspace_root invalide : {workspace_root_raw!r}, "
                         "doit être un chemin absolu vers un dossier existant"
            }), 400
        from prompt_builder import slugify_workspace
        slug = slugify_workspace(ws_path)
        body.setdefault("matiere", "WORKSPACE")
        body.setdefault("type", "DIR")
        body.setdefault("num", slug)
        body.setdefault("exo", "full")
        body["mode"] = MODE_WORKSPACE
        body["workspace_root"] = str(ws_path.resolve())

    # Phase A.8.3 : détection sujet libre avant validation des champs requis.
    # En sujet libre, matiere/type/num/exo sont synthétisés côté backend.
    sujet_libre_raw = (body.get("sujet_libre") or "").strip()
    is_libre = bool(sujet_libre_raw) and not is_workspace
    if is_libre:
        # Synthétise les sentinelles pour passer la validation
        from prompt_builder import slugify_topic
        slug = slugify_topic(sujet_libre_raw)
        body.setdefault("matiere", "LIBRE")
        body.setdefault("type", "SUJET")
        body.setdefault("num", slug)
        body.setdefault("exo", "full")

    # Phase S4 (Cartable) : détection source DROIT avant validation. La
    # sélection (slug matière, type CM|TD, num) alimente matiere/type/num ;
    # exo='full' (le droit n'a ni exo ni millésime). Le contenu (transcription
    # + fiche) est résolu côté _build_session_context via droit_resolver.
    source = (body.get("source") or "").strip().lower()
    is_droit = (source == "droit") and not is_workspace and not is_libre
    if is_droit:
        d_slug = (body.get("droit_matiere") or body.get("matiere") or "").strip()
        d_type = (body.get("droit_type") or body.get("type") or "").strip().upper()
        d_num = str(body.get("droit_num") or body.get("num") or "").strip()
        if not (d_slug and d_type and d_num):
            return jsonify({
                "error": "source droit : droit_matiere, droit_type (CM|TD) et "
                         "droit_num requis"
            }), 400
        if d_type not in ("CM", "TD"):
            return jsonify({
                "error": f"type droit invalide : {d_type!r} (attendu CM ou TD)"
            }), 400
        body["matiere"] = d_slug
        body["type"] = d_type
        body["num"] = d_num
        body.setdefault("exo", "full")
        body["source"] = "droit"

    required = ("matiere", "type", "num", "exo")
    missing = [k for k in required if k not in body]
    if missing:
        return jsonify({"error": f"champs manquants : {missing}"}), 400

    mode = (body.get("mode") or MODE_COLLE).strip()
    if mode not in (MODE_COLLE, MODE_GUIDE, MODE_DECOUVERTE, MODE_WORKSPACE):
        return jsonify({
            "error": f"mode invalide : {mode!r} (attendu colle, guidé, "
                     "découverte ou workspace)"
        }), 400

    # Phase A.8.3 : mode guidé interdit en sujet libre (pas de script Feynman
    # préparé, pas de slides à dérouler, Guidé n'a aucun sens).
    if is_libre and mode == MODE_GUIDE:
        return jsonify({
            "error": "mode guidé non supporté en sujet libre (pas de script "
                     "Feynman ni slides à dérouler). Utilise découverte ou colle."
        }), 400

    # Phase v15.7.4 : format colle. Lu seulement si mode=colle (en
    # guidé le tuteur a déjà accès aux PDF via Read/Grep, donc le
    # paramètre est sans effet, mais on le mémorise quand même pour
    # ne pas perdre la valeur user au prochain switch en colle).
    colle_format_raw = (body.get("colle_format") or "mixte").strip().lower()
    colle_format = colle_format_raw if colle_format_raw in ("oral", "photos", "mixte") else "mixte"

    # Phase v15.7.30 : ancrage corrigé (strict|consultatif|aucun). Idem
    # colle_format : mémorisé même en guidé pour ne pas perdre la valeur.
    corrige_anchor_raw = (body.get("corrige_anchor") or "strict").strip().lower()
    if corrige_anchor_raw in ("sans_corrigé", "sans_corrige", "sans corrigé", "sans corrige"):
        corrige_anchor_raw = "aucun"
    corrige_anchor = corrige_anchor_raw if corrige_anchor_raw in ("strict", "consultatif", "aucun") else "strict"
    # Phase A.8.3 : en sujet libre, l'ancrage corrigé n'a pas de sens (aucun
    # corrigé officiel). On force `aucun` quel que soit le choix utilisateur.
    # Phase A.9 : idem pour workspace : le tuteur explore un dossier
    # arbitraire, pas un exo COURS avec corrigé associé.
    # Phase S4 (Cartable) : en droit, pas de corrigé officiel d'exercice : la
    # fiche de révision tient lieu de référence. L'ancrage corrigé n'a pas de
    # sens → forcé `aucun` (placeholder propre dans le session_id).
    if is_libre or is_workspace or is_droit:
        corrige_anchor = "aucun"

    try:
        ctx = _build_session_context(body)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 400

    engine = _read_engine_pref()
    # Phase Z.8 : mode `lecture` supprimé, absorbé par `guidé`. Le mode
    # guidé utilise PROMPT_SYSTEME_GUIDE.md (posture tuteur + accès FS
    # Read/Grep + SUGGESTED_EDIT + UI slide-par-slide). Mode colle =
    # interrogation pure sans accès FS, prompt COMPAGNON.
    # Phase A.8 : mode `découverte` = tuteur explicateur zéro prérequis,
    # prompt DECOUVERTE.
    if mode == MODE_GUIDE:
        prompt_path = PROMPT_SYSTEME_GUIDE_PATH
    elif mode == MODE_DECOUVERTE:
        prompt_path = PROMPT_SYSTEME_DECOUVERTE_PATH
    elif mode == MODE_WORKSPACE:
        # Phase A.9 : prompt dédié + cours_root = workspace_root pour que les
        # tools FS du subprocess Claude Code aient le bon cwd. Le builder
        # n'utilise pas cours_root pour résoudre des PDF COURS (toutes les
        # sections COURS sont skippées dans la branche workspace de
        # build_initial_context_message).
        prompt_path = PROMPT_SYSTEME_WORKSPACE_PATH
    else:
        prompt_path = PROMPT_SYSTEME_PATH
    try:
        # Phase S4 (Cartable) : en droit, le builder n'utilise pas cours_root
        # (les chemins transcription/fiche sont absolus dans le ctx), mais on
        # le scope quand même sur la matière pour cohérence avec le client FS.
        if mode == MODE_WORKSPACE:
            prompt_cours_root = Path(body["workspace_root"])
        elif is_droit:
            prompt_cours_root = CARTABLE_ROOT / body["matiere"]
        else:
            prompt_cours_root = COURS_ROOT
        builder = PromptBuilder(prompt_path, prompt_cours_root)
    except OSError as e:
        return jsonify({"error": f"prompt système absent ({prompt_path}) : {e}"}), 500

    base_id = _build_session_id(
        ctx, mode=mode, colle_format=colle_format, corrige_anchor=corrige_anchor,
    )
    # Phase A.9 : suffixe _N. Par défaut _1 (écrasement si déjà là, le
    # front a déjà géré le conflict modal). Si body.force_new_session,
    # scan vers _2/_3/... pour ne PAS écraser.
    session_id = _resolve_session_id(
        base_id, force_new_session=bool(body.get("force_new_session")),
    )
    session_state = SessionState(
        session_id=session_id,
        sessions_dir=SESSIONS_DIR,
        context=ctx,
        engine=engine,
        model=DEFAULT_MODEL,
    )
    session_state.data["mode"] = mode  # trace dans le JSON
    session_state.data["colle_format"] = colle_format  # Phase v15.7.4
    session_state.data["corrige_anchor"] = corrige_anchor  # Phase v15.7.30
    # Phase A.8.3 : trace sujet libre dans le JSON (additif, pas de bump
    # schéma). Permet à l'archive .md et au panneau Historique d'afficher
    # le texte libre comme titre de séance.
    if is_libre:
        session_state.data["sujet_libre"] = sujet_libre_raw
    # Phase A.9 : trace workspace dans le JSON (path + focus + excludes).
    # Permet à la reprise (`/api/resume_session`) de reconstruire le ctx
    # avec le bon workspace_root, et au panneau Historique d'afficher le
    # basename du dossier comme titre.
    if is_workspace and ctx.workspace_root is not None:
        session_state.data["workspace_root"] = str(ctx.workspace_root)
        session_state.data["workspace_focus_subdir"] = (
            ctx.workspace_focus_subdir or ""
        )
        session_state.data["workspace_excludes"] = list(
            ctx.workspace_excludes or ()
        )
    # Phase S4 (Cartable) : trace la source DROIT dans le JSON (additif, pas de
    # bump schéma). Permet à /api/resume_session de reconstruire le ctx droit
    # et au panneau Historique d'afficher la matière de droit.
    if ctx.droit_source is not None:
        session_state.data["source"] = "droit"
        session_state.data["droit_matiere"] = ctx.droit_source
    session_state.start()

    # Phase A.9 : en mode workspace, on passe workspace_root au ClaudeClient
    # comme `cours_root`. Le subprocess CLI Claude Code prend alors ce path
    # comme cwd → Read/Grep/Glob scopés au workspace, pas à COURS_ROOT.
    # Phase S4 (Cartable) : en droit, on scope les tools FS sur le dossier de
    # la matière (lecture active de la fiche/transcription en mode guidé).
    if mode == MODE_WORKSPACE and ctx.workspace_root:
        client_cours_root = ctx.workspace_root
    elif ctx.droit_source is not None:
        client_cours_root = CARTABLE_ROOT / ctx.droit_source
    else:
        client_cours_root = COURS_ROOT
    client = ClaudeClient(
        engine=engine,
        system_prompt=builder.system_prompt,
        mode=mode,
        cours_root=client_cours_root,
    )
    initial = builder.build_initial_context_message(
        ctx, mode=mode, colle_format=colle_format,
        corrige_anchor=corrige_anchor,
    )
    client.append_user_message(initial)

    # Phase v15 : auto-advance opt-in. Si l'étudiant a coché la case
    # « 🤖 Auto-nav » au démarrage (mode guidé uniquement), on injecte
    # un message synthétique dans le _history qui rappelle au tuteur
    # qu'il peut émettre <<<NEXT_SLIDE>>>. Sinon (défaut), le tuteur
    # ne fait pas avancer de lui-même (cf. prompt §2.9).
    auto_advance = bool(body.get("auto_advance"))
    if auto_advance and mode == MODE_GUIDE:
        client.append_user_message(_AUTO_ADVANCE_REMINDER)
        # Persiste le flag pour que le bouton « Rappeler nav » sache
        # qu'il a vocation à s'afficher.
        session_state.set_meta("auto_advance", True)
        logger.info("Auto-advance activé pour session %s", session_id)

    with _state_lock:
        if _state is not None:
            try:
                _state.session_state.finalize(interrupted=True)
            except Exception:
                logger.exception("Cleanup ancien state a leve")
        _state = CompanionSession(session_state, client, builder)

    logger.info("Session demarree : %s (engine=%s, mode=%s)", session_id, engine, mode)
    # Pré-rasterisation des corrigés + script imprimable en arrière-plan,
    # pour que le 1ʳᵉ open du panneau « Corrigés & script » soit instantané.
    _kickoff_corrige_prerasterize(ctx)
    return jsonify({
        "ok": True,
        "session_id": session_id,
        "engine": engine,
        "mode": mode,
        "colle_format": colle_format,
        "corrige_anchor": corrige_anchor,
        "auto_advance": auto_advance and mode == MODE_GUIDE,
    })


_AUTO_ADVANCE_REMINDER = (
    "[Note système : auto-advance activé]\n\n"
    "L'étudiant a coché la case « 🤖 Auto-nav » au démarrage de la "
    "session. Tu peux donc émettre la balise <<<NEXT_SLIDE>>> à la fin "
    "de tes réponses quand tu juges la slide acquise (cf. prompt système "
    "§2.9, critères : étudiant a lu, a réagi correctement, point critique "
    "verrouillé, ce n'est pas une réponse à un meta d'arrivée slide).\n\n"
    "Sans ta balise, l'étudiant doit cliquer ➡ manuellement. Avec ta "
    "balise, le front avance auto après 1,5 s. Tu pilotes la cadence."
)


@app.route("/api/auto_advance/remind", methods=["POST"])
def api_auto_advance_remind():
    """Réinjecte le rappel auto-advance dans le _history du client. Utile
    si le tuteur a « oublié » d'émettre la balise en cours de session.
    Ajoute aussi une bulle visible côté front via le transcript."""
    global _state
    with _state_lock:
        if _state is None:
            return jsonify({"error": "pas de session active"}), 409
        _state.client.append_user_message(_AUTO_ADVANCE_REMINDER)
        _state.session_state.set_meta("auto_advance", True)
        # Le rappel n'apparaît PAS dans le transcript visible : c'est un
        # message system-like du backend, pas une intervention de l'étudiant.
        # Le tuteur le voit dans son contexte, c'est tout.
    logger.info("Auto-advance rappelé via /api/auto_advance/remind")
    return jsonify({"ok": True})


@app.route("/api/state/guided_index", methods=["POST"])
def api_state_guided_index():
    """Persiste l'index courant du mode guidé dans session_state.data.

    Appelé par le front à chaque changement de slide pour permettre la
    restauration après Ctrl+F5 à la slide où on était.
    """
    global _state
    body = request.get_json(silent=True) or {}
    idx = body.get("index")
    if not isinstance(idx, int) or idx < 0:
        return jsonify({"error": "index doit être un entier >= 0"}), 400
    with _state_lock:
        if _state is None:
            return jsonify({"error": "pas de session active"}), 409
        _state.session_state.set_meta("guided_index", idx)
    return ("", 204)


@app.route("/api/current_session", methods=["GET"])
def api_current_session():
    """Retourne l'état de la session in-memory active, pour permettre au front
    de se restaurer après un Ctrl+F5 (le state JS est perdu mais le backend
    garde tout). Si aucune session active, retourne ``{"active": False}``.

    Le mode guidé fetch lui-même ses slides via /api/guided/init après
    restauration : pas dupliqué ici.
    """
    global _state
    with _state_lock:
        if _state is None:
            return jsonify({"active": False})
        data = _state.session_state.data
        return jsonify({
            "active": True,
            "session_id": data.get("session_id"),
            "matiere": data.get("matiere"),
            "type": data.get("type"),
            "num": data.get("num"),
            "exo": data.get("exo"),
            "annee": data.get("annee"),
            "mode": data.get("mode", "colle"),
            "colle_format": data.get("colle_format", "mixte"),
            "corrige_anchor": data.get("corrige_anchor", "strict"),
            "engine": data.get("engine"),
            # Phase v15.7.31 : phase de cycle de vie + récap si déjà produit
            "phase": data.get("phase", "active"),
            "recap": data.get("recap"),
            "transcript": _annotate_transcript_with_branches(
                data.get("transcript") or [], data.get("messages") or {},
            ),
            "guided_index": data.get("guided_index", 0),
            "started_at": data.get("started_at"),
            # Phase A.9 : exposés pour que le front puisse construire un
            # `existing` complet et le passer à `showStartConflictModal`
            # quand l'user clique Lancer en pleine session.
            "last_alive": data.get("last_alive"),
            "interrupted": bool(data.get("interrupted")),
            "label": data.get("label"),
            "auto_advance": bool(data.get("auto_advance")),
        })


def _format_reading_state_line(reading_state) -> Optional[str]:
    """Formate une ligne ``[Contexte lecture actuelle : ...]`` injectée
    juste-avant-stream dans le user message. ``reading_state`` est un dict
    ``{kind, label, filename, page, total}`` envoyé par le front quand
    l'étudiant a un document ouvert dans le panneau « Docs ».
    """
    if not isinstance(reading_state, dict):
        return None
    label = (reading_state.get("label") or "").strip()
    if not label:
        return None
    kind = (reading_state.get("kind") or "document").strip().lower()
    kind_fr = {
        "enonce": "énoncé",
        "correction": "corrigé",
        "script": "script imprimable",
    }.get(kind, "document")
    filename = (reading_state.get("filename") or "").strip()
    try:
        page = int(reading_state.get("page") or 0)
        total = int(reading_state.get("total") or 0)
    except (TypeError, ValueError):
        page, total = 0, 0
    if page <= 0 or total <= 0:
        return None
    fname_part = f" ({filename})" if filename else ""
    return (
        f"[Contexte lecture actuelle : l'étudiant consulte la page {page}/{total} "
        f"du {kind_fr} « {label} »{fname_part}]"
    )


# ============================================================ Phase v15.7.4 : bascule format colle
# Slash-command reconnue en début de message : `/oral`, `/photos` (ou
# `/photo`), `/mixte`. Tolérance pour la dictée vocale : un point final
# possible (« slash photos point. ») et casse insensible. Si match, on
# n'envoie PAS au tuteur : on bascule + on injecte un marker système
# `[FORMAT BASCULÉ → ...]` dans l'historique du client (le tuteur le verra
# à sa prochaine réplique, doit acquitter d'un fragment et adapter, cf.
# règle §4.11 du prompt système COMPAGNON).
import re as _re_format

_SLASH_COLLE_FORMAT_RE = _re_format.compile(
    r"^/(oral|photos?|mixte)\.?\s*$",
    _re_format.IGNORECASE,
)
_VALID_COLLE_FORMATS = ("oral", "photos", "mixte")

# Phase A.8.4 : détection d'image markdown dans un user_text (anti-
# hallucination OCR). Patterne sur `![alt](path)`.
_HAS_IMAGE_MARKDOWN_RE = _re_format.compile(r"!\[[^\]]*\]\([^)]+\)")

# Phase v15.7.30 : slash-commands de bascule ancrage corrigé. Trois alias
# acceptés pour `aucun` (le plus user-friendly est `/sans_corrigé` mais on
# tolère aussi `/aucun` pour ceux qui dictent vocalement et ratent l'accent).
# Pattern : `/<mode>` casse insensible, point final toléré (dictée).
_SLASH_CORRIGE_ANCHOR_RE = _re_format.compile(
    r"^/(strict|consultatif|aucun|sans[_ ]corrig[ée])\.?\s*$",
    _re_format.IGNORECASE,
)
_VALID_CORRIGE_ANCHORS = ("strict", "consultatif", "aucun")


def _apply_colle_format_change(st, new_fmt: str) -> str:
    """Persiste le nouveau format colle + injecte le marker pour le tuteur.

    Phase A.8.2 : le **texte** du marker dépend du mode actif :
        - Colle : ``[FORMAT BASCULÉ → ...]`` (cf. règle §4.11 COMPAGNON)
        - Découverte : ``[FORMAT PÉDAGOGIQUE BASCULÉ → ...]`` (cf. règle
          §4.11 DECOUVERTE v1.2, distinct du COMPAGNON, posture différente)
    Le storage technique reste ``session_state.data["colle_format"]`` peu
    importe le mode (rétrocompat).

    Lève ``ValueError`` si ``new_fmt`` n'est pas dans ``_VALID_COLLE_FORMATS``
    (après normalisation : casse insensible, ``/photo`` → ``photos``).
    """
    raw = (new_fmt or "").strip().lower()
    if raw == "photo":
        raw = "photos"  # tolérance singulier → pluriel canonique
    if raw not in _VALID_COLLE_FORMATS:
        raise ValueError(
            f"format invalide : {new_fmt!r} (attendu : {_VALID_COLLE_FORMATS})"
        )
    with st.lock:
        st.session_state.set_meta("colle_format", raw)
        sess_mode = st.session_state.data.get("mode", MODE_COLLE)
        if sess_mode == MODE_DECOUVERTE:
            marker = f"[FORMAT PÉDAGOGIQUE BASCULÉ → {raw}]"
        else:
            marker = f"[FORMAT BASCULÉ → {raw}]"
        st.client.append_user_message(marker)
    return raw


def _apply_corrige_anchor_change(st, new_anchor: str) -> str:
    """Persiste le nouveau mode d'ancrage corrigé + injecte le marker.

    Phase v15.7.30. Pattern jumeau de ``_apply_colle_format_change`` :
    set_meta atomic + ``[ANCRAGE BASCULÉ → ...]`` dans l'historique du
    client (le tuteur le verra à sa prochaine réplique, doit acquitter
    d'un fragment et adapter, cf. règle §4.12 du prompt COMPAGNON).

    Lève ``ValueError`` si ``new_anchor`` n'est pas dans
    ``_VALID_CORRIGE_ANCHORS`` (après normalisation : casse insensible,
    alias ``sans_corrigé``/``sans corrige`` → ``aucun``).

    Note : la bascule ne re-injecte PAS le bloc CORRIGÉ OFFICIEL dans le
    contexte (s'il a été skippé au start avec ``aucun``, il reste absent).
    Le tuteur reste avec le contexte initial, juste avec une nouvelle
    posture pédagogique. Pour avoir le corrigé disponible après bascule
    de ``aucun`` → ``consultatif|strict``, il faut redémarrer la session.
    """
    raw = (new_anchor or "").strip().lower()
    if raw in ("sans_corrigé", "sans_corrige", "sans corrigé", "sans corrige"):
        raw = "aucun"
    if raw not in _VALID_CORRIGE_ANCHORS:
        raise ValueError(
            f"ancrage invalide : {new_anchor!r} (attendu : {_VALID_CORRIGE_ANCHORS})"
        )
    with st.lock:
        st.session_state.set_meta("corrige_anchor", raw)
        st.client.append_user_message(f"[ANCRAGE BASCULÉ → {raw}]")
    return raw


@app.route("/api/set_colle_format", methods=["POST"])
def api_set_colle_format():
    """Bascule le format colle en cours de séance (Phase v15.7.4).

    Body JSON : ``{"format": "oral" | "photos" | "mixte"}``

    Effets :
        - Persiste ``colle_format`` dans la session JSON (atomic write).
        - Injecte un marker ``[FORMAT BASCULÉ → ...]`` dans l'historique
          du ClaudeClient courant : le tuteur le verra à sa prochaine
          réplique et doit acquitter brièvement + adapter (règle §4.11
          du prompt COMPAGNON, pas de discussion).

    Codes :
        200 : OK, retourne ``{"ok": true, "colle_format": "<applied>"}``
        400 : format invalide
        409 : pas de session active
    """
    global _state
    body = request.get_json(silent=True) or {}
    fmt = body.get("format") or ""
    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409
    try:
        applied = _apply_colle_format_change(st, fmt)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    logger.info("colle_format basculé → %s", applied)
    return jsonify({"ok": True, "colle_format": applied})


@app.route("/api/set_corrige_anchor", methods=["POST"])
def api_set_corrige_anchor():
    """Bascule le mode d'ancrage corrigé en cours de séance (Phase v15.7.30).

    Body JSON : ``{"anchor": "strict" | "consultatif" | "aucun"}``

    Effets :
        - Persiste ``corrige_anchor`` dans la session JSON (atomic write).
        - Injecte un marker ``[ANCRAGE BASCULÉ → ...]`` dans l'historique
          du ClaudeClient courant : le tuteur le verra à sa prochaine
          réplique et doit acquitter brièvement + adapter (règle §4.12
          du prompt COMPAGNON, pas de discussion).

    Codes :
        200 : OK, retourne ``{"ok": true, "corrige_anchor": "<applied>"}``
        400 : ancrage invalide
        409 : pas de session active
    """
    global _state
    body = request.get_json(silent=True) or {}
    anchor = body.get("anchor") or ""
    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409
    try:
        applied = _apply_corrige_anchor_change(st, anchor)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    logger.info("corrige_anchor basculé → %s", applied)
    return jsonify({"ok": True, "corrige_anchor": applied})


# ============================================================ Phase A.10.13d
# Renommage photos via OCR Gemini Flash. Idée : remplacer les noms
# illisibles (cropped_1778561703186_v1.jpg) par un nom descriptif
# YYYY-MM-DD_HHMM_<kind>_<slug>_vN.ext. Le slug est extrait des 2-3
# premiers mots significatifs de l'OCR. Skip silencieux si l'OCR est
# de qualité médiocre (kind="?" ou completeness < 50). User : « le
# moteur rename les photos en fonction du contenu qu'il a ocr comme
# ça quand on veut relire les photos ça sera plus facile de s'y
# retrouver ». Permet aussi un portfolio user-facing futur lisible.

_RE_OCR_PARENS = re.compile(r"\([^)]*\)")
_RE_OCR_MD_CRUFT = re.compile(r"[#*`|]+")
_RE_OCR_SLUGIFY = re.compile(r"[^a-z0-9]+")
_OCR_STOPWORDS_FR = {
    "les", "des", "une", "que", "qui", "pour", "avec", "dans", "sur",
    "par", "est", "ont", "ces", "son", "ses", "son", "fait", "tout",
    "plus", "très", "tres", "bien", "mal", "comme", "mais", "donc",
    "etre", "être", "avoir", "cette", "leur", "leurs", "votre", "vos",
    "notre", "nos",
}


def _extract_slug_from_ocr(ocr_md: str, kind: str) -> Optional[str]:
    """Extrait 2-3 mots significatifs de l'OCR pour faire un slug."""
    if not ocr_md:
        return None
    # Retire les markers (vide), (illisible), etc. + markdown bruit
    text = _RE_OCR_PARENS.sub(" ", ocr_md)
    text = _RE_OCR_MD_CRUFT.sub(" ", text)
    # Tokenize en mots, garde les significatifs
    words = [w.strip(".,;:!?()[]{}") for w in text.split()]
    words = [
        w for w in words
        if len(w) >= 3
        and not w.isdigit()
        and w.lower() not in _OCR_STOPWORDS_FR
    ]
    if not words:
        return None
    # Garde max 3 mots, slugifie
    slug = "_".join(w.lower() for w in words[:3])
    slug = _RE_OCR_SLUGIFY.sub("_", slug).strip("_")
    if not slug:
        return None
    return slug[:40]  # cap


def _rename_photo_from_ocr(att: dict, ocr_block: dict) -> Optional[dict]:
    """Renomme physiquement la photo selon l'OCR Gemini Flash.

    Retourne ``{"rel_path", "filename"}`` si rename effectué, ``None``
    sinon (skip silencieux pour OCR médiocre, fichier introuvable,
    OSError). Le rel_path retourné est relatif à la base storage
    (UPLOADS_DIR pour storage="uploads", COURS_ROOT pour "cours").
    """
    kind = (ocr_block.get("kind_detected") or "?").strip().lower()
    completeness = ocr_block.get("completeness_pct") or 0
    try:
        completeness = int(completeness)
    except (TypeError, ValueError):
        completeness = 0
    # Skip si OCR trop médiocre : un slug aléatoire vaut moins que le
    # nom original (qui contient au moins le timestamp d'upload).
    if kind in ("?", "autre", "") or completeness < 50:
        return None
    ocr_md = ocr_block.get("ocr_markdown") or ""
    slug = _extract_slug_from_ocr(ocr_md, kind)
    if not slug:
        return None
    storage = att.get("storage") or "uploads"
    base_root = UPLOADS_DIR if storage == "uploads" else COURS_ROOT
    try:
        old_full = (base_root / att["rel_path"]).resolve()
        old_full.relative_to(base_root.resolve())
    except (ValueError, OSError, KeyError):
        return None
    if not old_full.is_file():
        return None
    ext = old_full.suffix.lstrip(".").lower() or "jpg"
    # Normalise kind : enlève accents / underscores parasites
    safe_kind = re.sub(r"[^a-z0-9_]", "", kind)[:30] or "image"
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    base_name = f"{timestamp}_{safe_kind}_{slug}"
    parent = old_full.parent
    v = 1
    while (parent / f"{base_name}_v{v}.{ext}").exists():
        v += 1
        if v > 99:  # garde-fou
            return None
    new_full = parent / f"{base_name}_v{v}.{ext}"
    try:
        old_full.rename(new_full)
    except OSError as e:
        logger.warning("rename photo OCR a échoué %s → %s : %s",
                       old_full, new_full, e)
        return None
    try:
        new_rel = new_full.relative_to(base_root.resolve()).as_posix()
    except ValueError:
        return None
    logger.info("photo renommée via OCR : %s → %s", att["rel_path"], new_rel)
    return {"rel_path": new_rel, "filename": new_full.name}


def _rebuild_user_text_with_renamed_attachments(text: str, attachments: list) -> str:
    """Phase A.10.13d : si on a renommé des photos juste avant la
    persistance, le `text` peut encore contenir les anciens markdown
    paths. On les remplace par les nouveaux. Best-effort : si on ne
    trouve pas l'ancien nom dans le text, on laisse comme tel.

    Le pattern markdown utilisé est :
        ![<original_name>](<rel ou _uploads/rel>)
    où `rel` peut maintenant pointer sur le nouveau filename. On
    cherche l'ancien (préservé dans l'entry att avant rename) ;
    mais comme on n'a pas conservé l'ancien rel_path, on régénère
    la liste complète des markdowns.
    """
    # Construire la liste de tous les attach_lines re-fraîches
    if not attachments:
        return text
    # Strip les anciennes lignes markdown image+text en cherchant un
    # regex matching toute ligne `![...](...)`. Approche simple :
    # supprimer toutes les lignes image existantes et re-append.
    new_attach_lines = []
    for att in attachments:
        rel = att["rel_path"]
        if att.get("storage") == "uploads":
            rel = f"_uploads/{rel}"
        if att.get("is_image"):
            new_attach_lines.append(
                f"![{att.get('original_name') or att['filename']}]({rel})"
            )
        else:
            new_attach_lines.append(
                f"[Pièce jointe : {att.get('original_name') or att['filename']} "
                f"({rel})]"
            )
    # Supprime toutes les lignes ![...](...) du text
    text_lines = text.split("\n")
    filtered = []
    for ln in text_lines:
        if re.match(r"^!\[[^\]]*\]\([^)]+\)\s*$", ln):
            continue
        if re.match(r"^\[Pièce jointe :[^\]]*\]\s*$", ln):
            continue
        filtered.append(ln)
    text = "\n".join(filtered).rstrip()
    if text and new_attach_lines:
        text = text + "\n\n" + "\n".join(new_attach_lines)
    elif new_attach_lines:
        text = "\n".join(new_attach_lines)
    return text


@app.route("/api/send_message", methods=["POST"])
def api_send_message():
    """Stocke le message user (et attache les pending_attachments). Le
    streaming démarre au prochain GET /api/stream_response.

    Les pièces jointes en attente sont injectées dans le texte avant envoi :
    - Images → markdown ``![nom](path)`` (rendu inline + vu par le tuteur multimodal)
    - Autres (PDF, Excel, …) → mention ``[Pièce jointe : nom (path)]``
      (le tuteur en mode guidé peut Read le fichier).

    Si le body contient ``reading_state`` (cf. panneau « Corrigés & script »
    côté front), une ligne ``[Contexte lecture actuelle : ...]`` est
    préfixée au texte : injection juste-avant-stream pour éviter la
    pollution de l'historique sur chaque navigation de page.

    Phase v15.7.4 : si ``text`` est exactement ``/oral``, ``/photos`` (ou
    ``/photo``), ou ``/mixte`` (casse insensible, point final toléré pour
    la dictée vocale), la slash-command est interceptée → bascule
    ``colle_format`` + marker système, **sans envoyer au tuteur**. Réponse
    202 ``{"ok": true, "slash_command": true, "colle_format": "<new>"}``.

    La file d'attente est vidée après injection. Si aucune photo n'a été
    posée, le message est envoyé tel quel.
    """
    global _state
    body = request.get_json(silent=True) or {}
    text = body.get("text") or ""
    # Phase v15.7.8 : autorise un envoi sans texte si au moins une pièce
    # jointe est en attente (cas « j'ai juste envie d'envoyer une photo »
    # sans commenter, le tuteur la commentera lui-même via [PHOTO_RECEIVED]).
    # Sinon, refuse comme avant.
    if not text.strip():
        with _state_lock:
            has_pending = bool(_state and _state.pending_attachments)
        if not has_pending:
            return jsonify({"error": "text vide"}), 400
    # Phase v15.7.4 : détection slash-command bascule format colle.
    slash_match = _SLASH_COLLE_FORMAT_RE.match(text.strip())
    if slash_match:
        fmt = slash_match.group(1).lower()
        with _state_lock:
            st = _state
        if st is None:
            return jsonify({"error": "pas de session active"}), 409
        try:
            applied = _apply_colle_format_change(st, fmt)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        logger.info("colle_format basculé via slash-command → %s", applied)
        return jsonify({
            "ok": True,
            "slash_command": True,
            "colle_format": applied,
        }), 202

    # Phase v15.7.30 : détection slash-command bascule ancrage corrigé.
    # `/strict`, `/consultatif`, `/aucun`, `/sans_corrigé` (+ tolérance
    # accent absent et espace interne dans `sans corrigé`).
    anchor_match = _SLASH_CORRIGE_ANCHOR_RE.match(text.strip())
    if anchor_match:
        raw = anchor_match.group(1).lower().replace(" ", "_")
        with _state_lock:
            st = _state
        if st is None:
            return jsonify({"error": "pas de session active"}), 409
        try:
            applied = _apply_corrige_anchor_change(st, raw)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        logger.info("corrige_anchor basculé via slash-command → %s", applied)
        return jsonify({
            "ok": True,
            "slash_command": True,
            "corrige_anchor": applied,
        }), 202
    reading_line = _format_reading_state_line(body.get("reading_state"))
    with _state_lock:
        if _state is None:
            return jsonify({"error": "pas de session active"}), 409
        attachments = list(_state.pending_attachments)
        _state.pending_attachments = []
        # Phase v15.7.20 : colle_format / mode du state pour décider si on
        # lance l'OCR Gemini Flash en pré-traitement (relâché ensuite hors
        # du lock pour que l'appel LLM ne bloque pas les autres handlers).
        sess_mode = _state.session_state.data.get("mode", MODE_COLLE)
        sess_colle_format = _state.session_state.data.get("colle_format", "mixte")

    # Phase v15.7.20 : OCR pré-traitée Gemini Flash sur les images.
    # Conditions : mode colle OU découverte ET colle_format ∈ {photos, mixte}
    # (pas `oral` puisque le user a explicitement opté pour l'oral pur).
    # Phase A.8.2 : étendu au mode découverte (§1.6ter du prompt
    # DECOUVERTE) : en photos et mixte, l'OCR Flash 2.5 sert au tuteur de
    # double-check anti-hallucination sur les photos de cahier de l'étudiant
    # (notes recopiées de définitions / syntaxes / exemples).
    # Hint : on prend la dernière réplique du tuteur si dispo (contexte
    # de ce qu'il attendait, oriente le `kind_detected`).
    image_attachments = [a for a in attachments if a.get("is_image")]
    ocr_blocks = []  # à renvoyer au front pour affichage collapsible
    if (image_attachments
            and sess_mode in (MODE_COLLE, MODE_DECOUVERTE)
            and sess_colle_format in ("photos", "mixte")):
        hint = _get_last_tutor_text_for_ocr_hint()
        for att in image_attachments:
            ocr = _ocr_attachment_internal(att, hint=hint)
            if ocr is not None:
                ocr_blocks.append({"attachment_id": att.get("id"), **ocr})

    with _state_lock:
        if _state is None:
            return jsonify({"error": "pas de session active"}), 409
        if attachments:
            attach_lines = []
            for att in attachments:
                # Phase A.10.2 : préfixe `_uploads/` pour les attachments
                # stockés sous UPLOADS_DIR (route vers /api/upload_file côté
                # renderMarkdown JS). Legacy storage="cours" reste sans
                # préfixe (route vers /api/cours_file).
                rel = att["rel_path"]
                if att.get("storage") == "uploads":
                    rel = f"_uploads/{rel}"
                if att.get("is_image"):
                    attach_lines.append(
                        f"![{att.get('original_name') or att['filename']}]({rel})"
                    )
                else:
                    attach_lines.append(
                        f"[Pièce jointe : {att.get('original_name') or att['filename']} "
                        f"({rel})]"
                    )
            # Phase v15.7.8 : pas de séparateur "\n\n" si text est vide
            # (cas envoi photo seule), sinon on aurait un préfixe inutile
            # de blancs avant la liste des pièces jointes.
            sep = "\n\n" if text.strip() else ""
            text = text.rstrip() + sep + "\n".join(attach_lines)
        # Phase v15.7.20 : injecte le bloc OCR Gemini APRÈS les images
        # markdown. Le tuteur voit l'image en multimodal natif (Anthropic/
        # Gemini) ou via Read (CLI), ET la pré-OCR Gemini Flash. Il
        # compare et signale toute divergence (cf. §1.6 v0.5).
        if ocr_blocks:
            # Phase A.10.13d : renommer les photos via OCR juste avant
            # de construire le markdown final. Si le rename réussit, le
            # markdown et session_photos utilisent les nouveaux noms.
            # Best-effort : si rename échoue, on garde le nom original.
            for blk in ocr_blocks:
                att_id = blk.get("attachment_id")
                if not att_id:
                    continue
                att = next(
                    (a for a in attachments if a.get("id") == att_id),
                    None,
                )
                if att is None:
                    continue
                new = _rename_photo_from_ocr(att, blk)
                if new:
                    att["rel_path"] = new["rel_path"]
                    att["filename"] = new["filename"]
                    # Rebuild attach_lines pour cette photo (le markdown
                    # initial pointait sur l'ancien nom).
                    old_md_prefix = f"![{att.get('original_name') or att['filename']}]"
                    # On reconstruira plus loin dans le persist
                    # session_photos. Pour le markdown courant, on a
                    # déjà concat ; il faut le mettre à jour.
            # Reconstruit le markdown final avec les nouveaux rel_paths
            # (au cas où on aurait renommé). Le `text` actuel peut
            # contenir les anciens chemins, on remplace.
            text = _rebuild_user_text_with_renamed_attachments(
                text, attachments,
            )
            ocr_text_parts = [
                "\n\n[OCR pré-traitée par Gemini Flash 2.5 : "
                "vérifie qu'elle correspond à ta lecture multimodale, "
                "sinon dis-le et signale la divergence à l'étudiant]:"
            ]
            for blk in ocr_blocks:
                ocr_text_parts.append(
                    f"\n\n--- OCR de l'image ---\n"
                    f"Type détecté : {blk.get('kind_detected', '?')}\n"
                    f"Complétude estimée : {blk.get('completeness_pct', '?')}%\n"
                    + (f"Warnings : {', '.join(blk.get('warnings') or [])}\n"
                       if blk.get('warnings') else "")
                    + f"\n{blk.get('ocr_markdown', '')}"
                )
            text = text + "".join(ocr_text_parts)
        # Phase v15.7.30.1 : reading_line stockée séparément (PAS concaténée
        # au pending_user_text). Sinon elle pollue le transcript persisté et
        # apparaît brute « [Contexte lecture actuelle : ...] » au rerender
        # (bulle student illisible). Le `_run_claude_streaming` la concatène
        # juste avant `client.append_user_message`, mais
        # `session_state.append_exchange("student", ...)` reçoit `user_text`
        # sans préfixe → transcript propre.
        _state.pending_user_text = text
        _state.pending_reading_line = reading_line
        # Phase A.9.1 : galerie photos : on persiste chaque image attachée
        # à ce send_message dans `session_photos` (champ additif, schema
        # non bumpé). Survit à la reprise et alimente l'onglet 📸 Photos
        # du sidebar. Le fichier disque reste l'unique source de vérité
        # (rel_path sous COURS_ROOT), on n'archive aucun binaire ici.
        image_attachments_for_gallery = [a for a in attachments if a.get("is_image")]
        if image_attachments_for_gallery:
            from utils import now_iso as _now_iso_photos
            existing_photos = list(
                _state.session_state.data.get("session_photos") or []
            )
            for att in image_attachments_for_gallery:
                existing_photos.append({
                    "id": att.get("id") or f"photo_{uuid.uuid4().hex[:10]}",
                    "rel_path": att.get("rel_path"),
                    "filename": att.get("filename"),
                    "original_name": att.get("original_name"),
                    "mime": att.get("mime") or "",
                    "size_bytes": att.get("size_bytes") or 0,
                    "sent_at": _now_iso_photos(),
                    # Phase A.10.2 : propage l'origine du stockage pour
                    # que la galerie sache routes vers /api/upload_file
                    # (uploads) ou /api/cours_file (cours legacy).
                    "storage": att.get("storage") or "uploads",
                })
            _state.session_state.set_meta("session_photos", existing_photos)
    return jsonify({
        "ok": True,
        "attachments_count": len(attachments),
        "ocr_blocks": ocr_blocks,  # Phase v15.7.20 : front affiche en collapsible
    }), 202


def _get_last_tutor_text_for_ocr_hint():
    """Phase v15.7.20 : récupère la dernière réplique du tuteur pour
    l'utiliser comme hint d'orientation au prompt OCR (« le tuteur
    attendait une table de vérité 8 lignes »). Retourne "" si aucun.

    Tronqué à 500 chars (cap _hint suffisant côté OCR_PHOTO_PROMPT).
    """
    global _state
    with _state_lock:
        if _state is None:
            return ""
        ts = _state.session_state.data.get("transcript") or []
    for msg in reversed(ts):
        if msg.get("role") == "claude":
            return (msg.get("text") or "")[:500]
    return ""


def _ocr_attachment_internal(att: dict, hint: str = ""):
    """Phase v15.7.20 : appelle Gemini Flash en interne pour OCR d'une
    image attachée. Réutilisable depuis send_message (auto) ou ocr_photo
    (explicit). Retourne le payload dict ou None si erreur.

    Best-effort : aucune exception remontée (sinon ça bloquerait l'envoi
    du message au tuteur, qui peut quand même bosser sur l'image en
    multimodal natif sans le pré-OCR).

    Phase A.10.13.bug3 (2026-05-14) : résolution disque via storage. Avant,
    le user_msg passait `rel_path` brut + `cours_root=COURS_ROOT` à
    `_run_isolated_lookup`, ce qui résolvait sous COURS_ROOT alors que le
    fichier est sous UPLOADS_DIR pour storage="uploads".
    `_extract_inline_images` retournait `[image introuvable: photo]` et
    Gemini Flash hallucinait l'OCR sur une image vide. On passe désormais
    le path absolu pour que `path.is_absolute()` court-circuite la
    résolution cours_root et que le fichier soit effectivement chargé.
    """
    rel_path = att.get("rel_path")
    if not rel_path:
        return None
    storage = att.get("storage") or "uploads"
    base_root = UPLOADS_DIR if storage == "uploads" else COURS_ROOT
    try:
        abs_path = (base_root / rel_path).resolve()
        abs_path.relative_to(base_root.resolve())  # garde-fou traversal
    except (ValueError, OSError):
        logger.warning("OCR auto : rel_path hors %s : %s", storage, rel_path)
        return None
    if not abs_path.is_file():
        logger.warning("OCR auto : fichier introuvable : %s", abs_path)
        return None
    try:
        sys_prompt = OCR_PHOTO_PROMPT.format(
            hint=(hint or "(aucun hint fourni)")[:500],
        )
        # Phase A.10.13.bug3 : path absolu pour court-circuiter la résolution
        # cours_root dans `_extract_inline_images`.
        user_msg = f"Voici la photo à analyser :\n\n![photo]({abs_path.as_posix()})"
        payload, _, err = _run_isolated_lookup(
            sys_prompt, user_msg,
            "<<<OCR>>>", "<<<END>>>",
            cours_root=COURS_ROOT,
            mode_override=MODE_COLLE,
            engine_override="gemini_api",
            model_override="gemini-2.5-flash",
            enable_web_search=False,
        )
        if err is not None:
            logger.warning("OCR auto échoué pour %s : err response", rel_path)
            return None
        ocr_md = (payload.get("ocr_markdown") or "").strip()
        if not ocr_md:
            return None
        warnings_list = payload.get("warnings") or []
        if not isinstance(warnings_list, list):
            warnings_list = []
        return {
            "ocr_markdown": ocr_md,
            "kind_detected": (payload.get("kind_detected") or "autre").strip(),
            "completeness_pct": (
                int(payload["completeness_pct"])
                if isinstance(payload.get("completeness_pct"), (int, float))
                else None
            ),
            "warnings": [
                str(w).strip() for w in warnings_list[:10]
                if isinstance(w, str) and w.strip()
            ],
            "model": "gemini-2.5-flash",
        }
    except Exception as e:  # noqa: BLE001 : best-effort, ne pas bloquer l'envoi
        logger.warning("OCR auto exception pour %s : %s", rel_path, e)
        return None


@app.route("/api/stream_response", methods=["GET"])
def api_stream_response():
    """SSE qui streame la réponse Claude au pending message user."""
    global _state
    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409

    with st.lock:
        # Cas 1 : 1ʳᵉ stream juste après start_session. Le contexte initial
        # a été pushé dans `client.append_user_message(initial)` côté
        # `/api/start_session`. On stream directement la réponse de Claude
        # à ce contexte sans append d'un nouveau user message.
        # Cas 2 : streams ultérieures déclenchées par /api/send_message →
        # `pending_user_text` contient le message texte (ou la transcription
        # micro). On l'append puis on stream.
        # Cas 3 (Phase A.7.2 v7.3) : retry après bascule à chaud. Le user
        # message est déjà dans `client._history` (transféré depuis l'ancien
        # client). On stream directement, sans rien re-toucher.
        if st.retry_pending:
            st.retry_pending = False
        elif st.initial_stream_pending and st.pending_user_text is None:
            st.initial_stream_pending = False  # consume one-shot
        elif st.pending_user_text is not None:
            user_text = st.pending_user_text
            reading_line = st.pending_reading_line
            st.pending_user_text = None
            st.pending_reading_line = None
            st.initial_stream_pending = False
            # Phase A.8.4 : détection présence d'image dans le user_text.
            # Si pas d'image, on injecte [AUCUNE IMAGE DANS CE MESSAGE] comme
            # marker explicite anti-hallucination du bloc OCR `📸 Ce que je
            # lis dans votre photo :`. Bug observé 2026-05-12 session PSI
            # TP_Shannon : user oublie d'attacher la photo, tuteur halluciné
            # une transcription complète avec faux OCR.
            has_image = bool(_HAS_IMAGE_MARKDOWN_RE.search(user_text))
            # Stocke pour utilisation au post-stream (filtre output_filters)
            st.last_user_had_image = has_image
            # Phase v15.7.30.1 : split LLM/transcript. Le tuteur voit le
            # contexte de lecture en préfixe ; le transcript persisté n'a
            # que le message utilisateur (rerender propre).
            no_image_marker = "" if has_image else "[AUCUNE IMAGE DANS CE MESSAGE]\n\n"
            # Phase A.10 : préfixe `[CONSIGNES ÉPINGLÉES PAR L'ÉTUDIANT]` ajouté
            # au llm_text mais PAS au user_text persisté. Les consignes sont
            # re-injectées à chaque tour pour rester saillantes dans le contexte
            # du tuteur (pattern de RAG-like prepend, le LLM tolère la
            # redondance). Le transcript reste propre côté replay.
            stickies_block = _format_stickies_block_for_llm(st)
            llm_text = (
                f"{stickies_block}{reading_line}\n\n{no_image_marker}{user_text}"
                if reading_line
                else f"{stickies_block}{no_image_marker}{user_text}"
            )
            st.client.append_user_message(llm_text)
            st.session_state.append_exchange("student", user_text)
        else:
            return jsonify({"error": "aucun message en attente"}), 409
        # Vider l'éventuelle queue résiduelle
        while not st.event_queue.empty():
            try:
                st.event_queue.get_nowait()
            except queue.Empty:
                break
        # Phase v15.7.21 : reset le flag cancel à chaque démarrage de
        # stream (sinon une annulation précédente bloquerait le suivant).
        st.cancel_requested = False
        st.streaming_thread = threading.Thread(
            target=_run_claude_streaming,
            args=(st,),
            daemon=True,
            name="claude-stream",
        )
        st.streaming_thread.start()

    return Response(
        stream_with_context(_sse_generator(st)),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.route("/api/cancel_stream", methods=["POST"])
def api_cancel_stream():
    """Annule le stream Compagnon en cours (Phase v15.7.21).

    Body JSON :
        {"action": "resume" | "delete_last_user"}

    - ``resume`` : annule le stream LLM en cours (le sub-process / API
      call peut continuer à tourner en background, on consume les tokens
      quoi qu'il arrive (c'est le compromis pour la simplicité). Le
      message user reste dans le transcript et l'historique. L'utilisateur
      peut relancer un nouveau stream avec un autre message ou
      reformuler.
    - ``delete_last_user`` : pareil + supprime aussi le dernier message
      user (du `client._history` ET du `session_state.transcript` via
      `_remove_last_message_pair`). Utile quand l'utilisateur veut
      « comme si je n'avais rien envoyé ».

    Codes :
        200 : OK, retourne {ok: true, action_applied, deleted_msg_id?}
        400 : action invalide
        409 : pas de session active OU pas de stream en cours
    """
    global _state
    body = request.get_json(silent=True) or {}
    action = (body.get("action") or "resume").strip()
    if action not in ("resume", "delete_last_user"):
        return jsonify({
            "error": "action invalide",
            "allowed": ["resume", "delete_last_user"],
        }), 400

    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409

    deleted_msg_id = None
    with st.lock:
        # Set le flag : le _sse_generator détectera et coupera
        # gracieusement à son prochain check (interval ~poll côté queue).
        st.cancel_requested = True

        if action == "delete_last_user":
            # Retire le dernier user msg du _history client (in-memory)
            # ET du transcript session_state (atomic write).
            try:
                hist = st.client._history
                # Trouve le dernier message role=user et le pop
                for i in range(len(hist) - 1, -1, -1):
                    if hist[i].get("role") == "user":
                        del hist[i]
                        break
            except Exception as e:  # noqa: BLE001
                logger.warning("cancel_stream delete history user a leve : %s", e)
            # Retire la dernière entry student du transcript persisté
            try:
                deleted_msg_id = _remove_last_student_message(st.session_state)
            except Exception as e:  # noqa: BLE001
                logger.warning("cancel_stream delete transcript student a leve : %s", e)

    logger.info(
        "Stream annulé (action=%s, deleted_msg_id=%s)", action, deleted_msg_id,
    )
    return jsonify({
        "ok": True,
        "action_applied": action,
        "deleted_msg_id": deleted_msg_id,
    })


def _remove_last_student_message(session_state):
    """Phase v15.7.21 : supprime la dernière entry role=student du
    transcript courant (et du chemin de branche actif), atomic write.

    Retourne l'id du message supprimé, ou None si aucun student trouvé.
    Utilisé par /api/cancel_stream{action: delete_last_user}.

    Note : on ne supprime pas l'objet de `messages` (l'arborescence
    branches conserve l'historique de toutes les modifs), juste on retire
    du `current_branch_path` actif. Le re-render UI reflètera l'état clean.
    """
    data = session_state.data
    branch_path = data.get("current_branch_path") or []
    messages = data.get("messages") or {}
    target_id = None
    for i in range(len(branch_path) - 1, -1, -1):
        mid = branch_path[i]
        msg = messages.get(mid)
        if msg and msg.get("role") == "student":
            target_id = mid
            # Tronque le path à partir de cet index (retire aussi tout
            # ce qui suit, qui serait des réponses claude orphelines
            # potentielles, mais en pratique le stream a été annulé
            # avant donc il n'y a rien après).
            new_path = branch_path[:i]
            session_state.set_meta("current_branch_path", new_path)
            # Re-dérive le transcript depuis le nouveau path
            new_transcript = []
            for pid in new_path:
                m = messages.get(pid)
                if m:
                    new_transcript.append(dict(m))
            session_state.set_meta("transcript", new_transcript)
            break
    return target_id


# ============================================================ /api/saved_selections : Phase v15.7.23
# Sélections de texte sauvegardées par l'utilisateur depuis les bulles
# Compagnon ou student, via popup contextuel (bouton 💾 Sauvegarder).
# Affichées dans l'onglet sidebar 🔖 Notes. Persistance dans le JSON
# de session → conservées en reprise. Schéma additif (pas de bump).

import uuid as _uuid_sel


@app.route("/api/saved_selections", methods=["GET"])
def api_saved_selections_list():
    """Liste les sélections sauvegardées de la session active."""
    global _state
    with _state_lock:
        if _state is None:
            return jsonify({"selections": [], "active": False})
        sels = list(_state.session_state.data.get("saved_selections") or [])
    return jsonify({"selections": sels, "active": True})


@app.route("/api/saved_selections", methods=["POST"])
def api_saved_selections_create():
    """Sauvegarde une sélection de texte.

    Body JSON : ``{text, message_id?, role?}``
    - ``text`` (obligatoire, ≤ 5000 chars) : la phrase / paragraphe sélectionné
    - ``message_id`` (optionnel) : id de la bulle source pour le scroll-back
    - ``role`` (optionnel) : ``"claude"`` | ``"student"`` (pour l'affichage)

    Réponse 200 : le selection dict créé `{id, text, message_id, role, captured_at}`.
    Codes : 400 (text vide / trop long), 409 (pas de session active).
    """
    global _state
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text vide"}), 400
    if len(text) > 5000:
        return jsonify({
            "error": "text trop long",
            "max_chars": 5000,
            "got_chars": len(text),
        }), 400
    message_id = (body.get("message_id") or "").strip() or None
    role = (body.get("role") or "").strip()
    if role not in ("claude", "student"):
        role = "claude"  # défaut prudent
    # Phase v15.7.26 : raw_text optional : source markdown brut de la
    # bulle source (avant rendu KaTeX/Markdown). Permet au panneau Notes
    # d'afficher le source propre quand la sélection visuelle contient
    # du LaTeX rendu (chars Unicode mathématiques inutilisables).
    raw_text = (body.get("raw_text") or "").strip() or None
    if raw_text and len(raw_text) > 10000:
        raw_text = raw_text[:10000]  # cap silencieux

    from utils import now_iso as _now_iso
    sel = {
        "id": f"sel_{_uuid_sel.uuid4().hex[:12]}",
        "text": text,
        "raw_text": raw_text,  # Phase v15.7.26
        "message_id": message_id,
        "role": role,
        "captured_at": _now_iso(),
    }
    with _state_lock:
        if _state is None:
            return jsonify({"error": "pas de session active"}), 409
        existing = list(_state.session_state.data.get("saved_selections") or [])
        existing.append(sel)
        _state.session_state.set_meta("saved_selections", existing)
    logger.info("Selection sauvegardée : %s (%d chars, role=%s)",
                sel["id"], len(text), role)
    return jsonify(sel)


@app.route("/api/saved_selections/<sel_id>", methods=["DELETE"])
def api_saved_selections_delete(sel_id):
    """Supprime une sélection sauvegardée par id."""
    global _state
    with _state_lock:
        if _state is None:
            return jsonify({"error": "pas de session active"}), 409
        existing = list(_state.session_state.data.get("saved_selections") or [])
        before = len(existing)
        new_list = [s for s in existing if s.get("id") != sel_id]
        if len(new_list) == before:
            return jsonify({"error": "selection introuvable"}), 404
        _state.session_state.set_meta("saved_selections", new_list)
    logger.info("Selection supprimée : %s", sel_id)
    return ("", 204)


# ============================================================ /api/session_photos : Phase A.9.1
# Galerie photos : liste les images envoyées au tuteur pendant la session
# active (auto-archivées au moment du send_message). Pendant que la conv
# s'allonge, l'étudiant peut revenir voir ce qu'il a transmis via l'onglet
# 📸 Photos du sidebar. DELETE retire l'entrée de la liste sans toucher
# au fichier disque (cohérent avec pending_attachments DELETE).


# Phase A.10.1 : backfill one-shot des photos pour les sessions
# antérieures à A.9.1 (qui n'ont pas le champ `session_photos`). On
# scanne le transcript student pour extraire les markdown `![alt](path)`
# pointant vers des images sous COURS_ROOT, on vérifie l'existence
# disque, et on reconstitue la galerie. Idempotent via le marker
# `session_photos_backfilled` (pose même quand la liste est vide pour
# éviter de re-importer ce que l'user vient de supprimer manuellement).

_BACKFILL_IMAGE_MD_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_BACKFILL_MIME_BY_EXT = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "webp": "image/webp", "gif": "image/gif", "svg": "image/svg+xml",
    "bmp": "image/bmp", "tiff": "image/tiff", "heic": "image/heic",
}


def _maybe_backfill_session_photos(st) -> None:
    """Backfill une fois `session_photos` depuis le transcript si la
    session est antérieure à A.9.1 (champ absent). Pose un marker
    `session_photos_backfilled=True` après la 1ʳᵉ exécution, même si la
    liste finale est vide (un transcript sans photo, ou des fichiers
    supprimés du disque, ne doivent pas re-déclencher le scan à chaque GET).
    """
    data = st.session_state.data
    if data.get("session_photos_backfilled"):
        return
    existing = data.get("session_photos")
    if existing:
        # Liste déjà populée (sessions A.9.1+ ou backfill antérieur
        # interrompu) → on pose juste le marker.
        st.session_state.set_meta("session_photos_backfilled", True)
        return
    transcript = data.get("transcript") or []
    photos: list[dict] = []
    seen_paths: set[str] = set()
    for entry in transcript:
        if entry.get("role") != "student":
            continue
        text = entry.get("text") or ""
        for m in _BACKFILL_IMAGE_MD_RE.finditer(text):
            alt = m.group(1).strip()
            raw_path = m.group(2).strip().replace("\\", "/")
            # Skip URLs externes
            if raw_path.startswith(("http://", "https://")):
                continue
            # Skip /api/cours_file?path=... (parfois inséré au rerender)
            if raw_path.startswith("/api/"):
                continue
            # Skip chemins absolus
            if raw_path.startswith("/") or (len(raw_path) >= 2 and raw_path[1] == ":"):
                continue
            # Phase A.10.3 : détecte le storage selon le préfixe `_uploads/` :
            #   "_uploads/sess/photos/p.jpg" → storage=uploads, sous UPLOADS_DIR
            #   "AN1/TD/TD5/photos/p.jpg"    → storage=cours,   sous COURS_ROOT
            if raw_path.startswith("_uploads/"):
                storage = "uploads"
                rel_path = raw_path[len("_uploads/"):]
                base_root = UPLOADS_DIR
            else:
                storage = "cours"
                rel_path = raw_path
                base_root = COURS_ROOT
            if rel_path in seen_paths:
                continue
            seen_paths.add(rel_path)
            try:
                full_path = (base_root / rel_path).resolve()
                full_path.relative_to(base_root.resolve())
            except (ValueError, OSError):
                continue  # hors base ou path invalide
            if not full_path.is_file():
                continue  # fichier supprimé / déplacé entretemps
            ext = full_path.suffix.lower().lstrip(".")
            if ext not in _IMAGE_EXTS:
                continue
            try:
                size_bytes = full_path.stat().st_size
            except OSError:
                continue
            photos.append({
                "id": f"photo_{uuid.uuid4().hex[:10]}",
                "rel_path": rel_path,
                "filename": full_path.name,
                "original_name": alt or full_path.name,
                "mime": _BACKFILL_MIME_BY_EXT.get(ext, "image/jpeg"),
                "size_bytes": size_bytes,
                "sent_at": entry.get("at") or "",
                "backfilled": True,
                "storage": storage,
            })
    st.session_state.set_meta("session_photos", photos)
    st.session_state.set_meta("session_photos_backfilled", True)
    if photos:
        logger.info(
            "Backfill galerie photos : %d photo(s) reconstituée(s) depuis le transcript",
            len(photos),
        )


@app.route("/api/session_photos", methods=["GET"])
def api_session_photos_list():
    """Liste les photos archivées de la session active.

    Réponse : `{"photos": [...], "active": bool}`. Chaque photo expose
    `id`, `rel_path` (servi via /api/cours_file), `filename`,
    `original_name`, `mime`, `size_bytes`, `sent_at`.

    Phase A.10.1 : backfill lazy au 1ᵉʳ GET pour les sessions antérieures
    à A.9.1 : scanne le transcript pour reconstituer les photos depuis
    leur markdown `![alt](path)`. Idempotent via marker.
    """
    global _state
    with _state_lock:
        if _state is None:
            return jsonify({"photos": [], "active": False})
        st = _state
    # Backfill une fois si applicable (manipule le state via set_meta, qui
    # a son propre lock, on relâche _state_lock pour éviter une réentrance).
    try:
        _maybe_backfill_session_photos(st)
    except Exception:  # noqa: BLE001 : best-effort, jamais bloquant
        logger.exception("backfill session_photos a leve, GET continue")
    with _state_lock:
        if _state is None:
            return jsonify({"photos": [], "active": False})
        photos = list(_state.session_state.data.get("session_photos") or [])
    return jsonify({"photos": photos, "active": True})


@app.route("/api/session_photos/<photo_id>", methods=["DELETE"])
def api_session_photos_delete(photo_id: str):
    """Retire une photo de la galerie (le fichier disque reste sous
    COURS/.../photos/, on ne fait que dépiler l'entrée de tracking)."""
    global _state
    with _state_lock:
        if _state is None:
            return jsonify({"error": "pas de session active"}), 409
        existing = list(_state.session_state.data.get("session_photos") or [])
        before = len(existing)
        new_list = [p for p in existing if p.get("id") != photo_id]
        if len(new_list) == before:
            return jsonify({"error": "photo introuvable"}), 404
        _state.session_state.set_meta("session_photos", new_list)
    logger.info("Photo retirée de la galerie : %s", photo_id)
    return ("", 204)


# ============================================================ /api/stickies : Phase A.10
# Mémoire persistante de séance : consignes épinglées que le tuteur doit
# respecter en priorité. Deux origines :
#   - kind="user"  : l'étudiant pin manuellement (chip 📌 sur une bulle student).
#   - kind="tutor" : le tuteur émet la balise <<<REMEMBER>>>{"text": "..."}<<<END>>>
#                    sur demande explicite (« retiens que… »).
#
# Persisté dans `session_state.data["stickies"]` (additif, pas de bump).
# Injecté à chaque tour par `prompt_builder._build_stickies_block` dans le
# contexte LLM, JAMAIS dans le transcript student (sinon le LLM verrait
# les consignes 2× : prompt + replay). À la reprise, replay propre.
#
# Le bloc LLM a la forme :
#   [CONSIGNES ÉPINGLÉES PAR L'ÉTUDIANT, à respecter en priorité]
#   - texte de la sticky 1
#   - texte de la sticky 2
#   [/CONSIGNES ÉPINGLÉES]
# Seules les stickies `enabled=True` y figurent.

_STICKY_TEXT_MAX_CHARS = 200


def _format_stickies_block_for_llm(st) -> str:
    """Phase A.10 : formate le bloc `[CONSIGNES ÉPINGLÉES…]` injecté en
    préfixe à chaque user message dans le contexte LLM.

    Lit `session_state.data["stickies"]` (filtre enabled=True), retourne
    un bloc terminé par `\n\n` (ou `""` si pas de sticky active).
    Le bloc N'EST PAS persisté dans le transcript student (canal séparé,
    cf. Phase v15.7.30.1).
    """
    try:
        stickies = list(st.session_state.data.get("stickies") or [])
    except Exception:  # noqa: BLE001 : best-effort, jamais bloquant
        return ""
    enabled = [s for s in stickies
               if s.get("enabled", True) and s.get("text", "").strip()]
    if not enabled:
        return ""
    lines = ["[CONSIGNES ÉPINGLÉES PAR L'ÉTUDIANT, à respecter en priorité]"]
    for s in enabled:
        kind_marker = "🤖" if s.get("kind") == "tutor" else "📌"
        lines.append(f"- {kind_marker} {s['text']}")
    lines.append("[/CONSIGNES ÉPINGLÉES]")
    lines.append("")  # ligne vide avant le contenu suivant
    return "\n".join(lines) + "\n"


def _normalize_sticky_text(raw) -> str:
    """Strip + collapse whitespace internes pour stocker un texte propre."""
    if not isinstance(raw, str):
        return ""
    return " ".join(raw.split())


@app.route("/api/stickies", methods=["GET"])
def api_stickies_list():
    """Liste les consignes épinglées de la session active.

    Réponse : `{stickies: [...], active: bool}`. Chaque sticky expose
    `id`, `kind` (user|tutor), `text`, `source_message_id`, `created_at`,
    `edited_at`, `enabled`.
    """
    global _state
    with _state_lock:
        if _state is None:
            return jsonify({"stickies": [], "active": False})
        stickies = list(_state.session_state.data.get("stickies") or [])
    return jsonify({"stickies": stickies, "active": True})


@app.route("/api/stickies", methods=["POST"])
def api_stickies_create():
    """Crée une nouvelle sticky.

    Body JSON : `{text, source_message_id?, kind?}`
    - `text` (requis, ≤ 200 chars après normalisation)
    - `source_message_id` (optionnel) : id de la bulle source pour le scroll-back
    - `kind` (optionnel) : `"user"` (défaut) | `"tutor"`
    """
    global _state
    body = request.get_json(silent=True) or {}
    text = _normalize_sticky_text(body.get("text"))
    if not text:
        return jsonify({"error": "text vide"}), 400
    if len(text) > _STICKY_TEXT_MAX_CHARS:
        return jsonify({
            "error": "text trop long",
            "max_chars": _STICKY_TEXT_MAX_CHARS,
            "got_chars": len(text),
        }), 400
    kind = (body.get("kind") or "user").strip().lower()
    if kind not in ("user", "tutor"):
        kind = "user"
    source_message_id = (body.get("source_message_id") or "").strip() or None
    from utils import now_iso as _now_iso_st
    sticky = {
        "id": f"sticky_{uuid.uuid4().hex[:12]}",
        "kind": kind,
        "text": text,
        "source_message_id": source_message_id,
        "created_at": _now_iso_st(),
        "edited_at": None,
        "enabled": True,
    }
    with _state_lock:
        if _state is None:
            return jsonify({"error": "pas de session active"}), 409
        existing = list(_state.session_state.data.get("stickies") or [])
        existing.append(sticky)
        _state.session_state.set_meta("stickies", existing)
    logger.info("Sticky ajoutée : %s (kind=%s, %d chars)",
                sticky["id"], kind, len(text))
    return jsonify(sticky)


@app.route("/api/stickies/<sticky_id>", methods=["PATCH"])
def api_stickies_patch(sticky_id: str):
    """Édite une sticky existante. Body JSON `{text?, enabled?}`.

    - `text` (optionnel) : nouveau texte (≤ 200 chars), normalisé.
    - `enabled` (optionnel) : bool. False = désactive (la sticky reste
      dans la liste mais n'est plus injectée dans le contexte LLM).
    """
    global _state
    body = request.get_json(silent=True) or {}
    has_text = "text" in body
    has_enabled = "enabled" in body
    if not has_text and not has_enabled:
        return jsonify({"error": "rien à modifier (text et/ou enabled requis)"}), 400
    new_text = None
    if has_text:
        new_text = _normalize_sticky_text(body.get("text"))
        if not new_text:
            return jsonify({"error": "text vide"}), 400
        if len(new_text) > _STICKY_TEXT_MAX_CHARS:
            return jsonify({
                "error": "text trop long",
                "max_chars": _STICKY_TEXT_MAX_CHARS,
                "got_chars": len(new_text),
            }), 400
    new_enabled = None
    if has_enabled:
        new_enabled = bool(body.get("enabled"))
    from utils import now_iso as _now_iso_st
    with _state_lock:
        if _state is None:
            return jsonify({"error": "pas de session active"}), 409
        existing = list(_state.session_state.data.get("stickies") or [])
        idx = next((i for i, s in enumerate(existing) if s.get("id") == sticky_id), -1)
        if idx < 0:
            return jsonify({"error": "sticky introuvable"}), 404
        updated = dict(existing[idx])
        if new_text is not None:
            updated["text"] = new_text
            updated["edited_at"] = _now_iso_st()
        if new_enabled is not None:
            updated["enabled"] = new_enabled
        existing[idx] = updated
        _state.session_state.set_meta("stickies", existing)
    logger.info("Sticky modifiée : %s (text_changed=%s, enabled_changed=%s)",
                sticky_id, has_text, has_enabled)
    return jsonify(updated)


@app.route("/api/stickies/<sticky_id>", methods=["DELETE"])
def api_stickies_delete(sticky_id: str):
    """Supprime une sticky par id."""
    global _state
    with _state_lock:
        if _state is None:
            return jsonify({"error": "pas de session active"}), 409
        existing = list(_state.session_state.data.get("stickies") or [])
        new_list = [s for s in existing if s.get("id") != sticky_id]
        if len(new_list) == len(existing):
            return jsonify({"error": "sticky introuvable"}), 404
        _state.session_state.set_meta("stickies", new_list)
    logger.info("Sticky supprimée : %s", sticky_id)
    return ("", 204)


@app.route("/api/stickies/import_from/<path:session_id>", methods=["POST"])
def api_stickies_import_from(session_id: str):
    """Copie les stickies sélectionnées d'une autre session vers la
    session active. Body JSON : `{sticky_ids: [id1, id2, ...]}` (si
    omis, importe **toutes** les stickies enabled de la session source).

    Les ids sont régénérés (sticky du source non altérée), `created_at`
    pointe sur l'import, `source_message_id` reste celui du source (peut
    pointer vers un msg qui n'existe pas dans la session actuelle,
    le front gère l'introuvable).
    """
    global _state
    body = request.get_json(silent=True) or {}
    sticky_ids_filter = body.get("sticky_ids")
    if sticky_ids_filter is not None and not isinstance(sticky_ids_filter, list):
        return jsonify({"error": "sticky_ids doit être une liste"}), 400

    # Sécurité : empêche path traversal sur le filename
    if ".." in session_id or "/" in session_id or "\\" in session_id:
        return jsonify({"error": "session_id invalide"}), 400

    source_path = SESSIONS_DIR / f"{session_id}.json"
    if not source_path.is_file():
        return jsonify({"error": "session source introuvable"}), 404
    try:
        with source_path.open("r", encoding="utf-8") as f:
            source_data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return jsonify({"error": f"impossible de lire la session source : {e}"}), 500

    source_stickies = source_data.get("stickies") or []
    if not isinstance(source_stickies, list):
        source_stickies = []

    if sticky_ids_filter:
        wanted = set(sticky_ids_filter)
        candidates = [s for s in source_stickies if s.get("id") in wanted]
    else:
        candidates = [s for s in source_stickies if s.get("enabled", True)]

    if not candidates:
        return jsonify({"ok": True, "imported_count": 0, "imported": []})

    from utils import now_iso as _now_iso_st
    now = _now_iso_st()
    new_stickies = []
    for src in candidates:
        text = _normalize_sticky_text(src.get("text"))
        if not text or len(text) > _STICKY_TEXT_MAX_CHARS:
            continue  # silently skip malformed source entries
        kind = src.get("kind") or "user"
        if kind not in ("user", "tutor"):
            kind = "user"
        new_stickies.append({
            "id": f"sticky_{uuid.uuid4().hex[:12]}",
            "kind": kind,
            "text": text,
            "source_message_id": src.get("source_message_id"),
            "created_at": now,
            "edited_at": None,
            "enabled": True,
            "imported_from": session_id,
        })

    with _state_lock:
        if _state is None:
            return jsonify({"error": "pas de session active"}), 409
        existing = list(_state.session_state.data.get("stickies") or [])
        existing.extend(new_stickies)
        _state.session_state.set_meta("stickies", existing)
    logger.info("Import stickies : %d depuis %s", len(new_stickies), session_id)
    return jsonify({
        "ok": True,
        "imported_count": len(new_stickies),
        "imported": new_stickies,
    })


# ============================================================ /api/dynamic_outline : Phase A.10.13c
# Sommaire dynamique : extracteur heuristique post-stream qui détecte les
# patterns structuraux (sections, questions, exercices) dans les réponses
# du tuteur, et les agglomère dans `session_state.data["dynamic_outline"]`.
# Visible en live dans l'onglet 📚 Docs. User : « les questions peuvent
# se préremplir automatiquement de ce que compagnon dit […] dynamique
# au fur et à mesure » + « dans le cas du mode découverte les chapitres
# et intitulé des sections ».
#
# Mécanisme : à chaque tour tuteur terminé, on parse le texte avec des
# regex pour trouver :
#   - Headings markdown `## H2`, `### H3`
#   - Patterns explicites : `**Exercice N**`, `**Question N**`,
#     `**Étape N**`, `**Chapitre N**`
#   - Listes numérotées de questions (`1. ...`, `2. ...`)
# Chaque match devient une entry de l'outline avec un id unique, snippet
# de contexte, source_message_id (pour scroll-back), enabled=True par
# défaut. Dédup par signature (kind + title normalisé).

_OUTLINE_RE_H2 = re.compile(r"^\s*##\s+(.+?)\s*$", re.MULTILINE)
_OUTLINE_RE_H3 = re.compile(r"^\s*###\s+(.+?)\s*$", re.MULTILINE)
_OUTLINE_RE_EXO = re.compile(
    r"\*\*(?:Exercice|Question|Étape|Etape|Chapitre|Partie|Thème|Theme)\s+(\d+|[A-Z]|[ivxlcdm]+)\s*[:\.\-]?\s*([^\*\n]{0,100})\*\*",
    re.IGNORECASE,
)
# Phase A.10.13c hotfix 2 (2026-05-14) : titres numérotés sans mot-clé
# explicite : `**1. Propriété des fonctions trigo**`, `**2. Théorème
# des gendarmes**`. C'est le pattern qu'utilise le tuteur quand il
# annonce une notion à noter au cahier (mode découverte/colle).
# Distingué du `**Exercice N**` par l'absence de mot-clé.
#
# Phase A.10.15 (2026-05-15) : préfixe optionnel `Titre :` / `Title :` /
# `Notion :` / `Concept :` / `Thème :` toléré. Friction user : Gemini API
# a commencé à émettre `**Titre : 1. Représentation de l'ADN…**` dans
# les "cartes" du cahier (blockquote), ce qui cassait l'extraction par
# rapport au format `**1. Titre**` qu'utilisait Claude. Le préfixe
# n'est pas capturé : le titre reste `1. Représentation de l'ADN…`.
_OUTLINE_RE_NUM_TITLE = re.compile(
    r"\*\*(?:(?:Titre|Title|Notion|Concept|Th[èe]me)\s*[:\-–—]?\s*)?(\d+)\.\s+([^*\n]{5,120})\*\*",
    re.IGNORECASE,
)
_OUTLINE_RE_NUMBERED_Q = re.compile(
    r"^\s*(\d+)\.\s+(.{10,150}?\?)\s*$",
    re.MULTILINE,
)

# Phase A.10.15 (2026-05-15) : version de l'extracteur. À bumper à chaque
# évolution non-additive des regex/heuristiques d'extraction d'outline.
# Le backfill se re-déclenche sur les sessions dont la version stockée
# est inférieure (signatures déjà-en-place dédoublonnées, signatures
# supprimées par l'user préservées via `dynamic_outline_deleted_signatures`).
# v2 : ajout préfixe `Titre :` / `Notion :` / `Concept :` / `Thème :` /
#      `Title :` (engine Gemini API) au regex NUM_TITLE.
_OUTLINE_EXTRACTOR_VERSION = 2


def _normalize_outline_title(s: str) -> str:
    """Normalise un titre pour dédup : strip, lower, retire markdown."""
    s = re.sub(r"[*_`#]", "", s).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s[:120]


def _extract_outline_entries(text: str, msg_id: str, mode: str) -> list[dict]:
    """Extrait les entries d'outline d'une réponse tuteur.

    Retourne une liste de dicts :
        {kind, title, snippet, source_message_id, signature}
    où `kind` ∈ {"section", "subsection", "exercise", "question"} et
    `signature` est la clé de dédup (normalised title + kind).
    """
    out = []
    if not text:
        return out

    for m in _OUTLINE_RE_H2.finditer(text):
        title = m.group(1).strip().rstrip(":")
        if len(title) < 3 or len(title) > 120:
            continue
        out.append({
            "kind": "section",
            "title": title,
            "snippet": "",
            "source_message_id": msg_id,
            "signature": f"section::{_normalize_outline_title(title)}",
        })

    for m in _OUTLINE_RE_H3.finditer(text):
        title = m.group(1).strip().rstrip(":")
        if len(title) < 3 or len(title) > 120:
            continue
        out.append({
            "kind": "subsection",
            "title": title,
            "snippet": "",
            "source_message_id": msg_id,
            "signature": f"subsection::{_normalize_outline_title(title)}",
        })

    # Captures `**Exercice N**`, `**Question N**`, etc. (mot-clé explicite).
    # On track les spans matchés pour éviter de re-matcher avec le pattern
    # numéroté générique `**N. Titre**` ci-dessous.
    exo_spans = []
    for m in _OUTLINE_RE_EXO.finditer(text):
        num = m.group(1)
        rest = m.group(2).strip(" :.-").strip()
        kw = m.group(0).split("**")[1].split()[0]
        kw_cap = kw.capitalize() if not kw.isupper() else kw
        if rest:
            title = f"{kw_cap} {num} : {rest}"[:120]
        else:
            title = f"{kw_cap} {num}"
        start = m.end()
        snippet = text[start:start + 200].strip()
        snippet = re.sub(r"\s+", " ", snippet)[:160]
        out.append({
            "kind": "exercise",
            "title": title,
            "snippet": snippet,
            "source_message_id": msg_id,
            "signature": f"exercise::{_normalize_outline_title(title)}",
        })
        exo_spans.append((m.start(), m.end()))

    # Phase A.10.13c hotfix 2 : titres numérotés `**N. Titre**` génériques
    # (sans mot-clé Exercice/Question/etc.). Ce sont les notions
    # pédagogiques que le tuteur fait noter au cahier (mode photos surtout).
    # Skip si la position est déjà matchée par _OUTLINE_RE_EXO.
    def _overlaps_exo(start, end):
        return any(s <= start < e for s, e in exo_spans)

    for m in _OUTLINE_RE_NUM_TITLE.finditer(text):
        if _overlaps_exo(m.start(), m.end()):
            continue
        num = m.group(1)
        title_body = m.group(2).strip().rstrip(":").rstrip()
        if len(title_body) < 5:
            continue
        title = f"{num}. {title_body}"[:120]
        out.append({
            "kind": "topic",
            "title": title,
            "snippet": "",
            "source_message_id": msg_id,
            "signature": f"topic::{_normalize_outline_title(title)}",
        })

    # Questions numérotées en liste (en mode colle uniquement, sinon
    # ça pollue avec les listes de bullets ordinaires en découverte).
    if mode == "colle":
        for m in _OUTLINE_RE_NUMBERED_Q.finditer(text):
            num = m.group(1)
            q = m.group(2).strip()
            title = f"Question {num} : {q[:80]}"
            out.append({
                "kind": "question",
                "title": title[:120],
                "snippet": "",
                "source_message_id": msg_id,
                "signature": f"question::{_normalize_outline_title(title)}",
            })

    return out


def _append_outline_from_tutor_msg(st, msg_id: str, text: str) -> None:
    """Best-effort : extrait les entries d'outline du dernier msg tuteur
    et les ajoute à session_state.data["dynamic_outline"]. Dédup via
    signature pour éviter les doublons sur replay/reformulations."""
    try:
        data = st.session_state.data
        mode = data.get("mode", "colle")
        new_entries = _extract_outline_entries(text, msg_id, mode)
        if not new_entries:
            return
        existing = list(data.get("dynamic_outline") or [])
        seen_sigs = {e.get("signature") for e in existing if isinstance(e, dict)}
        from utils import now_iso as _now_iso_outline
        added = 0
        for entry in new_entries:
            sig = entry.get("signature")
            if not sig or sig in seen_sigs:
                continue
            seen_sigs.add(sig)
            entry["id"] = f"outline_{uuid.uuid4().hex[:10]}"
            entry["created_at"] = _now_iso_outline()
            entry["enabled"] = True
            existing.append(entry)
            added += 1
        if added > 0:
            st.session_state.set_meta("dynamic_outline", existing)
            logger.info("Dynamic outline : +%d entries (msg %s)", added, msg_id)
    except Exception:  # noqa: BLE001
        logger.exception("_append_outline_from_tutor_msg a leve, best-effort skipped")


def _maybe_backfill_outline(st) -> None:
    """Phase A.10.13c hotfix : au 1ᵉʳ GET /api/dynamic_outline, si
    `dynamic_outline_backfilled` n'est pas posé, on parcourt tout le
    transcript persisté pour rattraper les sessions antérieures
    (ou les sessions où le compagnon a redémarré et perdu l'outline
    in-memory).

    Phase A.10.15 : le marker n'est plus suffisant : si on bump le
    `_OUTLINE_EXTRACTOR_VERSION` parce que les regex ont évolué, on
    veut re-balayer le transcript pour rattraper les patterns qui
    matchent désormais. Les entries déjà-en-place gardent leur id
    (dédup par `signature`). Les entries supprimées par l'utilisateur
    sont préservées via la liste `dynamic_outline_deleted_signatures`
    (cf. DELETE /api/dynamic_outline/<id>) pour ne PAS réapparaître.
    """
    data = st.session_state.data
    stored_version = int(data.get("dynamic_outline_extractor_version") or 0)
    if data.get("dynamic_outline_backfilled") and stored_version >= _OUTLINE_EXTRACTOR_VERSION:
        return
    mode = data.get("mode") or "colle"
    messages = data.get("messages") or {}
    branch = data.get("current_branch_path") or []
    existing = list(data.get("dynamic_outline") or [])
    seen_sigs = {e.get("signature") for e in existing if isinstance(e, dict)}
    deleted_sigs = set(data.get("dynamic_outline_deleted_signatures") or [])
    from utils import now_iso as _now_iso_o
    added = 0
    for mid in branch:
        m = messages.get(mid)
        if not isinstance(m, dict) or m.get("role") != "claude":
            continue
        text = m.get("text") or ""
        new_entries = _extract_outline_entries(text, mid, mode)
        for entry in new_entries:
            sig = entry.get("signature")
            if not sig or sig in seen_sigs or sig in deleted_sigs:
                continue
            seen_sigs.add(sig)
            entry["id"] = f"outline_{uuid.uuid4().hex[:10]}"
            entry["created_at"] = _now_iso_o()
            entry["enabled"] = True
            existing.append(entry)
            added += 1
    # Phase A.10.15 : re-tri chronologique par position de source_message_id
    # dans current_branch_path. Sans ce sort, les entries rétroactives (1, 2,
    # 3) qui s'insèrent APRÈS des entries live déjà présentes (4, 5) donnent
    # un ordre [4, 5, 1, 2, 3]. Le sort Python est stable, donc plusieurs
    # entries pointant le même message gardent leur ordre relatif d'extraction.
    branch_index = {mid: i for i, mid in enumerate(branch)}
    def _chrono_key(entry):
        mid = entry.get("source_message_id") or ""
        # Entries dont la source est hors branche (msg supprimé, branche
        # éditée) atterrissent à la fin avec ordre stable.
        return branch_index.get(mid, len(branch_index) + 1)
    existing.sort(key=_chrono_key)
    st.session_state.set_meta("dynamic_outline", existing)
    st.session_state.set_meta("dynamic_outline_backfilled", True)
    st.session_state.set_meta(
        "dynamic_outline_extractor_version", _OUTLINE_EXTRACTOR_VERSION,
    )
    if added:
        logger.info(
            "Dynamic outline backfill : +%d entries (extractor v%d)",
            added, _OUTLINE_EXTRACTOR_VERSION,
        )


@app.route("/api/dynamic_outline", methods=["GET"])
def api_dynamic_outline_list():
    """Liste les entrées du sommaire dynamique de la session active."""
    global _state
    with _state_lock:
        if _state is None:
            return jsonify({"outline": [], "active": False})
        st = _state
    # Lazy backfill (best-effort, idempotent via marker).
    try:
        _maybe_backfill_outline(st)
    except Exception:  # noqa: BLE001
        logger.exception("backfill dynamic_outline a leve, GET continue")
    with _state_lock:
        if _state is None:
            return jsonify({"outline": [], "active": False})
        outline = list(_state.session_state.data.get("dynamic_outline") or [])
        branch = list(_state.session_state.data.get("current_branch_path") or [])
    # Phase A.10.15 : tri chronologique défensif. Les sessions dont le
    # disque a un ordre obsolète (backfill rétroactif post-live entries,
    # cf. friction TP9 PRG2 du 2026-05-15) sont normalisées à la lecture.
    # Coût négligeable (n typiquement < 50) et sort stable préserve
    # l'ordre relatif des entries pointant le même message.
    branch_index = {mid: i for i, mid in enumerate(branch)}
    outline.sort(
        key=lambda e: branch_index.get(
            e.get("source_message_id") or "", len(branch_index) + 1,
        )
    )
    return jsonify({"outline": outline, "active": True})


@app.route("/api/dynamic_outline/<entry_id>", methods=["PATCH"])
def api_dynamic_outline_patch(entry_id: str):
    """Édite une entrée : body {title?, enabled?}. Permet de renommer
    ou désactiver une entry sans la supprimer."""
    global _state
    body = request.get_json(silent=True) or {}
    new_title = body.get("title")
    new_enabled = body.get("enabled")
    if new_title is None and new_enabled is None:
        return jsonify({"error": "title et/ou enabled requis"}), 400
    if new_title is not None:
        new_title = str(new_title).strip()
        if not new_title or len(new_title) > 200:
            return jsonify({"error": "title invalide (1-200 chars)"}), 400
    with _state_lock:
        if _state is None:
            return jsonify({"error": "pas de session active"}), 409
        existing = list(_state.session_state.data.get("dynamic_outline") or [])
        idx = next((i for i, e in enumerate(existing) if e.get("id") == entry_id), -1)
        if idx < 0:
            return jsonify({"error": "entry introuvable"}), 404
        updated = dict(existing[idx])
        if new_title is not None:
            updated["title"] = new_title
            from utils import now_iso as _now_iso_outline
            updated["edited_at"] = _now_iso_outline()
        if new_enabled is not None:
            updated["enabled"] = bool(new_enabled)
        existing[idx] = updated
        _state.session_state.set_meta("dynamic_outline", existing)
    return jsonify(updated)


@app.route("/api/dynamic_outline/<entry_id>", methods=["DELETE"])
def api_dynamic_outline_delete(entry_id: str):
    """Supprime une entry du sommaire.

    Phase A.10.15 : track la signature de l'entry supprimée dans
    `dynamic_outline_deleted_signatures` pour qu'elle ne réapparaisse
    pas lors d'un futur backfill (bump de `_OUTLINE_EXTRACTOR_VERSION`
    ou première extraction sur une session ancienne).
    """
    global _state
    with _state_lock:
        if _state is None:
            return jsonify({"error": "pas de session active"}), 409
        existing = list(_state.session_state.data.get("dynamic_outline") or [])
        target = next((e for e in existing if e.get("id") == entry_id), None)
        if target is None:
            return jsonify({"error": "entry introuvable"}), 404
        new_list = [e for e in existing if e.get("id") != entry_id]
        _state.session_state.set_meta("dynamic_outline", new_list)
        sig = target.get("signature")
        if sig:
            deleted = list(
                _state.session_state.data.get("dynamic_outline_deleted_signatures") or []
            )
            if sig not in deleted:
                deleted.append(sig)
                _state.session_state.set_meta(
                    "dynamic_outline_deleted_signatures", deleted,
                )
    return ("", 204)


# ============================================================ /api/export_recap : Phase A.10.13b
# Export PDF + MD on-demand de la session active. Remplace l'archive
# live .md de Phase A.8.1 (supprimée A.10.11) par un générateur ponctuel
# au clic utilisateur. User : « à la limite à la fin ça peut sortir un
# pdf récapitatif voire un bouton quelque part pour sortir un pdf
# recapitulatif de la section à chaque fois qu'on le veut et pas
# forcément qu'à la fin ».
#
# Retourne un .zip contenant {session_id}.pdf et {session_id}.md.


@app.route("/api/export_recap", methods=["GET"])
def api_export_recap():
    """Génère un récap PDF + MD de la session active et retourne un zip.

    Pas de body. Lit `_state.session_state.data` au moment du clic →
    snapshot complet (transcript + stickies + recap).

    Réponse : 200 application/zip avec download attachment, ou 409 si
    pas de session active, 500 si la génération échoue.
    """
    import io
    import zipfile
    from session_export import (
        render_session_md, render_session_pdf_bytes,
    )

    global _state
    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409

    try:
        data = st.session_state.data
    except Exception:  # noqa: BLE001
        return jsonify({"error": "session_state inaccessible"}), 500

    session_id = data.get("session_id") or "session"

    try:
        md_text = render_session_md(data)
    except Exception as e:  # noqa: BLE001
        logger.exception("render_session_md a leve")
        return jsonify({"error": f"render MD : {e}"}), 500

    try:
        pdf_bytes = render_session_pdf_bytes(data)
    except ImportError as e:
        return jsonify({"error": f"reportlab requis : {e}"}), 500
    except Exception as e:  # noqa: BLE001
        logger.exception("render_session_pdf_bytes a leve")
        return jsonify({"error": f"render PDF : {e}"}), 500

    # Empaquette en zip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{session_id}.md", md_text)
        zf.writestr(f"{session_id}.pdf", pdf_bytes)
    buf.seek(0)

    from flask import Response
    filename = f"recap_{session_id}.zip"
    return Response(
        buf.getvalue(),
        mimetype="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@app.route("/api/transcribe", methods=["POST"])
def api_transcribe():
    """Reçoit un blob audio (multipart) et retourne sa transcription.

    Phase A.6.2 : alimenté par le bouton micro toggle dans l'UI navigateur,
    cf. ``static/app.js``. Lazy-load Whisper large-v3 au premier appel.

    Le format est typiquement WebM/Opus (default MediaRecorder Chrome/Firefox)
    (faster-whisper utilise pyav/ffmpeg pour décoder, donc OK directement).
    """
    audio = request.files.get("audio")
    if audio is None or audio.filename == "":
        return jsonify({"error": "champ 'audio' manquant"}), 400

    # On déduit l'extension depuis le mimetype ou le filename pour aider
    # ffmpeg/pyav à choisir le bon decoder. WebM par défaut.
    suffix = ".webm"
    if audio.mimetype:
        if "wav" in audio.mimetype:
            suffix = ".wav"
        elif "ogg" in audio.mimetype:
            suffix = ".ogg"
        elif "mp4" in audio.mimetype or "m4a" in audio.mimetype:
            suffix = ".m4a"

    fd, tmp_path_str = tempfile.mkstemp(suffix=suffix, prefix="compagnon_rec_")
    os.close(fd)
    tmp_path = Path(tmp_path_str)
    audio.save(tmp_path_str)

    try:
        try:
            transcriber = _get_transcriber()
        except Exception as e:
            logger.exception("Whisper lazy-load echoue")
            return jsonify({
                "error": "whisper_load_failed",
                "detail": f"{type(e).__name__}: {e}",
            }), 500
        try:
            text, duration = transcriber.transcribe(tmp_path)
        except Exception as e:
            logger.exception("Whisper transcribe echoue")
            return jsonify({
                "error": "transcribe_failed",
                "detail": f"{type(e).__name__}: {e}",
            }), 500
        text = (text or "").strip()
        return jsonify({"text": text, "duration_seconds": duration})
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


# ============================================================ /api/rewrite : Phase A.7.2 v15.5
# Mini-utilitaire one-shot pour reformuler / resserrer / développer / corriger
# les fautes du brouillon dans userInput AVANT envoi à la conversation
# principale. Utile parce qu'aucun LLM SOTA grand public n'expose cette
# capacité « rewrite avant envoi » en standard, et que dicter au micro
# produit du texte plein de hésitations qu'on aimerait nettoyer sans
# couper le flow.
#
# Coût : ~300-1500 tokens in/out par appel selon longueur du texte. Sur
# quota Pro Max c'est invisible (compté à la session, pas au token).
# Sur API anthropic ~$0.005 par rewrite avec Sonnet/Opus.

REWRITE_INTENTS = {
    "reformulate": (
        "Reformule le texte ci-dessous en gardant exactement le même sens "
        "et le même registre, mais avec une syntaxe plus claire et "
        "naturelle. Conserve le tutoiement/vouvoiement et le niveau de "
        "langue d'origine. Ne change ni le fond ni les exemples cités. "
        "Vise un texte qu'un correcteur exigeant trouverait lisible et "
        "fluide."
    ),
    "concise": (
        "Resserre le texte ci-dessous : supprime les redondances, "
        "hésitations (« euh », « donc », « voilà »), faux départs et "
        "mots-béquilles. Cible 30-50 % de la longueur originale. Garde "
        "exactement le même sens, ne supprime aucune information "
        "factuelle ni aucun exemple."
    ),
    "expand": (
        "Développe le texte ci-dessous : explicite les nuances, "
        "justifications et exemples qui paraissent implicites mais "
        "utiles à formuler pour un interlocuteur exigeant. N'invente "
        "AUCUN fait, reste strictement fidèle au contenu d'origine. "
        "Tu peux ajouter des connecteurs logiques pour clarifier le "
        "raisonnement."
    ),
    "fix_typos": (
        "Corrige STRICTEMENT et UNIQUEMENT les fautes d'orthographe, de "
        "grammaire, d'accords, de conjugaison et de ponctuation du texte "
        "ci-dessous. Ne reformule pas, ne change pas le style, ne touche "
        "pas à la structure des phrases. Préserve même les tournures "
        "orales si elles sont grammaticalement correctes.\n\n"
        "INTERDICTIONS ABSOLUES (Phase v15.7.2) : tu ne supprimes AUCUN "
        "faux départ (« et non c'est », « enfin je veux dire », « ah "
        "non »), AUCUNE hésitation (« euh », « ben », « bah », « du "
        "coup », « voilà »), AUCUN mot-béquille, AUCUNE répétition. "
        "Même si le texte devient « moche » ou décousu, tu le laisses "
        "tel quel. Si l'utilisateur voulait nettoyer ces tics oraux, "
        "il aurait choisi « Plus concis » ou « Reformuler » ; en "
        "choisissant « Corriger fautes » il signale qu'il veut garder "
        "le grain brut de sa dictée et juste les accents/accords. "
        "Respecte ce choix."
    ),
}

REWRITE_SYSTEM_PROMPT = (
    "Tu es un assistant de réécriture de texte. Tu reçois un message "
    "rédigé par un étudiant et une consigne de transformation. Ta sortie "
    "DOIT contenir UNIQUEMENT la nouvelle version du texte, sans "
    "préambule (« Voici… »), sans postambule, sans guillemets autour, "
    "sans markdown supplémentaire (pas de gras/italique sauf si présent "
    "dans l'original), sans commentaire sur ce que tu as fait. Garde la "
    "même langue que l'original.\n\n"
    "Si un bloc [Contexte : dernier message du tuteur] est fourni AVANT "
    "le brouillon, il sert UNIQUEMENT à : (1) lever les ambiguïtés de "
    "pronoms (« celle », « il », « ça » → le terme exact), (2) aligner "
    "le vocabulaire technique sur celui du tuteur (ex. « la sortie E1 » "
    "→ « l'entrée E1 » si le tuteur vient de rappeler que E1 est une "
    "entrée). Tu n'as PAS le droit d'ajouter, corriger ou supprimer un "
    "raisonnement, un fait ou une conclusion du brouillon, même si le "
    "contexte du tuteur les contredit : l'étudiant doit trouver son "
    "erreur de fond lui-même, ton rôle se limite à la forme."
)

#: Cap pour éviter qu'un copier-coller massif ne déclenche un rewrite
#: monstrueux. Au-delà, l'endpoint refuse : l'utilisateur doit segmenter.
REWRITE_MAX_INPUT_CHARS = 8000

#: Cap pour le bloc de contexte tuteur. ~2000 chars couvrent un tour
#: Compagnon typique (200-800 chars). Au-delà on garde les 2000 derniers
#: caractères : la question reformulée se trouve typiquement en fin de
#: tour (pattern « Reprenez : … ? » du prompt système COMPAGNON §3).
REWRITE_MAX_CONTEXT_CHARS = 2000


@app.route("/api/rewrite", methods=["POST"])
def api_rewrite():
    """Reformule un brouillon avant envoi (Phase A.7.2 v15.5).

    Body JSON ::

        {
          "text": "<brouillon de l'utilisateur>",
          "intent": "reformulate" | "concise" | "expand" | "fix_typos",
          "context_tutor": "<dernier message du Compagnon, optionnel>"
        }

    Réponse 200 ::

        {"rewritten": "<nouveau texte>", "intent": "...", "engine": "...",
         "context_chars": <int, longueur du contexte injecté, 0 si absent>}

    Codes d'erreur :
        400 : text vide / intent invalide / texte trop long
        429 : quota CLI/API épuisé
        502 : erreur réseau / SDK
    """
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    intent = body.get("intent") or "reformulate"
    context_tutor = (body.get("context_tutor") or "").strip()
    if not text:
        return jsonify({"error": "text vide"}), 400
    if intent not in REWRITE_INTENTS:
        return jsonify({
            "error": "intent invalide",
            "allowed": sorted(REWRITE_INTENTS.keys()),
        }), 400
    if len(text) > REWRITE_MAX_INPUT_CHARS:
        return jsonify({
            "error": "text trop long",
            "max_chars": REWRITE_MAX_INPUT_CHARS,
            "got_chars": len(text),
        }), 400

    # Phase v15.7.1 : contexte tuteur : tronque par le DÉBUT pour garder
    # la fin du tour (où la question reformulée du prompt COMPAGNON §3
    # « Reprenez : … ? » se trouve typiquement).
    if context_tutor and len(context_tutor) > REWRITE_MAX_CONTEXT_CHARS:
        context_tutor = context_tutor[-REWRITE_MAX_CONTEXT_CHARS:]

    if context_tutor:
        user_msg = (
            f"[Contexte : dernier message du tuteur]\n"
            f"{context_tutor}\n"
            f"[/Contexte]\n\n"
            f"Consigne : {REWRITE_INTENTS[intent]}\n\n"
            f"---\n"
            f"Texte à transformer :\n{text}"
        )
    else:
        user_msg = (
            f"Consigne : {REWRITE_INTENTS[intent]}\n\n"
            f"---\n"
            f"Texte à transformer :\n{text}"
        )

    engine = _read_engine_pref()
    try:
        rewritten = _run_rewrite_on_engine(engine, user_msg)
    except ClaudeQuotaExhaustedError as e:
        # Phase v15.6.4 : DeepSeek 402 « Insufficient Balance », rate
        # limit Groq/Gemini, Anthropic API quota épuisé. Le moteur est
        # temporairement HS. Pas d'auto-fallback (l'utilisateur a choisi
        # son moteur pour des raisons précises : quota Pro Max à
        # préserver, modèle spécifique à tester) : on signale clairement
        # avec un code dédié pour que le frontend propose une bascule
        # manuelle au lieu de switcher dans son dos.
        logger.info("rewrite engine=%s quota/solde epuise : %s", engine, e)
        return jsonify({
            "error": "quota_exhausted",
            "detail": str(e)[:300],
            "engine": engine,
        }), 429
    except ClaudeClientError as e:
        logger.warning("rewrite engine=%s erreur claude : %s", engine, e)
        return jsonify({
            "error": "claude_error",
            "detail": str(e)[:300],
            "engine": engine,
        }), 502
    except ValueError as e:  # engine invalide
        return jsonify({"error": "engine invalide", "detail": str(e)}), 500

    if not rewritten:
        return jsonify({"error": "reponse_vide", "engine": engine}), 502

    return jsonify({
        "rewritten": rewritten,
        "intent": intent,
        "engine": engine,
        "context_chars": len(context_tutor),
    })


# ============================================================ /api/find_similar_exo : Phase Z.8.4
# Bouton « 💡 Trouve un exo équivalent » côté GUI : en mode colle,
# l'étudiant bloque sur un exo et veut un exemple SIMILAIRE pour
# s'entraîner sans spoiler le corrigé du CC en cours. L'endpoint
# lance UN appel Claude jetable avec accès FS scopé COURS/{matiere}/
# en mode guidé (Read/Grep/Glob), avec un system prompt dédié qui :
#   - Cherche un exo similaire dans les TDs/CC passés du même type
#   - INTERDIT de Read le corrigé du (matiere, type, num) en cours
#   - Renvoie ÉNONCÉ SEUL, pas de solution ni d'indices
# La conv principale (mode colle) n'est PAS modifiée : l'appel est
# isolé. Le résultat est rendu dans une bulle système dédiée.

FIND_EXO_SYSTEM_PROMPT_TEMPLATE = """Tu es un assistant de recherche d'exercices équivalents pour un étudiant L1 Informatique-Électronique de l'ISTIC Rennes. Ton rôle est UNIQUEMENT de trouver dans son arborescence de cours un exercice similaire à celui sur lequel il bloque, pour qu'il puisse s'entraîner SANS être spoilé.

## Contexte de la session en cours
- Matière : {matiere}
- Type : {type_courant} numéro {num_courant}
- Exo en cours : {exo_courant}

## Règles INVIOLABLES
1. **INTERDICTION ABSOLUE de Read le corrigé en cours.** Tu ne dois PAS ouvrir `correction_{type_courant}{num_courant}*.pdf` ni aucun fichier dans le dossier `corrections/` du `{type_courant}{num_courant}` courant. Si tu le fais accidentellement, tu DOIS arrêter et signaler l'erreur sans transmettre le contenu.
2. **Ne donne JAMAIS la solution** de l'exo équivalent que tu trouves. Pas d'indices, pas de pistes, pas de corrigé. Juste l'énoncé brut + une phrase pour expliquer pourquoi c'est similaire.
3. **Pas de cours magistral.** L'étudiant veut juste un exo voisin pour se débloquer. Pas de récap théorique.

## Méthode
1. Liste les TDs/TPs/CC précédents de la matière `{matiere}` via Glob (`COURS/{matiere}/TD/*/`, `COURS/{matiere}/CC/*/` etc.).
2. Lis (Read) les `enonce_*.pdf` ou `enonce_*.txt` des autres TDs/CC pour identifier ceux qui traitent du MÊME type de problème que `{type_courant}{num_courant} exo {exo_courant}`. Tu peux Read les CM/poly de la matière pour comprendre le sujet.
3. Choisis UN exercice voisin pertinent. Critères de similarité (par ordre de priorité) :
   - Même chapitre / concept du CM
   - Même type de question (calcul, démonstration, schéma, code)
   - Niveau de difficulté comparable

## Format de sortie STRICT
Tu produis un objet JSON minifié sur une seule ligne, encadré par les balises `<<<EXO_FOUND>>>` et `<<<END>>>`, suivi d'une phrase courte hors balises pour confirmation.

```
<<<EXO_FOUND>>>{{"matiere":"{matiere}","type":"<TD|TP|CC>","num":"<numero>","exo":"<numero exo>","label":"<TD3 - Exercice 2>","why":"<1 phrase, ce que cet exo a en commun avec celui qui te bloque>","enonce":"<l'énoncé brut tel qu'il apparaît dans le fichier source>"}}<<<END>>>
J'ai trouvé un exercice voisin : <label>. Tu peux essayer celui-ci avant de revenir au tien.
```

Si tu ne trouves rien de similaire, renvoie :
```
<<<EXO_FOUND>>>{{"none":true,"reason":"<1 phrase de pourquoi rien ne match>"}}<<<END>>>
Désolé, je n'ai pas trouvé d'exercice voisin dans tes cours.
```

## Description du blocage de l'étudiant
{description_blocage}
"""


@app.route("/api/find_similar_exo", methods=["POST"])
def api_find_similar_exo():
    """Trouve un exercice équivalent dans COURS/{matiere}/ (Phase Z.8.4).

    Body JSON ::

        {"description": "Je bloque sur le calcul de Hamming de l'ex 2..."}

    Le contexte (matière, type, num, exo en cours) est lu depuis la
    session active. La requête est jetable : pas de side-effect sur
    `_state.client` ni sur le transcript principal.

    Réponse 200 ::

        {
          "found": bool,
          "exo": {                # présent si found=true
            "matiere": "EN1",
            "type": "TD",
            "num": "5",
            "exo": "3",
            "label": "TD5, Exercice 3",
            "why": "Même type de calcul de bit de parité.",
            "enonce": "..."
          },
          "engine": "claude-…"
        }
    """
    global _state
    body = request.get_json(silent=True) or {}
    description = (body.get("description") or "").strip()
    if not description:
        return jsonify({"error": "description manquante"}), 400

    # Phase Z.9 : params optionnels :
    #   difficulty: "easier" | "harder" | "different" | None
    #     - easier    : exo plus simple pour entrer dans le sujet
    #     - harder    : exo plus dur pour stretch
    #     - different : autre angle, niveau comparable
    #     - None      : voisin standard (comportement initial)
    #   exclude: liste de {matiere, type, num, exo} déjà proposés dans la
    #     session. Le LLM doit les éviter. Permet à l'utilisateur de
    #     re-cliquer 🔄 sans retomber sur les mêmes.
    difficulty_raw = body.get("difficulty")
    difficulty = difficulty_raw if difficulty_raw in ("easier", "harder", "different") else None
    exclude_raw = body.get("exclude") or []
    exclude_list: list[dict] = []
    if isinstance(exclude_raw, list):
        for it in exclude_raw[:20]:  # cap pour éviter prompt obèse
            if isinstance(it, dict):
                exclude_list.append({
                    "matiere": str(it.get("matiere") or "").upper(),
                    "type": str(it.get("type") or "").upper(),
                    "num": str(it.get("num") or ""),
                    "exo": str(it.get("exo") or ""),
                })

    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409

    ctx = st.session_state.context
    matiere = (ctx.matiere or "").upper()
    type_courant = (ctx.type or "").upper()
    num_courant = str(ctx.num or "")
    exo_courant = str(ctx.exo or "?")

    if not matiere or not type_courant or not num_courant:
        return jsonify({"error": "contexte session incomplet"}), 409

    matiere_dir = COURS_ROOT / matiere
    if not matiere_dir.is_dir():
        return jsonify({
            "error": f"dossier matière introuvable : COURS/{matiere}/",
        }), 404

    sys_prompt = FIND_EXO_SYSTEM_PROMPT_TEMPLATE.format(
        matiere=matiere,
        type_courant=type_courant,
        num_courant=num_courant,
        exo_courant=exo_courant,
        description_blocage=description,
    )

    # Phase Z.9 : append des consignes de difficulté et d'exclusion en
    # fin du system prompt. Format texte simple, le LLM comprend bien.
    extra_instructions = []
    if difficulty == "easier":
        extra_instructions.append(
            "## Niveau de difficulté demandé\n"
            "Cherche un exercice **plus simple** que le précédent, pour permettre "
            "à l'étudiant d'entrer progressivement dans le concept. Privilégier "
            "les questions de cours, les exemples introductifs, ou les premiers "
            "exos d'un TD plutôt que les derniers."
        )
    elif difficulty == "harder":
        extra_instructions.append(
            "## Niveau de difficulté demandé\n"
            "Cherche un exercice **plus dur** que ce que l'étudiant ferait "
            "normalement, pour le pousser à s'étirer. Privilégier les exos "
            "de fin de TD, les CC plus avancés, ou les questions de synthèse."
        )
    elif difficulty == "different":
        extra_instructions.append(
            "## Angle différent demandé\n"
            "Cherche un exercice qui aborde le **même concept** mais sous un "
            "angle différent (autre type de question, autre application, autre "
            "formulation). Niveau de difficulté comparable au standard."
        )
    if exclude_list:
        excl_lines = []
        for it in exclude_list:
            ref = f"{it['matiere']} {it['type']}{it['num']} ex {it['exo']}"
            excl_lines.append(f"  - {ref.strip()}")
        extra_instructions.append(
            "## Exercices DÉJÀ proposés à éviter\n"
            "Ces exos ont déjà été suggérés à l'étudiant dans cette session :\n"
            + "\n".join(excl_lines) + "\n\n"
            "Tu DOIS choisir un exo DIFFÉRENT de ceux-là. Si tu ne trouves "
            "rien d'autre de pertinent, renvoie {\"none\":true,\"reason\":\""
            "Pas d'autre exo voisin disponible : tu as déjà vu les bons candidats."
            "\"}."
        )
    if extra_instructions:
        sys_prompt += "\n\n" + "\n\n".join(extra_instructions)

    engine = _read_engine_pref()
    try:
        # Mode GUIDE pour avoir Read/Grep/Glob scopés à COURS_ROOT.
        # On force cours_root sur matiere_dir pour que le tuteur ne
        # puisse Glob que dans COURS/{matiere}/ : il ne dérivera pas
        # vers d'autres matières, ne lira pas de personnel, etc.
        client = ClaudeClient(
            engine=engine,
            system_prompt=sys_prompt,
            mode=MODE_GUIDE,
            cours_root=matiere_dir,
        )
    except ValueError as e:
        return jsonify({"error": "engine invalide", "detail": str(e)}), 500

    # Le user message est minimal : toute l'instruction est dans le prompt
    # système. On envoie juste un signal pour démarrer.
    client.append_user_message("Lance la recherche.")

    try:
        client.stream_response(on_event=lambda _ev: None)
    except ClaudeQuotaExhaustedError as e:
        return jsonify({
            "error": "quota_exhausted",
            "detail": str(e)[:300],
            "engine": engine,
        }), 429
    except ClaudeClientError as e:
        return jsonify({
            "error": "claude_error",
            "detail": str(e)[:300],
            "engine": engine,
        }), 502

    history = client.history
    if not history or history[-1].get("role") != "assistant":
        return jsonify({"error": "reponse_vide"}), 502
    raw = (history[-1].get("content") or "").strip()

    # Parse la balise <<<EXO_FOUND>>>{...}<<<END>>>
    import re as _re
    m = _re.search(
        r"<<<EXO_FOUND>>>(.*?)<<<END>>>", raw, _re.DOTALL,
    )
    if not m:
        return jsonify({
            "error": "balise_absente",
            "detail": raw[:500],
            "engine": engine,
        }), 502
    try:
        payload = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        return jsonify({
            "error": "json_invalide",
            "detail": f"{e}: {m.group(1)[:300]}",
            "engine": engine,
        }), 502

    if payload.get("none"):
        return jsonify({
            "found": False,
            "reason": payload.get("reason") or "Pas d'exercice voisin trouvé.",
            "engine": engine,
        })

    # Phase Z.8.8 : résout les chemins PDF (énoncé + corrigés) de l'exo
    # voisin trouvé pour que le frontend puisse afficher des boutons
    # « 📄 Énoncé PDF » / « ✅ Corrigé PDF » qui ouvrent dans un nouvel
    # onglet via /api/cours_file?path=…. Helper réutilisable pour les
    # futures fonctionnalités (ex : pointe-moi le passage du CM, recherche
    # internet) qui voudront référencer un fichier de COURS/.
    exo_matiere = payload.get("matiere", matiere)
    exo_type = payload.get("type", "")
    exo_num = payload.get("num", "")
    exo_exo = payload.get("exo", "")
    pdf_paths = _resolve_exo_files(exo_matiere, exo_type, exo_num, exo_exo)

    return jsonify({
        "found": True,
        "exo": {
            "matiere": exo_matiere,
            "type": exo_type,
            "num": exo_num,
            "exo": exo_exo,
            "label": payload.get("label") or "Exercice voisin",
            "why": payload.get("why") or "",
            "enonce": payload.get("enonce") or "",
            "enonce_pdf_path": pdf_paths.get("enonce_pdf_path"),
            "correction_pdf_paths": pdf_paths.get("correction_pdf_paths") or [],
        },
        "engine": engine,
    })


# ============================================================ /api/find_cm_passage : Phase Z.9 (C2)
# Pointe l'étudiant vers le passage du CM qui définit le concept ciblé.
# Différent de l'exo voisin : ici on ne fait pas faire un exo, on
# l'envoie lire la bonne page du poly. Plus économe en effort cognitif.

FIND_CM_PASSAGE_PROMPT_TEMPLATE = """Tu es un assistant de localisation de contenu de cours pour un étudiant L1 Informatique-Électronique de l'ISTIC Rennes.

## Contexte de la session
- Matière : {matiere}
- Exo en cours : {type_courant}{num_courant} ex {exo_courant}

## Règle INVIOLABLE
INTERDICTION de Read le corrigé du `{type_courant}{num_courant}` en cours. Tu dois UNIQUEMENT chercher dans `COURS/{matiere}/CM/`, `COURS/{matiere}/poly/` ou les transcriptions de CM. Ne donne pas de solution à l'exo en cours.

## Méthode
1. Glob `COURS/{matiere}/CM/poly_*.pdf`, `COURS/{matiere}/CM/cm_*.pdf`, et les transcriptions `*.txt` éventuelles.
2. Read les fichiers pertinents pour identifier le passage qui définit / introduit / explique le concept évoqué dans la description du blocage.
3. Si plusieurs passages possibles, choisis le plus introductif (celui qui POSE la définition, pas celui qui l'utilise plus loin).

## Format de sortie STRICT
Tu produis un objet JSON minifié sur une seule ligne, encadré par les balises `<<<CM_FOUND>>>` et `<<<END>>>`, suivi d'une phrase courte hors balises pour confirmation.

```
<<<CM_FOUND>>>{{"matiere":"{matiere}","filename":"<nom du fichier ex poly_en1_4.pdf>","label":"<CM 4 : Logique combinatoire>","page":<numéro 1-indexé ou null>,"extract":"<3-8 lignes du passage qui définit le concept, copiées telles qu'elles>","why":"<1 phrase, pourquoi ce passage répond au blocage>"}}<<<END>>>
J'ai trouvé le passage qui définit ce concept dans <label>. Va jeter un œil et reviens.
```

Si tu ne trouves rien :
```
<<<CM_FOUND>>>{{"none":true,"reason":"<1 phrase>"}}<<<END>>>
```

## Description du blocage
{description_blocage}
"""


@app.route("/api/find_cm_passage", methods=["POST"])
def api_find_cm_passage():
    """Cherche dans les CM/polys le passage qui définit le concept en
    blocage. Renvoie nom de fichier + page + extrait court (Phase Z.9 C2).

    Body : ``{"description": "..."}``. Renvoie ``{found, passage:
    {matiere, filename, label, page, extract, why, pdf_path}, engine}``
    ou ``{found: false, reason}``.

    Comme `/api/find_similar_exo`, l'appel est jetable : ne pollue pas
    la conv principale. Mode GUIDE avec cours_root scopé à
    `COURS/{matiere}/`. Interdiction du corrigé en cours.
    """
    global _state
    body = request.get_json(silent=True) or {}
    description = (body.get("description") or "").strip()
    if not description:
        return jsonify({"error": "description manquante"}), 400

    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409

    ctx = st.session_state.context
    matiere = (ctx.matiere or "").upper()
    type_courant = (ctx.type or "").upper()
    num_courant = str(ctx.num or "")
    exo_courant = str(ctx.exo or "?")
    if not matiere or not type_courant or not num_courant:
        return jsonify({"error": "contexte session incomplet"}), 409
    matiere_dir = COURS_ROOT / matiere
    if not matiere_dir.is_dir():
        return jsonify({
            "error": f"dossier matière introuvable : COURS/{matiere}/",
        }), 404

    sys_prompt = FIND_CM_PASSAGE_PROMPT_TEMPLATE.format(
        matiere=matiere,
        type_courant=type_courant,
        num_courant=num_courant,
        exo_courant=exo_courant,
        description_blocage=description,
    )
    payload, engine, err_resp = _run_isolated_lookup(
        sys_prompt, "Lance la recherche.", "<<<CM_FOUND>>>", "<<<END>>>",
        cours_root=matiere_dir,
    )
    if err_resp is not None:
        return err_resp
    if payload.get("none"):
        return jsonify({
            "found": False,
            "reason": payload.get("reason") or "Aucun passage de CM identifié.",
            "engine": engine,
        })
    # Résout le pdf_path à partir du filename pour ouvrir dans un onglet
    fname = payload.get("filename") or ""
    pdf_rel = None
    if fname:
        # Cherche le fichier dans COURS/{matiere}/CM/
        cm_dir = matiere_dir / "CM"
        for p in cm_dir.rglob(fname):
            try:
                pdf_rel = p.relative_to(COURS_ROOT).as_posix()
                break
            except ValueError:
                continue
    return jsonify({
        "found": True,
        "passage": {
            "matiere": payload.get("matiere", matiere),
            "filename": fname,
            "label": payload.get("label") or fname,
            "page": payload.get("page"),
            "extract": payload.get("extract") or "",
            "why": payload.get("why") or "",
            "pdf_path": pdf_rel,
        },
        "engine": engine,
    })


# ============================================================ /api/web_search : Phase Z.9 (A1)
# Recherche internet d'un exo voisin OU d'un complément de cours.
# Active uniquement sur Claude API (tool web_search natif) et Gemini
# (Search Grounding). Les autres engines retournent une erreur claire
# qui propose la bascule.

WEB_SEARCH_EXO_PROMPT = """Tu es un assistant de recherche internet pour un étudiant L1 Informatique-Électronique français qui prépare un CC à l'ISTIC Rennes.

## RÈGLE INVIOLABLE : pas d'hallucination d'URLs
Tu DOIS impérativement utiliser ton outil de recherche internet avant de proposer une URL. **Ne JAMAIS inventer une URL à partir de ta connaissance interne**, même si le site est connu (Bibmath, Khan Academy, Wikiversité…). Les URLs profondes (`/exercices/calcul-binaire-3.html` etc.) NE sont PAS prévisibles.

Si ton tool ne retourne aucun résultat pertinent OU si tu n'as pas accès au tool, retourne `{{"results":[]}}` avec une `reason` honnête. Mieux vaut signaler l'échec qu'inventer.


## Contexte
- Matière : {matiere}
- L'étudiant a déjà cherché un exo voisin dans son arbo de cours locale et ce qu'il a trouvé ne lui convient pas (ou rien n'a été trouvé). Il veut maintenant des **ressources externes** pour s'entraîner sur le même concept.

## Méthode
Utilise tes outils de **recherche internet** pour trouver 2-3 ressources éducatives de qualité en **français**, accessibles librement. Privilégier dans cet ordre :
1. Sites pédagogiques universitaires français : Bibmath, Exo7 (math), Wikiversité, Khan Academy FR, Université en ligne.
2. Sites de fiches révision avec exos corrigés : fiches-bac.fr, kartable, schoolmouv, lelivrescolaire.
3. Cours en ligne ouverts (FUN, Coursera FR).
4. **À éviter** : sites de devoirs corrigés gratuits (« corrigé exo X »), forums de copie/triche, Stack Exchange (souvent en anglais).

## Description du besoin
{description_blocage}

## Format de sortie STRICT
Renvoie un objet JSON encadré par `<<<WEB_FOUND>>>` et `<<<END>>>`. Sortie minifiée sur une ligne :

```
<<<WEB_FOUND>>>{{"results":[{{"title":"<titre exact tel qu'on le voit sur la page>","url":"<URL complète>","source":"<nom du site/auteur>","why":"<1 phrase pour expliquer pourquoi cette ressource aide>","kind":"<exercice|cours|fiche|video|autre>"}}]}}<<<END>>>
J'ai trouvé X ressources externes : clique pour ouvrir.
```

Si rien de pertinent, `{{"results":[]}}` et une phrase pour dire pourquoi.
"""


@app.route("/api/web_search_exo", methods=["POST"])
def api_web_search_exo():
    """Recherche internet d'exos voisins / cours via Claude API web_search
    ou Gemini Search Grounding (Phase Z.9 A1).

    Body : ``{"description": "..."}``. Renvoie ``{found, results:
    [{title, url, source, why, kind}], engine}`` ou ``{found: false, reason}``.

    Restrictions engine : Claude API (api_anthropic) ou Gemini
    (gemini_api). Les autres engines retournent 400 avec message clair.
    """
    global _state
    body = request.get_json(silent=True) or {}
    description = (body.get("description") or "").strip()
    if not description:
        return jsonify({"error": "description manquante"}), 400

    # Phase Z.9.4 : body.force_engine permet au frontend de forcer le
    # moteur (bouton « Réessayer sur Claude API » dans la bulle d'erreur).
    forced_engine = body.get("force_engine")
    SUPPORTED_WEB = ("api_anthropic", "gemini_api")
    if forced_engine and forced_engine in SUPPORTED_WEB:
        engine = forced_engine
    else:
        engine = _read_engine_pref()
    if engine not in SUPPORTED_WEB:
        return jsonify({
            "error": "engine_unsupported",
            "detail": (
                f"La recherche internet n'est dispo que sur API Anthropic ou Gemini. "
                f"Moteur actuel : {engine}. Bascule via le sélecteur en haut."
            ),
            "engine": engine,
            "supported_engines": list(SUPPORTED_WEB),
        }), 400

    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409
    ctx = st.session_state.context
    matiere = (ctx.matiere or "").upper() or "?"

    sys_prompt = WEB_SEARCH_EXO_PROMPT.format(
        matiere=matiere, description_blocage=description,
    )
    # Phase v15.7.14 : query refined par Gemini Flash, transmise par le
    # frontend dans body.refined_query. Si présente, on l'ajoute comme
    # « hint » au sys_prompt pour orienter la recherche du LLM principal
    # vers les bons mots-clés. Sans ça, le LLM bricolait sa propre query
    # depuis la description verbeuse → souvent off-topic ou hallucinations.
    refined_query = (body.get("refined_query") or "").strip()
    if refined_query:
        sys_prompt += (
            "\n\n## QUERY DE RECHERCHE OPTIMISÉE\n"
            "Une requête courte et techniquement ciblée a été pré-formulée "
            "par un LLM dédié pour cette demande :\n"
            f"  → **{refined_query[:200]}**\n\n"
            "Utilise-la comme guide principal pour ta recherche internet "
            "(elle contient le jargon technique distinctif). Tu peux légèrement "
            "ajuster si tu vois mieux, mais reste centré sur ces mots-clés."
        )
    # Phase Z.9 : exclude_urls : URLs déjà vues dans la session, à éviter
    # au re-clic « Autre ressource ».
    excl = body.get("exclude_urls") or []
    if isinstance(excl, list) and excl:
        urls_str = "\n".join(f"  - {u}" for u in excl[:30] if isinstance(u, str))
        if urls_str:
            sys_prompt += (
                "\n\n## URLs déjà vues à éviter\n"
                "Ces URLs ont déjà été suggérées à l'étudiant :\n" + urls_str +
                "\n\nProposes-en de DIFFÉRENTES. Si rien d'autre de pertinent, "
                "renvoie `{\"results\":[]}` avec une `reason`."
            )
    # Pas de cours_root nécessaire (pas d'accès FS, pure recherche web).
    # Le mode importe peu : on passe MODE_COLLE pour ne pas activer Read/Grep.
    payload, used_engine, err_resp = _run_isolated_lookup(
        sys_prompt, "Lance la recherche.", "<<<WEB_FOUND>>>", "<<<END>>>",
        cours_root=None, mode_override=MODE_COLLE,
        engine_override=engine,  # forcer le moteur supporté
        enable_web_search=True,
        fallback_kind="web",  # Phase Z.9.3 : extrait URLs du raw si balise absente
    )
    if err_resp is not None:
        return err_resp
    results = payload.get("results") or []
    if not isinstance(results, list):
        results = []
    # Phase Z.9.1 : vérification anti-hallucination des URLs externes.
    # Le LLM (surtout Gemini sans grounding effectif) fabrique parfois
    # des URLs profondes plausibles mais inexistantes. On HEAD chaque URL.
    alive, dead_count = _filter_dead_urls(results, _verify_external_url)
    return jsonify({
        "found": bool(alive),
        "results": alive,
        "reason": payload.get("reason") or (
            f"Toutes les URLs ({dead_count}) renvoyées étaient mortes : "
            "probable hallucination du modèle. Réessaie ou bascule vers "
            "Claude API qui groundé mieux."
            if dead_count > 0 and not alive else None
        ),
        "dead_urls_filtered": dead_count,
        "engine": used_engine,
    })


# ============================================================ /api/find_youtube_video : Phase Z.9 (C3)
# Trouve une vidéo YouTube d'une chaîne éducative française qui explique
# le concept. Réutilise le même pipeline web search.

YOUTUBE_PROMPT = """Tu es un assistant qui trouve une vidéo YouTube éducative en **français** sur un concept précis pour un étudiant L1 Informatique-Électronique de l'ISTIC Rennes.

## RÈGLE INVIOLABLE : pas d'hallucination d'URLs
Tu DOIS impérativement utiliser ton outil de recherche internet (`web_search` côté Anthropic, `google_search` côté Gemini) avant de proposer une URL. Tu ne dois **JAMAIS** inventer un identifiant YouTube depuis ta connaissance interne. Les URLs YouTube ont la forme `https://www.youtube.com/watch?v=<ID>` où `<ID>` est unique et ne peut PAS être deviné.

Si ton tool de recherche ne retourne **aucun résultat pertinent** ou si tu n'as **pas accès au tool**, retourne `{{"results":[]}}` avec une `reason` honnête. Ne propose JAMAIS d'URL inventée.

## Méthode
1. Lance ta recherche avec une requête type `"<concept> YouTube cours" site:youtube.com` ou `"<chaîne préférée> <concept>"`. Utilise les chaînes à privilégier ci-dessous.
2. Pour chaque résultat candidat, vérifie que l'URL apparaît littéralement dans les résultats du tool (pas reconstruite à partir d'un titre).
3. Renvoie 1-3 vidéos **en français**, en copiant l'URL EXACTEMENT comme elle apparaît dans les résultats du tool.

## Chaînes à privilégier (par ordre)
- Yvan Monka, JeChercheUneOrange, Maths Adultes (math, logique)
- Heu?reka, Stupid Economics (sciences sociales / éco)
- Science Étonnante, Hygiène Mentale, Cocadmin (info / sciences)
- 3Blue1Brown FR, Numberphile FR (visualisation)
- Cours en ligne université/grandes écoles (CNAM, ENS, ENSL)

À ÉVITER : vidéos de devoirs corrigés type « correction exo X », vidéos en anglais (sauf si vraiment rien d'autre), vidéos très courtes < 3 min sans contenu.

## Description du concept à expliquer
{description}

## Format de sortie STRICT
```
<<<YT_FOUND>>>{{"results":[{{"title":"<titre exact>","url":"<URL YouTube vérifiée par le tool>","channel":"<nom de la chaîne>","why":"<1 phrase>"}}]}}<<<END>>>
```

Si rien de pertinent OU pas d'accès au tool : `{{"results":[],"reason":"<explication honnête>"}}`.
"""


@app.route("/api/find_youtube_video", methods=["POST"])
def api_find_youtube_video():
    """Trouve une vidéo YouTube éducative FR sur le concept (Phase Z.9 C3).

    Body : ``{"description": "..."}``. Mêmes contraintes engine que
    `/api/web_search_exo` (Claude API ou Gemini).
    """
    global _state
    body = request.get_json(silent=True) or {}
    description = (body.get("description") or "").strip()
    if not description:
        return jsonify({"error": "description manquante"}), 400

    # Phase Z.9.4 : force_engine pour bouton « Réessayer sur Claude API ».
    forced_engine = body.get("force_engine")
    SUPPORTED_WEB = ("api_anthropic", "gemini_api")
    if forced_engine and forced_engine in SUPPORTED_WEB:
        engine = forced_engine
    else:
        engine = _read_engine_pref()
    if engine not in SUPPORTED_WEB:
        return jsonify({
            "error": "engine_unsupported",
            "detail": (
                f"YouTube via web search n'est dispo que sur API Anthropic ou Gemini. "
                f"Moteur actuel : {engine}. Bascule via le sélecteur en haut."
            ),
            "engine": engine,
            "supported_engines": list(SUPPORTED_WEB),
        }), 400
    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409

    sys_prompt = YOUTUBE_PROMPT.format(description=description)
    # Phase v15.7.14 : query refined par Gemini Flash, transmise via
    # body.refined_query côté frontend. Hint au LLM pour la recherche
    # YouTube : utiliser ces mots-clés comme guide principal au lieu de
    # bricoler depuis la description verbeuse.
    refined_query = (body.get("refined_query") or "").strip()
    if refined_query:
        sys_prompt += (
            "\n\n## QUERY DE RECHERCHE OPTIMISÉE\n"
            "Une requête courte ciblée a été pré-formulée pour cette demande :\n"
            f"  → **{refined_query[:200]}**\n\n"
            "Utilise-la comme guide pour ta recherche YouTube (jargon technique "
            "distinctif). Tu peux légèrement ajuster, mais reste centré dessus."
        )
    excl = body.get("exclude_urls") or []
    if isinstance(excl, list) and excl:
        urls_str = "\n".join(f"  - {u}" for u in excl[:30] if isinstance(u, str))
        if urls_str:
            sys_prompt += (
                "\n\n## URLs déjà vues à éviter\n"
                "Ces vidéos ont déjà été suggérées :\n" + urls_str +
                "\n\nProposes-en de DIFFÉRENTES. Si rien d'autre, "
                "renvoie `{\"results\":[]}`."
            )
    payload, used_engine, err_resp = _run_isolated_lookup(
        sys_prompt, "Lance la recherche.", "<<<YT_FOUND>>>", "<<<END>>>",
        cours_root=None, mode_override=MODE_COLLE,
        engine_override=engine, enable_web_search=True,
        fallback_kind="youtube",  # Phase Z.9.3 : extrait URLs YT du raw si balise absente
    )
    if err_resp is not None:
        return err_resp
    results = payload.get("results") or []
    if not isinstance(results, list):
        results = []
    # Phase Z.9.1 : vérification oembed pour filtrer les videoIds inventés.
    alive, dead_count = _filter_dead_urls(results, _verify_youtube_url)
    return jsonify({
        "found": bool(alive),
        "results": alive,
        "reason": (
            f"Toutes les vidéos ({dead_count}) renvoyées étaient mortes : "
            "le modèle a probablement halluciné les videoIds. Réessaie, "
            "bascule sur Claude API (qui a un vrai web_search), ou "
            "cherche manuellement sur YouTube."
            if dead_count > 0 and not alive else None
        ),
        "dead_urls_filtered": dead_count,
        "engine": used_engine,
    })


# ============================================================ /api/refine_search_query : Phase v15.7.14
# Reformulation LLM d'une demande pédagogique en query de recherche
# externe optimisée. Force Gemini Flash (gemini-2.5-flash) pour la
# rapidité (~0.5-1.5s vs ~3-5s pour Opus / Pro) et la cohérence du
# wording technique. Coût négligeable : ~200 tokens in / 50 tokens out.
#
# Pourquoi pas le moteur courant ? Si l'utilisateur est sur Opus pour la
# colle, chaque click sur 🌐/🎬 paierait une requête Opus juste pour
# transformer une phrase en mots-clés : surcoût latence ET tokens
# pour un gain nul (Opus n'est pas meilleur que Flash sur cette tâche
# triviale). Forcer Flash garantit ~1s de latence quel que soit le moteur
# de la séance principale.

#: Phase v15.7.15, Étape 1/2 : infère le CONCEPT pédagogique sous-jacent
#: depuis la demande (qui peut contenir du jargon brut comme "COMP",
#: "S[1:0]"). Le LLM doit inférer ce que représente vraiment le composant
#: ou la notion, traduire les notations [N:M] en français pédagogique
#: (3 bits, 2 sorties), et estimer le niveau (lycée / L1 / L2 / prépa /
#: BTS) sans le hardcoder.
INFER_CONCEPT_PROMPT = """Tu es un assistant qui analyse une demande pédagogique pour en extraire le CONCEPT SOUS-JACENT.

L'INPUT est une phrase posée par un tuteur d'oral à un étudiant. Elle peut contenir des identifiants spécifiques au cours (COMP, MUX21, BAS3, etc.) ou des notations académiques brutes ([2:0], [1:0]) : ces noms sont propres à l'énoncé et n'ont aucun sens pour un moteur de recherche externe.

Ta tâche : INFÉRER le concept logique/mathématique général que cible la question, et le formuler en termes standards qu'un cours / un YouTuber pédagogique francophone utiliserait.

RÈGLES :
1. Si tu vois un identifiant non standard (COMP, MUX21, BAS, etc.), DEVINE le concept général (comparateur, multiplexeur, bascule…) à partir des indices contextuels (nombre d'entrées/sorties, vocabulaire associé, suite logique des questions).
2. Traduis les notations [N:M] en français pédagogique : `S[1:0]` → "2 sorties" ou "2 bits", `A[2:0]` → "3 entrées" ou "3 bits".
3. Estime le niveau pédagogique le plus probable (lycée / L1 / L2 / prépa / BTS / master) à partir des indices : complexité, vocabulaire, type de notation. NE HARDCODE PAS un niveau a priori : laisse les indices guider.
4. Si tu hésites entre plusieurs concepts (ex: COMP peut être comparateur ou compteur), liste-les tous dans `concept_alternatives` par ordre de probabilité.

FORMAT DE SORTIE STRICT :
<<<CONCEPT>>>{{"concept": "...", "concept_alternatives": ["...", "..."], "level": "...", "key_specs": "...", "domain": "..."}}<<<END>>>

Champs :
- `concept` : nom standard du concept en français (ex "comparateur 3 bits", "multiplexeur 2 vers 1", "fonction logique booléenne").
- `concept_alternatives` : 0 à 2 autres concepts plausibles si ambigu.
- `level` : un de {{"lycée", "L1", "L2", "L3", "prépa", "BTS", "master", "inconnu"}}.
- `key_specs` : specs techniques traduites en français (ex "3 entrées 2 sorties", "table de vérité à 8 lignes").
- `domain` : domaine large (ex "logique combinatoire", "circuits séquentiels", "analyse réelle", "topologie").

EXEMPLES :

Input : "Question 1.3 : analysez le composant COMP pour déterminer S[1:0] en fonction de A[2:0]. Établissez la table de vérité complète."
Output : <<<CONCEPT>>>{{"concept": "comparateur logique 3 bits", "concept_alternatives": ["codeur prioritaire 8 vers 3", "convertisseur de code"], "level": "L1", "key_specs": "3 entrées 2 sorties", "domain": "logique combinatoire"}}<<<END>>>

Input : "Donnez l'équation logique du MUX21 en fonction de SEL."
Output : <<<CONCEPT>>>{{"concept": "multiplexeur 2 vers 1", "concept_alternatives": [], "level": "L1", "key_specs": "2 entrées de données 1 sélecteur 1 sortie", "domain": "logique combinatoire"}}<<<END>>>

Input : "Démontrez que f est uniformément continue sur [a, b]."
Output : <<<CONCEPT>>>{{"concept": "continuité uniforme sur un compact", "concept_alternatives": ["théorème de Heine"], "level": "L2", "key_specs": "fonction continue intervalle fermé borné", "domain": "analyse réelle"}}<<<END>>>

DEMANDE PÉDAGOGIQUE À ANALYSER :
{description}
"""

#: Phase v15.7.15, Étape 2/2 : compose la query de recherche depuis le
#: concept inféré + specs en français + niveau pédagogique. Plus précis
#: qu'avant (v15.7.14) parce qu'il travaille sur du concept clean, pas
#: sur du jargon brut.
REFINE_SEARCH_QUERY_PROMPT = """Tu es un assistant qui compose une requête de recherche {target_label} optimisée à partir d'un concept pédagogique pré-analysé.

CONCEPT ANALYSÉ (output d'une étape précédente) :
- Concept principal : {concept}
- Concepts alternatifs : {concept_alts}
- Niveau pédagogique inféré : {level}
- Specs techniques : {key_specs}
- Domaine : {domain}

OUTPUT : UNE query principale de 4 à 10 mots + 2 à 3 alternatives, qui maximise les chances de matcher du contenu pertinent dans l'algo {target_label}.

RÈGLES STRICTES :
1. Utilise le `concept` français standard (PAS l'identifiant brut type COMP/MUX21 qui est propre à l'énoncé du cours).
2. Inclus si pertinent les `key_specs` en français (ex "3 bits", "2 sorties", "table de vérité 8 lignes") : JAMAIS la notation [N:M] qui ne matche rien sur YouTube/Google.
3. Calibre le vocabulaire selon le `level` :
   - lycée / BTS : termes simples, "exercice", "exemple"
   - L1 / L2 : termes universitaires standards, "cours", "fiche", "TD"
   - prépa : terminologie rigoureuse, "démonstration", "théorème"
   - master / inconnu : termes neutres, laisse à l'algo de matcher
4. Ajoute si pertinent un terme de contexte ({context_hints}).
5. Les alternatives doivent EXPLORER les concept_alternatives quand il y en a, ou varier l'angle (cours / exercice / vidéo / fiche).
6. Pas de ponctuation finale.

FORMAT DE SORTIE STRICT :
<<<REFINED>>>{{"query": "...", "alternatives": ["...", "..."]}}<<<END>>>

EXEMPLE 1 :
Concept : comparateur logique 3 bits / specs : 3 entrées 2 sorties / level : L1 / domain : logique combinatoire
Output : <<<REFINED>>>{{"query": "comparateur logique 3 bits cours table de vérité", "alternatives": ["circuit combinatoire 3 entrées 2 sorties exercice corrigé", "comparateur numérique table de vérité L1 électronique"]}}<<<END>>>

EXEMPLE 2 :
Concept : multiplexeur 2 vers 1 / specs : 2 entrées de données 1 sélecteur 1 sortie / level : L1 / domain : logique combinatoire
Output : <<<REFINED>>>{{"query": "multiplexeur 2 vers 1 équation logique booléenne", "alternatives": ["MUX 2:1 cours électronique numérique", "multiplexeur table de vérité explication"]}}<<<END>>>

QUERIES DÉJÀ ESSAYÉES À ÉVITER (propose des angles DIFFÉRENTS) :
{exclude_block}
"""


@app.route("/api/refine_search_query", methods=["POST"])
def api_refine_search_query():
    """Transforme une demande pédagogique en query de recherche optimisée
    via un workflow LLM 2-étapes (Phase v15.7.15).

    Body JSON :
        - description (str, obligatoire) : la description complète
          (output de _buildContextualExoDescription côté front).
        - target (str, "web" | "youtube", défaut "web") : pilote
          l'orientation de la query (jargon, type de contenu attendu).
        - exclude (list[str], optionnel) : queries déjà proposées à
          éviter (utilisé par le bouton 🔄 Reformuler côté front).

    Workflow interne (Phase v15.7.15 : 2 appels Gemini Flash successifs) :
        ÉTAPE 1, `INFER_CONCEPT_PROMPT` : analyse la demande, infère le
            concept logique sous-jacent (« comparateur 3 bits » au lieu
            de « COMP S[1:0] »), traduit les notations [N:M] en français,
            estime le niveau pédagogique sans hardcode. Output balisé
            `<<<CONCEPT>>>{json}<<<END>>>`.
        ÉTAPE 2, `REFINE_SEARCH_QUERY_PROMPT` : compose la query depuis
            le concept clean + specs + niveau. Plus précis que v15.7.14
            qui travaillait sur du jargon brut. Output balisé
            `<<<REFINED>>>{json}<<<END>>>`.

    Pourquoi 2 appels au lieu d'un :
        Le LLM ne mélange plus les responsabilités (analyse vs reformula-
        tion). Chaque étape a un prompt court et focalisé → meilleure
        qualité. Et la tâche d'inférence du concept (« COMP = comparateur
        ou compteur ? ») est explicite et auditable, pas masquée dans une
        chaîne de pensée. Coût : 2× ~$0.0001 = $0.0002 / recherche
        (négligeable). Latence : ~3s vs ~1.5s.

    Réponse 200 :
        {"query": "...", "alternatives": [...], "engine": "gemini_api",
         "model": "gemini-2.5-flash", "target": "...",
         "concept": "...", "level": "..."}  ← v15.7.15 : expose aussi
         le concept inféré et le level pour debug / affichage front.

    Codes :
        400 : description vide
        429 : quota Gemini épuisé (sur l'une ou l'autre étape)
        502 : pas de clé Gemini API ou erreur SDK ou réponse vide

    Phase v15.7.14 : moteur fixé à Gemini Flash.
    Phase v15.7.15 : workflow 2-étapes infer concept → compose query.
    """
    body = request.get_json(silent=True) or {}
    description = (body.get("description") or "").strip()
    if not description:
        return jsonify({"error": "description manquante"}), 400
    target = (body.get("target") or "web").strip().lower()
    if target not in ("web", "youtube"):
        target = "web"
    target_label = "YouTube" if target == "youtube" else "Google"
    context_hints = (
        '"vidéo cours", "explication", "exemple résolu" pour YouTube'
        if target == "youtube"
        else '"cours", "exercice corrigé", "fiche révision" pour Google'
    )

    excl = body.get("exclude") or []
    if isinstance(excl, list) and excl:
        excl_str = "\n".join(
            f"  - {q}" for q in excl[:10] if isinstance(q, str) and q.strip()
        )
        exclude_block = excl_str or "(aucune)"
    else:
        exclude_block = "(aucune)"

    # ÉTAPE 1 : Infer concept depuis la demande pédagogique brute
    infer_sys_prompt = INFER_CONCEPT_PROMPT.format(
        description=description[:3000],
    )
    concept_payload, used_engine_1, err_resp = _run_isolated_lookup(
        infer_sys_prompt,
        "Analyse.",
        "<<<CONCEPT>>>", "<<<END>>>",
        cours_root=None,
        mode_override=MODE_COLLE,
        engine_override="gemini_api",
        model_override="gemini-2.5-flash",
        enable_web_search=False,
    )
    if err_resp is not None:
        return err_resp
    concept = (concept_payload.get("concept") or "").strip()
    if not concept:
        return jsonify({
            "error": "reponse_vide",
            "step": "infer_concept",
            "engine": used_engine_1,
        }), 502
    concept_alts = concept_payload.get("concept_alternatives") or []
    if not isinstance(concept_alts, list):
        concept_alts = []
    concept_alts_str = ", ".join(
        str(a).strip() for a in concept_alts[:3] if isinstance(a, str) and a.strip()
    ) or "(aucun)"
    level = (concept_payload.get("level") or "inconnu").strip()
    key_specs = (concept_payload.get("key_specs") or "").strip() or "(non renseigné)"
    domain = (concept_payload.get("domain") or "").strip() or "(non renseigné)"

    # ÉTAPE 2 : Compose la query depuis le concept analysé
    refine_sys_prompt = REFINE_SEARCH_QUERY_PROMPT.format(
        target_label=target_label,
        context_hints=context_hints,
        exclude_block=exclude_block,
        concept=concept,
        concept_alts=concept_alts_str,
        level=level,
        key_specs=key_specs,
        domain=domain,
    )
    payload, used_engine_2, err_resp = _run_isolated_lookup(
        refine_sys_prompt,
        "Compose.",
        "<<<REFINED>>>", "<<<END>>>",
        cours_root=None,
        mode_override=MODE_COLLE,
        engine_override="gemini_api",
        model_override="gemini-2.5-flash",
        enable_web_search=False,
    )
    if err_resp is not None:
        return err_resp
    query = (payload.get("query") or "").strip()
    if not query:
        return jsonify({
            "error": "reponse_vide",
            "step": "compose_query",
            "engine": used_engine_2,
        }), 502
    alternatives = payload.get("alternatives") or []
    if not isinstance(alternatives, list):
        alternatives = []
    alternatives = [
        str(a).strip() for a in alternatives[:3]
        if isinstance(a, str) and a.strip()
    ]
    return jsonify({
        "query": query,
        "alternatives": alternatives,
        "engine": used_engine_2,
        "model": "gemini-2.5-flash",
        "target": target,
        # Phase v15.7.15 : expose le résultat de l'étape 1 pour debug /
        # affichage éventuel côté front (« reformulé via concept : … »).
        "concept": concept,
        "level": level,
    })


# ============================================================ /api/ocr_photo : Phase v15.7.20
# Pré-traitement OCR d'une photo via Gemini Flash 2.5 AVANT que le tuteur
# principal ne la voie. Le tuteur (souvent CLI subscription / Opus) est
# excellent pour le raisonnement pédagogique mais peut halluciner sur des
# objets structurés partiellement remplis (cas EN1 CC2 v15.7.19 : table
# avec colonne S vide validée à tort).
#
# Architecture (similaire à refine_search_query) :
# - Engine forcé = gemini_api + model = gemini-2.5-flash (~1-2s, ~$0.0001-0.0005).
# - Le LLM principal (tuteur) reçoit ensuite le bloc OCR injecté dans son
#   contexte ET fait sa propre lecture (§1.6 v0.5). En cas de divergence,
#   il signale à l'étudiant.
# - L'étudiant voit aussi l'OCR (collapsible côté front) → peut contester.

OCR_PHOTO_PROMPT = """Tu es un assistant OCR spécialisé dans la lecture précise des productions manuscrites d'étudiants.

INPUT : une photo d'un objet structuré (table de vérité, schéma logique, calcul posé, dessin, pseudo-code, équation algébrique, etc.) écrite à la main par l'étudiant.

OUTPUT : reproduction FIDÈLE et EXHAUSTIVE de ce qui est visible sur la photo, en Markdown.

RÈGLES STRICTES :

1. **Reproduis CASE PAR CASE / LIGNE PAR LIGNE** ce qui est effectivement visible. JAMAIS de complétion automatique.

2. **Marqueurs explicites pour les imperfections** :
   - Cellule vide d'un tableau : écris `(vide)` (pas un blanc, pas une valeur inférée).
   - Cellule illisible / floue / trop petite : écris `(illisible)`.
   - Cellule raturée : écris `(raturé : valeur originale → nouvelle valeur)` si possible, sinon `(raturé)`.
   - Photo coupée : signale dans `warnings` (« colonne 4 partiellement hors-cadre »).

3. **Préserve la structure** : tableau Markdown pour tables de vérité, ASCII art pour schémas si pertinent, ligne par ligne pour calculs avec retraits, équations en LaTeX inline (`$x^2$`).

4. **N'INFÉRE RIEN**. Si la colonne S d'une table de vérité est vide, dis-le. Si une connexion entre deux portes logiques manque sur un schéma, dis-le. Ne complète pas avec ce que tu attendrais : c'est exactement ce que cet endpoint cherche à éviter.

5. **`kind_detected`** : devine le type d'objet : `table_de_verite`, `schema_logique`, `calcul_pose`, `equation`, `dessin`, `pseudo_code`, `texte`, `autre`.

6. **`completeness_pct`** : estime grossièrement le % de complétude (cellules / éléments remplis vs total attendu). Pour une table de vérité 8 lignes × 4 colonnes (32 cellules) où colonne S vide → `completeness_pct: 75` (24/32).

FORMAT DE SORTIE STRICT :
<<<OCR>>>{{"ocr_markdown": "...", "kind_detected": "...", "completeness_pct": <int>, "warnings": ["...", "..."]}}<<<END>>>

Où `ocr_markdown` peut contenir des retours à la ligne (échappés `\\n` dans le JSON).

EXEMPLES :

Photo d'une table de vérité 8 lignes avec colonne S vide :
<<<OCR>>>{{"ocr_markdown": "| SEL | E0 | E1 | S |\\n|---|---|---|---|\\n| 0 | 0 | 0 | (vide) |\\n| 0 | 0 | 1 | (vide) |\\n| 0 | 1 | 0 | (vide) |\\n| 0 | 1 | 1 | (vide) |\\n| 1 | 0 | 0 | (vide) |\\n| 1 | 0 | 1 | (vide) |\\n| 1 | 1 | 0 | (vide) |\\n| 1 | 1 | 1 | (vide) |", "kind_detected": "table_de_verite", "completeness_pct": 75, "warnings": ["colonne S entièrement vide"]}}<<<END>>>

Photo d'une équation manuscrite :
<<<OCR>>>{{"ocr_markdown": "$S = E_0 \\\\cdot \\\\overline{{SEL}} + E_1 \\\\cdot SEL$", "kind_detected": "equation", "completeness_pct": 100, "warnings": []}}<<<END>>>

Photo d'un calcul posé incomplet :
<<<OCR>>>{{"ocr_markdown": "Ligne 1 : 245 × 13\\nLigne 2 : 245 × 3 = 735\\nLigne 3 : 245 × 10 = (vide)\\nLigne 4 : Total = (vide)", "kind_detected": "calcul_pose", "completeness_pct": 50, "warnings": ["lignes 3-4 non complétées"]}}<<<END>>>

HINT CONTEXTUEL (optionnel, ce que le tuteur attendait) :
{hint}

Maintenant, analyse la photo qui suit et applique le protocole strict.
"""


@app.route("/api/ocr_photo", methods=["POST"])
def api_ocr_photo():
    """Pré-traite une photo via Gemini Flash 2.5 (Phase v15.7.20).

    Body JSON :
        - attachment_id (str, obligatoire) : id d'une entry dans
          _state.pending_attachments (doit être is_image=True).
        - hint (str, optionnel) : contexte de ce qui est attendu, ex
          « table de vérité du MUX21 8 lignes », passé au prompt OCR
          pour orienter le `kind_detected`.

    Réponse 200 :
        {ocr_markdown, kind_detected, completeness_pct, warnings,
         engine: "gemini_api", model: "gemini-2.5-flash"}

    Codes :
        400 : attachment_id manquant / pas une image
        404 : attachment_id introuvable dans pending_attachments
        409 : pas de session active
        429/502 : quota Gemini / SDK error / réponse vide

    Phase v15.7.20 : engine forcé Gemini Flash (cf. README §choix
    Gemini Flash en v15.7.14, mêmes raisons : latence, coût, cohérence).
    """
    body = request.get_json(silent=True) or {}
    att_id = (body.get("attachment_id") or "").strip()
    hint = (body.get("hint") or "(aucun hint fourni : détecte toi-même le type d'objet)").strip()
    if not att_id:
        return jsonify({"error": "attachment_id manquant"}), 400

    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409
    with st.lock:
        target = next(
            (a for a in st.pending_attachments if a.get("id") == att_id),
            None,
        )
    if target is None:
        return jsonify({"error": "attachement introuvable"}), 404
    if not target.get("is_image"):
        return jsonify({"error": "OCR réservé aux images"}), 400

    rel_path = target["rel_path"]
    storage = target.get("storage") or "uploads"
    base_root = UPLOADS_DIR if storage == "uploads" else COURS_ROOT
    try:
        abs_path = (base_root / rel_path).resolve()
        abs_path.relative_to(base_root.resolve())
    except (ValueError, OSError):
        return jsonify({"error": f"path hors {storage}: {rel_path}"}), 400
    if not abs_path.is_file():
        return jsonify({"error": f"fichier absent: {abs_path.name}"}), 404
    sys_prompt = OCR_PHOTO_PROMPT.format(hint=hint[:500])
    # Phase A.10.13.bug3 : path absolu pour court-circuiter la résolution
    # cours_root dans `_extract_inline_images` (sinon storage="uploads"
    # résolu sous COURS_ROOT → image introuvable → Gemini hallucine).
    user_msg = f"Voici la photo à analyser :\n\n![photo]({abs_path.as_posix()})"

    payload, used_engine, err_resp = _run_isolated_lookup(
        sys_prompt, user_msg,
        "<<<OCR>>>", "<<<END>>>",
        cours_root=COURS_ROOT,  # legacy ; non utilisé (path absolu)
        mode_override=MODE_COLLE,
        engine_override="gemini_api",
        model_override="gemini-2.5-flash",
        enable_web_search=False,
    )
    if err_resp is not None:
        return err_resp
    ocr_markdown = (payload.get("ocr_markdown") or "").strip()
    if not ocr_markdown:
        return jsonify({
            "error": "reponse_vide",
            "engine": used_engine,
        }), 502
    kind_detected = (payload.get("kind_detected") or "autre").strip()
    completeness_pct = payload.get("completeness_pct")
    if not isinstance(completeness_pct, (int, float)):
        completeness_pct = None
    else:
        completeness_pct = int(completeness_pct)
    warnings_list = payload.get("warnings") or []
    if not isinstance(warnings_list, list):
        warnings_list = []
    warnings_list = [
        str(w).strip() for w in warnings_list[:10]
        if isinstance(w, str) and w.strip()
    ]
    return jsonify({
        "ocr_markdown": ocr_markdown,
        "kind_detected": kind_detected,
        "completeness_pct": completeness_pct,
        "warnings": warnings_list,
        "engine": used_engine,
        "model": "gemini-2.5-flash",
        "attachment_id": att_id,
    })


# ============================================================ Verify URLs (Phase Z.9.1)
# Anti-hallucination : les LLMs (surtout Gemini sans grounding effectif)
# adorent fabriquer des `videoId` YouTube plausibles ou des URLs
# profondes inventées. On vérifie côté backend AVANT de retourner les
# résultats au frontend. URLs mortes filtrées, frontend warning si on
# a tout drop.

_YT_ID_RE = re.compile(r"(?:v=|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})")
_VERIFY_TIMEOUT_S = 5.0
_VERIFY_USER_AGENT = "BotGSTAR-Compagnon/1.0 (verify-url; +gaylordaboeka@gmail.com)"


def _verify_youtube_url(url: str) -> bool:
    """Retourne True si la vidéo YouTube existe (oembed 200 OK).

    Endpoint oembed officiel : ``https://www.youtube.com/oembed?url=…&format=json``
    - 200 + JSON = vidéo publique et live
    - 401 / 404 = vidéo supprimée, privée, ou ID inventé
    - autres = transitoire (rate limit, géo) → on garde par défaut
    """
    import urllib.error
    import urllib.parse
    import urllib.request
    if not isinstance(url, str) or "youtube.com" not in url and "youtu.be" not in url:
        return False
    if not _YT_ID_RE.search(url):
        return False
    oembed_url = (
        "https://www.youtube.com/oembed?"
        + urllib.parse.urlencode({"url": url, "format": "json"})
    )
    try:
        req = urllib.request.Request(
            oembed_url,
            headers={"User-Agent": _VERIFY_USER_AGENT, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=_VERIFY_TIMEOUT_S) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        # 401/404 = vidéo supprimée / ID inventé
        if e.code in (401, 404):
            return False
        # Autres codes = on garde par défaut (rate limit, etc.)
        return True
    except Exception:  # noqa: BLE001 (réseau, timeout, etc.)
        # Erreur réseau = on garde par défaut (faux positif moins grave
        # que faux négatif). L'utilisateur jugera au clic.
        return True


def _verify_external_url(url: str) -> bool:
    """Retourne True si l'URL répond avec un statut < 400 sur HEAD.

    Tolérant sur les erreurs ponctuelles (timeout, 5xx) : on garde
    True par défaut, le user verra au clic.

    Phase Z.9.4 : durci sur DNS, si le domaine ne résout pas
    (`gaierror` / "Name or service not known" / "getaddrinfo failed"),
    on retourne False car le site n'existe pas (probable hallucination
    du LLM qui a fabriqué un domaine plausible).
    """
    import socket
    import urllib.error
    import urllib.request
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return False
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(
                url, method=method,
                headers={"User-Agent": _VERIFY_USER_AGENT},
            )
            with urllib.request.urlopen(req, timeout=_VERIFY_TIMEOUT_S) as resp:
                return resp.status < 400
        except urllib.error.HTTPError as e:
            if e.code == 405 and method == "HEAD":
                continue  # essai GET
            if 400 <= e.code < 500:
                return False
            return True  # 5xx = transitoire, on garde
        except urllib.error.URLError as e:
            # Phase Z.9.4 : DNS failure = domaine inexistant.
            reason = getattr(e, "reason", None)
            if isinstance(reason, socket.gaierror):
                return False
            reason_str = str(reason).lower() if reason else ""
            if (
                "getaddrinfo" in reason_str
                or "name or service not known" in reason_str
                or "no address associated" in reason_str
                or "nodename" in reason_str  # macOS variant
            ):
                return False
            # Autres URLError (timeout, refus connexion ponctuel) :
            # on garde True par défaut sauf pour HEAD qui essaie GET.
            if method == "HEAD":
                continue
            return True
        except socket.gaierror:
            return False
        except Exception:  # noqa: BLE001
            if method == "HEAD":
                continue
            return True
    return True


def _filter_dead_urls(results: list, verify_fn) -> tuple[list, int]:
    """Vérifie les URLs en parallèle et retourne (alive_results, dead_count).

    `verify_fn` : callback bool(url) (cf. _verify_youtube_url / _verify_external_url).
    Concurrent 4 workers : bonus latence ~3-5× sur 1-3 URLs.
    """
    from concurrent.futures import ThreadPoolExecutor
    if not results:
        return ([], 0)
    urls = [(i, (r.get("url") or "") if isinstance(r, dict) else "") for i, r in enumerate(results)]
    alive = [True] * len(results)
    with ThreadPoolExecutor(max_workers=4) as ex:
        for i, ok in zip(
            (i for i, _ in urls),
            ex.map(verify_fn, [u for _, u in urls], timeout=_VERIFY_TIMEOUT_S * 2),
        ):
            alive[i] = bool(ok)
    kept = [r for r, a in zip(results, alive) if a]
    return (kept, len(results) - len(kept))


# ============================================================ Helper isolé Phase Z.9 : _run_isolated_lookup
# Factorisation du pattern « lance UN ClaudeClient jetable, parse une
# balise <<<TAG>>>{json}<<<END>>>, retourne dict ou erreur Flask ».
# Utilisé par api_find_similar_exo, api_find_cm_passage,
# api_web_search_exo, api_find_youtube_video.

def _run_isolated_lookup(
    sys_prompt: str,
    user_msg: str,
    open_tag: str,
    close_tag: str,
    cours_root: Optional[Path] = None,
    mode_override: Optional[str] = None,
    engine_override: Optional[str] = None,
    model_override: Optional[str] = None,  # Phase v15.7.14
    enable_web_search: bool = False,
    fallback_kind: Optional[str] = None,  # Phase Z.9.3 : "youtube" | "web" | None
):
    """Lance un ClaudeClient jetable, parse la balise, retourne payload + engine.

    Returns tuple (payload_dict, engine_str, error_response_or_None).
    Si error_response_or_None est non-None, le caller doit le retourner direct.

    Phase v15.7.14 : ``model_override`` permet de forcer un modèle précis
    indépendamment de l'engine pref (utilisé par /api/refine_search_query
    pour forcer Gemini Flash même si l'utilisateur est sur Opus).
    """
    engine = engine_override or _read_engine_pref()
    mode = mode_override
    if mode is None:
        mode = MODE_GUIDE if cours_root is not None else MODE_COLLE
    try:
        client_kwargs = dict(
            engine=engine, system_prompt=sys_prompt, mode=mode,
            cours_root=cours_root,
        )
        if model_override:
            client_kwargs["model"] = model_override
        client = ClaudeClient(**client_kwargs)
    except ValueError as e:
        return ({}, engine, (jsonify({
            "error": "engine invalide", "detail": str(e),
        }), 500))
    if enable_web_search:
        # Marqueur que le client peut utiliser pour activer le tool
        # web_search natif (Anthropic) ou Search Grounding (Gemini).
        # Géré dans claude_client._stream_via_api / _stream_via_gemini
        # via inspection de cet attribut.
        try:
            client.set_enable_web_search(True)
        except AttributeError:
            # ClaudeClient n'a pas encore l'API : on continue sans
            # (le LLM peut quand même renvoyer un résultat plausible
            # depuis sa connaissance interne, qui sera moins fiable
            # mais utile en fallback).
            logger.info(
                "engine=%s ne supporte pas enable_web_search, fallback "
                "knowledge interne", engine,
            )
    client.append_user_message(user_msg)
    try:
        client.stream_response(on_event=lambda _ev: None)
    except ClaudeQuotaExhaustedError as e:
        return ({}, engine, (jsonify({
            "error": "quota_exhausted", "detail": str(e)[:300], "engine": engine,
        }), 429))
    except ClaudeClientError as e:
        return ({}, engine, (jsonify({
            "error": "claude_error", "detail": str(e)[:300], "engine": engine,
        }), 502))
    history = client.history
    if not history or history[-1].get("role") != "assistant":
        return ({}, engine, (jsonify({"error": "reponse_vide"}), 502))
    raw = (history[-1].get("content") or "").strip()
    import re as _re
    m = _re.search(
        re.escape(open_tag) + r"(.*?)" + re.escape(close_tag),
        raw, _re.DOTALL,
    )
    if not m:
        # Phase Z.9.3 : fallback si le LLM ne respecte pas le format
        # balisé, essaye d'extraire les URLs du texte brut directement.
        # Mieux qu'une erreur cryptique pour l'utilisateur.
        logger.warning(
            "balise_absente (engine=%s, open=%s) : raw[:300]: %s",
            engine, open_tag, raw[:300].replace("\n", " "),
        )
        if fallback_kind == "youtube":
            payload = _fallback_extract_youtube(raw)
            if payload is not None:
                logger.info("Fallback YT extrait %d URLs depuis raw", len(payload.get("results", [])))
                return (payload, engine, None)
        elif fallback_kind == "web":
            payload = _fallback_extract_web(raw)
            if payload is not None:
                logger.info("Fallback web extrait %d URLs depuis raw", len(payload.get("results", [])))
                return (payload, engine, None)
        return ({}, engine, (jsonify({
            "error": "balise_absente",
            "detail": raw[:500],
            "engine": engine,
            "hint": (
                "Le moteur n'a pas suivi le format de sortie demandé. "
                "Réessaie ou bascule sur un autre moteur (Claude API recommandé)."
            ),
        }), 502))
    try:
        payload = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        return ({}, engine, (jsonify({
            "error": "json_invalide", "detail": f"{e}: {m.group(1)[:300]}",
            "engine": engine,
        }), 502))
    return (payload, engine, None)


# ============================================================ Fallback URL extraction (Phase Z.9.3)
# Quand le LLM ne respecte pas le format <<<TAG>>>{json}<<<END>>>, on
# extrait directement les URLs du texte brut + on récupère les méta
# (titre, channel) via oembed YouTube ou heuristique pour le web.

_FALLBACK_YT_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/watch\?[^\s)\]'\"<>]*?v=|youtu\.be/)"
    r"([a-zA-Z0-9_-]{11})"
)
_FALLBACK_HTTP_URL_RE = re.compile(
    r"https?://[^\s)\]'\"<>]+",
)


def _fallback_extract_youtube(raw: str) -> Optional[dict]:
    """Extrait les URLs YouTube uniques du raw + récupère titre/channel
    via oembed. Retourne ``{"results": [...]}`` ou None si rien trouvé.
    """
    seen = set()
    urls_in_order = []
    for m in _FALLBACK_YT_URL_RE.finditer(raw):
        vid = m.group(1)
        if vid in seen:
            continue
        seen.add(vid)
        urls_in_order.append(f"https://www.youtube.com/watch?v={vid}")
    if not urls_in_order:
        return None
    results = []
    for url in urls_in_order[:5]:  # cap pour éviter une avalanche
        meta = _youtube_oembed_meta(url)
        if meta is None:
            continue  # vidéo morte ou inaccessible : skip
        # Cherche un contexte explicatif dans le raw (~200 chars autour)
        idx = raw.find(url)
        why = ""
        if idx >= 0:
            window = raw[max(0, idx - 250):idx + len(url) + 250]
            # Nettoie le markdown lourd, garde 1-2 phrases
            window = re.sub(r"\s+", " ", window).strip()
            why = window[:300]
        results.append({
            "title": meta.get("title", "Vidéo YouTube"),
            "url": url,
            "channel": meta.get("author_name", ""),
            "why": why,
        })
    return {"results": results}


def _youtube_oembed_meta(url: str) -> Optional[dict]:
    """Hit oembed pour récupérer ``{title, author_name}``. None si mort."""
    import urllib.error
    import urllib.parse
    import urllib.request
    oe = ("https://www.youtube.com/oembed?"
          + urllib.parse.urlencode({"url": url, "format": "json"}))
    try:
        req = urllib.request.Request(
            oe, headers={"User-Agent": _VERIFY_USER_AGENT, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=_VERIFY_TIMEOUT_S) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 (réseau, 4xx, etc.)
        pass
    return None


def _fallback_extract_web(raw: str) -> Optional[dict]:
    """Extrait les URLs HTTP non-YouTube uniques du raw. Pas de méta :
    on retourne juste l'URL et un titre heuristique (le domaine + slug).
    """
    seen = set()
    urls = []
    for m in _FALLBACK_HTTP_URL_RE.finditer(raw):
        u = m.group(0).rstrip(".,;:!?")  # nettoie ponctuation finale
        if u in seen:
            continue
        if "youtube.com" in u or "youtu.be" in u:
            continue  # exclu, géré par fallback YouTube
        seen.add(u)
        urls.append(u)
    if not urls:
        return None
    results = []
    for url in urls[:8]:
        # Heuristique : titre = domaine + dernier segment du path
        try:
            from urllib.parse import urlparse
            p = urlparse(url)
            host = p.netloc.replace("www.", "")
            slug = (p.path or "/").rstrip("/").rsplit("/", 1)[-1] or host
            title = f"{slug} ({host})"
        except Exception:  # noqa: BLE001
            title = url
        idx = raw.find(url)
        why = ""
        if idx >= 0:
            window = raw[max(0, idx - 200):idx + len(url) + 200]
            why = re.sub(r"\s+", " ", window).strip()[:250]
        results.append({
            "title": title,
            "url": url,
            "source": "",
            "kind": "autre",
            "why": why,
        })
    return {"results": results}


def _resolve_exo_files(
    matiere: str, type_code: str, num: str, exo: Optional[str] = None,
    annee: Optional[str] = None,
) -> dict:
    """Résout les chemins PDF d'un exercice référencé par (matière, type,
    num, exo). Helper transverse Phase Z.8.8 : utilisé par
    /api/find_similar_exo et réutilisable par les futures fonctionnalités
    qui réfèrent un fichier dans COURS/.

    Retourne un dict ::

        {
          "enonce_pdf_path": "EN1/CC/CC1/enonce_CC1_EN1.pdf"  # ou None
                              # (relatif à COURS_ROOT, prêt pour
                              # /api/cours_file?path=…)
          "correction_pdf_paths": [                           # liste, vide si rien
            "EN1/CC/CC1/corrections/correction_CC1_EN1_ex1.pdf",
            "EN1/CC/CC1/corrections/correction_CC1_EN1_ex2.pdf",
          ]
        }

    Tolérant : ne lève jamais. Si un fichier n'existe pas → None / [].
    """
    matiere = (matiere or "").upper()
    type_code = (type_code or "").upper()
    num = str(num or "")
    if not matiere or not type_code or not num:
        return {"enonce_pdf_path": None, "correction_pdf_paths": []}

    enonce_rel: Optional[str] = None
    corrections_rel: list[str] = []
    try:
        enonce_path = find_enonce_pdf(COURS_ROOT, matiere, type_code, num, annee)
        if enonce_path is not None:
            try:
                enonce_rel = enonce_path.relative_to(COURS_ROOT).as_posix()
            except ValueError:
                enonce_rel = None
    except Exception as e:  # noqa: BLE001 (tolérant)
        logger.debug("find_enonce_pdf a levé pour %s %s%s : %s",
                     matiere, type_code, num, e)

    if exo:
        try:
            corrs = resolve_corrections(
                COURS_ROOT, matiere, type_code, num, str(exo), annee,
            )
            for p in corrs or []:
                try:
                    corrections_rel.append(p.relative_to(COURS_ROOT).as_posix())
                except ValueError:
                    pass
        except Exception as e:  # noqa: BLE001 (tolérant)
            logger.debug(
                "resolve_corrections a levé pour %s %s%s ex %s : %s",
                matiere, type_code, num, exo, e,
            )

    return {
        "enonce_pdf_path": enonce_rel,
        "correction_pdf_paths": corrections_rel,
    }


def _run_rewrite_on_engine(engine: str, user_msg: str) -> str:
    """Exécute un rewrite sur un moteur donné. Retourne le texte nettoyé.

    Lève ``ClaudeQuotaExhaustedError`` si solde insuffisant / quota
    épuisé, ``ClaudeClientError`` si autre erreur SDK, ``ValueError``
    si l'engine n'est pas supporté.

    Mode COLLE = pas d'accès FS, pas de tools. Le mini-prompt système
    isole ce client de la doctrine pédagogique COMPAGNON/LECTURE.
    """
    client = ClaudeClient(
        engine=engine,
        system_prompt=REWRITE_SYSTEM_PROMPT,
        mode=MODE_COLLE,
    )
    client.append_user_message(user_msg)
    # No-op listener : le parser stream les TEXT_DELTA, on collecte le raw
    # via client.history (qui reçoit le message complet en fin de
    # stream_response). Pas besoin du streaming SSE pour un rewrite
    # one-shot : l'utilisateur attend ~1-3 s, c'est OK bloquant.
    client.stream_response(on_event=lambda _ev: None)
    history = client.history
    if not history or history[-1].get("role") != "assistant":
        return ""
    rewritten = (history[-1].get("content") or "").strip()
    # Strip de guillemets enveloppants éventuellement laissés par le modèle
    # malgré la consigne explicite. Cas observés : « …» en français,
    # "…" anglais, '…' simples.
    for opener, closer in (('"', '"'), ("'", "'"), ("«", "»")):
        # >=2 (et pas >2) : un cas pathologique '""' a un contenu vide, on
        # retourne "" et le caller décide quoi faire (essayer le moteur
        # suivant ou retourner 502).
        if rewritten.startswith(opener) and rewritten.endswith(closer) and len(rewritten) >= 2:
            rewritten = rewritten[len(opener):-len(closer)].strip()
            break
    return rewritten


@app.route("/api/apply_edit", methods=["POST"])
def api_apply_edit():
    """Applique une suggestion de correction (Phase A.7 lecture).

    Body JSON :
        {
          "file": "AN1/TD/TD5/scripts_oraux/SCRIPT_AN1_TD5_global.md",
          "before": "<texte exact à remplacer>",
          "after": "<nouveau texte>"
        }

    Sécurités :
    - chemin **relatif**, no traversal, doit résoudre sous COURS_ROOT
    - extension whitelist : ``.md``, ``.txt`` (les .pdf ne sont pas
      éditables, seul l'étudiant peut éditer ses fichiers persos)
    - ``before`` doit apparaître **une seule fois** dans le fichier
    - backup ``.bak`` créé à côté du fichier avant l'écriture atomique
    """
    body = request.get_json(silent=True) or {}
    file_rel = body.get("file")
    before = body.get("before")
    after = body.get("after")
    if not isinstance(file_rel, str) or not isinstance(before, str) or not isinstance(after, str):
        return jsonify({"error": "champs file/before/after string requis"}), 400
    if not before:
        return jsonify({"error": "before vide"}), 400
    if before == after:
        return jsonify({"error": "before == after, edit no-op"}), 400

    # Validation chemin
    norm = file_rel.replace("\\", "/")
    if norm.startswith("/") or len(norm) > 2 and norm[1] == ":":
        return jsonify({"error": "chemin absolu interdit"}), 400
    if ".." in Path(norm).parts:
        return jsonify({"error": "traversal '..' interdit"}), 400

    target = (COURS_ROOT / norm).resolve()
    try:
        target.relative_to(COURS_ROOT.resolve())
    except ValueError:
        return jsonify({"error": "chemin hors COURS_ROOT"}), 400

    if target.suffix.lower() not in (".md", ".txt"):
        return jsonify({
            "error": f"extension non éditable : {target.suffix} "
                     "(seuls .md et .txt sont éditables)"
        }), 400

    if not target.is_file():
        return jsonify({"error": "fichier introuvable"}), 404

    try:
        original = target.read_text(encoding="utf-8")
    except OSError as e:
        return jsonify({"error": f"lecture impossible : {e}"}), 500

    occurrences = original.count(before)
    if occurrences == 0:
        return jsonify({
            "error": "before introuvable dans le fichier (texte modifié entre-temps ?)"
        }), 422
    if occurrences > 1:
        return jsonify({
            "error": f"before présent {occurrences} fois (ambigu) : élargir le contexte"
        }), 422

    # Backup .bak
    backup = target.with_suffix(target.suffix + ".bak")
    try:
        backup.write_bytes(target.read_bytes())
    except OSError as e:
        logger.warning("Backup .bak echoue (continue quand meme) : %s", e)

    # Atomic write (avec retry Phase Z.8.7 sur les locks OneDrive Windows)
    new_content = original.replace(before, after, 1)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        tmp.write_text(new_content, encoding="utf-8")
        from utils import _replace_with_retry
        _replace_with_retry(tmp, target)
    except OSError as e:
        return jsonify({"error": f"écriture impossible : {e}"}), 500

    logger.info(
        "Edit applique : %s (-%d +%d chars)",
        norm, len(before), len(after),
    )
    return jsonify({
        "ok": True,
        "file": norm,
        "backup": backup.name,
        "delta_chars": len(after) - len(before),
    })


@app.route("/api/cours_file", methods=["GET"])
def api_cours_file():
    """Sert un fichier de COURS/ pour affichage inline dans la chat UI.

    Utilisé par le rendu d'images dans les réponses Compagnon
    (`![alt](path)` Markdown → `<img src="/api/cours_file?path=...">`).

    Sécurité : `path` doit résoudre **strictement sous COURS_ROOT**.
    Whitelist d'extensions : png, jpg, jpeg, webp, gif, svg, pdf.
    """
    rel = request.args.get("path", "").strip()
    if not rel:
        return jsonify({"error": "param 'path' manquant"}), 400
    # Empêche les chemins absolus (Linux ou Windows) et les .. naïfs
    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        return jsonify({"error": "chemin invalide"}), 400
    target = (COURS_ROOT / rel_path).resolve()
    try:
        target.relative_to(COURS_ROOT.resolve())
    except ValueError:
        return jsonify({"error": "hors COURS_ROOT"}), 403
    if not target.is_file():
        return jsonify({"error": "fichier introuvable"}), 404
    ext = target.suffix.lower().lstrip(".")
    if ext not in {"png", "jpg", "jpeg", "webp", "gif", "svg", "pdf"}:
        return jsonify({"error": f"extension non servable : {ext}"}), 415
    mime_map = {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "webp": "image/webp", "gif": "image/gif",
        "svg": "image/svg+xml", "pdf": "application/pdf",
    }
    return send_file(str(target), mimetype=mime_map[ext])


@app.route("/api/upload_file", methods=["GET"])
def api_upload_file():
    """Phase A.10.2 : sert un fichier de `_uploads/{session_id}/...` pour
    affichage inline dans la chat UI. Pendant de `/api/cours_file` qui sert
    depuis COURS_ROOT.

    Sécurité : `path` doit résoudre **strictement sous UPLOADS_DIR**. Pas
    de chemins absolus, pas de `..`. Whitelist d'extensions identique à
    `/api/cours_file` (png/jpg/jpeg/webp/gif/svg/pdf).
    """
    rel = request.args.get("path", "").strip()
    if not rel:
        return jsonify({"error": "param 'path' manquant"}), 400
    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        return jsonify({"error": "chemin invalide"}), 400
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    target = (UPLOADS_DIR / rel_path).resolve()
    try:
        target.relative_to(UPLOADS_DIR.resolve())
    except ValueError:
        return jsonify({"error": "hors UPLOADS_DIR"}), 403
    if not target.is_file():
        return jsonify({"error": "fichier introuvable"}), 404
    ext = target.suffix.lower().lstrip(".")
    if ext not in {"png", "jpg", "jpeg", "webp", "gif", "svg", "pdf"}:
        return jsonify({"error": f"extension non servable : {ext}"}), 415
    mime_map = {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "webp": "image/webp", "gif": "image/gif",
        "svg": "image/svg+xml", "pdf": "application/pdf",
    }
    return send_file(str(target), mimetype=mime_map[ext])


_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "heic", "gif", "svg", "bmp", "tiff"}
_DOC_EXTS = {"pdf", "doc", "docx", "xls", "xlsx", "csv", "txt", "md", "json", "ppt", "pptx"}


def _attachment_target_dir(session_id: str, is_image: bool) -> Path:
    """Phase A.10.2 : routage des uploads de séance vers UPLOADS_DIR.

    Avant A.10.2, les pièces jointes étaient stockées sous
    ``COURS/{MAT}/{TYPE}/{TYPE}{N}/{photos|attachments}/``. Friction
    user : *« c'est débile que les photos soit dans COURS/ car tout ne
    concerne pas les cours »* (sessions Sujet libre / Workspace ne
    sont pas liées à un exo COURS). Tout migre vers
    ``Compagnon_Revision/_uploads/{session_id}/{photos|attachments}/``.

    Bonus : un cleanup futur peut purger un dossier ``_uploads/<id>/``
    entier en une op (équivalent du DELETE de session côté
    `/api/sessions/<id>`). Aujourd'hui : best-effort, on garde les
    fichiers même si la session JSON est supprimée.
    """
    subfolder = "photos" if is_image else "attachments"
    return UPLOADS_DIR / session_id / subfolder


def _safe_filename(raw: str, fallback_ext: str = "bin") -> tuple[str, str]:
    """Sanitize un nom de fichier pour write disque. Retourne (stem, ext)."""
    raw = (raw or "").strip()
    # Garde uniquement caractères alphanum + _ - + .
    cleaned = "".join(c if (c.isalnum() or c in "_-+.") else "_" for c in raw)
    if not cleaned or cleaned == ".":
        cleaned = f"attachment.{fallback_ext}"
    p = Path(cleaned)
    stem = p.stem or "attachment"
    ext = p.suffix.lstrip(".").lower() or fallback_ext
    return stem, ext


@app.route("/api/upload_attachment", methods=["POST"])
def api_upload_attachment():
    """Upload générique d'une pièce jointe (image, PDF, Excel, audio, …).

    Sauvegarde dans ``COURS/{MAT}/{TYPE}/{TYPE}{N}/{photos|attachments}/``
    selon la nature (image vs autre). Push dans ``pending_attachments``
    pour que le prochain ``send_message`` l'attache au texte envoyé au
    tuteur.
    """
    global _state
    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409

    f = (request.files.get("file")
         or request.files.get("attachment")
         or request.files.get("photo"))
    if f is None or not f.filename:
        return jsonify({"error": "champ 'file' manquant"}), 400
    # `staged=1` → ne push PAS dans pending_attachments (le caller veut
    # juste un upload sans queue, ex: bouton 📎 pendant l'édition d'un
    # message qui inject le markdown directement dans le textarea).
    staged = (
        (request.form.get("staged") or request.args.get("staged") or "")
        .strip().lower() in ("1", "true", "yes")
    )

    raw_name = f.filename or ""
    ext_from_name = Path(raw_name).suffix.lower().lstrip(".")
    is_image = (
        ext_from_name in _IMAGE_EXTS
        or (f.mimetype and f.mimetype.startswith("image/"))
    )

    session_id = st.session_state.data.get("session_id") or "_no_session_id_"
    target_dir = _attachment_target_dir(session_id, is_image)
    target_dir.mkdir(parents=True, exist_ok=True)

    stem, ext = _safe_filename(raw_name, fallback_ext=("jpg" if is_image else "bin"))
    # Trouve le prochain `_vN` libre pour éviter overwrite
    v = 1
    while (target_dir / f"{stem}_v{v}.{ext}").exists():
        v += 1
    out_path = target_dir / f"{stem}_v{v}.{ext}"
    f.save(str(out_path))

    # Phase A.10.2 : rel_path est désormais relatif à UPLOADS_DIR (pas
    # COURS_ROOT). Format : "{session_id}/photos/{filename_vN.ext}".
    # Le markdown injecté dans le user message utilise le préfixe
    # `_uploads/` (cf. api_send_message) pour que le renderMarkdown
    # frontend route vers /api/upload_file. Le champ `storage="uploads"`
    # marque cette entry comme nouveau-schéma (vs "cours" legacy).
    rel_path = out_path.relative_to(UPLOADS_DIR).as_posix()
    att_id = f"att_{uuid.uuid4().hex[:10]}"
    from utils import now_iso as _now_iso
    att = {
        "id": att_id,
        "rel_path": rel_path,
        "filename": out_path.name,
        "original_name": raw_name,
        "mime": f.mimetype or "",
        "size_bytes": out_path.stat().st_size,
        "is_image": is_image,
        "uploaded_at": _now_iso(),
        "storage": "uploads",
    }
    with st.lock:
        st.pending_attachments.append(att)
    logger.info("Attachment uploaded : %s (%d bytes, image=%s)",
                rel_path, att["size_bytes"], is_image)
    return jsonify({"ok": True, **att})


@app.route("/api/pending_attachments", methods=["GET"])
def api_pending_attachments_list():
    """Liste les pièces jointes en file d'attente. Polled par le front
    desktop (toutes les 2s) et par la page mobile pour rafraîchir."""
    global _state
    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"attachments": [], "active_session": False})
    with st.lock:
        return jsonify({
            "attachments": list(st.pending_attachments),
            "active_session": True,
            "session_label": (
                f"{st.session_state.data.get('matiere', '?')} "
                f"{st.session_state.data.get('type', '?')}"
                f"{st.session_state.data.get('num', '?')} "
                f"ex{st.session_state.data.get('exo', '?')}"
            ),
        })


@app.route("/api/pending_attachments/<att_id>", methods=["DELETE"])
def api_pending_attachments_delete(att_id: str):
    """Retire une pièce jointe de la file (le fichier reste sur disque,
    seule la queue est nettoyée)."""
    global _state
    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409
    with st.lock:
        before = len(st.pending_attachments)
        st.pending_attachments = [
            a for a in st.pending_attachments if a.get("id") != att_id
        ]
        if len(st.pending_attachments) == before:
            return jsonify({"error": "attachement introuvable"}), 404
    return ("", 204)


@app.route("/api/pending_attachments/<att_id>/replace", methods=["POST"])
def api_pending_attachments_replace(att_id: str):
    """Remplace une pièce jointe image (suite à un crop côté client) par
    une nouvelle version (Phase v15.7.10).

    Multipart/form-data : champ ``file`` = nouveau blob image (typiquement
    output de ``canvas.toBlob`` après Cropper.js). L'ancien fichier reste
    sur disque (cohérent avec le pattern de DELETE qui ne touche que la
    queue) ; le nouveau est écrit dans le même dossier avec un suffixe
    ``_cropped_vN``. L'entry de la queue est mise à jour en place pour
    pointer vers le nouveau fichier (même ``att_id``, donc le tray frontal
    se rafraîchit naturellement au prochain poll).

    Codes :
        200 : OK, retourne le dict attachment mis à jour
        400 : champ file manquant / attachment non-image (refus de remplacer
              un PDF/Excel par une image)
        404 : att_id introuvable dans la queue
        409 : pas de session active
    """
    global _state
    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409

    f = (request.files.get("file")
         or request.files.get("attachment")
         or request.files.get("photo"))
    if f is None or not f.filename:
        return jsonify({"error": "champ 'file' manquant"}), 400

    # Trouve l'attachment cible dans la queue
    with st.lock:
        target = next(
            (a for a in st.pending_attachments if a.get("id") == att_id),
            None,
        )
    if target is None:
        return jsonify({"error": "attachement introuvable"}), 404
    if not target.get("is_image"):
        return jsonify({
            "error": "remplacement réservé aux images (crop)",
        }), 400

    # Phase A.10.2 : la base de stockage dépend du `storage` de l'entry :
    #   - "uploads" (défaut nouvelles) → résolu depuis UPLOADS_DIR
    #   - "cours" / absent (legacy backfill) → résolu depuis COURS_ROOT
    # Le re-crop d'une photo legacy va donc rester dans COURS/ aussi.
    target_storage = target.get("storage", "cours")
    target_base = UPLOADS_DIR if target_storage == "uploads" else COURS_ROOT
    old_path = target_base / target["rel_path"]
    target_dir = old_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    raw_name = f.filename or old_path.name
    ext_from_name = Path(raw_name).suffix.lower().lstrip(".")
    if not ext_from_name:
        ext_from_name = old_path.suffix.lstrip(".") or "jpg"
    stem_base = old_path.stem
    # Évite de cumuler les suffixes _cropped_v1_cropped_v1 si on re-crop :
    # si stem_base contient déjà "_cropped_v", on repart du préfixe original.
    if "_cropped_v" in stem_base:
        stem_base = stem_base.split("_cropped_v")[0]
    v = 1
    while (target_dir / f"{stem_base}_cropped_v{v}.{ext_from_name}").exists():
        v += 1
    out_path = target_dir / f"{stem_base}_cropped_v{v}.{ext_from_name}"
    f.save(str(out_path))

    new_rel_path = out_path.relative_to(target_base).as_posix()
    from utils import now_iso as _now_iso
    with st.lock:
        # Re-trouve l'attachment (la queue peut avoir été mutée entre
        # temps par un autre thread : paranoia).
        for a in st.pending_attachments:
            if a.get("id") == att_id:
                a["rel_path"] = new_rel_path
                a["filename"] = out_path.name
                a["mime"] = f.mimetype or a.get("mime") or "image/jpeg"
                a["size_bytes"] = out_path.stat().st_size
                a["uploaded_at"] = _now_iso()
                a["cropped"] = True
                updated = dict(a)
                break
        else:
            # L'attachment a été supprimé entre temps. Le nouveau fichier
            # reste sur disque mais la queue n'est pas modifiée.
            return jsonify({
                "error": "attachement supprimé pendant le remplacement",
            }), 404

    logger.info(
        "Attachment cropped : %s → %s (%d bytes)",
        target.get("rel_path"), new_rel_path, out_path.stat().st_size,
    )
    return jsonify({"ok": True, **updated})


@app.route("/api/upload_photo", methods=["POST"])
def api_upload_photo():
    """Sauvegarde un fichier image envoyé via multipart/form-data.

    Le fichier est routé vers `COURS/{MAT}/{TYPE}/{TYPE}{N}/photos/` (ou
    `COURS/{MAT}/CM/photos/` pour les CM, qui n'ont pas de sous-dossier
    `CM{N}/`). Le nom suit la convention CLAUDE.md §3 :

        photo_{MAT}_{TYPE}{N}_v{i}.{ext}

    où `v{i}` est incrémenté pour éviter d'écraser. Retourne le chemin
    relatif à COURS/ pour que le front puisse l'afficher / le mentionner
    à Claude dans le prochain message user.
    """
    global _state
    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409

    audio = request.files.get("file") or request.files.get("photo")
    if audio is None or audio.filename == "":
        return jsonify({"error": "champ 'file' manquant"}), 400

    ctx = st.session_state.context
    matiere = ctx.matiere.upper()
    type_code = ctx.type.upper()
    num = ctx.num

    # Routage selon TYPE (CM à plat, autres avec sous-dossier numéroté).
    if type_code == "CM":
        target_dir = COURS_ROOT / matiere / "CM" / "photos"
    elif type_code == "CC" and ctx.annee:
        target_dir = (COURS_ROOT / matiere / "CC" / ctx.annee
                      / f"CC{num}" / "photos")
    else:
        target_dir = (COURS_ROOT / matiere / type_code
                      / f"{type_code}{num}" / "photos")
    target_dir.mkdir(parents=True, exist_ok=True)

    # Extension depuis le filename ou le mimetype.
    ext = Path(audio.filename).suffix.lower().lstrip(".")
    if ext not in {"jpg", "jpeg", "png", "webp", "heic", "gif"}:
        if audio.mimetype:
            for cand_ext, cand_mime in [
                ("jpg", "jpeg"), ("png", "png"), ("webp", "webp"),
                ("heic", "heic"), ("gif", "gif"),
            ]:
                if cand_mime in audio.mimetype:
                    ext = cand_ext
                    break
        if ext not in {"jpg", "jpeg", "png", "webp", "heic", "gif"}:
            ext = "jpg"

    # Trouve le prochain `v{i}` libre.
    base_stem = f"photo_{matiere}_{type_code}{num}"
    v = 1
    while (target_dir / f"{base_stem}_v{v}.{ext}").exists():
        v += 1
    out_path = target_dir / f"{base_stem}_v{v}.{ext}"
    audio.save(str(out_path))

    rel_path = out_path.relative_to(COURS_ROOT).as_posix()
    logger.info("Photo sauvegardee : %s", rel_path)
    return jsonify({
        "ok": True,
        "filename": out_path.name,
        "rel_path": rel_path,
        "size_bytes": out_path.stat().st_size,
    })


@app.route("/api/guided/init", methods=["GET"])
def api_guided_init():
    """Wrapper qui catche les exceptions inattendues pour toujours
    retourner du JSON (Phase v15.7.36.1). Sans ça, une exception non
    catchée fait remonter du HTML 500 à Flask, et le content-type check
    côté JS affiche le faux message « endpoint absent ».

    Phase v15.7.36.3 : **ne plus retourner `guided_fallback_required: true`**
    sur exception générique. Sinon, si le mode guidé lite plante en interne
    (par ex `rasterize_if_needed` lève), le frontend ré-ouvre la modal de
    fallback dans une boucle infinie (l'user a déjà choisi ses fichiers !).
    Le bon comportement : laisser le front afficher l'erreur via le
    message d'erreur générique « Mode guidé indisponible : <error> ».
    """
    try:
        return _api_guided_init_impl()
    except Exception as e:  # noqa: BLE001
        logger.exception("/api/guided/init a leve : %s", e)
        return jsonify({
            "error": "Erreur serveur interne /api/guided/init",
            "detail": str(e),
            # PAS de guided_fallback_required ici : sinon boucle modal
        }), 500


def _api_guided_init_impl():
    """Données nécessaires au mode `guidé` (Phase A.7.2 v5).

    Retourne la liste des slides du SCRIPT actif (parsé depuis
    ``SCRIPT_*.md``) + l'URL PNG de chaque slide (rasterisée depuis
    ``slides_*.pdf`` à la volée si pas encore fait).

    Réponse :
        {
          "slides": [
            {"n": 1, "title": "...", "duration_min": 5,
             "png_url": "/api/cours_file?path=...",
             "oral_excerpt": "..."},
            ...
          ],
          "total": N,
          "titre_global": "..."
        }

    Erreurs : 409 si pas de session active, 404 si SCRIPT.md ou
    slides PDF introuvables (mode guidé indisponible pour ce doc).
    """
    global _state
    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409

    ctx = st.session_state.context
    matiere = ctx.matiere.upper()
    type_code = ctx.type.upper()
    num = ctx.num
    # Annee n'a de sens que pour les CC (millésime). Pour CM/TD/TP, on
    # l'ignore : sinon `_scan_script_dir` filtre sur `_{annee}` dans le
    # nom de fichier et écarte tous les scripts (les SCRIPT_*_CM{N}.md
    # ne portent pas de millésime).
    annee = ctx.annee if type_code == "CC" else None

    # Phase v15.7.35 : overrides explicites via query params permettent
    # à la modal de fallback frontend de pointer vers des fichiers
    # spécifiques (file picker manuel ou résultat scan IA).
    override_script = request.args.get("script_path") or ""
    override_slides = request.args.get("slides_path") or ""

    # Phase v15.7.36.1 : auto-flip si Gemini Flash (ou le user) a inversé
    # script et slides. Pattern erroné observé : script_path=.pdf +
    # slides_path=.txt → on swap. Le script doit être texte (.md/.txt) et
    # les slides un PDF. Si les deux sont du même type, on laisse et la
    # validation aval lèvera proprement.
    _script_ext = override_script.lower().rsplit(".", 1)[-1] if "." in override_script else ""
    _slides_ext = override_slides.lower().rsplit(".", 1)[-1] if "." in override_slides else ""
    if _script_ext == "pdf" and _slides_ext in ("txt", "md"):
        logger.info(
            "guided/init: auto-flip script↔slides (script=%s, slides=%s : extensions inversées)",
            override_script, override_slides,
        )
        override_script, override_slides = override_slides, override_script

    # Validation des extensions côté backend. Évite le 500 sur parse_script
    # qui essaie read_text() sur un .pdf binaire.
    if override_script:
        ext_low = override_script.lower().rsplit(".", 1)[-1] if "." in override_script else ""
        if ext_low not in ("md", "txt"):
            return jsonify({
                "error": "script_path doit être un .md ou .txt",
                "detail": (
                    f"Le script choisi ({override_script}) n'est pas un fichier "
                    f"texte. Le mode guidé attend un SCRIPT.md Feynman ou au "
                    f"minimum un script_oral_*.txt continu. Re-choisis le bon "
                    f"fichier via le file picker."
                ),
                "guided_fallback_required": True,
                "matiere": matiere,
                "type_code": type_code,
                "num": num,
                "folder_path": _safe_folder_path_for_fallback(matiere, type_code),
            }), 400
    if override_slides:
        ext_low = override_slides.lower().rsplit(".", 1)[-1] if "." in override_slides else ""
        if ext_low != "pdf":
            return jsonify({
                "error": "slides_path doit être un .pdf",
                "detail": (
                    f"Les slides choisies ({override_slides}) ne sont pas un "
                    f"PDF. Le mode guidé attend un slides_*.pdf (Beamer compilé). "
                    f"Re-choisis le bon fichier via le file picker."
                ),
                "guided_fallback_required": True,
                "matiere": matiere,
                "type_code": type_code,
                "num": num,
                "folder_path": _safe_folder_path_for_fallback(matiere, type_code),
            }), 400

    script_md: Optional[Path] = None
    if override_script:
        cand = _resolve(override_script, COURS_ROOT)
        if cand is not None and cand.is_file():
            script_md = cand
    if script_md is None:
        script_md = find_perso_script_md(COURS_ROOT, matiere, type_code, num, annee)
    if script_md is None:
        # Phase v15.7.35 : signale au front qu'une modal de fallback peut
        # s'ouvrir (file picker manuel ou scan IA). Le front décide ;
        # le repli en mode lecture libre reste l'option par défaut.
        return jsonify({
            "error": "SCRIPT_*.md introuvable",
            "detail": f"Aucun script Feynman pour {matiere} {type_code}{num}.",
            "guided_fallback_required": True,
            "missing_only": "script",
            "matiere": matiere,
            "type_code": type_code,
            "num": num,
            "folder_path": _safe_folder_path_for_fallback(matiere, type_code),
        }), 404

    slides_pdf: Optional[Path] = None
    if override_slides:
        cand = _resolve(override_slides, COURS_ROOT)
        if cand is not None and cand.is_file():
            slides_pdf = cand
    if slides_pdf is None:
        slides_pdf = find_perso_slides_pdf(COURS_ROOT, matiere, type_code, num, annee)
    if slides_pdf is None:
        return jsonify({
            "error": "slides_*.pdf introuvable",
            "detail": f"Aucun PDF de slides pour {matiere} {type_code}{num}.",
            "guided_fallback_required": True,
            "missing_only": "slides",
            "matiere": matiere,
            "type_code": type_code,
            "num": num,
            "folder_path": _safe_folder_path_for_fallback(matiere, type_code),
            # Si le script a été trouvé (overrides ou résolution), on le
            # remonte au front pour qu'il pré-remplisse la modal et ne
            # demande de parcourir QUE les slides.
            "script_path": script_md.relative_to(COURS_ROOT).as_posix() if script_md else None,
        }), 404

    structure = parse_script(script_md)
    if not structure.slides:
        # Phase v15.7.36 : fallback « mode guidé lite ». Si le script
        # pointé n'a pas les headers `## [SLIDE N]` Feynman (typiquement
        # un `script_oral_*.txt` continu, cas PSI `_revision_CC2/`), on
        # rasterise quand même les slides PDF page-par-page et on génère
        # des slides synthétiques. L'oral_excerpt de la 1ʳᵉ slide reçoit
        # le début du texte (~200 chars), les autres slides sont vides.
        # Le tuteur reçoit déjà le contenu complet du .txt comme matériau
        # via SCRIPT ORAL PERSO du prompt initial : pas besoin de
        # ré-injecter ici.
        return _build_guided_init_lite_response(script_md, slides_pdf)

    pngs = rasterize_if_needed(slides_pdf, dpi=150)
    # Map numéro slide → chemin PNG. pdftoppm produit slide-1.png ou
    # slide-01.png (zero-pad selon nb total). `_slide_num_re` capte les deux.
    import re
    _slide_num_re = re.compile(r"slide-(\d+)\.png$", re.IGNORECASE)
    png_by_num: dict[int, Path] = {}
    for p in pngs:
        m = _slide_num_re.match(p.name)
        if m:
            png_by_num[int(m.group(1))] = p

    out_slides = []
    missing_pngs: list[int] = []
    for slide in structure.slides:
        png_path = png_by_num.get(slide.n)
        png_url: Optional[str] = None
        if png_path is not None:
            try:
                rel = png_path.relative_to(COURS_ROOT).as_posix()
                png_url = f"/api/cours_file?path={rel}"
            except ValueError:
                png_url = None
        else:
            missing_pngs.append(slide.n)
        oral_excerpt = (slide.oral_text[:200] + "…") if len(slide.oral_text) > 200 else slide.oral_text
        out_slides.append({
            "n": slide.n,
            "title": slide.title,
            "duration_min": slide.duration_min,
            "png_url": png_url,
            "oral_excerpt": oral_excerpt,
        })

    # Détection d'incohérence SCRIPT ↔ slides PDF. Le SCRIPT.md est la
    # source de vérité (ARCHITECTURE.md §11) : si le PDF a plus ou moins
    # de pages, c'est qu'on a régénéré l'un sans l'autre. On signale
    # à l'UI qui pourra proposer de relancer `run_script_oral.py`.
    nb_slides_script = len(structure.slides)
    nb_pages_pdf = len(pngs)
    inconsistency = None
    if nb_slides_script != nb_pages_pdf or missing_pngs:
        inconsistency = {
            "nb_slides_script": nb_slides_script,
            "nb_pages_pdf": nb_pages_pdf,
            "missing_png_for_slides": missing_pngs,
            "script_path": script_md.relative_to(COURS_ROOT).as_posix(),
            "slides_pdf_path": slides_pdf.relative_to(COURS_ROOT).as_posix(),
            "regen_command": (
                f"python _scripts/run_script_oral.py "
                f"{script_md.relative_to(COURS_ROOT).as_posix()}"
            ),
            "message": (
                f"SCRIPT.md a {nb_slides_script} slides mais le PDF a "
                f"{nb_pages_pdf} pages. L'un des deux a été modifié sans "
                f"régénérer l'autre. Recompile depuis COURS/ avec : "
                f"`python _scripts/run_script_oral.py "
                f"{script_md.relative_to(COURS_ROOT).as_posix()}`"
            ),
        }

    return jsonify({
        "slides": out_slides,
        "total": len(out_slides),
        "titre_global": structure.titre_global,
        "inconsistency": inconsistency,
    })


def _build_guided_init_lite_response(script_path: Path, slides_pdf: Path):
    """Phase v15.7.36 : fallback « mode guidé lite » sans découpage script.

    Le script source (`.txt` ou `.md` sans headers SLIDE N) est traité
    comme du texte continu. Les slides PDF sont rasterisées page-par-page
    et exposées comme `total` slides synthétiques. Le tuteur a déjà le
    texte complet via SCRIPT ORAL PERSO injecté au prompt initial, donc
    il peut commenter une slide par son numéro de page sans avoir besoin
    de découpage explicite.

    Le frontend reçoit `lite: true` pour afficher un badge ℹ « mode lite »
    et adapter le wording (« page 1/N » au lieu de « slide titrée »).
    """
    import re
    pngs = rasterize_if_needed(slides_pdf, dpi=150)
    if not pngs:
        return jsonify({
            "error": "Slides PDF illisibles (rasterisation a échoué)",
            "detail": f"Aucun PNG produit depuis {slides_pdf.name}.",
        }), 500

    _slide_num_re = re.compile(r"slide-(\d+)\.png$", re.IGNORECASE)
    png_by_num: dict[int, Path] = {}
    for p in pngs:
        m = _slide_num_re.match(p.name)
        if m:
            png_by_num[int(m.group(1))] = p

    # Lit le texte source pour le poser sur la 1ʳᵉ slide (oral_excerpt).
    # Reste des slides : oral_excerpt vide (le tuteur lit le texte
    # continu en bloc via le contexte initial).
    try:
        oral_text_full = script_path.read_text(encoding="utf-8")
    except OSError:
        oral_text_full = ""
    excerpt_first = (
        oral_text_full[:200].replace("\n", " ").strip() + "…"
        if len(oral_text_full) > 200 else oral_text_full
    )

    out_slides = []
    nb_pages = len(png_by_num) or len(pngs)
    for n in sorted(png_by_num.keys()):
        png_path = png_by_num[n]
        try:
            rel = png_path.relative_to(COURS_ROOT).as_posix()
            png_url = f"/api/cours_file?path={rel}"
        except ValueError:
            png_url = None
        out_slides.append({
            "n": n,
            "title": f"Page {n}/{nb_pages}",
            "duration_min": None,
            "png_url": png_url,
            "oral_excerpt": excerpt_first if n == 1 else "",
        })

    return jsonify({
        "slides": out_slides,
        "total": len(out_slides),
        "titre_global": f"{script_path.stem.replace('script_oral_', '').replace('_', ' ')} (mode lite)",
        "inconsistency": None,
        "lite": True,
        "lite_reason": (
            f"Le script source `{script_path.name}` n'a pas de headers "
            f"`## [SLIDE N]` Feynman. Mode guidé « lite » : 1 page PDF = "
            f"1 slide synthétique. Le tuteur a reçu le texte continu "
            f"complet via SCRIPT ORAL PERSO et peut commenter chaque "
            f"page individuellement."
        ),
    })


# ============================================================ Phase v15.7.35 : fallback mode guidé
# Quand /api/guided/init renvoie guided_fallback_required (SCRIPT_*.md ou
# slides_*.pdf absents), le frontend ouvre une modal qui propose :
#   1. Parcourir manuellement → /api/browse_folder
#   2. Chercher avec IA → /api/scan_with_ai (Gemini Flash, cache mtime)
#   3. Repli en mode colle
# Si l'user choisit des fichiers, /api/guided/init est rappelé avec
# `?script_path=...&slides_path=...` (overrides), et la session continue
# en mode guidé.

# Extensions reconnues pour le file picker (filtre).
_BROWSE_EXTENSIONS = frozenset({".pdf", ".md", ".txt"})

# Cache de scan IA persisté par dossier scanné. Le mtime du dossier sert
# d'invalidation : si mtime cache < mtime dossier → re-scan.
_SCAN_CACHE_FILENAME = "_compagnon_scan.json"


def _safe_folder_path_for_fallback(matiere: str, type_code: str) -> str:
    """Phase v15.7.36.1 : folder_path à renvoyer dans les payloads
    ``guided_fallback_required``. Utilise ``_get_free_type_dir`` quand
    applicable, sinon fallback ``{MAT}/{TYPE}``.
    """
    try:
        from cours_resolver import _get_free_type_dir
        fd = _get_free_type_dir(COURS_ROOT, matiere, type_code)
        if fd is not None:
            return fd.relative_to(COURS_ROOT).as_posix()
    except Exception:
        pass
    return f"{matiere}/{type_code}"


def _is_under_cours_root(path: Path) -> bool:
    """True si ``path`` (normalisé) est strictement sous COURS_ROOT.

    Anti-traversal : refuse les paths qui sortent par symlinks ou `..`.
    Tolère les paths absolus déjà sous COURS_ROOT, et les relatifs.
    """
    try:
        resolved = path.resolve()
        cours_resolved = COURS_ROOT.resolve()
        return cours_resolved in resolved.parents or resolved == cours_resolved
    except OSError:
        return False


def _classify_file(p: Path) -> str:
    """Heuristique de classification pour le file picker.

    Retourne : ``script_md`` (SCRIPT_*.md avec headers), ``script_txt``
    (script oral .txt), ``script_imprimable`` (script_imprimable_*.pdf),
    ``slides_pdf`` (slides_*.pdf ou pitch_*.pdf), ``annale`` (annale_*),
    ``aide_memoire`` (aide_memoire_*), ``pdf`` (autre PDF), ``md`` (autre
    markdown), ``txt`` (autre texte). Cas par défaut : ``other``.
    """
    low = p.name.lower()
    suffix = p.suffix.lower()
    if low.startswith("script_") and suffix == ".md":
        return "script_md"
    if "script_oral" in low and suffix in (".txt", ".md"):
        return "script_txt"
    if "script_imprimable" in low and suffix == ".pdf":
        return "script_imprimable"
    if low.startswith("slides_") and suffix == ".pdf":
        return "slides_pdf"
    if "annale" in low:
        return "annale"
    if "aide_memoire" in low:
        return "aide_memoire"
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".md":
        return "md"
    if suffix == ".txt":
        return "txt"
    return "other"


@app.route("/api/browse_folder", methods=["POST"])
def api_browse_folder():
    """Liste le contenu d'un dossier sous COURS_ROOT (file picker safe).

    Body JSON : ``{path: str}`` (relatif à COURS_ROOT, vide = racine).

    Sécurité : refuse traversal (path doit rester sous COURS_ROOT après
    résolution). Filtre les fichiers techniques (`.bak`, `.tmp`, `*.pyc`).

    Réponse 200 : ``{cwd, parent_path?, entries: [{name, path_rel,
    is_dir, size?, kind?}]}``. Tri : dossiers d'abord, alpha.

    Codes : 200 OK, 400 path hors COURS_ROOT, 404 path inexistant.
    """
    body = request.get_json(silent=True) or {}
    raw_path = (body.get("path") or "").strip().replace("\\", "/")
    # Strip leading slashes pour éviter qu'un user tape `/PSI/...` ce qui
    # ferait pointer vers la racine du disque.
    raw_path = raw_path.lstrip("/")

    target = COURS_ROOT / raw_path if raw_path else COURS_ROOT
    if not _is_under_cours_root(target):
        return jsonify({"error": "path hors COURS_ROOT"}), 400
    if not target.is_dir():
        return jsonify({"error": f"dossier introuvable : {raw_path or '<racine>'}"}), 404

    entries = []
    try:
        items = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as e:
        return jsonify({"error": f"lecture impossible : {e}"}), 500

    for p in items:
        name = p.name
        # Skip techniques
        if name.endswith((".bak", ".tmp", ".pyc")):
            continue
        if name.startswith("."):
            continue
        is_dir = p.is_dir()
        if not is_dir and p.suffix.lower() not in _BROWSE_EXTENSIONS:
            # On expose quand même les dossiers de tous types (pour navigation),
            # mais on filtre les fichiers hors PDF/MD/TXT.
            continue
        entry = {
            "name": name,
            "path_rel": p.relative_to(COURS_ROOT).as_posix(),
            "is_dir": is_dir,
        }
        if not is_dir:
            try:
                entry["size"] = p.stat().st_size
            except OSError:
                entry["size"] = None
            entry["kind"] = _classify_file(p)
        entries.append(entry)

    parent_path: Optional[str] = None
    try:
        parent = target.parent.relative_to(COURS_ROOT).as_posix()
        if target != COURS_ROOT:
            parent_path = parent if parent != "." else ""
    except ValueError:
        parent_path = None

    return jsonify({
        "cwd": target.relative_to(COURS_ROOT).as_posix() if target != COURS_ROOT else "",
        "parent_path": parent_path,
        "entries": entries,
    })


def _resolve_themed_files_direct(folder: Path, theme: str) -> Optional[dict]:
    """Phase v15.7.36.4 : matching direct par thème dans le dossier.

    Cherche `script_oral_{theme}.{txt,md}`, `slides_{theme}.pdf`,
    `script_imprimable_{theme}.pdf` (matching insensible casse, suffix
    après le préfixe). Retourne le dict de paths COURS_ROOT-relatifs OU
    `None` si **moins de 2 fichiers** trouvés (auquel cas mieux vaut
    laisser Gemini chercher autre chose).

    Pourquoi déterministe avant IA : avec un theme=`Bit_information`,
    Gemini Flash propose parfois slides=`slides_TP_Shannon.pdf` au lieu
    de `slides_Bit_information.pdf` (matching de thème raté malgré
    instruction explicite). Le matching par suffix est trivialement
    correct quand les fichiers existent.
    """
    if not folder.is_dir() or not theme:
        return None
    theme_lower = theme.lower()

    def _find_in(d: Path, prefix: str, exts: tuple[str, ...]) -> Optional[Path]:
        if not d.is_dir():
            return None
        try:
            for p in sorted(d.iterdir()):
                if not p.is_file():
                    continue
                low = p.name.lower()
                if not low.startswith(prefix):
                    continue
                if not any(low.endswith(e) for e in exts):
                    continue
                # Le thème doit suivre le préfixe : `script_oral_{theme}.ext`
                middle = low[len(prefix):-len(next(e for e in exts if low.endswith(e)))]
                if middle == theme_lower:
                    return p
        except OSError:
            pass
        return None

    # Cherche dans `folder/scripts/` puis `folder/scripts_oraux/`
    # Phase v15.7.36.7 : priorité au SCRIPT_*.md Feynman (avec headers
    # `## [SLIDE N]`) sur le script_oral_*.txt (texte continu sans
    # headers). Sinon le mode guidé bascule en lite alors qu'un SCRIPT.md
    # canonique existe à côté (cas post-régénération PSI _revision_CC2).
    script_path = None
    slides_path = None
    impr_path = None
    for sub_name in ("scripts", "scripts_oraux"):
        sub = folder / sub_name
        if not sub.is_dir():
            continue
        # Pref 1 : SCRIPT_{theme}.md Feynman (mode guidé canonique)
        if script_path is None:
            script_path = _find_in(sub, "script_", (".md",))
            # `script_` matche aussi `script_oral_` et `script_imprimable_`.
            # On vérifie que le matché est bien le SCRIPT_*.md Feynman :
            # son nom doit commencer par `SCRIPT_` (uppercase strict d'après
            # convention §3 de COURS/CLAUDE.md). Sinon → None pour
            # fallback vers script_oral_*.{txt,md} ci-dessous.
            if script_path is not None and not script_path.name.startswith("SCRIPT_"):
                script_path = None
        # Pref 2 : script_oral_{theme}.{txt,md} (fallback texte continu)
        if script_path is None:
            script_path = _find_in(sub, "script_oral_", (".txt", ".md"))
        if slides_path is None:
            slides_path = _find_in(sub, "slides_", (".pdf",))
        if impr_path is None:
            impr_path = _find_in(sub, "script_imprimable_", (".pdf",))

    # Au moins 2 sur 3 pour considérer le matching réussi
    found_count = sum(1 for p in (script_path, slides_path, impr_path) if p)
    if found_count < 2:
        return None

    def _to_rel(p: Optional[Path]) -> Optional[str]:
        if p is None:
            return None
        try:
            return p.relative_to(COURS_ROOT).as_posix()
        except ValueError:
            return None

    return {
        "script_oral_path": _to_rel(script_path),
        "slides_pdf_path": _to_rel(slides_path),
        "script_imprimable_path": _to_rel(impr_path),
        "confidence_0_100": 100,
        "reasoning": (
            f"Matching direct par suffix `_{theme}` dans le dossier scripts/. "
            f"Aucun appel LLM nécessaire : convention de nommage cohérente."
        ),
    }


def _scan_with_ai_internal(folder: Path) -> dict:
    """Appel Gemini Flash pour suggérer script + slides dans un dossier.

    Liste les fichiers PDF/MD/TXT du dossier (récursif sur 2 niveaux),
    leur taille, leur classification heuristique. Demande un JSON
    `{script_oral_path, slides_pdf_path, script_imprimable_path?,
    confidence_0_100, reasoning}`.

    Engine forcé Gemini Flash 2.5 (pattern aligné sur les autres scans
    LLM du projet : refine_search_query, ocr_photo, session_recap).

    Fail-soft : si Gemini échoue ou produit du JSON cassé, retourne
    ``{script_oral_path: None, ...empty, error}``.
    """
    if not folder.is_dir():
        return {
            "script_oral_path": None,
            "slides_pdf_path": None,
            "script_imprimable_path": None,
            "confidence_0_100": 0,
            "reasoning": "dossier inexistant",
            "error": "folder_not_found",
        }

    # Liste les fichiers (récursif 2 niveaux)
    candidates: list[dict] = []
    def _walk(d: Path, depth: int):
        if depth < 0:
            return
        try:
            for p in d.iterdir():
                if p.name.startswith("."):
                    continue
                if p.is_dir():
                    _walk(p, depth - 1)
                elif p.is_file() and p.suffix.lower() in _BROWSE_EXTENSIONS:
                    try:
                        size = p.stat().st_size
                    except OSError:
                        size = None
                    candidates.append({
                        "path_rel": p.relative_to(folder).as_posix(),
                        "size": size,
                        "kind": _classify_file(p),
                    })
        except OSError:
            pass
    _walk(folder, 2)

    if not candidates:
        return {
            "script_oral_path": None,
            "slides_pdf_path": None,
            "script_imprimable_path": None,
            "confidence_0_100": 0,
            "reasoning": "aucun fichier pédagogique dans le dossier",
            "error": "no_candidates",
        }

    files_str = "\n".join(
        f"- {c['path_rel']}  ({c['kind']}, "
        f"{(c['size'] or 0) // 1024}KB)" for c in candidates
    )
    sys_prompt = (
        "Tu identifies le script oral et les slides PDF dans un dossier "
        "de révision. Tu produis EXCLUSIVEMENT du JSON minifié valide, "
        "sans markdown ni fences, sans texte hors JSON."
    )
    user_msg = (
        "Voici la liste des fichiers d'un dossier de révision étudiant. "
        "Identifie le script oral et les slides selon les RÈGLES STRICTES :\n\n"
        "**script_oral_path** : fichier TEXTE (.md ou .txt) que l'étudiant "
        "lit/récite. Convention nominale : `script_oral_*.txt` ou "
        "`SCRIPT_*.md`. JAMAIS un .pdf.\n\n"
        "**slides_pdf_path** : fichier PDF VISUEL (deck Beamer compilé) que "
        "l'étudiant a sous les yeux pendant la récitation. Convention "
        "nominale : `slides_*.pdf`. JAMAIS un .txt ou .md. Si le seul PDF "
        "candidat est `script_imprimable_*.pdf` ou `aide_memoire_*.pdf` "
        "(versions imprimables N&B, pas des slides Beamer), mets null : ce "
        "ne sont PAS des slides au sens visuel attendu par le mode guidé.\n\n"
        "**script_imprimable_path** : version imprimable du script "
        "(`script_imprimable_*.pdf` typiquement), distinct des slides "
        "Beamer. Optionnel.\n\n"
        "Si plusieurs candidats matchent une catégorie, préfère celui dont "
        "le nom est le plus précis (matching de thème) ou la taille la "
        "plus grande.\n\n"
        "**VÉRIFICATION** : avant de renvoyer, vérifie que `script_oral_path` "
        "se termine par .md ou .txt, et que `slides_pdf_path` se termine "
        "par .pdf. Si tu confonds, baisse la confidence à <40 et mentionne-"
        "le dans reasoning.\n\n"
        f"Fichiers disponibles :\n{files_str}\n\n"
        "Retourne EXACTEMENT ce JSON (chemins relatifs au dossier scanné) :\n"
        "{\n"
        '  "script_oral_path": "<path .md/.txt ou null>",\n'
        '  "slides_pdf_path": "<path .pdf ou null>",\n'
        '  "script_imprimable_path": "<path .pdf ou null>",\n'
        '  "confidence_0_100": <int>,\n'
        '  "reasoning": "<phrase courte expliquant les choix et signalant '
        'les incertitudes>"\n'
        "}\n"
        "Si aucun candidat clair pour un champ, mets null. Confidence "
        "bas si tu hésites. Pas de markdown, juste le JSON."
    )

    summarizer = ClaudeClient(
        engine="gemini_api",
        model="gemini-2.5-flash",
        system_prompt=sys_prompt,
        mode=MODE_COLLE,
        cours_root=COURS_ROOT,
    )
    summarizer.append_user_message(user_msg)

    chunks: list[str] = []

    def on_event(ev: ParserEvent) -> None:
        if ev.type == ParserEventType.TEXT_CHUNK:
            chunks.append(str(ev.payload))

    try:
        summarizer.stream_response(on_event=on_event)
    except Exception as e:  # noqa: BLE001
        logger.warning("scan_with_ai: Gemini a leve : %s", e)
        return {
            "script_oral_path": None,
            "slides_pdf_path": None,
            "script_imprimable_path": None,
            "confidence_0_100": 0,
            "reasoning": f"Gemini error : {e}",
            "error": "gemini_failed",
        }

    raw = "".join(chunks).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("scan_with_ai: JSON invalide (%s) : raw=%r", e, raw[:300])
        return {
            "script_oral_path": None,
            "slides_pdf_path": None,
            "script_imprimable_path": None,
            "confidence_0_100": 0,
            "reasoning": f"JSON LLM invalide : {raw[:200]}",
            "error": "json_invalid",
        }

    # Normalise chemins relatifs → COURS_ROOT pour cohérence avec le reste
    # de l'API (les autres endpoints reçoivent toujours du COURS_ROOT-relatif).
    def _to_cours_rel(rel_to_folder: Optional[str]) -> Optional[str]:
        if not rel_to_folder:
            return None
        try:
            candidate = (folder / rel_to_folder).resolve()
            if not _is_under_cours_root(candidate):
                return None
            return candidate.relative_to(COURS_ROOT.resolve()).as_posix()
        except (ValueError, OSError):
            return None

    script_path = _to_cours_rel(parsed.get("script_oral_path"))
    slides_path = _to_cours_rel(parsed.get("slides_pdf_path"))
    impr_path = _to_cours_rel(parsed.get("script_imprimable_path"))
    confidence = int(parsed.get("confidence_0_100") or 0)
    reasoning = str(parsed.get("reasoning") or "")

    # Phase v15.7.36.1 : auto-swap si Gemini a inversé script ↔ slides
    # (script proposé en .pdf et slides en .txt/.md). Convention stricte :
    # script doit être .md/.txt, slides doit être .pdf.
    def _ext(p: Optional[str]) -> str:
        if not p or "." not in p:
            return ""
        return p.lower().rsplit(".", 1)[-1]

    if _ext(script_path) == "pdf" and _ext(slides_path) in ("md", "txt"):
        logger.info(
            "scan_with_ai: auto-swap script↔slides (script=%s pdf vs slides=%s text : Gemini a inversé)",
            script_path, slides_path,
        )
        script_path, slides_path = slides_path, script_path
        reasoning = "[auto-swap script↔slides : Gemini avait inversé] " + reasoning
        confidence = min(confidence, 60)  # cap : signal d'hésitation

    # Validation finale : si script encore .pdf ou slides encore non-.pdf
    # après swap, c'est ambigu : on garde quand même mais on baisse la
    # confidence et on met un flag dans reasoning.
    if script_path and _ext(script_path) not in ("md", "txt"):
        reasoning = (
            f"[⚠ script_oral_path={script_path} n'est pas .md/.txt : re-vérifie] "
            + reasoning
        )
        confidence = min(confidence, 30)
    if slides_path and _ext(slides_path) != "pdf":
        reasoning = (
            f"[⚠ slides_pdf_path={slides_path} n'est pas .pdf : re-vérifie] "
            + reasoning
        )
        confidence = min(confidence, 30)

    return {
        "script_oral_path": script_path,
        "slides_pdf_path": slides_path,
        "script_imprimable_path": impr_path,
        "confidence_0_100": confidence,
        "reasoning": reasoning,
    }


@app.route("/api/claude_code_prompt", methods=["POST"])
def api_claude_code_prompt():
    """Phase v15.7.36 : génère un prompt clé-en-main pour Claude Code.

    Permet à l'utilisateur de régénérer proprement un SCRIPT.md Feynman
    avec headers `## [SLIDE N]` à partir d'un script_oral_*.txt continu +
    slides PDF, dans une session Claude Code séparée (qui a accès au
    filesystem complet COURS et peut lancer la pipeline + auditer).

    Body : ``{kind: "regen_script_md", matiere?, type_code?, num?}``
    (défaut = contexte session active).

    Réponse : ``{prompt: str, kind, matiere, type_code, num}``.

    Codes : 200 OK, 400 kind invalide, 409 pas de session ET pas de
    matiere/type_code/num fourni explicitement.
    """
    global _state
    body = request.get_json(silent=True) or {}
    kind = (body.get("kind") or "regen_script_md").strip()

    # Récupère le contexte depuis la session active ou depuis le body
    matiere = (body.get("matiere") or "").strip()
    type_code = (body.get("type_code") or body.get("type") or "").strip()
    num = (body.get("num") or "").strip()
    if not (matiere and type_code and num):
        with _state_lock:
            st = _state
        if st is None:
            return jsonify({"error": "pas de session active et matiere/type/num manquants"}), 409
        data = st.session_state.data
        matiere = matiere or (data.get("matiere") or "")
        type_code = type_code or (data.get("type") or "")
        num = num or (data.get("num") or "")
        # Récupère aussi les paths résolus dans le contexte
        context_files = data.get("context_files") or {}
        script_oral_rel = context_files.get("script_oral") or ""
        slides_pdf_rel = context_files.get("slides_pdf") or ""
        annale_rel = context_files.get("enonce") or ""
        aide_memoire_rel = context_files.get("poly_cm") or ""
    else:
        script_oral_rel = body.get("script_oral_path") or ""
        slides_pdf_rel = body.get("slides_pdf_path") or ""
        annale_rel = body.get("annale_path") or ""
        aide_memoire_rel = body.get("aide_memoire_path") or ""

    KINDS_VALID = ("regen_script_md", "audit_matiere_cc")
    if kind not in KINDS_VALID:
        return jsonify({"error": f"kind inconnu : {kind!r} (attendu {KINDS_VALID})"}), 400

    if kind == "regen_script_md":
        prompt_text = _build_prompt_regen_script_md(
            matiere=matiere, type_code=type_code, num=num,
            script_oral_rel=script_oral_rel, slides_pdf_rel=slides_pdf_rel,
            annale_rel=annale_rel, aide_memoire_rel=aide_memoire_rel,
        )
    elif kind == "audit_matiere_cc":
        prompt_text = _build_prompt_audit_matiere_cc(matiere=matiere)
    else:
        return jsonify({"error": f"kind non implémenté : {kind!r}"}), 400

    return jsonify({
        "prompt": prompt_text,
        "kind": kind,
        "matiere": matiere,
        "type_code": type_code,
        "num": num,
    })


def _build_prompt_regen_script_md(
    *, matiere: str, type_code: str, num: str,
    script_oral_rel: str, slides_pdf_rel: str,
    annale_rel: str, aide_memoire_rel: str,
) -> str:
    # Phase v15.7.36.4 : coerce None → "" pour éviter AttributeError sur
    # .split() / .replace() ci-dessous. Cas observé : session en mode
    # lite où context_files.script_oral peut être None si l'override
    # n'a pas été appliqué côté SessionContext.
    script_oral_rel = script_oral_rel or ""
    slides_pdf_rel = slides_pdf_rel or ""
    annale_rel = annale_rel or ""
    aide_memoire_rel = aide_memoire_rel or ""
    """Phase v15.7.36 : prompt Claude Code pour régénérer un SCRIPT_*.md
    Feynman à partir d'un script_oral_*.txt continu + slides_*.pdf compilées.

    Aligné strictement sur ``COURS/CLAUDE.md`` :
    - §1 : séparation Claude Code (exécute) vs Claude AI (interprète et
      produit SCRIPT_*.md). **Cette tâche est dans une zone grise** : c'est
      Claude Code qui doit générer le SCRIPT à partir d'artefacts existants
      (le .txt + slides PDF). C'est de la **rétro-ingénierie** plus que de
      la production académique pure.
    - §3 : conventions de nommage strictes (``SCRIPT_{MAT}_{TYPE}{n}_ex{e}.md``)
    - §4 D : workflow SCRIPT*.md → run_script_oral.py → .txt + slides .pdf
    - §6 RÈGLE ABSOLUE N°1/2/3 : PRESERVE.md, jamais de suppression directe,
      mise à jour docs méta.
    - §7 : ``_prompts_claude_ai/SPEC_script_oral_v2.md`` comme spec format.
    """
    cours_root_abs = "C:\\Users\\Gstar\\OneDrive\\Documents\\COURS"
    target_dir_rel = "/".join(script_oral_rel.split("/")[:-1]) if script_oral_rel else f"{matiere}/_revision_{type_code}/scripts"

    lines = [
        f"# Tâche Claude Code : Régénérer SCRIPT.md Feynman ({matiere} {type_code}/{num})",
        "",
        "Travaille depuis la racine du projet **COURS** :",
        f"`{cours_root_abs}`",
        "",
        "## Contexte",
        "",
        "Le **Compagnon de révision** (mode guidé) requiert un fichier",
        "`SCRIPT_*.md` au format Feynman v2 (avec frontmatter YAML +",
        "headers `## [SLIDE N]` + blocs `<<<BEAMER>>>…<<<END>>>`) qui",
        "découpe le script oral slide-par-slide. Sans ça, le mode bascule",
        "en « lite » (1 page PDF = 1 slide synthétique, pas de découpage",
        "oral). Le dossier ci-dessous a un script oral continu (.txt) + des",
        "slides PDF compilées, mais **pas la source Feynman**. Probablement",
        "que les .txt et slides ont été générés par une voie non standard",
        "(par exemple via Claude AI puis compilation directe), sans passer",
        "par `run_script_oral.py`.",
        "",
        "## Matériaux disponibles",
        "",
    ]
    if script_oral_rel:
        lines.append(f"- **Script oral continu** (entrée) : `{script_oral_rel}`")
    if slides_pdf_rel:
        lines.append(f"- **Slides PDF compilées** (référence visuelle) : `{slides_pdf_rel}`")
    # Source LaTeX éventuelle des slides (utile pour reconstruire le bloc Beamer)
    if slides_pdf_rel:
        slides_tex_rel = slides_pdf_rel[:-4] + ".tex" if slides_pdf_rel.endswith(".pdf") else ""
        if slides_tex_rel:
            lines.append(f"- **Source LaTeX des slides** (si présente, à vérifier) : `{slides_tex_rel}`")
    if annale_rel:
        lines.append(f"- **Annale Q&A** (contexte pédagogique global) : `{annale_rel}`")
    if aide_memoire_rel:
        lines.append(f"- **Aide-mémoire** (poly de référence) : `{aide_memoire_rel}`")

    lines.extend([
        "",
        "## Avant de commencer : lectures obligatoires",
        "",
        "1. `COURS/CLAUDE.md`, particulièrement §1 (rôles Claude Code/AI),",
        "   §3 (conventions de nommage), §4 D (workflow SCRIPT oral),",
        "   §6 RÈGLES ABSOLUES (PRESERVE.md, jamais de suppression directe,",
        "   docs méta à jour).",
        "2. `COURS/_prompts_claude_ai/SPEC_script_oral_v2.md` : **spec complète**",
        "   du format SCRIPT.md Feynman v2 (frontmatter, balises, blocs Beamer).",
        "   Lis-la avant tout : tout écart de format casse `run_script_oral.py`.",
        "3. `COURS/PRESERVE.md` : chemins intouchables.",
        "",
        "## Tâches",
        "",
        "### 1. Comprendre la structure visuelle des slides",
        "",
        "- Rasterise les slides PDF en PNG si pas déjà fait (cf. patterns",
        "  `_scripts/` qui utilisent `pdftoppm`).",
        "- Si une source `.tex` Beamer existe à côté du `.pdf`, lis-la : elle",
        "  contient déjà la structure `\\begin{frame}…\\end{frame}` que tu",
        "  pourras reprendre dans les blocs `<<<BEAMER>>>`.",
        "- Sinon, extrait le texte de chaque page PDF (`pdftotext` ou",
        "  lecture multimodale) pour identifier titres + contenu.",
        "",
        "### 2. Découper le script oral en sections par slide",
        "",
        "- Repère les transitions naturelles dans le `.txt` (changements de",
        "  thème, marqueurs « ensuite », « passons à », « maintenant », etc.)",
        "  qui matchent les transitions visuelles des slides.",
        "- Si le nombre de transitions naturelles ≠ nombre de pages PDF,",
        "  **demande arbitrage** avant de découper arbitrairement.",
        "",
        "### 3. Générer le SCRIPT.md Feynman v2",
        "",
        "- Format exact : suivre `SPEC_script_oral_v2.md`.",
        "- Frontmatter YAML obligatoire (`matiere`, `type`, `num`, `source`,",
        "  + autres champs requis par la spec).",
        "- `source: TRANSCRIPTION` si tu reprends fidèlement le `.txt`",
        "  existant. `source: INFERENCE` si tu reformules.",
        "- Headers `## [SLIDE N]` avec titre court.",
        "- Bloc `<<<BEAMER>>>…<<<END>>>` par slide, reprenant la structure",
        "  Beamer (`\\begin{frame}{Titre}…\\end{frame}`).",
        "- **Idempotence** : si la régen est ré-jouée sur le même `.txt`",
        "  sans modif, elle doit produire le même SCRIPT.md (modulo",
        "  timestamps internes éventuels).",
        "",
        "### 4. Sauvegarder",
        "",
        f"Chemin canonique selon §3 de `COURS/CLAUDE.md` :",
        f"`{target_dir_rel}/SCRIPT_{matiere}_{num}.md`",
        "",
        "**Atomic write obligatoire** (cf. règle inviolable §6) : écris dans",
        "un `.tmp` puis `os.replace`. Pas de write direct.",
        "",
        "### 5. Vérifier via la pipeline",
        "",
        "Relance la pipeline canonique pour confirmer que ton SCRIPT.md",
        "est bien parsable (Workflow D de §4 `COURS/CLAUDE.md`) :",
        "```bash",
        f"python _scripts/run_script_oral.py {target_dir_rel}/SCRIPT_{matiere}_{num}.md",
        "```",
        "Compare le `.txt` régénéré avec l'original (`diff`). Différences",
        "majeures = ajuste le découpage. Différences mineures (whitespace,",
        "ponctuation) = acceptable.",
        "",
        "Si la slide PDF a été modifiée par la régen (improbable, mais",
        "vérifie `slides_*.pdf`), c'est que la source Beamer a divergé.",
        "Compare le rendu visuel : décide si le nouveau PDF remplace.",
        "",
        "### 6. RÈGLES ABSOLUES (à respecter sans exception)",
        "",
        "- **RÈGLE N°1** : lis `PRESERVE.md` avant tout déplacement ou",
        "  suppression. Tout chemin listé est intouchable.",
        "- **RÈGLE N°2** : jamais de suppression directe d'un fichier",
        "  existant. Si tu veux remplacer le `.txt` ou les slides actuels,",
        "  déplace-les dans `_A_VALIDER/` + ajoute une entrée dans",
        "  `RAPPORT_NETTOYAGE.md`. Exception : versions parallèles via",
        "  suffixe (`_inference` vs `_transcription`, cf. §6 RÈGLE",
        "  INFÉRENCE → TRANSCRIPTION).",
        "- **RÈGLE N°3** : à la fin, rappelle à Gaylord la potentielle",
        "  mise à jour des docs méta (`CLAUDE.md`, `CHANGELOG.md`).",
        "- **Pas de push Discord automatique** sans validation explicite",
        "  de Gaylord.",
        "",
        "### 7. (Bonus) : Audit cross-matière",
        "",
        f"Une fois `{matiere} {type_code}/{num}` propre, scanne les autres",
        f"dossiers `{matiere}/_revision_*/scripts/` (et plus largement",
        f"`{matiere}/*/scripts_oraux/` selon §2 arborescence) pour repérer",
        "le même problème : présence d'un `script_oral_*.txt` SANS",
        "`SCRIPT_*.md` Feynman correspondant. Liste les paires orphelines",
        "dans un rapport `_audit/sessions/YYYY-MM-DD_audit_scripts_orphelins.md`",
        "selon §6 RÈGLE LOGGING. Ne touche pas aux fichiers identifiés sans",
        "validation Gaylord par fichier.",
        "",
        "## Reporting",
        "",
        "À la fin :",
        "- Affiche le path du SCRIPT.md créé.",
        "- Affiche le résultat de la pipeline (lignes du `.txt` régénéré",
        "  match l'original ou diffèrent).",
        "- Liste les orphelins identifiés en bonus (si tâche 7 lancée).",
        "- Rappelle à Gaylord les docs méta à mettre à jour le cas échéant.",
        "",
        "**Demande confirmation à chaque étape qui touche le disque.**",
        "L'utilisateur attend du livrable propre, pas du « j'ai fait quelque",
        "chose ».",
    ])
    return "\n".join(lines)


def _build_prompt_audit_matiere_cc(*, matiere: str) -> str:
    """Phase v15.7.36 : prompt Claude Code pour audit cross-CC d'une matière.

    Scanne `{matiere}/_revision_CC*/` et `{matiere}/{CM,TD,TP}/.../scripts_oraux/`
    pour repérer incohérences : .txt sans SCRIPT.md, slides PDF sans script,
    SCRIPT.md sans pipeline relancée, etc.
    """
    cours_root_abs = "C:\\Users\\Gstar\\OneDrive\\Documents\\COURS"
    lines = [
        f"# Tâche Claude Code : Audit incohérences scripts/slides ({matiere})",
        "",
        f"Travaille depuis `{cours_root_abs}`.",
        "",
        "## Objectif",
        "",
        f"Scanne récursivement `{matiere}/` pour identifier les **incohérences**",
        "dans les paires script/slides selon les conventions de",
        "`COURS/CLAUDE.md` §3 et §4 D. Produit un rapport actionnable.",
        "",
        "## Lectures obligatoires",
        "",
        "1. `COURS/CLAUDE.md` §1, §2, §3, §4 D, §6.",
        "2. `COURS/_prompts_claude_ai/SPEC_script_oral_v2.md`.",
        "3. `COURS/PRESERVE.md`.",
        "",
        "## Critères d'audit",
        "",
        "Pour chaque sous-dossier qui contient des matériaux de script/slides",
        f"dans `{matiere}` (notamment `scripts_oraux/`, `_revision_CC*/scripts/`,",
        "ou tout dossier ad hoc), vérifie :",
        "",
        "1. **Pair script_oral_*.txt / SCRIPT_*.md** : pour chaque",
        "   `script_oral_{theme}.txt`, le `SCRIPT_{MAT}_..._{theme}.md` Feynman",
        "   correspondant existe-t-il ? Sinon : **orphelin** (le compagnon",
        "   tombe en mode lite pour ce thème).",
        "",
        "2. **Pair SCRIPT.md / slides_*.pdf** : pour chaque `SCRIPT_*.md`, les",
        "   slides PDF correspondantes existent-elles avec le même `n` ? Sinon :",
        "   pipeline `run_script_oral.py` jamais relancée → orphelin inversé.",
        "",
        "3. **Pair script_imprimable_*.pdf / SCRIPT.md** : pour chaque",
        "   imprimable, le SCRIPT source existe-t-il ? Sinon : impossible de",
        "   régénérer proprement (le `_recopie.pdf` PSI vient probablement",
        "   d'un autre processus).",
        "",
        "4. **Cohérence n° de slides** : si SCRIPT.md a N slides mais le PDF",
        "   a M pages (cf. logique `inconsistency` côté `/api/guided/init`),",
        "   c'est un fichier régénéré sans l'autre. Note la divergence.",
        "",
        "## Sortie attendue",
        "",
        f"Rapport sauvé dans `COURS/_audit/sessions/YYYY-MM-DD_audit_{matiere}_scripts.md`",
        "(selon §6 RÈGLE LOGGING) avec :",
        "",
        "```markdown",
        f"# Audit scripts/slides : {matiere}",
        "## Orphelins .txt sans SCRIPT.md",
        "- `<path>` : (raisons probables, action suggérée)",
        "",
        "## Orphelins SCRIPT.md sans slides PDF",
        "- `<path>` : (pipeline jamais relancée, lancer `run_script_oral.py`)",
        "",
        "## Divergences SCRIPT/PDF (nb slides différents)",
        "- `<path>` : SCRIPT a N slides, PDF a M pages",
        "",
        "## Imprimables sans source SCRIPT",
        "- `<path>` : (probablement compilation hors pipeline standard)",
        "",
        "## Recommandations",
        "1. ...",
        "```",
        "",
        "## Règles",
        "",
        "- **Ne modifie aucun fichier** pendant l'audit. C'est read-only.",
        "- Si tu trouves des candidats à fixer, **demande validation** avant",
        "  de lancer la régen (qui sera traitée via la tâche dédiée",
        "  `regen_script_md` une par une).",
        "- Mets à jour `_audit/sessions/INDEX.md` (§6 RÈGLE LOGGING).",
    ]
    return "\n".join(lines)


@app.route("/api/scan_with_ai", methods=["POST"])
def api_scan_with_ai():
    """Scan IA d'un dossier pour suggérer script + slides + imprimable.

    Body JSON : ``{folder_path: str, force_refresh?: bool}`` : path relatif
    à COURS_ROOT.

    Cache : ``{folder}/_compagnon_scan.json`` valide si ``cache_mtime >=
    folder_mtime``. Sinon (ou ``force_refresh=true``), nouveau scan Gemini.

    Réponse 200 : ``{script_oral_path, slides_pdf_path, script_imprimable_path,
    confidence_0_100, reasoning, cached, scanned_at}``. Chemins relatifs
    à COURS_ROOT.

    Codes : 200 OK (même si Gemini fail → fallback dégradé dans payload),
    400 path invalide, 404 dossier inexistant.
    """
    body = request.get_json(silent=True) or {}
    folder_path = (body.get("folder_path") or "").strip().replace("\\", "/").lstrip("/")
    force = bool(body.get("force_refresh"))
    # Phase v15.7.36.4 : `theme` permet le matching direct par suffix
    # (`script_oral_{theme}.{txt,md}` etc.) AVANT d'appeler Gemini. Plus
    # fiable car Gemini se trompe parfois sur le matching de thème (cas
    # observé : theme=Bit_information mais propose slides_TP_Shannon).
    theme = (body.get("theme") or "").strip()

    if not folder_path:
        return jsonify({"error": "folder_path requis"}), 400

    target = COURS_ROOT / folder_path
    if not _is_under_cours_root(target):
        return jsonify({"error": "path hors COURS_ROOT"}), 400
    if not target.is_dir():
        return jsonify({"error": f"dossier introuvable : {folder_path}"}), 404

    from utils import now_iso as _now_iso

    # Phase v15.7.36.4 : tentative matching direct par thème (bypass
    # Gemini). Si réussit (≥2 fichiers trouvés par suffix), retourne
    # avec confidence 100 sans toucher au cache (le matching est trivial
    # et reproductible, pas besoin de le persister).
    if theme:
        direct = _resolve_themed_files_direct(target, theme)
        if direct is not None:
            direct["cached"] = False
            direct["scanned_at"] = _now_iso()
            direct["method"] = "direct_suffix_match"
            return jsonify(direct)

    cache_path = target / _SCAN_CACHE_FILENAME

    # Cache hit check : mtime cache >= mtime dossier (récursif sur 2 niveaux)
    if not force and cache_path.is_file():
        try:
            cache_mtime = cache_path.stat().st_mtime
            # Comparer au mtime max du dossier + sous-dossiers immédiats
            folder_mtime = target.stat().st_mtime
            for sub in target.iterdir():
                if sub.is_dir():
                    try:
                        folder_mtime = max(folder_mtime, sub.stat().st_mtime)
                    except OSError:
                        pass
            if cache_mtime >= folder_mtime:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                cached["cached"] = True
                return jsonify(cached)
        except (OSError, json.JSONDecodeError) as e:
            logger.info("scan_with_ai: cache invalide (%s), re-scan", e)

    # Cache miss : appel Gemini
    result = _scan_with_ai_internal(target)
    result["cached"] = False
    result["scanned_at"] = _now_iso()

    # Persist cache (atomic write)
    try:
        from utils import atomic_write_json
        atomic_write_json(cache_path, result)
    except Exception as e:  # noqa: BLE001
        logger.warning("scan_with_ai: persist cache a leve : %s", e)

    return jsonify(result)


def _kickoff_corrige_prerasterize(ctx) -> None:
    """Lance un thread daemon qui rasterise tous les corrigés + script
    imprimable en arrière-plan. Premier ouverture du panneau « Corrigés &
    script » = instantané, au lieu d'attendre 2-5 s par PDF la 1ʳᵉ fois.

    Idempotent (rasterize_correction skip si PNGs déjà à jour) : peut être
    appelé plusieurs fois sans coût ni effet de bord.
    """
    matiere = (getattr(ctx, "matiere", "") or "").upper()
    type_code = (getattr(ctx, "type", "") or "").upper()
    num = str(getattr(ctx, "num", "") or "")
    exo = str(getattr(ctx, "exo", "full") or "full")
    annee = getattr(ctx, "annee", None) or None

    def _worker():
        try:
            paths: list[Path] = []
            try:
                enonce = find_enonce_pdf(COURS_ROOT, matiere, type_code, num, annee)
                if enonce is not None:
                    paths.append(enonce)
            except Exception:  # noqa: BLE001
                logger.exception("prerasterize: find_enonce_pdf a leve")
            try:
                paths.extend(resolve_corrections(
                    COURS_ROOT, matiere, type_code, num, exo, annee,
                    prefer_concat=False,
                ))
            except Exception:  # noqa: BLE001
                logger.exception("prerasterize: resolve_corrections a leve")
            script = find_perso_script_imprimable(
                COURS_ROOT, matiere, type_code, num, annee
            )
            if script is not None:
                paths.append(script)
            # Phase A.8 : slides PDF aussi pré-rasterisées (exposées dans
            # le panneau Docs pour tous les modes, plus seulement guidé).
            slides = find_perso_slides_pdf(
                COURS_ROOT, matiere, type_code, num, annee
            )
            if slides is not None:
                paths.append(slides)
            for p in paths:
                if not p.is_file():
                    continue
                try:
                    rasterize_correction(p)
                except Exception:  # noqa: BLE001
                    logger.exception("prerasterize: rasterize a leve sur %s", p)
        except Exception:  # noqa: BLE001
            logger.exception("prerasterize worker a leve")

    t = threading.Thread(target=_worker, name="corrige-prerasterize", daemon=True)
    t.start()


def _label_for_correction_pdf(pdf_path: Path) -> str:
    """Génère un label lisible pour un PDF de correction.

    Conventions extraites de ``cours_pipeline.parse_correction_filename`` :
      - ``correction_TD5_AN1_ex3.pdf`` → ``Exercice 3``
      - ``correction_TD5_AN1_ex3-1.pdf`` → ``Exercice 3-1``
      - ``concat_TD5_AN1.pdf`` → ``Toutes les corrections``
      - ``correction_CC2_2024-25_AN1.pdf`` → ``CC2 : corrigé global``
      - ``annale_synthese_CC2.{pdf,md}`` → ``Annale Q&A : CC2``
      - ``aide_memoire_CC2.{pdf,md}`` → ``Aide-mémoire : CC2``
      - ``exos_TP_Shannon.{pdf,md}`` → ``Exos : TP_Shannon``
      - fallback → stem brut

    Phase v15.7.36.8 : patterns `annale_synthese_*` et `aide_memoire_*`
    ajoutés (matériaux des types libres `_revision_CC*/`). Avant, le
    regex ``_(CC\\d+)`` capturait `annale_synthese_CC2.pdf` comme « CC2 :
    corrigé global » alors que c'est une **annale Q&A** (questions +
    corrections), pas un corrigé d'exercice classique.
    """
    name = pdf_path.stem
    low = name.lower()
    if low.startswith("concat_"):
        return "Toutes les corrections"
    # Patterns spécifiques aux types libres (priorité sur les regex CC plus
    # bas, sinon `annale_synthese_CC2` matche `_(CC\d+)` et donne un label
    # trompeur « CC2 : corrigé global »).
    if low.startswith("annale_synthese"):
        m = re.search(r"_(CC\d+)", name, re.IGNORECASE)
        if m:
            return f"Annale Q&A : {m.group(1).upper()}"
        return "Annale Q&A"
    if low.startswith("aide_memoire"):
        m = re.search(r"_(CC\d+)", name, re.IGNORECASE)
        suffix = ""
        if "recopie" in low or "_a4" in low:
            suffix = " (imprimable A4)"
        if m:
            return f"Aide-mémoire : {m.group(1).upper()}{suffix}"
        return f"Aide-mémoire{suffix}"
    if low.startswith("exos_"):
        # `exos_TP_Shannon.pdf` → theme = TP_Shannon
        theme = name[len("exos_"):]
        return f"Exos : {theme}"
    m = re.search(r"_ex([\w-]+?)(?:_|$)", name, re.IGNORECASE)
    if m:
        return f"Exercice {m.group(1)}"
    m = re.search(r"_(CC\d+)(?:_|$)", name, re.IGNORECASE)
    if m:
        return f"{m.group(1).upper()} : corrigé global"
    return name


def _extract_exo_from_filename(name: str) -> Optional[str]:
    """Extrait le numéro d'exercice d'un nom de fichier corrigé.

    Patterns supportés (Phase Z.8.4) :
        correction_TD5_AN1_ex3.pdf            → "3"
        correction_TD8_EN1_ex2_2024-25.pdf    → "2"
        correction_TD5_AN1_ex3.5.pdf          → "3.5" (sous-question)
        correction_TD5_AN1.pdf                → None  (pas d'exo)
    Retourne None si pas de pattern `_ex...` détecté.
    """
    m = re.search(r"_ex([\w.]+?)(?:_\d{4}-\d{2})?\.pdf$", name, re.IGNORECASE)
    return m.group(1) if m else None


def _build_document_entry(pdf_path: Path, kind: str, label: Optional[str] = None) -> dict:
    """Rasterise un PDF et retourne l'entrée document pour /api/corrections/init.

    ``kind`` : ``correction`` ou ``script``, utilisé côté front pour préfixer
    les notes de tracking envoyées au tuteur.

    Phase Z.8.4 : ajout du champ ``exo`` (extrait du filename) pour permettre
    au tuteur de cibler un corrigé précis quand il y en a plusieurs (1 par
    exercice). Avant : SHOW_DOC matchait toujours le 1ᵉʳ corrigé du kind, donc
    pour un TD avec 5 corrections, "page 10 du corrigé de l'ex 3" ouvrait
    silencieusement le corrigé de l'ex 1.
    """
    pngs = rasterize_correction(pdf_path)
    pages = []
    for i, p in enumerate(pngs, start=1):
        try:
            rel = p.relative_to(COURS_ROOT).as_posix()
        except ValueError:
            continue
        png_url = f"/api/cours_file?path={rel}"
        pages.append({"n": i, "png_url": png_url})
    try:
        pdf_rel = pdf_path.relative_to(COURS_ROOT).as_posix()
    except ValueError:
        pdf_rel = pdf_path.name
    return {
        "kind": kind,
        "label": label or _label_for_correction_pdf(pdf_path),
        "filename": pdf_path.name,
        "pdf_path": pdf_rel,
        "exo": _extract_exo_from_filename(pdf_path.name),
        "total_pages": len(pages),
        "pages": pages,
    }


@app.route("/api/corrections/init", methods=["GET"])
def api_corrections_init():
    """Liste les documents (corrigés officiels + script imprimable) de la
    session active, rasterisés en PNG.

    Visible dans tous les modes (contrairement au mode guidé qui affiche les
    slides du SCRIPT). Re-résout les chemins fichiers à partir du contexte
    matière/type/num/exo/annee : fonctionne donc aussi sur reprise de
    session (où ``ctx.correction_paths`` est vide après ``SessionState.load``).

    Réponse :
        {
          "corrections": [
            {
              "kind": "correction",
              "label": "Exercice 3",
              "filename": "correction_TD5_AN1_ex3.pdf",
              "pdf_path": "AN1/TD/TD5/corrections/correction_TD5_AN1_ex3.pdf",
              "total_pages": 4,
              "pages": [{"n": 1, "png_url": "/api/cours_file?path=..."}, ...]
            },
            {"kind": "script", "label": "Script imprimable", ...}
          ],
          "total_corrections": N,
          "matiere": "AN1", "type": "TD", "num": "5", "exo": "3"
        }
    """
    global _state
    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409

    ctx = st.session_state.context
    matiere = (ctx.matiere or "").upper()
    type_code = (ctx.type or "").upper()
    num = str(ctx.num or "")
    exo = str(ctx.exo or "full")
    annee = ctx.annee or None

    out: list[dict] = []
    # Phase v15.7.36.3 : dédup des paths exposés. Pour les types libres
    # où l'annale_synthese servait à la fois d'énoncé et de corrigé,
    # le picker affichait 2 entrées pointant vers le MÊME PDF (« Énoncé »
    # + « Corrigé : annale_synthese.pdf »). Confus visuellement. Set ici
    # pour skip les doublons.
    _seen_paths: set[str] = set()

    # 1) Énoncé officiel : base de l'exercice. Toujours en 1ʳᵉ position
    # dans le picker pour faciliter la lecture séquentielle.
    try:
        enonce_pdf = find_enonce_pdf(COURS_ROOT, matiere, type_code, num, annee)
    except Exception:  # noqa: BLE001
        logger.exception("find_enonce_pdf a échoué")
        enonce_pdf = None
    if enonce_pdf is not None and enonce_pdf.is_file():
        out.append(_build_document_entry(
            enonce_pdf, kind="enonce", label="Énoncé"
        ))
        _seen_paths.add(str(enonce_pdf.resolve()))

    # 2) Corrigés officiels : re-résolus à chaque appel pour gérer le cas
    # « reprise de session » où ``ctx.correction_paths`` est vide (cf.
    # ``SessionState.load`` qui ne réhydrate pas les Path).
    try:
        # prefer_concat=False : on liste les fichiers individuels par exo
        # (« Exercice 1/2/3 ») plutôt qu'un seul « Toutes les corrections »
        # : moins ambigu vis-à-vis des items Énoncé / Script du même picker,
        # et robuste si un concat_*.pdf maison contient plus que les corrigés.
        correction_paths = resolve_corrections(
            COURS_ROOT, matiere, type_code, num, exo, annee,
            prefer_concat=False,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("resolve_corrections a échoué : %s", e)
        correction_paths = []
    # Phase v15.7.36.10 : pour les **types libres avec num=thème** (cas
    # PSI `_revision_CC2/Bit_information`), filtrer le picker Docs pour
    # exclure les fichiers globaux (annale_synthese, aide_memoire) qui
    # couvrent tous les thèmes. User feedback : « je vois annale dans
    # documents et je trouve ça incohérent que ce soit dans la session
    # _revision_CC2/Bit_information ». L'annale reste accessible au
    # tuteur via `correction_paths` du SessionContext (prompt initial) :
    # on filtre uniquement l'affichage frontend.
    from cours_resolver import _is_canonical_type
    is_themed_free_type = (
        not _is_canonical_type(type_code)
        and num and num.lower() != "full"
    )
    theme_lower = num.lower() if is_themed_free_type else None

    for pdf_path in correction_paths:
        if not pdf_path.is_file():
            continue
        # Phase v15.7.36.10 : filtrage par thème pour types libres :
        # le nom de fichier doit contenir le thème pour rester dans
        # le picker. annale_synthese_CC2.pdf ne contient pas
        # « Bit_information » → exclu pour ce thème. exos_TP_Shannon.pdf
        # contient « TP_Shannon » → gardé pour num=TP_Shannon.
        if is_themed_free_type and theme_lower not in pdf_path.name.lower():
            continue
        # Phase v15.7.36.3 : skip si déjà exposé (cas énoncé=corrigé pour
        # types libres avec annale_synthese unique)
        path_key = str(pdf_path.resolve())
        if path_key in _seen_paths:
            continue
        out.append(_build_document_entry(pdf_path, kind="correction"))
        _seen_paths.add(path_key)

    # 3) Script imprimable : version PDF du script_oral, à lire à l'écran
    # quand l'étudiant n'a pas la version papier sous les yeux.
    script_pdf = find_perso_script_imprimable(
        COURS_ROOT, matiere, type_code, num, annee
    )
    if script_pdf is not None and script_pdf.is_file():
        path_key = str(script_pdf.resolve())
        if path_key not in _seen_paths:
            out.append(_build_document_entry(
                script_pdf, kind="script", label="Script imprimable"
            ))
            _seen_paths.add(path_key)

    # 4) Slides PDF : affichées dans Docs pour tous les modes (Phase A.8).
    # Avant : seules les slides étaient visibles dans le panneau du mode
    # guidé, donc en mode colle / découverte le panneau Docs pouvait être
    # quasi-vide quand seul un fichier `slides_<theme>.pdf` existait
    # (cas PSI `_revision_CC2/TP_Shannon` : ni énoncé, ni script_imprimable,
    # juste slides + script_oral.txt → Docs vide). Avec ce fix, les slides
    # apparaissent dans Docs même quand on n'est pas en guidé.
    slides_pdf = find_perso_slides_pdf(
        COURS_ROOT, matiere, type_code, num, annee
    )
    if slides_pdf is not None and slides_pdf.is_file():
        path_key = str(slides_pdf.resolve())
        if path_key not in _seen_paths:
            out.append(_build_document_entry(
                slides_pdf, kind="slides", label="Slides"
            ))
            _seen_paths.add(path_key)

    return jsonify({
        "corrections": out,
        "total_corrections": len(out),
        "matiere": matiere,
        "type": type_code,
        "num": num,
        "exo": exo,
    })




_FALLBACK_PROVIDER_INFO = {
    "gemini_api":   ("Gemini 2.5 Pro",        "GEMINI_API_KEY"),
    "deepseek_api": ("DeepSeek V3 / R1",      "DEEPSEEK_API_KEY"),
    "groq_api":     ("Groq + Llama 3.3 70B",  "GROQ_API_KEY"),
    "api_anthropic": ("Claude API Anthropic", "ANTHROPIC_API_KEY"),
}


def _list_available_fallbacks(exclude: Optional[str] = None) -> list[dict]:
    """Liste les providers de fallback dont la clé API est définie.

    Sortie : list de ``{"engine": "deepseek_api", "label": "DeepSeek V3 / R1"}``
    pour que le front affiche un bouton par provider. ``exclude`` permet
    de retirer le provider courant (s'il a sauté, inutile de le proposer).
    Le CLI subscription Anthropic n'est jamais proposé en fallback (il
    a son propre système de quota fenêtre 5h, redémarrer ne sert à rien
    avant le reset).
    """
    out = []
    for engine_id, (label, env_key) in _FALLBACK_PROVIDER_INFO.items():
        if engine_id == exclude:
            continue
        if os.environ.get(env_key):
            out.append({"engine": engine_id, "label": label})
    return out


def _persist_engine_pref(engine_id: str) -> None:
    """Écrit `_secrets/engine_pref.json` atomiquement avec le nouvel engine.

    Cohérent avec gui.py `_save_engine_pref` (même format, même atomic
    pattern .tmp + os.replace). Le subprocess relancé manuellement
    relira cette préférence : utile si l'utilisateur Stop+Lance après.
    """
    ENGINE_PREF_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION_ENGINE_PREF,
        "engine": engine_id,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    tmp = ENGINE_PREF_PATH.with_suffix(ENGINE_PREF_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    from utils import _replace_with_retry
    _replace_with_retry(tmp, ENGINE_PREF_PATH)


@app.route("/api/switch_engine", methods=["POST"])
def api_switch_engine():
    """Bascule à chaud vers un autre engine sans perdre l'historique.

    Cas d'usage (Phase A.7.2 v7.3) : le quota Anthropic/Gemini/DeepSeek a
    sauté en plein flow ; le front affiche un card avec les providers de
    fallback dispos ; clic sur un bouton → POST ici.

    Construit un nouveau ``ClaudeClient`` du bon engine, **transfère
    l'historique** (`_history`) du client courant, qui contient déjà le
    user message ayant échoué, mais pas la réponse assistant absente.
    Persiste aussi le choix dans `engine_pref.json` pour les redémarrages
    futurs. Le retry du stream est ensuite déclenché côté front via un
    GET /api/stream_response (qui détectera `retry_pending=True` et
    relancera sans toucher à l'historique).
    """
    global _state
    body = request.get_json(silent=True) or {}
    new_engine = (body.get("engine") or "").strip()
    from claude_client import (  # noqa: E402 (import paresseux pour éviter cycle)
        ClaudeClient, SUPPORTED_ENGINES,
    )
    if new_engine not in SUPPORTED_ENGINES:
        return jsonify({
            "error": f"engine inconnu : {new_engine!r}",
            "supported": list(SUPPORTED_ENGINES),
        }), 400

    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409

    with st.lock:
        old_client = st.client
        # Snapshot de l'état utile à recréer un client équivalent.
        old_history = list(old_client.history)
        try:
            new_client = ClaudeClient(
                engine=new_engine,
                system_prompt=old_client._system_prompt,
                model=old_client._model,
                max_tokens=old_client._max_tokens,
                mode=old_client._mode,
                cours_root=old_client._cours_root,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("Construction client %s a leve", new_engine)
            return jsonify({"error": f"init {new_engine} : {e}"}), 500
        # Transfert de l'historique brut. Les rôles user/assistant sont
        # universels (cf. _stream_via_openai_compatible et _stream_via_gemini
        # qui convertissent à la volée). L'historique inclut le user
        # message qui a échoué côté ancien provider : on le retry tel quel.
        new_client._history = old_history
        st.client = new_client
        st.retry_pending = True

    try:
        _persist_engine_pref(new_engine)
    except OSError as e:
        logger.warning("Persistance engine_pref a leve : %s", e)
        # Pas bloquant : la session courante a basculé en mémoire,
        # juste les redémarrages futurs ne verront pas le changement.

    logger.info("Engine basculé à chaud : %s → %s", old_client.engine, new_engine)
    return jsonify({
        "ok": True,
        "engine": new_engine,
        "previous_engine": old_client.engine,
        "history_size": len(old_history),
    })


@app.route("/api/switch_engine_pref", methods=["POST"])
def api_switch_engine_pref():
    """Met à jour `_secrets/engine_pref.json` sans session active.
    Pour /api/switch_engine (bascule à chaud d'une session active),
    voir le endpoint dédié plus bas. Permet au sélecteur de moteur du
    header de fonctionner même quand aucune session n'est lancée."""
    try:
        body = request.get_json(silent=True) or {}
        new_engine = (body.get("engine") or "").strip()
        if not new_engine:
            return jsonify({"error": "engine requis"}), 400
        available_set = {"cli_subscription"}  # toujours dispo (pas de clé requise)
        for a in _list_available_fallbacks(exclude=None):
            available_set.add(a["engine"])
        if new_engine not in available_set:
            return jsonify({"error": f"moteur indisponible : {new_engine}"}), 400
        _persist_engine_pref(new_engine)
        logger.info("Engine pref persisté : %s", new_engine)
        return jsonify({"ok": True, "engine": new_engine})
    except Exception as e:  # noqa: BLE001
        logger.exception("switch_engine_pref a leve")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/engine", methods=["GET"])
def api_engine():
    """Retourne le moteur courant (lit engine_pref.json) + la liste des
    moteurs disponibles pour le sélecteur du header.

    Note : ``_list_available_fallbacks`` exclut ``cli_subscription`` par
    design (jamais utilisé en fallback auto, parce qu'il a son propre
    système de quota fenêtre 5h). Mais pour le sélecteur **manuel** où
    l'utilisateur choisit explicitement, on doit toujours proposer
    cli_subscription en plus.
    """
    current = _read_engine_pref()
    available = _list_available_fallbacks(exclude=None)
    # Ajoute cli_subscription en tête s'il n'y est pas déjà
    has_cli = any(a.get("engine") == "cli_subscription" for a in available)
    if not has_cli:
        available = [{
            "engine": "cli_subscription",
            "label": "CLI Claude (subscription)",
        }] + list(available)
    return jsonify({
        "current": current,
        "available": available,
    })


# ============================================================ Sessions REST API (Phase A.7.2 v9)

@app.route("/api/sessions", methods=["GET"])
def api_sessions_list():
    """Liste les sessions persistées dans _sessions/. Métadonnées légères
    (pas le transcript complet : fetch /api/sessions/<id> pour ça)."""
    out = []
    if SESSIONS_DIR.exists():
        for path in sorted(SESSIONS_DIR.glob("*.json"), reverse=True):
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            stats = data.get("stats") or {}
            # Phase A.10 : compteur de stickies pour le modal d'import.
            stickies = data.get("stickies") or []
            stickies_count = sum(
                1 for s in stickies if isinstance(s, dict) and s.get("enabled", True)
            ) if isinstance(stickies, list) else 0
            out.append({
                "session_id": data.get("session_id") or path.stem,
                "label": data.get("label"),  # None si jamais renommé
                "matiere": data.get("matiere"),
                "type": data.get("type"),
                "num": data.get("num"),
                "exo": data.get("exo"),
                "annee": data.get("annee"),
                "mode": data.get("mode"),
                # Phase A.8.6 : exposés pour findExistingSession côté JS
                # (différenciation mode/format/anchor) et pour l'affichage
                # de l'historique (chip mode + format + anchor).
                "colle_format": data.get("colle_format"),
                "corrige_anchor": data.get("corrige_anchor"),
                # Phase A.12.3 : workspace_root exposé pour que
                # findExistingSession matche les sessions workspace (dont
                # matiere/type/num sont synthétisés backend-side et absents
                # du body du formulaire au moment du submit).
                "workspace_root": data.get("workspace_root"),
                "started_at": data.get("started_at"),
                "ended_at": data.get("ended_at"),
                "last_alive": data.get("last_alive"),
                "interrupted": bool(data.get("interrupted")),
                "n_exchanges": int(stats.get("total_exchanges") or 0),
                "stickies_count": stickies_count,  # Phase A.10
                "has_resume_summary": bool(data.get("resume_summary")),
            })
    return jsonify({"sessions": out})


@app.route("/api/sessions/<session_id>", methods=["GET"])
def api_sessions_get(session_id: str):
    """Retourne le JSON complet d'une session (transcript inclus)."""
    path = _session_path(session_id)
    if path is None or not path.exists():
        return jsonify({"error": "session introuvable"}), 404
    try:
        with path.open("r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except (OSError, json.JSONDecodeError) as e:
        return jsonify({"error": f"lecture impossible : {e}"}), 500


@app.route("/api/sessions/<session_id>", methods=["DELETE"])
def api_sessions_delete(session_id: str):
    """Supprime un fichier de session. Refusé si c'est la session active
    in-memory (à finaliser via /api/end_session d'abord)."""
    global _state
    with _state_lock:
        if _state is not None and _state.session_state.data.get("session_id") == session_id:
            return jsonify({
                "error": "session active : utilisez /api/end_session d'abord",
            }), 409
    path = _session_path(session_id)
    if path is None or not path.exists():
        return jsonify({"error": "session introuvable"}), 404
    # Phase A.8.5 hotfix : backup automatique dans _sessions/_trash/
    # avant DELETE. Permet récupération si l'user a cliqué « Démarrer
    # une nouvelle » par erreur dans le modal conflict. Bug observé
    # 2026-05-12 : user a perdu une session de 55 messages en cliquant
    # par mégarde sur l'option destructive. Rotation FIFO 20 derniers.
    try:
        _backup_session_before_delete(path, session_id)
    except Exception:  # noqa: BLE001 (best-effort, ne bloque pas le DELETE)
        logger.exception("backup session avant DELETE a leve, on continue")
    try:
        path.unlink()
    except OSError as e:
        return jsonify({"error": f"suppression impossible : {e}"}), 500
    return ("", 204)


def _backup_session_before_delete(src_path: Path, session_id: str) -> None:
    """Phase A.8.5 hotfix : copie la session JSON dans _sessions/_trash/
    avant suppression. Format de nom : ``<id>__deleted_<YYYYMMDD-HHMMSS>.json``.

    Rotation FIFO : on garde les 20 backups les plus récents, les plus
    anciens sont retirés (le user pourra toujours les retrouver via
    l'historique OneDrive le cas échéant).
    """
    import shutil
    from datetime import datetime as _dt
    trash_dir = SESSIONS_DIR / "_trash"
    trash_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt.now().strftime("%Y%m%d-%H%M%S")
    dest = trash_dir / f"{session_id}__deleted_{ts}.json"
    shutil.copy2(src_path, dest)
    logger.info("session backup avant DELETE : %s → %s", src_path.name, dest.name)
    # Rotation FIFO : garde les 20 plus récents
    try:
        existing = sorted(trash_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in existing[20:]:
            try:
                old.unlink()
            except OSError:
                pass
    except Exception:  # noqa: BLE001
        pass


@app.route("/api/sessions/<session_id>", methods=["PATCH"])
def api_sessions_patch(session_id: str):
    """Met à jour le champ ``label`` d'une session (rename utilisateur).
    Body ``{"label": "Mon nom personnalisé"}`` ou ``{"label": null}`` pour
    réinitialiser. Le label apparaît dans la sidebar à la place du
    libellé auto.
    """
    body = request.get_json(silent=True) or {}
    if "label" not in body:
        return jsonify({"error": "champ 'label' requis"}), 400
    label = body["label"]
    if label is not None and not isinstance(label, str):
        return jsonify({"error": "label doit être une string ou null"}), 400
    if isinstance(label, str):
        label = label.strip()[:120] or None  # cap longueur, vide → null
    path = _session_path(session_id)
    if path is None or not path.exists():
        return jsonify({"error": "session introuvable"}), 404
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        data["label"] = label
        from utils import atomic_write_json as _atomic_write
        _atomic_write(path, data)
    except (OSError, json.JSONDecodeError) as e:
        return jsonify({"error": f"écriture impossible : {e}"}), 500
    return jsonify({"ok": True, "label": label})


def _session_path(session_id: str) -> Optional[Path]:
    """Résolution sécurisée d'un session_id vers son fichier. Refuse les
    chemins traversants (``..``, ``/``, ``\\``) et exige un format type
    ``YYYY-MM-DD_MAT_TYPN_exN`` (caractères safe)."""
    if not session_id or "/" in session_id or "\\" in session_id or ".." in session_id:
        return None
    if not all(c.isalnum() or c in "-_" for c in session_id):
        return None
    return SESSIONS_DIR / f"{session_id}.json"


# ============================================================ Resume session (Phase A.7.2 v9)

@app.route("/api/resume_session", methods=["POST"])
def api_resume_session():
    """Reprend une session existante depuis _sessions/. Body ``{session_id}``.

    Stratégie selon ancienneté :
    - **Récente** (< 10 tours OU last_alive < 6h) : replay complet du
      transcript dans l'historique du nouveau ClaudeClient. Le tuteur a
      tout le contexte fin.
    - **Ancienne** (≥ 10 tours ET ≥ 6h) : résumé en 1 message (≤120 mots)
      injecté comme tour synthétique. Économise les tokens à chaque
      réplique suivante. Le résumé est généré 1 fois et caché dans le
      JSON (champ ``resume_summary``) pour éviter les regen.
    """
    try:
        return _api_resume_session_impl()
    except Exception as e:  # noqa: BLE001 (top-level: log + 500 JSON, no crash)
        logger.exception("resume_session a leve une exception non catchee")
        return jsonify({"error": f"reprise impossible : {type(e).__name__}: {e}"}), 500


def _api_resume_session_impl():
    global _state
    body = request.get_json(silent=True) or {}
    sid = body.get("session_id")
    if not sid:
        return jsonify({"error": "session_id requis"}), 400
    logger.info("resume_session: début sid=%s", sid)
    path = _session_path(sid)
    if path is None or not path.exists():
        return jsonify({"error": "session introuvable"}), 404
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return jsonify({"error": f"lecture impossible : {e}"}), 500

    # Reconstruction du SessionContext (re-résolution des chemins fichiers)
    rebuild_body = {
        "matiere": data.get("matiere"),
        "type": data.get("type"),
        "num": data.get("num"),
        "exo": data.get("exo"),
        "annee": data.get("annee"),
    }
    # Phase A.9 : restaure workspace_root depuis le JSON pour les
    # sessions workspace (sinon _build_session_context retomberait sur
    # le pipeline COURS et tenterait de résoudre un énoncé inexistant).
    if data.get("workspace_root"):
        rebuild_body["workspace_root"] = data["workspace_root"]
        rebuild_body["workspace_focus_subdir"] = data.get(
            "workspace_focus_subdir", ""
        )
        rebuild_body["workspace_excludes"] = data.get(
            "workspace_excludes", []
        )
    # Phase S4 (Cartable) : restaure la source DROIT depuis le JSON pour que
    # _build_session_context reparte sur l'arbo DROIT (transcription + fiche)
    # plutôt que sur le pipeline COURS. matiere/type/num sont déjà dans
    # rebuild_body (slug / CM|TD / num).
    if data.get("source") == "droit":
        rebuild_body["source"] = "droit"
    try:
        ctx = _build_session_context(rebuild_body)
    except FileNotFoundError as e:
        return jsonify({"error": f"matériel introuvable pour reprise : {e}"}), 400
    logger.info("resume_session: ctx OK matiere=%s type=%s num=%s exo=%s",
                rebuild_body.get("matiere"), rebuild_body.get("type"),
                rebuild_body.get("num"), rebuild_body.get("exo"))

    mode = data.get("mode") or MODE_COLLE
    # Phase v15.7.4 : restaure le format colle persisté (défaut "mixte"
    # pour les anciennes sessions sans le champ).
    colle_format = data.get("colle_format") or "mixte"
    if colle_format not in ("oral", "photos", "mixte"):
        colle_format = "mixte"
    # Phase v15.7.30 : restaure le mode d'ancrage corrigé persisté
    # (défaut "strict" = comportement v0.5 historique pour les anciennes
    # sessions sans le champ).
    corrige_anchor = data.get("corrige_anchor") or "strict"
    if corrige_anchor not in ("strict", "consultatif", "aucun"):
        corrige_anchor = "strict"
    engine = _read_engine_pref()
    logger.info(
        "resume_session: mode=%s engine=%s colle_format=%s corrige_anchor=%s",
        mode, engine, colle_format, corrige_anchor,
    )
    # Phase A.8 → A.9 : sélection prompt selon les 4 modes.
    if mode == MODE_GUIDE:
        prompt_path = PROMPT_SYSTEME_GUIDE_PATH
    elif mode == MODE_DECOUVERTE:
        prompt_path = PROMPT_SYSTEME_DECOUVERTE_PATH
    elif mode == MODE_WORKSPACE:
        prompt_path = PROMPT_SYSTEME_WORKSPACE_PATH
    else:
        prompt_path = PROMPT_SYSTEME_PATH
    try:
        if mode == MODE_WORKSPACE and ctx.workspace_root:
            prompt_cours_root = ctx.workspace_root
        elif ctx.droit_source is not None:
            prompt_cours_root = CARTABLE_ROOT / ctx.droit_source
        else:
            prompt_cours_root = COURS_ROOT
        builder = PromptBuilder(prompt_path, prompt_cours_root)
    except OSError as e:
        return jsonify({"error": f"prompt système absent : {e}"}), 500

    # Recycle le SessionState (on continue d'écrire dans le même fichier)
    session_state = SessionState.load(path)
    from utils import now_iso as _now_iso
    session_state.set_meta("resumed_at", _now_iso())
    session_state.set_meta("interrupted", False)
    session_state.set_meta("interrupted_at", None)
    session_state.set_meta("ended_at", None)
    logger.info("resume_session: SessionState chargé + meta updated")

    # Phase A.9 : même override qu'au start, workspace_root devient le cwd
    # subprocess pour scoper Read/Grep/Glob au dossier choisi.
    # Phase S4 (Cartable) : idem pour le droit, cwd = dossier de la matière.
    if mode == MODE_WORKSPACE and ctx.workspace_root:
        client_cours_root = ctx.workspace_root
    elif ctx.droit_source is not None:
        client_cours_root = CARTABLE_ROOT / ctx.droit_source
    else:
        client_cours_root = COURS_ROOT
    client = ClaudeClient(
        engine=engine,
        system_prompt=builder.system_prompt,
        mode=mode,
        cours_root=client_cours_root,
    )
    logger.info("resume_session: ClaudeClient construit")
    # Contexte initial (énoncé/corrigé/perso/CM) : toujours en 1ʳᵉ position
    initial = builder.build_initial_context_message(
        ctx, mode=mode, colle_format=colle_format,
        corrige_anchor=corrige_anchor,
    )
    client.append_user_message(initial)
    logger.info("resume_session: contexte initial appended (%d chars)", len(initial))

    transcript = data.get("transcript") or []
    use_replay = _should_replay_transcript(data)
    summary_used = None
    if use_replay:
        # Replay : push chaque tour dans l'historique du client
        for entry in transcript:
            role = "user" if entry.get("role") == "student" else "assistant"
            text = (entry.get("text") or "").strip()
            if not text:
                continue
            client._history.append({"role": role, "content": text})
    else:
        # Résumé : check cache, génère sinon.
        # Phase v15.7.25 : invalider le cache si obsolète. Avant ce fix,
        # un résumé généré au tour 30 (par ex « arrêt sur exo 1 ») restait
        # utilisé même après 60 nouveaux tours (qui ont fait passer à
        # l'exo 2). Le tuteur reprenait alors avec le contexte d'exo 1
        # → régression majeure perçue par l'utilisateur.
        summary = data.get("resume_summary")
        summary_at = data.get("resume_summary_at")
        if summary and summary_at and transcript:
            last_msg = transcript[-1]
            last_at = (last_msg.get("at") or "").strip()
            if last_at and last_at > summary_at:
                logger.info(
                    "resume_summary obsolète (dernier msg %s > résumé %s) : regen",
                    last_at, summary_at,
                )
                summary = None
        if not summary:
            try:
                summary = _generate_resume_summary(transcript, engine)
            except Exception as e:  # noqa: BLE001
                logger.exception("Génération résumé a leve : %s", e)
                # Fallback : replay quand même, mieux que rien
                for entry in transcript:
                    role = "user" if entry.get("role") == "student" else "assistant"
                    text = (entry.get("text") or "").strip()
                    if text:
                        client._history.append({"role": role, "content": text})
                use_replay = True
                summary = None
            if summary:
                session_state.set_meta("resume_summary", summary)
                session_state.set_meta("resume_summary_at", _now_iso())
        if summary:
            synthetic = (
                f"[Reprise de session : résumé de la séance précédente]\n\n{summary}\n\n"
                f"Reprenez en une phrase pour situer où on en était, puis "
                f"attendez l'intervention de l'étudiant."
            )
            client.append_user_message(synthetic)
            summary_used = summary

    with _state_lock:
        if _state is not None:
            try:
                _state.session_state.finalize(interrupted=True)
            except Exception:
                logger.exception("Cleanup ancien state a leve")
        _state = CompanionSession(session_state, client, builder)

    logger.info(
        "Session reprise : %s (mode=%s, %s)",
        sid, mode, "replay" if use_replay else "résumé",
    )
    _kickoff_corrige_prerasterize(ctx)
    return jsonify({
        "ok": True,
        "session_id": data.get("session_id"),
        "mode": mode,
        "engine": engine,
        "replayed": use_replay,
        "summary_used": bool(summary_used),
        "transcript": _annotate_transcript_with_branches(
            transcript, session_state.data.get("messages") or {},
        ),
        "guided_index": data.get("guided_index", 0),
        "auto_advance": bool(session_state.data.get("auto_advance")),
        "colle_format": colle_format,
        "corrige_anchor": corrige_anchor,
        # Phase A.10.15 : exposer le contexte pour que le front puisse
        # synchroniser le form de démarrage avec la session reprise (le
        # user voit alors la bonne matière/type/num/exo dans l'entête,
        # plus l'incohérence « je suis en AN1 mais le form affiche PRG2 »).
        "matiere": data.get("matiere"),
        "type": data.get("type"),
        "num": data.get("num"),
        "exo": data.get("exo"),
        "annee": data.get("annee"),
        "sujet_libre": data.get("sujet_libre"),
        "workspace_root": data.get("workspace_root"),
    })


def _should_replay_transcript(data: dict) -> bool:
    """Décide replay (True) ou résumé (False) selon la longueur du transcript.

    Phase A.8.6 : replay par défaut, résumé **uniquement** au-delà du seuil
    ``replay_hard_cap_exchanges`` (lu live depuis `_secrets/runtime_settings.json`,
    éditable depuis la GUI Tk panneau Quota). Le critère « 6h d'inactivité »
    historique est supprimé : il faisait perdre tout le contexte fin
    (notes prises pendant la séance, points abordés, où on s'arrêtait)
    au moindre passage de nuit, alors que l'utilisateur préfère
    explicitement le coût en tokens d'un replay complet.

    Le hard cap reste pour les vraies bombes (300 tours par défaut ≈
    plusieurs centaines de milliers de tokens). En pratique, les sessions
    usuelles font 30-80 tours. L'utilisateur peut remonter ce seuil
    depuis le launcher pour les cas extrêmes où il veut quand même
    replay tout, ou le descendre pour économiser des tokens.
    """
    n = int((data.get("stats") or {}).get("total_exchanges") or 0)
    try:
        from runtime_settings import get_replay_hard_cap_exchanges
        cap = get_replay_hard_cap_exchanges()
    except Exception:  # noqa: BLE001 (fallback dur si import / settings cassé)
        cap = 300
    return n < cap


def _generate_resume_summary(transcript: list, engine: str) -> str:
    """Appelle un LLM (sync) pour résumer le transcript en ≤120 mots.

    Phase v15.7.25 : engine paramètre conservé pour rétrocompat mais on
    force `gemini_api` + `gemini-2.5-flash` à l'intérieur (pattern aligné
    sur `/api/refine_search_query` v15.7.14 et `/api/ocr_photo` v15.7.20).
    Raisons : latence ~1-2s vs 5-10s sur Opus, coût négligeable, et
    cohérence quel que soit le moteur de la séance principale. Une
    reprise de session ne devrait pas attendre 10s pour qu'un résumé
    soit prêt avant que le tuteur reparte.
    """
    if not transcript:
        return "(Pas de tour précédent : séance ouverte sans interaction.)"
    lines = []
    for entry in transcript:
        role_tag = "Tuteur" if entry.get("role") == "claude" else "Étudiant"
        text = (entry.get("text") or "").strip()
        if text:
            lines.append(f"{role_tag} : {text}")
    transcript_str = "\n\n".join(lines)

    sys_prompt = (
        "Tu es un assistant qui résume des sessions de révision orale. "
        "Tu produis des résumés concis, structurés, factuels, en français."
    )
    user_msg = (
        "Résume cette session de révision pour reprise ultérieure.\n\n"
        "Format : 1 paragraphe ≤120 mots. Focus sur ce qui a été acquis "
        "(concepts, formules, théorèmes verrouillés), où on s'est arrêté "
        "(slide N, exo M, ou point conceptuel précis), difficultés "
        "évidentes, concept laissé en suspens. Pas de méta type « la session "
        "a porté sur... ». Commence directement par le contenu.\n\n"
        "**ATTENTION** : si l'étudiant a abordé plusieurs exercices (ex 1, "
        "puis ex 2), focalise-toi sur le DERNIER en cours, pas le premier. "
        "Le tuteur va reprendre à partir du dernier point d'arrêt.\n\n"
        f"Transcript :\n{transcript_str}"
    )

    # Phase v15.7.25 : force Gemini Flash pour vitesse + cohérence
    # cross-engine (l'utilisateur peut être sur Opus / DeepSeek / etc.
    # pour la séance, mais le résumé doit toujours être rapide).
    summarizer = ClaudeClient(
        engine="gemini_api",
        model="gemini-2.5-flash",
        system_prompt=sys_prompt,
        mode=MODE_COLLE,
        cours_root=COURS_ROOT,
    )
    summarizer.append_user_message(user_msg)

    chunks: list[str] = []

    def on_event(ev: ParserEvent) -> None:
        if ev.type == ParserEventType.TEXT_CHUNK:
            chunks.append(str(ev.payload))

    summarizer.stream_response(on_event=on_event)
    return "".join(chunks).strip()


def _annotate_transcript_with_branches(transcript: list, messages: dict) -> list:
    """Annote chaque entry du transcript avec sibling_count + sibling_index
    pour que le front affiche les flèches < N/M > là où il y a plusieurs
    branches. Travaille sur une copie : ne mute pas le transcript original.
    """
    if not messages:
        return [dict(e) for e in transcript]
    # Index frères par parent_id
    by_parent: dict = {}
    for m in messages.values():
        by_parent.setdefault(m.get("parent_id"), []).append(m)
    for siblings in by_parent.values():
        siblings.sort(key=lambda m: m.get("at", ""))
    annotated = []
    for entry in transcript:
        e = dict(entry)
        siblings = by_parent.get(entry.get("parent_id"), [])
        e["sibling_count"] = len(siblings)
        try:
            e["sibling_index"] = next(
                i for i, s in enumerate(siblings) if s.get("id") == entry.get("id")
            )
        except StopIteration:
            e["sibling_index"] = 0
        # Ids des frères dans l'ordre, pour que le front puisse switcher
        e["sibling_ids"] = [s.get("id") for s in siblings]
        annotated.append(e)
    return annotated


_EDIT_NOTE_PREFIXES = (
    "[Note système : ce message a été édité par l'étudiant après envoi initial]\n\n",
    "[Note système : cette réponse a été éditée manuellement par l'étudiant après réception]\n\n",
)


def _strip_edit_note(text: str) -> str:
    """Retire le préfixe « note d'édition » d'un content de _history s'il
    existe, pour que le match par contenu ne soit pas cassé après une
    édition antérieure (cf. api_messages_patch)."""
    if not isinstance(text, str):
        return text
    for pfx in _EDIT_NOTE_PREFIXES:
        if text.startswith(pfx):
            return text[len(pfx):]
    return text


_PATCH_IMAGE_MD_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def _ocr_new_images_in_edited_text(
    old_text: str, new_text: str, session_data: dict,
) -> tuple[str, list[dict], list[dict]]:
    """Phase A.10.13.bug3 (2026-05-14) : détecte les images ajoutées dans
    un message édité (nouvelles refs `![alt](_uploads/...)` absentes de
    `old_text`) et lance OCR + rename + append OCR block, en miroir de
    ce que fait `api_send_message` pour `pending_attachments`.

    Frictions résolues : à l'édition, le markdown image est injecté dans
    le textarea via `refreshAttachmentsTray` redirection (cf. app.js
    A.8.5) puis le pending_attachment est DELETE'd. PATCH ne consommait
    aucune queue → aucune OCR → tuteur recevait l'image brute sans
    double-check pré-traité (régression vs send_message normal).

    Retourne ``(new_text_with_ocr, photos_to_add, ocr_blocks)`` :
    - new_text_with_ocr : texte avec OCR block appendé + paths renommés
    - photos_to_add : entries à pousser dans `session_photos`
    - ocr_blocks : blocs OCR pour le retour API (utile au debug front)
    """
    # Gating identique à api_send_message : OCR seulement en photos/mixte
    mode = session_data.get("mode") or MODE_COLLE
    colle_format = session_data.get("colle_format", "mixte")
    if mode not in (MODE_COLLE, MODE_DECOUVERTE):
        return new_text, [], []
    if colle_format not in ("photos", "mixte"):
        return new_text, [], []

    old_paths = {m.group(2) for m in _PATCH_IMAGE_MD_RE.finditer(old_text or "")}
    new_imgs = [
        (m.group(1), m.group(2))
        for m in _PATCH_IMAGE_MD_RE.finditer(new_text)
        if m.group(2) not in old_paths
    ]
    if not new_imgs:
        return new_text, [], []

    hint = _get_last_tutor_text_for_ocr_hint()
    photos_added: list[dict] = []
    ocr_blocks: list[dict] = []

    for alt, ref_path in new_imgs:
        # Déduit storage + rel_path bare depuis le préfixe `_uploads/`
        # (cf. A.10.2). Pas de préfixe = legacy storage="cours".
        if ref_path.startswith("_uploads/"):
            storage = "uploads"
            rel_bare = ref_path[len("_uploads/"):]
            base_root = UPLOADS_DIR
        else:
            storage = "cours"
            rel_bare = ref_path
            base_root = COURS_ROOT
        try:
            abs_path = (base_root / rel_bare).resolve()
            abs_path.relative_to(base_root.resolve())
        except (ValueError, OSError):
            logger.warning("PATCH OCR : path hors %s : %s", storage, ref_path)
            continue
        if not abs_path.is_file():
            logger.warning("PATCH OCR : fichier absent : %s", abs_path)
            continue
        att = {
            "id": f"att_patch_{uuid.uuid4().hex[:10]}",
            "rel_path": rel_bare,
            "filename": abs_path.name,
            "original_name": alt or abs_path.name,
            "mime": "image/jpeg",
            "size_bytes": abs_path.stat().st_size,
            "is_image": True,
            "storage": storage,
        }
        ocr = _ocr_attachment_internal(att, hint=hint)
        if ocr is None:
            continue
        # Rename via OCR (best-effort, peut retourner None si OCR médiocre)
        renamed = _rename_photo_from_ocr(att, ocr)
        if renamed:
            att["rel_path"] = renamed["rel_path"]
            att["filename"] = renamed["filename"]
            new_ref = (
                f"_uploads/{renamed['rel_path']}"
                if storage == "uploads"
                else renamed["rel_path"]
            )
            new_text = new_text.replace(ref_path, new_ref)
        ocr_blocks.append({"attachment_id": att["id"], **ocr})
        from utils import now_iso as _now_iso_patch_photo
        photos_added.append({
            "id": att["id"],
            "rel_path": att["rel_path"],
            "filename": att["filename"],
            "original_name": alt or att["filename"],
            "mime": att["mime"],
            "size_bytes": att["size_bytes"],
            "sent_at": _now_iso_patch_photo(),
            "storage": storage,
        })

    if ocr_blocks:
        ocr_text_parts = [
            "\n\n[OCR pré-traitée par Gemini Flash 2.5 : "
            "vérifie qu'elle correspond à ta lecture multimodale, "
            "sinon dis-le et signale la divergence à l'étudiant]:"
        ]
        for blk in ocr_blocks:
            ocr_text_parts.append(
                f"\n\n--- OCR de l'image ---\n"
                f"Type détecté : {blk.get('kind_detected', '?')}\n"
                f"Complétude estimée : {blk.get('completeness_pct', '?')}%\n"
                + (f"Warnings : {', '.join(blk.get('warnings') or [])}\n"
                   if blk.get('warnings') else "")
                + f"\n{blk.get('ocr_markdown', '')}"
            )
        new_text = new_text + "".join(ocr_text_parts)

    return new_text, photos_added, ocr_blocks


@app.route("/api/messages/<int:index>", methods=["PATCH"])
def api_messages_patch(index: int):
    """Modifie un message existant. Body ``{"text": str, "as_branch"?: bool}``.

    - ``as_branch=False`` (default) : édition in-place (transcript[index].text
      changé + edited_at posé). Le _history du client est sync via préfixe
      « note système ».
    - ``as_branch=True`` : crée une nouvelle branche en partant du parent
      du message (le message original reste accessible via les flèches
      < N/M >). Le current_branch_path bascule sur la nouvelle branche.
      Les messages enfants de l'original sont décrochés du chemin courant
      mais conservés dans le graphe : ils restent accessibles via switch.

    Met à jour _history du client en conséquence (rebuild complet en cas
    de branch, sync préfixe en cas d'edit in-place).
    """
    global _state
    try:
        # Phase A.10.13.bug3, étape 1 : validation + snapshot sous lock,
        # release pour pouvoir lancer l'OCR (qui réacquiert _state_lock
        # via _get_last_tutor_text_for_ocr_hint, et qui prend 5-10s sur
        # Gemini Flash).
        with _state_lock:
            if _state is None:
                return jsonify({"error": "pas de session active"}), 409
            body = request.get_json(silent=True) or {}
            new_text = body.get("text")
            as_branch = bool(body.get("as_branch", False))
            silent = bool(body.get("silent", False))
            if not isinstance(new_text, str) or not new_text.strip():
                return jsonify({"error": "champ 'text' non vide requis"}), 400
            new_text = new_text.strip()
            ss = _state.session_state
            transcript = ss.data.get("transcript") or []
            if index < 0 or index >= len(transcript):
                return jsonify({
                    "error": f"index hors plage : {index} (transcript a {len(transcript)} entrées)",
                }), 400
            old_entry = transcript[index]
            old_text = (old_entry.get("text") or "").strip()
            if old_text == new_text:
                return jsonify({"ok": True, "unchanged": True, "text": new_text})
            # Snapshot pour l'OCR hors-lock. On copie les champs utiles pour
            # le gating (mode, colle_format) : pas de référence dict directe
            # pour éviter une mutation concurrente.
            session_data_snapshot = {
                "mode": ss.data.get("mode") or MODE_COLLE,
                "colle_format": ss.data.get("colle_format", "mixte"),
            }
            # Gating OCR : uniquement pour les messages student en édit
            # in-place (pas branch, pas silent). En branch, le contenu
            # est utilisé pour créer une nouvelle entrée : l'OCR doit
            # courir aussi. En silent, c'est du nettoyage utilitaire,
            # pas une vraie modif → skip OCR.
            should_run_ocr = (
                not silent
                and old_entry.get("role") == "student"
            )

        # Étape 2 : OCR hors-lock pour les nouvelles images détectées.
        # Best-effort : si OCR rate, on continue avec new_text inchangé.
        patch_ocr_blocks: list[dict] = []
        patch_photos_added: list[dict] = []
        if should_run_ocr:
            try:
                new_text, patch_photos_added, patch_ocr_blocks = (
                    _ocr_new_images_in_edited_text(
                        old_text, new_text, session_data_snapshot,
                    )
                )
            except Exception:  # noqa: BLE001 (best-effort)
                logger.exception("PATCH OCR a levé, continue sans OCR")

        # Étape 3 : application des modifications sous lock.
        with _state_lock:
            if _state is None:
                return jsonify({"error": "pas de session active"}), 409
            ss = _state.session_state
            transcript = ss.data.get("transcript") or []
            # Re-vérif index (le transcript a pu changer si une autre
            # requête a édité entre-temps : improbable en single-user
            # mais on garde la cohérence).
            if index < 0 or index >= len(transcript):
                return jsonify({
                    "error": f"index hors plage : {index} (transcript a {len(transcript)} entrées)",
                }), 400
            old_entry = transcript[index]
            target_msg_id = old_entry.get("id")
            # Ajoute les nouvelles photos OCR'd à la galerie session_photos.
            if patch_photos_added:
                existing_photos = list(
                    ss.data.get("session_photos") or []
                )
                existing_photos.extend(patch_photos_added)
                ss.set_meta("session_photos", existing_photos)

            if as_branch and target_msg_id:
                # Crée une nouvelle branche : l'original est conservé dans
                # le graphe, accessible via switch. Le _history du client
                # est entièrement reconstruit pour matcher le nouveau path.
                new_entry = ss.create_branch_at(target_msg_id, new_text)
                _rebuild_history_from_path(_state)
                logger.info(
                    "messages/patch (branch): index=%d original=%s nouveau=%s",
                    index, target_msg_id, new_entry["id"],
                )
                return jsonify({
                    "ok": True,
                    "branched": True,
                    "new_id": new_entry["id"],
                    "original_id": target_msg_id,
                    "edited_at": new_entry.get("at"),
                })

            # Édition in-place (default)
            if target_msg_id:
                if silent:
                    # Pas de edited_at, pas de note système → écriture directe
                    ss.data["messages"][target_msg_id]["text"] = new_text
                    ss.data["transcript"] = ss._derive_transcript()
                    from utils import atomic_write_json as _atomic_write
                    _atomic_write(ss.path, ss.data)
                else:
                    ss.edit_message_in_place(target_msg_id, new_text)
            else:
                # Vieux schéma sans id : bascule via le helper legacy
                from utils import now_iso as _now_iso
                transcript[index]["text"] = new_text
                transcript[index]["edited_at"] = _now_iso()
                ss.data["transcript"] = transcript
                from utils import atomic_write_json as _atomic_write
                _atomic_write(ss.path, ss.data)

            # Sync _history du client (match par role + contenu sur indices
            # candidats). Le contenu côté _history reçoit en plus un
            # préfixe « note système » pour que le tuteur voie que le
            # message a été édité : utile pour la cohérence quand l'étudiant
            # troll un message ou corrige sa propre formulation après coup.
            history = _state.client._history
            target_role = "user" if old_entry.get("role") == "student" else "assistant"
            note_prefix = (
                "[Note système : ce message a été édité par l'étudiant après envoi initial]\n\n"
                if target_role == "user"
                else "[Note système : cette réponse a été éditée manuellement par l'étudiant après réception]\n\n"
            )
            # Old text dans _history peut déjà avoir un note_prefix (rééd).
            # On match en stripant les deux variantes possibles.
            updated = False
            for offset in (1, 2):
                hidx = index + offset
                if hidx < 0 or hidx >= len(history):
                    continue
                msg = history[hidx]
                if msg.get("role") != target_role:
                    continue
                hist_text = msg.get("content")
                if not isinstance(hist_text, str):
                    continue
                if _strip_edit_note(hist_text).strip() == old_text:
                    # silent=True : juste mettre à jour le contenu sans
                    # ajouter de note système (utile quand on retire une
                    # pièce jointe : pas une vraie modif de fond).
                    history[hidx]["content"] = (
                        new_text if silent else note_prefix + new_text
                    )
                    updated = True
                    break
            if not updated:
                logger.warning(
                    "messages/patch: pas trouvé l'entrée correspondante dans "
                    "_history (index=%d role=%s) : transcript modifié seul",
                    index, target_role,
                )
        logger.info(
            "messages/patch: édité index=%d role=%s (%d→%d chars, "
            "ocr_blocks=%d, photos_added=%d)",
            index, old_entry.get("role"), len(old_text), len(new_text),
            len(patch_ocr_blocks), len(patch_photos_added),
        )
        return jsonify({
            "ok": True,
            "text": new_text,
            "edited_at": transcript[index].get("edited_at"),
            # Phase A.10.13.bug3 : OCR blocks pour les nouvelles images
            # détectées dans le texte édité (mode photos/mixte uniquement).
            # Front peut afficher en collapsible si voulu.
            "ocr_blocks": patch_ocr_blocks,
        })
    except Exception as e:  # noqa: BLE001
        logger.exception("messages/patch a leve")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/messages/<msg_id>/siblings", methods=["GET"])
def api_messages_siblings(msg_id: str):
    """Retourne les messages frères (même parent_id) pour afficher
    les flèches < N/M > sous les messages avec branches multiples."""
    global _state
    try:
        with _state_lock:
            if _state is None:
                return jsonify({"error": "pas de session active"}), 409
            ss = _state.session_state
            try:
                siblings = ss.get_siblings(msg_id)
            except KeyError:
                return jsonify({"error": "message inconnu"}), 404
            current_path = ss.data.get("current_branch_path") or []
            current_id = None
            for sid in [s["id"] for s in siblings]:
                if sid in current_path:
                    current_id = sid
                    break
        return jsonify({
            "siblings": siblings,
            "current_id": current_id,
            "count": len(siblings),
        })
    except Exception as e:  # noqa: BLE001
        logger.exception("messages/siblings a leve")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/messages/<int:index>/regenerate", methods=["POST"])
def api_messages_regenerate(index: int):
    """Tronque le current_branch_path après l'index donné et arme le
    streaming pour générer une nouvelle réponse du tuteur. Utilisé par
    le bouton « 🔄 Recharger contexte » de l'éditeur (style Gemini AI
    Studio).

    Logique :
    - Si le message ciblé est ``student`` → on garde le student inclus,
      on tronque tout ce qui suit. Le prochain stream_response va
      générer la réponse claude depuis ce point.
    - Si le message ciblé est ``claude`` → on retire aussi le claude
      (la régen va le remplacer). Path tronqué jusqu'à index exclu, le
      dernier message restant est forcément student.
    """
    global _state
    try:
        with _state_lock:
            if _state is None:
                return jsonify({"error": "pas de session active"}), 409
            ss = _state.session_state
            transcript = ss.data.get("transcript") or []
            if index < 0 or index >= len(transcript):
                return jsonify({
                    "error": f"index hors plage : {index}",
                }), 400
            target = transcript[index]
            cut_idx = index if target.get("role") == "claude" else (index + 1)
            path = ss.data.get("current_branch_path") or []
            ss.data["current_branch_path"] = path[:cut_idx]
            ss.data["transcript"] = ss._derive_transcript()
            from utils import atomic_write_json as _atomic_write
            _atomic_write(ss.path, ss.data)
            _rebuild_history_from_path(_state)
            # Force la prochaine /api/stream_response à streamer sans
            # consommer pending_user_text (déjà à jour via _history).
            _state.retry_pending = True
            _state.initial_stream_pending = False
            _state.pending_user_text = None
            new_transcript = _annotate_transcript_with_branches(
                ss.data.get("transcript") or [],
                ss.data.get("messages") or {},
            )
        logger.info("messages/regenerate: tronqué après index=%d (%s)",
                    index, target.get("role"))
        return jsonify({"ok": True, "transcript": new_transcript})
    except Exception as e:  # noqa: BLE001
        logger.exception("messages/regenerate a leve")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/messages/<msg_id>/switch", methods=["POST"])
def api_messages_switch(msg_id: str):
    """Change la branche active pour passer par ``msg_id``. Reconstruit
    le _history du client en conséquence. Retourne le nouveau transcript."""
    global _state
    try:
        with _state_lock:
            if _state is None:
                return jsonify({"error": "pas de session active"}), 409
            ss = _state.session_state
            try:
                new_path = ss.switch_branch_to(msg_id)
            except KeyError:
                return jsonify({"error": "message inconnu"}), 404
            _rebuild_history_from_path(_state)
            transcript = _annotate_transcript_with_branches(
                ss.data.get("transcript") or [], ss.data.get("messages") or {},
            )
        logger.info("messages/switch: nouveau path %d ids", len(new_path))
        return jsonify({"ok": True, "transcript": transcript})
    except Exception as e:  # noqa: BLE001
        logger.exception("messages/switch a leve")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


def _rebuild_history_from_path(state) -> None:
    """Reconstruit ``client._history`` après un changement de branche.

    Le 1ᵉʳ message du _history (contexte initial du PromptBuilder) est
    conservé. Si il y avait un 2ᵉ message synthétique de reprise (résumé),
    il est conservé aussi. Tout le reste est recréé depuis le transcript
    courant (qui est dérivé du current_branch_path).
    """
    history = state.client._history
    transcript = state.session_state.data.get("transcript") or []
    # Trouve le préfixe à conserver : le contexte initial (toujours user, et
    # ne match aucun message du transcript), plus éventuellement un résumé
    # de reprise (user, contenu commençant par « [Reprise de session... »).
    preserved = []
    for msg in history:
        if msg.get("role") != "user":
            break
        content = msg.get("content") or ""
        if isinstance(content, str) and (
            content.startswith("[Reprise de session")
            or len(preserved) == 0  # le tout 1ᵉʳ message = contexte initial
        ):
            preserved.append(msg)
            continue
        break
    # Reconstruit la suite à partir du transcript
    rebuilt = list(preserved)
    for entry in transcript:
        role = "user" if entry.get("role") == "student" else "assistant"
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        # Si edited_at posé, on préfixe avec la note système
        if entry.get("edited_at"):
            note = (
                "[Note système : ce message a été édité par l'étudiant après envoi initial]\n\n"
                if role == "user"
                else "[Note système : cette réponse a été éditée manuellement par l'étudiant après réception]\n\n"
            )
            text = note + text
        rebuilt.append({"role": role, "content": text})
    state.client._history = rebuilt


_MARKER_SLIDE_RE = re.compile(
    r"\[Mode guidé\]\s*(?:.*?)slide\s+(\d+)\s*/\s*(\d+)",
    re.IGNORECASE,
)


def _is_guided_marker(text: str) -> bool:
    """True si le texte est un marker de transition slide injecté par
    sendGuidedSlideMeta côté front (commence par ``[Mode guidé]``)."""
    return bool(text) and text.lstrip().startswith("[Mode guidé]")


def _parse_marker_slide_index(text: str) -> Optional[int]:
    """Extrait l'index 0-based de la slide depuis un marker ``[Mode guidé]
    … slide N/M …``. Retourne None si pas matché."""
    if not _is_guided_marker(text):
        return None
    m = _MARKER_SLIDE_RE.search(text)
    if not m:
        return None
    try:
        return int(m.group(1)) - 1
    except (ValueError, TypeError):
        return None


@app.route("/api/messages/<int:index>", methods=["DELETE"])
def api_messages_delete(index: int):
    """Supprime un message du transcript courant (et du _history du
    ClaudeClient) sur session active. Utile pour nettoyer un échange
    raté avant une relance : équivalent du « delete message » de Gemini
    AI Studio.

    L'index est 0-based dans le transcript courant. Le ``_history`` du
    client a 1 entrée de plus en tête (le contexte initial), donc on
    supprime ``_history[index + 1]``. En cas de resume avec résumé, le
    premier message synthétique est aussi devant : on tente une
    correspondance par contenu, sinon on log et on supprime tel quel
    (le tuteur peut produire une réponse maladroite, pas un crash).
    """
    global _state
    try:
        with _state_lock:
            if _state is None:
                return jsonify({"error": "pas de session active"}), 409
            transcript = _state.session_state.data.get("transcript") or []
            if index < 0 or index >= len(transcript):
                return jsonify({
                    "error": f"index hors plage : {index} (transcript a {len(transcript)} entrées)",
                }), 400
            removed = transcript.pop(index)
            _state.session_state.data["transcript"] = transcript
            stats = _state.session_state.data.setdefault("stats", {})
            stats["total_exchanges"] = max(0, int(stats.get("total_exchanges", 0)) - 1)
            from utils import atomic_write_json as _atomic_write
            _atomic_write(_state.session_state.path, _state.session_state.data)

            # Synchronise le _history du client. Offset typique : +1 (le
            # contexte initial). En cas de resume avec résumé, l'offset
            # est +2 (initial + synthetic). On essaie de matcher par
            # contenu sur les indices candidats.
            history = _state.client._history
            target_role = "user" if removed.get("role") == "student" else "assistant"
            target_text = (removed.get("text") or "").strip()
            removed_from_history = False
            for offset in (1, 2):
                hidx = index + offset
                if hidx < 0 or hidx >= len(history):
                    continue
                msg = history[hidx]
                if msg.get("role") != target_role:
                    continue
                hist_text = msg.get("content")
                if _strip_edit_note(hist_text).strip() == target_text:
                    history.pop(hidx)
                    removed_from_history = True
                    break
            if not removed_from_history:
                logger.warning(
                    "messages/delete: pas trouvé l'entrée correspondante dans "
                    "_history (index=%d role=%s) : transcript supprimé seul",
                    index, target_role,
                )

            # Phase v15 : si on supprime un marker de transition slide,
            # on revient à la slide indiquée par le marker précédent (ou 0
            # si aucun marker antérieur). Cohérence : retirer la trace
            # « passé à slide N » doit aussi annuler la transition côté UI.
            new_guided_index = None
            if _is_guided_marker(removed.get("text") or ""):
                # Cherche le dernier marker dans le transcript restant
                # AVANT l'index supprimé (donc tout ce qui était antérieur).
                prev_marker_index = None
                for entry in reversed(transcript[:index]):
                    if _is_guided_marker(entry.get("text") or ""):
                        prev_marker_index = _parse_marker_slide_index(
                            entry.get("text") or "",
                        )
                        break
                new_guided_index = prev_marker_index if prev_marker_index is not None else 0
                _state.session_state.set_meta("guided_index", new_guided_index)
                logger.info(
                    "messages/delete: marker supprimé → retour slide %d",
                    new_guided_index,
                )
        logger.info("messages/delete: supprimé index=%d role=%s", index, removed.get("role"))
        return jsonify({
            "ok": True,
            "was_marker": _is_guided_marker(removed.get("text") or ""),
            "new_guided_index": new_guided_index,
        })
    except Exception as e:  # noqa: BLE001
        logger.exception("messages/delete a leve")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


def _generate_session_recap(
    transcript: list,
    mode: Optional[str] = None,
    matiere: Optional[str] = None,
) -> dict:
    """Phase v15.7.31 → A.9 : Récap de séance via Gemini Flash.

    Fait UN appel Gemini Flash qui scanne le transcript complet et produit
    un JSON structuré ``{summary, concepts_covered, exercises_handled,
    suggestions}``. Engine forcé pour vitesse + coût négligeable + cohérence
    cross-engine (la séance peut être sur Opus, DeepSeek, Gemini Pro, etc.,
    le récap doit rester rapide).

    Phase A.9 : paramètres ``mode`` et ``matiere`` ajoutés pour adapter
    le prompt LLM au type de séance : COURS (TD/TP/CC traditionnel),
    sujet libre, ou workspace. Sans ces paramètres le récap produit des
    résultats biaisés (terminologie « TD5 ex1 » sur une séance workspace).

    Retour fail-soft : si le LLM produit du JSON invalide, retourne un
    récap dégradé `{summary: "...", suggestions: []}` plutôt que de
    lever : l'utilisateur voit au moins un résumé textuel.
    """
    if not transcript:
        return {
            "summary": "(Pas de tour précédent : séance ouverte sans interaction.)",
            "concepts_covered": [],
            "exercises_handled": [],
            "suggestions": [],
        }
    lines = []
    for entry in transcript:
        role_tag = "Tuteur" if entry.get("role") == "claude" else "Étudiant"
        text = (entry.get("text") or "").strip()
        if text:
            lines.append(f"{role_tag} : {text}")
    transcript_str = "\n\n".join(lines)

    # Phase A.9 : contextualisation selon la source de la séance. Adapte
    # le vocabulaire dans le prompt LLM pour qu'il produise des labels
    # cohérents (« module xxx », « concept python xxx » en workspace au
    # lieu de « TD5 ex1 »).
    if mode == MODE_WORKSPACE or matiere == "WORKSPACE":
        kind_label = "exploration d'un dossier de projet sur disque (workspace)"
        exos_example = '["module src/auth.py", "section README §1", ...]'
        suggestions_example = (
            "« relire la docstring de fonction_X dans pkg/mod.py », "
            "« reformuler à voix haute le flow Y », « dessiner le diagramme "
            "des dépendances entre les modules Z et W »"
        )
    elif matiere == "LIBRE":
        kind_label = "apprentissage d'un sujet libre (hors cours académiques)"
        exos_example = '["concept de closures", "syntaxe async/await", ...]'
        suggestions_example = (
            "« revoir la définition de Y », « refaire un mini-exemple Z », "
            "« réciter à voix haute le pattern W »"
        )
    else:
        kind_label = "révision orale sur un exercice de TD/TP/CC"
        exos_example = '["TD5 ex1", "TD5 ex2 (partiel)", ...]'
        suggestions_example = (
            "« refaire l'ex 3 du TD5 sans regarder », « revoir la "
            "définition de continuité à gauche / à droite », « réciter "
            "à voix haute le théorème des accroissements finis »"
        )

    sys_prompt = (
        f"Tu es un assistant qui audite des sessions de {kind_label}. "
        "Tu produis exclusivement du JSON minifié valide, en français, "
        "factuel, sans paraphrase ni méta. Pas de markdown, pas de texte "
        "hors JSON."
    )
    user_msg = (
        f"Analyse cette session de {kind_label} et produis un JSON "
        "exactement à ce format (pas de texte avant/après, pas de "
        "fences ```json) :\n\n"
        "{\n"
        '  "summary": "1 paragraphe ≤150 mots : ce qui a été couvert, où on s\'est arrêté",\n'
        '  "concepts_covered": ["concept court 1", "concept 2", ...],\n'
        f'  "exercises_handled": {exos_example},\n'
        '  "suggestions": ["suggestion révision concrète 1", "...", ...]\n'
        "}\n\n"
        "RÈGLES pour `suggestions` :\n"
        "- 2 à 5 suggestions concrètes (ex : « refaire l'ex 3 du TD5 sans regarder », "
        "« revoir la définition de continuité à gauche / à droite », « réciter "
        "à voix haute le théorème des accroissements finis »).\n"
        "- Pas de méta type « continuez à travailler » : du concret.\n\n"
        f"Transcript :\n{transcript_str}"
    )

    summarizer = ClaudeClient(
        engine="gemini_api",
        model="gemini-2.5-flash",
        system_prompt=sys_prompt,
        mode=MODE_COLLE,
        cours_root=COURS_ROOT,
    )
    summarizer.append_user_message(user_msg)

    chunks: list[str] = []

    def on_event(ev: ParserEvent) -> None:
        if ev.type == ParserEventType.TEXT_CHUNK:
            chunks.append(str(ev.payload))

    summarizer.stream_response(on_event=on_event)
    raw = "".join(chunks).strip()
    # Strip défensif si Gemini a quand même ajouté des fences ```json
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Recap JSON invalide (%s) : fallback dégradé. Raw=%r", e, raw[:500])
        return {
            "summary": raw[:600] or "(Récap indisponible : JSON LLM invalide.)",
            "concepts_covered": [],
            "exercises_handled": [],
            "suggestions": [],
        }
    # Normalise les champs manquants (LLM peut omettre)
    parsed.setdefault("summary", "")
    parsed.setdefault("concepts_covered", [])
    parsed.setdefault("exercises_handled", [])
    parsed.setdefault("suggestions", [])
    return parsed


@app.route("/api/session_recap", methods=["POST"])
def api_session_recap():
    """Phase v15.7.31 : génère le récap post-séance et bascule en phase débrief.

    Sans body. Effets :
        - Lance ``_generate_session_recap(transcript)`` (Gemini Flash, ~3-8s)
        - Persiste ``recap`` + ``phase="debrief"`` + ``recap_at`` dans la
          session.
        - **NE finalise PAS** la session (heartbeat continue, _state reste).
        - Retourne `{ok, recap, phase}`.

    Idempotent : si ``phase`` est déjà ``"debrief"`` ou ``"closed"``,
    retourne le récap déjà persisté sans re-générer.

    Codes :
        200 : OK, recap généré ou retourné depuis cache
        409 : pas de session active
        502 : Gemini a échoué (JSON dégradé retourné quand même, code 200)
    """
    global _state
    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409

    # Idempotent : si déjà en phase debrief/closed, retourne ce qui est persisté
    existing_phase = st.session_state.data.get("phase")
    if existing_phase in ("debrief", "closed"):
        return jsonify({
            "ok": True,
            "recap": st.session_state.data.get("recap") or {},
            "phase": existing_phase,
            "cached": True,
        })

    transcript = st.session_state.data.get("transcript") or []
    try:
        recap = _generate_session_recap(transcript)
    except Exception as e:  # noqa: BLE001
        logger.exception("session_recap: génération a leve : %s", e)
        # Fallback dégradé
        recap = {
            "summary": "(Récap a échoué : voir logs serveur.)",
            "concepts_covered": [],
            "exercises_handled": [],
            "suggestions": [],
        }

    from utils import now_iso as _now_iso
    with st.lock:
        st.session_state.set_meta("recap", recap)
        st.session_state.set_meta("phase", "debrief")
        st.session_state.set_meta("recap_at", _now_iso())
        # Marker [PHASE DÉBRIEF ENGAGÉE] injecté dans le _history du tuteur.
        # Le prompt v0.7 §1.7 lui dit d'adopter une posture plus calme et
        # de répondre aux questions de débrief sans l'exigence colle stricte.
        st.client.append_user_message("[PHASE DÉBRIEF ENGAGÉE]")

    logger.info(
        "session_recap: généré : %d concepts, %d suggestions",
        len(recap.get("concepts_covered") or []),
        len(recap.get("suggestions") or []),
    )
    return jsonify({
        "ok": True,
        "recap": recap,
        "phase": "debrief",
        "cached": False,
    })


@app.route("/api/session_close", methods=["POST"])
def api_session_close():
    """Phase v15.7.31 : vraie finalisation après débrief (analogue à
    l'ancien ``/api/end_session`` mais nommé distinct pour clarté).

    Appelé par le bouton « 🚪 Fermer définitivement » de la carte récap.
    Set ``phase="closed"`` + ``final_closed_at`` puis ``finalize()``.

    Codes :
        200 : OK
        409 : pas de session active
    """
    global _state
    with _state_lock:
        st = _state
        _state = None
    if st is None:
        return jsonify({"error": "pas de session active"}), 409
    try:
        from utils import now_iso as _now_iso
        st.session_state.set_meta("phase", "closed")
        st.session_state.set_meta("final_closed_at", _now_iso())
        st.session_state.finalize(interrupted=False)
    except Exception as e:
        logger.exception("session_close: finalize a leve")
        return jsonify({"error": str(e)}), 500
    return jsonify({
        "ok": True,
        "session_id": st.session_state.data.get("session_id"),
        "duration_seconds": st.session_state.data.get("duration_seconds"),
    })


@app.route("/api/mini_exo", methods=["POST"])
def api_mini_exo():
    """Phase v15.7.31 : déclenche un mini-exo ciblé sur une difficulté.

    Body : ``{concept, detail?, exercise_context?}``. ``concept`` est le
    sujet à travailler (souvent repris d'une suggestion ou d'un concept du
    récap de débrief). ``detail`` précise éventuellement la difficulté.

    Effet : injecte un marker `[MINI-EXO : ...]` dans le `_history` du
    tuteur. Le prompt §1.7bis lui dit de produire un exo court ciblé
    (3-5 questions max) sur ce concept précis. Le user déclenche ensuite
    le stream avec un message vide ou « C'est parti » via `/api/send_message`.

    **N'envoie PAS le stream lui-même** : c'est au front d'appeler ensuite
    `/api/send_message` avec un message d'amorce (par exemple `Allons-y` ou
    le clic UI déclenche directement le stream via le flow normal).

    Codes :
        200 : OK, marker injecté
        400 : body invalide
        409 : pas de session active
    """
    global _state
    body = request.get_json(silent=True) or {}
    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409

    concept = (body.get("concept") or "").strip()
    detail = (body.get("detail") or "").strip()
    exo_ctx = (body.get("exercise_context") or "").strip()
    if not concept:
        return jsonify({"error": "concept requis"}), 400

    marker_parts = [f"[MINI-EXO : concept={concept!r}"]
    if detail:
        marker_parts.append(f"difficulté={detail!r}")
    if exo_ctx:
        marker_parts.append(f"context={exo_ctx!r}")
    marker_parts.append("]")
    marker = " ; ".join(marker_parts[:-1]) + " " + marker_parts[-1]

    with st.lock:
        st.client.append_user_message(marker)
        # Set retry_pending pour que le prochain GET /api/stream_response
        # streame la réponse du tuteur SANS attendre un /api/send_message
        # (le marker EST la requête, pas de bulle student à afficher).
        st.retry_pending = True

    logger.info("mini_exo: marker injecté pour concept=%r", concept)
    return jsonify({
        "ok": True,
        "concept": concept,
        "marker_injected": marker,
    })


#: Phase A.11.1 : requêtes canoniques des boutons d'avancement de la carte
#: récap de débrief. Le tuteur sait déjà répondre à ces demandes (aucune
#: modification de prompt système nécessaire) : ce sont des messages
#: utilisateur pré-rédigés, injectés tels quels dans l'historique.
_RECAP_ACTION_PROMPTS = {
    "bloc_lecon": (
        "Peux-tu me compiler, en un seul bloc bien structuré, toute la "
        "rédaction des leçons / fiches méthodologiques que nous avons vues "
        "ensemble durant cette séance ? Je veux pouvoir tout relire d'un coup."
    ),
    "bloc_exos": (
        "Peux-tu me regrouper, en un seul bloc, tous les exercices que nous "
        "avons traités durant cette séance, chacun avec sa correction "
        "rédigée ? Je veux un récapitulatif complet des exos de la séance."
    ),
    "serie_exos": (
        "Peux-tu me générer une nouvelle série d'exercices d'entraînement "
        "(énoncés seuls, sans correction) sur les concepts vus aujourd'hui, "
        "pour que je m'entraîne seul ensuite ?"
    ),
}


@app.route("/api/recap_action", methods=["POST"])
def api_recap_action():
    """Phase A.11.1 : actions d'avancement de la carte récap de débrief.

    Body : ``{action}`` ∈ {``bloc_lecon``, ``bloc_exos``, ``serie_exos``}.
    Injecte la requête correspondante dans l'historique du tuteur et arme
    ``retry_pending`` pour que le front streame la réponse sans bulle
    student : même pattern que ``/api/mini_exo``.

    Codes :
        200 : OK, requête injectée
        400 : action inconnue
        409 : pas de session active
    """
    global _state
    body = request.get_json(silent=True) or {}
    action = (body.get("action") or "").strip()
    prompt = _RECAP_ACTION_PROMPTS.get(action)
    if prompt is None:
        return jsonify({"error": f"action inconnue: {action!r}"}), 400
    with _state_lock:
        st = _state
    if st is None:
        return jsonify({"error": "pas de session active"}), 409

    with st.lock:
        st.client.append_user_message(prompt)
        st.retry_pending = True

    logger.info("recap_action: %s injecté", action)
    return jsonify({"ok": True, "action": action})


@app.route("/api/end_session", methods=["POST"])
def api_end_session():
    """Finalise la session courante (ended_at, duration_seconds).

    Phase v15.7.31 : endpoint conservé pour rétrocompat et pour l'usage
    « fermeture brutale sans débrief » (flag ``skip_recap: true``). Pour
    le flow standard post-séance, utiliser :
        1. POST /api/session_recap (récap + bascule en phase débrief)
        2. POST /api/session_close (vraie fermeture)
    """
    global _state
    body = request.get_json(silent=True) or {}
    interrupted = bool(body.get("interrupted", False))
    with _state_lock:
        st = _state
        _state = None
    if st is None:
        return jsonify({"error": "pas de session active"}), 409
    try:
        st.session_state.finalize(interrupted=interrupted)
    except Exception as e:
        logger.exception("finalize a leve")
        return jsonify({"error": str(e)}), 500
    return jsonify({
        "ok": True,
        "session_id": st.session_state.data.get("session_id"),
        "duration_seconds": st.session_state.data.get("duration_seconds"),
    })


# ============================================================ Streaming Claude

def _run_claude_streaming(st: CompanionSession) -> None:
    """Tourne dans un thread daemon. Pousse les ParserEvent dans la queue."""
    full_text_chunks: list[str] = []

    def on_event(event: ParserEvent) -> None:
        if event.type == ParserEventType.TEXT_CHUNK:
            full_text_chunks.append(str(event.payload))
        st.event_queue.put(event)

    try:
        stats = st.client.stream_response(on_event=on_event)
    except ClaudeQuotaExhaustedError as e:
        logger.warning("Quota epuise : %s", e)
        current_engine = st.client.engine
        available = _list_available_fallbacks(exclude=current_engine)
        st.event_queue.put((
            "__quota_midflow__", str(e), available,
        ))
        st.event_queue.put(("__done__",))
        return
    except ClaudeClientError as e:
        logger.exception("Claude client error : %s", e)
        st.event_queue.put(("__error__", "client_error", str(e)))
        st.event_queue.put(("__done__",))
        return

    # IMPORTANT : le filtrage + push __final_text__ DOIT se passer AVANT
    # __done__ (sinon le SSE generator return sur __done__ et __final_text__
    # reste dans la queue, jamais émis au front → l'utilisateur reste avec
    # le texte buggé à l'écran).
    try:
        if full_text_chunks:
            from output_filters import apply_all_filters
            raw_text = "".join(full_text_chunks)
            # Phase A.8.4 : passe user_had_image au filtre pour qu'il puisse
            # retirer un éventuel bloc OCR halluciné quand le user n'a pas
            # envoyé de photo dans ce tour.
            user_had_image = getattr(st, "last_user_had_image", True)
            filtered_text, filter_stats = apply_all_filters(
                raw_text, user_had_image=user_had_image,
            )
            # Auto-injection NEXT_SLIDE : si le tuteur a écrit une phrase
            # qui annonce la slide suivante mais a oublié la balise, on
            # injecte un event next_slide pour que le front avance quand
            # même. Sauf si le tuteur a aussi posé une question dans la
            # même réponse : dans ce cas on bloque (question pendante).
            announced_next = _detect_announced_next_slide(filtered_text)
            if announced_next and not filtered_text.rstrip().endswith("<<<NEXT_SLIDE>>>"):
                from output_filters import has_pending_question
                if has_pending_question(filtered_text):
                    logger.info("output_filters: tuteur annonce slide suivante "
                                "ET pose une question → auto-injection bloquée "
                                "(question pendante)")
                else:
                    logger.info("output_filters: tuteur annonce slide suivante "
                                "sans balise → auto-injection next_slide")
                    st.event_queue.put(ParserEvent(
                        type=ParserEventType.NEXT_SLIDE, payload="",
                    ))
            if filter_stats["any_filtered"]:
                logger.warning(
                    "output_filters: dérive détectée dans réponse claude : "
                    "role=%d recited=%d misplaced_next_slide=%d (%d→%d chars)",
                    filter_stats["role_hijacking_lines_removed"],
                    filter_stats["recited_paragraphs_removed"],
                    filter_stats["misplaced_next_slide_removed"],
                    len(raw_text), len(filtered_text),
                )
                history = st.client._history
                if history and history[-1].get("role") == "assistant":
                    history[-1]["content"] = filtered_text
                st.event_queue.put((
                    "__final_text__", filtered_text, filter_stats,
                ))
            st.session_state.append_exchange("claude", filtered_text)
            # Phase A.10.13c : extraction sommaire dynamique post-stream.
            # Cherche les patterns ## H2, ### H3, **Exercice N**, etc.
            # Best-effort, jamais bloquant.
            try:
                # Trouve l'id du dernier message claude (qu'on vient d'ajouter)
                branch = st.session_state.data.get("current_branch_path") or []
                last_msg_id = branch[-1] if branch else ""
                if last_msg_id:
                    _append_outline_from_tutor_msg(st, last_msg_id, filtered_text)
            except Exception:  # noqa: BLE001
                logger.exception("outline extraction a leve, skipped")
        if stats.get("input_tokens"):
            st.session_state.increment_stat("claude_tokens_input", stats["input_tokens"])
        if stats.get("output_tokens"):
            st.session_state.increment_stat("claude_tokens_output", stats["output_tokens"])
    except Exception:
        logger.exception("Persistance post-stream a leve")
    finally:
        # __done__ DOIT être le dernier event poussé pour fermer le SSE.
        st.event_queue.put(("__done__",))


# Heuristique : détection d'une annonce de slide suivante dans le texte
# du tuteur. Si match → on auto-injecte next_slide pour faire avancer le
# front malgré l'oubli de balise par le tuteur.
import re as _re_for_next_slide  # noqa: E402

_ANNOUNCE_NEXT_SLIDE_PATTERNS = [
    _re_for_next_slide.compile(r"\b(?:on\s+)?passe(?:z)?\s+(?:à|a)\s+la\s+(?:slide|prochaine)", _re_for_next_slide.IGNORECASE),
    _re_for_next_slide.compile(r"\bslide\s+suivante\b", _re_for_next_slide.IGNORECASE),
    _re_for_next_slide.compile(r"\bon\s+enchaîne\s+(?:sur\s+)?(?:la\s+)?slide", _re_for_next_slide.IGNORECASE),
    _re_for_next_slide.compile(r"\bon\s+avance\s+(?:à|a|sur)\s+la\s+slide", _re_for_next_slide.IGNORECASE),
]


def _detect_announced_next_slide(text: str) -> bool:
    """True si le texte du tuteur annonce une transition de slide (« on
    passe à la slide suivante », « slide suivante », « on enchaîne sur
    la slide N »). Heuristique conservative : seulement les patterns nets
    qui indiquent une intention d'avance, pas les mentions descriptives
    (« cette slide », « la slide précédente »).
    """
    if not text:
        return False
    return any(p.search(text) for p in _ANNOUNCE_NEXT_SLIDE_PATTERNS)


def _sse_generator(st: CompanionSession):
    """Drain la queue, émet des events SSE typés. Termine sur __done__ ou __error__.

    Phase v15.7.21 : checke `st.cancel_requested` à chaque itération.
    Si True (set par POST /api/cancel_stream), abandonne immédiatement
    avec un event `cancelled` au front. Le sub-process LLM peut continuer
    à tourner en background : on accepte le coût des tokens consommés
    pour la simplicité (pas d'arrêt forcé subprocess.kill()).
    """
    while True:
        # Phase v15.7.21 : poll non-bloquant pour pouvoir checker le flag
        # cancel régulièrement (vs queue.get() bloquant qui attendait
        # éventuellement un event qui n'arrivera jamais après cancel).
        try:
            item = st.event_queue.get(timeout=0.5)
        except queue.Empty:
            if st.cancel_requested:
                logger.info("Stream annulé via /api/cancel_stream : abandon SSE")
                yield "event: cancelled\ndata: {}\n\n"
                return
            continue
        if st.cancel_requested:
            # Un dernier event a slip dans la queue avant qu'on check.
            # On l'ignore et on coupe.
            yield "event: cancelled\ndata: {}\n\n"
            return
        if isinstance(item, tuple):
            tag = item[0]
            if tag == "__done__":
                yield "event: done\ndata: {}\n\n"
                return
            if tag == "__error__":
                _kind, msg = item[1], item[2]
                yield f"event: error\ndata: {json.dumps({'kind': _kind, 'message': msg})}\n\n"
                return
            if tag == "__quota_midflow__":
                # Phase A.7.2 v7.3 : événement custom signalant que le
                # quota a sauté en plein flow. Le payload contient le
                # message d'erreur + la liste des providers de fallback
                # dont la clé est dispo. Le front affiche un card avec
                # un bouton par provider qui POST /api/switch_engine.
                msg, available = item[1], item[2]
                yield (
                    f"event: quota_midflow\n"
                    f"data: {json.dumps({'message': msg, 'available': available})}\n\n"
                )
                return
            if tag == "__final_text__":
                # Phase A.7.2 v15 : la sortie streamée a déclenché un
                # filter (role hijacking, récitation, balise mal placée).
                # On pousse le texte filtré au front qui remplace la bulle
                # rendue live (sinon l'utilisateur reste avec le texte
                # buggé à l'écran alors que le _history backend est nettoyé).
                filtered_text, fstats = item[1], item[2]
                yield (
                    f"event: final_text\n"
                    f"data: {json.dumps({'text': filtered_text, 'stats': fstats})}\n\n"
                )
                continue
            continue
        # ParserEvent
        if item.type == ParserEventType.TEXT_CHUNK:
            yield f"event: text\ndata: {json.dumps(item.payload)}\n\n"
        elif item.type == ParserEventType.TTS:
            yield f"event: tts\ndata: {json.dumps(item.payload)}\n\n"
        elif item.type == ParserEventType.SUGGESTED_EDIT:
            # Phase A.7 lecture : pousse au front qui affichera un panneau
            # de suggestion avec un bouton Appliquer (POST /api/apply_edit).
            yield f"event: suggested_edit\ndata: {json.dumps(item.payload)}\n\n"
        elif item.type == ParserEventType.END_SESSION:
            yield "event: end\ndata: {}\n\n"
            return
        elif item.type == ParserEventType.NEXT_SLIDE:
            # Mode guidé : auto-advance piloté par le tuteur. Le front
            # déclenche gotoNextSlide() après un court délai pour laisser
            # l'étudiant lire la fin de la réponse.
            yield "event: next_slide\ndata: {}\n\n"
        elif item.type == ParserEventType.GOTO_SLIDE:
            # Mode guidé : saut arbitraire à une slide N. Payload {"n": int}.
            # Le front valide que n est dans [1, len(guidedSlides)] avant
            # d'appeler showGuidedSlide(n - 1, true).
            yield f"event: goto_slide\ndata: {json.dumps(item.payload)}\n\n"
        elif item.type == ParserEventType.SHOW_DOC:
            # Lecture/guidé : le tuteur prend le contrôle du panneau Docs
            # pour afficher une page précise. Payload {"kind": str, "page": int}.
            # Le front switche l'onglet, jump à la page, ajoute un marker.
            yield f"event: show_doc\ndata: {json.dumps(item.payload)}\n\n"
        elif item.type == ParserEventType.REMEMBER:
            # Phase A.10 : mémoire persistante. Le tuteur a émis la balise
            # <<<REMEMBER>>>{"text": "..."}<<<END>>> sur demande explicite
            # de l'étudiant. On persiste en `kind="tutor"` puis push un
            # event SSE `sticky_added` pour que le front toast + refresh
            # l'onglet 📌 Consignes.
            try:
                from utils import now_iso as _now_iso_st_evt
                sticky_payload = dict(item.payload or {})
                sticky_text = _normalize_sticky_text(sticky_payload.get("text"))
                if sticky_text:
                    new_sticky = {
                        "id": f"sticky_{uuid.uuid4().hex[:12]}",
                        "kind": "tutor",
                        "text": sticky_text,
                        "source_message_id": None,
                        "created_at": _now_iso_st_evt(),
                        "edited_at": None,
                        "enabled": True,
                    }
                    existing = list(st.session_state.data.get("stickies") or [])
                    existing.append(new_sticky)
                    st.session_state.set_meta("stickies", existing)
                    logger.info(
                        "Sticky tuteur persistée via <<<REMEMBER>>> : %s (%d chars)",
                        new_sticky["id"], len(sticky_text),
                    )
                    yield (
                        f"event: sticky_added\n"
                        f"data: {json.dumps(new_sticky)}\n\n"
                    )
            except Exception:
                logger.exception("REMEMBER persist a leve")


# ============================================================ Helpers


def _build_session_context(body: dict) -> SessionContext:
    """Construit un SessionContext depuis le body /api/start_session.

    Auto-résout via ``cours_resolver`` les chemins qui ne sont pas fournis
    explicitement dans le body : énoncé, corrigés, TACHE perso, script oral,
    slides. Le body peut surcharger n'importe lequel par un chemin explicite
    (utile pour les tests ou les cas non-canoniques).

    Phase A.8.3 : supporte aussi le cas ``sujet_libre``, body avec un texte
    libre du sujet utilisateur (« apprendre Python »), aucun matériel COURS.
    Le ctx construit a matiere='LIBRE', type='SUJET', num=<slug>, exo='full',
    tous les paths None, et sujet_libre rempli.
    """
    # Phase A.9 : short-circuit workspace, aucun matériel COURS résolu,
    # le contexte initial est le résumé auto du workspace (cf.
    # prompt_builder.build_workspace_summary).
    workspace_root_raw = (body.get("workspace_root") or "").strip()
    if workspace_root_raw:
        from prompt_builder import slugify_workspace
        ws_path = Path(workspace_root_raw).resolve()
        slug = slugify_workspace(ws_path)
        excludes_raw = body.get("workspace_excludes") or []
        if isinstance(excludes_raw, str):
            excludes_raw = [p.strip() for p in excludes_raw.split(",") if p.strip()]
        focus_subdir = (body.get("workspace_focus_subdir") or "").strip() or None
        return SessionContext(
            matiere="WORKSPACE",
            type="DIR",
            num=slug,
            exo="full",
            annee=None,
            enonce_path=None,
            cm_transcription_path=None,
            cm_poly_path=None,
            correction_paths=[],
            tache_path=None,
            script_oral_path=None,
            slides_pdf_path=None,
            workspace_root=ws_path,
            workspace_excludes=tuple(excludes_raw),
            workspace_focus_subdir=focus_subdir,
        )

    # Phase A.8.3 : short-circuit sujet libre, aucun matériel COURS résolu.
    sujet_libre_raw = (body.get("sujet_libre") or "").strip()
    if sujet_libre_raw:
        from prompt_builder import slugify_topic
        slug = slugify_topic(sujet_libre_raw)
        return SessionContext(
            matiere="LIBRE",
            type="SUJET",
            num=slug,
            exo="full",
            annee=None,
            enonce_path=None,
            cm_transcription_path=None,
            cm_poly_path=None,
            correction_paths=[],
            tache_path=None,
            script_oral_path=None,
            slides_pdf_path=None,
            sujet_libre=sujet_libre_raw,
        )

    # Phase S4 (Cartable) : short-circuit source DROIT, contenu navigué via
    # droit_resolver sous CARTABLE_ROOT (transcription + fiche markdown), aucun
    # matériel COURS. ctx : matiere=<slug>, type=CM|TD, num=<n>, exo='full',
    # droit_source=<slug>. Pas d'énoncé ni de corrigé officiel.
    if (body.get("source") or "").strip().lower() == "droit":
        slug = (body.get("matiere") or "").strip()
        d_type = (body.get("type") or "").strip().upper()
        d_num = str(body.get("num") or "").strip()
        transcription = droit_resolver.find_transcription(
            CARTABLE_ROOT, slug, d_type, d_num
        )
        fiche = droit_resolver.find_fiche(CARTABLE_ROOT, slug, d_type, d_num)
        arrets = droit_resolver.list_arrets(CARTABLE_ROOT, slug)
        methodo = (
            droit_resolver.list_methodo_matiere(CARTABLE_ROOT, slug)
            + droit_resolver.list_methodo_transverse(CARTABLE_ROOT)
        )
        return SessionContext(
            matiere=slug,
            type=d_type,
            num=d_num,
            exo="full",
            annee=None,
            enonce_path=None,
            cm_transcription_path=None,
            cm_poly_path=None,
            correction_paths=[],
            tache_path=None,
            script_oral_path=None,
            slides_pdf_path=None,
            droit_source=slug,
            droit_transcription_path=transcription,
            droit_fiche_path=fiche,
            droit_arrets_paths=arrets,
            droit_methodo_paths=methodo,
        )

    matiere = body["matiere"]
    type_code = body["type"]
    num = str(body["num"])
    exo = str(body["exo"])
    annee = (body.get("annee") or None) or None
    if annee:
        annee = str(annee).strip() or None

    # Phase v15.7.36.5 : `ignore_enonce` force enonce=None même si un
    # fichier d'énoncé existe sur disque. Le tuteur prend l'initiative
    # d'inventer ses questions depuis l'annale (corrigé) + poly (cf.
    # prompt initial `prompt_builder` § "Mode révision sans énoncé").
    if body.get("ignore_enonce"):
        enonce = None
    else:
        enonce = _resolve(body.get("enonce_path"), COURS_ROOT)
        if enonce is None:
            enonce = find_enonce_pdf(COURS_ROOT, matiere, type_code, num, annee)
    if enonce is None or not enonce.exists():
        # Pour les CM, l'énoncé est optionnel : le tuteur s'appuie sur le
        # SCRIPT_*.md / transcription CM qui sont systématiquement présents
        # quand un script Feynman a été produit. Sans poly côté disque,
        # on continue avec enonce=None.
        # Phase v15.7.36.3 : pour les **types libres** (`_revision_CC*/`,
        # `TP_recherche_docu/`, etc.), il n'y a généralement pas de fichier
        # d'énoncé strict, c'est de la révision globale avec aide_memoire
        # (poly), annale_synthese (Q&A = corrigé), scripts oraux. On tolère
        # enonce=None ; le tuteur a quand même tout le matériel via les
        # autres champs du SessionContext.
        # Phase v15.7.36.5 : `ignore_enonce` aussi, si l'user veut
        # explicitement que le tuteur invente, on tolère enonce=None pour
        # tous les types (y compris TD/TP canoniques).
        from cours_resolver import _is_canonical_type as _is_canon
        if (type_code.upper() == "CM" or not _is_canon(type_code)
                or body.get("ignore_enonce")):
            enonce = None
        else:
            raise FileNotFoundError(
                f"énoncé introuvable pour {matiere} {type_code}{num} "
                f"(annee={annee!r}) : fournir enonce_path explicitement ?"
            )

    correction_paths = _resolve_list(body.get("correction_paths"), COURS_ROOT)
    if not correction_paths:
        correction_paths = resolve_corrections(
            COURS_ROOT, matiere, type_code, num, exo, annee
        )

    tache_path = _resolve(body.get("tache_path"), COURS_ROOT)
    if tache_path is None:
        tache_path = find_perso_tache(
            COURS_ROOT, matiere, type_code, num, exo, annee
        )

    script_oral_path = _resolve(body.get("script_oral_path"), COURS_ROOT)
    if script_oral_path is None:
        script_oral_path = find_perso_script_oral(
            COURS_ROOT, matiere, type_code, num, annee
        )

    slides_pdf_path = _resolve(body.get("slides_pdf_path"), COURS_ROOT)
    if slides_pdf_path is None:
        slides_pdf_path = find_perso_slides_pdf(
            COURS_ROOT, matiere, type_code, num, annee
        )

    # Phase v15.7.33 : auto-résolution `cm_poly_path` pour les types libres.
    # Cas PSI `_revision_CC2/aide_memoire_CC2.pdf` qui est un poly de
    # révision (cheat sheet condensé), pas un énoncé d'exercice. Le tuteur
    # le reçoit dans la section « POLY DU PROF » du prompt initial.
    cm_poly_path = _resolve(body.get("cm_poly_path"), COURS_ROOT)
    if cm_poly_path is None:
        cm_poly_path = find_free_poly(COURS_ROOT, matiere, type_code)

    return SessionContext(
        matiere=matiere,
        type=type_code,
        num=num,
        exo=exo,
        annee=annee,
        enonce_path=enonce,
        cm_transcription_path=_resolve(body.get("cm_transcription_path"), COURS_ROOT),
        cm_poly_path=cm_poly_path,
        correction_paths=correction_paths,
        tache_path=tache_path,
        script_oral_path=script_oral_path,
        slides_pdf_path=slides_pdf_path,
    )


def _resolve_list(values, default_root: Path) -> list[Path]:
    """Variante list de ``_resolve`` pour ``correction_paths``."""
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    out: list[Path] = []
    for v in values:
        p = _resolve(v, default_root)
        if p is not None:
            out.append(p)
    return out


def _resolve(value, default_root: Path) -> Optional[Path]:
    """Accepte None, path absolu, ou path relatif au default_root."""
    if not value:
        return None
    p = Path(value)
    if not p.is_absolute():
        p = default_root / p
    return p


_MODE_SLUG = {
    MODE_COLLE: "colle",
    MODE_GUIDE: "guide",          # ASCII (Windows-safe, OneDrive sync, git)
    MODE_DECOUVERTE: "decouverte",
    MODE_WORKSPACE: "workspace",  # Phase A.9
}


def _build_session_id(
    ctx: SessionContext,
    mode: str = MODE_COLLE,
    colle_format: str = "mixte",
    corrige_anchor: str = "strict",
) -> str:
    """Format : ``YYYY-MM-DD_{MAT}_{TYPE}{N}_ex{n}_{mode}_{format}_{anchor}``.

    Sujet libre (Phase A.8.3) : ``YYYY-MM-DD_LIBRE_<slug>_full_{mode}_{format}_{anchor}``.
    Workspace (Phase A.9) : ``YYYY-MM-DD_WORKSPACE_<slug>_full_workspace_mixte_aucun``
    (format et anchor sont placeholders fixes en mode workspace,
    n'ont pas de sémantique).

    Droit (Phase S4, Cartable) : ``YYYY-MM-DD_DROIT_<slug>_<CM|TD><num>_full_{mode}_{format}_{anchor}``
    (pas d'exo ni de millésime ; anchor placeholder `aucun`, pas de corrigé officiel).

    Phase A.8.6 : suffixe mode/format/anchor ajouté pour éviter d'écraser
    une session existante quand on relance le même exercice avec une
    posture différente (colle vs découverte, oral vs photos, etc.).

    Le mode est slugifié en ASCII (guidé→guide, découverte→decouverte)
    pour rester compatible Windows / OneDrive / git filename whitelist
    (cf. ``_session_path`` qui n'accepte que ``[A-Za-z0-9_-]``).
    """
    today = datetime.now().strftime("%Y-%m-%d")
    if ctx.workspace_root is not None or ctx.matiere == "WORKSPACE":
        base = f"{today}_WORKSPACE_{ctx.num}_full"
    elif ctx.sujet_libre or ctx.matiere == "LIBRE":
        base = f"{today}_LIBRE_{ctx.num}_full"
    elif ctx.droit_source is not None:
        # Phase S4 (Cartable) : YYYY-MM-DD_DROIT_<slug>_<CM|TD><num>_full_…
        base = f"{today}_DROIT_{ctx.droit_source}_{ctx.type}{ctx.num}_full"
    else:
        base = f"{today}_{ctx.matiere}_{ctx.type}{ctx.num}_ex{ctx.exo}"
    mode_slug = _MODE_SLUG.get(mode, "colle")
    fmt = colle_format if colle_format in ("oral", "photos", "mixte") else "mixte"
    anc = corrige_anchor if corrige_anchor in ("strict", "consultatif", "aucun") else "strict"
    return f"{base}_{mode_slug}_{fmt}_{anc}"


def _resolve_session_id(
    base_id: str, force_new_session: bool = False,
    sessions_dir: Optional[Path] = None,
) -> str:
    """Phase A.9 : suffixe ``_N`` au session_id pour permettre plusieurs
    instances d'un même contexte (workspace/cours, même mode/format/anchor).

    - ``force_new_session=False`` (défaut) : retourne ``base_id_1``. Si
      `_1.json` existe sur disque, l'écrasement aura lieu (comportement
      Phase A.8.6 historique). Le front gère le modal de conflit
      en amont pour proposer Reprendre / Écraser / Conserver+nouvelle.
    - ``force_new_session=True`` : scanne ``_1.json``, ``_2.json``…
      retourne le premier ``_N`` libre. Garantit qu'aucune session
      existante n'est écrasée.

    Pourquoi tout suffixer par défaut (même quand y'a pas de doublon) :
    cohérence (toutes les sessions ont la même forme), pas de migration
    awkward quand un ``_2`` arrive (« mais l'ancienne s'appelle comment
    déjà »). Cf. friction user 2026-05-13 : « de base que tout soit à _1
    au cas où pour éviter si y'a un _2 ben de devoir renommer l'ancienne
    session en _1 ».
    """
    sessions_dir = sessions_dir or SESSIONS_DIR
    if not force_new_session:
        return f"{base_id}_1"
    n = 1
    while (sessions_dir / f"{base_id}_{n}.json").exists():
        n += 1
    return f"{base_id}_{n}"


def _read_engine_pref() -> str:
    """Lit ``_secrets/engine_pref.json``. Default cli_subscription si absent / malformé."""
    if not ENGINE_PREF_PATH.exists():
        return DEFAULT_ENGINE
    try:
        data = json.loads(ENGINE_PREF_PATH.read_text(encoding="utf-8"))
        engine = data.get("engine")
        # SUPPORTED_ENGINES défini dans claude_client (cli/api/gemini).
        # On l'importe ici pour ne pas dupliquer la liste d'engines connus.
        from claude_client import SUPPORTED_ENGINES
        if engine in SUPPORTED_ENGINES:
            return engine
        logger.warning("engine_pref engine inattendu : %r, fallback default", engine)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("engine_pref illisible : %s, fallback default", e)
    return DEFAULT_ENGINE


# ============================================================ Lancement

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info(
        "Compagnon Flask sur http://127.0.0.1:%d (engine pref=%s)",
        DEFAULT_PORT, _read_engine_pref(),
    )
    # 0.0.0.0 pour permettre l'accès via Tailscale (page /mobile depuis téléphone)
    app.run(host="0.0.0.0", port=DEFAULT_PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
