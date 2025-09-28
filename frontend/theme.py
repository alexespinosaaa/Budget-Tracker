# frontend/theme.py

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtGui import QLinearGradient, QRadialGradient, QColor, QPainter
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QWidget, QApplication


# =========================
# Theme model & registry
# =========================

@dataclass(frozen=True)
class Theme:
    """
    A compact theme spec. Keep the API small so we can easily add new themes later.
    """
    id:    int                 # integer persisted in DB
    key:   str                 # programmatic key (stable string)
    label: str                 # human readable name for Settings combobox
    variant: str               # "dark" | "light" (affects QSS base surfaces)
    # palette tokens
    PLUM: QColor
    INDIGO: QColor
    NAVY: QColor
    MAGENTA: QColor           # primary accent (used for 'checked' chips/focus ring)
    ACCENT_RED: QColor
    ACCENT_BLUE: QColor
    TEXT: str
    TEXT_SECONDARY: str
    # background glow / vignette strengths
    orb_magenta_alpha: int = 170
    orb_blue_alpha: int = 110
    vignette_alpha: int = 48


# -------- Built-in themes --------
# 0 — Midnight Glass (current default / original)
MIDNIGHT_GLASS = Theme(
    id=0,
    key="midnight_glass",
    label="Midnight Glass",
    variant="dark",
    PLUM=QColor("#1A0D1F"),
    INDIGO=QColor("#1E2340"),
    NAVY=QColor("#0E1A2A"),
    MAGENTA=QColor("#B91D73"),
    ACCENT_RED=QColor("#E53935"),
    ACCENT_BLUE=QColor("#2F6BCE"),
    TEXT="#FFFFFF",
    TEXT_SECONDARY="#B7B9BE",
    orb_magenta_alpha=170,
    orb_blue_alpha=110,
    vignette_alpha=48,
)

# 1 — Light Mist (soft, light UI)
LIGHT_MIST = Theme(
    id=1,
    key="light_mist",
    label="Light Mist",
    variant="light",
    PLUM=QColor("#EAEAF2"),
    INDIGO=QColor("#DDE3F2"),
    NAVY=QColor("#CCD6E8"),
    MAGENTA=QColor("#9C27B0"),
    ACCENT_RED=QColor("#D32F2F"),
    ACCENT_BLUE=QColor("#1976D2"),
    TEXT="#0E1220",
    TEXT_SECONDARY="#4B5563",
    orb_magenta_alpha=80,
    orb_blue_alpha=70,
    vignette_alpha=24,
)

# 2 — Autumn (warm browns/orange accent)
AUTUMN = Theme(
    id=2,
    key="autumn",
    label="Autumn",
    variant="dark",
    PLUM=QColor("#2B1B14"),
    INDIGO=QColor("#4A2C1B"),
    NAVY=QColor("#1A0F0A"),
    MAGENTA=QColor("#FF7A59"),   # warm pumpkin-ish accent
    ACCENT_RED=QColor("#C04B32"),
    ACCENT_BLUE=QColor("#1F6F8B"),
    TEXT="#FDFCFB",
    TEXT_SECONDARY="#E6D5C3",
    orb_magenta_alpha=140,
    orb_blue_alpha=90,
    vignette_alpha=56,
)

# 3 — Nord (cool nordic palette)
NORD = Theme(
    id=3,
    key="nord",
    label="Nord",
    variant="dark",
    PLUM=QColor("#2E3440"),
    INDIGO=QColor("#3B4252"),
    NAVY=QColor("#4C566A"),
    MAGENTA=QColor("#88C0D0"),   # cyan-ish nord accent
    ACCENT_RED=QColor("#BF616A"),
    ACCENT_BLUE=QColor("#81A1C1"),
    TEXT="#ECEFF4",
    TEXT_SECONDARY="#D8DEE9",
    orb_magenta_alpha=125,
    orb_blue_alpha=100,
    vignette_alpha=54,
)

