import re
from datetime import datetime
import argparse
from typing import Pattern, Optional
from pathlib import Path
import glob
import os

class DenodoLogUtil:

    log_type_vdp = 'vdp'
    log_type_processes = 'processes'
    log_type_sockets = 'sockets'
    log_type_vdp_connections = 'vdp-connections'
    log_type_vdp_datasources = 'vdp-datasources'
    log_type_vdp_queries = 'vdp-queries'
    log_type_vdp_querydatasources = 'vdp-querydatasources'
    log_type_vdp_resources = 'vdp-resources'
    log_type_vdp_threads = 'vdp-threads'
    log_type_vdp_loadcacheprocesses = 'vdp-loadcacheprocesses'
    log_type_vdp_data_catalog = 'vdp-data-catalog'
    log_type_design_studio_backend = 'design-studio-backend'
    log_type_sso = 'sso'
    log_type_catalina = 'catalina'


    log_types = [
        log_type_vdp,
        log_type_processes,
        log_type_sockets,
        log_type_vdp_connections,
        log_type_vdp_datasources,
        log_type_vdp_queries,
        log_type_vdp_querydatasources,
        log_type_vdp_resources,
        log_type_vdp_threads,
        log_type_vdp_loadcacheprocesses,
        log_type_vdp_data_catalog,
        log_type_design_studio_backend,
        log_type_sso,
        log_type_catalina
    ]
    # 日付書式フラグ
    date_iso_format = 0
    date_short_month_format = 1


    def parse_iso_datetime(self, date_str: str) -> datetime:
        """
        ISOフォーマットの日付文字列をdatetimeオブジェクトに変換する。
        末尾に 'Z' が付いている場合はUTCとして解釈する。
        :param date_str: ISOフォーマットの日付文字列
        :return: datetimeオブジェクト
        """
        if date_str.endswith('Z'):
            date_str = date_str.replace('Z', '+00:00')
        return datetime.fromisoformat(date_str)

    def parse_short_month_datetime(self, date_str: str) -> datetime:
        """
        短縮月形式の日付文字列をdatetimeオブジェクトに変換する。
        例: "19-Jul-2025 14:06:07.860"
        :param date_str: 短縮月形式の日付文字列
        :return: datetimeオブジェクト
        """
        return datetime.strptime(date_str, '%d-%b-%Y %H:%M:%S.%f')

    def is_in_time_range(self, date_str, start_time: datetime, end_time: datetime, dateFormat: Optional[int] = 0) -> bool:
        """
        Denodoログファイルから特定の時間帯に該当するログエントリを抽出するユーティリティ。
        """
        try:
            if dateFormat == 0:
                dt = self.parse_iso_datetime(date_str)
            elif dateFormat == 1:
                dt = self.parse_short_month_datetime(date_str)
            else:
                raise ValueError("Invalid date format")

            return start_time <= dt <= end_time
        except ValueError:
            return False

    def extract_entries(
            self, log_file_path: str, date_pattern: Pattern, group_num: int, 
            start_time: datetime, end_time: datetime, header_pattern: Optional[Pattern] = None, dateFormat: Optional[int] = 0) -> list[str]:
        """
        指定したログファイルから、日付パターンとグループ番号を使用してログエントリを抽出する。
        ヘッダー行のパターンが指定されている場合は、ヘッダー行を最初に追加する。
        :param dateFormat: 日付のフォーマット（0: ISOフォーマット, 1: 短縮月形式）
        :param log_file_path: ログファイルのパス
        :param date_pattern: 日付パターンの正規表現
        :param group_num: 日付部分を抽出するためのグループ番号
        :param start_time: 抽出開始時刻（datetimeオブジェクト）
        :param end_time: 抽出終了時刻（datetimeオブジェクト）
        :param header_pattern: ヘッダー行のパターン（オプション）
        """
        result_entries = []
        header_row = None
        with open(log_file_path, 'r', encoding='utf-8') as f:
            in_time_range = False
            for line in f:
                # ヘッダー行のパターンにマッチする場合は、ヘッダー行を保存
                if header_pattern and header_pattern.match(line):
                    if header_row is None:
                        header_row = line.strip()
                    continue
                match = date_pattern.match(line)
                if match:
                    date_str = match.group(group_num)
                    if self.is_in_time_range(date_str, start_time, end_time, dateFormat):
                        in_time_range = True
                        result_entries.append(line)
                    elif in_time_range:
                        # end_time以降の日付にマッチした場合は、フラグをFalseにする
                        in_time_range = False
                elif in_time_range:
                    # 日付がマッチしない行でも、フラグがTrueの場合はログエントリを追加
                    result_entries.append(line)
            # ヘッダー行が存在する場合は、最初に追加
            if header_row:
                result_entries.insert(0, header_row + '\n')
        return result_entries

    def extract_entries_as_dict(
            self, log_file_path: str, date_pattern: Pattern, group_num: int, 
            start_time: datetime, end_time: datetime, dateFormat: Optional[int] = 0) -> dict[str, list[str]]:
        """
        指定したログファイルから、日付パターンとグループ番号を使用してログエントリを抽出し、日付ごとのログエントリのDictを返す。
        :param log_file_path: ログファイルのパス
        :param date_pattern: 日付パターンの正規表現
        :param group_num: 日付部分を抽出するためのグループ番号
        :param start_time: 抽出開始時刻（datetimeオブジェクト）
        :param end_time: 抽出終了時刻（datetimeオブジェクト）
        :param dateFormat: 日付のフォーマット（0: ISOフォーマット, 1: 短縮月形式）
        :return: 日付ごとのログエントリのDict
        """
        result_entries = {}
        with open(log_file_path, 'r', encoding='utf-8') as f:
            in_time_range = False
            date_str = None  # 日付文字列を保持する変数
            for line in f:
                match = date_pattern.match(line)
                if match:
                    date_str = match.group(group_num)
                    if self.is_in_time_range(date_str, start_time, end_time, dateFormat):
                        in_time_range = True
                        if date_str not in result_entries:
                            result_entries[date_str] = []
                        result_entries[date_str].append(line.strip())
                    elif in_time_range:
                        # end_time以降の日付にマッチした場合は、フラグをFalseにする
                        in_time_range = False
                elif in_time_range:
                    if date_str:
                        result_entries[date_str].append(line.strip())
        return result_entries
    

    # 指定されたタイプ、開始時刻、終了時刻に基づいて抽出されたログエントリを指定されたディレクトリに保存する関数
    def save_entries_to_file(self, start_time: datetime, end_time: datetime, log_type: str, entries: list[str], output_dir: str) -> str:
        """
        抽出されたログエントリを指定されたディレクトリに保存する。
        :param entries: 抽出されたログエントリのリスト
        :param output_dir: 出力ディレクトリのパス
        :param log_type: ログの種類（例：vdp, processesなど）
        """
        import os
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # start_timeとend_timeをファイル名に含めるためのフォーマット
        start_time_str = start_time.strftime('%Y%m%d_%H%M%S')
        end_time_str = end_time.strftime('%Y%m%d_%H%M%S')
        # 出力ファイルのパスを生成
        output_file_path = os.path.join(output_dir, f"{log_type}_{start_time_str}_to_{end_time_str}.log")
        
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.writelines(entries)
        print(f"抽出されたログエントリは {output_file_path} に保存されました。")
        return output_file_path

    def detect_log_type(self, log_file_path: str) -> Optional[str]:
        """
        ログファイルのパスからログの種類を自動判別する。
        :param log_file_path: ログファイルのパス
        :return: 判別されたログの種類（例：vdp, processesなど）
        """
        log_file_name = Path(log_file_path).name.lower()
        for log_type in self.log_types:
            log_type_period = log_type + '.'
            if  log_file_name.startswith(log_type_period):
                return log_type
        # ログの種類が判別できない場合はNoneを返す
        return None

    def get_log_files(self, log_file_patterns: list[str], suffix: Optional[str] = None, recursive: bool = False) -> list[str]:
        """
        指定された文字列からログファイル一覧を取得する。
        :param log_file_path: ログファイルのパス（ワイルドカードを含む可能性がある）
        :param suffix: ファイルのサフィックス（例：.log）を指定する場合
        :param recursive: Trueの場合はサブディレクトリも再帰的に検索する
        :return: ログファイルのパスのリスト
        """
        extracted_log_files = []
        result_log_files = []
        for pattern in log_file_patterns:
            if recursive:
                extracted_log_files.extend(glob.glob(pattern, recursive=True))
            else:
                extracted_log_files.extend(glob.glob(pattern))
        
        for file_path in extracted_log_files:
            # file_pathがディレクトリの場合はサブディレクトリ配下のファイルを取得. globで**/*を使用
            if os.path.isdir(file_path):
                file_path = os.path.join(file_path, '**', '*')
                result_log_files.extend(glob.glob(file_path, recursive=True))
            else:
                result_log_files.append(file_path)
                

        # サフィックスが指定されている場合は、サフィックスでフィルタリング
        if suffix:
            result_log_files = [f for f in result_log_files if f.endswith(suffix)]
        # 重複を排除して返す
        result_log_files = list(set(result_log_files))

        return result_log_files
    
    # vdp.logファイルから特定の時間帯に該当するログエントリを抽出する関数
    def extract_vdp_log_in_time_range(self, start_time: datetime, end_time: datetime, log_file_path: str) -> list[str]:
        """
        vdp.logファイルから指定された時間帯に該当するログエントリを抽出して出力する。
        以下のような形式を想定
        ---
        12404 [Thread-3] INFO  2025-03-30T14:13:37.556 com.denodo.tomcat.manager.TomcatManager [] - Unable to delete work directory content  
        java.lang.IllegalArgumentException: File system element for parameter 'directory' does not exist: '/xxx/xxx/work'
            at org.apache.commons.io.FileUtils.requireExists(FileUtils.java:2785) ~[commons-io.jar:2.15.1]
            at org.apache.commons.io.FileUtils.requireDirectoryExists(FileUtils.java:2751) ~[commons-io.jar:2.15.1]
        12478 [Thread-3] INFO  2025-03-30T14:13:37.630 com.denodo.tomcat.manager.TomcatManager [] - Tomcat script launched with value 0  
        24658 [Thread-3] INFO  2025-03-30T14:13:49.810 com.denodo.tomcat.manager.TomcatManager [] - Deploying Denodo SSO  
        ---
        :param start_time: 抽出開始時刻（datetimeオブジェクト）
        :param end_time: 抽出終了時刻（datetimeオブジェクト）
        :param log_file_path: vdp.logファイルのパス
        """

        # 日付が含まれる行のパターン.
        # 例: "12404 [Thread-3] INFO  2025-03-30T14:13:37.556 com.denodo.tomcat.manager.TomcatManager [] - ..."
        date_pattern = re.compile(r'^(\S+)\s+\[.*?\]\s+\S+\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)\s')
        
        return self.extract_entries(log_file_path, date_pattern, 2, start_time, end_time)

    def extract_vdp_data_catalog_log_in_time_range(self, start_time: datetime, end_time: datetime, log_file_path: str) -> list[str]:
        """
        vdp-data-catalog.logファイルから指定された時間帯に該当するログエントリを抽出して出力する。
        vdp.logと同様の形式を想定
        """
        return self.extract_vdp_log_in_time_range(start_time, end_time, log_file_path)

    def extract_design_studio_backend_log_in_time_range(self, start_time: datetime, end_time: datetime, log_file_path: str) -> list[str]:
        """
        design-studio-backend.logファイルから指定された時間帯に該当するログエントリを抽出して出力する。
        vdp.logと同様の形式を想定
        """
        return self.extract_vdp_log_in_time_range(start_time, end_time, log_file_path)

    def extract_sso_log_in_time_range(self, start_time: datetime, end_time: datetime, log_file_path: str) -> list[str]:
        """
        sso.logファイルから指定された時間帯に該当するログエントリを抽出して出力する。
        vdp.logと同様の形式を想定
        """
        return self.extract_vdp_log_in_time_range(start_time, end_time, log_file_path)



    def extract_process_log_in_time_range(self, start_time: datetime, end_time: datetime, log_file_path: str) -> list[str]:
        """
        vdp_process.logファイルから指定された時間帯に該当するログエントリを抽出して出力する。
        以下のような形式を想定
        ---
        257 processes at: 2025-07-12T13:14:09.141
    
        イメージ名                     PID セッション名     セッション# メモリ使用量 状態            ユーザー名                                             CPU 時間 ウィンドウ タイトル                                                     
        ========================= ======== ================ =========== ============ =============== ================================================== ============ ========================================================================
        """
        # 日付が含まれる行のパターン.
        # 例: "257 processes at: 2025-07-12T13:14:09.141"
        date_pattern = re.compile(r'^\d+\s+processes\s+at:\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)$')
        # グループ番号は1（マッチした日付部分）
        group_num = 1
        return self.extract_entries(log_file_path, date_pattern, group_num, start_time, end_time)

    def extract_sockets_log_in_time_range(self, start_time: datetime, end_time: datetime, log_file_path: str) -> list[str]:
        """
        sockets.logファイルから指定された時間帯に該当するログエントリを抽出して出力する。
        以下のような形式を想定
        ---
        2025-07-12T13:14:31.073 
        62 UDP sockets 
        154 TCP sockets: 
            CLOSE_WAIT:	3 
            ESTABLISHED:	55 
            LISTENING:	75 
            TIME_WAIT:	20 
            FIN_WAIT_2:	1 
        
            アクティブな接続
            プロトコル  ローカル アドレス      外部アドレス           状態            PID
            TCP
        """
        # 日付が含まれる行のパターン.
        # 例: "2025-07-12T13:14:31.073"
        date_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)\s*$')
        # グループ番号は1（マッチした日付部分）
        group_num = 1
        return self.extract_entries(log_file_path, date_pattern, group_num, start_time, end_time)

    def extract_vdp_connections_log_in_time_range(self, start_time: datetime, end_time: datetime, log_file_path: str) -> list[str]:
        """
        vdp_connections.logファイルから指定された時間帯に該当するログエントリを抽出して出力する。  
        以下のような形式を想定
        ServerName	Host	Port	NotificationType	ConnectionId	ConnectionStartTime	ConnectionEndTime	ClientIP	UserAgent	AccessInterface	SessionId	SessionStartTime	SessionEndTime	Login	DatabaseName	WebServiceName	JMSQueueName	IntermediateClientIP
        vdp	localhost	9997	logout	7	2025-07-12T12:53:00.486	2025-07-12T13:39:34.696	127.0.0.1	Denodo-Data-Catalog	JDBC	15	2025-07-12T12:53:00.470	2025-07-12T13:39:34.696	admin	admin	-	-	127.0.0.1
        """
        # 日付が含まれる行のパターン.
        # 例: vdp	localhost	9997	logout	7	2025-07-12T12:53:00.486	...
        date_pattern = re.compile(r'^\S+\s+\S+\s+\d+\s+\S+\s+\d+\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)\s+')
        # グループ番号は1（マッチした日付部分）
        group_num = 1
        # ヘッダー行のパターン
        header_pattern = re.compile(r'^ServerName\s+')
        return self.extract_entries(log_file_path, date_pattern, group_num, start_time, end_time, header_pattern=header_pattern)
    
    def extract_vdp_datasources_log_in_time_range(self, start_time: datetime, end_time: datetime, log_file_path: str) -> list[str]:
        """
        vdp-datasources.logファイルから指定された時間帯に該当するログエントリを抽出して出力する。
        以下のような形式を想定
        Date	DatabaseName	DataSourceType	DataSourceName	ActiveRequests	NumRequests	MaxActive	NumActive	NumIdle	PingStatus	PingExecutionTime	PingDuration	PingDownCause	MaxActiveXA	NumActiveXA	NumIdleXA	MaxActiveNoXA	NumActiveNoXA	NumIdleNoXA
        2025-07-12T13:14:00.485	admin	jdbc	vdpcachedatasource	0	0	-	-	-	-	-	-	-	-	-	-	-	-	-
        """
        # 日付が含まれる行のパターン.
        # 例: "2025-07-12T13:14:00.485	admin	jdbc	vdpcachedatasource	0	0	-	-	-	-	-	-	-	-	-	-	-	-	-"
        date_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)\s+')
        # グループ番号は1（マッチした日付部分）
        group_num = 1
        # ヘッダー行のパターン
        header_pattern = re.compile(r'^Date\s+')
        return self.extract_entries(log_file_path, date_pattern, group_num, start_time, end_time, header_pattern=header_pattern)

    def extract_vdp_queries_log_in_time_range(self, start_time: datetime, end_time: datetime, log_file_path: str) -> list[str]:
        """
        vdp-queries.logファイルから指定された時間帯に該当するログエントリを抽出して出力する。
        以下のような形式を想定
        ServerName	Host	Port	Id	Database	UserName	NotificationType	SessionId	StartTime	EndTime	Duration	WaitingTime	NumRows	State	Completed	Cache	Query	RequestType	Elements	UserAgent	AccessInterface	ClientIP	TransactionId	WebServiceName	CpuTime	CpuUsageAvg	CpuUsageMax	CpuUsageMaxTime	CpuUsageStdDev	EstimatedQueryCost	GlobalSecurityPoliciesApplied
        vdp	localhost	9997	51	admin	admin	startRequest	23	2025-07-12T14:13:59.779	-	-	-	-	-	-	-	DESC DATABASE admin VERSION 2	DESC	-	Denodo-Web-Design-Studio	Web-Design-Studio	127.0.0.1	-	-	-	-	-	-	-	-	-
        """
        # 日付が含まれる行のパターン.
        # 例: vdp	localhost	9997	51	admin	admin	startRequest	23	2025-07-12T14:13:59.779	...
        date_pattern = re.compile(r'^\S+\s+\S+\s+\d+\s+\d+\s+\S+\s+\S+\s+\S+\s+\d+\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)\s+')
        # グループ番号は1（マッチした日付部分）
        group_num = 1
        # ヘッダー行のパターン
        header_pattern = re.compile(r'^ServerName\s+')
        return self.extract_entries(log_file_path, date_pattern, group_num, start_time, end_time, header_pattern=header_pattern)

    def extract_vdp_query_datasources_log_in_time_range(self, start_time: datetime, end_time: datetime, log_file_path: str) -> list[str]:
        """
        vdp-querydatasources.logファイルから指定された時間帯に該当するログエントリを抽出して出力する。
        以下のような形式を想定
        ServerName	Host	Port	VDPProvider	VDPRegion	SessionId	QueryId	QueryState	RequestType	QueryStartTime	QueryEndTime	DatabaseName	UserName	AccessInterface	UserAgent	ClientIP	ClientProvider	ClientRegion	QueryResultRows	EstimatedQueryResultRowSize	DataSourceDatabaseName	DataSourceName	DataSourceType	DataSourceAdapter	StartTime	EndTime	ResponseTime	Query	State	Exception	DataSourceProvider	DataSourceRegion	NumRowsToVDP	EstimateRowSizeToVDP	NumRowsFromVDP	EstimateRowSizeFromVDP	NoDelegationCauses	MemoryLimitReached	NestedJoinRightAccess	NestedTotalRightAccesses	EstimatedNumRowsReadInSource	EstimatedNumBytesReadInSource	EstimatedSourceCost
        vdp	localhost	9997	-	-	23	61	OK	SELECT VIEW	2025-07-12T14:13:59.958	2025-07-12T14:14:00.006	admin	admin	Web-Design-Studio	Denodo-Web-Design-Studio	127.0.0.1	-	-	1	368	admin	dual	Stored Procedure	-	2025-07-12T14:13:59.988	2025-07-12T14:14:00.006	2025-07-12T14:14:00.006	-	OK	-	-	-	1	-	0	0	-	false	false	0	-	-	-1
        """
        # 日付が含まれる行のパターン.
        # 例: vdp	localhost	9997	-	-	23	61	OK	SELECT VIEW	2025-07-12T14:13:59.958	...
        date_pattern = re.compile(r'^\S+\s+\S+\s+\d+\s+\S+\s+\S+\s+\d+\s+\d+\s+\S+\s+\S+\s+\S+\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)\s+')
        # グループ番号は1（マッチした日付部分）
        group_num = 1
        # ヘッダー行のパターン
        header_pattern = re.compile(r'^ServerName\s+')
        return self.extract_entries(log_file_path, date_pattern, group_num, start_time, end_time, header_pattern=header_pattern)

    def extract_vdp_resources_log_in_time_range(self, start_time: datetime, end_time: datetime, log_file_path: str) -> list[str]:
        """
        vdp-resources.logファイルから指定された時間帯に該当するログエントリを抽出して出力する。
        以下のような形式を想定
        ServerName	Host	Port	Date	Metaspace	G1 Survivor Space	G1 Old Gen	G1 Eden Space	Code Cache	HeapMemoryUsage	NonHeapMemoryUsage	LoadedClassCount	TotalLoadedClassCount	ThreadCount	PeakThreadCount	VDPTotalConn	VDPActiveConn	VDPActiveRequests	VDPWaitingRequests	VDPTotalMem	VDPMaxMem	CPU%	GC_CC:G1 Young Generation	GC_CC:G1 Old Generation	GC_CT:G1 Young Generation	GC_CT:G1 Old Generation	GC%:G1 Young Generation	GC%:G1 Old Generation	GC%
        vdp	localhost	9997	2025-07-12T13:14:00.813	108605904/-1	6291456/-1	100916224/4294967296	23068672/-1	28587776/268435456	130276352/4294967296	148814768/-1	15431	15431	71	71	14	8	0	0	186646528	4294967296	0	18	0	112	0
        """
        # 日付が含まれる行のパターン.
        # 例: "vdp localhost 9997 2025-07-12T13:14:00.813 ..."
        date_pattern = re.compile(r'^\S+\s+\S+\s+\d+\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)\s+')
        # グループ番号は1（マッチした日付部分）
        group_num = 1
        # ヘッダー行のパターン
        header_pattern = re.compile(r'^ServerName\s+')
        return self.extract_entries(log_file_path, date_pattern, group_num, start_time, end_time, header_pattern=header_pattern)

    """
    vdp-threads.logファイルから指定された時間帯に該当するログエントリを抽出して出力する。
    以下のような形式を想定
    Thread dump start at: 2025-07-12T13:14:00.530

 
    "main" Id=1 in RUNNABLE CpuTime=9484375000 (running in native) 
        at java.base@17.0.11/sun.nio.ch.Net.accept(Native Method) 
        at java.base@17.0.11/sun.nio.ch.NioSocketImpl.accept(NioSocketImpl.java:760) 
        at java.base@17.0.11/java.net.ServerSocket.implAccept(ServerSocket.java:675) 
    """
    def extract_vdp_threads_log_in_time_range(self, start_time: datetime, end_time: datetime, log_file_path: str) -> list[str]:
        """
        vdp-threads.logファイルから指定された時間帯に該当するログエントリを抽出して出力する。
        :param start_time: 抽出開始時刻（datetimeオブジェクト）
        :param end_time: 抽出終了時刻（datetimeオブジェクト）
        :param log_file_path: vdp-threads.logファイルのパス
        """
        # 日付が含まれる行のパターン.
        # 例: "Thread dump start at: 2025-07-12T13:14:00.530"
        date_pattern = re.compile(r'^Thread dump start at:\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)$')
        # グループ番号は1（マッチした日付部分）
        group_num = 1
        return self.extract_entries(log_file_path, date_pattern, group_num, start_time, end_time)

    """
    vdp-loadcacheprocesses.logファイルから指定された時間帯に該当するログエントリを抽出して出力する。
    以下のような形式を想定
    SessionId	ServerName	Host	Port	NotificationType	NotificationTimestamp	Id	QueryPatternId	DatabaseName	ViewName	SqlViewName	ProjectedFields	NumConditions	VDPConditionList	CacheStatus	TtlStatusInCache	TtlInCache	QueryPatternState	Exception	NumOfInsertedRows	NumOfReceivedRows	StartQueryPatternStorageTime	EndQueryPatternStorageTime	QueryPatternStorageTime	StartCachedResultMetadataStorageTime	EndCachedResultMetadataStorageTime	CachedResultMetadataStorageTime	StartDataStorageTime	EndDataStorageTime	DataStorageTime
    string	string	string	int	string	datetime	int	int	string	string	string	string	int	string	string	string	int	int	datetime	datetime	datetime	datetime	datetime	datetime	datetime
    """
    def extract_vdp_loadcacheprocesses_log_in_time_range(self, start_time: datetime, end_time: datetime, log_file_path: str) -> list[str]:
        """
        vdp-loadcacheprocesses.logファイルから指定された時間帯に該当するログエントリを抽出して出力する。
        :param start_time: 抽出開始時刻（datetimeオブジェクト）
        :param end_time: 抽出終了時刻（datetimeオブジェクト）
        :param log_file_path: vdp-loadcacheprocesses.logファイルのパス
        """
        # 日付が含まれる行のパターン.
        # 例: string	string	string	int	string	datetime	...
        date_pattern = re.compile(r'^\S+\s+\S+\s+\S+\s+\d+\s+\S+\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)\s+')
        # グループ番号は1（マッチした日付部分）
        group_num = 1
        # ヘッダー行のパターン
        header_pattern = re.compile(r'^SessionId\s+')
        return self.extract_entries(log_file_path, date_pattern, group_num, start_time, end_time, header_pattern=header_pattern)

    # catalina.logから指定された時間帯のログエントリを抽出する関数
    def extract_catalina_log_in_time_range(self, start_time: datetime, end_time: datetime, log_file_path: str) -> list[str]:
        """
        catalina.logファイルから指定された時間帯に該当するログエントリを抽出して出力する。
        以下のような形式を想定. Date部分は短縮月形式（例: 19-Jul-2025）であることに注意.
        ---
        19-Jul-2025 14:06:07.860 情報 [RMI TCP Connection(18585)-127.0.0.1] org.apache.catalina.core.ApplicationContext.log Destroying Spring FrameworkServlet 'dispatcherServlet'
        """
        # 日付が含まれる行のパターン.
        # 例: "19-Jul-2025 14:06:07.860 ..."
        date_pattern = re.compile(r'^(\d{1,2}-\w{3}-\d{4}\s+\d{2}:\d{2}:\d{2}\.\d+)\s')
        # グループ番号は1（マッチした日付部分）
        group_num = 1
        return self.extract_entries(log_file_path, date_pattern, group_num, start_time, end_time, dateFormat=1)

    # process.logから指定された時間帯のプロセス数を時間単位で抽出する関数
    def extract_process_count_in_time_range(self, start_time: datetime, end_time: datetime, log_file_path: str) -> list[str]:
        """
        process.logファイルから指定された時間帯に該当するプロセス数を時間単位で抽出して出力する。
        以下のような形式を想定
        ---
        257 processes at: 2025-07-12T13:14:09.141
        """
        # 日付とプロセス数が含まれる行のパターン. 
        # 例: "257 processes at: 2025-07-12T13:14:09.141"
        date_pattern = re.compile(r'^(\d+)\s+processes\s+at:\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)$')
        # グループ番号は2（マッチした日付部分）
        group_num = 2
        # 日付:日付ごとのプロセス数を抽出するための辞書
        log_entries_dict = self.extract_entries_as_dict(log_file_path, date_pattern, group_num, start_time, end_time)
        result_list = []  # 結果を格納するリスト
        # ヘッダ行
        header_row = "Date\tProcess Count\n"
        result_list.append(header_row)

        for date_str, entries in log_entries_dict.items():
            # date_patternのグループ番号1を使用して、プロセス数を抽出
            for entry in entries:
                match = date_pattern.match(entry)
                if match:
                    count = match.group(1)
                    # ヘッダー行の形式の文字列にする。
                    result_str = f"{date_str}\t{count}\n"
                    # 結果をリストに追加
                    result_list.append(result_str)

        return result_list

    # sockets.logから指定された時間帯のプロセス数を時間単位で抽出する関数
    def extract_sockets_count_in_time_range(self, start_time: datetime, end_time: datetime, log_file_path: str) -> list[str]:
        """
        sockets.logファイルから指定された時間帯に該当するソケット数を時間単位で抽出して出力する。
        以下のような形式を想定
        ---
        62 UDP sockets 
        154 TCP sockets: 
            CLOSE_WAIT:	3 
            ESTABLISHED:	55 
            LISTENING:	75 
            TIME_WAIT:	20 
            FIN_WAIT_2:	1 
        """
        # 日付が含まれる行のパターン.
        # 例: "2025-07-12T13:14:31.073"
        date_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)\s*$')
        # グループ番号は1（マッチした日付部分）
        group_num = 1
        # 日付:日付ごとのソケット数を抽出するための辞書
        log_entries_dict = self.extract_entries_as_dict(log_file_path, date_pattern, group_num, start_time, end_time)
        result_list = []  # 結果を格納するリスト
        # ヘッダ行
        header_row = "Date\tUDP sockets\tTCP sockets\tCLOSE_WAIT\tESTABLISHED\tLISTENING\tTIME_WAIT\tFIN_WAIT_2\n"
        result_list.append(header_row)
        for date_str, entries in log_entries_dict.items():
            # 結果を格納する辞書
            result_dict = {
                "UDP sockets": 0,
                "TCP sockets": 0,
                "CLOSE_WAIT": 0,
                "ESTABLISHED": 0,
                "LISTENING": 0,
                "TIME_WAIT": 0,
                "FIN_WAIT_2": 0
            }  
            # UDP socketsにマッチする行を抽出
            udp_pattern = re.compile(r'^(\d+)\s+UDP sockets\s*$')
            # TCP socketsにマッチする行を抽出
            tcp_pattern = re.compile(r'^(\d+)\s+TCP sockets:\s*$')
            # TCP socketsにマッチした状態のフラグ
            tcp_state = False
            for entry in entries:
                udp_match = udp_pattern.match(entry)
                tcp_match = tcp_pattern.match(entry)
                if udp_match:
                    result_dict['UDP sockets'] = int(udp_match.group(1))
                elif tcp_match:
                    result_dict['TCP sockets'] = int(tcp_match.group(1))
                    tcp_state = True  # TCP socketsの状態を開始
                else:
                    #tcp_stateがTrueの場合、TCPの状態行を抽出
                    if tcp_state:
                        # 空行の場合はtcp_stateをFalseにする
                        if not entry.strip():
                            tcp_state = False
                            continue
                        # 状態行のパターンを定義
                        state_pattern = re.compile(r'^\s*+(\w+):\s*(\d+)')
                        # print(f"Processing entry: {entry}")
                        state_match = state_pattern.match(entry)
                        if state_match:
                            state_name = state_match.group(1)
                            count = int(state_match.group(2))
                            # print(f"State: {state_name}, Count: {count}")
                            result_dict[state_name] = count
            # ヘッダー行の形式の文字列にする。
            result_str = f"{date_str}\t{result_dict['UDP sockets']}\t{result_dict['TCP sockets']}\t{result_dict['CLOSE_WAIT']}\t{result_dict['ESTABLISHED']}\t{result_dict['LISTENING']}\t{result_dict['TIME_WAIT']}\t{result_dict['FIN_WAIT_2']}\n"
            # 結果をリストに追加 
            result_list.append(result_str)

        return result_list

    # vdp-threads.logから指定された時間帯のプロセス数を時間単位で抽出する関数
    def extract_vdp_threads_count_in_time_range(self, start_time: datetime, end_time: datetime, log_file_path: str) -> list[str]:
        """
        vdp-threads.logファイルから指定された時間帯に該当するスレッド数を時間単位で抽出して出力する。
        以下のような形式を想定 Id=数字(空白)の行を抽出
        ---
        Thread dump start at: 2025-07-12T13:14:00.530
        ・・・
        Id=1   	PrevCpuTime=9484375000  	CpuTime=9484375000  	ElapsedCpuTime=0           	ElapsedTime=120054	CPU%=0           	"main" 
        Id=2   	PrevCpuTime=0           	CpuTime=0           	ElapsedCpuTime=0           	ElapsedTime=120054	CPU%=0           	"Reference Handler" 
        Id=3   	PrevCpuTime=0           	CpuTime=0           	ElapsedCpuTime=0           	ElapsedTime=120054	CPU%=0           	"Finalizer" 
        Id=4   	PrevCpuTime=0           	CpuTime=0           	ElapsedCpuTime=0           	ElapsedTime=120054	CPU%=0           	"Signal Dispatcher" 
        ・・・
        """
        # 日付とスレッド数が含まれる行のパターン.
        # 例: "Thread dump start at: 2025-07-12T13:14:00.530"
        date_pattern = re.compile(r'^Thread dump start at:\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)$')
        # グループ番号は1（マッチした日付部分）
        group_num = 1
        # 日付:日付ごとのスレッド数を抽出するための辞書
        log_entries_dict = self.extract_entries_as_dict(log_file_path, date_pattern, group_num, start_time, end_time)
        # スレッド数を抽出するためのパターン
        thread_pattern = re.compile(r'^Id=\d+\s+.*$')
        result_list = []  # 結果を格納するリスト
        # ヘッダ行
        header_row = "Date\tThread Count\n"
        result_list.append(header_row)

        for date_str, entries in log_entries_dict.items():
            count = 0
            for entry in entries:
                match = thread_pattern.match(entry)
                if match:
                    count += 1
            # ヘッダー行の形式の文字列にする。
            result_str = f"{date_str}\t{count}\n"
            # 結果をリストに追加
            result_list.append(result_str)

        return result_list

    # 指定されたログタイプに基づいて、対応するログファイルから指定された時間帯のログエントリを抽出する関数
    def extract_log_in_time_range(self, start_time: datetime, end_time: datetime, log_type: str, log_file_path: str) -> list[str]:
        """
        指定されたログタイプに基づいて、対応するログファイルから指定された時間帯のログエントリを抽出する。
        :param start_time: 抽出開始時刻（datetimeオブジェクト）
        :param end_time: 抽出終了時刻（datetimeオブジェクト）
        :param log_type: ログの種類（例：vdp, processesなど）
        :param log_file_path: ログファイルのパス
        """
        if log_type not in self.log_types:
            raise ValueError(f"無効なログタイプ: {log_type}. 有効なログタイプは: {', '.join(self.log_types)}")

        # ログタイプに応じて、対応する抽出関数を呼び出す
        if log_type == self.log_type_vdp:
            return self.extract_vdp_log_in_time_range(start_time, end_time, log_file_path)
        elif log_type == self.log_type_vdp_data_catalog:
            return self.extract_vdp_data_catalog_log_in_time_range(start_time, end_time, log_file_path)
        elif log_type == self.log_type_design_studio_backend:
            return self.extract_design_studio_backend_log_in_time_range(start_time, end_time, log_file_path)
        elif log_type == self.log_type_sso:
            return self.extract_sso_log_in_time_range(start_time, end_time, log_file_path)
        elif log_type == self.log_type_processes:
            return self.extract_process_log_in_time_range(start_time, end_time, log_file_path)
        elif log_type == self.log_type_sockets:
            return self.extract_sockets_log_in_time_range(start_time, end_time, log_file_path)
        elif log_type == self.log_type_vdp_connections:
            return self.extract_vdp_connections_log_in_time_range(start_time, end_time, log_file_path)
        elif log_type == self.log_type_vdp_datasources:
            return self.extract_vdp_datasources_log_in_time_range(start_time, end_time, log_file_path)
        elif log_type == self.log_type_vdp_queries:
            return self.extract_vdp_queries_log_in_time_range(start_time, end_time, log_file_path)
        elif log_type == self.log_type_vdp_querydatasources:
            return self.extract_vdp_query_datasources_log_in_time_range(start_time, end_time, log_file_path)
        elif log_type == self.log_type_vdp_resources:
            return self.extract_vdp_resources_log_in_time_range(start_time, end_time, log_file_path)
        elif log_type == self.log_type_vdp_threads:
            return self.extract_vdp_threads_log_in_time_range(start_time, end_time, log_file_path)
        elif log_type == self.log_type_vdp_loadcacheprocesses:
            return self.extract_vdp_loadcacheprocesses_log_in_time_range(start_time, end_time, log_file_path)
        elif log_type == self.log_type_catalina:
            return self.extract_catalina_log_in_time_range(start_time, end_time, log_file_path)

        raise ValueError(f"無効なログタイプ: {log_type}")

    # 指定されたログタイプに基づいて、対応するログファイルから指定された時間帯のログエントリのカウントを行う関数
    # log_typeがprocessesの場合は、プロセス数を時間単位で抽出する。
    # log_typeがsocketsの場合は、ソケット数を時間単位で抽出する。
    # log_typeがvdp_threadsの場合は、スレッド数を時間単位で抽出する。
    def count_log_entries_in_time_range(self, start_time: datetime, end_time: datetime, log_type: str, log_file_path: str) -> list[str]:
        """
        指定されたログタイプに基づいて、対応するログファイルから指定された時間帯のログエントリのカウントを行う。
        :param start_time: 抽出開始時刻（datetimeオブジェクト）
        :param end_time: 抽出終了時刻（datetimeオブジェクト）
        :param log_type: ログの種類（例：vdp, processesなど）
        :param log_file_path: ログファイルのパス
        """
        if log_type not in [self.log_type_processes, self.log_type_sockets, self.log_type_vdp_threads]:
            raise ValueError(f"無効なログタイプ: {log_type}. 有効なログタイプは: {', '.join(self.log_types)}")

        # ログタイプに応じて、対応するカウント関数を呼び出す
        if log_type == self.log_type_processes:
            entries = self.extract_process_count_in_time_range(start_time, end_time, log_file_path)
            return entries
        elif log_type == self.log_type_sockets:
            entries = self.extract_sockets_count_in_time_range(start_time, end_time, log_file_path)
            return entries
        elif log_type == self.log_type_vdp_threads:
            entries = self.extract_vdp_threads_count_in_time_range(start_time, end_time, log_file_path)
            return entries
        else:
            raise ValueError(f"無効なログタイプ: {log_type}")


