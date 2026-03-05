# サポート担当者支援ツール
## 概要
* Clineの.clinerulesとmemory-bankを用いたサポート支援ツール
* `template`ディレクトリには各サポートケース用のmemory-bankのテンプレートが格納されている.  
* `template`ディレクトリのmemory-bankにはサポート対象の顧客環境の情報が含まれている。
* Clineのチャット画面で「サポートケース〇〇番のmemory-bankを初期化してください」と指示することで、
`support_case_〇〇`のディレクトリが作成されて、`template/memory-bank`から`support_case_〇〇/memory-bank`が作成される。
* その後、「サポートケース〇〇番の調査をお願いします」といった指示で、対象のサポートケースに対する処理が行われる。

## 機能

* エンドユーザーから受け取った問い合わせ内容をチェックします。
* (実装中)問い合わせ内容に関連した過去チケット情報をベクトルDBから抽出します。
* (実装中)問い合わせ内容に関連したマニュアル情報をベクトルDBから抽出します。
* ログファイル、画像ファイルを参照して原因調査を行います。
* バックエンドサポートへの問い合わせ内容を作成します。


## ディレクトリ構成
* template  
  サポートケース毎のmemory-bankのテンプレートを格納しています。  
* support_case_**    
  サポートケース毎に作成されるディレクトリ。  

* support_case_**/input_data
  顧客から受領したログファイル、画像ファイルなどを格納するディレクトリ
* support_case_**/input_data/logs  
  顧客から連携されたログファイル  
* support_case_**/input_data/logs_in_timerange  
  問い合わせに関する事象が発生した時間帯のログファイル  
* support_case_**/input_data/images  
  問い合わせに関する画像ファイル  
* support_case_**/output_data/inquiries-check.txt  
  顧客からの問い合わせ内容をチェックした結果

## 準備
1. vscodeを起動して拡張機能`Cline`をインストールします。
2. Clineの設定を行います。
  vscodeの左側にあるアイコンからClineを選択して`Settings` > `API Configuration`を選択。AI Providerの設定を行います。
3. git cloneでこのプロジェクトをローカルにダウンロードします.
4. サポートケースを作成する  
  vscodeの左側にあるアイコンからClineを選択して、以下のとおり入力
  ```
  「サポートケース〇〇番を初期化してください」と入力。  
  ```
  サポートケース用のディレクトリ(support_case_〇〇)が作成される。
5. support_case_〇〇/memory-bank/activeContext.mdに問い合わせ内容を記入する。
6. support_case_〇〇/logsに顧客から受領したログファイルを格納
7. support_case_〇〇/imagesに顧客から受領した画像ファイルを格納
8. 顧客から受領したログファイルから問い合わせに関する事象発生時間帯のログを抽出
  ```
  cd support_case_〇〇
  python ..\denodo-log-util.py -o logs_in_timerange logs/* <開始時刻>　<終了時刻> logs/*
  ```
  例：コマンド
  ```
  python ..\denodo-log-util.py  -o logs_in_timerange 2025-03-12T13:14:00:37 2025-07-12T17:09:21.894 logs\*
  ```
  例：実行結果
  ```
  ログ抽出処理 ログタイプ:vdp-threads ログファイル: ～\logs\vdp-threads.log
  ログ抽出処理 ログタイプ:vdp-datasources ログファイル: ～\logs\logs\vdp-datasources.log
  ログ抽出処理 ログタイプ:vdp-querydatasources ログファイル: ～\logs\logs\vdp-querydatasources.log
  ログ抽出処理 ログタイプ:vdp-queries ログファイル: ～\logs\logs\vdp-queries.log
  ログ抽出処理 ログタイプ:vdp-loadcacheprocesses ログファイル: ～\logs\logs\vdp-loadcacheprocesses.log
  ログ抽出処理 ログタイプ:processes ログファイル: ～\logs\logs\processes.log
  ログ抽出処理 ログタイプ:sockets ログファイル: ～\logs\logs\sockets.log
  ログ抽出処理 ログタイプ:vdp-connections ログファイル: ～\logs\logs\vdp-connections.log
  ログ抽出処理 ログタイプ:vdp-resources ログファイル: ～\logs\logs\vdp-resources.log
  ログカウント処理 ログタイプ:vdp-threads ログファイル: ～\logs\logs\vdp-threads.log
  ログカウント処理 ログタイプ:processes ログファイル: ～\logs\logs\processes.log
  ログカウント処理 ログタイプ:sockets ログファイル: ～\logs\logs\sockets.log
  ```
9. vscodeの左側にあるアイコンからClineを選択して、以下のとおり入力
  ```
  「サポートケース〇〇番の調査を開始してください」
  ```
10. support_case_〇〇/memory-bank/activeContext.mdに調査結果が出力される。 


