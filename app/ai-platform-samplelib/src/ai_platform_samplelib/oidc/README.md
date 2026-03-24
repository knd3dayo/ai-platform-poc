# Zitadel OIDC Sample

このディレクトリには、以下の流れを確認するための PoC 実装が入っています。

1. クライアントが ZITADEL で OAuth 認証を行い access token を取得する
2. BFF が Bearer token を受け取り、署名・issuer・audience を検証する
3. BFF が Bearer token を下流 backend に転送する
4. backend が Bearer token を再検証し、認証・認可に利用する

## 前提条件

1. ZITADEL が `http://localhost:8080` で起動している
2. 対象の service account の Access Token Type が `JWT` になっている
3. service account key JSON が利用可能である
4. audience は `365171666990530564` を使用する

## 設定ファイル

非秘匿の設定値は [config.yml](config.yml) にあります。

- issuer
- expected audience
- default scopes
- downstream backend の URL
- 認可サンプルの許可 client_id
- role / custom claim 認可用の設定

秘匿情報やローカル環境依存の値は [.env](.env) で扱います。

最低限必要な設定は次です。

```env
OIDC_TEST_APPLICATION_KEY_PATH=/home/user/source/repos/ai-platform-poc/infra/91-zitadel/365508380967567366.json
```

## サーバー構成

### BFF

- 実装: [server.py](server.py)
- ポート: `5801`
- 役割:
  - Bearer token を受けて検証
  - 認可判定
  - 下流 backend への Bearer 転送

### Backend

- 実装: [backend_server.py](backend_server.py)
- ポート: `5802`
- 役割:
  - BFF から転送された Bearer token を再検証
  - claims を用いた認証・認可

## 起動方法

作業ディレクトリ:

```bash
cd /home/user/source/repos/ai-platform-poc/app/ai-platform-samplelib
```

### 1. backend を起動

```bash
PYTHONPATH=src .venv/bin/python -m ai_platform_samplelib.oidc.backend_server --port 5802
```

### 2. BFF を起動

```bash
PYTHONPATH=src .venv/bin/python -m ai_platform_samplelib.oidc.server --port 5801
```

## client 実行例

### Bearer token を取得して BFF にアクセス

```bash
PYTHONPATH=src .venv/bin/python -m ai_platform_samplelib.oidc.client --path /protected/me --print-token
```

### BFF から backend へ Bearer token を転送

```bash
PYTHONPATH=src .venv/bin/python -m ai_platform_samplelib.oidc.client --path /protected/forward/backend
```

## 主な endpoint

### BFF endpoint

- `/healthz`
- `/config`
- `/protected/me`
- `/protected/ping`
- `/protected/userinfo`
- `/protected/introspect`
- `/protected/authorize/client`
- `/protected/authorize/scope`
- `/protected/forward/backend`

### Backend endpoint

- `/healthz`
- `/config`
- `/backend/whoami`
- `/backend/authorize/client`
- `/backend/authorize/scope`
- `/backend/authorize/role`
- `/backend/authorize/claims`

## 動作確認の観点

### 1. クライアント認証

client が access token を取得できること。

期待値:

- `access_token` が返る
- JWT 構成では token に `.` が 2 つ含まれる

### 2. BFF 認証

`/protected/me` が `200` を返すこと。

期待値:

- issuer が `http://localhost:8080`
- audience が `365171666990530564`

### 3. backend 転送

`/protected/forward/backend` が `200` を返すこと。

期待値:

- BFF が Bearer token を backend に転送する
- backend 側でも subject と client_id が取れる

### 4. backend 認可

`/backend/authorize/client` が `200` を返すこと。

期待値:

- `client_id=login-client` が許可される

### 5. backend role / custom claim 認可

設定に応じて `/backend/authorize/role` と `/backend/authorize/claims` を利用できます。

期待値:

- project role claim が token に含まれ、`required_project_roles` を満たすと `200`
- custom claim が token に含まれ、`required_claim_values` を満たすと `200`

## 実装上の注意

1. 今回の PoC は service account の JWT access token を前提にしています
2. opaque token を使う場合は introspection client が token audience に含まれている必要があります
3. scope ベース認可 helper はありますが、現在の service account JWT では scope claim が空のため、PoC では client_id ベース認可を主に使っています
4. role / custom claim 認可は `config.yml` の `authorization.required_project_roles` と `authorization.required_claim_values` で切り替えます

## ZITADEL 側で role / custom claim を載せる設定

### project role を token に載せる

ZITADEL 管理画面で次を設定します。

1. Project で role を作成する
2. Role Assignments で対象 user または service account に role を割り当てる
3. Project の General Settings で role assertion を有効にする
4. 必要に応じて Application の Token Settings で User Roles inside ID Token を有効にする

PoC 側では次の設定と対応します。

```yaml
authorization:
  required_project_roles:
    - admin
  project_role_claim_keys:
    - urn:zitadel:iam:org:project:roles
    - urn:zitadel:iam:org:project:365171666990530564:roles
```

補足:

- ZITADEL の role claim は `urn:zitadel:iam:org:project:roles` または `urn:zitadel:iam:org:project:{projectid}:roles` で返ることがあります
- この PoC は両方の claim key を見られるようにしています

### custom claim を token に載せる

ZITADEL では custom claim は Actions の complement token flow で追加します。

代表例:

1. 固定値を custom claim として追加する
2. user metadata を custom claim として追加する
3. roles claim を別形式に整形して追加する

PoC 側では次の設定と対応します。

```yaml
authorization:
  required_claim_values:
    department:
      - sales
    feature_flags:
      - beta_user
```

この場合、token 内に例えば次のような claim が必要です。

```json
{
  "department": "sales",
  "feature_flags": ["beta_user", "can_export"]
}
```

## role / custom claim の確認手順

1. token を取得する
2. `/protected/me` または `/backend/whoami` の `claims` を確認する
3. claim 名と値が想定どおり入っていることを確認する
4. その claim 名を `authorization.project_role_claim_keys` または `authorization.required_claim_values` に反映する

## 関連ファイル

- [auth.py](auth.py)
- [settings.py](settings.py)
- [client.py](client.py)
- [server.py](server.py)
- [backend_server.py](backend_server.py)
- [config.yml](config.yml)
- [.env.example](.env.example)