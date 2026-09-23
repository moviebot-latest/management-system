
import os
import secrets
from datetime import date, datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, inspect
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
if not app.config["SECRET_KEY"]:
    raise RuntimeError("SECRET_KEY environment variable is required in production.")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)

database_url = os.environ.get("DATABASE_URL", "sqlite:///library.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

if database_url.startswith(("postgresql://", "postgresql+psycopg2://")):
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_timeout": 30,
        "pool_size": 5,
        "max_overflow": 5,
        "connect_args": {
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
            "sslmode": os.environ.get("PGSSLMODE", "require"),
        },
    }

db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    gender = db.Column(db.String(30), nullable=False)
    # Kept nullable only for compatibility with an older database schema.
    # New Library accounts do not collect or use department.
    department = db.Column(db.String(80), nullable=True)
    email = db.Column(db.String(160), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="member", server_default="member")
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)


class Book(db.Model):
    __tablename__ = "book"
    id = db.Column(db.Integer, primary_key=True)
    book_code = db.Column(db.String(30), unique=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(160), nullable=False)
    isbn = db.Column(db.String(40), unique=True, nullable=True)
    category = db.Column(db.String(100), nullable=False)
    total_copies = db.Column(db.Integer, nullable=False, default=1)
    available_copies = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)


class Issue(db.Model):
    __tablename__ = "issue"
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey("book.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    issue_date = db.Column(db.Date, nullable=False, default=date.today)
    due_date = db.Column(db.Date, nullable=False)
    return_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="issued")
    fine = db.Column(db.Integer, nullable=False, default=0)

    book = db.relationship("Book", backref=db.backref("issues", lazy=True))
    user = db.relationship("User", backref=db.backref("issues", lazy=True))


def db_retry(fn):
    try:
        return fn()
    except OperationalError:
        db.session.rollback()
        db.engine.dispose()
        return fn()


def is_admin():
    return session.get("role") == "admin"


def is_librarian():
    return session.get("role") in ("admin", "librarian")


def current_name():
    if is_admin():
        return os.environ.get("ADMIN_NAME", "Admin")
    user = User.query.get(session.get("user_id")) if session.get("user_id") else None
    return user.name if user else "User"


def is_reserved_username(username):
    admin_username = os.environ.get("ADMIN_USERNAME", "admin").strip()
    return username.strip().casefold() == admin_username.casefold() or username.strip().casefold() == "admin"


def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token()}


@app.before_request
def protect_post_requests():
    if request.method == "POST":
        sent = request.form.get("_csrf_token", "")
        expected = session.get("_csrf_token", "")
        if not expected or not sent or not secrets.compare_digest(sent, expected):
            return "Invalid or missing CSRF token.", 400


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "font-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; "
        "base-uri 'self'; form-action 'self'"
    )
    return response


def next_user_id():
    def query():
        n = User.query.count() + 1
        while User.query.filter_by(employee_id=f"LIB{n:03d}").first():
            n += 1
        return f"LIB{n:03d}"
    return db_retry(query)


def next_book_code():
    def query():
        n = Book.query.count() + 1
        while Book.query.filter_by(book_code=f"BK{n:04d}").first():
            n += 1
        return f"BK{n:04d}"
    return db_retry(query)


def dashboard_stats():
    def query():
        total_books = Book.query.count()
        total_copies = db.session.query(db.func.coalesce(db.func.sum(Book.total_copies), 0)).scalar() or 0
        available = db.session.query(db.func.coalesce(db.func.sum(Book.available_copies), 0)).scalar() or 0
        issued = total_copies - available
        members = User.query.filter(User.role == "member").count()
        librarians = User.query.filter(User.role == "librarian").count()
        active_issues = Issue.query.filter_by(status="issued").count()
        overdue = Issue.query.filter(Issue.status == "issued", Issue.due_date < date.today()).count()
        return {
            "total_books": total_books, "total_copies": total_copies,
            "available": available, "issued": issued, "members": members,
            "librarians": librarians, "active_issues": active_issues, "overdue": overdue
        }
    return db_retry(query)


