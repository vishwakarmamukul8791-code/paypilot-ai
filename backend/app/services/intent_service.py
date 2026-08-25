from __future__ import annotations

import re

from app.core.config import settings
from app.schemas.agent import PaymentConditions, PaymentIntent


_MONEY_CAPTURE_PATTERNS = [
    r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)",
    r"([\d,]+(?:\.\d{1,2})?)\s*(?:₹|rs\.?|inr)",
]


def _parse_money_token(token: str) -> float | None:
    """Parse plain, Western-grouped, or Indian-grouped INR amounts safely.

    Examples accepted: 19510, 19,510, 1,95,100, 1,951,000.
    Ambiguous/malformed grouping such as 19,51 or 19,5100 is rejected
    instead of silently stripping commas and authorizing the wrong amount.
    """
    token = token.strip()
    whole = token.split(".", 1)[0]
    if "," not in whole:
        valid = bool(re.fullmatch(r"\d+", whole))
    else:
        western = bool(re.fullmatch(r"\d{1,3}(?:,\d{3})+", whole))
        indian = bool(re.fullmatch(r"\d{1,2}(?:,\d{2})*,\d{3}", whole))
        valid = western or indian
    if not valid:
        return None
    return float(token.replace(",", ""))


def _invalid_money_token(text: str) -> str | None:
    for pattern in _MONEY_CAPTURE_PATTERNS:
        for match in re.finditer(pattern, text, re.I):
            token = match.group(1)
            if _parse_money_token(token) is None:
                return token
    return None


def _amount(text: str) -> float | None:
    for pattern in _MONEY_CAPTURE_PATTERNS:
        match = re.search(pattern, text, re.I)
        if match:
            return _parse_money_token(match.group(1))
    return None


def _money_values(text: str) -> list[float]:
    values: list[float] = []
    for pattern in _MONEY_CAPTURE_PATTERNS:
        for match in re.finditer(pattern, text, re.I):
            parsed = _parse_money_token(match.group(1))
            if parsed is not None:
                values.append(parsed)
    return values


def _condition_amount(text: str, patterns: list[str]) -> tuple[float | None, str]:
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            value = float(match.group(1).replace(",", ""))
            return value, text[: match.start()] + " " + text[match.end() :]
    return None, text


def _unsupported_instruction_reason(text: str) -> str | None:
    lower = text.lower().replace("’", "'")
    payment_terms = r"(?:pay(?:ment)?|send|transfer|remit|recharge)"
    if re.search(rf"\b{payment_terms}\b", lower) and re.search(r"(?:\$|€|£|\b(?:usd|dollars?|eur|euros?|gbp|pounds?)\b)", lower):
        return "Only INR payments are supported by this simulation. No payment was prepared."
    negation_patterns = [
        rf"\b(?:do\s+not|don't|dont|never)\b.{{0,40}}\b{payment_terms}\b",
        rf"\b(?:do\s+not|don't|dont|never)\s+want\s+to\b.{{0,30}}\b{payment_terms}\b",
        rf"\b(?:stop|cancel|abort)\b.{{0,40}}\b{payment_terms}\b",
        rf"\b{payment_terms}\b.{{0,40}}\b(?:stop|cancel|abort)\b",
    ]
    if any(re.search(pattern, lower) for pattern in negation_patterns):
        return "Negative or cancellation-style payment instructions are not executable. No payment was prepared."
    future_terms = (
        r"tomorrow|tonight|later|this\s+(?:afternoon|evening)|next\s+(?:day|week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
        r"schedule(?:d)?|recurring|every\s+(?:day|week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
        r"on\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|in\s+\d+\s*(?:minute|minutes|hour|hours|day|days)|"
        r"(?:at|after)\s+(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight)"
    )
    if re.search(rf"\b(?:pay|send|transfer|remit|recharge)\b.*\b(?:{future_terms})\b", lower) or re.search(r"\bschedule(?:d)?\b.*(?:₹|rs\.?|inr|pay|send|transfer|remit|recharge)", lower):
        return "Scheduled or recurring payments are not supported. Use an immediate single payment request."
    if re.search(r"\b(?:pay|send|transfer|remit|recharge)\b.*(?:,\s*)?\b(?:and\s+then|then)\b", lower):
        return "Chained payment instructions are not supported. Submit one immediate destination and amount at a time."
    return None


