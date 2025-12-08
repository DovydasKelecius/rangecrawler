# Contributing to RangeCrawler

Thank you for your interest in RangeCrawler!  
We’re two students building a modern, fully headless user-simulation framework for cyber ranges - every contribution helps, no matter how small, moves us closer to v1.0.

## Ways to Contribute
- Report bugs or request features → open an issue  
- Improve documentation → edit any file in `/docs` or the README  
- Fix typos, add examples, write tests  
- Submit code (agents, web UI, scenarios, health checks, Dockerfiles, etc.)

## How to Contribute

1. **Fork** the repository
2. Create a descriptive branch  
   ```bash
   git checkout -b fix/typo-readme
   git checkout -b feat/timeline-editor
   ```

Make your changes
Follow our Pull Request templates (bug fix / feature / docs)
Ensure the CI pipeline passes (if one is setup)
Open a Pull Request against the main branch


## Code Style & Requirements

Clean, readable code with comments where needed
All new features should have at least basic tests (when we add them)
Keep Docker images small and multi-platform
No telemetry or external calls without explicit opt-in

## License
By contributing, you agree that your contributions will be licensed under GNU GPL v3.0 - the same license as RangeCrawler.