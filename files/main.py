# main.py - CMC Launcher v1.1 (MOD LOADER EDITION)
import os
import sys
import json
import shutil
import subprocess
import time
import urllib.request
import urllib.error
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox, QLabel, QProgressBar, QMessageBox,
    QStackedWidget, QListWidget, QListWidgetItem, QFormLayout, QSpinBox,
    QLineEdit, QFileDialog, QInputDialog, QGraphicsDropShadowEffect, QFrame,
    QTabWidget
)
from PySide6.QtCore import (
    QThread, Signal, Qt, QPropertyAnimation, QEasingCurve,
    QTimer, QRect, QProcess
)
from PySide6.QtGui import QIcon, QFont, QColor
import minecraft_launcher_lib
from pypresence import Presence

# ============================================================================
# PATHS & CONFIGURATION
# ============================================================================

APP_DIR = os.path.dirname(os.path.abspath(__file__))

data_home = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".var/app/com.sedsujim.CMCLauncher/data"))
config_home = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".var/app/com.sedsujim.CMCLauncher/config"))

# Flatpak runtime is read-only under /app, así que use las carpetas de usuario.
ASSETS_DIR   = os.path.join(APP_DIR, "assets") if os.path.isdir(os.path.join(APP_DIR, "assets")) else os.path.join(data_home, "assets")
CONFIG_DIR   = os.path.join(config_home, "CMCLauncher")
PROFILES_DIR = os.path.join(config_home, "CMCLauncher")
LOGS_DIR     = os.path.join(data_home, "CMCLauncher", "logs")
CACHE_DIR    = os.path.join(data_home, "CMCLauncher", "cache")

CONFIG_FILE   = os.path.join(CONFIG_DIR,   "config.json")
PROFILES_FILE = os.path.join(PROFILES_DIR, "profiles.json")

MINECRAFT_DIR     = minecraft_launcher_lib.utils.get_minecraft_directory()
MODS_DIR          = os.path.join(MINECRAFT_DIR, "mods")
DISABLED_MODS_DIR = os.path.join(MODS_DIR, "disabled")

def _ensure_dir(d):
    try:
        os.makedirs(d, exist_ok=True)
    except PermissionError:
        pass

for d in [CONFIG_DIR, PROFILES_DIR, LOGS_DIR, MODS_DIR, DISABLED_MODS_DIR, CACHE_DIR]:
    _ensure_dir(d)

# ============================================================================
# VERSION UTILS
# ============================================================================

def parse_version(version_id: str):
    try:
        parts = version_id.split(".")
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return major, minor, patch
    except Exception:
        return 0, 0, 0


def is_legacy_version(version_id: str) -> bool:
    major, minor, _ = parse_version(version_id)
    return (major == 1 and minor < 13) or major == 0


# ============================================================================
# MOD LOADER APIs
# ============================================================================

class ModLoaderAPI:
    """Fetches available versions for each mod loader from their official APIs."""

    FABRIC_META  = "https://meta.fabricmc.net/v2"
    QUILT_META   = "https://meta.quiltmc.org/v3"
    FORGE_META   = "https://files.minecraftforge.net/net/minecraftforge/forge/maven-metadata.json"
    NEO_META_XML = "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"

    @staticmethod
    def _get_json(url: str, timeout: int = 10):
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())

    # Fabric
    @staticmethod
    def get_fabric_loader_versions(mc_version: str) -> list:
        try:
            data = ModLoaderAPI._get_json(
                f"{ModLoaderAPI.FABRIC_META}/versions/loader/{mc_version}")
            return [e["loader"]["version"] for e in data]
        except Exception:
            return []

    # Quilt
    @staticmethod
    def get_quilt_loader_versions(mc_version: str) -> list:
        try:
            data = ModLoaderAPI._get_json(
                f"{ModLoaderAPI.QUILT_META}/versions/loader/{mc_version}")
            return [e["loader"]["version"] for e in data]
        except Exception:
            return []

    # Forge
    @staticmethod
    def get_forge_versions(mc_version: str) -> list:
        try:
            data = ModLoaderAPI._get_json(ModLoaderAPI.FORGE_META, timeout=15)
            return data.get(mc_version, [])
        except Exception:
            return []

    # NeoForge
    @staticmethod
    def get_neoforge_versions(mc_version: str) -> list:
        try:
            with urllib.request.urlopen(ModLoaderAPI.NEO_META_XML, timeout=15) as r:
                xml = r.read().decode()
            versions = []
            for line in xml.splitlines():
                line = line.strip()
                if line.startswith("<version>") and line.endswith("</version>"):
                    versions.append(line[9:-10])
            _, minor, patch = parse_version(mc_version)
            prefix = f"{minor}.{patch}." if patch else f"{minor}."
            matching = [v for v in versions if v.startswith(prefix)]
            return list(reversed(matching))
        except Exception:
            return []


# ============================================================================
# MOD LOADER INSTALLER THREAD
# ============================================================================

