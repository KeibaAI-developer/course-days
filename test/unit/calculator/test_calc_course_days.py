"""calc_course_daysの単体テスト"""

from datetime import date, timedelta

import pandas as pd
import pytest

from course_days.calculator import calc_course_days
from course_days.exceptions import LookbackLimitExceededError
from course_days.params import COURSE_DAYS_COLUMNS

from .conftest import (
    MockDataInterface,
    RaceDay,
    build_race_basic_info,
    dirt_only_day_races,
    turf_day_races,
    turf_day_races_with_missing_low_numbers,
)


# 正常系
def test_calc_course_days_first_day() -> None:
    """過去に同一コースの開催がない場合は初日として計算される"""
    data_interface = MockDataInterface([])
    race_basic_info = build_race_basic_info(date(2025, 6, 8), "芝", "A")

    result = calc_course_days(race_basic_info, data_interface)

    assert result["芝コース日目"].iloc[0] == 1
    assert result["芝コース初日"].iloc[0] == "20250608"
    assert result["芝コース経過日数"].iloc[0] == 1
    assert result["芝コース週目"].iloc[0] == 1


def test_calc_course_days_counts_days_and_weeks() -> None:
    """連続する同一コースの開催日から日目・週目が計算される"""
    data_interface = MockDataInterface(
        [
            RaceDay(date(2025, 5, 31), 2, 1, turf_day_races("A")),
            RaceDay(date(2025, 6, 1), 2, 2, turf_day_races("A")),
            RaceDay(date(2025, 6, 7), 2, 3, turf_day_races("A")),
        ]
    )
    race_basic_info = build_race_basic_info(date(2025, 6, 8), "芝", "A")

    result = calc_course_days(race_basic_info, data_interface)

    assert result["芝コース日目"].iloc[0] == 4
    assert result["芝コース初日"].iloc[0] == "20250531"
    assert result["芝コース経過日数"].iloc[0] == 9
    assert result["芝コース週目"].iloc[0] == 2


def test_calc_course_days_resets_after_long_gap() -> None:
    """同一コースの開催間隔が14日以上空いた場合はリセットされる"""
    data_interface = MockDataInterface(
        [
            RaceDay(date(2025, 5, 10), 1, 7, turf_day_races("A")),
            RaceDay(date(2025, 5, 11), 1, 8, turf_day_races("A")),
            RaceDay(date(2025, 5, 31), 2, 1, turf_day_races("A")),
            RaceDay(date(2025, 6, 1), 2, 2, turf_day_races("A")),
        ]
    )
    race_basic_info = build_race_basic_info(date(2025, 6, 7), "芝", "A")

    result = calc_course_days(race_basic_info, data_interface)

    assert result["芝コース日目"].iloc[0] == 3
    assert result["芝コース初日"].iloc[0] == "20250531"
    assert result["芝コース経過日数"].iloc[0] == 8
    assert result["芝コース週目"].iloc[0] == 2


def test_calc_course_days_skips_different_course_days() -> None:
    """異なるコース区分の開催日は日数に数えず、セグメントも分断しない"""
    data_interface = MockDataInterface(
        [
            RaceDay(date(2025, 5, 25), 2, 1, turf_day_races("A")),
            RaceDay(date(2025, 5, 31), 2, 2, turf_day_races("B")),
            RaceDay(date(2025, 6, 1), 2, 3, turf_day_races("A")),
        ]
    )
    race_basic_info = build_race_basic_info(date(2025, 6, 8), "芝", "A")

    result = calc_course_days(race_basic_info, data_interface)

    assert result["芝コース日目"].iloc[0] == 3
    assert result["芝コース初日"].iloc[0] == "20250525"
    assert result["芝コース経過日数"].iloc[0] == 15
    assert result["芝コース週目"].iloc[0] == 3


def test_calc_course_days_skips_day_without_turf_race() -> None:
    """芝レースが存在しない開催日は日数に数えない"""
    data_interface = MockDataInterface(
        [
            RaceDay(date(2025, 6, 1), 2, 1, turf_day_races("A")),
            RaceDay(date(2025, 6, 7), 2, 2, dirt_only_day_races()),
        ]
    )
    race_basic_info = build_race_basic_info(date(2025, 6, 8), "芝", "A")

    result = calc_course_days(race_basic_info, data_interface)

    assert result["芝コース日目"].iloc[0] == 2
    assert result["芝コース初日"].iloc[0] == "20250601"
    assert result["芝コース経過日数"].iloc[0] == 8
    assert result["芝コース週目"].iloc[0] == 2


def test_calc_course_days_skips_missing_low_race_numbers() -> None:
    """レース番号1・2が欠番の開催日でも欠番を読み飛ばして芝コース区分を判定する"""
    data_interface = MockDataInterface(
        [
            RaceDay(date(2025, 6, 1), 2, 1, turf_day_races_with_missing_low_numbers("A")),
        ]
    )
    race_basic_info = build_race_basic_info(date(2025, 6, 8), "芝", "A")

    result = calc_course_days(race_basic_info, data_interface)

    assert result["芝コース日目"].iloc[0] == 2
    assert result["芝コース初日"].iloc[0] == "20250601"
    assert result["芝コース経過日数"].iloc[0] == 8
    assert result["芝コース週目"].iloc[0] == 2


