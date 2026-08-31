# resource_finder.py
import json
import os
import plistlib
import sys
from pathlib import Path
from typing import Dict, List, Optional, Union

PathLike = Union[str, Path]
_MANIFEST_CANDIDATES = ("unifypy.json", "app.json", "package.json")


class ResourceFinder:
    """
    Unified resource resolution for dev, PyInstaller (onedir/onefile), and installs.
    """

    _instance: "ResourceFinder" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initd", False):
            return
        self._initd = True

        # Runtime base dir (_MEIPASS / exe_dir / project_root).
        self._base_dir = self._runtime_base_dir()

        # Load metadata (manifest/Info.plist/env vars).
        self._meta = self._load_app_meta(self._base_dir)
        self._app_name = self._derive_app_name(self._meta)

        # Build search paths (ordered, deduped).
        self._search_dirs = self._build_search_dirs()

    # -------------- Public API --------------

    def get_app_meta(self) -> Dict:
        """
        Return app metadata.
        """
        return dict(self._meta)

    def get_app_name(self) -> str:
        """
        Return app name (manifest/display_name/name → .app name → exe/project name).
        """
        return self._app_name

    def get_project_root(self) -> Path:
        """
        Return source root in dev, runtime base in packaged builds.
        """
        if not self._is_frozen():
            return self._detect_project_root(default=self._base_dir)
        return self._base_dir

    def get_user_data_dir(self, create: bool = True) -> Path:
        """
        User data (writable) directory.
        """
        home = Path.home()
        if sys.platform == "win32":
            p = home / "AppData" / "Local" / self._app_name
        elif sys.platform == "darwin":
            p = home / "Library" / "Application Support" / self._app_name
        else:
            p = home / ".local" / "share" / self._app_name
        if create:
            p.mkdir(parents=True, exist_ok=True)
        return p.resolve()

    def get_user_cache_dir(self, create: bool = True) -> Path:
        p = self.get_user_data_dir(create=False) / "cache"
        if create:
            p.mkdir(parents=True, exist_ok=True)
        return p.resolve()

    def find_file(self, relpath: PathLike) -> Optional[Path]:
        """
        Find a file by relative path.
        """
        return self._find(relpath, want_dir=False)

    def find_directory(self, relpath: PathLike) -> Optional[Path]:
        """
        Find a directory by relative path.
        """
        return self._find(relpath, want_dir=True)

    # Common aliases.
    def find_models_dir(self) -> Optional[Path]:
        return self.find_directory("models")

    def find_assets_dir(self) -> Optional[Path]:
        return self.find_directory("assets")

    def find_config_dir(self) -> Optional[Path]:
        return self.find_directory("config")

    def find_libs_root(self) -> Optional[Path]:
        return self.find_directory("libs")

    # Find under a root (e.g., libs/models) by joining subpaths.
    def find_under(
        self, root: str, *subparts: PathLike, want_dir: bool = True
    ) -> Optional[Path]:
        parts: List[str] = []
        for s in subparts:
            if s is None:
                continue
            parts.extend(Path(str(s)).parts)  # Support merging "a/b" strings.
        rel = Path(root, *parts)
        return self._find(rel, want_dir=want_dir)

    # -------------- Compatibility helpers --------------

    def find_libs_dir_compat(
        self, *parts: PathLike, system: str = None, arch: str = None
    ) -> Optional[Path]:
        """Find libs or its subdirectories.

        - No args: return libs root
        - Positional: find_libs_dir_compat('libopus', 'Darwin', 'arm64')
        - Keywords: find_libs_dir_compat(system='Darwin', arch='arm64')
        - Legacy: find_libs_dir_compat(f'libopus/{system_dir}', arch_name)
        """
        segs: List[PathLike] = []
        segs.extend(parts)
        if system:
            segs.append(system)
        if arch:
            segs.append(arch)
        if not segs:
            return self.find_under("libs", want_dir=True)
        return self.find_under("libs", *segs, want_dir=True)

    # -------------- Internal implementation --------------

    def _is_frozen(self) -> bool:
        return getattr(sys, "frozen", False)

    def _runtime_base_dir(self) -> Path:
        """
        Unified runtime base dir: prefer _MEIPASS, then exe_dir, else project root.
        """
        if self._is_frozen():
            return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)).resolve()
        # resource_finder.py is in project/src/utils → parents[3] is project/
        return self._detect_project_root(default=Path(__file__).resolve().parents[2])

    def _detect_project_root(self, default: Path) -> Path:
        """
        Walk upward for marker files/dirs to locate project root.
        """
        markers = {"assets", "models", "pyproject.toml", "requirements.txt", ".git"}
        p = default
        for parent in [p] + list(p.parents):
            try:
                entries = {e.name for e in parent.iterdir()}
            except Exception:
                continue
            if markers & entries:
                return parent.resolve()
        return default.resolve()

    def _load_app_meta(self, base: Path) -> Dict:
        """
        Load manifest (unifypy.json/app.json/package.json) and macOS Info.plist.
        Environment variables can override.
        """
        meta: Dict = {}

        # Environment variables can inject/override.
        for k in ("APP_NAME",):
            if os.getenv(k):
                meta["name"] = os.getenv(k)

        # 1) Manifest (search base and base.parent).
        candidates: List[Path] = []
        for name in _MANIFEST_CANDIDATES:
            candidates.append(base / name)
            candidates.append(base.parent / name)

        for c in candidates:
            try:
                if c.is_file():
                    meta.update(json.loads(c.read_text(encoding="utf-8")))
                    meta["_manifest_path"] = str(c)
                    break
            except Exception:
                pass

        # 2) macOS Info.plist (if .app exists).
        if sys.platform == "darwin":
            app_root = self._locate_app_bundle_root()
            if app_root:
                plist = app_root / "Contents" / "Info.plist"
                if plist.is_file():
                    try:
                        with plist.open("rb") as f:
                            info = plistlib.load(f)
                        meta.setdefault(
                            "display_name",
                            info.get("CFBundleDisplayName") or info.get("CFBundleName"),
                        )
                        meta.setdefault("name", info.get("CFBundleName"))
                        meta.setdefault(
                            "version",
                            info.get("CFBundleShortVersionString")
                            or info.get("CFBundleVersion"),
                        )
                        meta["_plist_path"] = str(plist)
                    except Exception:
                        pass

        return meta

    def _locate_app_bundle_root(self) -> Optional[Path]:
        exe = Path(sys.executable).resolve()
        for p in [exe] + list(exe.parents):
            if p.name.endswith(".app"):
                return p
        return None

    def _derive_app_name(self, meta: Dict) -> str:
        name = (meta.get("name") or meta.get("display_name") or "").strip()
        if not name and sys.platform == "darwin":
            app_root = self._locate_app_bundle_root()
            if app_root:
                name = app_root.stem
        if not name:
            name = (
                Path(sys.executable).stem
                if self._is_frozen()
                else self._detect_project_root(self._base_dir).name
            )
        return name.strip()

    def _canon_env_keys(self) -> List[str]:
        """
        Generate env var names from app name (also supports legacy XIAOZHI_*).
        """
        canon = "".join(ch if ch.isalnum() else "_" for ch in self._app_name).upper()
        keys = [f"{canon}_DATA_DIR", f"{canon}_HOME", f"{canon}_RESOURCES_DIR"]
        # Backward compatibility: remove next line to drop legacy names.
        keys += ["XIAOZHI_DATA_DIR", "XIAOZHI_HOME", "XIAOZHI_RESOURCES_DIR"]
        return keys

    def _build_search_dirs(self) -> List[Path]:
        dirs: List[Path] = []

        # 0) Environment variables (highest priority).
        for key in self._canon_env_keys():
            v = os.getenv(key)
            if v:
                p = Path(v).resolve()
                if p.exists():
                    dirs.append(p)

        # 1) Runtime base dir (_MEIPASS / exe_dir / project_root).
        dirs.append(self._base_dir)

        # 2) PyInstaller onedir v6: _internal next to executable.
        try:
            exe_dir = Path(sys.executable).parent.resolve()
            internal = exe_dir / "_internal"
            if self._is_frozen() and internal.exists():
                dirs.append(internal)
        except Exception:
            pass

        # 3) Common system install locations.
        name = self._app_name
        if sys.platform == "darwin":
            candidates = [
                Path("/Library") / "Application Support" / name,
                Path("/usr/local/share") / name,
                Path("/opt") / name,
            ]
            app_root = self._locate_app_bundle_root()
            if app_root:
                res = app_root / "Contents" / "Resources"
                if res.exists():
                    candidates.insert(0, res)
            dirs += [c for c in candidates if c.exists()]
        elif sys.platform.startswith("linux"):
            dirs += [
                p
                for p in [
                    Path("/usr/share") / name,
                    Path("/usr/local/share") / name,
                    Path("/opt") / name,
                ]
                if p.exists()
            ]
        else:  # Windows
            dirs += [p for p in [Path("C:/ProgramData") / name] if p.exists()]

        # 4) User data (writable/override).
        dirs.append(self.get_user_data_dir(create=True))

        # 5) Final fallback: cwd.
        try:
            dirs.append(Path.cwd().resolve())
        except Exception:
            pass

        # Deduplicate while preserving order.
        out, seen = [], set()
        for d in dirs:
            d = d.resolve()
            if d not in seen:
                out.append(d)
                seen.add(d)
        return out

    def _find(self, relpath: PathLike, want_dir: bool) -> Optional[Path]:
        rp = Path(relpath)
        if rp.is_absolute():
            try:
                ok = rp.is_dir() if want_dir else rp.is_file()
            except OSError:
                ok = False
            return rp if ok else None

        for base in self._search_dirs:
            p = (base / rp).resolve()
            try:
                ok = p.is_dir() if want_dir else p.is_file()
            except OSError:
                ok = False
            if ok:
                return p
        return None


