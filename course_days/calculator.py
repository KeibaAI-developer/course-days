"""芝コース日数の計算.

レース基本情報の芝コース日目・芝コース初日・芝コース経過日数・芝コース週目を、
同一競馬場・同一コース区分の過去開催日を遡って計算する。

`keiba-data-interface` から移植した。アルゴリズムそのものは変えていない（リセット判定
14日・同一週判定2日・遡及上限365日・スケジュール取得窓14日・1開催日の最大レース番号12）。
変えたのは、受け取るものを `DataProvider` から公開APIの `DataInterface` にしたことと、
例外を本ライブラリのものにしたことである。
"""

import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd
from keiba_data_interface import DataInterface

from course_days.exceptions import LookbackLimitExceededError

# 芝コース日数情報のカラム名リスト
COURSE_DAYS_COLUMNS: list[str] = [
    "芝コース日目",
    "芝コース初日",
    "芝コース経過日数",
    "芝コース週目",
]

# 同一コースの開催間隔がこの日数以上空いた場合、コース使用がリセットされたとみなす
_RESET_GAP_DAYS = 14
# 開催間隔がこの日数以下なら同一週の開催とみなす
_SAME_WEEK_GAP_DAYS = 2
# 過去レースの遡及上限日数
_MAX_LOOKBACK_DAYS = 365
# get_scheduleで一度に取得する日数
_SCHEDULE_WINDOW_DAYS = 14
# 1開催日の最大レース番号
_MAX_RACE_NUM = 12


class CourseDaysCache:
    """コース日数の計算に関わる取得結果と計算結果を保持するキャッシュ.

    芝コース日数4カラムは「競馬場コード・開催日・コース区分」で決まり、レース単位の
    情報ではない。同じ開催日のレースを繰り返し処理すると、同じ遡及取得と計算が
    何度も走るため、次の3種類をキャッシュする。

    | 対象 | キー |
    |---|---|
    | コース日数4カラムの値 | 競馬場コード / 開催年 / 開催月日 / コース区分 |
    | 開催日のコース区分 | 競馬場コード / 開催年 / 開催月日 |
    | 開催スケジュール | 開始日 / 終了日 |

    上限は設けない。開催日の数は1年あたり200日程度で、5年分を連続処理しても
    1,000件に満たないため。

    Providerごとに別のインスタンスを持たせること。Providerが異なれば取得結果も
    異なりうるため。
    """

    def __init__(self) -> None:
        """キャッシュを初期化する."""
        self._course_days: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        self._course_kubun: dict[tuple[str, str, str], str | None] = {}
        self._schedule: dict[tuple[str, str], pd.DataFrame] = {}

    def get_course_days(self, key: tuple[str, str, str, str]) -> dict[str, Any] | None:
        """コース日数4カラムの値を返す.

        Args:
            key (tuple[str, str, str, str]): 競馬場コード / 開催年 / 開催月日 / コース区分

        Returns:
            dict[str, Any] | None: 4カラムの値。未計算ならNone
        """
        return self._course_days.get(key)

    def set_course_days(self, key: tuple[str, str, str, str], values: dict[str, Any]) -> None:
        """コース日数4カラムの値を保持する.

        Args:
            key (tuple[str, str, str, str]): 競馬場コード / 開催年 / 開催月日 / コース区分
            values (dict[str, Any]): 4カラムの値
        """
        self._course_days[key] = values

    def get_course_kubun(self, key: tuple[str, str, str]) -> tuple[bool, str | None]:
        """開催日のコース区分を返す.

        「芝レースが無い開催日」を `None` として保持するため、値の有無と値を分けて返す。

        Args:
            key (tuple[str, str, str]): 競馬場コード / 開催年 / 開催月日

        Returns:
            tuple[bool, str | None]: (保持しているか, コース区分)
        """
        if key not in self._course_kubun:
            return False, None
        return True, self._course_kubun[key]

    def set_course_kubun(self, key: tuple[str, str, str], course_kubun: str | None) -> None:
        """開催日のコース区分を保持する.

        Args:
            key (tuple[str, str, str]): 競馬場コード / 開催年 / 開催月日
            course_kubun (str | None): コース区分。芝レースが無い開催日はNone
        """
        self._course_kubun[key] = course_kubun

    def get_schedule(self, key: tuple[str, str]) -> pd.DataFrame | None:
        """開催スケジュールを返す.

        Args:
            key (tuple[str, str]): 開始日 / 終了日

        Returns:
            pd.DataFrame | None: 開催スケジュール。未取得ならNone
        """
        return self._schedule.get(key)

    def set_schedule(self, key: tuple[str, str], schedule_df: pd.DataFrame) -> None:
        """開催スケジュールを保持する.

        Args:
            key (tuple[str, str]): 開始日 / 終了日
            schedule_df (pd.DataFrame): 開催スケジュール
        """
        self._schedule[key] = schedule_df

    def clear(self) -> None:
        """キャッシュを空にする."""
        self._course_days.clear()
        self._course_kubun.clear()
        self._schedule.clear()


