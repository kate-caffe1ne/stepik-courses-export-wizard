import os
import re
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

import aiohttp
from bs4 import BeautifulSoup
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


class AsyncStepikExporter:
    """
    Класс для асинхронной работы со Stepik API и экспорта материалов курса в Markdown.
    """
    BASE_URL = "https://stepik.org/api"

    def __init__(self, client_id: str, client_secret: str, concurrency_limit: int = 5):
        self.client_id = client_id
        self.client_secret = client_secret
        self.headers: Dict[str, str] = {}
        self.semaphore = asyncio.Semaphore(concurrency_limit)
        self.session: Optional[aiohttp.ClientSession] = None

    async def authenticate(self):
        """Получение OAuth2 токена по Client Credentials."""
        auth_url = "https://stepik.org/oauth2/token/"
        auth_data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }
        async with self.session.post(auth_url, data=auth_data) as response:
            response.raise_for_status()
            data = await response.json()
            token = data.get('access_token')
            self.headers = {'Authorization': f'Bearer {token}'}
            logging.info("Токен авторизации успешно получен.")

    async def _fetch_paginated_data(self, endpoint: str, params: Dict[str, Any] = None) -> List[Dict]:
        """Асинхронный метод для получения данных с учетом пагинации API."""
        if params is None:
            params = {}

        results = []
        has_next = True
        page = 1

        while has_next:
            current_params = dict(params)
            current_params['page'] = page
            async with self.semaphore:
                async with self.session.get(
                    f"{self.BASE_URL}/{endpoint}",
                    headers=self.headers,
                    params=current_params
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

            key = endpoint.split('?')[0]
            if key in data:
                results.extend(data[key])

            has_next = data.get('meta', {}).get('has_next', False)
            page += 1
            await asyncio.sleep(0.1)

        return results

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Очистка имени файла/папки от недопустимых символов."""
        return re.sub(r'[\\/*?:"<>|]', '_', name).strip()

    def clean_html(self, raw_html: str) -> str:
        """Очистка HTML-разметки и форматирование в читаемый Markdown-текст."""
        if not raw_html:
            return ""
        soup = BeautifulSoup(raw_html, 'html.parser')

        for code_tag in soup.find_all('code'):
            code_text = code_tag.get_text()
            code_tag.replace_with(f"`{code_text}`")

        for pre_tag in soup.find_all('pre'):
            pre_text = pre_tag.get_text()
            pre_tag.replace_with(f"\n```\n{pre_text}\n```\n")

        text = soup.get_text(separator='\n')
        return '\n'.join(line.strip() for line in text.splitlines() if line.strip())

    async def _export_lesson(self, lesson_id: int, lesson_index: int, section_dir: Path) -> None:
        """Экспорт одного урока в отдельный Markdown-файл."""
        lessons = await self._fetch_paginated_data("lessons", {"pk": lesson_id})
        if not lessons:
            return

        lesson = lessons[0]
        lesson_title = lesson.get('title', f'Lesson_{lesson_id}')
        safe_lesson_title = self.sanitize_filename(f"{lesson_index:02d}_{lesson_title}")
        lesson_file_path = section_dir / f"{safe_lesson_title}.md"

        steps_ids = lesson.get('steps', [])
        if not steps_ids:
            return

        steps = await self._fetch_paginated_data("steps", {"pk": ",".join(map(str, steps_ids))})

        # Сортировка шагов по порядку их ID в уроке
        step_map = {step['id']: step for step in steps}
        ordered_steps = [step_map[s_id] for s_id in steps_ids if s_id in step_map]

        content_parts = [f"# {lesson_title}\n"]

        for step_idx, step in enumerate(ordered_steps, start=1):
            block = step.get('block', {})
            name = block.get('name')

            content_parts.append(f"## Шаг {step_idx} ({name})")

            if name == 'text':
                raw_text = block.get('text', '')
                clean_text = self.clean_html(raw_text)
                content_parts.append(clean_text)
            elif name == 'video':
                video = block.get('video', {})
                urls = video.get('urls', [])
                video_url = urls[0].get('url') if urls else "Видео недоступно"
                content_parts.append(f"[Видеозапись шага]({video_url})")
            else:
                raw_text = block.get('text', '')
                if raw_text:
                    content_parts.append(self.clean_html(raw_text))

            content_parts.append("\n---\n")

        lesson_file_path.write_text("\n\n".join(content_parts), encoding="utf-8")
        logging.info(f"Сохранен урок: {lesson_file_path}")

    async def export_course(self, course_id: int, output_base_dir: str):
        """Полный цикл асинхронной выгрузки курса и сохранения в Markdown-файлы."""
        logging.info(f"Начало выгрузки курса {course_id}...")

        course_data = await self._fetch_paginated_data("courses", {"pk": course_id})
        if not course_data:
            logging.error("Курс не найден.")
            return

        course_title = course_data[0].get('title', f'Course_{course_id}')
        safe_course_title = self.sanitize_filename(course_title)
        course_dir = Path(output_base_dir) / f"{course_id}_{safe_course_title}"
        course_dir.mkdir(parents=True, exist_ok=True)

        sections_ids = course_data[0].get('sections', [])
        if not sections_ids:
            logging.warning("У курса нет секций.")
            return

        sections = await self._fetch_paginated_data("sections", {"pk": ",".join(map(str, sections_ids))})
        section_map = {sec['id']: sec for sec in sections}
        ordered_sections = [section_map[s_id] for s_id in sections_ids if s_id in section_map]

        # Создание README курса со структурой
        readme_lines = [f"# {course_title}\n", f"ID курса: {course_id}\n", "## Содержание\n"]

        for s_idx, section in enumerate(ordered_sections, start=1):
            sec_title = section.get('title', f'Section_{section["id"]}')
            safe_sec_title = self.sanitize_filename(f"{s_idx:02d}_{sec_title}")
            section_dir = course_dir / safe_sec_title
            section_dir.mkdir(parents=True, exist_ok=True)

            readme_lines.append(f"{s_idx}. **{sec_title}**")

            units_ids = section.get('units', [])
            if not units_ids:
                continue

            units = await self._fetch_paginated_data("units", {"pk": ",".join(map(str, units_ids))})
            unit_map = {unit['id']: unit for unit in units}
            ordered_units = [unit_map[u_id] for u_id in units_ids if u_id in unit_map]

            lesson_tasks = []
            for u_idx, unit in enumerate(ordered_units, start=1):
                lesson_id = unit.get('lesson')
                if lesson_id:
                    lesson_tasks.append(self._export_lesson(lesson_id, u_idx, section_dir))

            await asyncio.gather(*lesson_tasks)

        (course_dir / "README.md").write_text("\n".join(readme_lines), encoding="utf-8")
        logging.info(f"Экспорт завершен! Структура сохранена в: {course_dir}")


async def main():
    load_dotenv()

    client_id = os.getenv("STEPIK_CLIENT_ID")
    client_secret = os.getenv("STEPIK_CLIENT_SECRET")
    course_id_str = os.getenv("COURSE_ID")
    output_dir = os.getenv("OUTPUT_DIR", "course_export")

    if not client_id or not client_secret or not course_id_str:
        logging.error("Пожалуйста, укажите STEPIK_CLIENT_ID, STEPIK_CLIENT_SECRET и COURSE_ID в файле .env")
        return

    course_id = int(course_id_str)

    async with aiohttp.ClientSession() as session:
        exporter = AsyncStepikExporter(client_id, client_secret)
        exporter.session = session
        await exporter.authenticate()
        await exporter.export_course(course_id, output_dir)


if __name__ == "__main__":
    asyncio.run(main())
