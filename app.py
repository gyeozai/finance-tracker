from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import calendar
import os
from collections import Counter
import requests

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///expenses.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

def get_exchange_rates():
    """获取实时汇率"""
    try:
        # 使用免费的汇率API
        response = requests.get('https://api.exchangerate-api.com/v4/latest/TWD')
        if response.status_code == 200:
            data = response.json()
            rates = data['rates']
            return {
                'NTD': 1.0,
                'MYR': 1 / rates['MYR'],  # 转换为1 MYR = x TWD
                'USD': 1 / rates['USD']   # 转换为1 USD = x TWD
            }
    except Exception as e:
        print(f"获取汇率失败: {e}")
    
    # 如果API调用失败，返回默认汇率
    return {
        'NTD': 1.0,
        'MYR': 7.2,  # 默认汇率
        'USD': 32.5  # 默认汇率
    }

def convert_to_ntd(amount, currency):
    """将金额转换为台币"""
    rates = get_exchange_rates()
    return amount * rates.get(currency, 1.0)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    currency = db.Column(db.String(10), nullable=False, default='NTD')
    type = db.Column(db.String(10), nullable=False, default='expense')  # 新增字段，用于区分支出和收入

@app.route('/')
def index():
    # Get current year and month
    now = datetime.now()
    year = request.args.get('year', now.year, type=int)
    month = request.args.get('month', now.month, type=int)
    
    # Get first and last day of the month
    first_day = datetime(year, month, 1)
    last_day = datetime(year, month, calendar.monthrange(year, month)[1])
    
    # Get all expenses for the month
    expenses = Expense.query.filter(
        Expense.date >= first_day,
        Expense.date <= last_day
    ).all()
    
    # Group expenses by date
    daily_expenses = {}
    for expense in expenses:
        date_str = expense.date.strftime('%Y-%m-%d')
        if date_str not in daily_expenses:
            daily_expenses[date_str] = []
        daily_expenses[date_str].append(expense)
    
    # Calculate daily totals (所有金额已经是台币)
    daily_totals = {}
    for date_str, day_expenses in daily_expenses.items():
        daily_totals[date_str] = sum(expense.amount for expense in day_expenses)
    
    # Generate calendar
    cal = calendar.monthcalendar(year, month)
    
    # Calculate previous and next month
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    
    # 获取支出和收入分类
    expense_categories = db.session.query(
        Expense.category,
        db.func.count(Expense.id).label('count')
    ).filter(Expense.type == 'expense').group_by(Expense.category).all()
    
    income_categories = db.session.query(
        Expense.category,
        db.func.count(Expense.id).label('count')
    ).filter(Expense.type == 'income').group_by(Expense.category).all()
    
    # 按使用次数降序排序
    expense_categories = sorted(expense_categories, key=lambda x: x[1], reverse=True)
    income_categories = sorted(income_categories, key=lambda x: x[1], reverse=True)
    
    # Get currency from session or default to NTD
    currency = session.get('currency', 'NTD')
    
    # Set currency symbol
    currency_symbol = {
        'NTD': 'NT$',
        'MYR': 'RM',
        'USD': '$'
    }.get(currency, 'NT$')
    
    # Get month name
    month_name = calendar.month_name[month]
    
    return render_template('index.html',
                         year=year,
                         month=month,
                         month_name=month_name,
                         calendar=cal,
                         daily_totals=daily_totals,
                         prev_month=prev_month,
                         prev_year=prev_year,
                         next_month=next_month,
                         next_year=next_year,
                         now=now,
                         expense_categories=expense_categories,
                         income_categories=income_categories,
                         currency=currency,
                         currency_symbol=currency_symbol)

@app.route('/day_detail/<date>')
def day_detail(date):
    """显示特定日期的详细支出和收入"""
    try:
        # 将日期字符串转换为datetime对象
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        
        # 获取该日期的所有记录
        records = Expense.query.filter(
            db.func.date(Expense.date) == date_obj.date()
        ).order_by(Expense.date.desc()).all()
        
        # 计算总支出和总收入
        total_expense = sum(record.amount for record in records if record.amount < 0)
        total_income = sum(record.amount for record in records if record.amount > 0)
        
        # 获取当前货币
        currency = session.get('currency', 'NTD')
        
        # 设置货币符号
        currency_symbol = {
            'NTD': 'NT$',
            'MYR': 'RM',
            'USD': '$'
        }.get(currency, 'NT$')
        
        return render_template('day_detail.html',
                             date=date_obj,
                             records=records,
                             total_expense=abs(total_expense),
                             total_income=total_income,
                             currency_symbol=currency_symbol)
    except ValueError:
        flash('Invalid date format!', 'danger')
        return redirect(url_for('index'))

