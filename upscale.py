import os
import time
import glob
import shutil
import socket
import subprocess
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

class FooocusUpscaler:
    def __init__(self, input_folder, base_fooocus_dir, output_folder):
        self.input_folder = input_folder
        self.fooocus_dir = os.path.join(base_fooocus_dir, "Fooocus")
        self.output_folder = output_folder
        self.status_callback = None

    def _log(self, message):
        """Передает лог в UI, если подключен коллбек, иначе печатает в консоль"""
        if self.status_callback:
            self.status_callback(message)
        else:
            print(message)

    def _ensure_playwright_browsers(self):
        """Проверяет и устанавливает Chromium для Playwright, если его нет"""
        try:
            subprocess.run(["playwright", "install", "chromium"], check=True, capture_output=True)
        except Exception:
            self._log("Установка браузера для Playwright...")
            subprocess.run(["python", "-m", "playwright", "install", "chromium"], capture_output=True)

    def wait_for_server(self, port=7865, timeout=600):
        self._log("Ожидание подключения к серверу Fooocus (Апскейл)...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                if sock.connect_ex(('127.0.0.1', port)) == 0:
                    self._log("Соединение с сервером установлено.")
                    time.sleep(3)
                    return True
            time.sleep(3)
        return False

    def process(self, status_callback=None):
        self.status_callback = status_callback

        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)

        if not os.path.exists(self.input_folder):
            folder_name = os.path.basename(self.input_folder)
            self._log(f"Ошибка: Директория {self.input_folder} не найдена.")
            return False, f"Папка {folder_name} не существует."

        images = [f for f in os.listdir(self.input_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if not images:
            self._log("Операция отменена: папка для отбора пуста.")
            return False, "Нет фото для апскейла."

        self._log(f"Найдено изображений для апскейла: {len(images)}")

        if not self.wait_for_server():
            self._log("Ошибка: Сервер Fooocus не отвечает.")
            return False, "Тайм-аут сервера."

        self._ensure_playwright_browsers()

        browser = None
        playwright = None
        try:
            self._log("Инициализация среды апскейла...")
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=False)
            page = browser.new_page()
            page.goto("http://127.0.0.1:7865")

            self._log("Загрузка интерфейса Фокуса...")
            page.wait_for_selector('#component-21', timeout=60000)

            self._log("Настройка параметров апскейла (2x)...")
            page.locator('#component-21 input[type="checkbox"]').check(force=True)
            page.locator('#component-23 input[type="checkbox"]').check(force=True)
            time.sleep(1)

            page.locator('#component-31').locator('[data-testid="Upscale (2x)-radio-label"]').click()
            page.locator('#component-217').locator('[data-testid="Speed-radio-label"]').click()
            page.locator('#component-221 input[type="number"]').fill("1")

            page.locator('#component-222').locator('[data-testid="jpeg-radio-label"]').click()

            page.locator('.tab-nav button', has_text='Advanced').click()
            page.locator('#component-271 input[type="number"]').fill("6")
            page.locator('#component-272 input[type="number"]').fill("4")

            today_str = datetime.now().strftime("%Y-%m-%d")
            fooocus_out_dir = os.path.join(self.fooocus_dir, "outputs", today_str)

            success_count = 0
            for index, img_name in enumerate(images, start=1):
                img_path = os.path.abspath(os.path.join(self.input_folder, img_name))
                self._log(f"[{index}/{len(images)}] Загрузка файла: {img_name}...")

                page.locator('#component-29 input[type="file"]').set_input_files(img_path)
                time.sleep(1)

                page.locator('#generate_button').click()
                self._log(f"[{index}/{len(images)}] Апскейл идет. Это займет некоторое время...")

                page.locator('#generate_button').wait_for(state="hidden", timeout=10000)
                page.locator('#generate_button').wait_for(state="visible", timeout=0)

                time.sleep(1.5)

                search_pattern = os.path.join(fooocus_out_dir, '*')
                list_of_files = [f for f in glob.glob(search_pattern) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]

                if list_of_files:
                    latest_file = max(list_of_files, key=os.path.getctime)
                    base_name = os.path.splitext(img_name)[0]
                    new_file_path = os.path.join(self.output_folder, f"upscaled_{base_name}.jpg")
                    
                    shutil.move(latest_file, new_file_path)
                    self._log(f"[{index}/{len(images)}] Успешно сохранено: upscaled_{base_name}.jpg")
                    success_count += 1
                else:
                    self._log(f"[{index}/{len(images)}] Внимание: Не удалось найти результат для {img_name}")

            self._log(f"Успешно обработано: {success_count} из {len(images)}")
            return True, "Апскейл завершен."

        except PlaywrightTimeoutError:
            self._log("Ошибка: Время ожидания браузера истекло. Возможно, нехватка памяти.")
            return False, "Тайм-аут апскейла."
        except Exception as e:
            self._log(f"Критическая ошибка процесса: {str(e)}")
            return False, f"Ошибка: {e}"
        finally:
            if browser:
                try:
                    browser.close()
                except:
                    pass
            if playwright:
                try:
                    playwright.stop()
                except:
                    pass

if __name__ == "__main__":
    # Динамические пути для тестов
    base_dir = os.path.dirname(os.path.abspath(__file__))
    in_dir = os.path.join(base_dir, "1_To_Upscale")
    out_dir = os.path.join(base_dir, "2_Ready_Stock")
    
    # Захардкожен только корень Фокуса для ручного теста (UI передаст его динамически)
    fooocus_root = r"D:\Stocks\Fooocus_win64_2-5-0" 

    upscaler = FooocusUpscaler(in_dir, fooocus_root, out_dir)
    upscaler.process()