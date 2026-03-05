import httpx
import json
import sys

def test_langgraph_agent(prompt: str):
    # BFFのURL (backend_key として config.yml のキーを指定)
    BFF_URL = "http://localhost:5401/api/v1/execute/langgraph_hitl_agent"
    
    # BFFのゲートキーパーを通過するためのモックトークン
    # 本来はEntraID等から取得した有効なトークンである必要があります
    headers = {
        "Authorization": "Bearer mock-user-access-token-12345",
        "Content-Type": "application/json"
    }
    
    # BFFの引数 'query' はクエリパラメータとして定義されているため、paramsで渡します
    params = {
        "query": prompt
    }

    print(f"--- Requesting BFF (LangGraph Agent) ---")
    print(f"Prompt: {prompt}")
    
    try:
        with httpx.Client() as client:
            response = client.post(
                BFF_URL, 
                headers=headers, 
                params=params, 
                timeout=65.0 # 長時間処理（HITL）を考慮して長めに設定
            )
            
        # ステータスコードの確認
        response.raise_for_status()
        
        result = response.json()
        
        print("\n--- Response Received ---")
        print(f"Backend Used : {result.get('backend')}")
        print(f"Trace ID     : {result.get('trace_id')}")  # これがW3C準拠のID
        print(f"Data Payload :")
        print(json.dumps(result.get("data"), indent=2, ensure_ascii=False))

    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP Error: {e.response.status_code}")
        print(e.response.text)
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "こんにちは。今日の天気は？"
    test_langgraph_agent(query)