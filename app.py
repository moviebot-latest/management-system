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

@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        required = ["name", "gender", "department", "email", "username", "password", "confirm"]
        if not all(f.get(x, "").strip() for x in required):
            flash("Please fill in all fields.", "error")
        elif f["password"] != f["confirm"]:
            flash("Passwords do not match.", "error")
        elif len(f["password"]) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif User.query.filter_by(username=f["username"].strip()).first():
            flash("Username already exists.", "error")
        elif User.query.filter_by(email=f["email"].strip().lower()).first():
            flash("Email already exists.", "error")
        else:
            user = User(
                employee_id=next_employee_id(),
                name=f["name"].strip(),
                gender=f["gender"],
                department=f["department"],
                email=f["email"].strip().lower(),
                username=f["username"].strip(),
                password_hash=generate_password_hash(f["password"])
            )
            db.session.add(user)
            db.session.commit()
            flash(f"Account created. Employee ID: {user.employee_id}", "success")
            return redirect(url_for("index"))
    return render_template("register.html")

@app.post("/login")
def login():
    f = request.form

    # Admin credentials are ONLY stored in Render Environment Variables.
    admin_username = os.environ.get("ADMIN_USERNAME")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if (admin_username and admin_password
            and f["username"].strip() == admin_username
            and f["password"] == admin_password):
        session["user_id"] = "admin"
        session["role"] = "admin"
        return redirect(url_for("dashboard"))

    user = User.query.filter_by(username=f["username"].strip()).first()
    if user and check_password_hash(user.password_hash, f["password"]):
        session["user_id"] = user.id
        session["role"] = "user"
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
    users = User.query.order_by(User.id.desc()).all()
    return render_template("dashboard.html", users=users, role=session.get("role"))

@app.post("/admin/users/create")
def create_user():
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))

    f = request.form
    if User.query.filter_by(username=f["username"].strip()).first():
        flash("Username already exists.", "error")
        return redirect(url_for("dashboard"))
    if User.query.filter_by(email=f["email"].strip().lower()).first():
        flash("Email already exists.", "error")
        return redirect(url_for("dashboard"))

    user = User(
        employee_id=next_employee_id(),
        name=f["name"].strip(),
        gender=f["gender"],
        department=f["department"].strip(),
        email=f["email"].strip().lower(),
        username=f["username"].strip(),
        password_hash=generate_password_hash(f["password"])
    )
    db.session.add(user)
    db.session.commit()
    flash("User created successfully.", "success")
    return redirect(url_for("dashboard"))

@app.post("/admin/users/<int:user_id>/edit")
def edit_user(user_id):
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))

    user = db.get_or_404(User, user_id)
    f = request.form

    duplicate_username = User.query.filter(
        User.username == f["username"].strip(), User.id != user_id
    ).first()
    duplicate_email = User.query.filter(
        User.email == f["email"].strip().lower(), User.id != user_id
    ).first()

    if duplicate_username or duplicate_email:
        flash("Username or email already exists.", "error")
        return redirect(url_for("dashboard"))

    user.name = f["name"].strip()
    user.gender = f["gender"]
    user.department = f["department"].strip()
    user.email = f["email"].strip().lower()
    user.username = f["username"].strip()

    if f.get("password"):
        if len(f["password"]) < 6:
            flash("New password must be at least 6 characters.", "error")
            return redirect(url_for("dashboard"))
        user.password_hash = generate_password_hash(f["password"])

    db.session.commit()
    flash("User updated successfully.", "success")
    return redirect(url_for("dashboard"))

@app.post("/admin/users/<int:user_id>/delete")
def delete_user(user_id):
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))

    user = db.get_or_404(User, user_id)
    db.session.delete(user)
    db.session.commit()
    flash("User deleted successfully.", "success")
    return redirect(url_for("dashboard"))

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
