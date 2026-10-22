"""只读查询开发数据库，核实实验室与设备事实。不做任何写操作。"""
import json
import os
import sys

import psycopg
from psycopg import sql

HOST = os.getenv("RAG_DB_HOST", "127.0.0.1")
PORT = int(os.getenv("RAG_DB_PORT", "5432"))
DB = os.getenv("RAG_DB_NAME", "ai_lab_db")
USER = os.getenv("RAG_DB_USER", "ai_lab_app_user")
PASSWORD = os.getenv("RAG_DB_PASSWORD")
SCHEMA = os.getenv("RAG_DB_SCHEMA", "app")


def main() -> int:
    if not PASSWORD:
        raise RuntimeError("请先设置环境变量 RAG_DB_PASSWORD")

    conn = psycopg.connect(
        host=HOST,
        port=PORT,
        dbname=DB,
        user=USER,
        password=PASSWORD,
        connect_timeout=8,
        sslmode="prefer",
        options="-cstatement_timeout=15000",
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SET search_path TO {}, pg_catalog").format(
                    sql.Identifier(SCHEMA)
                )
            )

            # 列出 schema 下所有表
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = %s ORDER BY table_name
                """,
                (SCHEMA,),
            )
            tables = [r[0] for r in cur.fetchall()]
            print("=== TABLES ===")
            print(json.dumps(tables, ensure_ascii=False))

            # 查询实验室
            cur.execute(
                """
                SELECT id, name, location, capacity, open_time, close_time,
                       description, img, status, created_at, updated_at
                FROM labs ORDER BY id
                """
            )
            cols = [d[0] for d in cur.description]
            labs = []
            for row in cur.fetchall():
                labs.append(dict(zip(cols, row)))
            print("=== LABS (%d) ===" % len(labs))
            for l in labs:
                l = dict(l)
                for k in ("open_time", "close_time", "created_at", "updated_at"):
                    if l.get(k) is not None:
                        l[k] = str(l[k])
                print(json.dumps(l, ensure_ascii=False))

            # 查询设备
            cur.execute(
                """
                SELECT id, lab_id, name, description, img, spec, quantity, status,
                       created_at, updated_at
                FROM equipments ORDER BY lab_id, id
                """
            )
            ecols = [d[0] for d in cur.description]
            equips = []
            for row in cur.fetchall():
                e = dict(zip(ecols, row))
                for k in ("created_at", "updated_at"):
                    if e.get(k) is not None:
                        e[k] = str(e[k])
                equips.append(e)
            print("=== EQUIPMENTS (%d) ===" % len(equips))
            for e in equips:
                print(json.dumps(e, ensure_ascii=False))

            # 查询预约记录统计（只看状态分布，不读敏感内容）
            try:
                cur.execute(
                    "SELECT status, count(*) FROM reservations GROUP BY status ORDER BY status"
                )
                print("=== RESERVATION STATUS COUNTS ===")
                for r in cur.fetchall():
                    print(r)
            except Exception as ex:
                print("reservations query skipped:", ex)

            # 用户表统计
            try:
                cur.execute("SELECT count(*) FROM users")
                print("=== USER COUNT ===", cur.fetchone()[0])
            except Exception as ex:
                print("users query skipped:", ex)

            # 保存到 JSON 供后续生成脚本使用
            out = {"tables": tables, "labs": labs, "equipments": equips}
            with open(
                r"D:/AI/faceprogram/rag_document_workbench/db_snapshot.json",
                "w",
                encoding="utf-8",
            ) as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
            print("=== SNAPSHOT WRITTEN ===")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
