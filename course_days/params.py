"""芝コース日数の定数.

カラム名・型・テーブル名をまとめる。
"""

# 芝コース日数のカラム名リスト
COURSE_DAYS_COLUMNS: list[str] = [
    "芝コース日目",
    "芝コース初日",
    "芝コース経過日数",
    "芝コース週目",
]

# 芝コース日数のカラム名 → pandas型
# 移行元（keiba-data-interfaceのRACE_BASIC_INFO_TYPES）と同じにする。芝コース初日は
# YYYYMMDDの文字列であり、日付型にすると戻り値が変わる
COURSE_DAYS_TYPES: dict[str, str] = {
    "芝コース日目": "Int64",
    "芝コース初日": "object",
    "芝コース経過日数": "Int64",
    "芝コース週目": "Int64",
}

# 芝コース日数を保存するテーブル名
TABLE_NAME: str = "course_days"

# course_daysテーブルの主キー
PRIMARY_KEYS: list[str] = ["keibajo_code", "kaisai_year", "kaisai_month_day", "course_kubun"]

# 芝コース日数のカラム名 → テーブルのカラム名
COLUMN_TO_DB: dict[str, str] = {
    "芝コース日目": "course_day",
    "芝コース初日": "first_date",
    "芝コース経過日数": "elapsed_days",
    "芝コース週目": "course_week",
}

# course_daysテーブルのDDL
# 主キーは「競馬場コード・開催年・開催月日・コース区分」。芝コース日数はこの4つで決まる
# 値でありレース単位の情報ではないため、レースごとに複製しない（5年分で数千行に収まる）。
# first_dateはYYYYMMDDの文字列で持つ。日付型にすると移行元と戻り値が変わる
TABLE_DDL: str = """
CREATE TABLE IF NOT EXISTS course_days (
    keibajo_code     VARCHAR(2)  NOT NULL,
    kaisai_year      VARCHAR(4)  NOT NULL,
    kaisai_month_day VARCHAR(4)  NOT NULL,
    course_kubun     VARCHAR(1)  NOT NULL,
    course_day       SMALLINT    NOT NULL,
    first_date       VARCHAR(8)  NOT NULL,
    elapsed_days     SMALLINT    NOT NULL,
    course_week      SMALLINT    NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (keibajo_code, kaisai_year, kaisai_month_day, course_kubun)
);
"""