# 4 — Desert (sandy, warm neutrals)
DESERT = Theme(
    id=4,
    key="desert",
    label="Desert",
    variant="dark",
    PLUM=QColor("#3E2C1C"),
    INDIGO=QColor("#60492C"),
    NAVY=QColor("#7E5A3C"),
    MAGENTA=QColor("#D4A373"),   # sand/amber accent
    ACCENT_RED=QColor("#B85C38"),
    ACCENT_BLUE=QColor("#4A90A4"),
    TEXT="#FDF8F4",
    TEXT_SECONDARY="#E1D7C6",
    orb_magenta_alpha=130,
    orb_blue_alpha=85,
    vignette_alpha=50,
)

# 5 — Forest (deep greens with teal accent)
FOREST = Theme(
    id=5,
    key="forest",
    label="Forest",
    variant="dark",
    PLUM=QColor("#0B1F16"),
    INDIGO=QColor("#123524"),
    NAVY=QColor("#0A2A1A"),
    MAGENTA=QColor("#34D399"),   # spring/emerald accent
    ACCENT_RED=QColor("#E57373"),
    ACCENT_BLUE=QColor("#1FA3A3"),
    TEXT="#ECF8F1",
    TEXT_SECONDARY="#B7D1C3",
    orb_magenta_alpha=130,
    orb_blue_alpha=90,
    vignette_alpha=58,
)

# 6 — OLED Black (pure black base, neon accents)
OLED_BLACK = Theme(
    id=6,
    key="oled_black",
    label="OLED Black",
    variant="dark",
    PLUM=QColor("#000000"),
    INDIGO=QColor("#000000"),
    NAVY=QColor("#000000"),
    MAGENTA=QColor("#FF3B81"),
    ACCENT_RED=QColor("#FF4D4D"),
    ACCENT_BLUE=QColor("#4DA3FF"),
    TEXT="#FFFFFF",
    TEXT_SECONDARY="#B7B9BE",
    orb_magenta_alpha=120,
    orb_blue_alpha=90,
    vignette_alpha=64,
)

# 7 — Monochrome Slate (grayscale, subtle accent)
MONOCHROME_SLATE = Theme(
    id=7,
    key="monochrome_slate",
    label="Monochrome Slate",
    variant="dark",
    PLUM=QColor("#111214"),
    INDIGO=QColor("#1B1D22"),
    NAVY=QColor("#0E0F13"),
    MAGENTA=QColor("#9CA3AF"),   # neutral accent
    ACCENT_RED=QColor("#9CA3AF"),
    ACCENT_BLUE=QColor("#9CA3AF"),
    TEXT="#E5E7EB",
    TEXT_SECONDARY="#9CA3AF",
    orb_magenta_alpha=110,
    orb_blue_alpha=80,
    vignette_alpha=52,
)

# ----- New themes (IDs 8–11) -----

# 8 — Sunset (warm, moody, peach/orange accents)
SUNSET = Theme(
    id=8,
    key="sunset",
    label="Sunset",
    variant="dark",
    PLUM=QColor("#2B1421"),
    INDIGO=QColor("#402335"),
    NAVY=QColor("#1A0E15"),
    MAGENTA=QColor("#FF6B6B"),
    ACCENT_RED=QColor("#FF3D3D"),
    ACCENT_BLUE=QColor("#FFB86B"),
    TEXT="#FFEFEF",
    TEXT_SECONDARY="#E7C9C9",
    orb_magenta_alpha=150,
    orb_blue_alpha=95,
    vignette_alpha=52,
)

# 9 — Icy Light Blue (crisp light UI for winter)
ICY_LIGHT_BLUE = Theme(
    id=9,
    key="icy_light_blue",
    label="Icy Light Blue",
    variant="light",
    PLUM=QColor("#E8F4FF"),
    INDIGO=QColor("#D6E9FF"),
    NAVY=QColor("#C7E0FF"),
    MAGENTA=QColor("#3BA7FF"),
    ACCENT_RED=QColor("#6EA8FE"),
    ACCENT_BLUE=QColor("#5CC8FF"),
    TEXT="#0E1220",
    TEXT_SECONDARY="#4B5563",
    orb_magenta_alpha=90,
    orb_blue_alpha=80,
    vignette_alpha=26,
)

