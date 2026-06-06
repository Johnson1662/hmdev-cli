#!/usr/bin/env node
/**
 * hmdev-cli — Python 运行环境管理器
 *
 * 职责:
 *   1. 自动检测系统 Python 3.10+
 *   2. 在 python/.venv 下创建虚拟环境
 *   3. 自动 pip install mcp httpx  (保留 mcp 依赖仅用于 httpx 兼容)
 *   4. 返回可执行 Python 路径供 bin 脚本使用
 */

const { spawn, execSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

const PKG_DIR = path.resolve(__dirname, '..');
const VENV_DIR = path.join(PKG_DIR, 'python', '.venv');
const SCRIPT = path.join(PKG_DIR, 'python', 'cli.py');

const TAG = '[hmdev]';

function getVenvPython() {
  return os.platform() === 'win32'
    ? path.join(VENV_DIR, 'Scripts', 'python.exe')
    : path.join(VENV_DIR, 'bin', 'python');
}

function getVenvPip() {
  const py = getVenvPython();
  return os.platform() === 'win32'
    ? path.join(VENV_DIR, 'Scripts', 'pip.exe')
    : path.join(VENV_DIR, 'bin', 'pip');
}

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

async function ensurePython() {
  const venvPy = getVenvPython();

  if (fs.existsSync(venvPy)) {
    try {
      execSync(`"${venvPy}" -c "import httpx"`, {
        encoding: 'utf-8',
        timeout: 10000,
        stdio: 'pipe',
      });
      return venvPy;
    } catch {
      // dependencies missing, reinstall
    }
  }

  const systemPy = findSystemPython();
  if (!systemPy) {
    throw new Error(
      `${TAG} 未找到 Python 3.10+。请先安装 Python: https://www.python.org/downloads/`
    );
  }

  const cleanEnv = { ...process.env, PYTHONHOME: '' };

  console.error(`${TAG} 首次运行：正在准备 Python 环境...`);

  execSync(`"${systemPy}" -m venv "${VENV_DIR}"`, {
    stdio: 'pipe',
    timeout: 60000,
    env: cleanEnv,
  });
  console.error(`${TAG} ✓ 虚拟环境已创建`);

  try {
    execSync(`"${getVenvPip()}" install --upgrade pip`, {
      stdio: 'pipe',
      timeout: 60000,
      env: cleanEnv,
    });
  } catch { /* non-fatal */ }

  console.error(`${TAG} 正在安装 Python 依赖 (httpx, rapidfuzz, jieba)...`);
  execSync(`"${getVenvPip()}" install httpx rapidfuzz jieba`, {
    stdio: 'pipe',
    timeout: 120000,
    env: cleanEnv,
  });
  console.error(`${TAG} ✓ 依赖安装完成`);

  return getVenvPython();
}

async function runPython(pythonBin, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonBin, [SCRIPT, ...args], {
      stdio: 'inherit',
      env: {
        ...process.env,
        PYTHONHOME: '',
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
      },
    });

    child.on('exit', (code) => resolve(code));
    child.on('error', (err) => reject(err));
  });
}

if (require.main === module) {
  ensurePython()
    .then((py) => {
      console.error(`${TAG} Python 就绪: ${py}`);
      process.exit(0);
    })
    .catch((err) => {
      console.error(err.message);
      process.exit(1);
    });
}

module.exports = { ensurePython, runPython };
