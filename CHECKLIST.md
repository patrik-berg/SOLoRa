# SOLoRa – Codex Checklist

Before treating any feature, bug fix, or substantial change as complete, verify every applicable item:

1. The task is understood and the implementation follows the existing architecture.
2. Every relevant file has been updated.
3. Unrelated changes have been avoided.
4. Tests have been added or updated.
5. All relevant tests pass.
6. The backend and frontend build without errors.
7. Documentation is updated when behavior, protocol, or architecture changes.
8. The change remains backward-compatible where practical.
9. Database and migration changes preserve existing data safely.
10. The SOLoRa radio protocol sends no unnecessary bytes or packets.
11. The principle **Normal state is silent** is preserved.
12. User traffic has priority over background synchronization.
13. No API keys, passwords, tokens, or other secrets are committed.
14. Git status is understood and the intended changes are ready to commit.
15. The commit message is short, clear, and follows the repository convention.
16. Any CI or GitHub Actions impact has been verified.
17. The change can be built as a Beta without automatically affecting Stable.
18. The final Swedish summary for Patrik states:
    - what changed;
    - which tests were run;
    - whether everything passed;
    - what, if anything, still needs manual testing.

If an applicable item is not satisfied, fix it before declaring the task complete. Mark genuinely non-applicable items as such rather than inventing verification.
