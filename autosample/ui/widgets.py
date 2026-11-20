"""Кастомні віджети: клавіатура, хвильова форма, індикатор рівня, спінбокс нот."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSpinBox, QWidget

from ..settings import is_black, note_name, parse_note
from . import style as S


class NoteSpinBox(QSpinBox):
    """Спінбокс, що показує ноту як «C3 · 60» і приймає введення «C#2» або «61»."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.c3 = True
        self.setRange(0, 127)

    def textFromValue(self, v):
        return f"{note_name(v, self.c3)}  ·  {v}"

    def valueFromText(self, text):
        n = parse_note(text.split("·")[0] if "·" in text else text, self.c3)
        return self.value() if n is None else n

    def validate(self, text, pos):
        from PySide6.QtGui import QValidator
        return (QValidator.Acceptable, text, pos) if text.strip() else (QValidator.Intermediate, text, pos)

    def set_c3(self, c3: bool):
        self.c3 = c3
        v = self.value()
        self.setValue((v + 1) % 128)
        self.setValue(v)


# ----------------------------------------------------------------------
class LevelMeter(QWidget):
    """Горизонтальний індикатор рівня на 1–2 канали, -60..0 dBFS, з peak-hold і кліпом."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.levels = [0.0, 0.0]
        self.holds = [-90.0, -90.0]
        self.clip = False
        self.nch = 2
        self.setMinimumHeight(34)

    def set_peaks(self, peaks):
        self.nch = len(peaks)
        while len(self.levels) < self.nch:
            self.levels.append(0.0)
            self.holds.append(-90.0)
        for i, p in enumerate(peaks):
            db = 20 * np.log10(max(float(p), 1e-9))
            self.levels[i] = max(db, self.levels[i] - 1.6)        # плавне падіння
            self.holds[i] = db if db > self.holds[i] else self.holds[i] - 0.25
            if p >= 0.999:
                self.clip = True
        self.update()

    def mousePressEvent(self, e):
        self.clip = False
        self.holds = [-90.0] * len(self.holds)
        self.update()

    def _x(self, db, w):
        return max(0.0, min(1.0, (db + 60) / 60)) * w

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width() - 34
        h = self.height()
        lane = (h - 14) / max(1, self.nch)
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, QColor(S.ACCENT_DIM))
        grad.setColorAt(0.7, QColor(S.ACCENT))
        grad.setColorAt(0.9, QColor(S.WARN))
        grad.setColorAt(1.0, QColor(S.REC))
        for i in range(self.nch):
            y = i * lane
            r = QRectF(0, y + 1, w, lane - 3)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(S.PANEL2))
            p.drawRoundedRect(r, 2, 2)
            lw = self._x(self.levels[i], w)
            p.setBrush(grad)
            p.drawRoundedRect(QRectF(0, y + 1, lw, lane - 3), 2, 2)
            hx = self._x(self.holds[i], w)
            p.setBrush(QColor("#ffffff"))
            p.drawRect(QRectF(hx - 1, y + 1, 2, lane - 3))
        # шкала
        p.setPen(QColor(S.MUTED))
        f = QFont(p.font())
        f.setPointSizeF(7)
        p.setFont(f)
        for db in (-48, -36, -24, -12, -6, 0):
            x = self._x(db, w)
            p.drawText(QRectF(x - 12, h - 12, 24, 12), Qt.AlignCenter, str(db))
        # кліп
        cr = QRectF(w + 6, 1, 28, h - 15)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(S.REC if self.clip else S.PANEL2))
        p.drawRoundedRect(cr, 3, 3)
        p.setPen(QColor("#1a0d0d" if self.clip else S.MUTED))
        p.drawText(cr, Qt.AlignCenter, "CLIP")


# ----------------------------------------------------------------------
class KeyboardWidget(QWidget):
    notePressed = Signal(int)
    noteReleased = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lo, self.hi = 21, 108
        self.planned: set[int] = set()
        self.recorded: set[int] = set()
        self.active = -1
        self.pressed = -1
        self.c3 = True
        self.setMinimumHeight(78)
        self.setMaximumHeight(96)
        self.setCursor(Qt.PointingHandCursor)

    def set_plan(self, notes, c3=True):
        self.planned = set(notes)
        self.c3 = c3
        lo = min([21] + list(notes))
        hi = max([108] + list(notes))
        self.lo = lo - (lo % 12)          # починаємо з C
        self.hi = hi if not is_black(hi) else hi + 1
        self.update()

    def set_recorded(self, notes):
        self.recorded = set(notes)
        self.update()

    def set_active(self, n):
        self.active = n
        self.update()

    def _geometry(self):
        whites = [n for n in range(self.lo, self.hi + 1) if not is_black(n)]
        ww = self.width() / max(1, len(whites))
        h = self.height()
        rects = {}
        for i, n in enumerate(whites):
            rects[n] = QRectF(i * ww, 0, ww, h)
        blacks = {}
        bw = ww * 0.62
        for n in range(self.lo, self.hi + 1):
            if is_black(n) and (n - 1) in rects:
                x = rects[n - 1].right() - bw / 2
                blacks[n] = QRectF(x, 0, bw, h * 0.6)
        return rects, blacks

    def _note_at(self, pos):
        rects, blacks = self._geometry()
        for n, r in blacks.items():
            if r.contains(pos):
                return n
        for n, r in rects.items():
            if r.contains(pos):
                return n
        return -1

    def mousePressEvent(self, e):
        if not self.isEnabled():
            return
        n = self._note_at(e.position())
        if n >= 0:
            self.pressed = n
            self.notePressed.emit(n)
            self.update()

    def mouseReleaseEvent(self, e):
        if self.pressed >= 0:
            self.noteReleased.emit(self.pressed)
            self.pressed = -1
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rects, blacks = self._geometry()
        f = QFont(p.font())
        f.setPointSizeF(7)
        p.setFont(f)
        for n, r in rects.items():
            if n in (self.active, self.pressed):
                c = QColor(S.ACTIVE)
            elif n in self.recorded:
                c = QColor(S.ACCENT)
            elif n in self.planned:
                c = QColor("#a9d8d3")
            else:
                c = QColor("#e4e7ec")
            p.setPen(QPen(QColor(S.BG), 1))
            p.setBrush(c)
            p.drawRoundedRect(r.adjusted(0.5, -3, -0.5, 0), 3, 3)
            if n % 12 == 0:
                p.setPen(QColor("#4b5260"))
                p.drawText(QRectF(r.x(), r.bottom() - 16, r.width(), 14), Qt.AlignCenter, note_name(n, self.c3))
        for n, r in blacks.items():
            if n in (self.active, self.pressed):
                c = QColor(S.ACTIVE)
            elif n in self.recorded:
                c = QColor("#2fa89d")
            elif n in self.planned:
                c = QColor("#2f5c58")
            else:
                c = QColor("#1b1e24")
            p.setPen(QPen(QColor(S.BG), 1))
            p.setBrush(c)
            p.drawRoundedRect(r.adjusted(0, -3, 0, 0), 2, 2)


# ----------------------------------------------------------------------
class WaveformWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = None
        self.sr = 48000
        self.loop = None
        self.title = ""
        self.live = False
        self._cache = None
        self._cache_w = 0
        self.setMinimumHeight(140)

    def set_data(self, data, sr, loop=None, title="", live=False):
        self.data = None if data is None or len(data) == 0 else data
        self.sr = sr
        self.loop = loop
        self.title = title
        self.live = live
        self._cache = None
        self.update()

    def _peaks(self, w):
        if self._cache is not None and self._cache_w == w:
            return self._cache
        d = self.data
        n, nch = d.shape
        w = max(1, int(w))
        if self.live:
            # під час запису масштаб фіксований (мінімум 4 с), щоб хвиля «бігла» вправо
            total = max(n, int(self.sr * 4))
        else:
            total = n
        edges = np.linspace(0, total, w + 1).astype(np.int64)
        mins = np.zeros((w, nch), np.float32)
        maxs = np.zeros((w, nch), np.float32)
        valid = edges[1:] <= n
        last = int(np.searchsorted(edges[1:], n, side="right"))
        if last > 0:
            starts = edges[:last]
            if np.all(np.diff(starts) > 0):
                mins[:last] = np.minimum.reduceat(d, starts, axis=0)[:last]
                maxs[:last] = np.maximum.reduceat(d, starts, axis=0)[:last]
            else:
                for i in range(last):
                    seg = d[edges[i]:max(edges[i + 1], edges[i] + 1)]
                    mins[i], maxs[i] = seg.min(axis=0), seg.max(axis=0)
        self._cache = (mins, maxs, total, last)
        self._cache_w = w
        return self._cache

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        r = self.rect()
        p.setPen(QPen(QColor(S.BORDER), 1))
        p.setBrush(QColor(S.PANEL))
        p.drawRoundedRect(QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        if self.data is None:
            p.setPen(QColor(S.MUTED))
            p.drawText(r, Qt.AlignCenter, "Тут з'явиться хвильова форма семпла")
            return
        pad = 10
        w = r.width() - 2 * pad
        h = r.height() - 2 * pad - 14
        mins, maxs, total, last = self._peaks(w)
        nch = mins.shape[1]
        lane = h / nch
        col = QColor(S.REC if self.live else S.ACCENT)

        # луп
        if self.loop and not self.live:
            x1 = pad + self.loop[0] / total * w
            x2 = pad + self.loop[1] / total * w
            p.fillRect(QRectF(x1, pad, max(1, x2 - x1), h), QColor(79, 209, 197, 28))
            p.setPen(QPen(QColor(S.WARN), 1, Qt.DashLine))
            p.drawLine(QPointF(x1, pad), QPointF(x1, pad + h))
            p.drawLine(QPointF(x2, pad), QPointF(x2, pad + h))

        for c in range(nch):
            mid = pad + lane * c + lane / 2
            p.setPen(QPen(QColor(S.BORDER), 1))
            p.drawLine(QPointF(pad, mid), QPointF(pad + w, mid))
            path = QPainterPath()
            amp = lane / 2 * 0.92
            p.setPen(QPen(col, 1))
            for i in range(last):
                x = pad + i
                y1 = mid - maxs[i, c] * amp
                y2 = mid - mins[i, c] * amp
                p.drawLine(QPointF(x, y1), QPointF(x, max(y2, y1 + 1)))

        # шкала часу
        p.setPen(QColor(S.MUTED))
        f = QFont(p.font())
        f.setPointSizeF(7.5)
        p.setFont(f)
        dur = total / self.sr
        step = next((s for s in (0.1, 0.25, 0.5, 1, 2, 5, 10, 30) if dur / s <= 12), 60)
        t = 0.0
        while t <= dur:
            x = pad + t / dur * w if dur else pad
            p.drawText(QRectF(x - 20, r.height() - pad - 12, 40, 12), Qt.AlignCenter, f"{t:g}s")
            t += step
        if self.title:
            p.setPen(QColor(S.TEXT))
            f.setPointSizeF(9)
            f.setBold(True)
            p.setFont(f)
            tw = p.fontMetrics().horizontalAdvance(self.title) + 16
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(18, 20, 24, 210))
            p.drawRoundedRect(QRectF(pad + 2, pad + 2, tw, 20), 4, 4)
            p.setPen(QColor(S.REC if self.live else S.TEXT))
            p.drawText(QRectF(pad + 10, pad + 2, w, 20), Qt.AlignLeft | Qt.AlignVCenter, self.title)
