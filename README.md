# Threads Autoposter (Freedom «Продукты» / Arbuz)

Автопостер для **Threads** на базе официального **Meta Threads Graph API**.
Публикует посты (с текстом или с готовыми карточками из `assets/`) и первый комментарий с твоим промокодом и инструкцией.

---

## Что настроено в проекте
* **Очередь контента (`posts.json`):** 44 ветки под Алматы и Астану (дискуссионные хуки, разборы ошибок, математика экономии, бытовые сценарии) + цикл `LOOP_QUEUE=true`.
* **Графические карточки (`assets/` и `build_cards.py`):** 6 готовых 4:5 карточек для постов. Если сменишь `PROMO_CODE` в `.env`, просто запусти `python build_cards.py`, чтобы перерисовать карточки под новый код.
* **Локальный автозапуск в Windows (`setup_scheduler.ps1`):** 4 раза в день (`10:30`, `14:30`, `19:00`, `22:00`) через `pythonw.exe` без всплывающих окон.
* **Облачный автозапуск 24/7 (`.github/workflows/autopost.yml`):** работает на GitHub Actions даже при выключенном ноутбуке.

---

## Как включить постинг 24/7 (когда ноутбук выключен) и картинки в Threads

По требованиям Meta Threads API картинки (`media_type=IMAGE`) загружаются только по **публичной HTTPS-ссылке**. Пока `IMAGE_BASE_URL` в `.env` пустой, посты безопасно выходят как `TEXT`.

Чтобы всё работало **24/7 без ноутбука** и **с картинками**:
1. Создай **публичный** репозиторий на GitHub (секреты туда не попадут — `.env` добавлен в `.gitignore`) и запушь туда содержимое папки `threads-autoposter`.
2. В настройках репозитория на GitHub:
   * **Settings → Secrets and variables → Actions → Repository secrets** добавь 3 секрета:
     * `PROMO_CODE` (твой промокод из `.env`)
     * `THREADS_ACCESS_TOKEN` (твой токен из `.env`)
     * `THREADS_USER_ID` (твой ID из `.env`)
   * **Settings → Secrets and variables → Actions → Variables** добавь переменную:
     * `IMAGE_BASE_URL` = `https://raw.githubusercontent.com/<ТВОЙ_GITHUB>/<РЕПОЗИТОРИЙ>/main`
3. Открой вкладку **Actions → Threads Cloud Autoposter → Enable workflow** (и при желании нажми **Run workflow** для проверки).
4. После переноса в облако отключи локальный планировщик на ноутбуке, чтобы не дублировать посты:
   ```powershell
   Unregister-ScheduledTask -TaskName 'ThreadsFreedomAutoposter' -Confirm:$false
   ```

*(Раз в ~50 дней обновляй `THREADS_ACCESS_TOKEN` в GitHub Secrets после вызова `autoposter.py refresh-token` локально.)*

---

## Полезные команды (локально)
* Проверить всё: `C:\Users\Huawei\AppData\Local\Python\bin\python.exe autoposter.py check`
* Посмотреть статистику: `C:\Users\Huawei\AppData\Local\Python\bin\python.exe autoposter.py status`
* Опубликовать следующий пост вручную: `C:\Users\Huawei\AppData\Local\Python\bin\python.exe autoposter.py post-next`
* Предпросмотр следующего поста: `C:\Users\Huawei\AppData\Local\Python\bin\python.exe autoposter.py post-next --dry-run`
* Перерисовать картинки из `assets/`: `C:\Users\Huawei\AppData\Local\Python\bin\python.exe build_cards.py`
* Продлить токен: `C:\Users\Huawei\AppData\Local\Python\bin\python.exe autoposter.py refresh-token`
