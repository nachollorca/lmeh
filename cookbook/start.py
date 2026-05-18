import marimo

__generated_with = "0.23.6"
app = marimo.App(
    width="medium",
    css_file="/home/nacho/.config/marimo/catppuccin-latte-mocha.css",
    auto_download=["ipynb"],
)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Get started
    """)
    return


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Let's start with a basic example. The task is **text classification**. In particular, we want to find out whether some social media comments contain hate speech or not.

    We define some examples to begin with:
    """)
    return


@app.cell
def _():
    from lmeh.datatypes import Example

    dataset = [
        Example(inputs={"comment": "I think you are pretty ugly"}, reference=True),
        Example(inputs={"comment": "I love raspberry muffins"}, reference=False),
        Example(inputs={"comment": "What is wrong with ur face bro?"}, reference=True),
        Example(inputs={"comment": "Paris is the capital of Italy"}, reference=False),
        Example(inputs={"comment": "a cagar al campo chaval"}, reference=True),
    ]
    return Example, dataset


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Now, we define the target function that performs the classification. Its outputs are the ones we will evaluate.

    The function must adhere to the `TargetFunction` protocol: take its **named inputs**, the **prompt template**, and an **LM config**, then return a `TargetOutput`. The harness unpacks `Example.inputs` as keyword arguments, so the parameter names here must match the dict keys.
    """)
    return


@app.cell
def _():
    from lmdk import complete, render_template

    from lmeh.datatypes import LMConfig, TargetOutput

    def detect_hate(comment: str, prompt_template: str, config: LMConfig) -> TargetOutput:
        prompt = render_template(template=prompt_template, COMMENT=comment)
        response = complete(
            model=config.model,
            generation_kwargs=config.generation_kwargs,
            prompt=prompt,
            return_request=True,
            output_schema=config.output_schema,
        )
        return TargetOutput.passthrough(response=response)

    return LMConfig, detect_hate


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Now, lets define the moving parts under test. The three sweepable axes are the **prompt template**, the **LM config** (model, generation kwargs, optional output schema), and the target function itself.
    """)
    return


@app.cell
def _(LMConfig):
    from pydantic import BaseModel, Field

    class Output(BaseModel):
        is_hate: bool
        reason: str = Field(description="The brief reason why the comment is hate speech or not")

    prompt_template = "Do you think the comment '{{ COMMENT }}' is hate speech?"

    config = LMConfig(
        model="mistral:mistral-small-latest",
        generation_kwargs={"temperature": 0.7},
        output_schema=Output,
    )
    return config, prompt_template


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    With these ingredients, we can already run a trial: execute the target function with one of the examples and the config under test.
    """)
    return


@app.cell
def _(config, dataset, detect_hate, prompt_template):
    from lmeh.execution import run_trial

    trial = run_trial(
        target=detect_hate,
        prompt_template=prompt_template,
        config=config,
        example=dataset[0],
    )

    print(trial.result.output)
    return (trial,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Now that our trial run successfully, we can jump into the quality measurements.

    Let's define a silly metric that simply compares the output from the function for the given example against the reference (our truth value).

    For this, we do not need an LLM judge. A `ProgrammaticMetric` whose scorer follows the `ProgrammaticScorer` protocol is more than enough. We define the possible values using the `Ordinal` scale.
    """)
    return


@app.cell
def _(Example):
    from lmeh.datatypes import Ordinal, ProgrammaticMetric, Score

    def is_correct(output: bool, example: Example) -> Score:
        raw_score = output.is_hate == example.reference
        if raw_score:
            reason = "Output matches the reference"
        else:
            reason = "Output does not match the reference"

        return Score(raw=raw_score, reason=reason)

    correctness = ProgrammaticMetric(
        name="correctness",
        description="whether the answer is correct or not",
        scale=Ordinal(levels=[False, True]),
        scorer=is_correct,
    )
    return Ordinal, correctness


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Finally, we can just score the trial against the metric.
    """)
    return


@app.cell
def _(correctness, trial):
    from lmeh.execution import score_metric

    scoring = score_metric(trial=trial, metric=correctness)
    scoring.score
    return (score_metric,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    For the sake of playing, we could also make an LLM Judge that evaluates the same and gives a brief explanation. You can use the default one or create one that adheres to the `LLMJudgeScorer` protocol. Judge metrics use the `LLMJudgeMetric` variant — they carry their own `LMConfig` and judge prompt template.
    """)
    return


@app.cell
def _(LMConfig, Ordinal):
    from lmeh.datatypes import LLMJudgeMetric
    from lmeh.judges import default_llm_judge

    correctness_2 = LLMJudgeMetric(
        name="correctness2",
        description="whether the answer is correct or not",
        scale=Ordinal(levels=[False, True]),
        scorer=default_llm_judge,
        config=LMConfig(
            model="mistral:mistral-medium-latest",
            generation_kwargs={"temperature": 0.1},
        ),
    )
    return (correctness_2,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Lets evaluate it on the same example and see what the Judge thinks about the system output.
    """)
    return


@app.cell
def _(correctness_2, score_metric, trial):
    judge_scoring = score_metric(trial=trial, metric=correctness_2)
    judge_scoring.score
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Finally, we can make a full run: execute our `detect_hate` target function on all the examples from our dataset and evaluate our two metrics on the outputs.
    """)
    return


@app.cell
def _(
    config,
    correctness,
    correctness_2,
    dataset,
    detect_hate,
    prompt_template,
):
    from lmeh.execution import run_experiment
    from lmeh.datatypes import Experiment

    experiment = Experiment(
        name="silly-test",
        target=detect_hate,
        prompt_template=prompt_template,
        config=config,
    )

    results = run_experiment(
        experiment=experiment,
        dataset=dataset,
        metrics=[correctness, correctness_2],
        workers=5
    )
    return (results,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    And we can use a reporting utility to see the results.
    """)
    return


@app.cell
def _(mo, results):
    from lmeh.reporting import markdown_report
    mo.md(markdown_report(results))
    return


if __name__ == "__main__":
    app.run()
