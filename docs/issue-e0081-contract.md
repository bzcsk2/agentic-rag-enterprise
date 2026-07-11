# E-008.1 Issue Contract — E-008 Consistency Remediation (narrow)

- **Parent issue:** E-008 (`139df74` + `a3ec258`) — CONDITIONAL FAIL on code-level audit.
- **Milestone:** M1 — Secure single-corpus data vertical slice.
- **Verdict basis:** `agentic-rag-enterprise-build-plan.md` §10.4, §10.5, §10.9, §10.10.
- **Scope:** narrow remediation of E-008 only. **No rollback of `139df74`.** No new
  runtime, no Planner/Evidence/multi-corpus. Reuses MetadataStore, IngestionJob,
  VectorStore, ParentStore, chunker, retriever.

```yaml
id: E-008.1
milestone: M1
depends_on: [E-008]
allowed_paths:
  - migrations/003_e0081_job_metadata.sql                # NEW
  - src/agentic_rag_enterprise/storage/metadata_store.py  # extend
  - src/agentic_rag_enterprise/ingestion/job.py           # extend (verify/compensate/idempotency/revision)
  - src/agentic_rag_enterprise/retrieval/retriever.py     # extend (control-plane active-version gate)
  - tests/unit/test_ingestion_job.py                       # extend
  - tests/integration/test_e008_ingestion_e2e.py          # extend
  - tests/integration/test_e008_crash_points.py           # extend
  - tests/unit/test_metadata_store.py                     # extend
  - docs/issue-e0081-contract.md
  - AGENTS.md
forbidden_paths:
  - /vol4/Agent/agentic-rag-for-dummies                   # upstream read-only
  - agents/ graph/ api/                                    # not in scope
rollback: "revert commit; drop migration 003 (ADD COLUMN idempotent via schema_migrations guard)"
```

## 1. 目标 (Goals)

收口 E-008 审计发现的 7 个直接对应 build plan MUST 的问题（P1-1…P1-7）。基础
MetadataStore / migration / IngestionJob / 测试保留。

## 2. 修复项 ↔ build plan

### P1-1 控制面 active-version gate（§10.10 #5）

检索在 Qdrant `status=active & deprecated=false` 过滤之外，再叠加 **Metadata DB
当前 active version** 过滤：命中点的 `document_version` 必须等于该 `(tenant,corpus,
document)` 的控制面 active version，否则剔除（不进入 Parent/模型路径）。`SecureRetriever`
注入可选 `metadata_store`； gate 仅在注入时生效（E-007 测试不受影响）。修复后：DB 已
切 v2、但 v1 Qdrant 点尚未清理时，检索**不返回 v1**（返回空，直到 publish 完成）。

### P1-2 幂等按 `document_id + version + content_hash`（§10.4）

提前返回 `ALREADY_INDEXED` 的条件改为：同一 `(tenant,corpus,document,version)` 已存在
**且 content_hash 相同** → 无论 `job_id` 是否相同，均 `ALREADY_INDEXED`，不修改 active
行、不重写数据面。同一 version + 不同 content_hash → 抛 `VersionContentConflict`，不覆盖
既有版本。

### P1-3 `base_lifecycle_revision` 持久化 + 单调 revision（§10.10 #8）

Job 领取时计算并持久化 `base_revision = MAX(lifecycle_revision)`（所有版本，不依赖 active
行）。提交时**只使用该持久值**作为 CAS `expected_revision`，不再提交前临时读取最新值。
`get_current_revision` 改为 `SELECT MAX(lifecycle_revision) FROM documents WHERE
(tenant,corpus,document)`（覆盖删除后无 active 行的竞争保护）。`commit_active_version`
读取单调 MAX 作 CAS，返回并持久化本次替换的 `previous_active_version`。

### P1-4 `verify` 步骤（§10.10 #4）

在 `write_qdrant` 与 `commit` 之间插入可重入 `verify` step：验证预期 Parent ID 全部存在、
预期 Child/Qdrant Point ID 全部存在、tenant/corpus/document/version/parent_id 身份一致、
数量与 chunk 结果一致、新版本仍为未提交（processing）状态；成功后写 `verify` step marker。

### P1-5 失败补偿完整性（§10.5 / §10.10 #7）

- `ActiveVersionConflict` 与通用异常统一走**同一幂等补偿**（不再单独标记 failed 而不清理）。
- 补偿不依赖内存列表：通过 `_ensure_chunked()` 确定性重建 + Metadata DB `chunks` 记录，
  删除本版本 Parent Store 条目、Qdrant processing 点、控制面 `chunks` 记录，并将 processing
  文档行置 `failed`。所有路径幂等。

### P1-6 `job_id` 不可变请求绑定

`validate_job_identity(job_id, tenant, corpus, document, version, raw_hash)` 在修改
Document 行之前执行；若 `job_id` 已存在且任一身份字段不一致 → 抛 `JobIdentityConflict`。

### P1-7 publish 只处理被替换的旧 active（§10.10 #2/#8）

`commit_active_version` 返回并持久化 `previous_active_version`；`publish` 只 deprecate 该
版本，不再扫描全部非 active 版本（避免误伤并发 Job 的 processing 版本）。

## 3. 非阻断（同批低成本收口）

- `run(max_step=...)` 部分完成返回 `IN_PROGRESS`（非 `INDEXED`），分离 crash 注入与生产 API。
- `_step_finalize` 真正构造并持久化 `IngestionManifest`（§10.9）至 `ingestion_jobs.manifest`。
- `apply_migrations` 将 DDL 与 `schema_migrations` marker 包进同一事务，避免崩溃导致重复加列。

## 4. 测试（build plan §23）

- `test_metadata_store.py`：`get_current_revision` 取 MAX、commit 返回 previous、身份冲突、
  manifest 持久化、迁移事务化。
- `test_ingestion_job.py`：不同 `job_id` 同 version+同 content → ALREADY_INDEXED；同 version+
  异 content → `VersionContentConflict`；base_revision CAS 拒绝旧 Job；verify 步骤；补偿清理
  chunk 记录与文档 failed。
- `test_e008_ingestion_e2e.py`：检索注入 metadata_store，验证 active-version gate。
- `test_e008_crash_points.py`：修正 #3 断言（DB active=v2 时旧版本不可见 → 返回空）；新增
  base_revision 旧 Job 覆盖场景、job 身份冲突场景。

## 5. 完成标准

`ruff` / `ruff format --check` / `mypy` / `pytest` / `pytest tests/baseline` 全绿；baseline 不破。
