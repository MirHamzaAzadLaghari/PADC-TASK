"""Tkinter user interface for the Premium Calculator.

Design notes
------------
* The keypad is ONE canvas, not 30 widgets. Buttons are rounded polygons that
  are hit-tested by coordinates, so hover / press feedback is a single
  ``itemconfigure`` call and the layout re-flows instantly on resize.
* Buttons fire on mouse-down (not mouse-up) to remove ~100 ms of perceived lag.
* Everything animated is a short colour tween (<= ~90 ms) driven by ``after``.
* The result line is a live preview: it updates on every key press.
"""

from __future__ import annotations

import re
import sys
import tkinter as tk
from tkinter import font as tkfont

from .engine import CalcError, Calculator, format_number

# --------------------------------------------------------------------------- #
# Theme: deep teal-black base, brass accent
# --------------------------------------------------------------------------- #
BG, PANEL, BORDER = "#0B1215", "#111C20", "#1B2C32"
TEXT, DIM, DIMMER, PREVIEW = "#EAF2F2", "#6F8A90", "#3A4F55", "#8FB3B8"
ACCENT, ACCENT_HOVER, ACCENT_PRESS, ON_ACCENT = "#F0B54A", "#F7C766", "#D79A2E", "#1A1203"
CORAL = "#FF7A6B"

STYLES = {
    "key":     dict(bg="#172429", hover="#203239", press="#2B434C", fg=TEXT,      scale=0.36, bold=True),
    "op":      dict(bg="#1A2D33", hover="#233B43", press="#2E4B55", fg=ACCENT,    scale=0.42, bold=False),
    "fn":      dict(bg="#121E22", hover="#1A2A30", press="#25393F", fg="#9DB9BE", scale=0.34, bold=False),
    "clear":   dict(bg="#121E22", hover="#1A2A30", press="#25393F", fg=CORAL,     scale=0.34, bold=True),
    "sci":     dict(bg="#101A1E", hover="#18272D", press="#223439", fg="#8FB3B8", scale=0.30, bold=False),
    "mem":     dict(bg=BG,        hover="#121E22", press="#1A2A30", fg=DIM,       scale=0.28, bold=False),
    "mem_on":  dict(bg=BG,        hover="#121E22", press="#1A2A30", fg=ACCENT,    scale=0.28, bold=True),
    "eq":      dict(bg=ACCENT,    hover=ACCENT_HOVER, press=ACCENT_PRESS, fg=ON_ACCENT, scale=0.46, bold=True),
    "chip":    dict(bg="#121E22", hover="#1A2A30", press="#25393F", fg="#9DB9BE", scale=0.40, bold=False),
    "chip_on": dict(bg="#2B2614", hover="#352E19", press="#40371F", fg=ACCENT,    scale=0.40, bold=False),
}

FONT = "Segoe UI"
PAD = 16


