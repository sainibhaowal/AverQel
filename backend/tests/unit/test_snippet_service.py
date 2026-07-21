from app.query.services.snippet_service import SnippetService


def test_snippet_service_clean_unicode():
    garbled = "This is a \ufffd test with \x01 control chars."
    cleaned = SnippetService.clean(garbled)
    assert cleaned == "This is a test with control chars."


def test_snippet_service_sentence_boundary():
    text = "Sentence one. Sentence two is very long and might get cut off if it exceeds the limit. Sentence three."
    cleaned = SnippetService.clean(text, max_chars=50)
    assert cleaned == "Sentence one."


def test_snippet_service_long_first_sentence():
    text = "This is one incredibly long single sentence that lacks any sort of punctuation and just goes on and on and on forever without stopping."
    cleaned = SnippetService.clean(text, max_chars=50)
    assert cleaned == "This is one incredibly long single sentence that l..."


def test_snippet_service_normal():
    text = "Normal text. Less than max. All good."
    cleaned = SnippetService.clean(text, 100)
    assert cleaned == "Normal text. Less than max. All good."
