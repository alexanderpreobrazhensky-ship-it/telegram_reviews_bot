import requests
import json

OPENAI_API_KEY = "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"

def ask_gpt(prompt):
    url = "https://api.openai.com/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "gpt-4.1-mini",
        "messages": [
            {"role": "system", "content": "Ты помощник для работы с отзывами автосервиса."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }

    response = requests.post(url, headers=headers, json=data, timeout=30)

    if response.status_code != 200:
        return f"Ошибка GPT: {response.text}"

    result = response.json()
    return result["choices"][0]["message"]["content"]
