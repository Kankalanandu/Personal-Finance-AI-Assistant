from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import datetime
import os
import random

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///finance.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
CORS(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login_form'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(256), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(128), nullable=False)
    description = db.Column(db.String(256))
    transaction_type = db.Column(db.String(16), nullable=False)
    date = db.Column(db.Date, default=datetime.utcnow)

class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    category = db.Column(db.String(128), nullable=False)
    limit = db.Column(db.Float, nullable=False)

class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    name = db.Column(db.String(128), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    deadline = db.Column(db.Date, nullable=False)

class Badge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.String(256))
    achieved_on = db.Column(db.Date, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/register_form', methods=['GET', 'POST'])
def register_form():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return render_template('register.html')
        user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        flash('Registered successfully!')
        return redirect('/login_form')
    return render_template('register.html')

@app.route('/login_form', methods=['GET', 'POST'])
def login_form():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect('/dashboard')
        flash('Invalid credentials')
        return render_template('login.html')
    return render_template('login.html')

@app.route('/logout', methods=['GET'])
@login_required
def logout():
    logout_user()
    flash("Successfully logged out!")
    return redirect('/login_form')

@app.route('/')
def index():
    return redirect('/dashboard')

def get_smart_tips(user_id):
    expenses = db.session.query(db.func.sum(Transaction.amount)).filter_by(user_id=user_id, transaction_type='expense').scalar() or 0
    income = db.session.query(db.func.sum(Transaction.amount)).filter_by(user_id=user_id, transaction_type='income').scalar() or 0
    budgets = Budget.query.filter_by(user_id=user_id).all()
    tips = []
    for b in budgets:
        spent = db.session.query(db.func.sum(Transaction.amount)).filter_by(user_id=user_id, transaction_type='expense', category=b.category).scalar() or 0
        if spent > b.limit:
            tips.append(f"Exceeded '{b.category}' budget by ₹{int(spent-b.limit)}.")
        elif spent > 0.85 * b.limit:
            tips.append(f"Close to '{b.category}' budget limit! Caution advised.")
    if income > 0 and expenses/income < 0.5:
        tips.append("Saving over 50% of income—great job!")
    elif income > 0 and expenses/income > 0.85:
        tips.append("Spending more than 85% of income. Time to reduce expenses.")
    advice_list = [
        "Automate your savings for consistency.",
        "Review subscriptions and cancel unused ones.",
        "Track small expenses—they add up fast.",
        "Set clear savings goals for the next quarter.",
        "Build an emergency fund for unplanned costs."
    ]
    tips.append(random.choice(advice_list))
    return tips

@app.route('/dashboard')
@login_required
def dashboard():
    expenses = db.session.query(db.func.sum(Transaction.amount)).filter_by(
        user_id=current_user.id, transaction_type='expense').scalar() or 0
    income = db.session.query(db.func.sum(Transaction.amount)).filter_by(
        user_id=current_user.id, transaction_type='income').scalar() or 0
    balance = income - expenses
    budgets = Budget.query.filter_by(user_id=current_user.id).all()
    category_data = db.session.query(Transaction.category, db.func.sum(Transaction.amount)).filter_by(
        user_id=current_user.id, transaction_type='expense').group_by(Transaction.category).all()
    categories = [cd[0] for cd in category_data]
    amounts = [float(cd[1]) for cd in category_data]
    smart_tips = get_smart_tips(current_user.id)
    return render_template(
        'dashboard.html',
        income=income, expenses=expenses,
        balance=balance, budgets=budgets,
        categories=categories, amounts=amounts,
        smart_tips=smart_tips
    )

@app.route('/add_budget_form', methods=['GET', 'POST'])
@login_required
def add_budget_form():
    if request.method == 'POST':
        category = request.form['category']
        limit = float(request.form['limit'])
        b = Budget(user_id=current_user.id, category=category, limit=limit)
        db.session.add(b)
        db.session.commit()
        return redirect('/add_budget_form')
    budgets = Budget.query.filter_by(user_id=current_user.id).all()
    return render_template('budget.html', budgets=budgets)

@app.route('/goals', methods=['GET', 'POST'])
@login_required
def manage_goals():
    if request.method == 'POST':
        name = request.form['name']
        target_amount = float(request.form['target_amount'])
        deadline = datetime.strptime(request.form['deadline'], "%Y-%m-%d").date()
        goal = Goal(user_id=current_user.id, name=name, target_amount=target_amount, deadline=deadline)
        db.session.add(goal)
        db.session.commit()
        return redirect('/goals')
    goals = Goal.query.filter_by(user_id=current_user.id).all()
    this_year = datetime.now().year
    yearly_income = db.session.query(db.func.sum(Transaction.amount)).filter(
        Transaction.user_id == current_user.id,
        Transaction.transaction_type == 'income',
        db.extract('year', Transaction.date) == this_year
    ).scalar() or 0
    yearly_expenses = db.session.query(db.func.sum(Transaction.amount)).filter(
        Transaction.user_id == current_user.id,
        Transaction.transaction_type == 'expense',
        db.extract('year', Transaction.date) == this_year
    ).scalar() or 0
    savings = yearly_income - yearly_expenses
    for goal in goals:
        goal.progress = min(100, int((savings / goal.target_amount) * 100))
    return render_template('goals.html', goals=goals)

def assign_badges(user_id):
    total_savings = (db.session.query(db.func.sum(Transaction.amount)).filter_by(
        user_id=user_id, transaction_type='income').scalar() or 0) - \
        (db.session.query(db.func.sum(Transaction.amount)).filter_by(
        user_id=user_id, transaction_type='expense').scalar() or 0)
    if total_savings > 100000 and not Badge.query.filter_by(user_id=user_id, name='Savings Superstar').first():
        badge = Badge(user_id=user_id, name="Savings Superstar",
            description="Saved over ₹100,000!", achieved_on=datetime.utcnow())
        db.session.add(badge)
        db.session.commit()

@app.route('/badges')
@login_required
def show_badges():
    assign_badges(current_user.id)
    badges = Badge.query.filter_by(user_id=current_user.id).all()
    return render_template('badges.html', badges=badges)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
