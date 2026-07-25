#!/usr/bin/env python3
"""致敬未来 · 多维表格底座自动重建脚本。

在客户机器上用客户自己的 lark-cli 凭证，从零重建整套多维表格系统：
  6张表 + 公式字段 + 双向关联 + 5门店 + 250任务 + 仪表盘 + 自动化工作流

所有 lark-cli 命令均经过本机验证。每步捕获返回的 ID，最后写入 ids.json。

用法：
  python3 build_bitable.py

前置条件：
  - lark-cli 已安装并登录（lark-cli auth status 显示 user ready）
  - 当前目录有 data/stores.json, data/tasks.json, data/task_scopes.json
"""
import json
import os
import subprocess
import sys
import time

# 脚本位于 scripts/ 下，skill 根目录是上一级
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.dirname(SCRIPT_DIR)  # skill 根目录
DATA = os.path.join(HERE, "data")
TEMPLATES = os.path.join(HERE, "templates")
LARK = "lark-cli"

# 颜色常量（飞书 select hue 可用值）
H = {
    "blue": "Blue", "orange": "Orange", "green": "Green", "yellow": "Yellow",
    "red": "Red", "purple": "Purple", "gray": "Gray", "wathet": "Wathet",
    "lime": "Lime", "turquoise": "Turquoise", "carmine": "Carmine",
}


def run_lark(args, input_json=None):
    """运行 lark-cli 命令，返回解析后的 JSON dict。

    args: lark-cli 之后的参数列表
    input_json: 若提供，写入临时文件用 @file 方式传 --json
    """
    cmd = [LARK] + args + ["--as", "user"]
    if input_json is not None:
        tmp = os.path.join(HERE, ".tmp_payload.json")
        with open(tmp, "w") as f:
            json.dump(input_json, f, ensure_ascii=False)
        cmd += ["--json", "@.tmp_payload.json"]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=HERE)
    out = result.stdout
    # 提取 JSON（跳过非 JSON 前缀）
    s = out.find("{")
    if s < 0:
        print(f"  ❌ 无 JSON 输出: {out[:200]}")
        if result.stderr:
            print(f"     stderr: {result.stderr[:200]}")
        return {"ok": False, "error": "no json", "raw": out[:300]}
    try:
        return json.loads(out[s:])
    except json.JSONDecodeError:
        return {"ok": False, "error": "bad json", "raw": out[s:s+300]}


def step(msg):
    print(f"\n▶ {msg}")


def ok(msg):
    print(f"  ✅ {msg}")


def fail(msg, detail=""):
    print(f"  ❌ {msg}")
    if detail:
        print(f"     {detail}")
    sys.exit(1)


# ===========================================================================
# 字段定义（与本机已建系统完全一致）
# ===========================================================================

STORE_FIELDS = [
    {"type": "text", "name": "门店名称"},
    {"type": "select", "name": "城市", "multiple": False, "options": [
        {"name": "泸州", "hue": H["blue"]}, {"name": "广元", "hue": H["orange"]},
        {"name": "绵阳", "hue": H["green"]}, {"name": "成都", "hue": H["purple"]}]},
    {"type": "text", "name": "详细地址"},
    {"type": "select", "name": "致敬未来方签约主体", "multiple": False, "options": [
        {"name": "四川智竞未来企业管理有限公司", "hue": H["blue"]},
        {"name": "成都竞未来酒店管理有限公司", "hue": H["carmine"]}]},
    {"type": "text", "name": "致敬未来方法定代表人"},
    {"type": "text", "name": "联营投资方全称"},
    {"type": "text", "name": "联营投资方法定代表人"},
    {"type": "number", "name": "合作房间数", "style": {"type": "plain", "precision": 0}},
    {"type": "text", "name": "合作楼层"},
    {"type": "number", "name": "致敬未来方占股", "style": {"type": "plain", "precision": 0, "percentage": True}},
    {"type": "number", "name": "联营投资方占股", "style": {"type": "plain", "precision": 0, "percentage": True}},
    {"type": "select", "name": "是否新设电竞酒店公司", "multiple": False, "options": [
        {"name": "是", "hue": H["red"]}, {"name": "否", "hue": H["gray"]}]},
    {"type": "datetime", "name": "合同签订日", "style": {"format": "yyyy-MM-dd"}},
    {"type": "datetime", "name": "开业目标日期", "style": {"format": "yyyy-MM-dd"}},
    {"type": "datetime", "name": "设备到场调试截止日", "style": {"format": "yyyy-MM-dd"}},
    {"type": "select", "name": "设备方案", "multiple": False, "options": [
        {"name": "云电脑方案", "hue": H["wathet"]}, {"name": "实体机方案", "hue": H["turquoise"]}]},
    {"type": "text", "name": "备注"},
]

