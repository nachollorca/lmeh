# CHANGELOG

<!-- version list -->

## v1.3.0 (2026-05-18)

### Continuous Integration

- Ignore notes
  ([`66103a4`](https://github.com/nachollorca/lmeh/commit/66103a49cec203dddf46fc5e41077d86083db3b5))

### Documentation

- Run a full experiment on the getting started notebook
  ([`a7b7991`](https://github.com/nachollorca/lmeh/commit/a7b79914406162c76670b8f90a3d14e81cf4fe62))

### Features

- **reporting**: Make a markdown report of the run results
  ([`27fb561`](https://github.com/nachollorca/lmeh/commit/27fb561c58197cca4e91fa3c22053d139c23f9a7))

### Refactoring

- **metrics-and-config**: Split into LLMJudge and ProgramaticMetric, get prompt_template out of
  Config, unify TargetConfig and JudgeConfig
  ([`3075799`](https://github.com/nachollorca/lmeh/commit/30757993422bf63fee153fc553087e1d6eff70a5))


## v1.2.0 (2026-05-18)

### Documentation

- **cookbook**: Add initial draft notebook
  ([`19725e6`](https://github.com/nachollorca/lmeh/commit/19725e6c33567134d34d2257cab4d32f30c05040))

- **cookbook**: Include ipynotebooks
  ([`d82a789`](https://github.com/nachollorca/lmeh/commit/d82a7897c3f234090639e58c47b7fcc136a53ed8))

- **readme**: Add execution section
  ([`7da8d50`](https://github.com/nachollorca/lmeh/commit/7da8d5096e0a1f79d5a9f9af08d86b1cf58801f4))

### Features

- **jugdge**: Create a default LLM judge
  ([`ddff7f3`](https://github.com/nachollorca/lmeh/commit/ddff7f38bfddd54b38d1069be8eeb017acb4cea0))


## v1.1.0 (2026-05-17)

### Bug Fixes

- Point what TargetFunction does, and what is it expected to return
  ([`5533753`](https://github.com/nachollorca/lmeh/commit/55337530ce5e8b00009539238e0225eff69adc21))

### Code Style

- Reorder the datatypes module
  ([`13db39e`](https://github.com/nachollorca/lmeh/commit/13db39e6b034d69de93faadca7529d9790607472))

### Continuous Integration

- **execution**: Fix type hinting with casts
  ([`c46e66e`](https://github.com/nachollorca/lmeh/commit/c46e66ec543c2ff286b1c617e0077ba63b0d9e38))

- **init**: Make a module-level init so the package actually works
  ([`78269b9`](https://github.com/nachollorca/lmeh/commit/78269b9c8ed3468fb746a87b583ed48083483bec))

### Documentation

- Clarify failure rate and rendered prompt
  ([`1cd87fc`](https://github.com/nachollorca/lmeh/commit/1cd87fcaf5d18b1c8868534542e2adea5e184fad))

- Fix mermaid
  ([`a479ff8`](https://github.com/nachollorca/lmeh/commit/a479ff830e7929ea9eb2abedafc244ea9012d9c4))

- Log the action plan
  ([`1f27dbc`](https://github.com/nachollorca/lmeh/commit/1f27dbc5cfdc87813b315b49b55e799cff98d2b5))

- Minor adjustments to readme
  ([`d6a230a`](https://github.com/nachollorca/lmeh/commit/d6a230abe48dcd12adc87c1c42598c24540f79e5))

- Remove dated TODO
  ([`fc56da4`](https://github.com/nachollorca/lmeh/commit/fc56da44abbeaebc0c5bec2b5c6cefc682a7923e))

- Remove PLAN
  ([`4f59af5`](https://github.com/nachollorca/lmeh/commit/4f59af5603df327050e17830c76f57f669f6dcde))

- Some more alignment
  ([`83dd38e`](https://github.com/nachollorca/lmeh/commit/83dd38e8ddf907037cdeca90f3a7bf7d686bcd35))

- Split between spec and TODO
  ([`214a3cb`](https://github.com/nachollorca/lmeh/commit/214a3cb2ee5b40a36197d761207c30c1a6724c5e))

- Try to make sense of the full story
  ([`9a41f89`](https://github.com/nachollorca/lmeh/commit/9a41f8901580a933faff95f955652e4ffcb515c4))

### Features

- First implementation for execution
  ([`0763d9f`](https://github.com/nachollorca/lmeh/commit/0763d9f602d2a981f0ec32233fe8ac475df18ec3))

### Refactoring

- Change namings once again
  ([`6233746`](https://github.com/nachollorca/lmeh/commit/62337468690c93bdb8e1027b527ab6f8df75fe28))

- Dismiss datasets where some examples have references and some have not
  ([`f997b18`](https://github.com/nachollorca/lmeh/commit/f997b1828383f84a6ddf690c3fbd7cae2bae6756))

- Fix hint errors
  ([`b143e2d`](https://github.com/nachollorca/lmeh/commit/b143e2d7fe377fecb7e29b44192a196776773746))

- Store successes and errors separately for trials and scorings
  ([`9338d6a`](https://github.com/nachollorca/lmeh/commit/9338d6abc0b91d914c0ee822a5b79c772a138e54))

### Testing

- Upload an example of the doubt I have
  ([`2c34b30`](https://github.com/nachollorca/lmeh/commit/2c34b308b5c511080b2fb94f2a9a473da74befb5))


## v1.0.0 (2026-05-03)

- Initial Release
