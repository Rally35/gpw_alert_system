# GPW Alert System

## Opis projektu
System do automatycznego pobierania danych giełdowych z GPW, analizy według strategii i wysyłania alertów.

## Struktura katalogów
- `data_fetcher/` - Pobieranie danych z Yahoo Finance
- `strategy_analyzer/` - Analiza strategii (MA50/MA100 itd.)
- `alert_system/` - Wysyłanie powiadomień e-mail
- `dashboard/` - Wizualizacja wykresów i alertów
- `database/` - Schemat bazy danych (PostgreSQL)
- `config/` - Pliki konfiguracyjne

## Instrukcja
- `git status` - Sprawdzenie aktualnych zmian w repo
- `git commit -m "Komentarz"` - Wprowadzenie zmian w repozytorium
- `git push origin main` - Pobranie aktualnego stanu repozytorium