@app.route('/add', methods=['POST'])
def add_expense():
    amount = float(request.form['amount'])
    category = request.form['category']
    description = request.form['description']
    date_str = request.form['date']
    currency = request.form['currency']
    record_type = request.form.get('type', 'expense')  # 获取记录类型，默认为支出
    
    # 保存货币到会话
    session['currency'] = currency
    
    # 将日期字符串转换为datetime对象
    date = datetime.strptime(date_str, '%Y-%m-%d')
    
    # 获取当前汇率并转换为台币
    rates = get_exchange_rates()
    ntd_amount = amount * rates.get(currency, 1.0)
    
    # 如果是收入，金额为正；如果是支出，金额为负
    if record_type == 'income':
        ntd_amount = abs(ntd_amount)  # 确保收入为正数
    else:
        ntd_amount = -abs(ntd_amount)  # 确保支出为负数
    
    # 创建新记录，使用台币金额
    new_expense = Expense(
        amount=ntd_amount,
        category=category,
        description=description,
        date=date,
        currency='NTD',  # 始终使用台币存储
        type=record_type  # 设置记录类型
    )
    db.session.add(new_expense)
    db.session.commit()
    
    flash('Record added successfully!')
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
def delete_expense(id):
    expense = Expense.query.get_or_404(id)
    db.session.delete(expense)
    db.session.commit()
    flash('Expense deleted successfully!')
    return redirect(url_for('index'))

@app.route('/categories', methods=['GET'])
def categories():
    # 获取所有分类及其使用次数
    expense_categories = db.session.query(
        Expense.category,
        db.func.count(Expense.id).label('count')
    ).filter(Expense.type == 'expense').group_by(Expense.category).all()
    
    income_categories = db.session.query(
        Expense.category,
        db.func.count(Expense.id).label('count')
    ).filter(Expense.type == 'income').group_by(Expense.category).all()
    
    # 将分类转换为对象，以便在模板中使用
    expense_categories = [{'name': cat[0], 'type': 'expense', 'count': cat[1]} for cat in expense_categories]
    income_categories = [{'name': cat[0], 'type': 'income', 'count': cat[1]} for cat in income_categories]
    
    # 合并分类
    all_categories = expense_categories + income_categories
    
    return render_template('categories.html', categories=all_categories)

@app.route('/add_category', methods=['POST'])
def add_category():
    category = request.form.get('category')
    category_type = request.form.get('type', 'expense')  # 默认为支出分类
    
    if category:
        # 检查分类是否已存在
        existing = db.session.query(Expense).filter_by(category=category, type=category_type).first()
        if not existing:
            # 创建一个新的支出记录来添加分类
            new_expense = Expense(
                date=datetime.now(),
                amount=0,
                currency='NTD',
                category=category,
                description='Category placeholder',
                type=category_type
            )
            db.session.add(new_expense)
            db.session.commit()
            flash('分类添加成功！', 'success')
        else:
            flash('分类已存在！', 'warning')
    return redirect(url_for('categories'))

@app.route('/delete_category', methods=['POST'])
def delete_category():
    category = request.form.get('category')
    category_type = request.form.get('type', 'expense')  # 默认为支出分类
    
    print(f"Attempting to delete category: {category} of type: {category_type}")  # 添加调试信息
    
    if category:
        try:
            # 直接删除分类
            result = db.session.query(Expense).filter_by(category=category, type=category_type).delete()
            print(f"Delete result: {result}")  # 添加调试信息
            db.session.commit()
            flash('Category deleted successfully!', 'success')
        except Exception as e:
            print(f"Error deleting category: {e}")  # 添加调试信息
            db.session.rollback()
            flash('Failed to delete category!', 'danger')
    else:
        flash('No category specified!', 'warning')
    return redirect(url_for('categories'))

