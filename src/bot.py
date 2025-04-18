import os
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters, CallbackQueryHandler
)
import pandas as pd
import logging

# Устанавливаем уровень логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

application = Application.builder().token(TOKEN).build()

# Загружаем Excel-файл при запуске
df = pd.read_excel(r'C:\Users\user\PycharmProjects\telegram_excel_sorter\data\Распределение.xlsx')

# Путь для сохранения заметок
NOTES_FILE = 'notes.csv'

# Убедимся, что файл для заметок существует
if not os.path.exists(NOTES_FILE):
    pd.DataFrame(columns=["User", "Keywords", "UniqueID", "Magazin", "Note"]).to_csv(NOTES_FILE, index=False)

# Состояния для ConversationHandler
SEARCH, CHOOSE_RESULT, NOTE, DELETE_NOTE = range(4)


# Команда /start
async def start_combined(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "📊 Введите слово для поиска по таблице или используйте команду /view_notes для просмотра заметок."
        )
    elif update.message:
        await update.message.reply_text(
            "📊 Введите слово для поиска по таблице или используйте команду /view_notes для просмотра заметок."
        )
    return SEARCH


# Форматирование результата поиска
def format_search_result(index, result, related_notes):
    result_text = (
        f"🔍 <b>Результат поиска: {index + 1}</b>\n\n"
        f"<b>Код:</b> {str(result.get('Код', 'Нет данных')).split('.')[0]}\n"
        f"<b>Магазин: </b> {result.get('Магазин', 'Нет данных')}\n"
        f"<b>Тип: </b> {result.get('Тип', 'Нет данных')}\n"
        f"<b>ФИО системотехника: </b> {result.get('ФИО системотехника', 'Нет данных')}\n"
        f"<b>Адрес: </b><code>{result.get('Адрес', 'Нет данных')}</code>\n"
        f"<b>Полный адрес:</b>{result.get('Полный адрес', 'Нет данных')}\n\n"
    )

    result_text += "📌 <b>Заметки:</b>\n"
    if related_notes.empty:
        result_text += "-\n"
    else:
        for local_index, note_row in enumerate(related_notes.itertuples(), start=1):
            result_text += f"{local_index}. {note_row.Note}\n"
    return result_text


# Обработка поиска
async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = update.message.text.lower()
    context.user_data['last_keyword'] = keyword

    result = df[df.apply(lambda row: row.astype(str).str.lower().str.contains(keyword).any(), axis=1)]
    notes_df = pd.read_csv(NOTES_FILE)

    if result.empty:
        await update.message.reply_text("🔍 Ничего не найдено. Введите другое ключевое слово.")
        return SEARCH
    else:
        context.user_data['search_results'] = result.head(10).to_dict(orient="records")
        keyboard = [["Начать новый поиск"]]

        for idx, row in enumerate(context.user_data['search_results']):
            unique_id = row.get('Код', 'Нет данных')
            row_notes = notes_df[notes_df['UniqueID'] == unique_id]
            result_text = format_search_result(idx, row, row_notes)

            await update.message.reply_text(result_text, parse_mode="HTML")
            keyboard.append([str(idx + 1)])

        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

        await update.message.reply_text(
            "Выберите номер результата для добавления/удаления заметки или начните новый поиск.",
            reply_markup=reply_markup
        )
        return CHOOSE_RESULT


# Обработка выбора результата поиска
async def choose_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected_text = update.message.text.strip()

    if selected_text.lower() == "начать новый поиск":
        await update.message.reply_text(
            "Введите новое ключевое слово для поиска:",
            reply_markup=ReplyKeyboardRemove()
        )
        return SEARCH

    if not selected_text.isdigit():
        await update.message.reply_text(
            "Ошибка: пожалуйста, введите только номер результата из списка."
        )
        return CHOOSE_RESULT

    selected_index = int(selected_text) - 1
    search_results = context.user_data.get('search_results', [])

    if 0 <= selected_index < len(search_results):
        context.user_data['selected_result'] = search_results[selected_index]
        unique_id = search_results[selected_index].get('Код', 'Нет данных')
        notes_df = pd.read_csv(NOTES_FILE)
        related_notes = notes_df[notes_df['UniqueID'] == unique_id]

        result_text = format_search_result(selected_index, search_results[selected_index], related_notes)
        await update.message.reply_text(result_text, parse_mode="HTML")

        # сохраняем уникальный код для добавления заметки
        context.user_data['add_note_unique_id'] = unique_id

        if related_notes.empty:
            await update.message.reply_text(
                "Введите текст заметки:",
                reply_markup=ReplyKeyboardRemove()
            )
            return NOTE
        else:
            keyboard = [["Добавить заметку"]]
            if len(related_notes) > 1:
                keyboard[0].append("Удалить все заметки")

            for idx, _ in enumerate(related_notes.itertuples(), start=1):
                keyboard.append([f"Удалить заметку {idx}"])
            keyboard.append(["Вернуться назад"])

            reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

            await update.message.reply_text(
                "Выберите действие:",
                reply_markup=reply_markup
            )
            context.user_data['related_notes'] = related_notes
            return DELETE_NOTE
    else:
        await update.message.reply_text(
            "Ошибка: номер результата вне допустимого диапазона. Выберите номер из списка."
        )
        return CHOOSE_RESULT


