# params.py

芝コース日数の定数定義です。

## 定数

| 定数 | 型 | 値 | 説明 |
|---|---|---|---|
| `COURSE_DAYS_COLUMNS` | `list[str]` | `["芝コース日目", "芝コース初日", "芝コース経過日数", "芝コース週目"]` | 芝コース日数のカラム名 |
| `COURSE_DAYS_TYPES` | `dict[str, str]` | `{"芝コース日目": "Int64", "芝コース初日": "object", "芝コース経過日数": "Int64", "芝コース週目": "Int64"}` | カラム名 → pandas型。芝コース初日はYYYYMMDDの文字列 |
| `TABLE_NAME` | `str` | `"course_days"` | 保存先テーブル名 |
| `CourseDaysKey` | 型エイリアス | `tuple[str, str, str, str]` | 芝コース日数を識別するキー `(競馬場コード, 開催年, 開催月日, コース区分)` |
| `PRIMARY_KEYS` | `list[str]` | `["keibajo_code", "kaisai_year", "kaisai_month_day", "course_kubun"]` | テーブルの主キー。`CourseDaysKey` の要素と同じ順序 |
| `COLUMN_TO_DB` | `dict[str, str]` | `{"芝コース日目": "course_day", "芝コース初日": "first_date", "芝コース経過日数": "elapsed_days", "芝コース週目": "course_week"}` | カラム名 → テーブルのカラム名 |
| `TABLE_DDL` | `str` | （DDL文字列） | `course_days` テーブルのCREATE TABLE DDL |

```python
from course_days import COURSE_DAYS_COLUMNS, COURSE_DAYS_TYPES, TABLE_NAME, CourseDaysKey
```

---

## `course_days` テーブル

`TABLE_DDL` で作成されるテーブルです。主キーは `(keibajo_code, kaisai_year, kaisai_month_day, course_kubun)`。芝コース日数は「競馬場・開催日・コース区分」で決まる値でありレース単位の情報ではないため、レースごとに複製しません。

| カラム名 | 型 | 説明 |
|---|---|---|
| `keibajo_code` | `VARCHAR(2) NOT NULL` | 競馬場コード |
| `kaisai_year` | `VARCHAR(4) NOT NULL` | 開催年 |
| `kaisai_month_day` | `VARCHAR(4) NOT NULL` | 開催月日（MMDD） |
| `course_kubun` | `VARCHAR(1) NOT NULL` | コース区分（A〜E） |
| `course_day` | `SMALLINT NOT NULL` | 芝コース日目 |
| `first_date` | `VARCHAR(8) NOT NULL` | 芝コース初日（YYYYMMDD）。文字列で持つ。日付型にすると戻り値の型が変わるため |
| `elapsed_days` | `SMALLINT NOT NULL` | 芝コース経過日数 |
| `course_week` | `SMALLINT NOT NULL` | 芝コース週目 |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT NOW()` | 登録日時 |
| `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT NOW()` | 更新日時。`upsert` 時に明示的に更新される |

保存先はKeibaAIのDB（db-client）です。mykeibadbのDBはmykeibadbという提供ソフトが生成するものであり、こちらから手を入れません。