class ModLoaderInstallerThread(QThread):
    status   = Signal(str)
    progress = Signal(int)
    finished = Signal(bool, str)

    def __init__(self, loader: str, mc_version: str, loader_version: str):
        super().__init__()
        self.loader         = loader.lower()
        self.mc_version     = mc_version
        self.loader_version = loader_version

    def _emit(self, text: str, pct: int = -1):
        self.status.emit(text)
        if pct >= 0:
            self.progress.emit(pct)

    def _base_cb(self):
        return {
            "setStatus":   lambda t: self._emit(str(t)),
            "setProgress": lambda v: self.progress.emit(int(float(v))),
        }

    def run(self):
        try:
            dispatch = {
                "fabric":   self._install_fabric,
                "quilt":    self._install_quilt,
                "forge":    self._install_forge,
                "neoforge": self._install_neoforge,
            }
            fn = dispatch.get(self.loader)
            if fn:
                fn()
            else:
                self.finished.emit(False, f"Unknown loader: {self.loader}")
        except Exception as e:
            self.finished.emit(False, str(e))

    # ---------------------------------------------------------------- Fabric
    def _install_fabric(self):
        self._emit("Installing Fabric…", 5)
        try:
            minecraft_launcher_lib.fabric.install_fabric(
                self.mc_version, MINECRAFT_DIR, self.loader_version,
                callback=self._base_cb())
            self.finished.emit(True,
                f"Fabric {self.loader_version} installed for {self.mc_version}")
        except AttributeError:
            self._fabric_fallback()

    def _fabric_fallback(self):
        self._emit("Downloading Fabric profile JSON…", 10)
        pid = f"fabric-loader-{self.loader_version}-{self.mc_version}"
        url = (f"https://meta.fabricmc.net/v2/versions/loader"
               f"/{self.mc_version}/{self.loader_version}/profile/json")
        vdir = os.path.join(MINECRAFT_DIR, "versions", pid)
        os.makedirs(vdir, exist_ok=True)
        urllib.request.urlretrieve(url, os.path.join(vdir, f"{pid}.json"))
        self._emit("Installing base Minecraft…", 40)
        minecraft_launcher_lib.install.install_minecraft_version(
            self.mc_version, MINECRAFT_DIR, callback=self._base_cb())
        self._emit("Fabric ready ✓", 100)
        self.finished.emit(True, f"Fabric {self.loader_version} ready for {self.mc_version}")

    # ----------------------------------------------------------------- Quilt
    def _install_quilt(self):
        self._emit("Installing Quilt…", 5)
        try:
            minecraft_launcher_lib.quilt.install_quilt(
                self.mc_version, MINECRAFT_DIR, self.loader_version,
                callback=self._base_cb())
            self.finished.emit(True,
                f"Quilt {self.loader_version} installed for {self.mc_version}")
        except AttributeError:
            self._quilt_fallback()

    def _quilt_fallback(self):
        self._emit("Downloading Quilt profile JSON…", 10)
        pid = f"quilt-loader-{self.loader_version}-{self.mc_version}"
        url = (f"https://meta.quiltmc.org/v3/versions/loader"
               f"/{self.mc_version}/{self.loader_version}/profile/json")
        vdir = os.path.join(MINECRAFT_DIR, "versions", pid)
        os.makedirs(vdir, exist_ok=True)
        urllib.request.urlretrieve(url, os.path.join(vdir, f"{pid}.json"))
        self._emit("Installing base Minecraft…", 40)
        minecraft_launcher_lib.install.install_minecraft_version(
            self.mc_version, MINECRAFT_DIR, callback=self._base_cb())
        self._emit("Quilt ready ✓", 100)
        self.finished.emit(True, f"Quilt {self.loader_version} ready for {self.mc_version}")

    # ----------------------------------------------------------------- Forge
    def _install_forge(self):
        self._emit("Installing Forge (may take a while)…", 5)
        try:
            minecraft_launcher_lib.forge.install_forge_version(
                self.loader_version, MINECRAFT_DIR, callback=self._base_cb())
            self.finished.emit(True, f"Forge {self.loader_version} installed")
        except AttributeError:
            self._forge_fallback()

    def _forge_fallback(self):
        fv  = self.loader_version
        url = (f"https://files.minecraftforge.net/net/minecraftforge/forge"
               f"/{fv}/forge-{fv}-installer.jar")
        jar = os.path.join(CACHE_DIR, f"forge-{fv}-installer.jar")
        self._emit("Downloading Forge installer…", 10)
        urllib.request.urlretrieve(url, jar)
        self._emit("Running Forge installer…", 40)
        res = subprocess.run(
            ["java", "-jar", jar, "--installClient", MINECRAFT_DIR],
            capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(res.stderr[-500:] or "Forge installer failed")
        self._emit("Forge ready ✓", 100)
        self.finished.emit(True, f"Forge {fv} installed")

    # -------------------------------------------------------------- NeoForge
    def _install_neoforge(self):
        self._emit("Installing NeoForge (may take a while)…", 5)
        try:
            minecraft_launcher_lib.neoforge.install_neoforge_version(
                self.loader_version, MINECRAFT_DIR, callback=self._base_cb())
            self.finished.emit(True, f"NeoForge {self.loader_version} installed")
        except AttributeError:
            self._neoforge_fallback()

    def _neoforge_fallback(self):
        ver = self.loader_version
        url = (f"https://maven.neoforged.net/releases/net/neoforged/neoforge"
               f"/{ver}/neoforge-{ver}-installer.jar")
        jar = os.path.join(CACHE_DIR, f"neoforge-{ver}-installer.jar")
        self._emit("Downloading NeoForge installer…", 10)
        urllib.request.urlretrieve(url, jar)
        self._emit("Running NeoForge installer…", 40)
        res = subprocess.run(
            ["java", "-jar", jar, "--installClient", MINECRAFT_DIR],
            capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(res.stderr[-500:] or "NeoForge installer failed")
        self._emit("NeoForge ready ✓", 100)
        self.finished.emit(True, f"NeoForge {ver} installed")


# ============================================================================
# LOADER VERSION FETCH THREAD
# ============================================================================

class LoaderVersionFetchThread(QThread):
    result = Signal(str, list)

    def __init__(self, loader: str, mc_version: str):
        super().__init__()
        self.loader     = loader
        self.mc_version = mc_version

    def run(self):
        versions = []
        try:
            fn = {
                "fabric":   ModLoaderAPI.get_fabric_loader_versions,
                "quilt":    ModLoaderAPI.get_quilt_loader_versions,
                "forge":    ModLoaderAPI.get_forge_versions,
                "neoforge": ModLoaderAPI.get_neoforge_versions,
            }.get(self.loader)
            if fn:
                versions = fn(self.mc_version)
        except Exception:
            pass
        self.result.emit(self.loader, versions)


# ============================================================================
# PERFORMANCE OPTIMIZER
# ============================================================================

class LaunchOptimizer:
    @staticmethod
    def get_optimal_jvm_args(ram_gb: int, version: str) -> list:
        xms = max(256, ram_gb * 512)
        xmx = ram_gb * 1024
        args = [f"-Xms{xms}M", f"-Xmx{xmx}M"]
        if not is_legacy_version(version):
            args += [
                "-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled",
                "-XX:MaxGCPauseMillis=200", "-XX:+UnlockExperimentalVMOptions",
                "-XX:+DisableExplicitGC", "-XX:+AlwaysPreTouch",
                "-XX:G1NewSizePercent=30", "-XX:G1MaxNewSizePercent=40",
                "-XX:G1HeapRegionSize=8M", "-XX:G1ReservePercent=20",
                "-XX:G1HeapWastePercent=5", "-XX:G1MixedGCCountTarget=4",
                "-XX:InitiatingHeapOccupancyPercent=15",
                "-XX:G1MixedGCLiveThresholdPercent=90",
                "-XX:G1RSetUpdatingPauseTimePercent=5",
                "-XX:SurvivorRatio=32", "-XX:+PerfDisableSharedMem",
                "-XX:MaxTenuringThreshold=1",
            ]
        else:
            args += [
                "-XX:+UseG1GC", "-XX:+UnlockExperimentalVMOptions",
                "-XX:MaxGCPauseMillis=50", "-XX:+DisableExplicitGC",
                "-XX:TargetSurvivorRatio=90", "-XX:G1NewSizePercent=50",
                "-XX:G1MaxNewSizePercent=80",
                "-XX:InitiatingHeapOccupancyPercent=10",
            ]
        return args


# ============================================================================
# DISCORD RPC
# ============================================================================

class DiscordRPC:
    def __init__(self, client_id):
        self.rpc = None
        if client_id:
            try:
                self.rpc = Presence(client_id)
                self.rpc.connect()
            except Exception:
                pass

    def _safe(self, **kw):
        if not self.rpc:
            return
        try:
            self.rpc.update(**kw)
        except Exception:
            pass

    def update_launcher(self, text):
        self._safe(details="In launcher", state=text,
                   large_image="cmc", large_text="CMC Launcher")

    def update_downloading(self, version, pct):
        self._safe(details=f"Downloading {version}", state=f"{pct}% complete",
                   large_image="cmc")

    def update_playing(self, profile, version, mode, server=None):
        state = f"{version} · {mode}" + (f" — {server}" if server else "")
        self._safe(details=profile, state=state, large_image="cmc",
                   large_text="CMC Launcher", start=int(time.time()))

    def clear(self):
        if not self.rpc:
            return
        try:
            self.rpc.clear()
            self.rpc.close()
        except Exception:
            pass


# ============================================================================
# INSTALLER THREAD (base MC)
# ============================================================================

class InstallerThread(QThread):
    progress = Signal(int)
    status   = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, version):
        super().__init__()
        self.version = version

    def run(self):
        cb = {
            "setStatus":          lambda t: self.status.emit(str(t)),
            "setProgress":        lambda v: self.progress.emit(int(float(v))),
            "setSubStatus":       lambda t: self.status.emit(str(t)),
            "setOverallProgress": lambda v: self.progress.emit(int(float(v))),
        }
        try:
            minecraft_launcher_lib.install.install_minecraft_version(
                self.version, MINECRAFT_DIR, callback=cb)
            self.finished.emit(True, self.version)
        except Exception as e:
            self.status.emit(f"Error: {e}")
            self.finished.emit(False, self.version)


# ============================================================================
# CUSTOM WIDGETS
# ============================================================================

class ModernButton(QPushButton):
    def __init__(self, text, primary=False):
        super().__init__(text)
        self.primary = primary
        self.setCursor(Qt.PointingHandCursor)
        sh = QGraphicsDropShadowEffect()
        sh.setBlurRadius(20)
        sh.setColor(QColor(0, 0, 0, 80))
        sh.setOffset(0, 4)
        self.setGraphicsEffect(sh)

    def _slide(self, dy):
        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(150)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        cur = self.geometry()
        self.anim.setStartValue(cur)
        self.anim.setEndValue(QRect(cur.x(), cur.y() + dy, cur.width(), cur.height()))
        self.anim.start()

    def enterEvent(self, e): self._slide(-2); super().enterEvent(e)
    def leaveEvent(self, e): self._slide(+2); super().leaveEvent(e)


class SidebarButton(QPushButton):
    def __init__(self, text, icon_char=""):
        super().__init__(f"  {icon_char}  {text}")
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)
        self.setFixedHeight(50)


