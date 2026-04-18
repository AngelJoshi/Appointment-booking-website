from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from functools import wraps
import random, string

# ── App Setup ──────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "change-this-to-a-random-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///appointments.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ── Admin Credentials ──────────────────────────────────────────────────────────
ADMIN_USERNAME = "ram"
ADMIN_PASSWORD = "joshi@123"

# ── Slot Configuration ─────────────────────────────────────────────────────────
# Morning: 9:00 AM to 10:30 AM  |  Evening: 6:00 PM to 9:00 PM
SLOT_RANGES = [
    ((9, 0), (10, 30)),
    ((18, 0), (21, 0)),
]
SLOT_MINUTES = 15

def build_all_slots():
    """Build full list of (hour, minute) tuples for all available slots."""
    slots = []
    for (sh, sm), (eh, em) in SLOT_RANGES:
        h, m = sh, sm
        while (h * 60 + m) < (eh * 60 + em):
            slots.append((h, m))
            m += SLOT_MINUTES
            if m >= 60:
                m -= 60
                h += 1
    return slots

ALL_SLOTS = build_all_slots()

# ── Database Model ─────────────────────────────────────────────────────────────
class Appointment(db.Model):
    __tablename__ = "appointments"
    id          = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    ref         = db.Column(db.String(12),  unique=True, nullable=False)
    client_name = db.Column(db.String(100), nullable=False)
    contact_no  = db.Column(db.String(20),  nullable=False)
    date_time   = db.Column(db.DateTime,    nullable=False)
    case_type   = db.Column(db.String(50),  nullable=False)
    status      = db.Column(db.String(20),  nullable=False, default="pending")
    created_at  = db.Column(db.DateTime,    default=datetime.utcnow)

    def __repr__(self):
        return f"<Appointment {self.ref} {self.client_name}>"

# ── Helpers ────────────────────────────────────────────────────────────────────
def generate_ref():
    return "RSJ-" + "".join(random.choices(string.digits, k=6))

def get_booked_slots(for_date):
    """Return set of (hour, minute) tuples already booked on a given date."""
    try:
        day_start = datetime(for_date.year, for_date.month, for_date.day)
        day_end   = day_start + timedelta(days=1)
        rows = Appointment.query.filter(
            Appointment.date_time >= day_start,
            Appointment.date_time <  day_end,
            Appointment.status.in_(["pending", "approved"])
        ).all()
        return {(r.date_time.hour, r.date_time.minute) for r in rows}
    except Exception as e:
        print(f"[DB ERROR in get_booked_slots] {e}")
        return set()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Please log in to access the dashboard.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return redirect(url_for("book"))


@app.route("/book", methods=["GET", "POST"])
def book():
    if request.method == "POST":
        client_name = request.form.get("client_name", "").strip()
        contact_no  = request.form.get("contact_no",  "").strip()
        date_str    = request.form.get("appt_date",   "").strip()
        slot_str    = request.form.get("appt_slot",   "").strip()
        case_type   = request.form.get("case_type",   "").strip()

        if not all([client_name, contact_no, date_str, slot_str, case_type]):
            flash("All fields are required.", "danger")
            return redirect(url_for("book"))

        try:
            appt_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            h, m      = map(int, slot_str.split(":"))
            dt        = datetime(appt_date.year, appt_date.month, appt_date.day, h, m)
        except Exception:
            flash("Invalid date or time slot.", "danger")
            return redirect(url_for("book"))

        if (h, m) not in ALL_SLOTS:
            flash("Selected time slot is not valid.", "danger")
            return redirect(url_for("book"))

        if dt <= datetime.now():
            flash("Cannot book a past date or time.", "danger")
            return redirect(url_for("book"))

        if (h, m) in get_booked_slots(appt_date):
            flash("That slot is already taken. Please choose another.", "danger")
            return redirect(url_for("book"))

        # Generate unique reference
        ref = generate_ref()
        while Appointment.query.filter_by(ref=ref).first():
            ref = generate_ref()

        appt = Appointment(
            ref=ref, client_name=client_name, contact_no=contact_no,
            date_time=dt, case_type=case_type, status="pending"
        )
        db.session.add(appt)
        db.session.commit()
        return redirect(url_for("confirmed", ref=ref))

    return render_template("booking.html")


