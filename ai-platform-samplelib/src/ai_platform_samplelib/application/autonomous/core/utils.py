import os
import io
import pathlib
import zipfile

from fastapi import UploadFile, HTTPException

class ExecutorUtil:
    """タスクの実行と管理に関するユーティリティ関数をまとめたクラスです。"""
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
    def extract_zip_to_dir(zip_file: UploadFile, dest_dir: pathlib.Path) -> None:
        """アップロードされた ZIP ファイルを指定ディレクトリに展開します。"""
        contents = zip_file.file.read()
        with zipfile.ZipFile(io.BytesIO(contents)) as zip_ref:
            # セキュリティチェック（Zip Slip 対策）
            for member in zip_ref.namelist():
                target_path = os.path.normpath(os.path.join(dest_dir, member))
                if not target_path.startswith(os.path.abspath(dest_dir)):
                    raise HTTPException(status_code=400, detail="不正なファイルパスがZIPに含まれています")
            zip_ref.extractall(dest_dir)


