"""Bounded, persistent C01 follow-up; deterministic analysis, never an LLM.

The frozen parent is passed in as verified bytes. Actions use only these bytes,
run in one SQLite transaction, and commit once. No network or external effects.
"""
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
import uuid


class LoopError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _rows(value):
    return list(csv.DictReader(io.StringIO(value.decode("utf-8-sig"))))


def _pearson(x, y):
    mx, my = sum(x)/len(x), sum(y)/len(y)
    a, b = [v-mx for v in x], [v-my for v in y]
    denominator = math.sqrt(sum(v*v for v in a)*sum(v*v for v in b))
    if denominator == 0:
        raise LoopError("INVALID_DATA", "变量没有变化，无法计算相关系数。")
    return sum(u*v for u,v in zip(a,b))/denominator


def residual_influence(predictions):
    """Describe held-out error concentration; never refit or select a model."""
    rows = _rows(predictions)
    outputs = []
    targets = ["cell_seeding_efficiency_24h_pct", "dna_cell_count_d21", "alp_norm_d21", "calcium_deposition_d21_ug_ml"]
    for target in targets:
        subset = [r for r in rows if r["round_id"] == "R1" and r["target"] == target]
        if len(subset) != 8 or len({r["sample_id"] for r in subset}) != 8:
            raise LoopError("INVALID_DATA", "原始逐折预测不完整。")
        errors = [{"sample_id":r["sample_id"], "absolute_error":abs(float(r["observed"])-float(r["predicted"]))} for r in subset]
        if any(not math.isfinite(e["absolute_error"]) for e in errors):
            raise LoopError("INVALID_DATA", "逐折误差不是有限数值。")
        total = sum(e["absolute_error"] for e in errors)
        largest = max(errors, key=lambda e:e["absolute_error"])
        outputs.append({"target":target,"sample_id":largest["sample_id"],"largest_error":largest["absolute_error"],
                        "share_of_absolute_error":largest["absolute_error"]/total if total else 0.0,
                        "all_errors":errors})
    return {"kind":"held_out_error_influence", "n":8, "targets":outputs,
            "interpretation":"逐折误差集中度是描述性诊断；删除样本后的重新建模、独立验证和新生物实验均未执行。"}


def correlation_influence(samples):
    """One exploratory pair, chosen after the historical dataset was seen."""
    rows = _rows(samples)
    if len(rows) != 8 or len({r["sample_id"] for r in rows}) != 8:
        raise LoopError("INVALID_DATA", "合金汇总样本不完整。")
    x = [float(r["water_contact_angle_deg"]) for r in rows]
    y = [float(r["cell_seeding_efficiency_24h_pct"]) for r in rows]
    if any(not math.isfinite(v) for v in x+y):
        raise LoopError("INVALID_DATA", "选定字段含非有限值。")
    full = _pearson(x,y)
    omitted = [{"sample_id":r["sample_id"],"pearson_r":_pearson(x[:i]+x[i+1:],y[:i]+y[i+1:])} for i,r in enumerate(rows)]
    return {"kind":"pair_correlation_influence","predictor":"water_contact_angle_deg",
            "outcome":"cell_seeding_efficiency_24h_pct","n":8,"pearson_r":full,"leave_one_out":omitted,
            "sign_changes":sum(1 for r in omitted if r["pearson_r"]*full < 0),
            "interpretation":"单对变量是在已见数据后选取的探索，逐一排除只做敏感性诊断；不作显著性、因果或临床推断。"}