def count_log_entries_main(
        start_time: datetime, end_time: datetime, logfiles: list[str], 
        log_type: Optional[str] = None, output_dir: Optional[str] = None, verbose_output: bool = False) -> list[str]:

    log_util = DenodoLogUtil()
    local_log_types = None

    output_log_files = []  # 出力ファイルのパスを格納するリスト
    
    extracted_logfiles = log_util.get_log_files(logfiles, suffix='.log', recursive=True)

    for log_file_path in extracted_logfiles:
        try:
            # ログタイプが指定されていない場合は、ログファイルのパスから自動判別
            if log_type:
                local_log_types = log_type
            else:
                local_log_types = log_util.detect_log_type(log_file_path)
            if not local_log_types:
                print(f"警告: ログファイル '{log_file_path}' のログタイプを自動判別できませんでした。")
                continue
            # processes.log, sockets.log, vdp-threads.logのいずれかのログタイプが指定されている場合は、対応するログファイルから指定された時間帯のログエントリのカウントを行う
            if not local_log_types in [log_util.log_type_processes, log_util.log_type_sockets, log_util.log_type_vdp_threads]:
                continue
            print(f"ログカウント処理 ログタイプ:{local_log_types} ログファイル: {log_file_path}")
            log_entries = log_util.count_log_entries_in_time_range(start_time, end_time, local_log_types, log_file_path)

        except ValueError as e:
            print(f"エラー: {e}")
            raise e
        # 出力ディレクトリが指定されている場合は、ファイルに保存
        if output_dir:
            output_log_files.append(log_util.save_entries_to_file(start_time, end_time, 'count-' + local_log_types , log_entries, output_dir))

        # verbose_outputオプションが指定されている場合は、ログエントリをコンソールに出力
        if verbose_output:
            # ログエントリが空でない場合のみ出力
            if log_entries:
                print(f"抽出された{local_log_types}ログエントリ:")
            else:
                print(f"指定された時間帯に該当する{local_log_types}ログエントリはありません。")
            for entry in log_entries:
                print(entry)

    return output_log_files

