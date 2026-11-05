"""Feishu Base (Bitable) Tools -- read/write the 智竞未来 project-management Base.

Provides tools for searching tasks, reading records, updating task fields,
and listing stores/pending work in a Feishu Bitable.  Uses the same
lazy-import + BaseRequest pattern as ``feishu_doc_tool.py``.

Base/table IDs are loaded at runtime from ``ids.json`` (install.sh copies it
next to the skill), with a ``ZHIJING_BASE_TOKEN`` env fallback -- nothing is
hard-coded to a specific tenant.  Write tools guard on the caller confirming
intent -- that is a prompt-layer convention (the agent's system prompt
enforces a "show what you'll change, then write" flow), not an identity
check: the tools do not verify who the caller is or whether they own the task.

The lark client is built per-call from ``FEISHU_APP_ID`` / ``FEISHU_APP_SECRET``
so the tools work both inside the feishu-comment event context *and* when
called directly from an agent turn (CLI, gateway, cron).
"""

import json
import logging
import os
import threading
from urllib.parse import quote

from tools.registry import registry, tool_error, tool_result

logger = logging.getLogger(__name__)

# Thread-local fallback client (set by feishu event handlers that already hold one).
_local = threading.local()


def set_client(client):
    """Store a lark client for the current thread (called by feishu handlers)."""
    _local.client = client


