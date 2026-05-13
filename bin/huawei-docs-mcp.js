#!/usr/bin/env node
/**
 * huawei-docs-mcp — MCP Server 入口
 *
 * 专门用于 AI 客户端（Claude Code, Cursor 等）的 MCP Server 模式。
 * 与 CLI 入口的区别是，它显式传递 "mcp" 子命令以确保进入 MCP 模式。
 *
 * 用法 (MCP 配置):
 *   "mcpServers": {
 *     "huawei-docs": {
 *       "command": "huawei-docs-mcp"
 *     }
 *   }
 */

const { ensurePython, runPython } = require('../scripts/python-runner');

async function main() {
  const pythonBin = await ensurePython();
  // 显式传入 mcp 子命令，确保进入 MCP Server 模式
  const exitCode = await runPython(pythonBin, ['mcp', ...process.argv.slice(2)]);
  process.exit(exitCode ?? 0);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
