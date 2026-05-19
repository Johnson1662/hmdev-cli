#!/usr/bin/env node
/**
 * hmdev-cli — HarmonyOS 开发 CLI 入口
 *
 * 自动管理 Python 虚拟环境，透传子命令到 Python 核心。
 *
 * 用法:
 *   hmdev-cli index
 *   hmdev-cli search ArkUI
 *   hmdev-cli get <url>
 *   hmdev-cli category harmonyos-guides
 *   hmdev-cli build --project ./MyApp
 *   hmdev-cli deploy --hap ./app.hap --device 2NP...
 *   hmdev-cli devices
 *   hmdev-cli run --bundle com.example.app
 */

const { ensurePython, runPython } = require('../scripts/runner');

async function main() {
  const pythonBin = await ensurePython();
  const exitCode = await runPython(pythonBin, process.argv.slice(2));
  process.exit(exitCode ?? 0);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
