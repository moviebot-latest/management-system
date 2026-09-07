import os
import secrets
from datetime import date, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
from flask_sqlalchemy import SQLAlchemy
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
database_url = os.environ.get("DATABASE_URL", "sqlite:///management.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Render/PostgreSQL can close an idle SSL connection. These pool settings make
# SQLAlchemy validate stale connections and recycle them before they go stale.
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
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    gender = db.Column(db.String(30), nullable=False)
    department = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)


def db_retry(fn):
    """Run a DB operation once, then reconnect and retry if a stale SSL connection is hit."""
    try:
        return fn()
    except OperationalError:
        db.session.rollback()
        db.engine.dispose()
        return fn()


def next_employee_id():
    def query():
        n = User.query.count() + 1
        while User.query.filter_by(employee_id=f"EMP{n:03d}").first():
            n += 1
        return f"EMP{n:03d}"
    return db_retry(query)


def is_admin():
    return session.get("role") == "admin"


def current_name():
    if is_admin():
        return os.environ.get("ADMIN_NAME", "Admin")
    user = User.query.get(session.get("user_id")) if session.get("user_id") else None
    return user.name if user else "User"


def user_stats():
    """Return live dashboard stats from PostgreSQL/SQLite."""
    def query():
        total = User.query.count()
        # This app has no inactive-user flag, so every registered user is active.
        active = total
        today = date.today()
        today_count = User.query.filter(db.func.date(User.created_at) == today).count()

        weekly = []
        for offset in range(6, -1, -1):
            day = today - timedelta(days=offset)
            count = User.query.filter(db.func.date(User.created_at) == day).count()
            weekly.append({"label": day.strftime("%a"), "date": day.strftime("%d %b"), "count": count})

        departments = db.session.query(User.department).distinct().count()
        max_count = max((x["count"] for x in weekly), default=1)
        return total, active, today_count, departments, weekly, max_count

    return db_retry(query)


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token()}


def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


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
    # Never allow authenticated pages to be restored from browser cache/BFCache
    # after logout. Public pages are also marked no-store to keep auth screens fresh.
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; form-action 'self'"
    )
    return response


def is_reserved_username(username):
    admin_username = os.environ.get("ADMIN_USERNAME", "admin").strip()
    return username.strip().casefold() == admin_username.casefold() or username.strip().casefold() == "admin"

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
    department = f.get("department", "").strip()
    email = f.get("email", "").strip().lower()
    username = f.get("username", "").strip()

    if is_reserved_username(username):
        flash("This username is restricted by admin.", "error")
        return redirect(url_for("register"))
    password = f.get("password", "")
    confirm = f.get("confirm", "")

    if not all([name, gender, department, email, username, password, confirm]):
        flash("Please fill in all fields.", "error")
        return redirect(url_for("register"))

    if password != confirm:
        flash("Passwords do not match. Please enter the same password in both fields.", "error")
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
            employee_id=next_employee_id(),
            name=name,
            gender=gender,
            department=department,
            email=email,
            username=username,
            password_hash=generate_password_hash(password),
        )
        db.session.add(user)
        db.session.commit()
    except (IntegrityError, OperationalError):
        db.session.rollback()
        db.engine.dispose()
        flash("Registration could not be completed. Please try again.", "error")
        return redirect(url_for("register"))

    flash("Account created successfully. Please login.", "success")
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
            session["role"] = "user"
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
    # Fully destroy the login session. The dashboard also checks this session
    # on browser back/forward navigation, so an old cached page cannot restore
    # an authenticated view after logout.
    session.clear()
    response = redirect(url_for("index"), code=303)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/auth-status")
def auth_status():
    """Small no-cache endpoint used by the dashboard to detect a logged-out session."""
    response = make_response({"authenticated": bool(session.get("user_id"))})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/dashboard")
def dashboard():
    if not session.get("user_id"):
        return redirect(url_for("index"))

    try:
        if is_admin():
            users = db_retry(lambda: User.query.order_by(User.id.desc()).all())
            total, active, today_count, departments, weekly, max_count = user_stats()
        else:
            users = []
            total = active = today_count = departments = 0
            weekly, max_count = [], 1
    except OperationalError:
        db.session.rollback()
        db.engine.dispose()
        flash("Database connection was temporarily unavailable. Please refresh and try again.", "error")
        return redirect(url_for("index"))

    return render_template(
        "dashboard.html",
        users=users,
        role=session.get("role"),
        current_name=session.get("name") or current_name(),
        current_username=session.get("username", ""),
        total_users=total,
        active_users=active,
        today_registrations=today_count,
        departments=departments,
        weekly_registrations=weekly,
        weekly_max=max_count,
    )


@app.route("/google16cb8e6f39fcab03.html")
def google_site_verification():
    return "google-site-verification: google16cb8e6f39fcab03.html"


@app.route("/robots.txt")
def robots():
    response = make_response(
        "User-agent: *\nAllow: /\n\n"
        f"Sitemap: {request.url_root.rstrip('/')}/sitemap.xml\n"
    )
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    return response


@app.route("/sitemap.xml")
def sitemap():
    urls = [url_for("index", _external=True), url_for("register", _external=True)]
    xml = '<?xml version="1.0" encoding="UTF-8"?>'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    for u in urls:
        xml += f"<url><loc>{u}</loc></url>"
    xml += "</urlset>"
    response = make_response(xml)
    response.headers["Content-Type"] = "application/xml; charset=utf-8"
    return response


