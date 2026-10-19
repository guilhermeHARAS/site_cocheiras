"""Validação e interpretação simples dos custos da cocheira."""
from __future__ import annotations

import re
import unicodedata
import uuid
import base64
import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

CATEGORIES = {
    "food": "Alimentação",
    "veterinary": "Veterinário",
    "farrier": "Ferrageamento",
    "training": "Treinamento",
    "transport": "Transporte",
    "medicine": "Medicamentos",
    "fees": "Taxas",
    "other": "Outros",
}

CATEGORY_ALIASES = {
    "alimentacao": "food", "racao": "food", "comida": "food",
    "veterinario": "veterinary", "veterinaria": "veterinary",
    "ferrageamento": "farrier", "ferrador": "farrier",
    "treinamento": "training", "treino": "training",
    "transporte": "transport", "frete": "transport",
    "medicamento": "medicine", "medicamentos": "medicine", "remedio": "medicine",
    "taxa": "fees", "taxas": "fees", "outros": "other", "outro": "other",
}

IMPORT_ALIASES = {
    "description": {"descricao", "descrição", "despesa", "item", "nome", "historico", "histórico"},
    "amount": {"valor", "custo", "preco", "preço", "total", "valor pago", "valor r$"},
    "date": {"data", "dia", "vencimento", "data pagamento", "pago em"},
    "category": {"categoria", "tipo", "grupo"},
    "recurring": {"recorrente", "fixa", "fixo", "mensal", "repetir"},
}
IMPORT_ALIAS_TO_FIELD = {_plain_alias: field for field, aliases in IMPORT_ALIASES.items() for _plain_alias in aliases}
MAX_IMPORT_ROWS = 2_000
MAX_FILE_BYTES = 8 * 1024 * 1024

CATEGORY_TERMS = {
    "food": ("racao", "feno", "alimentacao", "suplemento", "sal mineral", "pastagem"),
    "veterinary": ("veterinario", "consulta", "exame", "cirurgia", "vacina"),
    "farrier": ("ferrageamento", "ferrador", "ferradura", "casqueamento"),
    "training": ("treinamento", "treino", "adestramento", "instrutor"),
    "transport": ("transporte", "frete", "viagem", "combustivel"),
    "medicine": ("medicamento", "remedio", "farmacia", "vermifugo"),
    "fees": ("taxa", "inscricao", "mensalidade", "documentacao"),
}


def _plain(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(char for char in text if not unicodedata.combining(char))


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _plain(value)).strip()


