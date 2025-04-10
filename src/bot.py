import pandas as pd
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)

TOKEN = '7707299902:AAHj0fQYIEjxuZaPLxYB8IX_jFttPgMmc4Y'

# Загружаем Excel-файл при запуске
df = pd.read_excel(r'C:\Users\user\PycharmProjects\telegram_excel_sorter\data\Распределение.xlsx')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для поиска по таблице 📊\n"
        "Введите слово для поиска в таблице."
    )

async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = update.message.text.lower()  # Получаем текст запроса
    result = df[df.apply(lambda row: row.astype(str).str.lower().str.contains(keyword).any(), axis=1)]  # Поиск по ключевому слову

    if result.empty:
        await update.message.reply_text("🔍 Ничего не найдено.")  # Если нет результатов
    else:
        # Формируем текст с результатами
        result_text = ""
        for idx, row in result.head(10).iterrows():  # Берем первые 10 строк результата
            result_text += f"Строка {idx + 1}:\n"
            for col, val in row.items():
                result_text += f"{col}: {val}\n"  # Каждый столбец на новой строке
            result_text += "\n"  # Пустая строка между результатами

        # Ограничим длину сообщения (если нужно) и отправим
        result_text = result_text[:4096]  # Telegram ограничивает длину сообщений (4096 символов)

        await update.message.reply_text(f"Результаты поиска по ключевому слову: {keyword}\n\n{result_text}")

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))  # Обработчик команды /start
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search))  # Обработчик для поиска

    print("Бот запущен ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
