from app.services.query.query_classifier import QueryClassifier, QueryType


def test_query_classifier_comparison():
    assert (
        QueryClassifier.classify("Compare the Q3 revenue vs Q4 revenue")
        == QueryType.COMPARISON
    )
    assert (
        QueryClassifier.classify("What is the difference between A and B?")
        == QueryType.COMPARISON
    )


def test_query_classifier_summarization():
    assert (
        QueryClassifier.classify("Can you summarize the second chapter?")
        == QueryType.SUMMARIZATION
    )
    assert (
        QueryClassifier.classify("Give me a brief overview of the project.")
        == QueryType.SUMMARIZATION
    )


def test_query_classifier_verification():
    assert (
        QueryClassifier.classify("Is it true that the CEO resigned?")
        == QueryType.VERIFICATION
    )
    assert (
        QueryClassifier.classify("Verify if the compliance requirements are met.")
        == QueryType.VERIFICATION
    )


def test_query_classifier_synthesis():
    assert (
        QueryClassifier.classify("Synthesize the main arguments from all documents.")
        == QueryType.SYNTHESIS
    )
    assert (
        QueryClassifier.classify("What are the overall implications of this policy?")
        == QueryType.SYNTHESIS
    )


def test_query_classifier_exploratory():
    assert QueryClassifier.classify("Why did the system fail?") == QueryType.EXPLORATORY
    assert (
        QueryClassifier.classify("Explain how the new algorithm works.")
        == QueryType.EXPLORATORY
    )


def test_query_classifier_factual():
    assert (
        QueryClassifier.classify("What is the capital of France?") == QueryType.FACTUAL
    )
    assert (
        QueryClassifier.classify("When was this document created?") == QueryType.FACTUAL
    )
    assert QueryClassifier.classify("Who signed the contract?") == QueryType.FACTUAL
