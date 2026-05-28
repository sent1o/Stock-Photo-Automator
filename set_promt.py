import os

class PromptManager:
    def __init__(self, base_fooocus_dir):
        internal_fooocus = os.path.join(base_fooocus_dir, "Fooocus")
        self.wildcards_dir = os.path.join(internal_fooocus, "wildcards")
        self.stock_file = os.path.join(self.wildcards_dir, "stock.txt")

    def save_prompts(self, prompts_text):
        try:
            if not os.path.exists(self.wildcards_dir):
                os.makedirs(self.wildcards_dir)
                
            lines = [line.strip() for line in prompts_text.split('\n') if line.strip()]
            
            if not lines:
                return False, "Список промптов пуст (нечего сохранять)."

            with open(self.stock_file, "w", encoding="utf-8") as f:
                f.write('\n'.join(lines))
                
            return True, f"Сохранено промптов: {len(lines)}."
            
        except Exception as e:
            return False, f"Ошибка сохранения промптов: {e}"

    def load_prompts(self):
        try:
            if not os.path.exists(self.stock_file):
                return True, "" # Файла еще нет, это не ошибка
                
            with open(self.stock_file, "r", encoding="utf-8") as f:
                return True, f.read()
                
        except Exception as e:
            return False, f"Ошибка чтения промптов: {e}"