import os
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters, CallbackQueryHandler
)
import pandas as pd

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Загружаем Excel-файл при запуске
df = pd.read_excel(r'C:\Users\user\PycharmProjects\telegram_excel_sorter\data\Распределение.xlsx')

# Путь для сохранения заметок
NOTES_FILE = 'notes.csv'

# Убедимся, что файл для заметок существует
if not os.path.exists(NOTES_FILE):
    pd.DataFrame(columns=["User", "Magazin", "Note"]).to_csv(NOTES_FILE, index=False)

# Состояния для ConversationHandler
SEARCH, CHOOSE_RESULT, NOTE, DELETE_NOTE = range(4)


# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 Введите слово для поиска по таблице или используйте команду /view_notes для просмотра заметок."
    )
    return SEARCH


# Команда /view_notes
async def view_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        notes_df = pd.read_csv(NOTES_FILE)

        if notes_df.empty or "Note" not in notes_df.columns:
            await update.message.reply_text("📋 У вас пока нет заметок.")
        else:
            grouped = notes_df.groupby('UniqueID')

            for unique_id, group in grouped:
                magazin_name = group['Magazin'].iloc[0] if 'Magazin' in group.columns else "Неизвестно"

                # Преобразуем Код в строку и убираем точку, если есть
                unique_id_str = str(unique_id).split('.')[0]

                text = f"🏪 Магазин: {magazin_name} (Код: {unique_id_str})\n\n"
                for idx, row in group.iterrows():
                    note_text = row.get('Note', '-')
                    user = row.get('User', '-')
                    text += f"📝 {note_text} (от {user})\n"

                # Ограничим размер одного сообщения
                if len(text) > 4096:
                    for i in range(0, len(text), 4090):
                        await update.message.reply_text(text[i:i + 4090])
                else:
                    await update.message.reply_text(text)

                # Кнопки под каждым блоком
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("➕ Добавить", callback_data=f"add_{unique_id}"),
                    InlineKeyboardButton("🗑️ Удалить", callback_data=f"del_{unique_id}")
                ]
                ])
                await update.message.reply_text("Выберите действие:", reply_markup=keyboard)

        # Сообщение в конце
        await update.message.reply_text("Для начала поиска нажмите /start")

    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка при загрузке заметок: {e}")


# Форматирование результата поиска
def format_search_result(index, result, related_notes):
    result_text = (
        f"🔍 Результат поиска: {index + 1}\n\n"
        f"Код: {str(result.get('Код', 'Нет данных')).split('.')[0]}\n"
        f"Магазин: {result.get('Магазин', 'Нет данных')}\n"
        f"Тип: {result.get('Тип', 'Нет данных')}\n"
        f"ФИО системотехника: {result.get('ФИО системотехника', 'Нет данных')}\n"
        f"Адрес: {result.get('Адрес', 'Нет данных')}\n"
        f"Полный адрес: {result.get('Полный адрес', 'Нет данных')}\n\n"
    )
    result_text += "📌 Заметки:\n"
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

            await update.message.reply_text(result_text)
            keyboard.append([str(idx + 1)])

        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

        await update.message.reply_text(
            "Выберите номер результата для добавления/удаления заметки или начните новый поиск.",
            reply_markup=reply_markup
        )
        return CHOOSE_RESULT


# Обработка выбора результата
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

        # Повторно показать выбранный результат
        result_text = format_search_result(selected_index, search_results[selected_index], related_notes)
        await update.message.reply_text(result_text)

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
    return SEARCH


# Обработка нажатия кнопки "Start"
async def start_over(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📊 Введите слово для поиска по таблице или используйте команду /view_notes для просмотра заметок."
    )
    return SEARCH


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
        entry_points=[CommandHandler("start", start)],
        states={
            SEARCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search),
                CommandHandler("start", start),
                CommandHandler("view_notes", view_notes),
            ],
            CHOOSE_RESULT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, choose_result),
                CommandHandler("start", start),
                CommandHandler("view_notes", view_notes),
            ],
            NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_note_save),
                CommandHandler("start", start),
                CommandHandler("view_notes", view_notes),
            ],
            DELETE_NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, delete_note),
                CommandHandler("start", start),
                CommandHandler("view_notes", view_notes),
            ],
        },
        fallbacks=[MessageHandler(filters.ALL, fallback_handler)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("view_notes", view_notes))
    app.add_handler(CallbackQueryHandler(start_over, pattern="^start$"))

    print("Бот запущен ✅")
    app.run_polling()


if __name__ == "__main__":
    main()