# Добавление заметки
async def add_note_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note_text = update.message.text.strip()
    unique_id = context.user_data.get('add_note_unique_id')

    logger.debug(f"Получен уникальный код: {unique_id}, текст заметки: {note_text}")

    if unique_id and note_text:
        try:
            # Проверка на наличие файла и его загрузку
            if not os.path.exists(NOTES_FILE):
                logger.error(f"Файл {NOTES_FILE} не существует!")
                await update.message.reply_text(f"❌ Ошибка: файл заметок не найден.")
                return

            notes_df = pd.read_csv(NOTES_FILE)
            logger.debug(f"Загружены заметки: {notes_df.head()}")

            # Создаем новую строку с заметкой
            new_note = {
                'UniqueID': unique_id,
                'Note': note_text,
                'User': update.message.from_user.first_name  # или .full_name если хочешь полное имя
            }
            new_note_df = pd.DataFrame([new_note])  # Преобразуем в DataFrame

            # Добавляем новую строку в основной DataFrame
            notes_df = pd.concat([notes_df, new_note_df], ignore_index=True)
            notes_df.to_csv(NOTES_FILE, index=False)  # Сохраняем в файл
            logger.debug(f"Заметка добавлена: {new_note}")

            # Ответ пользователю
            await update.message.reply_text("📝 Заметка добавлена!")
            await update.message.reply_text(
                "📊 Введите слово для поиска по таблице или используйте команду /view_notes для просмотра заметок.",
                reply_markup=ReplyKeyboardRemove()  # Убираем клавиатуру после добавления
            )

            # Переходим в состояние поиска
            return SEARCH  # Переход к состоянию поиска

        except Exception as e:
            logger.error(f"Ошибка при добавлении заметки: {e}")
            await update.message.reply_text(f"❌ Ошибка при добавлении заметки: {e}")
    else:
        logger.warning("Ошибка: уникальный код или текст заметки отсутствует.")
        await update.message.reply_text("❌ Сессия завершена. Нажмите /start для начала поиска")

    return ConversationHandler.END  # Завершаем разговор


# Сохранение заметки
async def handle_note_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note_text = update.message.text
    user = update.effective_user.first_name
    selected_result = context.user_data.get('selected_result', {})

    unique_id = selected_result.get('Код', 'Нет данных')
    magazin = selected_result.get('Магазин', 'Не указан')

    notes_df = pd.read_csv(NOTES_FILE)

    new_note = pd.DataFrame([[user, "", unique_id, magazin, note_text]],
                            columns=["User", "Keywords", "UniqueID", "Magazin", "Note"])
    notes_df = pd.concat([notes_df, new_note], ignore_index=True)
    notes_df.to_csv(NOTES_FILE, index=False)

    # Измененный вывод сообщений после добавления заметки
    await update.message.reply_text("📝 Заметка добавлена!")
    await update.message.reply_text("📊 Введите слово для поиска по таблице или используйте команду /view_notes для просмотра заметок.",
                                     reply_markup=ReplyKeyboardRemove())
    return SEARCH  # Переход к следующему шагу (поиск)


# Удаление заметки
async def delete_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected_text = update.message.text.strip()
    related_notes = context.user_data.get('related_notes', pd.DataFrame())

    if selected_text == "Добавить заметку":
        await update.message.reply_text(
            "Введите текст заметки:",
            reply_markup=ReplyKeyboardRemove()
        )
        return NOTE

    if selected_text.startswith("Удалить заметку"):
        try:
            selected_index = int(selected_text.split()[-1]) - 1
            if 0 <= selected_index < len(related_notes):
                selected_note = related_notes.iloc[selected_index]
                notes_df = pd.read_csv(NOTES_FILE)
                notes_df = notes_df[~((notes_df['UniqueID'] == selected_note['UniqueID']) &
                                      (notes_df['Note'] == selected_note['Note']))]
                notes_df.to_csv(NOTES_FILE, index=False)

                # Изменённый вывод сообщений после удаления заметки
                await update.message.reply_text("🗑️ Заметка удалена.")
                await update.message.reply_text("📊 Введите слово для поиска по таблице или используйте команду /view_notes для просмотра заметок.")
                return SEARCH
            else:
                raise ValueError("Неверный индекс")
        except ValueError:
            await update.message.reply_text(
                "Ошибка: номер заметки вне допустимого диапазона. Попробуйте снова."
            )
            return DELETE_NOTE

    if selected_text == "Удалить все заметки":
        selected_result = context.user_data.get('selected_result', {})
        unique_id = selected_result.get('Код', 'Нет данных')

        notes_df = pd.read_csv(NOTES_FILE)
        notes_df = notes_df[notes_df['UniqueID'] != unique_id]
        notes_df.to_csv(NOTES_FILE, index=False)

        await update.message.reply_text("🗑️ Все заметки удалены.")
        await update.message.reply_text("📊 Введите слово для поиска по таблице или используйте команду /view_notes для просмотра заметок.")
        return SEARCH

    if selected_text == "Вернуться назад":
        search_results = context.user_data.get('search_results', [])
        keyboard = [["Начать новый поиск"]]
        for idx, row in enumerate(search_results):
            keyboard.append([str(idx + 1)])

        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

        await update.message.reply_text(
            "Выберите номер результата для добавления/удаления заметки или начните новый поиск.",
            reply_markup=reply_markup
        )
        return CHOOSE_RESULT

    await update.message.reply_text(
        "Ошибка: выберите корректное действие."
    )
    return DELETE_NOTE


