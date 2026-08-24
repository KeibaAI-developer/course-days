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
