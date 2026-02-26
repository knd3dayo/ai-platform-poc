import requests
import time
import json

# 設定：APIのURL（ホスト実行なら localhost、コンテナ間ならサービス名）
BASE_URL = "http://localhost:8000"

def test_cline_flow():
    print("🚀 1. タスクを開始します...")
    
    # テストデータ：最初に配置するファイルとプロンプト
    payload = {
        "prompt": "hello.py を読み込んで、数値を2倍にする double_it 関数を追加して保存してください。日本語で報告して。",
        "initial_files": {
            "hello.py": "def main():\n    print('Hello Cline!')\n\nif __name__ == '__main__':\n    main()"
        },
        "timeout": 300
    }

    # 実行リクエスト
    response = requests.post(f"{BASE_URL}/execute", json=payload)
    if response.status_code != 200:
        print(f"❌ エラー: {response.text}")
        return

    task_id = response.json()["task_id"]
    print(f"✅ タスク受理: task_id = {task_id}")

    # 2. ポーリング（状態監視）
    print("⏳ 2. 実行完了を待機中（ポーリング開始）...")
    start_time = time.time()
    
    while True:
        status_res = requests.get(f"{BASE_URL}/status/{task_id}")
        status_data = status_res.json()
        status = status_data["status"]

        if status in ["completed", "failed", "timeout", "cancelled"]:
            print(f"\n🏁 3. 実行終了: {status}")
            break
        
        # 経過を表示
        elapsed = int(time.time() - start_time)
        print(f"   [経過 {elapsed}s] ステータス: {status}...", end="\r")
        time.sleep(2)

    # 4. 結果の表示
    print("\n" + "="*50)
    if status == "completed":
        print("📝 --- Clineの出力 (stdout) ---")
        print(status_data.get("stdout"))
        print("\n📂 --- 生成・更新されたファイル ---")
        for artifact in status_data.get("artifacts", []):
            print(f"  - {artifact}")
    else:
        print("❌ --- エラー内容 (stderr) ---")
        print(status_data.get("stderr"))
    print("="*50)

if __name__ == "__main__":
    test_cline_flow()
    