def get_client():
    """Return an injected client, else build one from env credentials."""
    injected = getattr(_local, "client", None)
    if injected is not None:
        return injected
    # Build from env so the tools work outside the comment-event context too.
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    if not app_id or not app_secret:
        return None
    try:
        import lark_oapi as lark
        return lark.Client.builder().app_id(app_id).app_secret(app_secret).build()
    except Exception as exc:  # pragma: no cover - import/env issues
        logger.warning("feishu_base: cannot build client: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Base identity — loaded at runtime from ids.json (written by install.sh).
# Falls back to env vars. Never hard-coded to a specific tenant.
# ---------------------------------------------------------------------------

def _load_ids():
    """Load Base/table IDs from ids.json or env. Returns dict or empty."""
    import glob
    # 1. Explicit env override
    env_base = os.environ.get("ZHIJING_BASE_TOKEN")
    if env_base:
        return {"base_token": env_base, "tables": {}, "store_records": {}}
    # 2. ids.json next to the skill, or in common deploy locations
    candidates = [
        os.path.expanduser("~/.hermes/skills/zhijing-hotel-ops/ids.json"),
        os.path.expanduser("~/zhijing-deploy/ids.json"),
    ] + glob.glob(os.path.expanduser("~/*/zhijing-deploy/ids.json"))
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
    return {}


_IDS = _load_ids()
BASE_TOKEN = _IDS.get("base_token", "")
TABLES = _IDS.get("tables", {})


def _missing_ids_error(what):
    return (
        f"{what}未加载（ids.json 缺失或不完整）。请先运行 zhijing-deploy/install.sh 或 "
        "build_bitable.py 生成 ids.json（工具从 ~/.hermes/skills/zhijing-hotel-ops/ids.json "
        "读取），或设置环境变量 ZHIJING_BASE_TOKEN 指定 Base 后重试。"
    )


# Display names for the agent-facing docs.
TABLE_LABELS = {
    "stores": "门店主表",
    "tasks": "筹备任务表",
    "deliverables": "交付物验收表",
    "milestones": "阶段里程碑表",
    "roles": "岗位表",
    "members": "人员表",
}


def _check_feishu():
    """Return True if lark_oapi is importable (cheap probe, no eager import)."""
    import importlib.util
    try:
        return importlib.util.find_spec("lark_oapi") is not None
    except (ImportError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Low-level request helper
# ---------------------------------------------------------------------------

def _do_request(client, method, uri, paths=None, queries=None, body=None):
    """Build and execute a BaseRequest; return (code, msg, data_dict)."""
    from lark_oapi import AccessTokenType
    from lark_oapi.core.enum import HttpMethod
    from lark_oapi.core.model.base_request import BaseRequest

    # Explicit method mapping -- never silently downgrade (e.g. PUT -> POST).
    _METHODS = {
        "GET": HttpMethod.GET,
        "POST": HttpMethod.POST,
        "PUT": HttpMethod.PUT,
        "PATCH": HttpMethod.PATCH,
        "DELETE": HttpMethod.DELETE,
    }
    http_method = _METHODS.get(str(method).upper())
    if http_method is None:
        raise ValueError(f"unsupported HTTP method: {method!r}")
    builder = (
        BaseRequest.builder()
        .http_method(http_method)
        .uri(uri)
        .token_types({AccessTokenType.TENANT})
    )
    if paths:
        builder = builder.paths(paths)
    if queries:
        builder = builder.queries(queries)
    if body is not None:
        builder = builder.body(json.dumps(body, ensure_ascii=False).encode("utf-8"))
    resp = client.request(builder.build())

    code = getattr(resp, "code", None)
    msg = getattr(resp, "msg", "")
    data = {}
    raw = getattr(resp, "raw", None)
    if raw is not None and getattr(raw, "content", None):
        try:
            data = json.loads(raw.content).get("data", {}) or {}
        except (json.JSONDecodeError, AttributeError):
            data = {}
    if not data:
        data = getattr(resp, "data", {}) or {}
    return code, msg, data


def _query_records(client, table_key, field_names, conditions=None, limit=50, sort=None):
    """GET /records with a v3 filter query. Returns (code, msg, items_list).

    conditions: list of [field, op, value] triples (v3 filter shape).
    sort: list of {"field":..., "desc":...}.
    Field projection uses repeated `field_id` query params (v3 wire format
    has no projection parameter other than that), built by hand.
    """
    params = [("limit", str(limit)), ("offset", "0")]
    params += [("field_id", f) for f in field_names]
    if conditions:
        params.append(("filter", json.dumps(
            {"logic": "and", "conditions": conditions},
            ensure_ascii=False, separators=(",", ":"))))
    if sort:
        params.append(("sort", json.dumps(
            [{"field": s.get("field"), "desc": bool(s.get("desc", False))} for s in sort],
            ensure_ascii=False, separators=(",", ":"))))
    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params)
    table_id = TABLES.get(table_key, "")
    if not table_id:
        return -1, _missing_ids_error(f"表 {table_key} 的 table id"), []
    code, msg, data = _do_request(
        client, "GET",
        f"/open-apis/base/v3/bases/{BASE_TOKEN}/tables/{table_id}/records?{query}",
    )
    if code != 0:
        return code, msg, []
    items = data.get("items") or data.get("records") or []
    return code, msg, items


# ---------------------------------------------------------------------------
# Cell value decoding -- Bitable returns select/user/datetime as nested lists
# ---------------------------------------------------------------------------

def _decode_cell(val):
    """Flatten a Bitable cell value into a plain Python value for display."""
    if val is None:
        return None
    # select: [{"text": "已完成"}] or [{"name": "已完成"}]
    if isinstance(val, list):
        if not val:
            return None
        parts = []
        for item in val:
            if isinstance(item, dict):
                parts.append(item.get("text") or item.get("name") or str(item))
            else:
                parts.append(str(item))
        return parts[0] if len(parts) == 1 else parts
    if isinstance(val, dict):
        return val.get("text") or val.get("name") or str(val)
    return val


def _decode_record(record, fields):
    """Turn one raw record into {field: readable_value}, keeping only requested fields."""
    raw_fields = record.get("fields", {}) if isinstance(record, dict) else {}
    out = {"record_id": record.get("record_id", "")}
    for f in fields:
        out[f] = _decode_cell(raw_fields.get(f))
    return out


# ---------------------------------------------------------------------------
# Store keyword -> 门店主表 record_id resolution
# ---------------------------------------------------------------------------

def _resolve_store_record_id(keyword: str):
    """Resolve a store keyword to its 门店主表 record_id.

    Returns ``(record_id, error)``; exactly one of the two is None.

    Matching is done on the short keys of ``ids.json["store_records"]``
    (明逸/怡嘉/广元/绵阳/西博城), so both short names ("怡嘉") and contract
    full names ("逸尚东方酒店（广元店）") resolve.  There is deliberately NO
    fuzzy-text fallback: an unmatched keyword is an error, never a text search
    on the link field (business rule in SKILL.md: match by record_id).
    """
    store_records = _IDS.get("store_records") or {}
    if not store_records:
        return None, (
            "门店映射未加载（ids.json 缺少 store_records）——请先完成部署"
            "（zhijing-deploy/install.sh 或 build_bitable.py 会生成 ids.json），"
            "在此之前无法按门店精确查询。"
        )
    kw = (keyword or "").strip()
    if not kw:
        return None, "门店关键词为空。"
    hits = [key for key in store_records if key in kw or kw in key]
    if not hits:
        return None, (
            f"未找到门店「{kw}」。本工具只认已部署的 {len(store_records)} 家门店: "
            f"{'、'.join(store_records)}（简称或合同全称均可），不支持任意文本模糊匹配。"
        )
    if len(hits) > 1:
        return None, (
            f"门店关键词「{kw}」同时匹配多店: {'、'.join(hits)}，请用更精确的名称。"
        )
    key = hits[0]
    record_id = store_records.get(key) or ""
    if not record_id:
        return None, f"门店「{key}」的 record_id 为空，ids.json 不完整，请重新部署。"
    return record_id, None


# ===========================================================================
# Tool 1: search_tasks
# ===========================================================================

SEARCH_TASKS_SCHEMA = {
    "name": "search_tasks",
    "description": (
        "搜索筹备任务表中的任务。按门店、筹备阶段、责任方、任务状态、责任岗位等条件筛选。"
        "用户汇报进展时，先用此工具查到具体任务，再决定如何更新。"
        "至少提供一个筛选条件；门店名须是已部署5家门店的简称或合同全称（如 '怡嘉'、'逸尚东方酒店（广元店）'），工具会解析为 record_id 精确匹配。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "store": {
                "type": "string",
                "description": "门店简称或合同全称，如 '怡嘉'、'逸尚东方酒店（广元店）'。可省略。",
            },
            "stage": {
                "type": "string",
                "description": "筹备阶段，可选值：选址立项/装修清改/设备采购/技术配置/运营VI/OTA上线/开业前检查。可省略。",
            },
            "responsible_party": {
                "type": "string",
                "description": "责任方，可选值：智竞未来方/联营投资方/双方联合/待确认。可省略。",
            },
            "status": {
                "type": "string",
                "description": "任务状态，可选值：未开始/进行中/已阻塞/已完成。可省略。",
            },
            "keyword": {
                "type": "string",
                "description": "任务名称关键词，如 '装修'、'OTN'、'调试'。可省略。",
            },
            "limit": {
                "type": "integer",
                "description": "返回条数上限，默认20。",
            },
        },
        "required": [],
    },
}


