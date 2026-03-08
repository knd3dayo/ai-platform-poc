from typing import Optional
from pydantic import BaseModel, Field


class DenodoConfig(BaseModel):
    denodo_url: str = Field(..., description="Denodo MarketplaceのURL")
    username: str = Field(..., description="Denodoへの接続に使用するユーザー名")
    password: str = Field(..., description="Denodoへの接続に使用するパスワード")
    ai_sdk_url: Optional[str] = Field(None, description="Denodo AI SDKのURL")
