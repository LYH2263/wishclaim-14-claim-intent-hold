from app.db import connect

DEFAULT_HOLD_SECONDS = 300

def init_db():
    c = connect()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS wishes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, note TEXT, status TEXT,
      claimer TEXT, claimed_at TEXT, expires_at TEXT, data_quality TEXT,
      hold_claimer TEXT, hold_until TEXT
    );
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    """)
    cols = {r["name"] for r in c.execute("PRAGMA table_info(wishes)")}
    for col in ("hold_claimer", "hold_until"):
        if col not in cols:
            c.execute(f"ALTER TABLE wishes ADD COLUMN {col} TEXT")
    if c.execute("SELECT COUNT(*) c FROM wishes").fetchone()["c"] == 0:
        c.executemany(
            "INSERT INTO wishes(title,note,status,claimer,claimed_at,expires_at,data_quality) VALUES (?,?,?,?,?,?,?)",
            [
                ("机械键盘", "红轴", "open", None, None, None, "clean"),
                ("围巾", "羊毛", "open", None, None, None, "clean"),
                ("脏愿望-空标题", "", "open", None, None, None, "dirty"),
                ("过期锁样例", "应被TTL释放", "claimed", "ghost", "2020-01-01T00:00:00+00:00",
                 "2020-01-01T01:00:00+00:00", "dirty"),
            ],
        )
        c.execute("INSERT INTO settings(key,value) VALUES ('ttl_seconds','86400')")
        c.execute("INSERT INTO settings(key,value) VALUES ('wall_title','暖粉愿望墙')")
    c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES ('hold_seconds',?)",
              (str(DEFAULT_HOLD_SECONDS),))
    c.commit()
    c.close()
