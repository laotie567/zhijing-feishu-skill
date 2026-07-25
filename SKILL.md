---
name: zhijing-feishu-ops
version: 1.0.0
description: "致敬未来电竞酒店联营项目筹备协作系统。两个职责：(1)首次部署——重建飞书多维表格(6表+250任务)、安装配套工具、配置飞书BOT凭证；(2)日常协作——用户在飞书@机器人汇报进展，自动查询并写入筹备任务表格。涉及电竞酒店筹备/门店任务/飞书多维表格时使用。"
metadata:
  requires:
    bins: ["python3"]
  cliHelp: "lark-cli base --help"
---

# 致敬未来 · 电竞酒店联营筹备协作

> 本 skill 有两个阶段：**首次部署**（建系统）和**日常协作**（用系统）。
> 首次部署只需做一次；之后都是日常协作。

---

## 阶段一：首次部署（仅执行一次）

### 何时进入部署模式

当用户说"部署/安装/初始化智竞系统"、"建飞书表格"、"开始部署"等，进入部署流程。

### 部署前置条件（先确认，缺什么补什么）

逐项检查，缺了就引导用户补：

1. **lark-cli 是否安装并登录**（部署的核心依赖）
   ```bash
   lark-cli auth status
   ```
   - 未安装 → 提示 `npm install -g @larksuite/cli`
   - 未登录 → 提示 `lark-cli auth login`（用有建表权限的飞书账号扫码）
   - 已登录（user available）→ 继续

2. **飞书自建应用凭证**（部署飞书BOT需要）
   询问用户是否已有 App ID 和 App Secret。没有则引导到 https://open.feishu.cn 创建（权限清单见 `templates/env.example`）。

### 部署步骤（按顺序执行）

#### 步骤 1：重建多维表格底座

运行建表脚本（脚本会自动建 6 张表 + 写 5 门店 + 展开 250 条任务 + 建公式/关联）：

```bash
python3 {SKILL_DIR}/scripts/build_bitable.py
```

脚本结束时会在 skill 根目录生成 `ids.json`（记录所有表 ID 和门店 record_id）。**记住它打印的多维表格 URL**，后续要告诉用户。

> 如果脚本报错，常见原因：lark-cli 登录过期（重新 `lark-cli auth login`）。脚本幂等，可重跑。

#### 步骤 2：用真实 ID 生成业务 skill

部署产生的 Base ID 和门店 record_id 是全新的，要回填到日常协作用的指令里。运行：

```bash
python3 {SKILL_DIR}/scripts/render_skill.py
```

这个脚本读 `ids.json`，把 `templates/SKILL.md.template` 里的占位符（`{{BASE_TOKEN}}` 等）替换成真实 ID，生成最终的 `~/.hermes/skills/zhijing-hotel-ops/SKILL.md`（这是日常协作用的业务 skill）。

> 说明：本部署 skill（zhijing-feishu-ops）负责建系统；建好后日常对话用的是另一个业务 skill（zhijing-hotel-ops）。两个 skill 分工：部署 skill 管建，业务 skill 管用。

#### 步骤 3：安装备选工具

```bash
cp {SKILL_DIR}/scripts/feishu_base_tool.py ~/.hermes/hermes-agent/tools/
cp {SKILL_DIR}/ids.json ~/.hermes/skills/zhijing-hotel-ops/
```

#### 步骤 4：配置飞书 BOT 凭证

读取用户提供的 App ID / App Secret，写入 `~/.hermes/.env`（追加，勿覆盖已有内容）：

```bash
cat >> ~/.hermes/.env << 'EOF'
FEISHU_APP_ID=<用户提供的>
FEISHU_APP_SECRET=<用户提供的>
FEISHU_DOMAIN=feishu
FEISHU_CONNECTION_MODE=websocket
FEISHU_GROUP_POLICY=open
FEISHU_ALLOW_ALL_USERS=true
EOF
```

凭证模板和权限清单见 `templates/env.example`。

#### 步骤 5：重启 gateway 生效

```bash
hermes gateway restart
```

#### 步骤 6：部署完成确认

向用户报告：
- 多维表格地址（从 ids.json 读 url）
- 提示在飞书 @机器人 测试："怡嘉店装修搞定了"
- 提示后续日常对话会由 zhijing-hotel-ops skill 接管

---

## 阶段二：日常协作（部署后由 zhijing-hotel-ops 接管）

> ⚠️ 日常协作的业务逻辑、术语映射、查询命令都在 `templates/SKILL.md.template` 里。
> 部署完成后，那个文件会被渲染成 `~/.hermes/skills/zhijing-hotel-ops/SKILL.md`，届时由它接管日常对话。
> 本部署 skill 只在"部署/重装/维护"场景激活。

### 维护场景（本 skill 仍可处理）

- **"重建表格"** → 重新跑步骤1（会创建新 Base，旧的不删）
- **"更新业务规则"** → 编辑 `templates/SKILL.md.template` 后重跑步骤2
- **"查看部署状态"** → 读 `ids.json` 报告当前 Base ID 和各表情况
- **"重装到新机器"** → 在新机器 `hermes skills install <owner>/<repo>` 后重新走部署流程

---

## 目录结构

```
zhijing-feishu-skill/
├── SKILL.md                        ← 本文件（部署向导）
├── scripts/
│   ├── build_bitable.py            ← 重建多维表格（6表+250任务）
│   ├── render_skill.py             ← 用ids.json渲染业务skill模板
│   └── feishu_base_tool.py         ← 备选工具（结构化API）
├── data/
│   ├── stores.json                 ← 5家门店数据
│   ├── tasks.json                  ← 54条任务模板
│   └── task_scopes.json            ← 任务→门店映射
├── templates/
│   ├── SKILL.md.template           ← 业务skill模板（占位符，部署时渲染）
│   └── env.example                 ← 飞书凭证模板
└── references/
    └── deploy-details.md           ← 部署细节参考（可选）
```

---

## 重要约束

1. **凭证安全**：App Secret 只写入客户本地 `~/.hermes/.env`，绝不打印到对话、绝不提交 git。
2. **幂等性**：所有脚本可重跑。重跑会创建新资源（新 Base/新表），不会覆盖旧的。
3. **两个 skill 分工**：本 skill（zhijing-feishu-ops）管部署；业务 skill（zhijing-hotel-ops）管日常。部署完日常对话归后者。
4. **lark-cli 走 user 权限**：建表/读写都用客户登录的飞书账号身份，权限跟着账号走。
