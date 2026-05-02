# LibreOffice UNO Server

このディレクトリには次の 2 つを同居させたコンテナ定義があります。

- unoserver 本体
- Office ドキュメントを受け取り、unoserver に変換させて結果を返す FastAPI

## 前提

- LibreOffice 変換に使うため、コンテナ内に `libreoffice` と `python3-uno` が入っています
- FastAPI 経由の変換 API はアップロードされたバイト列を XML-RPC で unoserver に送るため、ホスト側との共有パスは必須ではありません
- ai-chat-util から raw UNO socket を直接使う場合は、別途その利用形態に応じたパス共有が必要です

## 起動

```bash
cd /home/user/source/repos/ai-platform-poc/infra/22-libreoffice-uno
docker compose up -d --build unoserver
docker compose ps
```

公開ポート:

- `2002`: raw UNO socket
- `2003`: unoserver XML-RPC port
- `2004`: FastAPI upload/convert API

ai-chat-util の `libreoffice_uno` は raw UNO socket を使うため、通常は `2002` を設定します。

## FastAPI API

エンドポイント:

- `GET /health`
- `POST /convert`

`POST /convert` の form-data:

- `file`: Office ドキュメント
- `convert_to`: 変換先拡張子。既定値は `pdf`
- `filter_name`: LibreOffice export filter 名。任意
- `input_filter`: LibreOffice import filter 名。任意
- `update_index`: 目次などの更新有無。既定値は `true`
- `password`: パスワード付き文書用。任意

例:

```bash
curl -o result.pdf \
  -F file=@/home/user/source/repos/ai-chat-util/work/test.xlsx \
  -F convert_to=pdf \
  http://127.0.0.1:2004/convert
```

返却は変換後ファイルのバイナリそのものです。`Content-Disposition` に元ファイル名ベースの出力名を付けます。

## ai-chat-util 設定例

```yml
ai_chat_util_config:
  office2pdf:
    method: libreoffice_uno
    libreoffice_uno:
      host: 127.0.0.1
      port: 2002
      connection_string: null
```

## 動作確認例

```bash
cd /home/user/source/repos/ai-chat-util/app
export AI_CHAT_UTIL_CONFIG=/home/user/source/repos/ai-chat-util/work/test-uno-config.yml

uv run python - <<'PY'
from ai_chat_util.core.common.config.runtime import init_runtime
from ai_chat_util.core.analysis.analyze_util import AnalyzePDFUtil

init_runtime(None)
print(
    AnalyzePDFUtil.convert_office_files_to_pdf(
        ['/home/user/source/repos/ai-chat-util/work/test.xlsx'],
        output_dir='/home/user/source/repos/ai-chat-util/work/uno-test-output',
    )
)
PY

uv run python src/ai_chat_util/test/simple_office_analysis.py \
  /home/user/source/repos/ai-chat-util/work/test.xlsx
```

FastAPI の確認:

```bash
curl http://127.0.0.1:2004/health
curl -o /tmp/test.pdf \
  -F file=@/home/user/source/repos/ai-chat-util/work/test.xlsx \
  -F convert_to=pdf \
  http://127.0.0.1:2004/convert
file /tmp/test.pdf
```