# CHANGELOG

<!-- version list -->

## v1.37.2 (2026-08-31)

### Bug Fixes

- Remove false warning from svelte
  ([`5bff32c`](https://github.com/nachollorca/promptuna/commit/5bff32c4e65f7d37841279d31f7c238615d27a07))


## v1.37.1 (2026-08-31)

### Bug Fixes

- **frontend**: Silence state_referenced_locally in JsonView
  ([`1bf36bd`](https://github.com/nachollorca/promptuna/commit/1bf36bd01d589f15ca232a4cc591eb7e2f584386))


## v1.37.0 (2026-08-31)

### Features

- **jobs**: Register also stacktraces
  ([`04ea04e`](https://github.com/nachollorca/promptuna/commit/04ea04ec7fd353c7e467bd6b04b64e5971e0e2ec))


## v1.36.0 (2026-08-31)

### Bug Fixes

- **jobs**: Aggregate summaries per (example, metric) cell
  ([`0431183`](https://github.com/nachollorca/promptuna/commit/0431183e4411158fcf41a0d410caf542e22129e5))

- **list-programs**: Further reinforce how programs are discovered
  ([`7eaa5a7`](https://github.com/nachollorca/promptuna/commit/7eaa5a779f0e7fea5ddb07b1a53786a7b6c84e16))

### Documentation

- **readme**: Document replicate divergence alongside the noise floor
  ([`c823aa5`](https://github.com/nachollorca/promptuna/commit/c823aa5d92c03b3cf7d38b947f157d6ec97cbff4))

### Features

- **evaluate**: Measure replicate divergence as telemetry
  ([`8613384`](https://github.com/nachollorca/promptuna/commit/861338417c5d72d357383917d8caff2d1ce333f2))

- **frontend**: Pack replicates of one example into a single trial row
  ([`8f43226`](https://github.com/nachollorca/promptuna/commit/8f43226da0e0176489ec6c205eeb252469fdaf50))

- **frontend**: Show noise floor and replicate divergence in the summary
  ([`6d8e496`](https://github.com/nachollorca/promptuna/commit/6d8e496b0fa6f018b4fe5ab11b7e460a597efe1b))

- **repeats**: Add server and CLI knobs for trial repetition
  ([`641aa66`](https://github.com/nachollorca/promptuna/commit/641aa66d19947dd4a41dd8be851c085f670420ee))

- **serialize**: Tag events with a replicate-independent example_id
  ([`b571531`](https://github.com/nachollorca/promptuna/commit/b5715315c8a74fdbe54e434442ea9c775235faf3))


## v1.35.3 (2026-08-20)

### Bug Fixes

- Lower supported python floor to 3.12 for cli and server
  ([#70](https://github.com/nachollorca/promptuna/pull/70),
  [`4322b89`](https://github.com/nachollorca/promptuna/commit/4322b894e7cce9b98c7e9ab1675ab9c6bc6d44d0))

### Continuous Integration

- Require python 3.12 in server and cli ([#69](https://github.com/nachollorca/promptuna/pull/69),
  [`ed5c801`](https://github.com/nachollorca/promptuna/commit/ed5c8015f29dbc53265012895f0bef6b49aded64))


## v1.35.2 (2026-08-20)

### Bug Fixes

- Trigger release
  ([`370e563`](https://github.com/nachollorca/promptuna/commit/370e563e9728be0a361fa00fbc2313603441d0b6))

### Continuous Integration

- Allow promptuna 3.12
  ([`755aa92`](https://github.com/nachollorca/promptuna/commit/755aa9220d472a06daf5ea2cca90a698513408ad))


## v1.35.1 (2026-08-19)

### Bug Fixes

- **frontend**: Keep trial rows pulsing until all metrics score
  ([`67f6ef1`](https://github.com/nachollorca/promptuna/commit/67f6ef1793070c91ab73bb25e613c18ddf4a897f))

### Documentation

- Write about the use of AI in the package
  ([`cfce645`](https://github.com/nachollorca/promptuna/commit/cfce6450c823502bc27aece974264285508a6f3d))

- **readme**: Edit the written with AI part
  ([`7079dac`](https://github.com/nachollorca/promptuna/commit/7079dac0d4f043c5d3d6375405973ca598d48c36))


## v1.35.0 (2026-08-07)

### Features

- **frontend**: Collapse large trial fields, per-metric chips, row ids
  ([`9d20d5f`](https://github.com/nachollorca/promptuna/commit/9d20d5f94794b70f5ab2589f1390e58c5674655c))

- **frontend**: Make expanders for large fields
  ([`7fe163d`](https://github.com/nachollorca/promptuna/commit/7fe163d136f314ba2076ccc75159a1428c8e33b6))


## v1.34.0 (2026-07-04)

### Bug Fixes

- **optimizer**: Make placeholders raw in the examples
  ([`07d3ddf`](https://github.com/nachollorca/promptuna/commit/07d3ddfca052d6d8a58c1df6f404cfd3a499201d))

### Features

- **frontend**: Make rows pulse when in progress, color by mean score
  ([`fd83ab1`](https://github.com/nachollorca/promptuna/commit/fd83ab185b03f30a4db988cd859f853f8726a168))

- **optimizer**: Emit and display proposer advice in job UI
  ([`6c0321d`](https://github.com/nachollorca/promptuna/commit/6c0321d4c570ef7d3dd4dcb0bbfc4d53d2b3463d))


## v1.33.0 (2026-07-01)

### Features

- **optimizer**: Add prompt template craft guidance
  ([`993b0d4`](https://github.com/nachollorca/promptuna/commit/993b0d433556c040395f1d6cd73309d452cd09d4))


## v1.32.0 (2026-07-01)

### Features

- **samples**: Add English and Spanish classify_sentiment prompts
  ([`ef13e98`](https://github.com/nachollorca/promptuna/commit/ef13e98e950e4c73a7fd3ef074c66c8cb7cab14c))


## v1.31.0 (2026-06-30)

### Documentation

- Re-run the notebook with the new examples
  ([`8a161df`](https://github.com/nachollorca/promptuna/commit/8a161dfdd255fd7b3502975ebfe0de5d3e02c1fb))

### Features

- **samples**: Refresh classify_sentiment tutorial sample
  ([`108be79`](https://github.com/nachollorca/promptuna/commit/108be79457b6db3a423b365066a32919e707e1a9))


## v1.30.0 (2026-06-30)

### Features

- **frontend**: Add side-by-side job comparison on Jobs tab
  ([`20ddca4`](https://github.com/nachollorca/promptuna/commit/20ddca46d25cab1aed8b8e1901f60c257c26c8bc))


## v1.29.0 (2026-06-29)

### Features

- **frontend**: Invert Start CTA colors on hover
  ([`f2d0605`](https://github.com/nachollorca/promptuna/commit/f2d06056591221bf0e2f3e8dd5cf4156cbb020ed))


## v1.28.0 (2026-06-29)

### Documentation

- Add centered logo to README and ignore .cursor/
  ([`b6432b1`](https://github.com/nachollorca/promptuna/commit/b6432b1e397cf740136b70e48a0b299a91d3d51a))

### Features

- **frontend**: Replace native selects with custom dropdown component
  ([`2ec02d6`](https://github.com/nachollorca/promptuna/commit/2ec02d602ae10afa98016ab820365af0ba98cb6c))

### Refactoring

- **frontend**: Consolidate logo into frontend/static/logo.png
  ([`b3280b2`](https://github.com/nachollorca/promptuna/commit/b3280b2381cfa0fb1f41bedad9b306671602addc))


## v1.27.0 (2026-06-28)

### Bug Fixes

- **ci**: Set PUBLIC_API_URL in verify workflow for svelte-check
  ([`edaaa83`](https://github.com/nachollorca/promptuna/commit/edaaa83f47148bff0a802136a3ad49978833daf1))

- **frontend**: Include lib and jobs routes omitted by gitignore
  ([`ce5cea2`](https://github.com/nachollorca/promptuna/commit/ce5cea2d934d15ee761f9e12b8f27ba4c44cf010))

### Chores

- **frontend**: Add ESLint, Prettier, and CI quality gates
  ([`8d8f504`](https://github.com/nachollorca/promptuna/commit/8d8f504d9e5c2bd78176db02f62509008bb83212))

### Documentation

- Consolidate web surface READMEs and remove HANDOFF
  ([`11dfc85`](https://github.com/nachollorca/promptuna/commit/11dfc85350cbf417bfd2749abf073406cdfdc949))

- Restructure README for clearer navigation
  ([`a0b2c5a`](https://github.com/nachollorca/promptuna/commit/a0b2c5adffa8c5c08e00c49b6e8cf2b094df11a4))

- **frontend**: Add self-contained GUI handoff
  ([`b3ce597`](https://github.com/nachollorca/promptuna/commit/b3ce5974c849c144832e4e241a1289b51c8d1648))

### Features

- Package web UI and API in a single container image
  ([`517e259`](https://github.com/nachollorca/promptuna/commit/517e259babbea3e08917d63652f625d679cc4b2d))

- **frontend**: Add SvelteKit web UI for job launch and live results
  ([`c3b4642`](https://github.com/nachollorca/promptuna/commit/c3b4642dec4b9a53c51d45e69573a24d69f63943))

- **frontend**: Apply Technical Precision design system
  ([`a9bb459`](https://github.com/nachollorca/promptuna/commit/a9bb459e1ca6ab30e4c6139b36837bb37bca23fa))


## v1.26.0 (2026-06-28)

### Features

- **server**: Stream proposal events and add job replay endpoints
  ([`aceacc6`](https://github.com/nachollorca/promptuna/commit/aceacc6933bdec3085065847ed2ce56316446ff1))


## v1.25.1 (2026-06-27)

### Bug Fixes

- Configure ty roots for workspace and test packages
  ([`9fad4c0`](https://github.com/nachollorca/promptuna/commit/9fad4c0213e23266d7b0e0629a779c971c9a8e6c))

### Documentation

- Add metrics-over-prompts philosophy to README
  ([`e850cd3`](https://github.com/nachollorca/promptuna/commit/e850cd3aa2bb881e4f7da5579c8447b54ecf4c2d))

- Explain optimizer plateaus and extension directions in README
  ([`446052a`](https://github.com/nachollorca/promptuna/commit/446052ac63fcb47e2c1a1b0ba17b2a88e352118e))


## v1.25.0 (2026-06-26)

### Bug Fixes

- Add PyPI readme and metadata to satellite packages
  ([`d858434`](https://github.com/nachollorca/promptuna/commit/d85843466d5b44131f82a44582f608b484e5dd91))

### Continuous Integration

- Refresh lock
  ([`9b3ea4e`](https://github.com/nachollorca/promptuna/commit/9b3ea4e1bfb490e7f6eea4824ce232f7060e352f))

### Features

- **cli**: Surface SKILL.md in promptuna --help
  ([`9c2c08d`](https://github.com/nachollorca/promptuna/commit/9c2c08d1c8daec4d02932123e6b8e67a6b0e8ea2))


## v1.24.0 (2026-06-26)

### Chores

- **release**: Publish all workspace packages with unified versioning
  ([`9bc574d`](https://github.com/nachollorca/promptuna/commit/9bc574d1bcd97d9939dcbda7cefb2d39f3caec0b))

### Features

- Document unified workspace versioning and release flow
  ([`b94e65c`](https://github.com/nachollorca/promptuna/commit/b94e65ce18eca52a6b5fbd2a8fda244dc4634eb6))

### Refactoring

- **cli**: Extract Typer CLI into separate workspace package
  ([`e860544`](https://github.com/nachollorca/promptuna/commit/e860544924c74c952d02c5403eccfa5d51214871))


## v1.23.0 (2026-06-25)

### Features

- Add Typer CLI for run, evaluate, optimize, and report
  ([`0d8dea5`](https://github.com/nachollorca/promptuna/commit/0d8dea54302ea352cb56668a056ceaee9a57cf1e))

### Refactoring

- Move render_history from optimize to report
  ([`9f6389d`](https://github.com/nachollorca/promptuna/commit/9f6389d26e0f473b94358f74e17ecd66f72290e4))


## v1.22.0 (2026-06-25)

### Features

- Add on-disk job persistence for server streaming jobs
  ([`c84ece5`](https://github.com/nachollorca/promptuna/commit/c84ece51bdf601fcb243a6cf746b7f0745e962cb))

- Add stream_job wrapper for shared job persistence
  ([`b81de49`](https://github.com/nachollorca/promptuna/commit/b81de49325764fc7aa5a958a34d7e00523d57f9f))

### Refactoring

- Rename run_experiment to evaluate
  ([`e1ddd73`](https://github.com/nachollorca/promptuna/commit/e1ddd73ccc775092ce99c3687367818da4239b8d))

- Rename stream_experiment to stream_evaluate
  ([`7b3c124`](https://github.com/nachollorca/promptuna/commit/7b3c1240c98503312934e1a29d8b47fb2ae9aebd))


## v1.21.0 (2026-06-24)

### Features

- **server**: Add GET /catalog for workspace artifact discovery
  ([`4cfed00`](https://github.com/nachollorca/promptuna/commit/4cfed0063ee2dce87daaccb4c600fd6d49729ead))

### Refactoring

- **getting-started**: Load classify_sentiment from samples
  ([`fd19c85`](https://github.com/nachollorca/promptuna/commit/fd19c850b6f9a4e972326bc421dcb5cde16254a6))


## v1.20.0 (2026-06-24)

### Chores

- Scaffold optional cli extra and future surface placeholders
  ([`eb4453d`](https://github.com/nachollorca/promptuna/commit/eb4453d56ad42ab6e7a7333142a999098df11963))

### Continuous Integration

- Ignore spec plans
  ([`a8e66d3`](https://github.com/nachollorca/promptuna/commit/a8e66d36c2fd34a15c3174bbdb48cdcd9c01f12d))

### Documentation

- Document usage surfaces and planned agent/server workflows
  ([`43ac095`](https://github.com/nachollorca/promptuna/commit/43ac095dab79cb30b77958d0ac705a8d190dfd2e))

### Features

- Support PROMPTUNA_PROJECTS_ROOT for project discovery
  ([`de1fd04`](https://github.com/nachollorca/promptuna/commit/de1fd04f64b5a0cdb722d03d1dc954bd534e7e37))

### Refactoring

- Extract on-disk project loader into promptuna.projects
  ([`d4947cb`](https://github.com/nachollorca/promptuna/commit/d4947cb3219231461be680c4b3c9497a3881f5a7))

- Move reference project from server/projects to samples/
  ([`32ffd64`](https://github.com/nachollorca/promptuna/commit/32ffd64ec23623ca10703d2585945d26910e88d4))

### Testing

- Add unit tests for promptuna.projects loader
  ([`35f6b03`](https://github.com/nachollorca/promptuna/commit/35f6b034b8c483ed69c3daac8423ba9df76ae4b2))


## v1.19.0 (2026-06-24)

### Bug Fixes

- **server**: Replay SSE events and include server in coverage gate
  ([`d52546a`](https://github.com/nachollorca/promptuna/commit/d52546aac0ebf0fe2b7aa35d246c20d76998c27a))

### Features

- **server**: Add FastAPI streaming run/evaluate/optimize API
  ([`f9ab4ab`](https://github.com/nachollorca/promptuna/commit/f9ab4abde24d9546b1c56a0a5090547e4f7ab6a8))


## v1.18.0 (2026-06-23)

### Features

- **run**: Add stream_run function that is parallel to stream_experiment and stream_optimize
  ([`d3494d5`](https://github.com/nachollorca/promptuna/commit/d3494d55482d1f5612ff9d53b7c38f990735fd2a))

- **serialize**: Add JSON event envelopes for stream_optimize
  ([`64dd36e`](https://github.com/nachollorca/promptuna/commit/64dd36e624926383668addecada5b36bd61b5018))

- **serialize**: Rename run_id to job_id and add serialize_error
  ([`28cc193`](https://github.com/nachollorca/promptuna/commit/28cc193b2ebb9690665e428acdccc041f04e1e8a))


## v1.17.0 (2026-06-21)

### Continuous Integration

- Pass specific file paths to prek
  ([`cad5053`](https://github.com/nachollorca/promptuna/commit/cad5053a0811c5e963723ca3b240a739e4e5b9c2))

- **justfile**: Freeze uv commands so that lock file does not get updated at prek
  ([`47b55d0`](https://github.com/nachollorca/promptuna/commit/47b55d0b7bbccf03482d69e9e6a7be217be139d7))

### Documentation

- **notebook**: Remove the LMConfig
  ([`a8172d2`](https://github.com/nachollorca/promptuna/commit/a8172d2002d5ac6a09035da0b4879ed45d7880ff))

### Features

- **optimizer**: Stream results
  ([`170b239`](https://github.com/nachollorca/promptuna/commit/170b2394e0252ef0ea53f2fe799ab09b839c6f45))

### Testing

- Enforce typing and linting in tests too
  ([`681137f`](https://github.com/nachollorca/promptuna/commit/681137fb50cd8bc5dbc31113dd8295009765222c))


## v1.16.0 (2026-06-19)

### Features

- **optimizer**: Account for the thinking process on the optimizing trajectory
  ([`7453287`](https://github.com/nachollorca/promptuna/commit/74532870979b35608a8623363fc2c705b0b01346))


## v1.15.0 (2026-06-19)

### Documentation

- Unify the definition of Program
  ([`c9771f9`](https://github.com/nachollorca/promptuna/commit/c9771f945be799ba8cf3367be4fc7fd5006223f2))

### Features

- **optimizer**: Use fenced blocks for verbatim templates in history
  ([`6695e2d`](https://github.com/nachollorca/promptuna/commit/6695e2df5b032a295e4585dc4d84ff7c5adc4dcf))


## v1.14.1 (2026-06-19)

### Bug Fixes

- **optimizer**: Make template clearer
  ([`adc38df`](https://github.com/nachollorca/promptuna/commit/adc38df417cd4be90750517953f8c685872880dc))


## v1.14.0 (2026-06-17)

### Features

- **optimizer**: Improve prompt rendering
  ([`4c6328b`](https://github.com/nachollorca/promptuna/commit/4c6328be27f0755b9f61408b3eda2e4a3b12848b))


## v1.13.0 (2026-06-17)

### Bug Fixes

- **optimizer**: Show weak examples only for best and last steps
  ([`5a6a1ad`](https://github.com/nachollorca/promptuna/commit/5a6a1ad9510f1e06f39639d113781132fddbea22))

### Features

- **optimizer**: Show rendered prompt instead of bare inputs in error analysis
  ([`68959b1`](https://github.com/nachollorca/promptuna/commit/68959b1b4c81daf10c80cc088342e3bda3403999))

### Refactoring

- Make a clear distinction between failure / error analysis / weakest example
  ([`aa04449`](https://github.com/nachollorca/promptuna/commit/aa04449d48175781bcd28943bcaefe2f20a6d7f9))

### Testing

- **optimizer**: Add tests for weak example rendering
  ([`426be9b`](https://github.com/nachollorca/promptuna/commit/426be9bd9dc4b1eba1ade701a7c4b2f93201744f))


## v1.12.0 (2026-06-16)

### Features

- **optimizer**: Add metric rubric to optimizer prompt
  ([`92806bf`](https://github.com/nachollorca/promptuna/commit/92806bfa33a1ec79fe82865f93612c18b889ae2a))

- **optimizer**: Show the scaffold and output schema of the program to the optimizer LM
  ([`71b060e`](https://github.com/nachollorca/promptuna/commit/71b060e2de09501dc6bdb0b4d4e500668fbdf3ee))


## v1.11.0 (2026-06-15)

### Features

- **program**: Add dataset loader
  ([`b07f44f`](https://github.com/nachollorca/promptuna/commit/b07f44f31f306748f0e42cf811aac96c6720645e))

### Refactoring

- **loader**: Move to its own module
  ([`f8f360d`](https://github.com/nachollorca/promptuna/commit/f8f360dab9c7d79c2d5ab374114fa08b2fef4a6b))


## v1.10.0 (2026-06-15)

### Documentation

- Add inspo and math to readme
  ([`d75fd0f`](https://github.com/nachollorca/promptuna/commit/d75fd0fee6fdc4fa99c2a2ba3c2fac8c720646a9))

- Remove comment that had been cleared out
  ([`2bf837d`](https://github.com/nachollorca/promptuna/commit/2bf837d6214f6f119a39b81cf257f77b7a4b24c5))

- Remove the pedantic mathy
  ([`ae850c1`](https://github.com/nachollorca/promptuna/commit/ae850c1b9b80bdb8256e456f3b9ec8201bf2db5a))

- Trim redundant docstrings
  ([`ba0d109`](https://github.com/nachollorca/promptuna/commit/ba0d109d02aa0e587561b6376b02cbeec589724b))

- **readme**: Add silly diagram for improvement loop
  ([`aee1dee`](https://github.com/nachollorca/promptuna/commit/aee1dee47bb7cb908ebbd9a73c261700d06b09f3))

### Features

- Edit readme but call it feat to trigger first pypi release
  ([`4ef14cc`](https://github.com/nachollorca/promptuna/commit/4ef14cc70ea8ae8ae891fe33202bc396c629082a))

### Refactoring

- Rename lmeh to promptuna
  ([`d0b44be`](https://github.com/nachollorca/promptuna/commit/d0b44be184701069486056196310a97da7b40efa))

- Reorganize the layout
  ([`ba8229d`](https://github.com/nachollorca/promptuna/commit/ba8229de96bfa90e603533528207991185a0e985))

### Testing

- Draft test suite
  ([`9f970bd`](https://github.com/nachollorca/promptuna/commit/9f970bde5006bf6b73864be095133046527f15c6))


## v1.9.0 (2026-06-12)

### Documentation

- **readme**: Explain briefly the concepts behind the optimization
  ([`08c3557`](https://github.com/nachollorca/promptuna/commit/08c35574aaf9d473a96c3b0068eadbec3ddc75bf))

### Features

- **optimizer**: Implement attentive reasoning queries
  ([`89f81a8`](https://github.com/nachollorca/promptuna/commit/89f81a8d7dd14cdd6963fcb2678d58892a2d3014))


## v1.8.0 (2026-06-12)

### Documentation

- **notebook**: Add a summary story of what we are doing
  ([`d4e1d24`](https://github.com/nachollorca/promptuna/commit/d4e1d24f653b08556f326d0c8af6d20efc3a2d52))

### Features

- **optimizer**: Stop propser early if the score is already perfect
  ([`c60741a`](https://github.com/nachollorca/promptuna/commit/c60741a43642702a405a45b4ad2564738477f38a))

### Refactoring

- **prompts**: Move prompts to jinja files instead of inlining them in the code
  ([`2301ca3`](https://github.com/nachollorca/promptuna/commit/2301ca3f21e7659eaccb12bb2e72db9a7ba61a54))


## v1.7.1 (2026-06-12)

### Bug Fixes

- **optimizer**: Ensure that jinja variables in nested prompt templates are shown properly
  ([`075dfa2`](https://github.com/nachollorca/promptuna/commit/075dfa26ab95599edc08f0aa80b715f3a597a65d))

- **optimizer**: Split the rendering of the results legend to avoid duplication in each step render
  ([`0a421ca`](https://github.com/nachollorca/promptuna/commit/0a421ca816556f878cc0e0d821d6982250af03a3))

### Refactoring

- **optimizer**: Move rendering code together instead of having reporting + optimizer
  ([`aa12d0f`](https://github.com/nachollorca/promptuna/commit/aa12d0f2d976faebf4b32566447f30883fce4491))


## v1.7.0 (2026-06-10)

### Code Style

- Little comments and style changes
  ([`e9308dc`](https://github.com/nachollorca/promptuna/commit/e9308dc470b1dd60c98edddeca266d0509638d31))

- Remove keyword-only separators
  ([`4d4ad62`](https://github.com/nachollorca/promptuna/commit/4d4ad62aa4cf9000af575703031fd88b1b95313b))

- **optimizer**: Use alias for nested output types
  ([`485c875`](https://github.com/nachollorca/promptuna/commit/485c875d57a77546e4ac2426b29d5dac90a50b67))

### Continuous Integration

- **gitignore**: Ignore notebooks
  ([`56ccecd`](https://github.com/nachollorca/promptuna/commit/56ccecd90fb2558849d92b50d8617b25b2bdf6bb))

### Documentation

- Clear up readme
  ([`5eefbdb`](https://github.com/nachollorca/promptuna/commit/5eefbdbfd90041aeed077883ba6cdeb3f5898192))

- **notebook**: Add optimization example
  ([`7bed3dc`](https://github.com/nachollorca/promptuna/commit/7bed3dc0a586dabf779ce012c82cb39e6f31f579))

- **notebook**: Add telemetry to the notebook
  ([`4f50ede`](https://github.com/nachollorca/promptuna/commit/4f50ede605773236820388a86c5e342e124b537b))

- **notebook**: Make the getting started notebook a first class citizen, use jupyter instead of
  marimo
  ([`f3cacf2`](https://github.com/nachollorca/promptuna/commit/f3cacf2b5bea6dce00f90ca699e5dbce83a7f057))

- **notebook**: Replace marimo with ipynb because we can render it in github
  ([`8882591`](https://github.com/nachollorca/promptuna/commit/88825919474565624c7eecc5a879dc3bfe0f0d51))

### Features

- Actually do the largest part of the implementation
  ([`fee6808`](https://github.com/nachollorca/promptuna/commit/fee68084119490610fc98c533aa4a407e36fdfc9))

- **optimizer**: Write initial sketch
  ([`2e2633f`](https://github.com/nachollorca/promptuna/commit/2e2633f241149a4c9074e3cca4cacf6ecf676379))

### Refactoring

- **datatypes**: Remove Dataset alias because it was misleading
  ([`f1fdec7`](https://github.com/nachollorca/promptuna/commit/f1fdec777c1083aa3912d1ab4d4a96d824a040fc))

- **optimizer**: Reduce cyclomatic complexity
  ([`0213f7f`](https://github.com/nachollorca/promptuna/commit/0213f7fa9b0567d00b06a74bc3debb74c25ecaee))


## v1.6.0 (2026-05-24)

### Features

- Add dispersion aggregates in RunResults
  ([`4f8117e`](https://github.com/nachollorca/promptuna/commit/4f8117e89a21ab4b38517c461c69166d17b698e2))


## v1.5.0 (2026-05-23)

### Documentation

- Make a better getting_started notebook
  ([`ae0c5ea`](https://github.com/nachollorca/promptuna/commit/ae0c5eaf080ee5bc0909465c68d39c2463007c57))

### Features

- Add repetition and aggregation in every stochastic touch
  ([`d594478`](https://github.com/nachollorca/promptuna/commit/d5944783a013616ee8fd813ed9992257ab6c5783))

### Refactoring

- Extract helpers for the thread processor to reduce cyclomatic complexity
  ([`6c1c15d`](https://github.com/nachollorca/promptuna/commit/6c1c15d3f72edc42e408404696e74a1e75950b68))

- Remove `OutputSchema` from `LMConfig`, it is now only responsibility of the target function
  ([`7b97e04`](https://github.com/nachollorca/promptuna/commit/7b97e049dcf530d1f4ff97a8312ae71958eed7e6))

- Split RawScore from Score to keep contracts honest
  ([`e260f0b`](https://github.com/nachollorca/promptuna/commit/e260f0b70a6656d09d87e3e948035c087d4326bf))


## v1.4.0 (2026-05-19)

### Features

- **datatypes**: Remove TargetOutput because now lmdk can natively observe requests / responses when
  complete is called
  ([`69cfef5`](https://github.com/nachollorca/promptuna/commit/69cfef53931aaa2f18c07e458037e0fd640636fa))


## v1.3.0 (2026-05-18)

### Continuous Integration

- Ignore notes
  ([`66103a4`](https://github.com/nachollorca/promptuna/commit/66103a49cec203dddf46fc5e41077d86083db3b5))

### Documentation

- Run a full experiment on the getting started notebook
  ([`a7b7991`](https://github.com/nachollorca/promptuna/commit/a7b79914406162c76670b8f90a3d14e81cf4fe62))

### Features

- **reporting**: Make a markdown report of the run results
  ([`27fb561`](https://github.com/nachollorca/promptuna/commit/27fb561c58197cca4e91fa3c22053d139c23f9a7))

### Refactoring

- **metrics-and-config**: Split into LLMJudge and ProgramaticMetric, get prompt_template out of
  Config, unify TargetConfig and JudgeConfig
  ([`3075799`](https://github.com/nachollorca/promptuna/commit/30757993422bf63fee153fc553087e1d6eff70a5))


## v1.2.0 (2026-05-18)

### Documentation

- **cookbook**: Add initial draft notebook
  ([`19725e6`](https://github.com/nachollorca/promptuna/commit/19725e6c33567134d34d2257cab4d32f30c05040))

- **cookbook**: Include ipynotebooks
  ([`d82a789`](https://github.com/nachollorca/promptuna/commit/d82a7897c3f234090639e58c47b7fcc136a53ed8))

- **readme**: Add execution section
  ([`7da8d50`](https://github.com/nachollorca/promptuna/commit/7da8d5096e0a1f79d5a9f9af08d86b1cf58801f4))

### Features

- **jugdge**: Create a default LLM judge
  ([`ddff7f3`](https://github.com/nachollorca/promptuna/commit/ddff7f38bfddd54b38d1069be8eeb017acb4cea0))


## v1.1.0 (2026-05-17)

### Bug Fixes

- Point what TargetFunction does, and what is it expected to return
  ([`5533753`](https://github.com/nachollorca/promptuna/commit/55337530ce5e8b00009539238e0225eff69adc21))

### Code Style

- Reorder the datatypes module
  ([`13db39e`](https://github.com/nachollorca/promptuna/commit/13db39e6b034d69de93faadca7529d9790607472))

### Continuous Integration

- **execution**: Fix type hinting with casts
  ([`c46e66e`](https://github.com/nachollorca/promptuna/commit/c46e66ec543c2ff286b1c617e0077ba63b0d9e38))

- **init**: Make a module-level init so the package actually works
  ([`78269b9`](https://github.com/nachollorca/promptuna/commit/78269b9c8ed3468fb746a87b583ed48083483bec))

### Documentation

- Clarify failure rate and rendered prompt
  ([`1cd87fc`](https://github.com/nachollorca/promptuna/commit/1cd87fcaf5d18b1c8868534542e2adea5e184fad))

- Fix mermaid
  ([`a479ff8`](https://github.com/nachollorca/promptuna/commit/a479ff830e7929ea9eb2abedafc244ea9012d9c4))

- Log the action plan
  ([`1f27dbc`](https://github.com/nachollorca/promptuna/commit/1f27dbc5cfdc87813b315b49b55e799cff98d2b5))

- Minor adjustments to readme
  ([`d6a230a`](https://github.com/nachollorca/promptuna/commit/d6a230abe48dcd12adc87c1c42598c24540f79e5))

- Remove dated TODO
  ([`fc56da4`](https://github.com/nachollorca/promptuna/commit/fc56da44abbeaebc0c5bec2b5c6cefc682a7923e))

- Remove PLAN
  ([`4f59af5`](https://github.com/nachollorca/promptuna/commit/4f59af5603df327050e17830c76f57f669f6dcde))

- Some more alignment
  ([`83dd38e`](https://github.com/nachollorca/promptuna/commit/83dd38e8ddf907037cdeca90f3a7bf7d686bcd35))

- Split between spec and TODO
  ([`214a3cb`](https://github.com/nachollorca/promptuna/commit/214a3cb2ee5b40a36197d761207c30c1a6724c5e))

- Try to make sense of the full story
  ([`9a41f89`](https://github.com/nachollorca/promptuna/commit/9a41f8901580a933faff95f955652e4ffcb515c4))

### Features

- First implementation for execution
  ([`0763d9f`](https://github.com/nachollorca/promptuna/commit/0763d9f602d2a981f0ec32233fe8ac475df18ec3))

### Refactoring

- Change namings once again
  ([`6233746`](https://github.com/nachollorca/promptuna/commit/62337468690c93bdb8e1027b527ab6f8df75fe28))

- Dismiss datasets where some examples have references and some have not
  ([`f997b18`](https://github.com/nachollorca/promptuna/commit/f997b1828383f84a6ddf690c3fbd7cae2bae6756))

- Fix hint errors
  ([`b143e2d`](https://github.com/nachollorca/promptuna/commit/b143e2d7fe377fecb7e29b44192a196776773746))

- Store successes and errors separately for trials and scorings
  ([`9338d6a`](https://github.com/nachollorca/promptuna/commit/9338d6abc0b91d914c0ee822a5b79c772a138e54))

### Testing

- Upload an example of the doubt I have
  ([`2c34b30`](https://github.com/nachollorca/promptuna/commit/2c34b308b5c511080b2fb94f2a9a473da74befb5))


## v1.0.0 (2026-05-03)

- Initial Release
