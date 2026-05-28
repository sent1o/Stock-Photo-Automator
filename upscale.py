import os
import time
import glob
import shutil
import socket
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

class FooocusUpscaler:
    def __init__(self, input_folder, base_fooocus_dir, output_folder):
        self.input_folder = input_folder
        self.fooocus_dir = os.path.join(base_fooocus_dir, "Fooocus")
        self.output_folder = output_folder
        self.status_callback = None

    def _log(self, message):
        """Передає лог у UI, якщо підключено колбек, інакше друкує в консоль"""
        if self.status_callback:
            self.status_callback(message)
        else:
            print(message)

    def wait_for_server(self, port=7865, timeout=600):
        self._log("Очікування підключення до сервера Fooocus (Апскейл)...")
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

    def process(self, status_callback=None):
        self.status_callback = status_callback

        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)

        if not os.path.exists(self.input_folder):
            folder_name = os.path.basename(self.input_folder)
            self._log(f"Помилка: Директорія {self.input_folder} не знайдена.")
            return False, f"Папка {folder_name} не існує."

        images = [f for f in os.listdir(self.input_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if not images:
            self._log("Операцію скасовано: папка для відбору порожня.")
            return False, "Немає фото для апскейлу."

        self._log(f"Знайдено зображень для апскейлу: {len(images)}")

        if not self.wait_for_server():
            self._log("Помилка: Сервер Fooocus не відповідає.")
            return False, "Тайм-аут сервера."

        browser = None
        playwright = None
        try:
            self._log("Ініціалізація середовища апскейлу...")
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=False)
            page = browser.new_page()
            page.goto("http://127.0.0.1:7865")

            self._log("Завантаження інтерфейсу Фокуса...")
            page.wait_for_selector('#component-21', timeout=60000)

            self._log("Налаштування параметрів апскейлу (2x)...")
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
                self._log(f"[{index}/{len(images)}] Завантаження файлу: {img_name}...")

                page.locator('#component-29 input[type="file"]').set_input_files(img_path)
                time.sleep(1)

                page.locator('#generate_button').click()
                self._log(f"[{index}/{len(images)}] Апскейл триває. Це займе певний час...")

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
                    self._log(f"[{index}/{len(images)}] Успішно збережено: upscaled_{base_name}.jpg")
                    success_count += 1
                else:
                    self._log(f"[{index}/{len(images)}] Увага: Не вдалося знайти результат для {img_name}")

            self._log(f"Успішно оброблено: {success_count} з {len(images)}")
            return True, "Апскейл завершено."

        except PlaywrightTimeoutError:
            self._log("Помилка: Час очікування браузера вичерпано. Можливо, нестача пам'яті.")
            return False, "Тайм-аут апскейлу."
        except Exception as e:
            self._log(f"Критична помилка процесу: {str(e)}")
            return False, f"Помилка: {e}"
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
    # Динамічні шляхи для тестів
    base_dir = os.path.dirname(os.path.abspath(__file__))
    in_dir = os.path.join(base_dir, "1_To_Upscale")
    out_dir = os.path.join(base_dir, "2_Ready_Stock")
    
    # Захардкоджений тільки корінь Фокуса для ручного тесту (UI передасть його динамічно)
    fooocus_root = r"D:\Stocks\Fooocus_win64_2-5-0" 

    upscaler = FooocusUpscaler(in_dir, fooocus_root, out_dir)
    upscaler.process()