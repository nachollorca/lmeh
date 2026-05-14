from dataclasses import dataclass

from lmdk import CompletionResponse, complete, render_template


@dataclass
class Doc:
    name: str
    text: str


template = """Your task is to summarize a document called {{ DOCNAME }}.

This is the text with its paragraphs indexed:

{{ PARAGRAPHS }}

Output references to paragraphs with square brackets.
"""


# I thought of evaluating this
def summarize_with_refs(
    doc: Doc, model: str, generation_kwargs: dict, prompt_template: str = template
) -> CompletionResponse:
    paragraphs = doc.text.split("/n/n")
    indexed_paragraphs = {i: para for i, para in enumerate(paragraphs, start=1)}
    prompt = render_template(
        template=prompt_template, DOCNAME=doc.name, PARAGRAPHS=indexed_paragraphs
    )
    return complete(prompt=prompt, model=model, generation_kwargs=generation_kwargs)


# But maybe we should aim to evaluate this instead
def summarize_with_refs2(
    docname: str,
    paragraphs: dict,
    model: str,
    generation_kwargs: dict,
    prompt_template: str = template,
) -> CompletionResponse:
    prompt = render_template(template=prompt_template, DOCNAME=docname, PARAGRAPHS=paragraphs)
    return complete(prompt=prompt, model=model, generation_kwargs=generation_kwargs)
    pass
