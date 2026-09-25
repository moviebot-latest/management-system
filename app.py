import os
import secrets
from datetime import datetime, date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, or_
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.environ.get('FLASK_ENV', 'production') == 'production',
    SESSION_COOKIE_SAMESITE='Lax',
    MAX_CONTENT_LENGTH=4 * 1024 * 1024,
)

database_url = os.environ.get('DATABASE_URL', 'sqlite:///library.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
if database_url.startswith(('postgresql://','postgresql+psycopg2://')):
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True, 'pool_recycle': 300, 'pool_timeout': 30,
        'pool_size': 5, 'max_overflow': 5,
        'connect_args': {'connect_timeout': 10, 'sslmode': os.environ.get('PGSSLMODE','require')}
    }

db=SQLAlchemy(app)

class User(db.Model):
    __tablename__='user'
    id=db.Column(db.Integer, primary_key=True)
    employee_id=db.Column(db.String(20), unique=True, nullable=False)
    name=db.Column(db.String(120), nullable=False)
    gender=db.Column(db.String(30), nullable=False, default='Other')
    department=db.Column(db.String(80), nullable=False, default='Library')
    email=db.Column(db.String(160), unique=True, nullable=False)
    username=db.Column(db.String(80), unique=True, nullable=False)
    password_hash=db.Column(db.String(255), nullable=False)
    role=db.Column(db.String(20), nullable=False, default='member')
    created_at=db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

class Book(db.Model):
    __tablename__='book'
    id=db.Column(db.Integer, primary_key=True)
    book_id=db.Column(db.String(20), unique=True, nullable=False)
    title=db.Column(db.String(180), nullable=False)
    author=db.Column(db.String(140), nullable=False)
    isbn=db.Column(db.String(40), unique=True, nullable=True)
    category=db.Column(db.String(80), nullable=False, default='General')
    description=db.Column(db.Text, nullable=True)
    cover_url=db.Column(db.String(600), nullable=True)
    total_copies=db.Column(db.Integer, nullable=False, default=1)
    available_copies=db.Column(db.Integer, nullable=False, default=1)
    created_at=db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

class Loan(db.Model):
    __tablename__='loan'
    id=db.Column(db.Integer, primary_key=True)
    book_id=db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    user_id=db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    issued_at=db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    due_at=db.Column(db.DateTime, nullable=False)
    returned_at=db.Column(db.DateTime, nullable=True)
    book=db.relationship('Book', backref=db.backref('loans', lazy=True))
    user=db.relationship('User', backref=db.backref('loans', lazy=True))


def db_retry(fn):
    try:
        return fn()
    except OperationalError:
        db.session.rollback(); db.engine.dispose(); return fn()


def csrf_token():
    token=session.get('_csrf_token')
    if not token:
        token=secrets.token_urlsafe(32); session['_csrf_token']=token
    return token

@app.context_processor
def inject(): return {'csrf_token': csrf_token()}

@app.before_request
def protect_post():
    if request.method=='POST':
        sent=request.form.get('_csrf_token',''); expected=session.get('_csrf_token','')
        if not expected or not sent or not secrets.compare_digest(sent,expected): return 'Invalid or missing CSRF token.',400

@app.after_request
def security_headers(r):
    r.headers['X-Content-Type-Options']='nosniff'; r.headers['X-Frame-Options']='SAMEORIGIN'
    r.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    r.headers['Cache-Control']='no-store, no-cache, must-revalidate, max-age=0'; r.headers['Pragma']='no-cache'
    r.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
    r.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
    return r

def is_reserved_username(username):
    admin=os.environ.get('ADMIN_USERNAME','admin').strip().casefold()
    return username.strip().casefold() in {admin,'admin'}

def is_logged(): return bool(session.get('user_id'))
def role(): return session.get('role','')
def is_admin(): return role()=='admin'
def is_librarian(): return role() in {'admin','librarian'}
def is_staff(): return role() in {'admin','librarian'}

def login_required(fn):
    @wraps(fn)
    def wrapper(*a,**kw):
        if not is_logged(): return redirect(url_for('index'))
        return fn(*a,**kw)
    return wrapper

