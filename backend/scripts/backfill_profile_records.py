"""迁移后从豆瓣原始导出补齐六字段资料和评论。"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session

from app.config import Settings
from app.database import create_database_engine
from app.profile_records import backfill_from_export


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export_file", type=Path)
    args = parser.parse_args()
    data = json.loads(args.export_file.read_text(encoding="utf-8-sig"))
    engine = create_database_engine(Settings())
    with Session(engine) as session:
        count = backfill_from_export(session, data["records"])
        session.commit()
    engine.dispose()
    print(json.dumps({"backfilled_records": count}))


if __name__ == "__main__":
    main()