def init_theme() -> None:
    """Pick the best installed UI font. Needs a Tk root to exist."""
    global FONT
    installed = set(tkfont.families())
    for name in ("Segoe UI Variable Display", "Segoe UI", "SF Pro Display", "Helvetica Neue",
                 "Inter", "Roboto", "Noto Sans", "DejaVu Sans"):
        if name in installed:
            FONT = name
            return


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _rgb(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(rgb)


def rrect_points(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


def rrect(canvas, x1, y1, x2, y2, r, **kw):
    return canvas.create_polygon(rrect_points(x1, y1, x2, y2, r), smooth=True, **kw)


_GROUP_RE = re.compile(r"^([-−])?(\d+)(\.\d*)?$")
_SCI_RE = re.compile(r"^([-−])?([\d.]+)e([+-]\d+)$")
_SUPERSCRIPT = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def group_digits(s: str) -> str:
    """1234567.5 -> 1,234,567.5 and 1.5e+20 -> 1.5×10²⁰ (display only)."""
    sci = _SCI_RE.match(s)
    if sci:
        sign, mantissa, exp = sci.groups()
        return f"{sign or ''}{mantissa}×10{str(int(exp)).translate(_SUPERSCRIPT)}"
    m = _GROUP_RE.match(s)
    if not m:
        return s
    sign, whole, frac = m.groups()
    return f"{sign or ''}{int(whole):,}{frac or ''}"


# --------------------------------------------------------------------------- #
# ButtonBoard: a canvas that draws and animates a set of rounded buttons
# --------------------------------------------------------------------------- #
class _Btn:
    __slots__ = ("key", "rect", "style", "shape", "text", "rgb", "anim")


class ButtonBoard(tk.Canvas):
    def __init__(self, master, layout, on_press, decorate=None, **kw):
        super().__init__(master, bg=BG, highlightthickness=0, bd=0, **kw)
        self.layout, self.on_press, self.decorate = layout, on_press, decorate
        self.buttons: list[_Btn] = []
        self.by_key: dict[str, _Btn] = {}
        self._hover: _Btn | None = None
        self.bind("<Configure>", lambda e: self.relayout())
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self._set_hover(None))
        self.bind("<ButtonPress-1>", self._press)

    # -- drawing ------------------------------------------------------------ #
    def relayout(self) -> None:
        w, h = self.winfo_width(), self.winfo_height()
        if w < 20 or h < 20:
            return
        for b in self.buttons:
            if b.anim:
                self.after_cancel(b.anim)
        self.delete("all")
        self.buttons, self.by_key, self._hover = [], {}, None
        if self.decorate:
            self.decorate(self, w, h)
        for key, label, style, x1, y1, x2, y2, px in self.layout(w, h):
            st = STYLES[style]
            b = _Btn()
            b.key, b.rect, b.style, b.anim, b.rgb = key, (x1, y1, x2, y2), style, None, _rgb(st["bg"])
            b.shape = rrect(self, x1, y1, x2, y2, min(x2 - x1, y2 - y1) * 0.30, fill=st["bg"], outline="")
            font = (FONT, -max(12, px), "bold" if st["bold"] else "normal")
            b.text = self.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=label, fill=st["fg"], font=font)
            self.buttons.append(b)
            self.by_key[key] = b

    # -- public tweaks ------------------------------------------------------ #
    def set_label(self, key: str, label: str) -> None:
        if key in self.by_key:
            self.itemconfigure(self.by_key[key].text, text=label)

    def set_style(self, key: str, style: str) -> None:
        b = self.by_key.get(key)
        if b:
            b.style = style
            self.itemconfigure(b.text, fill=STYLES[style]["fg"])
            self._tween(b, STYLES[style]["bg"], steps=4)

    def flash(self, key: str) -> None:
        """Visual feedback for keyboard input."""
        b = self.by_key.get(key)
        if b:
            self._tween(b, STYLES[b.style]["press"], steps=1)
            self.after(90, self._release, b)

    # -- events ------------------------------------------------------------- #
    def _hit(self, x, y):
        for b in self.buttons:
            x1, y1, x2, y2 = b.rect
            if x1 <= x <= x2 and y1 <= y <= y2:
                return b
        return None

    def _motion(self, e) -> None:
        self._set_hover(self._hit(e.x, e.y))

    def _set_hover(self, b) -> None:
        if b is self._hover:
            return
        old, self._hover = self._hover, b
        if old:
            self._tween(old, STYLES[old.style]["bg"])
        if b:
            self._tween(b, STYLES[b.style]["hover"])
        self.configure(cursor="hand2" if b else "")

    def _press(self, e) -> None:
        b = self._hit(e.x, e.y)
        if b:
            self._tween(b, STYLES[b.style]["press"], steps=1)
            self.on_press(b.key)  # fire immediately on mouse-down
            self.after(90, self._release, b)

    def _release(self, b) -> None:
        if b in self.buttons:
            st = STYLES[b.style]
            self._tween(b, st["hover"] if b is self._hover else st["bg"], steps=5)

    # -- animation ---------------------------------------------------------- #
    def _paint(self, b, rgb) -> None:
        b.rgb = rgb
        self.itemconfigure(b.shape, fill=_hex(rgb))

    def _tween(self, b, target: str, steps: int = 5, delay: int = 14) -> None:
        if b.anim:
            self.after_cancel(b.anim)
            b.anim = None
        start, end = b.rgb, _rgb(target)
        if steps <= 1:
            self._paint(b, end)
            return

        def step(i):
            t = i / steps
            t = 1 - (1 - t) * (1 - t)  # ease-out
            self._paint(b, tuple(round(s + (e - s) * t) for s, e in zip(start, end)))
            b.anim = self.after(delay, step, i + 1) if i < steps else None

        step(1)


