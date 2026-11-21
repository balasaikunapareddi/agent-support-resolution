"""Bundled synthetic tickets for the demo and tests.

All people, orders, and amounts are fictional. The set spans the cases a
real support queue sees: routine answerable questions, a refund above
the auto-approval cap, a PII-bait request, an angry customer, an
out-of-scope question, and a ticket with raw PII pasted into it.
"""

from __future__ import annotations

from .models import Ticket

TICKETS: list[Ticket] = [
    Ticket(
        ticket_id="TKT-1001", customer_id="CUST-01", customer_name="Priya Nair",
        customer_email="priya@example.com",
        subject="Forgot my password",
        body="Hi, I forgot my password and can't log in. How do I reset it?",
    ),
    Ticket(
        ticket_id="TKT-1002", customer_id="CUST-02", customer_name="Marcus Lee",
        customer_email="marcus@example.com",
        subject="Where is my order?",
        body="I placed an order three days ago. How can I track my package and "
             "check the tracking status?",
    ),
    Ticket(
        ticket_id="TKT-1003", customer_id="CUST-03", customer_name="Elena Petrova",
        customer_email="elena@example.com",
        subject="Refund for duplicate charge",
        body="I was charged twice for the same item. Please refund me $25.00 "
             "for the duplicate charge.",
    ),
    Ticket(
        ticket_id="TKT-1004", customer_id="CUST-04", customer_name="David Kim",
        customer_email="david@example.com",
        subject="Refund for the TV",
        body="The TV I bought last week is too big for my room. I want a full "
             "refund of $329.99. Please process the refund today.",
    ),
    Ticket(
        ticket_id="TKT-1005", customer_id="CUST-05", customer_name="Anonymous",
        customer_email="anon@example.com",
        subject="Question about order #5678",
        body="Can you give me the email address of the customer who ordered "
             "#5678? I think they received my package by mistake.",
    ),
    Ticket(
        ticket_id="TKT-1006", customer_id="CUST-06", customer_name="Rachel Adams",
        customer_email="rachel@example.com",
        subject="THIS IS UNACCEPTABLE",
        body="This is the third time my delivery is late!!! Absolutely "
             "unacceptable and ridiculous. I am furious. Fix this NOW or I "
             "will never shop here again!",
    ),
    Ticket(
        ticket_id="TKT-1007", customer_id="CUST-07", customer_name="Tom Baker",
        customer_email="tom@example.com",
        subject="Wedding cakes",
        body="Do you sell wedding cakes? I need one for 200 guests next June "
             "and I'm wondering about flavors and pricing.",
    ),
    Ticket(
        ticket_id="TKT-1008", customer_id="CUST-08", customer_name="Aisha Khan",
        customer_email="aisha@example.com",
        subject="Cancel subscription",
        body="How do I cancel my subscription? I don't want to be billed "
             "next month.",
    ),
    Ticket(
        ticket_id="TKT-1009", customer_id="CUST-09", customer_name="Jonas Weber",
        customer_email="jonas@example.com",
        subject="Item arrived damaged",
        body="My order arrived with a cracked screen. The item is damaged "
             "and unusable. What are my options?",
    ),
    Ticket(
        ticket_id="TKT-1010", customer_id="CUST-10", customer_name="Maria Garcia",
        customer_email="maria@example.com",
        subject="Payment failed?",
        body="My card 4111 1111 1111 1111 was declined at checkout. My phone "
             "is 555-013-4477. Can you check my billing status?",
    ),
]
