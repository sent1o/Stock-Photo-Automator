import os
import time
import glob
import shutil
import socket 
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

    def _read_prompts(self):
        if not os.path.exists(self.wildcards_file):
            self._log("Помилка: Файл із промптами не знайдено.")
            return []
        with open(self.wildcards_file, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    def wait_for_server(self, port=7865, timeout=600):
        self._log("Очікування підключення до сервера Fooocus...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                if sock.connect_ex(('127.0.0.1', port)) == 0:
                    self._log("З'єднання із сервером встановлено.")
                    time.sleep(3)
                    return True
            time.sleep(3)
        return False

    def run_generation(self, status_callback=None):
        self.status_callback = status_callback
        
        prompts = self._read_prompts()
        if not prompts:
            self._log("Генерацію скасовано: відсутні промпти.")
            return False, "Немає промптів."
        
        target_count = min(32, len(prompts))
        
        if not self.wait_for_server():
            self._log("Помилка: Сервер Fooocus не відповідає.")
            return False, "Тайм-аут сервера."

        browser = None
        playwright = None
        try:
            self._log("Ініціалізація середовища генерації...")
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=False)
            page = browser.new_page()
            page.goto("http://127.0.0.1:7865")
            
            self._log("Завантаження моделей інтерфейсу...")
            page.wait_for_selector('#generate_button:not([disabled])', timeout=120000)
            
            self._log("Налаштування параметрів зображення...")
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

            self._log("Параметри застосовано. Запуск процесу...")
            page.locator('#generate_button').click()

            self._log(f"Генерація ({target_count} зобр.) триває. Це займе певний час...")
            page.locator('#generate_button').wait_for(state="hidden", timeout=10000)
            page.locator('#generate_button').wait_for(state="visible", timeout=0) # Безлімітне очікування
            
            time.sleep(3) 
            self._log("Генерацію завершено. Обробка файлів...")
            
        except PlaywrightTimeoutError:
            self._log("Помилка: Час очікування браузера вичерпано. Можливо, нестача пам'яті.")
            return False, "Тайм-аут генерації."
        except Exception as e:
            self._log(f"Критична помилка процесу: {str(e)}")
            return False, f"Помилка: {e}"
        finally:
            # Гарантовано закриваємо браузер, навіть якщо була помилка
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

        # Перенесення файлів робимо після закриття браузера
        self.move_to_test_in(target_count)
        return True, "Генерація успішна."

    def move_to_test_in(self, target_count):
        self._log("Переміщення готових зображень у директорію перевірки...")
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
            self._log(f"Успішно переміщено {moved} зобр. Зображення готові до перевірки.")
        else:
            self._log("Увага: Не знайдено нових зображень для переміщення.")