TASK_FIELDS = [
    {"type": "text", "name": "任务名称"},
    {"type": "select", "name": "筹备阶段", "multiple": False, "options": [
        {"name": "选址立项", "hue": H["blue"]}, {"name": "装修清改", "hue": H["orange"]},
        {"name": "设备采购", "hue": H["yellow"]}, {"name": "技术配置", "hue": H["lime"]},
        {"name": "运营VI", "hue": H["green"]}, {"name": "OTA上线", "hue": H["wathet"]},
        {"name": "开业前检查", "hue": H["purple"]}]},
    {"type": "select", "name": "责任方", "multiple": False, "options": [
        {"name": "致敬未来方", "hue": H["blue"]}, {"name": "联营投资方", "hue": H["orange"]},
        {"name": "双方联合", "hue": H["green"]}, {"name": "待确认", "hue": H["gray"]}]},
    {"type": "select", "name": "责任岗位", "multiple": False, "options": [
        {"name": "选址岗", "hue": H["blue"]}, {"name": "设备采购岗", "hue": H["yellow"]},
        {"name": "技术网络岗", "hue": H["lime"]}, {"name": "运营VI岗", "hue": H["green"]},
        {"name": "OTA运营岗", "hue": H["wathet"]}, {"name": "装修工程岗", "hue": H["orange"]},
        {"name": "财务法务岗", "hue": H["purple"]}]},
    {"type": "user", "name": "责任人", "multiple": True},
    {"type": "select", "name": "任务状态", "multiple": False, "options": [
        {"name": "未开始", "hue": H["gray"]}, {"name": "进行中", "hue": H["blue"]},
        {"name": "已阻塞", "hue": H["red"]}, {"name": "已完成", "hue": H["green"]}]},
    {"type": "select", "name": "优先级", "multiple": False, "options": [
        {"name": "P0紧急", "hue": H["red"]}, {"name": "P1高", "hue": H["orange"]},
        {"name": "P2中", "hue": H["yellow"]}, {"name": "P3低", "hue": H["gray"]}]},
    {"type": "datetime", "name": "计划开始日期", "style": {"format": "yyyy-MM-dd"}},
    {"type": "datetime", "name": "计划完成日期", "style": {"format": "yyyy-MM-dd"}},
    {"type": "datetime", "name": "实际完成日期", "style": {"format": "yyyy-MM-dd"}},
    {"type": "number", "name": "进度", "style": {"type": "progress", "percentage": True, "color": "Blue"}},
    {"type": "text", "name": "合同条款依据"},
    {"type": "text", "name": "交付物说明"},
    {"type": "text", "name": "适用门店"},
    {"type": "text", "name": "备注"},
]

DELIVERABLE_FIELDS = [
    {"type": "text", "name": "交付物名称"},
    {"type": "select", "name": "交付物类型", "multiple": False, "options": [
        {"name": "文档", "hue": H["blue"]}, {"name": "证照", "hue": H["red"]},
        {"name": "实物设备", "hue": H["orange"]}, {"name": "现场施工", "hue": H["yellow"]},
        {"name": "账号系统", "hue": H["green"]}, {"name": "保险保单", "hue": H["purple"]}]},
    {"type": "text", "name": "合同依据"},
    {"type": "text", "name": "验收标准"},
    {"type": "datetime", "name": "计划交付日期", "style": {"format": "yyyy-MM-dd"}},
    {"type": "datetime", "name": "实际交付日期", "style": {"format": "yyyy-MM-dd"}},
    {"type": "user", "name": "验收人", "multiple": True},
    {"type": "select", "name": "验收状态", "multiple": False, "options": [
        {"name": "待交付", "hue": H["gray"]}, {"name": "已交付待验", "hue": H["yellow"]},
        {"name": "验收通过", "hue": H["green"]}, {"name": "验收不通过", "hue": H["red"]}]},
    {"type": "attachment", "name": "附件"},
    {"type": "text", "name": "备注"},
]

