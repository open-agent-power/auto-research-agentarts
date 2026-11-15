# S113：staged primary 真实进程竞争与中断验证

固定 HEAD `b714302b0258dbcebe43dcc4eed95ee67dd1458d`，在隔离合成Project用源码行 trace 同步、实际 SIGSTOP(19)/SIGKILL(-9)、独立 SQLite 只读连接核事务是否提交；trace 不替换产品方法或工具。独审将固定探针原样复制到新隔离目录，单 orchestrator 八场 exit0，原登记/parent/child/manager intent 的 claim 独立只读重算8/8。七个SIGKILL窗口 PID 101683/101707/101757/101819/101914/101987/102169；前五 adapter0、预算 used/reserved/dispatch=0/0/0，child已提交时 adapter0、0/1/1，存活竞争为锁忙、终止后原child/新ID停查；child完成而parent未终态时 adapter1、1/0/1，仍不重派。第八场 manager intent后暂停PID102282，旧Controller PID102292真实抢先执行一次合成工具，原strict未再次派发；resume/same-body EVIDENCE_CHANGED，异body IDEMPOTENCY_CONFLICT，原状态不变。

作者探针 `runs/s113-verification/multiprocess_probe.py` SHA `a4634a8bdc158d169bc9fe8cd35fc73274ae5aedb3b7f9157006b67b11a8297a`，作者证据manifest SHA `e3ac56f59996ef2d81d897d28ef782822893c3a3e49128d7ecbae099a0dcb8cd`；独审结果 `runs/s113-independent-review/cases-race-fixed4/index.json` SHA `e684c28ab063b21d069edd9b01e080f0aa54bd4514f8e2e8a72dcfbe09a91742`。作者7窗和抢先来自分开运行，非一次全程成功：fixed2因同步点重复SIGSTOP超时，fixed3把实际 EVIDENCE_CHANGED误认失败；原日志/现场保留。三个未提交窗口rollback journal未清理。

仅验证选定合成进程切点与竞争，不证明断电或恶意进程隔离；无真实Project/模型/研究行动。页面尚无原future ID执行入口；后续须明确可能消耗1工具及其中dev/validation ranking/score，unknown只沿原ID停查。
