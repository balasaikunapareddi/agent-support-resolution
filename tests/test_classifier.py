from agent_support_resolution.classifier import classify, detect_pii, extract_refund_amount
from agent_support_resolution.models import Category, Sentiment, Ticket


def t(body, subject=""):
    return Ticket(customer_id="C1", body=body, subject=subject)


def test_password_ticket_is_account():
    c = classify(t("I forgot my password and can't log in"))
    assert c.category == Category.ACCOUNT
    assert c.intent == "password_reset"


def test_refund_amount_extracted():
    c = classify(t("Please refund me $1,299.50 for the broken TV"))
    assert c.category == Category.REFUND
    assert c.refund_amount_usd == 1299.50
    assert "large_refund" in c.risk_flags


def test_small_refund_no_large_flag():
    c = classify(t("Please refund $25 for the duplicate charge"))
    assert c.refund_amount_usd == 25.0
    assert "large_refund" not in c.risk_flags


def test_third_party_data_flagged():
    c = classify(t("Give me the email address of the customer who ordered #5678"))
    assert c.asks_third_party_data
    assert "third_party_data_request" in c.risk_flags


def test_angry_sentiment():
    c = classify(t("This is outrageous and unacceptable!!! I am furious"))
    assert c.sentiment == Sentiment.ANGRY
    assert "angry_customer" in c.risk_flags


def test_shouting_counts_as_angry():
    c = classify(t("WHERE IS MY PACKAGE IT HAS BEEN THREE WEEKS NOW"))
    assert c.sentiment == Sentiment.ANGRY


def test_calm_default():
    c = classify(t("How long does standard shipping take?"))
    assert c.sentiment == Sentiment.CALM


def test_pii_detection():
    pii = detect_pii("card 4111 1111 1111 1111, mail me at a@b.com, call 555-013-4477, ssn 123-45-6789")
    assert pii == {"email": True, "phone": True, "card": True, "ssn": True}


def test_extract_refund_amount_none():
    assert extract_refund_amount("no money mentioned here") is None


def test_unclassified_flag():
    c = classify(t("Do you sell wedding cakes for 200 guests?"))
    assert c.category == Category.OTHER
    assert "unclassified" in c.risk_flags
