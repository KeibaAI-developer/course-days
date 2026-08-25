"""芝コース日数の一括計算と保存.

期間を指定して開催日を列挙し、まだ保存されていないものだけを計算して保存する。
予測時・学習データ生成時に読むだけで済むよう、あらかじめ流しておく。
"""

import logging
from typing import Any

from db_client import DbClient
from keiba_data_interface import DataInterface

from course_days.calculator import (
    CourseDaysCache,
    calc_course_days_for_key,
    extract_venue_days,
    get_course_kubun_of_day,
)
from course_days.params import CourseDaysKey
from course_days.store import CourseDaysStore

# まとめて保存する件数。途中で止まっても続きから再開できるよう区切る
_UPSERT_CHUNK_SIZE = 100


class CourseDaysComputer:
    """期間を指定して芝コース日数を計算し保存する.

    Attributes:
        data_interface (DataInterface): 開催スケジュール・レース基本情報の取得に使う
        db_client (DbClient): course_daysテーブルへの接続
    """

    def __init__(
        self,
        data_interface: DataInterface,
        db_client: DbClient,
        logger: logging.Logger | None = None,
    ) -> None:
        self.data_interface = data_interface
        self.db_client = db_client
        self._logger = logger or logging.getLogger(__name__)
        self._store = CourseDaysStore(db_client, self._logger.getChild("store"))

    def compute(self, start_date: str, end_date: str) -> int:
        """指定期間の開催日について計算し保存する.

        **保存済みの開催日は計算し直さない。** 長い期間をまとめて流すことを想定しており、
        途中で止まっても続きから再開できるようにする。

        Args:
            start_date (str): 開始日（YYYY-MM-DD形式）
            end_date (str): 終了日（YYYY-MM-DD形式）

        Returns:
            int: 保存した件数
        """
        self._store.setup()
        targets = self._collect_remaining(start_date, end_date)
        if not targets:
            self._logger.info("計算対象がありません: %s〜%s", start_date, end_date)
            return 0

        self._logger.info("芝コース日数を計算します: %d件", len(targets))
        cache = CourseDaysCache()
        saved_count = 0
        chunk: dict[CourseDaysKey, dict[str, Any]] = {}
        for key in targets:
            chunk[key] = calc_course_days_for_key(
                key, self.data_interface, self._logger.getChild("calculator"), cache
            )
            # まとめて保存すると途中で止まったときに何も残らない。区切って保存し、
            # 再実行したときに続きから進められるようにする
            if len(chunk) >= _UPSERT_CHUNK_SIZE:
                self._store.upsert(chunk)
                saved_count += len(chunk)
                self._logger.info("芝コース日数を保存しました: %d/%d件", saved_count, len(targets))
                chunk = {}
        if chunk:
            self._store.upsert(chunk)
            saved_count += len(chunk)
        self._logger.info("芝コース日数を保存しました: %d件", saved_count)
        return saved_count

    def count_remaining(self, start_date: str, end_date: str) -> int:
        """指定期間のうち未保存の開催日数を返す.

        Args:
            start_date (str): 開始日（YYYY-MM-DD形式）
            end_date (str): 終了日（YYYY-MM-DD形式）

        Returns:
            int: 未保存の開催日数
        """
        # 保存済みかどうかを見るためテーブルを読む。テーブルが無い環境でも数えられる
        # よう、computeと同じく先に作る
        self._store.setup()
        return len(self._collect_remaining(start_date, end_date))

    def collect_targets(self, start_date: str, end_date: str) -> list[CourseDaysKey]:
        """指定期間の芝の開催日をキーとして列挙する.

        開催スケジュールから開催日を取り出し、開催日ごとにコース区分を判定する。
        芝の開催が無い日・コース区分が不明な日は対象外。

        Args:
            start_date (str): 開始日（YYYY-MM-DD形式）
            end_date (str): 終了日（YYYY-MM-DD形式）

        Returns:
            list[CourseDaysKey]: (競馬場コード, 開催年, 開催月日, コース区分) のリスト
        """
        schedule_df = self.data_interface.get_schedule(start_date, end_date)
        if schedule_df.empty:
            self._logger.debug("開催がありません: %s〜%s", start_date, end_date)
            return []

        cache = CourseDaysCache()
        targets: list[CourseDaysKey] = []
        for keibajo_code in sorted(schedule_df["競馬場コード"].dropna().unique()):
            venue_days = extract_venue_days(schedule_df, str(keibajo_code))
            for _, schedule_row in venue_days.iterrows():
                course_kubun = get_course_kubun_of_day(
                    self.data_interface,
                    schedule_row,
                    self._logger.getChild("calculator"),
                    cache,
                )
                if course_kubun is None:
                    continue
                targets.append(
                    (
                        str(schedule_row["競馬場コード"]),
                        str(schedule_row["開催年"]),
                        str(schedule_row["開催月日"]),
                        course_kubun,
                    )
                )
        self._logger.debug("芝の開催日: %d件", len(targets))
        return targets

    def _collect_remaining(self, start_date: str, end_date: str) -> list[CourseDaysKey]:
        """指定期間のうち未保存の開催日をキーとして列挙する.

        Args:
            start_date (str): 開始日（YYYY-MM-DD形式）
            end_date (str): 終了日（YYYY-MM-DD形式）

        Returns:
            list[CourseDaysKey]: 未保存のキーのリスト
        """
        targets = self.collect_targets(start_date, end_date)
        if not targets:
            return []
        saved = self._store.select(targets)
        return [key for key in targets if key not in saved]
