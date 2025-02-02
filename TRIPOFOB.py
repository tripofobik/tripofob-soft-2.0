import os
import re
import zipfile
import xml.etree.ElementTree as ET
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.layout import Layout
from datetime import datetime
import threading
import queue
import json

console = Console()

class FileSearcher:
    def __init__(self):
        self.results = queue.Queue()
        self.total_files = 0
        self.processed_files = 0
        self.supported_extensions = {
            'Документы': ['.txt', '.doc', '.docx', '.pdf', '.rtf'],
            'Таблицы': ['.xls', '.xlsx', '.csv'],
            'Базы данных': ['.db', '.sql', '.sqlite'],
            'Веб-файлы': ['.html', '.xml', '.json'],
            'Исходный код': ['.py', '.js', '.cpp', '.java', '.php']
        }

    def save_results(self, results, pattern):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"search_results_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                'pattern': pattern,
                'timestamp': timestamp,
                'results': results
            }, f, ensure_ascii=False, indent=4)
        
        return filename

    def search_in_file(self, file_path, search_pattern):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                content = file.read()
                matches = re.finditer(search_pattern, content, re.IGNORECASE)
                results = []
                
                for match in matches:
                    start = max(0, match.start() - 50)
                    end = min(len(content), match.end() + 50)
                    context = content[start:end].replace('\n', ' ').strip()
                    results.append({
                        'match': match.group(),
                        'context': f"...{context}..."
                    })
                
                if results:
                    self.results.put({
                        'file': file_path,
                        'type': 'text',
                        'matches': results
                    })
        except Exception as e:
            console.print(f"[red]Ошибка чтения {file_path}: {e}")

    def search_in_xlsx_file(self, file_path, search_pattern):
        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                for name in z.namelist():
                    if name.startswith('xl/worksheets/sheet'):
                        with z.open(name) as sheet:
                            tree = ET.parse(sheet)
                            root = tree.getroot()
                            results = []
                            
                            for row in root.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row'):
                                for cell in row.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v'):
                                    if cell.text and re.search(search_pattern, cell.text, re.IGNORECASE):
                                        results.append({
                                            'match': cell.text,
                                            'context': f"Найдено в ячейке"
                                        })
                            
                            if results:
                                self.results.put({
                                    'file': file_path,
                                    'type': 'excel',
                                    'matches': results
                                })
        except Exception as e:
            console.print(f"[red]Ошибка чтения Excel {file_path}: {e}")

    def search_worker(self, files_queue, search_pattern):
        while True:
            try:
                file_path = files_queue.get_nowait()
                if file_path.endswith('.xlsx'):
                    self.search_in_xlsx_file(file_path, search_pattern)
                else:
                    self.search_in_file(file_path, search_pattern)
                self.processed_files += 1
                files_queue.task_done()
            except queue.Empty:
                break

    def search_in_directory(self, directory, search_pattern, file_types=None):
        files_queue = queue.Queue()
        
        # Собираем все файлы для поиска
        for root, _, files in os.walk(directory):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if file_types is None or ext in file_types:
                    file_path = os.path.join(root, file)
                    files_queue.put(file_path)
                    self.total_files += 1

        # Создаем и запускаем потоки для поиска
        threads = []
        for _ in range(min(os.cpu_count() or 1, 4)):
            t = threading.Thread(
                target=self.search_worker,
                args=(files_queue, search_pattern)
            )
            t.start()
            threads.append(t)

        # Отображаем прогресс
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(
                "[cyan]Поиск...", 
                total=self.total_files
            )
            
            while self.processed_files < self.total_files:
                progress.update(task, completed=self.processed_files)

        # Ждем завершения всех потоков
        for t in threads:
            t.join()

        # Собираем все результаты
        results = []
        while not self.results.empty():
            results.append(self.results.get())
        
        return results

def display_menu():
    console.clear()
    banner = """
    ████████╗██████╗░██╗██████╗░░█████╗░███████╗░█████╗░██████╗░ 2.0
    ╚══██╔══╝██╔══██╗██║██╔══██╗██╔══██╗██╔════╝██╔══██╗██╔══██╗
    ░░░██║░░░██████╔╝██║██████╔╝██║░░██║█████╗░░██║░░██║██████╦╝
    ░░░██║░░░██╔══██╗██║██╔═══╝░██║░░██║██╔══╝░░██║░░██║██╔══██╗
    ░░░██║░░░██║░░██║██║██║░░░░░╚█████╔╝██║░░░░░╚█████╔╝██████╦╝
    ░░░╚═╝░░░╚═╝░░╚═╝╚═╝╚═╝░░░░░░╚════╝░╚═╝░░░░░░╚════╝░╚═════╝░
    """
    console.print(Panel(banner, title="TRIPOFOB 2.0", style="bold blue"))

def display_results(results, pattern):
    if not results:
        console.print("\n[yellow]Результаты не найдены[/yellow]")
        return

    table = Table(title=f"Результаты поиска для: {pattern}")
    table.add_column("Файл", style="cyan", no_wrap=True)
    table.add_column("Совпадения", style="green")
    table.add_column("Контекст", style="white")

    for result in results:
        file_name = os.path.basename(result['file'])
        for match in result['matches']:
            table.add_row(
                file_name,
                match['match'],
                match['context']
            )

    console.print(table)

def main():
    searcher = FileSearcher()
    
    while True:
        display_menu()
        
        # Выбор типов файлов
        console.print("\n[yellow]Доступные типы файлов:[/yellow]")
        for i, (category, extensions) in enumerate(searcher.supported_extensions.items(), 1):
            console.print(f"{i}. {category} ({', '.join(extensions)})")
        console.print("0. Все типы файлов")
        
        choice = Prompt.ask("\nВыберите типы файлов (введите номера через запятую или 0 для всех)", default="0")
        
        selected_extensions = []
        if choice != "0":
            categories = [int(x.strip()) for x in choice.split(",")]
            for cat_num in categories:
                if 1 <= cat_num <= len(searcher.supported_extensions):
                    category = list(searcher.supported_extensions.keys())[cat_num-1]
                    selected_extensions.extend(searcher.supported_extensions[category])
        
        # Ввод поискового запроса
        pattern = Prompt.ask("\n[cyan]Введите данные для поиска[/cyan]")
        if not pattern:
            continue

        directory = Prompt.ask("\n[cyan]Введите путь для поиска[/cyan]", 
                             default=os.path.dirname(os.path.abspath(__file__)))

        # Выполнение поиска
        results = searcher.search_in_directory(
            directory, 
            pattern,
            selected_extensions if selected_extensions else None
        )

        # Отображение результатов
        display_results(results, pattern)

        # Сохранение результатов
        if results:
            if Prompt.ask("\nСохранить результаты в файл? (y/n)", default="n").lower() == 'y':
                filename = searcher.save_results(results, pattern)
                console.print(f"\n[green]Результаты сохранены в: {filename}[/green]")

        # Продолжить или выйти
        if Prompt.ask("\nПродолжить поиск? (y/n)", default="y").lower() != 'y':
            break

    console.print("\n[blue]Спасибо за использование TRIPOFOB 2.0![/blue]")

if __name__ == "__main__":
    main()