@app.route("/slots")
def slots():
    """Return available time slots for a given date as JSON."""
    date_str = request.args.get("date", "").strip()
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return jsonify({"error": "Invalid date"}), 400

    try:
        booked = get_booked_slots(d)
        now    = datetime.now()
        result = []
        for (h, m) in ALL_SLOTS:
            slot_dt = datetime(d.year, d.month, d.day, h, m)
            taken   = (h, m) in booked or slot_dt <= now
            label   = slot_dt.strftime("%I:%M %p").lstrip("0")
            result.append({
                "value":   f"{h:02d}:{m:02d}",
                "label":   label,
                "session": "Morning" if h < 12 else "Evening",
                "taken":   taken,
            })
        return jsonify(result)
    except Exception as e:
        print(f"[SLOTS ROUTE ERROR] {e}")
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/confirmed")
def confirmed():
    ref  = request.args.get("ref", "")
    appt = Appointment.query.filter_by(ref=ref).first()
    return render_template("confirmed.html", appt=appt)


@app.route("/status", methods=["GET", "POST"])
def status():
    appt = None
    if request.method == "POST":
        ref  = request.form.get("ref", "").strip().upper()
        appt = Appointment.query.filter_by(ref=ref).first()
        if not appt:
            flash("No appointment found with that reference number.", "danger")
    return render_template("status.html", appt=appt)


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        if (request.form.get("username") == ADMIN_USERNAME and
                request.form.get("password") == ADMIN_PASSWORD):
            session["logged_in"] = True
            flash("Welcome, Adv. Ram S. Joshi!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid credentials.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    filter_status = request.args.get("status", "all")
    q = Appointment.query
    if filter_status != "all":
        q = q.filter_by(status=filter_status)
    appointments = q.order_by(Appointment.date_time.asc()).all()
    total    = Appointment.query.count()
    pending  = Appointment.query.filter_by(status="pending").count()
    approved = Appointment.query.filter_by(status="approved").count()
    return render_template("dashboard.html",
        appointments=appointments,
        total=total, pending=pending, approved=approved,
        filter_status=filter_status
    )


@app.route("/approve/<int:appt_id>")
@login_required
def approve(appt_id):
    appt = Appointment.query.get_or_404(appt_id)
    appt.status = "approved"
    db.session.commit()
    flash(f"Approved: {appt.client_name}", "success")
    return redirect(url_for("dashboard", status=request.args.get("from", "all")))


@app.route("/reject/<int:appt_id>")
@login_required
def reject(appt_id):
    appt = Appointment.query.get_or_404(appt_id)
    appt.status = "rejected"
    db.session.commit()
    flash(f"Rejected: {appt.client_name}", "info")
    return redirect(url_for("dashboard", status=request.args.get("from", "all")))


@app.route("/delete/<int:appt_id>")
@login_required
def delete(appt_id):
    appt = Appointment.query.get_or_404(appt_id)
    db.session.delete(appt)
    db.session.commit()
    flash("Appointment deleted.", "info")
    return redirect(url_for("dashboard"))


# ── Run ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        # Add missing columns to existing databases (handles upgrades)
        try:
            with db.engine.connect() as con:
                con.execute(db.text("ALTER TABLE appointments ADD COLUMN status VARCHAR(20) DEFAULT 'pending'"))
                con.execute(db.text("ALTER TABLE appointments ADD COLUMN ref VARCHAR(12)"))
                con.execute(db.text("ALTER TABLE appointments ADD COLUMN created_at DATETIME"))
                con.commit()
                print("[DB] Schema updated with new columns.")
        except Exception:
            pass  # Columns already exist, ignore
    app.run(debug=True)