def staff_required(fn):
    @wraps(fn)
    def wrapper(*a,**kw):
        if not is_staff():
            flash('Librarian or admin access required.','error'); return redirect(url_for('dashboard'))
        return fn(*a,**kw)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*a,**kw):
        if not is_admin():
            flash('Admin access required.','error'); return redirect(url_for('dashboard'))
        return fn(*a,**kw)
    return wrapper

def next_code(model, field, prefix):
    rows=model.query.order_by(model.id.desc()).limit(1000).all()
    nums=[]
    for x in rows:
        v=getattr(x,field,'') or ''
        try: nums.append(int(v.replace(prefix,'')))
        except: pass
    n=max(nums,default=0)+1
    return f'{prefix}{n:04d}'

def migrate_existing_db():
    # Existing Management System deployments already have a user table.
    # Add only the new role column if it is missing; no existing accounts are deleted.
    try:
        if database_url.startswith(('postgresql://','postgresql+psycopg2://')):
            db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'member'"))
        else:
            cols=[r[1] for r in db.session.execute(text('PRAGMA table_info(user)')).fetchall()]
            if 'role' not in cols: db.session.execute(text("ALTER TABLE user ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'member'"))
        db.session.commit()
    except Exception:
        db.session.rollback()

@app.route('/')
def index():
    return redirect(url_for('dashboard')) if is_logged() else render_template('login.html')

@app.route('/register',methods=['GET','POST'])
def register():
    if request.method=='GET': return render_template('register.html')
    f=request.form
    name=f.get('name','').strip(); gender=f.get('gender','').strip(); email=f.get('email','').strip().lower(); username=f.get('username','').strip()
    password=f.get('password',''); confirm=f.get('confirm','')
    if is_reserved_username(username): flash('This username is reserved. Please choose another username.','error'); return redirect(url_for('register'))
    if not all([name,gender,email,username,password,confirm]): flash('Please fill in all fields.','error'); return redirect(url_for('register'))
    if '@' not in email: flash('Please enter a valid email address.','error'); return redirect(url_for('register'))
    if password!=confirm: flash('Passwords do not match.','error'); return redirect(url_for('register'))
    if len(password)<6: flash('Password must be at least 6 characters.','error'); return redirect(url_for('register'))
    if not (any(c.isalpha() for c in password) and any(c.isdigit() for c in password)):
        flash('Password must contain at least one letter and one number.','error'); return redirect(url_for('register'))
    try:
        if User.query.filter(db.func.lower(User.username)==username.casefold()).first(): flash('Username already exists.','error'); return redirect(url_for('register'))
        if User.query.filter(db.func.lower(User.email)==email.casefold()).first(): flash('Email already exists.','error'); return redirect(url_for('register'))
        u=User(employee_id=next_code(User,'employee_id','MEM'),name=name,gender=gender,department='Library',email=email,username=username,password_hash=generate_password_hash(password),role='member')
        db.session.add(u); db.session.commit()
    except (IntegrityError,OperationalError):
        db.session.rollback(); db.engine.dispose(); flash('Account could not be created. Please try again.','error'); return redirect(url_for('register'))
    flash('Library member account created successfully. Please login.','success'); return redirect(url_for('index'))

@app.post('/login')
def login():
    username=request.form.get('username','').strip(); password=request.form.get('password','')
    au=os.environ.get('ADMIN_USERNAME','admin'); ap=os.environ.get('ADMIN_PASSWORD','')
    if au and ap and username.casefold()==au.casefold() and secrets.compare_digest(password,ap):
        session.clear(); session.update(user_id='admin',role='admin',username=au,name=os.environ.get('ADMIN_NAME','Admin')); return redirect(url_for('dashboard'))
    try: u=db_retry(lambda: User.query.filter(db.func.lower(User.username)==username.casefold()).first())
    except OperationalError: flash('Database connection was temporarily unavailable.','error'); return redirect(url_for('index'))
    if u and check_password_hash(u.password_hash,password):
        session.clear(); session.update(user_id=u.id,role=u.role or 'member',username=u.username,name=u.name); return redirect(url_for('dashboard'))
    flash('Invalid username or password.','error'); return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('index'),303)

