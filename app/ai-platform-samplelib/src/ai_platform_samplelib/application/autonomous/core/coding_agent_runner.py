from typing import Optional, cast, Union
import uuid
import pathlib
import shlex
import os
from fastapi import UploadFile
from python_on_whales import docker as whales, Container, DockerClient
from ..model.models import ComposeConfig, CodingAgentConfig, TaskStatus
from .utils import ExecutorUtil

from ai_platform_samplelib.util.logging import get_application_logger

logger = get_application_logger()

class CodingAgentRunner:
    """
    コーディングエージェント用のdocker-compose.yml から設定を動的に読み取り、コンテナを実行するクラス
    
    
    """

    def __init__(self, compose_config: ComposeConfig, coding_agent_config: CodingAgentConfig, task_id: Optional[str] = None):

        self.compose_config = compose_config
        self.coding_agent_config = coding_agent_config
        self.task_id = task_id or str(uuid.uuid4())  # タスクごとに一意のIDを生成
        self.workspace = pathlib.Path(self.coding_agent_config.workspace_root) / self.task_id
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.command = shlex.split(self.compose_config.compose_command)
        self.detach = True  # デフォルトはバックグラウンド実行
        self.container = None
        self.task_status = TaskStatus(task_id=self.task_id)
        self.task_status.pendding()


    def prepare_workspace(self, 
                          data: Optional[dict[str, str]] = None, 
                          zip_file: Optional[UploadFile] = None, 
                          source_paths: Optional[list[pathlib.Path]] = None):
        """入力ソースに関わらずワークスペースを準備する（共通化）"""
        if zip_file:
            ExecutorUtil.add_zip_file(zip_file, self.workspace)

        if data:
            ExecutorUtil.add_data(data, self.workspace)

        if source_paths:
            ExecutorUtil.add_files(source_paths, self.workspace)
                    
    def run(self) -> Container:
        """
        コンテナを起動し、task_id を返します。
        volumes: [(ホストパス, コンテナパス, モード), ...] のリスト
        """
        params = {
            "service": self.compose_config.compose_service_name,
            "detach": self.detach,
            # "remove": True, # 終了時に自動削除
            "tty": False,   # ★明示的に False を指定（あるいは省略）
        }
        
        # 自然言語プロンプトは空白を含むため、呼び出し側で配列にして渡された場合はそのまま使う。
        # 文字列で渡された場合のみ shlex.split で分解する。
        params["command"] =  (shlex.split(self.command) if isinstance(self.command, str) else list(self.command))
        # WORKSPACE、USER_ID、GROUP_IDを設定
        params["envs"] = {
            "WORKSPACE": self.workspace.as_posix(),
            "USER_ID": str(os.getuid()),
            "GROUP_ID": str(os.getgid()),
        }

        # LLM 設定をホスト環境から引き継ぐ。
        # compose 側で env_file が指定されていても、ここで渡す env が優先されるため
        # CLI で設定した LLM_MODEL 等を確実にコンテナへ反映できる。
        for key in (
            "LLM_PROVIDER",
            "LLM_MODEL",
            "LLM_API_KEY",
            "LLM_BASE_URL",
        ):
            value = os.getenv(key)
            if value:
                params["envs"][key] = value

        # docker-compose.yml の volumes で ${WORKSPACE} を使っているため、
        # compose 側の変数置換に効く env-file をタスクごとに生成して渡す。
        # (compose.run(envs=...) は `--env` であり、変数置換には影響しない)
        compose_env_file = self.workspace / ".compose.env"
        compose_env_file.write_text(
            "\n".join(
                [
                    f"WORKSPACE={self.workspace.as_posix()}",
                    f"USER_ID={os.getuid()}",
                    f"GROUP_ID={os.getgid()}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        # クライアントは一度作れば使い回せます
        self.docker = DockerClient(
            compose_files=[self.compose_config.get_compose_path()],
            compose_project_directory=self.compose_config.compose_directory,
            compose_env_files=[compose_env_file],
            # service_name ではなく task_id をベースにしたユニークな名前に
            compose_project_name=f"task_{self.task_id}"
        )

        # コンテナを起動（Container オブジェクトが返る）
        container = self.docker.compose.run(**params)

        if not container or isinstance(container, str):
            raise RuntimeError("Failed to start container as an object")

        self.container =  cast(Container, container) # 明示的に Container 型にキャスト
        logger.info(f"Started container {self.container.name} for task {self.task_id} with command: {params['command']}")

        return self.container

    @classmethod
    async def create_runner(
        cls, 
        prompt: str,
        initial_files: Optional[dict[str, str]] = None,
        zip_file: Optional[UploadFile] = None,
        source_paths: Optional[list[pathlib.Path]] = None,
        task_id: Optional[str] = None,
        detach: bool = True
    ) -> "CodingAgentRunner":
        """
        インスタンス生成からコンテナ起動までを一括で行うエントリーポイント
        """
        # 1. Runnerの準備（プロジェクトパス等は環境変数から取得）
        compose_config = ComposeConfig.from_env()
        coding_agent_config = CodingAgentConfig.from_env()
        runner = cls(
            task_id=task_id, 
            compose_config=compose_config,
            coding_agent_config=coding_agent_config
        )

        runner.detach = detach

        runner.prepare_workspace(
            data=initial_files,
            zip_file=zip_file,
            source_paths=source_paths,
        )        # 2. ファイルの配置（ZIPまたは初期ファイル）

        # 3. コマンドと実行設定
        command_base = compose_config.compose_command
        runner.command = shlex.split(command_base)
        if prompt:
            runner.command.append(prompt)
        
        return runner
