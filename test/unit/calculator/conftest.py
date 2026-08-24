"""calc_course_days単体テスト用の共通定義.

開催日データから開催スケジュールとレース基本情報の応答を生成する
MockDataInterfaceを提供する。
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd
from keiba_data_interface.schema.columns import RACE_BASIC_INFO_COLUMNS

# 競馬場コード（東京）
KEIBAJO_CODE = "05"


@dataclass
class RaceDay:
    """テスト用の開催日データ

    Attributes:
        race_date (date): 開催日
        kai (int): 開催回
        nichime (int): 開催日目
        races (list[tuple[str, str | None] | None]): レース番号順の（芝ダ, コース区分）のリスト。
            要素がNoneの場合はそのレース番号が開催日に存在しない（欠番）ことを表す
        keibajo_code (str): 競馬場コード
    """

    race_date: date
    kai: int
    nichime: int
    races: list[tuple[str, str | None] | None]
    keibajo_code: str = KEIBAJO_CODE


class MockDataInterface:
    """開催日データから応答を生成するテスト用のデータ取得層.

    `calc_course_days` が使うメソッドだけを実装する。

    Attributes:
        race_days (dict[date, RaceDay]): 開催日ごとのレース構成
    """

    supports_bulk = True

    def __init__(self, race_days: list[RaceDay], supports_bulk: bool = True) -> None:
        self.race_days = {day.race_date: day for day in race_days}
        self.supports_bulk = supports_bulk
        self.get_race_basic_info_calls: list[str] = []
        self.get_race_basic_info_bulk_calls: list[list[str]] = []

    def get_schedule(self, start_date: str, end_date: str) -> pd.DataFrame:
        """期間内の開催日から開催スケジュールを生成する

        Args:
            start_date (str): 開始日（YYYY-MM-DD形式）
            end_date (str): 終了日（YYYY-MM-DD形式）

        Returns:
            pd.DataFrame: 開催スケジュールのDataFrame
        """
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        rows: list[list[object]] = []
        for day in self.race_days.values():
            if start <= day.race_date <= end:
                year = f"{day.race_date.year:04d}"
                monthday = f"{day.race_date.month:02d}{day.race_date.day:02d}"
                rows.append([year, monthday, day.keibajo_code, day.kai, day.nichime])
        columns = ["開催年", "開催月日", "競馬場コード", "開催回", "開催日目"]
        return pd.DataFrame(rows, columns=columns)

    def get_race_basic_info(self, race_code: str) -> pd.DataFrame:
        """レースコードに対応するレース基本情報を生成する

        Args:
            race_code (str): 16桁レースコード

        Returns:
            pd.DataFrame: 芝ダ・コース区分を含むレース基本情報のDataFrame（1行）

        Raises:
            ValueError: 開催日データに存在しないレースコードの場合
        """
        self.get_race_basic_info_calls.append(race_code)
        row = self._build_race_row(race_code)
        if row is None:
            raise ValueError(f"get_race_shosai()が空のDataFrameを返しました: race_code={race_code}")
        return pd.DataFrame([row])[["芝ダ", "コース区分"]]

    def get_race_basic_info_bulk(self, race_codes: list[str]) -> pd.DataFrame:
        """複数レースのレース基本情報をまとめて生成する

        存在しないレースコードの行は含めず、レースコード昇順で返す。

        Args:
            race_codes (list[str]): 16桁レースコードのリスト

        Returns:
            pd.DataFrame: 芝ダ・コース区分を含むレース基本情報のDataFrame
        """
        self.get_race_basic_info_bulk_calls.append(list(race_codes))
        rows = []
        for race_code in sorted(dict.fromkeys(race_codes)):
            row = self._build_race_row(race_code)
            if row is not None:
                rows.append(row)
        if not rows:
            return pd.DataFrame(columns=["レースコード", "芝ダ", "コース区分"])
        return pd.DataFrame(rows)[["レースコード", "芝ダ", "コース区分"]]

    def _build_race_row(self, race_code: str) -> dict[str, object] | None:
        """レースコードに対応する行を組み立てる

        Args:
            race_code (str): 16桁レースコード

        Returns:
            dict[str, object] | None: レース基本情報の1行。存在しない場合はNone
        """
        race_date = date(int(race_code[:4]), int(race_code[4:6]), int(race_code[6:8]))
        race_num = int(race_code[14:16])
        day = self.race_days.get(race_date)
        if day is None or race_num > len(day.races) or day.races[race_num - 1] is None:
            return None
        race = day.races[race_num - 1]
        assert race is not None
        shiba_da, course_kubun = race
        kubun_value = course_kubun if course_kubun is not None else pd.NA
        return {"レースコード": race_code, "芝ダ": shiba_da, "コース区分": kubun_value}


def build_race_basic_info(
    race_date: date,
    shiba_da: str,
    course_kubun: str | None,
    keibajo_code: str = KEIBAJO_CODE,
) -> pd.DataFrame:
    """対象レースのレース基本情報DataFrame（74カラム）を生成する

    Args:
        race_date (date): 開催日
        shiba_da (str): 芝ダ（"芝", "ダ"）
        course_kubun (str | None): コース区分（A〜E）。NoneはNaN扱い
        keibajo_code (str): 競馬場コード

    Returns:
        pd.DataFrame: レース基本情報のDataFrame（1行）
    """
    values: list[object] = [pd.NA] * len(RACE_BASIC_INFO_COLUMNS)
    df = pd.DataFrame([values], columns=RACE_BASIC_INFO_COLUMNS)
    monthday = f"{race_date.month:02d}{race_date.day:02d}"
    df["レースコード"] = f"{race_date.year:04d}{monthday}{keibajo_code}020111"
    df["開催年"] = f"{race_date.year:04d}"
    df["開催月日"] = monthday
    df["競馬場コード"] = keibajo_code
    df["芝ダ"] = shiba_da
    df["コース区分"] = course_kubun if course_kubun is not None else pd.NA
    return df


def turf_day_races(course_kubun: str) -> list[tuple[str, str | None] | None]:
    """ダート1レース後に芝レースが続く開催日のレース構成を生成する

    Args:
        course_kubun (str): 芝レースのコース区分

    Returns:
        list[tuple[str, str | None] | None]: レース番号順の（芝ダ, コース区分）のリスト
    """
    return [("ダ", None), ("芝", course_kubun)]


def turf_day_races_with_missing_low_numbers(
    course_kubun: str,
) -> list[tuple[str, str | None] | None]:
    """レース番号1・2が欠番で、3レース目に芝レースが続く開催日のレース構成を生成する

    2020-03-31 中山（レース番号03〜12のみ開催）を模したケース。

    Args:
        course_kubun (str): 芝レースのコース区分

    Returns:
        list[tuple[str, str | None] | None]: レース番号順の（芝ダ, コース区分）のリスト。
            レース番号1・2はNone（欠番）
    """
    return [None, None, ("芝", course_kubun)] + [("ダ", None)] * 9


def dirt_only_day_races() -> list[tuple[str, str | None] | None]:
    """芝レースが存在しない開催日のレース構成（12レース全てダート）を生成する

    Returns:
        list[tuple[str, str | None] | None]: レース番号順の（芝ダ, コース区分）のリスト
    """
    return [("ダ", None)] * 12
