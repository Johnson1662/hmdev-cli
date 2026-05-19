---
name: hmdev-cli
description: >
  HarmonyOS 开发 CLI 工具 — 文档查询、项目构建、设备部署、配置管理。
  当用户需要搜索/获取华为 HarmonyOS 开发文档、构建 HAP、部署应用到真机、管理连接设备、或配置 DevEco Studio 工具路径时使用。
  关键字触发：HarmonyOS、鸿蒙、构建、部署、hvigor、hdc、HAP、hmdev。
---

# hmdev-cli — HarmonyOS 开发 CLI

## 快速安装

```bash
npm install -g hmdev-cli
```

首次运行自动创建 Python 虚拟环境并安装依赖。

## 文档查询

构建、部署前查阅官方文档：

```bash
# 搜索文档（模糊匹配标题和 ID）
hmdev-cli search ArkUI

# 获取文档完整内容
hmdev-cli get https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/arkui-overview

# 查看分类索引
hmdev-cli index

# JSON 输出（方便脚本处理）
hmdev-cli search Ability Kit --json
```

## 构建 HAP

```bash
# 在当前项目目录构建
hmdev-cli build

# 指定项目目录
hmdev-cli build --project ./MyHarmonyApp

# 指定模块和产品
hmdev-cli build --module entry@default --product default

# 显式指定 hvigorw 路径（跳过自动检测）
hmdev-cli build --hvigor "D:/DevEco Studio/tools/hvigor/bin/hvigorw.js"
```

构建成功后会自动扫描输出目录定位 HAP 产物。

## 设备管理

```bash
# 无线连接设备（手机开启开发者选项→无线调试后获取 IP:PORT）
hmdev-cli connect 192.168.1.100:41015

# 查看已连接设备
hmdev-cli devices

# 未连接时自动用第一个设备
```

10s 超时保护，连接失败时有排查提示。

## 部署

```bash
# 部署最新构建产物到第一个设备
hmdev-cli deploy

# 指定 HAP 文件和设备
hmdev-cli deploy --hap ./entry-default-signed.hap --device 2NP0224627054426

# 无线连接 + 部署 + 启动（一步到位）
hmdev-cli connect 192.168.1.100:41015 && hmdev-cli deploy --start --bundle com.example.app
```

## 配置

当工具路径（hvigorw/hdc）无法自动检测时：

```bash
# 查看所有配置
hmdev-cli config

# 设置 DevEco Studio 安装目录（自动推导 hvigor/hdc）
hmdev-cli config --set studio.path "D:\DevEco Studio"

# 或直接指定具体工具路径
hmdev-cli config --set hvigor.path "D:/DevEco Studio/tools/hvigor/bin/hvigorw.js"

# 查看单个配置
hmdev-cli config --get hvigor.path

# 重置
hmdev-cli config --reset studio.path
```

配置存储在 `~/.hmdev/config.json`。检测优先级：CLI 参数 > 配置文件 > PATH > 默认路径 > 环境变量。

## 命令参考

| 命令 | 功能 |
|------|------|
| `index` | 文档索引 |
| `search <词>` | 搜索文档 |
| `get <URL>` | 获取文档 |
| `category <分类>` | 分类文档 |
| `build` | 构建 HAP |
| `deploy` | 部署到设备 |
| `devices` | 列出设备 |
| `run --bundle <名>` | 启动应用 |
| `connect <IP:PORT>` | 无线连接 |
| `config` | 管理配置 |

## 自动检测逻辑

**hvigorw 检测顺序：**
1. 项目目录下的 `hvigorw`/`hvigorw.bat`
2. 项目目录下的 `hvigor/hvigorw.js`
3. Config 文件中的 `hvigor.path` 或 `studio.path`
4. DevEco Studio 默认安装路径
5. `DEVECO_STUDIO_HOME` 环境变量

**hdc 检测顺序：**
1. 系统 PATH
2. Config 文件中的 `hdc.path` 或 `studio.path`
3. DevEco Studio 默认 SDK 路径
4. `HDC_HOME` 环境变量
