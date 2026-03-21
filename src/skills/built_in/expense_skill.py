"""Expense and income tracker skill with category budgets and reporting."""

from __future__ import annotations

from typing import Any

import structlog

from src.memory.engine import MemoryEngine, sanitize_fts_query
from src.skills.base_skill import BaseSkill, SkillResult

log = structlog.get_logger("assistant.skills.expenses")

_DEFAULT_CATEGORIES = [
    ("Hosting", "🖥", None),
    ("Software", "💿", None),
    ("Marketing", "📢", None),
    ("Salarios", "💰", None),
    ("Oficina", "🏢", None),
    ("Comida", "🍔", None),
    ("Transporte", "🚗", None),
    ("Educación", "📚", None),
    ("Herramientas", "🔧", None),
    ("Otros", "📦", None),
]

_EXPENSE_TABLES = """
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    currency TEXT DEFAULT 'USD',
    category TEXT NOT NULL,
    description TEXT,
    expense_type TEXT DEFAULT 'expense' CHECK(expense_type IN ('expense', 'income')),
    payment_method TEXT,
    date TEXT DEFAULT (date('now')),
    created_at TEXT DEFAULT (datetime('now')),
    project TEXT,
    is_tax_deductible INTEGER DEFAULT 0,
    receipt_path TEXT
);

CREATE TABLE IF NOT EXISTS expense_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    icon TEXT,
    budget_monthly REAL
);

CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);
CREATE INDEX IF NOT EXISTS idx_expenses_type ON expenses(expense_type);
CREATE INDEX IF NOT EXISTS idx_expenses_project ON expenses(project);
"""


def _fmt_money(amount: float, currency: str = "USD") -> str:
    """Format a monetary amount with $ sign and thousand separators."""
    if amount < 0:
        return f"-${abs(amount):,.2f} {currency}"
    return f"${amount:,.2f} {currency}"


def _parse_amount(text: str) -> float | None:
    """Parse a monetary amount string, stripping $ and commas."""
    cleaned = text.strip().lstrip("$").replace(",", "")
    try:
        value = float(cleaned)
        if value <= 0:
            return None
        return value
    except (ValueError, TypeError):
        return None


