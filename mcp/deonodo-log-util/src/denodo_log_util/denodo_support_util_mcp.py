
import os, sys
import asyncio
from typing import Annotated
from dotenv import load_dotenv
from datetime import datetime
import argparse
from fastmcp import FastMCP
from pydantic import Field
from denodo_support_util.denodo_log_util import denodo_log_util_main

mcp = FastMCP("Demo 🚀") #type :ignore

# Denodoログ切り取りツール
@mcp.tool()
def extract_log_mcp(
    start_time_str: Annotated[str, Field(description="抽出開始時刻 (ISOフォーマット)")] = "2023-10-01T00:00:00Z",
    end_time_str: Annotated[str, Field(description="抽出終了時刻 (ISOフォーマット)")] = "2023-10-01T23:59:59Z",
    logfiles: Annotated[list[str], Field(description="ログファイルの絶対パス (ワイルドカードを使用して複数指定可能)")] = [],
    output_dir: Annotated[str, Field(description="出力ディレクトリの絶対パス")] = "./input_data/logs_in_timerange",
    ) -> Annotated[list[str], Field(description="出力ファイルのパス")] :
    """
    Denodoログファイルから指定した時間帯のログを抽出します。
    param start_time: 抽出開始時刻 (ISOフォーマット)
    param end_time: 抽出終了時刻 (ISOフォーマット)
    param logfiles: ログファイルのパス (ワイルドカードを使用して複数指定可能)
    param output_dir: 出力ディレクトリのパス 
    """
    # 開始時刻と終了時刻をdatetimeオブジェクトに変換
    start_time = datetime.fromisoformat(start_time_str)
    end_time = datetime.fromisoformat(end_time_str)

    output_log_files = denodo_log_util_main(
        start_time_str=start_time_str,
        end_time_str=end_time_str,
        logfiles=logfiles,
        output_dir=output_dir
    )

    return output_log_files

# 引数解析用の関数
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MCP server with specified mode and APP_DATA_PATH.")
    # -m オプションを追加
    parser.add_argument("-m", "--mode", choices=["sse", "stdio"], default="stdio", help="Mode to run the server in: 'sse' for Server-Sent Events, 'stdio' for standard input/output.")
    # -d オプションを追加　APP_DATA_PATH を指定する
    parser.add_argument("-d", "--app_data_path", type=str, help="Path to the application data directory.")
    # 引数を解析して返す
    # -t tools オプションを追加 toolsはカンマ区切りの文字列. search_wikipedia_ja_mcp, vector_search, etc. 指定されていない場合は空文字を設定
    parser.add_argument("-t", "--tools", type=str, default="", help="Comma-separated list of tools to use, e.g., 'search_wikipedia_ja_mcp,vector_search_mcp'. If not specified, no tools are loaded.")
    # -p オプションを追加　ポート番号を指定する modeがsseの場合に使用.defaultは5001
    parser.add_argument("-p", "--port", type=int, default=5001, help="Port number to run the server on. Default is 5001.")
    # -v LOG_LEVEL オプションを追加 ログレベルを指定する. デフォルトは空白文字
    parser.add_argument("-v", "--log_level", type=str, default="", help="Log level to set for the server. Default is empty, which uses the default log level.")

    return parser.parse_args()

def main():
        # load_dotenv() を使用して環境変数を読み込む
    load_dotenv()
    # 引数を解析
    args = parse_args()
    mode = args.mode
    app_data_path = args.app_data_path
    os.environ["APP_DATA_PATH"] = app_data_path if app_data_path else os.getenv("APP_DATA_PATH", "")

    # APP_DATA_PATHを取得
    app_data_path = os.getenv("APP_DATA_PATH", None)
    if not app_data_path:
        raise ValueError("APP_DATA_PATH is required")

    print(f"APP_DATA_PATH={app_data_path}")

    if mode == "stdio":
        print(f"Running in stdio mode with APP_DATA_PATH: {app_data_path}")
        mcp.run()

    elif mode == "sse":
        # port番号を取得
        port = args.port
        print(f"Running in SSE mode with APP_DATA_PATH: {app_data_path}")
        mcp.run(transport="sse", port=port)


if __name__ == "__main__":
    main()
