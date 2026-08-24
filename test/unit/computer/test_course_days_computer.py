"""CourseDaysComputerの単体テスト.

DBへは接続せず、DbClientとDataInterfaceをモックにして検証する。
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from db_client import DbClient
from keiba_data_interface import DataInterface

from course_days.computer import CourseDaysComputer
from course_days.params import CourseDaysKey

_START = "2025-06-01"
_END = "2025-06-30"
_VALUES: dict[str, Any] = {
    "芝コース日目": 1,
    "芝コース初日": "20250608",
    "芝コース経過日数": 1,
    "芝コース週目": 1,
}


def _make_schedule(days: list[tuple[str, str, str]]) -> pd.DataFrame:
    """開催スケジュールを作る.

    Args:
        days (list[tuple[str, str, str]]): (競馬場コード, 開催年, 開催月日) のリスト

    Returns:
        pd.DataFrame: 開催スケジュール
    """
    return pd.DataFrame(
        [
            {
                "競馬場コード": keibajo_code,
                "開催年": year,
                "開催月日": monthday,
                "開催回": 3,
                "開催日目": 1,
            }
            for keibajo_code, year, monthday in days
        ]
    )


@pytest.fixture
def mock_data_interface() -> MagicMock:
    """DataInterfaceのモック（2開催日を返す）."""
    mock = MagicMock(spec=DataInterface)
    mock.get_schedule.return_value = _make_schedule(
        [("05", "2025", "0608"), ("06", "2025", "0615")]
    )
    return mock


@pytest.fixture
def mock_store() -> MagicMock:
    """CourseDaysStoreのモック（既定では未保存）."""
    store = MagicMock()
    store.select.return_value = {}
    return store


@pytest.fixture
def computer(mock_data_interface: MagicMock, mock_store: MagicMock) -> CourseDaysComputer:
    """モックを使うCourseDaysComputer."""
    with patch("course_days.computer.CourseDaysStore", return_value=mock_store):
        return CourseDaysComputer(mock_data_interface, MagicMock(spec=DbClient))


# 正常系
def test_compute_saves_all_target_days(
    computer: CourseDaysComputer, mock_store: MagicMock
) -> None:
    """指定期間の芝の開催日がすべて保存される."""
    with (
        patch("course_days.computer.get_course_kubun_of_day", return_value="A"),
        patch("course_days.computer.calc_course_days_for_key", return_value=_VALUES),
    ):
        saved = computer.compute(_START, _END)

    assert saved == 2
    mock_store.upsert.assert_called_once()
    assert set(mock_store.upsert.call_args.args[0]) == {
        ("05", "2025", "0608", "A"),
        ("06", "2025", "0615", "A"),
    }


def test_compute_creates_table(computer: CourseDaysComputer, mock_store: MagicMock) -> None:
    """計算の前にテーブルを作成する.

    取得API側ではDDLを実行しないため、テーブルの作成はここが担う。
    """
    with (
        patch("course_days.computer.get_course_kubun_of_day", return_value="A"),
        patch("course_days.computer.calc_course_days_for_key", return_value=_VALUES),
    ):
        computer.compute(_START, _END)

    mock_store.setup.assert_called_once()


def test_compute_skips_saved_days(computer: CourseDaysComputer, mock_store: MagicMock) -> None:
    """保存済みの開催日を計算し直さない.

    長い期間をまとめて流すことを想定しており、途中で止まっても続きから再開できる
    ようにする。
    """
    mock_store.select.return_value = {("05", "2025", "0608", "A"): _VALUES}

    with (
        patch("course_days.computer.get_course_kubun_of_day", return_value="A"),
        patch(
            "course_days.computer.calc_course_days_for_key", return_value=_VALUES
        ) as mock_calc,
    ):
        saved = computer.compute(_START, _END)

    assert saved == 1
    assert mock_calc.call_count == 1
    assert set(mock_store.upsert.call_args.args[0]) == {("06", "2025", "0615", "A")}


def test_count_remaining_returns_unsaved_count(
    computer: CourseDaysComputer, mock_store: MagicMock
) -> None:
    """count_remainingが未保存の件数を返す."""
    mock_store.select.return_value = {("05", "2025", "0608", "A"): _VALUES}

    with patch("course_days.computer.get_course_kubun_of_day", return_value="A"):
        remaining = computer.count_remaining(_START, _END)

    assert remaining == 1


def test_count_remaining_does_not_save(
    computer: CourseDaysComputer, mock_store: MagicMock
) -> None:
    """count_remainingが保存も計算もしない."""
    with (
        patch("course_days.computer.get_course_kubun_of_day", return_value="A"),
        patch("course_days.computer.calc_course_days_for_key") as mock_calc,
    ):
        computer.count_remaining(_START, _END)

    mock_store.upsert.assert_not_called()
    mock_calc.assert_not_called()


def test_count_remaining_creates_table(
    computer: CourseDaysComputer, mock_store: MagicMock
) -> None:
    """count_remainingもテーブルを作成する.

    保存済みかどうかを見るためテーブルを読むため、テーブルが無い環境では
    読み出しの時点で失敗する。
    """
    with patch("course_days.computer.get_course_kubun_of_day", return_value="A"):
        computer.count_remaining(_START, _END)

    mock_store.setup.assert_called_once()


def test_collect_targets_builds_keys_from_schedule(computer: CourseDaysComputer) -> None:
    """開催スケジュールからキーが組み立てられる."""
    with patch("course_days.computer.get_course_kubun_of_day", return_value="B"):
        targets = computer.collect_targets(_START, _END)

    assert targets == [("05", "2025", "0608", "B"), ("06", "2025", "0615", "B")]


# 準正常系
def test_days_without_turf_are_excluded(computer: CourseDaysComputer) -> None:
    """芝の開催が無い日を対象外にする.

    コース区分が判定できない日はNoneが返る。
    """
    with patch("course_days.computer.get_course_kubun_of_day", side_effect=["A", None]):
        targets = computer.collect_targets(_START, _END)

    assert targets == [("05", "2025", "0608", "A")]


def test_compute_with_no_target_returns_zero(
    computer: CourseDaysComputer, mock_store: MagicMock
) -> None:
    """対象が0件のとき何もせず0を返す."""
    with patch("course_days.computer.get_course_kubun_of_day", return_value=None):
        saved = computer.compute(_START, _END)

    assert saved == 0
    mock_store.upsert.assert_not_called()


def test_compute_with_empty_schedule_returns_zero(
    computer: CourseDaysComputer, mock_data_interface: MagicMock, mock_store: MagicMock
) -> None:
    """開催がない期間では何もせず0を返す."""
    mock_data_interface.get_schedule.return_value = pd.DataFrame()

    saved = computer.compute(_START, _END)

    assert saved == 0
    mock_store.upsert.assert_not_called()


def test_compute_saves_in_chunks(
    computer: CourseDaysComputer, mock_data_interface: MagicMock, mock_store: MagicMock
) -> None:
    """件数が多いときは区切って保存する.

    まとめて保存すると途中で止まったときに何も残らない。
    """
    days = [("05", "2025", f"06{day:02d}") for day in range(1, 31)]
    mock_data_interface.get_schedule.return_value = _make_schedule(days)

    with (
        patch("course_days.computer.get_course_kubun_of_day", return_value="A"),
        patch("course_days.computer.calc_course_days_for_key", return_value=_VALUES),
        patch("course_days.computer._UPSERT_CHUNK_SIZE", 10),
    ):
        saved = computer.compute(_START, _END)

    assert saved == 30
    assert mock_store.upsert.call_count == 3


def test_targets_are_ordered_by_venue_then_schedule(
    computer: CourseDaysComputer, mock_data_interface: MagicMock
) -> None:
    """キーが競馬場コードの昇順に並び、同一競馬場内では開催スケジュールの並びを保つ.

    開催日は開催スケジュールが返した順のまま扱う（並べ替えない）。競馬場コードだけを
    見るテストでは、開催日の扱いが壊れても気づけない。
    """
    mock_data_interface.get_schedule.return_value = _make_schedule(
        [
            ("06", "2025", "0622"),
            ("05", "2025", "0615"),
            ("05", "2025", "0608"),
        ]
    )

    with patch("course_days.computer.get_course_kubun_of_day", return_value="A"):
        targets: list[CourseDaysKey] = computer.collect_targets(_START, _END)

    assert targets == [
        ("05", "2025", "0615", "A"),
        ("05", "2025", "0608", "A"),
        ("06", "2025", "0622", "A"),
    ]