def calc_course_days(
    race_basic_info: pd.DataFrame,
    data_interface: DataInterface,
    logger: logging.Logger | None = None,
    cache: CourseDaysCache | None = None,
) -> pd.DataFrame:
    """芝コース日数4カラムを計算して埋めたDataFrameを返す

    対象レースと同一競馬場・同一コース区分の過去開催日をProviderから遡及取得し、
    芝コース日目・芝コース初日・芝コース経過日数・芝コース週目を計算する。
    芝レースでない場合やコース区分が不明な場合は4カラムをNaNのまま返す。

    Args:
        race_basic_info (pd.DataFrame): レース基本情報（1行、RACE_BASIC_INFO_COLUMNSのカラム）
        data_interface (DataInterface): 過去レース取得に使用するデータ取得層
        logger (logging.Logger | None): ロガーインスタンス
        cache (CourseDaysCache | None): 計算結果と取得結果のキャッシュ。省略時は
            キャッシュせず毎回計算する

    Returns:
        pd.DataFrame: 芝コース日数4カラムを設定したレース基本情報

    Raises:
        LookbackLimitExceededError: 過去レースの遡及が上限日数を超えた場合
    """
    logger = logger or logging.getLogger(__name__)
    df = race_basic_info.copy()
    row = df.iloc[0]
    if row["芝ダ"] != "芝" or pd.isna(row["コース区分"]):
        logger.debug(
            "芝レースでないかコース区分が不明のためコース日数を計算しません: レースコード=%s",
            row["レースコード"],
        )
        return df

    keibajo_code = str(row["競馬場コード"])
    course_kubun = str(row["コース区分"])
    key = (keibajo_code, str(row["開催年"]), str(row["開催月日"]), course_kubun)

    if cache is not None:
        cached_values = cache.get_course_days(key)
        if cached_values is not None:
            logger.debug("コース日数をキャッシュから取得します: キー=%s", key)
            return _apply_course_days(df, cached_values)

    race_date = _to_date(str(row["開催年"]), str(row["開催月日"]))
    logger.debug(
        "コース日数の計算を開始します: 競馬場コード=%s, コース区分=%s, 開催日=%s",
        keibajo_code,
        course_kubun,
        race_date,
    )
    past_days = _collect_same_course_days(
        data_interface, keibajo_code, course_kubun, race_date, logger, cache
    )

    # 対象レース日を含めた同一コースの開催日リスト（昇順）
    course_day_list = past_days + [race_date]
    first_date = course_day_list[0]
    course_week = 1
    for prev_day, cur_day in zip(course_day_list, course_day_list[1:]):
        if (cur_day - prev_day).days > _SAME_WEEK_GAP_DAYS:
            course_week += 1

    values: dict[str, Any] = {
        "芝コース日目": len(course_day_list),
        "芝コース初日": first_date.strftime("%Y%m%d"),
        "芝コース経過日数": (race_date - first_date).days + 1,
        "芝コース週目": course_week,
    }
    if cache is not None:
        cache.set_course_days(key, values)
    logger.debug(
        "コース日数の計算が完了しました: 芝コース日目=%d, 芝コース週目=%d",
        len(course_day_list),
        course_week,
    )
    return _apply_course_days(df, values)


def _apply_course_days(df: pd.DataFrame, values: dict[str, Any]) -> pd.DataFrame:
    """計算済みのコース日数4カラムをDataFrameへ設定する

    キャッシュするのは計算した4カラムの値だけとし、呼び出しごとに渡された
    レース基本情報へ設定する。DataFrame全体をキャッシュすると他のカラムまで
    共有してしまうため。

    Args:
        df (pd.DataFrame): 設定先のレース基本情報（1行）
        values (dict[str, Any]): コース日数4カラムの値

    Returns:
        pd.DataFrame: 4カラムを設定したDataFrame
    """
    df["芝コース日目"] = pd.array([values["芝コース日目"]], dtype="Int64")
    df["芝コース初日"] = values["芝コース初日"]
    df["芝コース経過日数"] = pd.array([values["芝コース経過日数"]], dtype="Int64")
    df["芝コース週目"] = pd.array([values["芝コース週目"]], dtype="Int64")
    return df


