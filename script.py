import os
import re
import ssl
import sys
import asyncio
import logging
import argparse
import getpass
from pathlib import Path
from typing import List, Dict, Any, Optional

import aiohttp
import certifi
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

    async def _fetch_by_ids(self, endpoint: str, ids: List[int], chunk_size: int = 20) -> List[Dict]:
        """Получение объектов пачками через параметр ids[] с ограничением размера пачки."""
        if not ids:
            return []

        results = []
        key = endpoint.split('?')[0]

        for i in range(0, len(ids), chunk_size):
            chunk = ids[i:i + chunk_size]
            params = [('ids[]', str(item_id)) for item_id in chunk]
            async with self.semaphore:
                async with self.session.get(
                    f"{self.BASE_URL}/{endpoint}",
                    headers=self.headers,
                    params=params
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

            if key in data:
                results.extend(data[key])
            await asyncio.sleep(0.05)

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
        logging.info(f"Запрос урока {lesson_index} (ID: {lesson_id})...")
        lessons = await self._fetch_by_ids("lessons", [lesson_id])
        if not lessons:
            logging.warning(f"Урок с ID {lesson_id} не найден.")
            return

        lesson = lessons[0]
        lesson_title = lesson.get('title', f'Lesson_{lesson_id}')
        safe_lesson_title = self.sanitize_filename(f"{lesson_index:02d}_{lesson_title}")
        lesson_file_path = section_dir / f"{safe_lesson_title}.md"

        steps_ids = lesson.get('steps', [])
        if not steps_ids:
            logging.warning(f"В уроке {lesson_title} (ID: {lesson_id}) нет шагов.")
            return

        steps = await self._fetch_by_ids("steps", steps_ids)

        # Сортировка шагов по порядку их ID в уроке
        step_map = {step['id']: step for step in steps}
        ordered_steps = [step_map[s_id] for s_id in steps_ids if s_id in step_map]

        content_parts = [f"# {lesson_title}\n"]

        total_steps = len(ordered_steps)
        for step_idx, step in enumerate(ordered_steps, start=1):
            step_id = step.get('id')
            block = step.get('block', {})
            name = block.get('name', 'unknown')

            logging.info(f"  [Урок '{lesson_title}'] Скачивание шага {step_idx}/{total_steps} (ID: {step_id}, тип: {name})...")

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

        course_data = await self._fetch_by_ids("courses", [course_id])
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

        sections = await self._fetch_by_ids("sections", sections_ids)
        section_map = {sec['id']: sec for sec in sections}
        ordered_sections = [section_map[s_id] for s_id in sections_ids if s_id in section_map]

        # Создание README курса со структурой
        readme_lines = [f"# {course_title}\n", f"ID курса: {course_id}\n", "## Содержание\n"]

        total_sections = len(ordered_sections)
        for s_idx, section in enumerate(ordered_sections, start=1):
            sec_title = section.get('title', f'Section_{section["id"]}')
            safe_sec_title = self.sanitize_filename(f"{s_idx:02d}_{sec_title}")
            section_dir = course_dir / safe_sec_title
            section_dir.mkdir(parents=True, exist_ok=True)

            logging.info(f"Начало обработки модуля {s_idx}/{total_sections}: '{sec_title}' (ID: {section.get('id')})")
            readme_lines.append(f"{s_idx}. **{sec_title}**")

            units_ids = section.get('units', [])
            if not units_ids:
                continue

            units = await self._fetch_by_ids("units", units_ids)
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


def parse_course_id(course_input: str) -> Optional[int]:
    """Извлечение числового ID курса из строки или URL."""
    course_input = course_input.strip()
    match = re.search(r'(?:course/|^)(\d+)', course_input)
    if match:
        return int(match.group(1))
    return None


async def run_export(client_id: str, client_secret: str, course_id: int, output_dir: str):
    """Асинхронный запуск процесса аутентификации и экспорта курса."""
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    async with aiohttp.ClientSession(connector=connector) as session:
        exporter = AsyncStepikExporter(client_id, client_secret)
        exporter.session = session
        await exporter.authenticate()
        await exporter.export_course(course_id, output_dir)


def cli_entrypoint():
    """Главная точка входа для консольной утилиты."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Асинхронный экспорт материалов курса Stepik в Markdown-файлы."
    )
    parser.add_argument("-i", "--client-id", help="Stepik Client ID")
    parser.add_argument("-s", "--client-secret", help="Stepik Client Secret")
    parser.add_argument("-c", "--course", help="ID курса или ссылка на курс (напр. https://stepik.org/course/196305/)")
    parser.add_argument("-o", "--output", default=None, help="Директория для сохранения (по умолчанию: course_export)")

    args = parser.parse_args()

    client_id = args.client_id or os.getenv("STEPIK_CLIENT_ID")
    client_secret = args.client_secret or os.getenv("STEPIK_CLIENT_SECRET")
    course_input = args.course or os.getenv("COURSE_ID")
    output_dir = args.output or os.getenv("OUTPUT_DIR", "course_export")

    if not client_id:
        client_id = input("Введите Stepik Client ID: ").strip()

    if not client_secret:
        client_secret = getpass.getpass("Введите Stepik Client Secret: ").strip()

    while not course_input:
        course_input = input("Введите ID курса или ссылку на курс (например https://stepik.org/course/58852/): ").strip()

    course_id = parse_course_id(course_input)
    while course_id is None:
        logging.error(f"Не удалось извлечь ID курса из значения: '{course_input}'")
        course_input = input("Повторите ввод ID курса или ссылки: ").strip()
        course_id = parse_course_id(course_input)

    if not client_id or not client_secret:
        logging.error("Client ID и Client Secret обязательны для выполнения экспорта.")
        sys.exit(1)

    try:
        asyncio.run(run_export(client_id, client_secret, course_id, output_dir))
    except KeyboardInterrupt:
        logging.warning("\nЭкспорт прерван пользователем.")
        sys.exit(130)
    except Exception as exc:
        logging.error(f"Произошла ошибка: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    cli_entrypoint()