# 10 — Black & White (high-contrast, no color)
BLACK_WHITE = Theme(
    id=10,
    key="black_white",
    label="Black & White",
    variant="dark",
    PLUM=QColor("#000000"),
    INDIGO=QColor("#000000"),
    NAVY=QColor("#000000"),
    MAGENTA=QColor("#FFFFFF"),
    ACCENT_RED=QColor("#FFFFFF"),
    ACCENT_BLUE=QColor("#FFFFFF"),
    TEXT="#FFFFFF",
    TEXT_SECONDARY="#CFCFCF",
    orb_magenta_alpha=110,
    orb_blue_alpha=80,
    vignette_alpha=64,
)

# 11 — Winter Lights (deep navy + neon magenta/cyan)
WINTER_LIGHTS = Theme(
    id=11,
    key="winter_lights",
    label="Winter Lights",
    variant="dark",
    PLUM=QColor("#0B1020"),
    INDIGO=QColor("#111A33"),
    NAVY=QColor("#0A0F1F"),
    MAGENTA=QColor("#C77DFF"),
    ACCENT_RED=QColor("#FF5C8A"),
    ACCENT_BLUE=QColor("#74C0FC"),
    TEXT="#EAF6FF",
    TEXT_SECONDARY="#A8C1D8",
    orb_magenta_alpha=140,
    orb_blue_alpha=95,
    vignette_alpha=56,
)

# Registry
_THEMES_BY_ID: Dict[int, Theme] = {
    t.id: t for t in (
        MIDNIGHT_GLASS,
        LIGHT_MIST,
        AUTUMN,
        NORD,
        DESERT,
        FOREST,
        OLED_BLACK,
        MONOCHROME_SLATE,
    )
}
_THEMES_BY_KEY: Dict[str, Theme] = {t.key: t for t in _THEMES_BY_ID.values()}

# Register new themes without altering the original construction logic
_THEMES_BY_ID[SUNSET.id] = SUNSET
_THEMES_BY_ID[ICY_LIGHT_BLUE.id] = ICY_LIGHT_BLUE
_THEMES_BY_ID[BLACK_WHITE.id] = BLACK_WHITE
_THEMES_BY_ID[WINTER_LIGHTS.id] = WINTER_LIGHTS

_THEMES_BY_KEY.update({
    SUNSET.key: SUNSET,
    ICY_LIGHT_BLUE.key: ICY_LIGHT_BLUE,
    BLACK_WHITE.key: BLACK_WHITE,
    WINTER_LIGHTS.key: WINTER_LIGHTS,
})

# Default theme key/id (used if DB has nothing yet)
_DEFAULT_THEME_ID: int = MIDNIGHT_GLASS.id

# Global runtime selection
_current_theme_id: int = _DEFAULT_THEME_ID
_theme_changed_callbacks: List[Callable[[Theme], None]] = []


# =========================
# QSS builder
# =========================