def extract_log_main(
        start_time: datetime, end_time: datetime, logfiles: list[str], 
        log_type: Optional[str] = None, output_dir: Optional[str] = None, verbose_output: bool = False) -> list[str]:
    log_util = DenodoLogUtil()    
    local_log_types = None
    output_log_files = []  # 出力ファイルのパスを格納するリスト

    extracted_logfiles = log_util.get_log_files(logfiles, suffix='.log', recursive=True)

    for log_file_path in extracted_logfiles:
        log_entries = []
        try:
            # ログタイプが指定されていない場合は、ログファイルのパスから自動判別
            if log_type:
                local_log_types = log_type
            else:
                local_log_types = log_util.detect_log_type(log_file_path)
            if not local_log_types:
                print(f"警告: ログファイル '{log_file_path}' のログタイプを自動判別できませんでした。")
                continue
            print(f"ログ抽出処理 ログタイプ:{local_log_types} ログファイル: {log_file_path}")
            # 指定されたログタイプに基づいて、対応するログファイルから指定された時間帯のログエントリを抽出
            log_entries = log_util.extract_log_in_time_range(start_time, end_time, local_log_types, log_file_path)

        except ValueError as e:
            print(f"エラー: {e}")
            raise e 

        # 出力ディレクトリが指定されている場合は、ファイルに保存
        if output_dir:
            output_log_files.append(log_util.save_entries_to_file(start_time, end_time, local_log_types, log_entries, output_dir))

        # verbose_outputオプションが指定されている場合は、ログエントリをコンソールに出力
        if verbose_output:
            # ログエントリが空でない場合のみ出力
            if log_entries:
                print(f"抽出された{local_log_types}ログエントリ:")
            else:
                print(f"指定された時間帯に該当する{local_log_types}ログエントリはありません。")
            for entry in log_entries:
                print(entry)

    return output_log_files