@app.route('/dashboard')
@login_required
def dashboard():
    try:
        books=db_retry(lambda: Book.query.order_by(Book.id.desc()).all())
        members=db_retry(lambda: User.query.filter(User.role.in_(['member','librarian'])).order_by(User.id.desc()).all()) if is_staff() else []
        active_loans=db_retry(lambda: Loan.query.filter_by(user_id=session.get('user_id')).filter(Loan.returned_at.is_(None)).order_by(Loan.due_at.asc()).all()) if not is_staff() else []
        overdue=db_retry(lambda: Loan.query.filter(Loan.returned_at.is_(None),Loan.due_at < datetime.utcnow()).count()) if is_staff() else sum(1 for x in active_loans if x.due_at < datetime.utcnow())
        total_copies=sum(b.total_copies for b in books); available=sum(b.available_copies for b in books)
        all_loans=db_retry(lambda: Loan.query.filter(Loan.returned_at.is_(None)).count())
    except OperationalError:
        db.session.rollback(); flash('Database connection was temporarily unavailable.','error'); return redirect(url_for('index'))
    return render_template('dashboard.html',books=books,members=members,role=role(),current_name=session.get('name','User'),current_username=session.get('username',''),total_books=len(books),total_copies=total_copies,available_copies=available,issued=all_loans,overdue=overdue,active_loans=active_loans,now=datetime.utcnow())

@app.post('/books/create')
@staff_required
def create_book():
    f=request.form; title=f.get('title','').strip(); author=f.get('author','').strip(); isbn=f.get('isbn','').strip() or None; category=f.get('category','General').strip(); desc=f.get('description','').strip(); cover=f.get('cover_url','').strip() or None
    try: copies=max(1,int(f.get('copies','1')))
    except: copies=1
    if not title or not author: flash('Title and author are required.','error'); return redirect(url_for('dashboard'))
    if isbn and Book.query.filter_by(isbn=isbn).first(): flash('ISBN already exists.','error'); return redirect(url_for('dashboard'))
    try:
        b=Book(book_id=next_code(Book,'book_id','BK'),title=title,author=author,isbn=isbn,category=category or 'General',description=desc,cover_url=cover,total_copies=copies,available_copies=copies); db.session.add(b); db.session.commit(); flash('Book added successfully.','success')
    except (IntegrityError,OperationalError): db.session.rollback(); db.engine.dispose(); flash('Book could not be added.','error')
    return redirect(url_for('dashboard'))

@app.post('/books/<int:book_id>/edit')
@staff_required
def edit_book(book_id):
    b=db.get_or_404(Book,book_id); f=request.form; title=f.get('title','').strip(); author=f.get('author','').strip(); isbn=f.get('isbn','').strip() or None
    try: new_total=max(1,int(f.get('copies','1')))
    except: new_total=b.total_copies
    if isbn and Book.query.filter(Book.isbn==isbn,Book.id!=book_id).first(): flash('ISBN already exists.','error'); return redirect(url_for('dashboard'))
    issued=b.total_copies-b.available_copies; b.title=title or b.title; b.author=author or b.author; b.isbn=isbn; b.category=f.get('category','General').strip() or 'General'; b.description=f.get('description','').strip(); b.cover_url=f.get('cover_url','').strip() or None
    if new_total<issued: flash(f'Copies cannot be less than currently issued copies ({issued}).','error'); return redirect(url_for('dashboard'))
    b.total_copies=new_total; b.available_copies=new_total-issued
    db.session.commit(); flash('Book updated successfully.','success'); return redirect(url_for('dashboard'))

@app.post('/books/<int:book_id>/delete')
@staff_required
def delete_book(book_id):
    b=db.get_or_404(Book,book_id)
    if Loan.query.filter_by(book_id=book_id).first(): flash('This book has issue history and cannot be deleted.','error'); return redirect(url_for('dashboard'))
    db.session.delete(b); db.session.commit(); flash('Book deleted.','success'); return redirect(url_for('dashboard'))

