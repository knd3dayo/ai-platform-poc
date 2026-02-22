from litellm.integrations.custom_logger import CustomLogger

class MyEnterpriseGuardrail(CustomLogger):
    # 【入力ゲート】LLMへ送信する直前に発火
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        messages = data.get("messages", [])
        for msg in messages:
            content = msg.get("content", "")
            # 例: 簡易的な禁止ワードチェック（インジェクション検知のモック）
            if "社外秘" in content or "password" in content:
                raise Exception("【Security Alert】機密情報が含まれているため、リクエストを遮断しました。")
        return data

    # 【出力ゲート】LLMから応答を受け取った直後に発火
    async def async_post_call_success_hook(self, data, user_api_key_dict, response):
        # ここで応答内容のDLP（情報漏洩）スキャンや、MCP呼び出しパラメータの検証を行います
        pass