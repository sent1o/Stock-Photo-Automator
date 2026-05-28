import sys
import os
import socket
from pathlib import Path
from dotenv import load_dotenv

from PyQt6.QtCore import QObject, QSettings, QThread, QTimer, pyqtSignal as Signal, Qt
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGridLayout, QLabel,
    QLineEdit, QMainWindow, QPushButton, QSizePolicy, QTextEdit,
    QVBoxLayout, QHBoxLayout, QWidget
)

from set_promt import PromptManager
from generate import FooocusGenerator
from upscale import FooocusUpscaler
from metadata import MetadataInjector

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") 
APP_ORG = "StockPhotoAutomator"
APP_NAME = "FooocusLandingUI"

FOLDER_IN = "1_To_Upscale"
FOLDER_OUT = "2_Ready_Stock"

def patch_fooocus_bat(base_fooocus_dir):
    bat_path = os.path.join(base_fooocus_dir, "run.bat")
    if not os.path.exists(bat_path):
        return
    with open(bat_path, 'r', encoding='utf-8') as f:
        content = f.read()
    if "--disable-in-browser" not in content:
        new_content = content.replace("entry_with_update.py", "entry_with_update.py --disable-in-browser")
        with open(bat_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

def is_fooocus_running():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(('127.0.0.1', 7865)) == 0

class BackendWorker(QObject):
    finished = Signal()
    status_update = Signal(str)
    
    def __init__(self, mode, root_folder, prompts_text="", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.root_folder = root_folder
        self.prompts_text = prompts_text

    def run(self):
        try:
            if self.mode == "generation":
                pm = PromptManager(self.root_folder)
                success, msg = pm.save_prompts(self.prompts_text)
                self.status_update.emit(msg)
                
                if not success:
                    return

                gen = FooocusGenerator(self.root_folder)
                gen.run_generation(status_callback=self.status_update.emit)
                
            elif self.mode == "upscale":
                base_dir = os.path.dirname(os.path.abspath(__file__))
                in_dir = os.path.join(base_dir, FOLDER_IN)
                out_dir = os.path.join(base_dir, FOLDER_OUT)

                upscaler = FooocusUpscaler(in_dir, self.root_folder, out_dir)
                success, msg = upscaler.process(status_callback=self.status_update.emit)
                
                if not success:
                    return

                self.status_update.emit("Инициализация модуля прошивки метаданных...")
                injector = MetadataInjector(out_dir, self.root_folder, OPENAI_API_KEY)
                injector.process(status_callback=self.status_update.emit)
                
        except Exception as e:
            self.status_update.emit(f"❌ Критический сбой процесса. Детали: {e}")
        finally:
            self.finished.emit()

class StockPhotoAutomatorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings(APP_ORG, APP_NAME)
        self.worker_thread = None
        self.worker = None
        self.status_history = ["", "", ""]

        self.setWindowTitle("Stock Photo Automator")
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_internal", "icon.ico")
        self.setWindowIcon(QIcon(icon_path))
        self.setMinimumSize(850, 700)
        self.resize(900, 750)

        self._build_ui()
        self._apply_styles()
        self._load_settings()

        self.update_status("Система инициализирована. Ожидание команд...")

        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self._check_dynamic_states)
        self.state_timer.start(2000)
        
        self._check_dynamic_states()

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(15)

        top_layout = QHBoxLayout()
        top_layout.addWidget(self._create_settings_block(), stretch=2)
        top_layout.addWidget(self._create_fooocus_control_block(), stretch=1)
        root.addLayout(top_layout)

        root.addWidget(self._create_main_action_block())
        root.addWidget(self._create_status_block(), stretch=0)
        self.setCentralWidget(central)

    def _create_block(self, title):
        block = QFrame()
        block.setObjectName("Block")
        layout = QVBoxLayout(block)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("BlockTitle")
        layout.addWidget(heading)
        return block, layout

    def _create_settings_block(self):
        block, layout = self._create_block("  ⛯ Настройки путей")

        path_badge = QFrame()
        path_badge.setObjectName("PathBadge")
        badge_layout = QHBoxLayout(path_badge)
        badge_layout.setContentsMargins(10, 5, 5, 5)
        badge_layout.setSpacing(10)

        label = QLabel("  Папка Fooocus: ")
        label.setObjectName("BadgeLabel")
        
        self.root_folder_input = QLineEdit()
        self.root_folder_input.setReadOnly(True)
        self.root_folder_input.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.root_folder_input.setObjectName("BadgeInput")

        self.browse_button = QPushButton("🗁")
        self.browse_button.setObjectName("SecondaryButton")
        self.browse_button.clicked.connect(self._browse_root_folder)

        badge_layout.addWidget(label)
        badge_layout.addWidget(self.root_folder_input, stretch=1)
        badge_layout.addWidget(self.browse_button)
        
        layout.addWidget(path_badge)
        folders_layout = QHBoxLayout()
        self.btn_open_in = QPushButton("✖ К проверке")
        self.btn_open_in.setObjectName("FolderButtonIn")
        self.btn_open_in.clicked.connect(lambda: self._open_folder(FOLDER_IN))
        
        self.btn_open_out = QPushButton("🗹 Апскейл")
        self.btn_open_out.setObjectName("FolderButtonOut")
        self.btn_open_out.clicked.connect(lambda: self._open_folder(FOLDER_OUT))
        
        folders_layout.addWidget(self.btn_open_in)
        folders_layout.addWidget(self.btn_open_out)
        layout.addLayout(folders_layout)
        
        return block

    def _create_fooocus_control_block(self):
        block, layout = self._create_block(" ┆ Управление Fooocus")
        
        self.start_server_button = QPushButton("Запустить Fooocus ⏻")
        self.start_server_button.setObjectName("FooocusButton")
        self.start_server_button.setMinimumHeight(55)
        self.start_server_button.clicked.connect(self._start_fooocus_server)
        
        self.start_manual_button = QPushButton()
        self.start_manual_button.setObjectName("SecondaryButton")
        self.start_manual_button.setMinimumHeight(45)
        self.start_manual_button.clicked.connect(self._start_fooocus_manual)
        
        btn_layout = QHBoxLayout(self.start_manual_button)
        btn_layout.setContentsMargins(15, 0, 15, 0)
        
        text_label = QLabel("Открыть веб-интерфейс\nдля ручного использования")
        text_label.setObjectName("ManualBtnText")
        text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        icon_label = QLabel("✦")
        icon_label.setObjectName("ManualBtnIcon")
        icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        btn_layout.addWidget(text_label, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        btn_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        layout.addWidget(self.start_server_button)
        layout.addWidget(self.start_manual_button)
        layout.addStretch()
        return block

    def _create_main_action_block(self):
        block, layout = self._create_block(" ❯❯❯❯ Генерация и Апскейл")

        self.prompts_input = QTextEdit()
        self.prompts_input.setPlaceholderText("Введите список промптов. Каждый промпт должен начинаться с новой строки...")
        layout.addWidget(self.prompts_input, stretch=1) 

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(15)

        gen_layout = QVBoxLayout()
        self.generate_button = QPushButton("▶︎ Запустить генерацию")
        self.generate_button.setObjectName("PrimaryButton")
        self.generate_button.setMinimumHeight(55)
        self.generate_button.clicked.connect(self._start_generation)
        
        gen_hint = QLabel("🛈 Добавьте промпты для старта пакетной генерации.")
        gen_hint.setObjectName("HistoryStatus")
        gen_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        gen_hint.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        
        gen_layout.addWidget(self.generate_button)
        gen_layout.addWidget(gen_hint)

        up_layout = QVBoxLayout()
        self.upscale_button = QPushButton("🗐 Апскейл и прошивка метаданных")
        self.upscale_button.setObjectName("SuccessButton")
        self.upscale_button.setMinimumHeight(55)
        self.upscale_button.clicked.connect(self._start_upscale_metadata)
        
        up_hint = QLabel(f"🛈 Фото для обработки должны быть в папке {FOLDER_IN}.")
        up_hint.setObjectName("HistoryStatus")
        up_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        up_hint.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        up_layout.addWidget(self.upscale_button)
        up_layout.addWidget(up_hint)

        buttons_layout.addLayout(gen_layout)
        buttons_layout.addLayout(up_layout)

        layout.addLayout(buttons_layout)
        return block

    def _create_status_block(self):
        block, layout = self._create_block(" ☰ Журнал процесса")
        
        log_layout = QVBoxLayout()
        log_layout.setSpacing(0)
        log_layout.setContentsMargins(0, 0, 0, 0)
        
        self.log_history = QTextEdit()
        self.log_history.setObjectName("LogHistory")
        self.log_history.setReadOnly(True)
        self.log_history.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.log_history.setFixedHeight(95)
        self.log_history.setText("\n\n\n\n")
        
        self.current_status_label = QLabel("Ожидание...")
        self.current_status_label.setObjectName("CurrentStatus")
        self.current_status_label.setWordWrap(True)
        
        log_layout.addWidget(self.log_history)
        log_layout.addWidget(self.current_status_label)
        
        layout.addLayout(log_layout)
        return block

    def update_status(self, text):
        old_text = self.current_status_label.text()
        
        if old_text and old_text != "Ожидание...":
            self.log_history.append(old_text)
            
        self.current_status_label.setText(text)
        
        scrollbar = self.log_history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _check_dynamic_states(self):
        root_folder = self.root_folder_input.text().strip()
        has_fooocus_dir = os.path.exists(root_folder) and bool(root_folder)
        self.start_server_button.setEnabled(has_fooocus_dir)
        self.start_manual_button.setEnabled(has_fooocus_dir)

        is_running = is_fooocus_running()

        base_dir = os.path.dirname(os.path.abspath(__file__))
        in_dir = os.path.join(base_dir, FOLDER_IN)
        has_photos = False
        if os.path.exists(in_dir):
            has_photos = any(f.lower().endswith(('.png', '.jpg', '.jpeg')) for f in os.listdir(in_dir))
            
        if has_photos:
            self.btn_open_in.setText("🗹 К проверке")
            self.btn_open_in.setProperty("has_files", True)
        else:
            self.btn_open_in.setText("✖ К проверке")
            self.btn_open_in.setProperty("has_files", False)
            
        self.btn_open_in.style().unpolish(self.btn_open_in)
        self.btn_open_in.style().polish(self.btn_open_in)

        out_dir = os.path.join(base_dir, FOLDER_OUT)
        has_out_photos = False
        if os.path.exists(out_dir):
            has_out_photos = any(f.lower().endswith(('.png', '.jpg', '.jpeg')) for f in os.listdir(out_dir))
            
        if has_out_photos:
            self.btn_open_out.setText("🗹 Апскейл")
            self.btn_open_out.setProperty("has_files", True)
        else:
            self.btn_open_out.setText("✖ Апскейл")
            self.btn_open_out.setProperty("has_files", False)
            
        self.btn_open_out.style().unpolish(self.btn_open_out)
        self.btn_open_out.style().polish(self.btn_open_out)

        has_prompts = bool(self.prompts_input.toPlainText().strip())

        if self.worker_thread and self.worker_thread.isRunning():
            return

        self.generate_button.setEnabled(is_running and has_prompts)
        self.upscale_button.setEnabled(is_running and has_photos)

    def _open_folder(self, folder_name):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_dir, folder_name)
        if not os.path.exists(path):
            os.makedirs(path)
        os.startfile(path)

    def _start_fooocus_server(self):
        if is_fooocus_running():
            self.update_status("⚠️ Сервер Fooocus уже запущен и работает на порту 7865.")
            return

        import subprocess
        root_folder = self.root_folder_input.text().strip()
        bat_path = os.path.join(root_folder, "run.bat")
        
        self.update_status("Инициализация локального сервера Fooocus...")
        patch_fooocus_bat(root_folder)
        
        try:
            subprocess.Popen(["cmd.exe", "/c", "start", "", bat_path], cwd=root_folder, shell=True)
            self.update_status("Запуск сервера в фоновом режиме. Ожидание готовности...")
        except Exception as e:
            self.update_status(f"❌ Ошибка запуска сервера: {e}")

    def _start_fooocus_manual(self):
        import webbrowser
        
        if not is_fooocus_running():
            self.update_status("⚠️ Сервер Fooocus еще не запущен! Сначала запустите его.")
            return

        self.update_status("Открываю интерфейс Fooocus в браузере...")
        try:
            webbrowser.open("http://127.0.0.1:7865")
            self.update_status("✅ Интерфейс открыт в вашем браузере.")
        except Exception as e:
            self.update_status(f"❌ Ошибка открытия браузера: {e}")

    def _start_generation(self):
        prompts_text = self.prompts_input.toPlainText()
        self._run_worker("generation", self.generate_button, prompts_text=prompts_text)

    def _start_upscale_metadata(self):
        if not OPENAI_API_KEY:
            self.update_status("❌ Ошибка: Ключ OpenAI API не найден в файле .env!")
            return
        self._run_worker("upscale", self.upscale_button)

    def _run_worker(self, mode, disabled_button, prompts_text=""):
        if self.worker_thread and self.worker_thread.isRunning():
            return

        root_folder = self.root_folder_input.text().strip()

        self.generate_button.setDisabled(True)
        self.upscale_button.setDisabled(True)

        self.worker_thread = QThread(self)
        self.worker = BackendWorker(mode=mode, root_folder=root_folder, prompts_text=prompts_text)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.status_update.connect(self.update_status)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.finished.connect(self._on_worker_finished)

        self.worker_thread.start()

    def _on_worker_finished(self):
        self.worker_thread = None
        self.worker = None
        self._check_dynamic_states()

    def _apply_styles(self):
        self.setFont(QFont("Segoe UI", 10))
        self.setStyleSheet(
            '''
            QMainWindow, QWidget { background: #18191c; color: #d4d4d4; }
            QFrame#Block { background: #222428; border-radius: 12px; }
            QLabel#BlockTitle { color: #ffffff; font-size: 13pt; }
            QLabel#HistoryStatus { background: transparent; color: #666666; font-size: 9pt; }
            QTextEdit#LogHistory { background: transparent; border: none; border-radius: 0px; border-left: 4px solid #00c6ff; color: #666666; font-size: 9pt; padding: 0px 8px; }
            QTextEdit#LogHistory QScrollBar:vertical { background: #222428; width: 6px; }
            QTextEdit#LogHistory QScrollBar::track:vertical { background: #222428; border: none; }
            QTextEdit#LogHistory QScrollBar::handle:vertical { background: #444; border-radius: 3px; }
            QTextEdit#LogHistory QScrollBar::add-line:vertical, QTextEdit#LogHistory QScrollBar::sub-line:vertical { height: 0px; }
            QTextEdit#LogHistory QScrollBar::add-page:vertical, QTextEdit#LogHistory QScrollBar::sub-page:vertical { background: #222428; }
            QLabel#CurrentStatus { background: #121315; border-left: 4px solid #00c6ff; color: #00c6ff; font-family: Consolas, monospace; font-size: 10pt; padding: 10px 12px; border-top-right-radius: 6px; border-bottom-right-radius: 6px; }
            QLineEdit, QTextEdit { background: #121315; border: 1px solid #333; border-radius: 6px; padding: 8px; }
            QPushButton { border-radius: 8px; font-weight: bold; color: white; padding: 6px; }
            QPushButton:disabled { background: #333333; color: #666; }
            QPushButton#PrimaryButton, QPushButton#SuccessButton { border: 1px solid transparent; font-size: 11pt; }
            QPushButton#PrimaryButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00c6ff, stop:1 #0072ff); }
            QPushButton#PrimaryButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0072ff, stop:1 #00c6ff); border: 1px solid #ffffff; }
            QPushButton#SuccessButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ff7e5f, stop:1 #feb47b); }
            QPushButton#SuccessButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #feb47b, stop:1 #ff7e5f); border: 1px solid #ffffff; }
            QPushButton#PrimaryButton:disabled, QPushButton#SuccessButton:disabled { background: #2a2d32; color: #555555; border: 1px dashed #444444; }
            QPushButton#FooocusButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #11998e, stop:1 #38ef7d); font-size: 16pt; font-weight: bold; padding-bottom: 10px; }
            QPushButton#FooocusButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #38ef7d, stop:1 #11998e); }
            QPushButton#SecondaryButton { background: #2c2f35; border: 1px solid #444; font-size: 8pt; }
            QPushButton#SecondaryButton:hover { background: #3c4048; }
            QLabel#ManualBtnText { background: transparent; font-size: 10pt; font-weight: normal; color: #d4d4d4; }
            QLabel#ManualBtnIcon { background: transparent; font-size: 18pt; color: #ffffff; }
            QPushButton#FolderButtonIn, QPushButton#FolderButtonOut { background: transparent; font-size: 11pt; border: 1px solid #444; color: #888; }
            QPushButton#FolderButtonIn:hover, QPushButton#FolderButtonOut:hover { border: 1px solid #666; color: #aaa; background: rgba(255, 255, 255, 0.05); }
            QPushButton#FolderButtonIn[has_files="true"] { border: 1px solid #00c6ff; color: #00c6ff; }
            QPushButton#FolderButtonIn[has_files="true"]:hover { background: rgba(0, 198, 255, 0.1); }
            QPushButton#FolderButtonOut[has_files="true"] { border: 1px solid #ff7e5f; font-size: 11pt; color: #ff7e5f; }
            QPushButton#FolderButtonOut[has_files="true"]:hover { background: rgba(255, 126, 95, 0.1); }
            QFrame#PathBadge { background: #121315; border: 1px solid #333; border-radius: 8px; }
            QLabel#BadgeLabel { color: #888; font-weight: bold; }
            QLineEdit#BadgeInput { background: transparent; border: none; color: #d4d4d4; padding: 0px; }
            '''
        )

    def _load_settings(self):
        root = self.settings.value("root_folder", "", str)
        self.root_folder_input.setText(root)
        self._load_prompts_to_ui(root)

    def _save_settings(self):
        self.settings.setValue("root_folder", self.root_folder_input.text())

    def _browse_root_folder(self):
        start_dir = self.root_folder_input.text() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Выберите корневую папку Fooocus", start_dir)
        if folder:
            self.root_folder_input.setText(folder)
            self._save_settings()
            self._load_prompts_to_ui(folder)
            
    def _load_prompts_to_ui(self, root_folder):
        if os.path.exists(root_folder):
            pm = PromptManager(root_folder)
            success, text = pm.load_prompts()
            if success and text:
                self.prompts_input.setText(text)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setOrganizationName(APP_ORG)
    app.setApplicationName(APP_NAME)
    window = StockPhotoAutomatorWindow()
    window.show()
    sys.exit(app.exec())