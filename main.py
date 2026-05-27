#!/usr/bin/env python3
"""财务助手 - 记账、预算、统计与理财持仓。"""

from datetime import date

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from db import get_conn, init_db
from services import budget as budget_svc
from services import investment as invest_svc
from services import ledger
from services import report as report_svc
from utils import (
    choose_from_list,
    current_year_month,
    prompt,
    prompt_float,
    prompt_int,
)

console = Console()


def show_header():
    console.print(
        Panel.fit(
            "[bold cyan]财务助手[/] · 记账 · 预算 · 统计 · 理财",
            border_style="cyan",
        )
    )


def menu_record_expense(conn):
    cats = ledger.list_categories(conn, "expense")
    accs = ledger.list_accounts(conn)
    cat = choose_from_list(cats, lambda c: c.name, "支出分类")
    if not cat:
        return
    acc = choose_from_list(accs, lambda a: f"{a.name} (余额 ¥{a.balance:.2f})", "账户")
    if not acc:
        return
    amount = prompt_float("金额 (元)")
    note = prompt("备注", "")
    trans_date = prompt("日期 YYYY-MM-DD", date.today().isoformat())
    tid = ledger.add_transaction(
        conn,
        amount=amount,
        ttype="expense",
        category_id=cat.id,
        account_id=acc.id,
        note=note,
        trans_date=trans_date,
    )
    console.print(f"[green]✓[/] 已记支出 ¥{amount:.2f}，流水号 #{tid}")


def menu_record_income(conn):
    cats = ledger.list_categories(conn, "income")
    accs = ledger.list_accounts(conn)
    cat = choose_from_list(cats, lambda c: c.name, "收入分类")
    if not cat:
        return
    acc = choose_from_list(accs, lambda a: f"{a.name} (余额 ¥{a.balance:.2f})", "账户")
    if not acc:
        return
    amount = prompt_float("金额 (元)")
    note = prompt("备注", "")
    trans_date = prompt("日期 YYYY-MM-DD", date.today().isoformat())
    tid = ledger.add_transaction(
        conn,
        amount=amount,
        ttype="income",
        category_id=cat.id,
        account_id=acc.id,
        note=note,
        trans_date=trans_date,
    )
    console.print(f"[green]✓[/] 已记收入 ¥{amount:.2f}，流水号 #{tid}")


def show_accounts(conn):
    accounts = ledger.list_accounts(conn)
    table = Table(title="账户余额", show_header=True, header_style="bold")
    table.add_column("ID", style="dim")
    table.add_column("名称")
    table.add_column("类型")
    table.add_column("余额", justify="right")
    for a in accounts:
        table.add_row(str(a.id), a.name, a.type, f"¥{a.balance:,.2f}")
    total = report_svc.total_assets(conn)
    table.add_row("", "[bold]合计[/]", "", f"[bold]¥{total:,.2f}[/]")
    console.print(table)


def show_recent_transactions(conn):
    ym = prompt("查看月份 YYYY-MM", current_year_month())
    txs = ledger.list_transactions(conn, year_month=ym, limit=30)
    if not txs:
        console.print("[yellow]该月暂无流水[/]")
        return
    table = Table(title=f"{ym} 最近流水", show_header=True, header_style="bold")
    table.add_column("ID", style="dim")
    table.add_column("日期")
    table.add_column("类型")
    table.add_column("分类")
    table.add_column("账户")
    table.add_column("金额", justify="right")
    table.add_column("备注")
    for t in txs:
        type_label = "[green]收入[/]" if t.type == "income" else "[red]支出[/]"
        sign = "+" if t.type == "income" else "-"
        table.add_row(
            str(t.id),
            t.date,
            type_label,
            t.category_name or "",
            t.account_name or "",
            f"{sign}¥{t.amount:,.2f}",
            t.note or "",
        )
    console.print(table)


