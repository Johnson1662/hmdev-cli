#!/usr/bin/env python3
"""
hmdev-cli — HarmonyOS Build & Deploy tools.

Detects hvigorw and hdc, runs builds, manages device operations.
"""

import os
import platform
import subprocess
from pathlib import Path

from config import Config


def _find_on_path(name: str) -> str | None:
    try:
        result = subprocess.run(
            ["where", name] if platform.system() == "Windows" else ["which", name],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[0]
    except Exception:
        pass
    return None


# ── Hvigor Tool ──────────────────────────────────────────────────────────────

_HVIGOR_PATHS = {
    "Windows": [
        "C:\\Program Files\\Huawei\\DevEco Studio\\tools\\hvigor\\bin\\hvigorw.js",
        "D:\\DevEco Studio\\tools\\hvigor\\bin\\hvigorw.js",
    ],
    "Darwin": [
        "/Applications/DevEco-Studio.app/Contents/tools/hvigor/bin/hvigorw.js",
        os.path.expanduser("~/Library/Application Support/Huawei/DevEco Studio/tools/hvigor/bin/hvigorw.js"),
    ],
    "Linux": [
        os.path.expanduser("~/DevEco Studio/tools/hvigor/bin/hvigorw.js"),
        "/opt/DevEco Studio/tools/hvigor/bin/hvigorw.js",
    ],
}


class HvigorTool:
    def __init__(self, project_dir: str = "."):
        self.project_dir = Path(project_dir).resolve()
        self._hvigor_path: str | None = None

    def detect(self, config: Config | None = None) -> str | None:
        cfg = config or Config()

        # 1. 项目目录下的包装脚本
        for name in ["hvigorw.bat", "hvigorw"]:
            candidate = self.project_dir / name
            if candidate.exists():
                self._hvigor_path = str(candidate)
                return self._hvigor_path

        # 2. 项目目录下的 hvigor/hvigorw.js
        candidate = self.project_dir / "hvigor" / "hvigorw.js"
        if candidate.exists():
            self._hvigor_path = str(candidate)
            return self._hvigor_path

        # 3. 配置文件中的路径
        cfg_hvigor = cfg.get("hvigor.path")
        if cfg_hvigor and os.path.exists(cfg_hvigor):
            self._hvigor_path = cfg_hvigor
            return self._hvigor_path

        cfg_studio = cfg.get("studio.path")
        if cfg_studio:
            candidate = os.path.join(cfg_studio, "tools", "hvigor", "bin", "hvigorw.js")
            if os.path.exists(candidate):
                self._hvigor_path = candidate
                return candidate

        # 4. DevEco Studio 默认安装路径
        system = platform.system()
        for path in _HVIGOR_PATHS.get(system, []):
            if os.path.exists(path):
                self._hvigor_path = path
                return self._hvigor_path

        # 5. DEVECO_STUDIO_HOME 环境变量
        studio_home = os.environ.get("DEVECO_STUDIO_HOME", "")
        if studio_home:
            candidate = os.path.join(studio_home, "tools", "hvigor", "bin", "hvigorw.js")
            if os.path.exists(candidate):
                self._hvigor_path = candidate
                return candidate

        return None

    def build(self, module: str = "entry@default", product: str = "default") -> subprocess.CompletedProcess:
        if not self._hvigor_path:
            raise RuntimeError(
                "未找到 hvigorw。\n"
                "  可执行: hmdev-cli config set hvigor.path \"<路径>\"\n"
                "  或:     hmdev-cli config set studio.path \"<DevEco Studio 安装目录>\""
            )

        is_node_script = self._hvigor_path.endswith(".js")
        cmd = ["node", self._hvigor_path] if is_node_script else [self._hvigor_path]
        cmd.extend(["--mode", "module", "-p", f"module={module}", "-p", f"product={product}", "assembleHap"])

        print(f"[hmdev] 构建命令: {' '.join(cmd)}")
        print(f"[hmdev] 工作目录: {self.project_dir}")
        print()

        return subprocess.run(cmd, cwd=str(self.project_dir), timeout=600)

    @staticmethod
    def find_hap(project_dir: str, module: str = "entry") -> list[str]:
        module_name = module.split("@")[0] if "@" in module else module
        base = Path(project_dir) / module_name / "build" / "default" / "outputs" / "default"
        if not base.exists():
            base = Path(project_dir) / module_name / "build" / "output" / "default"
        if not base.exists():
            return []
        return sorted([str(p) for p in base.glob("*.hap")], key=os.path.getmtime, reverse=True)


# ── HDC Tool ─────────────────────────────────────────────────────────────────

_HDC_PATHS = {
    "Windows": [
        "C:\\Program Files\\Huawei\\DevEco Studio\\sdk\\default\\openharmony\\toolchains\\bin\\hdc.exe",
        "D:\\DevEco Studio\\sdk\\default\\openharmony\\toolchains\\bin\\hdc.exe",
    ],
    "Darwin": [
        "/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/bin/hdc",
    ],
    "Linux": [
        os.path.expanduser("~/DevEco Studio/sdk/default/openharmony/toolchains/bin/hdc"),
    ],
}


class HDCTool:
    def __init__(self):
        self._hdc_path: str | None = None

    def detect(self, config: Config | None = None) -> str | None:
        cfg = config or Config()
        hdc_name = "hdc.exe" if platform.system() == "Windows" else "hdc"

        # 1. 系统 PATH
        on_path = _find_on_path(hdc_name)
        if on_path:
            self._hdc_path = on_path
            return on_path

        # 2. 配置文件中的路径
        cfg_hdc = cfg.get("hdc.path")
        if cfg_hdc and os.path.exists(cfg_hdc):
            self._hdc_path = cfg_hdc
            return self._hdc_path

        cfg_studio = cfg.get("studio.path")
        if cfg_studio:
            candidate = os.path.join(cfg_studio, "sdk", "default", "openharmony", "toolchains", "bin", hdc_name)
            if os.path.exists(candidate):
                self._hdc_path = candidate
                return candidate

        # 3. DevEco Studio 默认 SDK 路径
        system = platform.system()
        for candidate in _HDC_PATHS.get(system, []):
            if os.path.exists(candidate):
                self._hdc_path = candidate
                return candidate

        # 4. HDC_HOME 环境变量
        hdc_home = os.environ.get("HDC_HOME", "")
        if hdc_home:
            candidate = os.path.join(hdc_home, hdc_name)
            if os.path.exists(candidate):
                self._hdc_path = candidate
                return candidate

        return None

    def _run(self, args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
        if not self._hdc_path:
            raise RuntimeError(
                "未找到 hdc。\n"
                "  可执行: hmdev-cli config set hdc.path \"<路径>\"\n"
                "  或:     hmdev-cli config set studio.path \"<DevEco Studio 安装目录>\""
            )
        return subprocess.run([self._hdc_path] + args, capture_output=True, text=True, timeout=timeout)

    @staticmethod
    def succeeded(result: subprocess.CompletedProcess) -> bool:
        return result.returncode == 0 and "[Fail]" not in result.stdout and "[Fail]" not in result.stderr

    def list_devices(self) -> list[dict]:
        result = self._run(["list", "targets"])
        devices = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("[") or "Empty" in line:
                continue
            parts = line.rsplit(None, 1)
            if len(parts) == 2:
                devices.append({"id": parts[0], "status": parts[1]})
            elif parts:
                devices.append({"id": parts[0], "status": "unknown"})
        return devices

    def install_hap(self, hap_path: str, device_id: str | None = None) -> subprocess.CompletedProcess:
        args = []
        if device_id:
            args.extend(["-t", device_id])
        args.extend(["install", hap_path])
        return self._run(args, timeout=120)

    def start_app(self, bundle: str, ability: str = "EntryAbility", device_id: str | None = None) -> subprocess.CompletedProcess:
        args = []
        if device_id:
            args.extend(["-t", device_id])
        args.extend(["shell", "aa", "start", "-a", ability, "-b", bundle])
        return self._run(args, timeout=30)

    def connect_wireless(self, ip_port: str, timeout: int = 30) -> subprocess.CompletedProcess:
        return self._run(["tconn", ip_port], timeout=timeout)