# 準正常系
@pytest.mark.parametrize(
    "shiba_da, course_kubun",
    [
        ("ダ", None),
        ("ダ", "A"),
        ("芝", None),
    ],
)
def test_calc_course_days_returns_nan_for_non_target_race(
    shiba_da: str, course_kubun: str | None
) -> None:
    """芝レースでない場合やコース区分が不明な場合は4カラムがNaNのまま返る"""
    data_interface = MockDataInterface([])
    race_basic_info = build_race_basic_info(date(2025, 6, 8), shiba_da, course_kubun)

    result = calc_course_days(race_basic_info, data_interface)

    for column in COURSE_DAYS_COLUMNS:
        assert pd.isna(result[column].iloc[0])


def test_calc_course_days_raises_when_lookback_exceeds_limit() -> None:
    """遡及が上限日数を超えた場合はLookbackLimitExceededErrorが発生する"""
    target_date = date(2025, 6, 8)
    race_days = []
    # 上限を超えて毎週同一コースの開催が続くデータを生成する
    for week in range(1, 60):
        race_days.append(
            RaceDay(target_date - timedelta(days=7 * week), 1, week, turf_day_races("A"))
        )
    data_interface = MockDataInterface(race_days)
    race_basic_info = build_race_basic_info(target_date, "芝", "A")

    with pytest.raises(LookbackLimitExceededError):
        calc_course_days(race_basic_info, data_interface)


# 正常系（一括取得によるコース区分の判定）


@pytest.mark.parametrize("race_day_count", [1, 3])
def test_bulk_provider_issues_single_call_per_race_day(race_day_count: int) -> None:
    """一括取得に対応したProviderでは開催日ごとに1回だけ問い合わせる.

    レース番号ごとに取得すると1開催日あたり最大12回の問い合わせが発生する。
    遡及する開催日の数だけ呼び出され、それを超えないことを検証する。
    """
    target_date = date(2025, 6, 8)
    race_days = [
        RaceDay(target_date - timedelta(days=7 * week), 1, week, turf_day_races("A"))
        for week in range(1, race_day_count + 1)
    ]
    data_interface = MockDataInterface(race_days)
    race_basic_info = build_race_basic_info(target_date, "芝", "A")

    calc_course_days(race_basic_info, data_interface)

    assert data_interface.get_race_basic_info_calls == []
    assert len(data_interface.get_race_basic_info_bulk_calls) == race_day_count
    for race_codes in data_interface.get_race_basic_info_bulk_calls:
        assert len(race_codes) == 12


def test_bulk_provider_passes_race_numbers_in_ascending_order() -> None:
    """一括取得へレース番号1〜12のレースコードが昇順で渡される."""
    target_date = date(2025, 6, 8)
    data_interface = MockDataInterface(
        [RaceDay(target_date - timedelta(days=7), 1, 1, turf_day_races("A"))]
    )
    race_basic_info = build_race_basic_info(target_date, "芝", "A")

    calc_course_days(race_basic_info, data_interface)

    race_codes = data_interface.get_race_basic_info_bulk_calls[0]
    assert [code[-2:] for code in race_codes] == [f"{n:02d}" for n in range(1, 13)]


def test_bulk_and_one_by_one_return_same_result() -> None:
    """一括取得の経路と1件ずつ取得の経路で結果が一致する."""
    target_date = date(2025, 6, 8)
    race_days = [
        RaceDay(target_date - timedelta(days=7 * week), 1, week, turf_day_races("A"))
        for week in range(1, 4)
    ]
    race_basic_info = build_race_basic_info(target_date, "芝", "A")

    bulk_result = calc_course_days(race_basic_info, MockDataInterface(race_days))
    one_by_one_result = calc_course_days(
        race_basic_info, MockDataInterface(race_days, supports_bulk=False)
    )

    pd.testing.assert_frame_equal(bulk_result, one_by_one_result)


def test_one_by_one_provider_does_not_use_bulk() -> None:
    """一括取得に未対応のProviderでは1件ずつ取得する経路を通る."""
    target_date = date(2025, 6, 8)
    data_interface = MockDataInterface(
        [RaceDay(target_date - timedelta(days=7), 1, 1, turf_day_races("A"))],
        supports_bulk=False,
    )
    race_basic_info = build_race_basic_info(target_date, "芝", "A")

    calc_course_days(race_basic_info, data_interface)

    assert data_interface.get_race_basic_info_bulk_calls == []
    assert data_interface.get_race_basic_info_calls != []


@pytest.mark.parametrize("supports_bulk", [True, False])
def test_missing_low_race_numbers_are_skipped(supports_bulk: bool) -> None:
    """レース番号1・2が欠番でも3レース目の芝レースのコース区分で判定される."""
    target_date = date(2025, 6, 8)
    data_interface = MockDataInterface(
        [
            RaceDay(
                target_date - timedelta(days=7),
                1,
                1,
                turf_day_races_with_missing_low_numbers("A"),
            )
        ],
        supports_bulk=supports_bulk,
    )
    race_basic_info = build_race_basic_info(target_date, "芝", "A")

    result = calc_course_days(race_basic_info, data_interface)

    assert result["芝コース日目"].iloc[0] == 2


@pytest.mark.parametrize("supports_bulk", [True, False])
def test_dirt_only_day_is_not_counted(supports_bulk: bool) -> None:
    """芝レースが存在しない開催日は同一コースの開催日として数えられない."""
    target_date = date(2025, 6, 8)
    data_interface = MockDataInterface(
        [RaceDay(target_date - timedelta(days=7), 1, 1, dirt_only_day_races())],
        supports_bulk=supports_bulk,
    )
    race_basic_info = build_race_basic_info(target_date, "芝", "A")

    result = calc_course_days(race_basic_info, data_interface)

    assert result["芝コース日目"].iloc[0] == 1