def _collect_same_course_days(
    data_interface: DataInterface,
    keibajo_code: str,
    course_kubun: str,
    race_date: date,
    logger: logging.Logger,
    cache: CourseDaysCache | None = None,
) -> list[date]:
    """対象レース日より前の同一競馬場・同一コース区分の開催日リストを昇順で返す

    対象レース日から過去に向かって開催スケジュールを取得し、同一コース区分の開催日を収集する。
    直近の同一コース開催日との間隔が_RESET_GAP_DAYS以上空いた時点で遡及を終了する。

    Args:
        data_interface (DataInterface): 過去レース取得に使用するデータ取得層
        keibajo_code (str): 競馬場コード（2桁）
        course_kubun (str): コース区分（A〜E）
        race_date (date): 対象レースの開催日
        logger (logging.Logger): ロガーインスタンス
        cache (CourseDaysCache | None): 取得結果のキャッシュ

    Returns:
        list[date]: 同一コース区分の開催日リスト（昇順）

    Raises:
        LookbackLimitExceededError: 遡及が_MAX_LOOKBACK_DAYSを超えた場合
    """
    collected: list[date] = []
    # 直近の同一コース開催日（遡及終了判定の基準）
    latest = race_date
    window_end = race_date - timedelta(days=1)
    while (latest - window_end).days < _RESET_GAP_DAYS:
        window_start = window_end - timedelta(days=_SCHEDULE_WINDOW_DAYS - 1)
        if (race_date - window_start).days > _MAX_LOOKBACK_DAYS:
            logger.error(
                "コース日数計算の遡及が上限を超えました: 競馬場コード=%s, 開催日=%s",
                keibajo_code,
                race_date,
            )
            raise LookbackLimitExceededError(
                f"コース日数計算の遡及が上限（{_MAX_LOOKBACK_DAYS}日）を超えました: "
                f"競馬場コード={keibajo_code}, 開催日={race_date}"
            )
        schedule_df = _get_schedule(data_interface, window_start, window_end, cache)
        venue_days_df = _extract_venue_days(schedule_df, keibajo_code)
        for _, schedule_row in venue_days_df.iterrows():
            day = _to_date(str(schedule_row["開催年"]), str(schedule_row["開催月日"]))
            if (latest - day).days >= _RESET_GAP_DAYS:
                return sorted(collected)
            day_course_kubun = _get_course_kubun_of_day(data_interface, schedule_row, logger, cache)
            if day_course_kubun == course_kubun:
                collected.append(day)
                latest = day
        window_end = window_start - timedelta(days=1)
    return sorted(collected)


def _get_schedule(
    data_interface: DataInterface,
    start_date: date,
    end_date: date,
    cache: CourseDaysCache | None,
) -> pd.DataFrame:
    """開催スケジュールを取得する

    同じ期間を繰り返し取得しないようキャッシュする。戻り値は呼び出し側で変更しない
    こと（`_extract_venue_days`は絞り込みで新しいDataFrameを作るため変更しない）。

    Args:
        data_interface (DataInterface): 取得に使用するデータ取得層
        start_date (date): 開始日
        end_date (date): 終了日
        cache (CourseDaysCache | None): 取得結果のキャッシュ

    Returns:
        pd.DataFrame: 開催スケジュールのDataFrame
    """
    key = (start_date.isoformat(), end_date.isoformat())
    if cache is not None:
        cached_schedule = cache.get_schedule(key)
        if cached_schedule is not None:
            return cached_schedule

    schedule_df = data_interface.get_schedule(key[0], key[1])
    if cache is not None:
        cache.set_schedule(key, schedule_df)
    return schedule_df


def _get_course_kubun_of_day(
    data_interface: DataInterface,
    schedule_row: "pd.Series[Any]",
    logger: logging.Logger,
    cache: CourseDaysCache | None = None,
) -> str | None:
    """開催日のコース区分を取得する

    レース番号1〜12のレース基本情報を取得し、レース番号の小さい順に見て最初に
    見つかった芝レースのコース区分を返す。芝コースのコース区分は競馬場・開催日単位で
    共通であるため、1レース分の情報で判定できる。
    開催日に存在しないレース番号は読み飛ばす。

    一括取得に対応したProviderでは12レース分を1回で取得する。レース番号ごとに
    取得すると1開催日あたり最大12回の問い合わせが発生し、コース日数の計算が
    入力生成全体のボトルネックになるため。

    Args:
        data_interface (DataInterface): 過去レース取得に使用するデータ取得層
        schedule_row (pd.Series): 開催スケジュールの1行
        logger (logging.Logger): ロガーインスタンス
        cache (CourseDaysCache | None): 判定結果のキャッシュ

    Returns:
        str | None: コース区分（A〜E）。芝レースが存在しない開催日はNone
    """
    key = (
        str(schedule_row["競馬場コード"]),
        str(schedule_row["開催年"]),
        str(schedule_row["開催月日"]),
    )
    if cache is not None:
        is_cached, cached_kubun = cache.get_course_kubun(key)
        if is_cached:
            return cached_kubun

    race_codes = _build_race_codes_of_day(schedule_row)
    if data_interface.supports_bulk:
        course_kubun = _find_course_kubun_in_bulk(data_interface, race_codes)
    else:
        course_kubun = _find_course_kubun_one_by_one(data_interface, race_codes, logger)

    if course_kubun is None:
        logger.debug(
            "芝レースが存在しない開催日です: 開催年=%s, 開催月日=%s",
            schedule_row["開催年"],
            schedule_row["開催月日"],
        )
    if cache is not None:
        cache.set_course_kubun(key, course_kubun)
    return course_kubun