def _build_qss(theme: Theme) -> str:
    """
    Build the global application stylesheet using the theme.
    Differences between dark/light variants are handled here.
    """
    TEXT = theme.TEXT
    TEXT_SECONDARY = theme.TEXT_SECONDARY
    MAGENTA = theme.MAGENTA

    if theme.variant == "light":
        # Light surfaces: subtle dark borders and translucent white backgrounds
        base = f"""
        QWidget {{
            background: transparent;
            color: {TEXT};
            font-family: Inter, "Segoe UI", "SF Pro Display", "Noto Sans", Arial;
            font-size: 14px;
        }}

        #Sidebar {{
            background: rgba(0,0,0,0.03);
            border-right: 1px solid rgba(0,0,0,0.08);
        }}

        QPushButton[circle="true"] {{
            background: rgba(0,0,0,0.06);
            border: 1px solid rgba(0,0,0,0.08);
            border-radius: 16px;
        }}
        QPushButton[circle="true"]:hover {{
            background: rgba(0,0,0,0.12);
            border-color: rgba(0,0,0,0.18);
        }}
        QPushButton[circle="true"]:checked {{
            background: rgba({MAGENTA.red()},{MAGENTA.green()},{MAGENTA.blue()},0.20);
            border-color: {MAGENTA.name()};
        }}

        QPushButton[square="true"] {{
            background: rgba(0,0,0,0.06);
            border: 1px solid rgba(0,0,0,0.10);
            border-radius: 8px;
        }}
        QPushButton[square="true"]:hover {{ background: rgba(0,0,0,0.12); }}

        QFrame[kind="glass"] {{
            background: rgba(255,255,255,0.60);
            border: 1px solid rgba(0,0,0,0.08);
            border-radius: 14px;
        }}
        QFrame[kind="glassDeep"] {{
            background: rgba(255,255,255,0.72);
            border: 1px solid rgba(0,0,0,0.10);
            border-radius: 14px;
        }}

        QLabel[muted="true"] {{ color: {TEXT_SECONDARY}; }}
        QLabel[title="true"] {{ font-size: 28px; font-weight: 800; letter-spacing: .2px; }}
        QLabel[value="true"] {{ font-size: 26px; font-weight: 800; }}
        QLabel[kpi="true"]   {{ font-size: 12px; color: {TEXT_SECONDARY}; }}

        QFrame[kind="plot"] {{
            background: rgba(0,0,0,0.03);
            border: 1px solid rgba(0,0,0,0.08);
            border-radius: 10px;
        }}
        """
    else:
        # Dark variant (original look)
        base = f"""
        QWidget {{
            background: transparent;
            color: {TEXT};
            font-family: Inter, "Segoe UI", "SF Pro Display", "Noto Sans", Arial;
            font-size: 14px;
        }}

        #Sidebar {{
            background: rgba(255,255,255,0.02);
            border-right: 1px solid rgba(255,255,255,0.06);
        }}

        QPushButton[circle="true"] {{
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 16px;
        }}
        QPushButton[circle="true"]:hover {{
            background: rgba(255,255,255,0.12);
            border-color: rgba(255,255,255,0.18);
        }}
        QPushButton[circle="true"]:checked {{
            background: rgba({MAGENTA.red()},{MAGENTA.green()},{MAGENTA.blue()},0.35);
            border-color: {MAGENTA.name()};
        }}

        QPushButton[square="true"] {{
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 8px;
        }}
        QPushButton[square="true"]:hover {{ background: rgba(255,255,255,0.12); }}

        QFrame[kind="glass"] {{
            background: rgba(8,10,18,0.58);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px;
        }}
        QFrame[kind="glassDeep"] {{
            background: rgba(6,8,14,0.66);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 14px;
        }}

        QLabel[muted="true"] {{ color: {TEXT_SECONDARY}; }}
        QLabel[title="true"] {{ font-size: 28px; font-weight: 800; letter-spacing: .2px; }}
        QLabel[value="true"] {{ font-size: 26px; font-weight: 800; }}
        QLabel[kpi="true"]   {{ font-size: 12px; color: {TEXT_SECONDARY}; }}

        QFrame[kind="plot"] {{
            background: rgba(255,255,255,0.02);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 10px;
        }}
        """
    return base


# =========================
# Background painter
# =========================

