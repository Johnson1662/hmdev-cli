#!/usr/bin/env node
/**
 * Huawei Docs MCP — Python 运行环境管理器
 *
 * 职责：
 *   1. 自动检测系统 Python 3.10+
 *   2. 在 python/.venv 下创建虚拟环境
 *   3. 自动 pip install mcp httpx
 *   4. 返回可执行 Python 路径供 bin 脚本使用
 *
 * 首次运行会自动安装依赖，后续直接复用 venv。
 */

const { spawn, execSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

const PKG_DIR = path.resolve(__dirname, '..');
const VENV_DIR = path.join(PKG_DIR, 'python', '.venv');
const SCRIPT = path.join(PKG_DIR, 'python', 'server.py');

/**
 * 返回当前平台下 venv 中的 Python 可执行文件路径
 */
function getVenvPython() {
  return os.platform() === 'win32'
    ? path.join(VENV_DIR, 'Scripts', 'python.exe')
    : path.join(VENV_DIR, 'bin', 'python');
}

/**
 * 返回当前平台下 venv 中的 pip 可执行文件路径
 */
function getVenvPip() {
  const py = getVenvPython();
  return os.platform() === 'win32'
    ? path.join(VENV_DIR, 'Scripts', 'pip.exe')
    : path.join(VENV_DIR, 'bin', 'pip');
}

/**
 * 查找系统级 Python 3.10+
 * 按优先级尝试常见可执行文件名
 */
function findSystemPython() {
  const candidates = os.platform() === 'win32'
    ? ['python', 'python3', 'py']
    : ['python3', 'python'];

  for (const cmd of candidates) {
    const env = { ...process.env, PYTHONHOME: '' };
    try {
      const out = execSync(
        `"${cmd}" -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')"`,
        { encoding: 'utf-8', timeout: 10000, env }
      ).trim();
      const [major, minor] = out.split('.').map(Number);
      if (major >= 3 && minor >= 10) {
        // Resolve full path
        const which = execSync(
          os.platform() === 'win32' ? `where "${cmd}"` : `which "${cmd}"`,
          { encoding: 'utf-8', timeout: 5000, env }
        ).trim().split('\n')[0];
        return which || cmd;
      }
    } catch {
      continue;
    }
  }
  return null;
}

/**
 * 确保 Python 虚拟环境就绪
 *   1. 检查 venv 是否存在且有效
 *   2. 如果不存在，创建 venv + pip install 依赖
 *   3. 返回 Python 可执行文件路径
 */
async function ensurePython() {
  const venvPy = getVenvPython();

  // 快速路径：venv 已存在且有效
  if (fs.existsSync(venvPy)) {
    try {
      execSync(`"${venvPy}" -c "import mcp, httpx"`, {
        encoding: 'utf-8',
        timeout: 10000,
        stdio: 'pipe',
      });
      return venvPy;
    } catch {
      // 依赖缺失，重新安装
    }
  }

  // 需要初始化
  const systemPy = findSystemPython();
  if (!systemPy) {
    throw new Error(
      '[huawei-docs] 未找到 Python 3.10+。请先安装 Python: https://www.python.org/downloads/'
    );
  }

  // 干净的 env，避免 PYTHONHOME 污染
  const cleanEnv = { ...process.env, PYTHONHOME: '' };

  console.error('[huawei-docs] 首次运行：正在准备 Python 环境...');

  // 创建虚拟环境
  execSync(`"${systemPy}" -m venv "${VENV_DIR}"`, {
    stdio: 'pipe',
    timeout: 60000,
    env: cleanEnv,
  });
  console.error('[huawei-docs] ✓ 虚拟环境已创建');

  // 升级 pip
  try {
    execSync(`"${getVenvPip()}" install --upgrade pip`, {
      stdio: 'pipe',
      timeout: 60000,
      env: cleanEnv,
    });
  } catch { /* 非致命 */ }

  // 安装依赖
  console.error('[huawei-docs] 正在安装 Python 依赖 (mcp, httpx)...');
  execSync(`"${getVenvPip()}" install mcp httpx`, {
    stdio: 'pipe',
    timeout: 120000,
    env: cleanEnv,
  });
  console.error('[huawei-docs] ✓ 依赖安装完成');

  return getVenvPython();
}

/**
 * 启动 Python 进程并接管 stdio
 * @param {string} pythonBin - Python 可执行文件路径
 * @param {string[]} args - 传递给 server.py 的参数
 * @returns {Promise<number>} 退出码
 */
async function runPython(pythonBin, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonBin, [SCRIPT, ...args], {
      stdio: 'inherit',
      env: {
        ...process.env,
        PYTHONHOME: '',   // 清除 Conda 污染
        PYTHONUNBUFFERED: '1',
      },
    });

    child.on('exit', (code) => resolve(code));
    child.on('error', (err) => reject(err));
  });
}

// 允许直接运行：node scripts/python-runner.js (用于 postinstall)
if (require.main === module) {
  ensurePython()
    .then((py) => {
      console.error(`[huawei-docs] Python 就绪: ${py}`);
      process.exit(0);
    })
    .catch((err) => {
      console.error(err.message);
      process.exit(1);
    });
}

module.exports = { ensurePython, runPython };