def migrate_old_schema():
    """Add the role column to an older Employee Management database without deleting data."""
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    if "user" in tables:
        columns = {c["name"] for c in inspector.get_columns("user")}
        if "role" not in columns:
            db.session.execute(text(
                "ALTER TABLE \"user\" ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'member'"
            ))
            db.session.commit()


@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    f = request.form
    name = f.get("name", "").strip()
    gender = f.get("gender", "").strip()
    email = f.get("email", "").strip().lower()
    username = f.get("username", "").strip()
    password = f.get("password", "")
    confirm = f.get("confirm", "")

    if is_reserved_username(username):
        flash("This username is restricted by admin.", "error")
        return redirect(url_for("register"))
    if not all([name, gender, email, username, password, confirm]):
        flash("Please fill in all fields.", "error")
        return redirect(url_for("register"))
    if password != confirm:
        flash("Passwords do not match.", "error")
        return redirect(url_for("register"))
    if len(password) < 6:
        flash("Password must be at least 6 characters.", "error")
        return redirect(url_for("register"))

    try:
        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "error")
            return redirect(url_for("register"))
        if User.query.filter_by(email=email).first():
            flash("Email already exists.", "error")
            return redirect(url_for("register"))
        user = User(
            employee_id=next_user_id(), name=name, gender=gender,
            email=email, username=username,
            password_hash=generate_password_hash(password), role="member"
        )
        db.session.add(user)
        db.session.commit()
    except (IntegrityError, OperationalError):
        db.session.rollback()
        db.engine.dispose()
        flash("Registration could not be completed. Please try again.", "error")
        return redirect(url_for("register"))

    flash("Library member account created successfully. Please login.", "success")
    return redirect(url_for("index"))


@app.post("/login")
def login():
    f = request.form
    username = f.get("username", "").strip()
    password = f.get("password", "")
    admin_username = os.environ.get("ADMIN_USERNAME")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if admin_username and admin_password and username == admin_username and password == admin_password:
        session.clear()
        session["user_id"] = "admin"
        session["role"] = "admin"
        session["username"] = admin_username
        session["name"] = os.environ.get("ADMIN_NAME", "Admin")
        return redirect(url_for("dashboard"))

    try:
        user = db_retry(lambda: User.query.filter_by(username=username).first())
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session["user_id"] = user.id
            session["role"] = user.role or "member"
            session["username"] = user.username
            session["name"] = user.name
            return redirect(url_for("dashboard"))
    except OperationalError:
        db.session.rollback()
        flash("Database connection was temporarily unavailable. Please try again.", "error")
        return redirect(url_for("index"))

    flash("Invalid username or password.", "error")
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    response = redirect(url_for("index"), code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.get("/auth-status")
def auth_status():
    response = make_response({"authenticated": bool(session.get("user_id"))})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.route("/dashboard")
def dashboard():
    if not session.get("user_id"):
        return redirect(url_for("index"))

    try:
        stats = dashboard_stats()
        books = db_retry(lambda: Book.query.order_by(Book.id.desc()).all())
        if is_admin():
            users = db_retry(lambda: User.query.order_by(User.id.desc()).all())
        else:
            users = []
        if session.get("user_id") == "admin":
            my_issues = []
        else:
            my_issues = db_retry(lambda: Issue.query.filter_by(user_id=session["user_id"]).order_by(Issue.id.desc()).all())
        recent_issues = db_retry(lambda: Issue.query.order_by(Issue.id.desc()).limit(50).all()) if is_librarian() else []
    except OperationalError:
        db.session.rollback()
        db.engine.dispose()
        flash("Database connection was temporarily unavailable. Please refresh and try again.", "error")
        return redirect(url_for("index"))

    return render_template(
        "dashboard.html", role=session.get("role"),
        current_name=session.get("name") or current_name(),
        current_username=session.get("username", ""),
        books=books, users=users, stats=stats,
        my_issues=my_issues, recent_issues=recent_issues,
        today=date.today()
    )


@app.post("/admin/users/create")
def create_user():
    if not is_admin():
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    f = request.form
    name, gender = f.get("name","").strip(), f.get("gender","").strip()
    email, username = f.get("email","").strip().lower(), f.get("username","").strip()
    password, confirm = f.get("password",""), f.get("confirm","")
    role = f.get("role","member").strip().lower()
    if role not in ("member", "librarian"):
        role = "member"
    if not all([name, gender, email, username, password, confirm]):
        flash("Please fill in all fields.", "error"); return redirect(url_for("dashboard"))
    if is_reserved_username(username):
        flash("This username is restricted by admin.", "error"); return redirect(url_for("dashboard"))
    if password != confirm:
        flash("Passwords do not match.", "error"); return redirect(url_for("dashboard"))
    if len(password) < 6:
        flash("Password must be at least 6 characters.", "error"); return redirect(url_for("dashboard"))
    try:
        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "error"); return redirect(url_for("dashboard"))
        if User.query.filter_by(email=email).first():
            flash("Email already exists.", "error"); return redirect(url_for("dashboard"))
        user = User(employee_id=next_user_id(), name=name, gender=gender, email=email,
                    username=username, password_hash=generate_password_hash(password), role=role)
        db.session.add(user); db.session.commit()
    except (IntegrityError, OperationalError):
        db.session.rollback(); db.engine.dispose()
        flash("User could not be created. Please try again.", "error"); return redirect(url_for("dashboard"))
    flash("Library user created successfully.", "success")
    return redirect(url_for("dashboard"))


