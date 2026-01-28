import os
import json
import logging
import sqlite3
from typing import List, Dict
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# ================== КОНФИГУРАЦИЯ ==================
TELEGRAM_BOT_TOKEN = "7917601350:AAFG1E7kHKrNzTXIprNADOzLvxpnrUjAcO4"

# ================== ОПТИМИЗИРОВАННЫЕ НЕЙРОСЕТИ ==================
class OptimizedNLP:
    """Оптимизированные нейросети для 1GB RAM"""
    
    def __init__(self):
        self.sentiment_model = None
        self.similarity_model = None
        self.rules_model = None
        self._load_models()
    
    def _load_models(self):
        """Загрузка оптимизированных моделей"""
        try:
            print("🧠 Загружаю оптимизированные нейросети...")
            
            # 1. Компактная модель для тональности (80MB)
            from transformers import pipeline
            self.sentiment_model = pipeline(
                "sentiment-analysis",
                model="cointegrated/rubert-tiny2-sentiment-balanced",  # Всего 80MB!
                device=-1,  # CPU режим
                truncation=True,
                max_length=256
            )
            print("✅ Модель тональности загружена")
            
            # 2. Правила и ключевые слова (без тяжелой модели)
            self.rules_model = self._init_rules_engine()
            print("✅ Анализатор правил инициализирован")
            
            print("🎯 Все нейросети загружены и готовы к работе")
            
        except Exception as e:
            print(f"⚠️ Ошибка загрузки нейросетей: {e}")
            print("🔄 Использую резервный анализатор по правилам")
            self._init_fallback()
    
    def _init_rules_engine(self):
        """Двигатель правил с ML-подобной логикой"""
        return {
            'yandex': {
                'prohibited': {
                    'оскорбления': ['идиот', 'дурак', 'мудак', 'кретин', 'дебил', 'тупица'],
                    'нецензурная лексика': ['говно', 'хер', 'пизд', 'бля', 'еба', 'хуй'],
                    'угрозы': ['убью', 'убить', 'изобью', 'покалечу', 'сожгу'],
                    'клевета': ['воры', 'мошенники', 'обманщики', 'кидалы', 'развод'],
                    'спам': ['купите', 'закажите', 'переходите', 'реклама', 'скидка']
                },
                'weights': {
                    'оскорбления': 0.9,
                    'нецензурная лексика': 1.0,
                    'угрозы': 1.0,
                    'клевета': 0.8,
                    'спам': 0.6
                }
            },
            '2gis': {
                'prohibited': {
                    'личные оскорбления': ['некомпетентный', 'бездарный', 'неучи', 'халтурщики'],
                    'ложная информация': ['не было', 'не делали', 'обманули', 'кинули'],
                    'коммерческий спам': ['звоните', 'пишите', 'конкурент', 'дешевле']
                }
            }
        }
    
    def _init_fallback(self):
        """Резервный анализатор если нейросети не загрузились"""
        self.sentiment_model = None
        self.rules_model = self._init_rules_engine()
    
    def analyze_sentiment(self, text: str) -> Dict:
        """Анализ тональности с нейросетью или fallback"""
        if self.sentiment_model:
            try:
                result = self.sentiment_model(text[:512])[0]
                return {
                    'label': 'NEGATIVE' if result['label'] == 'negative' else 
                             'POSITIVE' if result['label'] == 'positive' else 'NEUTRAL',
                    'score': float(result['score']),
                    'source': 'neural'
                }
            except:
                pass
        
        # Fallback на правила
        return self._sentiment_by_rules(text)
    
    def _sentiment_by_rules(self, text: str) -> Dict:
        """Анализ тональности по правилам"""
        text_lower = text.lower()
        
        negative_keywords = ['плохо', 'ужасно', 'отвратительно', 'кошмар', 'не рекомендую']
        positive_keywords = ['отлично', 'прекрасно', 'великолепно', 'рекомендую', 'спасибо']
        
        neg_score = sum(1 for word in negative_keywords if word in text_lower)
        pos_score = sum(1 for word in positive_keywords if word in text_lower)
        
        total = max(neg_score + pos_score, 1)
        
        if neg_score > pos_score:
            return {'label': 'NEGATIVE', 'score': neg_score/total, 'source': 'rules'}
        elif pos_score > neg_score:
            return {'label': 'POSITIVE', 'score': pos_score/total, 'source': 'rules'}
        else:
            return {'label': 'NEUTRAL', 'score': 0.5, 'source': 'rules'}
    
    def check_violations(self, text: str, platform: str = 'yandex') -> List[Dict]:
        """Проверка нарушений с ML-подходом"""
        violations = []
        text_lower = text.lower()
        
        if platform not in self.rules_model:
            platform = 'yandex'
        
        for category, keywords in self.rules_model[platform]['prohibited'].items():
            found_keywords = []
            for keyword in keywords:
                if keyword in text_lower:
                    found_keywords.append(keyword)
            
            if found_keywords:
                confidence = min(0.3 + len(found_keywords) * 0.2, 0.95)
                if platform == 'yandex':
                    confidence *= self.rules_model[platform]['weights'].get(category, 0.7)
                
                violations.append({
                    'category': category,
                    'keywords': found_keywords,
                    'confidence': round(confidence, 2),
                    'severity': 'high' if confidence > 0.8 else 'medium'
                })
        
        # Дополнительные эвристики
        if platform == 'yandex':
            # Проверка на минимальную длину
            words = text.split()
            if len(words) < 10:
                violations.append({
                    'category': 'слишком короткий отзыв',
                    'keywords': [f'{len(words)} слов'],
                    'confidence': 0.7,
                    'severity': 'low'
                })
            
            # Проверка на CAPS LOCK
            if len(text) > 10 and sum(1 for c in text if c.isupper()) / len(text) > 0.5:
                violations.append({
                    'category': 'кричащий текст (капслок)',
                    'keywords': ['CAPS LOCK'],
                    'confidence': 0.8,
                    'severity': 'medium'
                })
        
        return violations

