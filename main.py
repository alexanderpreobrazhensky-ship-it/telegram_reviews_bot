import os
import re
import json
import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Tuple
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# Импорт нейросетей
try:
    from transformers import pipeline
    from sentence_transformers import SentenceTransformer, util
    NLP_AVAILABLE = True
except ImportError:
    NLP_AVAILABLE = False
    print("⚠️ NLP библиотеки не установлены. Установите: pip install transformers torch sentence-transformers")

# ================== КОНФИГУРАЦИЯ ==================
TELEGRAM_BOT_TOKEN = "7917601350:AAFG1E7kHKrNzTXIprNADOzLvxpnrUjAcO4"

# Загрузка правил площадок
def load_rules():
    rules = {
        'yandex': {
            'prohibited': [
                'нецензурная брань', 'оскорбления', 'угрозы',
                'реклама сторонних услуг', 'разглашение персональных данных',
                'клевета', 'фейковые отзывы', 'спам'
            ],
            'min_words': 10,
            'max_emojis': 3,
            'require_details': True
        },
        '2gis': {
            'prohibited': [
                'матерные выражения', 'личные оскорбления',
                'коммерческая реклама', 'заведомо ложная информация',
                'многочисленные однотипные отзывы'
            ],
            'min_words': 5,
            'require_rating_explanation': True
        }
    }
    return rules

RULES = load_rules()

# ================== НЕЙРОСЕТИ ==================
class ReviewAnalyzer:
    def __init__(self):
        self.sentiment_analyzer = None
        self.similarity_model = None
        self.init_models()
    
    def init_models(self):
        """Инициализация нейросетевых моделей"""
        if not NLP_AVAILABLE:
            return
            
        try:
            # Модель для тональности (русская)
            self.sentiment_analyzer = pipeline(
                "sentiment-analysis",
                model="blanchefort/rubert-base-cased-sentiment"
            )
            
            # Модель для семантического поиска нарушений
            self.similarity_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
            print("✅ Нейросетевые модели загружены")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки моделей: {e}")

    def analyze_sentiment(self, text: str) -> Dict:
        """Анализ тональности нейросетью"""
        if not self.sentiment_analyzer:
            return {'label': 'NEUTRAL', 'score': 0.5}
        
        try:
            result = self.sentiment_analyzer(text[:512])[0]  # Ограничиваем длину
            return {
                'label': result['label'],  # POSITIVE/NEGATIVE/NEUTRAL
                'score': float(result['score'])
            }
        except:
            return {'label': 'NEUTRAL', 'score': 0.5}

    def check_violations(self, text: str, platform: str) -> List[Dict]:
        """Поиск нарушений правил площадки"""
        violations = []
        text_lower = text.lower()
        
        # Проверка по ключевым словам
        for rule in RULES[platform]['prohibited']:
            if rule in text_lower:
                violations.append({
                    'rule': rule,
                    'type': 'keyword',
                    'confidence': 0.9,
                    'evidence': f"Содержит запрещенное: '{rule}'"
                })
        
        # Семантический поиск нарушений (если есть модель)
        if self.similarity_model:
            try:
                text_embedding = self.similarity_model.encode(text, convert_to_tensor=True)
                
                for rule in RULES[platform]['prohibited']:
                    rule_embedding = self.similarity_model.encode(rule, convert_to_tensor=True)
                    similarity = util.cos_sim(text_embedding, rule_embedding).item()
                    
                    if similarity > 0.7:  # Порог сходства
                        violations.append({
                            'rule': rule,
                            'type': 'semantic',
                            'confidence': similarity,
                            'evidence': f"Семантическое сходство: {similarity:.2%}"
                        })
            except Exception as e:
                print(f"Ошибка семантического анализа: {e}")
        
        # Проверка формальных критериев
        if platform == 'yandex':
            words = text.split()
            if len(words) < RULES[platform]['min_words']:
                violations.append({
                    'rule': 'Минимальная длина отзыва',
                    'type': 'formal',
                    'confidence': 1.0,
                    'evidence': f"Всего {len(words)} слов, требуется {RULES[platform]['min_words']}"
                })
            
            emoji_count = len(re.findall(r'[\U00010000-\U0010ffff]', text))
            if emoji_count > RULES[platform]['max_emojis']:
                violations.append({
                    'rule': 'Слишком много эмодзи',
                    'type': 'formal',
                    'confidence': 1.0,
                    'evidence': f"Найдено {emoji_count} эмодзи"
                })
        
        return violations

analyzer = ReviewAnalyzer()

