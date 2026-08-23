"""course-days: 芝コース日数の計算とDB保存.

芝コース日目・芝コース初日・芝コース経過日数・芝コース週目を計算し、KeibaAIのDBへ
保存する。予測時・学習データ生成時は保存済みの値を読むだけで済ませる。
"""

from course_days.exceptions import CourseDaysError, LookbackLimitExceededError
from course_days.params import COURSE_DAYS_COLUMNS, COURSE_DAYS_TYPES, TABLE_NAME

__all__ = [
    "COURSE_DAYS_COLUMNS",
    "COURSE_DAYS_TYPES",
    "TABLE_NAME",
    "CourseDaysError",
    "LookbackLimitExceededError",
]
