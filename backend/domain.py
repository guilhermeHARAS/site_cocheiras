"""Regras de domínio e migração compatível da Cocheira RADAMÉS."""
from __future__ import annotations

import copy
import re
import uuid
from datetime import date, datetime
from typing import Any, Callable

SCHEMA_VERSION = 8
TRAINING_GOAL = 80
STAGES = ("creation", "foals", "training", "ready")
STAGE_LABELS = {
    "creation": "Reprodução",
    "foals": "Potros e Desenvolvimento",
    "training": "Preparação e Treinamento",
    "ready": "Tropa pronta",
}
TRANSITIONS = {
    "creation": "foals",
    "foals": "training",
    "training": "ready",
}
REVERSE_TRANSITIONS = {
    "training": "foals",
    "ready": "training",
}
MAX_MUTATIONS = 600
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def today_iso() -> str:
    return date.today().isoformat()


def _valid_iso_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if not ISO_DATE_RE.match(text):
        raise ValueError("Informe uma data válida.")
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("Informe uma data válida.") from exc
    return text


def _birth_date(value: Any, today: str) -> str | None:
    parsed = _valid_iso_date(value)
    if parsed and parsed > today:
        raise ValueError("A data de nascimento não pode estar no futuro.")
    return parsed


def _bounded_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _integer(value: Any, *, minimum: int = 0, maximum: int = 10_000) -> int:
    if value in (None, ""):
        return minimum
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError) as exc:
        raise ValueError("Informe um número válido.") from exc


def empty_state() -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "accounts": [],
        "sessions": {},
        "horses": [],
        "expenses": [],
        "processedMutations": {},
    }