class C01Loop:
    MAX_STEPS = 2
    def __init__(self, path, parent_manifest, files):
        self.root = Path(os.path.abspath(path))
        if os.path.normcase(str(self.root.resolve())) != os.path.normcase(str(self.root)):
            raise LoopError("UNSAFE_PATH", "研究目录不能经过符号链接或重定向。")
        self.db = self.root / "continuation.sqlite3"
        self.parent_sha = _sha(parent_manifest)
        self.code_sha = _sha(Path(__file__).read_bytes())
        self.predictions = files["loo_predictions.csv"]
        self.samples = files["cleaned_samples.csv"]
        self.input_sha = {"loo_predictions.csv":_sha(self.predictions),"cleaned_samples.csv":_sha(self.samples)}

    def _guard(self):
        for path in (self.root,*self.root.parents):
            if path.is_symlink() or getattr(path,"is_junction",lambda:False)():
                raise LoopError("UNSAFE_PATH", "研究目录包含重定向路径。")
        if self.root.exists():
            if not self.root.is_dir(): raise LoopError("UNSAFE_PATH", "研究目录不可用。")
            for p in self.root.iterdir():
                try:
                    meta=p.lstat()
                    if p.is_symlink() or getattr(p,"is_junction",lambda:False)() or p.name not in {"continuation.sqlite3", "continuation.sqlite3-journal", "continuation.sqlite3-wal", "continuation.sqlite3-shm"}:
                        raise LoopError("UNSAFE_PATH", "研究目录包含未知或重定向文件。")
                    if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:
                        raise LoopError("UNSAFE_PATH", "研究文件存在共享硬链接。")
                except FileNotFoundError:
                    pass

    def _connect(self, create=False):
        self._guard()
        if not self.root.exists():
            if not create: return None,False
            try: self.root.mkdir(parents=True,exist_ok=False)
            except FileExistsError: pass
            else:
                try:
                    fd=os.open(str(self.db),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                    os.close(fd)
                    new=True
                except OSError:
                    raise LoopError("INVALID_STATE", "无法安全初始化研究账本。") from None
                self._guard()
                connection=sqlite3.connect(self.db,timeout=10,isolation_level=None)
                connection.row_factory=sqlite3.Row
                connection.execute("PRAGMA busy_timeout=10000")
                return connection,new
        if not self.db.exists():
            raise LoopError("INVALID_STATE", "现有研究目录不完整，不能自动接管。")
        self._guard()
        connection = sqlite3.connect(self.db, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        return connection,False

    def _init(self, con, new=False):
        if new:
            con.execute("CREATE TABLE identity (id INTEGER PRIMARY KEY CHECK(id=1), parent_sha TEXT NOT NULL, input_json TEXT NOT NULL, version TEXT NOT NULL, code_sha TEXT NOT NULL)")
            con.execute("CREATE TABLE action (ordinal INTEGER PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, action_id TEXT UNIQUE NOT NULL, observation_sha TEXT NOT NULL, record_json TEXT NOT NULL, created_at REAL NOT NULL)")
        try:
            identity = con.execute("SELECT * FROM identity WHERE id=1").fetchone()
        except sqlite3.DatabaseError:
            raise LoopError("INVALID_STATE", "现有账本不是完整的 C01 研究账本。") from None
        expected = (self.parent_sha, _json(self.input_sha), "c01-continuation-v1", self.code_sha)
        if identity is None:
            if not new or con.execute("SELECT COUNT(*) FROM action").fetchone()[0]: raise LoopError("INVALID_STATE", "研究账本缺少身份。")
            con.execute("INSERT INTO identity VALUES(1,?,?,?,?)",expected)
        elif (identity["parent_sha"],identity["input_json"],identity["version"],identity["code_sha"]) != expected:
            raise LoopError("PARENT_MISMATCH", "原始快照或输入身份已变化，禁止继续。")

    def _state(self, con):
        actions = [json.loads(r["record_json"]) for r in con.execute("SELECT record_json FROM action ORDER BY ordinal")]
        if len(actions)>self.MAX_STEPS: raise LoopError("INVALID_STATE", "研究行动次数异常。")
        status = "idle" if not actions else "paused" if len(actions)<self.MAX_STEPS else "needs_review"
        return self._seal({"version":"c01-continuation-v1","parent_snapshot_sha256":self.parent_sha,"analysis_code_sha256":self.code_sha,"inputs":self.input_sha,
                "origin":"deterministic_local_policy_not_llm","status":status,"actions":actions,
                "budget":{"used":len(actions),"max":self.MAX_STEPS},"cloud_calls":0,"model_calls":0,
                "next_action":"检查逐折误差集中度" if not actions else "检查选定变量关联对单个合金的敏感性" if len(actions)==1 else "等待领域复核和独立反馈；当前不继续调参"})

    @staticmethod
    def _seal(value):
        return {**value,"observation_sha256":_sha(_json(value).encode("utf-8"))}

    def status(self):
        con, new = self._connect()
        if con is None:
            return self._seal({"version":"c01-continuation-v1","parent_snapshot_sha256":self.parent_sha,"analysis_code_sha256":self.code_sha,"inputs":self.input_sha,
                    "origin":"deterministic_local_policy_not_llm","status":"idle","actions":[],"budget":{"used":0,"max":self.MAX_STEPS},"cloud_calls":0,"model_calls":0,"next_action":"检查逐折误差集中度"}
            )
        try:
            con.execute("BEGIN")
            self._init(con,new)
            value = self._state(con)
            con.commit()
            return value
        except sqlite3.DatabaseError:
            con.rollback(); raise LoopError("INVALID_STATE", "研究账本不可用，未进行写入。") from None
        except BaseException:
            con.rollback(); raise
        finally: con.close()

    def step(self, request_id, observation_sha256):
        if not isinstance(request_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{12,100}",request_id):
            raise LoopError("INVALID_REQUEST", "请求编号无效。")
        con,new = self._connect(create=True)
        try:
            if new:
                # Persist the identity separately, so a stale request or a
                # failed pure calculation cannot strand an empty database.
                con.execute("BEGIN IMMEDIATE")
                self._init(con,True)
                con.commit()
            con.execute("BEGIN IMMEDIATE")
            self._init(con)
            existing = con.execute("SELECT record_json FROM action WHERE request_id=?",(request_id,)).fetchone()
            if existing:
                value=self._state(con);con.commit();return {"replayed":True,"state":value}
            observation=self._state(con)
            ordinal=observation["budget"]["used"]+1
            if ordinal>self.MAX_STEPS: raise LoopError("BUDGET_EXHAUSTED", "本轮两项分析已完成，等待人工复核。")
            if not isinstance(observation_sha256,str) or observation_sha256 != observation["observation_sha256"]:
                raise LoopError("STALE_OBSERVATION", "研究状态已变化；请刷新后再决定下一步。")
            obs_sha=observation["observation_sha256"]
            previous = [observation["actions"][-1]["id"]] if observation["actions"] else ["R1","R2"]
            if ordinal==1:
                output=residual_influence(self.predictions)
                title="逐折误差集中度"
                reason="首轮存在越界预测，先核对各终点误差是否由个别合金主导。"
                action="inspect_residual_influence"
            else:
                output=correlation_influence(self.samples)
                title="接触角与细胞接种：单样本敏感性"
                reason="前一步提示样本影响需核查；对已见数据中选定的材料—生物变量对逐一剔除合金作探索。"
                action="inspect_pair_sensitivity"
            record={"id":uuid.uuid4().hex,"request_id":request_id,"ordinal":ordinal,"action":action,"title":title,"decision_origin":"local_script_not_llm",
                    "reason":reason,"observation_sha256":obs_sha,"evidence_ids":previous,"input_sha256":self.input_sha,
                    "result":output,"decision":"继续检查关联敏感性" if ordinal==1 else "停止继续选模，等待标签、重复结构与独立反馈复核",
                    "limitations":["仅8个合金；已见数据后的探索，不是独立验证。","不证明临床有效性、因果关系或新发现。"]}
            con.execute("INSERT INTO action VALUES(?,?,?,?,?,?)",(ordinal,request_id,record["id"],obs_sha,_json(record),time.time()))
            value=self._state(con);con.commit();return {"replayed":False,"state":value}
        except sqlite3.DatabaseError:
            con.rollback(); raise LoopError("INVALID_STATE", "研究账本不可用，未进行写入。") from None
        except BaseException:
            con.rollback();raise
        finally: con.close()
