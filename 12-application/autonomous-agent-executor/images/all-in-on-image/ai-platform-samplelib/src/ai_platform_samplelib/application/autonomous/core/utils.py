import os
import io
import pathlib
import io
import zipfile
from typing import Union
from fastapi import UploadFile, HTTPException
import zipfile
import tempfile
from pathlib import Path
import atexit

class ExecutorUtil:
    """タスクの実行と管理に関するユーティリティ関数をまとめたクラスです。"""
    @staticmethod
    def create_temporary_zip(source_dir: Path) -> Path:
        """ディレクトリを一時的なZIPファイルに固める"""
        tmp_zip = Path(tempfile.NamedTemporaryFile(suffix=".zip", delete=False).name)
        atexit.register(lambda: tmp_zip.unlink(missing_ok=True))  # 終了時に自動削除
        with zipfile.ZipFile(tmp_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file in source_dir.rglob('*'):
                if file.is_file():
                    # source_dir からの相対パスで格納
                    zf.write(file, file.relative_to(source_dir))
        return tmp_zip

    @staticmethod
    def make_zip_from_dir(src_dir: pathlib.Path, zip_path: pathlib.Path) -> None:
        """ディレクトリ全体をzip化します（zip_path は上書き）。"""
        if not src_dir.exists() or not src_dir.is_dir():
            raise FileNotFoundError(f"Directory not found: {src_dir}")

        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in src_dir.rglob("*"):
                if not p.is_file():
                    continue
                # zip 内のパスは src_dir からの相対
                zf.write(p, arcname=str(p.relative_to(src_dir)))

    @staticmethod
    def cleanup_file(path: str) -> None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

    @staticmethod
    def get_container_logs(container, tail: int = 200) -> tuple[str, str]:
        """docker コンテナの stdout/stderr を取得して (stdout, stderr) を返します。"""
        # docker SDK の tail は str/int を受け付ける
        out = container.logs(stdout=True, stderr=False, tail=tail)
        err = container.logs(stdout=False, stderr=True, tail=tail)
        return out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")

    @staticmethod
    def extract_zip_to_dir(zip_file: Union[UploadFile, pathlib.Path], dest_dir: pathlib.Path) -> None:
        """UploadFile(API) または Path(CLI) から ZIP を展開します。"""
        
        # 1. バイナリデータの取得
        if isinstance(zip_file, pathlib.Path):
            # CLIの場合: Pathオブジェクトから直接読み込む
            with open(zip_file, "rb") as f:
                contents = f.read()
        else:
            # APIの場合: UploadFileから読み込む
            # ※同期的なread()を想定（非同期の場合は await が必要だが、通常 utils は同期的に書くことが多い）
            contents = zip_file.file.read()

        # 2. ZIPの展開
        with zipfile.ZipFile(io.BytesIO(contents)) as zip_ref:
            # Zip Slip 対策: 展開先が dest_dir の外に出ないかチェック
            for member in zip_ref.namelist():
                member_path = dest_dir / member
                if not str(member_path.resolve()).startswith(str(dest_dir.resolve())):
                    raise Exception(f"Unsafe zip member detected: {member}")
            
            zip_ref.extractall(dest_dir)