# --------------------------------------------------------------------------- #
# Display
# --------------------------------------------------------------------------- #
class Display(tk.Canvas):
    def __init__(self, master, **kw):
        super().__init__(master, bg=BG, highlightthickness=0, bd=0, **kw)
        self.top, self.bottom, self.color, self.error = "", "0", TEXT, False
        self.mem = self.inv = False
        self._fade_id = None
        self.expr_font = tkfont.Font(family=FONT, size=-18)
        self.res_font = tkfont.Font(family=FONT, size=-56, weight="bold")
        self.badge_font = tkfont.Font(family=FONT, size=-13, weight="bold")
        self.bind("<Configure>", lambda e: self.redraw())

    def redraw(self) -> None:
        w, h = self.winfo_width(), self.winfo_height()
        if w < 40:
            return
        self.delete("all")
        rrect(self, PAD, 4, w - PAD, h - 4, 24, fill=PANEL, outline=BORDER)
        self.i_mem = self.create_text(PAD + 22, 24, anchor="w", font=self.badge_font, fill=ACCENT)
        self.i_inv = self.create_text(PAD + 46, 24, anchor="w", font=self.badge_font, fill=PREVIEW)
        self.i_toast = self.create_text(w - PAD - 22, 24, anchor="e", font=self.badge_font, fill=DIM)
        self.i_expr = self.create_text(w - PAD - 22, 58, anchor="e", font=self.expr_font, fill=DIM)
        self.i_res = self.create_text(w - PAD - 22, h - 58, anchor="e", font=self.res_font, fill=self.color)
        self._apply()

    def render(self, top: str, bottom: str, color: str = TEXT, error: bool = False, animate: bool = False) -> None:
        self.top, self.bottom, self.color, self.error = top, bottom, color, error
        if self._fade_id:
            self.after_cancel(self._fade_id)
            self._fade_id = None
        if not hasattr(self, "i_res") or not self.find_withtag(self.i_res):
            return
        self._apply()
        if animate:
            self._fade(color)

    def set_badges(self, mem: bool, inv: bool) -> None:
        self.mem, self.inv = mem, inv
        if hasattr(self, "i_mem"):
            self.itemconfigure(self.i_mem, text="M" if mem else "")
            self.itemconfigure(self.i_inv, text="2nd" if inv else "", )
            self.coords(self.i_inv, PAD + (46 if mem else 22), 24)

    def toast(self, message: str) -> None:
        self.itemconfigure(self.i_toast, text=message)
        self.after(1100, lambda: self.itemconfigure(self.i_toast, text=""))

    def _apply(self) -> None:
        avail = self.winfo_width() - 2 * (PAD + 22)
        # expression line: trim from the left if too long
        text = self.top
        self.expr_font.configure(size=-18)
        width = self.expr_font.measure(text)
        if width > avail and text:
            keep = max(4, int(len(text) * avail / width) - 2)
            text = "…" + text[-keep:]
        self.itemconfigure(self.i_expr, text=text)
        # result line: shrink font to fit (errors use a smaller maximum)
        max_px = int(self.winfo_height() * (0.20 if self.error else 0.36))
        self.res_font.configure(size=-max_px)
        width = self.res_font.measure(self.bottom)
        if width > avail:
            self.res_font.configure(size=-max(14, int(max_px * avail / width) - 1))
        self.itemconfigure(self.i_res, text=self.bottom, fill=self.color)
        self.set_badges(self.mem, self.inv)

    def _fade(self, target: str, steps: int = 7) -> None:
        if self._fade_id:
            self.after_cancel(self._fade_id)
        start, end = _rgb(DIMMER), _rgb(target)

        def step(i):
            t = i / steps
            self.itemconfigure(self.i_res, fill=_hex(tuple(round(s + (e - s) * t) for s, e in zip(start, end))))
            self._fade_id = self.after(14, step, i + 1) if i < steps else None

        step(1)

    def shake(self) -> None:
        offsets = [-9, 9, -6, 6, -3, 3, 0]
        last = [0]

        def step(i):
            if i < len(offsets):
                self.move(self.i_res, offsets[i] - last[0], 0)
                last[0] = offsets[i]
                self.after(16, step, i + 1)

        step(0)


