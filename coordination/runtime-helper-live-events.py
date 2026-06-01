from __future__ import annotations

import json
import sqlite3
import sys


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: runtime-helper-live-events.py max|events DB [SEQ]", file=sys.stderr)
        return 2

    command = sys.argv[1]
    db_path = sys.argv[2]

    with sqlite3.connect(db_path) as con:
        if command == "max":
            row = con.execute("select coalesce(max(seq), 0) from event_log").fetchone()
            print(row[0] or 0)
            return 0

        if command == "events":
            if len(sys.argv) < 4:
                print("events requires SEQ", file=sys.stderr)
                return 2
            last_seq = int(sys.argv[3])
            rows = []
            for row in con.execute(
                """
                select seq, type, ts, actor, agent_id, payload_json
                from event_log
                where seq > ?
                order by seq
                """,
                (last_seq,),
            ):
                rows.append(
                    {
                        "seq": row[0],
                        "type": row[1],
                        "ts": row[2],
                        "actor": row[3],
                        "agent_id": row[4],
                        "payload": json.loads(row[5]),
                    }
                )
            print(json.dumps(rows, ensure_ascii=False))
            return 0

    print(f"unknown command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