def _handle_search_tasks(args: dict, **kwargs) -> str:
    client = get_client()
    if client is None:
        return tool_error("Feishu client 未配置（缺少 FEISHU_APP_ID/SECRET）")

    # v3 filter uses [field, op, value] triples.
    # select: "==" exact match; text: "intersects" for contains;
    # link (所属门店): "==" on the store record_id (see _resolve_store_record_id).
    conditions = []
    store = args.get("store", "").strip()
    stage = args.get("stage", "").strip()
    party = args.get("responsible_party", "").strip()
    status = args.get("status", "").strip()
    keyword = args.get("keyword", "").strip()
    limit = min(int(args.get("limit") or 20), 100)

    if stage:
        conditions.append(["筹备阶段", "==", stage])
    if party:
        conditions.append(["责任方", "==", party])
    if status:
        conditions.append(["任务状态", "==", status])
    if store:
        # 所属门店 is a link field: resolve the keyword to the store's
        # record_id and match exactly (business rule: use record_id).
        store_record_id, store_err = _resolve_store_record_id(store)
        if store_err:
            return tool_error(store_err)
        conditions.append(["所属门店", "==", store_record_id])
    if keyword:
        conditions.append(["任务名称", "intersects", [keyword]])

    field_names = [
        "任务名称", "筹备阶段", "责任方", "责任岗位", "责任人",
        "任务状态", "计划完成日期", "实际完成日期", "催办状态", "逾期天数",
        "合同条款依据", "适用门店", "所属门店", "优先级", "备注",
    ]
    code, msg, items = _query_records(
        client, "tasks", field_names,
        conditions=conditions or None, limit=limit,
    )
    if code != 0:
        return tool_error(f"搜索失败: code={code} msg={msg}")

    decoded = [_decode_record(r, field_names) for r in items]
    return tool_result(
        success=True,
        count=len(decoded),
        tasks=decoded,
        hint="已返回匹配的任务。更新前请向用户确认要改哪条、改哪些字段。",
    )


