# hmdev-cli

HarmonyOS 开发 CLI 工具 — **文档查询 + 项目构建 + 设备部署**，一行命令搞定。

```bash
npm install -g hmdev-cli
```

---

## 特性

- **文档查询** — 直接从华为官方 API 获取 13000+ 篇 HarmonyOS 开发文档
- **项目构建** — 自动检测 hvigorw，构建 HAP 产物
- **设备部署** — 通过 hdc 安装/启动应用，支持 USB 和无线调试
- **零配置** — 自动管理 Python 虚拟环境，自动安装依赖
- **跨平台** — Windows / macOS / Linux

## 安装

```bash
npm install -g hmdev-cli
```

安装后会自动创建 Python 虚拟环境并安装依赖。

## 使用方法

### 文档查询

```bash
# 查看所有文档分类索引
hmdev-cli index

# 搜索文档
hmdev-cli search ArkUI
hmdev-cli search Ability Kit
hmdev-cli search 数据管理

# 获取文档内容
hmdev-cli get https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkui-overview

# 查看分类下的文档
hmdev-cli category harmonyos-guides
hmdev-cli category 开发指南

# JSON 输出（方便脚本处理）
hmdev-cli index --json
hmdev-cli search ArkUI --json
```

### 构建与部署

```bash
# 构建 HAP（在当前项目目录）
hmdev-cli build

# 指定项目目录
hmdev-cli build --project ./MyApp

# 指定模块和产品
hmdev-cli build --module entry@default --product default

# 指定 hvigorw 路径
hmdev-cli build --hvigor "D:/DevEco Studio/tools/hvigor/bin/hvigorw.js"

# 列出已连接设备
hmdev-cli devices

# 部署 HAP 到设备（自动选择第一个设备）
hmdev-cli deploy --hap ./entry/build/default/outputs/default/entry-default-signed.hap

# 部署到指定设备并启动
hmdev-cli deploy --hap ./app.hap --device 2NP0224627054426 --start --bundle com.example.app

# 无线部署
hmdev-cli deploy --hap ./app.hap --tconn 192.168.137.215:41015 --start --bundle com.example.app

# 启动应用
hmdev-cli run --bundle com.example.app
```

### 设备连接

```bash
# 无线连接（手机开启无线调试后获取 IP:PORT）
hmdev-cli connect 192.168.1.100:41015

# 查看已连接设备
hmdev-cli devices
```

### 组合使用

```powershell
# 构建 → 部署 → 启动
hmdev-cli build --project ./MyApp && hmdev-cli deploy --start --bundle com.example.app

# 无线连接 → 部署 → 启动（一步到位）
hmdev-cli connect 192.168.1.100:41015 && hmdev-cli deploy --start --bundle com.example.app
```

## AI 技能 (Skill)

hmdev-cli 提供配套的 AI 技能，让 Claude 等 AI 助手直接学会使用该工具：

```bash
# 技能文件位于项目 hmdev-cli-skill/ 目录
hmdev-cli-skill/
├── SKILL.md       # 技能描述与使用指南
├── scripts/       # 预留：自动化脚本
└── references/    # 预留：参考文档
```

AI 加载该技能后，能自动完成文档查询、构建、部署等操作。

## 命令参考

| 命令 | 说明 |
|------|------|
| `index` | 查看所有文档索引 |
| `search <关键词>` | 搜索文档 |
| `get <URL>` | 获取文档内容（支持 `--full` 查看完整内容） |
| `category <分类>` | 查看分类下的文档列表（别名 `cat`） |
| `build` | 构建 HarmonyOS HAP |
| `deploy` | 部署 HAP 到设备 |
| `devices` | 列出已连接设备 |
| `run` | 启动应用 |
| `connect <IP:PORT>` | 无线连接设备 |

可用分类：`harmonyos-guides`（开发指南）、`harmonyos-references`（API 参考）、`harmonyos-releases`（版本说明）、`best-practices`（最佳实践）、`harmonyos-faqs`（FAQ）、`games-guides`（游戏开发）

## 工作原理

```
npm install -g hmdev-cli
         │
         ▼
  [postinstall] 自动创建 python/.venv
         │
         ▼
  pip install httpx
         │
         ▼
  hmdev-cli index ──────► Python cli.py ──► 华为官方 API
  hmdev-cli build ──────► Python cli.py ──► hvigorw (本地构建)
  hmdev-cli deploy ─────► Python cli.py ──► hdc (设备管理)
```

- Node.js 包装器负责：环境管理、进程调度
- Python 核心负责：API 调用、HTML 转文本、构建调度、设备操作
- 无需 Docker、无需浏览器

## 开发

```bash
git clone https://github.com/Johnson1662/hmdev-cli.git
cd hmdev-cli

npm install

node bin/hmdev-cli.js index
node bin/hmdev-cli.js search ArkUI
node bin/hmdev-cli.js build --project /path/to/harmonyos-project
```

## License

MIT
