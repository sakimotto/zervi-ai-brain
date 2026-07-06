"""Seed data for Saki departmental agents and RAG knowledge.

This module contains the system prompts and sample documents/facts used to
bootstrap the AI brain for Zervi. It is imported by crud.py during startup
seeding and can be extended as new departments or policies are added.
"""

import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

DEPARTMENT_PROMPTS: Dict[str, str] = {
    "Sales Agent": """You are the Zervi Sales Agent, an expert inside the Odoo sales workflow.

Your responsibilities:
- Help users review sales quotations, sales orders, customers, and invoices.
- Suggest the next best action: confirm a quotation, create an invoice, send a follow-up email, or check delivery status.
- Use the visible record context (active order, customer, list of orders) to give specific, named recommendations.
- Cite sources when you use retrieved knowledge or past conversations.

Rules:
- Never confirm a sales order or create an invoice without the user's explicit confirmation.
- Always show a confirmation message that includes the order name/number before calling a high-risk tool.
- If you don't have enough context, ask a clarifying question instead of guessing.
- Be structured and specific: mention record names, amounts, states, and dates. Use headings and bullet points for record summaries.
""",

    "Purchasing Agent": """You are the Zervi Purchasing Agent, an expert in procurement and supplier management.

Your responsibilities:
- Help users review requests for quotation, purchase orders, supplier invoices, and incoming receipts.
- Suggest next actions: confirm a PO, check expected arrival dates, follow up with a vendor, or match a receipt.
- Use the visible record context (active PO, vendor, list of POs) to give specific, named recommendations.
- Cite sources when you use retrieved knowledge or past conversations.

Rules:
- Never confirm a purchase order or commit spend without the user's explicit confirmation.
- Always show a confirmation message that includes the PO reference and vendor before calling a high-risk tool.
- If delivery dates or vendor information is missing, ask the user before acting.
- Be structured and specific: mention PO references, vendors, expected dates, and states. Use headings and bullet points for record summaries.
""",

    "Accounting Agent": """You are the Zervi Accounting Agent, an expert in Odoo accounting, invoicing, and reconciliation.

Your responsibilities:
- Help users review customer invoices, vendor bills, payments, journal entries, and account balances.
- Suggest next actions: send a payment reminder, create a follow-up activity, review overdue items, or trace a journal entry.
- Use the visible record context (active invoice, partner, list of moves) to give specific, named recommendations.
- Cite sources when you use retrieved knowledge or past conversations.

Rules:
- Never post, reconcile, or register payments without the user's explicit confirmation.
- Do not give tax, legal, or compliance advice; defer those to a human accountant.
- Always show a confirmation message that includes the document number and partner before calling a high-risk tool.
- Be structured and specific: mention invoice numbers, due dates, amounts, and states. Use headings and bullet points for record summaries.
""",

    "Warehouse Agent": """You are the Zervi Warehouse Agent, an expert in inventory, stock pickings, and logistics.

Your responsibilities:
- Help users review incoming receipts, outgoing deliveries, internal transfers, and stock levels.
- Suggest next actions: validate a ready picking, check availability, print a picking list, or trace a backorder.
- Use the visible record context (active picking, product, list of transfers) to give specific, named recommendations.
- Cite sources when you use retrieved knowledge or past conversations.

Rules:
- Never validate a transfer or adjust stock without the user's explicit confirmation.
- Always show a confirmation message that includes the picking reference and operation type before calling a high-risk tool.
- If serial/lot tracking is involved, remind the user to verify lot numbers before validation.
- Be structured and specific: mention picking references, states, products, and quantities. Use headings and bullet points for record summaries.
""",

    "Manufacturing Agent": """You are the Zervi Manufacturing Agent, an expert in production planning and shop-floor operations.

Your responsibilities:
- Help users review manufacturing orders, BOMs, work orders, component availability, and production output.
- Suggest next actions: check component availability, mark an MO done, create a follow-up activity, or review a work center.
- Use the visible record context (active MO, BOM, list of orders) to give specific, named recommendations.
- Cite sources when you use retrieved knowledge or past conversations.

Rules:
- Never mark a manufacturing order done or consume components without the user's explicit confirmation.
- Always show a confirmation message that includes the MO reference and product before calling a high-risk tool.
- If components are missing, clearly list what is short and suggest a purchase or transfer.
- Be structured and specific: mention MO references, products, quantities, and component status. Use headings and bullet points for record summaries.
""",

    "HR Agent": """You are the Zervi HR Agent, an expert in employee records, contracts, leave, and timesheets.

Your responsibilities:
- Help users review employee profiles, contracts, leave requests, timesheets, and recruitment statuses.
- Suggest next actions: create a follow-up activity, review a contract, check leave balance, or view related payroll records.
- Use the visible record context (active employee, list of employees) to give specific, named recommendations.
- Cite sources when you use retrieved knowledge or past conversations.

Rules:
- Never modify contracts, approve leave, or process payroll without the user's explicit confirmation.
- Respect privacy: do not disclose sensitive employee information unless the user has access to the record.
- Always show a confirmation message that includes the employee name before calling a high-risk tool.
- Be structured and specific: mention employee names, contract states, and relevant dates. Use headings and bullet points for record summaries.
""",
}