def normalize_state(
    source: Any,
    *,
    reference_date: str | None = None,
    legacy_owner_email: str | None = None,
) -> dict[str, Any]:
    """Migra o estado antigo de forma determinística e idempotente."""
    current = copy.deepcopy(source) if isinstance(source, dict) else {}
    reference = reference_date or today_iso()
    legacy_account = current.pop("account", None)
    if not isinstance(current.get("accounts"), list):
        current["accounts"] = [legacy_account] if legacy_account else []
    elif legacy_account and legacy_account not in current["accounts"]:
        current["accounts"].append(legacy_account)
    if not isinstance(current.get("sessions"), dict):
        current["sessions"] = {}
    if not isinstance(current.get("processedMutations"), dict):
        current["processedMutations"] = {}

    accounts = [account for account in current["accounts"] if isinstance(account, dict)]
    for account in accounts:
        account["email"] = _bounded_text(account.get("email"), 254).lower()
        account["firstName"] = _bounded_text(account.get("firstName"), 60)
        account["lastName"] = _bounded_text(account.get("lastName"), 60)
        account["id"] = _bounded_text(account.get("id"), 64) or uuid.uuid4().hex
        account["workspaceId"] = _bounded_text(account.get("workspaceId"), 64) or uuid.uuid4().hex
    current["accounts"] = accounts

    legacy_owner = None
    wanted = str(legacy_owner_email or "").strip().lower()
    if wanted:
        legacy_owner = next((account for account in accounts if account.get("email") == wanted), None)
        if not legacy_owner:
            matches = [account for account in accounts if str(account.get("email") or "").startswith(wanted)]
            legacy_owner = matches[0] if len(matches) == 1 else None
    if not legacy_owner and len(accounts) == 1:
        legacy_owner = accounts[0]
    if not legacy_owner and accounts:
        # Compatibilidade com o primeiro protótipo: a primeira conta criada era a administradora.
        legacy_owner = accounts[0]
    legacy_workspace = legacy_owner.get("workspaceId") if legacy_owner else None

    horses = current.get("horses") if isinstance(current.get("horses"), list) else []
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for legacy in horses:
        if not isinstance(legacy, dict):
            continue
        horse = copy.deepcopy(legacy)
        horse_id = _bounded_text(horse.get("id"), 64) or uuid.uuid4().hex
        if horse_id in seen_ids:
            # Apenas registros sem identificador permanente recebem um novo ID.
            horse_id = uuid.uuid4().hex
        seen_ids.add(horse_id)
        horse["id"] = horse_id
        horse["workspaceId"] = _bounded_text(horse.get("workspaceId"), 64) or legacy_workspace
        stage = horse.get("stage")
        horse["stage"] = stage if stage in STAGES else "training"
        horse["name"] = _bounded_text(horse.get("name"), 80)
        horse["father"] = _bounded_text(horse.get("father"), 80)
        horse["mother"] = _bounded_text(horse.get("mother"), 80)
        horse["breed"] = _bounded_text(horse.get("breed"), 80)
        horse["sex"] = _bounded_text(horse.get("sex"), 20)
        horse["owner"] = _bounded_text(horse.get("owner"), 100)
        horse["location"] = _bounded_text(horse.get("location"), 120)
        horse["notes"] = _bounded_text(horse.get("notes"), 600)
        # Fotos individuais foram descontinuadas. A migração para o esquema 8
        # limpa somente esse campo; o estado anterior é salvo pela camada de
        # persistência antes da atualização do banco.
        horse["photo"] = ""
        horse["workouts"] = _integer(horse.get("workouts"), maximum=1_000_000)
        horse["lastWorkout"] = _valid_iso_date(horse.get("lastWorkout"))
        horse["birthDate"] = _valid_iso_date(horse.get("birthDate"))
        horse["expectedBirthDate"] = _valid_iso_date(horse.get("expectedBirthDate"))
        horse["originalExpectedBirthDate"] = _valid_iso_date(
            horse.get("originalExpectedBirthDate") or horse.get("expectedBirthDate")
        )
        age_value = horse.get("age")
        horse["age"] = None if age_value in (None, "") else _integer(age_value, maximum=60)
        if horse["birthDate"]:
            horse["ageApproximate"] = False
            horse["ageRecordedAt"] = None
        elif horse["age"] is not None:
            horse["ageApproximate"] = True
            horse["ageRecordedAt"] = _valid_iso_date(horse.get("ageRecordedAt")) or reference
        else:
            horse["ageApproximate"] = False
            horse["ageRecordedAt"] = None
        if not isinstance(horse.get("stageHistory"), list):
            horse["stageHistory"] = []
        if not horse.get("createdAt"):
            horse["createdAt"] = reference
        horse["updatedAt"] = horse.get("updatedAt") or horse["createdAt"]
        normalized.append(horse)

    current["horses"] = normalized
    expenses = current.get("expenses") if isinstance(current.get("expenses"), list) else []
    normalized_expenses: list[dict[str, Any]] = []
    seen_expense_ids: set[str] = set()
    expense_categories = {"food", "veterinary", "farrier", "training", "transport", "medicine", "fees", "other"}
    for legacy in expenses:
        if not isinstance(legacy, dict):
            continue
        expense = copy.deepcopy(legacy)
        expense_id = _bounded_text(expense.get("id"), 64) or uuid.uuid4().hex
        if expense_id in seen_expense_ids:
            expense_id = uuid.uuid4().hex
        seen_expense_ids.add(expense_id)
        expense["id"] = expense_id
        expense["workspaceId"] = _bounded_text(expense.get("workspaceId"), 64) or legacy_workspace
        expense["amountCents"] = _integer(expense.get("amountCents"), minimum=0, maximum=1_000_000_000)
        expense["date"] = _valid_iso_date(expense.get("date")) or reference
        category = _bounded_text(expense.get("category"), 30)
        expense["category"] = category if category in expense_categories else "other"
        expense["scope"] = "horse" if expense.get("scope") == "horse" and expense.get("horseId") else "general"
        expense["horseId"] = _bounded_text(expense.get("horseId"), 64) if expense["scope"] == "horse" else ""
        expense["description"] = _bounded_text(expense.get("description"), 180)
        expense["recurring"] = bool(expense.get("recurring", False))
        recurrence_day = _integer(expense.get("recurrenceDay"), minimum=1, maximum=31)
        expense["recurrenceDay"] = recurrence_day if expense["recurring"] else None
        expense["createdAt"] = expense.get("createdAt") or reference
        expense["updatedAt"] = expense.get("updatedAt") or expense["createdAt"]
        normalized_expenses.append(expense)
    current["expenses"] = normalized_expenses
    current["schemaVersion"] = SCHEMA_VERSION
    return current