# ============================================================================
# MAIN WINDOW
# ============================================================================

class CMCLauncherUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CMC Launcher")
        self.setFixedSize(1000, 700)

        icon_path = os.path.join(ASSETS_DIR, "icon.png")
        if os.path.exists(icon_path):
            try:
                self.setWindowIcon(QIcon(icon_path))
            except Exception:
                pass

        self.config = self._load_config()
        self.rpc    = DiscordRPC(self.config.get("rpc_client_id"))

        self._setup_ui()
        self._connect_signals()
        self._load_initial_data()
        self._play_entrance_animation()

    # =========================================================== UI SETUP ===

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        self.setStyleSheet("""
QWidget {
    background-color: #0f0f0f;
    color: #ffffff;
    font-family: Arial;
}

QFrame {
    background-color: #141414;
    border: 1px solid #222;
    border-radius: 10px;
}

QPushButton {
    background-color: #1a1a1a;
    color: white;
    border: 1px solid #333;
    padding: 6px;
    border-radius: 6px;
}

QPushButton:hover {
    background-color: #2a2a2a;
}

QPushButton:pressed {
    background-color: #000;
}

QComboBox, QLineEdit, QSpinBox {
    background-color: #111;
    color: white;
    border: 1px solid #333;
    border-radius: 6px;
    padding: 5px;
}

QListWidget {
    background-color: #0d0d0d;
    border: 1px solid #222;
}

QTabWidget::pane {
    border: 1px solid #222;
}

QTabBar::tab {
    background: #111;
    color: white;
    padding: 8px;
    border: 1px solid #222;
}

QTabBar::tab:selected {
    background: #1f1f1f;
}

QProgressBar {
    background-color: #111;
    border: 1px solid #333;
}

QProgressBar::chunk {
    background-color: white;
}
""")
        ml = QHBoxLayout(central)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        ml.addWidget(self._create_sidebar())

        self.stack = QStackedWidget()
        self.stack.setObjectName("contentStack")
        self.stack.addWidget(self._create_play_page())      # 0
        self.stack.addWidget(self._create_loaders_page())   # 1
        self.stack.addWidget(self._create_profiles_page())  # 2
        self.stack.addWidget(self._create_mods_page())      # 3
        self.stack.addWidget(self._create_options_page())   # 4
        ml.addWidget(self.stack, 1)

    # ---------------------------------------------------------------- sidebar
    def _create_sidebar(self):
        sb = QFrame()
        sb.setObjectName("sidebar")
        sb.setFixedWidth(220)
        lay = QVBoxLayout(sb)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        hdr = QWidget()
        hdr.setFixedHeight(80)
        hdr.setObjectName("sidebarHeader")
        hl = QVBoxLayout(hdr)
        hl.setContentsMargins(20, 20, 20, 10)
        logo = QLabel("CMC"); logo.setObjectName("logoText"); hl.addWidget(logo)
        ver  = QLabel("Launcher v1.1"); ver.setObjectName("versionText"); hl.addWidget(ver)
        lay.addWidget(hdr)

        nav = QWidget()
        nl  = QVBoxLayout(nav)
        nl.setContentsMargins(10, 20, 10, 20)
        nl.setSpacing(8)

        self.btn_home     = SidebarButton("Play",        "▶")
        self.btn_loaders  = SidebarButton("Mod Loaders", "⚙")
        self.btn_perfiles = SidebarButton("Profiles",    "👤")
        self.btn_mods     = SidebarButton("Mods",        "📦")
        self.btn_opciones = SidebarButton("Settings",    "🔧")

        self.sidebar_buttons = [
            self.btn_home, self.btn_loaders,
            self.btn_perfiles, self.btn_mods, self.btn_opciones,
        ]
        for b in self.sidebar_buttons:
            nl.addWidget(b)
        nl.addStretch()
        lay.addWidget(nav, 1)

        ft = QLabel("Made for the Community ♥ CLT")
        ft.setObjectName("sidebarFooter")
        ft.setAlignment(Qt.AlignCenter)
        ft.setFixedHeight(40)
        lay.addWidget(ft)

        self.btn_home.setChecked(True)
        return sb

    # ------------------------------------------------------------------ Play
    def _create_play_page(self):
        page = QWidget(); page.setObjectName("playPage")
        lay  = QVBoxLayout(page); lay.setContentsMargins(40,40,40,40); lay.setSpacing(18)

        hdr = QWidget(); hl = QVBoxLayout(hdr); hl.setSpacing(6)
        t = QLabel("Ready to Play"); t.setObjectName("pageTitle"); hl.addWidget(t)
        s = QLabel("Select your profile, version and mod loader")
        s.setObjectName("pageSubtitle"); hl.addWidget(s)
        lay.addWidget(hdr); lay.addSpacing(6)

        # Profile card
        pc = self._card("Profile", "👤"); pl = QHBoxLayout(); pl.setSpacing(10)
        self.profile_combo = QComboBox(); self.profile_combo.setFixedHeight(45)
        pl.addWidget(self.profile_combo, 1)
        self.manage_profiles_btn = ModernButton("Manage")
        self.manage_profiles_btn.setFixedHeight(45)
        self.manage_profiles_btn.setFixedWidth(110)
        pl.addWidget(self.manage_profiles_btn)
        pc.layout().addLayout(pl); lay.addWidget(pc)

        # Version card
        vc = self._card("Minecraft Version", "🎮"); vl = QHBoxLayout()
        self.version_combo = QComboBox(); self.version_combo.setFixedHeight(45)
        vl.addWidget(self.version_combo, 1)
        vc.layout().addLayout(vl); lay.addWidget(vc)

        # Loader card
        lc = self._card("Mod Loader", "🔩"); ll = QHBoxLayout(); ll.setSpacing(10)
        self.play_loader_combo = QComboBox(); self.play_loader_combo.setFixedHeight(45)
        self.play_loader_combo.addItems(["Vanilla", "Fabric", "Quilt", "Forge", "NeoForge"])
        ll.addWidget(self.play_loader_combo, 1)
        self.play_loader_ver_combo = QComboBox(); self.play_loader_ver_combo.setFixedHeight(45)
        self.play_loader_ver_combo.addItem("— select version first —")
        ll.addWidget(self.play_loader_ver_combo, 1)
        self.play_fetch_btn = ModernButton("Fetch")
        self.play_fetch_btn.setFixedHeight(45); self.play_fetch_btn.setFixedWidth(80)
        ll.addWidget(self.play_fetch_btn)
        lc.layout().addLayout(ll); lay.addWidget(lc)

        # Progress
        pw = QWidget(); pl2 = QVBoxLayout(pw); pl2.setSpacing(8)
        self.status_label = QLabel("Ready to launch")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)
        pl2.addWidget(self.status_label)
        self.progress = QProgressBar(); self.progress.setObjectName("modernProgress")
        self.progress.setFixedHeight(8); self.progress.setValue(0)
        self.progress.setTextVisible(False)
        pl2.addWidget(self.progress)
        lay.addWidget(pw); lay.addStretch()

        # Launch button
        self.play_btn = ModernButton("LAUNCH GAME", primary=True)
        self.play_btn.setObjectName("playButton"); self.play_btn.setFixedHeight(65)
        sh = QGraphicsDropShadowEffect()
        sh.setBlurRadius(30); sh.setColor(QColor(59,130,246,100)); sh.setOffset(0,8)
        self.play_btn.setGraphicsEffect(sh)
        lay.addWidget(self.play_btn)
        return page

    # ---------------------------------------------------------- Loaders page
    def _create_loaders_page(self):
        page = QWidget(); page.setObjectName("contentPage")
        lay  = QVBoxLayout(page); lay.setContentsMargins(40,40,40,40); lay.setSpacing(20)

        t = QLabel("Mod Loader Manager"); t.setObjectName("pageTitle"); lay.addWidget(t)
        s = QLabel("Install Fabric, Quilt, Forge or NeoForge for any Minecraft version")
        s.setObjectName("pageSubtitle"); lay.addWidget(s); lay.addSpacing(5)

        self.loader_tabs = QTabWidget(); self.loader_tabs.setObjectName("loaderTabs")

        self.loader_mc_combos     = {}
        self.loader_ver_combos    = {}
        self.loader_fetch_btns    = {}
        self.loader_install_btns  = {}
        self.loader_status_labels = {}
        self.loader_progress_bars = {}

        for name, icon in [("Fabric","🪡"),("Quilt","🧵"),("Forge","⚒"),("NeoForge","🔥")]:
            tab = QWidget()
            tl  = QVBoxLayout(tab); tl.setContentsMargins(25,25,25,15); tl.setSpacing(16)

            # MC version row
            mr = QHBoxLayout(); mc_lbl = QLabel("Minecraft version:")
            mc_lbl.setFixedWidth(145); mr.addWidget(mc_lbl)
            mc_cb = QComboBox(); mc_cb.setFixedHeight(40)
            mr.addWidget(mc_cb, 1); self.loader_mc_combos[name] = mc_cb
            tl.addLayout(mr)

            # Loader version row
            lr = QHBoxLayout(); lv_lbl = QLabel(f"{name} version:")
            lv_lbl.setFixedWidth(145); lr.addWidget(lv_lbl)
            lv_cb = QComboBox(); lv_cb.setFixedHeight(40)
            lv_cb.addItem("— click Fetch —"); lr.addWidget(lv_cb, 1)
            fb = ModernButton("Fetch versions")
            fb.setFixedHeight(40); fb.setFixedWidth(130); lr.addWidget(fb)
            self.loader_ver_combos[name] = lv_cb
            self.loader_fetch_btns[name] = fb
            tl.addLayout(lr)

            # Progress bar
            pb = QProgressBar(); pb.setObjectName("modernProgress")
            pb.setFixedHeight(8); pb.setValue(0); pb.setTextVisible(False)
            self.loader_progress_bars[name] = pb; tl.addWidget(pb)

            # Status label
            sl = QLabel(""); sl.setObjectName("statusLabel"); sl.setAlignment(Qt.AlignCenter)
            self.loader_status_labels[name] = sl; tl.addWidget(sl)

            tl.addStretch()

            # Install button
            ib = ModernButton(f"Install {name}", primary=True); ib.setFixedHeight(50)
            self.loader_install_btns[name] = ib; tl.addWidget(ib)

            self.loader_tabs.addTab(tab, f"{icon} {name}")

        lay.addWidget(self.loader_tabs)

        ll = QLabel("Installed Mod Loader Profiles"); ll.setObjectName("sectionLabel")
        lay.addWidget(ll)
        self.installed_loaders_list = QListWidget()
        self.installed_loaders_list.setObjectName("modernList")
        self.installed_loaders_list.setMaximumHeight(130)
        lay.addWidget(self.installed_loaders_list)
        return page

    # --------------------------------------------------------- Profiles page
    def _create_profiles_page(self):
        page = QWidget(); page.setObjectName("contentPage")
        lay  = QVBoxLayout(page); lay.setContentsMargins(40,40,40,40); lay.setSpacing(20)
        QLabel("Profile Management", objectName="pageTitle")
        lay.addWidget(QLabel("Profile Management", objectName="pageTitle"))
        lay.addWidget(QLabel("Create and manage your game profiles", objectName="pageSubtitle"))
        lay.addSpacing(5)

        fc = QFrame(); fc.setObjectName("formCard")
        fl = QFormLayout(fc); fl.setContentsMargins(25,25,25,25)
        fl.setSpacing(15); fl.setLabelAlignment(Qt.AlignRight)
        self.input_profile_name  = QLineEdit(); self.input_profile_name.setPlaceholderText("e.g., MainProfile"); self.input_profile_name.setFixedHeight(40)
        self.input_display_name  = QLineEdit(); self.input_display_name.setPlaceholderText("e.g., My Profile");   self.input_display_name.setFixedHeight(40)
        self.input_player_name   = QLineEdit(); self.input_player_name.setPlaceholderText("e.g., Steve");          self.input_player_name.setFixedHeight(40)
        fl.addRow("Profile ID:",   self.input_profile_name)
        fl.addRow("Display Name:", self.input_display_name)
        fl.addRow("Player Name:",  self.input_player_name)
        lay.addWidget(fc)

        bc = QWidget(); bl = QHBoxLayout(bc); bl.setSpacing(12)
        self.btn_save_profile    = ModernButton("Save Profile", primary=True); self.btn_save_profile.setFixedHeight(45)
        self.btn_delete_profile  = ModernButton("Delete");                     self.btn_delete_profile.setFixedHeight(45)
        self.btn_reload_profiles = ModernButton("Refresh");                    self.btn_reload_profiles.setFixedHeight(45)
        bl.addWidget(self.btn_save_profile); bl.addWidget(self.btn_delete_profile); bl.addWidget(self.btn_reload_profiles)
        lay.addWidget(bc)

        lay.addWidget(QLabel("Existing Profiles", objectName="sectionLabel"))
        self.profiles_list = QListWidget(); self.profiles_list.setObjectName("modernList"); lay.addWidget(self.profiles_list)
        return page

    # ------------------------------------------------------------ Mods page
    def _create_mods_page(self):
        page = QWidget(); page.setObjectName("contentPage")
        lay  = QVBoxLayout(page); lay.setContentsMargins(40,40,40,40); lay.setSpacing(20)
        lay.addWidget(QLabel("Mod Manager", objectName="pageTitle"))
        lay.addWidget(QLabel("Enable, disable, and manage your mods", objectName="pageSubtitle"))
        lay.addSpacing(5)

        bc = QWidget(); bl = QHBoxLayout(bc); bl.setSpacing(12)
        self.btn_refresh_mods = ModernButton("Refresh");          self.btn_refresh_mods.setFixedHeight(45)
        self.btn_add_mod      = ModernButton("Add Mod",primary=True); self.btn_add_mod.setFixedHeight(45)
        self.btn_open_mods    = ModernButton("Open Folder");      self.btn_open_mods.setFixedHeight(45)
        bl.addWidget(self.btn_refresh_mods); bl.addWidget(self.btn_add_mod)
        bl.addWidget(self.btn_open_mods); bl.addStretch()
        lay.addWidget(bc)

        info = QLabel("💡 Double-click a mod to enable/disable it  •  Requires a mod loader installed")
        info.setObjectName("infoLabel"); lay.addWidget(info)
        self.mods_list = QListWidget(); self.mods_list.setObjectName("modernList"); lay.addWidget(self.mods_list)
        return page

    # ---------------------------------------------------------- Options page
    def _create_options_page(self):
        page = QWidget(); page.setObjectName("contentPage")
        lay  = QVBoxLayout(page); lay.setContentsMargins(40,40,40,40); lay.setSpacing(20)
        lay.addWidget(QLabel("Settings", objectName="pageTitle"))
        lay.addWidget(QLabel("Configure launcher preferences", objectName="pageSubtitle"))
        lay.addSpacing(5)

        sc = QFrame(); sc.setObjectName("formCard")
        sl = QVBoxLayout(sc); sl.setContentsMargins(25,25,25,25); sl.setSpacing(20)

        rw = QWidget(); rl = QHBoxLayout(rw); rl.setContentsMargins(0,0,0,0)
        rl.addWidget(QLabel("Memory Allocation (RAM)", objectName="settingLabel"))
        rl.addStretch()
        self.ram_spin = QSpinBox(); self.ram_spin.setRange(1,16)
        self.ram_spin.setValue(self.config.get("default_ram_gb", 2))
        self.ram_spin.setSuffix(" GB"); self.ram_spin.setFixedHeight(40); self.ram_spin.setFixedWidth(120)
        rl.addWidget(self.ram_spin); sl.addWidget(rw)

        div1 = QFrame(); div1.setFrameShape(QFrame.HLine); div1.setObjectName("divider"); sl.addWidget(div1)

        sl.addWidget(QLabel("Performance Optimizations", objectName="settingLabel"))
        sl.addWidget(QLabel(
            "✓ Aikar's flags (1.13+) / Legacy flags (<1.13)\n"
            "✓ G1GC garbage collector  ✓ Optimized heap",
            objectName="statusText"))

        div2 = QFrame(); div2.setFrameShape(QFrame.HLine); div2.setObjectName("divider"); sl.addWidget(div2)

        sl.addWidget(QLabel("Discord Rich Presence", objectName="settingLabel"))
        sl.addWidget(QLabel("✓ Connected" if self.rpc.rpc else "✗ Disconnected",
                             objectName="statusText"))

        sl.addStretch(); lay.addWidget(sc); lay.addStretch()
        return page

    def _card(self, title, icon):
        card = QFrame(); card.setObjectName("selectorCard")
        cl   = QVBoxLayout(card); cl.setContentsMargins(20,20,20,20); cl.setSpacing(12)
        cl.addWidget(QLabel(f"{icon}  {title}", objectName="cardTitle"))
        return card

    # ======================================================== SIGNALS ===

    def _connect_signals(self):
        # Sidebar
        self.btn_home.clicked.connect(    lambda: self._switch(0, self.btn_home))
        self.btn_loaders.clicked.connect( lambda: self._switch(1, self.btn_loaders))
        self.btn_perfiles.clicked.connect(lambda: self._switch(2, self.btn_perfiles))
        self.btn_mods.clicked.connect(    lambda: self._switch(3, self.btn_mods))
        self.btn_opciones.clicked.connect(lambda: self._switch(4, self.btn_opciones))
        self.manage_profiles_btn.clicked.connect(lambda: self._switch(2, self.btn_perfiles))

        # Profiles
        self.btn_save_profile.clicked.connect(self.save_profile_action)
        self.btn_delete_profile.clicked.connect(self.delete_profile_action)
        self.btn_reload_profiles.clicked.connect(self.load_profiles_list)
        self.profiles_list.itemClicked.connect(self.on_profile_selected)

        # Mods
        self.btn_refresh_mods.clicked.connect(self.reload_mods)
        self.btn_add_mod.clicked.connect(self.add_mod_file)
        self.btn_open_mods.clicked.connect(self.open_mods_folder)
        self.mods_list.itemDoubleClicked.connect(self.toggle_mod)

        # Play-page loader fetch
        self.play_fetch_btn.clicked.connect(self.on_play_fetch_loader_versions)
        self.play_loader_combo.currentTextChanged.connect(self._on_play_loader_changed)

        # Launch
        self.play_btn.clicked.connect(self.on_play)
        self.version_combo.currentTextChanged.connect(
            lambda v: self.rpc.update_launcher(f"Selecting {v}"))

        # Loader manager tabs
        for name in ["Fabric", "Quilt", "Forge", "NeoForge"]:
            n = name
            self.loader_fetch_btns[n].clicked.connect(
                lambda _=False, ln=n: self.fetch_loader_versions(ln))
            self.loader_install_btns[n].clicked.connect(
                lambda _=False, ln=n: self.install_loader(ln))

    def _switch(self, index, btn):
        for b in self.sidebar_buttons:
            b.setChecked(False)
        btn.setChecked(True)
        self.stack.setCurrentIndex(index)
        if index == 1:
            self.refresh_installed_loaders()

    # ======================================================= INIT DATA ===

    def _load_initial_data(self):
        self.load_versions()
        self.reload_mods()
        self.load_profiles_list()
        self.populate_profile_combo()
        self.rpc.update_launcher("Browsing launcher")

    def _play_entrance_animation(self):
        self.setWindowOpacity(0)
        a = QPropertyAnimation(self, b"windowOpacity")
        a.setDuration(500); a.setStartValue(0); a.setEndValue(1)
        a.setEasingCurve(QEasingCurve.OutCubic); a.start()
        self._entrance_anim = a

    def _load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"last_version": None, "default_ram_gb": 2,
                "rpc_client_id": "1465868632394305629"}

    def _save_config(self):
        try:
            self.config["default_ram_gb"] = self.ram_spin.value()
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        except Exception:
            pass

    # ======================================================== VERSIONS ===

    def load_versions(self):
        self.version_combo.clear()
        cache = os.path.join(CACHE_DIR, "versions.json")
        try:
            if os.path.exists(cache) and (time.time() - os.path.getmtime(cache)) < 3600:
                with open(cache) as f:
                    ids = json.load(f)
                for v in ids:
                    self.version_combo.addItem(v)
                self._populate_loader_mc_combos(ids)
                return
        except Exception:
            pass
        try:
            versions = minecraft_launcher_lib.utils.get_version_list()
            ids = [v["id"] for v in versions if v.get("type") == "release"]
            for v in ids:
                self.version_combo.addItem(v)
            with open(cache, "w") as f:
                json.dump(ids, f)
            self._populate_loader_mc_combos(ids)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load versions:\n{e}")

    def _populate_loader_mc_combos(self, ids: list):
        for cb in self.loader_mc_combos.values():
            cb.clear()
            for v in ids:
                cb.addItem(v)

    # =================================================== LOADER MANAGER ===

    def fetch_loader_versions(self, loader_name: str):
        mc_ver = self.loader_mc_combos[loader_name].currentText()
        if not mc_ver:
            return
        sl = self.loader_status_labels[loader_name]
        lv = self.loader_ver_combos[loader_name]
        fb = self.loader_fetch_btns[loader_name]
        sl.setText("Fetching versions…")
        lv.clear(); lv.addItem("Loading…")
        fb.setEnabled(False)

        self._fetch_thread = LoaderVersionFetchThread(loader_name.lower(), mc_ver)
        self._fetch_thread.result.connect(self._on_loader_versions_fetched)
        self._fetch_thread.start()

    def _on_loader_versions_fetched(self, loader_lower: str, versions: list):
        key = next((k for k in self.loader_ver_combos if k.lower() == loader_lower), None)
        if not key:
            return
        cb = self.loader_ver_combos[key]
        sl = self.loader_status_labels[key]
        fb = self.loader_fetch_btns[key]
        cb.clear()
        if versions:
            for v in versions:
                cb.addItem(v)
            sl.setText(f"{len(versions)} versions available")
        else:
            cb.addItem("— no versions found —")
            sl.setText("⚠ No versions found for this MC release")
        fb.setEnabled(True)

    def install_loader(self, loader_name: str):
        mc_ver     = self.loader_mc_combos[loader_name].currentText()
        loader_ver = self.loader_ver_combos[loader_name].currentText()
        if not mc_ver or loader_ver.startswith("—") or loader_ver == "Loading…":
            QMessageBox.warning(self, "Warning",
                                "Fetch loader versions first, then select one.")
            return

        if QMessageBox.question(
            self, "Install",
            f"Install {loader_name} {loader_ver} for Minecraft {mc_ver}?\n\n"
            "The base Minecraft version will be downloaded if needed.",
            QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        sl = self.loader_status_labels[loader_name]
        pb = self.loader_progress_bars[loader_name]
        ib = self.loader_install_btns[loader_name]
        sl.setText("Starting installation…"); pb.setValue(0); ib.setEnabled(False)

        self._loader_thread = ModLoaderInstallerThread(loader_name, mc_ver, loader_ver)
        self._loader_thread.status.connect(sl.setText)
        self._loader_thread.progress.connect(pb.setValue)
        self._loader_thread.finished.connect(
            lambda ok, msg, ln=loader_name, ib_=ib, pb_=pb, sl_=sl:
                self._on_loader_installed(ok, msg, ln, ib_, pb_, sl_))
        self._loader_thread.start()

    def _on_loader_installed(self, ok, msg, loader_name, ib, pb, sl):
        ib.setEnabled(True)
        pb.setValue(100 if ok else 0)
        if ok:
            sl.setText(f"✓ {msg}")
            QMessageBox.information(self, "Success",
                f"{msg}\n\nYou can now select this loader on the Play page.")
            self.refresh_installed_loaders()
            self._refresh_play_loader_versions()
        else:
            sl.setText(f"✗ {msg}")
            QMessageBox.critical(self, "Error", f"Installation failed:\n{msg}")

    def refresh_installed_loaders(self):
        self.installed_loaders_list.clear()
        vdir = os.path.join(MINECRAFT_DIR, "versions")
        if not os.path.isdir(vdir):
            return
        keywords = ["fabric-loader", "quilt-loader", "forge", "neoforge"]
        for entry in sorted(os.listdir(vdir)):
            low = entry.lower()
            if any(kw in low for kw in keywords):
                icon = ("🪡" if "fabric"   in low else
                        "🧵" if "quilt"    in low else
                        "🔥" if "neoforge" in low else "⚒")
                self.installed_loaders_list.addItem(
                    QListWidgetItem(f"{icon}  {entry}"))

    # ---------------------------------------- Play-page loader quick picker
    def on_play_fetch_loader_versions(self):
        loader = self.play_loader_combo.currentText()
        mc_ver = self.version_combo.currentText()
        if loader == "Vanilla" or not mc_ver:
            self.play_loader_ver_combo.clear()
            self.play_loader_ver_combo.addItem("— vanilla, no loader needed —")
            return
        self.play_loader_ver_combo.clear()
        self.play_loader_ver_combo.addItem("Loading…")
        self._play_fetch_thread = LoaderVersionFetchThread(loader.lower(), mc_ver)
        self._play_fetch_thread.result.connect(self._on_play_loader_versions_fetched)
        self._play_fetch_thread.start()

    def _on_play_loader_versions_fetched(self, _, versions: list):
        self.play_loader_ver_combo.clear()
        if versions:
            for v in versions:
                self.play_loader_ver_combo.addItem(v)
        else:
            self.play_loader_ver_combo.addItem("— no versions found —")

    def _on_play_loader_changed(self, loader: str):
        if loader == "Vanilla":
            self.play_loader_ver_combo.clear()
            self.play_loader_ver_combo.addItem("— no loader —")

    def _refresh_play_loader_versions(self):
        self.play_loader_ver_combo.clear()
        self.play_loader_ver_combo.addItem("— click Fetch —")

    # ============================================================== MODS ===

    def reload_mods(self):
        self.mods_list.clear()
        enabled, disabled = [], []
        if os.path.exists(MODS_DIR):
            for f in os.listdir(MODS_DIR):
                if f != "disabled" and os.path.isfile(os.path.join(MODS_DIR, f)):
                    enabled.append(f)
        if os.path.exists(DISABLED_MODS_DIR):
            for f in os.listdir(DISABLED_MODS_DIR):
                if os.path.isfile(os.path.join(DISABLED_MODS_DIR, f)):
                    disabled.append(f)
        for m in sorted(enabled):
            it = QListWidgetItem(f"✓  {m}"); it.setData(Qt.UserRole, ("enabled", m))
            self.mods_list.addItem(it)
        for m in sorted(disabled):
            it = QListWidgetItem(f"✗  {m}"); it.setData(Qt.UserRole, ("disabled", m))
            self.mods_list.addItem(it)

    def add_mod_file(self):
        fp, _ = QFileDialog.getOpenFileName(self, "Select Mod (.jar)", "", "JAR Files (*.jar)")
        if fp:
            try:
                shutil.copy(fp, os.path.join(MODS_DIR, os.path.basename(fp)))
                self.reload_mods()
                QMessageBox.information(self, "Success", "Mod added")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def toggle_mod(self, item):
        status, name = item.data(Qt.UserRole)
        src = os.path.join(MODS_DIR if status == "enabled" else DISABLED_MODS_DIR, name)
        dst = os.path.join(DISABLED_MODS_DIR if status == "enabled" else MODS_DIR, name)
        try:
            shutil.move(src, dst); self.reload_mods()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def open_mods_folder(self):
        try:
            if os.name == "nt":
                os.startfile(MODS_DIR)
            else:
                subprocess.Popen(["xdg-open", MODS_DIR])
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ========================================================= PROFILES ===

    def load_profiles_list(self):
        self.profiles_list.clear()
        for key, val in self._read_profiles().items():
            display = val.get("display_name", key)
            player  = val.get("player_name", display)
            it = QListWidgetItem(f"👤  {display}  •  {player}")
            it.setData(Qt.UserRole, key); self.profiles_list.addItem(it)

    def on_profile_selected(self, item):
        key     = item.data(Qt.UserRole)
        profile = self._read_profiles().get(key, {})
        self.input_profile_name.setText(key)
        self.input_display_name.setText(profile.get("display_name", ""))
        self.input_player_name.setText( profile.get("player_name",  ""))

    def save_profile_action(self):
        key = self.input_profile_name.text().strip()
        if not key:
            QMessageBox.warning(self, "Warning", "Profile ID required"); return
        display = self.input_display_name.text().strip() or key
        player  = self.input_player_name.text().strip()  or display
        data    = self._read_profiles()
        data[key] = {"display_name": display, "player_name": player,
                     "ram_gb": self.ram_spin.value()}
        self._write_profiles(data)
        self.load_profiles_list(); self.populate_profile_combo()
        QMessageBox.information(self, "Success", "Profile saved")
        self.rpc.update_launcher(f"Saved '{display}'")

    def delete_profile_action(self):
        item = self.profiles_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Warning", "Select a profile"); return
        key = item.data(Qt.UserRole)
        if QMessageBox.question(self, "Confirm", f"Delete '{key}'?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            data = self._read_profiles()
            data.pop(key, None)
            self._write_profiles(data)
            self.load_profiles_list(); self.populate_profile_combo()
            QMessageBox.information(self, "Success", "Profile deleted")

    def populate_profile_combo(self):
        self.profile_combo.clear()
        for key, val in self._read_profiles().items():
            self.profile_combo.addItem(val.get("display_name", key), key)

    def _read_profiles(self):
        try:
            if os.path.exists(PROFILES_FILE):
                with open(PROFILES_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _write_profiles(self, data):
        try:
            with open(PROFILES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # =========================================================== LAUNCH ===

    def on_play(self):
        idx = self.profile_combo.currentIndex()
        if idx == -1:
            QMessageBox.warning(self, "Warning", "Select a profile"); return
        profile_key = self.profile_combo.itemData(idx)
        profile     = self._read_profiles().get(profile_key, {})
        player_name = profile.get("player_name", profile.get("display_name", profile_key))

        version = self.version_combo.currentText()
        if not version:
            QMessageBox.warning(self, "Warning", "Select a version"); return

        loader      = self.play_loader_combo.currentText()
        loader_ver  = self.play_loader_ver_combo.currentText()
        launch_version = self._resolve_launch_version(version, loader, loader_ver)
        if launch_version is None:
            return

        mode, ok = QInputDialog.getItem(
            self, "Mode", "Select:",
            ["Survival", "Creative", "Hardcore", "Server"], 0, False)
        if not ok:
            return

        server_addr = None
        if mode == "Server":
            server_addr, ok2 = QInputDialog.getText(self, "Server", "Address (ip:port):")
            if not ok2 or not server_addr:
                return

        version_json = os.path.join(
            MINECRAFT_DIR, "versions", version, f"{version}.json")
        if not os.path.exists(version_json):
            self.status_label.setText(f"Downloading {version}…")
            self.inst_thread = InstallerThread(version)
            self.inst_thread.progress.connect(self.progress.setValue)
            self.inst_thread.status.connect(self.status_label.setText)
            self.inst_thread.progress.connect(
                lambda p: self.rpc.update_downloading(version, p))
            self.inst_thread.finished.connect(
                lambda s, v: self._after_install(
                    s, v, player_name, profile_key, mode, server_addr, launch_version))
            self.inst_thread.start()
        else:
            self._start_game(launch_version, player_name, profile_key, mode, server_addr)

    def _resolve_launch_version(self, mc_version, loader, loader_ver):
        """Returns the version profile ID to launch, or None to abort."""
        if loader == "Vanilla" or loader_ver.startswith("—"):
            return mc_version

        if loader == "Fabric":
            pid = f"fabric-loader-{loader_ver}-{mc_version}"
        elif loader == "Quilt":
            pid = f"quilt-loader-{loader_ver}-{mc_version}"
        elif loader == "Forge":
            pid = loader_ver          # Forge full version string is the profile ID
        elif loader == "NeoForge":
            pid = f"neoforge-{loader_ver}"
        else:
            return mc_version

        profile_json = os.path.join(MINECRAFT_DIR, "versions", pid, f"{pid}.json")
        if os.path.exists(profile_json):
            return pid

        # Not installed yet — redirect
        reply = QMessageBox.question(
            self, "Loader Not Installed",
            f"{loader} {loader_ver} for {mc_version} is not installed yet.\n\n"
            "Open Mod Loaders page to install it?",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self._switch(1, self.btn_loaders)
        return None

    def _after_install(self, success, version, player_name, profile_key,
                       mode, server_addr, launch_version):
        if not success:
            QMessageBox.critical(self, "Error", f"Install failed for {version}")
            self.status_label.setText("Install failed"); return
        self._start_game(launch_version, player_name, profile_key, mode, server_addr)

    def _start_game(self, version, player_name, profile_key, mode, server_addr):
        ram_gb = self.ram_spin.value()
        try:
            options = minecraft_launcher_lib.utils.generate_test_options()
        except Exception:
            options = {}

        options["jvmArguments"]  = LaunchOptimizer.get_optimal_jvm_args(ram_gb, version)
        options["username"]       = player_name
        options["playerUsername"] = player_name

        try:
            cmd = minecraft_launcher_lib.command.get_minecraft_command(
                version, MINECRAFT_DIR, options)
            display = self._read_profiles().get(profile_key, {}).get(
                "display_name", profile_key)
            self.rpc.update_playing(display, version, mode, server_addr)

            self.game_process = QProcess()
            self.game_process.start(cmd[0], cmd[1:])
            self.status_label.setText("🎮 Launching Minecraft…")
            self.progress.setValue(0)
            QTimer.singleShot(2000,
                lambda: self.status_label.setText("✓ Launched successfully"))
            self._save_config()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Launch failed:\n{e}")
            self.status_label.setText("Launch failed")

    def closeEvent(self, event):
        try:
            self._save_config(); self.rpc.clear()
        except Exception:
            pass
        event.accept()


# ============================================================================
# STYLESHEET
# ============================================================================

STYLESHEET = """
QWidget {background:#0a0e27;color:#e4e7f0;
         font-family:'Inter','Segoe UI',sans-serif;font-size:13px;}

#sidebar {background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
          stop:0 #0d1229,stop:1 #080b1a);
          border-right:1px solid rgba(59,130,246,0.1);}
#sidebarHeader {background:rgba(59,130,246,0.05);
                border-bottom:1px solid rgba(59,130,246,0.1);}
#logoText    {font-size:28px;font-weight:800;color:#3b82f6;letter-spacing:2px;}
#versionText {font-size:11px;color:#6b7280;font-weight:500;}
#sidebarFooter {color:#4b5563;font-size:11px;padding:10px;background:rgba(0,0,0,0.2);}

SidebarButton {background:transparent;color:#9ca3af;border:none;border-radius:8px;
               padding:12px 16px;text-align:left;font-size:14px;font-weight:500;}
SidebarButton:hover   {background:rgba(59,130,246,0.1);color:#e4e7f0;}
SidebarButton:checked {background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                        stop:0 rgba(59,130,246,0.2),stop:1 rgba(59,130,246,0.1));
                        color:#3b82f6;border-left:3px solid #3b82f6;}

#playPage,#contentPage {background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
                         stop:0 #0a0e27,stop:1 #0d1229);}
#pageTitle   {font-size:26px;font-weight:700;color:#f9fafb;letter-spacing:-0.5px;}
#pageSubtitle{font-size:14px;color:#9ca3af;font-weight:400;}
#cardTitle   {font-size:13px;font-weight:600;color:#d1d5db;letter-spacing:0.3px;}
#sectionLabel{font-size:12px;font-weight:600;color:#9ca3af;
              text-transform:uppercase;letter-spacing:1px;margin-top:8px;}
#statusLabel {font-size:13px;color:#6b7280;font-weight:500;}
#infoLabel   {font-size:12px;color:#6b7280;padding:10px;
              background:rgba(59,130,246,0.05);border-radius:8px;
              border-left:3px solid #3b82f6;}
#settingLabel{font-size:14px;font-weight:600;color:#e4e7f0;}
#statusText  {font-size:13px;color:#6b7280;}

#selectorCard,#formCard {
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
             stop:0 rgba(15,23,42,0.6),stop:1 rgba(15,23,42,0.3));
  border:1px solid rgba(71,85,105,0.3);border-radius:12px;}
#divider {background:rgba(71,85,105,0.3);min-height:1px;max-height:1px;}

ModernButton {
  background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #374151,stop:1 #1f2937);
  color:#f9fafb;border:1px solid rgba(75,85,99,0.5);
  border-radius:8px;padding:10px 20px;font-weight:600;font-size:13px;}
ModernButton:hover    {background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                        stop:0 #4b5563,stop:1 #374151);
                        border:1px solid rgba(107,114,128,0.7);}
ModernButton:disabled {background:#1f2937;color:#4b5563;
                        border:1px solid rgba(75,85,99,0.2);}

#playButton {
  background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #3b82f6,stop:1 #2563eb);
  color:white;border:none;border-radius:12px;
  font-size:16px;font-weight:700;letter-spacing:1px;}
#playButton:hover {background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                   stop:0 #2563eb,stop:1 #1d4ed8);}

QComboBox {background:rgba(31,41,55,0.8);border:1px solid rgba(75,85,99,0.5);
           border-radius:8px;padding:10px 15px;color:#f9fafb;font-size:13px;}
QComboBox:hover {border:1px solid rgba(59,130,246,0.5);}
QComboBox QAbstractItemView {background:#1f2937;border:1px solid rgba(75,85,99,0.5);
                              selection-background-color:#3b82f6;outline:none;}

QLineEdit {background:rgba(31,41,55,0.6);border:1px solid rgba(75,85,99,0.5);
           border-radius:8px;padding:10px 15px;color:#f9fafb;font-size:14px;}
QLineEdit:focus {border:1px solid #3b82f6;background:rgba(31,41,55,0.9);}

QSpinBox {background:rgba(31,41,55,0.8);border:1px solid rgba(75,85,99,0.5);
          border-radius:8px;padding:8px 12px;color:#f9fafb;
          font-size:14px;font-weight:600;}

#modernProgress {background:rgba(31,41,55,0.6);border:none;border-radius:4px;}
#modernProgress::chunk {background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                         stop:0 #3b82f6,stop:1 #2563eb);border-radius:4px;}

#modernList {background:rgba(15,23,42,0.4);border:1px solid rgba(71,85,105,0.3);
             border-radius:8px;padding:8px;outline:none;}
#modernList::item          {background:transparent;color:#e4e7f0;padding:10px;
                             border-radius:6px;margin:2px 0;}
#modernList::item:hover    {background:rgba(59,130,246,0.1);}
#modernList::item:selected {background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                             stop:0 rgba(59,130,246,0.25),
                             stop:1 rgba(59,130,246,0.15));color:#f9fafb;}

QTabWidget::pane  {background:rgba(15,23,42,0.4);
                   border:1px solid rgba(71,85,105,0.3);border-radius:8px;}
QTabBar::tab      {background:rgba(31,41,55,0.4);color:#9ca3af;
                   border:1px solid rgba(71,85,105,0.2);
                   border-radius:6px 6px 0 0;
                   padding:10px 22px;font-weight:600;margin-right:4px;}
QTabBar::tab:selected {background:rgba(59,130,246,0.2);color:#3b82f6;
                        border-bottom:2px solid #3b82f6;}
QTabBar::tab:hover    {background:rgba(59,130,246,0.1);color:#e4e7f0;}

QMessageBox {background:#1f2937;}
QMessageBox QPushButton {background:#3b82f6;color:white;border:none;
                          border-radius:6px;padding:8px 20px;
                          font-weight:600;min-width:80px;}
"""

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Inter", 10))
    app.setStyleSheet(STYLESHEET)
    window = CMCLauncherUI()
    window.show()
    sys.exit(app.exec())