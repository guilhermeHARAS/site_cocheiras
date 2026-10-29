"""Assistente local, somente leitura, para consultas sobre a cocheira."""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

from audit_assistant import answer_audit_question, is_audit_question
from domain import TRAINING_GOAL
from finance_assistant import answer_financial_question, is_finance_question

STAGE_NAMES = {
    "creation": "Reprodução",
    "foals": "Potros e Desenvolvimento",
    "training": "Preparação e Treinamento",
    "ready": "Tropa pronta",
}
MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}


def _plain(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text)).strip()


def _names(horses: list[dict[str, Any]]) -> str:
    values = [str(horse.get("name") or "Nome não definido") for horse in horses]
    if not values:
        return "nenhum"
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + " e " + values[-1]


def _stage_in(question: str) -> str | None:
    if any(term in question for term in ("cruza", "cruzas", "reproducao", "nascimento previsto")):
        return "creation"
    if any(term in question for term in ("potro", "potros", "desenvolvimento")):
        return "foals"
    if any(term in question for term in ("treinamento", "treinando", "em treino", "preparacao")):
        return "training"
    if any(term in question for term in ("tropa pronta", "pronto para torneio", "prontos para torneio")):
        return "ready"
    return None


def _find_horse(horses: list[dict[str, Any]], fragment: str) -> dict[str, Any] | None:
    wanted = _plain(fragment)
    if not wanted:
        return None
    exact = next((horse for horse in horses if _plain(horse.get("name")) == wanted), None)
    if exact:
        return exact
    matches = [horse for horse in horses if wanted in _plain(horse.get("name")) or _plain(horse.get("name")) in wanted]
    return matches[0] if len(matches) == 1 else None


def _age(horse: dict[str, Any], today: date) -> str:
    birth = horse.get("birthDate")
    if birth:
        born = date.fromisoformat(str(birth))
        months = (today.year - born.year) * 12 + today.month - born.month - (today.day < born.day)
        if months < 12:
            return f"{max(0, months)} " + ("mês" if months == 1 else "meses")
        years, remaining_months = divmod(months, 12)
        label = f"{years} " + ("ano" if years == 1 else "anos")
        if not remaining_months:
            return label
        return label + f" e {remaining_months} " + ("mês" if remaining_months == 1 else "meses")
    if horse.get("age") is not None:
        years = int(horse["age"])
        reference = horse.get("ageRecordedAt")
        if reference:
            recorded = date.fromisoformat(str(reference))
            years += today.year - recorded.year - ((today.month, today.day) < (recorded.month, recorded.day))
        return f"{years} " + ("ano" if years == 1 else "anos")
    return "idade não informada"


def _birth_period(query: str, today: date) -> tuple[int | None, int | None, str]:
    numeric_period = re.search(r"\b(0?[1-9]|1[0-2])(?:[/\-]|\s+)(20\d{2})\b", query)
    month = int(numeric_period.group(1)) if numeric_period else next((number for name, number in MONTHS.items() if re.search(rf"\b{name}\b", query)), None)
    year_match = re.search(r"\b(20\d{2})\b", query)
    year = int(numeric_period.group(2)) if numeric_period else int(year_match.group(1)) if year_match else None
    if any(term in query for term in ("este mes", "nesse mes", "neste mes", "mes atual", "do mes")):
        month, year = today.month, today.year
    if any(term in query for term in ("este ano", "nesse ano", "neste ano", "ano atual", "do ano")):
        year = today.year
    month_name = next((name for name, number in MONTHS.items() if number == month), None)
    if month_name and year:
        label = f"{month_name.capitalize()} de {year}"
    elif month_name:
        label = f"{month_name.capitalize()} (todos os anos)"
    elif year:
        label = str(year)
    else:
        label = "período não especificado"
    return month, year, label


def _date_br(value: str) -> str:
    parsed = date.fromisoformat(value)
    return parsed.strftime("%d/%m/%Y")


def _births_in_period(
    horses: list[dict[str, Any]], field: str, month: int | None, year: int | None
) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for horse in horses:
        value = horse.get(field)
        if not value:
            continue
        try:
            parsed = date.fromisoformat(str(value))
        except ValueError:
            continue
        if month and parsed.month != month:
            continue
        if year and parsed.year != year:
            continue
        found.append(horse)
    return sorted(found, key=lambda horse: horse.get(field) or "9999")


