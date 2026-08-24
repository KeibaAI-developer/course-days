"""定数のテスト."""

from course_days.params import COURSE_DAYS_COLUMNS, COURSE_DAYS_TYPES


# 正常系
def test_columns_and_types_have_same_keys() -> None:
    """カラム名リストと型定義のキーが一致する.

    片方だけにカラムがあると、型が付かないカラムや存在しないカラムの型定義が生まれる。
    """
    assert set(COURSE_DAYS_COLUMNS) == set(COURSE_DAYS_TYPES)


def test_columns_order_matches_types_order() -> None:
    """カラム名リストの並びが型定義の並びと一致する."""
    assert COURSE_DAYS_COLUMNS == list(COURSE_DAYS_TYPES)


def test_first_date_is_object_type() -> None:
    """芝コース初日がobject型である.

    値はYYYYMMDDの文字列であり、日付型にすると移行元と戻り値が変わる。
    """
    assert COURSE_DAYS_TYPES["芝コース初日"] == "object"
