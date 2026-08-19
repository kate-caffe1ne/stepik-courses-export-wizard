# Stepik Courses Export Wizard 🧙

CLI-утилита для асинхронной выгрузки текстовых материалов, заданий и структуры курсов с платформы [Stepik](https://stepik.org) в иерархические Markdown-файлы.

> ⚠️ **Важно:** утилита корректно работает **только с бесплатными курсами**. Материалы платных или закрытых курсов недоступны через данный тип авторизации API без соответствующих прав доступа.

## Возможности
- Асинхронное скачивание модулей, уроков и шагов через официальный Stepik API.
- Поддержка ссылок на курс любого вида или прямых числовых ID курса.
- Очистка HTML-разметки и форматирование кода в чистый Markdown.
- Автоматическая генерация структуры курса в `README.md`.
- Интерактивный режим ввода данных, поддержка флагов командной строки и файлов `.env`.

---

## Получение API-ключей Stepik

Для доступа к API Stepik необходимо создать OAuth-приложение:

1. Войдите в свой аккаунт на [Stepik](https://stepik.org).
2. Перейдите в раздел создания OAuth-приложений: [https://stepik.org/oauth2/applications/](https://stepik.org/oauth2/applications/).
3. Нажмите кнопку **New Application** (Создать приложение).
4. Заполните поля формы:
   - **Name**: любое имя (например, `CourseExporter`).
   - **Client type**: `Confidential`.
   - **Authorization grant type**: `Client credentials`.
5. Нажмите **Save** и скопируйте сгенерированные **Client ID** и **Client Secret**.

---

## Предварительная настройка окружения

Перед установкой утилиты убедитесь, что у вас установлены **Python (>= 3.9)** и **pipx** (или стандартный `pip`).

### 🍏 macOS
1. Установите Python и pipx с помощью [Homebrew](https://brew.sh/):
   ```bash
   brew install python pipx
   pipx ensurepath
   ```
2. Перезапустите терминал или примените изменения профиля (`source ~/.zshrc`).

### 🖼️ Windows
1. Скачайте и установите Python с официального сайта [python.org](https://www.python.org/downloads/) (обязательно отметьте галочку **"Add python.exe to PATH"** при установке).
2. Откройте командную строку или PowerShell и установите `pipx`:
   ```powershell
   py -m pip install --user pipx
   py -m pipx ensurepath
   ```
3. Перезапустите командную строку или PowerShell.

### 🐧 Linux (Ubuntu / Debian / etc)
1. Установите Python, pip и pipx через пакетный менеджер:
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-pip python3-venv pipx
   pipx ensurepath
   ```
2. Перезапустите терминал или примените изменения профиля (`source ~/.bashrc`).

---

## Установка

### Вариант 1. Через `pipx` (рекомендуется)
Установка в изолированное окружение с глобально доступной командой:
```bash
pipx install git+https://github.com/kate-caffe1ne/stepik-courses-export-wizard.git
```

### Вариант 2. В текущее виртуальное окружение через `pip`
```bash
pip install git+https://github.com/kate-caffe1ne/stepik-courses-export-wizard.git
```

---

## Варианты запуска

### 1. Интерактивный режим
Если запустить утилиту без аргументов и переменных окружения, она запросит все необходимые данные в консоли:
```bash
stepik-export
```

### 2. С аргументами командной строки
```bash
stepik-export --client-id ВАШ_ID --client-secret ВАШ_SECRET --course https://stepik.org/course/58852/ --output my_courses
```

Доступные флаги:
- `-i`, `--client-id` — Stepik Client ID
- `-s`, `--client-secret` — Stepik Client Secret
- `-c`, `--course` — Числовой ID курса или ссылка на курс (например, `https://stepik.org/course/58852/syllabus`)
- `-o`, `--output` — Папка для сохранения (по умолчанию: `course_export`)

### 3. Локальный запуск для разработчиков (через `.env`)
1. Склонируйте репозиторий и создайте файл `.env`:
   ```bash
   cp .env.example .env
   ```
2. Заполните параметры в `.env`:
   ```dotenv
   STEPIK_CLIENT_ID=your_client_id_here
   STEPIK_CLIENT_SECRET=your_client_secret_here
   COURSE_ID=58852
   OUTPUT_DIR=course_export
   ```
3. Запустите скрипт напрямую:
   ```bash
   python script.py
   ```

---

## Структура экспортированных файлов

После экспорта формируется иерархическая структура каталогов и Markdown-файлов:

```
course_export/
└── COURSE_ID_Название_курса/
    ├── README.md                              # Оглавление и список модулей курса
    ├── 01_Название_модуля_1/
    │   ├── 01_Название_урока_1.md
    │   └── 02_Название_урока_2.md
    └── 02_Название_модуля_2/
        ├── 01_Название_урока_1.md
        └── 02_Название_урока_2.md
```
