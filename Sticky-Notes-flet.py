import flet as ft
import sqlite3
import json
import os
import smtplib
import threading
import time
from email.message import EmailMessage
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DB_FILE = "sticky_notes_manager.db"


# ============================================================
# FLET COMPATIBILITY HELPERS
# This file avoids fragile APIs:
#   ft.border.all
#   ft.border.only
#   ft.alignment.center
#   ft.padding.symmetric
# It should work better with newer/changed Flet versions.
# ============================================================

def run_app(main_function):
    try:
        ft.run(main_function)
    except AttributeError:
        ft.app(target=main_function)


def icon(name, fallback_text=""):
    """
    Safe icon lookup. If the icon name is missing in a Flet version,
    return fallback text instead of crashing.
    """
    try:
        return getattr(ft.Icons, name)
    except Exception:
        return None


# ============================================================
# DATABASE
# ============================================================

class NotesDatabase:
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file
        self.create_tables()

    def connect(self):
        return sqlite3.connect(self.db_file)

    def create_tables(self):
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT,
                    category TEXT,
                    priority TEXT,
                    color TEXT,
                    location TEXT,
                    timezone TEXT,
                    due_datetime TEXT,
                    email_to TEXT,
                    pinned INTEGER DEFAULT 0,
                    archived INTEGER DEFAULT 0,
                    alarm_sent INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            conn.commit()

    def add_note(self, data):
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as conn:
            cur = conn.execute("""
                INSERT INTO notes (
                    title, content, category, priority, color,
                    location, timezone, due_datetime, email_to,
                    pinned, archived, alarm_sent, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["title"],
                data["content"],
                data["category"],
                data["priority"],
                data["color"],
                data["location"],
                data["timezone"],
                data["due_datetime"],
                data["email_to"],
                int(data["pinned"]),
                int(data["archived"]),
                0,
                now,
                now,
            ))
            conn.commit()
            return cur.lastrowid

    def update_note(self, note_id, data):
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute("""
                UPDATE notes
                SET title=?,
                    content=?,
                    category=?,
                    priority=?,
                    color=?,
                    location=?,
                    timezone=?,
                    due_datetime=?,
                    email_to=?,
                    pinned=?,
                    archived=?,
                    updated_at=?
                WHERE id=?
            """, (
                data["title"],
                data["content"],
                data["category"],
                data["priority"],
                data["color"],
                data["location"],
                data["timezone"],
                data["due_datetime"],
                data["email_to"],
                int(data["pinned"]),
                int(data["archived"]),
                now,
                note_id,
            ))
            conn.commit()

    def delete_note(self, note_id):
        with self.connect() as conn:
            conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
            conn.commit()

    def get_note(self, note_id):
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
            return dict(row) if row else None

    def get_notes(self, search="", category="All", status="Active"):
        query = "SELECT * FROM notes WHERE 1=1"
        params = []

        if status == "Active":
            query += " AND archived=0"
        elif status == "Archived":
            query += " AND archived=1"

        if category and category != "All":
            query += " AND category=?"
            params.append(category)

        if search and search.strip():
            query += " AND (title LIKE ? OR content LIKE ? OR location LIKE ?)"
            pattern = f"%{search.strip()}%"
            params.extend([pattern, pattern, pattern])

        query += """
            ORDER BY pinned DESC,
            CASE priority
                WHEN 'High' THEN 1
                WHEN 'Medium' THEN 2
                WHEN 'Low' THEN 3
                ELSE 4
            END,
            updated_at DESC
        """

        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_due_notes(self):
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM notes
                WHERE archived=0
                  AND alarm_sent=0
                  AND due_datetime IS NOT NULL
                  AND due_datetime != ''
            """).fetchall()
            return [dict(row) for row in rows]

    def mark_alarm_sent(self, note_id):
        with self.connect() as conn:
            conn.execute("UPDATE notes SET alarm_sent=1 WHERE id=?", (note_id,))
            conn.commit()

    def reset_alarm_sent(self, note_id):
        with self.connect() as conn:
            conn.execute("UPDATE notes SET alarm_sent=0 WHERE id=?", (note_id,))
            conn.commit()

    def export_json(self, output_file="sticky_notes_export.json"):
        notes = self.get_notes(status="All")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(notes, f, indent=4, ensure_ascii=False)
        return output_file


# ============================================================
# EMAIL
# ============================================================

