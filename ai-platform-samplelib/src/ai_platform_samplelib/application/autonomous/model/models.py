from typing import Dict, Optional, List, ClassVar, Literal
from datetime import datetime
from pydantic import BaseModel, Field
import os
from dotenv import load_dotenv
class ComposeConfig(BaseModel):

    env_file: ClassVar[str] = ".env"  # デフォルトの環境変数ファイルパス
    
    project_directory: str = Field(..., description="Path to the directory containing docker-compose.yml")
    compose_file: str = Field(..., description="Name of the docker-compose file")
    service_name: str = Field(..., description="Name of the service in docker-compose to run")
    compose_command : str = Field(..., description="Command to execute in the container (overrides default)")
    @classmethod
    def set_env_file(cls, env_file: str):
        cls.env_file = env_file

    @classmethod
    def from_env(cls):
        load_dotenv(cls.env_file)  # 指定された環境変数ファイルをロード
        params = {
            "project_directory": os.getenv("COMPOSE_PROJECT_DIRECTORY", "."),
            "compose_file": os.getenv("COMPOSE_FILE", "docker-compose.yml"),
            "service_name": os.getenv("COMPOSE_SERVICE_NAME", "executor-service"),
            "compose_command": os.getenv("COMPOSE_COMMAND", "cline -y")
        }

        return cls(**params)
        

    def get_compose_path(self) -> str:
        return os.path.join(self.project_directory, self.compose_file)

class AutonomousAgentRequest(BaseModel):
    prompt: str = Field(..., examples=["hello.py を修正して"])
    initial_files: Optional[Dict[str, str]] = None # 事前に配置したいファイル
    timeout: int = Field(default=300, ge=1, le=1800)

class TaskStatus(BaseModel):
    task_id: str
    status: Literal["running", "completed", "failed", "timeout", "cancelled"]  # running, completed, failed, timeout, cancelled
    sub_status: Optional[Literal["running-foreground", "running-background","pulling", "starting", "exited"]] = None  # より詳細な状態（例: "pulling", "starting", "running", "exited"など）
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    artifacts: Optional[List[str]] = None
    created_at: datetime
    container_id: Optional[str] = None

