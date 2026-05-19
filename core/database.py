import sqlite3
import json
import os
import threading
from datetime import datetime
from typing import Any

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eaas.db")
_lock = threading.RLock()


def _conn():
    c = sqlite3.connect(_DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS suppliers (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    contact         TEXT,
    phone           TEXT,
    email           TEXT,
    city            TEXT,
    iban            TEXT,
    rating          REAL DEFAULT 0,
    on_time_rate    REAL DEFAULT 0,
    defect_rate     REAL DEFAULT 0,
    lead_time_target REAL DEFAULT 0,
    lead_time_actual REAL DEFAULT 0,
    total_orders    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS products (
    sku             TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    category        TEXT,
    stock           INTEGER DEFAULT 0,
    price           REAL DEFAULT 0,
    cost            REAL DEFAULT 0,
    status          TEXT,
    reorder_point   INTEGER DEFAULT 0,
    reorder_qty     INTEGER DEFAULT 0,
    lead_time       INTEGER DEFAULT 0,
    supplier_id     INTEGER,
    platforms       TEXT,
    return_rate     REAL DEFAULT 0,
    image_path      TEXT,
    monthly_sales   TEXT,
    weight_kg       REAL DEFAULT 0,
    barcode         TEXT,
    description     TEXT,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
);

CREATE TABLE IF NOT EXISTS materials (
    code            TEXT PRIMARY KEY,
    name            TEXT,
    stock           INTEGER DEFAULT 0,
    reorder_point   INTEGER DEFAULT 0,
    unit_cost       REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bom (
    sku             TEXT,
    material_code   TEXT,
    qty             INTEGER DEFAULT 1,
    PRIMARY KEY (sku, material_code),
    FOREIGN KEY (sku) REFERENCES products(sku),
    FOREIGN KEY (material_code) REFERENCES materials(code)
);

CREATE TABLE IF NOT EXISTS orders (
    id              TEXT PRIMARY KEY,
    platform        TEXT,
    platform_color  TEXT,
    sku             TEXT,
    product         TEXT,
    qty             INTEGER,
    total           REAL,
    status          TEXT,
    customer        TEXT,
    city            TEXT,
    district        TEXT,
    address         TEXT,
    note            TEXT,
    cargo           TEXT,
    tracking        TEXT,
    tracking_url    TEXT,
    est_days        INTEGER,
    deadline_hours  INTEGER,
    invoice         TEXT,
    commission      REAL,
    cargo_cost      REAL,
    kdv             REAL,
    date            TEXT,
    label_path      TEXT,
    invoice_path    TEXT
);

CREATE TABLE IF NOT EXISTS order_reviews (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    TEXT,
    user        TEXT,
    rating      INTEGER,
    text        TEXT,
    reply       TEXT,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT,
    descr       TEXT,
    type        TEXT,
    amount      REAL,
    category    TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    severity    INTEGER,
    type        TEXT,
    title       TEXT,
    body        TEXT,
    target_sku  TEXT,
    action      TEXT,
    created_at  TEXT,
    read        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS agent_actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT,
    target      TEXT,
    payload     TEXT,
    status      TEXT,
    created_at  TEXT,
    applied_at  TEXT
);
"""


def init_db():
    with _lock:
        c = _conn()
        for stmt in _SCHEMA.strip().split(";"):
            if stmt.strip():
                c.execute(stmt)
        c.commit()
        live_mode = (os.environ.get("EAAS_DATA_MODE", "LIVE").upper() == "LIVE")
        if _get_setting(c, "seeded") != "1":
            _seed_reference_only(c) if live_mode else _seed(c)
            _set_setting(c, "seeded", "1")
            _set_setting(c, "data_mode", "LIVE" if live_mode else "MOCK")
            c.commit()
        c.close()


def _seed_reference_only(c):
    from core.mock_data import (SUPPLIERS, MATERIALS, ADVISOR_INSIGHTS)
    for s in SUPPLIERS:
        c.execute("""INSERT OR REPLACE INTO suppliers(id,name,contact,phone,email,city,iban,
                     rating,on_time_rate,defect_rate,lead_time_target,lead_time_actual,total_orders)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (s["id"], s["name"], s["contact"], s["phone"], s["email"], s["city"], s["iban"],
                   s["rating"], s["on_time_rate"], s["defect_rate"], s["lead_time_target"],
                   s["lead_time_actual"], s["total_orders"]))
    for m in MATERIALS:
        c.execute("""INSERT OR REPLACE INTO materials(code,name,stock,reorder_point,unit_cost)
                     VALUES(?,?,?,?,?)""",
                  (m["code"], m["name"], m["stock"], m["reorder_point"], m["unit_cost"]))
    for n in ADVISOR_INSIGHTS:
        c.execute("""INSERT INTO notifications(severity,type,title,body,target_sku,action,read)
                     VALUES(?,?,?,?,?,?,0)""",
                  (n["severity"], n["type"], n["title"], n["body"],
                   n.get("target_sku"), n.get("action")))


def _get_setting(c, k, default=None):
    row = c.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
    return row["value"] if row else default


def _set_setting(c, k, v):
    c.execute("INSERT INTO settings(key,value) VALUES(?,?) "
              "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))


def get_setting(k, default=None):
    with _lock:
        c = _conn()
        v = _get_setting(c, k, default)
        c.close()
        return v


def set_setting(k, v):
    with _lock:
        c = _conn()
        _set_setting(c, k, v)
        c.commit()
        c.close()


def _seed(c):
    from core.mock_data import (SUPPLIERS, PRODUCTS, MATERIALS, BOM, ORDERS,
                                 TRANSACTIONS, ADVISOR_INSIGHTS)
    for s in SUPPLIERS:
        c.execute("""INSERT OR REPLACE INTO suppliers(id,name,contact,phone,email,city,iban,
                     rating,on_time_rate,defect_rate,lead_time_target,lead_time_actual,total_orders)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (s["id"], s["name"], s["contact"], s["phone"], s["email"], s["city"], s["iban"],
                   s["rating"], s["on_time_rate"], s["defect_rate"], s["lead_time_target"],
                   s["lead_time_actual"], s["total_orders"]))
    for p in PRODUCTS:
        c.execute("""INSERT OR REPLACE INTO products(sku,name,category,stock,price,cost,status,
                     reorder_point,reorder_qty,lead_time,supplier_id,platforms,return_rate,
                     image_path,monthly_sales,weight_kg,barcode)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (p["sku"], p["name"], p["category"], p["stock"], p["price"], p["cost"],
                   p["status"], p["reorder_point"], p["reorder_qty"], p["lead_time"],
                   p["supplier_id"], json.dumps(p["platforms"]), p["return_rate"],
                   p["image_path"], json.dumps(p["monthly_sales"]), p["weight_kg"], p["barcode"]))
    for m in MATERIALS:
        c.execute("INSERT OR REPLACE INTO materials VALUES(?,?,?,?,?)",
                  (m["code"], m["name"], m["stock"], m["reorder_point"], m["unit_cost"]))
    for sku, items in BOM.items():
        for code, qty in items:
            c.execute("INSERT OR REPLACE INTO bom(sku,material_code,qty) VALUES(?,?,?)",
                      (sku, code, qty))
    for o in ORDERS:
        c.execute("""INSERT OR REPLACE INTO orders(id,platform,platform_color,sku,product,qty,
                     total,status,customer,city,district,address,note,cargo,tracking,tracking_url,
                     est_days,deadline_hours,invoice,commission,cargo_cost,kdv,date)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (o["id"], o["platform"], o["platform_color"], o["sku"], o["product"], o["qty"],
                   o["total"], o["status"], o["customer"], o["city"], o["district"], o["address"],
                   o["note"], o["cargo"], o["tracking"], o["tracking_url"], o["est_days"],
                   o["deadline_hours"], o["invoice"], o["commission"], o["cargo_cost"], o["kdv"],
                   o["date"]))
        for rv in o.get("reviews", []):
            c.execute("INSERT INTO order_reviews(order_id,user,rating,text,reply) VALUES(?,?,?,?,?)",
                      (o["id"], rv["user"], rv["rating"], rv["text"], rv.get("reply")))
    for t in TRANSACTIONS:
        c.execute("INSERT INTO transactions(date,descr,type,amount,category) VALUES(?,?,?,?,?)",
                  (t["date"], t["desc"], t["type"], t["amount"], t["cat"]))
    now = datetime.now().isoformat()
    for ins in ADVISOR_INSIGHTS:
        c.execute("""INSERT INTO notifications(severity,type,title,body,target_sku,action,created_at)
                     VALUES(?,?,?,?,?,?,?)""",
                  (ins["severity"], ins["type"], ins["title"], ins["body"],
                   ins.get("target_sku"), ins.get("action"), now))


def fetch_all(query, params=()):
    with _lock:
        c = _conn()
        rows = [dict(r) for r in c.execute(query, params).fetchall()]
        c.close()
        return rows


def fetch_one(query, params=()):
    with _lock:
        c = _conn()
        r = c.execute(query, params).fetchone()
        c.close()
        return dict(r) if r else None


def execute(query, params=()):
    with _lock:
        c = _conn()
        cur = c.execute(query, params)
        c.commit()
        lid = cur.lastrowid
        c.close()
        return lid


def get_products() -> list:
    rows = fetch_all("SELECT p.*, s.name AS supplier_name, s.on_time_rate, s.defect_rate "
                     "FROM products p LEFT JOIN suppliers s ON p.supplier_id = s.id")
    for r in rows:
        try:
            r["monthly_sales"] = json.loads(r["monthly_sales"] or "[]")
        except Exception:
            r["monthly_sales"] = []
        try:
            r["platforms"] = json.loads(r["platforms"] or "[]")
        except Exception:
            r["platforms"] = []
    return rows


def get_product(sku: str) -> dict:
    p = fetch_one("SELECT p.*, s.name AS supplier_name, s.on_time_rate, s.defect_rate, "
                  "s.lead_time_actual, s.rating AS supplier_rating "
                  "FROM products p LEFT JOIN suppliers s ON p.supplier_id = s.id "
                  "WHERE p.sku=?", (sku,))
    if not p:
        return None
    try:
        p["monthly_sales"] = json.loads(p["monthly_sales"] or "[]")
    except Exception:
        p["monthly_sales"] = []
    try:
        p["platforms"] = json.loads(p["platforms"] or "[]")
    except Exception:
        p["platforms"] = []
    return p


def update_product(sku: str, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [sku]
    execute(f"UPDATE products SET {cols} WHERE sku=?", vals)


def add_product(p: dict):
    execute("""INSERT INTO products(sku,name,category,stock,price,cost,status,reorder_point,
               reorder_qty,lead_time,supplier_id,platforms,return_rate,image_path,monthly_sales,
               weight_kg,barcode,description)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (p["sku"], p["name"], p.get("category", ""), p.get("stock", 0),
             p.get("price", 0), p.get("cost", 0), p.get("status", "Satışta"),
             p.get("reorder_point", 0), p.get("reorder_qty", 0), p.get("lead_time", 0),
             p.get("supplier_id"), json.dumps(p.get("platforms", [])),
             p.get("return_rate", 0), p.get("image_path"),
             json.dumps(p.get("monthly_sales", [0]*12)),
             p.get("weight_kg", 0), p.get("barcode", ""), p.get("description", "")))


def get_suppliers() -> list:
    return fetch_all("SELECT * FROM suppliers ORDER BY rating DESC")


def get_orders(status_filter: str = None) -> list:
    if status_filter == "active":
        q = "SELECT * FROM orders WHERE status != 'İade' ORDER BY date DESC"
        rows = fetch_all(q)
    elif status_filter == "returns":
        q = "SELECT * FROM orders WHERE status = 'İade' ORDER BY date DESC"
        rows = fetch_all(q)
    else:
        rows = fetch_all("SELECT * FROM orders ORDER BY date DESC")
    for r in rows:
        r["reviews"] = fetch_all("SELECT * FROM order_reviews WHERE order_id=?", (r["id"],))
    return rows


def get_transactions() -> list:
    rows = fetch_all("SELECT * FROM transactions ORDER BY date DESC")
    for r in rows:
        r["desc"] = r.pop("descr", "")
        r["cat"] = r.pop("category", "")
    return rows


def get_notifications(only_unread: bool = False) -> list:
    if only_unread:
        return fetch_all("SELECT * FROM notifications WHERE read=0 ORDER BY severity DESC, id DESC")
    return fetch_all("SELECT * FROM notifications ORDER BY severity DESC, id DESC")


def mark_notification_read(nid: int):
    execute("UPDATE notifications SET read=1 WHERE id=?", (nid,))


def add_notification(severity: int, type_: str, title: str, body: str,
                     target_sku: str = None, action: str = None):
    execute("""INSERT INTO notifications(severity,type,title,body,target_sku,action,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (severity, type_, title, body, target_sku, action, datetime.now().isoformat()))


def get_materials() -> list:
    return fetch_all("SELECT * FROM materials")


def get_bom(sku: str) -> list:
    return fetch_all("""SELECT b.qty, m.code, m.name, m.stock, m.reorder_point, m.unit_cost
                        FROM bom b JOIN materials m ON b.material_code = m.code
                        WHERE b.sku=?""", (sku,))


def log_agent_action(action_type: str, target: str, payload: dict, status: str = "pending"):
    execute("""INSERT INTO agent_actions(action_type,target,payload,status,created_at)
               VALUES(?,?,?,?,?)""",
            (action_type, target, json.dumps(payload), status, datetime.now().isoformat()))
