from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from urllib.parse import quote
from xmlrpc.client import ServerProxy

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from unoserver.client import UnoClient # type: ignore


DEFAULT_OUTPUT_EXTENSION = "pdf"

app = FastAPI(title="LibreOffice UNO Convert API", version="1.0.0")


def _build_client() -> UnoClient:
    return UnoClient(
        server=os.environ.get("UNOSERVER_XMLRPC_HOST", "127.0.0.1"),
        port=os.environ.get("UNOSERVER_XMLRPC_PORT", "2003"),
        host_location=os.environ.get("UNOSERVER_HOST_LOCATION", "remote"),
        protocol=os.environ.get("UNOSERVER_XMLRPC_PROTOCOL", "http"),
    )


def _normalize_extension(value: str | None) -> str:
    normalized = (value or DEFAULT_OUTPUT_EXTENSION).strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="convert_to must not be empty")
    return normalized.lstrip(".")


def _build_download_filename(original_filename: str | None, convert_to: str) -> str:
    original_name = original_filename or "converted"
    source_path = Path(original_name)
    stem = source_path.stem or "converted"
    return f"{stem}.{convert_to}"


@app.get("/health")
def healthcheck() -> JSONResponse:
    try:
        with ServerProxy(
            f"{os.environ.get('UNOSERVER_XMLRPC_PROTOCOL', 'http')}://"
            f"{os.environ.get('UNOSERVER_XMLRPC_HOST', '127.0.0.1')}:"
            f"{os.environ.get('UNOSERVER_XMLRPC_PORT', '2003')}",
            allow_none=True,
        ) as proxy:
            info = proxy.info()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"unoserver unavailable: {exc}") from exc
    return JSONResponse({"status": "ok", "unoserver": info})


@app.post("/convert")
async def convert_document(
    file: UploadFile = File(...),
    convert_to: str = Form(DEFAULT_OUTPUT_EXTENSION),
    filter_name: str | None = Form(None),
    update_index: bool = Form(True),
    input_filter: str | None = Form(None),
    password: str | None = Form(None),
) -> Response:
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="uploaded file is empty")

    output_extension = _normalize_extension(convert_to)

    try:
        converted = _build_client().convert(
            indata=payload,
            convert_to=output_extension,
            filtername=filter_name,
            update_index=update_index,
            infiltername=input_filter,
            password=password,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"conversion failed: {exc}") from exc

    media_type = mimetypes.guess_type(f"result.{output_extension}")[0] or "application/octet-stream"
    download_name = _build_download_filename(file.filename, output_extension)
    encoded_name = quote(download_name, safe="")
    # filename= には latin-1 で表現できる ASCII フォールバック名のみ使用し、
    # 日本語等は filename*=UTF-8''... (RFC 5987) で渡す
    ascii_name = Path(download_name).stem.encode("ascii", errors="replace").decode("ascii") + f".{output_extension}"
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{encoded_name}"
        )
    }
    return Response(content=converted, media_type=media_type, headers=headers)