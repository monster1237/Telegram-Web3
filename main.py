import sqlite3
import re
import os
from telebot import TeleBot, types
import requests
import pytz
from datetime import datetime
from solders.pubkey import Pubkey

# 你的电报机器人Token
bot_token = os.environ['TGbot_token']
bot = TeleBot(bot_token)

# Solana和Ethereum地址的正则表达式模式
solana_address_pattern = r'[123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]{32,44}'
eth_address_pattern = r'0x[a-fA-F0-9]{40}'

# 在这个线程中创建一个新的数据库连接
conn = sqlite3.connect('messages.db')
c = conn.cursor()

# 创建表
c.execute("""
CREATE TABLE IF NOT EXISTS messages (
    chat_id INTEGER,
    message_text TEXT,
    message_date INTEGER
)
""")
conn.commit()

# Solana地址验证函数
def validate_solana_address(address):
    try:
        pubkey = Pubkey(address)
        return True  # 如果地址有效，则返回True
    except ValueError:
        return False  # 如果地址无效，则返回False


# 获取涨跌幅信息和社交信息的函数
def get_token_info(address, chat_id):
    url = f"https://api.dexscreener.com/latest/dex/tokens/{address}"
    response = requests.get(url)
    data = response.json()

    # 检查是否有有效的配对数据
    if data.get('pairs') is None:
        # 如果没有有效数据，发送CA地址
        message_content = f"价格检测失败\nCA提取: `{address}`"
        bot.send_message(chat_id=chat_id,
                         text=message_content,
                         parse_mode='Markdown')
        return

    # 获取第一个配对的数据
    pair_data = data['pairs'][0] if data['pairs'] else {}

    # 获取基本信息
    token_name = pair_data.get('baseToken', {}).get('name', '无')
    current_price = float(pair_data.get('priceUsd',
                                        '0'))  # 确保current_price是浮点数
    total_supply = float(pair_data.get('liquidity', {}).get('base', '0'))
    volume_24h = float(pair_data.get('volume', {}).get('h24', '0'))
    liquidity = float(pair_data.get('liquidity', {}).get('usd', '0'))

    # 初始化涨跌幅信息
    price_change_info = {
        'm5': pair_data.get('priceChange', {}).get('m5', '无'),
        'h1': pair_data.get('priceChange', {}).get('h1', '无'),
        'h6': pair_data.get('priceChange', {}).get('h6', '无'),
        'h24': pair_data.get('priceChange', {}).get('h24', '无')
    }

    # 初始化社交信息
    social_info = ""
    for social in pair_data.get('info', {}).get('socials', []):
        social_type = social.get('type', '').title()
        social_url = social.get('url', '无')
        social_info += f"{social_type}: {social_url}\n" if social_type and social_url else ""

    # 计算代币创建时间与当前日期的差异（转换为+8时区）
    tz_shanghai = pytz.timezone('Asia/Shanghai')
    pair_created_at = datetime.fromtimestamp(
        pair_data.get('pairCreatedAt', 0) / 1000, tz_shanghai)
    time_since_creation = datetime.now(tz_shanghai) - pair_created_at
    days_since_creation = time_since_creation.days
    hours_since_creation = time_since_creation.seconds // 3600
    minutes_since_creation = (time_since_creation.seconds // 60) % 60

    message_content = f"**名称**: *{token_name}*\n" \
                      f"**地址**: `{address}`\n" \
                      f"**现在价格**: ${current_price:,.8f}\n" \
                      f"**5分钟涨跌幅**: {price_change_info['m5']}%\n" \
                      f"**1小时涨跌幅**: {price_change_info['h1']}%\n" \
                      f"**6小时涨跌幅**: {price_change_info['h6']}%\n" \
                      f"**24小时涨跌幅**: {price_change_info['h24']}%\n" \
                      f"**创建时间**: {pair_created_at.strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)\n" \
                      f"**距离时间**: {days_since_creation}天 {hours_since_creation}小时 {minutes_since_creation}分钟\n" \
                      f"**24小时交易量**: {volume_24h:,.2f}\n" \
                      f"**流动性**: ${liquidity:,.2f}\n" \
                      f"**代币总数量**: {total_supply:,.0f}\n\n" \
                      f"**社交**:\n{social_info}\n" \
                      f"**网址**: {pair_data.get('url', '无')}"
    token_image_url = pair_data.get('info', {}).get('imageUrl', '')
    if token_image_url:
        bot.send_photo(chat_id=chat_id,
                       photo=token_image_url,
                       caption=message_content,
                       parse_mode='Markdown')
    else:
        bot.send_message(chat_id=chat_id,
                         text=message_content,
                         parse_mode='Markdown')


# 电报机器人监听函数
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    # 在这个线程中创建一个新的数据库连接
    conn = sqlite3.connect('messages.db')
    c = conn.cursor()

    # 将消息存储在数据库中
    c.execute("INSERT INTO messages VALUES (?, ?, ?)",
              (message.chat.id, message.text, message.date))
    conn.commit()

    # 检查消息是否包含ETH或SOL地址
    match_sol = re.search(solana_address_pattern, message.text)
    match_eth = re.search(eth_address_pattern, message.text)
    if match_sol or match_eth:
        # 如果找到地址，调用get_token_info函数
        address = match_sol.group() if match_sol else match_eth.group()
        get_token_info(address, message.chat.id)

# 电报机器人监听群组消息的函数
@bot.message_handler(content_types=['text'], func=lambda message: True, chat_types=['group', 'supergroup'])
def handle_group_messages(message):
    # 在这个线程中创建一个新的数据库连接
    conn = sqlite3.connect('messages.db')
    c = conn.cursor()

    # 将消息存储在数据库中
    c.execute("INSERT INTO messages VALUES (?, ?, ?)",
              (message.chat.id, message.text, message.date))
    conn.commit()

    # 检查消息是否包含ETH或SOL地址
    match_sol = re.search(solana_address_pattern, message.text)
    match_eth = re.search(eth_address_pattern, message.text)
    if match_sol or match_eth:
        # 如果找到地址，调用get_token_info函数
        address = match_sol.group() if match_sol else match_eth.group()
        get_token_info(address, message.chat.id)

# 轮询电报服务器
bot.polling()