DEPARTMENT_SKILLS: Dict[str, List[str]] = {
    "Sales Agent": ["Low_Risk_Tools", "Sales_Tools", "Invoicing_Tools", "Search_Tools"],
    "Purchasing Agent": ["Low_Risk_Tools", "Purchasing_Tools", "Search_Tools"],
    "Accounting Agent": ["Low_Risk_Tools", "Invoicing_Tools", "Search_Tools", "Accounting_Tools"],
    "Warehouse Agent": ["Low_Risk_Tools", "Inventory_Tools", "Search_Tools"],
    "Manufacturing Agent": ["Low_Risk_Tools", "Manufacturing_Tools", "Search_Tools"],
    "HR Agent": ["Low_Risk_Tools", "Search_Tools"],
}

DEPARTMENT_DOCUMENTS: List[Dict[str, Any]] = [
    {
        "source": "sales",
        "title": "Zervi Sales Playbook",
        "content_type": "policy",
        "content": """Zervi Sales Playbook

1. Quotation to order flow
   - A lead or opportunity is qualified before a quotation is created.
   - Quotations are sent to the customer for approval.
   - Once approved, the quotation is confirmed as a sales order.

2. Discount policy
   - Standard markup is 30% on cost.
   - Discounts up to 10% can be approved by the sales rep.
   - Discounts above 10% require sales manager approval.
   - Any discount that results in margin below 5% requires executive approval.

3. Invoicing rules
   - Invoice after delivery unless the customer has a pre-pay agreement.
   - Down-payment invoices are allowed for custom or large orders.
   - Overdue invoices are followed up at 7, 14, and 30 days.

4. Customer follow-up
   - A follow-up activity is created automatically when a quotation is sent.
   - Sales reps review open quotations weekly.
""",
        "metadata": {"department": "sales"},
    },
    {
        "source": "purchasing",
        "title": "Zervi Procurement Guidelines",
        "content_type": "policy",
        "content": """Zervi Procurement Guidelines

1. Purchase requisition
   - Departments create a purchase request for goods or services.
   - Purchasing reviews the request, selects a vendor, and creates a request for quotation (RFQ).

2. Vendor selection
   - Preferred vendors are listed in the approved vendor master.
   - New vendors require finance and operations approval before first PO.
   - At least two quotes are requested for orders over $5,000.

3. Purchase order approval
   - POs under $1,000: buyer approval.
   - POs $1,000-$10,000: purchasing manager approval.
   - POs over $10,000: CFO or delegated executive approval.

4. Receiving
   - All incoming goods must be received in Odoo within 24 hours of physical receipt.
   - Receipt quantities are matched to the PO. Discrepancies are flagged to purchasing and the vendor.

5. Three-way matching
   - Invoices are matched to PO and receipt before payment approval.
""",
        "metadata": {"department": "purchasing"},
    },
    {
        "source": "accounting",
        "title": "Zervi Invoice and Payment Policy",
        "content_type": "policy",
        "content": """Zervi Invoice and Payment Policy

1. Customer invoices
   - Invoices are created from confirmed sales orders or manually for services.
   - Standard payment terms are Net 30 unless otherwise agreed.
   - Invoices must be sent to the customer within 24 hours of shipment or service completion.

2. Overdue follow-up
   - Friendly reminder at 7 days overdue.
   - Formal reminder at 14 days overdue.
   - Escalation to sales manager and finance at 30 days overdue.

3. Vendor payments
   - Vendor bills are approved by the department head before payment.
   - Payments are batched weekly on Fridays.
   - Early-payment discounts are taken when available and approved.

4. Reconciliation
   - Bank statements are imported weekly.
   - Unreconciled items are reviewed by the 10th of the following month.

5. General rule
   - No journal entries or payments are posted without supporting documentation.
""",
        "metadata": {"department": "accounting"},
    },
    {
        "source": "warehouse",
        "title": "Zervi Warehouse SOP",
        "content_type": "procedure",
        "content": """Zervi Warehouse Standard Operating Procedure

1. Receiving
   - Verify carrier and PO number before unloading.
   - Count and inspect goods. Record damage or shortages immediately.
   - Receive goods in Odoo against the correct PO within 24 hours.

2. Put-away
   - Move received stock to the assigned location within 4 hours.
   - Update Odoo with the final location.

3. Picking
   - Pick orders in wave sequence when possible.
   - Verify lot/serial numbers for tracked products.
   - Stage picked goods in the shipping area.

4. Shipping
   - Validate the picking only after the carrier has picked up the goods.
   - Print and attach the delivery note and shipping label.

5. Backorders
   - If stock is short, create a backorder and notify sales/customer service.
   - Backorders are reviewed daily and prioritized by promised date.

6. Inventory counts
   - Cycle counts are performed weekly for high-value items.
   - Full physical count is performed quarterly.
""",
        "metadata": {"department": "warehouse"},
    },
    {
        "source": "manufacturing",
        "title": "Zervi Manufacturing Run Book",
        "content_type": "procedure",
        "content": """Zervi Manufacturing Run Book

1. Planning
   - Manufacturing orders (MOs) are created from sales orders or MRP proposals.
   - Confirm component availability before scheduling an MO.

2. BOM and routing
   - Use the approved BOM and routing for each product.
   - Report any BOM discrepancies to engineering before production starts.

3. Production start
   - Reserve components when the MO is confirmed.
   - Work orders are released in sequence according to the routing.

4. Shop floor
   - Operators log start/end times on each work order.
   - Scrap or rework is recorded immediately with reason codes.

5. Completion
   - Finished goods are moved to stock and quality is checked.
   - Mark the MO done only when all operations are complete and output is received.

6. Maintenance
   - Work centers have a preventive maintenance schedule.
   - Breakdowns are logged and maintenance is notified before the next run.
""",
        "metadata": {"department": "manufacturing"},
    },
    {
        "source": "hr",
        "title": "Zervi HR Quick Reference",
        "content_type": "policy",
        "content": """Zervi HR Quick Reference

1. Hiring
   - Job openings are approved by the department head and HR.
   - Offers require HR and finance sign-off.

2. Contracts
   - All employees have a signed contract on file before onboarding.
   - Contract renewals are reviewed 30 days before expiry.

3. Leave
   - Annual leave requests require manager approval.
   - Sick leave is recorded but does not require pre-approval.
   - Unpaid leave requires HR approval.

4. Timesheets
   - Timesheets are submitted weekly by end of day Friday.
   - Managers approve timesheets by the following Monday.

5. Offboarding
   - Departures are coordinated with IT and finance.
   - Final pay is processed after all company assets are returned.
""",
        "metadata": {"department": "hr"},
    },
    {
        "source": "company",
        "title": "Zervi Company Overview",
        "content_type": "general",
        "content": """Zervi Group Overview

- Zervi is a multi-disciplinary group serving residential and commercial clients.
- Core operations span sales, purchasing, warehousing, manufacturing, accounting, and human resources.
- Odoo is the central ERP for all departments.
- Saki is the AI assistant embedded in Odoo to help users complete daily tasks faster and with fewer errors.
- When in doubt, Saki asks for confirmation before performing high-risk actions such as confirming orders, validating transfers, posting invoices, or marking manufacturing orders done.
""",
        "metadata": {"department": "all"},
    },
]

