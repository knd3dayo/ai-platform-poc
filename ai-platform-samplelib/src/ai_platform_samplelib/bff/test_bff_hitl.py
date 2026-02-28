import requests
import json
import sys

# BFFのベースURL
BFF_BASE_URL = "http://localhost:5401/api/v1"
BACKEND_KEY = "langgraph_hitl_agent"

def run_bff_hitl_test():
    headers = {
        "Authorization": "Bearer mock-user-token-12345",
        "Content-Type": "application/json"
    }

    print("==================================================")
    print(f"🚀 [Step 1] BFF経由でリクエスト送信 (/execute/{BACKEND_KEY})")
    print("==================================================")

    # BFFの /execute は query をクエリパラメータで受け取る設計
    params = {"query": "Aliceに50,000円を送金しておいて。"}
    
    response = requests.post(
        f"{BFF_BASE_URL}/execute/{BACKEND_KEY}", 
        headers=headers, 
        params=params
    )
    
    if response.status_code != 200:
        print(f"❌ エラー発生: {response.text}")
        return

    res_json = response.json()
    trace_id = res_json.get("trace_id") # BFFが生成した重要なID
    data = res_json.get("data", {})

    print(f"BFF発行 Trace ID: {trace_id}")
    print(f"LangGraph応答: {data}\n")

    # 承認が必要な場合の処理
    if data.get("status") == "requires_approval":
        print("==================================================")
        print("⏸️  [Step 2] ユーザーによる承認待ち")
        print("==================================================")
        print(f"提案内容: {data.get('message')}")
        
        user_input = input("\n>> この処理を承認しますか？ (y/n): ")
        
        if user_input.lower() in ['y', 'yes']:
            print("\n==================================================")
            print("▶️  [Step 3] BFF経由で再開リクエスト (/resume)")
            print("==================================================")
            
            # 再開時は、初回に受け取った trace_id を渡す
            resume_params = {
                "action": "approve",
                "trace_id": trace_id 
            }
            
            resume_response = requests.post(
                f"{BFF_BASE_URL}/resume/{BACKEND_KEY}", 
                headers=headers, 
                params=resume_params
            )
            
            resume_data = resume_response.json()
            print(f"\n🎉 最終結果: {resume_data.get('message')}")
        else:
            print("\n🚫 処理をキャンセルしました。")
    else:
        print(f"✅ 完了: {data.get('message')}")

if __name__ == "__main__":
    run_bff_hitl_test()