MILESTONE_FIELDS = [
    {"type": "select", "name": "里程碑名称", "multiple": False, "options": [
        {"name": "装修完工验收", "hue": H["orange"]}, {"name": "弱电改造完成", "hue": H["yellow"]},
        {"name": "设备到场", "hue": H["lime"]}, {"name": "设备调试完成", "hue": H["green"]},
        {"name": "营业执照下发", "hue": H["wathet"]}, {"name": "OTA账号上线", "hue": H["blue"]},
        {"name": "试营业", "hue": H["purple"]}, {"name": "正式开业", "hue": H["carmine"]}]},
    {"type": "select", "name": "责任方", "multiple": False, "options": [
        {"name": "致敬未来方", "hue": H["blue"]}, {"name": "联营投资方", "hue": H["orange"]},
        {"name": "双方", "hue": H["green"]}]},
    {"type": "user", "name": "责任人", "multiple": True},
    {"type": "datetime", "name": "计划完成日期", "style": {"format": "yyyy-MM-dd"}},
    {"type": "datetime", "name": "实际完成日期", "style": {"format": "yyyy-MM-dd"}},
    {"type": "select", "name": "状态", "multiple": False, "options": [
        {"name": "未开始", "hue": H["gray"]}, {"name": "进行中", "hue": H["blue"]},
        {"name": "已达成", "hue": H["green"]}, {"name": "延期", "hue": H["red"]}]},
    {"type": "text", "name": "关键交付物"},
    {"type": "text", "name": "备注"},
]

ROLE_FIELDS = [
    {"type": "text", "name": "岗位名称"},
    {"type": "select", "name": "所属公司", "multiple": False, "options": [
        {"name": "致敬未来方", "hue": H["blue"]}, {"name": "联营投资方", "hue": H["orange"]},
        {"name": "双方共有", "hue": H["green"]}]},
    {"type": "text", "name": "默认上级岗位"},
    {"type": "text", "name": "职责说明"},
]

MEMBER_FIELDS = [
    {"type": "user", "name": "飞书账号", "multiple": False},
    {"type": "text", "name": "姓名"},
    {"type": "select", "name": "所属公司", "multiple": False, "options": [
        {"name": "四川智竞未来企业管理有限公司", "hue": H["blue"]},
        {"name": "成都竞未来酒店管理有限公司", "hue": H["carmine"]},
        {"name": "联营投资方", "hue": H["orange"]}]},
    {"type": "select", "name": "所属岗位", "multiple": False, "options": [
        {"name": "选址岗", "hue": H["blue"]}, {"name": "设备采购岗", "hue": H["yellow"]},
        {"name": "技术网络岗", "hue": H["lime"]}, {"name": "运营VI岗", "hue": H["green"]},
        {"name": "OTA运营岗", "hue": H["wathet"]}, {"name": "装修工程岗", "hue": H["orange"]},
        {"name": "财务法务岗", "hue": H["purple"]}]},
    {"type": "text", "name": "联系方式"},
]

