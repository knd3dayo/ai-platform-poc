import threading
import time
import requests
import uuid
import uvicorn
from fastapi import FastAPI, Request

# ==========================================
# 1. 擬似的な統合Webhook受信サーバー
# ==========================================
webhook_port = 18080
webhook_app = FastAPI()
webhook_event = threading.Event()
last_payload = {}

@webhook_app.post("/webhook")
async def receive_webhook(request: Request):
    """APIサーバー(5202)からの非同期通知を受け取るエンドポイント"""
    global last_payload
    data = await request.json()
    
    print(f"\n🔔 [Webhook Receiver] 通知を受信しました！")
    print(f"  ┣ イベント種別 : {data.get('event_type')}")
    print(f"  ┣ ステータス   : {data.get('status')}")
    print(f"  ┣ メタデータ   : {data.get('metadata')}")
    print(f"  ┗ 実行結果     : {data.get('result')}")
    
    last_payload = data
    webhook_event.set() # 待機中のメインスレッドに通知
    return {"status": "ok"}

def start_webhook_server():
    # ログを出さずに静かに起動する
    uvicorn.run(webhook_app, host="0.0.0.0", port=webhook_port, log_level="critical")

# ==========================================
# 2. 非同期APIのテストシナリオ
# ==========================================
def run_async_test():
    # Executor APIのURL（ホストで実行する場合はlocalhost、コンテナ内からは host.docker.internal を使用）
    API_URL = "http://host.docker.internal:8000"
    # WEBHOOK_URL = f"http://localhost:{webhook_port}/webhook"
    # docker コンテナ内からはホストのIPを `host.docker.internal` で参照する
    WEBHOOK_URL = f"http://host.docker.internal:{webhook_port}/webhook"
    thread_id = f"async-sim-{uuid.uuid4()}"

    print("==================================================")
    print("🚀 [Step 1] クライアントから非同期リクエスト送信 (/chat_async)")
    print("==================================================")
    chat_payload = {
        "thread_id": thread_id,
        "message": "Aliceに50,000円を送金しておいて。",
        "webhook_url": WEBHOOK_URL,
        "event_type": "request_money_transfer",
        "metadata": {"user_id": "emp_001", "department": "sales"}
    }
    
    response = requests.post(f"{API_URL}/chat_async", json=chat_payload)
    print(f"即時レスポンス (HTTP 200): {response.json()}\n")
    print("⏳ バックグラウンド処理の完了（Webhook通知）を待機中...")
    
    webhook_event.wait() # Webhookが来るまでプログラムを待機
    webhook_event.clear()

    # Webhookが「承認待ち」だった場合
    if last_payload.get("status") == "requires_approval":
        print("\n==================================================")
        print("⏸️  [Step 2] 人間による承認（HITL）")
        print("==================================================")
        result = last_payload.get("result", {})
        print(f"⚠️ {result.get('message')}")
        print(f"   ツール: {result.get('tool_name')}")
        print(f"   引数  : {result.get('tool_args')}")
        
        user_input = input("\n>> 承認しますか？ (y/n): ")
        if user_input.lower() in ['y', 'yes']:
            print("\n==================================================")
            print("▶️  [Step 3] クライアントから非同期再開リクエスト (/resume_async)")
            print("==================================================")
            resume_payload = {
                "thread_id": thread_id,
                "action": "approve",
                "webhook_url": WEBHOOK_URL,
                "event_type": "confirm_money_transfer",
                "metadata": {"user_id": "emp_001", "approved_by": "manager_999"}
            }
            
            res_resume = requests.post(f"{API_URL}/resume_async", json=resume_payload)
            print(f"即時レスポンス (HTTP 200): {res_resume.json()}\n")
            print("⏳ ツール実行の完了（Webhook通知）を待機中...")
            
            webhook_event.wait()
            print("\n✅ 全フロー完了！")

if __name__ == "__main__":
    # Webhook受信サーバーを別スレッドで起動
    server_thread = threading.Thread(target=start_webhook_server, daemon=True)
    server_thread.start()
    
    # サーバーが立ち上がるのを少し待つ
    time.sleep(1)
    
    # テストシナリオの実行
    run_async_test()