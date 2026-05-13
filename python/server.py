#!/usr/bin/env python3
"""
Huawei HarmonyOS Developer Docs — CLI & MCP Server

双模式工具（通过 npm 包 huawei-docs-mcp 安装）：
  huawei-docs index              查看文档索引
  huawei-docs search <关键词>      搜索文档
  huawei-docs get <URL>          获取文档内容
  huawei-docs category <分类>     查看分类下的文档
  huawei-docs mcp                启动 MCP 服务器（默认）

安装方式（无需克隆仓库）：
  npm install -g huawei-docs-mcp

Uses Huawei's official internal REST APIs (reverse-engineered from the SPA):
  - getDocumentById: fetch doc content by slug + catalog
  - getCatalogTree: fetch navigation tree
  - getNavigationAddress: fetch breadcrumb/nav info

No Playwright or browser needed — works with plain httpx.
"""

import asyncio
import json
import re
import sys
import time
from argparse import ArgumentParser, RawDescriptionHelpFormatter, SUPPRESS
from typing import Any, Optional
from html.parser import HTMLParser

import httpx
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

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
    """Convert HTML content to clean plain text."""
    if not html:
        return ""
    parser = HTMLToText()
    parser.feed(html)
    text = parser.get_text()
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── API Functions ──────────────────────────────────────────────────────────────

async def fetch_doc(object_id: str, catalog_name: str, language: str = "cn") -> dict:
    """Fetch document content via getDocumentById API."""
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
    data = resp.json()
    return data


async def fetch_catalog_tree(catalog_name: str, object_id: str = "", language: str = "cn") -> dict:
    """Fetch navigation tree via getCatalogTree API."""
    client = get_client()
    payload = {
        "language": language,
        "catalogName": catalog_name,
    }
    if object_id:
        payload["objectId"] = object_id

    resp = await client.post(
        f"{API_BASE}/getCatalogTree",
        json=payload,
    )
    resp.raise_for_status()
    data = resp.json()
    return data


