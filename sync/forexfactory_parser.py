"""
Парсер HTML файлов ForexFactory Calendar.
Извлекает новостные события из сохранённых HTML страниц.
"""

import re
import logging
from typing import List, Optional, Union, IO
from datetime import datetime

import pandas as pd
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MONTHS = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"
}


def _parse_month_year(soup) -> tuple:
    """Извлекает месяц и год из HTML страницы ForexFactory."""
    text = soup.get_text()
    match = re.search(r"\b([A-Za-z]{3})\s+(\d{4})\b", text)
    if match:
        mon_str, year_str = match.groups()
        mon_num = MONTHS.get(mon_str)
        if mon_num:
            return year_str, mon_num
    return None, None


def parse_html_content(html_content: Union[bytes, str], filename: str = "") -> List[dict]:
    """
    Парсит содержимое одного HTML файла ForexFactory Calendar.

    Args:
        html_content: HTML как bytes или str
        filename: имя файла для логирования

    Returns:
        Список словарей {timestamp, impact, event, currency}
    """
    try:
        if isinstance(html_content, bytes):
            for encoding in ['windows-1252', 'utf-8', 'latin-1']:
                try:
                    html_content = html_content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue

        soup = BeautifulSoup(html_content, "html.parser")

        year_str, month_str = _parse_month_year(soup)
        if not year_str or not month_str:
            logger.warning(f"Не удалось определить месяц/год в файле: {filename}")
            return []

        rows = soup.find_all("tr", class_=re.compile("calendar__row"))
        all_events = []
        current_day = None
        current_time = "00:00"

        for row in rows:
            # Разделители дней
            if "day-breaker" in row.get("class", []):
                day_cell = row.find("td", class_=re.compile("calendar__cell"))
                if day_cell:
                    day_text = day_cell.get_text(strip=True)
                    dmatch = re.search(r"\b(\d{1,2})\b", day_text)
                    if dmatch:
                        current_day = dmatch.group(1)
                        current_time = "00:00"
                continue

            # Ячейка с датой
            date_cell = row.find("td", class_=re.compile("calendar__date"))
            if date_cell:
                dtext = date_cell.get_text(strip=True)
                dmatch = re.search(r"\b(\d{1,2})\b", dtext)
                if dmatch:
                    current_day = dmatch.group(1)
                    current_time = "00:00"

            # Извлекаем данные события
            time_cell = row.find("td", class_=re.compile("calendar__time"))
            currency_cell = row.find("td", class_=re.compile("calendar__currency"))
            event_cell = row.find("td", class_=re.compile("calendar__event"))
            impact_cell = row.find("td", class_=re.compile("calendar__impact"))

            time_text = time_cell.get_text(strip=True) if time_cell else ""
            currency_text = currency_cell.get_text(strip=True) if currency_cell else ""
            event_text = event_cell.get_text(strip=True) if event_cell else ""

            # Обновляем текущее время
            if time_text and time_text not in ["", "All Day", "Day"]:
                if ":" in time_text:
                    current_time = time_text
                else:
                    current_time = "00:00"
            elif time_text in ["All Day", "Day"]:
                current_time = "00:00"

            # Уровень важности
            impact_level = "low"
            if impact_cell:
                impact_span = impact_cell.find("span", class_=re.compile("icon--ff-impact"))
                if impact_span:
                    classes = str(impact_span.get("class", []))
                    if "red" in classes:
                        impact_level = "high"
                    elif "ora" in classes:
                        impact_level = "medium"

            # Добавляем событие если есть валюта и название
            if currency_text and event_text:
                if current_day:
                    full_date = f"{year_str}-{month_str}-{int(current_day):02d}"
                else:
                    full_date = f"{year_str}-{month_str}-01"

                if current_time and current_time != "00:00":
                    datetime_str = f"{full_date} {current_time}:00"
                else:
                    datetime_str = f"{full_date} 00:00:00"

                all_events.append({
                    "timestamp": datetime_str,
                    "impact": impact_level,
                    "event": event_text,
                    "currency": currency_text
                })

        logger.info(f"Парсинг {filename}: {len(all_events)} событий ({year_str}-{month_str})")
        return all_events

    except Exception as e:
        logger.error(f"Ошибка парсинга {filename}: {e}")
        return []


def parse_html_files(files: list) -> pd.DataFrame:
    """
    Обрабатывает несколько HTML файлов ForexFactory и возвращает DataFrame.

    Args:
        files: список файловых объектов (UploadedFile) или кортежей (filename, content_bytes)

    Returns:
        pd.DataFrame с колонками [timestamp, impact, event, currency], отсортированный по timestamp
    """
    all_events = []

    for f in files:
        if hasattr(f, 'read'):
            # Streamlit UploadedFile
            content = f.read()
            name = getattr(f, 'name', 'unknown.html')
            f.seek(0)
        elif isinstance(f, tuple):
            # (filename, content_bytes)
            name, content = f
        else:
            continue

        events = parse_html_content(content, name)
        all_events.extend(events)

    if not all_events:
        return pd.DataFrame(columns=['timestamp', 'impact', 'event', 'currency'])

    df = pd.DataFrame(all_events)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)
    return df
