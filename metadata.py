import os
import sys
import re
import json
import glob
import logging
import openai
from bs4 import BeautifulSoup
from iptcinfo3 import IPTCInfo
from dotenv import load_dotenv

# Отключаем спам от iptcinfo в консоль
logging.getLogger('iptcinfo').setLevel(logging.ERROR)

class MetadataInjector:
    def __init__(self, upscale_dir, base_fooocus_dir, openai_key=None):
        self.upscale_dir = upscale_dir
        self.fooocus_dir = os.path.join(base_fooocus_dir, "Fooocus")
        self.openai_key = openai_key
        self.log_cache = {}
        self.status_callback = None

    def _log(self, message):
        """Передает лог в UI, если подключен коллбек, иначе печатает в консоль"""
        if self.status_callback:
            self.status_callback(message)
        else:
            print(message)

    def _get_prompt_from_logs(self, original_png_name):
        # Сначала ищем в кэше
        for cached_file, prompt in self.log_cache.items():
            if cached_file == original_png_name:
                return prompt

        search_pattern = os.path.join(self.fooocus_dir, "outputs", "**", "*.html")
        all_html_files = glob.glob(search_pattern, recursive=True)

        for html_file in all_html_files:
            try:
                with open(html_file, 'r', encoding='utf-8') as f:
                    soup = BeautifulSoup(f, 'html.parser')
                    containers = soup.find_all('div', class_='image-container')
                    for container in containers:
                        a_tag = container.find('a')
                        if a_tag and a_tag.get('href'):
                            file_name = os.path.basename(a_tag['href'].strip())
                        else:
                            img_div = container.find('div', string=re.compile(r'.*\.png'))
                            if not img_div:
                                continue
                            file_name = img_div.text.strip()

                        prompt_td = container.find('td', class_='label', string='Prompt')
                        if prompt_td:
                            prompt_value = prompt_td.find_next_sibling('td', class_='value')
                            if prompt_value:
                                self.log_cache[file_name] = prompt_value.text.strip()
                                if file_name == original_png_name:
                                    return self.log_cache[file_name]
            except Exception:
                continue # Игнорируем битые HTML файлы и идем дальше
                
        return None

    def _clean_keywords(self, keywords_list):
        stop_words = ["ai", "generated", "midjourney", "fooocus", "artificial", "danger", "violence", "blood", "render", "cgi"]
        cleaned = []
        for k in keywords_list:
            word = re.sub(r'[^a-zA-Z0-9\s]', '', k).strip().lower()
            if not word or any(stop in word for stop in stop_words):
                continue
            if word not in cleaned:
                cleaned.append(word)
            if len(cleaned) == 25:
                break
        return cleaned

    def process(self, status_callback=None):
        self.status_callback = status_callback
        
        if not self.openai_key:
            self._log("Ошибка: API ключ OpenAI не указан.")
            return False, "Отсутствует API ключ OpenAI."

        self._log("Инициализация прошивки метаданных...")
        
        if not os.path.exists(self.upscale_dir):
            folder_name = os.path.basename(self.upscale_dir)
            self._log("Ошибка: Директория для апскейла не найдена.")
            return False, f"Папка {folder_name} не существует."

        images = [f for f in os.listdir(self.upscale_dir) if f.lower().endswith(('.jpg', '.jpeg'))]
        if not images:
            self._log("Операция отменена: отсутствуют JPEG изображения для обработки.")
            return False, "Нет изображений для обработки."

        client = openai.OpenAI(api_key=self.openai_key)
        success_count = 0
        
        for index, img_name in enumerate(images, start=1):
            original_png = img_name.replace("upscaled_", "")
            original_png = os.path.splitext(original_png)[0] + ".png"
            
            self._log(f"[{index}/{len(images)}] Анализ логов для файла {img_name}...")
            prompt = self._get_prompt_from_logs(original_png)

            if not prompt:
                self._log(f"Внимание: Промпт для {img_name} не найден в логах. Пропуск.")
                continue

            self._log(f"[{index}/{len(images)}] Получение данных от OpenAI...")
            sys_prompt = (
                "You are an expert stock photography contributor. Based on the given image generation prompt, "
                "create metadata for stock agencies in JSON format. Requirements: 'title': 5 to 8 words maximum. "
                "'description': up to 20 words maximum. 'keywords': exactly 25 highly relevant keywords "
                "(single words or very short phrases), comma separated. Do NOT include words related to AI "
                "generation, rendering, or unsafe content."
            )
            
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": f"Prompt: {prompt}"}
                    ],
                    response_format={ "type": "json_object" }
                )
                meta_data = json.loads(response.choices[0].message.content)
            except Exception as e:
                self._log(f"Ошибка API OpenAI для {img_name}: {str(e)}")
                continue

            img_path = os.path.join(self.upscale_dir, img_name)
            self._log(f"[{index}/{len(images)}] Интеграция IPTC метаданных...")
            
            try:
                iptc = IPTCInfo(img_path, force=True)
                iptc['object name'] = meta_data.get('title', '').encode('utf-8')
                iptc['caption/abstract'] = meta_data.get('description', '').encode('utf-8')
                
                raw_keywords = [k.strip() for k in meta_data.get('keywords', '').split(',')]
                clean_keywords = self._clean_keywords(raw_keywords)
                iptc['keywords'] = [k.encode('utf-8') for k in clean_keywords]
                
                iptc.save()
                
                # Удаляем бэкап файл, который создает iptcinfo3
                bak_file = img_path + "~"
                if os.path.exists(bak_file):
                    os.remove(bak_file)
                    
                self._log(f"[{index}/{len(images)}] Успешно прошито (Ключей: {len(clean_keywords)})")
                success_count += 1
                
            except Exception as e:
                self._log(f"Ошибка записи IPTC для {img_name}: {str(e)}")

        self._log(f"Процесс завершен. Успешно обработано изображений: {success_count} из {len(images)}.")
        return True, "Метаданные успешно прошиты."

if __name__ == "__main__":
    load_dotenv()
    
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    UPSCALE_DIR = os.path.join(base_dir, "2_Ready_Stock")
    # Только для локального теста
    FOOOCUS_DIR = r"D:\Stocks\Fooocus_win64_2-5-0" 
    OPENAI_KEY = os.getenv("OPENAI_API_KEY") 
    
    injector = MetadataInjector(UPSCALE_DIR, FOOOCUS_DIR, OPENAI_KEY)
    injector.process()