from collections import deque
from typing import Any, Dict, Optional, List, ClassVar, Literal
from datetime import datetime
from pydantic import BaseModel, Field, field_serializer
import os
from dotenv import load_dotenv

class CodingAgentConfig(BaseModel):

    env_file: ClassVar[str] = ".env"  # デフォルトの環境変数ファイルパス

    llm_provider: str = Field(..., description="LLMプロバイダーの名前（例: openai, azure, anthropic）")
    llm_model: str = Field(..., description="LLM model to use (e.g., gpt-4o)")
    llm_base_url: Optional[str] = Field(None, description="Base URL for the LLM API")
    workspace_root: str = Field(default="/tmp/autonomous_agent_tasks", description="Root directory for task workspaces")
    
    @classmethod
    def set_env_file(cls, env_file: str):
        cls.env_file = env_file

    @classmethod
    def from_env(cls):
        load_dotenv(cls.env_file)  # 指定された環境変数ファイルをロード
        params = {
            "llm_provider": os.getenv("LLM_PROVIDER", "openai"),
            "llm_model": os.getenv("LLM_MODEL", "gpt-4o"),
            "llm_base_url": os.getenv("LLM_BASE_URL"),
            "workspace_root": os.getenv("WORKSPACE_ROOT", "/tmp/autonomous_agent_tasks")
        }
        return cls(**params)
    
class ComposeConfig(BaseModel):

    env_file: ClassVar[str] = ".env"  # デフォルトの環境変数ファイルパス
    
    compose_directory: str = Field(..., description="Path to the directory containing docker-compose.yml")
    compose_file: str = Field(..., description="Name of the docker-compose file")
    compose_service_name: str = Field(..., description="Name of the service in docker-compose to run")
    compose_command : str = Field(..., description="Command to execute in the container (overrides default)")

    @classmethod
    def set_env_file(cls, env_file: str):
        cls.env_file = env_file

    @classmethod
    def from_env(cls):
        load_dotenv(cls.env_file)  # 指定された環境変数ファイルをロード
        params = {
            "compose_directory": os.getenv("COMPOSE_DIRECTORY", "."),
            "compose_file": os.getenv("COMPOSE_FILE", "docker-compose.yml"),
            "compose_service_name": os.getenv("COMPOSE_SERVICE_NAME", "executor-service"),
            "compose_command": os.getenv("COMPOSE_COMMAND", "cline -y")
        }

        return cls(**params)

    def get_compose_path(self) -> str:
        return os.path.join(self.compose_directory, self.compose_file)

class AutonomousAgentRequest(BaseModel):
    prompt: str = Field(..., examples=["hello.py を修正して"])
    initial_files: Optional[Dict[str, str]] = None # 事前に配置したいファイル
    timeout: int = Field(default=300, ge=1, le=1800)

class TaskStatus(BaseModel):
    task_id: str
    status: Optional[Literal[
        "pending", "running", "exited"
        ]] = None
    sub_status: Optional[Literal[
        "not-started", "running-foreground", "running-background","pulling", "starting", "failed", "timeout", "cancelled", "completed"
        ]] = None  # より詳細な状態（例: "pulling", "starting", "running", "exited"など）
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    artifacts: Optional[List[str]] = None
    created_at: Optional[datetime] = None
    container_id: Optional[str] = None

    # 逐次通知/統合向けの拡張メタ情報。
    # SV層では server_logs(リングバッファ) 等を入れることがある。
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_serializer("metadata")
    def _serialize_metadata(self, metadata: Dict[str, Any]):
        if not isinstance(metadata, dict):
            return metadata

        server_logs = metadata.get("server_logs")
        if isinstance(server_logs, deque):
            # shallow copy して server_logs だけ list 化
            return {**metadata, "server_logs": list(server_logs)}

        return metadata

    def pendding(self):
        self.status = "pending"
        self.sub_status = "not-started"

    def starting_foregrond(self):
        self.status = "running"
        self.sub_status = "running-foreground"
    
    def starting_background(self):
        self.status = "running"
        self.sub_status = "running-background"
    
    def timeouted(self, timeout: int):
        self.status = "exited"
        self.sub_status = "timeout"
        self.stderr=f"Task timed out after {timeout} seconds"
    
    def completed(self):
        self.status = "exited"
        self.sub_status = "completed"
    
    def failed(self):
        self.status = "exited"
        self.sub_status = "failed"

    def cancelled(self):
        self.status = "exited"
        self.sub_status = "cancelled"
        
    def is_exited(self) -> bool:
        return self.status == "exited"
    