@app.post("/admin/users/<int:user_id>/edit")
def edit_user(user_id):
    if not is_admin():
        flash("Admin access required.", "error"); return redirect(url_for("index"))
    try:
        user = db_retry(lambda: db.get_or_404(User, user_id))
        f = request.form
        name, gender = f.get("name","").strip(), f.get("gender","").strip()
        email, username = f.get("email","").strip().lower(), f.get("username","").strip()
        password, confirm = f.get("password",""), f.get("confirm","")
        if not all([name, gender, email, username]):
            flash("Please fill in all user fields.", "error"); return redirect(url_for("dashboard"))
        if is_reserved_username(username):
            flash("This username is restricted by admin.", "error"); return redirect(url_for("dashboard"))
        if User.query.filter(User.username == username, User.id != user_id).first():
            flash("Username already exists.", "error"); return redirect(url_for("dashboard"))
        if User.query.filter(User.email == email, User.id != user_id).first():
            flash("Email already exists.", "error"); return redirect(url_for("dashboard"))
        if password:
            if len(password) < 6 or password != confirm:
                flash("New password is invalid or passwords do not match.", "error"); return redirect(url_for("dashboard"))
            user.password_hash = generate_password_hash(password)
        user.name, user.gender, user.email, user.username = name, gender, email, username
        db.session.commit()
    except (IntegrityError, OperationalError):
        db.session.rollback(); db.engine.dispose()
        flash("User update could not be completed.", "error"); return redirect(url_for("dashboard"))
    flash("User updated successfully.", "success")
    return redirect(url_for("dashboard"))


@app.post("/admin/users/<int:user_id>/role")
def change_role(user_id):
    if not is_admin():
        flash("Admin access required.", "error"); return redirect(url_for("index"))
    new_role = request.form.get("role","member").lower()
    if new_role not in ("member","librarian"):
        flash("Invalid role.", "error"); return redirect(url_for("dashboard"))
    try:
        user = db_retry(lambda: db.get_or_404(User, user_id))
        user.role = new_role
        db.session.commit()
    except OperationalError:
        db.session.rollback(); db.engine.dispose()
        flash("Role update failed. Please try again.", "error"); return redirect(url_for("dashboard"))
    flash(("User promoted to Librarian." if new_role == "librarian" else "Librarian demoted to Member."), "success")
    return redirect(url_for("dashboard"))


@app.post("/admin/users/<int:user_id>/delete")
def delete_user(user_id):
    if not is_admin():
        flash("Admin access required.", "error"); return redirect(url_for("index"))
    try:
        user = db_retry(lambda: db.get_or_404(User, user_id))
        if Issue.query.filter_by(user_id=user.id, status="issued").first():
            flash("This member has an active issued book. Return it before deleting the account.", "error")
            return redirect(url_for("dashboard"))
        db.session.delete(user); db.session.commit()
    except OperationalError:
        db.session.rollback(); db.engine.dispose()
        flash("Delete failed because the database connection was unavailable.", "error"); return redirect(url_for("dashboard"))
    flash("User deleted successfully.", "success")
    return redirect(url_for("dashboard"))


