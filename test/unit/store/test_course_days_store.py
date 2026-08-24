"""CourseDaysStoreの単体テスト.

DBへは接続せず、DbClientをモックにして呼び出しと組み立てを検証する。
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest
from db_client import DbClient

from course_days.params import PRIMARY_KEYS, TABLE_NAME
from course_days.store import CourseDaysStore

_KEY_A = ("05", "2025", "0608", "A")
_KEY_B = ("05", "2025", "0615", "A")
_VALUES_A: dict[str, Any] = {
    "芝コース日目": 2,
    "芝コース初日": "20250601",
    "芝コース経過日数": 8,
    "芝コース週目": 2,
}
_VALUES_B: dict[str, Any] = {
    "芝コース日目": 3,
    "芝コース初日": "20250601",
    "芝コース経過日数": 15,
    "芝コース週目": 3,
}


def _make_row(key: tuple[str, str, str, str], values: dict[str, Any]) -> dict[str, Any]:
    """DBから読んだ1行を組み立てる.

    Args:
        key (tuple[str, str, str, str]): 主キー
        values (dict[str, Any]): 芝コース日数4カラムの値

    Returns:
        dict[str, Any]: テーブルのカラム名をキーとする1行
    """
    return {
        "keibajo_code": key[0],
        "kaisai_year": key[1],
        "kaisai_month_day": key[2],
        "course_kubun": key[3],
        "course_day": values["芝コース日目"],
        "first_date": values["芝コース初日"],
        "elapsed_days": values["芝コース経過日数"],
        "course_week": values["芝コース週目"],
    }


@pytest.fixture
def mock_db_client() -> MagicMock:
    """DbClientのモック.

    specを付けて、DbClientに存在しないメソッドの呼び出しを検出できるようにする。
    """
    mock = MagicMock(spec=DbClient)
    mock.select.return_value = pd.DataFrame()
    return mock


@pytest.fixture
def store(mock_db_client: MagicMock) -> CourseDaysStore:
    """モックDbClientを使うCourseDaysStore."""
    return CourseDaysStore(mock_db_client)


# 正常系
def test_setup_executes_ddl(store: CourseDaysStore, mock_db_client: MagicMock) -> None:
    """setupがDDLを実行する."""
    store.setup()

    mock_db_client.setup_table.assert_called_once()
    ddl = mock_db_client.setup_table.call_args.args[0]
    assert "CREATE TABLE IF NOT EXISTS course_days" in ddl


def test_select_returns_saved_values(store: CourseDaysStore, mock_db_client: MagicMock) -> None:
    """保存されている値を主キーごとに読み出せる."""
    mock_db_client.select.return_value = pd.DataFrame(
        [_make_row(_KEY_A, _VALUES_A), _make_row(_KEY_B, _VALUES_B)]
    )

    result = store.select([_KEY_A, _KEY_B])

    assert result == {_KEY_A: _VALUES_A, _KEY_B: _VALUES_B}


def test_select_issues_one_query(store: CourseDaysStore, mock_db_client: MagicMock) -> None:
    """キーの数によらずクエリが1回で済む.

    1件ずつ引くと、1レースの入力生成で45回のクエリになる。
    """
    store.select([_KEY_A, _KEY_B])

    mock_db_client.select.assert_called_once()


def test_select_filters_by_each_primary_key_column(
    store: CourseDaysStore, mock_db_client: MagicMock
) -> None:
    """主キーのカラムごとにIN条件で絞り込む."""
    store.select([_KEY_A, _KEY_B])

    where = mock_db_client.select.call_args.kwargs["where"]
    assert set(where) == set(PRIMARY_KEYS)
    assert where["kaisai_month_day"] == ["0608", "0615"]


def test_select_excludes_keys_not_requested(
    store: CourseDaysStore, mock_db_client: MagicMock
) -> None:
    """要求していないキーを戻り値へ含めない.

    主キーは4カラムの組であり、カラムごとのIN条件では組の直積が返る。要求した2つの
    キーの値を組み替えたキー（どのカラムもIN条件には一致する）が混ざっても、
    取り出す側で除外できることを検証する。
    """
    requested_a = ("05", "2025", "0608", "A")
    requested_b = ("06", "2025", "0615", "B")
    # 4カラムとも要求キーのどれかに含まれるが、組としては要求していない
    unwanted = ("05", "2025", "0615", "B")
    mock_db_client.select.return_value = pd.DataFrame(
        [
            _make_row(requested_a, _VALUES_A),
            _make_row(requested_b, _VALUES_B),
            _make_row(unwanted, _VALUES_B),
        ]
    )

    result = store.select([requested_a, requested_b])

    assert set(result) == {requested_a, requested_b}


def test_select_converts_values_to_expected_types(
    store: CourseDaysStore, mock_db_client: MagicMock
) -> None:
    """芝コース初日が文字列、それ以外が整数になる.

    移行元の戻り値と型を合わせる。
    """
    mock_db_client.select.return_value = pd.DataFrame([_make_row(_KEY_A, _VALUES_A)])

    values = store.select([_KEY_A])[_KEY_A]

    assert isinstance(values["芝コース初日"], str)
    for column in ("芝コース日目", "芝コース経過日数", "芝コース週目"):
        assert isinstance(values[column], int)


def test_upsert_passes_primary_keys(store: CourseDaysStore, mock_db_client: MagicMock) -> None:
    """upsertが主キーを指定して保存する.

    同じ主キーで保存し直したときに重複行ができないようにする。
    """
    store.upsert({_KEY_A: _VALUES_A})

    mock_db_client.upsert.assert_called_once()
    assert mock_db_client.upsert.call_args.args[0] == TABLE_NAME
    assert mock_db_client.upsert.call_args.kwargs["primary_keys"] == PRIMARY_KEYS


def test_upsert_builds_row_with_db_column_names(
    store: CourseDaysStore, mock_db_client: MagicMock
) -> None:
    """保存する行がテーブルのカラム名で組み立てられる."""
    store.upsert({_KEY_A: _VALUES_A})

    df = mock_db_client.upsert.call_args.args[1]
    row = df.iloc[0].to_dict()
    row.pop("updated_at")
    assert row == _make_row(_KEY_A, _VALUES_A)


def test_upsert_sets_updated_at(store: CourseDaysStore, mock_db_client: MagicMock) -> None:
    """保存する行にupdated_atが入る.

    DEFAULT NOW()はINSERTのときにしか効かず、upsertが更新するのは渡したDataFrameに
    含まれるカラムだけである。入れないと更新しても登録時のままになる。
    """
    before = datetime.now(UTC)

    store.upsert({_KEY_A: _VALUES_A})

    df = mock_db_client.upsert.call_args.args[1]
    updated_at = df.iloc[0]["updated_at"]
    assert isinstance(updated_at, datetime)
    assert updated_at.tzinfo is not None
    assert before <= updated_at <= datetime.now(UTC)


def test_upsert_saves_all_keys_in_one_call(
    store: CourseDaysStore, mock_db_client: MagicMock
) -> None:
    """複数キーを1回の呼び出しで保存する."""
    store.upsert({_KEY_A: _VALUES_A, _KEY_B: _VALUES_B})

    mock_db_client.upsert.assert_called_once()
    assert len(mock_db_client.upsert.call_args.args[1]) == 2


# 準正常系
def test_select_with_empty_keys_issues_no_query(
    store: CourseDaysStore, mock_db_client: MagicMock
) -> None:
    """空のリストを渡すとクエリを発行せず空の辞書を返す."""
    result = store.select([])

    assert result == {}
    mock_db_client.select.assert_not_called()


def test_upsert_with_empty_values_issues_no_query(
    store: CourseDaysStore, mock_db_client: MagicMock
) -> None:
    """空の辞書を渡すとクエリを発行しない."""
    store.upsert({})

    mock_db_client.upsert.assert_not_called()


def test_select_returns_only_saved_keys(store: CourseDaysStore, mock_db_client: MagicMock) -> None:
    """未保存のキーは戻り値に含まれない."""
    mock_db_client.select.return_value = pd.DataFrame([_make_row(_KEY_A, _VALUES_A)])

    result = store.select([_KEY_A, _KEY_B])

    assert set(result) == {_KEY_A}


def test_select_deduplicates_keys(store: CourseDaysStore, mock_db_client: MagicMock) -> None:
    """重複したキーを渡しても条件が重複しない."""
    store.select([_KEY_A, _KEY_A])

    where = mock_db_client.select.call_args.kwargs["where"]
    assert where["kaisai_month_day"] == ["0608"]