def menu_delete_transaction(conn):
    tid = prompt_int("要删除的流水 ID")
    if ledger.delete_transaction(conn, tid):
        console.print("[green]✓[/] 已删除并回滚账户余额")
    else:
        console.print("[red]未找到该流水[/]")


def show_monthly_report(conn):
    ym = prompt("统计月份 YYYY-MM", current_year_month())
    summary = report_svc.monthly_summary(conn, ym)
    income = summary.get("income", 0)
    expense = summary.get("expense", 0)
    balance = income - expense

    console.print(Panel(
        f"收入 [green]¥{income:,.2f}[/]\n"
        f"支出 [red]¥{expense:,.2f}[/]\n"
        f"结余 [{'green' if balance >= 0 else 'red'}]¥{balance:,.2f}[/]",
        title=f"{ym} 月报",
        border_style="blue",
    ))

    breakdown = report_svc.category_breakdown(conn, ym, "expense")
    if breakdown:
        table = Table(title="支出分类占比", show_header=True)
        table.add_column("分类")
        table.add_column("金额", justify="right")
        table.add_column("占比", justify="right")
        for name, total in breakdown:
            pct = (total / expense * 100) if expense > 0 else 0
            table.add_row(name, f"¥{total:,.2f}", f"{pct:.1f}%")
        console.print(table)


def menu_set_budget(conn):
    ym = prompt("预算月份 YYYY-MM", current_year_month())
    cats = ledger.list_categories(conn, "expense")
    cat = choose_from_list(cats, lambda c: c.name, "支出分类")
    if not cat:
        return
    limit_amount = prompt_float("预算上限 (元)")
    budget_svc.set_budget(conn, ym, cat.id, limit_amount)
    console.print(f"[green]✓[/] 已设置 {cat.name} 预算 ¥{limit_amount:.2f}")


def show_budgets(conn):
    ym = prompt("查看月份 YYYY-MM", current_year_month())
    budgets = budget_svc.list_budgets_with_spent(conn, ym)
    if not budgets:
        console.print("[yellow]该月尚未设置预算[/]")
        return
    table = Table(title=f"{ym} 预算执行情况", show_header=True, header_style="bold")
    table.add_column("分类")
    table.add_column("预算", justify="right")
    table.add_column("已用", justify="right")
    table.add_column("剩余", justify="right")
    table.add_column("状态")
    for b in budgets:
        spent = b.spent or 0
        remain = b.limit_amount - spent
        if spent > b.limit_amount:
            status = "[red]超支[/]"
        elif spent >= b.limit_amount * 0.9:
            status = "[yellow]接近上限[/]"
        else:
            status = "[green]正常[/]"
        table.add_row(
            b.category_name or "",
            f"¥{b.limit_amount:,.2f}",
            f"¥{spent:,.2f}",
            f"¥{remain:,.2f}",
            status,
        )
    console.print(table)

    over = budget_svc.over_budget_items(conn, ym)
    if over:
        console.print("[bold red]超支提醒：[/]")
        for b in over:
            console.print(
                f"  · {b.category_name}: 已用 ¥{b.spent:.2f} / 预算 ¥{b.limit_amount:.2f}"
            )


def menu_add_investment(conn):
    name = prompt("标的名称")
    invest_type = prompt("类型 (基金/股票/存款等)", "基金")
    principal = prompt_float("投入本金 (元)", allow_zero=True)
    shares = prompt_float("份额/股数", allow_zero=True)
    current_price = prompt_float("当前单价 (元)", allow_zero=True)
    buy_date = prompt("买入日期 YYYY-MM-DD", date.today().isoformat())
    note = prompt("备注", "")
    iid = invest_svc.add_investment(
        conn,
        name=name,
        invest_type=invest_type,
        principal=principal,
        shares=shares,
        current_price=current_price,
        buy_date=buy_date,
        note=note,
    )
    console.print(f"[green]✓[/] 已添加持仓 #{iid}")