@app.post("/admin/books/create")
def create_book():
    if not is_librarian():
        flash("Librarian or Admin access required.", "error"); return redirect(url_for("index"))
    f=request.form
    title, author = f.get("title","").strip(), f.get("author","").strip()
    isbn, category = f.get("isbn","").strip(), f.get("category","").strip()
    try: copies=int(f.get("copies","1"))
    except ValueError: copies=0
    if not title or not author or not category or copies < 1:
        flash("Enter valid book details and at least 1 copy.", "error"); return redirect(url_for("dashboard"))
    try:
        if isbn and Book.query.filter_by(isbn=isbn).first():
            flash("ISBN already exists.", "error"); return redirect(url_for("dashboard"))
        b=Book(book_code=next_book_code(), title=title, author=author, isbn=isbn or None,
               category=category, total_copies=copies, available_copies=copies)
        db.session.add(b); db.session.commit()
    except (IntegrityError, OperationalError):
        db.session.rollback(); db.engine.dispose()
        flash("Book could not be added.", "error"); return redirect(url_for("dashboard"))
    flash("Book added successfully.", "success"); return redirect(url_for("dashboard"))


@app.post("/librarian/books/<int:book_id>/edit")
def edit_book(book_id):
    if not is_librarian(): flash("Librarian or Admin access required.", "error"); return redirect(url_for("index"))
    try:
        b=db_retry(lambda: db.get_or_404(Book, book_id)); f=request.form
        title, author = f.get("title","").strip(), f.get("author","").strip()
        isbn, category = f.get("isbn","").strip(), f.get("category","").strip()
        try: new_total=int(f.get("copies","1"))
        except ValueError: new_total=0
        active_issued=b.total_copies-b.available_copies
        if not title or not author or not category or new_total < active_issued:
            flash(f"Copies cannot be less than currently issued copies ({active_issued}).", "error"); return redirect(url_for("dashboard"))
        if isbn and Book.query.filter(Book.isbn==isbn, Book.id!=book_id).first():
            flash("ISBN already exists.", "error"); return redirect(url_for("dashboard"))
        b.title,b.author,b.isbn,b.category=title,author,isbn or None,category
        b.total_copies=new_total; b.available_copies=new_total-active_issued
        db.session.commit()
    except (IntegrityError, OperationalError):
        db.session.rollback(); db.engine.dispose()
        flash("Book update could not be completed.", "error"); return redirect(url_for("dashboard"))
    flash("Book updated successfully.", "success"); return redirect(url_for("dashboard"))


@app.post("/librarian/books/<int:book_id>/delete")
def delete_book(book_id):
    if not is_librarian(): flash("Librarian or Admin access required.", "error"); return redirect(url_for("index"))
    try:
        b=db_retry(lambda: db.get_or_404(Book, book_id))
        if Issue.query.filter_by(book_id=book_id, status="issued").first():
            flash("Cannot delete a book while copies are issued.", "error"); return redirect(url_for("dashboard"))
        db.session.delete(b); db.session.commit()
    except OperationalError:
        db.session.rollback(); db.engine.dispose()
        flash("Book deletion failed.", "error"); return redirect(url_for("dashboard"))
    flash("Book deleted successfully.", "success"); return redirect(url_for("dashboard"))


