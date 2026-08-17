import requests
import time
import logging
from bs4 import BeautifulSoup
from typing import List, Dict, Any

# Настройка логирования для контроля процесса
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


class StepikExporter:
    """
    Класс для работы со Stepik API и экспорта текстовых материалов курса.
    """
    BASE_URL = "https://stepik.org/api"

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = self._get_access_token()
        self.headers = {'Authorization': f'Bearer {self.token}'}

    def _get_access_token(self) -> str:
        """Получение OAuth2 токена по Client Credentials."""
        auth_url = "https://stepik.org/oauth2/token/"
        auth_data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }
        response = requests.post(auth_url, data=auth_data)
        response.raise_for_status()
        logging.info("Токен авторизации успешно получен.")
        return response.json().get('access_token')

    def _fetch_paginated_data(self, endpoint: str, params: Dict[str, Any] = None) -> List[Dict]:
        """Универсальный метод для получения данных с учетом пагинации API."""
        if params is None:
            params = {}

        results = []
        has_next = True
        page = 1

        while has_next:
            params['page'] = page
            response = requests.get(f"{self.BASE_URL}/{endpoint}", headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()

            # API возвращает ключ, совпадающий с названием эндпоинта (например, 'sections')
            key = endpoint.split('?')[0]
            if key in data:
                results.extend(data[key])

            has_next = data['meta']['has_next']
            page += 1
            time.sleep(0.2)  # Защита от Rate Limit

        return results

    def clean_html(self, raw_html: str) -> str:
        """Очистка HTML-разметки и форматирование в читаемый текст."""
        if not raw_html:
            return ""
        soup = BeautifulSoup(raw_html, 'html.parser')

        # Замена тегов кода на маркдаун-формат
        for code_tag in soup.find_all('code'):
            code_text = code_tag.get_text()
            code_tag.replace_with(f"`{code_text}`")

        for pre_tag in soup.find_all('pre'):
            pre_text = pre_tag.get_text()
            pre_tag.replace_with(f"\n```\n{pre_text}\n```\n")

        text = soup.get_text(separator='\n')
        # Удаление избыточных пустых строк
        return '\n'.join(line.strip() for line in text.splitlines() if line.strip())

    def export_course(self, course_id: int, output_filename: str):
        """Полный цикл выгрузки курса и сохранения в файл."""
        logging.info(f"Начало выгрузки курса {course_id}...")

        # 1. Получаем курс
        course_data = self._fetch_paginated_data("courses", {"pk": course_id})
        if not course_data:
            logging.error("Курс не найден.")
            return

        course_title = course_data[0].get('title', f'Course_{course_id}')
        sections_ids = course_data[0].get('sections', [])

        with open(output_filename, 'w', encoding='utf-8') as file:
            file.write(f"# Курс: {course_title}\n\n")

            # 2. Перебираем секции (модули)
            if not sections_ids:
                return

            sections = self._fetch_paginated_data("sections", {"pk": ",".join(map(str, sections_ids))})
            for section in sections:
                file.write(f"## Модуль: {section['title']}\n\n")

                # 3. Перебираем юниты внутри секции
                units_ids = section.get('units', [])
                if not units_ids:
                    continue

                units = self._fetch_paginated_data("units", {"pk": ",".join(map(str, units_ids))})
                lesson_ids = [unit['lesson'] for unit in units]

                # 4. Перебираем уроки
                if not lesson_ids:
                    continue

                lessons = self._fetch_paginated_data("lessons", {"pk": ",".join(map(str, lesson_ids))})

                # Создаем словарь для сохранения порядка уроков
                lessons_dict = {lesson['id']: lesson for lesson in lessons}

                for unit in units:
                    lesson = lessons_dict.get(unit['lesson'])
                    if not lesson:
                        continue

                    file.write(f"### Урок: {lesson['title']}\n\n")

                    # 5. Перебираем шаги (steps) в уроке
                    steps_ids = lesson.get('steps', [])
                    if not steps_ids:
                        continue

                    steps = self._fetch_paginated_data("steps", {"pk": ",".join(map(str, steps_ids))})

                    # Фильтруем только текстовые шаги, чтобы отсечь тесты и видео
                    for step in steps:
                        block = step.get('block', {})
                        if block.get('name') == 'text':
                            raw_text = block.get('text', '')
                            clean_text = self.clean_html(raw_text)
                            file.write(f"{clean_text}\n\n---\n\n")

        logging.info(f"Экспорт завершен! Данные сохранены в файл: {output_filename}")


# ==========================================
# Настройки запуска
# ==========================================
if __name__ == "__main__":
    CLIENT_ID = "ВАШ_CLIENT_ID"
    CLIENT_SECRET = "ВАШ_CLIENT_SECRET"
    COURSE_ID = 67  # Замените на ID нужного курса (ID можно найти в URL курса)
    OUTPUT_FILE = f"stepik_export_{COURSE_ID}.md"

    exporter = StepikExporter(CLIENT_ID, CLIENT_SECRET)
    exporter.export_course(COURSE_ID, OUTPUT_FILE)
