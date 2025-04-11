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
    pd.DataFrame(columns=["User", "Keywords", "UniqueID", "Magazin", "Note"]).to_csv(NOTES_FILE, index=False)

# Состояния для ConversationHandler
SEARCH, CHOOSE_RESULT, NOTE, DELETE_NOTE = range(4)


# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для поиска по таблице 📊\n"
        "Введите слово для поиска в таблице или используйте команду /view_notes для просмотра заметок."
    )
    return SEARCH


# Команда /view_notes
async def view_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    notes_df = pd.read_csv(NOTES_FILE)
    if notes_df.empty:
        await update.message.reply_text("📋 У вас пока нет заметок.")
        return

    response_text = "📋 Ваши заметки:\n"
    for idx, note_row in notes_df.iterrows():
        response_text += (
            f"{idx + 1}. Пользователь: {note_row['User']}\n"
            f"Магазин: {note_row['Magazin']}\n"
            f"Заметка: {note_row['Note']}\n\n"
        )

    await update.message.reply_text(response_text)


# Форматирование результата поиска
def format_search_result(index, result, related_notes):
    result_text = (
        f"🔍 Результат поиска: {index + 1}\n\n"
        f"Код: {result.get('Код', 'Нет данных')}\n"
        f"Магазин: {result.get('Магазин', 'Нет данных')}\n"
        f"Тип: {result.get('Тип', 'Нет данных')}\n"
        f"ФИО системотехника: {result.get('ФИО системотехника', 'Нет данных')}\n"
        f"Адрес: {result.get('Адрес', 'Нет данных')}\n"
        f"Полный адрес: {result.get('Полный адрес', 'Нет данных')}\n\n"
    )
    # Добавляем заметки, если они есть
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

    # Поиск в основном файле
    result = df[df.apply(lambda row: row.astype(str).str.lower().str.contains(keyword).any(), axis=1)]

    # Загружаем заметки для текущего ключевого слова
    notes_df = pd.read_csv(NOTES_FILE)

    if result.empty:
        await update.message.reply_text("🔍 Ничего не найдено. Введите другое ключевое слово.")
        return SEARCH
    else:
        # Сохраняем результаты поиска в контекст пользователя
        context.user_data['search_results'] = result.head(10).to_dict(orient="records")

        keyboard = []  # Кнопки для выбора результатов

        for idx, row in enumerate(context.user_data['search_results']):
            # Получаем заметки для текущего результата по уникальному идентификатору
            unique_id = row.get('Код', 'Нет данных')
            row_notes = notes_df[notes_df['UniqueID'] == unique_id]
            result_text = format_search_result(idx, row, row_notes)

            # Отправляем сообщение с результатом
            await update.message.reply_text(result_text)

            # Добавляем кнопку для выбора результата
            keyboard.append([str(idx + 1)])  # Кнопка для выбора результата

        # Добавляем кнопку "Начать новый поиск"
        keyboard.append(["Начать новый поиск"])

        # Кнопки для выбора результатов
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

        await update.message.reply_text(
            "Выберите номер результата для добавления/удаления заметки или начните новый поиск.",
            reply_markup=reply_markup
        )
        return CHOOSE_RESULT


# Обработка выбора результата
async def choose_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected_text = update.message.text.strip()

    # Проверяем, нажал ли пользователь "Начать новый поиск"
    if selected_text.lower() == "начать новый поиск":
        await update.message.reply_text(
            "Введите новое ключевое слово для поиска:",
            reply_markup=ReplyKeyboardRemove()  # Убираем клавиатуру
        )
        return SEARCH

    # Проверяем, является ли введённое значение числом
    if not selected_text.isdigit():
        await update.message.reply_text(
            "Ошибка: пожалуйста, введите только номер результата из списка."
        )
        return CHOOSE_RESULT

    selected_index = int(selected_text) - 1  # Преобразуем ввод в индекс (с учётом нумерации с 0)
    search_results = context.user_data.get('search_results', [])

    # Проверяем, находится ли выбранный номер в допустимых пределах
    if 0 <= selected_index < len(search_results):
        context.user_data['selected_result'] = search_results[selected_index]
        unique_id = search_results[selected_index].get('Код', 'Нет данных')
        notes_df = pd.read_csv(NOTES_FILE)
        related_notes = notes_df[notes_df['UniqueID'] == unique_id]

        if related_notes.empty:
            # Если заметок нет, предлагаем добавить новую
            await update.message.reply_text(
                "Введите текст заметки:",
                reply_markup=ReplyKeyboardRemove()
            )
            return NOTE
        else:
            # Если заметки есть, создаем кнопки для добавления и удаления
            keyboard = [["Добавить новую заметку"]]
            for idx, _ in enumerate(related_notes.itertuples(), start=1):
                keyboard.append([f"Удалить заметку {idx}"])

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

    if selected_text == "Добавить новую заметку":
        # Добавление новой заметки
        await update.message.reply_text(
            "Введите текст новой заметки:",
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
                await update.message.reply_text("🗑️ Заметка удалена! Возвращаемся к поиску.")
                return SEARCH
            else:
                raise ValueError("Неверный индекс")
        except ValueError:
            await update.message.reply_text(
                "Ошибка: номер заметки вне допустимого диапазона. Попробуйте снова."
            )
            return DELETE_NOTE

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

    await update.message.reply_text("📝 Заметка добавлена! Возвращаемся к поиску.")
    await update.message.reply_text("Введите слово для поиска в таблице:", reply_markup=ReplyKeyboardRemove())
    return SEARCH


# Универсальный обработчик для неактивного бота
async def fallback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Бот неактивен. Нажмите кнопку ниже, чтобы начать заново.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Start", callback_data="start")]])
    )


# Обработка нажатия кнопки "Start"
async def start_over(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Отвечаем на нажатие кнопки
    await query.edit_message_text(
        "Привет! Я бот для поиска по таблице 📊\nВведите слово для поиска или используйте команду /view_notes для просмотра заметок."
    )
    return SEARCH


# Основная функция
def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SEARCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search),
            ],
            CHOOSE_RESULT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, choose_result),
            ],
            NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_note_save),
            ],
            DELETE_NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, delete_note),
            ],
        },
        fallbacks=[MessageHandler(filters.ALL, fallback_handler)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("view_notes", view_notes))  # Новый обработчик
    app.add_handler(CallbackQueryHandler(start_over, pattern="^start$"))

    print("Бот запущен ✅")
    app.run_polling()


if __name__ == "__main__":
    main()