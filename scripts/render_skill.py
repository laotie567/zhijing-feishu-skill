#!/usr/bin/env python3
"""用 ids.json 渲染业务 skill 模板，安装到 ~/.hermes/skills/zhijing-hotel-ops/。

读取 ids.json（build_bitable.py 生成），把 templates/SKILL.md.template 里的
占位符（{{BASE_TOKEN}} 等）替换成真实 ID，输出为业务 skill。

用法：python3 scripts/render_skill.py
"""
import json
import os
import re
import shutil
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)  # skill 根目录
IDS_PATH = os.path.join(SKILL_ROOT, "ids.json")
TEMPLATE_PATH = os.path.join(SKILL_ROOT, "templates", "SKILL.md.template")
BUSINESS_SKILL_NAME = "zhijing-hotel-ops"
DEST_DIR = os.path.expanduser(f"~/.hermes/skills/{BUSINESS_SKILL_NAME}")


def main():
    # 1. 检查 ids.json
    if not os.path.isfile(IDS_PATH):
        print(f"❌ 找不到 {IDS_PATH}")
        print("   请先运行: python3 scripts/build_bitable.py")
        sys.exit(1)

    ids = json.load(open(IDS_PATH))

    # 2. 检查模板
    if not os.path.isfile(TEMPLATE_PATH):
        print(f"❌ 找不到模板 {TEMPLATE_PATH}")
        sys.exit(1)
    content = open(TEMPLATE_PATH, encoding="utf-8").read()

    # 3. 占位符 → 真实 ID 映射
    mapping = {
        "{{BASE_TOKEN}}": ids["base_token"],
        "{{BASE_URL}}": ids.get("url", ""),
        "{{TABLE_STORES}}": ids["tables"]["stores"],
        "{{TABLE_TASKS}}": ids["tables"]["tasks"],
        "{{TABLE_DELIVERABLES}}": ids["tables"]["deliverables"],
        "{{TABLE_MILESTONES}}": ids["tables"]["milestones"],
        "{{TABLE_ROLES}}": ids["tables"]["roles"],
        "{{TABLE_MEMBERS}}": ids["tables"]["members"],
        "{{STORE_MINGYI_ID}}": ids["store_records"]["明逸"],
        "{{STORE_YIJIA_ID}}": ids["store_records"]["怡嘉"],
        "{{STORE_GUANGYUAN_ID}}": ids["store_records"]["广元"],
        "{{STORE_MIANYANG_ID}}": ids["store_records"]["绵阳"],
        "{{STORE_XIBOCHENG_ID}}": ids["store_records"]["西博城"],
    }

    count = 0
    for placeholder, real_id in mapping.items():
        n = content.count(placeholder)
        content = content.replace(placeholder, real_id)
        count += n

    # 4. 写入业务 skill 目录
    os.makedirs(DEST_DIR, exist_ok=True)
    out_path = os.path.join(DEST_DIR, "SKILL.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    # 5. 拷贝 ids.json 到业务 skill 目录（feishu_base_tool 运行时读取）
    shutil.copy(IDS_PATH, os.path.join(DEST_DIR, "ids.json"))

    # 6. 验证无残留占位符
    leaks = re.findall(r"\{\{[A-Z_]+\}\}", content)

    print(f"✅ 业务 skill 已渲染安装: {out_path}")
    print(f"   替换了 {count} 处占位符为真实 ID")
    print(f"   ids.json 已拷贝到 {DEST_DIR}/")
    if leaks:
        print(f"   ⚠️ 仍有未替换占位符: {leaks}")
    else:
        print(f"   ✓ 占位符全部替换完成")
    print(f"\n下一步: 重启 gateway 生效 → hermes gateway restart")


if __name__ == "__main__":
    main()
