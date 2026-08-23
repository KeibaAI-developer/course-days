"""芝コース日数の取得と一括計算の使用例.

Usage:
    python example/example_get_course_days.py [--race_code <race_code>]
"""

import argparse
import logging

from db_client import DbClient
from keiba_data_interface import DataInterface

from course_days import COURSE_DAYS_COLUMNS, CourseDaysCache, CourseDaysComputer, get_course_days


def main() -> None:
    """指定レースの芝コース日数を取得して表示する."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--race_code", default="2025122806050811")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    data_interface = DataInterface(provider="mykeibadb")
    db_client = DbClient()

    # 取得。保存済みならDBを読むだけ、未保存ならその場で計算して保存する
    race_basic_info = data_interface.get_race_basic_info(args.race_code)
    # 同じ開催日のレースを続けて処理するならキャッシュを渡す
    cache = CourseDaysCache()
    result = get_course_days(race_basic_info, data_interface, db_client, logger, cache)

    print(f"\nレースコード: {args.race_code}")
    for column in COURSE_DAYS_COLUMNS:
        print(f"  {column}: {result[column].iloc[0]}")

    # 一括計算。あらかじめ流しておけば取得は読むだけで済む
    computer = CourseDaysComputer(data_interface, db_client, logger)
    remaining = computer.count_remaining("2025-12-01", "2025-12-31")
    print(f"\n2025年12月の未保存の開催日: {remaining}件")
    print("保存するには: python scripts/compute_course_days.py "
          "--start_date 2025-12-01 --end_date 2025-12-31")


if __name__ == "__main__":
    main()
