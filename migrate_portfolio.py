"""把本地 portfolio.json 迁移到 portfolio.db。"""

from portfolio import PORTFOLIO_DB_FILE, PORTFOLIO_FILE, migrate_json_to_db


def main():
    imported_count = migrate_json_to_db()
    if imported_count:
        print(f"已从 {PORTFOLIO_FILE.name} 导入 {imported_count} 条持仓到 {PORTFOLIO_DB_FILE.name}")
    else:
        print("没有需要迁移的数据，或迁移已经完成")


if __name__ == "__main__":
    main()
