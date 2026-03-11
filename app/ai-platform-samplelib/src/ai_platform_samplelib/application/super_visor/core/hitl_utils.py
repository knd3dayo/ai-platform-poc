from __future__ import annotations

import json
import os
import pathlib
import re
import zipfile
from typing import Any


def build_user_input_with_context(message: str, source_dirs: list[pathlib.Path]) -> str:
    user_input = message
    normalized_sources = [p for p in source_dirs if isinstance(p, pathlib.Path)]

    if len(normalized_sources) == 1:
        source_path = normalized_sources[0]
        user_input += (
            f"\n\n[Context] 作業ディレクトリ(ホスト): {source_path.resolve()}"
            "\n[Context] executor コンテナ内の作業ディレクトリ: /workspace"
            "\n[Context] タスクでは /workspace からのパスで参照してください。"
        )
    elif len(normalized_sources) >= 2:
        listed = "\n".join([f"- {p.resolve()}" for p in normalized_sources])
        user_input += (
            "\n\n[Context] 取り込み対象(ホスト)が複数指定されています:"
            f"\n{listed}"
            "\n[Context] executor コンテナ内では /workspace/inputs/<name>/... に配置されます。"
            "\n[Context] タスクでは /workspace からのパスで参照してください。"
        )

    return user_input


def extract_tasks_from_plan_text(plan_text: str, *, max_tasks: int = 50) -> list[str]:
    """Planner出力(Markdown/JSON/自然文)からサブタスク文字列を抽出する（PoC）。"""

    text = (plan_text or "").strip()
    if not text:
        return []

    def _clean_task(s: str) -> str:
        s = (s or "").strip()
        if not s:
            return ""
        m_bold = re.fullmatch(r"\*\*(.+)\*\*", s)
        if m_bold:
            s = m_bold.group(1).strip()
        m_code = re.fullmatch(r"`(.+)`", s)
        if m_code:
            s = m_code.group(1).strip()
        s = s.rstrip("：:")
        return s

    def _is_meta_task(s: str) -> bool:
        if not s:
            return True
        if s.startswith("担当エージェント"):
            return True
        if "タスクの割り振り" in s or "タスク割り振り" in s:
            return True
        return False

    def _dedupe_keep_order(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            key = item.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    # 1) JSON を最優先
    try:
        if text.lstrip().startswith("{"):
            obj = json.loads(text)
            if isinstance(obj, dict) and isinstance(obj.get("tasks"), list):
                raw_tasks = [t for t in (obj.get("tasks") or []) if isinstance(t, str)]
                cleaned = [_clean_task(t) for t in raw_tasks]
                cleaned = [t for t in cleaned if t and not _is_meta_task(t)]
                cleaned = _dedupe_keep_order(cleaned)
                return cleaned[:max_tasks]
    except Exception:
        pass

    # JSONが文章中に埋まっているケース（最初の { 〜 最後の } を雑に試す）
    try:
        start = text.find("{")
        end = text.rfind("}")
        if 0 <= start < end:
            obj = json.loads(text[start : end + 1])
            if isinstance(obj, dict) and isinstance(obj.get("tasks"), list):
                raw_tasks = [t for t in (obj.get("tasks") or []) if isinstance(t, str)]
                cleaned = [_clean_task(t) for t in raw_tasks]
                cleaned = [t for t in cleaned if t and not _is_meta_task(t)]
                cleaned = _dedupe_keep_order(cleaned)
                return cleaned[:max_tasks]
    except Exception:
        pass

    # 2) Markdown/自然文: 「タスクリスト」セクションのトップレベル項目だけ拾う
    start_markers = ("タスクリスト", "タスク一覧", "task list", "tasks")
    stop_markers = ("タスクの割り振り", "タスク割り振り", "割り振り", "担当エージェント")

    def _extract_top_level_items(lines: list[str], *, require_tasks_section: bool) -> list[str]:
        in_tasks_section = not require_tasks_section
        collected: list[str] = []

        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped:
                continue

            normalized = stripped.lstrip("#").strip()
            if not in_tasks_section and any(m in normalized.lower() for m in start_markers):
                in_tasks_section = True
                continue
            if in_tasks_section and any(m in normalized for m in stop_markers):
                break
            if not in_tasks_section:
                continue

            # ネストした箇条書き（インデントあり）は爆発しやすいので捨てる
            leading_spaces = len(raw_line) - len(raw_line.lstrip(" "))
            if leading_spaces >= 2:
                continue

            m_num = re.match(r"^\s*\d+[\.|\)]\s+(.+)$", raw_line)
            if m_num:
                task = _clean_task(m_num.group(1))
                if task and not _is_meta_task(task):
                    collected.append(task)
            else:
                m_bullet = re.match(r"^\s*[-\*]\s+(.+)$", raw_line)
                if m_bullet:
                    task = _clean_task(m_bullet.group(1))
                    if task and not _is_meta_task(task):
                        collected.append(task)

            if len(collected) >= max_tasks:
                break

        return collected

    lines = text.splitlines()
    tasks = _extract_top_level_items(lines, require_tasks_section=True)
    if not tasks:
        tasks = _extract_top_level_items(lines, require_tasks_section=False)

    tasks = _dedupe_keep_order(tasks)
    if tasks:
        return tasks[:max_tasks]

    return [text]


def raw_summary_from_results(*, results: list[dict[str, Any]], max_parallel: int) -> str:
    lines: list[str] = []
    lines.append(f"逐次実行の結果サマリ (max_parallel={max_parallel}):")
    for i, item in enumerate(results, start=1):
        task = item.get("task")
        tool_name = item.get("tool")
        elapsed = item.get("elapsed_sec")
        res = item.get("result")
        status = res.get("status") if isinstance(res, dict) else None
        stdout = res.get("stdout") if isinstance(res, dict) else None
        tail = ""
        if isinstance(stdout, str) and stdout.strip():
            tail = stdout.strip().splitlines()[-1]
        lines.append(
            f"{i}. task={task!s} tool={tool_name!s} elapsed={elapsed!s}s status={status!s} last={tail!s}"
        )
    return "\n".join(lines)


def session_default_dir(source_dirs: list[pathlib.Path]) -> pathlib.Path:
    base = (source_dirs[0] if source_dirs else pathlib.Path.cwd()).resolve()
    return base / ".sv_sessions"


def session_file_path(session_dir: pathlib.Path, session_id: str) -> pathlib.Path:
    return session_dir / f"sv_hitl_{session_id}.json"


def safe_extract_zip(zip_path: str, dest_dir: pathlib.Path) -> pathlib.Path:
    """ZIP を dest_dir に安全に展開して、展開先ディレクトリを返す。"""

    dest_dir.mkdir(parents=True, exist_ok=True)
    base = dest_dir.resolve()

    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue

            target = (dest_dir / member.filename).resolve()
            if not str(target).startswith(str(base) + os.sep) and target != base:
                raise ValueError(f"Unsafe zip entry path: {member.filename}")

        zf.extractall(dest_dir)

    return dest_dir