def _build_race_codes_of_day(schedule_row: "pd.Series[Any]") -> list[str]:
    """開催日のレース番号1〜12に対応する16桁レースコードを組み立てる

    Args:
        schedule_row (pd.Series): 開催スケジュールの1行

    Returns:
        list[str]: レース番号昇順の16桁レースコード
    """
    year = str(schedule_row["開催年"])
    monthday = str(schedule_row["開催月日"])
    keibajo_code = str(schedule_row["競馬場コード"])
    kai = int(schedule_row["開催回"])
    nichime = int(schedule_row["開催日目"])
    return [
        f"{year}{monthday}{keibajo_code}{kai:02d}{nichime:02d}{race_num:02d}"
        for race_num in range(1, _MAX_RACE_NUM + 1)
    ]


def _find_course_kubun_in_bulk(data_interface: DataInterface, race_codes: list[str]) -> str | None:
    """一括取得したレース基本情報から最初の芝レースのコース区分を返す

    get_race_basic_info_bulkはレースコード昇順で返す。同一開催日ではレースコードの
    末尾2桁がレース番号であるため、レースコード昇順はレース番号昇順と一致する。
    存在しないレース番号の行は含まれない。

    Args:
        data_interface (DataInterface): 過去レース取得に使用するデータ取得層
        race_codes (list[str]): レース番号昇順の16桁レースコード

    Returns:
        str | None: コース区分（A〜E）。芝レースが存在しない場合はNone
    """
    races = data_interface.get_race_basic_info_bulk(race_codes)
    for _, race_row in races.iterrows():
        course_kubun = _extract_course_kubun(race_row)
        if course_kubun is not None:
            return course_kubun
    return None


def _find_course_kubun_one_by_one(
    data_interface: DataInterface, race_codes: list[str], logger: logging.Logger
) -> str | None:
    """レース基本情報を1件ずつ取得して最初の芝レースのコース区分を返す

    一括取得に対応していないProvider向けの経路。

    Args:
        data_interface (DataInterface): 過去レース取得に使用するデータ取得層
        race_codes (list[str]): レース番号昇順の16桁レースコード
        logger (logging.Logger): ロガーインスタンス

    Returns:
        str | None: コース区分（A〜E）。芝レースが存在しない場合はNone
    """
    for race_code in race_codes:
        try:
            race_row = data_interface.get_race_basic_info(race_code).iloc[0]
        except ValueError as exc:
            logger.debug(
                "レース基本情報を取得できなかったため読み飛ばします: race_code=%s, %s",
                race_code,
                exc,
            )
            continue
        course_kubun = _extract_course_kubun(race_row)
        if course_kubun is not None:
            return course_kubun
    return None


def _extract_course_kubun(race_row: "pd.Series[Any]") -> str | None:
    """レース基本情報の1行から芝レースのコース区分を取り出す

    Args:
        race_row (pd.Series): レース基本情報の1行

    Returns:
        str | None: コース区分（A〜E）。芝レースでないかコース区分が不明な場合はNone
    """
    if race_row["芝ダ"] != "芝" or pd.isna(race_row["コース区分"]):
        return None
    return str(race_row["コース区分"])


def _extract_venue_days(schedule_df: pd.DataFrame, keibajo_code: str) -> pd.DataFrame:
    """開催スケジュールから指定競馬場の開催日行を新しい順に取り出す

    Args:
        schedule_df (pd.DataFrame): 開催スケジュールのDataFrame
        keibajo_code (str): 競馬場コード（2桁）

    Returns:
        pd.DataFrame: 指定競馬場の開催日行（開催日の降順、開催日単位で重複排除）
    """
    df = schedule_df[schedule_df["競馬場コード"] == keibajo_code]
    df = df.drop_duplicates(subset=["開催年", "開催月日"])
    df = df.sort_values(["開催年", "開催月日"], ascending=False)
    return df.reset_index(drop=True)


def _to_date(year: str, monthday: str) -> date:
    """開催年と開催月日からdate型を生成する

    Args:
        year (str): 開催年（yyyy形式4桁）
        monthday (str): 開催月日（mmdd形式4桁）

    Returns:
        date: 開催日
    """
    return date(int(year), int(monthday[:2]), int(monthday[2:]))