# ===========================================================================
# Tool 2: get_task
# ===========================================================================

GET_TASK_SCHEMA = {
    "name": "get_task",
    "description": "按 record_id 获取单条筹备任务的完整详情（含所有字段）。",
    "parameters": {
        "type": "object",
        "properties": {
            "record_id": {"type": "string", "description": "任务的 record_id（rec 开头）"},
        },
        "required": ["record_id"],
    },
}


def _handle_get_task(args: dict, **kwargs) -> str:
    client = get_client()
    if client is None:
        return tool_error("Feishu client 未配置")
    rid = args.get("record_id", "").strip()
    if not rid:
        return tool_error("record_id 必填")

    tasks_table = TABLES.get("tasks", "")
    if not tasks_table:
        return tool_error(_missing_ids_error("筹备任务表 table id"))
    code, msg, data = _do_request(
        client, "GET",
        f"/open-apis/base/v3/bases/{BASE_TOKEN}/tables/{tasks_table}/records/{rid}",
    )
    if code != 0:
        return tool_error(f"获取失败: code={code} msg={msg}")
    record = data.get("record") or data
    raw_fields = record.get("fields", {}) if isinstance(record, dict) else {}
    decoded = {k: _decode_cell(v) for k, v in raw_fields.items()}
    return tool_result(success=True, record_id=rid, fields=decoded)


# ===========================================================================
# Tool 3: update_task
# ===========================================================================

UPDATE_TASK_SCHEMA = {
    "name": "update_task",
    "description": (
        "更新一条筹备任务的字段。常见更新：任务状态、实际完成日期、计划开始/完成日期、备注、进度。"
        "【重要】写入前必须先向用户确认要改的内容，用户同意后再调用本工具。"
        "select 字段值用选项名数组（如 任务状态=[\"已完成\"]）；日期用 'YYYY-MM-DD' 字符串。"
        "注意：本工具不校验调用者是否为该任务的「责任人」（无可靠的调用者身份），"
        "越权防护仅依赖可更新字段白名单与写入前的用户确认。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "record_id": {"type": "string", "description": "任务的 record_id（rec 开头）"},
            "updates": {
                "type": "object",
                "description": (
                    "要更新的字段键值对。键为字段名，值为目标值。例如 "
                    '{"任务状态":["已完成"],"实际完成日期":"2026-07-25","备注":"..."}。'
                    "可更新字段：任务状态/计划开始日期/计划完成日期/实际完成日期/进度/备注/优先级。"
                ),
            },
            "change_summary": {
                "type": "string",
                "description": "本次变更的中文摘要，用于审计日志（必填）。",
            },
        },
        "required": ["record_id", "updates", "change_summary"],
    },
}

