from functools import wraps
from fastmcp import FastMCP, Context
import inspect
from typing import Optional


import jwt
import os
from typing import Optional, Dict
from contextvars import ContextVar

# スレッド/タスクセーフなコンテキスト変数
current_raw_headers: ContextVar[Dict[str, str]] = ContextVar("raw_headers", default={})

def identity_aware_tool(mcp_instance: FastMCP):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # FastMCPから自動注入されたcontextを回収
            context: Optional[Context] = kwargs.pop("context", None)
            
            if not isinstance(context, Context):
                return await func(*args, **kwargs)

            # FastMCPの内部構造からリクエストオブジェクトにアクセス
            # (FastMCPのバージョンにより構造が微細に異なる場合があるため安全にアクセス)
            request_context = getattr(context, "request_context", None)
            if not request_context:
                return await func(*args, **kwargs)
            
            request = getattr(request_context, "request", None)
            if not request:
                return await func(*args, **kwargs)
            
            # --- [追加] 生ヘッダーのキャプチャ処理 ---
            # すべてのヘッダーを小文字キーの辞書に変換して保存（プロキシでの小文字化対策）
            headers = {k.lower(): v for k, v in request.headers.items()}
            current_raw_headers.set(headers)
            return await func(*args, **kwargs)

        # --- FastMCP用シグネチャ調整ロジック ---
        sig = inspect.signature(func)
        params = list(sig.parameters.values())
        if "context" not in [p.name for p in params]:
            params.append(
                inspect.Parameter(
                    "context",
                    inspect.Parameter.KEYWORD_ONLY,
                    annotation=Context,
                    default=None,
                )
            )

        setattr(wrapper, "__signature__", sig.replace(parameters=params))

        return mcp_instance.tool()(wrapper)
    return decorator
    