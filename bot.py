from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler, ContextTypes
import asyncio
from dotenv import load_dotenv
import os
from revgen import generate_reviews
from wbparser import get_product_info
import aiosqlite

# Загрузка переменных окружения
load_dotenv()

# Загрузка токена API Telegram и пути к бд из переменных окружения
TG_API_TOKEN = os.getenv('TG_API_TOKEN')
DB_PATH = os.getenv('DB_PATH')

# Состояния для ConversationHandler
ARTICLE, MODEL, RATING, PREF, GENDER, NUMBER, FORMAT = range(7)

# Обработчик команды start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    
    user_first_name = update.message.from_user.first_name  
    await update.message.reply_text(
        f"Привет, {user_first_name}! Я бот для генерации отзывов на товары маркетплейса Wildberries.\n"
        "Используйте команду /generate для начала работы."
    )

# Функция для проверки и регистрации пользователя в базе данных
async def ensure_user_registered(user_id, user_name):
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id_user FROM users WHERE id_user = ?", (user_id,))
        user = await cursor.fetchone()
        if user is None:
            await db.execute("INSERT INTO users (id_user, user_name) VALUES (?, ?)", (user_id, user_name))
            await db.commit()

# Обработчик команды генерации отзывов
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    context.user_data['user_id'] = user_id  
    
    await ensure_user_registered(user_id, user_name)
    
    await update.message.reply_text(
        "Отлично! Давайте начнем.\n"
        "Отправьте мне артикул товара, на который хотите сгенерировать отзывы."
    )
    return ARTICLE

# Обработчик команды автоматической генерации отзывов
async def autogenerate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    context.user_data['user_id'] = user_id  
    
    await ensure_user_registered(user_id, user_name)

    await update.message.reply_text(
        "Отлично! Давайте начнем.\n"
        "Отправьте мне артикул товара, на который хотите сгенерировать отзывы."
    )
    
    return ARTICLE

# Обработчик получения и проверки артикула товара (для autogenerate)
async def receive_article_for_autogenerate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    
    article = update.message.text
    if not article.isdigit() or not (6 <= len(article) <= 9):
        await update.message.reply_text("Введите корректный артикул (только числа от 6 до 9 символов).")
        return ARTICLE
    else:
        product_data = await get_product_info(article)
        if not product_data:
            await update.message.reply_text("Товар с таким артикулом не найден... \nПопробуйте другой артикул.")
            return ARTICLE
        else:
            # Параметры по-умолчанию для autogenerate
            context.user_data.update({
                'article': article,
                'model': 'gpt-4o-mini',
                'rating_preference':'balanced',
                'gender_preference': None,  
                'num_reviews': 5,          
                'format_type': 'xlsx'     
            })
            
            await update.message.reply_text("Генерация отзывов началась.\nЭто может занять некоторое время...")
            asyncio.create_task(register_generation(
                context.user_data['user_id'], 
                article, 
                'gpt-4o-mini', 
                'balanced',
                None, 
                5, 
                'xlsx', update
            ))
            return ConversationHandler.END