def _result(
    answer: str,
    matches: list[dict[str, Any]] | None = None,
    intent: str = "query",
    options: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "answer": answer,
        "matches": [horse.get("id") for horse in (matches or []) if horse.get("id")],
        "intent": intent,
        "options": options or [],
    }


def _records(count: int) -> str:
    return f"{count} registro" if count == 1 else f"{count} registros"


def _known_parent(horses: list[dict[str, Any]], query: str) -> tuple[str, str] | None:
    """Retorna nome original e normalizado quando um genitor conhecido aparece na pergunta."""
    known: dict[str, str] = {}
    for horse in horses:
        for field in ("father", "mother"):
            original = str(horse.get(field) or "").strip()
            normalized = _plain(original)
            if normalized:
                known.setdefault(normalized, original)
    mentioned = [(normalized, original) for normalized, original in known.items() if re.search(rf"\b{re.escape(normalized)}\b", query)]
    if not mentioned:
        return None
    mentioned.sort(key=lambda item: len(item[0]), reverse=True)
    normalized, original = mentioned[0]
    if any(other not in normalized for other, _ in mentioned[1:]):
        return None
    return original, normalized


def _children(
    horses: list[dict[str, Any]],
    parent: str,
    relation: str,
    stage: str | None = None,
) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for horse in horses:
        father = _plain(horse.get("father"))
        mother = _plain(horse.get("mother"))
        matches = (relation in ("father", "both") and father == parent) or (relation in ("mother", "both") and mother == parent)
        if matches and (not stage or horse.get("stage") == stage):
            found.append(horse)
    return found