class ExpenseSkill(BaseSkill):
    """Track expenses, income, budgets, and generate financial reports."""

    def __init__(self, memory_engine: MemoryEngine | None = None) -> None:
        self._memory = memory_engine
        self._initialized = False

    @property
    def name(self) -> str:
        return "expenses"

    @property
    def description(self) -> str:
        return "Registro de gastos, ingresos, presupuestos y reportes financieros"

    @property
    def natural_patterns(self) -> dict[str, list[str]]:
        return {
            "nuevo": [
                r"(?:registra|anota|agrega|a[ñn]ade)\s+(?:un\s+)?gasto\s+(?:de\s+)?(?P<args>.+)",
                r"gast[eé]\s+(?P<args>.+)",
                r"(?:pagu[eé]|compr[eé]|pag(?:ué|ue))\s+(?P<args>.+)",
            ],
            "ingreso": [
                r"(?:registra|anota|agrega)\s+(?:un\s+)?ingreso\s+(?:de\s+)?(?P<args>.+)",
                r"(?:me\s+)?(?:pagaron|entr[oó]|cobr[eé]|recib[ií])\s+(?P<args>.+)",
            ],
            "ver": [
                r"(?:mu[eé]strame|ver|dame|c[oó]mo\s+van)\s+(?:los?\s+|mis?\s+)?(?:gastos?|finanzas?|expenses?)",
                r"(?:resumen|reporte)\s+(?:de\s+)?(?:gastos?|finanzas?)",
                r"(?:cu[aá]nto\s+(?:he\s+)?gastado|cu[aá]nto\s+llevo)",
            ],
            "hoy": [
                r"(?:gastos?|cu[aá]nto\s+gast[eé])\s+(?:de\s+)?hoy",
                r"(?:qu[eé]\s+(?:he\s+)?gastado|cu[aá]nto\s+llevo)\s+hoy",
            ],
            "balance": [
                r"(?:cu[aá]l\s+es\s+)?(?:mi\s+)?balance",
                r"(?:cu[aá]nto\s+tengo|estado\s+financiero)",
            ],
            "categorias": [
                r"(?:mu[eé]strame|ver|dame|cu[aá]les\s+son)\s+(?:las?\s+)?categor[ií]as?\s+(?:de\s+)?gastos?",
            ],
        }

    @property
    def triggers(self) -> list[str]:
        return [
            "!gasto",
            "!gastos",
            "!expense",
            "!expenses",
            "!ingreso",
            "!income",
            "!finanzas",
            "!finance",
        ]

    def _ensure_tables(self, memory: MemoryEngine) -> None:
        """Create expense tables and seed default categories if needed."""
        if self._initialized:
            return

        for statement in _split_sql(_EXPENSE_TABLES):
            memory.execute(statement)

        # Seed default categories (ignore duplicates)
        for cat_name, icon, budget in _DEFAULT_CATEGORIES:
            try:
                memory.execute(
                    "INSERT OR IGNORE INTO expense_categories (name, icon, budget_monthly) "
                    "VALUES (?, ?, ?)",
                    (cat_name, icon, budget),
                )
            except Exception:
                pass  # Already exists

        self._initialized = True
        log.info("expenses.tables_ready")

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        memory = self._memory or context.get("memory")
        if memory is None:
            return SkillResult(success=False, message="Motor de memoria no disponible.")

        self._ensure_tables(memory)

        # Detect trigger to provide context
        original_text = context.get("original_text", "").lower().strip()
        is_income_trigger = any(
            original_text.startswith(t) for t in ("!ingreso", "!income")
        )

        if not args:
            return self._summary_month(memory)

        parts = args.split(maxsplit=1)
        sub = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        dispatch: dict[str, str] = {
            "nuevo": "add_expense",
            "nueva": "add_expense",
            "new": "add_expense",
            "add": "add_expense",
            "ingreso": "add_income",
            "income": "add_income",
            "ver": "summary_month",
            "view": "summary_month",
            "hoy": "today",
            "today": "today",
            "semana": "week",
            "week": "week",
            "mes": "month",
            "month": "month",
            "categorias": "categories",
            "categories": "categories",
            "categoria": "category_cmd",
            "category": "category_cmd",
            "buscar": "search",
            "search": "search",
            "reporte": "report",
            "report": "report",
            "balance": "balance",
            "top": "top",
            "deducible": "deductible",
            "deductible": "deductible",
            "proyecto": "project_expense",
            "project": "project_expense",
            "borrar": "delete",
            "delete": "delete",
            "editar": "edit",
            "edit": "edit",
        }

        action = dispatch.get(sub)

        if action == "add_expense":
            return self._add_expense(memory, rest, expense_type="expense")
        elif action == "add_income":
            return self._add_expense(memory, rest, expense_type="income")
        elif action == "summary_month":
            return self._summary_month(memory)
        elif action == "today":
            return self._summary_today(memory)
        elif action == "week":
            return self._summary_week(memory)
        elif action == "month":
            return self._summary_month(memory, month_arg=rest)
        elif action == "categories":
            return self._list_categories(memory)
        elif action == "category_cmd":
            return self._category_command(memory, rest)
        elif action == "search":
            return self._search(memory, rest)
        elif action == "report":
            return self._report(memory, rest)
        elif action == "balance":
            return self._balance(memory)
        elif action == "top":
            return self._top_categories(memory)
        elif action == "deductible":
            return self._mark_deductible(memory, rest)
        elif action == "project_expense":
            return self._project_expense(memory, rest)
        elif action == "delete":
            return self._delete_expense(memory, rest)
        elif action == "edit":
            return self._edit_expense(memory, rest)
        else:
            # Try to parse as quick expense: <amount> <category> [description]
            if is_income_trigger:
                return self._add_expense(memory, args, expense_type="income")
            return self._add_expense(memory, args, expense_type="expense")

    # ── Add expense/income ───────────────────────────────────────────

    def _add_expense(
        self,
        memory: MemoryEngine,
        args: str,
        expense_type: str = "expense",
    ) -> SkillResult:
        if not args.strip():
            if expense_type == "income":
                return SkillResult(
                    success=False,
                    message="Uso: !ingreso <monto> [descripción]\nEjemplo: !ingreso 5000 Pago cliente XPlus",
                )
            return SkillResult(
                success=False,
                message=(
                    "Uso: !gasto <monto> <categoría> [descripción]\n"
                    "Ejemplo: !gasto 29.99 Software Licencia GitHub Copilot\n"
                    "Categorías: Hosting, Software, Marketing, Salarios, Oficina, "
                    "Comida, Transporte, Educación, Herramientas, Otros"
                ),
            )

        parts = args.split()
        amount = _parse_amount(parts[0])
        if amount is None:
            return SkillResult(
                success=False,
                message=f"Monto inválido: '{parts[0]}'. Debe ser un número positivo.",
            )

        if expense_type == "income":
            # Income: <amount> [description]
            category = "Ingreso"
            description = " ".join(parts[1:]) if len(parts) > 1 else None
        else:
            # Expense: <amount> <category> [description]
            if len(parts) < 2:
                return SkillResult(
                    success=False,
                    message="Falta la categoría. Uso: !gasto <monto> <categoría> [descripción]",
                )
            category = self._resolve_category(memory, parts[1])
            description = " ".join(parts[2:]) if len(parts) > 2 else None

        expense_id = memory.insert_returning_id(
            """
            INSERT INTO expenses (amount, category, description, expense_type)
            VALUES (?, ?, ?, ?)
            """,
            (amount, category, description, expense_type),
        )

        type_label = "Ingreso" if expense_type == "income" else "Gasto"
        log.info(
            "expenses.added",
            id=expense_id,
            type=expense_type,
            amount=amount,
            category=category,
        )

        msg = f"{type_label} #{expense_id} registrado: {_fmt_money(amount)} — {category}"
        if description:
            msg += f" ({description})"
        return SkillResult(success=True, message=msg, data={"id": expense_id})

    # ── Project expense ──────────────────────────────────────────────

    def _project_expense(self, memory: MemoryEngine, args: str) -> SkillResult:
        """!gasto proyecto <project> <amount> <category> [description]"""
        parts = args.split()
        if len(parts) < 3:
            return SkillResult(
                success=False,
                message="Uso: !gasto proyecto <nombre_proyecto> <monto> <categoría> [descripción]",
            )

        project = parts[0]
        amount = _parse_amount(parts[1])
        if amount is None:
            return SkillResult(
                success=False,
                message=f"Monto inválido: '{parts[1]}'.",
            )

        category = self._resolve_category(memory, parts[2])
        description = " ".join(parts[3:]) if len(parts) > 3 else None

        expense_id = memory.insert_returning_id(
            """
            INSERT INTO expenses (amount, category, description, expense_type, project)
            VALUES (?, ?, ?, 'expense', ?)
            """,
            (amount, category, description, project),
        )

        log.info("expenses.project_added", id=expense_id, project=project, amount=amount)
        msg = (
            f"Gasto #{expense_id} registrado: {_fmt_money(amount)} — {category}\n"
            f"Proyecto: {project}"
        )
        if description:
            msg += f"\nDescripción: {description}"
        return SkillResult(success=True, message=msg, data={"id": expense_id})

    # ── Summaries ────────────────────────────────────────────────────

    def _summary_today(self, memory: MemoryEngine) -> SkillResult:
        rows = memory.fetchall_dicts(
            """
            SELECT id, amount, category, description, expense_type, date
            FROM expenses
            WHERE date = date('now')
            ORDER BY created_at DESC
            """,
        )

        if not rows:
            return SkillResult(success=True, message="No hay movimientos registrados hoy.")

        total_exp = sum(r["amount"] for r in rows if r["expense_type"] == "expense")
        total_inc = sum(r["amount"] for r in rows if r["expense_type"] == "income")

        lines = ["Movimientos de hoy:", ""]
        for r in rows:
            icon = "🔴" if r["expense_type"] == "expense" else "🟢"
            desc = f" — {r['description']}" if r["description"] else ""
            lines.append(f"  {icon} #{r['id']}: {_fmt_money(r['amount'])} [{r['category']}]{desc}")

        lines.append("")
        if total_exp > 0:
            lines.append(f"Total gastos: {_fmt_money(total_exp)}")
        if total_inc > 0:
            lines.append(f"Total ingresos: {_fmt_money(total_inc)}")
        if total_inc > 0 and total_exp > 0:
            lines.append(f"Balance hoy: {_fmt_money(total_inc - total_exp)}")

        return SkillResult(success=True, message="\n".join(lines), data={"rows": rows})

    def _summary_week(self, memory: MemoryEngine) -> SkillResult:
        rows = memory.fetchall_dicts(
            """
            SELECT expense_type, category, SUM(amount) as total, COUNT(*) as count
            FROM expenses
            WHERE date >= date('now', '-7 days')
            GROUP BY expense_type, category
            ORDER BY expense_type, total DESC
            """,
        )

        if not rows:
            return SkillResult(success=True, message="No hay movimientos en los últimos 7 días.")

        expenses = [r for r in rows if r["expense_type"] == "expense"]
        incomes = [r for r in rows if r["expense_type"] == "income"]
        total_exp = sum(r["total"] for r in expenses)
        total_inc = sum(r["total"] for r in incomes)

        lines = ["Resumen semanal (últimos 7 días):", ""]

        if expenses:
            lines.append("Gastos por categoría:")
            for r in expenses:
                pct = (r["total"] / total_exp * 100) if total_exp > 0 else 0
                bar = self._bar(pct)
                lines.append(
                    f"  {r['category']}: {_fmt_money(r['total'])} "
                    f"({r['count']} mov.) {bar} {pct:.0f}%"
                )
            lines.append(f"\nTotal gastos: {_fmt_money(total_exp)}")

        if incomes:
            lines.append("\nIngresos:")
            for r in incomes:
                lines.append(f"  {r['category']}: {_fmt_money(r['total'])} ({r['count']} mov.)")
            lines.append(f"Total ingresos: {_fmt_money(total_inc)}")

        lines.append(f"\nBalance semanal: {_fmt_money(total_inc - total_exp)}")
        return SkillResult(success=True, message="\n".join(lines))

    def _summary_month(
        self, memory: MemoryEngine, month_arg: str = ""
    ) -> SkillResult:
        if month_arg.strip():
            # Parse month: accept "3", "03", "2026-03"
            month_str = month_arg.strip()
            if len(month_str) <= 2:
                try:
                    m = int(month_str)
                    # Use current year
                    date_filter = f"strftime('%Y-%m', date) = strftime('%Y', 'now') || '-' || printf('%02d', {m})"
                    month_label = f"mes {m}"
                except ValueError:
                    return SkillResult(success=False, message=f"Mes inválido: '{month_str}'")
            elif "-" in month_str:
                date_filter = f"strftime('%Y-%m', date) = '{month_str}'"
                month_label = month_str
            else:
                return SkillResult(
                    success=False,
                    message="Formato de mes: número (3) o año-mes (2026-03)",
                )
        else:
            date_filter = "strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"
            month_label = "este mes"

        rows = memory.fetchall_dicts(
            f"""
            SELECT expense_type, category, SUM(amount) as total, COUNT(*) as count
            FROM expenses
            WHERE {date_filter}
            GROUP BY expense_type, category
            ORDER BY expense_type, total DESC
            """,
        )

        if not rows:
            return SkillResult(success=True, message=f"No hay movimientos para {month_label}.")

        expenses = [r for r in rows if r["expense_type"] == "expense"]
        incomes = [r for r in rows if r["expense_type"] == "income"]
        total_exp = sum(r["total"] for r in expenses)
        total_inc = sum(r["total"] for r in incomes)

        lines = [f"Resumen de {month_label}:", ""]

        if expenses:
            lines.append("Gastos por categoría:")
            # Check budgets
            budgets = {
                r["name"]: r["budget_monthly"]
                for r in memory.fetchall_dicts(
                    "SELECT name, budget_monthly FROM expense_categories WHERE budget_monthly IS NOT NULL"
                )
            }
            for r in expenses:
                pct = (r["total"] / total_exp * 100) if total_exp > 0 else 0
                bar = self._bar(pct)
                budget_warn = ""
                if r["category"] in budgets and budgets[r["category"]]:
                    budget = budgets[r["category"]]
                    if r["total"] > budget:
                        budget_warn = f" ⚠️ EXCEDE presupuesto ({_fmt_money(budget)})"
                    else:
                        budget_warn = f" ({r['total']/budget*100:.0f}% del presupuesto)"
                lines.append(
                    f"  {r['category']}: {_fmt_money(r['total'])} "
                    f"({r['count']} mov.) {bar} {pct:.0f}%{budget_warn}"
                )
            lines.append(f"\nTotal gastos: {_fmt_money(total_exp)}")

        if incomes:
            lines.append("\nIngresos:")
            for r in incomes:
                lines.append(f"  {r['category']}: {_fmt_money(r['total'])} ({r['count']} mov.)")
            lines.append(f"Total ingresos: {_fmt_money(total_inc)}")

        balance = total_inc - total_exp
        emoji = "📈" if balance >= 0 else "📉"
        lines.append(f"\n{emoji} Balance: {_fmt_money(balance)}")

        return SkillResult(success=True, message="\n".join(lines))

    # ── Balance ──────────────────────────────────────────────────────

    def _balance(self, memory: MemoryEngine) -> SkillResult:
        row = memory.fetchone(
            """
            SELECT
                COALESCE(SUM(CASE WHEN expense_type='income' THEN amount ELSE 0 END), 0) as income,
                COALESCE(SUM(CASE WHEN expense_type='expense' THEN amount ELSE 0 END), 0) as expenses
            FROM expenses
            """,
        )

        if row is None:
            return SkillResult(success=True, message="No hay movimientos registrados.")

        income, expenses = row[0], row[1]
        balance = income - expenses

        # Monthly breakdown (last 3 months)
        months = memory.fetchall_dicts(
            """
            SELECT
                strftime('%Y-%m', date) as month,
                COALESCE(SUM(CASE WHEN expense_type='income' THEN amount ELSE 0 END), 0) as income,
                COALESCE(SUM(CASE WHEN expense_type='expense' THEN amount ELSE 0 END), 0) as expenses
            FROM expenses
            WHERE date >= date('now', '-3 months')
            GROUP BY strftime('%Y-%m', date)
            ORDER BY month DESC
            """,
        )

        lines = [
            "Balance general:",
            f"  Total ingresos: {_fmt_money(income)}",
            f"  Total gastos:   {_fmt_money(expenses)}",
            f"  Balance:        {_fmt_money(balance)}",
        ]

        if months:
            lines.append("\nÚltimos meses:")
            for m in months:
                bal = m["income"] - m["expenses"]
                icon = "📈" if bal >= 0 else "📉"
                lines.append(
                    f"  {m['month']}: {icon} {_fmt_money(bal)} "
                    f"(+{_fmt_money(m['income'])} / -{_fmt_money(m['expenses'])})"
                )

        return SkillResult(success=True, message="\n".join(lines))

    # ── Top categories ───────────────────────────────────────────────

    def _top_categories(self, memory: MemoryEngine) -> SkillResult:
        rows = memory.fetchall_dicts(
            """
            SELECT category, SUM(amount) as total, COUNT(*) as count
            FROM expenses
            WHERE expense_type = 'expense'
              AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            GROUP BY category
            ORDER BY total DESC
            LIMIT 5
            """,
        )

        if not rows:
            return SkillResult(success=True, message="No hay gastos este mes.")

        grand_total = sum(r["total"] for r in rows)
        lines = ["Top 5 categorías de gasto (este mes):", ""]
        for i, r in enumerate(rows, 1):
            pct = (r["total"] / grand_total * 100) if grand_total > 0 else 0
            bar = self._bar(pct)
            lines.append(
                f"  {i}. {r['category']}: {_fmt_money(r['total'])} "
                f"({r['count']} mov.) {bar} {pct:.0f}%"
            )

        lines.append(f"\nTotal: {_fmt_money(grand_total)}")
        return SkillResult(success=True, message="\n".join(lines))

    # ── Categories ───────────────────────────────────────────────────

    def _list_categories(self, memory: MemoryEngine) -> SkillResult:
        rows = memory.fetchall_dicts(
            "SELECT * FROM expense_categories ORDER BY name",
        )

        if not rows:
            return SkillResult(success=True, message="No hay categorías definidas.")

        lines = ["Categorías de gastos:", ""]
        for r in rows:
            icon = r["icon"] or "•"
            budget_str = (
                f" — Presupuesto: {_fmt_money(r['budget_monthly'])}/mes"
                if r["budget_monthly"]
                else ""
            )

            # Current month spending for this category
            spent_row = memory.fetchone(
                """
                SELECT COALESCE(SUM(amount), 0) FROM expenses
                WHERE category = ? AND expense_type = 'expense'
                  AND strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
                """,
                (r["name"],),
            )
            spent = spent_row[0] if spent_row else 0

            spent_str = f" (gastado: {_fmt_money(spent)})" if spent > 0 else ""
            lines.append(f"  {icon} {r['name']}{budget_str}{spent_str}")

        return SkillResult(success=True, message="\n".join(lines))

    def _category_command(self, memory: MemoryEngine, args: str) -> SkillResult:
        parts = args.split()
        if not parts:
            return SkillResult(
                success=False,
                message="Uso: !gasto categoria nueva <nombre> [presupuesto_mensual]",
            )

        sub = parts[0].lower()
        if sub in ("nueva", "new", "crear", "create"):
            if len(parts) < 2:
                return SkillResult(
                    success=False,
                    message="Uso: !gasto categoria nueva <nombre> [presupuesto_mensual]",
                )
            cat_name = parts[1]
            budget = None
            if len(parts) > 2:
                budget = _parse_amount(parts[2])

            try:
                memory.execute(
                    "INSERT INTO expense_categories (name, budget_monthly) VALUES (?, ?)",
                    (cat_name, budget),
                )
            except Exception:
                return SkillResult(
                    success=False,
                    message=f"La categoría '{cat_name}' ya existe.",
                )

            msg = f"Categoría '{cat_name}' creada."
            if budget:
                msg += f" Presupuesto mensual: {_fmt_money(budget)}"
            log.info("expenses.category_created", name=cat_name, budget=budget)
            return SkillResult(success=True, message=msg)

        elif sub in ("presupuesto", "budget"):
            if len(parts) < 3:
                return SkillResult(
                    success=False,
                    message="Uso: !gasto categoria presupuesto <nombre> <monto>",
                )
            cat_name = self._resolve_category(memory, parts[1])
            budget = _parse_amount(parts[2])
            if budget is None:
                return SkillResult(success=False, message=f"Monto inválido: '{parts[2]}'")

            memory.execute(
                "UPDATE expense_categories SET budget_monthly = ? WHERE name = ?",
                (budget, cat_name),
            )
            return SkillResult(
                success=True,
                message=f"Presupuesto de '{cat_name}' actualizado a {_fmt_money(budget)}/mes.",
            )

        return SkillResult(
            success=False,
            message="Subcomandos: nueva, presupuesto",
        )

    # ── Search ───────────────────────────────────────────────────────

    def _search(self, memory: MemoryEngine, query: str) -> SkillResult:
        if not query.strip():
            return SkillResult(success=False, message="Uso: !gasto buscar <término>")

        # Search in description and category
        search_term = f"%{query}%"
        rows = memory.fetchall_dicts(
            """
            SELECT id, amount, category, description, expense_type, date, project
            FROM expenses
            WHERE description LIKE ? OR category LIKE ? OR project LIKE ?
            ORDER BY date DESC
            LIMIT 20
            """,
            (search_term, search_term, search_term),
        )

        if not rows:
            return SkillResult(success=True, message=f"No se encontraron resultados para '{query}'.")

        total = sum(r["amount"] for r in rows)
        lines = [f"Resultados para '{query}' ({len(rows)} encontrados):", ""]
        for r in rows:
            icon = "🔴" if r["expense_type"] == "expense" else "🟢"
            desc = f" — {r['description']}" if r["description"] else ""
            proj = f" 📁{r['project']}" if r["project"] else ""
            lines.append(
                f"  {icon} #{r['id']} [{r['date']}]: {_fmt_money(r['amount'])} "
                f"[{r['category']}]{desc}{proj}"
            )

        lines.append(f"\nTotal: {_fmt_money(total)}")
        return SkillResult(success=True, message="\n".join(lines), data={"rows": rows})

    # ── Report ───────────────────────────────────────────────────────

    def _report(self, memory: MemoryEngine, month_arg: str = "") -> SkillResult:
        if month_arg.strip():
            month_str = month_arg.strip()
            if len(month_str) <= 2:
                try:
                    m = int(month_str)
                    date_filter = f"strftime('%Y-%m', date) = strftime('%Y', 'now') || '-' || printf('%02d', {m})"
                    month_label = f"mes {m}"
                except ValueError:
                    return SkillResult(success=False, message=f"Mes inválido: '{month_str}'")
            elif "-" in month_str:
                date_filter = f"strftime('%Y-%m', date) = '{month_str}'"
                month_label = month_str
            else:
                return SkillResult(success=False, message="Formato: número (3) o año-mes (2026-03)")
        else:
            date_filter = "strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"
            month_label = "este mes"

        # Category breakdown
        cat_rows = memory.fetchall_dicts(
            f"""
            SELECT category, expense_type, SUM(amount) as total, COUNT(*) as count,
                   AVG(amount) as avg_amount, MIN(amount) as min_amount, MAX(amount) as max_amount
            FROM expenses
            WHERE {date_filter}
            GROUP BY category, expense_type
            ORDER BY expense_type, total DESC
            """,
        )

        # Daily totals
        daily_rows = memory.fetchall_dicts(
            f"""
            SELECT date, expense_type, SUM(amount) as total
            FROM expenses
            WHERE {date_filter}
            GROUP BY date, expense_type
            ORDER BY date
            """,
        )

        # Top individual expenses
        top_expenses = memory.fetchall_dicts(
            f"""
            SELECT id, amount, category, description, date
            FROM expenses
            WHERE {date_filter} AND expense_type = 'expense'
            ORDER BY amount DESC
            LIMIT 5
            """,
        )

        # Tax deductible total
        deductible_row = memory.fetchone(
            f"""
            SELECT COALESCE(SUM(amount), 0)
            FROM expenses
            WHERE {date_filter} AND is_tax_deductible = 1 AND expense_type = 'expense'
            """,
        )
        deductible_total = deductible_row[0] if deductible_row else 0

        # Project breakdown
        project_rows = memory.fetchall_dicts(
            f"""
            SELECT project, SUM(amount) as total, COUNT(*) as count
            FROM expenses
            WHERE {date_filter} AND project IS NOT NULL AND expense_type = 'expense'
            GROUP BY project
            ORDER BY total DESC
            """,
        )

        if not cat_rows and not daily_rows:
            return SkillResult(success=True, message=f"No hay datos para el reporte de {month_label}.")

        expenses = [r for r in cat_rows if r["expense_type"] == "expense"]
        incomes = [r for r in cat_rows if r["expense_type"] == "income"]
        total_exp = sum(r["total"] for r in expenses)
        total_inc = sum(r["total"] for r in incomes)
        balance = total_inc - total_exp

        lines = [
            f"{'=' * 40}",
            f"  REPORTE FINANCIERO — {month_label.upper()}",
            f"{'=' * 40}",
            "",
            f"  Ingresos totales:  {_fmt_money(total_inc)}",
            f"  Gastos totales:    {_fmt_money(total_exp)}",
            f"  Balance:           {_fmt_money(balance)}",
        ]

        if deductible_total > 0:
            lines.append(f"  Deducible (tax):   {_fmt_money(deductible_total)}")

        # Category breakdown
        if expenses:
            lines.extend(["", f"{'-' * 40}", "  GASTOS POR CATEGORÍA", f"{'-' * 40}"])
            for r in expenses:
                pct = (r["total"] / total_exp * 100) if total_exp > 0 else 0
                bar = self._bar(pct, width=15)
                lines.append(f"  {r['category']:<15} {_fmt_money(r['total']):>14} {bar} {pct:>4.0f}%")
                lines.append(
                    f"    {r['count']} mov. | Prom: {_fmt_money(r['avg_amount'])} | "
                    f"Min: {_fmt_money(r['min_amount'])} | Max: {_fmt_money(r['max_amount'])}"
                )

        if incomes:
            lines.extend(["", f"{'-' * 40}", "  INGRESOS", f"{'-' * 40}"])
            for r in incomes:
                lines.append(f"  {r['category']:<15} {_fmt_money(r['total']):>14} ({r['count']} mov.)")

        # Top expenses
        if top_expenses:
            lines.extend(["", f"{'-' * 40}", "  TOP 5 GASTOS INDIVIDUALES", f"{'-' * 40}"])
            for i, r in enumerate(top_expenses, 1):
                desc = r["description"] or "(sin descripción)"
                lines.append(
                    f"  {i}. {_fmt_money(r['amount'])} [{r['category']}] — {desc} ({r['date']})"
                )

        # Project breakdown
        if project_rows:
            lines.extend(["", f"{'-' * 40}", "  GASTOS POR PROYECTO", f"{'-' * 40}"])
            for r in project_rows:
                lines.append(f"  📁 {r['project']}: {_fmt_money(r['total'])} ({r['count']} mov.)")

        # Daily chart
        if daily_rows:
            lines.extend(["", f"{'-' * 40}", "  ACTIVIDAD DIARIA (gastos)", f"{'-' * 40}"])
            daily_expenses = [r for r in daily_rows if r["expense_type"] == "expense"]
            if daily_expenses:
                max_daily = max(r["total"] for r in daily_expenses)
                for r in daily_expenses:
                    bar_len = int((r["total"] / max_daily) * 20) if max_daily > 0 else 0
                    bar = "█" * bar_len
                    lines.append(f"  {r['date'][-5:]} {bar} {_fmt_money(r['total'])}")

        lines.extend(["", f"{'=' * 40}"])
        return SkillResult(success=True, message="\n".join(lines))

    # ── Mark deductible ──────────────────────────────────────────────

    def _mark_deductible(self, memory: MemoryEngine, args: str) -> SkillResult:
        expense_id = self._parse_id(args)
        if expense_id is None:
            return SkillResult(success=False, message="Uso: !gasto deducible <id>")

        row = memory.fetchone(
            "SELECT id, amount, category, is_tax_deductible FROM expenses WHERE id = ?",
            (expense_id,),
        )
        if row is None:
            return SkillResult(success=False, message=f"Gasto #{expense_id} no encontrado.")

        # Toggle deductible status
        new_status = 0 if row[3] else 1
        memory.execute(
            "UPDATE expenses SET is_tax_deductible = ? WHERE id = ?",
            (new_status, expense_id),
        )

        status_text = "marcado como deducible" if new_status else "desmarcado como deducible"
        log.info("expenses.deductible_toggled", id=expense_id, deductible=bool(new_status))
        return SkillResult(
            success=True,
            message=f"Gasto #{expense_id} ({_fmt_money(row[1])} — {row[2]}) {status_text}.",
        )

    # ── Delete ───────────────────────────────────────────────────────

    def _delete_expense(self, memory: MemoryEngine, args: str) -> SkillResult:
        expense_id = self._parse_id(args)
        if expense_id is None:
            return SkillResult(success=False, message="Uso: !gasto borrar <id>")

        row = memory.fetchone(
            "SELECT id, amount, category, expense_type FROM expenses WHERE id = ?",
            (expense_id,),
        )
        if row is None:
            return SkillResult(success=False, message=f"Registro #{expense_id} no encontrado.")

        memory.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        type_label = "Ingreso" if row[3] == "income" else "Gasto"
        log.info("expenses.deleted", id=expense_id)
        return SkillResult(
            success=True,
            message=f"{type_label} #{expense_id} eliminado: {_fmt_money(row[1])} — {row[2]}",
        )

    # ── Edit ─────────────────────────────────────────────────────────

    def _edit_expense(self, memory: MemoryEngine, args: str) -> SkillResult:
        """Edit an expense field: !gasto editar <id> <field> <value>"""
        parts = args.split(maxsplit=2)
        if len(parts) < 3:
            return SkillResult(
                success=False,
                message=(
                    "Uso: !gasto editar <id> <campo> <valor>\n"
                    "Campos: monto, categoria, descripcion, metodo, proyecto"
                ),
            )

        expense_id = self._parse_id(parts[0])
        if expense_id is None:
            return SkillResult(success=False, message=f"ID inválido: '{parts[0]}'")

        row = memory.fetchone("SELECT id FROM expenses WHERE id = ?", (expense_id,))
        if row is None:
            return SkillResult(success=False, message=f"Registro #{expense_id} no encontrado.")

        field_map: dict[str, str] = {
            "monto": "amount",
            "amount": "amount",
            "categoria": "category",
            "category": "category",
            "descripcion": "description",
            "description": "description",
            "metodo": "payment_method",
            "method": "payment_method",
            "proyecto": "project",
            "project": "project",
        }

        field_name = parts[1].lower()
        db_field = field_map.get(field_name)
        if db_field is None:
            return SkillResult(
                success=False,
                message=f"Campo desconocido: '{field_name}'. Usa: monto, categoria, descripcion, metodo, proyecto",
            )

        value: Any = parts[2]
        if db_field == "amount":
            value = _parse_amount(parts[2])
            if value is None:
                return SkillResult(success=False, message=f"Monto inválido: '{parts[2]}'")
        elif db_field == "category":
            value = self._resolve_category(memory, parts[2])

        memory.execute(
            f"UPDATE expenses SET {db_field} = ? WHERE id = ?",
            (value, expense_id),
        )

        log.info("expenses.edited", id=expense_id, field=db_field)
        return SkillResult(
            success=True,
            message=f"Registro #{expense_id}: {field_name} actualizado a '{value}'.",
        )

    # ── Helpers ──────────────────────────────────────────────────────

    def _resolve_category(self, memory: MemoryEngine, name: str) -> str:
        """Resolve category name with case-insensitive match, fallback to input."""
        row = memory.fetchone(
            "SELECT name FROM expense_categories WHERE LOWER(name) = LOWER(?)",
            (name,),
        )
        if row:
            return row[0]

        # Partial match
        row = memory.fetchone(
            "SELECT name FROM expense_categories WHERE LOWER(name) LIKE LOWER(?) LIMIT 1",
            (f"{name}%",),
        )
        if row:
            return row[0]

        # Return as-is (will create implicitly)
        return name

    @staticmethod
    def _bar(percentage: float, width: int = 10) -> str:
        """Generate a text-based progress bar."""
        filled = int(percentage / 100 * width)
        filled = min(filled, width)
        return "█" * filled + "░" * (width - filled)

    @staticmethod
    def _parse_id(text: str) -> int | None:
        text = text.strip().lstrip("#")
        try:
            return int(text)
        except (ValueError, TypeError):
            return None


def _split_sql(sql_block: str) -> list[str]:
    """Split a SQL block into individual statements."""
    statements: list[str] = []
    current: list[str] = []
    for line in sql_block.strip().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(current))
            current = []
    if current:
        joined = "\n".join(current).strip()
        if joined:
            statements.append(joined)
    return statements