# Обработчик для получения и проверки артикула товара (для generate)
async def receive_article(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    
    article = update.message.text
    if not article.isdigit() or not (6 <= len(article) <= 9):
        await update.message.reply_text("Введите корректный артикул .\n"
                                        "(только числа от 6 до 9 символов).")
        return ARTICLE
    else:
        product_data = await get_product_info(article)
        if not product_data:
            await update.message.reply_text("Товар с таким артикулом не найден. .\n"
                                            "Попробуйте другой артикул.")
            return ARTICLE
        else:
            context.user_data['article'] = article
            keyboard = [
                [InlineKeyboardButton("🚀 GPT-4o-mini", callback_data='gpt-3.5-turbo-0125'),
                 InlineKeyboardButton("🧠 GPT-4o", callback_data='gpt-4o-mini')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Выберите модель для генерации отзывов:\n\n"
                "<b>🚀 GPT-3.5 Turbo:</b>\n"
                "Быстрая и надежная.\n"
                "📊 Качество: 🟪🟪🟪🟪🟪🟪⬜️⬜️⬜️⬜️ (6 из 10)\n"
                "⏱️ Скорость: 🟪🟪🟪🟪🟪🟪🟪🟪🟪⬜️ (9 из 10)\n\n"
                "<b>🧠 GPT-4 Turbo:</b>\n"
                "Самая передовая модель.\n"
                "📊 Качество: 🟪🟪🟪🟪🟪🟪🟪🟪🟪🟪 (10 из 10)\n"
                "⏱️ Скорость: 🟪🟪🟪🟪🟪⬜️⬜️⬜️⬜️⬜️(5 из 10)",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            return MODEL

# Обработчик выбора модели 
async def receive_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    
    query = update.callback_query
    await query.answer()
    model_choice = query.data
    context.user_data['model'] = model_choice
    return await ask_for_rating(update, context)

# Выбор рейтинга
async def ask_for_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    
    keyboard = [
        [InlineKeyboardButton("🔵 Сбалансированный (1-5🌟)", callback_data='balanced')],
        [InlineKeyboardButton("🟢 Положительный (4-5🌟)", callback_data='positive')],
        [InlineKeyboardButton("🟡 Нейтральный (3🌟)", callback_data='neutral')],
        [InlineKeyboardButton("🔴 Отрицательный (1-2🌟)", callback_data='negative')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.reply_text(
        'Выберите требуемый рейтинг отзывов: \n(Рекомендуется сбалансированный режим)',
        reply_markup=reply_markup
    )
    return RATING

# Обработчик рейтинга
async def receive_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    
    query = update.callback_query
    await query.answer()
    context.user_data['rating_preference'] = query.data
    
    keyboard = [
        [InlineKeyboardButton("✅ Да", callback_data='yes')],
        [InlineKeyboardButton("❌ Нет", callback_data='no')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.reply_text('Вы хотите получить отзывы от конкретной аудитории?\n (Мужчины/Женщины)', reply_markup=reply_markup)
    return PREF

# Обработчик выбора предпочтений пользователя
async def receive_gender_preference(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    
    query = update.callback_query
    await query.answer()
    if query.data == 'yes':
        keyboard = [
            [InlineKeyboardButton("🤵‍♂️ Мужчины", callback_data='мужчина')],
            [InlineKeyboardButton("👩 Женщины", callback_data='женщина')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text('Выберите пол для отзывов:', reply_markup=reply_markup)
        return GENDER
    else:
        context.user_data['gender_preference'] = None  # Установка значения по умолчанию при выборе 'Нет'
        await query.message.reply_text("Сколько отзывов вы хотите сгенерировать?\n"
                                       "Введите количество (от 1 до 10).")
        return NUMBER

# Обработчик выбора гендера
async def receive_gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    
    query = update.callback_query
    await query.answer()
    context.user_data['gender_preference'] = query.data  # Сохраняем выбор пола: 'male' или 'female'
    
    await query.message.reply_text("Сколько отзывов вы хотите сгенерировать?\n"
                                   "Введите количество (от 1 до 10).")
    return NUMBER

# Обработчик выбора количества отзывов
async def receive_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    
    text = update.message.text
    if text.isdigit() and 1 <= int(text) <= 10:
        context.user_data['num_reviews'] = int(text)
        keyboard = [
            [InlineKeyboardButton("CSV", callback_data='csv'),
             InlineKeyboardButton("JSON", callback_data='json'),
             InlineKeyboardButton("XML", callback_data='xml'),
             InlineKeyboardButton("XLSX", callback_data='xlsx')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            'Выберите формат файла для сохранения отзывов:', reply_markup=reply_markup
        )
        return FORMAT
    else:
        await update.message.reply_text("Введите корректное число отзывов от 1 до 10.")
        return NUMBER

# Обработчик выбора формата файла для сохранения отзывов
async def format_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer() 
    
    format_type = query.data  
    context.user_data['format_type'] = format_type  
    
    user_id = context.user_data['user_id']
    product_id = context.user_data['article']
    num_reviews = context.user_data['num_reviews']
    rating_preference =context.user_data['rating_preference']
    model_name = context.user_data['model']
    gender_preference = context.user_data['gender_preference']
    
    await query.message.reply_text("Генерация отзывов началась.\nЭто может занять некоторое время...")

    asyncio.create_task(register_generation(user_id, product_id, model_name, rating_preference, gender_preference, num_reviews, format_type, query))

    return ConversationHandler.END

# Функция генерации отзывов (и записи информации о генерации в бд)
async def register_generation(user_id, product_id, model_name, rating_preference, gender_preference, num_reviews, format_type, query):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO generation (id_user, id_product, model, rating_pref, num_reviews) VALUES (?, ?, ?, ?, ?)
        """, (user_id, product_id, model_name, rating_preference, num_reviews))
        await db.commit()
        cursor = await db.execute("SELECT last_insert_rowid()")
        id_gen = (await cursor.fetchone())[0]
        
    review_output = await generate_reviews(product_id, id_gen, rating_preference, gender_preference, num_reviews, model_name, format_type)

    if isinstance(review_output, str):
        with open(review_output, 'rb') as file:
            await query.message.reply_document(document=file, filename=os.path.basename(review_output))
    else:
        await query.message.reply_document(document=review_output, filename=f'reviews.{format_type}')

# Запуск повторной генерации отзывов 
async def regenerate_reviews(query, context):
    
    user_id = context.user_data['user_id']
    product_id = context.user_data['article']
    num_reviews = context.user_data['num_reviews']
    format_type = context.user_data['format_type']
    model_name = context.user_data['model']
    rating_preference =context.user_data['rating_preference']
    gender_preference = context.user_data['gender_preference']
    
    await query.message.reply_text("Генерация отзывов началась.\n" 
                                   "Это может занять некоторое время...")
    
    asyncio.create_task(register_generation(user_id, product_id, model_name, rating_preference, gender_preference, num_reviews, format_type, query))

    return ConversationHandler.END

# Обработчик команды повторной генерации 
async def regenerate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if all(key in context.user_data for key in ['article', 'num_reviews', 'format_type', 'model','rating_preference','gender_preference']):
        await update.message.reply_text("Повторная генерация отзывов запущена.")
        await regenerate_reviews(update, context)
    else:
        await update.message.reply_text("Не найдены данные для повторной генерации.\n" 
                                        "Пожалуйста, используйте /generate для начала новой генерации.")

def main():
    app = Application.builder().token(TG_API_TOKEN).build()
    
    # Создание обработчика диалогов 
    manual_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start), 
            CommandHandler("generate", generate), 
            ],
        states={
            ARTICLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_article)],  # Обработка ввода артикула
            MODEL: [CallbackQueryHandler(receive_model)], # Выбор модели для генерации
            RATING: [CallbackQueryHandler(receive_rating)],  # Выбор рейтинга
            PREF: [CallbackQueryHandler(receive_gender_preference)],  # Выбор предпочтения по полу
            GENDER: [CallbackQueryHandler(receive_gender)], # Выбор конкретного пола
            NUMBER: [MessageHandler(filters.Regex('^\d+$'), receive_number)], # Ввод количества отзывов
            FORMAT: [CallbackQueryHandler(format_choice)] # Выбор формата файла
        },
        fallbacks=[CommandHandler('start', start)],
        per_message=False,
        per_chat=True,
        per_user=True 
    )

    auto_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("autogenerate", autogenerate)
            ],
        states={
            ARTICLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_article_for_autogenerate)]
        },
        fallbacks=[CommandHandler('start', start)],
        per_message=False,
        per_chat=True,
        per_user=True 
    )

    app.add_handler(manual_handler)
    app.add_handler(auto_handler)
    app.add_handler(CommandHandler('regenerate', regenerate))
    app.add_handler(CommandHandler('autogenerate', autogenerate))
    app.run_polling()
    
if __name__ == '__main__':

    main()