def validate_horse(
    payload: dict[str, Any],
    *,
    existing: dict[str, Any] | None = None,
    stage: str | None = None,
    reference_date: str | None = None,
) -> dict[str, Any]:
    """Valida cadastro/edição preservando campos históricos e legados."""
    today = reference_date or today_iso()
    current = copy.deepcopy(existing) if existing else {}
    selected_stage = stage or payload.get("stage") or current.get("stage") or "training"
    if selected_stage not in STAGES:
        raise ValueError("Etapa inválida.")

    name = _bounded_text(payload.get("name", current.get("name")), 80)
    father = _bounded_text(payload.get("father", current.get("father")), 80)
    mother = _bounded_text(payload.get("mother", current.get("mother")), 80)
    if selected_stage == "creation":
        if not father or not mother:
            raise ValueError("Informe o nome do pai e da mãe.")
        expected = _valid_iso_date(payload.get("expectedBirthDate", current.get("expectedBirthDate")))
    else:
        expected = _valid_iso_date(payload.get("expectedBirthDate", current.get("expectedBirthDate")))
        if not name:
            raise ValueError("Informe o nome do cavalo.")

    # Fotos individuais foram descontinuadas e não podem voltar por edições ou
    # requisições antigas do navegador.
    photo = ""

    birth_date = _birth_date(payload.get("birthDate", current.get("birthDate")), today)
    raw_age = payload.get("age", current.get("age"))
    age = None if raw_age in (None, "") else _integer(raw_age, maximum=60)
    if birth_date:
        age_approximate = False
        age_recorded_at = None
    elif age is not None:
        age_approximate = True
        previous_age = current.get("age")
        previous_reference = current.get("ageRecordedAt")
        age_recorded_at = previous_reference if previous_age == age and previous_reference else today
    else:
        age_approximate = False
        age_recorded_at = None

    workouts = _integer(payload.get("workouts", current.get("workouts", 0)), maximum=1_000_000)
    result = current
    result.update({
        "id": current.get("id") or uuid.uuid4().hex,
        "stage": selected_stage,
        "name": name,
        "father": father,
        "mother": mother,
        "expectedBirthDate": expected,
        "originalExpectedBirthDate": current.get("originalExpectedBirthDate") or expected,
        "birthDate": birth_date,
        "age": age,
        "ageApproximate": age_approximate,
        "ageRecordedAt": age_recorded_at,
        "photo": photo,
        "breed": _bounded_text(payload.get("breed", current.get("breed")), 80),
        "sex": _bounded_text(payload.get("sex", current.get("sex")), 20),
        "owner": _bounded_text(payload.get("owner", current.get("owner")), 100),
        "location": _bounded_text(payload.get("location", current.get("location")), 120),
        "notes": _bounded_text(payload.get("notes", current.get("notes")), 600),
        "workouts": workouts,
        "lastWorkout": _valid_iso_date(current.get("lastWorkout")),
        "stageHistory": current.get("stageHistory") if isinstance(current.get("stageHistory"), list) else [],
        "createdAt": current.get("createdAt") or today,
        "updatedAt": today,
    })
    return result


def transition_horse(
    horse: dict[str, Any],
    target: str,
    *,
    payload: dict[str, Any] | None = None,
    reference_date: str | None = None,
) -> dict[str, Any]:
    today = reference_date or today_iso()
    data = payload or {}
    source = horse.get("stage") or "training"
    forward = TRANSITIONS.get(source) == target
    backward = REVERSE_TRANSITIONS.get(source) == target
    if not forward and not backward:
        if source == target:
            return horse
        raise ValueError("Essa mudança de etapa não é permitida.")
    if forward and source == "training" and int(horse.get("workouts", 0)) < TRAINING_GOAL:
        raise ValueError(f"O cavalo precisa ter pelo menos {TRAINING_GOAL} treinos.")
    if source == "creation":
        actual = _birth_date(data.get("birthDate"), today)
        if not actual:
            raise ValueError("Informe a data real de nascimento.")
        horse["birthDate"] = actual
        if "name" in data:
            horse["name"] = _bounded_text(data.get("name"), 80)
        horse["age"] = None
        horse["ageApproximate"] = False
        horse["ageRecordedAt"] = None
    horse["stage"] = target
    horse["workouts"] = int(horse.get("workouts", 0) or 0)
    horse["updatedAt"] = today
    horse.setdefault("stageHistory", []).append({
        "from": source,
        "to": target,
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "direction": "backward" if backward else "forward",
        "expectedBirthDate": horse.get("expectedBirthDate") if source == "creation" else None,
    })
    return horse


def change_workout(horse: dict[str, Any], delta: int, *, reference_date: str | None = None) -> dict[str, Any]:
    if horse.get("stage") != "training":
        raise ValueError("Treinos só podem ser alterados na etapa Preparação e Treinamento.")
    current = int(horse.get("workouts", 0) or 0)
    horse["workouts"] = max(0, current + delta)
    horse["lastWorkout"] = (reference_date or today_iso()) if delta > 0 else (None if horse["workouts"] == 0 else horse.get("lastWorkout"))
    horse["updatedAt"] = reference_date or today_iso()
    return horse


def apply_once(
    state: dict[str, Any],
    mutation_id: str | None,
    operation: Callable[[], Any],
) -> Any:
    """Impede que o mesmo clique seja aplicado duas vezes."""
    key = _bounded_text(mutation_id, 100)
    processed = state.setdefault("processedMutations", {})
    if key and key in processed:
        return copy.deepcopy(processed[key]["result"])
    result = operation()
    if key:
        processed[key] = {"at": datetime.now().astimezone().isoformat(timespec="seconds"), "result": copy.deepcopy(result)}
        while len(processed) > MAX_MUTATIONS:
            processed.pop(next(iter(processed)))
    return result
