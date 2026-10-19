"""Consultas financeiras em linguagem natural, sem alterar os dados."""
from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date
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
CATEGORY_TERMS = {
    "food": ("alimentacao", "racao", "feno", "comida", "suplemento", "pastagem", "sal mineral"),
    "veterinary": ("veterinario", "veterinaria", "consulta", "exame", "vacina", "cirurgia"),
    "farrier": ("ferrageamento", "ferrador", "ferradura", "casqueamento"),
    "training": ("treinamento", "treino", "adestramento", "instrutor"),
    "transport": ("transporte", "frete", "viagem", "combustivel"),
    "medicine": ("medicamento", "medicamentos", "remedio", "remedios", "farmacia", "vermifugo"),
    "fees": ("taxa", "taxas", "inscricao", "mensalidade", "documentacao"),
    "other": ("outro", "outros"),
}
MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
FINANCE_TERMS = (
    "custo", "custos", "gasto", "gastos", "gastei", "gastamos", "despesa", "despesas",
    "financeiro", "valor pago", "pagamos", "paguei", "media por cavalo", "orcamento",
    "gastar", "gastaremos", "previsao de gastos", "projecao de custos",
    "compare", "comparar", "comparacao", "aumentou", "diminuiu", "diferenca",
    "categoria mais cara", "mais caro", "pico de gastos", "historico mensal",
    "alerta", "alertas", "fora do normal", "anormal", "aumentaram muito", "ultrapassou a media",
    "sugestao", "sugestoes", "economizar", "economia", "reduzir custos", "oportunidade",
    "relatorio", "resumo financeiro", "balanco financeiro", "planilha financeira", "pdf financeiro",
    "estimar", "estimativa", "projetar",
    "alimentacao", "racao", "veterinario", "ferrageamento", "transporte", "medicamento",
    "mensalidade", "despesa fixa", "despesas fixas", "lancamento", "lancamentos",
)


def _plain(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text)).strip()


def is_finance_question(question: str) -> bool:
    query = _plain(question)
    return any(re.search(rf"\b{re.escape(term)}\b", query) for term in FINANCE_TERMS)


def _money(cents: int) -> str:
    value = max(0, int(cents or 0)) / 100
    rendered = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {rendered}"


def _month_shift(year: int, month: int, delta: int) -> tuple[int, int]:
    absolute = year * 12 + month - 1 + delta
    return absolute // 12, absolute % 12 + 1


def _month_label(year: int, month: int) -> str:
    name = next(name for name, number in MONTHS.items() if number == month)
    return f"{name.capitalize()} de {year}"


def _period(query: str, today: date) -> dict[str, Any]:
    if any(term in query for term in ("mes que vem", "proximo mes", "mes seguinte")):
        year, month = _month_shift(today.year, today.month, 1)
        return {"kind": "month", "year": year, "month": month, "label": _month_label(year, month), "future": True}
    if any(term in query for term in ("este mes", "nesse mes", "neste mes", "mes atual", "do mes", "no mes")):
        return {"kind": "month", "year": today.year, "month": today.month, "label": _month_label(today.year, today.month)}
    numeric = re.search(r"\b(0?[1-9]|1[0-2])(?:[/\-]|\s+)(20\d{2})\b", query)
    month = int(numeric.group(1)) if numeric else next((number for name, number in MONTHS.items() if re.search(rf"\b{name}\b", query)), None)
    year_match = re.search(r"\b(20\d{2})\b", query)
    year = int(numeric.group(2)) if numeric else int(year_match.group(1)) if year_match else None
    if month:
        year = year or today.year
        return {"kind": "month", "year": year, "month": month, "label": _month_label(year, month)}
    if any(term in query for term in ("mes passado", "ultimo mes", "mes anterior")):
        year, month = _month_shift(today.year, today.month, -1)
        return {"kind": "month", "year": year, "month": month, "label": _month_label(year, month)}
    if any(term in query for term in ("este ano", "nesse ano", "neste ano", "ano atual", "do ano")):
        return {"kind": "year", "year": today.year, "label": str(today.year)}
    if any(term in query for term in ("anual", "ano inteiro")):
        return {"kind": "year", "year": today.year, "label": str(today.year)}
    if year:
        return {"kind": "year", "year": year, "label": str(year)}
    recent = re.search(r"ultimos? (\d{1,2}) meses", query)
    if recent:
        count = min(24, max(1, int(recent.group(1))))
        return {"kind": "recent", "count": count, "label": f"últimos {count} meses"}
    return {"kind": "month", "year": today.year, "month": today.month, "label": _month_label(today.year, today.month), "default": True}


