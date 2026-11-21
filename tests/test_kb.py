from agent_support_resolution.kb import KnowledgeBase

kb = KnowledgeBase()


def test_password_query_finds_password_article():
    top = kb.search("I forgot my password, how do I reset it?")[0]
    assert top.article_id == "KB-001"


def test_refund_query_finds_refund_policy():
    top = kb.search("I was charged twice, please refund me")[0]
    assert top.article_id == "KB-002"


def test_tracking_query_finds_tracking_article():
    top = kb.search("where is my order, tracking number?")[0]
    assert top.article_id == "KB-004"


def test_out_of_scope_scores_near_zero():
    top = kb.search("do you sell wedding cakes for 200 guests?")[0]
    assert top.score < 0.15


def test_search_is_deterministic():
    a = kb.search("cancel my subscription")
    b = kb.search("cancel my subscription")
    assert [(r.article_id, r.score) for r in a] == [(r.article_id, r.score) for r in b]


def test_top_k_respected():
    assert len(kb.search("shipping", top_k=2)) == 2
    assert len(kb.search("shipping", top_k=5)) == 5


def test_scores_sorted_descending():
    results = kb.search("refund policy for damaged items")
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
