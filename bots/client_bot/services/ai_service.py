import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from openai import OpenAI


ALLOWED_FIELDS = {
    "fio",
    "phone",
    "pdn_consent",
    "was_here_before",
    "car_plate",
    "car_make_model",
    "vin",
    "problem_text",
    "parts_text",
    "last_visit_text",
    "last_visit_category",
    "last_visit_date",
    "booking_date",
    "booking_time",
    "wants_booking",
}

FORBIDDEN_PATTERNS = {
    "pricing": re.compile(r"\b(цена|стоимост|руб|₽|доллар|евро|\bтыс)\b", re.IGNORECASE),
    "timing": re.compile(r"\b(срок|за\s*\d+\s*(дн|дня|дней|час)|готов|будет\s*готов)\b", re.IGNORECASE),
    "availability": re.compile(r"\b(в\s*наличии|есть\s*запчаст|имеется\s*на\s*склад)\b", re.IGNORECASE),
    "upsell": re.compile(r"\b(рекомендуем|советуем|предлагаем|лучше\s*сделать)\b", re.IGNORECASE),
    "already_done": re.compile(
        r"\b(мы\s*записали|уже\s*записали|вы\s*записан\w*|передали\s*мастеру|"
        r"заявка\s*создана)\b",
        re.IGNORECASE,
    ),
}


@dataclass
class AIResult:
    reply: str
    fields: dict[str, Any]
    used: bool
    reason: str


