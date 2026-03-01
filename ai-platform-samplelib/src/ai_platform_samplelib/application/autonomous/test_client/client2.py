import requests
import shutil
import os
import time
import pathlib

# 設定
BASE_URL = "http://localhost:7101"
SRC_DIR = "./src"        # 送信したいソースコードがあるディレクトリ
ZIP_NAME = "temp_project" # 作成される一時ファイル名

def test_cline_zip_flow(resume_task_id=None):
    # 0. 事前準備：送信対象のディレクトリがない場合は作成（テスト用）
    if not os.path.exists(SRC_DIR):
        os.makedirs(SRC_DIR)
        with open(f"{SRC_DIR}/main.py", "w") as f:
            f.write("def start():\n    print('Starting project...')\n")

    print(f"🚀 1. プロジェクトをZIP化して送信します... {'(Resume: ' + resume_task_id + ')' if resume_task_id else ''}")
    
    # 1. フォルダをZIP化
    # base_name="temp_project" -> temp_project.zip が作られる
    zip_file_path = shutil.make_archive(ZIP_NAME, "zip", SRC_DIR)

    try:
        # 2. APIへ送信
        with open(zip_file_path, "rb") as f:
            files = {"file": (os.path.basename(zip_file_path), f, "application/zip")}
            # フォームデータ
            data = {
                "prompt": "プロジェクトの main.py にログ出力機能を追加し、全体の構造を整理してください。",
                "timeout": 600
            }
            # クエリパラメータで task_id を渡せるようにする
            params = {"task_id": resume_task_id} if resume_task_id else {}
            
            response = requests.post(f"{BASE_URL}/execute/zip", files=files, data=data, params=params)

        if response.status_code != 200:
            print(f"❌ エラー: {response.text}")
            return

        task_id = response.json()["task_id"]
        print(f"✅ タスク受理: task_id = {task_id}")

        # 3. ポーリング（状態監視）
        print("⏳ 2. 実行中（リアルタイムログ表示）...")
        start_time = time.time()
        last_log_len = 0
        
        while True:
            status_res = requests.get(f"{BASE_URL}/status/{task_id}", params={"tail": 20})
            status_data = status_res.json()
            status = status_data["status"]

            # 新着ログを表示
            current_stdout = status_data.get("stdout") or ""
            if len(current_stdout) > last_log_len:
                print(f"\n[Cline Log]\n{current_stdout[last_log_len:]}", end="")
                last_log_len = len(current_stdout)

            if status in ["completed", "failed", "timeout", "cancelled"]:
                print(f"\n🏁 3. 実行終了: {status}")
                break
            
            elapsed = int(time.time() - start_time)
            print(f"   [経過 {elapsed}s] ステータス: {status}...", end="\r")
            time.sleep(2)

        # 4. 結果表示
        print("\n" + "="*50)
        if status == "completed":
            print("📝 --- 最終結果 ---")
            print(status_data.get("stdout"))
            print("\n📂 --- 成果物リスト ---")
            for artifact in status_data.get("artifacts", []):
                print(f"  - {artifact}")
        else:
            print(f"❌ エラー内容: {status_data.get('stderr')}")
        print("="*50)

    finally:
        # 5. 後片付け：作成した一時ZIPファイルを削除
        if os.path.exists(zip_file_path):
            os.remove(zip_file_path)
            print(f"\n🧹 一時ファイル {zip_file_path} を削除しました。")

if __name__ == "__main__":
    test_cline_zip_flow()