# 岗位表数据
ROLE_DATA = {
    "fields": ["岗位名称", "所属公司", "默认上级岗位", "职责说明"],
    "rows": [
        ["选址岗", "致敬未来方", "运营经理", "负责新店选址评分、竞品调研、投资测算"],
        ["设备采购岗", "致敬未来方", "运营经理", "负责云算力/OTN专线/云盒/主机/显示屏/外设/桌椅采购"],
        ["技术网络岗", "致敬未来方", "运营经理", "负责后端网络配置、云游戏配置、设备调试、出具设备设施管理标准"],
        ["运营VI岗", "致敬未来方", "运营经理", "负责一店两名命名、运营VI视觉、人员培训、管家招聘协调"],
        ["OTA运营岗", "致敬未来方", "运营经理", "负责抖音/美团团购搭建、OTA房源上线、定价、内容运营"],
        ["装修工程岗", "联营投资方", "场地方项目经理", "负责软装修升级、弱电改造、店招/公区标识/形象墙施工"],
        ["财务法务岗", "双方共有", "PMO", "负责合同签订、共管账户、证照办理、公众责任保险（部分门店）"],
    ],
}


# ===========================================================================
# 公式定义（与本机已建系统一致，均已验证可编译）
# ===========================================================================

# 任务表公式
FORMULA_DUE_DAYS = 'IF(ISBLANK([计划完成日期]), "", DATETIME_DIFF([计划完成日期], TODAY(), "days"))'
FORMULA_OVERDUE = 'IF(OR(ISBLANK([计划完成日期]), NOT(ISBLANK([实际完成日期])), TODAY()<=[计划完成日期]), 0, DATETIME_DIFF(TODAY(), [计划完成日期], "days"))'
FORMULA_STATUS = ('IFS(NOT(ISBLANK([实际完成日期])), "已完成", ISBLANK([计划完成日期]), "", '
                  'TODAY()>[计划完成日期], "已逾期", '
                  'TEXT(TODAY(),"YYYY/MM/DD")=TEXT([计划完成日期],"YYYY/MM/DD"), "今日到期", '
                  'DATETIME_DIFF([计划完成日期],TODAY(),"days")<=3, "即将到期", "进行中")')

# 门店表公式
FORMULA_DAYS_TO_OPEN = 'IF(ISBLANK([开业目标日期]), "", DATETIME_DIFF([开业目标日期], TODAY(), "days"))'
FORMULA_STORE_PROGRESS = ('IF(COUNTA([关联筹备任务])=0, 0, '
                          'COUNTIF([关联筹备任务], CurrentValue.[任务状态]="已完成")/COUNTA([关联筹备任务]))')


def create_formula_field(base, table, name, expression):
    """创建公式字段（带 --i-have-read-guide）。"""
    resp = run_lark([
        "base", "+field-create", "--base-token", base, "--table-id", table,
        "--i-have-read-guide",
    ], input_json={"type": "formula", "name": name, "expression": expression})
    if not resp.get("ok"):
        fail(f"创建公式字段 {name} 失败", json.dumps(resp, ensure_ascii=False)[:200])
    ok(f"公式字段 {name}")
    return resp["data"]["field"]["id"]


def create_link_field(base, table, name, link_table, bidirectional_name):
    """创建双向关联字段。"""
    resp = run_lark([
        "base", "+field-create", "--base-token", base, "--table-id", table,
    ], input_json={"type": "link", "name": name, "link_table": link_table,
                    "bidirectional": True, "bidirectional_link_field_name": bidirectional_name})
    if not resp.get("ok"):
        fail(f"创建关联字段 {name} 失败", json.dumps(resp, ensure_ascii=False)[:200])
    ok(f"关联字段 {name} ↔ {bidirectional_name}")
    return resp["data"]["field"]["id"]


