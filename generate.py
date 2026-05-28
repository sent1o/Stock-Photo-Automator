import os
import time
import glob
import shutil
import socket 
import subprocess
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

class FooocusGenerator:
    def __init__(self, base_fooocus_dir):
        self.fooocus_dir = os.path.join(base_fooocus_dir, "Fooocus")
        self.wildcards_file = os.path.join(self.fooocus_dir, "wildcards", "stock.txt")
        self.status_callback = None

    def _log(self, message):
        """Передає лог у UI, якщо підключено колбек, інакше друкує в консоль"""
        if self.status_callback:
            self.status_callback(message)
        else:
            print(message)

    def _ensure_playwright_browsers(self):
        """Перевіряє і встановлює Chromium для Playwright, якщо його немає"""
        try:
            subprocess.run(["playwright", "install", "chromium"], check=True, capture_output=True)
        except Exception:
            self._log("Установка браузера для Playwright...")
            subprocess.run(["python", "-m", "playwright", "install", "chromium"], capture_output=True)

    def _read_prompts(self):
        if not os.path.exists(self.wildcards_file):
            self._log("Ошибка: Файл с промптами не найден.")
            return []
        with open(self.wildcards_file, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    def wait_for_server(self, port=7865, timeout=600):
        self._log("Ожидание подключения к серверу Fooocus...")
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

    def run_generation(self, status_callback=None):
        self.status_callback = status_callback
        
        self._ensure_playwright_browsers()
        
        prompts = self._read_prompts()
        if not prompts:
            self._log("Генерация отменена: отсутствуют промпты.")
            return False, "Нет промптов."
        
        target_count = min(32, len(prompts))
        
        if not self.wait_for_server():
            self._log("Ошибка: Сервер Fooocus не отвечает.")
            return False, "Тайм-аут сервера."

        browser = None
        playwright = None
        try:
            self._log("Инициализация среды генерации...")
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=False)
            page = browser.new_page()
            page.goto("http://127.0.0.1:7865")
            
            self._log("Загрузка моделей интерфейса...")
            page.wait_for_selector('#generate_button:not([disabled])', timeout=120000)
            
            self._log("Настройка параметров изображения...")
            page.locator('#positive_prompt textarea').fill('__stock__')
            
            page.locator('#component-23 input[type="checkbox"]').check(force=True)
            time.sleep(1.5) 

            page.locator('.tab-nav button', has_text='Settings').click()
            page.locator('#component-217').locator('label', has_text='Quality').click()
            page.locator('#aspect_ratios_accordion .label-wrap').click()
            time.sleep(0.5)
            page.locator('#component-219 label', has_text='1216×832').click(force=True)
            page.locator('#component-221 input[type="number"]').fill(str(target_count))

            page.locator('.tab-nav button', has_text='Styles').click()
            page.locator('label', has_text='Fooocus Photograph').locator('input[type="checkbox"]').check(force=True)

            page.locator('.tab-nav button', has_text='Advanced').click()
            page.locator('#component-271 input[type="number"]').fill("6")
            page.locator('#component-272 input[type="number"]').fill("4")
            page.locator('#component-274 input[type="checkbox"]').check(force=True)
            time.sleep(1.5)

            page.locator('.tab-nav button', has_text='Debug Tools').click()
            page.locator('#component-296 input[type="checkbox"]').check(force=True)

            self._log("Параметры применены. Запуск процесса...")
            page.locator('#generate_button').click()

            self._log(f"Генерация ({target_count} изобр.) идет. Это займет некоторое время...")
            page.locator('#generate_button').wait_for(state="hidden", timeout=10000)
            page.locator('#generate_button').wait_for(state="visible", timeout=0) # Безлимитное ожидание
            
            time.sleep(3) 
            self._log("Генерация завершена. Обработка файлов...")
            
        except PlaywrightTimeoutError:
            self._log("Ошибка: Время ожидания браузера истекло. Возможно, нехватка памяти.")
            return False, "Тайм-аут генерации."
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

        self.move_to_test_in(target_count)
        return True, "Генерация успешна."

    def move_to_test_in(self, target_count):
        self._log("Перемещение готовых изображений в директорию проверки...")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        test_in_dir = os.path.join(base_dir, "1_To_Upscale")
                
        if not os.path.exists(test_in_dir):
            os.makedirs(test_in_dir)

        search_pattern = os.path.join(self.fooocus_dir, "outputs", "*", "*.png")
        all_files = glob.glob(search_pattern)
        
        all_files.sort(key=os.path.getctime, reverse=True)
        newest_files = all_files[:target_count]

        moved = 0
        for file_path in newest_files:
            file_name = os.path.basename(file_path)
            dest_path = os.path.join(test_in_dir, file_name)
            try:
                shutil.move(file_path, dest_path)
                moved += 1
            except Exception as e:
                pass
                
        if moved > 0:
            self._log(f"Успешно перемещено {moved} изобр. Изображения готовы к проверке.")
        else:
            self._log("Внимание: Не найдено новых изображений для перемещения.")