# Allowed mutable fields + their kinds, to prevent accidental writes to
# formula/link/system fields.
_MUTABLE_FIELDS = {
    "任务状态": "select",
    "计划开始日期": "datetime",
    "计划完成日期": "datetime",
    "实际完成日期": "datetime",
    "进度": "number",
    "备注": "text",
    "优先级": "select",
}


def _encode_value(field, value):
    """Encode a plain Python value into the Bitable cell-write format."""
    kind = _MUTABLE_FIELDS.get(field)
    if kind is None:
        return None  # caller rejects unknown fields
    if value is None or value == "":
        return None
    if kind == "select":
        return value if isinstance(value, list) else [value]
    if kind == "datetime":
        # Bitable accepts "YYYY-MM-DD" or "YYYY-MM-DD HH:mm:ss".
        return value
    if kind == "number":
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    return value  # text


def _handle_update_task(args: dict, **kwargs) -> str:
    client = get_client()
    if client is None:
        return tool_error("Feishu client 未配置")
    rid = args.get("record_id", "").strip()
    updates = args.get("updates") or {}
    summary = args.get("change_summary", "").strip()
    if not rid:
        return tool_error("record_id 必填")
    if not updates:
        return tool_error("updates 不能为空")
    if not summary:
        return tool_error("change_summary 必填（用于审计）")

    # Guardrails, honest scope: (1) mutable-field whitelist below;
    # (2) prompt-layer "confirm before write" convention.
    # This tool does NOT verify the caller's identity, nor whether the caller
    # is the task's 责任人 -- requests here carry no verifiable end-user
    # identity.  Ownership checks can only be enabled once the 责任人 field
    # is actually assigned (currently blank on all tasks); implementing one
    # without that identity source would be security theater.
    # Guard: only allow known mutable fields.
    rejected = {k for k in updates if k not in _MUTABLE_FIELDS}
    if rejected:
        return tool_error(
            f"以下字段不可更新（公式/关联/系统字段或未知字段）: {list(rejected)}。"
            f"可更新字段: {list(_MUTABLE_FIELDS.keys())}"
        )

    fields_payload = {}
    for k, v in updates.items():
        encoded = _encode_value(k, v)
        if encoded is not None:
            fields_payload[k] = encoded

    tasks_table = TABLES.get("tasks", "")
    if not tasks_table:
        return tool_error(_missing_ids_error("筹备任务表 table id"))
    code, msg, data = _do_request(
        client, "PATCH",
        f"/open-apis/base/v3/bases/{BASE_TOKEN}/tables/{tasks_table}/records/{rid}",
        body=fields_payload,
    )
    if code != 0:
        return tool_error(f"更新失败: code={code} msg={msg}")
    return tool_result(
        success=True,
        record_id=rid,
        updated_fields=list(fields_payload.keys()),
        change_summary=summary,
        hint="更新已写入。建议告知用户该门店下一项待办。",
    )


# ===========================================================================
# Tool 4: list_my_pending
# ===========================================================================

LIST_PENDING_SCHEMA = {
    "name": "list_my_pending",
    "description": (
        "查询未完成的筹备任务（可选按门店、责任方过滤），用于在记录进展后向用户反馈下一步待办。"
        "默认按筹备阶段排序，便于看出当前在哪个阶段、下一步该做什么。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "store": {"type": "string", "description": "门店简称或合同全称，如 '怡嘉'、'逸尚东方酒店（广元店）'。可省略查全部。"},
            "responsible_party": {
                "type": "string",
                "description": "责任方：智竞未来方/联营投资方。可省略。",
            },
            "stage": {"type": "string", "description": "限定某个筹备阶段。可省略。"},
        },
        "required": [],
    },
}