# --------------------------------------------------------------------------- #
# History drawer
# --------------------------------------------------------------------------- #
class HistoryList(tk.Canvas):
    ROW = 76

    def __init__(self, master, on_pick, **kw):
        super().__init__(master, bg=BG, highlightthickness=0, bd=0, yscrollincrement=24, **kw)
        self.on_pick, self.entries, self._hl = on_pick, [], None
        self.small = tkfont.Font(family=FONT, size=-15)
        self.big = tkfont.Font(family=FONT, size=-24, weight="bold")
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Motion>", self._hover)
        self.bind("<Leave>", lambda e: self._hl and self.itemconfigure(self._hl, state="hidden"))
        self.bind("<ButtonPress-1>", self._click)
        self.bind("<MouseWheel>", lambda e: self.yview_scroll((-3 if e.delta > 0 else 3), "units"))
        self.bind("<Button-4>", lambda e: self.yview_scroll(-3, "units"))
        self.bind("<Button-5>", lambda e: self.yview_scroll(3, "units"))

    def set_entries(self, entries) -> None:
        self.entries = entries
        self.redraw()

    def redraw(self) -> None:
        w = self.winfo_width()
        if w < 40:
            return
        self.delete("all")
        self._hl = None
        if not self.entries:
            self.create_text(w / 2, 110, text="Calculations you run show up here.\nClick one to reuse its result.",
                             fill=DIM, font=self.small, justify="center", width=w - 56)
            self.configure(scrollregion=(0, 0, w, 1))
            return
        self._hl = rrect(self, 10, 0, w - 10, 0, 14, fill="#172429", outline="", state="hidden")
        avail = w - 44
        y = 0
        for expr, result in self.entries:
            text = expr + " ="
            width = self.small.measure(text)
            if width > avail:
                text = "…" + text[-max(4, int(len(text) * avail / width) - 2):]
            self.create_text(w - 22, y + 26, anchor="e", text=text, fill=DIM, font=self.small)
            shown = group_digits(result)
            width = self.big.measure(shown)
            font = self.big if width <= avail else (FONT, -max(12, int(24 * avail / width) - 1), "bold")
            self.create_text(w - 22, y + 53, anchor="e", text=shown, fill=TEXT, font=font)
            y += self.ROW
        self.configure(scrollregion=(0, 0, w, y))

    def _index(self, e):
        i = int(self.canvasy(e.y) // self.ROW)
        return i if 0 <= i < len(self.entries) else None

    def _hover(self, e) -> None:
        i = self._index(e)
        if self._hl is None:
            return
        if i is None:
            self.itemconfigure(self._hl, state="hidden")
            return
        w = self.winfo_width()
        self.coords(self._hl, *rrect_points(10, i * self.ROW + 4, w - 10, (i + 1) * self.ROW - 4, 14))
        self.itemconfigure(self._hl, state="normal")
        self.configure(cursor="hand2")

    def _click(self, e) -> None:
        i = self._index(e)
        if i is not None:
            self.on_pick(*self.entries[i])


class HistoryPanel(tk.Frame):
    WIDTH = 300

    def __init__(self, master, on_pick, on_clear):
        super().__init__(master, bg=BG, width=self.WIDTH)
        self.pack_propagate(False)
        tk.Frame(self, bg=BORDER, width=1).pack(side="left", fill="y")
        inner = tk.Frame(self, bg=BG)
        inner.pack(side="left", fill="both", expand=True)

        def layout(w, h):
            ch = 34
            y1 = (h - ch) / 2
            return [("clear_history", "Clear", "chip", w - PAD - 72, y1, w - PAD, y1 + ch, 14)]

        def decorate(canvas, w, h):
            canvas.create_text(PAD + 4, h / 2, anchor="w", text="History", fill=TEXT,
                               font=(FONT, -22, "bold"))

        self.header = ButtonBoard(inner, layout, lambda key: on_clear(), decorate=decorate, height=56)
        self.header.pack(fill="x")
        self.list = HistoryList(inner, on_pick)
        self.list.pack(fill="both", expand=True)


# --------------------------------------------------------------------------- #
# Key maps
# --------------------------------------------------------------------------- #
BASIC_ROWS = [
    [("MC", "mem"), ("MR", "mem"), ("M+", "mem"), ("M-", "mem")],
    [("AC", "clear"), ("back", "fn"), ("%", "fn"), ("÷", "op")],
    [("7", "key"), ("8", "key"), ("9", "key"), ("×", "op")],
    [("4", "key"), ("5", "key"), ("6", "key"), ("−", "op")],
    [("1", "key"), ("2", "key"), ("3", "key"), ("+", "op")],
    [("±", "key"), ("0", "key"), (".", "key"), ("=", "eq")],
]
SCI_ROWS = [
    [("inv", "mem"), ("ans", "mem"), ("mod", "mem")],
    [("sin", "sci"), ("cos", "sci"), ("tan", "sci")],
    [("ln", "sci"), ("log", "sci"), ("pi", "sci")],
    [("sqrt", "sci"), ("sq", "sci"), ("pow", "sci")],
    [("(", "sci"), (")", "sci"), ("fact", "sci")],
    [("e", "sci"), ("inv_x", "sci"), ("abs", "sci")],
]
LABELS = {
    "back": "⌫", "M-": "M−", "inv": "2nd", "ans": "Ans", "mod": "mod", "sin": "sin", "cos": "cos",
    "tan": "tan", "ln": "ln", "log": "log", "pi": "π", "sqrt": "√", "sq": "x²", "pow": "xʸ",
    "fact": "n!", "e": "e", "inv_x": "1/x", "abs": "|x|",
}
INV_LABELS = {"sin": "sin⁻¹", "cos": "cos⁻¹", "tan": "tan⁻¹", "ln": "eˣ", "log": "10ˣ", "sqrt": "∛", "sq": "x³"}

ACTIONS = {
    **{d: ("digit", d) for d in "0123456789."},
    "+": ("op", "+"), "−": ("op", "−"), "×": ("op", "×"), "÷": ("op", "÷"), "pow": ("op", "^"),
    "=": ("eq", None), "AC": ("clear", None), "back": ("back", None), "±": ("sign", None),
    "%": ("post", "%"), "fact": ("post", "!"), "sq": ("post", "^2"),
    "(": ("ins", "("), ")": ("ins", ")"), "pi": ("ins", "π"), "e": ("ins", "e"), "ans": ("ins", "Ans"),
    "mod": ("ins", "mod("), "sin": ("ins", "sin("), "cos": ("ins", "cos("), "tan": ("ins", "tan("),
    "ln": ("ins", "ln("), "log": ("ins", "log("), "sqrt": ("ins", "√("), "inv_x": ("ins", "1÷("),
    "abs": ("ins", "abs("),
    "MC": ("mem", "C"), "MR": ("mem", "R"), "M+": ("mem", "+"), "M-": ("mem", "-"),
    "inv": ("inv", None),
}
INV_ACTIONS = {
    "sin": ("ins", "asin("), "cos": ("ins", "acos("), "tan": ("ins", "atan("),
    "ln": ("ins", "e^("), "log": ("ins", "10^("), "sqrt": ("ins", "∛("), "sq": ("post", "^3"),
}
KEYMAP = {**{d: d for d in "0123456789"}, ".": ".", "+": "+", "-": "−", "*": "×", "/": "÷", "^": "pow",
          "(": "(", ")": ")", "%": "%", "!": "fact", "=": "="}

OPERATORS = "+−×÷^"
PLAIN_NUMBER = re.compile(r"−?[\d.]+")
TOKEN_TAIL = re.compile(r"(?:[a-z]+\(|Ans|1÷\(|10\^\(|e\^\(|[√∛]\()$")
NEG_WRAPPED = re.compile(r"\(−([\d.]+)\)$")
TRAILING_NUMBER = re.compile(r"[\d.]+$")

SCI_EXTRA_WIDTH, HISTORY_WIDTH = 320, HistoryPanel.WIDTH


# --------------------------------------------------------------------------- #
# Application
# --------------------------------------------------------------------------- #
class App:
    def __init__(self, root: tk.Tk, scientific: bool = True):
        init_theme()
        self.root = root
        self.calc = Calculator()
        self.sci, self.inv, self.show_history = scientific, False, False
        self.expr, self.after_eq, self.last_result, self._preview, self._preview_raw = "", False, "", "0", "0"
        self.history: list[tuple[str, str]] = []
        self.labels = {k: LABELS.get(k, k) for rows in (BASIC_ROWS, SCI_ROWS) for row in rows for k, _ in row}

        root.title("Calculator")
        root.configure(bg=BG)
        width = 400 + (SCI_EXTRA_WIDTH if scientific else 0)
        root.geometry(f"{width}x700+{(root.winfo_screenwidth() - width) // 2}+{max(0, (root.winfo_screenheight() - 700) // 2)}")
        root.minsize(380, 600)

        self.main = tk.Frame(root, bg=BG)
        self.main.pack(side="left", fill="both", expand=True)
        self.toolbar = ButtonBoard(self.main, self._toolbar_layout, self.on_toolbar, height=56)
        self.toolbar.pack(fill="x")
        self.display = Display(self.main, height=170)
        self.display.pack(fill="x")
        self.keypad = ButtonBoard(self.main, self._keypad_layout, self.press)
        self.keypad.pack(fill="both", expand=True)
        self.panel = HistoryPanel(root, self.recall, self.clear_history)

        root.bind("<Key>", self.on_key)
        for seq in ("<Control-c>", "<Command-c>"):
            root.bind(seq, lambda e: self.copy())
        for seq in ("<Control-v>", "<Command-v>"):
            root.bind(seq, lambda e: self.paste())
        self.refresh()

    # -- layouts ------------------------------------------------------------ #
    def _toolbar_layout(self, w, h):
        ch, y1, x = 34, (h - 34) / 2, PAD
        specs = [
            ("history", "History", "chip_on" if self.show_history else "chip", x, y1, x + 96, y1 + ch, 14),
            ("sci", "Scientific", "chip_on" if self.sci else "chip", x + 104, y1, x + 222, y1 + ch, 14),
            ("angle", self.calc.angle_mode, "chip", w - PAD - 72, y1, w - PAD, y1 + ch, 14),
        ]
        return specs

    def _keypad_layout(self, w, h):
        gap = 10
        cols, offset = (7, 3) if self.sci else (4, 0)
        weights = (0.55, 1, 1, 1, 1, 1)
        cw = (w - 2 * PAD - gap * (cols - 1)) / cols
        unit = (h - 2 * PAD - gap * 5) / sum(weights)
        rows, y = [], PAD
        for wt in weights:
            rows.append((y, y + unit * wt))
            y += unit * wt + gap
        specs = []

        def add(grid, col_offset):
            for r, row in enumerate(grid):
                for c, (key, style) in enumerate(row):
                    x1 = PAD + (c + col_offset) * (cw + gap)
                    y1, y2 = rows[r]
                    style = "mem_on" if key == "inv" and self.inv else style
                    px = int(min(cw, y2 - y1) * STYLES[style]["scale"])
                    specs.append((key, self.labels[key], style, x1, y1, x1 + cw, y2, px))

        add(BASIC_ROWS, offset)
        if self.sci:
            add(SCI_ROWS, 0)
        return specs

    # -- toolbar ------------------------------------------------------------ #
    def on_toolbar(self, key: str) -> None:
        if key == "angle":
            self.calc.angle_mode = "RAD" if self.calc.angle_mode == "DEG" else "DEG"
            self.toolbar.set_label("angle", self.calc.angle_mode)
            self.refresh()
        elif key == "sci":
            self.sci = not self.sci
            self.toolbar.set_style("sci", "chip_on" if self.sci else "chip")
            self._resize(SCI_EXTRA_WIDTH if self.sci else -SCI_EXTRA_WIDTH)
        elif key == "history":
            self.show_history = not self.show_history
            self.toolbar.set_style("history", "chip_on" if self.show_history else "chip")
            if self.show_history:
                self.panel.pack(side="right", fill="y", before=self.main)
                self.panel.list.set_entries(self.history)
            else:
                self.panel.pack_forget()
            self._resize(HISTORY_WIDTH if self.show_history else -HISTORY_WIDTH)

    def _resize(self, delta: int) -> None:
        self.root.update_idletasks()
        if self.root.state() == "normal":
            width = max(380, self.root.winfo_width() + delta)
            x = max(0, min(self.root.winfo_x(), self.root.winfo_screenwidth() - width))
            self.root.geometry(f"{width}x{self.root.winfo_height()}+{x}+{self.root.winfo_y()}")
        self.root.update_idletasks()
        self.keypad.relayout()

    # -- input -------------------------------------------------------------- #
    def press(self, key: str) -> None:
        action = (INV_ACTIONS if self.inv and key in INV_ACTIONS else ACTIONS).get(key)
        if action:
            self.dispatch(*action)

    def press_from_keyboard(self, key: str) -> None:
        self.keypad.flash(key)
        self.press(key)

    def on_key(self, e) -> None:
        if e.state & 0x4:  # Ctrl combos are handled by their own bindings
            return
        ks, ch = e.keysym, e.char
        if ks in ("Return", "KP_Enter"):
            self.press_from_keyboard("=")
        elif ks == "BackSpace":
            self.press_from_keyboard("back")
        elif ks in ("Escape", "Delete"):
            self.press_from_keyboard("AC")
        elif ch in KEYMAP:
            self.press_from_keyboard(KEYMAP[ch])
        elif ch == ",":
            self.dispatch("ins", ",")
        elif ch and ch.isascii() and ch.isalpha():
            self.dispatch("ins", ch.lower())

    def dispatch(self, kind: str, payload) -> None:
        getattr(self, "_do_" + kind)(payload)
        if kind not in ("eq", "mem"):
            self.refresh()
        elif kind == "mem":
            self.display.set_badges(self.calc.memory != 0, self.inv)

    def _fresh(self) -> None:
        if self.after_eq:
            self.expr, self.after_eq = "", False

    def _continue_from_result(self) -> None:
        if self.after_eq:
            self.expr, self.after_eq = self.last_result.replace("-", "−"), False

    def _do_digit(self, ch: str) -> None:
        self._fresh()
        tail = TRAILING_NUMBER.search(self.expr)
        number = tail.group() if tail else ""
        if ch == ".":
            if "." in number:
                return
            if not number:
                ch = "0."
        elif number == "0":
            self.expr = self.expr[:-1]
        self.expr += ch

    def _do_op(self, op: str) -> None:
        self._continue_from_result()
        if not self.expr:
            self.expr = "−" if op == "−" else "0"
            if op != "−":
                self.expr += op
            return
        last = self.expr[-1]
        if last in OPERATORS:
            if op == "−" and last in "×÷^":
                self.expr += op
            else:
                self.expr = self.expr[:-1] + op
        elif last == "(" and op != "−":
            return
        else:
            self.expr += op

    def _do_ins(self, text: str) -> None:
        self._fresh()
        self.expr += text

    def _do_post(self, text: str) -> None:
        self._continue_from_result()
        if self.expr and self.expr[-1] not in OPERATORS + "(":
            self.expr += text

    def _do_clear(self, _=None) -> None:
        self.expr, self.after_eq, self._preview, self._preview_raw = "", False, "0", "0"

    def _do_back(self, _=None) -> None:
        if self.after_eq:
            self._do_clear()
            return
        m = TOKEN_TAIL.search(self.expr)
        self.expr = self.expr[: m.start()] if m else self.expr[:-1]

    def _do_sign(self, _=None) -> None:
        self._continue_from_result()
        e = self.expr
        wrapped = NEG_WRAPPED.search(e)
        if not e:
            self.expr = "−"
        elif wrapped:
            self.expr = e[: wrapped.start()] + wrapped.group(1)
        elif e.startswith("−") and PLAIN_NUMBER.fullmatch(e):
            self.expr = e[1:]
        else:
            tail = TRAILING_NUMBER.search(e)
            if tail:
                s = tail.start()
                if s == 0:
                    self.expr = "−" + e
                else:
                    self.expr = e[:s] + "(−" + tail.group() + ")"

    def _do_inv(self, _=None) -> None:
        self.inv = not self.inv
        for key, label in INV_LABELS.items():
            self.labels[key] = label if self.inv else LABELS.get(key, key)
            self.keypad.set_label(key, self.labels[key])
        self.keypad.set_style("inv", "mem_on" if self.inv else "mem")
        self.display.set_badges(self.calc.memory != 0, self.inv)

    def _do_mem(self, op: str) -> None:
        if op == "C":
            self.calc.memory_clear()
        elif op == "R":
            value = format_number(self.calc.memory).replace("-", "−")
            self._fresh()
            self.expr += f"({value})" if value.startswith("−") else value
            self.refresh()
        else:
            value = self._current_value()
            if value is None:
                return
            (self.calc.memory_add if op == "+" else self.calc.memory_subtract)(value)
        self.display.set_badges(self.calc.memory != 0, self.inv)

    def _current_value(self):
        if self.after_eq:
            return self.calc.ans
        if not self.expr:
            return 0
        try:
            return self.calc.evaluate(self.expr)
        except CalcError:
            return None

    def _do_eq(self, _=None) -> None:
        if not self.expr:
            return
        shown = self._closed(self.expr)
        try:
            result = self.calc.calculate(self.expr)
        except CalcError as err:
            self.display.render(shown, str(err), CORAL, error=True)
            self.display.shake()
            return
        self.history.insert(0, (shown, result))
        del self.history[200:]
        if self.show_history:
            self.panel.list.set_entries(self.history)
        self.last_result, self.after_eq, self._preview, self._preview_raw = result, True, group_digits(result), result
        self.display.render(shown + " =", self._preview, TEXT, animate=True)
        t_us = getattr(self.calc, "last_execution_time_us", 0.0)
        time_str = f"{t_us:.1f} µs" if t_us < 1000 else f"{t_us/1000:.2f} ms"
        self.display.toast(time_str)

    @staticmethod
    def _closed(expr: str) -> str:
        return expr + ")" * max(0, expr.count("(") - expr.count(")"))

    # -- display ------------------------------------------------------------ #
    def refresh(self) -> None:
        e = self.expr
        if not e:
            self.display.render("", "0")
        elif PLAIN_NUMBER.fullmatch(e):
            self.display.render("", group_digits(e))
        else:
            try:
                self._preview_raw = format_number(self.calc.evaluate(e))
                self._preview = group_digits(self._preview_raw)
            except CalcError:
                pass  # keep the last good preview while the expression is incomplete
            self.display.render(self._closed(e), self._preview, PREVIEW)
        self.display.set_badges(self.calc.memory != 0, self.inv)

    # -- history / clipboard ------------------------------------------------ #
    def recall(self, expr: str, result: str) -> None:
        self.expr, self.after_eq = result.replace("-", "−"), False
        self.refresh()

    def clear_history(self) -> None:
        self.history.clear()
        self.panel.list.set_entries(self.history)

    def copy(self) -> None:
        text = self.last_result if self.after_eq else self._preview_raw
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.display.toast("Copied")

    def paste(self) -> None:
        try:
            raw = self.root.clipboard_get()
        except tk.TclError:
            return
        raw = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", raw)
        clean = re.sub(r"[^0-9a-zA-Z.+\-*/^%!(),×÷−π√∛]", "", raw).replace("-", "−").replace("*", "×").replace("/", "÷")
        if clean:
            self._fresh()
            self.expr = (self.expr + clean)[:400]
            self.refresh()


def run(scientific: bool = True) -> None:
    if sys.platform == "win32":  # crisp text on high-DPI displays
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    App(root, scientific)
    root.mainloop()