def answer_question(
    horses: list[dict[str, Any]],
    question: str,
    *,
    expenses: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
    reference_date: str | None = None,
) -> dict[str, Any]:
    """Interpreta perguntas comuns sem alterar nem transmitir os dados."""
    original = str(question or "").strip()[:500]
    query = _plain(original)
    if not query:
        raise ValueError("Digite uma pergunta sobre a cocheira.")
    today = date.fromisoformat(reference_date) if reference_date else date.today()

    if is_audit_question(original):
        return answer_audit_question(horses, expenses or [], original, reference_date=today.isoformat())

    if is_finance_question(original) or (context or {}).get("type") == "finance" and query.startswith(("e ", "agora ", "somente ", "apenas ")):
        return answer_financial_question(expenses or [], horses, original, context=context, reference_date=today.isoformat())

    if not horses:
        return _result("Ainda não há cavalos cadastrados para consultar.", intent="empty")

    if "exemplo" in query:
        return _result(
            "Você pode perguntar de várias formas. Escolha um exemplo abaixo para testar:",
            intent="help",
            options=[
                {"label": "Quantos filhos?", "question": "Quantos filhos Trovão tem?"},
                {"label": "Filhos como pai", "question": "Quais são os filhos do pai Trovão?"},
                {"label": "Filhos como mãe", "question": "Quais são os filhos da mãe Estrela?"},
                {"label": "Filhos em treinamento", "question": "Quais filhos do pai Trovão estão em treinamento?"},
                {"label": "Treinos de um cavalo", "question": "Quantos treinos tem Aurora?"},
            ],
        )

    if re.search(r"\bfilh(?:o|a|os|as)\b", query):
        known_parent = _known_parent(horses, query)
        parent_match = re.search(r"filh(?:o|a|os|as) (?:do|da|de )?(?:o |a )?(?:cavalo |garanhao |egua |pai |mae )?(.+?)(?: tem| esta| estao| na etapa| em treinamento| na tropa| que|$)", query)
        if known_parent:
            label, parent = known_parent
        elif parent_match:
            label = parent_match.group(1).strip().title()
            parent = _plain(label)
        else:
            return _result(
                "De qual cavalo ou égua você quer consultar os filhos?",
                intent="clarification",
                options=[
                    {"label": "Ver exemplos", "question": "Mostre exemplos de perguntas sobre filiação"},
                ],
            )

        explicit_both = any(term in query for term in ("pai ou mae", "pai e mae", "nos dois", "qualquer filiacao", "ambos"))
        mother_only = bool(re.search(r"\b(?:egua|mae|como mae)\b", query)) and not explicit_both
        father_only = bool(re.search(r"\b(?:garanhao|pai|como pai)\b", query)) and not explicit_both
        asks_count = any(term in query.split() for term in ("quantos", "quantas", "total", "numero"))
        stage_filter = _stage_in(query)

        if not mother_only and not father_only and not explicit_both:
            action = "Contar" if asks_count else "Mostrar"
            return _result(
                f"Você quer procurar {label} em qual parte da filiação?",
                intent="clarification",
                options=[
                    {"label": "Como pai", "question": f"{action} filhos do pai {label}"},
                    {"label": "Como mãe", "question": f"{action} filhos da mãe {label}"},
                    {"label": "Pai ou mãe", "question": f"{action} filhos de {label} como pai ou mãe"},
                ],
            )

        relation = "mother" if mother_only else "father" if father_only else "both"
        found = _children(horses, parent, relation, stage_filter)
        relation_label = "como mãe" if relation == "mother" else "como pai" if relation == "father" else "como pai ou mãe"
        stage_text = f" na etapa {STAGE_NAMES[stage_filter]}" if stage_filter else ""
        if not found:
            return _result(f"Não encontrei filhos de {label} {relation_label}{stage_text}.", intent="parentage")
        if asks_count or query.startswith("contar"):
            quantity = f"{len(found)} filho cadastrado" if len(found) == 1 else f"{len(found)} filhos cadastrados"
            return _result(f"{label} tem {quantity} {relation_label}{stage_text}: {_names(found)}.", found, "parentage")
        return _result(f"Filhos de {label} {relation_label}{stage_text}: {_names(found)}.", found, "parentage")

    relation = re.search(r"(?:quem e |qual e |qual a |qual o )?(pai|mae|filiacao) (?:do|da|de) (.+)$", query)
    if relation:
        horse = _find_horse(horses, relation.group(2))
        if not horse:
            return _result("Não consegui identificar esse cavalo pelo nome.", intent="parentage")
        father = horse.get("father") or "não informado"
        mother = horse.get("mother") or "não informada"
        if relation.group(1) == "pai":
            return _result(f"O pai de {horse.get('name')} é {father}.", [horse], "parentage")
        if relation.group(1) == "mae":
            return _result(f"A mãe de {horse.get('name')} é {mother}.", [horse], "parentage")
        return _result(f"A filiação de {horse.get('name')} é {father} × {mother}.", [horse], "parentage")

    workout_horse = re.search(r"(?:quantos? treinos? (?:tem |possui )?|faltam quantos? treinos? (?:para |pro |pra )?)(.+)$", query)
    if workout_horse:
        horse = _find_horse(horses, workout_horse.group(1))
        if horse:
            workouts = int(horse.get("workouts", 0) or 0)
            if query.startswith("faltam"):
                missing = max(0, TRAINING_GOAL - workouts)
                return _result(f"Faltam {missing} treinos para {horse.get('name')} atingir a meta de {TRAINING_GOAL}.", [horse], "workouts")
            return _result(f"{horse.get('name')} tem {workouts} treinos registrados.", [horse], "workouts")

    age_match = re.search(r"(?:qual (?:e )?a idade|quantos anos (?:tem )?|idade) (?:do|da|de )?(.+)$", query)
    if age_match:
        horse = _find_horse(horses, age_match.group(1))
        if horse:
            return _result(f"{horse.get('name')} tem {_age(horse, today)}.", [horse], "age")

    location_match = re.search(
        r"(?:onde (?:esta|fica)|qual (?:e )?a localizacao (?:do|da|de)|localizacao (?:do|da|de))\s+(.+)$",
        query,
    )
    if location_match:
        horse = _find_horse(horses, location_match.group(1))
        if not horse:
            return _result("Não consegui identificar esse cavalo pelo nome.", intent="location")
        location = horse.get("location")
        if not location:
            return _result(f"A localização atual de {horse.get('name')} ainda não foi informada.", [horse], "location")
        return _result(f"{horse.get('name')} está em {location}.", [horse], "location")

    if any(term in query for term in ("80 treinos", "meta de treinos", "meta dos treinos", "pode ir para tropa", "prontos para ir")):
        found = [horse for horse in horses if horse.get("stage") == "training" and int(horse.get("workouts", 0) or 0) >= TRAINING_GOAL]
        if not found:
            return _result(f"Nenhum cavalo em treinamento atingiu {TRAINING_GOAL} treinos ainda.", intent="workouts")
        return _result(f"{len(found)} podem ser enviados para a Tropa pronta: {_names(found)}.", found, "workouts")

    if "mais treinos" in query:
        training = [horse for horse in horses if horse.get("stage") == "training"]
        if not training:
            return _result("Não há cavalos na etapa Preparação e Treinamento.", intent="workouts")
        maximum = max(int(horse.get("workouts", 0) or 0) for horse in training)
        found = [horse for horse in training if int(horse.get("workouts", 0) or 0) == maximum]
        return _result(f"{_names(found)} tem a maior contagem, com {maximum} treinos.", found, "workouts")

    birth_question = any(term in query for term in ("nascimento", "nascimentos", "nasceram", "nascidos", "nascido", "previsao de parto"))
    if birth_question:
        expected = any(term in query for term in ("previsto", "previstos", "previsao", "proximo", "proximos", "cruza"))
        actual = any(term in query for term in ("nasceram", "nascidos", "nascido", "data real"))
        month, year, period_label = _birth_period(query, today)
        if not expected and not actual:
            suffix = "" if period_label == "período não especificado" else f" em {period_label}"
            return _result(
                "Você quer consultar previsões de nascimento ou animais que já nasceram?",
                intent="clarification",
                options=[
                    {"label": "Nascimentos previstos", "question": f"Mostrar nascimentos previstos{suffix}"},
                    {"label": "Animais que nasceram", "question": f"Mostrar animais nascidos{suffix}"},
                ],
            )

        field = "expectedBirthDate" if expected else "birthDate"
        source = [horse for horse in horses if horse.get("stage") == "creation"] if expected else horses
        found = _births_in_period(source, field, month, year)
        if expected and month is None and year is None:
            found = [horse for horse in found if str(horse.get(field)) >= today.isoformat()]
            period_label = "próximas previsões"
        kind = "nascimentos previstos" if expected else "animais nascidos"
        if not found:
            return _result(f"Não encontrei {kind} em {period_label}.", intent="births")
        items = [f"{horse.get('name') or 'Nome a definir'} — {_date_br(str(horse[field]))}" for horse in found[:12]]
        count = len(found)
        summary = f"{count} nascimento previsto" if expected and count == 1 else f"{count} nascimentos previstos" if expected else f"{count} animal nascido" if count == 1 else f"{count} animais nascidos"
        return _result(f"{period_label}: {summary}. " + "; ".join(items) + ".", found[:12], "births")

    if "cada etapa" in query or "por etapa" in query:
        counts = {stage: sum(horse.get("stage") == stage for horse in horses) for stage in STAGE_NAMES}
        answer = "; ".join(f"{label}: {counts[stage]}" for stage, label in STAGE_NAMES.items())
        return _result(f"Quantidade por etapa — {answer}.", horses, "count")

    stage = _stage_in(query)
    asks_count = any(term in query.split() for term in ("quantos", "quantas", "total", "numero"))
    if stage:
        found = [horse for horse in horses if horse.get("stage") == stage]
        label = STAGE_NAMES[stage]
        if asks_count:
            return _result(f"Há {_records(len(found))} na etapa {label}.", found, "count")
        if not found:
            return _result(f"Não há registros em {label}.", intent="stage")
        return _result(f"Em {label}: {_names(found)}.", found, "stage")

    if asks_count and any(term in query for term in ("cavalo", "animal", "cadastro", "todos")):
        return _result(f"Há {_records(len(horses))} no total.", horses, "count")

    mentioned = [horse for horse in horses if _plain(horse.get("name")) and _plain(horse.get("name")) in query]
    if len(mentioned) == 1:
        horse = mentioned[0]
        stage_name = STAGE_NAMES.get(horse.get("stage"), "Etapa não informada")
        parents = f"{horse.get('father') or 'pai não informado'} × {horse.get('mother') or 'mãe não informada'}"
        extra = f" Possui {int(horse.get('workouts', 0) or 0)} treinos." if horse.get("stage") == "training" else ""
        location = f" Localização atual: {horse.get('location')}." if horse.get("location") else " Localização atual não informada."
        return _result(f"{horse.get('name')} está em {stage_name}, tem {_age(horse, today)} e sua filiação é {parents}.{location}{extra}", [horse], "details")

    return _result(
        "Não tive certeza do que você quer consultar. Escolha uma opção ou reformule a pergunta.",
        intent="clarification",
        options=[
            {"label": "Filiação", "question": "Mostre exemplos de perguntas sobre filiação"},
            {"label": "Treinos", "question": "Quais cavalos têm mais treinos?"},
            {"label": "Etapas", "question": "Quantos cavalos existem em cada etapa?"},
            {"label": "Nascimentos", "question": "Quais são os próximos nascimentos?"},
            {"label": "Localização", "question": "Onde está Aurora?"},
        ],
    )
