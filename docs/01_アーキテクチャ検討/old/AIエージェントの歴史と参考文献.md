# AIエージェントの歴史と参考文献

本資料は、AIエージェント技術の進化の歴史と、本システムの Application 層・Tool 層の設計を支える参考文献を一体で整理した統合版である。歴史的背景、アーキテクチャとの対応関係、参考文献一覧を1つの流れで確認できるように再構成した。

## 1. AIエージェント技術の進化の歴史（2023年〜現在）

### 第1期：LLMの「脳」としての発見と基本構造の定義（2023年）
* 初期の大規模言語モデル（LLM）は「一度テキストを出力して終わり」という単発処理しかできなかった。この限界を突破したのが、OpenAIのLilian Weng氏によるブログ（[*LLM Powered Autonomous Agents*](https://lilianweng.github.io/posts/2023-06-23-agent/), 2023）や代表的サーベイ論文（[*A Survey on LLM based Autonomous Agents*](https://arxiv.org/abs/2308.11432), 2023）である。
* これらは、LLMを「推論エンジン（脳）」とし、**「Planning（計画）」「Memory（記憶）」「Action（行動）」**を結合すべきだと定義した。これが全エージェントの「基本解剖図」となった。

### 第2期：複雑性の克服と運用基盤の誕生（2023年末〜2024年）
#### 潮流A：複雑性の克服と「マルチエージェント・パターン」の体系化
1つの巨大なプロンプトにすべてを任せる手法は精度低下を招き、制御不能になる問題が深刻化した。これに対し、エージェントを専門化して連携させる手法が普及した。
* **マルチエージェント設計**: Microsoftの [*AutoGen*](https://arxiv.org/abs/2308.08155)（2023）が合議手法を確立し、[*Agent Design Pattern Catalogue*](https://arxiv.org/abs/2405.10467)（2024）によって「ルーティング」や「オーケストレーター・ワーカー」など18の設計パターンが理論的に体系化された。
* **LangChainからLangGraphへの変遷**: 従来の直線的な制御フローから、**「循環（Cycles）」と「持続的な状態管理（Persistence）」**を可能にするグラフ構造へのシフトが起きた。
* **ベストプラクティスの明文化**: Anthropicのレポート [*Building effective agents*](https://www.anthropic.com/research/building-effective-agents)（2024年末）により、「制御フローを人間が固定する Workflow」と「LLMが動的に決定する Agent」の連続体（スペクトラム）という指針が提示された。

#### 潮流B：実運用の壁と「スキャフォールディング（足場組み）」の誕生
自律型エージェントの実運用において、「文脈の忘却」や「無限ループ」といった破綻が露呈した。この時期、LLMをエージェント化するには、LLM自身の性能向上よりも、それを取り囲むシステム側の周辺構造、すなわち**「Agent Scaffolding（エージェントの足場組み）」**が不可欠であるという認識が広がった。
* **理論の体系化**: [*CoALA*](https://arxiv.org/abs/2309.02427)（2023）は、LLMを脳として機能させるために外部システムが提供する「作業メモリ」や「意思決定サイクル」を「認知アーキテクチャ」として体系化した。
* **メモリ管理の革新**: [*MemGPT*](https://arxiv.org/abs/2310.08560)（2023）は、コンテキストウィンドウの限界をOSのメモリ管理（ページング）に見立てて解決する手法を提案した。
* **実装基盤の進化**: LangChain等に見られた「同期的・オンメモリ」な人間介在（HITL）の限界を突破するため、**状態（State）をDBに永続化し、安全に再開できる Checkpointer を備えた LangGraph** が誕生した。

### 第3期：実運用化を支える「2つの潮流」（2025年〜2026年）
エージェントを本番業務に投入するために、以下の2つの概念が並列・相互補完的に発展した。

* **【潮流A：ハイブリッド構成の定着（パラダイムシフト）】**
    「すべてをAIに任せるのは非効率」という教訓から、コスト・速度・確実性を両立する[*Autonoma*](https://arxiv.org/abs/2603.19270)（2026）的な階層型アプローチ、すなわち定型処理は WF 型、判断や合議を伴う難所は SV 型、探索的タスクは自律型へ分けるハイブリッド構成が、ビジネスの最適解となった。
* **【潮流B：ハーネスエンジニアリングの確立（実装技術）】**
    スキャフォールディングを産業レベルで深化させた概念として、**「Harness Engineering（ハーネスエンジニアリング）」**が確立された。Mitchell Hashimoto氏の [*My AI Adoption Journey (Step 5: Engineer the Harness)*](https://mitchellh.com/writing/my-ai-adoption-journey)（2025-2026）や、OpenAIの [*Harness engineering*](https://openai.com/index/harness-engineering/)（2026年2月）、Anthropicの [*Harness design*](https://www.anthropic.com/engineering/harness-design-long-running-apps)（2026年3月）が相次いで発表された。プロンプトの工夫ではなく、**実行のサンドボックス化や状態の永続化、自動テスト環境などの「環境（ハーネス）」を作り込むこと**で、長時間のタスク完遂を保証する技術が確立された。

---

## 2. 歴史的背景と本システム・アーキテクチャの関係

当システムの設計は、これら発展フェーズで得られた業界の教訓をエンタープライズ基準で統合したものである。最大の特徴は、**「最適な設計パラダイム」と「堅牢な実装エンジニアリング」の両輪をシステム基盤として実装している点**にある。

**① 「Application層」と「Tool層」の分離（第1期の教訓）**
第1期で定義された「脳」と「行動」の分離原則に基づき、Application層とTool層を明確に分離している。これにより、AIが勝手にシステムを操作するリスクを抑え、ガバナンスを集中させている。

**② ハイブリッド構成の導入：潮流A（パラダイム）の体現**
第2期・第3期の潮流Aで確立された「マルチエージェント設計」と「ハイブリッド構成」の思想に従い、Application層を**制御フローの委譲度**に応じて3つに分類している。
* **WF型（Dify / 固定フローの LangGraph）**: 人間が経路を事前定義し、予測可能な定型処理を安全かつ低コストに実行する。
* **SV型（LangGraph / DeepAgents 等）**: 人間が状態遷移や枠組みを決め、その中でのタスク分担、合議、再試行をAIに部分委譲する。要件に応じて、生の LangGraph を基盤に独自ハーネスを実装する選択と、DeepAgents 等の上位ライブラリを活用する選択を使い分ける。
* **自律型（DeepAgents / Claude Code 等）**: AIに計画と実行を完全委譲し、高度な推論や探索が求められるタスクを解決する。

単一の型に寄せるのではなく、要求受付時に Coordinator 相当の入口ユニットが意図解釈とルーティングを担い、外側を WF 型、内側を SV 型、必要に応じて限定的に自律型を用いることで、実務に適したハイブリッドマルチエージェント構成を組み立てる。

**③ 各型とハイブリッド構成を支えるハーネスの実装：潮流B（実装技術）の体現**
自律性を持たせた SV 型・自律型、さらにはそれらを含むハイブリッドマルチエージェント構成を本番稼働させるため、第2期・第3期の潮流Bで提唱された**ハーネスエンジニアリング**をインフラレベルで組み込んでいる。ただし、本システムでは記憶管理やコンテキスト圧縮の機構を独自に再発明することは避け、**各実装基盤やエージェントが持つ標準アーキテクチャへ責務を委譲（Offload）**している。
* **SV型の記憶管理**: LangGraph の Checkpointer による全状態の永続化、Pause / Resume、非同期 HITL をベースとしつつ、プロンプト肥大化を防ぐため、Graph 内部のノード処理や上位ライブラリが提供する動的要約、メッセージ切り詰めなどのコンテキスト圧縮を標準設計として組み込む。
* **自律型の記憶管理**: Cline の memory-bank のようなファイルベースの文脈保持や、各コーディングエージェントが内部で備える RAG 機構、自動要約の仕組みをそのまま活用する。

加えて、ハイブリッド構成全体では、型をまたぐ状態引継ぎ、共通トレース、承認ポイントの一貫性、監査可能性といった横断要件をハーネスとして担保する。

本システムは、権限を隔離したサンドボックス環境、状態保持の基盤、監査可能な実行環境の提供に特化することで、各ツールの進化に追従しつつ、長時間のタスクを安全に完遂する安定性を実体化している。

---

## 3. 参考文献

本章では、本システムの Application 層・Tool 層が依拠するAIエージェントの概念定義、およびアーキテクチャ設計の妥当性を裏付ける業界標準の参考文献と学術論文を列挙する。

### I. 初期の概念（AIエージェントの基本構造と定義）
このセクションでは、2023年頃までに確立された「単なる言語生成AI」と「AIエージェント」を区別するための根本的な定義と、システムとして備えるべき基本モジュールを示す。

#### 1. 産業界における一般的なエージェント定義（NVIDIA）
* **文献名**: *AI エージェントとは | NVIDIA 用語集*
* **リンク**: [https://www.nvidia.com/ja-jp/glossary/ai-agents/](https://www.nvidia.com/ja-jp/glossary/ai-agents/)
* **概要**: AIエージェントが高レベルな目標を自律的に達成するために**「推論・計画」「メモリ」「ツール実行」**という主要な構成要素を組み合わせていることを明記している。
* **本書のアーキテクチャとのマッピング**: 本書の「Application層」と「Tool層」の役割分担が、業界標準のアーキテクチャであるという根拠になる。

#### 2. 自律型エージェントの究極形態と実装概念（OpenAI）
* **文献名**: *LLM Powered Autonomous Agents* (Lilian Weng, OpenAI Blog, 2023年6月)
* **リンク**: [https://lilianweng.github.io/posts/2023-06-23-agent/](https://lilianweng.github.io/posts/2023-06-23-agent/)
* **概要**: AI自身がエラーからの回復を含めた「思考→行動→観察」のループを自力で回し続ける**完全自動化を見据えたエージェント像**を定義している。
* **本書のアーキテクチャとのマッピング**: 本書の3分類における**自律型**の技術的な羅針盤であり、権限隔離や強制停止条件が不可欠であることの理論的根拠になる。

#### 3. 学術的・概念的な定義（AIエージェントの内部モジュール構造）
* **文献名**: *A Survey on Large Language Model based Autonomous Agents* (arXiv:2308.11432)
* **リンク**: [https://arxiv.org/abs/2308.11432](https://arxiv.org/abs/2308.11432)
* **概要**: **「Profile」「Memory」「Planning」「Action」**という4つのモジュール構造を提示した代表的サーベイ論文である。
* **本書のアーキテクチャとのマッピング**: Application層が Planning として機能し、そこから生じる Action と Memory の安全な実行インターフェースとして Tool層を配置する設計の妥当性を示している。

#### 4. SV型（スーパーバイザー・HITL・合議）の概念的裏付け
* **文献名**: *AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation* (arXiv:2308.08155)
* **リンク**: [https://arxiv.org/abs/2308.08155](https://arxiv.org/abs/2308.08155)
* **概要**: 複数の特化型エージェントの対話によって複雑なタスクを解決するフレームワーク「AutoGen」の基盤論文である。
* **本書のアーキテクチャとのマッピング**: エージェント間での役割分担や、人間の承認を介在させるマルチエージェント設計の有効性を実証しており、本資料の SV 型の裏付けとなる。

### II. それを拡張した現在の概念（実装パターンの深化とスキャフォールディング）
このセクションでは、初期の抽象的な概念を実運用に乗せるために発展した、2024年以降の**Agent Scaffolding**や、実践的なコンテキスト管理、制御フローに関する最新のアーキテクチャ論を示す。

#### 5. AIエージェント構成に関する業界標準レポート（WF/SV/自律型の分類）
* **文献名**: *Building effective agents* (Anthropic, 2024年12月)
* **リンク**: [https://www.anthropic.com/research/building-effective-agents](https://www.anthropic.com/research/building-effective-agents)
* **概要**: システムを「Workflow」と「Agent」の連続体として捉えるベストプラクティス集である。
* **本書のアーキテクチャとのマッピング**: 本書における **WF型 / SV型 / 自律型** の3層定義と根底で共鳴しており、実装基盤を選択する指針となる。

#### 6. スキャフォールディングの体系化（足場組みの理論）
* **文献名**: *Cognitive Architectures for Language Agents (CoALA)* (arXiv:2309.02427)
* **リンク**: [https://arxiv.org/abs/2309.02427](https://arxiv.org/abs/2309.02427)
* **概要**: LLMをエージェント化するために必要な周辺コードを「認知アーキテクチャ」として体系化した論文である。
* **本書のアーキテクチャとのマッピング**: LangGraph などが担う、状態管理、ループ制御、チェックポイントといったシステム的支援の必要性を学術的に裏付ける。

#### 7. コンテキスト圧縮と高度な記憶管理（Memoryの実践）
* **文献名**: *MemGPT: Towards LLMs as Operating Systems* (arXiv:2310.08560)
* **リンク**: [https://arxiv.org/abs/2310.08560](https://arxiv.org/abs/2310.08560)
* **概要**: 限られたコンテキストウィンドウと外部ストレージを「ページング機能」で動的に管理するアーキテクチャを提唱した論文である。
* **本書のアーキテクチャとのマッピング**: 動的要約や memory-bank のようなファイルへの状態書き出しといった記憶管理機構の重要性を実証している。

#### 8. アーキテクチャのパターン分類（18の設計パターン）
* **文献名**: *Agent Design Pattern Catalogue: A Collection of Architectural Patterns for Foundation Model based Agents* (arXiv:2405.10467)
* **リンク**: [https://arxiv.org/abs/2405.10467](https://arxiv.org/abs/2405.10467)
* **概要**: LLMを活用したAIエージェントのアーキテクチャパターンを18種類にカタログ化した論文である。
* **本書のアーキテクチャとのマッピング**: 本資料におけるWF型、SV型、自律型の連携パターンの理論的根拠として有用である。

#### 9. 3つの型を階層的に組み合わせた最新の実践例（2026年最新）
* **文献名**: *Autonoma: A Hierarchical Multi-Agent Framework for End-to-End Workflow Automation* (arXiv:2603.19270)
* **リンク**: [https://arxiv.org/abs/2603.19270](https://arxiv.org/abs/2603.19270)
* **概要**: Coordinator、Planner、Supervisor を組み合わせる階層型フレームワークを提唱する最新論文である。
* **本書のアーキテクチャとのマッピング**: 「業務の特性に合わせてWF型、SV型、自律型を適材適所で組み合わせる」という本アーキテクチャの妥当性を後押しする。

#### 10. 最新の実践的アーキテクチャ論（Harness Engineering）
* **文献名**: *My AI Adoption Journey (Step 5: Engineer the Harness)* (Mitchell Hashimoto, 2025-2026)
* **リンク**: [https://mitchellh.com/writing/my-ai-adoption-journey](https://mitchellh.com/writing/my-ai-adoption-journey)
* **概要**: エージェントが動きやすい環境をソフトウェアの力で構築する「ハーネスエンジニアリング」の重要性を認知させた実践的連載記事である。
* **文献名**: *Harness engineering: leveraging Codex in an agent-first world* (OpenAI, 2026年2月)
* **リンク**: [https://openai.com/index/harness-engineering/](https://openai.com/index/harness-engineering/)
* **概要**: CI/CD、サンドボックス、承認プロセスといった「エージェントの周辺環境」を整備することで出力の安定性を担保するという新パラダイムを定義した。
* **文献名**: *Harness design for long-running application development* (Anthropic, 2026年3月)
* **リンク**: [https://www.anthropic.com/engineering/harness-design-long-running-apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)
* **概要**: 長時間に及ぶ自律タスクを成功させるための「ハーネス設計」について解説した最新レポートである。
* **本書のアーキテクチャとのマッピング**: 各型とハイブリッド構成を支えるハーネスが、単なる実装上の便利機能ではなく、業務適用を成立させる設計責務であることを裏付ける。