def send_email_reminder(to_email, subject, body):
    """
    Optional email reminder.

    Windows SMTP example:
        set SMTP_HOST=smtp.gmail.com
        set SMTP_PORT=587
        set SMTP_USER=your_email@gmail.com
        set SMTP_PASSWORD=your_gmail_app_password
        set SMTP_FROM=your_email@gmail.com
    """

    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM", smtp_user).strip()

    if not smtp_host or not smtp_user or not smtp_password or not smtp_from:
        return False, "SMTP settings are missing. Email was not sent."

    try:
        msg = EmailMessage()
        msg["From"] = smtp_from
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        return True, "Email sent successfully."

    except Exception as e:
        return False, f"Email failed: {e}"


# ============================================================
# HELPERS
# ============================================================

def safe_timezone(timezone_text):
    try:
        return ZoneInfo((timezone_text or "Australia/Brisbane").strip())
    except ZoneInfoNotFoundError:
        return ZoneInfo("Australia/Brisbane")


def parse_due_datetime(due_text, timezone_text):
    """
    Required due date format:
        YYYY-MM-DD HH:MM

    Example:
        2026-05-28 15:30
    """

    if not due_text or not due_text.strip():
        return None, None

    try:
        dt = datetime.strptime(due_text.strip(), "%Y-%m-%d %H:%M")
        tz = safe_timezone(timezone_text)
        return dt.replace(tzinfo=tz), None
    except ValueError:
        return None, "Invalid date/time. Use format: YYYY-MM-DD HH:MM"


def priority_badge_color(priority):
    if priority == "High":
        return "#fee2e2"
    if priority == "Medium":
        return "#fef3c7"
    if priority == "Low":
        return "#dcfce7"
    return "#e5e7eb"


def priority_left_color(priority):
    if priority == "High":
        return "#ef4444"
    if priority == "Medium":
        return "#f59e0b"
    if priority == "Low":
        return "#22c55e"
    return "#94a3b8"


def truncate_text(value, max_len=90):
    value = value or ""
    value = value.replace("\n", " ")
    if len(value) <= max_len:
        return value
    return value[:max_len] + "..."


def now_for_timezone(tz_name):
    return datetime.now(safe_timezone(tz_name))


# ============================================================
# MAIN APP
# ============================================================

