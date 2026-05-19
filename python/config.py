"""
hmdev-cli — 配置管理

存储位置: ~/.hmdev/config.json
优先级: CLI参数 > 配置文件 > 系统PATH/项目 > DevEco Studio默认路径 > 环境变量
"""

import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".hmdev"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_KEYS = {
    "node.path": "",
    "studio.path": "",
    "hvigor.path": "",
    "hdc.path": "",
}

_KEYS_HELP = {
    "node.path": "Node.js 可执行文件路径（如 C:\\Program Files\\nodejs\\node.exe）",
    "studio.path": "DevEco Studio 安装目录（如 D:\\DevEco Studio）",
    "hvigor.path": "hvigorw.js 路径（如 D:\\DevEco Studio\\tools\\hvigor\\bin\\hvigorw.js）",
    "hdc.path": "hdc 可执行文件路径（如 D:\\DevEco Studio\\sdk\\...\\toolchains\\bin\\hdc.exe）",
}


class Config:
    def __init__(self):
        self._data: dict[str, str] = {}
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._loaded = True
        self._data = dict(DEFAULT_KEYS)
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                self._data.update(raw)
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, key: str) -> str:
        self._ensure_loaded()
        return self._data.get(key, "")

    def set(self, key: str, value: str):
        if key not in DEFAULT_KEYS:
            raise KeyError(f"未知配置项: {key}。可用: {', '.join(DEFAULT_KEYS)}")
        self._ensure_loaded()
        self._data[key] = value
        self._save()

    def reset(self, key: str):
        if key not in DEFAULT_KEYS:
            raise KeyError(f"未知配置项: {key}。可用: {', '.join(DEFAULT_KEYS)}")
        self._ensure_loaded()
        self._data[key] = ""
        self._save()

    def get_all(self) -> dict[str, str]:
        self._ensure_loaded()
        return dict(self._data)

    @staticmethod
    def keys_help() -> dict[str, str]:
        return dict(_KEYS_HELP)

    @staticmethod
    def config_path() -> str:
        return str(CONFIG_PATH)