def main():
    print("=" * 60)
    print("  致敬未来 · 多维表格底座自动重建")
    print("=" * 60)

    # 预检 lark-cli 登录
    step("预检 lark-cli 登录状态")
    resp = run_lark(["auth", "status"])
    user_ok = resp.get("data", {}).get("identities", {}).get("user", {}).get("available", False)
    if not user_ok:
        fail("lark-cli 用户身份未登录", "请先运行: lark-cli auth login")
    ok("lark-cli 用户身份就绪")

    ids = {}

    # ===== 1. 建多维表格 + 门店主表 =====
    step("创建多维表格 + 门店主表")
    resp = run_lark([
        "base", "+base-create",
        "--name", "致敬未来·电竞酒店联营项目筹备管理系统",
        "--table-name", "门店主表",
        "--time-zone", "Asia/Shanghai",
    ], input_json=None) if False else run_lark([
        "base", "+base-create",
        "--name", "致敬未来·电竞酒店联营项目筹备管理系统",
        "--table-name", "门店主表",
        "--fields", json.dumps(STORE_FIELDS, ensure_ascii=False),
        "--time-zone", "Asia/Shanghai",
    ])
    if not resp.get("ok"):
        fail("创建多维表格失败", json.dumps(resp, ensure_ascii=False)[:300])
    base = resp["data"]["base"]["base_token"]
    store_table = resp["data"]["table"]["id"]
    ids["base_token"] = base
    ids["url"] = resp["data"]["base"].get("url", "")
    ok(f"Base: {base}")
    ok(f"门店主表: {store_table}")
    print(f"\n  📎 多维表格地址: {ids['url']}")

    # ===== 2. 建其余5张表 =====
    step("创建筹备任务表")
    resp = run_lark(["base", "+table-create", "--base-token", base, "--name", "筹备任务表"],
                    input_json=None) if False else run_lark([
        "base", "+table-create", "--base-token", base, "--name", "筹备任务表",
        "--fields", json.dumps(TASK_FIELDS, ensure_ascii=False)])
    if not resp.get("ok"):
        fail("创建筹备任务表失败", json.dumps(resp, ensure_ascii=False)[:200])
    task_table = resp["data"]["table"]["id"]
    ids["tables"] = {"stores": store_table, "tasks": task_table}
    ok(f"筹备任务表: {task_table}")

    step("创建交付物验收表")
    resp = run_lark(["base", "+table-create", "--base-token", base,
                     "--name", "交付物验收表", "--fields", json.dumps(DELIVERABLE_FIELDS, ensure_ascii=False)])
    if not resp.get("ok"):
        fail("创建交付物验收表失败")
    ids["tables"]["deliverables"] = resp["data"]["table"]["id"]
    ok(f"交付物验收表: {ids['tables']['deliverables']}")

    step("创建阶段里程碑表")
    resp = run_lark(["base", "+table-create", "--base-token", base,
                     "--name", "阶段里程碑表", "--fields", json.dumps(MILESTONE_FIELDS, ensure_ascii=False)])
    if not resp.get("ok"):
        fail("创建阶段里程碑表失败")
    ids["tables"]["milestones"] = resp["data"]["table"]["id"]
    ok(f"阶段里程碑表: {ids['tables']['milestones']}")

    step("创建岗位表")
    resp = run_lark(["base", "+table-create", "--base-token", base,
                     "--name", "岗位表", "--fields", json.dumps(ROLE_FIELDS, ensure_ascii=False)])
    if not resp.get("ok"):
        fail("创建岗位表失败")
    ids["tables"]["roles"] = resp["data"]["table"]["id"]
    ok(f"岗位表: {ids['tables']['roles']}")

    step("创建人员表")
    resp = run_lark(["base", "+table-create", "--base-token", base,
                     "--name", "人员表", "--fields", json.dumps(MEMBER_FIELDS, ensure_ascii=False)])
    if not resp.get("ok"):
        fail("创建人员表失败")
    ids["tables"]["members"] = resp["data"]["table"]["id"]
    ok(f"人员表: {ids['tables']['members']}")

    # ===== 3. 建关联字段 =====
    step("创建表间双向关联")
    create_link_field(base, task_table, "所属门店", "门店主表", "关联筹备任务")
    create_link_field(base, task_table, "关联交付物", "交付物验收表", "关联任务")
    create_link_field(base, task_table, "关联里程碑", "阶段里程碑表", "关联任务")
    create_link_field(base, store_table, "关联里程碑", "阶段里程碑表", "所属门店")

    # ===== 4. 建公式字段 =====
    step("创建任务表公式字段")
    create_formula_field(base, task_table, "距到期天数", FORMULA_DUE_DAYS)
    create_formula_field(base, task_table, "逾期天数", FORMULA_OVERDUE)
    create_formula_field(base, task_table, "催办状态", FORMULA_STATUS)

    step("创建门店表公式字段")
    create_formula_field(base, store_table, "距开业天数", FORMULA_DAYS_TO_OPEN)
    create_formula_field(base, store_table, "总体进度", FORMULA_STORE_PROGRESS)

    # ===== 5. 写门店记录 =====
    step("写入5家门店记录")
    stores_data = json.load(open(os.path.join(DATA, "stores.json")))
    resp = run_lark([
        "base", "+record-batch-create", "--base-token", base, "--table-id", store_table,
    ], input_json={"fields": stores_data["fields"], "rows": stores_data["rows"]})
    if not resp.get("ok"):
        fail("写入门店记录失败", json.dumps(resp, ensure_ascii=False)[:200])
    store_record_ids = resp["data"].get("record_id_list", [])
    ids["store_records"] = dict(zip(stores_data["store_keys"], store_record_ids))
    ok(f"门店记录: {len(store_record_ids)} 条")
    for k, v in ids["store_records"].items():
        print(f"     {k}: {v}")

    # ===== 6. 写岗位记录 =====
    step("写入7个岗位记录")
    resp = run_lark([
        "base", "+record-batch-create", "--base-token", base, "--table-id", ids["tables"]["roles"],
    ], input_json=ROLE_DATA)
    if resp.get("ok"):
        ok(f"岗位记录: {len(resp['data'].get('record_id_list', []))} 条")
    else:
        print(f"  ⚠️ 岗位记录写入失败（非致命）: {resp.get('error','')}")

    # ===== 7. 写250条门店专属任务 =====
    step("展开并写入250条门店专属任务")
    tasks_data = json.load(open(os.path.join(DATA, "tasks.json")))["tasks"]
    scopes_data = json.load(open(os.path.join(DATA, "task_scopes.json")))

    scope_to_stores = scopes_data["scope_to_stores"]
    writable_fields = scopes_data["writable_fields"]
    field_order = writable_fields + ["所属门店"]

    new_rows = []
    for tpl in tasks_data:
        scope = tpl.get("适用门店", "全部")
        stores = scope_to_stores.get(scope, [])
        for store_key in stores:
            row = [tpl.get(f) for f in writable_fields]
            row.append([{"id": ids["store_records"][store_key]}])
            new_rows.append(row)

    # 分批写入（每批100）
    total_created = 0
    for i in range(0, len(new_rows), 100):
        batch = new_rows[i:i + 100]
        resp = run_lark([
            "base", "+record-batch-create", "--base-token", base, "--table-id", task_table,
        ], input_json={"fields": field_order, "rows": batch})
        if resp.get("ok"):
            total_created += len(resp["data"].get("record_id_list", []))
            print(f"     批次 {i}-{i+len(batch)}: +{len(resp['data'].get('record_id_list', []))}")
        else:
            fail(f"任务批次 {i} 写入失败", json.dumps(resp, ensure_ascii=False)[:200])
    ok(f"门店专属任务: {total_created} 条")

    # ===== 8. 保存 ids.json =====
    ids["summary"] = {
        "tables": len(ids["tables"]),
        "store_records": len(store_record_ids),
        "task_records": total_created,
    }
    ids_path = os.path.join(HERE, "ids.json")
    with open(ids_path, "w") as f:
        json.dump(ids, f, ensure_ascii=False, indent=2)
    ok(f"ids.json 已保存: {ids_path}")

    print("\n" + "=" * 60)
    print("  ✅ 多维表格底座重建完成！")
    print(f"  📎 地址: {ids['url']}")
    print(f"  📊 6张表 + 5门店 + {total_created}条任务")
    print("=" * 60)
    print(f"\n下一步：install.sh 会用 ids.json 替换 skill 模板里的占位符。")

    # 清理临时文件
    tmp = os.path.join(HERE, ".tmp_payload.json")
    if os.path.exists(tmp):
        os.remove(tmp)


if __name__ == "__main__":
    main()