def main(page: ft.Page):
    db = NotesDatabase()

    page.title = "Modern Sticky Notes Manager"
    page.bgcolor = "#f8fafc"
    page.padding = 0

    # Window settings can fail on some platforms, so keep them safe.
    try:
        page.window_width = 1250
        page.window_height = 820
        page.window_min_width = 950
        page.window_min_height = 650
    except Exception:
        pass

    selected_note_id = {"value": None}
    alarm_dialog_open = {"value": False}

    # --------------------------------------------------------
    # Top/Sidebar Controls
    # --------------------------------------------------------

    current_time_text = ft.Text("", size=12, color="#475569")

    search_box = ft.TextField(
        hint_text="Search title, content, or location...",
        height=45,
        dense=True,
        border_radius=10,
    )

    category_filter = ft.Dropdown(
        label="Category",
        value="All",
        width=170,
        options=[
            ft.dropdown.Option("All"),
            ft.dropdown.Option("Personal"),
            ft.dropdown.Option("Work"),
            ft.dropdown.Option("Teaching"),
            ft.dropdown.Option("Research"),
            ft.dropdown.Option("Shopping"),
            ft.dropdown.Option("Ideas"),
            ft.dropdown.Option("Other"),
        ],
    )

    status_filter = ft.Dropdown(
        label="Status",
        value="Active",
        width=145,
        options=[
            ft.dropdown.Option("Active"),
            ft.dropdown.Option("Archived"),
            ft.dropdown.Option("All"),
        ],
    )

    notes_list = ft.ListView(expand=True, spacing=12, padding=10)

    # --------------------------------------------------------
    # Editor Controls
    # --------------------------------------------------------

    selected_note_label = ft.Text("New note", size=13, color="#64748b")

    title_field = ft.TextField(
        label="Title",
        hint_text="Enter note title",
        border_radius=10,
    )

    content_field = ft.TextField(
        label="Content",
        hint_text="Write your note here...",
        multiline=True,
        min_lines=8,
        max_lines=12,
        border_radius=10,
    )

    category_field = ft.Dropdown(
        label="Category",
        value="Personal",
        options=[
            ft.dropdown.Option("Personal"),
            ft.dropdown.Option("Work"),
            ft.dropdown.Option("Teaching"),
            ft.dropdown.Option("Research"),
            ft.dropdown.Option("Shopping"),
            ft.dropdown.Option("Ideas"),
            ft.dropdown.Option("Other"),
        ],
    )

    priority_field = ft.Dropdown(
        label="Priority",
        value="Medium",
        options=[
            ft.dropdown.Option("High"),
            ft.dropdown.Option("Medium"),
            ft.dropdown.Option("Low"),
        ],
    )

    color_field = ft.Dropdown(
        label="Note colour",
        value="#fff7cc",
        options=[
            ft.dropdown.Option("#fff7cc", "Yellow"),
            ft.dropdown.Option("#dcfce7", "Green"),
            ft.dropdown.Option("#dbeafe", "Blue"),
            ft.dropdown.Option("#fce7f3", "Pink"),
            ft.dropdown.Option("#f3e8ff", "Purple"),
            ft.dropdown.Option("#ffffff", "White"),
        ],
    )

    location_field = ft.TextField(
        label="Location",
        hint_text="Example: UQ Library, Home, Lab, Brisbane",
        border_radius=10,
    )

    timezone_field = ft.TextField(
        label="Timezone",
        value="Australia/Brisbane",
        hint_text="Example: Australia/Brisbane",
        border_radius=10,
    )

    due_field = ft.TextField(
        label="Due date and time",
        hint_text="YYYY-MM-DD HH:MM",
        border_radius=10,
    )

    email_field = ft.TextField(
        label="Email reminder recipient",
        hint_text="Optional email address",
        border_radius=10,
    )

    pinned_checkbox = ft.Checkbox(label="Pinned")
    archived_checkbox = ft.Checkbox(label="Archived")

    # --------------------------------------------------------
    # Message Helper
    # --------------------------------------------------------

    def show_message(message, error=False):
        try:
            page.snack_bar = ft.SnackBar(
                content=ft.Text(message),
                bgcolor="#dc2626" if error else "#2563eb",
            )
            page.snack_bar.open = True
            page.update()
        except Exception:
            print("[MESSAGE]", message)

    # --------------------------------------------------------
    # Form Helpers
    # --------------------------------------------------------

    def clear_editor():
        selected_note_id["value"] = None
        title_field.value = ""
        content_field.value = ""
        category_field.value = "Personal"
        priority_field.value = "Medium"
        color_field.value = "#fff7cc"
        location_field.value = ""
        timezone_field.value = "Australia/Brisbane"
        due_field.value = ""
        email_field.value = ""
        pinned_checkbox.value = False
        archived_checkbox.value = False
        selected_note_label.value = "New note"
        page.update()

    def collect_form_data():
        title = (title_field.value or "").strip()
        if not title:
            return None, "Title is required."

        due_text = (due_field.value or "").strip()
        timezone_text = (timezone_field.value or "").strip() or "Australia/Brisbane"

        if due_text:
            _, error = parse_due_datetime(due_text, timezone_text)
            if error:
                return None, error

        return {
            "title": title,
            "content": (content_field.value or "").strip(),
            "category": category_field.value or "Personal",
            "priority": priority_field.value or "Medium",
            "color": color_field.value or "#fff7cc",
            "location": (location_field.value or "").strip(),
            "timezone": timezone_text,
            "due_datetime": due_text,
            "email_to": (email_field.value or "").strip(),
            "pinned": bool(pinned_checkbox.value),
            "archived": bool(archived_checkbox.value),
        }, None

    def load_note_into_editor(note_id):
        note = db.get_note(note_id)
        if not note:
            show_message("Note not found.", error=True)
            return

        selected_note_id["value"] = note["id"]

        title_field.value = note["title"] or ""
        content_field.value = note["content"] or ""
        category_field.value = note["category"] or "Personal"
        priority_field.value = note["priority"] or "Medium"
        color_field.value = note["color"] or "#fff7cc"
        location_field.value = note["location"] or ""
        timezone_field.value = note["timezone"] or "Australia/Brisbane"
        due_field.value = note["due_datetime"] or ""
        email_field.value = note["email_to"] or ""
        pinned_checkbox.value = bool(note["pinned"])
        archived_checkbox.value = bool(note["archived"])

        selected_note_label.value = f"Editing note #{note['id']}"
        page.update()

    # --------------------------------------------------------
    # Notes Rendering
    # --------------------------------------------------------

    def build_note_card(note):
        title = note["title"] or "Untitled"
        content = note["content"] or "No content"
        category = note["category"] or "Other"
        priority = note["priority"] or "Medium"
        due = note["due_datetime"] or "No due date"
        location = note["location"] or "No location"
        timezone_name = note["timezone"] or "Australia/Brisbane"
        pinned = "📌 " if note["pinned"] else ""
        status = "Archived" if note["archived"] else "Active"

        # Use a left colour strip instead of Flet border APIs for compatibility.
        left_strip = ft.Container(width=6, bgcolor=priority_left_color(priority), border_radius=8)

        card_body = ft.Container(
            expand=True,
            bgcolor=note["color"] or "#ffffff",
            border_radius=16,
            padding=14,
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                f"{pinned}{title}",
                                size=16,
                                weight=ft.FontWeight.BOLD,
                                color="#0f172a",
                                expand=True,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Container(
                                bgcolor=priority_badge_color(priority),
                                padding=8,
                                border_radius=20,
                                content=ft.Text(priority, size=11, color="#0f172a"),
                            ),
                        ],
                    ),
                    ft.Text(
                        truncate_text(content, 140),
                        size=13,
                        color="#334155",
                    ),
                    ft.Divider(height=4, color="#e2e8f0"),
                    ft.Text(f"Category: {category}", size=12, color="#64748b"),
                    ft.Text(f"Due: {due}", size=12, color="#64748b"),
                    ft.Text(f"Timezone: {timezone_name}", size=12, color="#64748b"),
                    ft.Text(f"Location: {location}", size=12, color="#64748b"),
                    ft.Text(status, size=11, italic=True, color="#64748b"),
                ],
            ),
        )

        return ft.Container(
            bgcolor="#ffffff",
            border_radius=16,
            ink=True,
            on_click=lambda e, note_id=note["id"]: load_note_into_editor(note_id),
            content=ft.Row(
                spacing=0,
                controls=[
                    left_strip,
                    card_body,
                ],
            ),
        )

    def refresh_notes():
        notes_list.controls.clear()

        notes = db.get_notes(
            search=search_box.value or "",
            category=category_filter.value or "All",
            status=status_filter.value or "Active",
        )

        if not notes:
            notes_list.controls.append(
                ft.Container(
                    padding=30,
                    content=ft.Column(
                        controls=[
                            ft.Text("📝", size=45),
                            ft.Text("No notes found", size=18, color="#64748b"),
                            ft.Text("Create a new note or change the filters.", size=13, color="#94a3b8"),
                        ],
                    ),
                )
            )
        else:
            for note in notes:
                notes_list.controls.append(build_note_card(note))

        page.update()

    # --------------------------------------------------------
    # Actions
    # --------------------------------------------------------

    def new_note_click(e):
        clear_editor()

    def save_note_click(e):
        data, error = collect_form_data()
        if error:
            show_message(error, error=True)
            return

        note_id = selected_note_id["value"]

        if note_id is None:
            new_id = db.add_note(data)
            selected_note_id["value"] = new_id
            selected_note_label.value = f"Editing note #{new_id}"
            show_message("Note created.")
        else:
            old_note = db.get_note(note_id)
            db.update_note(note_id, data)

            if old_note and old_note.get("due_datetime") != data["due_datetime"]:
                db.reset_alarm_sent(note_id)

            show_message("Note updated.")

        refresh_notes()

    def delete_note_click(e):
        note_id = selected_note_id["value"]
        if note_id is None:
            show_message("No note selected.", error=True)
            return

        db.delete_note(note_id)
        clear_editor()
        refresh_notes()
        show_message("Note deleted.")

    def duplicate_note_click(e):
        data, error = collect_form_data()
        if error:
            show_message(error, error=True)
            return

        data["title"] = data["title"] + " Copy"
        new_id = db.add_note(data)
        load_note_into_editor(new_id)
        refresh_notes()
        show_message("Note duplicated.")

    def archive_toggle_click(e):
        if selected_note_id["value"] is None:
            show_message("No note selected.", error=True)
            return

        archived_checkbox.value = not bool(archived_checkbox.value)
        save_note_click(e)

    def export_click(e):
        output_file = db.export_json()
        show_message(f"Exported to {output_file}")

    def send_test_email_click(e):
        email_to = (email_field.value or "").strip()
        if not email_to:
            show_message("Enter an email address first.", error=True)
            return

        ok, msg = send_email_reminder(
            to_email=email_to,
            subject="Test email from Sticky Notes Manager",
            body="This is a test email reminder from your Flet sticky notes app.",
        )
        show_message(msg, error=not ok)

    def set_due_plus_minutes(minutes):
        due_dt = datetime.now() + timedelta(minutes=minutes)
        due_field.value = due_dt.strftime("%Y-%m-%d %H:%M")
        page.update()

    def filter_changed(e):
        refresh_notes()

    search_box.on_change = filter_changed
    category_filter.on_change = filter_changed
    status_filter.on_change = filter_changed

    # --------------------------------------------------------
    # Alarm Dialog
    # --------------------------------------------------------

    def show_alarm_dialog(note):
        if alarm_dialog_open["value"]:
            return

        alarm_dialog_open["value"] = True

        def close_alarm(e):
            try:
                alarm_dialog.open = False
                alarm_dialog_open["value"] = False
                page.update()
            except Exception:
                alarm_dialog_open["value"] = False

        def snooze_alarm(e):
            new_due = datetime.now() + timedelta(minutes=5)
            note_data = {
                "title": note["title"],
                "content": note["content"] or "",
                "category": note["category"] or "Personal",
                "priority": note["priority"] or "Medium",
                "color": note["color"] or "#fff7cc",
                "location": note["location"] or "",
                "timezone": note["timezone"] or "Australia/Brisbane",
                "due_datetime": new_due.strftime("%Y-%m-%d %H:%M"),
                "email_to": note["email_to"] or "",
                "pinned": bool(note["pinned"]),
                "archived": bool(note["archived"]),
            }
            db.update_note(note["id"], note_data)
            db.reset_alarm_sent(note["id"])
            close_alarm(e)
            refresh_notes()
            show_message("Alarm snoozed for 5 minutes.")

        alarm_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("⏰ Sticky Note Alarm"),
            content=ft.Column(
                tight=True,
                controls=[
                    ft.Text(note["title"], size=18, weight=ft.FontWeight.BOLD),
                    ft.Text(note["content"] or "No content"),
                    ft.Divider(),
                    ft.Text(f"Due: {note['due_datetime']}"),
                    ft.Text(f"Timezone: {note['timezone']}"),
                    ft.Text(f"Location: {note['location'] or 'No location'}"),
                ],
            ),
            actions=[
                ft.TextButton("Snooze 5 min", on_click=snooze_alarm),
                ft.ElevatedButton("Stop", on_click=close_alarm),
            ],
        )

        try:
            page.dialog = alarm_dialog
            alarm_dialog.open = True
            page.update()
        except Exception:
            alarm_dialog_open["value"] = False
            print("[ALARM]", note["title"])

    # --------------------------------------------------------
    # Background Loops
    # --------------------------------------------------------

    def alarm_loop():
        while True:
            try:
                now_utc = datetime.now(ZoneInfo("UTC"))
                due_notes = db.get_due_notes()

                for note in due_notes:
                    due_dt, error = parse_due_datetime(
                        note["due_datetime"] or "",
                        note["timezone"] or "Australia/Brisbane",
                    )

                    if error or due_dt is None:
                        continue

                    due_utc = due_dt.astimezone(ZoneInfo("UTC"))

                    if now_utc >= due_utc:
                        db.mark_alarm_sent(note["id"])

                        if note["email_to"]:
                            ok, msg = send_email_reminder(
                                to_email=note["email_to"],
                                subject=f"Sticky Note Reminder: {note['title']}",
                                body=(
                                    "Reminder from Sticky Notes Manager\n\n"
                                    f"Title: {note['title']}\n"
                                    f"Category: {note['category']}\n"
                                    f"Priority: {note['priority']}\n"
                                    f"Location: {note['location']}\n"
                                    f"Due: {note['due_datetime']} {note['timezone']}\n\n"
                                    f"{note['content']}"
                                ),
                            )
                            print("[EMAIL]", msg)

                        print("[ALARM]", note["title"])
                        show_alarm_dialog(note)
                        refresh_notes()

            except Exception as e:
                print("[ALARM ERROR]", e)

            time.sleep(20)

    def clock_loop():
        while True:
            try:
                now = datetime.now(ZoneInfo("Australia/Brisbane"))
                current_time_text.value = "Current time: " + now.strftime("%Y-%m-%d %H:%M:%S Australia/Brisbane")
                page.update()
            except Exception:
                pass
            time.sleep(1)

    threading.Thread(target=alarm_loop, daemon=True).start()
    threading.Thread(target=clock_loop, daemon=True).start()

    # --------------------------------------------------------
    # Layout
    # --------------------------------------------------------

    sidebar = ft.Container(
        width=430,
        bgcolor="#ffffff",
        padding=20,
        content=ft.Column(
            expand=True,
            spacing=14,
            controls=[
                ft.Row(
                    controls=[
                        ft.Column(
                            expand=True,
                            spacing=2,
                            controls=[
                                ft.Text("Sticky Notes", size=28, weight=ft.FontWeight.BOLD, color="#0f172a"),
                                ft.Text("Notes, alarms, location, timezone, email reminders", size=12, color="#64748b"),
                            ],
                        ),
                        ft.ElevatedButton("+", on_click=new_note_click),
                    ],
                ),
                current_time_text,
                search_box,
                ft.Row(controls=[category_filter, status_filter]),
                ft.Divider(),
                notes_list,
            ],
        ),
    )

    instructions_box = ft.Container(
        bgcolor="#f8fafc",
        border_radius=14,
        padding=16,
        content=ft.Column(
            spacing=6,
            controls=[
                ft.Text("Reminder instructions", weight=ft.FontWeight.BOLD, color="#0f172a"),
                ft.Text("Alarm format: YYYY-MM-DD HH:MM", size=13, color="#475569"),
                ft.Text("Example: 2026-05-28 15:30", size=13, color="#475569"),
                ft.Text("Timezone examples: Australia/Brisbane, Asia/Dubai, Europe/London, America/New_York", size=13, color="#475569"),
                ft.Text("Email reminder is optional and requires SMTP environment variables.", size=13, color="#475569"),
            ],
        ),
    )

    editor_card = ft.Container(
        bgcolor="#ffffff",
        border_radius=20,
        padding=24,
        content=ft.Column(
            spacing=16,
            controls=[
                title_field,
                content_field,
                ft.Row(controls=[category_field, priority_field, color_field]),
                ft.Row(controls=[location_field, timezone_field]),
                ft.Row(controls=[due_field, email_field]),
                ft.Row(
                    wrap=True,
                    controls=[
                        ft.OutlinedButton("Due in 1 min", on_click=lambda e: set_due_plus_minutes(1)),
                        ft.OutlinedButton("Due in 5 min", on_click=lambda e: set_due_plus_minutes(5)),
                        ft.OutlinedButton("Due in 1 hour", on_click=lambda e: set_due_plus_minutes(60)),
                    ],
                ),
                ft.Row(controls=[pinned_checkbox, archived_checkbox]),
                instructions_box,
                ft.Row(
                    wrap=True,
                    controls=[
                        ft.ElevatedButton("Save Note", on_click=save_note_click),
                        ft.OutlinedButton("Archive / Unarchive", on_click=archive_toggle_click),
                        ft.OutlinedButton("Send Test Email", on_click=send_test_email_click),
                        ft.OutlinedButton("Export JSON", on_click=export_click),
                    ],
                ),
            ],
        ),
    )

    editor_panel = ft.Container(
        expand=True,
        padding=30,
        content=ft.Column(
            expand=True,
            spacing=18,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Row(
                    controls=[
                        ft.Column(
                            expand=True,
                            spacing=2,
                            controls=[
                                ft.Text("Note Editor", size=26, weight=ft.FontWeight.BOLD, color="#0f172a"),
                                selected_note_label,
                            ],
                        ),
                        ft.Row(
                            wrap=True,
                            controls=[
                                ft.ElevatedButton("New", on_click=new_note_click),
                                ft.ElevatedButton("Save", on_click=save_note_click),
                                ft.OutlinedButton("Duplicate", on_click=duplicate_note_click),
                                ft.OutlinedButton("Delete", on_click=delete_note_click),
                            ],
                        ),
                    ],
                ),
                editor_card,
            ],
        ),
    )

    page.add(
        ft.Row(
            expand=True,
            spacing=0,
            controls=[
                sidebar,
                editor_panel,
            ],
        )
    )

    clear_editor()
    refresh_notes()


if __name__ == "__main__":
    run_app(main)
