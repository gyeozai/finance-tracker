from app import db, Expense
from datetime import datetime

def check_database():
    print("检查数据库内容：")
    print("-" * 50)
    
    # 获取所有记录
    records = Expense.query.all()
    print(f"总记录数：{len(records)}")
    
    # 按月份分组统计
    monthly_stats = {}
    for record in records:
        month_key = f"{record.date.year}-{record.date.month:02d}"
        if month_key not in monthly_stats:
            monthly_stats[month_key] = {
                'expense': 0,
                'income': 0,
                'count': 0
            }
        monthly_stats[month_key]['count'] += 1
        if record.amount < 0:
            monthly_stats[month_key]['expense'] += abs(record.amount)
        else:
            monthly_stats[month_key]['income'] += record.amount
    
    print("\n每月统计：")
    for month, stats in sorted(monthly_stats.items()):
        print(f"{month}:")
        print(f"  记录数：{stats['count']}")
        print(f"  支出：{stats['expense']:.2f}")
        print(f"  收入：{stats['income']:.2f}")
        print()
    
    # 检查最近的记录
    print("\n最近的5条记录：")
    recent_records = Expense.query.order_by(Expense.date.desc()).limit(5).all()
    for record in recent_records:
        print(f"日期：{record.date.strftime('%Y-%m-%d %H:%M')}")
        print(f"金额：{record.amount}")
        print(f"类别：{record.category}")
        print(f"描述：{record.description}")
        print("-" * 30)

if __name__ == '__main__':
    check_database() 