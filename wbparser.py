# -*- coding: utf-8 -*-

import aiohttp  
import asyncio  
import aiosqlite
import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv('DB_PATH')

async def get_card_url(id):
    """Асинхронная функция для определения URL адресов по артикулу."""
    
    # Варианты составления URL для артикулов различной длины
    if len(str(id)) == 6:
        basket_num = get_basket(id[:3]) # Определение номера сервера на котором хранится информация
        volume = id[:1] 
        part = id[:3]
    elif len(str(id)) == 7:
        basket_num = get_basket(id[:2])
        volume = id[:2]
        part = id[:4]
    elif len(str(id)) == 8:
        basket_num = get_basket(id[:3])
        volume = id[:3]
        part = id[:5]
    elif len(str(id)) == 9:
        basket_num = get_basket(id[:4])
        volume = id[:4]
        part = id[:6]
    else:
        print('Введен некорректный артикул')
    
    # Ссылка на запрос предоставляющий json файл содержащий характеристики и описание товара    
    link = f'https://basket-{basket_num}.wbbasket.ru/vol{volume}/part{part}/{id}/info/ru/card.json'
    
    # Ссылка на запрос предоставляющий json файл содержащий цену товара
    price_link = f'https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={id}'
    
    return link, price_link

def get_basket(short_id):
    """Функция для определения номера сервера на котором хранится информация о товаре"""
    
    short_id = int(short_id)
    
    if 0 <= short_id <= 143:
        return '01'
    elif 144 <= short_id <= 287:
        return '02'
    elif 288 <= short_id <= 431:
        return '03'
    elif 432 <= short_id <= 719:
        return '04'
    elif 720 <= short_id <= 1007:
        return '05'
    elif 1008 <= short_id <= 1061:
        return '06'
    elif 1062 <= short_id <= 1115:
        return '07'
    elif 1116 <= short_id <= 1169:
        return '08'
    elif 1170 <= short_id <= 1313:
        return '09'
    elif 1314 <= short_id <= 1601:
        return '10'
    elif 1602 <= short_id <= 1655:
        return '11'
    elif 1656 <= short_id <= 1919:
        return '12'
    elif 1920 <= short_id <= 2045:
        return '13'
    elif 2046 <= short_id <= 2189:
        return '14'
    elif 2190 <= short_id <= 2405:
        return '15'
    else:
        return '16'
    
async def get_card_info(session, url_1, url_2):
    """Асинхронная функция для получения информации о карточке товара и его цене."""
    
    headers=get_headers()
    async with session.get(url=url_1, headers=headers) as response:
        response_json = await response.json()
    price = await get_price(session, url_2, headers)
    
    return response_json, price

async def get_price(session, url, headers):
    """Асинхронная функция для получения цены товара."""
    
    try:
        async with session.get(url=url, headers=headers) as url_resp:
            data = await url_resp.json()
            data = data.get('data', {}).get('products', [])
            if data:
                price_info = data[0]['sizes'][0]['price'].get('product')
                if price_info is not None:
                    return price_info / 100
    except:
        return 'Цена неизвестна'

def get_json_data(response, price):
    """Функция для формирования словаря с данными о товаре."""
    
    product_data = {  
        'идентификатор': response.get('nm_id', None),
        'наименование_товара': response.get('imt_name', None),
        'категория': response.get('subj_root_name', None),
        'подкатегория': response.get('subj_name', None),
        'описание_товара': response.get('description', None),
        'цена_в_рублях': price,
        'ссылка': f'https://www.wildberries.ru/catalog/{response.get("nm_id", None)}/detail.aspx'
    }
    
    # Добавление дополнительных характеристик товара, если они есть
    options = response.get('options', [])
    for option in options:
        option_name = option.get('name', '').replace(' ', '_').lower()
        product_data[option_name] = option.get('value', None)

    return product_data

def get_headers():
    """Функция возвращает заголовки, используемые для HTTP-запросов."""
    return {
        'Accept': '*/*',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Connection': 'keep-alive',
        'Origin': 'https://www.wildberries.by',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'cross-site',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36',
        'sec-ch-ua': '"Google Chrome";v="111", "Not(A:Brand";v="8", "Chromium";v="111"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': 'macOS',
    }

async def get_product_info(id):
    """Основная асинхронная функция для получения данных о товаре, и внесения их в базу данных."""
    
    session = aiohttp.ClientSession()
    try:
        link, price_link = await get_card_url(id)
        response, price = await get_card_info(session, link, price_link)
        if response.get('nm_id', None) is None: 
            return None
        product_data = get_json_data(response, price)
    
        async with aiosqlite.connect(DB_PATH) as db:
            # Проверяем, есть товар в базе данных
            cursor = await db.execute("SELECT id_product FROM products WHERE id_product = ?", (product_data['идентификатор'],))
            exists = await cursor.fetchone()
            if not exists:
                # Если товара нет в бд, записываем его
                await db.execute("INSERT INTO products (id_product, product_name) VALUES (?, ?)", 
                                 (product_data['идентификатор'], product_data['наименование_товара']))
                await db.commit()
                
        return product_data
    
    # Если произошла ошибка, выводим её
    except Exception as e:
        print(f"Ошибка при получении данных: {e}")
        return None
    finally:
        await session.close()