# ================== БАЗА ДАННЫХ ==================
def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect('reviews.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT,
            text TEXT,
            rating INTEGER,
            sentiment_label TEXT,
            sentiment_score REAL,
            violations_json TEXT,
            complaint_generated BOOLEAN DEFAULT 0,
            complaint_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id INTEGER,
            platform TEXT,
            complaint_text TEXT,
            status TEXT DEFAULT 'draft',
            submitted_at TIMESTAMP,
            FOREIGN KEY (review_id) REFERENCES reviews (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# ================== ТЕКСТЫ ЖАЛОБ ==================
def generate_complaint(review_text: str, violations: List[Dict], platform: str) -> str:
    """Генерация текста жалобы"""
    
    templates = {
        'yandex': """
Уважаемая служба модерации Яндекс.Карт!

Просим удалить отзыв от пользователя, так как он нарушает правила платформы:

Нарушения:
{violations_list}

Текст отзыва:
"{review_text}"

Данный отзыв:
1. Содержит запрещенный контент
2. Не соответствует действительности
3. Нарушает правила публикации отзывов

Просим рассмотреть жалобу и удалить отзыв в соответствии с пунктом {rule_section} правил Яндекс.Карт.

С уважением,
Администрация техцентра «Лира»
        """,
        
        '2gis': """
Уважаемая администрация 2ГИС!

Просим удалить отзыв, опубликованный на нашей странице, по следующим причинам:

Выявленные нарушения правил платформы:
{violations_list}

Оригинальный текст отзыва:
"{review_text}"

Основания для удаления:
- Отзыв содержит неподтвержденную информацию
- Нарушены правила публикации контента
- Присутствуют признаки накрутки/фейка

Просим принять меры в соответствии с пользовательским соглашением 2ГИС.

С уважением,
Техцентр «Лира»
        """
    }
    
    violations_list = "\n".join([
        f"- {v['rule']} ({v['type']}, уверенность: {v['confidence']:.0%})"
        for v in violations[:5]  # Берем 5 самых серьезных нарушений
    ])
    
    complaint = templates[platform].format(
        violations_list=violations_list,
        review_text=review_text[:500],  # Ограничиваем длину
        rule_section="5.2" if platform == 'yandex' else "3.1"
    )
    
    return complaint.strip()

# ================== КОМАНДЫ БОТА ==================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    await update.message.reply_text(
        "🔧 **Анализатор отзывов техцентра «Лира»**\n\n"
        "Я помогаю анализировать отзывы на Яндекс и 2ГИС.\n\n"
        "📋 **Команды:**\n"
        "/analyze_yandex <текст отзыва> - анализ отзыва для Яндекс\n"
        "/analyze_gis <текст отзыва> - анализ для 2ГИС\n"
        "/stats - статистика по отзывам\n"
        "/complaint <id отзыва> - показать текст жалобы\n\n"
        "Пример:\n"
        "/analyze_yandex Отвратительный сервис! Мастера некомпетентны, всё сделали криво. Не рекомендую!"
    )

async def analyze_yandex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализ отзыва для Яндекс"""
    await analyze_review(update, context, 'yandex')

async def analyze_gis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализ отзыва для 2ГИС"""
    await analyze_review(update, context, '2gis')

async def analyze_review(update: Update, context: ContextTypes.DEFAULT_TYPE, platform: str):
    """Общий анализ отзыва"""
    if not context.args:
        await update.message.reply_text(
            f"❗ Укажите текст отзыва\n"
            f"Пример: /analyze_{'yandex' if platform == 'yandex' else 'gis'} "
            f"Текст отзыва с рейтингом 2 звезды"
        )
        return
    
    review_text = " ".join(context.args)
    user = update.effective_user
    
    # Анализ нейросетью
    sentiment = analyzer.analyze_sentiment(review_text)
    violations = analyzer.check_violations(review_text, platform)
    
    # Генерация жалобы если есть нарушения
    complaint = None
    if violations:
        complaint = generate_complaint(review_text, violations, platform)
    
    # Сохранение в БД
    conn = sqlite3.connect('reviews.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO reviews (platform, text, sentiment_label, sentiment_score, violations_json, complaint_generated, complaint_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        platform,
        review_text,
        sentiment['label'],
        sentiment['score'],
        json.dumps(violations, ensure_ascii=False),
        bool(complaint),
        complaint
    ))
    review_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Формируем ответ
    response = f"📊 **Анализ отзыва ({platform.upper()})**\n\n"
    response += f"📝 **Текст:** {review_text[:200]}...\n\n"
    response += f"🎯 **Тональность:** {sentiment['label']} ({sentiment['score']:.0%})\n\n"
    
    if violations:
        response += f"🚨 **Нарушения найдены:** {len(violations)}\n"
        for i, v in enumerate(violations[:3], 1):
            response += f"{i}. {v['rule']} ({v['confidence']:.0%})\n"
        
        response += f"\n📄 **Жалоба сгенерирована:** Да (ID: {review_id})\n"
        response += f"📋 **Для просмотра:** /complaint_{review_id}"
    else:
        response += "✅ **Нарушений не обнаружено**\n"
        response += "Отзыв соответствует правилам площадки"
    
    await update.message.reply_text(response)

