"""Головне вікно AutoSample."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, dsp
from ..audio import AudioInput, input_devices, output_devices
from ..engine import Job, SamplingEngine, build_jobs
from ..export import SampleResult, instrument_dir, write_mappings
from ..midi import MidiOut
from ..pitch import detect_pitch
from ..settings import (
    Settings,
    config_dir,
    default_output_dir,
    even_expr,
    even_velocities,
    note_name,
    parse_values,
    parse_velocities,
)
from ..wavfile import read_wav
from . import style as S
from .widgets import KeyboardWidget, LevelMeter, NoteSpinBox, WaveformWidget

LOG_COLORS = {"info": S.MUTED, "ok": S.ACCENT, "warn": S.WARN, "err": S.REC}


def _spin(lo, hi, val=0, suffix="", step=1):
    w = QSpinBox()
    w.setRange(lo, hi)
    w.setSingleStep(step)
    w.setValue(val)
    if suffix:
        w.setSuffix(suffix)
    return w


def _dspin(lo, hi, val=0.0, suffix="", step=0.1, dec=2):
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(dec)
    w.setSingleStep(step)
    w.setValue(val)
    if suffix:
        w.setSuffix(suffix)
    return w


def _fmt_time(sec: float) -> str:
    sec = int(round(sec))
    if sec < 60:
        return f"{sec} с"
    m, s = divmod(sec, 60)
    if m < 60:
        return f"{m} хв {s:02d} с"
    h, m = divmod(m, 60)
    return f"{h} год {m:02d} хв"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"AutoSample {__version__}")
        self.resize(1360, 860)
        self.audio = AudioInput()
        self.midi = MidiOut()
        self.engine: SamplingEngine | None = None
        self.results: dict = {}
        self.preview_key = None
        self._in_devices: list[dict] = []
        self._out_devices: list[dict] = []
        self._loading = False
        self._test_note = None

        self._build_ui()
        self._refresh_devices()
        self._load_last()

        self.meter_timer = QTimer(self)
        self.meter_timer.timeout.connect(self._tick)
        self.meter_timer.start(33)

    # ==================================================================
    # UI
    # ==================================================================
    def _build_ui(self):
        root = QWidget(objectName="Root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # ---- header ----
        header = QFrame(objectName="Header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(18, 10, 18, 10)
        logo = QLabel("AUTO·SAMPLE", objectName="Logo")
        sub = QLabel("hardware synth sampler", objectName="LogoSub")
        lv = QVBoxLayout()
        lv.setSpacing(0)
        lv.addWidget(logo)
        lv.addWidget(sub)
        hl.addLayout(lv)
        hl.addSpacing(24)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Назва інструмента")
        self.name_edit.setMinimumWidth(220)
        hl.addWidget(QLabel("Інструмент:"))
        hl.addWidget(self.name_edit)
        hl.addSpacing(10)
        self.summary = QLabel("", objectName="Summary")
        hl.addWidget(self.summary)
        hl.addStretch(1)
        b_open = QPushButton("Відкрити пресет", objectName="Flat")
        b_save = QPushButton("Зберегти пресет", objectName="Flat")
        b_open.clicked.connect(self._open_preset)
        b_save.clicked.connect(self._save_preset)
        hl.addWidget(b_open)
        hl.addWidget(b_save)
        hl.addSpacing(10)
        self.btn_start = QPushButton("●  Почати запис", objectName="Primary")
        self.btn_stop = QPushButton("■  Стоп", objectName="Danger")
        self.btn_start.clicked.connect(self._start_all)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_stop.setEnabled(False)
        hl.addWidget(self.btn_start)
        hl.addWidget(self.btn_stop)
        v.addWidget(header)

        # ---- progress ----
        pr = QWidget()
        pl = QHBoxLayout(pr)
        pl.setContentsMargins(18, 8, 18, 0)
        self.progress = QProgressBar()
        self.progress.setFixedHeight(6)
        self.progress.setValue(0)
        self.status = QLabel("Готово до запису", objectName="Status")
        self.status.setMinimumWidth(320)
        self.status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        pl.addWidget(self.progress, 1)
        pl.addWidget(self.status)
        v.addWidget(pr)

        # ---- body ----
        body = QSplitter(Qt.Horizontal)
        body.setHandleWidth(12)
        body.setContentsMargins(18, 10, 18, 14)
        v.addWidget(body, 1)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(10)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_connect(), "Підключення")
        self.tabs.addTab(self._tab_record(), "Запис")
        self.tabs.addTab(self._tab_process(), "Обробка")
        self.tabs.addTab(self._tab_export(), "Експорт")
        ll.addWidget(self.tabs, 1)
        ll.addWidget(self._monitor_card())
        left.setMinimumWidth(400)
        left.setMaximumWidth(520)
        body.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)
        self.keyboard = KeyboardWidget()
        self.keyboard.setToolTip("Клікни по клавіші, щоб зіграти ноту на синті")
        self.keyboard.notePressed.connect(self._kb_press)
        self.keyboard.noteReleased.connect(self._kb_release)
        rl.addWidget(self.keyboard)
        self.wave = WaveformWidget()
        rl.addWidget(self.wave, 2)

        tb = QHBoxLayout()
        self.lbl_count = QLabel("Семпли: 0", objectName="Muted")
        tb.addWidget(self.lbl_count)
        tb.addStretch(1)
        self.btn_play = QPushButton("▶  Слухати")
        self.btn_play.setToolTip("Пробіл")
        self.btn_rerec = QPushButton("⟳  Перезаписати")
        self.btn_del = QPushButton("✕  Видалити")
        self.btn_map = QPushButton("Оновити SFZ / DS")
        self.btn_folder = QPushButton("Відкрити папку")
        for b in (self.btn_play, self.btn_rerec, self.btn_del, self.btn_map, self.btn_folder):
            tb.addWidget(b)
        self.btn_play.clicked.connect(self._play_selected)
        self.btn_rerec.clicked.connect(self._rerecord_selected)
        self.btn_del.clicked.connect(self._delete_selected)
        self.btn_map.clicked.connect(self._write_mappings)
        self.btn_folder.clicked.connect(self._open_folder)
        rl.addLayout(tb)

        lower = QSplitter(Qt.Vertical)
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(["Prog", "Нота", "MIDI", "Vel", "Шар", "RR", "Звучить", "Довжина",
                                              "Пік", "Файл"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        hh = self.table.horizontalHeader()
        for c in range(9):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(9, QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.doubleClicked.connect(lambda _: self._play_selected())
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        lower.addWidget(self.table)
        self.log = QPlainTextEdit(objectName="Log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        lower.addWidget(self.log)
        lower.setSizes([300, 120])
        rl.addWidget(lower, 3)
        body.addWidget(right)
        body.setSizes([440, 900])

        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self._play_selected)
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self._escape)

        # перерахунок підсумку при будь-якій зміні
        for w in self.findChildren(QSpinBox) + self.findChildren(QDoubleSpinBox):
            w.valueChanged.connect(self._changed)
        for w in self.findChildren(QComboBox):
            w.currentIndexChanged.connect(self._changed)
        for w in self.findChildren(QCheckBox):
            w.toggled.connect(self._changed)
        for w in self.findChildren(QLineEdit):
            if w.parent() is not None and not isinstance(w.parent(), (QSpinBox, QDoubleSpinBox, QComboBox)):
                w.textChanged.connect(self._changed)

    def _scroll(self, *groups):
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(14, 4, 14, 14)
        for g in groups:
            lay.addWidget(g)
        lay.addStretch(1)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(inner)
        return sa

    def _group(self, title):
        g = QGroupBox(title)
        f = QFormLayout(g)
        f.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        f.setHorizontalSpacing(14)
        f.setVerticalSpacing(8)
        f.setContentsMargins(0, 8, 0, 0)
        return g, f

    # ---- вкладка: підключення ----
    def _tab_connect(self):
        g1, f1 = self._group("Аудіо-вхід")
        self.cb_api = QComboBox()
        self.cb_in = QComboBox()
        self.cb_in.setMinimumWidth(200)
        self.cb_chan = QComboBox()
        self.cb_sr = QComboBox()
        for sr in (44100, 48000, 88200, 96000):
            self.cb_sr.addItem(f"{sr} Hz", sr)
        self.cb_bits = QComboBox()
        for label, val in (("16 bit", "16"), ("24 bit", "24"), ("32 bit float", "32f")):
            self.cb_bits.addItem(label, val)
        f1.addRow("Драйвер", self.cb_api)
        f1.addRow("Пристрій", self.cb_in)
        f1.addRow("Входи", self.cb_chan)
        f1.addRow("Частота", self.cb_sr)
        f1.addRow("Розрядність", self.cb_bits)
        self.cb_api.currentIndexChanged.connect(self._fill_in_devices)
        self.cb_in.currentIndexChanged.connect(self._fill_channels)
        self.cb_in.currentIndexChanged.connect(self._restart_audio)
        self.cb_chan.currentIndexChanged.connect(self._restart_audio)
        self.cb_sr.currentIndexChanged.connect(self._restart_audio)

        g2, f2 = self._group("MIDI-вихід")
        self.cb_midi = QComboBox()
        self.sp_mch = _spin(1, 16, 1)
        f2.addRow("Порт", self.cb_midi)
        f2.addRow("Канал", self.sp_mch)
        self.cb_midi.currentIndexChanged.connect(self._open_midi)

        g3, f3 = self._group("Прослуховування / моніторинг")
        self.cb_out = QComboBox()
        f3.addRow("Вихід", self.cb_out)
        self.lbl_out = QLabel("", objectName="Muted")
        self.lbl_out.setWordWrap(True)
        f3.addRow(self.lbl_out)
        self.cb_out.currentIndexChanged.connect(self._restart_audio)

        b_ref = QPushButton("↻  Оновити список пристроїв")
        b_ref.clicked.connect(self._refresh_devices)
        g4 = QWidget()
        l4 = QVBoxLayout(g4)
        l4.setContentsMargins(0, 14, 0, 0)
        l4.addWidget(b_ref)
        return self._scroll(g1, g2, g3, g4)

    # ---- вкладка: запис ----
    def _tab_record(self):
        g1, f1 = self._group("Діапазон нот")
        self.sp_lo = NoteSpinBox()
        self.sp_hi = NoteSpinBox()
        self.sp_step = _spin(1, 24, 3, " півт.")
        self.sp_step.setToolTip("Крок між нотами: 1 = кожна нота, 3 = мала терція, 12 = октава")
        f1.addRow("Від", self.sp_lo)
        f1.addRow("До", self.sp_hi)
        f1.addRow("Крок", self.sp_step)

        g2, f2 = self._group("Динаміка")
        self.sp_layers = _spin(1, 16, 1)
        self.ed_vels = QLineEdit("127")
        self.ed_vels.setToolTip("Значення velocity через кому. Кожне — окремий шар.")
        self.sp_layers.valueChanged.connect(
            lambda n: (not self._loading) and self.ed_vels.setText(", ".join(map(str, even_velocities(n)))))
        self.sp_rr = _spin(1, 16, 1)
        self.sp_rr.setToolTip("Скільки разів записати кожну ноту (round robin) — для живішого звучання")
        f2.addRow("Шари velocity", self.sp_layers)
        f2.addRow("Значення", self.ed_vels)
        f2.addRow("Round robin", self.sp_rr)

        ge, fe = self._group("Експресія: шари aftertouch / CC")
        self.cb_expr = QComboBox()
        self.cb_expr.addItem("Вимкнено", "off")
        self.cb_expr.addItem("Aftertouch (Channel Pressure)", "aftertouch")
        self.cb_expr.addItem("MIDI CC (запасний варіант)", "cc")
        self.cb_expr.setToolTip("Окремий вимір запису, як velocity: кожна нота записується з кожним значенням.\n"
                                "Aftertouch — для синтів, що реагують на тиск (MicroFreak: джерело Press).\n"
                                "CC — якщо синт не приймає aftertouch: керуй напряму параметром, який модулює тиск.")
        self.sp_ecc = _spin(0, 127, 1)
        self.sp_ecc.setToolTip("Номер CC — див. MIDI Implementation Chart свого синта")
        self.sp_elayers = _spin(1, 8, 3)
        self.ed_evals = QLineEdit("0, 64, 127")
        self.ed_evals.setToolTip("Значення 0–127 через кому. Кожне — окремий шар.")
        self.sp_elayers.valueChanged.connect(
            lambda n: (not self._loading) and self.ed_evals.setText(", ".join(map(str, even_expr(n)))))
        self.sp_esettle = _spin(0, 2000, 50, " мс", 10)
        self.sp_esettle.setToolTip("Пауза після надсилання CC, перш ніж грати ноту")
        self.cb_exf = QComboBox()
        self.cb_exf.addItem("Тим самим, що й при записі", "same")
        self.cb_exf.addItem("Мод-колесом (CC1)", "cc1")
        self.cb_exf.setToolTip("Яким контролером перемикати/кросфейдити шари в семплері.\n"
                               "DecentSampler не підтримує aftertouch — там завжди використовується мод-колесо.")
        fe.addRow("Режим", self.cb_expr)
        self.lbl_ecc = QLabel("Номер CC")
        fe.addRow(self.lbl_ecc, self.sp_ecc)
        fe.addRow("Кількість шарів", self.sp_elayers)
        fe.addRow("Значення", self.ed_evals)
        self.lbl_esettle = QLabel("Пауза після CC")
        fe.addRow(self.lbl_esettle, self.sp_esettle)
        fe.addRow("Кросфейд у семплері", self.cb_exf)

        gs, fs = self._group("Свел (рампа тиску)")
        self.ch_swell = QCheckBox("Записати свел-артикуляцію")
        self.ch_swell.setToolTip("Окремий запис кожної ноти, під час якого тиск плавно наростає.\n"
                                 "Зберігається окремим інструментом «… Swell».")
        self.cb_ssrc = QComboBox()
        self.cb_ssrc.addItem("Aftertouch", "aftertouch")
        self.cb_ssrc.addItem("CC (номер вище)", "cc")
        self.sp_sfrom = _spin(0, 127, 0)
        self.sp_sto = _spin(0, 127, 127)
        self.sp_sdelay = _dspin(0, 20, 0.0, " с", 0.25)
        self.sp_sramp = _dspin(0.1, 30, 3.0, " с", 0.5)
        fs.addRow(self.ch_swell)
        fs.addRow("Джерело", self.cb_ssrc)
        fs.addRow("Від", self.sp_sfrom)
        fs.addRow("До", self.sp_sto)
        fs.addRow("Затримка перед рампою", self.sp_sdelay)
        fs.addRow("Тривалість рампи", self.sp_sramp)
        hint_s = QLabel("Нота тримається не менше ніж затримка + рампа + 0,5 с. Записується одна верхня "
                        "velocity, без лупу. Тиск можна вести й униз (Від > До).", objectName="Muted")
        hint_s.setWordWrap(True)
        fs.addRow(hint_s)

        g3, f3 = self._group("Таймінг")
        self.sp_hold = _dspin(0.05, 60, 3.0, " с", 0.5)
        self.cb_rel = QComboBox()
        self.cb_rel.addItem("Фіксований хвіст", "fixed")
        self.cb_rel.addItem("До тиші (авто)", "silence")
        self.sp_rel = _dspin(0, 60, 2.0, " с", 0.5)
        self.sp_relmax = _dspin(0.5, 120, 10.0, " с", 1)
        self.sp_sil = _dspin(-120, -20, -60, " dB", 1, 0)
        self.sp_pre = _spin(0, 2000, 100, " мс", 10)
        self.sp_gap = _spin(0, 10000, 300, " мс", 50)
        f3.addRow("Утримання ноти", self.sp_hold)
        f3.addRow("Release", self.cb_rel)
        self.lbl_rel = QLabel("Хвіст після note-off")
        self.lbl_relmax = QLabel("Макс. хвіст")
        self.lbl_sil = QLabel("Поріг тиші")
        f3.addRow(self.lbl_rel, self.sp_rel)
        f3.addRow(self.lbl_relmax, self.sp_relmax)
        f3.addRow(self.lbl_sil, self.sp_sil)
        f3.addRow("Пре-рол", self.sp_pre)
        f3.addRow("Пауза між нотами", self.sp_gap)
        self.cb_rel.currentIndexChanged.connect(self._update_release_rows)

        g4, f4 = self._group("Програми / пресети синта")
        self.ch_prog = QCheckBox("Надсилати Program Change")
        self.sp_p1 = _spin(1, 128, 1)
        self.sp_p2 = _spin(1, 128, 1)
        self.sp_msb = _spin(-1, 127, -1)
        self.sp_msb.setSpecialValueText("—")
        self.sp_lsb = _spin(-1, 127, -1)
        self.sp_lsb.setSpecialValueText("—")
        self.sp_pwait = _dspin(0, 10, 1.0, " с", 0.25)
        f4.addRow(self.ch_prog)
        f4.addRow("Програма від", self.sp_p1)
        f4.addRow("до", self.sp_p2)
        f4.addRow("Bank MSB", self.sp_msb)
        f4.addRow("Bank LSB", self.sp_lsb)
        f4.addRow("Чекати після зміни", self.sp_pwait)
        hint = QLabel("Діапазон програм = пакетний запис: кожна програма стане окремим інструментом.",
                      objectName="Muted")
        hint.setWordWrap(True)
        f4.addRow(hint)
        return self._scroll(g1, g2, ge, gs, g3, g4)

    # ---- вкладка: обробка ----
    def _tab_process(self):
        g1, f1 = self._group("Початок семпла")
        self.ch_tstart = QCheckBox("Авто-обрізка тиші на початку")
        self.sp_tstart = _dspin(-90, -10, -50, " dB", 1, 0)
        self.sp_preatt = _dspin(0, 50, 1.0, " мс", 0.5, 1)
        self.sp_lat = _dspin(-500, 500, 0, " мс", 1, 1)
        self.sp_lat.setToolTip("Використовується, коли авто-обрізку вимкнено: зсув старту відносно note-on")
        f1.addRow(self.ch_tstart)
        f1.addRow("Поріг", self.sp_tstart)
        f1.addRow("Запас перед атакою", self.sp_preatt)
        f1.addRow("Компенсація затримки", self.sp_lat)

        g2, f2 = self._group("Кінець семпла")
        self.ch_tend = QCheckBox("Авто-обрізка тиші в кінці")
        self.sp_tend = _dspin(-120, -20, -60, " dB", 1, 0)
        self.sp_fin = _dspin(0, 50, 0.5, " мс", 0.5, 1)
        self.sp_fout = _dspin(0, 2000, 30, " мс", 5, 0)
        f2.addRow(self.ch_tend)
        f2.addRow("Поріг", self.sp_tend)
        f2.addRow("Fade in", self.sp_fin)
        f2.addRow("Fade out", self.sp_fout)

        g3, f3 = self._group("Рівень")
        self.ch_dc = QCheckBox("Прибрати DC-зміщення")
        self.cb_norm = QComboBox()
        self.cb_norm.addItem("Вимкнено", "off")
        self.cb_norm.addItem("Кожен семпл окремо", "sample")
        self.cb_norm.addItem("Весь інструмент (зберігає динаміку)", "instrument")
        self.sp_norm = _dspin(-24, 0, -1.0, " dBFS", 0.5, 1)
        f3.addRow(self.ch_dc)
        f3.addRow("Нормалізація", self.cb_norm)
        f3.addRow("Цільовий пік", self.sp_norm)

        g5, f5 = self._group("Висота тону")
        self.cb_root = QComboBox()
        self.cb_root.addItem("За надісланою MIDI-нотою", "midi")
        self.cb_root.addItem("За реальною висотою (авто)", "detect")
        self.cb_root.addItem("За реальною висотою + точний тюнінг", "detect_tune")
        f5.addRow("Root note", self.cb_root)
        hint5 = QLabel("Програма завжди визначає реальну висоту кожного семпла й попереджає, якщо синт "
                       "грає не ту ноту (Octave/Transpose у пресеті). «За реальною висотою» — root note "
                       "береться з того, що реально прозвучало; «+ тюнінг» ще й компенсує розстроювання в центах. "
                       "Для шумів/ударних автоматично використовується MIDI-нота.", objectName="Muted")
        hint5.setWordWrap(True)
        f5.addRow(hint5)

        g4, f4 = self._group("Луп (для сталих звуків)")
        self.ch_loop = QCheckBox("Авто-пошук точок лупу")
        self.sp_lmin = _dspin(0.05, 30, 0.5, " с", 0.1)
        self.sp_lx = _dspin(0, 500, 30, " мс", 5, 0)
        f4.addRow(self.ch_loop)
        f4.addRow("Мін. довжина лупу", self.sp_lmin)
        f4.addRow("Кросфейд", self.sp_lx)
        hint = QLabel("Луп шукається між атакою і note-off по нульових перетинах з найкращою кореляцією. "
                      "Точки пишуться у WAV (smpl), SFZ і DecentSampler.", objectName="Muted")
        hint.setWordWrap(True)
        f4.addRow(hint)
        return self._scroll(g1, g2, g3, g5, g4)

    # ---- вкладка: експорт ----
    def _tab_export(self):
        g1, f1 = self._group("Куди зберігати")
        self.ed_out = QLineEdit()
        b = QPushButton("…")
        b.setFixedWidth(34)
        b.clicked.connect(self._pick_folder)
        row = QHBoxLayout()
        row.addWidget(self.ed_out, 1)
        row.addWidget(b)
        f1.addRow("Папка", row)
        self.ed_naming = QLineEdit()
        f1.addRow("Імена файлів", self.ed_naming)
        tok = QLabel("Токени: {name} {note} {midi} {vel} {rr} {prog} {expr} {art}", objectName="Muted")
        f1.addRow(tok)
        self.lbl_example = QLabel("", objectName="Muted")
        self.lbl_example.setWordWrap(True)
        f1.addRow(self.lbl_example)
        self.cb_c3 = QComboBox()
        self.cb_c3.addItem("C3 = 60  (Ableton, Yamaha)", True)
        self.cb_c3.addItem("C4 = 60  (Roland, MIDI-стандарт)", False)
        self.cb_c3.currentIndexChanged.connect(self._c3_changed)
        f1.addRow("Назви нот", self.cb_c3)

        g2, f2 = self._group("Формати інструмента")
        self.ch_sfz = QCheckBox("SFZ  (Sforzando, TAL-Sampler, Bitwig, Kontakt через імпорт…)")
        self.ch_ds = QCheckBox("DecentSampler  (.dspreset)")
        f2.addRow(self.ch_sfz)
        f2.addRow(self.ch_ds)
        hint = QLabel("WAV-файли завжди містять root note і точки лупу (smpl-чанк), тож їх правильно "
                      "розкладають Ableton Sampler, Logic, Kontakt, Reaper та ін.", objectName="Muted")
        hint.setWordWrap(True)
        f2.addRow(hint)
        return self._scroll(g1, g2)

    def _monitor_card(self):
        card = QFrame(objectName="Card")
        l = QVBoxLayout(card)
        l.setContentsMargins(12, 10, 12, 12)
        top = QHBoxLayout()
        t = QLabel("ВХІДНИЙ РІВЕНЬ", objectName="Muted")
        top.addWidget(t)
        top.addStretch(1)
        self.lbl_floor = QLabel("", objectName="Muted")
        top.addWidget(self.lbl_floor)
        l.addLayout(top)
        self.meter = LevelMeter()
        self.meter.setToolTip("Клік — скинути індикатор кліпу")
        l.addWidget(self.meter)
        row = QHBoxLayout()
        self.btn_test = QPushButton("♪  Тест-нота")
        self.btn_test.setToolTip("Зіграти ноту з середини діапазону з макс. velocity")
        self.btn_floor = QPushButton("Виміряти шум")
        self.btn_floor.setToolTip("Записати 1,5 с тиші й підібрати пороги обрізки")
        self.btn_panic = QPushButton("Panic")
        self.btn_panic.setToolTip("All Notes Off на всіх каналах")
        self.btn_mon = QPushButton("🎧  Монітор")
        self.btn_mon.setCheckable(True)
        self.btn_mon.setToolTip("Чути синт наживо через вибраний вихід")
        self.btn_test.clicked.connect(self._test_note_click)
        self.btn_floor.clicked.connect(self._measure_floor)
        self.btn_panic.clicked.connect(self._panic)
        self.btn_mon.toggled.connect(self._monitor_toggled)
        row.addWidget(self.btn_test)
        row.addWidget(self.btn_floor)
        row.addWidget(self.btn_mon)
        row.addWidget(self.btn_panic)
        l.addLayout(row)
        return card

    def _monitor_toggled(self, on):
        self.audio.monitor = on
        if on and not self._loading and not self.audio.has_output:
            self._log(self.audio.out_error or "Вихід не відкрито — вибери його на вкладці «Підключення».", "warn")

    # ==================================================================
    # settings <-> UI
    # ==================================================================
    def collect(self) -> Settings:
        s = Settings()
        s.audio_device = self.cb_in.currentText()
        s.sample_rate = int(self.cb_sr.currentData() or 48000)
        s.bit_depth = self.cb_bits.currentData() or "24"
        ch = self.cb_chan.currentData() or (1, True)
        s.first_channel, s.stereo = ch
        s.monitor_device = "" if self.cb_out.currentData() == "same" else self.cb_out.currentText()
        s.monitor_on = self.btn_mon.isChecked()
        s.root_mode = self.cb_root.currentData() or "midi"
        s.midi_port = self.cb_midi.currentData() or ""
        s.midi_channel = self.sp_mch.value()
        s.note_start, s.note_end, s.note_step = self.sp_lo.value(), self.sp_hi.value(), self.sp_step.value()
        s.velocities = self.ed_vels.text()
        s.round_robins = self.sp_rr.value()
        s.expr_mode = self.cb_expr.currentData() or "off"
        s.expr_cc = self.sp_ecc.value()
        s.expr_values = self.ed_evals.text()
        s.expr_settle_ms = self.sp_esettle.value()
        s.expr_xfade_ctrl = self.cb_exf.currentData() or "same"
        s.swell_on = self.ch_swell.isChecked()
        s.swell_source = self.cb_ssrc.currentData() or "aftertouch"
        s.swell_from, s.swell_to = self.sp_sfrom.value(), self.sp_sto.value()
        s.swell_delay_s, s.swell_ramp_s = self.sp_sdelay.value(), self.sp_sramp.value()
        s.hold_s = self.sp_hold.value()
        s.release_mode = self.cb_rel.currentData()
        s.release_s, s.release_max_s, s.silence_db = self.sp_rel.value(), self.sp_relmax.value(), self.sp_sil.value()
        s.preroll_ms, s.gap_ms = self.sp_pre.value(), self.sp_gap.value()
        s.send_program = self.ch_prog.isChecked()
        s.program_start, s.program_end = self.sp_p1.value(), self.sp_p2.value()
        s.bank_msb, s.bank_lsb, s.program_wait_s = self.sp_msb.value(), self.sp_lsb.value(), self.sp_pwait.value()
        s.trim_start, s.trim_start_db = self.ch_tstart.isChecked(), self.sp_tstart.value()
        s.pre_attack_ms, s.latency_ms = self.sp_preatt.value(), self.sp_lat.value()
        s.trim_end, s.trim_end_db = self.ch_tend.isChecked(), self.sp_tend.value()
        s.fade_in_ms, s.fade_out_ms = self.sp_fin.value(), self.sp_fout.value()
        s.remove_dc = self.ch_dc.isChecked()
        s.normalize, s.normalize_db = self.cb_norm.currentData(), self.sp_norm.value()
        s.auto_loop, s.loop_min_s, s.loop_xfade_ms = self.ch_loop.isChecked(), self.sp_lmin.value(), self.sp_lx.value()
        s.name = self.name_edit.text().strip() or "MySynth"
        s.output_dir = self.ed_out.text().strip() or default_output_dir()
        s.naming = self.ed_naming.text().strip() or Settings.naming
        s.note_names_c3 = bool(self.cb_c3.currentData())
        s.export_sfz, s.export_ds = self.ch_sfz.isChecked(), self.ch_ds.isChecked()
        return s

    def apply(self, s: Settings):
        self._loading = True
        try:
            self._select_text(self.cb_c3, None, data=s.note_names_c3)
            self._c3_changed()
            # аудіо-пристрій: спершу вибрати драйвер
            api = s.audio_device.split(" · ")[0] if " · " in s.audio_device else ""
            if api:
                self._select_text(self.cb_api, api)
            self._select_text(self.cb_in, s.audio_device)
            self._fill_channels()
            self._select_text(self.cb_chan, None, data=(s.first_channel, s.stereo))
            self._select_text(self.cb_sr, None, data=s.sample_rate)
            self._select_text(self.cb_bits, None, data=s.bit_depth)
            asio_mismatch = s.audio_device.startswith("ASIO") and not s.monitor_device.startswith("ASIO")
            if asio_mismatch or not s.monitor_device or not self._select_text(self.cb_out, s.monitor_device):
                self.cb_out.setCurrentIndex(0)
            self.btn_mon.setChecked(s.monitor_on)
            self._select_text(self.cb_root, None, data=s.root_mode)
            self._select_text(self.cb_midi, None, data=s.midi_port)
            self.sp_mch.setValue(s.midi_channel)
            self.sp_lo.setValue(s.note_start)
            self.sp_hi.setValue(s.note_end)
            self.sp_step.setValue(s.note_step)
            self.sp_layers.setValue(len(parse_velocities(s.velocities)))
            self.ed_vels.setText(s.velocities)
            self.sp_rr.setValue(s.round_robins)
            self._select_text(self.cb_expr, None, data=s.expr_mode)
            self.sp_ecc.setValue(s.expr_cc)
            self.sp_elayers.setValue(max(1, len(parse_values(s.expr_values, 0, 127))))
            self.ed_evals.setText(s.expr_values)
            self.sp_esettle.setValue(s.expr_settle_ms)
            self._select_text(self.cb_exf, None, data=s.expr_xfade_ctrl)
            self.ch_swell.setChecked(s.swell_on)
            self._select_text(self.cb_ssrc, None, data=s.swell_source)
            self.sp_sfrom.setValue(s.swell_from)
            self.sp_sto.setValue(s.swell_to)
            self.sp_sdelay.setValue(s.swell_delay_s)
            self.sp_sramp.setValue(s.swell_ramp_s)
            self.sp_hold.setValue(s.hold_s)
            self._select_text(self.cb_rel, None, data=s.release_mode)
            self.sp_rel.setValue(s.release_s)
            self.sp_relmax.setValue(s.release_max_s)
            self.sp_sil.setValue(s.silence_db)
            self.sp_pre.setValue(s.preroll_ms)
            self.sp_gap.setValue(s.gap_ms)
            self.ch_prog.setChecked(s.send_program)
            self.sp_p1.setValue(s.program_start)
            self.sp_p2.setValue(s.program_end)
            self.sp_msb.setValue(s.bank_msb)
            self.sp_lsb.setValue(s.bank_lsb)
            self.sp_pwait.setValue(s.program_wait_s)
            self.ch_tstart.setChecked(s.trim_start)
            self.sp_tstart.setValue(s.trim_start_db)
            self.sp_preatt.setValue(s.pre_attack_ms)
            self.sp_lat.setValue(s.latency_ms)
            self.ch_tend.setChecked(s.trim_end)
            self.sp_tend.setValue(s.trim_end_db)
            self.sp_fin.setValue(s.fade_in_ms)
            self.sp_fout.setValue(s.fade_out_ms)
            self.ch_dc.setChecked(s.remove_dc)
            self._select_text(self.cb_norm, None, data=s.normalize)
            self.sp_norm.setValue(s.normalize_db)
            self.ch_loop.setChecked(s.auto_loop)
            self.sp_lmin.setValue(s.loop_min_s)
            self.sp_lx.setValue(s.loop_xfade_ms)
            self.name_edit.setText(s.name)
            self.ed_out.setText(s.output_dir or default_output_dir())
            self.ed_naming.setText(s.naming)
            self.ch_sfz.setChecked(s.export_sfz)
            self.ch_ds.setChecked(s.export_ds)
        finally:
            self._loading = False
        self._update_release_rows()
        self._restart_audio()
        self._open_midi()
        self._changed()

    @staticmethod
    def _select_text(cb: QComboBox, text, data=None):
        if data is not None:
            for i in range(cb.count()):
                if cb.itemData(i) == data:
                    cb.setCurrentIndex(i)
                    return True
            return False
        i = cb.findText(text)
        if i >= 0:
            cb.setCurrentIndex(i)
            return True
        return False

    def _load_last(self):
        p = config_dir() / "last_session.json"
        s = Settings()
        if p.exists():
            try:
                s = Settings.load(p)
            except Exception:
                pass
        if not s.output_dir:
            s.output_dir = default_output_dir()
        self.apply(s)
        geo = QSettings("AutoSample", "AutoSample").value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self._log("Вибери аудіо-вхід і MIDI-порт на вкладці «Підключення», натисни «Тест-нота» — і вперед.", "info")

    def closeEvent(self, e):
        if self.engine and self.engine.isRunning():
            if QMessageBox.question(self, "Іде запис", "Зупинити запис і вийти?") != QMessageBox.Yes:
                e.ignore()
                return
            self.engine.stop()
            self.engine.wait(3000)
        try:
            self.collect().save(config_dir() / "last_session.json")
            QSettings("AutoSample", "AutoSample").setValue("geometry", self.saveGeometry())
        except Exception:
            pass
        self.audio.stop()
        self.midi.close()
        super().closeEvent(e)

    # ==================================================================
    # пристрої
    # ==================================================================
    def _refresh_devices(self):
        prev_in, prev_out, prev_midi = self.cb_in.currentText(), self.cb_out.currentText(), self.cb_midi.currentData()
        self._loading = True
        try:
            try:
                self._in_devices = input_devices()
                self._out_devices = output_devices()
            except Exception as e:
                self._in_devices, self._out_devices = [], []
                self._log(f"Аудіо недоступне: {e}", "err")
            apis = []
            for d in self._in_devices:
                a = d["label"].split(" · ")[0]
                if a not in apis:
                    apis.append(a)
            # ASIO / WASAPI зверху — у них найменша затримка
            # WASAPI — безпечний дефолт (не захоплює пристрій монопольно); ASIO — для тих, хто знає навіщо
            order = {"Windows WASAPI": 0, "ASIO": 1, "Windows DirectSound": 3, "MME": 4, "Windows WDM-KS": 5}
            apis.sort(key=lambda a: order.get(a, 2))
            cur_api = self.cb_api.currentText()
            self.cb_api.clear()
            self.cb_api.addItems(apis)
            if cur_api:
                self._select_text(self.cb_api, cur_api)
            self._fill_in_devices()
            self._select_text(self.cb_in, prev_in)
            self._fill_channels()
            self.cb_out.clear()
            self.cb_out.addItem("Той самий, що й вхід (рекомендовано)", "same")
            self.cb_out.addItem("Системний за замовчуванням", "default")
            for d in self._out_devices:
                self.cb_out.addItem(d["label"], d["index"])
            self._select_text(self.cb_out, prev_out)
            self.cb_midi.clear()
            self.cb_midi.addItem("— не вибрано —", "")
            for name in MidiOut.list_ports():
                self.cb_midi.addItem(name, name)
            if prev_midi:
                self._select_text(self.cb_midi, None, data=prev_midi)
        finally:
            self._loading = False

    def _fill_in_devices(self):
        api = self.cb_api.currentText()
        was = self._loading
        self._loading = True
        cur = self.cb_in.currentText()
        self.cb_in.clear()
        for d in self._in_devices:
            if d["label"].startswith(api + " · "):
                self.cb_in.addItem(d["label"], d["index"])
        self._select_text(self.cb_in, cur)
        self._fill_channels()
        self._loading = was
        self._restart_audio()

    def _fill_channels(self):
        idx = self.cb_in.currentData()
        dev = next((d for d in self._in_devices if d["index"] == idx), None)
        cur = self.cb_chan.currentData()
        was = self._loading
        self._loading = True
        self.cb_chan.clear()
        if dev:
            n = dev["channels"]
            for c in range(1, n, 2):
                self.cb_chan.addItem(f"{c}–{c + 1}  стерео", (c, True))
            for c in range(1, n + 1):
                self.cb_chan.addItem(f"{c}  моно", (c, False))
        if cur is not None:
            self._select_text(self.cb_chan, None, data=cur)
        self._loading = was

    def _restart_audio(self):
        if self._loading or (self.engine and self.engine.isRunning()):
            return
        idx = self.cb_in.currentData()
        ch = self.cb_chan.currentData()
        if idx is None or ch is None:
            self.audio.stop()
            return
        first, stereo = ch
        sr = int(self.cb_sr.currentData() or 48000)
        out = self._resolve_output(idx)
        try:
            self.audio.start(idx, sr, first - 1, 2 if stereo else 1, out)
            self.audio.monitor = self.btn_mon.isChecked()
            self.audio.device_label = self.cb_in.currentText()
            self._set_status(f"Вхід: {self.cb_in.currentText()} · {sr} Hz")
        except Exception as e:
            self.audio.stop()
            self._log(f"Не вдалося відкрити аудіо-вхід ({sr} Hz): {e}", "err")
            self._set_status("Аудіо-вхід не відкрито")
        if self.audio.out_error:
            self.lbl_out.setText("⚠ " + self.audio.out_error)
            self._log(self.audio.out_error, "warn")
        elif self.audio.has_output:
            mode = "спільний потік із входом" if self.audio.duplex else f"{self.audio.out_sr} Hz"
            txt = f"Звук іде на: {self.audio.out_info} ({mode})"
            if self.cb_in.currentText().startswith("ASIO") and not self.audio.duplex:
                txt += ("\n⚠ Вхід працює через ASIO, а вихід — через інший драйвер. Якщо це та сама звукова "
                        "карта, звуку не буде (ASIO займає її монопольно) — вибери «Той самий, що й вхід».")
            self.lbl_out.setText(txt)
        else:
            self.lbl_out.setText("")

    def _resolve_output(self, in_idx):
        """Індекс вихідного пристрою для прослуховування/моніторингу."""
        data = self.cb_out.currentData()
        try:
            if data == "same":
                info = sd.query_devices(in_idx)
                if info["max_output_channels"] > 0:
                    return in_idx
                # шукаємо вихід із тією ж назвою в тому ж драйвері, інакше дефолт драйвера
                api = info["hostapi"]
                base = info["name"].split("(")[-1].strip(") ") if "(" in info["name"] else info["name"]
                for i, d in enumerate(sd.query_devices()):
                    if d["hostapi"] == api and d["max_output_channels"] > 0 and base and base in d["name"]:
                        return i
                dflt = sd.query_hostapis(api)["default_output_device"]
                return dflt if dflt >= 0 else None
            if data == "default":
                d = sd.default.device[1]
                return d if d is not None and d >= 0 else None
            return data
        except Exception:
            return None

    def _open_midi(self):
        if self._loading:
            return
        name = self.cb_midi.currentData()
        try:
            self.midi.open(name or "")
            if name:
                self._log(f"MIDI: {name}", "ok")
        except Exception as e:
            self._log(str(e), "err")

    # ==================================================================
    # реакція на зміни
    # ==================================================================
    def _changed(self, *_):
        if self._loading:
            return
        s = self.collect()
        extra = f" (+{s.swell_samples()} свел)" if s.swell_on else ""
        self.summary.setText(f"{s.main_samples()} семплів{extra}  ·  ≈ {_fmt_time(s.estimated_seconds())}")
        self.keyboard.set_plan(s.notes(), s.note_names_c3)
        progs = s.programs()
        from ..export import sample_filename
        ex = sample_filename(s, progs[0], s.notes()[0], s.velocity_list()[-1], 1, s.expr_list()[-1])
        self.lbl_example.setText(f"Приклад: {ex}")
        cc_mode = s.expr_mode == "cc"
        expr_on = s.expr_mode != "off"
        for w in (self.sp_elayers, self.ed_evals, self.cb_exf):
            w.setEnabled(expr_on)
        need_cc = cc_mode or (s.swell_on and s.swell_source == "cc")
        self.sp_ecc.setEnabled(need_cc)
        self.lbl_ecc.setEnabled(need_cc)
        self.sp_esettle.setEnabled(need_cc)
        self.lbl_esettle.setEnabled(need_cc)
        for w in (self.cb_ssrc, self.sp_sfrom, self.sp_sto, self.sp_sdelay, self.sp_sramp):
            w.setEnabled(s.swell_on)
        on = s.send_program
        for w in (self.sp_p1, self.sp_p2, self.sp_msb, self.sp_lsb, self.sp_pwait):
            w.setEnabled(on)
        self.sp_tstart.setEnabled(s.trim_start)
        self.sp_preatt.setEnabled(s.trim_start)
        self.sp_lat.setEnabled(not s.trim_start)
        self.sp_tend.setEnabled(s.trim_end)
        self.sp_norm.setEnabled(s.normalize != "off")
        self.sp_lmin.setEnabled(s.auto_loop)
        self.sp_lx.setEnabled(s.auto_loop)

    def _update_release_rows(self):
        fixed = self.cb_rel.currentData() == "fixed"
        for w in (self.lbl_rel, self.sp_rel):
            w.setVisible(fixed)
        for w in (self.lbl_relmax, self.sp_relmax, self.lbl_sil, self.sp_sil):
            w.setVisible(not fixed)

    def _c3_changed(self):
        c3 = bool(self.cb_c3.currentData()) if self.cb_c3.currentData() is not None else True
        self.sp_lo.set_c3(c3)
        self.sp_hi.set_c3(c3)
        self._refresh_table_names()

    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Папка для семплів", self.ed_out.text() or default_output_dir())
        if d:
            self.ed_out.setText(d)

    # ==================================================================
    # таймер: індикатор + live-хвиля
    # ==================================================================
    def _tick(self):
        if self.audio.running:
            self.meter.set_peaks(self.audio.read_peaks())
        else:
            self.meter.set_peaks([0.0] * self.audio.nch)
        if self.engine and self.engine.isRunning():
            chunks = self.audio.snapshot()
            if chunks:
                d = np.concatenate(chunks, axis=0)
                self.wave.set_data(d, self.audio.sr, title="● REC", live=True)

    # ==================================================================
    # тест / шум / panic / клавіатура
    # ==================================================================
    def _need_midi(self) -> bool:
        if not self.midi.is_open:
            self._log("Спершу вибери MIDI-порт на вкладці «Підключення».", "warn")
            self.tabs.setCurrentIndex(0)
            return False
        return True

    def _test_note_click(self):
        if not self._need_midi():
            return
        s = self.collect()
        notes = s.notes()
        n = notes[len(notes) // 2] if notes else 60
        v = s.velocity_list()[-1]
        hold = min(s.hold_s, 2.0)
        capture = self.audio.running
        if capture:
            self.audio.begin_capture()
        self.btn_test.setEnabled(False)
        self._kb_press(n, v)

        def release():
            self._kb_release(n)
            self.btn_test.setEnabled(True)
            if not capture:
                return
            x = self.audio.end_capture()
            pk = dsp.peak(x)
            if pk < 1e-4:
                self._log(f"Тест: надіслано {note_name(n, s.note_names_c3)} ({n}) на канал {s.midi_channel}, "
                          "але на вході тиша. Перевір кабель, вхід і MIDI-канал синта.", "warn")
                return
            det, conf = detect_pitch(x, self.audio.sr, int(0.15 * self.audio.sr))
            name = f"{note_name(n, s.note_names_c3)} ({n})"
            if det is None or conf < 0.6:
                self._log(f"Тест: надіслано {name}, рівень {dsp.lin2db(pk):.1f} dB, висоту не визначено.", "info")
            elif abs(det - n) < 0.5:
                self._log(f"Тест: надіслано {name} → звучить {note_name(round(det), s.note_names_c3)} "
                          f"({(det - round(det)) * 100:+.0f}¢), рівень {dsp.lin2db(pk):.1f} dB ✓", "ok")
            else:
                self._log(f"Тест: надіслано {name}, а звучить {note_name(round(det), s.note_names_c3)} "
                          f"({det - n:+.1f} півт.)! MIDI в порядку — це транспонування на синті "
                          "(Octave/Transpose у пресеті). Або вибери «Root note: за реальною висотою».", "warn")

        QTimer.singleShot(int(hold * 1000), release)

    def _kb_press(self, n, vel=None):
        if not self._need_midi():
            return
        self.midi.note_on(self.sp_mch.value(), n, vel or parse_velocities(self.ed_vels.text())[-1])
        self.keyboard.set_active(n)

    def _kb_release(self, n):
        if self.midi.is_open:
            self.midi.note_off(self.sp_mch.value(), n)
        if not (self.engine and self.engine.isRunning()):
            self.keyboard.set_active(-1)

    def _panic(self):
        if self.midi.is_open:
            self.midi.panic()
            self._log("Panic: All Notes Off", "info")
        self.audio.stop_play()

    def _measure_floor(self):
        if not self.audio.running:
            self._log("Аудіо-вхід не відкрито.", "warn")
            return
        self.btn_floor.setEnabled(False)
        self.lbl_floor.setText("вимірюю…")
        self.audio.begin_capture()

        def done():
            x = self.audio.end_capture()
            self.btn_floor.setEnabled(True)
            if not len(x):
                self.lbl_floor.setText("")
                return
            rms = dsp.lin2db(float(np.sqrt(np.mean(np.square(x)))))
            pk = dsp.lin2db(dsp.peak(x))
            self.lbl_floor.setText(f"шум: {rms:.0f} dB RMS / {pk:.0f} dB пік")
            # пороги трохи вище піку шуму
            thr = min(-20.0, round(pk + 6))
            self.sp_tstart.setValue(max(thr, -90))
            self.sp_tend.setValue(max(thr, -120))
            self.sp_sil.setValue(max(min(-20.0, round(rms + 6)), -120))
            self._log(f"Рівень шуму {rms:.1f} dB RMS, пік {pk:.1f} dB → пороги обрізки {thr:.0f} dB", "ok")

        QTimer.singleShot(1500, done)

    # ==================================================================
    # запис
    # ==================================================================
    def _start_all(self):
        s = self.collect()
        jobs = build_jobs(s)
        dirs = {instrument_dir(s, p) for p in s.programs()}
        existing = [d for d in dirs if (d / "Samples").exists() and any((d / "Samples").glob("*.wav"))]
        if existing:
            r = QMessageBox.question(
                self, "Папка вже існує",
                f"У папці «{existing[0]}» уже є семпли.\nФайли з однаковими іменами буде перезаписано. Продовжити?")
            if r != QMessageBox.Yes:
                return
        # новий повний прохід: прибираємо зі списку семпли цих програм
        progs = set(s.programs())
        self.results = {k: v for k, v in self.results.items() if v.program not in progs}
        self._rebuild_table()
        self._run(jobs, s)

    def _run(self, jobs: list[Job], s: Settings):
        if not jobs:
            return
        if not self._need_midi():
            return
        if not self.audio.running:
            self._log("Аудіо-вхід не відкрито — перевір вкладку «Підключення».", "warn")
            self.tabs.setCurrentIndex(0)
            return
        if s.sample_rate != self.audio.sr:
            self._restart_audio()
        try:
            Path(s.output_dir).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self._log(f"Не можу створити папку: {e}", "err")
            return
        self.audio.stop_play()
        self.engine = SamplingEngine(s, self.audio, self.midi, jobs, self.results, self)
        self.engine.progress.connect(self._on_progress)
        self.engine.sampleDone.connect(self._on_sample)
        self.engine.noteActive.connect(self.keyboard.set_active)
        self.engine.message.connect(lambda lvl, t: self._log(t, lvl))
        self.engine.finishedRun.connect(self._on_finished)
        self._set_running(True)
        self.progress.setMaximum(len(jobs))
        self.progress.setValue(0)
        self._set_status(f"Запис… 0 / {len(jobs)}")
        self._log(f"Старт: {len(jobs)} семплів → {instrument_dir(s, s.programs()[0]).parent if s.send_program else instrument_dir(s, None)}", "info")
        self.engine.start()

    def _stop(self):
        if self.engine and self.engine.isRunning():
            self.engine.stop()
            self._set_status("Зупиняю…")

    def _escape(self):
        if self.engine and self.engine.isRunning():
            self._stop()
        else:
            self.audio.stop_play()

    def _set_running(self, on: bool):
        self.btn_start.setEnabled(not on)
        self.btn_stop.setEnabled(on)
        for w in (self.btn_rerec, self.btn_del, self.btn_map, self.btn_test, self.btn_floor, self.btn_play):
            w.setEnabled(not on)
        self.keyboard.setEnabled(not on)
        # пристрої не можна міняти під час запису
        for w in (self.cb_api, self.cb_in, self.cb_chan, self.cb_sr, self.cb_midi, self.sp_mch):
            w.setEnabled(not on)

    def _on_progress(self, done, total, eta):
        self.progress.setValue(done)
        self._set_status(f"Запис… {done} / {total}  ·  залишилось ≈ {_fmt_time(eta)}")

    def _on_sample(self, r: SampleResult):
        self.results[r.key] = r
        self._upsert_row(r)
        self.keyboard.set_recorded({x.note for x in self.results.values()})
        self.lbl_count.setText(f"Семпли: {len(self.results)}")

    def _on_finished(self, ok: bool):
        self._set_running(False)
        self.keyboard.set_active(-1)
        if ok:
            self._set_status(f"Готово ✓  {len(self.results)} семплів")
            self._log("Готово! Інструмент збережено.", "ok")
            QApplication_beep()
        else:
            self._set_status("Зупинено")
        self.wave.set_data(None, 48000)
        if self.table.rowCount():
            self.table.selectRow(self.table.rowCount() - 1)
        self.engine = None
        self._restart_audio() if not self.audio.running else None

    # ==================================================================
    # таблиця семплів
    # ==================================================================
    def _row_of(self, key):
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.UserRole) == key:
                return row
        return -1

    def _upsert_row(self, r: SampleResult):
        row = self._row_of(r.key)
        if row < 0:
            row = self.table.rowCount()
            self.table.insertRow(row)
        c3 = bool(self.cb_c3.currentData())
        if r.detected is None:
            heard = "—"
        else:
            nn = round(r.detected)
            cents = (r.detected - nn) * 100
            heard = f"{note_name(nn, c3)} {cents:+.0f}¢"
        off = r.detected is not None and abs(r.detected - r.note) >= 0.5
        if r.art == "swell":
            layer = "Свел"
        elif r.expr is None:
            layer = "—"
        else:
            layer = (f"AT {r.expr}" if self.cb_expr.currentData() != "cc"
                     else f"CC{self.sp_ecc.value()} {r.expr}")
        vals = [f"{r.program:03d}" if r.program else "—", note_name(r.note, c3), str(r.note), str(r.vel),
                layer, str(r.rr), heard, f"{r.frames / r.sr:.2f} с",
                f"{r.peak_db:.1f} dB" + (" ⟲" if r.loop else ""), os.path.basename(r.path)]
        for c, t in enumerate(vals):
            it = QTableWidgetItem(t)
            if c < 9:
                it.setTextAlignment(Qt.AlignCenter)
            if c == 6:
                if off:
                    it.setForeground(QColor(S.WARN))
                    it.setToolTip(f"Звучить на {r.detected - r.note:+.1f} півт. від надісланої ноти; "
                                  f"root note у файлі: {note_name(r.root_note, c3)} ({r.root_note})")
                elif r.detected is None:
                    it.setToolTip("Висоту не визначено (шум / ударний / дуже короткий звук)")
            if c == 8 and r.clipped:
                it.setForeground(QColor(S.REC))
                it.setToolTip("Кліп на вході")
            if c == 0:
                it.setData(Qt.UserRole, r.key)
            self.table.setItem(row, c, it)
        if self.engine and self.engine.isRunning():
            self.table.scrollToItem(self.table.item(row, 0))

    def _rebuild_table(self):
        self.table.setRowCount(0)
        for r in sorted(self.results.values(), key=lambda r: (r.program or 0, r.note, r.vel, r.rr)):
            self._upsert_row(r)
        self.keyboard.set_recorded({x.note for x in self.results.values()})
        self.lbl_count.setText(f"Семпли: {len(self.results)}")

    def _refresh_table_names(self):
        if hasattr(self, "table"):
            self._rebuild_table()

    def _selected(self) -> list[SampleResult]:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        out = []
        for row in rows:
            key = self.table.item(row, 0).data(Qt.UserRole)
            if key in self.results:
                out.append(self.results[key])
        return out

    def _on_select(self):
        if self.engine and self.engine.isRunning():
            return
        sel = self._selected()
        if not sel:
            return
        r = sel[0]
        try:
            data, sr, meta = read_wav(r.path)
        except Exception as e:
            self._log(f"Не вдалося прочитати {r.path}: {e}", "err")
            return
        c3 = bool(self.cb_c3.currentData())
        title = f"{note_name(r.note, c3)}  ·  vel {r.vel}  ·  rr {r.rr}"
        self.wave.set_data(data, sr, meta.get("loop") or r.loop, title)
        self._preview = (data, sr)

    def _play_selected(self):
        if self.engine and self.engine.isRunning():
            return
        sel = self._selected()
        if not sel:
            return
        try:
            data, sr, _ = read_wav(sel[0].path)
            self.audio.play(data, sr)
        except Exception as e:
            self._log(f"Відтворення не вдалося: {e}", "err")

    def _rerecord_selected(self):
        sel = self._selected()
        if not sel:
            self._log("Виділи семпли в таблиці, які треба перезаписати.", "warn")
            return
        s = self.collect()
        jobs = [Job(r.program, r.note, r.vel, r.rr, r.expr, r.art) for r in sel]
        if any(j.program is not None for j in jobs):
            s.send_program = True
        self._run(jobs, s)

    def _delete_selected(self):
        sel = self._selected()
        if not sel:
            return
        r = QMessageBox.question(self, "Видалити семпли",
                                 f"Видалити {len(sel)} семпл(ів) зі списку і з диска?\nЦе не можна скасувати.")
        if r != QMessageBox.Yes:
            return
        for x in sel:
            try:
                if os.path.exists(x.path):
                    os.remove(x.path)
            except Exception as e:
                self._log(f"Не вдалося видалити {x.path}: {e}", "err")
            self.results.pop(x.key, None)
        self._rebuild_table()
        self.wave.set_data(None, 48000)
        self._write_mappings()

    def _write_mappings(self):
        s = self.collect()
        progs = {r.program for r in self.results.values()}
        if not progs:
            self._log("Немає семплів для мапінгу.", "warn")
            return
        for p in sorted(progs, key=lambda p: p or 0):
            for f in write_mappings(s, p, list(self.results.values())):
                self._log(f"Збережено: {f}", "ok")

    def _open_folder(self):
        s = self.collect()
        d = instrument_dir(s, None)
        if not d.exists():
            d = Path(s.output_dir)
        d.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(d))
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(d)])

    def _table_menu(self, pos):
        m = QMenu(self)
        m.addAction("▶  Слухати", self._play_selected)
        m.addAction("⟳  Перезаписати", self._rerecord_selected)
        m.addSeparator()
        m.addAction("✕  Видалити", self._delete_selected)
        m.exec(self.table.viewport().mapToGlobal(pos))

    # ==================================================================
    # пресети
    # ==================================================================
    def _open_preset(self):
        path, _ = QFileDialog.getOpenFileName(self, "Відкрити пресет", str(config_dir() / "presets"),
                                              "AutoSample preset (*.json)")
        if path:
            try:
                self.apply(Settings.load(path))
                self._log(f"Пресет завантажено: {os.path.basename(path)}", "ok")
            except Exception as e:
                self._log(f"Не вдалося відкрити пресет: {e}", "err")

    def _save_preset(self):
        (config_dir() / "presets").mkdir(parents=True, exist_ok=True)
        s = self.collect()
        path, _ = QFileDialog.getSaveFileName(self, "Зберегти пресет",
                                              str(config_dir() / "presets" / f"{s.name}.json"),
                                              "AutoSample preset (*.json)")
        if path:
            s.save(path)
            self._log(f"Пресет збережено: {path}", "ok")

    # ==================================================================
    def _set_status(self, t):
        self.status.setText(t)

    def _log(self, text, level="info"):
        col = LOG_COLORS.get(level, S.MUTED)
        from html import escape
        self.log.appendHtml(f'<span style="color:{col}">{escape(text)}</span>')


def QApplication_beep():
    from PySide6.QtWidgets import QApplication
    QApplication.beep()
