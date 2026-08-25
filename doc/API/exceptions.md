# exceptions.py

本ライブラリの例外です。すべて `CourseDaysError` を基底に持ち、呼び出し側は本ライブラリ由来の例外をまとめて捕まえられます。

| 例外 | 基底 | 送出条件 |
|---|---|---|
| `CourseDaysError` | `Exception` | 基底例外。直接は送出しない |
| `LookbackLimitExceededError` | `CourseDaysError` | 同一コースの開催日を遡る処理が上限（365日）を超えた場合。同一コースの使用が1年以上途切れないことは無く、データの不整合か判定条件の誤りが疑われる |

存在しないレースコードに対する `DataNotFoundError` は keiba-data-interface の例外であり、本ライブラリでは欠番の読み飛ばしにのみ使い、呼び出し側へは伝播しません。