async def show_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать текст жалобы"""
    if not context.args:
        await update.message.reply_text("Укажите ID отзыва: /complaint 1")
        return
    
    try:
        review_id = int(context.args[0])
        conn = sqlite3.connect('reviews.db')
        cursor = conn.cursor()
        cursor.execute('SELECT platform, complaint_text FROM reviews WHERE id = ?', (review_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result or not result[1]:
            await update.message.reply_text(f"Жалоба для отзыва #{review_id} не найдена")
            return
        
        platform, complaint_text = result
        
        # Отправляем жалобы частями (Telegram ограничение 4096 символов)
        chunks = [complaint_text[i:i+4000] for i in range(0, len(complaint_text), 4000)]
        
        await update.message.reply_text(f"📄 **Текст жалобы для {platform.upper()}** (ID: {review_id}):\n\n")
        
        for i, chunk in enumerate(chunks, 1):
            await update.message.reply_text(f"Часть {i}:\n```\n{chunk}\n```")
        
        await update.message.reply_text(
            f"✅ **Жалоба готова к отправке**\n\n"
            f"Что делать дальше:\n"
            f"1. Скопируйте текст выше\n"
            f"2. Перейдите на страницу отзыва\n"
            f"3. Нажмите 'Пожаловаться'\n"
            f"4. Вставьте текст жалобы\n\n"
            f"📊 Статистика: /stats"
        )
        
    except ValueError:
        await update.message.reply_text("ID должен быть числом")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика по отзывам"""
    conn = sqlite3.connect('reviews.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM reviews')
    total = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM reviews WHERE complaint_generated = 1')
    with_complaints = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT platform, COUNT(*) 
        FROM reviews 
        WHERE complaint_generated = 1 
        GROUP BY platform
    ''')
    by_platform = cursor.fetchall()
    
    conn.close()
    
    response = "📈 **Статистика анализа отзывов**\n\n"
    response += f"📊 Всего проанализировано: {total} отзывов\n"
    response += f"🚨 С нарушениями: {with_complaints} ({with_complaints/max(total,1)*100:.0f}%)\n\n"
    
    if by_platform:
        response += "**По площадкам:**\n"
        for platform, count in by_platform:
            response += f"- {platform.upper()}: {count} жалоб\n"
    
    response += f"\n🔍 **Последние отзывы:** /recent_5"
    
    await update.message.reply_text(response)

async def recent_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать последние отзывы"""
    limit = 5
    conn = sqlite3.connect('reviews.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, platform, text, created_at 
        FROM reviews 
        ORDER BY id DESC 
        LIMIT ?
    ''', (limit,))
    
    reviews = cursor.fetchall()
    conn.close()
    
    if not reviews:
        await update.message.reply_text("Еще нет проанализированных отзывов")
        return
    
    response = f"📋 **Последние {limit} отзывов**\n\n"
    
    for idx, (review_id, platform, text, created_at) in enumerate(reviews, 1):
        preview = text[:100] + "..." if len(text) > 100 else text
        response += f"{idx}. **{platform.upper()}** (ID: {review_id})\n"
        response += f"   {preview}\n"
        response += f"   📅 {created_at[:10]}\n"
        response += f"   📄 /complaint_{review_id}\n\n"
    
    await update.message.reply_text(response)

# ================== ЗАПУСК ==================
def main():
    """Запуск бота"""
    # Инициализация БД
    init_db()
    
    # Проверка нейросетей
    if not NLP_AVAILABLE:
        print("⚠️ ВНИМАНИЕ: Нейросетевые модели не установлены")
        print("Установите: pip install transformers torch sentence-transformers")
        print("Будет использоваться упрощенный анализ по ключевым словам")
    
    # Запуск бота
    try:
        print("🤖 Запускаю бота-анализатора отзывов...")
        app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Регистрация команд
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("analyze_yandex", analyze_yandex))
        app.add_handler(CommandHandler("analyze_gis", analyze_gis))
        
        # Динамические команды для жалоб
        app.add_handler(CommandHandler("complaint", show_complaint))
        
        # Статистика
        app.add_handler(CommandHandler("stats", stats))
        app.add_handler(CommandHandler("recent_5", recent_reviews))
        
        # Обработка обычных сообщений
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, 
                                      lambda u, c: u.message.reply_text("Используйте команды из /start")))
        
        logger.info("Бот запущен")
        print("✅ Анализатор отзывов запущен!")
        print("🔗 Ищите в Telegram: /start")
        
        app.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"Ошибка запуска: {e}")
        print(f"❌ Ошибка: {e}")
        raise

if __name__ == "__main__":
    main()
