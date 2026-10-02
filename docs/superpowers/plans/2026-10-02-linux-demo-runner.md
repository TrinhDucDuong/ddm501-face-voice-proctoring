# Linux demo runner implementation plan

**Goal:** Run `deploy-demo` on this machine without executing the Windows runner binary blocked by Code Integrity.

**Architecture:** GitHub Actions uses a self hosted Ubuntu WSL runner. Its checkout lives on drive C, so Windows PowerShell can verify the exact SHA, stage source outside OneDrive, and use the existing Docker Desktop Compose project, `.env`, mounts, and volumes. Only protected `main` deploys.

**Constraints:** Keep biometric data and tokens local. Do not relax Windows Code Integrity or replace the local deploy with a no-op. Preserve the existing quality and container jobs. Verify the GitHub run, services, DAGs, and Grafana after deployment.

## Tasks

- [ ] Configure Ubuntu runner with label `ddm501-linux-demo`, checkout on drive C, and a persistent service.
- [ ] Add a Windows deployment script that checks the exact Git SHA, stages the release, builds with Compose, waits for health, and verifies monitoring.
- [ ] Change only the `deploy-demo` workflow job to use the Linux label and invoke the Windows deployment script through WSL interop.
- [ ] Run a local cross-OS preflight, then push to FSB `main` and watch the GitHub run through `deploy-demo`.
- [ ] Confirm service endpoints and both Airflow DAGs; record the new runner instructions in `OPERATIONS.md`.