@app.route("/change-password", methods=["GET", "POST"])
def change_password():
    if request.method == "GET":
        return render_template("change_password.html")

    f = request.form
    username = f.get("username", "").strip()
    current_password = f.get("current_password", "")
    new_password = f.get("new_password", "")
    confirm_password = f.get("confirm_password", "")

    if not all([username, current_password, new_password, confirm_password]):
        flash("Please fill in all fields.", "error")
        return redirect(url_for("change_password"))
    if new_password != confirm_password:
        flash("New passwords do not match.", "error")
        return redirect(url_for("change_password"))
    if len(new_password) < 6:
        flash("New password must be at least 6 characters.", "error")
        return redirect(url_for("change_password"))

    if username == os.environ.get("ADMIN_USERNAME"):
        flash("Admin password is managed in Render Environment Variables.", "error")
        return redirect(url_for("change_password"))

    user = db_retry(lambda: User.query.filter_by(username=username).first())
    if not user or not check_password_hash(user.password_hash, current_password):
        flash("Username or current password is incorrect.", "error")
        return redirect(url_for("change_password"))

    try:
        user.password_hash = generate_password_hash(new_password)
        db.session.commit()
    except OperationalError:
        db.session.rollback()
        db.engine.dispose()
        flash("Database connection was temporarily unavailable. Please try again.", "error")
        return redirect(url_for("change_password"))

    flash("Password changed successfully. Please login again.", "success")
    session.clear()
    return redirect(url_for("index"))


@app.post("/admin/users/create")
def create_user():
    if not is_admin():
        flash("Admin access required.", "error")
        return redirect(url_for("index"))

    f = request.form
    name = f.get("name", "").strip()
    gender = f.get("gender", "").strip()
    department = f.get("department", "").strip()
    email = f.get("email", "").strip().lower()
    username = f.get("username", "").strip()
    password = f.get("password", "")
    confirm = f.get("confirm", "")

    if not all([name, gender, department, email, username, password, confirm]):
        flash("Please fill in all fields.", "error")
        return redirect(url_for("dashboard"))
    if is_reserved_username(username):
        flash("This username is restricted by admin.", "error")
        return redirect(url_for("dashboard"))

    if password != confirm:
        flash("Passwords do not match.", "error")
        return redirect(url_for("dashboard"))
    if len(password) < 6:
        flash("Password must be at least 6 characters.", "error")
        return redirect(url_for("dashboard"))

    try:
        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "error")
            return redirect(url_for("dashboard"))
        if User.query.filter_by(email=email).first():
            flash("Email already exists.", "error")
            return redirect(url_for("dashboard"))

        user = User(
            employee_id=next_employee_id(),
            name=name,
            gender=gender,
            department=department,
            email=email,
            username=username,
            password_hash=generate_password_hash(password),
        )
        db.session.add(user)
        db.session.commit()
    except (IntegrityError, OperationalError):
        db.session.rollback()
        db.engine.dispose()
        flash("User could not be created. Please try again.", "error")
        return redirect(url_for("dashboard"))

    flash("User created successfully.", "success")
    return redirect(url_for("dashboard"))


@app.post("/admin/users/<int:user_id>/edit")
def edit_user(user_id):
    if not is_admin():
        flash("Admin access required.", "error")
        return redirect(url_for("index"))

    try:
        user = db_retry(lambda: db.get_or_404(User, user_id))
        f = request.form
        name = f.get("name", "").strip()
        gender = f.get("gender", "").strip()
        department = f.get("department", "").strip()
        email = f.get("email", "").strip().lower()
        username = f.get("username", "").strip()
        password = f.get("password", "")
        confirm = f.get("confirm", "")

        if not all([name, gender, department, email, username]):
            flash("Please fill in all user fields.", "error")
            return redirect(url_for("dashboard"))

        if is_reserved_username(username):
            flash("This username is restricted by admin.", "error")
            return redirect(url_for("dashboard"))
        if User.query.filter(User.username == username, User.id != user_id).first():
            flash("Username already exists.", "error")
            return redirect(url_for("dashboard"))
        if User.query.filter(User.email == email, User.id != user_id).first():
            flash("Email already exists.", "error")
            return redirect(url_for("dashboard"))

        if password:
            if len(password) < 6:
                flash("New password must be at least 6 characters.", "error")
                return redirect(url_for("dashboard"))
            if password != confirm:
                flash("New passwords do not match.", "error")
                return redirect(url_for("dashboard"))
            user.password_hash = generate_password_hash(password)

        user.name = name
        user.gender = gender
        user.department = department
        user.email = email
        user.username = username
        db.session.commit()
    except (IntegrityError, OperationalError):
        db.session.rollback()
        db.engine.dispose()
        flash("User update could not be completed. Please try again.", "error")
        return redirect(url_for("dashboard"))

    flash("User updated successfully.", "success")
    return redirect(url_for("dashboard"))


@app.post("/admin/users/<int:user_id>/delete")
def delete_user(user_id):
    if not is_admin():
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    try:
        user = db_retry(lambda: db.get_or_404(User, user_id))
        db.session.delete(user)
        db.session.commit()
    except OperationalError:
        db.session.rollback()
        db.engine.dispose()
        flash("Delete failed because the database connection was unavailable.", "error")
        return redirect(url_for("dashboard"))
    flash("User deleted successfully.", "success")
    return redirect(url_for("dashboard"))


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)
