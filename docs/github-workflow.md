# GitHub workflow

Matrix is for coordination. GitHub is for code.

## Project registry

`projects/registry.yaml` records the canonical repository, Matrix room, local clone on each machine, responsible agent, and deployment target. Add a project before asking an agent to code in it.

## Required path

1. Mo explicitly mentions an agent in the relevant project room.
2. Create or identify a GitHub issue.
3. Use the registered local clone on the agent's machine.
4. Create `agent/<agent-id>/<issue>-<slug>` from the current default branch.
5. Run the project's tests.
6. Commit and push only the intended branch.
7. Open a pull request and post its URL and verification summary in the originating Matrix thread.
8. Mention another agent if review is needed.
9. Mo approves merge and release.

## Prohibited without separate explicit approval

- Direct pushes to `main`.
- Force pushes.
- Repository deletion.
- Production deployment.
- Credential creation, printing, rotation, or storage changes.
- Spending money or changing paid service settings.

## Credentials

Do not distribute Mo's broad personal token. Prefer a GitHub App limited to assigned repositories. Until then, use separate fine-grained per-machine credentials with no delete or administration rights. The hub repository itself should demonstrate branch protection and required checks before autonomous coding is relaxed.
