"""Auditoria somente leitura dos cadastros da cocheira."""
from __future__ import annotations

import re
import statistics
import unicodedata
from collections import defaultdict
from datetime import date
from typing import Any

AUDIT_TERMS = (
    "auditoria", "audite", "auditar", "duplicado", "duplicados", "repetido", "repetidos",
    "dados faltando", "informacoes faltando", "cadastros incompletos", "sem idade", "sem filiacao",
    "sem proprietario", "data inconsistente", "datas inconsistentes", "valor suspeito", "valores suspeitos", "despesa suspeita", "despesas suspeitas",
)


def _plain(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text)).strip()


def is_audit_question(question: str) -> bool:
    query = _plain(question)
    return any(re.search(rf"\b{re.escape(term)}\b", query) for term in AUDIT_TERMS)


def _names(items: list[dict[str, Any]]) -> str:
    return ", ".join(str(item.get("name") or "Nome não definido") for item in items)


def answer_audit_question(
    horses: list[dict[str, Any]], expenses: list[dict[str, Any]], question: str, *, reference_date: str | None = None
) -> dict[str, Any]:
    query = _plain(question)
    today = date.fromisoformat(reference_date) if reference_date else date.today()
    sections: list[str] = []

    names: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for horse in horses:
        if _plain(horse.get("name")):
            names[_plain(horse.get("name"))].append(horse)
    duplicates = [items for items in names.values() if len(items) > 1]

    born = [horse for horse in horses if horse.get("stage") != "creation"]
    missing_age = [horse for horse in born if not horse.get("birthDate") and horse.get("age") in (None, "")]
    missing_parentage = [horse for horse in born if not horse.get("father") or not horse.get("mother")]
    missing_owner = [horse for horse in born if not horse.get("owner")]

    date_issues: list[str] = []
    for horse in horses:
        birth = horse.get("birthDate")
        expected = horse.get("expectedBirthDate")
        try:
            if birth and date.fromisoformat(str(birth)) > today:
                date_issues.append(f"{horse.get('name') or 'Sem nome'} tem nascimento no futuro")
        except ValueError:
            date_issues.append(f"{horse.get('name') or 'Sem nome'} tem data de nascimento inválida")
        try:
            if horse.get("stage") == "creation" and expected and date.fromisoformat(str(expected)) < today:
                date_issues.append(f"{horse.get('name') or 'Cruza sem nome'} tem previsão vencida")
        except ValueError:
            date_issues.append(f"{horse.get('name') or 'Cruza sem nome'} tem previsão inválida")

    expense_keys: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    invalid_expenses: list[str] = []
    amounts = [int(item.get("amountCents") or 0) for item in expenses if int(item.get("amountCents") or 0) > 0]
    for item in expenses:
        key = (item.get("date"), item.get("category"), int(item.get("amountCents") or 0), _plain(item.get("description")))
        expense_keys[key].append(item)
        try:
            date.fromisoformat(str(item.get("date") or ""))
        except ValueError:
            invalid_expenses.append(str(item.get("description") or "Despesa sem descrição") + " tem data inválida")
        if int(item.get("amountCents") or 0) <= 0:
            invalid_expenses.append(str(item.get("description") or "Despesa sem descrição") + " tem valor inválido")
    duplicated_expenses = [items for items in expense_keys.values() if len(items) > 1]
    suspicious: list[dict[str, Any]] = []
    if len(amounts) >= 3:
        median = statistics.median(amounts)
        suspicious = [item for item in expenses if int(item.get("amountCents") or 0) > median * 3]

    wants_duplicates = any(term in query for term in ("duplicado", "duplicados", "repetido", "repetidos"))
    wants_missing = any(term in query for term in ("faltando", "incompletos", "sem idade", "sem filiacao", "sem proprietario"))
    wants_dates = "data" in query
    wants_expenses = any(term in query for term in ("despesa", "valor suspeito"))
    full = not any((wants_duplicates, wants_missing, wants_dates, wants_expenses)) or any(term in query for term in ("auditoria", "audite", "auditar"))

    if full or wants_duplicates:
        horse_text = "; ".join(_names(items) + f" ({len(items)} cadastros)" for items in duplicates) if duplicates else "nenhum nome duplicado"
        expense_text = f"{sum(len(items) for items in duplicated_expenses)} lançamentos em {len(duplicated_expenses)} grupo(s) repetido(s)" if duplicated_expenses else "nenhuma despesa idêntica duplicada"
        sections.append(f"Duplicidades: {horse_text}; {expense_text}.")
    if full or wants_missing:
        sections.append(
            f"Cadastros incompletos: {len(missing_age)} sem idade; {len(missing_parentage)} sem filiação completa; "
            f"{len(missing_owner)} sem proprietário."
        )
        if missing_age:
            sections.append("Sem idade: " + _names(missing_age) + ".")
        if missing_parentage:
            sections.append("Sem filiação completa: " + _names(missing_parentage) + ".")
        if missing_owner:
            sections.append("Sem proprietário: " + _names(missing_owner) + ".")
    if full or wants_dates:
        sections.append("Datas: " + ("; ".join(date_issues) if date_issues else "nenhuma inconsistência encontrada") + ".")
    if full or wants_expenses:
        descriptions = [str(item.get("description") or "Despesa sem descrição") for item in suspicious]
        expense_alerts = invalid_expenses + (["valores muito acima da mediana: " + ", ".join(descriptions)] if descriptions else [])
        sections.append("Despesas: " + ("; ".join(expense_alerts) if expense_alerts else "nenhum valor ou data suspeita encontrado") + ".")

    return {
        "answer": "\n\n".join(sections),
        "matches": [horse.get("id") for group in duplicates for horse in group if horse.get("id")],
        "intent": "audit",
        "options": [
            {"label": "Ver duplicados", "question": "Existem cavalos ou despesas duplicados?"},
            {"label": "Dados faltando", "question": "Quais cadastros estão incompletos?"},
            {"label": "Datas inconsistentes", "question": "Existem datas inconsistentes?"},
            {"label": "Despesas suspeitas", "question": "Existem despesas ou valores suspeitos?"},
        ],
        "context": {"type": "audit"},
    }
