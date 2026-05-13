# huawei-docs-mcp

华为 HarmonyOS 开发文档 CLI + MCP Server — **一行命令安装**，无需克隆仓库、无需手动配置 Python 环境。

```bash
npm install -g huawei-docs-mcp
```

---

## 特性

- **双模式**：既是一个命令行工具，也是一个 MCP Server（兼容 Claude Code、Cursor 等 AI 客户端）
- **零配置**：自动管理 Python 虚拟环境，自动安装依赖
- **实时数据**：直接从华为官方 API 获取文档，无需抓取网页
- **覆盖全面**：6 大分类、13000+ 篇文档（开发指南、API 参考、最佳实践、FAQ、版本说明、游戏开发）
- **跨平台**：Windows / macOS / Linux

## 使用方法

### 作为 CLI 工具

```bash
# 查看所有文档分类索引
huawei-docs index

# 搜索文档
huawei-docs search ArkUI
huawei-docs search Ability Kit
huawei-docs search 数据管理

# 获取文档内容
huawei-docs get https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkui-overview

# 查看分类下的文档
huawei-docs category harmonyos-guides
huawei-docs category 开发指南

# JSON 输出（方便脚本处理）
huawei-docs index --json
huawei-docs search ArkUI --json

# 不全局安装，直接用
npx huawei-docs-mcp index
```

### 作为 MCP Server

在 AI 客户端的 MCP 配置中添加：

**Claude Code** (`~/.claude/settings.json`):
```json
{
  "mcpServers": {
    "huawei-docs": {
      "command": "huawei-docs-mcp"
    }
  }
}
```

**Cursor** (`~/.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "huawei-docs": {
      "command": "huawei-docs-mcp"
    }
  }
}
```

然后 AI 就可以帮你搜索、查询华为开发文档了。

### 可用命令

| 命令 | 说明 |
|------|------|
| `huawei-docs index` | 查看所有文档索引 |
| `huawei-docs search <关键词>` | 搜索文档 |
| `huawei-docs get <URL>` | 获取文档内容（支持 `--full` 查看完整内容） |
| `huawei-docs category <分类>` | 查看分类下的文档列表（别名 `cat`） |
| `huawei-docs mcp` | 启动 MCP Server |

可用分类：`harmonyos-guides`（开发指南）、`harmonyos-references`（API 参考）、`harmonyos-releases`（版本说明）、`best-practices`（最佳实践）、`harmonyos-faqs`（FAQ）、`games-guides`（游戏开发）

## 工作原理

```
npm install -g huawei-docs-mcp
         │
         ▼
  [postinstall] 自动创建 python/.venv
         │
         ▼
  pip install mcp httpx
         │
         ▼
  huawei-docs index ──────► Python server.py ──► 华为官方 API
                                                    │
  Claude Code ──► huawei-docs-mcp ──► MCP stdio ──► 文档内容
```

- Node.js 包装器负责：环境管理、进程调度、跨平台兼容
- Python 核心负责：API 调用、HTML 转文本、索引构建
- 无需 Docker、无需浏览器、无需手动 pip install

## 开发

```bash
git clone https://github.com/Johnson1662/huawei-docs-mcp.git
cd huawei-docs-mcp

# 安装依赖（自动创建 venv）
npm install

# 本地测试
node bin/huawei-docs.js index
node bin/huawei-docs.js search ArkUI
```

## License

MIT
