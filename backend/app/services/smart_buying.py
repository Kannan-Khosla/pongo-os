"""Planning snapshot contract and validated draft exports; no operational writes."""

import csv
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from io import StringIO
import json
from pathlib import Path

from fastapi import HTTPException

from app.schemas.smart_buying import SmartBuyingExportRequest


def load_smart_buying_snapshot() -> dict:
    # The frontend and backend intentionally share one versioned planning snapshot.
    path = Path(__file__).resolve().parents[3] / "frontend/src/smartBuyingData.json"
    return json.loads(path.read_text(encoding="utf-8"))


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def export_purchase_draft(payload: SmartBuyingExportRequest) -> str:
    data = load_smart_buying_snapshot()
    suppliers = {row["id"]: row for row in data["suppliers"]}
    products = {row["id"]: row for row in data["products"]}
    deals = {row["id"]: row for row in data["deals"]}

    def require(condition: bool, message: str) -> None:
        if not condition:
            raise HTTPException(status_code=422, detail=message)

    require(payload.supplier_id in suppliers, "Select a supplier from the Smart Buying dataset.")
    require(payload.as_of.isoformat() == data["asOf"], "The draft date must match the current planning snapshot.")
    supplier = suppliers[payload.supplier_id]
    for line in payload.lines:
        product = products.get(line.product_id)
        require(product is not None and product["supplierId"] == payload.supplier_id, "A draft line does not belong to the selected supplier.")
        require(line.units == line.cases * product["casePack"], f"Case quantity does not match sellable units for {product['sku']}.")
        require(line.units >= product["moq"], f"Quantity is below the supplier minimum for {product['sku']}.")
        require(line.unit_cost == money(product["cost"]), f"Unit cost no longer matches the offer for {product['sku']}.")

    gross = sum((money(line.unit_cost * line.units) for line in payload.lines), Decimal(0))
    rows = []
    for line in payload.lines:
        product = products[line.product_id]
        deal = deals.get(product.get("dealId"))
        discount = Decimal(0)
        if deal and (
            deal["supplierId"] == payload.supplier_id
            and line.product_id in deal["productIds"]
            and date.fromisoformat(deal["start"]) <= payload.as_of <= date.fromisoformat(deal["expiry"])
            and line.units >= deal["minUnits"]
            and gross >= money(deal["minSpend"])
        ):
            discount = Decimal(str(deal["discount"]))
            if deal["type"] == "buy_x_get_y":
                free_cases = (line.cases // (deal["buyCases"] + deal["freeCases"])) * deal["freeCases"]
                discount = Decimal(free_cases) / line.cases
        subtotal = money(line.unit_cost * line.units)
        savings = money(subtotal * discount)
        net = subtotal - savings
        effective_cost = (net / line.units).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        retail = money(Decimal(str(product["retail"])) * line.units)
        require(abs(line.discount - discount) <= Decimal("0.000000000001"), f"The promotion threshold or discount does not match {product['sku']}.")
        require(abs(line.effective_cost - effective_cost) <= Decimal("0.000001"), f"Effective unit cost does not reconcile for {product['sku']}.")
        require(line.line_total == net and line.retail_value == retail, f"Draft totals do not reconcile for {product['sku']}.")
        rows.append([
            "Product", product["sku"], product["name"], line.cases, line.units,
            f"{line.unit_cost:.2f}", f"{discount * 100:.2f}%", f"{effective_cost:.6f}",
            f"{net:.2f}", f"{retail:.2f}", f"{retail - net:.2f}",
        ])

    net = sum((line.line_total for line in payload.lines), Decimal(0))
    freight = Decimal(0) if net >= money(supplier["freeFreight"]) else money(supplier["freight"])
    tax = money((net + freight) * Decimal(str(data["taxRate"])))
    require(payload.freight == freight, "Freight does not match the supplier's net merchandise threshold.")
    require(payload.tax == tax, "Tax does not reconcile with merchandise and freight.")
    retail = sum((line.retail_value for line in payload.lines), Decimal(0))
    profit = retail - net - freight

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Record", "SKU", "Description", "Cases", "Units", "Unit Cost CAD", "Deal Discount", "Effective Unit Cost CAD", "Amount CAD", "Retail Value CAD", "Projected Gross Profit CAD"])
    for label, value in (
        ("Status", "Planning draft - not sent to supplier"),
        ("PO Number", payload.po_number),
        ("Supplier", supplier["name"]),
        ("Created Date", payload.as_of.isoformat()),
        ("Expected Delivery", payload.expected_delivery.isoformat()),
    ):
        writer.writerow([label, "", value, *([""] * 8)])
    writer.writerows(rows)
    for label, amount in (
        ("Subtotal before discounts", gross), ("Discounts / potential supplier savings", gross - net),
        ("Merchandise after discounts", net), ("Freight", freight), ("GST 5%", tax),
        ("Final purchase cost", net + freight + tax), ("Suggested retail value", retail),
        ("Projected gross profit after freight, before GST", profit),
    ):
        writer.writerow([label, *([""] * 7), f"{amount:.2f}", "", ""])
    writer.writerow(["Total units", "", "", "", sum(line.units for line in payload.lines), *([""] * 6)])
    margin = profit / retail * 100 if retail else Decimal(0)
    writer.writerow(["Projected gross margin", "", f"{margin:.2f}%", *([""] * 8)])
    writer.writerow(["Basis", "", "Synthetic offers; CAD; recoverable GST excluded from gross profit. Rebate savings assumed to reduce cash cost. No order placed.", *([""] * 8)])
    return output.getvalue()