DEPARTMENT_FACTS: List[Dict[str, Any]] = [
    {"category": "sales", "key": "discount_threshold", "value": "Sales discounts above 10% require manager approval."},
    {"category": "sales", "key": "invoice_timing", "value": "Customer invoices are normally created after delivery unless the customer has a pre-pay agreement."},
    {"category": "purchasing", "key": "receiving_sla", "value": "All incoming goods must be received in Odoo within 24 hours of physical receipt."},
    {"category": "purchasing", "key": "quote_requirement", "value": "At least two vendor quotes are required for purchase orders over $5,000."},
    {"category": "accounting", "key": "payment_terms", "value": "Standard customer payment terms are Net 30 unless otherwise agreed."},
    {"category": "accounting", "key": "payment_batch_day", "value": "Vendor payments are batched and processed weekly on Fridays."},
    {"category": "warehouse", "key": "validation_rule", "value": "Stock pickings are validated only after the carrier has picked up the goods."},
    {"category": "warehouse", "key": "backorder_review", "value": "Backorders are reviewed daily and prioritized by promised date."},
    {"category": "manufacturing", "key": "mo_done_rule", "value": "A manufacturing order is marked done only when all operations are complete and output is received."},
    {"category": "manufacturing", "key": "scrap_logging", "value": "Scrap or rework is recorded immediately with a reason code."},
    {"category": "hr", "key": "timesheet_deadline", "value": "Timesheets are submitted weekly by end of day Friday and approved by the following Monday."},
    {"category": "hr", "key": "contract_renewal", "value": "Contract renewals are reviewed 30 days before expiry."},
]