# --------- Singleton and convenience functions ---------
resource_finder = ResourceFinder()


def get_app_meta() -> Dict:
    return resource_finder.get_app_meta()


def get_app_name() -> str:
    return resource_finder.get_app_name()


def get_project_root() -> Path:
    return resource_finder.get_project_root()


def get_user_data_dir(create: bool = True) -> Path:
    return resource_finder.get_user_data_dir(create)


def get_user_cache_dir(create: bool = True) -> Path:
    return resource_finder.get_user_cache_dir(create)


def find_file(p: PathLike) -> Optional[Path]:
    return resource_finder.find_file(p)


def find_directory(p: PathLike) -> Optional[Path]:
    return resource_finder.find_directory(p)


def find_models_dir() -> Optional[Path]:
    return resource_finder.find_models_dir()


def find_assets_dir() -> Optional[Path]:
    return resource_finder.find_assets_dir()


def find_config_dir() -> Optional[Path]:
    return resource_finder.find_config_dir()


# Legacy signature: find_libs_dir(f"libopus/{system_dir}", arch_name) /
# find_libs_dir(system='Darwin', arch='arm64')
def find_libs_dir(
    *parts: PathLike, system: str = None, arch: str = None
) -> Optional[Path]:
    return resource_finder.find_libs_dir_compat(*parts, system=system, arch=arch)


# Optional: more granular lookups.
def find_models_subdir(*parts: PathLike) -> Optional[Path]:
    return resource_finder.find_under("models", *parts, want_dir=True)


def find_assets_subpath(*parts: PathLike) -> Optional[Path]:
    return resource_finder.find_under("assets", *parts, want_dir=False)
