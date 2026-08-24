"""course-daysの例外.

すべて `CourseDaysError` を基底に持つ。呼び出し側が本ライブラリ由来の例外を
まとめて捕まえられるようにするため。
"""


class CourseDaysError(Exception):
    """course-daysの基底例外."""


class LookbackLimitExceededError(CourseDaysError):
    """同一コースの開催日を遡る処理が上限を超えた場合の例外.

    上限まで遡っても同一コースの開催が途切れない場合、データの不整合か
    判定条件の誤りが疑われる。
    """