def init_default_categories():
    """初始化默认分类"""
    # 检查是否存在任何分类
    existing_categories = db.session.query(Expense.category).distinct().all()
    existing_categories = [cat[0] for cat in existing_categories]
    
    # 默认支出分类列表
    default_expense_categories = ['Food', 'Shopping', 'Housing']
    
    # 默认收入分类列表
    default_income_categories = ['Salary', 'Bursary']
    
    # 添加不存在的默认支出分类
    for category in default_expense_categories:
        if category not in existing_categories:
            new_expense = Expense(
                date=datetime.now(),
                amount=0,
                currency='NTD',
                category=category,
                description='Default category',
                type='expense'
            )
            db.session.add(new_expense)
    
    # 添加不存在的默认收入分类
    for category in default_income_categories:
        if category not in existing_categories:
            new_expense = Expense(
                date=datetime.now(),
                amount=0,
                currency='NTD',
                category=category,
                description='Default category',
                type='income'
            )
            db.session.add(new_expense)
    
    db.session.commit()
    print("Default categories initialized.")

@app.route('/monthly_stats/<int:year>/<int:month>')
def monthly_stats(year, month):
    try:
        # 获取指定月份的所有记录
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
            
        records = Expense.query.filter(
            Expense.date >= start_date,
            Expense.date < end_date
        ).order_by(Expense.date.desc()).all()
        
        # 计算总支出和总收入
        total_expense = sum(record.amount for record in records if record.amount < 0)
        total_income = sum(record.amount for record in records if record.amount > 0)
        
        # 按类别分组统计
        category_stats = {}
        for record in records:
            if record.category not in category_stats:
                category_stats[record.category] = 0
            category_stats[record.category] += record.amount
        
        # 获取当前货币
        currency = session.get('currency', 'NTD')
        currency_symbol = {
            'NTD': 'NT$',
            'MYR': 'RM',
            'USD': '$'
        }.get(currency, 'NT$')
        
        # 获取月份名称
        month_name = start_date.strftime('%B')
        
        return render_template('monthly_stats.html', 
                              records=records, 
                              total_expense=total_expense,
                              total_income=total_income,
                              category_stats=category_stats,
                              currency_symbol=currency_symbol,
                              year=year,
                              month=month,
                              month_name=month_name)
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/yearly_stats/<int:year>')
def yearly_stats(year):
    try:
        # 获取指定年份的所有记录
        start_date = datetime(year, 1, 1)
        end_date = datetime(year + 1, 1, 1)
            
        records = Expense.query.filter(
            Expense.date >= start_date,
            Expense.date < end_date
        ).order_by(Expense.date.desc()).all()
        
        # 计算总支出和总收入
        total_expense = sum(record.amount for record in records if record.amount < 0)
        total_income = sum(record.amount for record in records if record.amount > 0)
        
        # 按月份分组统计
        monthly_stats = {}
        for i in range(1, 13):
            monthly_stats[i] = 0
        
        for record in records:
            month = record.date.month
            monthly_stats[month] += record.amount
        
        # 按类别分组统计
        category_stats = {}
        for record in records:
            if record.category not in category_stats:
                category_stats[record.category] = 0
            category_stats[record.category] += record.amount
        
        # 获取当前货币
        currency = session.get('currency', 'TWD')
        currency_symbol = {
            'NTD': 'NT$',
            'MYR': 'RM',
            'USD': '$'
        }.get(currency, '')
        
        return render_template('yearly_stats.html', 
                              records=records, 
                              total_expense=total_expense,
                              total_income=total_income,
                              monthly_stats=monthly_stats,
                              category_stats=category_stats,
                              currency_symbol=currency_symbol,
                              year=year)
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/delete_record/<int:record_id>', methods=['POST'])
def delete_record(record_id):
    try:
        # 获取记录信息用于重定向
        record = Expense.query.get_or_404(record_id)
        date = record.date
        
        # 删除记录
        db.session.delete(record)
        db.session.commit()
        
        flash('Record deleted successfully!', 'success')
        return redirect(url_for('day_detail', date=date.strftime('%Y-%m-%d')))
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting record: {str(e)}', 'danger')
        return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        init_default_categories()  # 初始化默认分类
    app.run(debug=True, port=5001) 