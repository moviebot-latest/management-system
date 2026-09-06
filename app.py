import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app=Flask(__name__)
app.config["SECRET_KEY"]=os.environ.get("SECRET_KEY","dev-secret-change-me")
url=os.environ.get("DATABASE_URL","sqlite:///management.db")
if url.startswith("postgres://"): url=url.replace("postgres://","postgresql://",1)
app.config["SQLALCHEMY_DATABASE_URI"]=url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"]=False
db=SQLAlchemy(app)

class User(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    employee_id=db.Column(db.String(20),unique=True,nullable=False)
    name=db.Column(db.String(120),nullable=False)
    gender=db.Column(db.String(30),nullable=False)
    department=db.Column(db.String(80),nullable=False)
    email=db.Column(db.String(160),unique=True,nullable=False)
    username=db.Column(db.String(80),unique=True,nullable=False)
    password_hash=db.Column(db.String(255),nullable=False)
    created_at=db.Column(db.DateTime,server_default=db.func.now())

def next_id():
    n=User.query.count()+1
    while User.query.filter_by(employee_id=f"EMP{n:03d}").first(): n+=1
    return f"EMP{n:03d}"

@app.route("/")
def index(): return redirect(url_for("dashboard")) if session.get("user_id") else render_template("login.html")

@app.route("/register",methods=["GET","POST"])
def register():
    if request.method=="POST":
        f=request.form
        if not all(f.get(x,"").strip() for x in ["name","gender","department","email","username","password","confirm"]):
            flash("Please fill in all fields.","error")
        elif f["password"]!=f["confirm"]: flash("Passwords do not match.","error")
        elif len(f["password"])<6: flash("Password must be at least 6 characters.","error")
        elif User.query.filter_by(username=f["username"].strip()).first(): flash("Username already exists.","error")
        elif User.query.filter_by(email=f["email"].strip().lower()).first(): flash("Email already exists.","error")
        else:
            u=User(employee_id=next_id(),name=f["name"].strip(),gender=f["gender"],department=f["department"],email=f["email"].strip().lower(),username=f["username"].strip(),password_hash=generate_password_hash(f["password"]))
            db.session.add(u); db.session.commit()
            flash(f"Account created. Employee ID: {u.employee_id}","success")
            return redirect(url_for("index"))
    return render_template("register.html")

@app.post("/login")
def login():
    f=request.form
    if f["username"]=="admin" and f["password"]=="admin123":
        session.update(user_id="admin",role="admin"); return redirect(url_for("dashboard"))
    u=User.query.filter_by(username=f["username"].strip()).first()
    if u and check_password_hash(u.password_hash,f["password"]):
        session.update(user_id=u.id,role="user"); return redirect(url_for("dashboard"))
    flash("Invalid username or password.","error"); return redirect(url_for("index"))

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("index"))

@app.route("/dashboard")
def dashboard():
    if not session.get("user_id"): return redirect(url_for("index"))
    return render_template("dashboard.html",users=User.query.order_by(User.id.desc()).all(),role=session["role"])

@app.post("/admin/users/create")
def create_user():
    if session.get("role")!="admin": return redirect(url_for("dashboard"))
    f=request.form
    if User.query.filter_by(username=f["username"].strip()).first() or User.query.filter_by(email=f["email"].strip().lower()).first():
        flash("Username or email already exists.","error"); return redirect(url_for("dashboard"))
    u=User(employee_id=next_id(),name=f["name"].strip(),gender=f["gender"],department=f["department"],email=f["email"].strip().lower(),username=f["username"].strip(),password_hash=generate_password_hash(f["password"]))
    db.session.add(u); db.session.commit(); flash("User created successfully.","success"); return redirect(url_for("dashboard"))

@app.post("/admin/users/<int:id>/edit")
def edit_user(id):
    if session.get("role")!="admin": return redirect(url_for("dashboard"))
    u=db.get_or_404(User,id); f=request.form
    if User.query.filter(User.username==f["username"].strip(),User.id!=id).first() or User.query.filter(User.email==f["email"].strip().lower(),User.id!=id).first():
        flash("Username or email already exists.","error"); return redirect(url_for("dashboard"))
    u.name=f["name"].strip(); u.gender=f["gender"]; u.department=f["department"]; u.email=f["email"].strip().lower(); u.username=f["username"].strip()
    if f.get("password"): u.password_hash=generate_password_hash(f["password"])
    db.session.commit(); flash("User updated successfully.","success"); return redirect(url_for("dashboard"))

@app.post("/admin/users/<int:id>/delete")
def delete_user(id):
    if session.get("role")!="admin": return redirect(url_for("dashboard"))
    db.session.delete(db.get_or_404(User,id)); db.session.commit(); flash("User deleted successfully.","success"); return redirect(url_for("dashboard"))

with app.app_context(): db.create_all()
if __name__=="__main__": app.run(debug=True)
