#!/usr/bin/env python3
"""
hmdev-cli — HarmonyOS 开发 CLI 工具

Usage:
  hmdev-cli index              查看文档索引
  hmdev-cli search <关键词>     搜索文档
  hmdev-cli get <URL>         获取文档内容
  hmdev-cli category <分类>    查看分类文档
  hmdev-cli build             构建 HAP
  hmdev-cli deploy            部署到设备
  hmdev-cli devices           列出设备
  hmdev-cli run               启动应用
"""

import asyncio
import json
import re
import shutil
import subprocess
import subprocess
import time
from argparse import ArgumentParser, RawDescriptionHelpFormatter, SUPPRESS
from html.parser import HTMLParser
from typing import Any

import httpx
from rapidfuzz import fuzz
import jieba

from builder import HvigorTool, HDCTool
from config import Config

# ── API Configuration ─────────────────────────────────────────────────────────
API_BASE = "https://svc-drcn.developer.huawei.com/community/servlet/consumer/cn/documentPortal"
REFERER = "https://developer.huawei.com/"

CATALOGS = {
    "harmonyos-guides": "开发指南",
    "harmonyos-references": "API参考",
    "harmonyos-releases": "版本说明",
    "best-practices": "最佳实践",
    "harmonyos-faqs": "FAQ",
    "games-guides": "游戏开发",
}

# ── HTTP Client ────────────────────────────────────────────────────────────────
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Content-Type": "application/json",
                "Referer": REFERER,
            },
            timeout=30.0,
            follow_redirects=True,
        )
    return _client


# ── Simple HTML → Markdown Converter ──────────────────────────────────────────

class HTMLToText(HTMLParser):
    """Simple HTML to plain-text converter."""
    def __init__(self):
        super().__init__()
        self.lines = []
        self.current_line = ""
        self.skip_tag = 0
        self.in_pre = False
        self.in_li = False
        self.list_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ('script', 'style', 'noscript'):
            self.skip_tag += 1
        elif tag == 'br':
            self.flush_line()
        elif tag == 'p':
            self.flush_line()
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.flush_line()
            self.flush_line()
        elif tag == 'li':
            self.flush_line()
            self.current_line += "• "
        elif tag in ('ul', 'ol'):
            self.list_depth += 1
        elif tag == 'div' or tag == 'section':
            pass
        elif tag == 'pre' or tag == 'code':
            pass

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ('script', 'style', 'noscript'):
            if self.skip_tag > 0:
                self.skip_tag -= 1
        elif tag == 'p':
            self.flush_line()
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.flush_line()
        elif tag in ('li', 'ul', 'ol'):
            if tag in ('ul', 'ol'):
                self.list_depth = max(0, self.list_depth - 1)
        elif tag == 'a':
            pass

    def handle_data(self, data):
        if self.skip_tag > 0:
            return
        self.current_line += data

    def handle_entityref(self, name):
        char_map = {
            'amp': '&', 'lt': '<', 'gt': '>', 'quot': '"',
            'nbsp': ' ', 'apos': "'",
        }
        self.current_line += char_map.get(name, f'&{name};')

    def flush_line(self):
        line = self.current_line.strip()
        if line:
            self.lines.append(line)
        self.current_line = ""

    def get_text(self):
        self.flush_line()
        return '\n'.join(self.lines)


def html_to_text(html: str) -> str:
    if not html:
        return ""
    parser = HTMLToText()
    parser.feed(html)
    text = parser.get_text()
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── API Functions ──────────────────────────────────────────────────────────────

async def fetch_doc(object_id: str, catalog_name: str, language: str = "cn") -> dict:
    client = get_client()
    resp = await client.post(
        f"{API_BASE}/getDocumentById",
        json={
            "objectId": object_id,
            "version": "",
            "catalogName": catalog_name,
            "language": language,
        },
    )
    resp.raise_for_status()
    return resp.json()


async def fetch_catalog_tree(catalog_name: str, object_id: str = "", language: str = "cn") -> dict:
    client = get_client()
    payload = {"language": language, "catalogName": catalog_name}
    if object_id:
        payload["objectId"] = object_id
    resp = await client.post(f"{API_BASE}/getCatalogTree", json=payload)
    resp.raise_for_status()
    return resp.json()