def show_investments(conn):
    items = invest_svc.list_investments(conn)
    if not items:
        console.print("[yellow]暂无理财持仓[/]")
        return
    table = Table(title="理财持仓", show_header=True, header_style="bold")
    table.add_column("ID", style="dim")
    table.add_column("名称")
    table.add_column("类型")
    table.add_column("本金", justify="right")
    table.add_column("市值", justify="right")
    table.add_column("盈亏", justify="right")
    table.add_column("收益率", justify="right")
    for i in items:
        profit_style = "green" if i.profit >= 0 else "red"
        table.add_row(
            str(i.id),
            i.name,
            i.invest_type,
            f"¥{i.principal:,.2f}",
            f"¥{i.market_value:,.2f}",
            f"[{profit_style}]{'+' if i.profit >= 0 else ''}¥{i.profit:,.2f}[/]",
            f"[{profit_style}]{i.profit_rate:+.2f}%[/]",
        )
    console.print(table)

    summary = invest_svc.portfolio_summary(items)
    console.print(Panel(
        f"持仓 {summary['count']} 项\n"
        f"总本金 ¥{summary['principal']:,.2f}\n"
        f"总市值 ¥{summary['market_value']:,.2f}\n"
        f"总盈亏 ¥{summary['profit']:+,.2f} ({summary['profit_rate']:+.2f}%)",
        title="投资组合汇总",
        border_style="magenta",
    ))


def menu_update_investment_price(conn):
    iid = prompt_int("持仓 ID")
    price = prompt_float("新单价 (元)", allow_zero=True)
    if invest_svc.update_price(conn, iid, price):
        console.print("[green]✓[/] 已更新现价")
    else:
        console.print("[red]未找到该持仓[/]")


def menu_add_account(conn):
    name = prompt("账户名称")
    acc_type = prompt("类型 (cash/bank/e_wallet/credit)", "bank")
    balance = prompt_float("初始余额 (元)", allow_zero=True)
    aid = ledger.add_account(conn, name, acc_type, balance)
    console.print(f"[green]✓[/] 已创建账户 #{aid}")


def menu_adjust_balance(conn):
    accs = ledger.list_accounts(conn)
    acc = choose_from_list(accs, lambda a: f"{a.name} (当前 ¥{a.balance:.2f})", "选择账户")
    if not acc:
        return
    balance = prompt_float("调整为余额 (元)", allow_zero=True)
    if ledger.adjust_account_balance(conn, acc.id, balance):
        console.print("[green]✓[/] 余额已更新")


def main():
    init_db()
    show_header()

    actions = {
        "1": ("记支出", menu_record_expense),
        "2": ("记收入", menu_record_income),
        "3": ("查看账户", show_accounts),
        "4": ("最近流水", show_recent_transactions),
        "5": ("删除流水", menu_delete_transaction),
        "6": ("月度报表", show_monthly_report),
        "7": ("设置预算", menu_set_budget),
        "8": ("预算执行", show_budgets),
        "9": ("添加持仓", menu_add_investment),
        "10": ("查看持仓", show_investments),
        "11": ("更新现价", menu_update_investment_price),
        "12": ("新建账户", menu_add_account),
        "13": ("调整余额", menu_adjust_balance),
        "0": ("退出", None),
    }

    while True:
        console.print()
        for key in sorted(actions.keys(), key=lambda x: (x == "0", x)):
            label, _ = actions[key]
            console.print(f"  [cyan]{key:>2}[/]. {label}")

        choice = input("\n请选择: ").strip()
        if choice == "0":
            console.print("[dim]再见！[/]")
            break
        action = actions.get(choice)
        if not action or not action[1]:
            console.print("[yellow]无效选项[/]")
            continue
        try:
            with get_conn() as conn:
                action[1](conn)
        except ValueError as e:
            console.print(f"[red]错误: {e}[/]")
        except Exception as e:
            console.print(f"[red]操作失败: {e}[/]")


if __name__ == "__main__":
    main()
