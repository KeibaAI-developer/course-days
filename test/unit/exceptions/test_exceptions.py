"""例外のテスト."""

from course_days.exceptions import CourseDaysError, LookbackLimitExceededError


# 正常系
def test_lookback_limit_exceeded_error_inherits_course_days_error() -> None:
    """LookbackLimitExceededErrorがCourseDaysErrorを継承する.

    呼び出し側が本ライブラリ由来の例外をまとめて捕まえられるようにするため。
    """
    assert issubclass(LookbackLimitExceededError, CourseDaysError)


def test_course_days_error_inherits_exception() -> None:
    """CourseDaysErrorがExceptionを継承する."""
    assert issubclass(CourseDaysError, Exception)