async def seed_department_knowledge(
    db: Any,
    embed_fn: Callable[[str], Coroutine[Any, Any, Optional[List[float]]]],
    create_document: Callable[..., Coroutine[Any, Any, Any]],
    create_fact: Callable[..., Coroutine[Any, Any, Any]],
    list_documents: Callable[..., Coroutine[Any, Any, Sequence[Any]]],
    list_facts: Callable[..., Coroutine[Any, Any, Sequence[Any]]],
) -> None:
    """Seed sample RAG documents and facts, skipping ones that already exist."""
    existing_docs = await list_documents(db, limit=10000)
    existing_doc_keys = {
        (getattr(d, "source", None), getattr(d, "title", None)) for d in existing_docs
    }

    for doc in DEPARTMENT_DOCUMENTS:
        if (doc["source"], doc["title"]) in existing_doc_keys:
            continue
        embedding = await embed_fn(doc["content"])
        if not embedding:
            logger.warning("Skipping document '%s' seeding: no embedding available", doc["title"])
            continue
        await create_document(
            db,
            source=doc["source"],
            title=doc["title"],
            content_type=doc["content_type"],
            content=doc["content"],
            embedding=embedding,
            metadata=doc.get("metadata"),
        )

    # Seed facts as shared knowledge (user_id = 0) so every user can retrieve them.
    SYSTEM_USER_ID = 0
    existing_facts = await list_facts(db, user_id=SYSTEM_USER_ID, limit=10000)
    existing_fact_keys = {
        (getattr(f, "category", None), getattr(f, "key", None)) for f in existing_facts
    }
    for fact in DEPARTMENT_FACTS:
        if (fact["category"], fact["key"]) in existing_fact_keys:
            continue
        embedding = await embed_fn(fact["value"])
        if not embedding:
            logger.warning("Skipping fact '%s' seeding: no embedding available", fact["key"])
            continue
        await create_fact(
            db,
            user_id=SYSTEM_USER_ID,
            category=fact["category"],
            key=fact["key"],
            value=fact["value"],
            embedding=embedding,
            is_shared=True,
        )
