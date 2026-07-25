# 致敬未来 · 电竞酒店联营协作系统

> 一个 Hermes Agent skill：在飞书里 @机器人 说人话，自动理解并写入电竞酒店筹备任务表格。

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Hermes Agent](https://img.shields.io/badge/Hermes-Agent-blueviolet)](https://hermes-agent.nousresearch.com)

---

## 这是什么

致敬未来集团通过联营模式开设电竞酒店。本系统管理**合同签订后到正式开业前**双方联合筹备期的协作：

- 联营投资方负责：装修清改、弱电改造、证照、场地
- 致敬未来方负责：设备采购、技术配置、运营VI、OTA上线

用户在飞书 @机器人 汇报进展（如"怡嘉店装修搞定了"），Agent 自动查询对应任务、确认后写入多维表格。

## 架构

```
用户 @飞书机器人 说话
    │ WebSocket
    ▼
Hermes Agent（本 skill 提供业务大脑）
    │ 调用 lark-cli 命令
    ▼
飞书多维表格（6表 + 250条门店专属任务）
```

## 快速开始（客户部署）

### 前置条件

1. **Hermes Agent** 已安装（`hermes --version` 可用）
2. **lark-cli** 已安装并登录：
   ```bash
   npm install -g @larksuite/cli
   lark-cli auth login  # 用有建表权限的飞书账号
   ```
3. **飞书自建应用**（在 [open.feishu.cn](https://open.feishu.cn) 创建，权限见 `templates/env.example`）

### 安装 skill

```bash
hermes skills install <your-org>/zhijing-feishu-skill
```

### 部署系统

安装后，在 Hermes 对话里说：

> **"部署智竞飞书系统"**

Agent 会自动执行：
1. 重建多维表格（6表 + 5门店 + 250任务）
2. 渲染业务 skill（替换真实 ID）
3. 安装备选工具
4. 引导填写飞书 BOT 凭证
5. 重启 gateway 生效

也可手动执行：`python3 scripts/build_bitable.py && python3 scripts/render_skill.py`

## 目录结构

```
├── SKILL.md                  # 部署向导 skill（本仓库的主 skill）
├── scripts/
│   ├── build_bitable.py      # 重建多维表格
│   ├── render_skill.py       # 渲染业务 skill（替换ID占位符）
│   └── feishu_base_tool.py   # 备选工具（结构化API调用）
├── data/                     # 门店/任务数据（无ID，纯业务内容）
├── templates/
│   ├── SKILL.md.template     # 业务 skill 模板（日常协作用的）
│   └── env.example           # 飞书凭证模板
└── references/               # 参考文档
```

## 两个 skill 的分工

| skill | 职责 | 何时活跃 |
|-------|------|---------|
| `zhijing-feishu-ops`（本仓库） | 部署/重装/维护系统 | 首次部署、重装、维护时 |
| `zhijing-hotel-ops`（部署后生成） | 日常协作（查/写任务） | 部署完成后的日常对话 |

## 安全

- **零凭证**：本仓库不含任何飞书凭证，App Secret 由客户在本地填写
- **`ids.json` 被 gitignore**：每台机器部署生成的 ID 不同，不提交
- 飞书凭证只写入客户本地 `~/.hermes/.env`

## 业务覆盖

- **5家门店**：泸州明逸、泸州怡嘉、逸尚东方（广元/绵阳/西博城）
- **7个筹备阶段**：选址立项→装修清改→设备采购→技术配置→运营VI→OTA上线→开业前检查
- **250条任务**：已逐店展开并关联，精确到每家店的具体待办

## License

MIT
