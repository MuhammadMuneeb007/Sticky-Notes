import sys
import sqlite3
import json
from datetime import datetime
import pygame  # Replace winsound with pygame
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLabel, QLineEdit, QFrame, QScrollArea,
    QGridLayout, QGraphicsDropShadowEffect, QComboBox, QMessageBox,
    QDialog, QDateTimeEdit
)
from PyQt6.QtCore import Qt, QSize, QTimer, QDateTime, pyqtSignal, QTime
from PyQt6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor, QIcon
import sys
import sqlite3
import json
from datetime import datetime
import pygame
from pathlib import Path


class Database:
    def __init__(self):
        self.conn = sqlite3.connect('sticky_notes.db')
        self.create_tables()

    def create_tables(self):
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT,
                category TEXT,
                color TEXT,
                pinned BOOLEAN,
                archived BOOLEAN,
                alarm TIMESTAMP,
                formatting TEXT,
                created_at TIMESTAMP
            )
        ''')
        self.conn.commit()

    def add_note(self, note_data):
        query = '''
            INSERT INTO notes (content, category, color, pinned, archived, 
                             alarm, formatting, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        '''
        self.conn.execute(query, (
            note_data['content'],
            note_data['category'],
            note_data['color'],
            note_data['pinned'],
            note_data['archived'],
            note_data['alarm'],
            json.dumps(note_data['formatting']),
            datetime.now().isoformat()
        ))
        self.conn.commit()
        return self.conn.execute('SELECT last_insert_rowid()').fetchone()[0]

    def update_note(self, note_id, note_data):
        query = '''
            UPDATE notes 
            SET content=?, category=?, color=?, pinned=?, archived=?,
                alarm=?, formatting=?
            WHERE id=?
        '''
        self.conn.execute(query, (
            note_data['content'],
            note_data['category'],
            note_data['color'],
            note_data['pinned'],
            note_data['archived'],
            note_data['alarm'],
            json.dumps(note_data['formatting']),
            note_id
        ))
        self.conn.commit()

    def get_notes(self, archived=False, category=None, search=None):
        query = 'SELECT * FROM notes WHERE archived = ?'
        params = [archived]
        
        if category and category != 'All':
            query += ' AND category = ?'
            params.append(category)
        
        if search:
            query += ' AND content LIKE ?'
            params.append(f'%{search}%')
        
        query += ' ORDER BY pinned DESC, created_at DESC'
        return self.conn.execute(query, params).fetchall()

    def delete_note(self, note_id):
        self.conn.execute('DELETE FROM notes WHERE id=?', (note_id,))
        self.conn.commit()

class ModernButton(QPushButton):
    def __init__(self, text, primary=False, parent=None):
        super().__init__(text, parent)
        self.primary = primary
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_style()

    def update_style(self):
        if self.primary:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #2563eb;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 0 20px;
                    font-size: 14px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #1d4ed8;
                }
                QPushButton:pressed {
                    background-color: #1e40af;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #f8fafc;
                    color: #475569;
                    border: 1px solid #e2e8f0;
                    border-radius: 8px;
                    padding: 0 20px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #f1f5f9;
                    border-color: #cbd5e1;
                }
            """)

class StickyNote(QFrame):
    noteChanged = pyqtSignal(dict)
    deleteRequested = pyqtSignal(int)

    def __init__(self, note_data=None, parent=None):
        super().__init__(parent)
        self.note_data = note_data or {
            'id': None,
            'content': '',
            'category': 'Uncategorized',
            'color': '#FFFEF8',
            'pinned': False,
            'archived': False,
            'alarm': None,
            'formatting': {'bold': False, 'italic': False, 'underline': False}
        }
        self.setup_ui()
        self.setup_autosave()

    def setup_ui(self):
        self.setFixedSize(240, 240)
        self.setObjectName("stickyNote")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Top bar
        top_bar = QHBoxLayout()
        
        # Pin button
        self.pin_btn = QPushButton("📌")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setChecked(self.note_data['pinned'])
        self.pin_btn.clicked.connect(self.toggle_pin)
        
        # Bell button
        self.bell_btn = QPushButton("🔔")
        self.bell_btn.clicked.connect(self.set_alarm)
        
        # Category dropdown
        self.category_combo = QComboBox()
        self.category_combo.addItems(['Uncategorized', 'Personal', 'Work', 'Shopping', 'Ideas'])
        self.category_combo.setCurrentText(self.note_data['category'])
        self.category_combo.currentTextChanged.connect(self.update_category)
        
        for btn in [self.pin_btn, self.bell_btn]:
            btn.setFlat(True)
            btn.setFixedSize(24, 24)
            btn.setStyleSheet("""
                QPushButton {
                    color: #666;
                    background: transparent;
                    border: none;
                    font-size: 18px;
                }
                QPushButton:checked {
                    color: #007AFF;
                }
            """)
            
        self.category_combo.setStyleSheet("""
            QComboBox {
                border: none;
                background: transparent;
                color: #999;
                font-size: 13px;
            }
            QComboBox::drop-down {
                border: none;
            }
        """)
        
        top_bar.addWidget(self.pin_btn)
        top_bar.addWidget(self.bell_btn)
        top_bar.addStretch()
        top_bar.addWidget(self.category_combo)
        layout.addLayout(top_bar)

        # Text area
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Take a note...")
        self.text_edit.setFrameShape(QFrame.Shape.NoFrame)
        self.text_edit.setText(self.note_data['content'])
        self.text_edit.textChanged.connect(self.text_changed)
        layout.addWidget(self.text_edit)

        # Formatting toolbar
        toolbar = QHBoxLayout()
        
        # Bold button
        self.bold_btn = QPushButton("B")
        self.bold_btn.setCheckable(True)
        self.bold_btn.setChecked(self.note_data['formatting']['bold'])
        self.bold_btn.clicked.connect(self.toggle_bold)
        
        # Italic button
        self.italic_btn = QPushButton("I")
        self.italic_btn.setCheckable(True)
        self.italic_btn.setChecked(self.note_data['formatting']['italic'])
        self.italic_btn.clicked.connect(self.toggle_italic)
        
        # Underline button
        self.underline_btn = QPushButton("U")
        self.underline_btn.setCheckable(True)
        self.underline_btn.setChecked(self.note_data['formatting']['underline'])
        self.underline_btn.clicked.connect(self.toggle_underline)
        
        # Delete button
        self.delete_btn = QPushButton("🗑")
        self.delete_btn.clicked.connect(self.request_delete)

        for btn in [self.bold_btn, self.italic_btn, self.underline_btn, self.delete_btn]:
            btn.setFlat(True)
            btn.setFixedSize(28, 28)
            btn.setStyleSheet("""
                QPushButton {
                    color: #999;
                    font-weight: 500;
                    background: transparent;
                    border: none;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: rgba(0, 0, 0, 0.05);
                    border-radius: 4px;
                }
                QPushButton:checked {
                    color: #3981F7;
                }
            """)
            toolbar.addWidget(btn)
            
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Note styling
        self.setStyleSheet(f"""
            #stickyNote {{
                background-color: rgba(255, 255, 255, 0.95);
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }}
            QTextEdit {{
                background: transparent;
                color: #334155;
                font-size: 14px;
                line-height: 1.5;
            }}
            QTextEdit[readOnly="true"] {{
                color: #64748b;
            }}
        """)

        # Add shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setColor(QColor(0, 0, 0, 15))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

        self.apply_formatting()

    def setup_autosave(self):
        self.autosave_timer = QTimer()
        self.autosave_timer.setInterval(1000)  # 1 second
        self.autosave_timer.timeout.connect(self.save_note)
        self.autosave_timer.start()

    def text_changed(self):
        self.note_data['content'] = self.text_edit.toPlainText()
        self.emit_change()

    def toggle_pin(self, checked):
        self.note_data['pinned'] = checked
        self.emit_change()

    def toggle_bold(self, checked):
        self.note_data['formatting']['bold'] = checked
        self.apply_formatting()
        self.emit_change()

    def toggle_italic(self, checked):
        self.note_data['formatting']['italic'] = checked
        self.apply_formatting()
        self.emit_change()

    def toggle_underline(self, checked):
        self.note_data['formatting']['underline'] = checked
        self.apply_formatting()
        self.emit_change()

    def apply_formatting(self):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold if self.note_data['formatting']['bold'] else QFont.Weight.Normal)
        fmt.setFontItalic(self.note_data['formatting']['italic'])
        fmt.setFontUnderline(self.note_data['formatting']['underline'])
        
        cursor = self.text_edit.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.mergeCharFormat(fmt)

    def update_category(self, category):
        self.note_data['category'] = category
        self.emit_change()

    def set_alarm(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Set Alarm")
        dialog.setWindowIcon(QIcon("dialog_icon.png"))
        layout = QVBoxLayout(dialog)

        datetime_edit = QDateTimeEdit(QDateTime.currentDateTime())
        datetime_edit.setCalendarPopup(True)
        datetime_edit.setMinimumDateTime(QDateTime.currentDateTime())  # Can't set past alarms
        layout.addWidget(datetime_edit)

        save_btn = ModernButton("Set Alarm", primary=True)
        save_btn.clicked.connect(dialog.accept)
        layout.addWidget(save_btn)

        clear_btn = ModernButton("Clear Alarm")
        clear_btn.clicked.connect(lambda: self.clear_alarm(dialog))
        layout.addWidget(clear_btn)

        if dialog.exec():
            self.note_data['alarm'] = datetime_edit.dateTime().toString(Qt.DateFormat.ISODate)
            self.bell_btn.setStyleSheet(self.bell_btn.styleSheet() + "QPushButton { color: #3981F7; }")
            self.emit_change()

    def clear_alarm(self, dialog):
        self.note_data['alarm'] = None
        self.bell_btn.setStyleSheet(self.bell_btn.styleSheet().replace("color: #3981F7;", "color: #999;"))
        self.emit_change()
        dialog.close()

    def request_delete(self):
        if self.note_data['id']:
            self.deleteRequested.emit(self.note_data['id'])

    def save_note(self):
        if self.note_data.get('id'):
            self.emit_change()

    def emit_change(self):
        self.noteChanged.emit(self.note_data)

class StickyNotesApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.show_archived = False
        self.current_category = 'All'
        
        # Initialize pygame mixer
        pygame.mixer.init()
        self.sound_file = str(Path(__file__).parent / 'alarm.mp3')  # Default alarm sound
        self.volume = 0.5  # Default volume 50%
        self.alarm_playing = False
        self.alarm_sound = None
        
        self.setup_ui()
        self.load_notes()
        
        # Add alarm checker timer
        self.alarm_timer = QTimer()
        self.alarm_timer.timeout.connect(self.check_alarms)
        self.alarm_timer.start(60000)  # Check every minute
        
        # Create a repeating timer for continuous beeping
        self.beep_timer = QTimer()
        self.beep_timer.timeout.connect(self.play_beep)

        self.setWindowIcon(QIcon("app_icon.png"))

    def play_beep(self):
        if self.alarm_playing:
            try:
                pygame.mixer.Sound.play(self.alarm_sound)
            except:
                QApplication.beep()

    def check_alarms(self):
        current_time = QDateTime.currentDateTime()
        notes = self.db.get_notes(archived=False)
        
        for note in notes:
            alarm_time = note[6]  # alarm field from database
            if alarm_time:
                alarm_dt = QDateTime.fromString(alarm_time, Qt.DateFormat.ISODate)
                if alarm_dt.isValid() and abs(current_time.secsTo(alarm_dt)) < 60:
                    self.trigger_alarm(note[1])  # Pass note content
                    
                    # Update note to clear the alarm
                    note_data = {
                        'content': note[1],
                        'category': note[2],
                        'color': note[3],
                        'pinned': note[4],
                        'archived': note[5],
                        'alarm': None,  # Clear the alarm
                        'formatting': json.loads(note[7])
                    }
                    self.db.update_note(note[0], note_data)

    def trigger_alarm(self, note_content):
        try:
            # Setup continuous alarm sound
            self.alarm_playing = True
            if Path(self.sound_file).exists():
                self.alarm_sound = pygame.mixer.Sound(self.sound_file)
                self.alarm_sound.set_volume(self.volume)
            else:
                # Fallback to system beep
                self.alarm_sound = None
            
            # Start continuous beeping
            self.beep_timer.start(2000)  # Beep every 2 seconds
            
            # Show notification with stop button
            msg = QMessageBox()
            msg.setWindowTitle("⏰ ALARM - Sticky Note")
            msg.setText(f"<h3>⚠️ Active Alarm!</h3><p>{note_content[:200]}...</p>")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowIcon(QIcon("alarm_icon.png"))
            
            # Add stop and snooze buttons
            stop_btn = msg.addButton("🛑 Stop Alarm", QMessageBox.ButtonRole.AcceptRole)
            snooze_btn = msg.addButton("💤 Snooze (5 min)", QMessageBox.ButtonRole.ActionRole)
            
            # Style the dialog to be more attention-grabbing
            msg.setStyleSheet("""
                QMessageBox {
                    background-color: #FFE0B2;
                }
                QMessageBox QLabel {
                    color: #333;
                    min-width: 300px;
                    font-size: 14px;
                }
                QPushButton {
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #f0f0f0;
                }
            """)
            
            # Keep dialog on top
            msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            
            result = msg.exec()
            
            # Stop the alarm
            self.stop_alarm()
            
            # Handle snooze if requested
            if msg.clickedButton() == snooze_btn:
                self.snooze_alarm(note_content)
                
        except Exception as e:
            print(f"Error playing alarm sound: {e}")
            QApplication.beep()

    def stop_alarm(self):
        self.alarm_playing = False
        self.beep_timer.stop()
        if self.alarm_sound:
            self.alarm_sound.stop()
        pygame.mixer.stop()

    def snooze_alarm(self, note_content):
        # Stop current alarm
        self.stop_alarm()
        
        # Reschedule alarm for 5 minutes later
        new_alarm_time = QDateTime.currentDateTime().addSecs(300)
        # Find the note and update its alarm time
        notes = self.db.get_notes(archived=False)
        for note in notes:
            if note[1] == note_content:  # Match by content
                note_data = {
                    'content': note[1],
                    'category': note[2],
                    'color': note[3],
                    'pinned': note[4],
                    'archived': note[5],
                    'alarm': new_alarm_time.toString(Qt.DateFormat.ISODate),
                    'formatting': json.loads(note[7])
                }
                self.db.update_note(note[0], note_data)
                break

    def setup_ui(self):
        self.setWindowTitle("Modern Sticky Notes")
        self.setMinimumSize(1000, 700)
        
        # Main widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # Main layout
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # Header
        header = QHBoxLayout()
        title = QLabel("Professional Notes")
        title.setObjectName("mainTitle")
        title.setStyleSheet("""
            QLabel#mainTitle {
                font-size: 28px;
                font-weight: 600;
                color: #1e293b;
                margin: 20px 0;
            }
        """)
        header.addWidget(title)
        header.addStretch()
        
        new_note_btn = ModernButton("+ New Note", primary=True)
        new_note_btn.clicked.connect(self.add_note)
        header.addWidget(new_note_btn)
        layout.addLayout(header)

        # Search and filters
        filters = QHBoxLayout()
        
        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search notes...")
        self.search_box.setFixedHeight(36)
        self.search_box.textChanged.connect(self.filter_notes)
        self.search_box.setStyleSheet("""
            QLineEdit {
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                background-color: white;
                color: #475569;
                font-size: 14px;
                padding: 0 12px;
            }
            QLineEdit:focus {
                border-color: #2563eb;
                background-color: #f8fafc;
            }
        """)
        filters.addWidget(self.search_box)
        
        # Category filter
        self.category_filter = QComboBox()
        self.category_filter.addItem("All")
        self.category_filter.addItems(['Personal', 'Work', 'Shopping', 'Ideas', 'Uncategorized'])
        self.category_filter.setFixedHeight(36)
        self.category_filter.setFixedWidth(120)
        self.category_filter.currentTextChanged.connect(self.filter_notes)
        self.category_filter.setStyleSheet("""
            QComboBox {
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                background-color: white;
                color: #475569;
                font-size: 14px;
                padding: 0 12px;
            }
            QComboBox:focus {
                border-color: #2563eb;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
            }
        """)
        filters.addWidget(self.category_filter)
        
        # Archive button
        self.archive_btn = ModernButton("Show Archived")
        self.archive_btn.clicked.connect(self.toggle_archived)
        filters.addWidget(self.archive_btn)
        
        filters.addStretch()
        layout.addLayout(filters)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: #f8fafc;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #cbd5e1;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #94a3b8;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)
        layout.addWidget(scroll)

        # Notes container
        notes_widget = QWidget()
        self.notes_layout = QGridLayout(notes_widget)
        self.notes_layout.setSpacing(24)
        scroll.setWidget(notes_widget)

        # Window styling
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #f8fafc, stop: 1 #f1f5f9
                );
            }
            QLabel#mainTitle {
                font-size: 28px;
                font-weight: 600;
                color: #1e293b;
                margin-left: 12px;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: #f8fafc;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #cbd5e1;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #94a3b8;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

    def add_note(self):
        note = StickyNote()
        note.noteChanged.connect(self.save_note)
        note.deleteRequested.connect(self.delete_note)
        
        # Find first empty cell
        row = self.notes_layout.rowCount()
        col = self.notes_layout.columnCount()
        
        for i in range(row):
            for j in range(3):  # 3 columns
                if self.notes_layout.itemAtPosition(i, j) is None:
                    self.notes_layout.addWidget(note, i, j)
                    break
            else:
                continue
            break
        else:
            # No empty cells found, add to new row
            self.notes_layout.addWidget(note, row, 0)
        
        # Save new note to database
        note_id = self.db.add_note(note.note_data)
        note.note_data['id'] = note_id

    def save_note(self, note_data):
        if note_data.get('id'):
            self.db.update_note(note_data['id'], note_data)

    def delete_note(self, note_id):
        reply = QMessageBox.question(
            self, 'Delete Note',
            'Are you sure you want to delete this note?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_note(note_id)
            self.load_notes()

    def toggle_archived(self):
        self.show_archived = not self.show_archived
        self.archive_btn.setText("Show Active" if self.show_archived else "Show Archived")
        self.load_notes()

    def filter_notes(self):
        self.current_category = self.category_filter.currentText()
        self.load_notes()

    def clear_notes_layout(self):
        while self.notes_layout.count():
            item = self.notes_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def load_notes(self):
        self.clear_notes_layout()
        
        # Get filtered notes from database
        notes = self.db.get_notes(
            archived=self.show_archived,
            category=self.current_category if self.current_category != 'All' else None,
            search=self.search_box.text()
        )

        if not notes:
            # Show empty state
            empty_label = QLabel("No notes found")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("""
                QLabel {
                    color: #666;
                    font-size: 16px;
                    padding: 40px;
                }
            """)
            self.notes_layout.addWidget(empty_label, 0, 1)
            
            # Add empty note placeholders
            positions = [(i, j) for i in range(2) for j in range(3)]
            for row, col in positions:
                note = StickyNote()
                self.notes_layout.addWidget(note, row, col)
        else:
            # Create note widgets
            for i, note_data in enumerate(notes):
                note = StickyNote({
                    'id': note_data[0],
                    'content': note_data[1],
                    'category': note_data[2],
                    'color': note_data[3],
                    'pinned': note_data[4],
                    'archived': note_data[5],
                    'alarm': note_data[6],
                    'formatting': json.loads(note_data[7])
                })
                note.noteChanged.connect(self.save_note)
                note.deleteRequested.connect(self.delete_note)
                
                row = i // 3
                col = i % 3
                self.notes_layout.addWidget(note, row, col)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Set application-wide font
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    window = StickyNotesApp()
    window.show()
    sys.exit(app.exec())

