"""get_course_daysの単体テスト.

DBへは接続せず、DbClientとDataInterfaceをモックにして検証する。
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from db_client import DbClient
from keiba_data_interface import DataInterface

from course_days.calculator import CourseDaysCache
from course_days.getters import get_course_days
from course_days.params import COURSE_DAYS_COLUMNS

_KEY = ("05", "2025", "0608", "A")
_SAVED: dict[str, Any] = {
    "芝コース日目": 2,
    "芝コース初日": "20250601",
    "芝コース経過日数": 8,
    "芝コース週目": 2,
}


def _make_race_basic_info(turf_dirt: str = "芝", course_kubun: str | None = "A") -> pd.DataFrame:
    """テスト用のレース基本情報を作る.

    Args:
        turf_dirt (str): 芝ダ
        course_kubun (str | None): コース区分。Noneは不明を表す

    Returns:
        pd.DataFrame: 芝コース日数4カラムがNaNのレース基本情報（1行）
    """
    row: dict[str, Any] = {
        "レースコード": "2025060805020111",
        "競馬場コード": _KEY[0],
        "開催年": _KEY[1],
        "開催月日": _KEY[2],
        "芝ダ": turf_dirt,
        "コース区分": course_kubun if course_kubun is not None else pd.NA,
    }
    for column in COURSE_DAYS_COLUMNS:
        row[column] = pd.NA
    return pd.DataFrame([row])


def _make_calculated(values: dict[str, Any]) -> pd.DataFrame:
    """計算結果に見立てたレース基本情報を作る.

    Args:
        values (dict[str, Any]): 芝コース日数4カラムの値

    Returns:
        pd.DataFrame: 4カラムが埋まったレース基本情報（1行）
    """
    df = _make_race_basic_info()
    for column, value in values.items():
        df[column] = [value]
    return df


@pytest.fixture
def mock_db_client() -> MagicMock:
    """DbClientのモック."""
    return MagicMock(spec=DbClient)


@pytest.fixture
def mock_data_interface() -> MagicMock:
    """DataInterfaceのモック."""
    return MagicMock(spec=DataInterface)


@pytest.fixture
def mock_store() -> MagicMock:
    """CourseDaysStoreのモック（既定では未保存）."""
    store = MagicMock()
    store.select.return_value = {}
    return store


# 正常系
def test_saved_values_are_returned_without_calculating(
    mock_db_client: MagicMock, mock_data_interface: MagicMock, mock_store: MagicMock
) -> None:
    """保存済みの開催日ではDBを引くだけで、計算が走らない."""
    mock_store.select.return_value = {_KEY: _SAVED}

    with (
        patch("course_days.getters.CourseDaysStore", return_value=mock_store),
        patch("course_days.getters.calculate") as mock_calculate,
    ):
        result = get_course_days(_make_race_basic_info(), mock_data_interface, mock_db_client)

    mock_calculate.assert_not_called()
    assert result["芝コース日目"].iloc[0] == 2
    assert result["芝コース初日"].iloc[0] == "20250601"
    assert result["芝コース経過日数"].iloc[0] == 8
    assert result["芝コース週目"].iloc[0] == 2


def test_unsaved_values_are_calculated_and_saved(
    mock_db_client: MagicMock, mock_data_interface: MagicMock, mock_store: MagicMock
) -> None:
    """未保存の開催日では計算し、保存してから返す.

    予測は当日のレースを対象にするため、バッチが回る前の開催日は必ず未保存になる。
    """
    with (
        patch("course_days.getters.CourseDaysStore", return_value=mock_store),
        patch("course_days.getters.calculate", return_value=_make_calculated(_SAVED)),
    ):
        result = get_course_days(_make_race_basic_info(), mock_data_interface, mock_db_client)

    mock_store.upsert.assert_called_once_with({_KEY: _SAVED})
    assert result["芝コース日目"].iloc[0] == 2


def test_table_is_never_created(
    mock_db_client: MagicMock, mock_data_interface: MagicMock, mock_store: MagicMock
) -> None:
    """取得ではDDLを実行しない.

    テーブルの作成はCourseDaysStore.setupかバッチの役割であり、取得のたびに
    DDLを走らせない。
    """
    with (
        patch("course_days.getters.CourseDaysStore", return_value=mock_store),
        patch("course_days.getters.calculate", return_value=_make_calculated(_SAVED)),
    ):
        get_course_days(_make_race_basic_info(), mock_data_interface, mock_db_client)

    mock_store.setup.assert_not_called()


def test_calculation_does_not_receive_cache(
    mock_db_client: MagicMock, mock_data_interface: MagicMock, mock_store: MagicMock
) -> None:
    """計算にはキャッシュを渡さない.

    calc_course_daysは計算した値をキャッシュへ入れるため、渡すと保存に失敗しても
    値だけが残る。
    """
    cache = CourseDaysCache()

    with (
        patch("course_days.getters.CourseDaysStore", return_value=mock_store),
        patch(
            "course_days.getters.calculate", return_value=_make_calculated(_SAVED)
        ) as mock_calculate,
    ):
        get_course_days(_make_race_basic_info(), mock_data_interface, mock_db_client, cache=cache)

    assert mock_calculate.call_args.args[3] is None


def test_cache_is_not_filled_when_saving_fails(
    mock_db_client: MagicMock, mock_data_interface: MagicMock, mock_store: MagicMock
) -> None:
    """保存に失敗したときキャッシュへ入れない.

    入れてしまうと、次回以降はDBを見ずに未保存の値を返し、保存の失敗を隠す。
    """
    mock_store.upsert.side_effect = RuntimeError("保存に失敗しました")
    cache = CourseDaysCache()

    with (
        patch("course_days.getters.CourseDaysStore", return_value=mock_store),
        patch("course_days.getters.calculate", return_value=_make_calculated(_SAVED)),
        pytest.raises(RuntimeError, match="保存に失敗しました"),
    ):
        get_course_days(_make_race_basic_info(), mock_data_interface, mock_db_client, cache=cache)

    assert cache.get_course_days(_KEY) is None

    # 2回目もDBを引く（キャッシュで素通りしない）
    mock_store.upsert.side_effect = None
    with (
        patch("course_days.getters.CourseDaysStore", return_value=mock_store),
        patch("course_days.getters.calculate", return_value=_make_calculated(_SAVED)),
    ):
        get_course_days(_make_race_basic_info(), mock_data_interface, mock_db_client, cache=cache)

    assert mock_store.select.call_count == 2


def test_cache_avoids_second_select(
    mock_db_client: MagicMock, mock_data_interface: MagicMock, mock_store: MagicMock
) -> None:
    """一度読んだ開催日は2回目以降DBを引かない."""
    mock_store.select.return_value = {_KEY: _SAVED}
    cache = CourseDaysCache()

    with (
        patch("course_days.getters.CourseDaysStore", return_value=mock_store),
        patch("course_days.getters.calculate"),
    ):
        get_course_days(_make_race_basic_info(), mock_data_interface, mock_db_client, cache=cache)
        get_course_days(_make_race_basic_info(), mock_data_interface, mock_db_client, cache=cache)

    assert mock_store.select.call_count == 1


def test_calculated_values_are_cached(
    mock_db_client: MagicMock, mock_data_interface: MagicMock, mock_store: MagicMock
) -> None:
    """計算した値もキャッシュへ入る（2回目は計算もDBの読み出しもしない）."""
    cache = CourseDaysCache()

    with (
        patch("course_days.getters.CourseDaysStore", return_value=mock_store),
        patch(
            "course_days.getters.calculate", return_value=_make_calculated(_SAVED)
        ) as mock_calculate,
    ):
        get_course_days(_make_race_basic_info(), mock_data_interface, mock_db_client, cache=cache)
        get_course_days(_make_race_basic_info(), mock_data_interface, mock_db_client, cache=cache)

    assert mock_calculate.call_count == 1
    assert mock_store.select.call_count == 1


def test_returned_dtypes_match_schema(
    mock_db_client: MagicMock, mock_data_interface: MagicMock, mock_store: MagicMock
) -> None:
    """戻り値の4カラムのdtypeが移行元と同じになる."""
    mock_store.select.return_value = {_KEY: _SAVED}

    with (
        patch("course_days.getters.CourseDaysStore", return_value=mock_store),
        patch("course_days.getters.calculate"),
    ):
        result = get_course_days(_make_race_basic_info(), mock_data_interface, mock_db_client)

    assert result["芝コース日目"].dtype == pd.Int64Dtype()
    assert result["芝コース経過日数"].dtype == pd.Int64Dtype()
    assert result["芝コース週目"].dtype == pd.Int64Dtype()
    assert result["芝コース初日"].dtype == object


def test_input_dataframe_is_not_modified(
    mock_db_client: MagicMock, mock_data_interface: MagicMock, mock_store: MagicMock
) -> None:
    """入力DataFrameが変更されない."""
    mock_store.select.return_value = {_KEY: _SAVED}
    race_basic_info = _make_race_basic_info()

    with (
        patch("course_days.getters.CourseDaysStore", return_value=mock_store),
        patch("course_days.getters.calculate"),
    ):
        get_course_days(race_basic_info, mock_data_interface, mock_db_client)

    assert pd.isna(race_basic_info["芝コース日目"].iloc[0])


# 準正常系
@pytest.mark.parametrize(
    ("turf_dirt", "course_kubun"),
    [("ダート", "A"), ("芝", None)],
    ids=["dirt", "unknown_course_kubun"],
)
def test_out_of_scope_race_returns_na_without_touching_db(
    mock_db_client: MagicMock,
    mock_data_interface: MagicMock,
    mock_store: MagicMock,
    turf_dirt: str,
    course_kubun: str | None,
) -> None:
    """ダートレース・コース区分不明では4カラムがNaNのまま返り、DBを引かない."""
    with (
        patch("course_days.getters.CourseDaysStore", return_value=mock_store),
        patch("course_days.getters.calculate") as mock_calculate,
    ):
        result = get_course_days(
            _make_race_basic_info(turf_dirt, course_kubun), mock_data_interface, mock_db_client
        )

    for column in COURSE_DAYS_COLUMNS:
        assert pd.isna(result[column].iloc[0])
    mock_store.select.assert_not_called()
    mock_calculate.assert_not_called()


# 異常系
def test_calculation_error_is_propagated(
    mock_db_client: MagicMock, mock_data_interface: MagicMock, mock_store: MagicMock
) -> None:
    """計算が失敗した場合に例外が伝播する（握りつぶさない）."""
    with (
        patch("course_days.getters.CourseDaysStore", return_value=mock_store),
        patch("course_days.getters.calculate", side_effect=RuntimeError("計算に失敗しました")),
        pytest.raises(RuntimeError, match="計算に失敗しました"),
    ):
        get_course_days(_make_race_basic_info(), mock_data_interface, mock_db_client)

    mock_store.upsert.assert_not_called()
