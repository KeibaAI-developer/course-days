"""芝コース日数を期間指定で一括計算し保存するスクリプト.

予測時・学習データ生成時は保存済みの値を読むだけで済ませるため、あらかじめ流しておく。
保存済みの開催日は計算し直さないため、途中で止まっても再実行すれば続きから進む。

Usage:
    python scripts/compute_course_days.py --start_date 2020-01-01 --end_date 2025-12-31

Example:
    python scripts/compute_course_days.py --start_date 2025-01-01 --end_date 2025-12-31
    python scripts/compute_course_days.py --start_date 2025-12-01 --end_date 2025-12-31 --count_only
"""

import argparse
import logging

from db_client import DbClient
from keiba_data_interface import DataInterface

from course_days.computer import CourseDaysComputer


def main() -> None:
    """指定期間の芝コース日数を計算して保存する."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--start_date", required=True, help="開始日（YYYY-MM-DD形式）")
    parser.add_argument("--end_date", required=True, help="終了日（YYYY-MM-DD形式）")
    parser.add_argument("--provider", default="mykeibadb", help="データ取得元")
    parser.add_argument(
        "--count_only",
        action="store_true",
        help="未保存の開催日数を数えるだけで保存しない",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logger = logging.getLogger("compute_course_days")

    computer = CourseDaysComputer(DataInterface(args.provider), DbClient(), logger)

    if args.count_only:
        remaining = computer.count_remaining(args.start_date, args.end_date)
        print(f"未保存の開催日: {remaining}件（{args.start_date}〜{args.end_date}）")
        return

    saved = computer.compute(args.start_date, args.end_date)
    print(f"保存した開催日: {saved}件（{args.start_date}〜{args.end_date}）")


if __name__ == "__main__":
    main()
