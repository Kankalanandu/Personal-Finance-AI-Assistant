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

# Database Models
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
    earned_date = db.Column(db.Date, default=datetime.utcnow)

# Create tables globally for cloud deployment
with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists!')
            return redirect(url_for('register'))
        
        password_hash = generate_password_hash(password)
        new_user = User(name=name, email=email, password_hash=password_hash)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful!')
        return redirect(url_for('login_form'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login_form():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password!')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    transactions = Transaction.query.filter_by(user_id=current_user.id).all()
    budgets = Budget.query.filter_by(user_id=current_user.id).all()
    goals = Goal.query.filter_by(user_id=current_user.id).all()
    
    # Calculate totals
    total_income = sum(t.amount for t in transactions if t.transaction_type == 'income')
    total_expenses = sum(t.amount for t in transactions if t.transaction_type == 'expense')
    balance = total_income - total_expenses
    
    return render_template('dashboard.html', 
                         transactions=transactions[:5],  # Show last 5 transactions
                         budgets=budgets,
                         goals=goals,
                         balance=balance,
                         total_income=total_income,
                         total_expenses=total_expenses)

@app.route('/add_transaction', methods=['GET', 'POST'])
@login_required
def add_transaction():
    if request.method == 'POST':
        amount = float(request.form['amount'])
        category = request.form['category']
        description = request.form['description']
        transaction_type = request.form['type']
        
        new_transaction = Transaction(
            user_id=current_user.id,
            amount=amount,
            category=category,
            description=description,
            transaction_type=transaction_type
        )
        
        db.session.add(new_transaction)
        db.session.commit()
        
        # Check for achievements
        check_achievements(current_user.id)
        
        flash('Transaction added successfully!')
        return redirect(url_for('dashboard'))
    
    return render_template('add_transaction.html')

@app.route('/transactions')
@login_required
def transactions():
    user_transactions = Transaction.query.filter_by(user_id=current_user.id).all()
    return render_template('transactions.html', transactions=user_transactions)

@app.route('/set_budget', methods=['GET', 'POST'])
@login_required
def set_budget():
    if request.method == 'POST':
        category = request.form['category']
        limit = float(request.form['limit'])
        
        # Check if budget for this category already exists
        existing_budget = Budget.query.filter_by(user_id=current_user.id, category=category).first()
        if existing_budget:
            existing_budget.limit = limit
        else:
            new_budget = Budget(user_id=current_user.id, category=category, limit=limit)
            db.session.add(new_budget)
        
        db.session.commit()
        flash('Budget updated successfully!')
        return redirect(url_for('budgets'))
    
    return render_template('set_budget.html')

@app.route('/budgets')
@login_required
def budgets():
    user_budgets = Budget.query.filter_by(user_id=current_user.id).all()
    
    # Calculate spending for each budget
    budget_data = []
    for budget in user_budgets:
        spent = sum(t.amount for t in Transaction.query.filter_by(
            user_id=current_user.id, 
            category=budget.category, 
            transaction_type='expense'
        ).all())
        
        budget_data.append({
            'budget': budget,
            'spent': spent,
            'remaining': budget.limit - spent,
            'percentage': (spent / budget.limit * 100) if budget.limit > 0 else 0
        })
    
    return render_template('budgets.html', budget_data=budget_data)

@app.route('/set_goal', methods=['GET', 'POST'])
@login_required
def set_goal():
    if request.method == 'POST':
        name = request.form['name']
        target_amount = float(request.form['target_amount'])
        deadline = datetime.strptime(request.form['deadline'], '%Y-%m-%d').date()
        
        new_goal = Goal(user_id=current_user.id, name=name, target_amount=target_amount, deadline=deadline)
        db.session.add(new_goal)
        db.session.commit()
        
        flash('Goal set successfully!')
        return redirect(url_for('goals'))
    
    return render_template('set_goal.html')

@app.route('/goals')
@login_required
def goals():
    user_goals = Goal.query.filter_by(user_id=current_user.id).all()
    return render_template('goals.html', goals=user_goals)

@app.route('/achievements')
@login_required
def achievements():
    user_badges = Badge.query.filter_by(user_id=current_user.id).all()
    return render_template('achievements.html', badges=user_badges)

def check_achievements(user_id):
    user = User.query.get(user_id)
    transactions = Transaction.query.filter_by(user_id=user_id).all()
    
    # First transaction badge
    if len(transactions) == 1 and not Badge.query.filter_by(user_id=user_id, name='First Step').first():
        badge = Badge(user_id=user_id, name='First Step', description='Added your first transaction')
        db.session.add(badge)
    
    # 10 transactions badge
    if len(transactions) >= 10 and not Badge.query.filter_by(user_id=user_id, name='Getting Started').first():
        badge = Badge(user_id=user_id, name='Getting Started', description='Added 10 transactions')
        db.session.add(badge)
    
    # Budget setter badge
    budgets = Budget.query.filter_by(user_id=user_id).all()
    if len(budgets) >= 1 and not Badge.query.filter_by(user_id=user_id, name='Budget Planner').first():
        badge = Badge(user_id=user_id, name='Budget Planner', description='Set your first budget')
        db.session.add(badge)
    
    db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