# Команда /view_notes
async def view_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not os.path.exists(NOTES_FILE):
            logger.error(f"Файл {NOTES_FILE} не найден!")
            await update.message.reply_text(f"❌ Ошибка: файл заметок не найден.")
            return

        notes_df = pd.read_csv(NOTES_FILE)
        logger.debug(f"Загружены заметки: {notes_df.head()}")

        if notes_df.empty or "Note" not in notes_df.columns:
            await update.message.reply_text("📋 У вас пока нет заметок.")
        else:
            grouped = notes_df.groupby('UniqueID')

            for unique_id, group in grouped:
                unique_id_str = str(unique_id).split('.')[0]

                # Находим имя магазина по коду в основном df
                store_name = df[df['Код'].astype(str).str.split('.').str[0] == unique_id_str]['Магазин'].values
                magazin_name = store_name[0] if len(store_name) > 0 else "Неизвестно"

                text = f"🏪 Магазин: {magazin_name} (Код: {unique_id_str})\n\n"
                for idx, row in group.iterrows():
                    note_text = row.get('Note', '-')
                    user = row.get('User', '-')
                    text += f"📝 {note_text} (от {user})\n"

                if len(text) > 4096:
                    for i in range(0, len(text), 4090):
                        await update.message.reply_text(text[i:i + 4090])
                else:
                    await update.message.reply_text(text)

                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("➕ Добавить", callback_data=f"add_{unique_id}"),
                    InlineKeyboardButton("🗑️ Удалить", callback_data=f"del_{unique_id}")
                ]])
                await update.message.reply_text("Выберите действие:", reply_markup=keyboard)

        await update.message.reply_text("Для начала поиска нажмите /start")

    except Exception as e:
        logger.error(f"Ошибка при загрузке заметок: {e}")
        await update.message.reply_text(f"⚠️ Ошибка при загрузке заметок: {e}")


# Обработчик кнопки "Добавить"
async def add_note_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Извлекаем unique_id из callback_data
    callback_data = update.callback_query.data
    unique_id = callback_data.split('_')[1]

    # Отправляем запрос на добавление заметки
    await update.callback_query.answer()  # Откликаемся на кнопку
    await update.callback_query.message.reply_text(
        "Введите текст для новой заметки:",
        reply_markup=ReplyKeyboardRemove()  # Убираем клавиатуру
    )

    # Сохраняем unique_id в context.user_data для использования в следующем шаге
    context.user_data['add_note_unique_id'] = unique_id
    return NOTE  # Переход к следующему шагу (НЕ ADD_NOTE)


# Универсальный обработчик
async def fallback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and (update.message.text.startswith('/start') or update.message.text.startswith('/view_notes')):
        return

    if update.message:
        await update.message.reply_text(
            "🤖 Я не понял это сообщение. Нажмите кнопку ниже, чтобы начать заново.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 Начать заново", callback_data="start")]
            ])
        )
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "🤖 Что-то пошло не так. Нажмите кнопку ниже, чтобы начать заново.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 Начать заново", callback_data="start")]
            ])
        )


# Основная функция
def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_combined),
            CallbackQueryHandler(start_combined, pattern="^start$"),
        ],
        states={
            SEARCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search),
                CommandHandler("start", start_combined),
                CommandHandler("view_notes", view_notes),
                CallbackQueryHandler(add_note_callback, pattern="^add_"),
                CallbackQueryHandler(start_combined, pattern="^start$"),
            ],
            CHOOSE_RESULT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, choose_result),
                CommandHandler("start", start_combined),
                CommandHandler("view_notes", view_notes),
                CallbackQueryHandler(start_combined, pattern="^start$"),
            ],
            NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_note_text),
                CommandHandler("start", start_combined),
                CommandHandler("view_notes", view_notes),
                CallbackQueryHandler(start_combined, pattern="^start$"),
            ],
            DELETE_NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, delete_note),
                CommandHandler("start", start_combined),
                CommandHandler("view_notes", view_notes),
                CallbackQueryHandler(start_combined, pattern="^start$"),
            ],
        },
        fallbacks=[MessageHandler(filters.ALL, fallback_handler)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("view_notes", view_notes))
    app.add_handler(CommandHandler('start', start_combined))
    app.add_handler(CallbackQueryHandler(start_combined, pattern='^start$'))
    app.add_handler(CallbackQueryHandler(add_note_callback, pattern='^add_'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_note_text))

    print("Бот запущен ✅")
    app.run_polling()


if __name__ == "__main__":
    main()