async def fetch_navigation_address(catalog_name: str, language: str = "cn") -> dict:
    client = get_client()
    resp = await client.post(
        f"{API_BASE}/getNavigationAddress",
        json={"catalogName": catalog_name, "lang": language},
    )
    resp.raise_for_status()
    return resp.json()


def extract_nav_tree(tree_data: dict) -> list[dict]:
    pages = []
    value = tree_data.get("value", {})
    catalog_name = value.get("catalogName", "")
    tree_list = value.get("catalogTreeList", [])

    if not isinstance(tree_list, list):
        return pages

    def walk(node, depth=0):
        if not node or not isinstance(node, dict):
            return
        node_name = node.get("nodeName", "")
        object_id = node.get("relateDocument", "")
        children = node.get("children", [])

        if object_id and node_name and catalog_name:
            pages.append({
                "title": node_name,
                "object_id": object_id,
                "catalog_name": catalog_name,
                "depth": depth,
                "url": f"https://developer.huawei.com/consumer/cn/doc/{catalog_name}/{object_id}",
            })

        for child in (children or []):
            if isinstance(child, dict):
                walk(child, depth + 1)

    for item in tree_list:
        if isinstance(item, dict):
            walk(item, 0)

    return pages


def extract_doc_content(api_response: dict) -> dict:
    value = api_response.get("value", {})
    title = value.get("title", "未知标题")
    content_raw = (value.get("content") or {}).get("content", "")
    content_text = html_to_text(content_raw)

    metadata = {
        "title": title,
        "language": value.get("lang", ""),
        "business_name": value.get("businessName", ""),
        "version": value.get("version", ""),
        "status": value.get("status", ""),
    }

    anchors = []
    for anchor in value.get("anchorList", []):
        anchors.append({
            "id": anchor.get("anchorId", ""),
            "title": anchor.get("title", ""),
            "level": int(anchor.get("level", 0)),
        })

    return {
        "title": title,
        "content": content_text,
        "content_html": content_raw[:5000],
        "metadata": metadata,
        "anchors": anchors,
    }


# ── Index Cache ───────────────────────────────────────────────────────────────
_index_cache: dict[str, Any] | None = None
_index_cache_ts: float = 0
_CACHE_TTL = 600  # 10 minutes


