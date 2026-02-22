from litellm.integrations.custom_logger import CustomLogger

class MyEnterpriseGuardrail(CustomLogger):
    # 【入力ゲート】LLMへ送信する直前に発火
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        messages = data.get("messages", [])
        for msg in messages:
            content = msg.get("content", "")
            # 例: 簡易的な禁止ワードチェック
            if "litellm_ng_test" in content or "社外秘" in content or "password" in content:
                raise Exception("【Security Alert】機密情報が含まれているため、リクエストを遮断しました。")
        return data

    # 【出力ゲート】LLMから応答を受け取った直後に発火
    async def async_post_call_success_hook(self, data, user_api_key_dict, response):
        pass

# ↓↓↓ 【重要】この1行を末尾に追加してインスタンスを作成します ↓↓↓
proxy_handler_instance = MyEnterpriseGuardrail()