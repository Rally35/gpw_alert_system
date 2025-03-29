

1. **Pełna logika wejścia/wyjścia:**
   - Obecnie strategia generuje sygnał wejścia (ENTRY) w momencie spełnienia określonej liczby warunków (np. 3 z 4 dodatkowych).
        Strategia opisana w pliku wymaga również generowania sygnału wyjścia (exit trigger), np. na podstawie trailing stop-loss (np. dynamicznego poziomu stop-loss obliczanego na bazie ATR) oraz warunków takich jak spadek poniżej SMA5 przez 2 dni czy RSI poniżej określonego poziomu.
   - Konieczne byłoby rozszerzenie strategii o logikę sygnału wyjścia oraz mechanizm śledzenia (monitorowania) otwartych pozycji.

2. **Obserwacja (Watchlist) i dynamiczne przejście do alertu:**  DONE
   - Chciałbyś mieć możliwość obserwowania spółek, które są bliskie spełnienia pełnych warunków (sygnał WATCH) oraz automatycznego przejścia do sygnału ALERT (ENTRY), gdy zostanie osiągnięty określony poziom wejścia.
        Obecnie strategia zwraca sygnał jedynie wtedy, gdy warunki są spełnione, ale nie ma mechanizmu „watchlist”, który śledziłby spółki pod obserwacją.
   - Byłoby wskazane rozróżnienie sygnałów – np. status WATCH dla spółek, które spełniły 2 kryteria, i status PENDING lub ENTRY dla spółek, które spełniły 3 kryteria.
        Dodatkowo, w polu szczegółów (JSON) można zapisywać „trigger entry price”, czyli poziom wejścia, przy którym spółka przejdzie z WATCH do ALERT.

5. **Backtesting i kalibracja parametrów:**  TO DO
   - Strategia zakłada przeprowadzenie backtestu na danych historycznych (np. minimum 200 dni) i kalibrację parametrów dla różnych sektorów.
        Obecnie w projekcie nie ma modułu do backtestingu ani narzędzi do kalibracji.
   - Dodanie takiego modułu umożliwiłoby przetestowanie skuteczności strategii na historycznych danych przed wdrożeniem jej w czasie rzeczywistym.

00. NEXT

Twoje podejście jest jak najbardziej trafne. Aby móc zarządzać zarówno sygnałami wejścia, jak i wyjścia, warto rozdzielić alerty (sygnały generowane przez strategię) od otwartych pozycji, które już zostały przyjęte do portfela. Oto jakie zmiany możesz wprowadzić:

### Logika sygnałów w strategii:

WATCH vs. ALERT:
W metodzie analyze() strategii (np. w MomentumTrendBreakoutStrategy) wprowadź rozróżnienie:

WATCH: spółka spełnia minimalnie 2 kryteria i jest w fazie obserwacji. W polu details umieść również „trigger_entry” – potencjalny poziom wejścia (np. maksymalna cena z ostatnich 5 dni), który sugeruje, że przy przekroczeniu tego poziomu spółka może przejść do pełnego alertu.

ALERT (ENTRY): spółka spełnia 3 lub więcej kryteriów i generuje pełny sygnał wejścia. W details również pojawi się trigger entry, ale z perspektywy użytkownika będzie to już cena wejścia, która jest gotowa do wykorzystania.

### Proces decyzyjny:

Po wygenerowaniu sygnału ALERT (ENTRY) system wysyła alert, ale decyzję o otwarciu pozycji podejmuje użytkownik (np. przez dashboard lub API). Po zatwierdzeniu, sygnał zostaje przeniesiony do tabeli positions.

Dla sygnałów WATCH system może automatycznie czyścić stare wpisy (np. usuwając poprzednie WATCH alerty przed nowym skanowaniem), dzięki czemu dashboard zawsze pokazuje aktualnie obserwowane spółki.

###  Moduł monitorowania pozycji:

Po otwarciu pozycji, dodatkowy moduł (lub rozbudowana logika strategii) monitorowałby te pozycje, obliczając dynamiczne poziomy wyjścia (exit trigger), np. na podstawie trailing stop loss, spadku poniżej SMA5, RSI lub innych warunków.

System może wysyłać alerty dotyczące wyjścia z pozycji – informując, że spełnione zostały warunki do zamknięcia transakcji.

###  Lokalizacja logiki:

Cała logika związana z generowaniem sygnałów (zarówno wejścia, jak i wyjścia) powinna być zawarta w module konkretnej strategii. To on będzie analizował dane, wyliczał wskaźniki i na tej podstawie decydował, czy dany sygnał powinien mieć status WATCH, czy ALERT.

Oddzielny moduł (lub tabela) do monitorowania otwartych pozycji umożliwi Ci późniejsze podejmowanie decyzji handlowych i automatyzację wyjścia z pozycji.

### Podsumowując
### Alerty:
Sygnały generowane przez strategię będą miały status WATCH (gdy spełnione są minimalne kryteria, a trigger entry jest tylko potencjalnym poziomem wejścia) lub ALERT/ENTRY (gdy spełniono pełne kryteria). Status i szczegóły (w tym trigger_entry) będą przechowywane w tabeli alertów.

### Otwarte Pozycje:
Po zatwierdzeniu przez użytkownika, alerty ALERT mogą być przenoszone do oddzielnej tabeli positions, gdzie system będzie monitorował otwarte transakcje i generował sygnały wyjścia.

### Decyzje Użytkownika:
Użytkownik decyduje, które sygnały WATCH przekształcić w otwarte pozycje oraz otrzymuje alerty wyjścia, które mogą być wykorzystane do zarządzania transakcjami.

Takie podejście umożliwia pełną kontrolę nad cyklem transakcyjnym, od monitorowania spółek pod obserwacją, przez zatwierdzanie wejścia, aż po zarządzanie i monitorowanie otwartych pozycji. Jeśli masz dodatkowe pytania lub potrzebujesz dalszych szczegółów – śmiało pytaj!