def denodo_log_util_main(start_time_str: str, end_time_str: str, logfiles: list[str], 
        log_type: Optional[str] = None, output_dir: Optional[str] = None, verbose_output: bool = False) -> list[str]:

    start_time = log_util.parse_iso_datetime(start_time_str)
    end_time = log_util.parse_iso_datetime(end_time_str)

    log_type_local = log_type
    extract_log_main_result = extract_log_main(start_time, end_time, logfiles, log_type_local, output_dir, verbose_output)

    log_type_local = log_type
    count_log_entries_main_result = count_log_entries_main(start_time, end_time, logfiles, log_type_local, output_dir, verbose_output)

    print("抽出されたログファイル:")
    for file_path in extract_log_main_result:
        print(file_path)
    print("カウントされたログファイル:")
    for file_path in count_log_entries_main_result:
        print(file_path)

    return extract_log_main_result + count_log_entries_main_result  

if __name__ == "__main__":
    # テスト用のコードをここに追加することができます。
    # 例: DenodoLogUtil().extract_vdp_log_in_time_range(datetime(2025, 3, 30, 14, 0), datetime(2025, 3, 30, 15, 0), 'path/to/vdp.log')

    # argparseを使用してコマンドライン引数を解析
    # -- 引数の形式: python denodo-log-util.py <start_time> <end_time> <log_file_path> -t "vdp" または "vdp_process"
    log_types = DenodoLogUtil.log_types

    parser = argparse.ArgumentParser(description='Denodoログファイルから指定した時間帯のログを抽出します。')
    parser.add_argument('start_time', type=str, help='抽出開始時刻 (ISOフォーマット)')
    parser.add_argument('end_time', type=str, help='抽出終了時刻 (ISOフォーマット)')
    # logfiles ログファイルのパスを指定する引数. 複数のファイルの指定が可能。ｍた、pathlibを用いてワイルドカードを使用してファイルを指定することも可能。
    parser.add_argument('logfiles', nargs='+', type=str, help='ログファイルのパス (ワイルドカードを使用して複数指定可能)')

    parser.add_argument('-t', '--log_type', type=str, choices=log_types, help=' ログの種類を指定するオプション。指定しない場合は自動判別モード。ファイル名に含まれる文字列に基づいてログの種類を判別する。')
    # 出力ディレクトリの指定。ディレクトリ指定があった場合は、出力ファイルをそのディレクトリに保存する。
    parser.add_argument('-o', '--output_dir', type=str, help='出力ディレクトリのパス (オプション)')
    # コンソール表示を行うオプション。 
    parser.add_argument('-v', '--verbose_output', action='store_true', help='コンソールにログエントリを出力するオプション。指定しない場合は、出力ファイルにのみ保存する。')

    log_util = DenodoLogUtil()
    args = parser.parse_args()
    start_time_str = args.start_time
    end_time_str = args.end_time
    log_file_path_list = args.logfiles
    log_type = args.log_type
    output_dir = args.output_dir
    verbose_output = args.verbose_output

    denodo_log_util_main(start_time_str, end_time_str, log_file_path_list, log_type, output_dir, verbose_output)
