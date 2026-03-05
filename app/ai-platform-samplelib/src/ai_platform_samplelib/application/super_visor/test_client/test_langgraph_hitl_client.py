import requests
import uuid

# FastAPIサーバーのURL
BASE_URL = "http://localhost:5201/api"

def run_api_test():
    # DifyのセッションID（会話ID）を模擬
    thread_id = f"dify-sim-{uuid.uuid4()}"
    
    print("==================================================")
    print("🚀 [Step 1] Difyからの初回リクエスト送信 (/api/chat)")
    print("==================================================")
    
    chat_payload = {
        "thread_id": thread_id,
        "message": "Aliceに50,000円を送金しておいて。"
    }
    
    print(f"送信データ: {chat_payload}")
    response = requests.post(f"{BASE_URL}/chat", json=chat_payload)
    
    if response.status_code != 200:
        print(f"❌ エラー発生: {response.text}")
        return

    data = response.json()
    print(f"\n受信データ: {data}\n")

    # APIから「承認が必要（requires_approval）」と返ってきた場合の処理
    if data.get("status") == "requires_approval":
        print("==================================================")
        print("⏸️  [Step 2] DifyのUIでの承認待ち（HITL）")
        print("==================================================")
        print(f"⚠️ AIが以下の処理を提案しています。")
        print(f"   実行ツール: {data.get('tool_name')}")
        print(f"   パラメータ: {data.get('tool_args')}")
        print(f"   メッセージ: {data.get('message')}")
        
        # ユーザーに承認を求める（Difyの「質問ノード」の代わり）
        user_input = input("\n>> この処理を承認して実行しますか？ (y/n): ")
        
        if user_input.lower() in ['y', 'yes']:
            print("\n==================================================")
            print("▶️  [Step 3] 承認OK！処理の再開リクエスト (/api/resume)")
            print("==================================================")
            
            resume_payload = {
                "thread_id": thread_id,
                "action": "approve"
            }
            print(f"送信データ: {resume_payload}")
            
            resume_response = requests.post(f"{BASE_URL}/resume", json=resume_payload)
            resume_data = resume_response.json()
            
            print(f"\n🎉 最終結果: {resume_data['message']}")
            
        else:
            print("\n🚫 処理をキャンセルしました。")
            
    else:
        # ツール呼び出しが不要で普通に回答が返ってきた場合
        print("==================================================")
        print("✅ 処理完了（ツール実行なし）")
        print("==================================================")
        print(f"最終結果: {data.get('message')}")

if __name__ == "__main__":
    run_api_test()