async def fetch_navigation_address(catalog_name: str, language: str = "cn") -> dict:
    """Fetch navigation address via getNavigationAddress API."""
    client = get_client()
    resp = await client.post(
        f"{API_BASE}/getNavigationAddress",
        json={
            "catalogName": catalog_name,
            "lang": language,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    return data


def extract_nav_tree(tree_data: dict) -> list[dict]:
    """Extract navigable links from the catalog tree response."""
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
    """Extract structured doc content from the API response."""
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
    """Build a complete index of all docs by fetching catalog trees."""
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


# ── MCP Server ────────────────────────────────────────────────────────────────
server = Server("huawei-docs")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_index",
            description="获取华为HarmonyOS开发文档的完整目录索引，包含所有分类及其文档列表。数据来自官方API，实时准确。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="search_docs",
            description="在华为HarmonyOS开发文档中搜索相关页面。通过分类目录和文档标题进行匹配。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词（如 'ArkUI', 'Ability Kit', '数据管理', '分布式' 等）",
                    }
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_page",
            description="获取某篇华为HarmonyOS开发文档的完整内容。通过URL来获取。",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "文档页面的URL（如 https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkui-overview）",
                    }
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="get_category",
            description="获取指定分类下的所有文档。",
            inputSchema={
                "type": "object",
                "properties": {
                    "catalog": {
                        "type": "string",
                        "description": "分类名称：开发指南(harmonyos-guides)、API参考(harmonyos-references)、最佳实践(best-practices)、FAQ(harmonyos-faqs)、版本说明(harmonyos-releases)",
                    }
                },
                "required": ["catalog"],
            },
        ),
        Tool(
            name="refresh_index",
            description="强制刷新文档索引缓存，重新从官方API获取最新数据。",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


def parse_doc_url(url: str) -> tuple[str, str]:
    """Parse a doc URL into (catalog_name, object_id)."""
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


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "get_index":
            index = await build_index()
            lines = [
                f"# 华为HarmonyOS开发文档索引",
                f"来源：华为官方API（实时获取）",
                f"更新时间：{index.get('last_updated', 'N/A')}",
                f"总计 {index['total_pages']} 篇文档",
                "",
            ]
            for cat_name, cat_info in index.get("catalogs", {}).items():
                label = cat_info.get("label", cat_name)
                count = cat_info.get("count", 0)
                lines.append(f"## {label} ({count}篇) — `{cat_name}`")
                for page in cat_info.get("first_10", []):
                    lines.append(f"- [{page['title'][:70]}]({page['url']})")
                if count > 10:
                    lines.append(f"  … 及 {count-10} 篇更多文档")
                lines.append("")
            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "search_docs":
            query = arguments.get("query", "")
            if not query:
                return [TextContent(type="text", text="请提供搜索关键词。")]

            index = await build_index()
            query_lower = query.lower()
            results = []
            seen = set()

            for page in index.get("all_pages", []):
                title = page.get("title", "").lower()
                obj_id = page.get("object_id", "").lower()
                if query_lower in title or query_lower in obj_id or query_lower in page.get("catalog_name", ""):
                    if page.get("url") not in seen:
                        seen.add(page["url"])
                        results.append(page)

            if not results:
                return [TextContent(
                    type="text",
                    text=f"未找到与 '{query}' 相关的文档。\n\n"
                         f"提示：可用的分类有 开发指南(harmonyos-guides)、API参考(harmonyos-references)、"
                         f"最佳实践(best-practices)、FAQ(harmonyos-faqs)、版本说明(harmonyos-releases)。\n"
                         f"尝试用 get_index 查看所有文档。",
                )]

            lines = [f"# 搜索结果：'{query}'", f"找到 {len(results)} 篇相关文档\n"]
            for page in results[:30]:
                catalog_label = CATALOGS.get(page.get("catalog_name", ""), page.get("catalog_name", ""))
                lines.append(f"- [{page['title'][:70]}]({page['url']}) [{catalog_label}]")
            if len(results) > 30:
                lines.append(f"\n...及另外 {len(results) - 30} 篇相关文档")

            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "get_page":
            url = arguments.get("url", "")
            if not url:
                return [TextContent(type="text", text="请提供文档URL。")]
            catalog, object_id = parse_doc_url(url)
            doc = await fetch_doc(object_id=object_id, catalog_name=catalog)
            content = extract_doc_content(doc)
            lines = [
                f"# {content['title']}",
                f"来源：{url}",
                f"分类：{CATALOGS.get(catalog, catalog)}",
                "",
                content["content"][:12000],
            ]
            if len(content["content"]) > 12000:
                lines.append("\n[内容已截断]")
            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "get_category":
            catalog = arguments.get("catalog", "")
            if not catalog:
                available = "\n".join(f"- {v} ({k})" for k, v in CATALOGS.items())
                return [TextContent(type="text", text=f"请指定分类名称。可用分类：\n{available}")]

            catalog_key = None
            for k, v in CATALOGS.items():
                if catalog == k or catalog == v or catalog in k or catalog in v:
                    catalog_key = k
                    break
            if not catalog_key:
                return [TextContent(type="text", text=f"未知分类 '{catalog}'。可用分类：\n" + "\n".join(f"- {v} ({k})" for k, v in CATALOGS.items()))]

            tree = await fetch_catalog_tree(catalog_key)
            pages = extract_nav_tree(tree)
            label = CATALOGS[catalog_key]

            lines = [f"# {label} — `{catalog_key}`", f"共 {len(pages)} 篇文档\n"]
            for page in pages:
                indent = "  " * page.get("depth", 0)
                lines.append(f"{indent}- [{page['title'][:70]}]({page['url']})")

            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "refresh_index":
            global _index_cache, _index_cache_ts
            _index_cache = None
            _index_cache_ts = 0
            index = await build_index()
            return [TextContent(type="text", text=f"✅ 索引已刷新。共 {index['total_pages']} 篇文档，{len(index['catalogs'])} 个分类。")]

        return [TextContent(type="text", text=f"未知工具：{name}")]

    except Exception as e:
        return [TextContent(type="text", text=f"错误：{type(e).__name__}: {str(e)}")]


async def mcp_main():
    """Run as MCP server (stdio)."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="huawei-docs",
                server_version="2.1.0",
                capabilities={"tools": {"listChanged": False}},
            )
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Mode
# ═══════════════════════════════════════════════════════════════════════════════

def print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


async def cmd_index(args):
    """显示所有文档分类索引"""
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
    """搜索文档"""
    index = await build_index()
    query_lower = args.query.lower()
    results = []
    seen = set()

    for page in index.get("all_pages", []):
        title = page.get("title", "").lower()
        obj_id = page.get("object_id", "").lower()
        if query_lower in title or query_lower in obj_id or query_lower in page.get("catalog_name", ""):
            if page.get("url") not in seen:
                seen.add(page["url"])
                results.append(page)

    if args.json:
        print_json({"query": args.query, "total": len(results), "results": results[:50]})
        return

    if not results:
        print(f"未找到与 '{args.query}' 相关的文档。")
        print(f"可用分类: {', '.join(f'{v}({k})' for k, v in CATALOGS.items())}")
        return

    print(f"搜索结果: '{args.query}' (共 {len(results)} 篇)\n")
    for page in results[:30]:
        cat = CATALOGS.get(page.get("catalog_name", ""), page.get("catalog_name", ""))
        print(f"  [{cat}] {page['title']}")
        print(f"         {page['url']}")
    if len(results) > 30:
        print(f"\n...及另外 {len(results) - 30} 篇")


async def cmd_get(args):
    """获取文档内容"""
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
    # If --full, show everything; otherwise first 80 lines
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
    """查看分类下的文档"""
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


CLI_COMMANDS = {
    "index": cmd_index,
    "search": cmd_search,
    "get": cmd_get,
    "category": cmd_category,
    "cat": cmd_category,  # alias
    "mcp": None,  # handled separately
}


def build_cli_parser():
    parser = ArgumentParser(
        prog="huawei-docs",
        description="华为 HarmonyOS 开发文档 CLI 工具",
        epilog="示例:\n"
               "  huawei-docs index                    查看文档索引\n"
               "  huawei-docs search ArkUI              搜索 ArkUI 相关文档\n"
               "  huawei-docs get <URL>                 获取文档内容\n"
               "  huawei-docs get --full <URL>          获取完整文档内容\n"
               "  huawei-docs category harmonyos-guides 查看分类文档\n"
               "  huawei-docs category --json 开发指南   查看分类文档 (JSON格式)\n"
               "  huawei-docs mcp                       启动 MCP 服务器",
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

    # mcp
    sub.add_parser("mcp", help="启动 MCP 服务器")

    return parser


async def cli_main():
    parser = build_cli_parser()
    args = parser.parse_args()

    if args.command == "mcp" or args.command is None:
        await mcp_main()
        return

    cmd_func = CLI_COMMANDS.get(args.command)
    if cmd_func:
        await cmd_func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    # Heuristic: if any arg is -h/--help, or first non-program-name arg is a
    # known CLI subcommand, run in CLI mode.  Otherwise default to MCP mode
    # so existing tools (Claude Code, Command Code) keep working unchanged.
    known_cli = {"index", "search", "get", "category", "cat", "mcp"}
    args = sys.argv[1:]

    if "-h" in args or "--help" in args or (args and args[0] in known_cli):
        asyncio.run(cli_main())
    else:
        asyncio.run(mcp_main())
