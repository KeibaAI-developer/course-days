"""芝コース日数の取得.

保存済みの値をDBから読み、無ければ計算して保存する。呼び出し側はこのモジュールだけを
使えばよい。
"""

import logging
from typing import Any

import pandas as pd
from db_client import DbClient
from keiba_data_interface import DataInterface

from course_days.calculator import CourseDaysCache, apply_course_days, build_key
from course_days.calculator import calc_course_days as calculate
from course_days.params import COURSE_DAYS_COLUMNS
from course_days.store import CourseDaysStore


def get_course_days(
    race_basic_info: pd.DataFrame,
    data_interface: DataInterface,
    db_client: DbClient,
    logger: logging.Logger | None = None,
    cache: CourseDaysCache | None = None,
) -> pd.DataFrame:
    """芝コース日数4カラムを設定したレース基本情報を返す.

    処理の流れ。

    1. 芝レースでない、またはコース区分が不明なら4カラムをNaNのまま返す
    2. メモリキャッシュにあればそれを使う
    3. `course_days` テーブルを引く
    4. 保存されていればその値を設定して返す
    5. 保存されていなければ計算し、保存してから返す

    **5は例外にしない。** 予測は当日のレースを対象にするため、バッチが回る前の開催日は
    必ず未保存になる。ここで例外にすると予測が実行できない。これはフォールバック
    （失敗を握りつぶして別の手段に倒すこと）ではなく、値をその場で実体化しているだけで
    ある。計算そのものが失敗した場合は例外をそのまま伝播させる。未保存だったことは
    `logger.info` に残し、バッチの実行漏れに気づけるようにする。

    Args:
        race_basic_info (pd.DataFrame): レース基本情報（1行）
        data_interface (DataInterface): 未保存だった場合の計算に使う
        db_client (DbClient): course_daysテーブルへの接続
        logger (logging.Logger | None): ロガー
        cache (CourseDaysCache | None): 読み出した値のメモリキャッシュ。省略時は
            呼び出しのたびにDBを引く

    Returns:
        pd.DataFrame: 芝コース日数4カラムを設定したレース基本情報（1行）

    Raises:
        LookbackLimitExceededError: 未保存で計算した際、過去レースの遡及が上限日数を
            超えた場合
    """
    logger = logger or logging.getLogger(__name__)
    df = race_basic_info.copy()
    key = build_key(race_basic_info)
    if key is None:
        logger.debug(
            "芝レースでないかコース区分が不明のためコース日数を取得しません: レースコード=%s",
            df.iloc[0]["レースコード"],
        )
        return df

    if cache is not None:
        cached_values = cache.get_course_days(key)
        if cached_values is not None:
            logger.debug("コース日数をキャッシュから取得します: キー=%s", key)
            return apply_course_days(df, cached_values)

    store = CourseDaysStore(db_client, logger.getChild("store"))
    saved = store.select([key])
    if key in saved:
        logger.debug("コース日数をDBから取得しました: キー=%s", key)
        if cache is not None:
            cache.set_course_days(key, saved[key])
        return apply_course_days(df, saved[key])

    logger.info("コース日数が未保存のため計算して保存します: キー=%s", key)
    calculated = calculate(race_basic_info, data_interface, logger.getChild("calculator"), cache)
    # DBから読んだときと同じPythonの型に揃える。計算結果はpandasの型になっている
    values = {
        column: _to_python(column, calculated[column].iloc[0]) for column in COURSE_DAYS_COLUMNS
    }
    # テーブルが無い環境でも動くよう、書き込む直前に作る。保存済みの開催日ではここへ
    # 来ないため、DDLが走るのは未保存だったときだけである
    store.setup()
    store.upsert({key: values})
    if cache is not None:
        cache.set_course_days(key, values)
    return apply_course_days(df, values)


def _to_python(column: str, value: Any) -> Any:
    """計算結果の値をPythonの型へ揃える.

    DBから読んだ値（`CourseDaysStore.select`）と型を合わせる。芝コース初日は文字列、
    それ以外は整数である。

    Args:
        column (str): 芝コース日数のカラム名
        value (Any): 計算結果の値

    Returns:
        Any: Pythonの型へ揃えた値
    """
    if column == "芝コース初日":
        return str(value)
    return int(value)