@app.post("/librarian/issue")
def issue_book():
    if not is_librarian(): flash("Librarian or Admin access required.", "error"); return redirect(url_for("index"))
    try:
        book_id=int(request.form.get("book_id","0")); user_id=int(request.form.get("user_id","0"))
        days=int(request.form.get("days","14"))
    except ValueError:
        flash("Invalid issue details.", "error"); return redirect(url_for("dashboard"))
    if days < 1 or days > 90:
        flash("Due period must be between 1 and 90 days.", "error"); return redirect(url_for("dashboard"))
    try:
        book=db_retry(lambda: db.get_or_404(Book, book_id))
        user=db_retry(lambda: db.get_or_404(User, user_id))
        if user.role not in ("member","librarian"):
            flash("Invalid library member.", "error"); return redirect(url_for("dashboard"))
        if book.available_copies < 1:
            flash("No available copy of this book.", "error"); return redirect(url_for("dashboard"))
        if Issue.query.filter_by(book_id=book.id,user_id=user.id,status="issued").first():
            flash("This user already has an active issue for this book.", "error"); return redirect(url_for("dashboard"))
        issue=Issue(book_id=book.id,user_id=user.id,issue_date=date.today(),
                    due_date=date.today()+timedelta(days=days),status="issued",fine=0)
        book.available_copies-=1; db.session.add(issue); db.session.commit()
    except (IntegrityError, OperationalError):
        db.session.rollback(); db.engine.dispose()
        flash("Book issue could not be completed.", "error"); return redirect(url_for("dashboard"))
    flash("Book issued successfully.", "success"); return redirect(url_for("dashboard"))


@app.post("/librarian/issues/<int:issue_id>/return")
def return_book(issue_id):
    if not is_librarian(): flash("Librarian or Admin access required.", "error"); return redirect(url_for("index"))
    try:
        issue=db_retry(lambda: db.get_or_404(Issue, issue_id))
        if issue.status != "issued":
            flash("This book has already been returned.", "error"); return redirect(url_for("dashboard"))
        today=date.today()
        issue.return_date=today
        issue.status="returned"
        issue.fine=max((today-issue.due_date).days,0)*5
        issue.book.available_copies=min(issue.book.available_copies+1,issue.book.total_copies)
        db.session.commit()
    except OperationalError:
        db.session.rollback(); db.engine.dispose()
        flash("Book return failed.", "error"); return redirect(url_for("dashboard"))
    flash("Book returned successfully.", "success"); return redirect(url_for("dashboard"))


@app.route("/change-password", methods=["GET","POST"])
def change_password():
    # Authenticated-only password change avoids a public credential-collection form.
    if not session.get("user_id"):
        return redirect(url_for("index"))
    if request.method=="GET":
        return render_template("change_password.html")
    f=request.form
    current_password=f.get("current_password","")
    new_password=f.get("new_password","")
    confirm=f.get("confirm_password","")
    if not all([current_password,new_password,confirm]) or new_password!=confirm or len(new_password)<6:
        flash("Please enter valid passwords. New passwords must match and be at least 6 characters.","error")
        return redirect(url_for("change_password"))
    if is_admin():
        flash("Admin password is managed in Render Environment Variables.","error")
        return redirect(url_for("dashboard"))
    try:
        user=db_retry(lambda: db.get_or_404(User,session["user_id"]))
        if not check_password_hash(user.password_hash,current_password):
            flash("Current password is incorrect.","error"); return redirect(url_for("change_password"))
        user.password_hash=generate_password_hash(new_password); db.session.commit()
    except OperationalError:
        db.session.rollback(); db.engine.dispose()
        flash("Database connection was temporarily unavailable.","error"); return redirect(url_for("change_password"))
    session.clear(); flash("Password changed successfully. Please login again.","success")
    return redirect(url_for("index"))


@app.route("/google16cb8e6f39fcab03.html")
def google_site_verification():
    return "google-site-verification: google16cb8e6f39fcab03.html"


@app.route("/robots.txt")
def robots():
    response=make_response("User-agent: *\nAllow: /\n\nSitemap: "+request.url_root.rstrip("/")+"/sitemap.xml\n")
    response.headers["Content-Type"]="text/plain; charset=utf-8"; return response


@app.route("/sitemap.xml")
def sitemap():
    urls=[url_for("index",_external=True),url_for("register",_external=True)]
    xml='<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    xml += "".join(f"<url><loc>{u}</loc></url>" for u in urls)+"</urlset>"
    response=make_response(xml); response.headers["Content-Type"]="application/xml; charset=utf-8"; return response


with app.app_context():
    db.create_all()
    try:
        migrate_old_schema()
    except Exception:
        db.session.rollback()


if __name__ == "__main__":
    app.run(debug=True)
