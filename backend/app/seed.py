from app.db import connect

SCHEMA = """
CREATE TABLE IF NOT EXISTS wishes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, note TEXT, status TEXT,
  claimer TEXT, claimed_at TEXT, expires_at TEXT,
  hold_claimer TEXT, hold_until TEXT,
  data_quality TEXT
);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
"""

# Columns added after the initial snapshot; applied idempotently to old DBs.
MIGRATIONS = [
    ("hold_claimer", "ALTER TABLE wishes ADD COLUMN hold_claimer TEXT"),
    ("hold_until", "ALTER TABLE wishes ADD COLUMN hold_until TEXT"),
]


def init_db():
    c = connect()
    c.executescript(SCHEMA)
    existing = {r["name"] for r in c.execute("PRAGMA table_info(wishes)")}
    for name, ddl in MIGRATIONS:
        if name not in existing:
            c.execute(ddl)
    if c.execute("SELECT COUNT(*) c FROM wishes").fetchone()["c"] == 0:
        c.executemany(
            "INSERT INTO wishes(title,note,status,claimer,claimed_at,expires_at,"
            "hold_claimer,hold_until,data_quality) VALUES (?,?,?,?,?,?,?,?,?)",
            [
                ("机械键盘", "红轴", "open", None, None, None, None, None, "clean"),
                ("围巾", "羊毛", "open", None, None, None, None, None, "clean"),
                ("脏愿望-空标题", "", "open", None, None, None, None, None, "dirty"),
                ("过期锁样例", "应被TTL释放", "claimed", "ghost",
                 "2020-01-01T00:00:00+00:00", "2020-01-01T01:00:00+00:00",
                 None, None, "dirty"),
            ],
        )
        c.execute("INSERT INTO settings(key,value) VALUES ('ttl_seconds','86400')")
        c.execute("INSERT INTO settings(key,value) VALUES ('hold_seconds_default','600')")
        c.execute("INSERT INTO settings(key,value) VALUES ('wall_title','暖粉愿望墙')")
        c.commit()
    c.close()
