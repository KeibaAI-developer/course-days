"""course_daysテーブルの読み書き.

芝コース日数はKeibaAIのDBへ保存する。mykeibadbのDBはmykeibadbという提供ソフトが
生成するものであり、こちらから手を入れない。
"""

import logging
from typing import Any

import pandas as pd
from db_client import DbClient

from course_days.params import COLUMN_TO_DB, PRIMARY_KEYS, TABLE_DDL, TABLE_NAME

# 主キーの型（競馬場コード, 開催年, 開催月日, コース区分）
CourseDaysKey = tuple[str, str, str, str]


class CourseDaysStore:
    """course_daysテーブルの読み書き.

    Attributes:
        db_client (DbClient): KeibaAIのDBへ接続するクライアント
    """

    def __init__(self, db_client: DbClient, logger: logging.Logger | None = None) -> None:
        self.db_client = db_client
        self._logger = logger or logging.getLogger(__name__)

    def setup(self) -> None:
        """テーブルが無ければ作成する."""
        self._logger.debug("course_daysテーブルを作成します（存在しない場合）")
        self.db_client.setup_table(TABLE_DDL)

    def select(self, keys: list[CourseDaysKey]) -> dict[CourseDaysKey, dict[str, Any]]:
        """主キーのリストに対応する芝コース日数をまとめて読み出す.

        1レースの入力生成で45件の開催日が必要になるため、1件ずつ引くと元の問題が形を
        変えて残る。1回のクエリで引く。

        主キーは4カラムの組であり、組のINでは絞り込めない。カラムごとのINで引いて
        （要求した組の上位集合が返る）、要求した組だけを取り出す。開催日の数は限られる
        ため、上位集合が問題になるほど大きくなることはない。

        Args:
            keys (list[CourseDaysKey]): (競馬場コード, 開催年, 開催月日, コース区分) のリスト

        Returns:
            dict[CourseDaysKey, dict[str, Any]]: 主キー → 芝コース日数4カラムの値。
                保存されているキーのみを含む
        """
        if not keys:
            self._logger.debug("読み出し対象が無いためクエリを発行しません")
            return {}

        unique_keys = list(dict.fromkeys(keys))
        where = {
            column: sorted({key[index] for key in unique_keys})
            for index, column in enumerate(PRIMARY_KEYS)
        }
        self._logger.debug("course_daysを読み出します: キー=%d件", len(unique_keys))
        df = self.db_client.select(TABLE_NAME, where=where)

        wanted = set(unique_keys)
        result: dict[CourseDaysKey, dict[str, Any]] = {}
        for _, row in df.iterrows():
            key = (
                str(row["keibajo_code"]),
                str(row["kaisai_year"]),
                str(row["kaisai_month_day"]),
                str(row["course_kubun"]),
            )
            if key not in wanted:
                continue
            result[key] = {
                column: _to_value(column, row[db_column])
                for column, db_column in COLUMN_TO_DB.items()
            }
        self._logger.debug("course_daysを読み出しました: %d件", len(result))
        return result

    def upsert(self, values: dict[CourseDaysKey, dict[str, Any]]) -> None:
        """芝コース日数をまとめて保存する（既存キーは更新する）.

        Args:
            values (dict[CourseDaysKey, dict[str, Any]]): 主キー → 芝コース日数4カラムの値
        """
        if not values:
            self._logger.debug("保存対象が無いためクエリを発行しません")
            return

        rows = []
        for key, course_days in values.items():
            row: dict[str, Any] = dict(zip(PRIMARY_KEYS, key, strict=True))
            for column, db_column in COLUMN_TO_DB.items():
                row[db_column] = course_days[column]
            rows.append(row)

        self._logger.debug("course_daysを保存します: %d件", len(rows))
        self.db_client.upsert(TABLE_NAME, pd.DataFrame(rows), primary_keys=PRIMARY_KEYS)
        self._logger.debug("course_daysを保存しました: %d件", len(rows))


def _to_value(column: str, db_value: Any) -> Any:
    """DBの値を芝コース日数の値へ変換する.

    芝コース初日はYYYYMMDDの文字列、それ以外は整数である。移行元の戻り値と型を
    合わせるため、DBから読んだ値をPythonの型へ揃える。

    Args:
        column (str): 芝コース日数のカラム名
        db_value (Any): DBから読んだ値

    Returns:
        Any: 芝コース日数の値
    """
    if column == "芝コース初日":
        return str(db_value)
    return int(db_value)