def _category(query: str) -> str | None:
    candidates: list[tuple[int, str]] = []
    for key, terms in CATEGORY_TERMS.items():
        for term in terms:
            if re.search(rf"\b{re.escape(term)}\b", query):
                candidates.append((len(term), key))
    return max(candidates)[1] if candidates else None


def _expense_month(expense: dict[str, Any]) -> tuple[int, int] | None:
    try:
        parsed = date.fromisoformat(str(expense.get("date") or ""))
        return parsed.year, parsed.month
    except ValueError:
        return None


def _for_month(expenses: list[dict[str, Any]], year: int, month: int) -> list[dict[str, Any]]:
    target = (year, month)
    found: list[dict[str, Any]] = []
    for expense in expenses:
        source = _expense_month(expense)
        if not source:
            continue
        if source == target:
            found.append(expense)
        elif expense.get("recurring") and source < target:
            projected = dict(expense)
            day = min(calendar.monthrange(year, month)[1], max(1, int(expense.get("recurrenceDay") or 1)))
            projected["date"] = f"{year:04d}-{month:02d}-{day:02d}"
            projected["recurringProjection"] = True
            found.append(projected)
    return found


def _period_expenses(expenses: list[dict[str, Any]], period: dict[str, Any], today: date) -> list[dict[str, Any]]:
    if period["kind"] == "month":
        return _for_month(expenses, period["year"], period["month"])
    if period["kind"] == "year":
        last_month = today.month if period["year"] == today.year else 12
        return [item for month in range(1, last_month + 1) for item in _for_month(expenses, period["year"], month)]
    months = [_month_shift(today.year, today.month, -offset) for offset in reversed(range(period["count"]))]
    return [item for year, month in months for item in _for_month(expenses, year, month)]


def _base_result(
    answer: str,
    options: list[dict[str, str]] | None = None,
    expenses: list[dict[str, Any]] | None = None,
    *,
    context: dict[str, Any] | None = None,
    actions: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "answer": answer,
        "matches": [],
        "expenseMatches": [item.get("id") for item in (expenses or []) if item.get("id")],
        "intent": "costs",
        "options": options or [],
        "context": context or {},
        "actions": actions or [],
    }


def _breakdown(items: list[dict[str, Any]]) -> list[tuple[str, int]]:
    totals = {key: 0 for key in CATEGORIES}
    for item in items:
        key = str(item.get("category") or "other")
        totals[key if key in totals else "other"] += int(item.get("amountCents") or 0)
    return sorted(((key, value) for key, value in totals.items() if value), key=lambda pair: pair[1], reverse=True)


def _list(items: list[dict[str, Any]], limit: int = 8) -> str:
    ordered = sorted(items, key=lambda item: (str(item.get("date") or ""), int(item.get("amountCents") or 0)), reverse=True)
    rows = []
    for item in ordered[:limit]:
        description = str(item.get("description") or CATEGORIES.get(item.get("category"), "Despesa"))
        marker = " (fixa)" if item.get("recurring") else ""
        rows.append(f"{description}: {_money(item.get('amountCents', 0))} em {str(item.get('date') or '')[8:10]}/{str(item.get('date') or '')[5:7]}{marker}")
    suffix = f" Mais {len(items) - limit} lançamento(s) não exibido(s)." if len(items) > limit else ""
    return "; ".join(rows) + suffix


def _month_totals(expenses: list[dict[str, Any]], period: dict[str, Any], today: date) -> list[tuple[int, int, int]]:
    if period["kind"] == "year":
        last_month = today.month if period["year"] == today.year else 12
        months = [(period["year"], month) for month in range(1, last_month + 1)]
    elif period["kind"] == "recent":
        months = [_month_shift(today.year, today.month, -offset) for offset in reversed(range(period["count"]))]
    else:
        months = [(period["year"], period["month"])]
    return [
        (year, month, sum(int(item.get("amountCents") or 0) for item in _for_month(expenses, year, month)))
        for year, month in months
    ]


