# RangeCrawler Refactoring TODO

- [x] Create a single entry point `src/main.py` using `typer` for subcommands.
- [x] Refactor `src/agent/headless_client.py` to have a callable `run_agent()` function.
- [x] Create `src/dashboard/app.py` as a placeholder FastAPI app.
- [x] Update `src/broker/server.py` to support `RANGECRAWLER_CONFIG` environment variable.
- [x] Add `typer[all]` to `requirements.txt`.
- [x] Create `pyproject.toml` for packaging and `rangecrawler` command.
- [ ] Verify imports across all modules.
- [ ] Add `typer`'s rich help and auto-completion support (partially done via `add_completion=True`).
- [ ] (Optional) Add more subcommands if needed (e.g., `setup`, `test`).
- [x] Provide run examples and documentation for the new structure.