def _amount_to_cents(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    text = str(value or "").strip().replace("R$", "").replace(" ", "")
    if not text:
        return 0
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", text):
        text = text.replace(".", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    try:
        return int((Decimal(text) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except InvalidOperation as exc:
        raise ValueError("Informe um valor válido.") from exc


def _valid_date(value: Any) -> str:
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError("Informe uma data válida para a despesa.") from exc


def validate_expense(payload: dict[str, Any], *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    current = dict(existing or {})
    cents = _amount_to_cents(payload.get("amountCents", payload.get("amount", current.get("amountCents", 0))))
    if cents <= 0 or cents > 10_000_000_00:
        raise ValueError("Informe um valor maior que zero.")
    category = str(payload.get("category", current.get("category", "other")))
    if category not in CATEGORIES:
        category = "other"
    scope = str(payload.get("scope", current.get("scope", "general")))
    if scope not in ("general", "horse"):
        scope = "general"
    horse_id = str(payload.get("horseId", current.get("horseId", "")) or "").strip()[:64]
    if scope == "horse" and not horse_id:
        raise ValueError("Selecione o cavalo relacionado à despesa.")
    if scope == "general":
        horse_id = ""
    today = date.today().isoformat()
    recurring_raw = payload.get("recurring", current.get("recurring", False))
    recurring = recurring_raw is True or _key(recurring_raw) in {"1", "sim", "s", "yes", "mensal", "fixa", "fixo", "recorrente"}
    recurrence_day = int(payload.get("recurrenceDay") or current.get("recurrenceDay") or str(payload.get("date", current.get("date", today)))[-2:])
    recurrence_day = min(31, max(1, recurrence_day))
    result = current
    result.update({
        "id": current.get("id") or uuid.uuid4().hex,
        "workspaceId": current.get("workspaceId"),
        "amountCents": cents,
        "date": _valid_date(payload.get("date", current.get("date", today))),
        "category": category,
        "scope": scope,
        "horseId": horse_id,
        "description": str(payload.get("description", current.get("description", "")) or "").strip()[:180],
        "recurring": recurring,
        "recurrenceDay": recurrence_day if recurring else None,
        "createdAt": current.get("createdAt") or today,
        "updatedAt": today,
    })
    return result


def parse_expense_text(text: str, horses: list[dict[str, Any]], *, reference_date: str | None = None) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("Descreva a despesa que deseja lançar.")
    plain = _plain(raw)
    number_pattern = r"((?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?|\d+\.\d{1,2})"
    amount_match = (
        re.search(r"r\$\s*" + number_pattern, plain)
        or re.search(number_pattern + r"\s*reais?", plain)
        or re.search(r"(?<![\d/.-])" + number_pattern + r"(?![\d/.-])", plain)
    )
    amount_cents = _amount_to_cents(amount_match.group(1)) if amount_match else 0

    category = "other"
    for key, terms in CATEGORY_TERMS.items():
        if any(term in plain for term in terms):
            category = key
            break

    reference = date.fromisoformat(reference_date) if reference_date else date.today()
    expense_date = reference
    explicit = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", plain)
    if "ontem" in plain:
        expense_date = reference - timedelta(days=1)
    elif explicit:
        year = int(explicit.group(3) or reference.year)
        if year < 100:
            year += 2000
        try:
            expense_date = date(year, int(explicit.group(2)), int(explicit.group(1)))
        except ValueError:
            pass

    selected = None
    for horse in sorted(horses, key=lambda item: len(str(item.get("name") or "")), reverse=True):
        name = _plain(horse.get("name"))
        if name and name in plain:
            selected = horse
            break

    issues = []
    if amount_cents <= 0:
        issues.append("Não encontrei o valor da despesa.")
    return {
        "draft": {
            "amountCents": amount_cents,
            "date": expense_date.isoformat(),
            "category": category,
            "scope": "horse" if selected else "general",
            "horseId": selected.get("id") if selected else "",
            "description": raw[:180],
            "recurring": any(term in plain for term in ("recorrente", "mensal", "todo mes", "todos os meses", "despesa fixa", "custo fixo")),
        },
        "issues": issues,
        "summary": "Revise os dados identificados antes de salvar.",
    }


def _category(value: Any, description: str) -> str:
    explicit = CATEGORY_ALIASES.get(_key(value))
    if explicit:
        return explicit
    plain = _plain(description)
    for key, terms in CATEGORY_TERMS.items():
        if any(term in plain for term in terms):
            return key
    return "other"


def _import_date(value: Any, reference: date) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)) and 1 <= float(value) <= 100_000:
        return (date(1899, 12, 30) + timedelta(days=int(value))).isoformat()
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return reference.isoformat()


def _import_record(values: dict[str, Any], reference: date, origin: str) -> dict[str, Any]:
    description = str(values.get("description") or "").strip()[:180]
    try:
        amount = _amount_to_cents(values.get("amount"))
    except ValueError:
        amount = 0
    recurring_value = values.get("recurring", False)
    recurring = recurring_value is True or _key(recurring_value) in {"1", "sim", "s", "x", "mensal", "fixa", "fixo", "recorrente"}
    record_date = _import_date(values.get("date"), reference)
    issues = []
    if amount <= 0:
        issues.append("Confira o valor")
    if not description:
        description = CATEGORIES.get(_category(values.get("category"), ""), "Despesa")
    return {
        "amountCents": amount,
        "date": record_date,
        "category": _category(values.get("category"), description),
        "description": description,
        "recurring": recurring,
        "recurrenceDay": int(record_date[-2:]) if recurring else None,
        "importOrigin": origin,
        "issues": issues,
        "selected": not issues,
    }


def _header_mapping(row: list[Any]) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for index, cell in enumerate(row):
        field = IMPORT_ALIAS_TO_FIELD.get(_key(cell))
        if field and field not in mapping.values():
            mapping[index] = field
    return mapping


def parse_expense_spreadsheet(filename: str, content_base64: str, *, reference_date: str | None = None) -> dict[str, Any]:
    try:
        raw = base64.b64decode(content_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Não foi possível ler o arquivo enviado.") from exc
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise ValueError("A planilha deve ter no máximo 8 MB.")
    suffix = Path(filename or "").suffix.lower()
    sheets: list[tuple[str, list[list[Any]]]] = []
    if suffix == ".csv":
        text = raw.decode("utf-8-sig", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t|")
        except csv.Error:
            dialect = csv.excel
            dialect.delimiter = ";"
        sheets.append(("CSV", list(csv.reader(io.StringIO(text), dialect))[:MAX_IMPORT_ROWS + 20]))
    elif suffix == ".xlsx":
        try:
            from openpyxl import load_workbook
            workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            for sheet in workbook.worksheets:
                sheets.append((sheet.title, [list(row) for row in sheet.iter_rows(values_only=True, max_row=MAX_IMPORT_ROWS + 20)]))
        except Exception as exc:
            raise ValueError("O arquivo Excel está inválido ou protegido por senha.") from exc
    else:
        raise ValueError("Envie uma planilha .xlsx ou .csv.")
    reference = date.fromisoformat(reference_date) if reference_date else date.today()
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    for sheet_name, rows in sheets:
        candidates = [(index, _header_mapping(row)) for index, row in enumerate(rows[:20])]
        header_index, mapping = max(candidates, key=lambda item: len(item[1]), default=(0, {}))
        if "amount" not in mapping.values():
            warnings.append(f"A aba “{sheet_name}” não possui uma coluna Valor ou Custo.")
            continue
        for row_number, row in enumerate(rows[header_index + 1:], start=header_index + 2):
            if not any(str(cell or "").strip() for cell in row):
                continue
            values = {field: row[index] if index < len(row) else None for index, field in mapping.items()}
            records.append(_import_record(values, reference, f"{sheet_name}, linha {row_number}"))
            if len(records) >= MAX_IMPORT_ROWS:
                break
    if not records:
        raise ValueError("Nenhuma despesa foi encontrada. Use ao menos uma coluna Valor ou Custo.")
    return {"records": records, "warnings": warnings}


def parse_expense_notes(text: str, *, reference_date: str | None = None) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("Cole ou digite as anotações de custos.")
    reference = date.fromisoformat(reference_date) if reference_date else date.today()
    lines = [line.strip(" -•\t") for line in raw.splitlines() if line.strip(" -•\t")]
    groups: list[str] = []
    for line in lines:
        if re.search(r"(?:r\$\s*)?\d+(?:[.,]\d+)?", _plain(line)):
            groups.append(line)
        elif groups:
            groups[-1] += " " + line
        else:
            groups.append(line)
    records: list[dict[str, Any]] = []
    for index, group in enumerate(groups[:MAX_IMPORT_ROWS], start=1):
        parsed = parse_expense_text(group, [], reference_date=reference.isoformat())["draft"]
        record = _import_record({
            "amount": parsed["amountCents"], "date": parsed["date"], "category": parsed["category"],
            "description": group, "recurring": parsed.get("recurring", False),
        }, reference, f"Anotações, item {index}")
        # O interpretador retorna centavos; evita convertê-los novamente como reais.
        record["amountCents"] = parsed["amountCents"]
        record["issues"] = [] if parsed["amountCents"] > 0 else ["Confira o valor"]
        record["selected"] = not record["issues"]
        records.append(record)
    return {"records": records, "warnings": []}