async def build_index() -> dict[str, Any]:
    global _index_cache, _index_cache_ts
    now = time.time()
    if _index_cache and (now - _index_cache_ts) < _CACHE_TTL:
        return _index_cache

    all_pages = []
    catalog_info = {}

    for catalog_name, catalog_label in CATALOGS.items():
        try:
            tree_data = await fetch_catalog_tree(catalog_name)
            pages = extract_nav_tree(tree_data)
            all_pages.extend(pages)
            catalog_info[catalog_name] = {
                "label": catalog_label,
                "count": len(pages),
                "first_10": pages[:10],
            }
        except Exception as e:
            catalog_info[catalog_name] = {
                "label": catalog_label,
                "count": 0,
                "error": str(e),
            }

    result = {
        "title": "华为HarmonyOS开发文档",
        "catalogs": catalog_info,
        "all_pages": all_pages,
        "total_pages": len(all_pages),
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _index_cache = result
    _index_cache_ts = time.time()
    return result


# ── Search Ranking ─────────────────────────────────────────────────────────────

def _extract_terms(text: str) -> list[str]:
    """Split query into deduplicated terms (whitespace + jieba segmentation)."""
    raw = text.lower().strip()
    terms = []
    seen = set()
    for part in raw.split():
        for w in jieba.lcut(part):
            w = w.strip()
            if w and len(w) >= 1 and w not in seen:
                seen.add(w)
                terms.append(w)
    return terms


def _score_term(term: str, title: str, object_id: str, catalog: str) -> float:
    """Score a single query term against a document."""
    t = title.lower()
    o = object_id.lower()
    c = catalog.lower()
    q = term.lower().strip()

    s = 0.0

    # Exact substring match
    if t == q:
        s += 3.0
    elif q in t:
        s += 2.0
    if q in o:
        s += 1.0
    if q in c:
        s += 0.3

    # Fuzzy match
    s += (fuzz.partial_ratio(q, t) / 100.0) * 1.5

    return s


def compute_relevance_score(query: str, title: str, object_id: str, catalog_name: str) -> float:
    """
    Compute a relevance score for a document against the query.

    For single-term queries: exact + fuzzy + word overlap scoring.
    For multi-term  queries: per-term scoring + all-terms-matched bonus,
    so "ArkUI 组件" ranks docs containing BOTH words above those with only one.

    Higher score = more relevant.
    """
    q = query.lower().strip()
    t = title.lower()
    o = object_id.lower()
    c = catalog_name.lower()

    score = 0.0

    # ── Phase 1: Whole-phrase matching (original behavior) ──
    if t == q:
        score += 5.0
    elif t.startswith(q):
        score += 4.0
    elif q in t:
        score += 3.0

    if q in o:
        score += 1.5
    if q in c:
        score += 0.5

    score += (fuzz.partial_ratio(q, t) / 100.0) * 2.0
    score += (fuzz.token_sort_ratio(q, t) / 100.0) * 1.5
    score += (fuzz.token_set_ratio(q, t) / 100.0) * 1.0
    score += (fuzz.partial_ratio(q, o) / 100.0) * 0.8

    # ── Phase 2: Per-term scoring (multi-keyword support) ──
    terms = _extract_terms(q)
    if len(terms) <= 1:
        q_words = set(terms)  # jieba single token
        t_words = set(w for w in jieba.lcut(t) if w.strip())
        if q_words and t_words:
            common = q_words & t_words
            score += (len(common) / len(q_words)) * 2.0
            for qw in q_words:
                if len(qw) < 2:
                    continue
                for tw in t_words:
                    if tw != qw and tw.startswith(qw):
                        score += 0.5
                        break
        return score

    # Multi-term: score each term individually
    term_results = []
    for term in terms:
        ts = _score_term(term, title, object_id, catalog_name)
        term_results.append(ts)

    # Average term score + coverage bonus
    avg_term = sum(term_results) / len(terms)
    score += avg_term * 2.0

    matched_any = sum(1 for ts in term_results if ts >= 1.0)
    matched_title = sum(1 for ts in term_results if ts >= 2.0)

    # Bonus when ALL query terms appear in the title
    if len(terms) > 1 and matched_title >= len(terms):
        score += 8.0
    elif len(terms) > 1 and matched_any >= len(terms):
        score += 5.0
    elif matched_title >= 2:
        score += 3.0
    elif matched_any >= 2:
        score += 1.5

    # Coverage: fraction of terms that matched
    coverage = matched_any / len(terms)
    score += coverage * 2.0

    return score


# ── CLI Helpers ────────────────────────────────────────────────────────────────

def parse_doc_url(url: str) -> tuple[str, str]:
    url = url.split("?")[0].rstrip("/")
    for catalog in CATALOGS:
        pattern = f"/{catalog}/"
        if pattern in url:
            idx = url.find(pattern) + len(pattern)
            object_id = url[idx:]
            return catalog, object_id
    parts = url.rstrip("/").split("/")
    object_id = parts[-1] if parts else ""
    for catalog in CATALOGS:
        if catalog in url:
            return catalog, object_id
    return "harmonyos-guides", object_id


def print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


# ── CLI Commands: Docs ────────────────────────────────────────────────────────

async def cmd_index(args):
    index = await build_index()
    if args.json:
        print_json(index)
        return

    print(f"华为 HarmonyOS 开发文档索引 (共 {index['total_pages']} 篇)")
    print(f"更新时间: {index['last_updated']}\n")
    for cat_name, cat_info in index["catalogs"].items():
        label = cat_info.get("label", cat_name)
        count = cat_info.get("count", 0)
        err = cat_info.get("error")
        if err:
            print(f"  [{cat_name}] {label} — 错误: {err}")
        else:
            print(f"  [{cat_name}] {label} ({count} 篇)")
            for p in cat_info.get("first_10", []):
                print(f"    └─ {p['title'][:70]}")
                print(f"         {p['url']}")
            if count > 10:
                print(f"    … 及 {count - 10} 篇")
        print()


async def cmd_search(args):
    index = await build_index()
    query = args.query.strip()
    if not query:
        print("请提供搜索关键词。")
        return

    query_lower = query.lower()
    seen = set()
    scored = []

    for page in index.get("all_pages", []):
        title = page.get("title", "")
        obj_id = page.get("object_id", "")
        catalog = page.get("catalog_name", "")

        score = compute_relevance_score(query, title, obj_id, catalog)

        # Include if exact match exists or fuzzy score is significant
        if (query_lower in title.lower()
                or query_lower in obj_id.lower()
                or query_lower in catalog.lower()
                or score >= 1.5):
            if page.get("url") not in seen:
                seen.add(page["url"])
                page = dict(page)
                page["_score"] = round(score, 2)
                scored.append(page)

    # Sort: higher score first, shorter title as tiebreaker
    scored.sort(key=lambda p: (-p["_score"], len(p.get("title", ""))))

    if args.json:
        out = {
            "query": args.query,
            "total": len(scored),
            "results": scored[:50],
        }
        print_json(out)
        return

    if not scored:
        print(f"未找到与 '{args.query}' 相关的文档。")
        print(f"可用分类: {', '.join(f'{v}({k})' for k, v in CATALOGS.items())}")
        return

    print(f"搜索结果: '{args.query}' (共 {len(scored)} 篇)\n")
    for i, page in enumerate(scored[:30], 1):
        cat = CATALOGS.get(page.get("catalog_name", ""), page.get("catalog_name", ""))
        print(f"  [{i}] [{cat}] {page['title']}")
        print(f"       {page['url']}")
    if len(scored) > 30:
        print(f"\n...及另外 {len(scored) - 30} 篇")


async def cmd_get(args):
    catalog, object_id = parse_doc_url(args.url)
    doc = await fetch_doc(object_id=object_id, catalog_name=catalog)
    content = extract_doc_content(doc)

    if args.json:
        print_json(content)
        return

    print(f"# {content['title']}")
    print(f"分类: {CATALOGS.get(catalog, catalog)}")
    print(f"URL:  {args.url}\n")

    body = content["content"]
    if args.full:
        print(body)
    else:
        lines = body.split("\n")
        for line in lines[:80]:
            print(line)
        if len(lines) > 80:
            n_remain = sum(len(l) for l in lines[80:])
            print(f"\n[... 内容已截断, 剩余 {len(lines) - 80} 行 / ~{n_remain} 字符. 使用 --full 查看完整内容]")


async def cmd_category(args):
    catalog_key = None
    for k, v in CATALOGS.items():
        if args.catalog == k or args.catalog == v or args.catalog in k or args.catalog in v:
            catalog_key = k
            break

    if not catalog_key:
        print(f"未知分类 '{args.catalog}'")
        print(f"可用分类: {', '.join(f'{v}({k})' for k, v in CATALOGS.items())}")
        return

    tree = await fetch_catalog_tree(catalog_key)
    pages = extract_nav_tree(tree)
    label = CATALOGS[catalog_key]

    if args.json:
        print_json({"catalog": catalog_key, "label": label, "total": len(pages), "pages": pages})
        return

    print(f"{label} ({catalog_key}) — 共 {len(pages)} 篇文档\n")
    for page in pages:
        indent = "  " * page.get("depth", 0)
        print(f"{indent}  {page['title']}")
        print(f"{indent}  {page['url']}")


# ── CLI Commands: Build & Deploy ──────────────────────────────────────────────

async def cmd_build(args):
    tool = HvigorTool(args.project)
    if args.hvigor:
        tool._hvigor_path = args.hvigor
    else:
        found = tool.detect(Config())
        if not found:
            print("[hmdev] ❌ 未找到 hvigorw。请安装 DevEco Studio 或使用 --hvigor 指定路径。")
            print("   也可用配置文件指定路径: hmdev-cli config set hvigor.path \"<路径>\"")
            return

    result = tool.build(args.module, args.product)
    hap_files = HvigorTool.find_hap(args.project, args.module)

    if args.json:
        print_json({
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "hap_files": hap_files,
        })
        return

    if result.returncode == 0:
        print(f"\n[hmdev] ✅ 构建成功")
        if hap_files:
            print(f"   产物: {hap_files[0]}")
        else:
            print(f"   产物: 未找到 .hap 文件，请检查构建配置")
    else:
        print(f"\n[hmdev] ❌ 构建失败 (exit code: {result.returncode})")


async def cmd_deploy(args):
    hdc = HDCTool()
    if not hdc.detect(Config()):
        print("[hmdev] ❌ 未找到 hdc。请确保 DevEco Studio 已安装且 hdc 在 PATH 中。")
        return

    hap_path = args.hap
    if not hap_path:
        hap_files = HvigorTool.find_hap(".")
        if not hap_files:
            print("[hmdev] ❌ 未找到 HAP 文件。请使用 --hap 指定路径或先执行 build。")
            return
        hap_path = hap_files[0]
        print(f"[hmdev] 自动选择最新构建产物: {hap_path}")

    if args.tconn:
        print(f"[hmdev] 无线连接: {args.tconn}")
        tr = hdc.connect_wireless(args.tconn)
        if not HDCTool.succeeded(tr):
            print(f"[hmdev] ❌ 无线连接失败: {tr.stderr.strip()}")
            return
        print(f"[hmdev] ✅ 无线连接成功")

    device_id = args.device
    if not device_id:
        devices = hdc.list_devices()
        if not devices:
            print("[hmdev] ❌ 未检测到已连接的设备。请连接设备或使用 --device 指定。")
            return
        device_id = devices[0]["id"]
        print(f"[hmdev] 自动选择设备: {device_id}")

    print(f"[hmdev] 正在安装: {hap_path}")
    ir = hdc.install_hap(hap_path, device_id)
    if not HDCTool.succeeded(ir):
        err = ir.stderr.strip() or ir.stdout.strip()
        print(f"[hmdev] ❌ 安装失败: {err}")
        return
    print(f"[hmdev] ✅ 安装成功")

    app_started = False
    if args.start:
        bundle = args.bundle
        if not bundle:
            print("[hmdev] ⚠️ --start 需要 --bundle 参数，跳过启动")
        else:
            print(f"[hmdev] 正在启动: {bundle}")
            sr = hdc.start_app(bundle, args.ability, device_id)
            if not HDCTool.succeeded(sr):
                print(f"[hmdev] ❌ 启动失败: {sr.stderr.strip()}")
            else:
                print(f"[hmdev] ✅ 应用已启动")
                app_started = True

    if args.json:
        print_json({
            "success": True,
            "device": device_id,
            "hap": hap_path,
            "app_started": app_started,
        })


async def cmd_devices(args):
    hdc = HDCTool()
    if not hdc.detect(Config()):
        print("[hmdev] ❌ 未找到 hdc。请确保 DevEco Studio 已安装。")
        return

    devices = hdc.list_devices()
    if args.json:
        print_json({"devices": devices})
        return

    if not devices:
        print("[hmdev] 未检测到已连接的设备。")
        print("  请通过 USB 连接设备或在开发者选项中开启无线调试。")
        return

    print(f"[hmdev] 已连接设备 ({len(devices)}):\n")
    for d in devices:
        status_icon = "✅" if d["status"] == "device" else "❓"
        print(f"  {status_icon}  {d['id']}  [{d['status']}]")


async def cmd_run(args):
    hdc = HDCTool()
    if not hdc.detect(Config()):
        print("[hmdev] ❌ 未找到 hdc。请确保 DevEco Studio 已安装。")
        return

    device_id = args.device
    if not device_id:
        devices = hdc.list_devices()
        if not devices:
            print("[hmdev] ❌ 未检测到已连接的设备。")
            return
        device_id = devices[0]["id"]
        print(f"[hmdev] 自动选择设备: {device_id}")

    print(f"[hmdev] 正在启动: {args.bundle} ({args.ability})")
    sr = hdc.start_app(args.bundle, args.ability, device_id)

    if args.json:
        print_json({
            "success": sr.returncode == 0,
            "device": device_id,
            "bundle": args.bundle,
            "ability": args.ability,
        })
        return

    if sr.returncode == 0:
        print(f"[hmdev] ✅ 应用已启动")
    else:
        print(f"[hmdev] ❌ 启动失败: {sr.stderr.strip()}")


async def cmd_connect(args):
    hdc = HDCTool()
    if not hdc.detect(Config()):
        print("[hmdev] ❌ 未找到 hdc。请确保 DevEco Studio 已安装。")
        return

    address = args.address
    print(f"[hmdev] 正在连接无线设备: {address}")
    try:
        result = hdc.connect_wireless(address)
    except subprocess.TimeoutExpired:
        if args.json:
            print_json({"success": False, "address": address, "error": "连接超时"})
            return
        print(f"[hmdev] ❌ 连接超时: {address}")
        print("   请确认:")
        print("   1. 手机和电脑在同一局域网")
        print("   2. 手机已开启「开发者选项 → 无线调试」")
        print("   3. 地址格式为 IP:PORT（如 192.168.1.100:41015）")
        return

    if args.json:
        print_json({
            "success": result.returncode == 0,
            "address": address,
            "error": result.stderr.strip() if result.returncode != 0 else "",
        })
        return

    if result.returncode == 0:
        print(f"[hmdev] ✅ 连接成功: {address}")
        devices = hdc.list_devices()
        for d in devices:
            if d["id"] == address or d["status"] == "device":
                print(f"   设备: {d['id']} [{d['status']}]")
    else:
        err = result.stderr.strip() or result.stdout.strip()
        print(f"[hmdev] ❌ 连接失败: {err}")
        print("   请确认:")
        print("   1. 手机和电脑在同一局域网")
        print("   2. 手机已开启「开发者选项 → 无线调试」")
        print("   3. 地址格式为 IP:PORT（如 192.168.1.100:41015）")


# ── CLI Commands: Config ──────────────────────────────────────────────────────

async def cmd_config(args):
    cfg = Config()

    if args.get:
        key = args.get
        val = cfg.get(key)
        if val:
            print(f"{key} = {val}")
        else:
            print(f"{key} 未设置")
        return

    if args.set:
        key, value = args.set
        try:
            cfg.set(key, value)
            print(f"[hmdev] ✅ 已设置 {key} = {value}")
            print(f"   配置保存至: {Config.config_path()}")
        except KeyError as e:
            print(f"[hmdev] ❌ {e}")
        return

    if args.reset:
        key = args.reset
        try:
            cfg.reset(key)
            print(f"[hmdev] ✅ 已重置 {key}")
        except KeyError as e:
            print(f"[hmdev] ❌ {e}")
        return

    all_config = cfg.get_all()
    print(f"hmdev-cli 配置 ({Config.config_path()})\n")
    for key in sorted(all_config):
        val = all_config[key]
        help_text = Config.keys_help().get(key, "")
        if val:
            print(f"  {key} = {val}")
        else:
            print(f"  {key} = (未设置)")
        if help_text:
            print(f"    {help_text}")
        print()


async def cmd_update(args):
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        print("[hmdev] ❌ 未找到 npm。请确保 Node.js 已安装。")
        return
    print("[hmdev] 正在更新 hmdev-cli ...")
    result = subprocess.run([npm, "update", "-g", "hmdev-cli"], capture_output=True, text=True)
    if result.returncode == 0:
        print("[hmdev] ✅ 更新成功")
    else:
        err = result.stderr.strip() or result.stdout.strip()
        print(f"[hmdev] ❌ 更新失败: {err}")


# ── CLI Registration ──────────────────────────────────────────────────────────

CLI_COMMANDS = {
    "index": cmd_index,
    "search": cmd_search,
    "get": cmd_get,
    "category": cmd_category,
    "cat": cmd_category,
    "build": cmd_build,
    "deploy": cmd_deploy,
    "devices": cmd_devices,
    "run": cmd_run,
    "connect": cmd_connect,
    "config": cmd_config,
    "update": cmd_update,
}


def build_cli_parser():
    parser = ArgumentParser(
        prog="hmdev-cli",
        description="HarmonyOS 开发 CLI 工具 — 文档查询、项目构建、设备部署",
        epilog="示例:\n"
               "  hmdev-cli index                       查看文档索引\n"
               "  hmdev-cli search ArkUI                 搜索文档\n"
               "  hmdev-cli get <URL>                    获取文档内容\n"
               "  hmdev-cli build --project ./MyApp      构建 HAP\n"
               "  hmdev-cli deploy --hap ./app.hap       部署到设备\n"
               "  hmdev-cli devices                      列出设备\n"
               "  hmdev-cli run --bundle com.example.app 启动应用\n"
               "  hmdev-cli connect 192.168.1.100:41015  无线连接设备",
        formatter_class=RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # index
    p = sub.add_parser("index", help="查看所有文档分类索引")
    p.add_argument("--json", action="store_true", dest="json", help=SUPPRESS)

    # search
    p = sub.add_parser("search", help="搜索文档")
    p.add_argument("query", help="搜索关键词")
    p.add_argument("--json", action="store_true", dest="json", help=SUPPRESS)

    # get
    p = sub.add_parser("get", help="获取文档内容")
    p.add_argument("url", help="文档 URL")
    p.add_argument("--full", action="store_true", help="显示完整内容")
    p.add_argument("--json", action="store_true", dest="json", help=SUPPRESS)

    # category
    p = sub.add_parser("category", aliases=["cat"], help="查看分类下的文档")
    p.add_argument("catalog", help="分类名称（如 harmonyos-guides, 开发指南）")
    p.add_argument("--json", action="store_true", dest="json", help=SUPPRESS)

    # build
    p = sub.add_parser("build", help="构建 HarmonyOS HAP")
    p.add_argument("--project", default=".", help="项目目录（默认当前目录）")
    p.add_argument("--module", default="entry@default", help="模块名称（默认 entry@default）")
    p.add_argument("--product", default="default", help="产品（默认 default）")
    p.add_argument("--hvigor", help="hvigorw 路径（自动检测）")
    p.add_argument("--json", action="store_true", dest="json", help=SUPPRESS)

    # deploy
    p = sub.add_parser("deploy", help="部署 HAP 到设备")
    p.add_argument("--hap", help="HAP 文件路径（自动查找最新构建产物）")
    p.add_argument("--device", help="设备 UDID 或无线地址（默认使用第一个设备）")
    p.add_argument("--tconn", help="无线连接地址 (IP:PORT)")
    p.add_argument("--start", action="store_true", help="安装后启动应用")
    p.add_argument("--bundle", help="应用 Bundle 名称")
    p.add_argument("--ability", default="EntryAbility", help="Ability 名称（默认 EntryAbility）")
    p.add_argument("--json", action="store_true", dest="json", help=SUPPRESS)

    # devices
    p = sub.add_parser("devices", help="列出已连接设备")
    p.add_argument("--json", action="store_true", dest="json", help=SUPPRESS)

    # run
    p = sub.add_parser("run", help="启动应用")
    p.add_argument("--bundle", required=True, help="应用 Bundle 名称")
    p.add_argument("--ability", default="EntryAbility", help="Ability 名称（默认 EntryAbility）")
    p.add_argument("--device", help="设备 UDID 或无线地址（默认使用第一个设备）")
    p.add_argument("--json", action="store_true", dest="json", help=SUPPRESS)

    # connect
    p = sub.add_parser("connect", help="无线连接设备 (hdc tconn)")
    p.add_argument("address", help="设备无线调试地址 (IP:PORT)")
    p.add_argument("--json", action="store_true", dest="json", help=SUPPRESS)

    # config
    p = sub.add_parser("config", help="查看或修改配置")
    p.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"), help="设置配置项")
    p.add_argument("--get", metavar="KEY", help="查看单个配置项")
    p.add_argument("--reset", metavar="KEY", help="重置配置项")
    p.add_argument("--json", action="store_true", dest="json", help=SUPPRESS)

    # update
    p = sub.add_parser("update", help="更新 hmdev-cli 到最新版本 (npm update -g)")
    p.add_argument("--json", action="store_true", dest="json", help=SUPPRESS)

    return parser


async def cli_main():
    parser = build_cli_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    cmd_func = CLI_COMMANDS.get(args.command)
    if cmd_func:
        await cmd_func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(cli_main())