def _historical_variable_average(expenses: list[dict[str, Any]], today: date, months: int = 3) -> int:
    totals: list[int] = []
    for offset in range(1, months + 1):
        year, month = _month_shift(today.year, today.month, -offset)
        value = sum(int(item.get("amountCents") or 0) for item in _for_month(expenses, year, month) if not item.get("recurring"))
        totals.append(value)
    return round(sum(totals) / len(totals)) if totals else 0


def answer_financial_question(
    expenses: list[dict[str, Any]],
    horses: list[dict[str, Any]],
    question: str,
    *,
    context: dict[str, Any] | None = None,
    reference_date: str | None = None,
) -> dict[str, Any]:
    """Responde consultas de custo usando somente os registros da conta."""
    query = _plain(question)
    today = date.fromisoformat(reference_date) if reference_date else date.today()
    period = _period(query, today)
    incoming = context if isinstance(context, dict) and context.get("type") == "finance" else {}
    follow_up = query.startswith(("e ", "agora ", "somente ", "apenas ", "nesse periodo", "neste periodo"))
    saved_period = incoming.get("period")
    if period.get("default") and follow_up and isinstance(saved_period, dict) and saved_period.get("kind") in ("month", "year", "recent"):
        period = dict(saved_period)
    items = _period_expenses(expenses, period, today)
    category = _category(query)
    if category is None and follow_up and incoming.get("category") in CATEGORIES:
        category = str(incoming["category"])
    if category:
        items = [item for item in items if item.get("category") == category]
    category_text = f" de {CATEGORIES[category]}" if category else ""
    conversation_context = {"type": "finance", "period": period, "category": category}

    def _result(answer, options=None, selected=None, *, actions=None):
        return _base_result(answer, options, selected, context=conversation_context, actions=actions)

    if any(term in query for term in ("exemplo", "o que posso perguntar", "como funciona")):
        return _result("Posso somar, comparar, listar e analisar despesas. Escolha um exemplo:", [
            {"label": "Total do mês", "question": "Quanto gastamos este mês?"},
            {"label": "Por categoria", "question": "Como os custos deste mês estão distribuídos por categoria?"},
            {"label": "Custo por cavalo", "question": "Qual é o custo médio por cavalo este mês?"},
            {"label": "Despesas fixas", "question": "Quais são as despesas fixas deste mês?"},
            {"label": "Comparar meses", "question": "Compare este mês com o mês passado"},
        ])

    if not expenses:
        return _result("Ainda não há despesas cadastradas para analisar.")

    if any(term in query for term in ("relatorio", "resumo financeiro", "balanco financeiro", "planilha financeira", "pdf financeiro")):
        report_period = str(period["year"]) if period["kind"] == "year" else f"{period['year']:04d}-{period['month']:02d}" if period["kind"] == "month" else f"{today.year:04d}-{today.month:02d}"
        total = sum(int(item.get("amountCents") or 0) for item in items)
        breakdown = _breakdown(items)
        leader = f" A maior categoria é {CATEGORIES[breakdown[0][0]]}, com {_money(breakdown[0][1])}." if breakdown else ""
        return _result(
            f"O relatório de {period['label']} reúne {len(items)} lançamento(s), total de {_money(total)}.{leader} Escolha o formato para baixar.",
            selected=items,
            actions=[
                {"type": "report", "format": "pdf", "period": report_period, "label": "Baixar PDF"},
                {"type": "report", "format": "xlsx", "period": report_period, "label": "Baixar planilha"},
            ],
        )

    if any(term in query for term in ("aumentaram muito", "custos aumentaram", "gastos aumentaram")):
        if period["kind"] != "month":
            period = {"kind": "month", "year": today.year, "month": today.month, "label": _month_label(today.year, today.month)}
        previous_year, previous_month = _month_shift(period["year"], period["month"], -1)
        current = dict(_breakdown(_for_month(expenses, period["year"], period["month"])))
        previous = dict(_breakdown(_for_month(expenses, previous_year, previous_month)))
        alerts = []
        for key, value in sorted(current.items(), key=lambda pair: pair[1], reverse=True):
            old = previous.get(key, 0)
            if old and value >= old * 1.25:
                alerts.append(f"{CATEGORIES[key]} subiu de {_money(old)} para {_money(value)} ({round((value - old) * 100 / old)}%)")
            elif not old and value:
                alerts.append(f"{CATEGORIES[key]} apareceu neste mês com {_money(value)}, sem valor no mês anterior")
        if not alerts:
            return _result(f"Não encontrei categorias com aumento de 25% ou mais em {period['label']} comparado ao mês anterior.")
        return _result("Alertas de aumento: " + "; ".join(alerts) + ".")

    if any(term in query for term in ("fora do normal", "anormal", "despesa suspeita", "valor suspeito")):
        values = sorted(int(item.get("amountCents") or 0) for item in items if int(item.get("amountCents") or 0) > 0)
        median = values[len(values) // 2] if values else 0
        unusual = [item for item in items if median and int(item.get("amountCents") or 0) >= median * 2.5]
        if not unusual:
            return _result(f"Não encontrei lançamentos pelo menos 2,5 vezes maiores que a mediana em {period['label']}. Isso é um alerta estatístico, não uma confirmação de erro.")
        return _result(f"Possíveis valores fora do padrão em {period['label']}: {_list(unusual)}. Confirme os documentos antes de corrigir qualquer lançamento.", selected=unusual)

    if any(term in query for term in ("ultrapassou a media", "acima da media", "categorias acima da media")):
        breakdown = _breakdown(items)
        average = round(sum(value for _, value in breakdown) / len(breakdown)) if breakdown else 0
        above = [(key, value) for key, value in breakdown if value > average]
        if not above:
            return _result(f"Não há categorias acima da média em {period['label']}.")
        rows = [f"{CATEGORIES[key]} com {_money(value)}" for key, value in above]
        return _result(f"A média entre as categorias com movimento em {period['label']} é {_money(average)}. Acima dela: " + "; ".join(rows) + ".")

    if any(term in query for term in ("sugestao", "sugestoes", "economizar", "economia", "reduzir custos", "oportunidade")):
        breakdown = _breakdown(items)
        total = sum(value for _, value in breakdown)
        if not total:
            return _result(f"Não há despesas em {period['label']} para gerar sugestões.")
        key, value = breakdown[0]
        fixed_total = sum(int(item.get("amountCents") or 0) for item in items if item.get("recurring"))
        suggestions = [f"revisar {CATEGORIES[key]}, que representa {round(value * 100 / total)}% do total"]
        if fixed_total:
            suggestions.append(f"reavaliar contratos e despesas fixas, que somam {_money(fixed_total)}")
        if period["kind"] == "month":
            previous_year, previous_month = _month_shift(period["year"], period["month"], -1)
            previous_total = sum(int(item.get("amountCents") or 0) for item in _for_month(expenses, previous_year, previous_month))
            if previous_total and total > previous_total:
                suggestions.append(f"investigar o aumento de {_money(total - previous_total)} em relação ao mês anterior")
        return _result("Sugestões baseadas nos dados: " + "; ".join(suggestions) + ". São pontos para revisão administrativa, não garantias de economia.")

    if any(term in query for term in ("compare", "comparacao", "comparar", "aumentou", "diminuiu", "diferenca")):
        current_period = _period(query, today)
        if current_period["kind"] != "month":
            return _result("A comparação precisa de um mês de referência.", [
                {"label": "Este mês × anterior", "question": "Compare este mês com o mês passado"},
            ])
        previous_year, previous_month = _month_shift(current_period["year"], current_period["month"], -1)
        current_items = _for_month(expenses, current_period["year"], current_period["month"])
        previous_items = _for_month(expenses, previous_year, previous_month)
        current_total = sum(int(item.get("amountCents") or 0) for item in current_items)
        previous_total = sum(int(item.get("amountCents") or 0) for item in previous_items)
        difference = current_total - previous_total
        if not previous_total:
            return _result(f"{current_period['label']} soma {_money(current_total)}. O mês anterior não tem despesas para uma comparação percentual.")
        percent = abs(difference) * 100 / previous_total
        direction = "aumento" if difference > 0 else "redução" if difference < 0 else "nenhuma variação"
        if not difference:
            return _result(f"{current_period['label']} e {_month_label(previous_year, previous_month)} tiveram o mesmo total: {_money(current_total)}.")
        detail = f"{direction} de {_money(abs(difference))} ({percent:.1f}%)".replace(".", ",")
        return _result(f"{current_period['label']}: {_money(current_total)}. {_month_label(previous_year, previous_month)}: {_money(previous_total)}. Houve {detail}.")

    if any(term in query for term in ("mes mais caro", "mes que mais", "maior mes", "pico de gastos")):
        analysis_period = period if period["kind"] in ("year", "recent") else {"kind": "year", "year": today.year, "label": str(today.year)}
        totals = _month_totals(expenses, analysis_period, today)
        maximum = max((value for _, _, value in totals), default=0)
        if not maximum:
            return _result(f"Não há despesas em {analysis_period['label']}.")
        leaders = [_month_label(year, month) for year, month, value in totals if value == maximum]
        return _result(f"O maior custo de {analysis_period['label']} ocorreu em {' e '.join(leaders)}, com {_money(maximum)}.")

    if any(term in query for term in ("evolucao", "mes a mes", "por mes", "historico mensal")):
        analysis_period = period if period["kind"] in ("year", "recent") else {"kind": "recent", "count": 6, "label": "últimos 6 meses"}
        totals = _month_totals(expenses, analysis_period, today)
        rows = [f"{_month_label(year, month)}: {_money(value)}" for year, month, value in totals]
        return _result(f"Evolução em {analysis_period['label']} — " + "; ".join(rows) + ".")

    forecast_question = any(term in query for term in ("previsao", "projecao", "projetar", "estimar", "estimativa", "vou gastar", "vamos gastar", "gastaremos"))
    if forecast_question and period["kind"] == "year":
        year = period["year"]
        completed_month = today.month if year == today.year else 0
        actual = sum(int(item.get("amountCents") or 0) for item in _period_expenses(expenses, {"kind": "year", "year": year, "label": str(year)}, today)) if completed_month else 0
        fixed_monthly = sum(int(item.get("amountCents") or 0) for item in _for_month(expenses, today.year, today.month) if item.get("recurring"))
        variable_average = _historical_variable_average(expenses, today)
        remaining = max(0, 12 - completed_month)
        estimate = actual + remaining * (fixed_monthly + variable_average)
        low = actual + remaining * (fixed_monthly + round(variable_average * .8))
        high = actual + remaining * (fixed_monthly + round(variable_average * 1.2))
        return _result(
            f"A projeção para {year} é {_money(estimate)}, com faixa provável entre {_money(low)} e {_money(high)}. "
            f"Ela combina {_money(actual)} já registrados, despesas fixas e a média variável dos últimos 3 meses. Valores futuros são estimativas, não garantias."
        )

    if period.get("future") or forecast_question:
        fixed = [item for item in items if item.get("recurring")]
        fixed_total = sum(int(item.get("amountCents") or 0) for item in fixed)
        variable_average = _historical_variable_average(expenses, today)
        estimate = fixed_total + variable_average
        low = fixed_total + round(variable_average * .8)
        high = fixed_total + round(variable_average * 1.2)
        return _result(
            f"A estimativa para {period['label']} é {_money(estimate)}, com faixa provável entre {_money(low)} e {_money(high)}. "
            f"A conta usa {_money(fixed_total)} de despesas fixas e a média variável dos últimos 3 meses. É uma estimativa, não uma garantia.",
            selected=fixed,
        )

    if any(term in query for term in ("fixa", "fixas", "recorrente", "recorrentes")):
        fixed = [item for item in items if item.get("recurring")]
        if not fixed:
            return _result(f"Não há despesas fixas{category_text} em {period['label']}.")
        total = sum(int(item.get("amountCents") or 0) for item in fixed)
        return _result(f"Há {len(fixed)} despesa(s) fixa(s){category_text} em {period['label']}, totalizando {_money(total)}. {_list(fixed)}.", selected=fixed)

    if any(term in query for term in ("distribu", "por categoria", "categorias", "onde gast", "com o que")):
        breakdown = _breakdown(items)
        if not breakdown:
            return _result(f"Não há despesas em {period['label']} para distribuir por categoria.")
        total = sum(value for _, value in breakdown)
        rows = [f"{CATEGORIES[key]}: {_money(value)} ({round(value * 100 / total)}%)" for key, value in breakdown]
        return _result(f"Distribuição de {period['label']} — " + "; ".join(rows) + f". Total: {_money(total)}.", selected=items)

    if any(term in query for term in ("maior categoria", "categoria mais cara", "mais gastamos", "maior custo")) and "despesa" not in query:
        breakdown = _breakdown(items)
        if not breakdown:
            return _result(f"Não há despesas em {period['label']}.")
        key, value = breakdown[0]
        return _result(f"A maior categoria em {period['label']} é {CATEGORIES[key]}, com {_money(value)}.", selected=items)

    if any(term in query for term in ("maior despesa", "despesa mais cara", "maior lancamento", "gasto mais alto")):
        if not items:
            return _result(f"Não há despesas{category_text} em {period['label']}.")
        maximum = max(int(item.get("amountCents") or 0) for item in items)
        found = [item for item in items if int(item.get("amountCents") or 0) == maximum]
        return _result(f"A maior despesa{category_text} em {period['label']} foi {_money(maximum)}. {_list(found)}.", selected=found)

    if any(term in query for term in ("media por cavalo", "medio por cavalo", "custo por cavalo", "cada cavalo")):
        total = sum(int(item.get("amountCents") or 0) for item in items)
        horse_count = sum(horse.get("stage") in ("foals", "training", "ready") for horse in horses)
        if not horse_count:
            return _result(f"O total em {period['label']} é {_money(total)}, mas não há cavalos nas etapas Potros e Desenvolvimento, Preparação e Treinamento ou Tropa pronta para calcular a média.")
        return _result(f"Em {period['label']}, o custo médio é {_money(round(total / horse_count))} por cavalo: {_money(total)} divididos por {horse_count} cavalos.", selected=items)

    if any(term in query for term in ("media mensal", "media por mes", "media dos meses")):
        months = 1 if period["kind"] == "month" else 12 if period["kind"] == "year" else period["count"]
        total = sum(int(item.get("amountCents") or 0) for item in items)
        return _result(f"A média mensal em {period['label']} é {_money(round(total / months))}, considerando {_money(total)} em {months} mês(es).", selected=items)

    if any(term in query for term in ("quantas despesas", "quantos gastos", "quantos lancamentos", "numero de despesas")):
        return _result(f"Há {len(items)} lançamento(s){category_text} em {period['label']}.", selected=items)

    if any(term in query for term in ("liste", "listar", "mostre", "quais", "detalhe", "ultimas despesas", "gastos recentes")):
        if not items:
            return _result(f"Não há despesas{category_text} em {period['label']}.")
        total = sum(int(item.get("amountCents") or 0) for item in items)
        return _result(f"Despesas{category_text} em {period['label']}: {_list(items)}. Total: {_money(total)}.", selected=items)

    # Se a pessoa disser "com sela", "com evento" etc., busca também na descrição.
    described = re.search(r"\bcom (?!o que\b)(.+?)(?:\s+(?:este|neste|nesse|no|em)\s+(?:mes|ano|janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)|$)", query)
    if described and not category:
        term = described.group(1).strip()
        matched = [item for item in items if term in _plain(item.get("description"))]
        if not matched:
            return _result(f"Não encontrei despesas com “{term}” em {period['label']}.")
        total = sum(int(item.get("amountCents") or 0) for item in matched)
        return _result(f"As despesas com “{term}” em {period['label']} somam {_money(total)}. {_list(matched)}.", selected=matched)

    # Uma pergunta financeira genérica recebe um resumo útil, sem exigir palavras exatas.
    total = sum(int(item.get("amountCents") or 0) for item in items)
    if not items:
        return _result(f"Não há despesas{category_text} em {period['label']}.")
    breakdown = _breakdown(items)
    leader = f" A maior categoria é {CATEGORIES[breakdown[0][0]]}, com {_money(breakdown[0][1])}." if breakdown and not category else ""
    return _result(
        f"O custo total{category_text} em {period['label']} é {_money(total)}, em {len(items)} lançamento(s).{leader}",
        [
            {"label": "Ver categorias", "question": f"Como os custos de {period['label']} estão distribuídos por categoria?"},
            {"label": "Custo por cavalo", "question": f"Qual é o custo médio por cavalo em {period['label']}?"},
            {"label": "Despesas fixas", "question": f"Quais são as despesas fixas de {period['label']}?"},
            {"label": "Comparar", "question": f"Compare {period['label']} com o mês anterior"},
        ],
        items,
    )