class AIService:
    def __init__(self, logger: logging.Logger, settings: dict | None = None) -> None:
        self.logger = logger
        self.api_key = self._get_env_value("CLIENT_DEEPSEEK_API_KEY")
        self.base_url = self._get_env_value("CLIENT_DEEPSEEK_BASE_URL")
        self.model = self._get_env_value("CLIENT_DEEPSEEK_MODEL")
        self.timeout = self._get_timeout_seconds()
        self.force_fallback = self._get_env_value("CLIENT_FORCE_FALLBACK") == "1"
        if not self.force_fallback:
            self.force_fallback = self._get_env_value("FORCE_FALLBACK") == "1"
        if settings:
            if "ai_timeout_seconds" in settings and settings["ai_timeout_seconds"] is not None:
                try:
                    self.timeout = int(settings["ai_timeout_seconds"])
                except (TypeError, ValueError):
                    pass
            if "force_fallback" in settings and settings["force_fallback"] is not None:
                try:
                    self.force_fallback = bool(int(settings["force_fallback"]))
                except (TypeError, ValueError):
                    self.force_fallback = bool(settings["force_fallback"])
        self._client: Optional[OpenAI] = None

    @staticmethod
    def _get_env_value(primary: str) -> str:
        primary_value = os.getenv(primary)
        if primary_value is None:
            return ""
        return primary_value.strip()

    def _get_timeout_seconds(self) -> int:
        raw_value = self._get_env_value("CLIENT_AI_TIMEOUT_SECONDS")
        if not raw_value:
            return 10
        try:
            return int(raw_value)
        except ValueError:
            return 10

    def is_enabled(self) -> bool:
        if self.force_fallback:
            return False
        if not self.api_key or not self.base_url or not self.model:
            return False
        return True

    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def ping(self, timeout_seconds: int = 3) -> bool:
        if not self.is_configured():
            return False
        messages = [
            {"role": "system", "content": "Отвечай одним словом."},
            {"role": "user", "content": "ping"},
        ]
        previous_timeout = self.timeout
        self.timeout = min(self.timeout, timeout_seconds) if self.timeout else timeout_seconds
        try:
            _ = self._chat(messages)
            return True
        except Exception:  # noqa: BLE001
            return False
        finally:
            self.timeout = previous_timeout

    def _client_instance(self) -> OpenAI:
        if not self._client:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def _chat(self, messages: list[dict[str, str]]) -> str:
        client = self._client_instance()
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.2,
            timeout=self.timeout,
        )
        content = response.choices[0].message.content or ""
        return content.strip()

    @staticmethod
    def _is_unauthorized(exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        if status_code == 401:
            return True
        response = getattr(exc, "response", None)
        response_status = getattr(response, "status_code", None)
        return response_status == 401

    def _parse_json(self, content: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _check_guardrails(self, text: str) -> list[str]:
        violations = []
        for reason, pattern in FORBIDDEN_PATTERNS.items():
            if pattern.search(text):
                violations.append(reason)
        return violations

    def _filter_fields(self, raw_fields: Any) -> dict[str, Any]:
        if not isinstance(raw_fields, dict):
            return {}
        filtered = {}
        for key, value in raw_fields.items():
            if key not in ALLOWED_FIELDS:
                continue
            if value is None:
                continue
            filtered[key] = value
        return filtered

    def build_message_prompt(
        self,
        stage: str,
        missing_fields: list[str],
        known_fields: dict[str, Any],
        user_text: str,
    ) -> list[dict[str, str]]:
        system = (
            "Ты помощник сервисного бота автосервиса. Твоя задача — помогать уточнять данные "
            "анкеты и задавать короткие вопросы. СТРОГИЕ ЗАПРЕТЫ: не называй цены, сроки ремонта, "
            "наличие запчастей, не навязывай услуги. НЕ выдумывай факты. НЕ утверждай, что запись "
            "или передача мастеру уже сделаны. Разрешено: короткие уточняющие вопросы и помощь "
            "в формулировке проблемы. Можно объяснить: запись только на следующий день, Пн–Пт 09–19. "
            "Отвечай строго JSON без пояснений. Формат: {\"reply\":\"...\", \"fields\":{...}}. "
            "В fields добавляй только то, что явно сказано пользователем, иначе не добавляй."
        )
        user_payload = {
            "stage": stage,
            "missing_fields": missing_fields,
            "known_fields": known_fields,
            "user_text": user_text,
            "instruction": (
                "Сформулируй короткий следующий вопрос для первого поля из missing_fields. "
                "Если пользователь уже дал это поле, спроси следующее."
            ),
        }
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]

    def build_tldr_prompt(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        system = (
            "Сделай краткое TL;DR обращения для мастера (1–3 строки). "
            "НЕ выдумывай. НЕ называй цены, сроки, наличие. НЕ обещай запись. "
            "Только факты из данных. Ответ строго JSON: {\"tldr\":\"...\"}."
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]

    def generate_reply(
        self,
        stage: str,
        missing_fields: list[str],
        known_fields: dict[str, Any],
        user_text: str,
    ) -> AIResult:
        if self.force_fallback:
            return AIResult(reply="", fields={}, used=False, reason="force_fallback")
        if not self.is_enabled():
            return AIResult(reply="", fields={}, used=False, reason="missing_config")
        try:
            content = self._chat(self.build_message_prompt(stage, missing_fields, known_fields, user_text))
            payload = self._parse_json(content)
            if not payload:
                return AIResult(reply="", fields={}, used=False, reason="invalid_json")
            reply = str(payload.get("reply") or "").strip()
            fields = self._filter_fields(payload.get("fields"))
            violations = self._check_guardrails(reply)
            if violations:
                self.logger.info("ai_safeguard violation=%s", ",".join(violations))
                return AIResult(reply="", fields={}, used=False, reason="safeguard_violation")
            return AIResult(reply=reply, fields=fields, used=True, reason="ai_success")
        except Exception as exc:  # noqa: BLE001
            if self._is_unauthorized(exc):
                self.logger.warning("ai_unauthorized: %s", exc)
                return AIResult(reply="", fields={}, used=False, reason="unauthorized")
            self.logger.exception("ai_error: %s", exc)
            return AIResult(reply="", fields={}, used=False, reason="ai_error")

    def generate_tldr(self, payload: dict[str, Any]) -> AIResult:
        if self.force_fallback:
            return AIResult(reply="", fields={}, used=False, reason="force_fallback")
        if not self.is_enabled():
            return AIResult(reply="", fields={}, used=False, reason="missing_config")
        try:
            content = self._chat(self.build_tldr_prompt(payload))
            parsed = self._parse_json(content)
            if not parsed or "tldr" not in parsed:
                return AIResult(reply="", fields={}, used=False, reason="invalid_json")
            tldr = str(parsed.get("tldr") or "").strip()
            violations = self._check_guardrails(tldr)
            if violations:
                self.logger.info("ai_safeguard_tldr violation=%s", ",".join(violations))
                return AIResult(reply="", fields={}, used=False, reason="safeguard_violation")
            return AIResult(reply=tldr, fields={}, used=True, reason="ai_success")
        except Exception as exc:  # noqa: BLE001
            if self._is_unauthorized(exc):
                self.logger.warning("ai_unauthorized_tldr: %s", exc)
                return AIResult(reply="", fields={}, used=False, reason="unauthorized")
            self.logger.exception("ai_error_tldr: %s", exc)
            return AIResult(reply="", fields={}, used=False, reason="ai_error")


def normalize_date_string(value: str) -> str | None:
    cleaned = value.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d.%m"):
        try:
            parsed = datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
        if fmt == "%d.%m":
            parsed = parsed.replace(year=datetime.now().year)
        return parsed.strftime("%Y-%m-%d")
    return None