def _handle_list_my_pending(args: dict, **kwargs) -> str:
    client = get_client()
    if client is None:
        return tool_error("Feishu client 未配置")

    # status != 已完成  (v3 supports "!=" on select)
    conditions = [["任务状态", "!=", "已完成"]]
    store = args.get("store", "").strip()
    party = args.get("responsible_party", "").strip()
    stage = args.get("stage", "").strip()
    if store:
        # Same rule as search_tasks: record_id exact match, never fuzzy text.
        store_record_id, store_err = _resolve_store_record_id(store)
        if store_err:
            return tool_error(store_err)
        conditions.append(["所属门店", "==", store_record_id])
    if party:
        conditions.append(["责任方", "==", party])
    if stage:
        conditions.append(["筹备阶段", "==", stage])

    field_names = [
        "任务名称", "筹备阶段", "责任方", "责任岗位", "任务状态",
        "计划完成日期", "优先级", "催办状态", "所属门店",
    ]
    code, msg, items = _query_records(
        client, "tasks", field_names,
        conditions=conditions, limit=50,
        sort=[{"field": "筹备阶段", "desc": False}],
    )
    if code != 0:
        return tool_error(f"查询失败: code={code} msg={msg}")
    decoded = [_decode_record(r, field_names) for r in items]
    return tool_result(
        success=True,
        count=len(decoded),
        pending=decoded,
        hint="这些是未完成的任务，按筹备阶段排序。可向用户反馈下一步待办。",
    )


# ===========================================================================
# Tool 5: list_stores
# ===========================================================================

LIST_STORES_SCHEMA = {
    "name": "list_stores",
    "description": "列出所有联营门店及其进度概览（门店名/城市/占股/是否新设公司/总体进度/距开业天数）。",
    "parameters": {"type": "object", "properties": {}, "required": []},
}


def _handle_list_stores(args: dict, **kwargs) -> str:
    client = get_client()
    if client is None:
        return tool_error("Feishu client 未配置")
    field_names = [
        "门店名称", "城市", "智竞未来方签约主体", "联营投资方全称",
        "合作房间数", "智竞未来方占股", "是否新设电竞酒店公司",
        "合同签订日", "开业目标日期", "距开业天数", "总体进度", "备注",
    ]
    code, msg, items = _query_records(client, "stores", field_names, limit=20)
    if code != 0:
        return tool_error(f"查询失败: code={code} msg={msg}")
    decoded = [_decode_record(r, field_names) for r in items]
    return tool_result(success=True, count=len(decoded), stores=decoded)


# ===========================================================================
# Registration
# ===========================================================================

_FEISHU_ENV = ["FEISHU_APP_ID", "FEISHU_APP_SECRET"]

registry.register(
    name="search_tasks",
    toolset="feishu_base",
    schema=SEARCH_TASKS_SCHEMA,
    handler=_handle_search_tasks,
    check_fn=_check_feishu,
    requires_env=_FEISHU_ENV,
    is_async=False,
    description="搜索筹备任务表",
    emoji="\U0001F50D",
)

registry.register(
    name="get_task",
    toolset="feishu_base",
    schema=GET_TASK_SCHEMA,
    handler=_handle_get_task,
    check_fn=_check_feishu,
    requires_env=_FEISHU_ENV,
    is_async=False,
    description="获取单条任务详情",
    emoji="\U0001F4CB",
)

registry.register(
    name="update_task",
    toolset="feishu_base",
    schema=UPDATE_TASK_SCHEMA,
    handler=_handle_update_task,
    check_fn=_check_feishu,
    requires_env=_FEISHU_ENV,
    is_async=False,
    description="更新任务字段（需先确认）",
    emoji="\u270F\uFE0F",
)

registry.register(
    name="list_my_pending",
    toolset="feishu_base",
    schema=LIST_PENDING_SCHEMA,
    handler=_handle_list_my_pending,
    check_fn=_check_feishu,
    requires_env=_FEISHU_ENV,
    is_async=False,
    description="查询未完成任务（下一步待办）",
    emoji="\U0001F4C5",
)

registry.register(
    name="list_stores",
    toolset="feishu_base",
    schema=LIST_STORES_SCHEMA,
    handler=_handle_list_stores,
    check_fn=_check_feishu,
    requires_env=_FEISHU_ENV,
    is_async=False,
    description="列出门店及进度",
    emoji="\U0001F3E8",
)
