#!/usr/bin/env node
/**
 * huawei-docs — CLI 入口
 *
 * 直接透传子命令到 Python server.py
 * 自动管理 Python 虚拟环境（首次运行自动创建）
 *
 * 用法:
 *   huawei-docs index
 *   huawei-docs search ArkUI
 *   huawei-docs get <url>
 *   huawei-docs category harmonyos-guides
 *   (无参数启动 MCP Server 模式)
 */

const { ensurePython, runPython } = require('../scripts/python-runner');

async function main() {
  const pythonBin = await ensurePython();
  const exitCode = await runPython(pythonBin, process.argv.slice(2));
  process.exit(exitCode ?? 0);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