class BackgroundCanvas(QWidget):
    """
    Paints the window background using the active theme.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)

    def paintEvent(self, event):
        theme = _THEMES_BY_ID[_current_theme_id]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()

        # Base gradient
        g = QLinearGradient(0, 0, w, h)
        g.setColorAt(0.0, theme.PLUM)
        g.setColorAt(0.55, theme.INDIGO)
        g.setColorAt(1.0, theme.NAVY)
        p.fillRect(self.rect(), g)

        # Left accent orb
        orb1 = QRadialGradient(QPointF(w * 0.25, h * 0.45), min(w, h) * 0.6)
        orb1.setColorAt(
            0.0,
            QColor(theme.MAGENTA.red(), theme.MAGENTA.green(), theme.MAGENTA.blue(), theme.orb_magenta_alpha),
        )
        orb1.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(self.rect(), orb1)

        # Right cool orb
        orb2 = QRadialGradient(QPointF(w * 0.85, h * 0.30), min(w, h) * 0.7)
        orb2.setColorAt(
            0.0,
            QColor(theme.ACCENT_BLUE.red(), theme.ACCENT_BLUE.green(), theme.ACCENT_BLUE.blue(), theme.orb_blue_alpha),
        )
        orb2.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(self.rect(), orb2)

        # Vignette
        v = QRadialGradient(QPointF(w * 0.5, h * 0.5), max(w, h) * 0.75)
        v.setColorAt(0.85, QColor(0, 0, 0, 0))
        v.setColorAt(1.0, QColor(0, 0, 0, theme.vignette_alpha))
        p.fillRect(self.rect(), v)


# =========================
# Public API
# =========================

def list_theme_options() -> List[Tuple[int, str]]:
    """
    Return a simple [(id, label), ...] list for your Settings combobox.
    Persist only the integer id in the DB.
    """
    return [(t.id, t.label) for t in sorted(_THEMES_BY_ID.values(), key=lambda x: x.id)]


def theme_from_id(theme_id: int) -> Theme:
    """Resolve a theme id to a Theme object, falling back to default if needed."""
    return _THEMES_BY_ID.get(theme_id, _THEMES_BY_ID[_DEFAULT_THEME_ID])


def theme_from_key(key: str) -> Theme:
    """Resolve a theme key to a Theme object, falling back to default if needed."""
    return _THEMES_BY_KEY.get(key, _THEMES_BY_ID[_DEFAULT_THEME_ID])


def current_theme() -> Theme:
    return theme_from_id(_current_theme_id)


def current_theme_id() -> int:
    return _current_theme_id


def current_theme_key() -> str:
    return current_theme().key


def apply_app_theme(theme_id: Optional[int] = None) -> None:
    """
    Apply a theme app-wide. If theme_id is None, read it from the profile.
    Supports both 'theme_id' and legacy 'themes' integer columns.
    """
    global _current_theme_id

    resolved_id: Optional[int] = None

    if theme_id is not None:
        resolved_id = int(theme_id)
    else:
        # Correct import path for your project
        try:
            from backend.crud.profile import get_current_profile  # type: ignore
        except Exception:
            get_current_profile = None  # type: ignore

        if get_current_profile:
            try:
                profile = get_current_profile() or {}
                # Prefer 'theme_id', fall back to 'themes', then 'theme'
                pid = (
                    profile.get("theme_id",
                        profile.get("themes",
                            profile.get("theme")
                        )
                    )
                )
                if isinstance(pid, int):
                    resolved_id = pid
            except Exception:
                resolved_id = None

    if resolved_id is None:
        resolved_id = _DEFAULT_THEME_ID

    _current_theme_id = resolved_id
    theme = theme_from_id(_current_theme_id)

    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(_build_qss(theme))

    # Notify subscribers (widgets that repaint on theme change)
    for cb in list(_theme_changed_callbacks):
        try:
            cb(theme)
        except Exception:
            pass


def on_theme_changed(callback: Callable[[Theme], None]) -> None:
    """
    Optional: subscribe widgets that need a repaint or to recalc cached colors.
    Most Qt widgets will restyle automatically via stylesheet, so you might not need this.
    """
    _theme_changed_callbacks.append(callback)


# Backwards-compat shim (so existing calls still work)
def build_qss() -> str:
    """Deprecated: prefer apply_app_theme(...) which sets the app stylesheet directly."""
    return _build_qss(current_theme())