@app.post('/books/<int:book_id>/issue')
@login_required
def issue_book(book_id):
    if is_admin() or is_librarian():
        username=request.form.get('username','').strip(); u=User.query.filter_by(username=username).first() if username else None
        if not u: flash('Select a valid member username.','error'); return redirect(url_for('dashboard'))
    else: u=User.query.get(session['user_id'])
    b=Book.query.get_or_404(book_id)
    if b.available_copies<=0: flash('No available copy for this book.','error'); return redirect(url_for('dashboard'))
    existing=Loan.query.filter_by(book_id=b.id,user_id=u.id,returned_at=None).first()
    if existing: flash('This member already has an active copy of this book.','error'); return redirect(url_for('dashboard'))
    active=Loan.query.filter_by(user_id=u.id,returned_at=None).count()
    if active>=5 and not is_staff(): flash('Maximum 5 active books allowed.','error'); return redirect(url_for('dashboard'))
    l=Loan(book_id=b.id,user_id=u.id,due_at=datetime.utcnow().replace(microsecond=0)); from datetime import timedelta; l.due_at += timedelta(days=14)
    b.available_copies-=1; db.session.add(l); db.session.commit(); flash(f'Book issued to {u.name}.','success'); return redirect(url_for('dashboard'))

@app.post('/loans/<int:loan_id>/return')
@login_required
def return_book(loan_id):
    l=Loan.query.get_or_404(loan_id)
    if not is_staff() and l.user_id!=session.get('user_id'): flash('You can only return your own book.','error'); return redirect(url_for('dashboard'))
    if not l.returned_at:
        l.returned_at=datetime.utcnow(); l.book.available_copies=min(l.book.total_copies,l.book.available_copies+1); db.session.commit(); flash('Book returned successfully.','success')
    return redirect(url_for('dashboard'))

@app.post('/admin/members/<int:user_id>/role')
@admin_required
def change_role(user_id):
    u=User.query.get_or_404(user_id); new_role=request.form.get('role','member')
    if new_role not in {'member','librarian'}: new_role='member'
    u.role=new_role; db.session.commit(); flash(f'{u.name} is now {new_role}.','success'); return redirect(url_for('dashboard'))

@app.post('/admin/members/<int:user_id>/delete')
@admin_required
def delete_member(user_id):
    u=User.query.get_or_404(user_id)
    if Loan.query.filter_by(user_id=user_id,returned_at=None).first(): flash('Member has active issued books. Return them before deleting.','error'); return redirect(url_for('dashboard'))
    Loan.query.filter_by(user_id=user_id).delete(synchronize_session=False); db.session.delete(u); db.session.commit(); flash('Member removed.','success'); return redirect(url_for('dashboard'))

@app.route('/change-password',methods=['GET','POST'])
@login_required
def change_password():
    if request.method=='GET': return render_template('change_password.html')
    old=request.form.get('current_password',''); new=request.form.get('new_password',''); confirm=request.form.get('confirm_password','')
    if not all([old,new,confirm]): flash('Please fill in all fields.','error'); return redirect(url_for('change_password'))
    if new!=confirm: flash('New passwords do not match.','error'); return redirect(url_for('change_password'))
    if len(new)<6 or not any(c.isalpha() for c in new) or not any(c.isdigit() for c in new): flash('New password must be at least 6 characters and contain a letter and number.','error'); return redirect(url_for('change_password'))
    if is_admin(): flash('Admin password is managed in Render Environment Variables.','error'); return redirect(url_for('change_password'))
    u=User.query.get_or_404(session['user_id'])
    if not check_password_hash(u.password_hash,old): flash('Current password is incorrect.','error'); return redirect(url_for('change_password'))
    u.password_hash=generate_password_hash(new); db.session.commit(); session.clear(); flash('Password changed successfully. Please login again.','success'); return redirect(url_for('index'))

@app.get('/auth-status')
def auth_status(): return {'authenticated':is_logged()}

with app.app_context():
    db.create_all(); migrate_existing_db()
    # Seed a small demo collection only when there are no books at all.
    if Book.query.count()==0:
        db.session.add_all([
            Book(book_id='BK0001',title='Python Programming',author='Library Collection',isbn=None,category='Programming',description='A starter programming book.',cover_url=None,total_copies=5,available_copies=5),
            Book(book_id='BK0002',title='Database Systems',author='Library Collection',isbn=None,category='Database',description='Database concepts and SQL.',cover_url=None,total_copies=3,available_copies=3)
        ]); db.session.commit()

if __name__=='__main__': app.run(debug=True)
