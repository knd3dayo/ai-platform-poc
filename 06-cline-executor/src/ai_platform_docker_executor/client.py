import requests
import time
import os

# 設定：APIのURL
BASE_URL = "http://localhost:8000"

def test_cline_flow(resume_task_id=None):
    print(f"🚀 1. タスクを開始します... {'(Resume: ' + resume_task_id + ')' if resume_task_id else ''}")
    
    # テストデータ
    payload = {
        "prompt": "hello.py を読み込んで、現在の内容をコメントで追記してください。日本語で報告して。",
        "initial_files": {
            "hello.py": "print('Hello, persistent world!')"
        }
    }

    # 実行リクエスト (既存の task_id があればクエリパラメータで渡す)
    params = {"task_id": resume_task_id} if resume_task_id else {}
    response = requests.post(f"{BASE_URL}/execute", json=payload, params=params)
    
    if response.status_code != 200:
        print(f"❌ エラー: {response.text}")
        return

    task_id = response.json()["task_id"]
    print(f"✅ タスク受理: task_id = {task_id}")

    # 2. ポーリング（状態監視）
    print("⏳ 2. 実行中（リアルタイムログを表示します）...")
    start_time = time.time()
    last_log_len = 0
    
    while True:
        # 実行中もログを取得するためにポーリング
        status_res = requests.get(f"{BASE_URL}/status/{task_id}", params={"tail": 10})
        status_data = status_res.json()
        status = status_data["status"]

        # 新しいログがあれば表示
        current_stdout = status_data.get("stdout") or ""
        if len(current_stdout) > last_log_len:
            print(f"\n[Cline Log]\n{current_stdout[last_log_len:]}", end="")
            last_log_len = len(current_stdout)

        if status in ["completed", "failed", "timeout", "cancelled"]:
            print(f"\n🏁 3. 実行終了: {status}")
            break
        
        elapsed = int(time.time() - start_time)
        print(f"   [経過 {elapsed}s] 監視中...", end="\r")
        time.sleep(2)

    # 4. 結果の最終表示
    print("\n" + "="*50)
    if status == "completed":
        print("📝 --- 最終結果 (stdout) ---")
        print(status_data.get("stdout"))
        print("\n📂 --- 更新されたファイル ---")
        print(status_data.get("artifacts"))
    else:
        print("❌ --- エラー内容 (stderr) ---")
        print(status_data.get("stderr"))
    print("="*50)
    
    return task_id

if __name__ == "__main__":
    # 初回実行
    tid = test_cline_flow()
    
    # 続けて、同じ task_id で「再開」をテストしたい場合は以下をアンコメント
    # time.sleep(5)
    # print("\n--- 既存のタスクIDで再実行をテストします ---")
    # test_cline_flow(resume_task_id=tid)