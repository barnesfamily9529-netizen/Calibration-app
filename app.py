"""
Calibration Gage Management - Flask Application
Simple web app for managing calibration gages with SQLite backend.
"""

import sqlite3
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, flash

DATABASE = Path(__file__).parent / "calibration.db"
app = Flask(__name__)
app.secret_key = "calibration-app-secret-key"


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database and create tables if they don't exist."""
    conn = get_db()
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='gages'"
    )
    if cur.fetchone():
        info = conn.execute("PRAGMA table_info(gages)").fetchall()
        cols = [r[1] for r in info]
        if "location" in cols or "month_code" not in cols:
            conn.execute("DROP TABLE gages")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS gages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gage_id TEXT NOT NULL UNIQUE,
            month_code TEXT,
            number TEXT,
            gage_type TEXT,
            description TEXT,
            manufacturer TEXT,
            model TEXT,
            serial TEXT,
            cert_number TEXT,
            cal_date TEXT,
            due_date TEXT,
            interval_years REAL,
            condition TEXT,
            status TEXT DEFAULT 'Active',
            comments TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def _strip(value):
    """Return stripped string or None if empty."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _get_form_gage(request):
    """Extract gage data from request form."""
    from datetime import datetime, timedelta

    interval = request.form.get("interval_years", "").strip()
    cal_date = _strip(request.form.get("cal_date")) or None
    due_date = _strip(request.form.get("due_date")) or None

    interval_years = float(interval) if interval else None

    if cal_date and interval_years is not None and not due_date:
        try:
            cal_date_obj = datetime.strptime(cal_date, "%Y-%m-%d").date()
            due_date_obj = cal_date_obj + timedelta(days=round(interval_years * 365))
            due_date = due_date_obj.isoformat()
        except ValueError:
            pass

    return {
        "gage_id": _strip(request.form.get("gage_id")),
        "month_code": _strip(request.form.get("month_code")),
        "number": _strip(request.form.get("number")),
        "gage_type": _strip(request.form.get("gage_type")),
        "description": _strip(request.form.get("description")),
        "manufacturer": _strip(request.form.get("manufacturer")),
        "model": _strip(request.form.get("model")),
        "serial": _strip(request.form.get("serial")),
        "cert_number": _strip(request.form.get("cert_number")),
        "cal_date": cal_date,
        "due_date": due_date,
        "interval_years": interval_years,
        "condition": _strip(request.form.get("condition")),
        "status": _strip(request.form.get("status")) or "Active",
        "comments": _strip(request.form.get("comments")),
    }


@app.route("/")
def index():
    """List and filter calibration gages."""
    from datetime import date, timedelta

    search = (request.args.get("search") or "").strip()
    status_filter = (request.args.get("status") or "").strip()
    overdue_only = request.args.get("overdue") == "1"
    sort_by = request.args.get("sort_by", "due_date")
    sort_dir = request.args.get("sort_dir", "asc")

    conn = get_db()

    query = "SELECT * FROM gages WHERE 1=1"
    params = []

    if search:
        query += """
            AND (
                gage_id LIKE ?
                OR gage_type LIKE ?
                OR description LIKE ?
                OR manufacturer LIKE ?
            )
        """
        like_term = f"%{search}%"
        params.extend([like_term, like_term, like_term, like_term])

    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)

    gages = conn.execute(query, params).fetchall()
    conn.close()

    valid_sort_fields = {
        "gage_id": "gage_id",
        "gage_type": "gage_type",
        "description": "description",
        "status": "status",
        "condition": "condition",
        "manufacturer": "manufacturer",
        "due_date": "due_date",
    }

    sort_field = valid_sort_fields.get(sort_by, "due_date")
    reverse_sort = sort_dir == "desc"

    def sort_key(g):
        value = g[sort_field] or ""
        return str(value).lower()

    gages = sorted(gages, key=sort_key, reverse=reverse_sort)

    today = date.today()
    today_iso = today.isoformat()

    due_soon_dates = set()
    for i in range(0, 31):
        due_soon_dates.add((today + timedelta(days=i)).isoformat())

    if overdue_only:
        filtered_gages = []
        for gage in gages:
            due_date = gage["due_date"] or ""
            status = gage["status"] or ""
            if due_date and status == "Active" and due_date < today_iso:
                filtered_gages.append(gage)
        gages = filtered_gages

    return render_template(
        "index.html",
        gages=gages,
        today=today_iso,
        due_soon_dates=due_soon_dates,
        search=search,
        status_filter=status_filter,
        overdue_only=overdue_only,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
@app.route("/add", methods=["GET", "POST"])
def add():
    """Add a new calibration gage."""
    if request.method == "POST":
        g = _get_form_gage(request)
        if not g["gage_id"]:
            flash("Gage ID is required.", "error")
            return redirect(url_for("add"))

        conn = get_db()
        try:
            conn.execute(
                """INSERT INTO gages (
                    gage_id, month_code, number, gage_type, description,
                    manufacturer, model, serial, cert_number, cal_date,
                    due_date, interval_years, condition, status, comments
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    g["gage_id"], g["month_code"], g["number"], g["gage_type"],
                    g["description"], g["manufacturer"], g["model"], g["serial"],
                    g["cert_number"], g["cal_date"], g["due_date"],
                    g["interval_years"], g["condition"], g["status"], g["comments"],
                ),
            )
            conn.commit()
            flash("Gage added successfully.", "success")
            return redirect(url_for("index"))
        except sqlite3.IntegrityError:
            flash("A gage with this ID already exists.", "error")
            return redirect(url_for("add"))
        finally:
            conn.close()

    return render_template("add.html")


@app.route("/edit/<int:gage_pk>", methods=["GET", "POST"])
def edit(gage_pk):
    """Edit an existing calibration gage."""
    conn = get_db()
    gage = conn.execute("SELECT * FROM gages WHERE id = ?", (gage_pk,)).fetchone()

    if not gage:
        conn.close()
        flash("Gage not found.", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        g = _get_form_gage(request)
        if not g["gage_id"]:
            flash("Gage ID is required.", "error")
            conn.close()
            return redirect(url_for("edit", gage_pk=gage_pk))

        try:
            conn.execute(
                """UPDATE gages SET
                    gage_id=?, month_code=?, number=?, gage_type=?, description=?,
                    manufacturer=?, model=?, serial=?, cert_number=?, cal_date=?,
                    due_date=?, interval_years=?, condition=?, status=?, comments=?
                    WHERE id=?""",
                (
                    g["gage_id"], g["month_code"], g["number"], g["gage_type"],
                    g["description"], g["manufacturer"], g["model"], g["serial"],
                    g["cert_number"], g["cal_date"], g["due_date"],
                    g["interval_years"], g["condition"], g["status"], g["comments"],
                    gage_pk,
                ),
            )
            conn.commit()
            flash("Gage updated successfully.", "success")
            conn.close()
            return redirect(url_for("index"))
        except sqlite3.IntegrityError:
            flash("A gage with this ID already exists.", "error")
            conn.close()
            return redirect(url_for("edit", gage_pk=gage_pk))

    conn.close()
    return render_template("edit.html", gage=gage)


@app.route("/delete/<int:gage_pk>", methods=["POST"])
def delete(gage_pk):
    """Delete a calibration gage."""
    conn = get_db()
    conn.execute("DELETE FROM gages WHERE id = ?", (gage_pk,))
    conn.commit()
    conn.close()
    flash("Gage deleted.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
