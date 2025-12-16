import os
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf", "doc", "docx", "xlsx", "csv", "txt"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{BASE_DIR / 'crm.db'}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)

UPLOAD_FOLDER.mkdir(exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def delete_attachment_file(attachment: "Attachment") -> None:
    file_path = UPLOAD_FOLDER / attachment.stored_name
    if file_path.exists():
        file_path.unlink()


def delete_task_with_children(task: "Task") -> None:
    for sub in list(task.subtasks):
        delete_task_with_children(sub)
    for attachment in list(task.attachments):
        delete_attachment_file(attachment)
        db.session.delete(attachment)
    db.session.delete(task)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    tasks = db.relationship("Task", backref="assignee", lazy=True)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(50))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tasks = db.relationship("Task", backref="contact", lazy=True)
    attachments = db.relationship("Attachment", backref="contact", lazy=True)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(50), default="Nová")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    contact_id = db.Column(db.Integer, db.ForeignKey("contact.id"), nullable=False)
    assignee_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    parent_task_id = db.Column(db.Integer, db.ForeignKey("task.id"))

    subtasks = db.relationship(
        "Task",
        backref=db.backref("parent", remote_side=[id]),
        lazy=True,
    )
    attachments = db.relationship("Attachment", backref="task", lazy=True)


class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stored_name = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    contact_id = db.Column(db.Integer, db.ForeignKey("contact.id"), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"))


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def ensure_default_users():
    if User.query.count() == 0:
        first = User(username="manager")
        first.set_password("manager123")
        second = User(username="agent")
        second.set_password("agent123")
        db.session.add_all([first, second])
        db.session.commit()


@app.before_request
def setup_defaults():
    db.create_all()
    ensure_default_users()


@app.route("/")
@login_required
def index():
    recent_contacts = Contact.query.order_by(Contact.created_at.desc()).limit(5).all()
    recent_tasks = Task.query.order_by(Task.created_at.desc()).limit(5).all()
    return render_template("index.html", contacts=recent_contacts, tasks=recent_tasks)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("index"))
        flash("Nesprávne prihlasovacie údaje", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/contacts")
@login_required
def contacts():
    return render_template("contacts.html", contacts=Contact.query.order_by(Contact.created_at.desc()).all())


@app.route("/contacts/new", methods=["GET", "POST"])
@login_required
def new_contact():
    if request.method == "POST":
        name = request.form.get("name")
        if not name:
            flash("Meno je povinné", "danger")
            return redirect(url_for("new_contact"))
        contact = Contact(
            name=name,
            email=request.form.get("email"),
            phone=request.form.get("phone"),
            notes=request.form.get("notes"),
        )
        db.session.add(contact)
        db.session.commit()
        flash("Kontakt bol vytvorený", "success")
        return redirect(url_for("contact_detail", contact_id=contact.id))
    return render_template("new_contact.html")


@app.route("/contacts/<int:contact_id>/edit", methods=["GET", "POST"])
@login_required
def edit_contact(contact_id):
    contact = Contact.query.get_or_404(contact_id)
    if request.method == "POST":
        name = request.form.get("name")
        if not name:
            flash("Meno je povinné", "danger")
            return redirect(url_for("edit_contact", contact_id=contact.id))
        contact.name = name
        contact.email = request.form.get("email")
        contact.phone = request.form.get("phone")
        contact.notes = request.form.get("notes")
        db.session.commit()
        flash("Kontakt bol upravený", "success")
        return redirect(url_for("contact_detail", contact_id=contact.id))
    return render_template("edit_contact.html", contact=contact)


@app.route("/contacts/<int:contact_id>", methods=["GET", "POST"])
@login_required
def contact_detail(contact_id):
    contact = Contact.query.get_or_404(contact_id)
    tasks = Task.query.filter_by(contact_id=contact.id, parent_task_id=None).order_by(Task.created_at.desc()).all()
    assignees = User.query.all()
    if request.method == "POST":
        title = request.form.get("title")
        if not title:
            flash("Názov úlohy je povinný", "danger")
            return redirect(url_for("contact_detail", contact_id=contact.id))
        task = Task(
            title=title,
            description=request.form.get("description"),
            status=request.form.get("status", "Nová"),
            contact_id=contact.id,
            assignee_id=request.form.get("assignee_id") or None,
            parent_task_id=request.form.get("parent_task_id") or None,
        )
        db.session.add(task)
        db.session.commit()
        flash("Úloha bola pridaná", "success")
        return redirect(url_for("contact_detail", contact_id=contact.id))
    return render_template("contact_detail.html", contact=contact, tasks=tasks, assignees=assignees)


@app.route("/tasks/<int:task_id>/status", methods=["POST"])
@login_required
def update_task_status(task_id):
    task = Task.query.get_or_404(task_id)
    task.status = request.form.get("status", task.status)
    db.session.commit()
    flash("Stav úlohy bol aktualizovaný", "success")
    return redirect(url_for("contact_detail", contact_id=task.contact_id))


@app.route("/tasks/<int:task_id>/edit", methods=["POST"])
@login_required
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    title = request.form.get("title")
    if not title:
        flash("Názov úlohy je povinný", "danger")
        return redirect(url_for("contact_detail", contact_id=task.contact_id))
    task.title = title
    task.description = request.form.get("description")
    task.status = request.form.get("status", task.status)
    task.assignee_id = request.form.get("assignee_id") or None
    db.session.commit()
    flash("Úloha bola upravená", "success")
    return redirect(url_for("contact_detail", contact_id=task.contact_id))


@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    contact_id = task.contact_id
    delete_task_with_children(task)
    db.session.commit()
    flash("Úloha bola odstránená", "success")
    return redirect(url_for("contact_detail", contact_id=contact_id))


@app.route("/contacts/<int:contact_id>/delete", methods=["POST"])
@login_required
def delete_contact(contact_id):
    contact = Contact.query.get_or_404(contact_id)
    for attachment in [a for a in contact.attachments if a.task_id is None]:
        delete_attachment_file(attachment)
        db.session.delete(attachment)
    for task in list(contact.tasks):
        delete_task_with_children(task)
    db.session.delete(contact)
    db.session.commit()
    flash("Kontakt bol odstránený", "success")
    return redirect(url_for("contacts"))


@app.route("/contacts/<int:contact_id>/upload", methods=["POST"])
@login_required
def upload_file(contact_id):
    contact = Contact.query.get_or_404(contact_id)
    file = request.files.get("file")
    if file and allowed_file(file.filename):
        original_name = file.filename
        filename = secure_filename(f"{datetime.utcnow().timestamp()}_{original_name}")
        file.save(UPLOAD_FOLDER / filename)
        attachment = Attachment(
            stored_name=str(filename),
            original_name=original_name,
            contact_id=contact.id,
            task_id=request.form.get("task_id") or None,
        )
        db.session.add(attachment)
        db.session.commit()
        flash("Súbor bol pridaný", "success")
    else:
        flash("Neplatný súbor", "danger")
    return redirect(url_for("contact_detail", contact_id=contact.id))


@app.route("/files/<path:filename>")
@login_required
def download_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)


@app.route("/attachments/<int:attachment_id>/delete", methods=["POST"])
@login_required
def delete_attachment(attachment_id):
    attachment = Attachment.query.get_or_404(attachment_id)
    contact_id = attachment.contact_id
    delete_attachment_file(attachment)
    db.session.delete(attachment)
    db.session.commit()
    flash("Súbor bol odstránený", "success")
    return redirect(url_for("contact_detail", contact_id=contact_id))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
