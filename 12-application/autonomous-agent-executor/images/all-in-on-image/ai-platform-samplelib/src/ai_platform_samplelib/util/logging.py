import logging


def get_application_logger() -> logging.Logger:
    """アプリケーション全体で使用するロガーを取得する関数。"""
    # アプリケーション共通のロガーを設定
    logger = logging.getLogger("ai_platform_samplelib")
    logger.setLevel(logging.DEBUG)  # デバッグレベルに設定
    handler = logging.StreamHandler()  # コンソール出力用のハンドラー ファイル名、関数名、行番業を追加
    format = "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d - %(funcName)s()] %(message)s"
    formatter = logging.Formatter(format)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