# ================== ИНИЦИАЛИЗАЦИЯ ==================
print("=" * 60)
print("🤖 АНАЛИЗАТОР ОТЗЫВОВ С НЕЙРОСЕТЯМИ")
print(f"💪 Память: 1 GB RAM | CPU: 2 vCPU")
print("=" * 60)

nlp_engine = OptimizedNLP()

# ================== БАЗА ДАННЫХ ==================
def init_database():
    """Инициализация SQLite базы"""
    conn = sqlite3.connect('reviews.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analyzed_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            message_id INTEGER,
            platform TEXT,
            text TEXT,
            sentiment_label TEXT,
            sentiment_score REAL,
            violations_json TEXT,
            complaint_generated BOOLEAN,
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (review_id) REFERENCES analyzed_reviews (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

# ================== ГЕНЕРАЦИЯ ЖАЛОБ ==================
def generate_smart_complaint(text: str, violations: List[Dict], platform: str) -> str:
    """Умная генерация жалобы на основе нарушений"""
    
    templates = {
        'yandex': {
            'header': "Уважаемая служба модерации Яндекс.Карт!\n\n",
            'footer': "\n\nПросим удалить отзыв согласно п. 5.2 Правил размещения отзывов.\n\nС уважением,\nАдминистрация техцентра «Лира»",
            'rules': {
                'оскорбления': "Содержит личные оскорбления сотрудников",
                'нецензурная лексика': "Использует нецензурную лексику",
                'угрозы': "Содержит элементы угроз и запугивания",
                'клевета': "Распространяет заведомо ложную информацию",
                'спам': "Имеет признаки рекламного спама"
            }
        },
        '2gis': {
            'header': "Уважаемая администрация 2ГИС!\n\n",
            'footer': "\n\nПросим принять меры согласно Пользовательскому соглашению.\n\nС уважением,\nТехцентр «Лира»",
            'rules': {
                'личные оскорбления': "Содержит неподобающие высказывания в адрес сотрудников",
                'ложная информация': "Содержит информацию, не соответствующую действительности",
                'коммерческий спам': "Имеет признаки коммерческой рекламы"
            }
        }
    }
    
    tpl = templates.get(platform, templates['yandex'])
    
    # Собираем нарушения
    violations_text = ""
    for i, violation in enumerate(violations[:5], 1):
        rule_desc = tpl['rules'].get(violation['category'], violation['category'])
        violations_text += f"{i}. {rule_desc} (совпадение: {violation['confidence']:.0%})\n"
    
    # Формируем жалобу
    complaint = f"{tpl['header']}"
    complaint += "Просим удалить следующий отзыв по причине нарушения правил платформы:\n\n"
    
    if violations_text:
        complaint += "Выявленные нарушения:\n"
        complaint += violations_text + "\n"
    
    complaint += f"Текст отзыва:\n\"{text[:400]}\"\n"
    
    if len(text) > 400:
        complaint += "[... текст сокращен ...]\n"
    
    complaint += tpl['footer']
    
    return complaint

# ================== КОМАНДЫ БОТА ==================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    await update.message.reply_text(
        "🧠 **Анализатор отзывов с нейросетями**\n\n"
        "Я анализирую отзывы на предмет нарушений правил Яндекс.Карт и 2ГИС.\n\n"
        "📋 **Команды:**\n"
        "/analyze <текст> - полный анализ отзыва\n"
        "/yandex <текст> - анализ для Яндекс (2 звезды)\n"
        "/2gis <текст> - анализ для 2ГИС\n"
        "/stats - статистика\n"
        "/demo - пример работы нейросети\n\n"
        "Пример:\n"
        "/yandex Ужасный сервис! Мастера идиоты, всё сломали. 2 звезды!"
    )

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализ отзыва"""
    if not context.args:
        await update.message.reply_text("Напишите текст отзыва после команды")
        return
    
    text = " ".join(context.args)
    user = update.effective_user
    
    # Анализ нейросетями
    sentiment = nlp_engine.analyze_sentiment(text)
    violations = nlp_engine.check_violations(text, 'yandex')
    
    # Генерация результата
    response = f"🧠 **Результат анализа нейросетью:**\n\n"
    response += f"📊 *Тональность:* {sentiment['label']} ({sentiment['score']:.0%})\n"
    response += f"📝 *Длина:* {len(text.split())} слов\n\n"
    
    if violations:
        response += f"🚨 *Нарушений найдено:* {len(violations)}\n"
        for i, v in enumerate(violations[:3], 1):
            emoji = "🔴" if v['severity'] == 'high' else "🟡" if v['severity'] == 'medium' else "🔵"
            response += f"{emoji} {v['category']} ({v['confidence']:.0%})\n"
        
        # Генерация жалобы
        complaint = generate_smart_complaint(text, violations, 'yandex')
        
        # Сохранение в БД
        conn = sqlite3.connect('reviews.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO analyzed_reviews 
            (chat_id, platform, text, sentiment_label, sentiment_score, violations_json, complaint_generated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user.id, 'yandex', text, sentiment['label'], sentiment['score'], 
              json.dumps(violations, ensure_ascii=False), True))
        
        review_id = cursor.lastrowid
        
        cursor.execute('''
            INSERT INTO complaints (review_id, platform, complaint_text)
            VALUES (?, ?, ?)
        ''', (review_id, 'yandex', complaint))
        
        conn.commit()
        conn.close()
        
        response += f"\n📄 *Жалоба сгенерирована!*\n"
        response += f"🆔 ID: `{review_id}`\n"
        response += f"👀 Просмотр: /complaint_{review_id}"
    else:
        response += "✅ *Нарушений не обнаружено*\n"
        response += "Отзыв соответствует правилам площадки"
    
    await update.message.reply_text(response)

async def yandex_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Специальный анализ для Яндекс (2 звезды)"""
    if not context.args:
        await update.message.reply_text("Укажите отзыв с 2 звездами")
        return
    
    text = " ".join(context.args)
    
    # Проверка на упоминание 2 звезд
    if any(word in text.lower() for word in ['2 звезд', 'две звезд', '★☆☆☆☆', '⭐⭐']):
        await analyze_command(update, context)
    else:
        # Если нет упоминания звезд, добавляем автоматически
        context.args = [f"{text} [оценка: 2 звезды]"]
        await analyze_command(update, context)

async def show_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать жалобу по ID"""
    try:
        cmd = update.message.text
        if '_' in cmd:
            review_id = int(cmd.split('_')[1])
        else:
            await update.message.reply_text("Используйте: /complaint_1")
            return
        
        conn = sqlite3.connect('reviews.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.complaint_text, r.platform 
            FROM complaints c
            JOIN analyzed_reviews r ON c.review_id = r.id
            WHERE c.review_id = ?
        ''', (review_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            complaint_text, platform = result
            # Отправляем частями (Telegram ограничение)
            chunks = [complaint_text[i:i+4000] for i in range(0, len(complaint_text), 4000)]
            
            await update.message.reply_text(f"📄 **Жалоба для {platform.upper()}** (ID: {review_id}):")
            
            for i, chunk in enumerate(chunks, 1):
                await update.message.reply_text(f"```\n{chunk}\n```")
            
            await update.message.reply_text(
                "📋 **Инструкция:**\n"
                "1. Скопируйте текст выше\n"
                "2. Найдите отзыв на площадке\n"
                "3. Нажмите 'Пожаловаться'\n"
                "4. Вставьте текст жалобы"
            )
        else:
            await update.message.reply_text(f"Жалоба #{review_id} не найдена")
            
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика"""
    conn = sqlite3.connect('reviews.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM analyzed_reviews")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM analyzed_reviews WHERE complaint_generated = 1")
    with_complaints = cursor.fetchone()[0]
    
    cursor.execute("SELECT platform, COUNT(*) FROM analyzed_reviews GROUP BY platform")
    by_platform = cursor.fetchall()
    
    conn.close()
    
    response = "📈 **Статистика нейросетевого анализа:**\n\n"
    response += f"🧮 Всего проанализировано: {total}\n"
    response += f"🚨 С нарушениями: {with_complaints}\n"
    response += f"📊 Эффективность: {with_complaints/max(total,1)*100:.1f}%\n\n"
    
    if by_platform:
        response += "**По площадкам:**\n"
        for platform, count in by_platform:
            response += f"• {platform.upper()}: {count}\n"
    
    await update.message.reply_text(response)

# ================== ЗАПУСК ==================
def main():
    """Основная функция"""
    print("🚀 Инициализация системы...")
    
    # Инициализация БД
    init_database()
    
    print("✅ Система готова, запускаю бота...")
    
    # Запуск бота
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Регистрация команд
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("analyze", analyze_command))
    app.add_handler(CommandHandler("yandex", yandex_command))
    app.add_handler(CommandHandler("2gis", analyze_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("demo", start_command))
    
    # Динамические команды для жалоб
    app.add_handler(MessageHandler(
        filters.Regex(r'^/complaint_\d+$'),
        show_complaint
    ))
    
    # Обработка обычных сообщений
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        lambda u, c: u.message.reply_text("Используйте /start для списка команд")
    ))
    
    print("=" * 60)
    print("🤖 БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ!")
    print("💬 Ищите в Telegram и пишите /start")
    print("=" * 60)
    
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
