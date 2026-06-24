import json
import logging
import os
import queue
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import (
    BooleanVar,
    Frame,
    IntVar,
    LabelFrame,
    Listbox,
    StringVar,
    Tk,
    Toplevel,
    filedialog,
    messagebox,
)
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from typing import Optional
ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "_scripts"
for _sub in ("dialogue", "audio", "quota", "web"):
    sys.path.insert(0, str(SCRIPTS / _sub))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))
from config import (
    CARTABLE_ROOT,
    COURS_ROOT,
    DEFAULT_ENGINE,
    ENGINE_PREF_PATH,
    LOGS_DIR,
    PROJECT_ROOT,
    SCHEMA_VERSION_ENGINE_PREF,
    SECRETS_DIR,
    SESSIONS_DIR,
)
from cours_resolver import (
    find_perso_script_oral,
    find_perso_slides_pdf,
    list_annees_for_cc,
    list_exos_for_num,
    list_matieres,
    list_nums_for_type,
    list_types_for_matiere,
)
import droit_resolver
from quota_check import get_usage_snapshot
from runtime_settings import (
    DEFAULT_CONTEXT_CAPS,
    get_last_selection,
    load_settings,
    update_last_selection,
    update_settings,
)
from session_state import SessionState
logger = logging.getLogger(__name__)
MATIERES = ("AN1", "EN1", "PSI", "ISE", "PRG2")
TYPES = ("TD", "TP", "CC", "CM", "Examen", "Quiz")
QUOTA_REFRESH_MS = 60_000
PROC_POLL_MS = 500
LOG_TAIL_LINES = 400
QUOTA_RESET_KEY_MAP = {
    "session_pct": "session_resets_at",
    "weekly_pct": "weekly_resets_at",
    "weekly_sonnet_pct": "weekly_sonnet_resets_at",
}
def _fmt_time_until(iso_ts: Optional[str]) -> str:
    if not iso_ts:
        return ""
    try:
        dt = datetime.fromisoformat(iso_ts)
    except ValueError:
        return ""
    now = datetime.now().astimezone()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=now.tzinfo)
    delta = dt - now
    total = int(delta.total_seconds())
    if total <= 0:
        return "(reset)"
    days, rem = divmod(total, 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes = rem // 60
    if days > 0:
        return f"Dans {days}j {hours:d}h"
    if hours > 0:
        return f"Dans {hours}h{minutes:02d}"
    return f"Dans {minutes}min"
class CompagnonGUI:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("Compagnon de révision")
        self.root.geometry("1100x900")
        self.root.minsize(900, 800)
        self._proc: Optional[subprocess.Popen] = None
        self._proc_log_queue: queue.Queue[str] = queue.Queue()
        self._stop_log_thread = threading.Event()
        self._widgets_ready = False
        self._last_launch_args: Optional[list[str]] = None
        self._threshold_save_after_id: Optional[str] = None
        self._caps_save_after_id: Optional[str] = None
        self._gemini_fallback_proposed = False
        self._build_form_vars()
        self._build_layout()
        self._widgets_ready = True
        self._wire_cascade_traces()
        self._guarded(self._cascade_from_matiere)
        self._refresh_quota()
        self._refresh_session_list()
        self._poll_proc()
        self._poll_log_queue()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    def _build_form_vars(self) -> None:
        matieres = list_matieres(COURS_ROOT) or list(MATIERES)
        last = get_last_selection()
        default_matiere = last.get("matiere") or matieres[0]
        if default_matiere not in matieres:
            default_matiere = matieres[0]
        self.matiere = StringVar(value=default_matiere)
        self.type_code = StringVar(value=last.get("type", ""))
        self.num = StringVar(value=last.get("num", ""))
        self.exo = StringVar(value=last.get("exo") or "full")
        self.annee = StringVar(value=last.get("annee", ""))
        self.droit_matiere = StringVar(value="")
        self.droit_type = StringVar(value="")
        self.droit_num = StringVar(value="")
        self.mode = StringVar(value=last.get("mode") or "colle")
        cf = (last.get("colle_format") or "mixte").strip().lower()
        if cf not in ("oral", "photos", "mixte"):
            cf = "mixte"
        self.colle_format = StringVar(value=cf)
        ca = (last.get("corrige_anchor") or "strict").strip().lower()
        if ca in ("sans_corrigé", "sans_corrige", "sans corrigé", "sans corrige"):
            ca = "aucun"
        if ca not in ("strict", "consultatif", "aucun"):
            ca = "strict"
        self.corrige_anchor = StringVar(value=ca)
        self.enable_audio = BooleanVar(value=False)
        self.skip_quota = BooleanVar(value=False)
        self.ignore_enonce = BooleanVar(value=False)
        self.sujet_libre_mode = BooleanVar(value=False)
        self.sujet_libre_text = ""
        self.workspace_mode = BooleanVar(value=False)
        self.droit_mode = BooleanVar(value=False)
        self.workspace_root = StringVar(
            value=str(last.get("workspace_root", "") or ""),
        )
        self.workspace_focus_subdir = StringVar(
            value=str(last.get("workspace_focus_subdir", "") or ""),
        )
        self.resume_mode = BooleanVar(value=False)
        settings = load_settings()
        self.session_threshold = IntVar(value=settings["session_threshold_pct"])
        self.weekly_threshold = IntVar(value=settings["weekly_threshold_pct"])
        self.replay_hard_cap = IntVar(value=settings["replay_hard_cap_exchanges"])
        self.cap_vars: dict[str, IntVar] = {
            k: IntVar(value=settings["context_caps"][k])
            for k in DEFAULT_CONTEXT_CAPS
        }
        engine = self._read_engine_pref()
        self.engine = StringVar(value=engine)
    def _read_engine_pref(self) -> str:
        if not ENGINE_PREF_PATH.exists():
            return DEFAULT_ENGINE
        try:
            data = json.loads(ENGINE_PREF_PATH.read_text(encoding="utf-8"))
            engine = data.get("engine")
            if engine in ("cli_subscription", "api_anthropic",
                          "gemini_api", "deepseek_api", "groq_api"):
                return engine
        except (OSError, json.JSONDecodeError):
            pass
        return DEFAULT_ENGINE
    def _save_engine_pref(self) -> None:
        SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION_ENGINE_PREF,
            "engine": self.engine.get(),
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        tmp = ENGINE_PREF_PATH.with_suffix(ENGINE_PREF_PATH.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, ENGINE_PREF_PATH)
        self._log_local(f"Moteur changé : {self.engine.get()}")
    def _build_layout(self) -> None:
        outer = Frame(self.root, padx=10, pady=10)
        outer.pack(fill="both", expand=True)
        outer.grid_columnconfigure(0, weight=1, minsize=500)
        outer.grid_columnconfigure(1, weight=1, minsize=420)
        outer.grid_rowconfigure(0, weight=1)
        left_col = Frame(outer)
        left_col.grid(row=0, column=0, sticky="nsew")
        right_col = Frame(outer)
        right_col.grid(row=0, column=1, sticky="nsew")
        self._build_launch_frame(left_col).pack(fill="x", padx=4, pady=4, anchor="n")
        self._build_engine_frame(left_col).pack(fill="x", padx=4, pady=4, anchor="n")
        self._build_sessions_frame(left_col).pack(fill="both", expand=True, padx=4, pady=4)
        self._build_quota_frame(right_col).pack(fill="x", padx=4, pady=4, anchor="n")
        self._build_advanced_frame(right_col).pack(fill="x", padx=4, pady=4, anchor="n")
        self._build_console_frame(right_col).pack(fill="both", expand=True, padx=4, pady=4)
        self._build_status_bar(outer).grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
    def _build_launch_frame(self, parent) -> LabelFrame:
        f = LabelFrame(parent, text="▶  Lancer une session", padx=8, pady=8)
        f.grid_columnconfigure(1, weight=1, minsize=120)
        f.grid_columnconfigure(3, weight=1, minsize=160)
        row = 0
        ttk.Label(f, text="Matière").grid(row=row, column=0, sticky="w")
        self.matiere_combo = ttk.Combobox(
            f, textvariable=self.matiere, width=8, state="readonly",
        )
        self.matiere_combo.grid(row=row, column=1, sticky="ew", padx=4)
        ttk.Label(f, text="Type").grid(row=row, column=2, sticky="w", padx=(10, 0))
        self.type_combo = ttk.Combobox(
            f, textvariable=self.type_code, width=18, state="readonly",
        )
        self.type_combo.grid(row=row, column=3, sticky="ew", padx=4)
        row += 1
        ttk.Label(f, text="Num").grid(row=row, column=0, sticky="w", pady=(6, 0))
        self.num_combo = ttk.Combobox(f, textvariable=self.num, width=14)
        self.num_combo.grid(row=row, column=1, sticky="ew", padx=4, pady=(6, 0))
        ttk.Label(f, text="Exo").grid(row=row, column=2, sticky="w", padx=(10, 0), pady=(6, 0))
        self.exo_combo = ttk.Combobox(f, textvariable=self.exo, width=10)
        self.exo_combo.grid(row=row, column=3, sticky="ew", padx=4, pady=(6, 0))
        row += 1
        ttk.Label(f, text="Année").grid(row=row, column=0, sticky="w", pady=(6, 0))
        self.annee_combo = ttk.Combobox(f, textvariable=self.annee, width=12)
        self.annee_combo.grid(row=row, column=1, sticky="ew", padx=4, pady=(6, 0))
        ttk.Label(f, text="(CC seulement, sinon désactivé)", foreground="#666").grid(
            row=row, column=2, columnspan=2, sticky="w", pady=(6, 0)
        )
        row += 1
        ttk.Label(f, text="Mode").grid(row=row, column=0, sticky="w", pady=(6, 0))
        mode_frame = Frame(f)
        mode_frame.grid(row=row, column=1, columnspan=3, sticky="w", padx=4, pady=(6, 0))
        self.rb_mode_decouverte = ttk.Radiobutton(
            mode_frame, text="🌱 Découverte",
            variable=self.mode, value="découverte",
        )
        self.rb_mode_decouverte.pack(side="left", padx=(0, 12))
        self.rb_mode_guide = ttk.Radiobutton(
            mode_frame, text="📖 Guidé",
            variable=self.mode, value="guidé",
        )
        self.rb_mode_guide.pack(side="left", padx=(0, 12))
        ttk.Radiobutton(
            mode_frame, text="🎯 Colle",
            variable=self.mode, value="colle",
        ).pack(side="left")
        row += 1
        self.mode_hint_label = ttk.Label(
            f, text="", foreground="#888", wraplength=440, justify="left",
        )
        self.mode_hint_label.grid(
            row=row, column=0, columnspan=4, sticky="we", padx=4, pady=(2, 4),
        )
        def _resize_mode_hint(event):
            new_wrap = max(200, event.width - 20)
            if event.widget.cget("wraplength") != new_wrap:
                event.widget.config(wraplength=new_wrap)
        self.mode_hint_label.bind("<Configure>", _resize_mode_hint)
        self.mode.trace_add("write", lambda *_: self._refresh_mode_hint())
        self._refresh_mode_hint()
        row += 1
        self.colle_format_label = ttk.Label(f, text="Format")
        self.colle_format_label.grid(row=row, column=0, sticky="w", pady=(6, 0))
        self.colle_format_frame = Frame(f)
        self.colle_format_frame.grid(row=row, column=1, columnspan=3, sticky="w", padx=4, pady=(6, 0))
        for label, value in (
            ("🎙 Oral", "oral"),
            ("📸 Photos", "photos"),
            ("🔀 Mixte (défaut)", "mixte"),
        ):
            ttk.Radiobutton(
                self.colle_format_frame, text=label,
                variable=self.colle_format, value=value,
            ).pack(side="left", padx=(0, 10))
        self.mode.trace_add("write", lambda *_: self._refresh_colle_format_visibility())
        self._refresh_colle_format_visibility()
        row += 1
        self.corrige_anchor_label = ttk.Label(f, text="Ancrage corrigé")
        self.corrige_anchor_label.grid(row=row, column=0, sticky="w", pady=(6, 0))
        self.corrige_anchor_frame = Frame(f)
        self.corrige_anchor_frame.grid(row=row, column=1, columnspan=3, sticky="w", padx=4, pady=(6, 0))
        for label, value in (
            ("📘 Strict (défaut)", "strict"),
            ("📖 Consultatif", "consultatif"),
            ("🚫 Sans corrigé", "aucun"),
        ):
            ttk.Radiobutton(
                self.corrige_anchor_frame, text=label,
                variable=self.corrige_anchor, value=value,
            ).pack(side="left", padx=(0, 10))
        self._refresh_corrige_anchor_visibility()
        row += 1
        actions_row = Frame(f)
        actions_row.grid(row=row, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Button(
            actions_row, text="🔄 Rescan COURS",
            command=lambda: self._guarded(self._cascade_from_matiere),
        ).pack(side="left", padx=(0, 6))
        self.btn_open_script = ttk.Button(
            actions_row, text="📖 Ouvrir script", command=self._open_script,
        )
        self.btn_open_script.pack(side="left", padx=2)
        self.btn_open_slides = ttk.Button(
            actions_row, text="📊 Ouvrir slides", command=self._open_slides,
        )
        self.btn_open_slides.pack(side="left", padx=2)
        row += 1
        ttk.Checkbutton(
            f,
            text="🎲 Le tuteur invente ses propres questions (ignore l'énoncé si présent)",
            variable=self.ignore_enonce,
        ).grid(row=row, column=0, columnspan=4, sticky="w", pady=(8, 0))
        row += 1
        ttk.Checkbutton(
            f,
            text="💡 Sujet libre (hors COURS/, apprendre n'importe quel sujet)",
            variable=self.sujet_libre_mode,
            command=self._toggle_sujet_libre_ui,
        ).grid(row=row, column=0, columnspan=4, sticky="w", pady=(4, 0))
        row += 1
        from tkinter import Text as TkText
        self.sujet_libre_label = ttk.Label(
            f, text="Sujet :", anchor="ne",
        )
        self.sujet_libre_label.grid(row=row, column=0, sticky="ne", pady=(4, 0))
        self.sujet_libre_text_widget = TkText(
            f, height=2, width=50, wrap="word",
        )
        self.sujet_libre_text_widget.grid(
            row=row, column=1, columnspan=3, sticky="ew", padx=4, pady=(4, 0),
        )
        self._toggle_sujet_libre_ui()
        row += 1
        ttk.Checkbutton(
            f,
            text="⚖️ Droit (Cartable : transcription + fiche, au lieu de COURS/)",
            variable=self.droit_mode,
            command=self._toggle_droit_ui,
        ).grid(row=row, column=0, columnspan=4, sticky="w", pady=(4, 0))
        row += 1
        self.droit_frame = Frame(f)
        self.droit_frame.grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(2, 0),
        )
        ttk.Label(self.droit_frame, text="Matière").grid(row=0, column=0, sticky="w")
        self.droit_matiere_combo = ttk.Combobox(
            self.droit_frame, textvariable=self.droit_matiere, width=18,
            state="readonly",
        )
        self.droit_matiere_combo.grid(row=0, column=1, sticky="ew", padx=4, pady=2)
        self.droit_matiere_combo.bind(
            "<<ComboboxSelected>>", lambda e: self._droit_on_matiere(),
        )
        ttk.Label(self.droit_frame, text="Type").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.droit_type_combo = ttk.Combobox(
            self.droit_frame, textvariable=self.droit_type, width=8,
            state="readonly",
        )
        self.droit_type_combo.grid(row=0, column=3, sticky="ew", padx=4, pady=2)
        self.droit_type_combo.bind(
            "<<ComboboxSelected>>", lambda e: self._droit_on_type(),
        )
        ttk.Label(self.droit_frame, text="N°").grid(row=0, column=4, sticky="w", padx=(10, 0))
        self.droit_num_combo = ttk.Combobox(
            self.droit_frame, textvariable=self.droit_num, width=10,
            state="readonly",
        )
        self.droit_num_combo.grid(row=0, column=5, sticky="ew", padx=4, pady=2)
        self.droit_num_combo.bind(
            "<<ComboboxSelected>>", lambda e: self._droit_refresh_launch(),
        )
        self.droit_frame.grid_columnconfigure(1, weight=1)
        self._toggle_droit_ui()
        row += 1
        self.workspace_mode_cb = ttk.Checkbutton(
            f,
            text="📁 Workspace (dossier disque arbitraire : codebase, docs, CV…)",
            variable=self.workspace_mode,
            command=self._toggle_workspace_ui,
        )
        self.workspace_mode_cb.grid(
            row=row, column=0, columnspan=4, sticky="w", pady=(4, 0),
        )
        row += 1
        self.workspace_frame = Frame(f)
        self.workspace_frame.grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(2, 0),
        )
        ttk.Label(self.workspace_frame, text="Dossier :").grid(
            row=0, column=0, sticky="w",
        )
        self.workspace_root_entry = ttk.Entry(
            self.workspace_frame, textvariable=self.workspace_root, width=60,
        )
        self.workspace_root_entry.grid(
            row=0, column=1, sticky="ew", padx=4, pady=2,
        )
        ttk.Button(
            self.workspace_frame, text="Parcourir…",
            command=self._workspace_browse,
        ).grid(row=0, column=2, padx=2)
        ttk.Label(self.workspace_frame, text="Raccourcis :").grid(
            row=1, column=0, sticky="w",
        )
        combo_with_btns = Frame(self.workspace_frame)
        combo_with_btns.grid(row=1, column=1, sticky="ew", padx=4, pady=2)
        combo_with_btns.grid_columnconfigure(0, weight=1)
        self.workspace_preset_combo = ttk.Combobox(
            combo_with_btns, state="readonly",
        )
        self.workspace_preset_combo.grid(row=0, column=0, sticky="ew")
        self.workspace_preset_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: self._workspace_preset_apply(),
        )
        ttk.Button(
            combo_with_btns, text="+", width=2,
            command=self._workspace_preset_add,
        ).grid(row=0, column=1, padx=(2, 0))
        ttk.Button(
            combo_with_btns, text="−", width=2,
            command=self._workspace_preset_remove,
        ).grid(row=0, column=2, padx=(1, 0))
        ttk.Label(
            self.workspace_frame,
            text="(« + » mémorise le dossier ci-dessus dans la liste ; "
                 "« − » retire celui sélectionné dans la liste)",
            foreground="#666",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Label(
            self.workspace_frame, text="Focus sous-dossier :",
        ).grid(row=3, column=0, sticky="w")
        ttk.Entry(
            self.workspace_frame,
            textvariable=self.workspace_focus_subdir, width=60,
        ).grid(row=3, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(
            self.workspace_frame, text="Parcourir…",
            command=self._workspace_focus_browse,
        ).grid(row=3, column=2, padx=2)
        ttk.Label(
            self.workspace_frame, text="Excludes additionnels :",
        ).grid(row=4, column=0, sticky="w")
        self.workspace_excludes_var = StringVar()
        ttk.Entry(
            self.workspace_frame,
            textvariable=self.workspace_excludes_var, width=60,
        ).grid(row=4, column=1, sticky="ew", padx=4, pady=2)
        ttk.Label(
            self.workspace_frame,
            text="(comma-sep, ex. _archives, *.log)",
            foreground="#666",
        ).grid(row=4, column=2, sticky="w")
        self.workspace_root.trace_add(
            "write", lambda *_: self._save_workspace_settings(),
        )
        self.workspace_focus_subdir.trace_add(
            "write", lambda *_: self._save_workspace_settings(),
        )
        self.workspace_excludes_var.trace_add(
            "write", lambda *_: self._save_workspace_settings(),
        )
        self.workspace_frame.grid_columnconfigure(1, weight=1)
        self._refresh_workspace_presets_combo()
        try:
            from runtime_settings import get_workspace_excludes
            self.workspace_excludes_var.set(", ".join(get_workspace_excludes()))
        except Exception:
            pass
        self._toggle_workspace_ui()
        row += 1
        btns = Frame(f)
        btns.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        self.btn_launch = ttk.Button(btns, text="▶  Lancer", command=self._launch)
        self.btn_launch.pack(side="left", padx=2)
        ttk.Button(btns, text="⏹  Stop", command=self._stop).pack(side="left", padx=2)
        ttk.Button(btns, text="🗂  Ouvrir l'UI navigateur", command=self._open_browser).pack(
            side="left", padx=2
        )
        row += 1
        self.launch_hint = ttk.Label(f, text="", foreground="#a04040")
        self.launch_hint.grid(
            row=row, column=0, columnspan=4, sticky="w", pady=(2, 0),
        )
        row += 1
        funnel_row = Frame(f)
        funnel_row.grid(
            row=row, column=0, columnspan=4, sticky="w", pady=(8, 0),
        )
        ttk.Label(funnel_row, text="🔗 Accès distant :").pack(
            side="left", padx=(0, 6),
        )
        self.btn_funnel = ttk.Button(
            funnel_row, text="…", width=20, command=self._toggle_funnel,
        )
        self.btn_funnel.pack(side="left")
        self.funnel_status_label = ttk.Label(
            funnel_row, text="(checking…)", foreground="#888",
        )
        self.funnel_status_label.pack(side="left", padx=(8, 0))
        self.root.after(800, self._refresh_funnel_status)
        return f
    def _wire_cascade_traces(self) -> None:
        self.matiere.trace_add(
            "write", lambda *_: self._guarded(self._cascade_from_matiere)
        )
        self.type_code.trace_add(
            "write", lambda *_: self._guarded(self._cascade_from_type)
        )
        self.num.trace_add(
            "write", lambda *_: self._guarded(self._cascade_from_num)
        )
        self.annee.trace_add(
            "write", lambda *_: self._guarded(self._refresh_exos)
        )
        for var in (
            self.mode, self.colle_format, self.corrige_anchor,
        ):
            var.trace_add("write", lambda *_: self._save_selection_silent())
        for var in (self.session_threshold, self.weekly_threshold,
                    self.replay_hard_cap):
            var.trace_add("write", lambda *_: self._schedule_thresholds_save())
        for cap_var in self.cap_vars.values():
            cap_var.trace_add("write", lambda *_: self._schedule_caps_save())
    def _guarded(self, fn) -> None:
        if not self._widgets_ready:
            return
        if getattr(self, "_in_cascade", False):
            return
        self._in_cascade = True
        try:
            fn()
        finally:
            self._in_cascade = False
    def _cascade_from_matiere(self) -> None:
        matieres = list_matieres(COURS_ROOT) or list(MATIERES)
        self.matiere_combo["values"] = matieres
        if self.matiere.get() not in matieres and matieres:
            self.matiere.set(matieres[0])
        self._cascade_from_type()
    def _cascade_from_type(self) -> None:
        types = list_types_for_matiere(COURS_ROOT, self.matiere.get())
        self.type_combo["values"] = types or list(TYPES)
        if self.type_code.get() not in (types or list(TYPES)):
            self.type_code.set((types or list(TYPES))[0])
        self._cascade_from_num()
    def _cascade_from_num(self) -> None:
        nums = list_nums_for_type(
            COURS_ROOT, self.matiere.get(), self.type_code.get()
        )
        self.num_combo["values"] = nums
        if nums and self.num.get() not in nums:
            self.num.set(nums[0])
        elif not nums:
            self.num.set("")
        self._refresh_annees()
        self._refresh_exos()
    def _refresh_annees(self) -> None:
        is_cc = self.type_code.get().upper() == "CC"
        if is_cc:
            annees = list_annees_for_cc(
                COURS_ROOT, self.matiere.get(), self.num.get()
            )
            self.annee_combo["values"] = annees
            self.annee_combo.config(state="readonly" if annees else "normal")
            if annees and self.annee.get() not in annees:
                self.annee.set(annees[0])
            elif not annees:
                self.annee.set("")
        else:
            self.annee_combo["values"] = []
            self.annee_combo.config(state="disabled")
            self.annee.set("")
    def _refresh_exos(self) -> None:
        type_upper = self.type_code.get().upper()
        annee = self.annee.get() if type_upper == "CC" else None
        annee = annee or None
        exos = list_exos_for_num(
            COURS_ROOT,
            self.matiere.get(),
            self.type_code.get(),
            self.num.get(),
            annee,
        )
        self.exo_combo["values"] = exos
        if exos and self.exo.get() not in exos:
            self.exo.set(exos[0])
        if type_upper in ("CC", "CM"):
            self.exo_combo.config(state="disabled")
        else:
            self.exo_combo.config(state="normal")
        self._refresh_avail_buttons()
        self._refresh_colle_format_visibility()
    def _refresh_mode_hint(self) -> None:
        label = getattr(self, "mode_hint_label", None)
        if label is None:
            return
        mode = self.mode.get()
        hints = {
            "découverte": (
                "🌱 Explication zéro prérequis. Le tuteur t'enseigne le "
                "sujet from scratch : exposition courte → question simple "
                "→ validation. Idéal pour démarrer un cours jamais suivi, "
                "ou apprendre un sujet libre hors COURS/."
            ),
            "guidé": (
                "📖 Slide-par-slide sur ton script de révision. Le tuteur "
                "t'accompagne dans la lecture de ton SCRIPT_*.md (style "
                "Feynman), pose des questions de vérification aux moments "
                "clés, peut proposer des corrections du script. Idéal pour "
                "consolider après avoir préparé ton matériel."
            ),
            "colle": (
                "🎯 Interrogation stricte (style colleur d'oral). "
                "Vouvoiement, pas de validation floue, barème d'indices "
                "progressifs en cas de blocage. Idéal pour vérifier la "
                "maîtrise quand tu es prêt à être interrogé sec."
            ),
        }
        label.config(text=hints.get(mode, ""))
    def _toggle_sujet_libre_ui(self) -> None:
        active = bool(self.sujet_libre_mode.get())
        if active and bool(getattr(self, "workspace_mode", BooleanVar()).get()):
            self.workspace_mode.set(False)
            if hasattr(self, "_toggle_workspace_ui"):
                self._toggle_workspace_ui()
        widgets = [
            getattr(self, "sujet_libre_label", None),
            getattr(self, "sujet_libre_text_widget", None),
        ]
        for w in widgets:
            if w is None:
                continue
            try:
                if active:
                    w.grid()
                else:
                    w.grid_remove()
            except Exception:
                pass
        for combo_attr in (
            "matiere_combo", "type_combo", "num_combo",
            "exo_combo", "annee_combo",
        ):
            combo = getattr(self, combo_attr, None)
            if combo is None:
                continue
            try:
                combo.config(state="disabled" if active else "readonly")
            except Exception:
                pass
        rb_guide = getattr(self, "rb_mode_guide", None)
        if rb_guide is not None:
            try:
                if active and self.mode.get() == "guidé":
                    self.mode.set("découverte")
                rb_guide.config(state="disabled" if active else "normal")
            except Exception:
                pass
        if hasattr(self, "btn_launch"):
            try:
                if active:
                    self.btn_launch.config(state="normal")
                    if hasattr(self, "launch_hint"):
                        self.launch_hint.config(text="")
                else:
                    self._refresh_avail_buttons()
            except Exception:
                pass
    def _toggle_droit_ui(self) -> None:
        active = bool(self.droit_mode.get())
        if active and bool(self.sujet_libre_mode.get()):
            self.sujet_libre_mode.set(False)
            self._toggle_sujet_libre_ui()
        if active and bool(getattr(self, "workspace_mode", BooleanVar()).get()):
            self.workspace_mode.set(False)
            self._toggle_workspace_ui()
        frame = getattr(self, "droit_frame", None)
        if frame is not None:
            try:
                if active:
                    frame.grid()
                else:
                    frame.grid_remove()
            except Exception:
                pass
        for combo_attr in (
            "matiere_combo", "type_combo", "num_combo",
            "exo_combo", "annee_combo",
        ):
            combo = getattr(self, combo_attr, None)
            if combo is None:
                continue
            try:
                combo.config(state="disabled" if active else "readonly")
            except Exception:
                pass
        if (active and getattr(self, "droit_matiere_combo", None) is not None
                and not self.droit_matiere_combo["values"]):
            self._droit_load_matieres()
        if active:
            self._droit_refresh_launch()
        elif hasattr(self, "btn_launch"):
            try:
                self._refresh_avail_buttons()
            except Exception:
                pass
    def _droit_load_matieres(self) -> None:
        try:
            matieres = droit_resolver.list_matieres(CARTABLE_ROOT)
        except Exception:
            logger.exception("droit_resolver.list_matieres a levé")
            matieres = []
        self.droit_matiere_combo["values"] = matieres
        self.droit_type_combo["values"] = []
        self.droit_num_combo["values"] = []
    def _droit_on_matiere(self) -> None:
        slug = self.droit_matiere.get()
        try:
            types = (droit_resolver.list_types_for_matiere(CARTABLE_ROOT, slug)
                     if slug else [])
        except Exception:
            logger.exception("droit_resolver.list_types_for_matiere a levé")
            types = []
        self.droit_type_combo["values"] = types
        self.droit_type.set("")
        self.droit_num_combo["values"] = []
        self.droit_num.set("")
        self._droit_refresh_launch()
    def _droit_on_type(self) -> None:
        slug = self.droit_matiere.get()
        tcode = self.droit_type.get()
        try:
            nums = (droit_resolver.list_nums_for_type(CARTABLE_ROOT, slug, tcode)
                    if (slug and tcode) else [])
        except Exception:
            logger.exception("droit_resolver.list_nums_for_type a levé")
            nums = []
        self.droit_num_combo["values"] = nums
        self.droit_num.set("")
        self._droit_refresh_launch()
    def _droit_refresh_launch(self) -> None:
        if not bool(self.droit_mode.get()):
            return
        complete = bool(
            self.droit_matiere.get() and self.droit_type.get() and self.droit_num.get()
        )
        if hasattr(self, "btn_launch"):
            try:
                self.btn_launch.config(state="normal" if complete else "disabled")
                if hasattr(self, "launch_hint"):
                    self.launch_hint.config(
                        text="" if complete else "(Choisis matière + CM/TD + n°)"
                    )
            except Exception:
                pass
    def _toggle_workspace_ui(self) -> None:
        if hasattr(self, "_refresh_colle_format_visibility"):
            self._refresh_colle_format_visibility()
        active = bool(self.workspace_mode.get())
        if active and bool(self.sujet_libre_mode.get()):
            self.sujet_libre_mode.set(False)
            self._toggle_sujet_libre_ui()
        frame = getattr(self, "workspace_frame", None)
        if frame is not None:
            try:
                if active:
                    frame.grid()
                else:
                    frame.grid_remove()
            except Exception:
                pass
        for combo_attr in (
            "matiere_combo", "type_combo", "num_combo",
            "exo_combo", "annee_combo",
        ):
            combo = getattr(self, combo_attr, None)
            if combo is None:
                continue
            try:
                combo.config(state="disabled" if active else "readonly")
            except Exception:
                pass
        rb_guide = getattr(self, "rb_mode_guide", None)
        if rb_guide is not None:
            try:
                if active and self.mode.get() == "guidé":
                    self.mode.set("découverte")
                rb_guide.config(state="disabled" if active else "normal")
            except Exception:
                pass
        if hasattr(self, "btn_launch"):
            try:
                if active:
                    has_path = bool(self.workspace_root.get().strip())
                    self.btn_launch.config(state="normal" if has_path else "disabled")
                    if hasattr(self, "launch_hint"):
                        self.launch_hint.config(
                            text="" if has_path
                            else "(Sélectionne un dossier workspace)"
                        )
                else:
                    self._refresh_avail_buttons()
            except Exception:
                pass
    def _workspace_browse(self) -> None:
        current = self.workspace_root.get().strip()
        initial = current if current and Path(current).is_dir() else None
        chosen = filedialog.askdirectory(
            title="Sélectionner le dossier workspace",
            initialdir=initial,
            mustexist=True,
        )
        if chosen:
            self.workspace_root.set(chosen.replace("/", os.sep))
            self._toggle_workspace_ui()
    def _workspace_focus_browse(self) -> None:
        root_raw = self.workspace_root.get().strip()
        if not root_raw:
            messagebox.showinfo(
                "Focus sous-dossier",
                "Sélectionne d'abord un dossier workspace (Dossier : "
                "Parcourir…) avant de choisir un sous-dossier de focus.",
            )
            return
        try:
            ws_root = Path(root_raw).resolve()
        except (OSError, ValueError) as e:
            messagebox.showerror(
                "Focus sous-dossier",
                f"Workspace_root invalide : {e}",
            )
            return
        if not ws_root.is_dir():
            messagebox.showerror(
                "Focus sous-dossier",
                f"Workspace_root introuvable : {ws_root}",
            )
            return
        current_focus = self.workspace_focus_subdir.get().strip()
        initial = str(ws_root)
        if current_focus:
            candidate = (ws_root / current_focus).resolve()
            try:
                candidate.relative_to(ws_root)
                if candidate.is_dir():
                    initial = str(candidate)
            except (ValueError, OSError):
                pass
        chosen = filedialog.askdirectory(
            title="Sélectionner le sous-dossier de focus (dans le workspace)",
            initialdir=initial,
            mustexist=True,
        )
        if not chosen:
            return
        try:
            chosen_path = Path(chosen).resolve()
            rel = chosen_path.relative_to(ws_root)
        except (ValueError, OSError):
            messagebox.showwarning(
                "Focus sous-dossier",
                "Le dossier choisi est en dehors du workspace_root. "
                "Le focus doit être un sous-dossier du workspace.",
            )
            return
        rel_str = str(rel)
        if rel_str in ("", "."):
            self.workspace_focus_subdir.set("")
        else:
            self.workspace_focus_subdir.set(rel_str.replace("/", os.sep))
    def _refresh_workspace_presets_combo(self) -> None:
        try:
            from runtime_settings import get_workspace_presets
            presets = get_workspace_presets()
        except Exception:
            presets = []
        if hasattr(self, "workspace_preset_combo"):
            self.workspace_preset_combo["values"] = presets
    def _workspace_preset_apply(self) -> None:
        chosen = self.workspace_preset_combo.get().strip()
        if chosen:
            self.workspace_root.set(chosen)
            self._toggle_workspace_ui()
    def _workspace_preset_add(self) -> None:
        current = self.workspace_root.get().strip()
        if not current:
            messagebox.showinfo(
                "Raccourcis workspace",
                "Sélectionne d'abord un dossier (bouton Parcourir…) avant "
                "de l'ajouter aux raccourcis.",
            )
            return
        try:
            from runtime_settings import (
                get_workspace_presets, update_workspace_presets,
            )
            presets = get_workspace_presets()
            if current not in presets:
                presets.append(current)
                update_workspace_presets(presets)
                self._refresh_workspace_presets_combo()
                self._log_local(f"📁 Raccourci ajouté : {current}")
            else:
                self._log_local(f"📁 Raccourci déjà présent : {current}")
        except Exception as e:
            messagebox.showerror("Erreur raccourcis", str(e))
    def _workspace_preset_remove(self) -> None:
        chosen = self.workspace_preset_combo.get().strip()
        if not chosen:
            messagebox.showinfo(
                "Raccourcis workspace",
                "Sélectionne d'abord un raccourci dans la liste déroulante "
                "avant de cliquer « − ».",
            )
            return
        try:
            from runtime_settings import (
                get_workspace_presets, update_workspace_presets,
            )
            presets = [p for p in get_workspace_presets() if p != chosen]
            update_workspace_presets(presets)
            self._refresh_workspace_presets_combo()
            self.workspace_preset_combo.set("")
            self._log_local(f"📁 Raccourci retiré : {chosen}")
        except Exception as e:
            messagebox.showerror("Erreur raccourcis", str(e))
    def _save_workspace_settings(self) -> None:
        if not getattr(self, "_widgets_ready", False):
            return
        try:
            from runtime_settings import (
                update_last_selection, update_workspace_excludes,
            )
            update_last_selection(
                workspace_root=self.workspace_root.get(),
                workspace_focus_subdir=self.workspace_focus_subdir.get(),
            )
            raw = self.workspace_excludes_var.get() or ""
            patterns = [p.strip() for p in raw.split(",") if p.strip()]
            update_workspace_excludes(patterns)
        except (OSError, ValueError):
            pass
    def _refresh_colle_format_visibility(self) -> None:
        frame = getattr(self, "colle_format_frame", None)
        label = getattr(self, "colle_format_label", None)
        if frame is None:
            return
        is_workspace = bool(getattr(self, "workspace_mode", BooleanVar()).get())
        visible = is_workspace or self.mode.get() in ("colle", "découverte")
        if visible:
            for w in (label, frame):
                if w is None:
                    continue
                try:
                    w.grid()
                except Exception:
                    pass
        else:
            for w in (label, frame):
                if w is None:
                    continue
                try:
                    w.grid_remove()
                except Exception:
                    pass
        self._refresh_corrige_anchor_visibility()
    def _refresh_corrige_anchor_visibility(self) -> None:
        frame = getattr(self, "corrige_anchor_frame", None)
        label = getattr(self, "corrige_anchor_label", None)
        if frame is None:
            return
        is_workspace = bool(getattr(self, "workspace_mode", BooleanVar()).get())
        is_libre = bool(getattr(self, "sujet_libre_mode", BooleanVar()).get())
        anchor_incoherent = is_workspace or is_libre
        corrige_unavailable = False
        if not anchor_incoherent:
            try:
                from cours_resolver import resolve_corrections
                matiere = (self.matiere.get() or "").strip()
                type_code = (self.type_code.get() or "").strip()
                num = (self.num.get() or "").strip()
                exo = (self.exo.get() or "").strip() or "full"
                annee = (self.annee.get() or "").strip() or None
                if matiere and type_code and num:
                    found = resolve_corrections(
                        COURS_ROOT, matiere, type_code, num, exo, annee
                    )
                    corrige_unavailable = not found
            except Exception:
                corrige_unavailable = False
        anchor_disabled = anchor_incoherent or corrige_unavailable
        if anchor_disabled:
            try:
                if self.corrige_anchor.get() != "aucun":
                    self.corrige_anchor.set("aucun")
            except Exception:
                pass
        if self.mode.get() in ("colle", "découverte") or is_workspace:
            for w in (label, frame):
                if w is None:
                    continue
                try:
                    w.grid()
                except Exception:
                    pass
            try:
                state = "disabled" if anchor_disabled else "normal"
                for child in frame.winfo_children():
                    if isinstance(child, ttk.Radiobutton):
                        child.config(state=state)
            except Exception:
                pass
            try:
                if corrige_unavailable and not anchor_incoherent:
                    label.config(text="Ancrage corrigé (corrigé indisponible)")
                else:
                    label.config(text="Ancrage corrigé")
            except Exception:
                pass
        else:
            for w in (label, frame):
                if w is None:
                    continue
                try:
                    w.grid_remove()
                except Exception:
                    pass
    def _refresh_avail_buttons(self) -> None:
        if not getattr(self, "_widgets_ready", False):
            return
        annee = self._current_annee_or_none()
        matiere = self.matiere.get()
        type_code = self.type_code.get()
        num = self.num.get().strip()
        try:
            script = find_perso_script_oral(
                COURS_ROOT, matiere, type_code, num, annee,
            )
        except (OSError, ValueError):
            script = None
        try:
            slides = find_perso_slides_pdf(
                COURS_ROOT, matiere, type_code, num, annee,
            )
        except (OSError, ValueError):
            slides = None
        try:
            from cours_resolver import find_enonce_pdf
            enonce = find_enonce_pdf(COURS_ROOT, matiere, type_code, num, annee)
        except (OSError, ValueError, ImportError):
            enonce = None
        if hasattr(self, "btn_open_script"):
            self.btn_open_script.config(
                state="normal" if script is not None else "disabled"
            )
        if hasattr(self, "btn_open_slides"):
            self.btn_open_slides.config(
                state="normal" if slides is not None else "disabled"
            )
        from cours_resolver import _is_canonical_type, resolve_corrections, find_free_poly
        type_upper = type_code.upper()
        is_canonical = _is_canonical_type(type_code)
        free_corrections = []
        free_poly = None
        if not is_canonical:
            try:
                free_corrections = resolve_corrections(
                    COURS_ROOT, matiere, type_code, num,
                    self.exo.get().strip() or "full", annee,
                )
            except (OSError, ValueError):
                free_corrections = []
            try:
                free_poly = find_free_poly(COURS_ROOT, matiere, type_code)
            except (OSError, ValueError):
                free_poly = None
        if type_upper == "CM":
            can_launch = bool(script or slides)
            hint = "" if can_launch else "Aucun script ni slides généré pour ce CM"
        elif not is_canonical:
            can_launch = bool(enonce or free_corrections or free_poly or script or slides)
            hint = "" if can_launch else (
                "Aucun matériau pédagogique reconnu ici (nommage hors "
                "conventions COURS). Pour un dossier libre comme celui-ci, "
                "coche la case 📁 Workspace : le tuteur lira tous les fichiers."
            )
        else:
            can_launch = enonce is not None
            hint = "" if can_launch else "Énoncé PDF introuvable"
        if hasattr(self, "btn_launch"):
            self.btn_launch.config(state="normal" if can_launch else "disabled")
        if hasattr(self, "launch_hint"):
            self.launch_hint.config(text=hint)
        guide_available = bool(slides or (not is_canonical and (free_poly or script)))
        if hasattr(self, "rb_mode_guide"):
            self.rb_mode_guide.config(
                state="normal" if guide_available else "disabled"
            )
        if not guide_available and self.mode.get() == "guidé":
            self.mode.set("colle")
        decouverte_available = can_launch
        if hasattr(self, "rb_mode_decouverte"):
            self.rb_mode_decouverte.config(
                state="normal" if decouverte_available else "disabled"
            )
        if not decouverte_available and self.mode.get() == "découverte":
            self.mode.set("colle")
        self._save_selection_silent()
    def _save_selection_silent(self) -> None:
        if not getattr(self, "_widgets_ready", False):
            return
        try:
            update_last_selection(
                matiere=self.matiere.get(),
                type=self.type_code.get(),
                num=self.num.get().strip(),
                exo=self.exo.get().strip(),
                annee=self.annee.get().strip(),
                mode=self.mode.get(),
                colle_format=self.colle_format.get(),
                corrige_anchor=self.corrige_anchor.get(),
                enable_audio=self.enable_audio.get(),
                skip_quota=self.skip_quota.get(),
            )
        except (OSError, ValueError):
            logger.exception("save_selection_silent a leve, ignore")
    def _build_quota_frame(self, parent) -> LabelFrame:
        f = LabelFrame(parent, text="📊  Quota Pro Max (live)", padx=8, pady=8)
        self.quota_bars: dict[str, ttk.Progressbar] = {}
        self.quota_labels: dict[str, ttk.Label] = {}
        self.quota_reset_labels: dict[str, ttk.Label] = {}
        for i, (key, label) in enumerate([
            ("session_pct", "Session 5h"),
            ("weekly_pct", "Hebdo 7j"),
            ("weekly_sonnet_pct", "Hebdo Sonnet"),
            ("extra_pct", "Overage"),
        ]):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="w")
            bar = ttk.Progressbar(f, length=160, maximum=100)
            bar.grid(row=i, column=1, sticky="ew", padx=4, pady=2)
            lbl = ttk.Label(f, text="...", width=8, anchor="e")
            lbl.grid(row=i, column=2, sticky="e")
            reset_lbl = ttk.Label(
                f, text="", width=14, anchor="e", foreground="#666",
            )
            reset_lbl.grid(row=i, column=3, sticky="e", padx=(6, 0))
            self.quota_bars[key] = bar
            self.quota_labels[key] = lbl
            self.quota_reset_labels[key] = reset_lbl
        f.grid_columnconfigure(1, weight=1)
        seuil = LabelFrame(f, text="Seuils (refus de démarrer si dépassés)", padx=6, pady=6)
        seuil.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ttk.Label(seuil, text="Session 5h ≤").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(
            seuil, from_=10, to=100, increment=1, width=6,
            textvariable=self.session_threshold,
        ).grid(row=0, column=1, sticky="w", padx=(4, 12))
        ttk.Label(seuil, text="%").grid(row=0, column=2, sticky="w")
        ttk.Label(seuil, text="Hebdo 7j ≤").grid(row=0, column=3, sticky="w", padx=(12, 0))
        ttk.Spinbox(
            seuil, from_=10, to=100, increment=1, width=6,
            textvariable=self.weekly_threshold,
        ).grid(row=0, column=4, sticky="w", padx=4)
        ttk.Label(seuil, text="%").grid(row=0, column=5, sticky="w")
        ttk.Button(seuil, text="🔄 Recharger depuis disque", command=self._reload_thresholds).grid(
            row=1, column=0, columnspan=6, sticky="w", pady=(6, 0)
        )
        ttk.Label(
            seuil, text="(Auto-save 500 ms après modification.)",
            foreground="#666",
        ).grid(row=2, column=0, columnspan=6, sticky="w", pady=(4, 0))
        ttk.Label(f, text="Refresh toutes les 60 s.", foreground="#888").grid(
            row=5, column=0, columnspan=4, sticky="w", pady=(6, 0)
        )
        return f
    def _build_engine_frame(self, parent) -> LabelFrame:
        f = LabelFrame(parent, text="🤖  Moteur (modèle)", padx=8, pady=8)
        ttk.Radiobutton(
            f,
            text="Claude : CLI subscription (Pro Max, défaut)",
            variable=self.engine,
            value="cli_subscription",
            command=self._save_engine_pref,
        ).pack(anchor="w")
        ttk.Radiobutton(
            f,
            text="Claude : API Anthropic (facturé à la conso)",
            variable=self.engine,
            value="api_anthropic",
            command=self._save_engine_pref,
        ).pack(anchor="w")
        ttk.Radiobutton(
            f,
            text="Gemini 3.5 Flash : API (contexte 1M, free tier)",
            variable=self.engine,
            value="gemini_api",
            command=self._save_engine_pref,
        ).pack(anchor="w")
        ttk.Radiobutton(
            f,
            text="DeepSeek V3 / R1 : API (raisonnement math/code, free tier)",
            variable=self.engine,
            value="deepseek_api",
            command=self._save_engine_pref,
        ).pack(anchor="w")
        ttk.Radiobutton(
            f,
            text="Groq + Llama 3.3 70B : API (free tier généreux : 14 400/jour)",
            variable=self.engine,
            value="groq_api",
            command=self._save_engine_pref,
        ).pack(anchor="w")
        ttk.Label(
            f,
            text="(Stocké dans _secrets/engine_pref.json, lu par compagnon.py\n"
                 "au démarrage. Chaque provider exige sa clé en variable d'env :\n"
                 "GEMINI_API_KEY, DEEPSEEK_API_KEY, GROQ_API_KEY. Voir README\n"
                 "section « Moteurs supportés » pour les liens d'inscription.)",
            foreground="#666", wraplength=380, justify="left",
        ).pack(anchor="w", pady=(4, 0))
        return f
    def _build_advanced_frame(self, parent) -> LabelFrame:
        f = LabelFrame(parent, text="⚙️  Caps contexte (avancé)", padx=8, pady=8)
        labels = {
            "cm_transcription_words": "CM transcription (mots)",
            "perso_material_words": "TACHE / script perso (mots)",
            "correction_total_chars": "Corrigés cumulés (caractères)",
        }
        for i, (key, label) in enumerate(labels.items()):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="w")
            ttk.Spinbox(
                f, from_=100, to=200_000, increment=100, width=10,
                textvariable=self.cap_vars[key],
            ).grid(row=i, column=1, sticky="w", padx=4, pady=2)
        replay_row = len(labels)
        ttk.Label(f, text="Replay complet si tours ≤").grid(
            row=replay_row, column=0, sticky="w", pady=(8, 0),
        )
        ttk.Spinbox(
            f, from_=10, to=2000, increment=10, width=10,
            textvariable=self.replay_hard_cap,
        ).grid(row=replay_row, column=1, sticky="w", padx=4, pady=(8, 0))
        ttk.Label(
            f,
            text=(
                "En dessous du seuil, à la reprise le tuteur reçoit le "
                "transcript\ncomplet (toutes les notes prises sont préservées).\n"
                "Au-dessus, reprise avec un résumé court de la séance à la "
                "place\ndu transcript (économise des tokens mais le tuteur perd "
                "le\ncontexte fin et risque d'oublier ce qu'on a noté)."
            ),
            foreground="#666", justify="left",
        ).grid(row=replay_row + 1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        ttk.Label(
            f,
            text="(Auto-save 500 ms après modification.\n"
                 "Les caps sont lus à la création du PromptBuilder ; un changement\n"
                 "prend effet au prochain démarrage de session, pas pendant.\n"
                 "Le seuil replay est lu live à chaque reprise.)",
            foreground="#666", justify="left",
        ).grid(row=replay_row + 2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        return f
    def _build_sessions_frame(self, parent) -> LabelFrame:
        f = LabelFrame(parent, text="📁  Sessions", padx=8, pady=8)
        f.grid_rowconfigure(0, weight=1)
        f.grid_columnconfigure(0, weight=1)
        self.sessions_list = Listbox(f, height=8)
        self.sessions_list.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(f, orient="vertical", command=self.sessions_list.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.sessions_list.config(yscrollcommand=scroll.set)
        self.sessions_list.bind("<<ListboxSelect>>", self._on_session_select)
        btns = Frame(f)
        btns.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(btns, text="🔄 Refresh", command=self._refresh_session_list).pack(side="left", padx=2)
        ttk.Button(btns, text="📂 _sessions/", command=lambda: self._open_path(SESSIONS_DIR)).pack(side="left", padx=2)
        ttk.Button(btns, text="📂 _logs/", command=lambda: self._open_path(LOGS_DIR)).pack(side="left", padx=2)
        ttk.Button(btns, text="📂 _secrets/", command=lambda: self._open_path(SECRETS_DIR)).pack(side="left", padx=2)
        return f
    def _build_console_frame(self, parent) -> LabelFrame:
        f = LabelFrame(parent, text="💻  Console (tail compagnon.py)", padx=8, pady=8)
        self.console = ScrolledText(
            f, height=18, state="disabled", wrap="word",
            background="#0e1116", foreground="#d6deeb", insertbackground="#fff",
            font=("Consolas", 9),
        )
        self.console.pack(fill="both", expand=True)
        return f
    def _build_status_bar(self, parent) -> Frame:
        f = Frame(parent, relief="groove", borderwidth=1, padx=6, pady=4)
        self.status_var = StringVar(value="Prêt.")
        ttk.Label(f, textvariable=self.status_var, foreground="#222").pack(side="left")
        return f
    def _launch(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            messagebox.showinfo(
                "Session active",
                "Une session est déjà en cours. Stop-la d'abord.",
            )
            return
        is_workspace = bool(self.workspace_mode.get())
        is_libre = bool(self.sujet_libre_mode.get()) and not is_workspace
        is_droit = bool(self.droit_mode.get()) and not is_workspace and not is_libre
        workspace_path = self.workspace_root.get().strip() if is_workspace else ""
        if is_workspace:
            if not workspace_path:
                messagebox.showwarning(
                    "Workspace",
                    "Sélectionne un dossier workspace avant de lancer.",
                )
                return
            if not Path(workspace_path).is_dir():
                messagebox.showerror(
                    "Workspace",
                    f"Dossier introuvable : {workspace_path}",
                )
                return
            mat_arg = "WORKSPACE"
            type_arg = "DIR"
            num_arg = "_"
            exo_arg = "full"
        elif is_libre:
            try:
                sujet_text = self.sujet_libre_text_widget.get("1.0", "end").strip()
            except Exception:
                sujet_text = ""
            if not sujet_text:
                messagebox.showwarning(
                    "Sujet libre",
                    "Décris ton sujet en 1-3 phrases avant de lancer.",
                )
                return
            mat_arg = "LIBRE"
            type_arg = "SUJET"
            num_arg = "_"
            exo_arg = "full"
        elif is_droit:
            slug = self.droit_matiere.get().strip()
            dtype = self.droit_type.get().strip().upper()
            dnum = self.droit_num.get().strip()
            if not (slug and dtype and dnum):
                messagebox.showwarning(
                    "Droit",
                    "Choisis la matière, le type (CM/TD) et la séance avant de lancer.",
                )
                return
            mat_arg = slug
            type_arg = dtype
            num_arg = dnum
            exo_arg = "full"
        else:
            mat_arg = self.matiere.get()
            type_arg = self.type_code.get()
            num_arg = self.num.get().strip()
            exo_arg = self.exo.get().strip()
        args = [
            sys.executable, "-u",
            str(PROJECT_ROOT / "compagnon.py"),
            mat_arg, type_arg, num_arg, exo_arg,
        ]
        if is_workspace:
            args += ["--workspace-root", workspace_path]
            focus = self.workspace_focus_subdir.get().strip()
            if focus:
                args += ["--workspace-focus", focus]
            extra_excl = (self.workspace_excludes_var.get() or "").strip()
            for pat in [p.strip() for p in extra_excl.split(",") if p.strip()]:
                args += ["--workspace-exclude", pat]
        if is_libre:
            args += ["--sujet-libre", sujet_text]
        if is_droit:
            args += ["--source", "droit"]
        if (not is_libre and not is_workspace and not is_droit
                and self.annee.get().strip()):
            args += ["--annee", self.annee.get().strip()]
        if (not is_workspace and self.mode.get()
                and self.mode.get() != "colle"):
            args += ["--mode", self.mode.get()]
        if self.mode.get() in ("colle", "découverte") and self.colle_format.get() != "mixte":
            args += ["--colle-format", self.colle_format.get()]
        if self.mode.get() in ("colle", "découverte") and self.corrige_anchor.get() != "strict":
            args += ["--corrige-anchor", self.corrige_anchor.get()]
        if self.ignore_enonce.get():
            args += ["--ignore-enonce"]
        args.append("--autostart")
        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            self._proc = subprocess.Popen(
                args,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
        except OSError as e:
            messagebox.showerror("Échec lancement", str(e))
            return
        self._stop_log_thread.clear()
        threading.Thread(
            target=self._read_proc_stdout,
            daemon=True,
            name="proc-stdout",
        ).start()
        self.status_var.set(f"En cours, PID {self._proc.pid}")
        self._log_local(f"▶ Lancé : {' '.join(args[1:])}")
        self._last_launch_args = list(args)
        self._gemini_fallback_proposed = False
        try:
            update_last_selection(
                matiere=self.matiere.get(),
                type=self.type_code.get(),
                num=self.num.get().strip(),
                exo=self.exo.get().strip(),
                annee=self.annee.get().strip(),
                mode=self.mode.get(),
                colle_format=self.colle_format.get(),
                corrige_anchor=self.corrige_anchor.get(),
                enable_audio=self.enable_audio.get(),
                skip_quota=self.skip_quota.get(),
            )
        except (OSError, ValueError):
            logger.exception("update_last_selection a leve, ignore")
    def _stop(self) -> None:
        if self._proc is None or self._proc.poll() is not None:
            self._log_local("Aucune session active.")
            return
        pid = self._proc.pid
        self._log_local(f"⏹ Stop demandé (PID {pid})")
        try:
            if os.name == "nt":
                self._proc.send_signal(subprocess.signal.CTRL_BREAK_EVENT)
            else:
                self._proc.terminate()
        except OSError as e:
            self._log_local(f"send_signal a levé : {e}")
        self.root.after(5000, lambda: self._hard_kill_if_alive(pid))
    def _hard_kill_if_alive(self, pid: int) -> None:
        if self._proc is None or self._proc.poll() is not None:
            return
        if self._proc.pid != pid:
            return
        self._log_local(f"⚠ Hard kill (taskkill /F /T /PID {pid})")
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True, check=False,
                )
            else:
                self._proc.kill()
        except OSError:
            pass
    def _read_proc_stdout(self) -> None:
        if self._proc is None or self._proc.stdout is None:
            return
        try:
            for line in self._proc.stdout:
                if self._stop_log_thread.is_set():
                    break
                self._proc_log_queue.put(line.rstrip("\n"))
        except (OSError, ValueError):
            pass
    def _poll_log_queue(self) -> None:
        while True:
            try:
                line = self._proc_log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_console(line)
            self._maybe_propose_gemini_fallback(line)
        self.root.after(150, self._poll_log_queue)
    def _maybe_propose_gemini_fallback(self, line: str) -> None:
        if self._gemini_fallback_proposed:
            return
        if "Impossible" not in line or "Quota" not in line:
            return
        if self.engine.get() not in ("cli_subscription", "api_anthropic"):
            return
        if not self._last_launch_args:
            return
        self._gemini_fallback_proposed = True
        self.root.after(50, self._show_gemini_fallback_dialog)
    _FALLBACK_PROVIDERS = (
        ("gemini_api",   "Gemini 3.5 Flash",      "GEMINI_API_KEY",
         "https://aistudio.google.com/app/apikey"),
        ("deepseek_api", "DeepSeek V3 / R1",      "DEEPSEEK_API_KEY",
         "https://platform.deepseek.com/api_keys"),
        ("groq_api",     "Groq + Llama 3.3 70B",  "GROQ_API_KEY",
         "https://console.groq.com/keys"),
    )
    def _show_gemini_fallback_dialog(self) -> None:
        if self.engine.get() not in ("cli_subscription", "api_anthropic"):
            return
        candidate = None
        for engine_id, label, env_key, signup_url in self._FALLBACK_PROVIDERS:
            if os.environ.get(env_key):
                candidate = (engine_id, label, env_key, signup_url)
                break
        if candidate is None:
            lines = [
                "Quota Anthropic atteint, mais aucune clé alternative n'est définie.",
                "",
                "Configure au moins une de ces clés (PowerShell, ex. setx pour persister) :",
                "",
            ]
            for _id, label, env_key, url in self._FALLBACK_PROVIDERS:
                lines.append(f"  • {label} : $env:{env_key} = '...'")
                lines.append(f"    Inscription : {url}")
                lines.append("")
            lines.append("Puis relance la GUI et démarre la session.")
            messagebox.showwarning("Quota Anthropic atteint", "\n".join(lines))
            return
        engine_id, label, env_key, _signup = candidate
        others = [
            other_label for o_id, other_label, k, _ in self._FALLBACK_PROVIDERS
            if o_id != engine_id and os.environ.get(k)
        ]
        msg = (
            f"Le quota Claude est dépassé pour cette fenêtre.\n\n"
            f"Basculer sur {label} pour cette séance ?\n\n"
            f"({env_key} détectée. La séance se relance immédiatement "
            f"avec les mêmes paramètres.)"
        )
        if others:
            msg += (
                f"\n\nAutres alternatives détectées : {', '.join(others)}. "
                f"Tu peux les choisir manuellement via le panneau Moteur "
                f"de la GUI au lieu d'accepter ce popup."
            )
        choice = messagebox.askyesno("Quota Anthropic atteint", msg)
        if not choice:
            self._log_local(
                f"Bascule {label} refusée : quota Anthropic à attendre."
            )
            return
        self.engine.set(engine_id)
        try:
            self._save_engine_pref()
        except Exception as e:
            messagebox.showerror("Bascule échouée", f"Sauvegarde engine_pref : {e}")
            return
        self._log_local(f"🔁 Bascule {label} : relance subprocess avec mêmes args.")
        self._relaunch_with_saved_args()
    def _relaunch_with_saved_args(self) -> None:
        if not self._last_launch_args:
            self._log_local("Pas d'args sauvegardés, relance impossible.")
            return
        if self._proc is not None and self._proc.poll() is None:
            self._log_local("Subprocess encore actif, attendre fin avant relance.")
            return
        args = list(self._last_launch_args)
        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            self._proc = subprocess.Popen(
                args, cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                bufsize=1, text=True, encoding="utf-8", errors="replace",
                creationflags=creationflags,
            )
        except OSError as e:
            messagebox.showerror("Échec relance", str(e))
            return
        self._stop_log_thread.clear()
        threading.Thread(
            target=self._read_proc_stdout, daemon=True, name="proc-stdout",
        ).start()
        self.status_var.set(f"En cours (Gemini), PID {self._proc.pid}")
        self._log_local(f"▶ Relancé sur Gemini : {' '.join(args[1:])}")
    def _poll_proc(self) -> None:
        if self._proc is not None:
            ret = self._proc.poll()
            if ret is not None:
                self.status_var.set(f"Terminé (code {ret}).")
                self._log_local(f"◽ Process terminé (code {ret})")
                self._proc = None
        self.root.after(PROC_POLL_MS, self._poll_proc)
    def _refresh_quota(self) -> None:
        threading.Thread(
            target=self._fetch_quota_async, daemon=True, name="quota-fetch"
        ).start()
        self.root.after(QUOTA_REFRESH_MS, self._refresh_quota)
    def _fetch_quota_async(self) -> None:
        snap = get_usage_snapshot()
        self.root.after(0, lambda: self._apply_quota(snap))
    def _apply_quota(self, snap: dict) -> None:
        if snap.get("error"):
            for lbl in self.quota_labels.values():
                lbl.config(text="(N/A)")
            for bar in self.quota_bars.values():
                bar["value"] = 0
            for reset_lbl in self.quota_reset_labels.values():
                reset_lbl.config(text="")
            return
        for key, bar in self.quota_bars.items():
            pct = snap.get(key)
            if pct is None:
                self.quota_labels[key].config(text="(N/A)")
                bar["value"] = 0
            else:
                bar["value"] = max(0, min(100, pct))
                self.quota_labels[key].config(text=f"{pct:.0f} %")
            reset_key = QUOTA_RESET_KEY_MAP.get(key)
            if reset_key is None:
                self.quota_reset_labels[key].config(text="")
            else:
                self.quota_reset_labels[key].config(
                    text=_fmt_time_until(snap.get(reset_key))
                )
    def _schedule_thresholds_save(self) -> None:
        if not getattr(self, "_widgets_ready", False):
            return
        if self._threshold_save_after_id is not None:
            try:
                self.root.after_cancel(self._threshold_save_after_id)
            except Exception:
                pass
        self._threshold_save_after_id = self.root.after(
            500, self._save_thresholds_silent
        )
    def _save_thresholds_silent(self) -> None:
        try:
            update_settings(
                session_threshold_pct=self.session_threshold.get(),
                weekly_threshold_pct=self.weekly_threshold.get(),
                replay_hard_cap_exchanges=self.replay_hard_cap.get(),
            )
        except (OSError, ValueError, TypeError):
            pass
    def _reload_thresholds(self) -> None:
        s = load_settings()
        self.session_threshold.set(s["session_threshold_pct"])
        self.weekly_threshold.set(s["weekly_threshold_pct"])
        self.replay_hard_cap.set(s["replay_hard_cap_exchanges"])
        self._log_local("🔄 Seuils rechargés depuis disque")
    def _schedule_caps_save(self) -> None:
        if not getattr(self, "_widgets_ready", False):
            return
        if self._caps_save_after_id is not None:
            try:
                self.root.after_cancel(self._caps_save_after_id)
            except Exception:
                pass
        self._caps_save_after_id = self.root.after(
            500, self._save_caps_silent
        )
    def _save_caps_silent(self) -> None:
        try:
            update_settings(
                context_caps={k: v.get() for k, v in self.cap_vars.items()},
            )
        except (OSError, ValueError, TypeError):
            pass
    def _refresh_session_list(self) -> None:
        self.sessions_list.delete(0, "end")
        if not SESSIONS_DIR.exists():
            return
        sessions = sorted(SESSIONS_DIR.glob("*.json"), reverse=True)
        resumable = {p.name for p in SessionState.find_resumable(SESSIONS_DIR)}
        for path in sessions[:50]:
            marker = "↩ " if path.name in resumable else "   "
            self.sessions_list.insert("end", f"{marker}{path.name}")
    def _on_session_select(self, _evt) -> None:
        sel = self.sessions_list.curselection()
        if not sel:
            return
        line = self.sessions_list.get(sel[0])
        name = line.lstrip("↩ ").strip()
        path = SESSIONS_DIR / name
        if not path.exists():
            return
        self._show_session_preview(path)
    def _show_session_preview(self, path: Path) -> None:
        win = Toplevel(self.root)
        win.title(path.name)
        win.geometry("700x500")
        text = ScrolledText(win, wrap="word", font=("Consolas", 9))
        text.pack(fill="both", expand=True)
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            content = f"(lecture impossible : {e})"
        text.insert("1.0", content)
        text.configure(state="disabled")
    def _open_path(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(str(path))
            else:
                subprocess.run(["xdg-open", str(path)], check=False)
        except OSError as e:
            messagebox.showerror("Ouverture dossier", str(e))
    def _open_file_in_default_app(self, path: Path) -> None:
        if not path.exists():
            messagebox.showerror(
                "Fichier introuvable",
                f"Le fichier n'existe pas :\n{path}",
            )
            return
        try:
            if os.name == "nt":
                os.startfile(str(path))
            else:
                subprocess.run(["xdg-open", str(path)], check=False)
        except OSError as e:
            messagebox.showerror("Ouverture fichier", str(e))
    def _current_annee_or_none(self) -> Optional[str]:
        if self.type_code.get().upper() != "CC":
            return None
        v = self.annee.get().strip()
        return v or None
    def _open_script(self) -> None:
        path = find_perso_script_oral(
            COURS_ROOT,
            self.matiere.get(),
            self.type_code.get(),
            self.num.get().strip(),
            self._current_annee_or_none(),
        )
        if path is None:
            messagebox.showinfo(
                "Script introuvable",
                "Pas de script_oral_*.txt ni SCRIPT_*.md trouvé pour "
                f"{self.matiere.get()} {self.type_code.get()}{self.num.get()}.\n\n"
                "Le script vit dans `COURS/{MAT}/{TYPE}/{TYPE}{N}/scripts_oraux/`.",
            )
            return
        self._open_file_in_default_app(path)
        self._log_local(f"📖 Ouvert : {path.name}")
    def _open_slides(self) -> None:
        path = find_perso_slides_pdf(
            COURS_ROOT,
            self.matiere.get(),
            self.type_code.get(),
            self.num.get().strip(),
            self._current_annee_or_none(),
        )
        if path is None:
            messagebox.showinfo(
                "Slides introuvables",
                "Pas de slides_*.pdf trouvé pour "
                f"{self.matiere.get()} {self.type_code.get()}{self.num.get()}.\n\n"
                "Les slides vivent dans `COURS/{MAT}/{TYPE}/{TYPE}{N}/scripts_oraux/`.",
            )
            return
        self._open_file_in_default_app(path)
        self._log_local(f"📊 Ouvert : {path.name}")
    def _open_browser(self) -> None:
        import webbrowser
        webbrowser.open("http://127.0.0.1:5680/")
    def _funnel_run(self, args: list[str]) -> tuple[int, str, str]:
        import subprocess
        flags = 0
        startupinfo = None
        if os.name == "nt":
            flags = subprocess.CREATE_NO_WINDOW
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        try:
            r = subprocess.run(
                args, capture_output=True, text=True, timeout=10,
                creationflags=flags, startupinfo=startupinfo,
            )
            return r.returncode, r.stdout or "", r.stderr or ""
        except (FileNotFoundError, subprocess.SubprocessError) as e:
            return -1, "", str(e)
    def _funnel_status_parse(self) -> tuple[str, Optional[str]]:
        rc, out, _ = self._funnel_run(["tailscale", "funnel", "status"])
        if rc != 0:
            return "off", None
        if "No serve config" in out:
            return "off", None
        if "(Funnel on)" in out:
            state = "public"
        elif "(tailnet only)" in out:
            state = "tailnet"
        else:
            state = "off"
        url = None
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("https://") and "ts.net" in line:
                url = line.split()[0]
                break
        return state, url
    def _refresh_funnel_status(self) -> None:
        def worker():
            state, url = self._funnel_status_parse()
            self.root.after(0, lambda: self._apply_funnel_status_ui(state, url))
        threading.Thread(target=worker, daemon=True).start()
        self.root.after(30_000, self._refresh_funnel_status)
    def _apply_funnel_status_ui(self, state: str, url: Optional[str]) -> None:
        if not hasattr(self, "btn_funnel"):
            return
        if state == "public":
            self.btn_funnel.config(text="🌐 Public : passer en privé")
            txt = url or "(URL inconnue)"
            self.funnel_status_label.config(
                text=f"⚠ exposé Internet : {txt}", foreground="#a04040",
            )
        elif state == "tailnet":
            self.btn_funnel.config(text="🔒 Privé tailnet : passer en public")
            txt = url or "(URL inconnue)"
            self.funnel_status_label.config(
                text=f"tailnet only : {txt}", foreground="#3a8a3a",
            )
        else:
            self.btn_funnel.config(text="⚪ Coupé : activer privé tailnet")
            self.funnel_status_label.config(
                text="(rien d'exposé, accessible que localhost)",
                foreground="#888",
            )
    def _toggle_funnel(self) -> None:
        self.btn_funnel.config(state="disabled", text="⏳ …")
        self.funnel_status_label.config(
            text="(toggle en cours, 5-10 s…)", foreground="#888",
        )
        def worker():
            state, _url = self._funnel_status_parse()
            err_acc = ""
            if state == "public":
                rc1, _, err1 = self._funnel_run(
                    ["tailscale", "funnel", "--https=443", "off"],
                )
                if rc1 != 0:
                    err_acc += err1
                rc2, _, err2 = self._funnel_run([
                    "tailscale", "serve", "--bg",
                    "--https=443", "http://127.0.0.1:5680",
                ])
                rc = rc2
                if rc2 != 0:
                    err_acc += err2
                action = "passage en tailnet privé"
            elif state == "tailnet":
                rc, _o, err = self._funnel_run([
                    "tailscale", "funnel", "--bg",
                    "--https=443", "http://127.0.0.1:5680",
                ])
                action = "activation Funnel public"
                if rc != 0:
                    err_acc = err
            else:
                rc, _, err = self._funnel_run([
                    "tailscale", "serve", "--bg",
                    "--https=443", "http://127.0.0.1:5680",
                ])
                action = "activation tailnet privé"
                if rc != 0:
                    err_acc = err
            if rc != 0:
                self.root.after(
                    0,
                    lambda err=err_acc: self._funnel_toggle_failed(action, err),
                )
                return
            self.root.after(800, self._refresh_funnel_status)
            self.root.after(0, lambda: self.btn_funnel.config(state="normal"))
        threading.Thread(target=worker, daemon=True).start()
    def _funnel_toggle_failed(self, action: str, err: str) -> None:
        self.btn_funnel.config(state="normal", text="❌ erreur")
        short_err = (err or "?").strip().splitlines()[0][:120]
        self.funnel_status_label.config(
            text=f"{action} échouée : {short_err}", foreground="#a04040",
        )
        self._log_local(f"❌ tailscale funnel: {action} échouée : {short_err}")
        self.root.after(5000, self._refresh_funnel_status)
    def _log_local(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._append_console(f"[{ts}] {msg}")
    def _append_console(self, line: str) -> None:
        self.console.configure(state="normal")
        self.console.insert("end", line + "\n")
        idx_excess = self.console.index(f"end-{LOG_TAIL_LINES + 100}l")
        if idx_excess and idx_excess != "1.0":
            self.console.delete("1.0", idx_excess)
        self.console.see("end")
        self.console.configure(state="disabled")
    def _on_close(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            if not messagebox.askyesno(
                "Session active",
                "Une session compagnon.py tourne encore. La stopper et quitter ?",
            ):
                return
            self._stop()
        self._stop_log_thread.set()
        self.root.after(200, self.root.destroy)
    def run(self) -> None:
        self.root.mainloop()
def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    CompagnonGUI().run()
if __name__ == "__main__":
    main()