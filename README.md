# course-days

## 概要

`course-days`は、芝コース何日目かを計算しKeibaAIのDBへ保存するライブラリです。

芝コース日目・芝コース初日・芝コース経過日数・芝コース週目の4つを扱います。これらは「競馬場・開催日・コース区分」で決まる値であり、レース単位の情報ではありません。

予測時・学習データ生成時は保存済みの値を読むだけで済ませます。計算は同一競馬場・同一コース区分の過去開催日を遡って行うため、呼び出しのたびに計算すると入力生成1レースあたり45回・約1.4秒かかっていました。

## 動作要件

- Python 3.12以上
- PostgreSQL（KeibaAIのDB）

## 依存パッケージ

- [keiba-data-interface](https://github.com/KeibaAI-developer/keiba-data-interface) — レース基本情報・開催スケジュールの取得
- [db-client](https://github.com/KeibaAI-developer/db-client) — KeibaAIのDBへの接続

## インストール

```bash
pip install -e /path/to/course-days
```

## セットアップ

### 環境変数

依存ライブラリの `.env` に接続情報を設定します。

- KeibaAIのDB（db-client）— 芝コース日数の保存先
- 競馬データの取得元DB（mykeibadb）— 計算に使うレース基本情報・開催スケジュール

保存先を**mykeibadbのDBにはしません**。mykeibadbのDBはmykeibadbという提供ソフトが生成するものであり、こちらから手を入れないためです。

## テーブル

主キーは `競馬場コード, 開催年, 開催月日, コース区分`。芝コース日数はこの4つで決まる値であり、レースごとに複製しません。

| カラム | 型 | 内容 |
|---|---|---|
| `keibajo_code` | VARCHAR | 競馬場コード（2桁） |
| `kaisai_year` | VARCHAR | 開催年（4桁） |
| `kaisai_month_day` | VARCHAR | 開催月日（4桁） |
| `course_kubun` | VARCHAR | コース区分（A〜E） |
| `course_day` | SMALLINT | 芝コース日目 |
| `first_date` | VARCHAR | 芝コース初日（YYYYMMDD） |
| `elapsed_days` | SMALLINT | 芝コース経過日数 |
| `course_week` | SMALLINT | 芝コース週目 |

## ドキュメント

- [SPEC](https://github.com/KeibaAI-developer/course-days/issues/1) — 仕様
- [PLAN](https://github.com/KeibaAI-developer/course-days/issues/2) — 実装計画

## テスト

```bash
pytest test/unit -v
```
