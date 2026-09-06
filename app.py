import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret")
database_url = os.environ.get("DATABASE_URL", "sqlite:///management.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
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
    created_at = db.Column(db.DateTime, server_default=db.func.now())

def next_employee_id():
    n = User.query.count() + 1
    while User.query.filter_by(employee_id=f"EMP{n:03d}").first():
        n += 1
    return f"EMP{n:03d}"

def is_admin():
    return session.get("role") == "admin"

def current_name():
    if is_admin():
        return os.environ.get("ADMIN_NAME", "Admin")
    user = User.query.get(session.get("user_id")) if session.get("user_id") else None
    return user.name if user else "User"

@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    # Public self-registration: a normal user can create only their own account.
    # Admin-only create/edit/delete remains protected by /admin/* routes.
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        f = request.form
        required = ["name", "gender", "department", "email", "username", "password", "confirm"]
        name = f.get("name", "").strip()
        gender = f.get("gender", "").strip()
        department = f.get("department", "").strip()
        email = f.get("email", "").strip().lower()
        username = f.get("username", "").strip()
        password = f.get("password", "")
        confirm = f.get("confirm", "")

        if not all(f.get(x, "").strip() for x in required):
            flash("Please fill in all fields.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif User.query.filter_by(username=username).first():
            flash("Username already exists.", "error")
        elif User.query.filter_by(email=email).first():
            flash("Email already exists.", "error")
        else:
            user = User(
                employee_id=next_employee_id(),
                name=name,
                gender=gender,
                department=department,
                email=email,
                username=username,
                password_hash=generate_password_hash(password)
            )
            db.session.add(user)
            db.session.commit()
            flash(f"Account created successfully. Employee ID: {user.employee_id}", "success")
            return redirect(url_for("index"))

    return render_template("register.html")

@app.post("/login")
def login():
    f = request.form
    username = f.get("username", "").strip()
    password = f.get("password", "")
    admin_username = os.environ.get("ADMIN_USERNAME")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if (admin_username and admin_password and username == admin_username and password == admin_password):
        session.clear()
        session["user_id"] = "admin"
        session["role"] = "admin"
        session["username"] = admin_username
        session["name"] = os.environ.get("ADMIN_NAME", "Admin")
        return redirect(url_for("dashboard"))

    user = User.query.filter_by(username=username).first()
    if user and check_password_hash(user.password_hash, password):
        session.clear()
        session["user_id"] = user.id
        session["role"] = "user"
        session["username"] = user.username
        session["name"] = user.name
        return redirect(url_for("dashboard"))

    flash("Invalid username or password.", "error")
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
def dashboard():
    if not session.get("user_id"):
        return redirect(url_for("index"))
    users = User.query.order_by(User.id.desc()).all() if is_admin() else []
    return render_template(
        "dashboard.html",
        users=users,
        role=session.get("role"),
        current_name=session.get("name") or current_name(),
        current_username=session.get("username", "")
    )

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

    # Admin credentials live in Render Environment Variables and cannot be changed here.
    if username == os.environ.get("ADMIN_USERNAME"):
        flash("Admin password is managed in Render Environment Variables.", "error")
        return redirect(url_for("change_password"))

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, current_password):
        flash("Username or current password is incorrect.", "error")
        return redirect(url_for("change_password"))

    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    flash("Password changed successfully. Please login again.", "success")
    session.clear()
    return redirect(url_for("index"))

@app.post("/admin/users/create")
def create_user():
    if not is_admin():
        flash("Admin access required.", "error")
        return redirect(url_for("index"))

    f = request.form
    required = ["name", "gender", "department", "email", "username", "password", "confirm"]
    if not all(f.get(x, "").strip() for x in required):
        flash("Please fill in all fields.", "error")
        return redirect(url_for("dashboard"))
    if f["password"] != f["confirm"]:
        flash("Passwords do not match.", "error")
        return redirect(url_for("dashboard"))
    if len(f["password"]) < 6:
        flash("Password must be at least 6 characters.", "error")
        return redirect(url_for("dashboard"))
    if User.query.filter_by(username=f["username"].strip()).first():
        flash("Username already exists.", "error")
        return redirect(url_for("dashboard"))
    if User.query.filter_by(email=f["email"].strip().lower()).first():
        flash("Email already exists.", "error")
        return redirect(url_for("dashboard"))

    user = User(
        employee_id=next_employee_id(), name=f["name"].strip(), gender=f["gender"],
        department=f["department"].strip(), email=f["email"].strip().lower(),
        username=f["username"].strip(), password_hash=generate_password_hash(f["password"])
    )
    db.session.add(user)
    db.session.commit()
    flash("User created successfully.", "success")
    return redirect(url_for("dashboard"))

@app.post("/admin/users/<int:user_id>/edit")
def edit_user(user_id):
    if not is_admin():
        flash("Admin access required.", "error")
        return redirect(url_for("index"))

    user = db.get_or_404(User, user_id)
    f = request.form
    username = f.get("username", "").strip()
    email = f.get("email", "").strip().lower()
    if not all(f.get(x, "").strip() for x in ["name", "gender", "department", "email", "username"]):
        flash("Please fill in all user fields.", "error")
        return redirect(url_for("dashboard"))

    if User.query.filter(User.username == username, User.id != user_id).first() or User.query.filter(User.email == email, User.id != user_id).first():
        flash("Username or email already exists.", "error")
        return redirect(url_for("dashboard"))

    user.name = f["name"].strip()
    user.gender = f["gender"]
    user.department = f["department"].strip()
    user.email = email
    user.username = username
    if f.get("password"):
        if len(f["password"]) < 6:
            flash("New password must be at least 6 characters.", "error")
            return redirect(url_for("dashboard"))
        if f["password"] != f.get("confirm", ""):
            flash("New passwords do not match.", "error")
            return redirect(url_for("dashboard"))
        user.password_hash = generate_password_hash(f["password"])
    db.session.commit()
    flash("User updated successfully.", "success")
    return redirect(url_for("dashboard"))

@app.post("/admin/users/<int:user_id>/delete")
def delete_user(user_id):
    if not is_admin():
        flash("Admin access required.", "error")
        return redirect(url_for("index"))
    user = db.get_or_404(User, user_id)
    db.session.delete(user)
    db.session.commit()
    flash("User deleted successfully.", "success")
    return redirect(url_for("dashboard"))

# Creates missing tables only; it does not drop or reset existing PostgreSQL data.
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