def _clean_name(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(value.strip(" .,-").split())
    return cleaned or None


def _strip_money_token(value: str) -> str:
    value = re.sub(r"(?:₹|rs\.?|inr)\s*[\d,]+(?:\.\d{1,2})?", " ", value, flags=re.I)
    value = re.sub(r"[\d,]+(?:\.\d{1,2})?\s*(?:₹|rs\.?|inr)", " ", value, flags=re.I)
    return " ".join(value.split())


def parse_intent_rules(message: str) -> PaymentIntent:
    text = " ".join(message.strip().split())
    lower = text.lower()
    unsupported = _unsupported_instruction_reason(text)
    if unsupported:
        return PaymentIntent(action="unknown", confidence=1.0, guardrail_reason=unsupported)
    invalid_money = _invalid_money_token(text)
    if invalid_money and re.search(r"\b(?:pay|send|transfer|remit|recharge|settle|clear)\b", lower):
        return PaymentIntent(
            action="unknown",
            confidence=1.0,
            guardrail_reason=(
                f"Amount format '{invalid_money}' is ambiguous. "
                "Use a clear INR amount such as ₹19,510 or ₹1,95,100."
            ),
        )
    if any(x in lower for x in ["unusual transaction", "suspicious transaction", "anything unusual", "anything suspicious", "fraud"]):
        return PaymentIntent(action="unusual_transactions")
    if any(x in lower for x in ["spent this month", "spend this month", "monthly spending", "how much did i spend"]):
        return PaymentIntent(action="spend_summary")

    min_remaining, text_wo_min = _condition_amount(text, [
        r"(?:leave|keep|remain(?:s|ing)?|stays?|balance stays?)\D{0,24}(?:₹|rs\.?|inr)?\s*([\d,]+)",
        r"at least\s*(?:₹|rs\.?|inr)?\s*([\d,]+)\s*(?:remain|left|in my account)",
        r"only if\D{0,30}(?:₹|rs\.?|inr)?\s*([\d,]+)\s*(?:remain|left|stays?)",
    ])
    confirm_above, amount_text = _condition_amount(text_wo_min, [
        r"(?:ask me|confirm|approval).*?(?:above|over|more than)\s*(?:₹|rs\.?|inr)?\s*([\d,]+)",
        r"(?:above|over|more than)\s*(?:₹|rs\.?|inr)?\s*([\d,]+).*?(?:ask|confirm|approval)",
    ])
    conditions = PaymentConditions(minimum_remaining_balance=min_remaining, confirm_if_above=confirm_above)

    if "bill" in lower and any(x in lower for x in ["pay", "settle", "clear"]):
        provider = None
        for pattern in [r"(?:pay|settle|clear)\s+(?:my\s+)?(.+?)\s+bill(?:\s|$)", r"(?:pay|settle|clear)\s+(?:the\s+)?bill\s+(?:for|to)\s+(.+?)(?:\s+(?:₹|rs\.?|inr)|$)"]:
            match = re.search(pattern, amount_text, re.I)
            if match:
                provider = _clean_name(_strip_money_token(match.group(1)))
                break
        return PaymentIntent(action="pay_bill", bill_provider=provider, amount=_amount(amount_text), conditions=conditions)

    if any(x in lower for x in ["transfer", "send", "pay", "recharge"]):
        if len(_money_values(amount_text)) > 1 or re.search(r"\b(?:to|pay)\s+[A-Za-z0-9][A-Za-z0-9 &._-]+\s+and\s+[A-Za-z0-9]", amount_text, re.I):
            return PaymentIntent(action="unknown", confidence=1.0, guardrail_reason="Multiple payments in one instruction are not supported. Submit one destination and amount at a time.")
        amount = _amount(amount_text)
        beneficiary = None
        patterns = [
            r"(?:transfer|send|pay)\s+(?:₹|rs\.?|inr)?\s*[\d,]+(?:\.\d{1,2})?\s+(?:to\s+)?([A-Za-z0-9][A-Za-z0-9 &._-]{0,60}?)(?:\s+(?:only|but|if|and|please)|$)",
            r"(?:transfer|send|pay)\s+(?:to\s+)?([A-Za-z0-9][A-Za-z0-9 &._-]{0,60}?)\s+(?:₹|rs\.?|inr)\s*[\d,]+(?:\.\d{1,2})?(?:\s|$)",
            r"recharge\s+([A-Za-z0-9][A-Za-z0-9 &._-]{0,60}?)\s+(?:for\s+)?(?:₹|rs\.?|inr)\s*[\d,]+(?:\.\d{1,2})?(?:\s|$)",
            r"(?:transfer|send|pay)\s+(?:to\s+)?([A-Za-z0-9][A-Za-z0-9 &._-]{0,60}?)(?:\s+(?:only|but|if|and|please)|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, amount_text, re.I)
            if match:
                beneficiary = _clean_name(match.group(1))
                break
        return PaymentIntent(action="transfer", beneficiary=beneficiary, amount=amount, conditions=conditions, confidence=0.9)
    return PaymentIntent(action="unknown", confidence=0.35)


def _merge_with_deterministic_safety(message: str, llm: PaymentIntent) -> PaymentIntent:
    deterministic = parse_intent_rules(message)
    if deterministic.guardrail_reason:
        return deterministic

    if deterministic.action != "unknown":
        data = llm.model_dump()
        data["action"] = deterministic.action
        if deterministic.action in {"transfer", "pay_bill"}:
            # Side-effect fields are always taken from deterministic parsing.
            # The model may interpret language, but it cannot invent payment authority.
            data["beneficiary"] = deterministic.beneficiary
            data["bill_provider"] = deterministic.bill_provider
            data["amount"] = deterministic.amount
            data["currency"] = "INR"
        data["conditions"] = deterministic.conditions.model_dump()
        data["guardrail_reason"] = None
        return PaymentIntent.model_validate(data)

    # Never allow an LLM-only interpretation to create a financial side effect.
    # Unknown deterministic input can still use model assistance for read-only
    # analysis intents, but transfer/bill execution requires deterministic evidence.
    if llm.action in {"spend_summary", "unusual_transactions"}:
        return PaymentIntent(action=llm.action, confidence=llm.confidence)
    return deterministic


def parse_intent(message: str) -> tuple[PaymentIntent, str]:
    deterministic = parse_intent_rules(message)
    if deterministic.guardrail_reason:
        return deterministic, "deterministic-guardrail"
    if settings.gemini_api_key:
        client = None
        try:
            from google import genai
            client = genai.Client(api_key=settings.gemini_api_key)
            prompt = (
                "Extract one safe INR payment intent. Never invent a destination, bill provider, or amount. "
                "Supported actions: transfer, pay_bill, spend_summary, unusual_transactions, unknown. "
                "A transfer can represent a person transfer, merchant payment, mobile recharge, or another user-created destination. "
                "Do not turn negated, scheduled, recurring, or multi-payment instructions into executable payments. "
                "For conditional payments, capture minimum_remaining_balance and confirm_if_above.\n\n"
                f"User request: {message}"
            )
            interaction = client.interactions.create(model=settings.gemini_model, input=prompt, response_format={"type": "text", "mime_type": "application/json", "schema": PaymentIntent.model_json_schema()})
            intent = PaymentIntent.model_validate_json(interaction.output_text)
            return _merge_with_deterministic_safety(message, intent), "gemini"
        except Exception:
            return deterministic, "deterministic-fallback"
        finally:
            if client is not None:
                close = getattr(client, "close", None)
                if callable(close):
                    close()
    return deterministic, "deterministic-demo"
