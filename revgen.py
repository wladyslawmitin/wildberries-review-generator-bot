import asyncio
import random
import pandas as pd
import sys
import os
import json
import io
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
import openai
from openai import AsyncOpenAI
import selectors
import aiosqlite
from wbparser import get_product_info
import preprompt as pp

# Загрузка переменных окружения
load_dotenv()

# Загрузка пути к базе данных
DB_PATH = os.getenv('DB_PATH')

# Авторизация по API ключу
async def authorization():
    client = openai.AsyncClient(api_key=os.getenv("OPENAI_API_KEY"))
    return client

# Функция для получения ответов от модели
async def get_model_responses(prompt, model_name):
    client = await authorization()
    response = await client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000,
        temperature=1
    )

    return response.choices[0].message.content

# Функция для преобразования характеристик в более читаемый для модели вид
def get_char_prompt(product_data):
    prompt_parts = [
        f"Наименование товара: {product_data['наименование_товара']}",
        f"Категория: {product_data['категория']}",
        f"Подкатегория: {product_data['подкатегория']}",
        f"Описание товара: {product_data['описание_товара']}",
        f"Цена в рублях: {product_data['цена_в_рублях']}"
    ]
    for key, value in product_data.items():
        if key not in ['идентификатор', 'наименование_товара', 'категория', 'подкатегория', 'описание_товара', 'цена_в_рублях', 'ссылка']:
            readable_key = key.replace('_', ' ').capitalize()
            prompt_parts.append(f"{readable_key}: {value}")
    return "\n".join(prompt_parts).strip()

# Функция извлечения сценариев из ответа модели и выбора случайного сценария
async def parse_scenarios(data):
    # Разбивка текста на строки
    lines = data.split('\n')
    
    # Словарь для хранения сценариев
    scenarios_dict = {"0": "Придумай сценарий сам"}
    
    current_key = None
    current_text = []
    
    for line in lines:
        if line.startswith(tuple(f"{i}." for i in range(1, 11))):
            if current_key:
                scenarios_dict[current_key] = ' '.join(current_text).strip()
                current_text = []
            current_key = line.split('.')[0]
            current_text.append(line[len(current_key) + 2:])
        else:
            current_text.append(line)
    
    if current_key:
        scenarios_dict[current_key] = ' '.join(current_text).strip()
    
    return random.choice(list(scenarios_dict.values()))

# Функция создания итогового промпта
async def build_prompt(product_id, id_gen, rating_preference, gender_preference, model_name="gpt-4o-mini"):
    product_data = await get_product_info(product_id)
    product_info = get_char_prompt(product_data)
    product_name = product_data['наименование_товара']
    sex, profession, income, marital_status, children, hobby = pp.who_am_i(gender_preference)

    task_descr = pp.get_task_deskr(product_name)
    product_charact = pp.get_product_charact(product_info)
    review_prescription = pp.get_review_prescription(product_name)
    reviewer_profile = pp.get_reviewer_profile(sex, profession, income, marital_status, children, hobby)
    
    situation_prompt = pp.create_situation(sex, profession, income, marital_status, children, hobby, product_info)
    situation_description = await get_model_responses(situation_prompt, model_name)
    current_situation = await parse_scenarios(situation_description)
    situation = pp.get_situation(current_situation, product_name)
    
    additionally = pp.get_additionally()
    review_type, rating = pp.get_review_type(product_name,rating_preference)
    
    grammar_instruct = pp.get_grammar_instruct()
    facts = pp.get_facts(product_name)

    complete_prompt = f"{task_descr}{product_charact}{review_prescription}{reviewer_profile}{situation}{additionally}{review_type}{grammar_instruct}{facts}"
    
    # Записываем данные о генерации
    context_data = {
        'id_gen': id_gen,
        'rating': rating,
        'sex': sex,
        'profession': profession,
        'marital_status': marital_status,
        'children': children,
        'hobby': hobby,
        'current_situation': current_situation
    }
    
    return complete_prompt, context_data

# Функция генерации отзывов
async def generate_reviews(product_id, id_gen, rating_preference, gender_preference, num_reviews, model_name, format_type):
    
    if_windows()
    
    prompts_and_contexts = [await build_prompt(product_id, id_gen, rating_preference, gender_preference, model_name) for _ in range(num_reviews)]
    prompts = [item[0] for item in prompts_and_contexts]
    context_datas = [item[1] for item in prompts_and_contexts]

    reviews = await asyncio.gather(*(get_model_responses(prompt, model_name) for prompt in prompts))
    num_review = 0
    
    all_new_rows = []

    # Записываем все отзывы в бд
    for context_data, review in zip(context_datas, reviews):
        num_review += 1
        await save_review(
            context_data['id_gen'],
            num_review,
            review,
            context_data['rating'],
            context_data['current_situation'],
            context_data['sex'],
            context_data['profession'],
            context_data['marital_status'],
            context_data['children'],
            context_data['hobby']
        )
        
        all_new_rows.append({
            'id_gen': context_data['id_gen'],
            'product_id': product_id,
            'num_review': num_review,
            'review': review,
            'rating': context_data['rating'],
            'sex': context_data['sex']
        })
    
    reviews_df = pd.DataFrame(all_new_rows)
    
    if format_type == 'csv':
        output = io.StringIO()
        reviews_df.to_csv(output, index=False)
        output.seek(0)
        return output
        
    elif format_type == 'json':
        output = io.StringIO()
        reviews_df.to_json(output, orient='records', force_ascii=False)
        output.seek(0)
        return output
        
    elif format_type == 'xml':
        root = ET.Element("Reviews")
        for _, row in reviews_df.iterrows():
            review_element = ET.SubElement(root, "Review")
            for col in reviews_df.columns:
                child = ET.SubElement(review_element, col)
                child.text = str(row[col])
        xml_string = ET.tostring(root, encoding='unicode', method='xml')
        output = io.BytesIO()
        output.write(xml_string.encode('utf-8'))  
        output.seek(0)
        return output
        
    elif format_type == 'xlsx':
        output = io.BytesIO()
        reviews_df.to_excel(output, index=False)
        output.seek(0)
        return output

# Функция добавления записей об отзывах в бд
async def save_review(id_gen, num_review, review, rating, current_situation, sex, profession, marital_status, children, hobby):
    try:
        async with aiosqlite.connect(DB_PATH) as db: 
            await db.execute("""
                INSERT INTO reviews (id_gen, num_review, review, rating, current_situation, sex, profession, marital_status, children, hobby) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (id_gen, num_review, review, rating, current_situation, sex, profession, marital_status, children, hobby))
            await db.commit()
    except Exception as e:
        print(f"Произошла ошибка при сохранении отзыва: {e}")

# Установка политики обработки цикла событий для Windows
def if_windows():
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())