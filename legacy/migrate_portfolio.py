"""Migrate the legacy holdings database to the transaction-ledger schema."""

import storage


def main():
    result = storage.ensure_database()
    if result["migrated"]:
        print(f"已迁移 {result['migrated']} 条期初持仓")
        print(f"迁移前备份: {result['backup']}")
    else:
        print("数据库已是最新结构")


if __name__ == "__main__":
    main()
