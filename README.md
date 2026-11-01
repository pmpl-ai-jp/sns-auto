# sns-auto：Instagram・Threads 自動運用（IT転職・ITスクール × AI活用）

月額0〜800円ほど（AIのAPIのみ従量課金）で、投稿の生成 → ガードレールチェック → 予約投稿 → 運用ログ作成までを自動で回します。

## 仕組み（全自動モード）
6つの役割のAIエージェントが、毎日自動で回ります。

| 役割 | タイミング | 内容 |
|---|---|---|
| 分析係 | 毎朝6:00 | 公開済み投稿の反応（Threads：返信・再投稿、IG：保存・シェア）を取得し、テーマごとの成績を出す |
| リサーチ係 | 毎朝6:00 | テーマと、最近伸びた投稿からネタ候補を8個出す |
| 企画係 | 毎朝6:00 | 成績の良いテーマの割合を増やす（基本割合の0.7〜1.5倍） |
| 執筆係 | 毎朝6:00 | Threads 6本＋IGカルーセル1本を書く（上位モデルのClaude Sonnet 5.5。伸びた投稿をお手本として渡す） |
| チェック係 | 毎回 | NGワード・数字・体験談の機械チェック＋AIの論理チェック（書いたモデルとは別のClaude Haiku 5.5）。通らなければ書き直し、最後まで通らなければ捨てる |
| 返信係 | 1日4回 | 自分の投稿への返信・コメントに公式APIで返事（1日30件まで、お金や個別相談の話題は返さない） |
| 公開 | 毎時 | Threadsは7・9・12・15・19・22時、IGは20時に公開 |
| 週次 | 月曜9:00 | トークン更新、noteの運用ログ下書き |

## 使うAIモデル
| 役割 | モデル | 料金（100万トークンあたり） |
|---|---|---|
| 執筆 | Claude Sonnet 5.5 | 入力2ドル／出力10ドル |
| リサーチ・企画・返信・論理チェック | Claude Haiku 5.5 | 入力0.10ドル／出力0.50ドル |

月の見込みは400〜1,000円。`config/settings.yaml` の `models` を書き換えれば、Geminiにも戻せます（その場合は `prices` に料金を追加）。

## 立ち上げ期間（最初の14日間）
最初に投稿を作った日から14日間は、自動で安全側の設定になります。期間が終わると、何もしなくても通常の設定に戻ります。

| 項目 | 立ち上げ期間 | 通常 |
|---|---|---|
| Threadsの投稿 | 1日4本（8・12・19・22時） | 1日6本 |
| 自動返信 | 1日10件まで | 1日30件まで |
| PR投稿 | 出さない | `auto_ok: true` の案件のみ |

日数や値は `config/settings.yaml` の `warmup` で変えられます。

## 安全装置（全自動でも止まる仕組み）
- **予算上限**：AIの費用を呼び出しごとに記録し、月2,500円に達したらその月のAI処理を止めます（`data/cost/`）。
- **公開できない投稿は捨てる**：チェックで問題が残った投稿は、人の確認待ちにせず破棄します。
- **PR投稿**：`affiliates.yaml` で `auto_ok: true` にした案件だけ、自動で【PR】付きで公開します。
- **連続エラーで停止**：公開が3回続けて失敗したら、`KILL_SWITCH` を自動でONにします。
- **自動化しないこと**：いいね・フォロー・DMの自動化（規約違反・停止リスク）、noteの自動公開（個人向けAPIなし）。

## 人がやること
- 最初のセットアップだけ。あとは見なくても回ります。
- noteは `note_drafts/` の下書きを、気が向いたときに貼って公開します（ここだけは手作業）。
- `KILL_SWITCH` がONになったら、原因（多くはトークン切れ）を直してOFFに戻します。

## セットアップ

1. **このリポジトリを公開リポジトリとしてGitHubに作成します**（Actions無料、Instagram画像の公開URLに使います）。`config/settings.yaml` の `public_base_url` を書き換えます。
2. **Claude APIキー**：Anthropic Consoleで発行します。使いすぎ防止のため、Console側でも月の利用上限（例：20ドル）を設定しておくと二重の安全装置になります。Geminiを使う場合は、Google AI StudioでGemini APIキーを発行します。
3. **Instagram**：アカウントをプロアカウント（クリエイター）に切り替えます → Meta for Developersでアプリを作成 → 「Instagram API with Instagram Login」を追加 → 自分を **Instagramテスター** に登録 → 権限 `instagram_business_basic`, `instagram_business_content_publish`, `instagram_business_manage_comments`, `instagram_business_manage_insights` で長期トークンを発行します。
4. **Threads**：同じアプリに Threads API を追加 → 自分をThreadsテスターに登録 → `threads_basic`, `threads_content_publish`, `threads_manage_insights`, `threads_read_replies`, `threads_manage_replies` で長期トークン（60日）を発行します。
5. **GitHub PAT**：fine-grained tokenで、このリポジトリの「Secrets: Read and write」権限を付けます（トークン自動更新用）。
6. **Secretsを登録**（Settings → Secrets and variables → Actions）：
   `ANTHROPIC_API_KEY`（Geminiを使う場合は `GEMINI_API_KEY`）, `PROFILE_YAML`（経歴ファイルの中身をそのまま貼る）, `IG_USER_ID`, `IG_TOKEN`, `THREADS_USER_ID`, `THREADS_TOKEN`, `GH_PAT`
7. Actionsタブから `generate` を手動実行 → `queue/` を確認 → `publish` を手動実行して、テストします。

## 注意
- 経歴（`config/profile.yaml`）は公開リポジトリに置きません。Secretsの `PROFILE_YAML` から実行時に書き出し、`.gitignore` でコミットされないようにしています。
- 公開リポジトリなので、`queue/` の下書きも外から見えます。気になる場合は非公開リポジトリ（月2,000分の無料枠）にし、画像の置き場所をCloudflare R2などの無料枠に変えてください。
- 写実的な人物画像は使いません（AIラベルや誤認のリスクがあるため）。
- noteは自動投稿しません（個人向けの公式APIがなく、規約上のリスクもあるため）。
